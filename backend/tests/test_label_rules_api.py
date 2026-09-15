"""Confirmed-label API tests using only synthetic labels and an in-memory DB."""

import atexit
from datetime import date
import os
from pathlib import Path
import tempfile
import unittest

_scratch = tempfile.TemporaryDirectory(prefix=".test-run-label-api-", dir=Path(__file__).resolve().parents[1])
atexit.register(_scratch.cleanup)
os.environ["SPENDA_DB_URL"] = "sqlite://"
os.environ["SPENDA_UPLOAD_DIR"] = _scratch.name
os.environ["SPENDA_LLM_ENABLED"] = "false"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api import accounts, categories, rules
from app.db import Base, get_db


class LabelRulesApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False, autoflush=False)
        self.account = models.Account(name="Synthetic bank one")
        self.other_account = models.Account(name="Synthetic bank two")
        self.rent = models.Category(name="Rent")
        self.other_category = models.Category(name="Other")
        self.db.add_all([self.account, self.other_account, self.rent, self.other_category])
        self.db.commit()
        app = FastAPI()
        for router in (rules.router, accounts.router, categories.router):
            app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def payload(self, **overrides):
        data = {"account_id": self.account.id, "label": "Example Label", "direction": "debit", "category_id": self.rent.id}
        return {**data, **overrides}

    def create_mapping(self, **overrides):
        response = self.client.post("/rules/labels", json=self.payload(**overrides))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_upsert_normalizes_whitespace_and_case_with_stable_id(self):
        created = self.create_mapping(label="  EXAMPLE\t Label\n")
        self.assertEqual(created["label"], "example label")
        updated = self.create_mapping(label="Example   label", category_id=self.other_category.id)
        self.assertEqual(updated["id"], created["id"])
        self.assertEqual(updated["category_id"], self.other_category.id)
        self.assertEqual(self.db.query(models.StatementLabelRule).count(), 1)
        unicode_rule = self.create_mapping(label="Straße")
        self.assertEqual(unicode_rule["label"], "strasse")
        self.assertEqual(self.create_mapping(label="STRASSE")["id"], unicode_rule["id"])

    def test_same_label_can_have_different_account_and_direction_mappings(self):
        debit = self.create_mapping()
        credit = self.create_mapping(direction="credit", category_id=self.other_category.id)
        other_account = self.create_mapping(account_id=self.other_account.id, category_id=self.other_category.id)
        self.assertEqual(len({debit["id"], credit["id"], other_account["id"]}), 3)
        response = self.client.get("/rules/labels", params={"account_id": self.account.id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual({row["id"] for row in response.json()}, {debit["id"], credit["id"]})
        self.assertEqual(len(self.client.get("/rules/labels").json()), 3)

    def test_database_rejects_duplicate_scoped_key(self):
        self.create_mapping()
        self.db.add(models.StatementLabelRule(**self.payload(label="example label")))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.query(models.StatementLabelRule).count(), 1)

    def test_invalid_direction_or_label_is_rejected_without_insert(self):
        for overrides in (
            {"direction": "outgoing"}, {"direction": "DEBIT"}, {"label": " \t\n"},
            {"label": ""}, {"label": "x" * 256}, {"label": "ß" * 128}, {"label": None},
        ):
            with self.subTest(overrides=overrides):
                response = self.client.post("/rules/labels", json=self.payload(**overrides))
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.db.query(models.StatementLabelRule).count(), 0)

    def test_missing_account_or_category_is_rejected(self):
        for overrides in ({"account_id": 99999}, {"category_id": 99999}):
            with self.subTest(overrides=overrides):
                response = self.client.post("/rules/labels", json=self.payload(**overrides))
                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.client.get("/rules/labels?account_id=99999").status_code, 404)
        self.assertEqual(self.db.query(models.StatementLabelRule).count(), 0)

    def test_delete_mapping_and_missing_mapping(self):
        mapping = self.create_mapping()
        response = self.client.delete(f"/rules/labels/{mapping['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(self.client.get("/rules/labels").json(), [])
        self.assertEqual(self.client.delete(f"/rules/labels/{mapping['id']}").status_code, 404)

    def test_account_deletion_removes_only_its_mappings(self):
        self.create_mapping()
        kept = self.create_mapping(account_id=self.other_account.id)
        response = self.client.delete(f"/accounts/{self.account.id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row["id"] for row in self.client.get("/rules/labels").json()], [kept["id"]])

    def test_category_deletion_removes_only_its_mappings(self):
        self.create_mapping()
        kept = self.create_mapping(direction="credit", category_id=self.other_category.id)
        response = self.client.delete(f"/categories/{self.rent.id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row["id"] for row in self.client.get("/rules/labels").json()], [kept["id"]])

    def test_saving_and_deleting_mapping_does_not_recategorize_existing_transactions(self):
        transaction = models.Transaction(
            account_id=self.account.id, posted_at=date(2026, 9, 16),
            description="Synthetic description", merchant="Synthetic merchant", note="Example Label",
            raw_amount=-100, direction="debit", category_id=self.other_category.id,
            category_source="fallback", fingerprint="synthetic-confirmed-label",
        )
        self.db.add(transaction)
        self.db.commit()
        mapping = self.create_mapping()
        self.db.refresh(transaction)
        self.assertEqual((transaction.category_id, transaction.category_source), (self.other_category.id, "fallback"))
        self.client.delete(f"/rules/labels/{mapping['id']}")
        self.db.refresh(transaction)
        self.assertEqual((transaction.category_id, transaction.category_source), (self.other_category.id, "fallback"))


if __name__ == "__main__":
    unittest.main()
