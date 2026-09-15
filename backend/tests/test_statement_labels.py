"""Synthetic label regressions; never read a user's statement or database."""

import atexit
from datetime import date
from io import BytesIO
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_scratch = tempfile.TemporaryDirectory(prefix=".test-run-labels-", dir=Path(__file__).resolve().parents[1])
atexit.register(_scratch.cleanup)
os.environ["SPENDA_DB_URL"] = "sqlite://"
os.environ["SPENDA_UPLOAD_DIR"] = _scratch.name
os.environ["SPENDA_LLM_ENABLED"] = "false"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import xlwt

from app import models
from app.api import admin, analytics, export, rules, transactions, upload
from app.categorize import service
from app.categorize.autogrow import autogrow_categories
from app.db import Base, get_db
from app.parsers.utils import extract_merchant, extract_upi_metadata


ICICI_UPI = "UPI/Example Receiver/example@upi/Rent/Example Bank/123456789012/AXIabcdef1234567890/"
MISLEADING_MERCHANT = "UPI/Apollo Example/example@upi/Rent/Example Bank/123456789012/AXIabcdef1234567890/"
CANARA_UPI = "UPI/DR/123456789012/EXAMPLE/BANK/example@upi/GROCERY//AXIabcdef1234567890/16/09/2026 13:08:32 - rent"


class StatementLabelParserTests(unittest.TestCase):
    def test_icici_upi_fields_do_not_treat_transaction_reference_as_purpose(self):
        metadata = extract_upi_metadata(ICICI_UPI)
        self.assertEqual(metadata.get("user_label"), "Rent")
        self.assertEqual(metadata.get("receiver"), "Example Receiver")
        self.assertEqual(metadata.get("vpa"), "example@upi")
        self.assertEqual(metadata.get("ref"), "123456789012")
        self.assertNotEqual(metadata.get("purpose"), "AXIabcdef1234567890")

    def test_icici_upi_merchant_is_receiver_rather_than_user_label(self):
        self.assertEqual(extract_merchant(ICICI_UPI), "Example Receiver")

    def test_imps_and_neft_labels_are_distinct_from_receiver(self):
        cases = [
            ("MMT/IMPS/123456789012/Self/Example Receiver/Example Bank", "Self"),
            ("BIL/NEFT/IN123456789012/Rent/Example Receiver/Example Bank", "Rent"),
        ]
        for description, label in cases:
            with self.subTest(description=description):
                metadata = extract_upi_metadata(description)
                self.assertEqual(metadata.get("user_label"), label)
                self.assertEqual(metadata.get("receiver"), "Example Receiver")
                self.assertEqual(extract_merchant(description), "Example Receiver")

    def test_canara_timestamp_label_and_structured_fields_are_preserved(self):
        metadata = extract_upi_metadata(CANARA_UPI)
        self.assertEqual(metadata.get("user_label"), "rent")
        self.assertEqual(metadata.get("direction"), "debit")
        self.assertEqual(metadata.get("receiver"), "EXAMPLE")
        self.assertEqual(metadata.get("ref"), "123456789012")
        self.assertEqual(metadata.get("purpose"), "GROCERY")


class StatementLabelFlowTests(unittest.TestCase):
    def setUp(self):
        upload_settings = patch.object(upload, "get_settings", return_value=SimpleNamespace(upload_dir=_scratch.name))
        upload_settings.start()
        self.addCleanup(upload_settings.stop)
        # Pin this despite another test module having cached application settings.
        category_settings = patch.object(service, "get_settings", return_value=SimpleNamespace(llm_enabled=False))
        category_settings.start()
        self.addCleanup(category_settings.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False, autoflush=False)
        self.account = models.Account(name="Synthetic ICICI", kind="bank", institution="ICICI", currency="INR")
        self.rent = models.Category(name="Rent")
        self.health = models.Category(name="Healthcare")
        self.other = models.Category(name="Other")
        self.db.add_all([self.account, self.rent, self.health, self.other])
        self.db.flush()
        self.db.add_all([
            models.Rule(pattern="apollo", category_id=self.health.id, priority=1),
            models.Rule(pattern="rent", category_id=self.rent.id, priority=100),
        ])
        self.db.commit()
        app = FastAPI()
        app.include_router(upload.router)
        app.include_router(rules.router)
        app.include_router(admin.router)
        app.include_router(analytics.router)
        app.include_router(transactions.router)
        app.include_router(export.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def transaction(self, *, category_id=None, source="fallback", note=None, description=MISLEADING_MERCHANT):
        transaction = models.Transaction(
            account_id=self.account.id, posted_at=date(2026, 9, 16),
            description=description, merchant="Apollo Example", raw_amount=-15000,
            direction="debit", category_id=category_id, category_source=source,
            note=note, fingerprint=f"synthetic-label-{self.db.query(models.Transaction).count()}",
        )
        self.db.add(transaction)
        self.db.commit()
        return transaction

    def run_action(self, path):
        response = self.client.post(path)
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()

    def test_real_xls_upload_prefers_label_over_conflicting_merchant_rule(self):
        workbook = xlwt.Workbook()
        sheet = workbook.add_sheet("Synthetic Statement")
        for row_index, values in enumerate([
            ["Transaction Date", "Description", "Debit", "Credit"],
            ["16/09/2026", MISLEADING_MERCHANT, 15000, ""],
        ]):
            for column_index, value in enumerate(values):
                sheet.write(row_index, column_index, value)
        stream = BytesIO()
        workbook.save(stream)
        self.assertTrue(stream.getvalue().startswith(bytes.fromhex("D0CF11E0A1B11AE1")))
        response = self.client.post(
            "/upload", data={"account_id": self.account.id},
            files={"file": ("synthetic-labels.xls", stream.getvalue(), "application/vnd.ms-excel")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["inserted"], 1)
        transaction = self.db.query(models.Transaction).one()
        self.assertEqual(transaction.category_id, self.rent.id)
        self.assertEqual(transaction.category_source, "upi_label")
        self.assertEqual(transaction.note, "Rent")
        self.assertEqual(transaction.merchant, "Apollo Example")
        self.assertEqual(transaction.raw_amount, -15000)

    def test_recategorize_preserves_label_precedence(self):
        transaction = self.transaction(category_id=self.rent.id, source="upi_label", note="Rent")
        self.run_action("/rules/recategorize")
        self.assertEqual((transaction.category_id, transaction.category_source), (self.rent.id, "upi_label"))

    def test_reparse_recovers_label_precedence_and_note(self):
        transaction = self.transaction(category_id=self.health.id, source="rule")
        self.run_action("/admin/reparse-merchants")
        self.assertEqual((transaction.category_id, transaction.category_source), (self.rent.id, "upi_label"))
        self.assertEqual((transaction.merchant, transaction.note), ("Apollo Example", "Rent"))

    def test_both_actions_preserve_manual_category_and_note(self):
        transaction = self.transaction(category_id=self.other.id, source="user", note="My existing note")
        for path in ("/rules/recategorize", "/admin/reparse-merchants"):
            with self.subTest(path=path):
                self.run_action(path)
                self.assertEqual((transaction.category_id, transaction.category_source), (self.other.id, "user"))
                self.assertEqual(transaction.note, "My existing note")

    def test_recategorize_refreshes_source_when_category_is_unchanged(self):
        transaction = self.transaction(category_id=self.rent.id, description=ICICI_UPI)
        transaction.merchant = "Example Receiver"
        self.db.commit()
        self.run_action("/rules/recategorize")
        self.assertEqual((transaction.category_id, transaction.category_source), (self.rent.id, "upi_label"))

    def test_reparse_refreshes_source_when_category_is_unchanged(self):
        transaction = self.transaction(category_id=self.rent.id, description=ICICI_UPI)
        self.run_action("/admin/reparse-merchants")
        self.assertEqual((transaction.category_id, transaction.category_source), (self.rent.id, "upi_label"))

    def test_unknown_explicit_note_is_not_overridden_by_merchant_or_autogrow(self):
        description = MISLEADING_MERCHANT.replace("/Rent/", "/Needs explanation/")
        first = self.transaction(description=description)
        second = self.transaction(description=description)
        self.run_action("/rules/recategorize")
        for transaction in (first, second):
            self.assertEqual((transaction.category_id, transaction.category_source), (self.other.id, "label_review"))
            self.assertEqual(transaction.note, "Needs explanation")
        self.assertEqual(autogrow_categories(self.db)["reassigned"], 0)

    def test_bank_and_reference_fields_cannot_trigger_categories(self):
        self.db.add(models.Rule(pattern="rent", category_id=self.rent.id, priority=0, note="seed"))
        self.db.commit()
        description = "UPI/Unknown Receiver/apollo@upi/payment on/Rent Bank/123456789012/ApolloReference/"
        category, source = service.categorize_statement_row(self.db, description=description, direction="debit")
        self.assertEqual((category, source), (self.other.id, "fallback"))

    def test_confirmed_mapping_overrides_rules_only_for_its_account_and_direction(self):
        self.db.add(models.StatementLabelRule(account_id=self.account.id, label="rent", direction="debit", category_id=self.other.id))
        self.db.commit()
        arguments = dict(description=ICICI_UPI, account_id=self.account.id, direction="debit")
        self.assertEqual(service.categorize_statement_row(self.db, **arguments), (self.other.id, "upi_label"))
        self.assertEqual(service.categorize_statement_row(self.db, **{**arguments, "direction": "credit"}), (self.rent.id, "upi_label"))
        self.assertEqual(service.categorize_statement_row(self.db, **{**arguments, "account_id": self.account.id + 100}), (self.rent.id, "upi_label"))

    def test_confirmed_generic_bank_note_is_used_before_merchant_fallback(self):
        description = MISLEADING_MERCHANT.replace("/Rent/", "/payment on/")
        self.db.add(models.StatementLabelRule(account_id=self.account.id, label="payment on", direction="debit", category_id=self.rent.id))
        self.db.commit()
        transaction = self.transaction(description=description)
        self.run_action("/rules/recategorize")
        self.assertEqual((transaction.category_id, transaction.category_source), (self.rent.id, "upi_label"))

    def test_exact_category_labels_still_respect_direction_unless_confirmed(self):
        for name, direction in [("Salary", "debit"), ("Interest Income", "debit"), ("Loan Given", "credit")]:
            category = models.Category(name=name)
            self.db.add(category)
            self.db.commit()
            description = ICICI_UPI.replace("/Rent/", f"/{name}/")
            args = dict(description=description, direction=direction, account_id=self.account.id)
            self.assertEqual(service.categorize_statement_row(self.db, **args), (self.other.id, "label_review"))
            self.db.add(models.StatementLabelRule(account_id=self.account.id, label=name.casefold(), direction=direction, category_id=category.id))
            self.db.commit()
            self.assertEqual(service.categorize_statement_row(self.db, **args), (category.id, "upi_label"))

    def test_only_uncategorized_includes_notes_waiting_for_confirmation(self):
        transaction = self.transaction(category_id=self.other.id, source="label_review", description=ICICI_UPI)
        self.db.add(models.StatementLabelRule(account_id=self.account.id, label="rent", direction="debit", category_id=self.rent.id))
        self.db.commit()
        self.run_action(f"/rules/recategorize?only_uncategorized=true&account_id={self.account.id}")
        self.assertEqual((transaction.category_id, transaction.category_source), (self.rent.id, "upi_label"))

    def test_account_scoped_reparse_preserves_other_accounts_and_manual_merchant(self):
        other_account = models.Account(name="Unrelated account", kind="bank")
        self.db.add(other_account)
        self.db.commit()
        unrelated = self.transaction(category_id=self.health.id)
        unrelated.account_id = other_account.id
        manual = self.transaction(category_id=self.other.id, source="user", note="Keep this")
        manual.merchant = "My custom merchant"
        target = self.transaction(category_id=self.health.id)
        self.db.commit()
        self.run_action(f"/admin/reparse-merchants?account_id={self.account.id}")
        self.assertEqual(target.category_id, self.rent.id)
        self.assertEqual(unrelated.category_id, self.health.id)
        self.assertEqual((manual.merchant, manual.note, manual.category_source), ("My custom merchant", "Keep this", "user"))

    def test_review_summary_list_and_export_include_unclear_notes_but_not_manual_other(self):
        review = self.transaction(category_id=self.other.id, source="label_review", note="Needs explanation")
        self.transaction(category_id=self.other.id, source="user")
        self.assertEqual(self.client.get("/analytics/summary").json()["uncategorized_count"], 1)
        self.assertEqual([r["id"] for r in self.client.get("/transactions?category_id=0").json()], [review.id])
        import csv
        from io import StringIO
        exported = list(csv.DictReader(StringIO(self.client.get("/export/csv?category_id=0").text)))
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["category_source"], "label_review")
        result = self.client.patch(f"/transactions/{review.id}", json={"category_id": self.other.id})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get("/analytics/summary").json()["uncategorized_count"], 0)
        self.assertEqual(self.client.get("/transactions?category_id=0").json(), [])


if __name__ == "__main__":
    unittest.main()
