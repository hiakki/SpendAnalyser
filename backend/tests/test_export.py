"""CSV exports must match the selected ledger and preserve text as text."""
import csv
import io
import os
import unittest
from datetime import date
from pathlib import Path

# Safe even when unittest discovers this module before the other test modules.
os.environ["SPENDA_DB_URL"] = "sqlite://"
os.environ["SPENDA_LLM_ENABLED"] = "false"
os.environ["SPENDA_UPLOAD_DIR"] = str(Path(__file__).resolve().parents[2] / ".artifacts" / "test-uploads")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api.export import _spreadsheet_text, router
from app.db import Base, get_db


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        account = models.Account(name="QA account")
        category = models.Category(name="Groceries")
        self.db.add_all([account, category])
        self.db.flush()
        for i, (description, direction, category_id) in enumerate([
            ("=SUM(1,2)", "debit", None),
            ("Market purchase", "debit", category.id),
            ("Market refund", "credit", category.id),
        ]):
            self.db.add(models.Transaction(
                account_id=account.id, posted_at=date(2026, 9, 1), description=description,
                merchant="Market", raw_amount=-125.5 if direction == "debit" else 125.5,
                direction=direction, category_id=category_id, fingerprint=f"export-{i}",
            ))
        self.db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.category_id = category.id

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def rows(self, **params):
        response = self.client.get("/export/csv", params=params)
        self.assertEqual(response.status_code, 200)
        return list(csv.DictReader(io.StringIO(response.text)))

    def test_export_combines_filters_and_keeps_numeric_amounts(self):
        rows = self.rows(category_id=self.category_id, direction="debit", q="market", start="2026-09-01", end="2026-09-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Market purchase")
        self.assertEqual(rows[0]["amount"], "-125.50")
        self.assertEqual(self.rows(account_id=999), [])
        self.assertEqual(self.rows(start="2026-09-02"), [])

    def test_uncategorized_export_and_formula_escaping(self):
        rows = self.rows(category_id=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "'=SUM(1,2)")
        self.assertEqual(rows[0]["category"], "")

    def test_formula_prefixes_and_plain_text(self):
        for value in ["=1+1", "+1+1", "-1+1", "@SUM(1)", "  =1", "\ttext", "\rtext", "\ntext"]:
            with self.subTest(value=value):
                self.assertEqual(_spreadsheet_text(value), "'" + value)
        self.assertEqual(_spreadsheet_text("Coffee"), "Coffee")
        self.assertEqual(_spreadsheet_text(None), "")


if __name__ == "__main__":
    unittest.main()
