"""Synthetic regression tests. Never open the user's statements or database."""

import asyncio
import atexit
from datetime import date
from io import BytesIO
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

# Set storage before importing app modules; tests own and remove this directory.
_scratch = tempfile.TemporaryDirectory(prefix=".test-run-", dir=Path(__file__).resolve().parents[1])
atexit.register(_scratch.cleanup)
os.environ["SPENDA_DB_URL"] = "sqlite://"
os.environ["SPENDA_UPLOAD_DIR"] = _scratch.name
os.environ["SPENDA_LLM_ENABLED"] = "false"

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api import analytics, budgets, upload
from app.categorize.autogrow import autogrow_categories
from app.db import Base, get_db
from app.parsers.base import ParsedRow, ParseResult
from app.parsers.table import dataframe_to_rows
from app.parsers.utils import parse_amount


class ParserRegressionTests(unittest.TestCase):
    def parse(self, data):
        return dataframe_to_rows(pd.DataFrame(data), source_label="synthetic", log=[], warnings=[])

    def test_blank_debit_does_not_swallow_credit(self):
        rows = self.parse({"Date": ["15/09/2026"], "Description": ["Salary"], "Debit": [float("nan")], "Credit": [1250]})
        self.assertEqual([r.amount for r in rows], [1250])
        self.assertEqual(rows[0].direction, "credit")

    def test_short_column_alias_does_not_match_description_or_address(self):
        rows = self.parse({"Date": ["15/09/2026"], "Description": ["Synthetic store"], "Address": ["123"], "Amount": [-55]})
        self.assertEqual([r.amount for r in rows], [-55])

    def test_blank_description_is_not_imported_as_nan(self):
        self.assertEqual(self.parse({"Date": ["15/09/2026"], "Description": [float("nan")], "Amount": [-55]}), [])

    def test_first_statement_date_column_wins(self):
        rows = self.parse({"Transaction Date": ["15/09/2026"], "Value Date": ["16/09/2026"], "Description": ["Synthetic"], "Amount": [-55]})
        self.assertEqual(rows[0].posted_at, date(2026, 9, 15))

    def test_nonfinite_amounts_are_rejected(self):
        for value in (float("nan"), float("inf"), "-Infinity", "NaN"):
            with self.subTest(value=value):
                self.assertIsNone(parse_amount(value))
        self.assertEqual(parse_amount("1,250.50 CR"), 1250.5)
        self.assertEqual(parse_amount("(1,250.50)"), -1250.5)


class DatabaseRegressionTests(unittest.TestCase):
    def setUp(self):
        # Settings can already be cached by another test module. Pin the upload
        # endpoint to this suite's scratch directory regardless of import order.
        settings_patch = patch.object(upload, "get_settings", return_value=SimpleNamespace(upload_dir=_scratch.name))
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False, autoflush=False)
        self.account = models.Account(name="Synthetic bank", kind="bank", currency="INR")
        self.other = models.Category(name="Other")
        self.db.add_all([self.account, self.other])
        self.db.commit()
        app = FastAPI()
        app.include_router(analytics.router)
        app.include_router(upload.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def txn(self, description="Synthetic", amount=-100, posted_at=date(2026, 9, 15), **kwargs):
        row = ParsedRow(posted_at=posted_at, description=description, amount=amount)
        txn = models.Transaction(account_id=self.account.id, posted_at=posted_at, description=description,
                                 raw_amount=amount, direction=row.direction, fingerprint=row.fingerprint(), **kwargs)
        self.db.add(txn)
        self.db.commit()
        return txn

    def import_rows(self, rows):
        result = ParseResult(rows=rows)
        result.merge_period()
        with patch.object(upload, "parse_file", return_value=result), patch.object(upload, "autogrow_categories", return_value={"created_categories": [], "reassigned": 0, "loan_assigned": 0}):
            return asyncio.run(upload.upload_statement(account_id=self.account.id, file=UploadFile(filename="synthetic.csv", file=BytesIO(b"synthetic")), password=None, db=self.db))

    def test_duplicate_after_new_row_preserves_all_inserts(self):
        self.txn(description="Already imported", amount=-20)
        rows = [ParsedRow(date(2026, 9, 15), "New before duplicate", -10),
                ParsedRow(date(2026, 9, 15), "Already imported", -20),
                ParsedRow(date(2026, 9, 15), "New after duplicate", -30)]
        result = self.import_rows(rows)
        self.assertEqual((result.inserted, result.duplicates), (2, 1))
        self.assertEqual(self.db.query(models.Transaction).count(), 3)
        self.assertEqual(self.db.query(models.Transaction).filter_by(statement_id=result.statement.id).count(), 2)
        repeated = self.import_rows(rows)
        self.assertEqual((repeated.inserted, repeated.duplicates), (0, 3))
        self.assertEqual(self.db.query(models.Transaction).count(), 3)

    def test_identical_payments_retained_but_reupload_deduplicated(self):
        row = ParsedRow(date(2026, 9, 15), "Repeated payment", -45)
        self.assertEqual(self.import_rows([row, row]).inserted, 2)
        self.assertEqual(self.import_rows([row, row]).duplicates, 2)
        self.assertEqual(self.db.query(models.Transaction).count(), 2)

    def test_savepoint_handles_duplicate_missed_by_initial_lookup(self):
        self.txn(description="Already imported", amount=-20)
        rows = [ParsedRow(date(2026, 9, 15), "New before duplicate", -10),
                ParsedRow(date(2026, 9, 15), "Already imported", -20),
                ParsedRow(date(2026, 9, 15), "New after duplicate", -30)]
        original_query = self.db.query
        lookups = 0

        def query(*entities, **kwargs):
            nonlocal lookups
            result = original_query(*entities, **kwargs)
            if len(entities) == 1 and entities[0] is models.Transaction.id:
                lookups += 1
                if lookups == 2:
                    # Simulate a stale precheck; the actual unique constraint
                    # still fires on flush, exercising savepoint recovery.
                    original_filter = result.filter_by
                    def stale_filter(**filters):
                        filtered = original_filter(**filters)
                        filtered.first = lambda: None
                        return filtered
                    result.filter_by = stale_filter
            return result

        with patch.object(self.db, "query", side_effect=query):
            result = self.import_rows(rows)
        self.assertEqual((result.inserted, result.duplicates), (2, 1))
        self.assertEqual(self.db.query(models.Transaction).count(), 3)
        self.assertEqual(self.db.query(models.Transaction).filter_by(statement_id=result.statement.id).count(), 2)

    def test_multipart_csv_upload_and_reupload_flow(self):
        csv = b"Date,Description,Debit,Credit\n15/09/2026,Synthetic debit,12.50,\n15/09/2026,Synthetic credit,,90.00\n"
        response = self.client.post("/upload", data={"account_id": self.account.id}, files={"file": ("synthetic.csv", csv, "text/csv")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["inserted"], 2)
        totals = self.client.get("/analytics/summary").json()
        self.assertEqual((totals["spend"], totals["income"], totals["net"]), (12.5, 90, 77.5))
        repeated = self.client.post("/upload", data={"account_id": self.account.id}, files={"file": ("synthetic.csv", csv, "text/csv")})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual((repeated.json()["inserted"], repeated.json()["duplicates"]), (0, 2))
        self.assertEqual(self.db.query(models.Transaction).count(), 2)

    def test_failed_parse_removes_saved_file(self):
        before = set(Path(_scratch.name).iterdir())
        with patch.object(upload, "parse_file", side_effect=ValueError("synthetic parse error")):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(upload.upload_statement(account_id=self.account.id, file=UploadFile(filename="bad.csv", file=BytesIO(b"bad")), password=None, db=self.db))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(set(Path(_scratch.name).iterdir()), before)

    def test_monthly_totals_and_filtered_uncategorized_count(self):
        self.txn("Groceries", -125, category_id=self.other.id)
        self.txn("Salary", 1000)
        self.txn("Earlier", -10, posted_at=date(2026, 8, 1))
        response = self.client.get("/analytics/summary", params={"start": "2026-09-01", "account_id": self.account.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"spend": 125, "income": 1000, "net": 875, "n_transactions": 2, "uncategorized_count": 1})
        months = self.client.get("/analytics/by-month").json()
        self.assertEqual(months, [{"month": "2026-08", "spend": 10, "income": 0, "net": -10, "count": 1},
                                 {"month": "2026-09", "spend": 125, "income": 1000, "net": 875, "count": 2}])

    def test_invalid_date_range_and_merchant_limit_rejected(self):
        self.assertEqual(self.client.get("/analytics/summary?start=2026-09-20&end=2026-09-01").status_code, 422)
        self.assertEqual(self.client.get("/analytics/top-merchants?limit=-1").status_code, 422)

    def test_autogrow_preserves_user_other_choice(self):
        first = self.txn("First", -10, merchant="Synthetic Merchant", category_id=self.other.id, category_source="user")
        second = self.txn("Second", -20, merchant="Synthetic Merchant", category_id=self.other.id, category_source="user")
        result = autogrow_categories(self.db)
        self.assertEqual(result["reassigned"], 0)
        self.assertEqual((first.category_id, second.category_id), (self.other.id, self.other.id))

    def test_unknown_shop_and_person_remain_other_after_csv_upload(self):
        csv = b"Date,Description,Amount\n15/09/2026,UNRECOGNIZED SHOP,-195\n15/09/2026,RAJ GAUTAM,-200\n"
        response = self.client.post("/upload", data={"account_id": self.account.id}, files={"file": ("synthetic.csv", csv, "text/csv")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["inserted"], 2)
        rows = self.db.query(models.Transaction).all()
        self.assertEqual({row.category_id for row in rows}, {self.other.id})
        self.assertEqual({row.category_source for row in rows}, {"fallback"})
        self.assertIsNone(self.db.query(models.Category).filter_by(name="Loan Given").first())
        self.assertNotIn("Loan Given", " ".join(response.json()["warnings"]))

    def test_budget_override_and_constant_query_count(self):
        self.txn("Budget debit", -60, category_id=self.other.id)
        self.db.add_all([models.Budget(category_id=self.other.id, month="*", amount=100),
                         models.Budget(category_id=self.other.id, month="2026-09", amount=80)])
        self.db.add_all([models.Category(name=f"Synthetic category {index}") for index in range(20)])
        self.db.commit()
        queries = []
        def record(connection, cursor, statement, parameters, context, many):
            queries.append(statement)
        event.listen(self.engine, "before_cursor_execute", record)
        try:
            result = budgets.budget_status(month="2026-09", db=self.db)
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        self.assertEqual(len(queries), 3)
        self.assertEqual(result[0]["budget"], 80)
        self.assertEqual(result[0]["remaining"], 20)


if __name__ == "__main__":
    unittest.main()
