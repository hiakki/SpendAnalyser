from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional


@dataclass
class ParsedRow:
    posted_at: date
    description: str
    amount: float  # signed: negative = debit (spend), positive = credit (refund/income)
    currency: str = "INR"
    value_at: Optional[date] = None
    merchant: Optional[str] = None
    raw_row: Optional[str] = None  # source text for debugging
    user_label: Optional[str] = None  # explicit comment the user typed in their UPI/banking app

    @property
    def direction(self) -> str:
        return "credit" if self.amount > 0 else "debit"

    def fingerprint(self) -> str:
        """Stable hash to dedupe identical rows across re-uploads."""
        key = self.fingerprint_key()
        return hashlib.sha1(key.encode()).hexdigest()[:32]

    def fingerprint_key(self) -> str:
        """Natural transaction key used before adding duplicate occurrence info."""
        return f"{self.posted_at.isoformat()}|{round(self.amount, 2)}|{(self.description or '').strip().lower()}"

    def fingerprint_for_occurrence(self, occurrence: int) -> str:
        """Stable fingerprint that preserves repeated identical payments.

        The first occurrence keeps the historical fingerprint so old imports still
        dedupe correctly. Later occurrences add a deterministic suffix.
        """
        key = self.fingerprint_key()
        if occurrence > 1:
            key = f"{key}|occurrence:{occurrence}"
        return hashlib.sha1(key.encode()).hexdigest()[:32]


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    detected_format: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    log: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge_period(self) -> None:
        if not self.rows:
            return
        dates = [r.posted_at for r in self.rows]
        self.period_start = min(dates)
        self.period_end = max(dates)


def parse_file(path: Path, hint_kind: Optional[str] = None, password: Optional[str] = None) -> ParseResult:
    """Dispatch to the right parser based on suffix / mime.
    `password` only applies to PDFs (credit-card statements are commonly encrypted)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from .pdf_parser import parse_pdf

        return parse_pdf(path, password=password)
    if suffix in {".xls", ".xlsx"}:
        from .xls_parser import parse_xls

        return parse_xls(path)
    if suffix in {".csv", ".txt"}:
        from .csv_parser import parse_csv

        return parse_csv(path)
    raise ValueError(f"Unsupported file type: {suffix}")
