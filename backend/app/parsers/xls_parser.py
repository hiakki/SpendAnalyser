from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import ParseResult
from .table import dataframe_to_rows


def parse_xls(path: Path) -> ParseResult:
    result = ParseResult(detected_format="xls")
    sheets = pd.read_excel(path, sheet_name=None, dtype=str, header=None, engine=None)
    for sheet_name, raw in sheets.items():
        if raw is None or raw.empty:
            continue
        # detect header row: pick row with the most "header-like" tokens
        header_row = _detect_header_row(raw)
        if header_row is None:
            result.warnings.append(f"sheet '{sheet_name}': no header row detected, skipping")
            continue
        df = raw.iloc[header_row + 1 :].copy()
        df.columns = [str(c).strip() for c in raw.iloc[header_row].tolist()]
        df = df.dropna(how="all")
        rows = dataframe_to_rows(
            df,
            source_label=f"{path.name}::{sheet_name}",
            log=result.log,
            warnings=result.warnings,
        )
        result.rows.extend(rows)
    result.merge_period()
    return result


_HEADER_HINTS = {
    "date",
    "txn",
    "transaction",
    "description",
    "narration",
    "particulars",
    "details",
    "amount",
    "debit",
    "credit",
    "withdrawal",
    "deposit",
    "balance",
    "ref",
}


def _detect_header_row(df: pd.DataFrame) -> int | None:
    best = -1
    best_score = 0
    for i in range(min(len(df), 25)):
        row = df.iloc[i].astype(str).str.lower().tolist()
        score = sum(1 for cell in row for h in _HEADER_HINTS if h in cell)
        if score > best_score:
            best_score = score
            best = i
    return best if best_score >= 2 else None
