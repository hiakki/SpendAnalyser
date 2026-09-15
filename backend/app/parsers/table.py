from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from .base import ParsedRow
from .utils import extract_merchant, extract_upi_metadata, parse_amount, try_parse_date


DATE_COLS = {
    "date", "txn date", "transaction date", "posting date", "post date",
    "value date", "tran date", "trans date", "txn dt", "transaction dt",
    "transaction date & time",
}
DESC_COLS = {
    "description", "narration", "particulars", "details", "transaction details",
    "remarks", "memo", "narrative", "description / narration", "tran particulars",
    "transaction particulars", "transaction remarks",
}
DEBIT_COLS = {
    "debit", "debits", "withdrawal", "withdrawals", "withdrawal amt.",
    "withdrawal amount", "withdrawal amt", "withdrawal (dr)", "dr", "dr amount",
    "spent", "debit amount", "debit (rs.)",
}
CREDIT_COLS = {
    "credit", "credits", "deposit", "deposits", "deposit amt.",
    "deposit amount", "deposit amt", "deposit (cr)", "cr", "cr amount",
    "received", "credit amount", "credit (rs.)",
}
AMOUNT_COLS = {
    "amount", "amount (inr)", "amount (rs.)", "amount (rs)", "amount in inr",
    "amount(in rs)", "amount in rs.", "amount in rs", "transaction amount",
    "amt", "tran amount", "txn amount", "rs.", "rs", "inr",
}
TYPE_COLS = {"type", "dr/cr", "drcr", "dr / cr", "indicator", "dr/ cr"}


def _normalize(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _find_col(columns: list[str], candidates: set[str]) -> Optional[str]:
    norm = {_normalize(c): c for c in columns}
    # Respect statement column order when several aliases exist (for example
    # transaction date and value date), rather than unordered set iteration.
    for nc, orig in norm.items():
        if nc in candidates:
            return orig
    # partial match
    for nc, orig in norm.items():
        for cand in sorted(candidates, key=lambda value: (-len(value), value)):
            if re.search(r"(?<!\w)" + re.escape(cand) + r"(?!\w)", nc):
                return orig
    return None


def dataframe_to_rows(
    df: pd.DataFrame,
    *,
    source_label: str,
    log: list[str],
    warnings: list[str],
) -> list[ParsedRow]:
    if df is None or df.empty:
        return []
    columns = [str(c) for c in df.columns]
    date_col = _find_col(columns, DATE_COLS)
    desc_col = _find_col(columns, DESC_COLS)
    debit_col = _find_col(columns, DEBIT_COLS)
    credit_col = _find_col(columns, CREDIT_COLS)
    amount_col = _find_col(columns, AMOUNT_COLS)
    type_col = _find_col(columns, TYPE_COLS)

    if not date_col or not desc_col:
        warnings.append(f"{source_label}: missing date/description columns; found {columns}")
        return []
    if not (debit_col or credit_col or amount_col):
        warnings.append(f"{source_label}: missing amount columns; found {columns}")
        return []

    log.append(
        f"{source_label}: cols date={date_col} desc={desc_col} "
        f"debit={debit_col} credit={credit_col} amount={amount_col} type={type_col}"
    )

    out: list[ParsedRow] = []
    for _, row in df.iterrows():
        d = try_parse_date(str(row.get(date_col) or ""))
        if not d:
            continue
        desc_value = row.get(desc_col)
        desc = "" if pd.isna(desc_value) else str(desc_value).strip()
        if not desc:
            continue
        amount: Optional[float] = None
        if debit_col is not None or credit_col is not None:
            dr = parse_amount(row.get(debit_col)) if debit_col else None
            cr = parse_amount(row.get(credit_col)) if credit_col else None
            if dr and dr != 0:
                amount = -abs(dr)
            elif cr and cr != 0:
                amount = abs(cr)
        if amount is None and amount_col is not None:
            amount = parse_amount(row.get(amount_col))
            if amount is not None and type_col is not None:
                t = str(row.get(type_col) or "").strip().upper()
                if t in {"DR", "DEBIT", "WITHDRAWAL"} and amount > 0:
                    amount = -amount
                elif t in {"CR", "CREDIT", "DEPOSIT"} and amount < 0:
                    amount = abs(amount)
        if amount is None or amount == 0:
            continue
        meta = extract_upi_metadata(desc)
        out.append(
            ParsedRow(
                posted_at=d,
                description=desc,
                amount=amount,
                merchant=extract_merchant(desc),
                user_label=meta.get("user_label"),
                raw_row=" | ".join(str(v) for v in row.values),
            )
        )
    return out
