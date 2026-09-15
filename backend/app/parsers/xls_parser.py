from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import ParseResult
from .table import AMOUNT_COLS, CREDIT_COLS, DATE_COLS, DEBIT_COLS, DESC_COLS, _find_col, dataframe_to_rows


def parse_xls(path: Path) -> ParseResult:
    # Pandas inspects workbook contents, so a bank's mislabeled .xls/.xlsx
    # extension does not force the wrong reader. Both engines are dependencies.
    with pd.ExcelFile(path) as workbook:
        result = ParseResult(detected_format="xlsx" if workbook.engine == "openpyxl" else "xls")
        sheets = pd.read_excel(workbook, sheet_name=None, dtype=str, header=None)
    for sheet_name, raw in sheets.items():
        if raw is None or raw.empty:
            continue
        # Require actual transaction columns, not header words in bank notices.
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


def _detect_header_row(df: pd.DataFrame) -> int | None:
    for i in range(min(len(df), 100)):
        columns = [str(cell).strip() for cell in df.iloc[i].tolist() if pd.notna(cell)]
        date_col = _find_col(columns, DATE_COLS)
        desc_col = _find_col(columns, DESC_COLS)
        amount_col = _find_col(columns, DEBIT_COLS | CREDIT_COLS | AMOUNT_COLS)
        if date_col and desc_col and amount_col and len({date_col, desc_col, amount_col}) == 3:
            return i
    return None
