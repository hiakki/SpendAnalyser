from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Optional

from dateutil import parser as dtparser


DATE_PATTERNS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
]


_DATE_RE = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}"
    r")\b"
)


def try_parse_date(text: str) -> Optional[date]:
    if not text:
        return None
    text = str(text).strip()
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return dtparser.parse(text, dayfirst=True, fuzzy=False).date()
    except (ValueError, TypeError, OverflowError):
        pass
    m = _DATE_RE.search(text)
    if m:
        try:
            return dtparser.parse(m.group(1), dayfirst=True, fuzzy=False).date()
        except (ValueError, TypeError, OverflowError):
            return None
    return None


_AMOUNT_RE = re.compile(
    r"(-?\(?\s*(?:Rs\.?|INR|\$|€|£)?\s*[-+]?[\d,]+\.\d{1,2}\s*\)?)(\s*(?:CR|DR|Cr|Dr))?",
    re.IGNORECASE,
)
_NEG_PAREN_RE = re.compile(r"^\(.*\)$")


def parse_amount(text: str) -> Optional[float]:
    """Parse an amount string like '1,234.56', '(1,234.56)', '1234.56 Cr'.
    Returns float; negative means money out unless caller decides otherwise.
    A trailing CR is treated as positive, DR as negative."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    cr_dr = None
    m_cr = re.search(r"\b(CR|DR)\b", s, re.IGNORECASE)
    if m_cr:
        cr_dr = m_cr.group(1).upper()
        s = s[: m_cr.start()].strip()

    negative = False
    if _NEG_PAREN_RE.match(s):
        negative = True
        s = s[1:-1]
    s = re.sub(r"(?i)(rs\.?|inr|\$|€|£)", "", s).strip()
    s = s.replace(",", "")
    if s.startswith("-"):
        negative = True
        s = s[1:]
    if s.startswith("+"):
        s = s[1:]
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    if negative:
        v = -v
    if cr_dr == "DR" and v > 0:
        v = -v
    if cr_dr == "CR" and v < 0:
        v = -v
    return v


_MERCHANT_CLEAN_RE = re.compile(r"[^A-Za-z0-9 &.'-]+")


# Generic UPI flow indicators that appear in parts[6] but aren't real merchants.
# Comparison is case-insensitive and ignores whitespace.
_GENERIC_PURPOSES = {
    "PAYTOB", "PAYTOMERCHANT", "PAYMENT", "UPIINTENT", "UPI", "INTENT",
    "P2P", "P2M", "OTHER", "OTHERS", "MISC", "MOPSUPITXN", "MOPSUPI",
    "BHARATQR", "QR", "INSTANT", "TRANSFER", "TXN", "NA", "N/A",
}

# Words that appear in NEFT/IMPS narrations as noise — strip from heuristic merchant.
_DESC_NOISE = {
    "DRAWDOWN", "CASA", "NEFT", "IMPS", "RTGS", "INET", "MOB",
    "CR", "DR", "CONSUMER", "ACCOUNT", "TRANSACTION", "TRANSFER",
}

# Trailing "HH:MM:SS - <user comment>" or "DD/MM/YYYY HH:MM:SS - <user comment>"
# that appears at the very end of UPI descriptions when the user added a note in
# their UPI app. Anchored on the timestamp followed by a space-dash-space; the
# label must start with a letter and cannot contain '/' (which would mean we
# accidentally matched a UPI ref-number suffix).
_USER_LABEL_RE = re.compile(
    r"\d{1,2}:\d{2}(?::\d{2})?\s+[-–]\s+(?P<label>[A-Za-z][A-Za-z0-9 &.'_-]{0,80}?)\s*$"
)

# Bank-code → label hint, used as a *weak* fallback when there's no user comment.
_BANK_CODE_HINT = re.compile(r"/(?:HDF|ICI|SBI|AXI|UTIB|YESB|KKBK|PYTM|OKHDF|OKBIZ|OKAXIS|OKICI|OKSBI)\d", re.IGNORECASE)


def extract_upi_metadata(description: str) -> dict:
    """Pull structured fields out of a typical UPI narration like:
        UPI/DR/525905063541/OTTRAVELI/UTIB/**LINFO@OKAXIS/USVISA//AXI...../16/09/2025 13:08:32 - us visa

    Returns a dict with any of: direction, ref, receiver, vpa, purpose, user_label.
    All keys are optional; absent ones aren't included."""
    out: dict[str, str] = {}
    if not description:
        return out
    s = description.strip()

    # User label after the trailing timestamp
    m = _USER_LABEL_RE.search(s)
    if m:
        label = m.group("label").strip().strip("-_.")
        if label and len(label) >= 2 and not label.isdigit():
            out["user_label"] = label

    # Tokenize on '/' for UPI-style descriptions
    if s.upper().startswith("UPI") or s.upper().startswith("UPI/"):
        parts = [p.strip() for p in s.split("/")]
        # parts[0]=UPI, parts[1]=DR/CR, parts[2]=ref, parts[3]=receiver short,
        # parts[4]=bank code, parts[5]=vpa, parts[6]=purpose
        if len(parts) >= 2 and parts[1].upper() in {"DR", "CR"}:
            out["direction"] = "debit" if parts[1].upper() == "DR" else "credit"
        if len(parts) >= 3 and parts[2].isdigit():
            out["ref"] = parts[2]
        if len(parts) >= 4 and parts[3] and not parts[3].isdigit():
            out["receiver"] = parts[3]
        if len(parts) >= 6 and "@" in parts[5]:
            out["vpa"] = parts[5]
        if len(parts) >= 7 and parts[6] and not parts[6].isdigit():
            cand = parts[6].strip()
            # PDFs line-break long words and the next UPI segment can bleed
            # into parts[6] via the whitespace join. Keep only the leading
            # consecutive all-caps tokens (any length, including single
            # leading letters) and concatenate.
            # "G ROCERY" → "GROCERY", "W ATER B903" → "WATER",
            # "GA RDENING" → "GARDENING", "SE LF" → "SELF",
            # "MOVIES J" → "MOVIESJ", "PAY TO B" → "PAYTOB".
            if cand and " " in cand:
                tokens = cand.split()
                kept: list[str] = []
                for tok in tokens:
                    if re.fullmatch(r"[A-Z]+", tok):
                        kept.append(tok)
                    else:
                        break
                if kept:
                    collapsed = "".join(kept)
                    if 2 <= len(collapsed) <= 30:
                        cand = collapsed
            # Reject generic UPI-flow tokens that aren't merchant identities.
            cleaned_upper = re.sub(r"\s+", "", cand).upper()
            if cleaned_upper in _GENERIC_PURPOSES:
                cand = ""
            if cand and cand.upper() not in {"NA", "N/A"} and len(cand) >= 2:
                out["purpose"] = cand
    return out


def extract_merchant(description: str) -> str:
    """Best-effort merchant name from a transaction description.
    Priority: user_label (UPI app comment) > purpose > receiver > heuristic on cleaned text."""
    if not description:
        return ""
    meta = extract_upi_metadata(description)
    if meta.get("user_label"):
        return _titleish(meta["user_label"])
    if meta.get("purpose"):
        return _titleish(meta["purpose"])
    if meta.get("receiver"):
        return _titleish(meta["receiver"])

    s = description
    s = re.sub(r"(?i)\bupi[/-][a-z0-9._@-]+", " ", s)
    s = re.sub(r"\b[A-Z]{2,}\d{4,}\b", " ", s)
    s = re.sub(r"\b\d{6,}\b", " ", s)
    s = _MERCHANT_CLEAN_RE.sub(" ", s)
    parts: list[str] = []
    for raw in s.split():
        p = raw.strip(" .,-'&_")
        if len(p) >= 3 and p.upper() not in _DESC_NOISE:
            parts.append(p)
    if not parts:
        return description.strip()[:40]
    return " ".join(parts[:4]).title()


def _titleish(s: str) -> str:
    s = s.strip().strip("-_.")
    # CamelCase / UPPERCASE single words → title; multi-word phrases stay as title-case
    if s.isupper() or s.islower():
        return s.title()
    return s
