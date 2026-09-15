"""Generated PDFs cover text positioning and image-only diagnostics."""

import atexit
from datetime import date
from io import BytesIO
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_scratch = tempfile.TemporaryDirectory(prefix=".test-pdf-", dir=Path(__file__).resolve().parents[1])
atexit.register(_scratch.cleanup)
os.environ["SPENDA_DB_URL"] = "sqlite://"
os.environ["SPENDA_UPLOAD_DIR"] = _scratch.name
os.environ["SPENDA_LLM_ENABLED"] = "false"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
import pdfplumber
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.api import upload
from app.db import Base, get_db
from app.parsers.base import parse_file


_HEIGHT = 842
_BOUNDS = [19, 49, 119, 189, 390, 456, 522, 574]
_REPEATED_DESCRIPTION = ["SYNTHETIC MERCHANT", "Payment reference TEST123", "Synthetic wrapped narrative", "End of payment"]


def _text(pdf, x, top, text):
    # Helvetica's 8pt glyphs begin 6.344pt above their baseline, matching
    # pdfplumber's word.top coordinate without mocking PDF extraction.
    pdf.setFont("Helvetica", 8)
    pdf.drawString(x, _HEIGHT - top - 6.344, text)


def _header(pdf, top):
    bottom = top + 30
    for x in _BOUNDS:
        pdf.line(x, _HEIGHT - top, x, _HEIGHT - bottom)
    pdf.line(_BOUNDS[0], _HEIGHT - top, _BOUNDS[-1], _HEIGHT - top)
    pdf.line(_BOUNDS[0], _HEIGHT - bottom, _BOUNDS[-1], _HEIGHT - bottom)
    labels = [("S No.",), ("Transaction", "Date"), ("Cheque No.",),
              ("Transaction Remarks",), ("Withdrawal", "Amount (INR)"),
              ("Deposit", "Amount (INR)"), ("Balance (INR)",)]
    for x, lines in zip(_BOUNDS, labels):
        for index, label in enumerate(lines):
            _text(pdf, x + 3, top + 4 + index * 10, label)


def _transaction(pdf, serial, desc_top, description, amount, balance, posted="15.09.2026"):
    # Description begins five points above the date/money and continues below.
    _text(pdf, 22, desc_top + 5, str(serial))
    _text(pdf, 52, desc_top + 5, posted)
    for index, line in enumerate(description):
        _text(pdf, 192, desc_top + index * 10, line)
    _text(pdf, 393 if amount < 0 else 459, desc_top + 5, f"{abs(amount):,.2f}")
    _text(pdf, 525, desc_top + 5, f"{balance:,.2f}")


def statement_pdf_bytes():
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(595, _HEIGHT))
    _text(pdf, 20, 40, "Synthetic bank statement")
    _header(pdf, 210)
    _transaction(pdf, 1, 242, _REPEATED_DESCRIPTION, -195, 9805)
    _transaction(pdf, 2, 282, _REPEATED_DESCRIPTION, -195, 9610)
    _transaction(pdf, 3, 322, ["SYNTHETIC SALARY", "Monthly credit reference TEST456"], 1250, 10860)
    _text(pdf, 20, 780, "Synthetic page 1 of 2")
    pdf.showPage()
    _header(pdf, 77)
    _transaction(pdf, 4, 109, ["SYNTHETIC TRANSPORT", "Second page payment TEST789"], -80, 10780, posted="16.09.2026")
    _text(pdf, 20, 780, "Synthetic page 2 of 2")
    pdf.save()
    return output.getvalue()


class PdfParserTests(unittest.TestCase):
    def parse_bytes(self, payload, filename="synthetic.pdf"):
        path = Path(_scratch.name) / filename
        path.write_bytes(payload)
        return parse_file(path)

    def test_header_only_grid_preserves_wrapped_rows_and_second_page(self):
        payload = statement_pdf_bytes()
        # Prove the fixture has only header borders, not a fully ruled table.
        with pdfplumber.open(BytesIO(payload)) as document:
            self.assertEqual(len(document.pages), 2)
            self.assertEqual([len(page.extract_tables()[0]) for page in document.pages], [1, 1])
        result = self.parse_bytes(payload)
        self.assertEqual([row.amount for row in result.rows], [-195, -195, 1250, -80])
        self.assertEqual([row.direction for row in result.rows], ["debit", "debit", "credit", "debit"])
        self.assertEqual(result.rows[0].description, " ".join(_REPEATED_DESCRIPTION))
        self.assertEqual(result.rows[1].description, result.rows[0].description)
        self.assertEqual(result.rows[2].description, "SYNTHETIC SALARY Monthly credit reference TEST456")
        self.assertEqual(result.rows[3].description, "SYNTHETIC TRANSPORT Second page payment TEST789")
        self.assertEqual(result.period_start, date(2026, 9, 15))
        self.assertEqual(result.period_end, date(2026, 9, 16))
        self.assertFalse({9805, 9610, 10860, 10780} & {abs(row.amount) for row in result.rows})

    def test_unsupported_text_layout_is_not_reported_as_a_scan(self):
        output = BytesIO()
        pdf = canvas.Canvas(output)
        pdf.drawString(40, 700, "Synthetic readable account information without transaction rows")
        pdf.save()
        result = self.parse_bytes(output.getvalue(), "unsupported-text.pdf")
        self.assertEqual(result.rows, [])
        warnings = " ".join(result.warnings).lower()
        self.assertIn("text", warnings)
        self.assertIn("layout", warnings)
        self.assertNotIn("ocr required", warnings)
        self.assertNotIn("image-only", warnings)

    def test_description_alignment_can_change_between_rows(self):
        output = BytesIO()
        pdf = canvas.Canvas(output, pagesize=(595, _HEIGHT))
        _header(pdf, 77)
        # First narrative aligns with its date; the next begins above its date.
        _transaction(pdf, 1, 109, [], -100, 900)
        _text(pdf, 192, 114, "FIRST MERCHANT")
        _transaction(pdf, 2, 149, ["SECOND MERCHANT", "Second continuation"], -200, 700)
        pdf.save()
        result = self.parse_bytes(output.getvalue(), "mixed-alignment.pdf")
        self.assertEqual([row.description for row in result.rows], ["FIRST MERCHANT", "SECOND MERCHANT Second continuation"])
        self.assertEqual([row.amount for row in result.rows], [-100, -200])

    def test_image_only_pdf_explains_ocr_requirement(self):
        bitmap = Image.new("RGB", (600, 150), "white")
        ImageDraw.Draw(bitmap).text((10, 30), "Synthetic statement as image", fill="black")
        output = BytesIO()
        pdf = canvas.Canvas(output)
        pdf.drawImage(ImageReader(bitmap), 30, 600, width=500, height=125)
        pdf.save()
        result = self.parse_bytes(output.getvalue(), "synthetic-scan.pdf")
        self.assertEqual(result.rows, [])
        self.assertIn("ocr", " ".join(result.warnings).lower())


class PdfUploadTests(unittest.TestCase):
    def setUp(self):
        settings_patch = patch.object(upload, "get_settings", return_value=SimpleNamespace(upload_dir=_scratch.name))
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False, autoflush=False)
        self.account = models.Account(name="Synthetic PDF bank", kind="bank")
        self.db.add_all([self.account, models.Category(name="Other")])
        self.db.commit()
        app = FastAPI()
        app.include_router(upload.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_repeated_pdf_payments_survive_and_reupload_is_idempotent(self):
        payload = statement_pdf_bytes()
        response = self.client.post("/upload", data={"account_id": self.account.id}, files={"file": ("synthetic.pdf", payload, "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["inserted"], 4)
        repeated = self.client.post("/upload", data={"account_id": self.account.id}, files={"file": ("synthetic.pdf", payload, "application/pdf")})
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual((repeated.json()["inserted"], repeated.json()["duplicates"]), (0, 4))
        rows = self.db.query(models.Transaction).order_by(models.Transaction.id).all()
        self.assertEqual([row.raw_amount for row in rows], [-195, -195, 1250, -80])
        self.assertEqual(len({row.fingerprint for row in rows}), 4)


if __name__ == "__main__":
    unittest.main()
