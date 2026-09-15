from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pdfplumber

from .base import ParsedRow, ParseResult
from .table import CREDIT_COLS, DATE_COLS, DEBIT_COLS, DESC_COLS, _find_col, dataframe_to_rows
from .utils import extract_merchant, extract_upi_metadata, parse_amount, try_parse_date


def parse_pdf(path: Path, password: Optional[str] = None) -> ParseResult:
    """Multi-strategy parser:
       1. Detect bank-specific layouts (Canara passbook so far) and use a
          dedicated walker that handles multi-line transactions.
       2. Otherwise try `extract_tables` page-by-page; each table is fed
          through the same column-mapping logic as XLS/CSV.
       3. Fallback: regex over raw text lines for credit-card statements
          that are text-only ("DD MMM  Merchant Desc  1,234.56 [Dr|Cr]")."""
    result = ParseResult(detected_format="pdf")
    table_rows: list[ParsedRow] = []
    text_rows: list[ParsedRow] = []
    canara_rows: list[ParsedRow] = []
    has_text = False

    with pdfplumber.open(str(path), password=password) as pdf:
        first_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        has_text = bool(first_text.strip())
        is_canara = _looks_like_canara(first_text)

        if is_canara:
            # Use the bank-specific walker exclusively. The generic
            # text-fallback regex greedily grabs the balance column as the
            # amount on these multi-line passbook layouts, producing ghost
            # transactions with balance-sized debits.
            result.detected_format = "pdf-canara-passbook"
            result.log.append("detected Canara passbook format; using dedicated multi-line walker")
            for page_idx, page in enumerate(pdf.pages):
                canara_rows.extend(
                    _parse_canara_page(page, page_idx=page_idx + 1, log=result.log, warnings=result.warnings)
                )
        else:
            for page_idx, page in enumerate(pdf.pages):
                has_text = has_text or bool(page.chars)
                # Some bank PDFs draw a grid around the headings only. Reading
                # that grid as a table yields no data, while a text regex can
                # mistake the trailing running balance for the payment amount.
                positioned = _parse_header_grid_page(
                    page, source=f"p{page_idx + 1}", log=result.log, warnings=result.warnings,
                )
                if positioned is not None:
                    table_rows.extend(positioned)
                    result.detected_format = "pdf-positioned-columns"
                    continue
                try:
                    tables = page.extract_tables() or []
                except Exception as exc:  # noqa: BLE001
                    result.warnings.append(f"page {page_idx + 1} table extract failed: {exc}")
                    tables = []
                for ti, raw in enumerate(tables):
                    rows_from_table = _table_to_rows(raw, source=f"p{page_idx + 1}t{ti + 1}", log=result.log, warnings=result.warnings)
                    table_rows.extend(rows_from_table)

                try:
                    text = page.extract_text() or ""
                except Exception as exc:  # noqa: BLE001
                    result.warnings.append(f"page {page_idx + 1} text extract failed: {exc}")
                    text = ""
                text_rows.extend(_text_to_rows(text, source=f"p{page_idx + 1}", log=result.log))

    # Merge in priority: bank-specific > tables > text-fallback. Only suppress
    # rows that a higher-priority parser already found; repeated identical rows
    # within the same parser are real payments and must be preserved.
    merged: list[ParsedRow] = []
    seen_from_higher_priority: set[tuple] = set()
    for bucket in (canara_rows, table_rows, text_rows):
        bucket_keys: set[tuple] = set()
        for r in bucket:
            key = (r.posted_at, round(r.amount, 2), (r.description or "").strip().lower()[:60])
            if key in seen_from_higher_priority:
                continue
            merged.append(r)
            bucket_keys.add(key)
        seen_from_higher_priority.update(bucket_keys)

    result.rows = merged
    result.merge_period()
    if not merged:
        result.warnings.append(
            "No transactions recognized in this text PDF. Its statement layout is not yet supported."
            if has_text else
            "No readable text found in this PDF. Scanned statements require OCR; upload a text PDF or Excel export."
        )
    return result


def _parse_header_grid_page(page, *, source: str, log: list[str], warnings: list[str]) -> list[ParsedRow] | None:
    """Use a header-only grid's actual column bounds for borderless bank rows.

    None means this is not the supported layout. An empty list means the
    financial columns were recognized but no safe rows could be extracted:
    do not then guess amounts from the page's trailing balance column.
    """
    try:
        tables = page.find_tables()
    except Exception:
        return None
    layout = None
    for table in tables:
        if len(table.rows) != 1:
            continue
        columns = [" ".join((cell or "").split()) for cell in table.extract()[0]]
        names = {
            "date": _find_col(columns, DATE_COLS),
            "description": _find_col(columns, DESC_COLS),
            "debit": _find_col(columns, DEBIT_COLS),
            "credit": _find_col(columns, CREDIT_COLS),
        }
        if not all(names.values()) or len(set(names.values())) != 4:
            continue
        cells = {name: table.rows[0].cells[columns.index(column)] for name, column in names.items()}
        if any(cell is None for cell in cells.values()):
            continue
        layout = cells, table.bbox[3]
        break
    if layout is None:
        return None
    cells, header_bottom = layout
    words = [w for w in page.extract_words() if w["top"] >= header_bottom - 1]

    def in_column(word, column):
        left, _, right, _ = cells[column]
        center = (word["x0"] + word["x1"]) / 2
        return left <= center < right

    def lines(items):
        grouped = []
        for word in sorted(items, key=lambda w: (w["top"], w["x0"])):
            if not grouped or abs(word["top"] - grouped[-1][0]["top"]) > 2:
                grouped.append([word])
            else:
                grouped[-1].append(word)
        return [sorted(line, key=lambda w: w["x0"]) for line in grouped]

    anchors = []
    for line in lines([w for w in words if in_column(w, "date")]):
        raw = " ".join(w["text"] for w in line)
        # Do not let dateutil turn a stray page number into a transaction date.
        if not re.fullmatch(r"\d{1,4}[./-](?:\d{1,2}|[A-Za-z]{3,9})[./-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}", raw):
            continue
        parsed_date = try_parse_date(raw)
        if parsed_date:
            anchors.append((line[0]["top"], parsed_date, max(w["bottom"] - w["top"] for w in line)))
    if not anchors:
        warnings.append(f"{source}: transaction columns found but no valid dates; no amounts guessed")
        return []

    description_words = [w for w in words if in_column(w, "description")]
    # The date and amounts can sit halfway down the description's first line.
    # Infer each row separately: single-line and wrapped narratives can have
    # different alignments even on the same page.
    starts = []
    for y, _, height in anchors:
        nearby = [w["top"] for w in description_words if y - height <= w["top"] <= y + height]
        starts.append(min(y, min(nearby)) if nearby else y)
    out = []
    for index, (y, posted_at, height) in enumerate(anchors):
        amounts = {}
        for column in ("debit", "credit"):
            amount_words = sorted(
                [w for w in words if in_column(w, column) and abs(w["top"] - y) <= 3],
                key=lambda w: w["x0"],
            )
            amounts[column] = parse_amount(" ".join(w["text"] for w in amount_words))
        debit, credit = amounts["debit"], amounts["credit"]
        if bool(debit) == bool(credit):
            warnings.append(f"{source}: row {index + 1} has ambiguous or empty debit/credit cells; skipped")
            continue
        bottom = starts[index + 1] if index + 1 < len(anchors) else page.height
        row_lines = lines([w for w in description_words if starts[index] - 1 <= w["top"] < bottom - 1])
        pieces = []
        previous_y = None
        for line in row_lines:
            current_y = line[0]["top"]
            if previous_y is not None and current_y - previous_y > max(20, height * 2.5):
                break  # Keep the page footer out of the final description.
            pieces.append(" ".join(w["text"] for w in line))
            previous_y = current_y
        description = " ".join(pieces).strip()
        if not description:
            warnings.append(f"{source}: row {index + 1} has no description; skipped")
            continue
        metadata = extract_upi_metadata(description)
        out.append(ParsedRow(
            posted_at=posted_at,
            description=description,
            amount=-abs(debit) if debit else abs(credit),
            merchant=extract_merchant(description),
            user_label=metadata.get("user_label"),
            raw_row=description,
        ))
    log.append(f"{source}: positioned debit/credit columns extracted {len(out)} rows")
    return out


# ---------- Canara passbook ----------
_CANARA_HEADER_HINTS = ("Particulars", "Deposits", "Withdrawals", "Balance")


def _looks_like_canara(text: str) -> bool:
    if not text:
        return False
    score = sum(1 for h in _CANARA_HEADER_HINTS if h in text)
    return score >= 3 and "Chq" in text


_DATE_DDMMYYYY_RE = re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")
_CANARA_COLS = ("Date", "Particulars", "Deposits", "Withdrawals", "Balance")


def _parse_canara_page(page, *, page_idx: int, log: list[str], warnings: list[str]) -> list[ParsedRow]:
    """Walk a Canara passbook page using positional word extraction.

    Why positional and not `extract_tables`: page 1 of these passbooks has a
    customer-info header section that confuses pdfplumber's column-boundary
    inference (table widens to 9 cols vs 5 for transaction pages). By anchoring
    on the *header row* ("Date Particulars Deposits Withdrawals Balance") we get
    the actual column x-coordinates per page and can bucket every other word
    into the right column.

    A transaction looks like:
        Particulars [3-5 wrapped lines of the UPI string]
        Date Particulars(suffix) Deposit-OR-Withdrawal Balance     ← "data row"
        Particulars [HH:MM:SS]                                     ← timestamp tail
        Particulars [Chq: ref]                                     ← terminator
    """
    try:
        words = page.extract_words(use_text_flow=True) or []
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"page {page_idx} canara extract_words failed: {exc}")
        return []
    if not words:
        return []

    # Group words into visual lines by y-coordinate (top), tolerant of ~3px jitter
    from collections import defaultdict

    lines: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        key = round(w["top"] / 3) * 3
        lines[key].append(w)
    sorted_ys = sorted(lines.keys())

    # Find the header line: one containing all 5 column names
    header_y = None
    col_anchors: dict[str, float] = {}
    for y in sorted_ys:
        text_in_line = " ".join(w["text"] for w in lines[y])
        if all(c in text_in_line for c in _CANARA_COLS):
            header_y = y
            for w in lines[y]:
                if w["text"] in _CANARA_COLS and w["text"] not in col_anchors:
                    col_anchors[w["text"]] = w["x0"]
            if len(col_anchors) == len(_CANARA_COLS):
                break
    if not col_anchors or len(col_anchors) < len(_CANARA_COLS) or header_y is None:
        # Some interstitial pages (e.g. just a continuation) may not repeat header.
        return []

    # Midpoint boundaries between adjacent column anchors
    anchors_sorted = sorted(col_anchors.items(), key=lambda kv: kv[1])
    boundaries: list[tuple[float, str]] = []
    for i in range(len(anchors_sorted) - 1):
        mid = (anchors_sorted[i][1] + anchors_sorted[i + 1][1]) / 2.0
        boundaries.append((mid, anchors_sorted[i][0]))
    # Beyond last boundary: last column

    def column_for(x: float) -> str:
        for mid, col in boundaries:
            if x < mid:
                return col
        return anchors_sorted[-1][0]

    # Build per-line column dicts, in y order, only for lines below the header
    rows: list[dict[str, str]] = []
    for y in sorted_ys:
        if y <= header_y:
            continue
        buckets: dict[str, list[tuple[float, str]]] = {c: [] for c in _CANARA_COLS}
        for w in lines[y]:
            col = column_for(w["x0"])
            buckets[col].append((w["x0"], w["text"]))
        cells: dict[str, str] = {}
        for c in _CANARA_COLS:
            ws = sorted(buckets[c], key=lambda t: t[0])
            # Join with a space; downstream UPI-purpose extraction collapses
            # incorrectly-spaced all-caps single words.
            cells[c] = " ".join(t for _, t in ws).strip()
        if any(cells.values()):
            rows.append(cells)

    # Walk rows with the same transaction-builder logic
    out: list[ParsedRow] = []
    pending_desc: list[str] = []
    pending_date: Optional[str] = None
    pending_deposit: Optional[float] = None
    pending_withdrawal: Optional[float] = None

    def commit() -> None:
        nonlocal pending_desc, pending_date, pending_deposit, pending_withdrawal
        if pending_date and ((pending_deposit and pending_deposit > 0) or (pending_withdrawal and pending_withdrawal > 0)):
            d = try_parse_date(pending_date)
            if d:
                if pending_deposit and pending_deposit > 0:
                    amount = pending_deposit
                else:
                    amount = -float(pending_withdrawal or 0)
                desc = " ".join(s for s in pending_desc if s).strip()
                if desc and amount != 0:
                    meta = extract_upi_metadata(desc)
                    out.append(
                        ParsedRow(
                            posted_at=d,
                            description=desc,
                            amount=amount,
                            merchant=extract_merchant(desc),
                            user_label=meta.get("user_label"),
                            raw_row=desc,
                        )
                    )
        pending_desc = []
        pending_date = None
        pending_deposit = None
        pending_withdrawal = None

    for cells in rows:
        date_c = cells.get("Date", "")
        part_c = cells.get("Particulars", "")
        dep_c = cells.get("Deposits", "")
        wd_c = cells.get("Withdrawals", "")

        if "opening balance" in part_c.lower():
            continue
        if part_c.lower().startswith("chq"):
            commit()
            continue
        if _DATE_DDMMYYYY_RE.match(date_c):
            if pending_date:
                commit()
            pending_date = date_c
            if part_c:
                pending_desc.append(part_c)
            if dep_c:
                pending_deposit = parse_amount(dep_c)
            if wd_c:
                pending_withdrawal = parse_amount(wd_c)
            continue
        if part_c:
            pending_desc.append(part_c)

    commit()
    log.append(f"p{page_idx}: canara walker extracted {len(out)} rows")
    return out


def _table_to_rows(raw: list[list[Optional[str]]], *, source: str, log: list[str], warnings: list[str]) -> list[ParsedRow]:
    if not raw or len(raw) < 2:
        return []
    # find the header row inside this table
    header_idx = _detect_header(raw)
    if header_idx is None:
        return []
    columns = [(c or "").strip() for c in raw[header_idx]]
    data = raw[header_idx + 1 :]
    # pad/truncate
    width = len(columns)
    normalized = []
    for r in data:
        r = list(r) + [None] * (width - len(r))
        normalized.append(r[:width])
    df = pd.DataFrame(normalized, columns=columns)
    df = df.dropna(how="all")
    if df.empty:
        return []
    return dataframe_to_rows(df, source_label=source, log=log, warnings=warnings)


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


def _detect_header(raw: list[list[Optional[str]]]) -> Optional[int]:
    best, score = None, 0
    for i, row in enumerate(raw[: min(len(raw), 8)]):
        cells = [(c or "").lower() for c in row]
        s = sum(1 for c in cells for h in _HEADER_HINTS if h and h in c)
        if s > score:
            best, score = i, s
    return best if score >= 2 else None


# -------- text fallback ---------
_TEXT_TXN_RE = re.compile(
    r"^(?P<date>\d{1,2}[/-][A-Za-z]{3,9}[/-]?\d{0,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s*\d{0,4})"
    r"\s+(?P<desc>.+?)\s+"
    r"(?P<amount>[\d,]+\.\d{2})\s*(?P<dc>CR|DR|Cr|Dr)?\s*$"
)


def _text_to_rows(text: str, *, source: str, log: list[str]) -> list[ParsedRow]:
    out: list[ParsedRow] = []
    if not text:
        return out
    # Try to anchor a statement year if we see one e.g. "Statement Period: 01-Mar-2025 to 31-Mar-2025"
    year_match = re.search(r"(20\d{2})", text)
    default_year = int(year_match.group(1)) if year_match else None

    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 12:
            continue
        m = _TEXT_TXN_RE.match(line)
        if not m:
            continue
        raw_date = m.group("date")
        if default_year and not re.search(r"\d{4}", raw_date) and not re.search(r"\d{2}$", raw_date):
            raw_date = f"{raw_date} {default_year}"
        d = try_parse_date(raw_date)
        if not d:
            continue
        amount = parse_amount(f"{m.group('amount')} {m.group('dc') or ''}")
        if amount is None or amount == 0:
            continue
        # In CC statements, charges are debit by default unless marked CR
        if (m.group("dc") or "").upper() != "CR" and amount > 0:
            amount = -amount
        desc = m.group("desc").strip()
        meta = extract_upi_metadata(desc)
        out.append(
            ParsedRow(
                posted_at=d,
                description=desc,
                amount=amount,
                merchant=extract_merchant(desc),
                user_label=meta.get("user_label"),
                raw_row=line,
            )
        )
    if out:
        log.append(f"{source}: text-fallback extracted {len(out)} rows")
    return out
