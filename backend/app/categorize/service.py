from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from ..parsers.utils import extract_upi_metadata
from .llm import llm_categorize
from .rules import match_rule


def _other_category_id(db: Session) -> Optional[int]:
    other = db.query(models.Category).filter_by(name="Other").first()
    return other.id if other else None


def categorize_text(db: Session, text: str, *, direction: str | None = None) -> tuple[Optional[int], str]:
    """Return (category_id, source) for a piece of text.
    source ∈ {rule, llm, fallback}."""
    cfg = get_settings()
    hit = match_rule(db, text, direction=direction)
    if hit:
        return hit.category_id, "rule"
    if cfg.llm_enabled:
        res = llm_categorize(db, text)
        if res and res[1] >= cfg.llm_min_confidence:
            return res[0], "llm"
    return _other_category_id(db), "fallback"


# Bank/app-generated remarks describe the payment mechanism, not its purpose.
# Keep them as notes, but do not treat them as a deliberate category label.
_GENERIC_REMARKS = {"payment on", "payment fr", "payment from", "paidviacred", "mopsupitxn",
                    "paytob", "paytomerchant", "payment", "upi", "upiintent", "intent", "na", "n/a"}


def categorize_statement_row(
    db: Session, *, description: str, merchant: str | None = None,
    user_label: str | None = None, direction: str | None = None, account_id: int | None = None,
) -> tuple[Optional[int], str]:
    """One label-first path for imports and both recategorization endpoints.

    An unrecognized explicit label needs review; merchant names, routing banks,
    reference IDs and optional LLM guesses must not override its meaning.
    """
    meta = extract_upi_metadata(description)
    label = " ".join((user_label or meta.get("user_label") or "").split())
    if label and account_id is not None and direction in {"debit", "credit"}:
        confirmed = db.query(models.StatementLabelRule).filter_by(
            account_id=account_id, label=label.casefold(), direction=direction,
        ).first()
        if confirmed:
            return confirmed.category_id, "upi_label"
    if label and label.casefold() not in _GENERIC_REMARKS:
        # A label can name a category directly, including a user-created one.
        category = next((c for c in db.query(models.Category).all() if c.name.casefold() == label.casefold()), None)
        if category:
            if (direction == "debit" and category.name in {"Salary", "Interest Income"}) or (category.name == "Loan Given" and direction != "debit"):
                return _other_category_id(db), "label_review"
            return category.id, "upi_label"
        hit = match_rule(db, label, direction=direction)
        if hit:
            return hit.category_id, "upi_label"
        return _other_category_id(db), "label_review"
    if meta.get("narration_format", "").startswith("icici-"):
        # Routing bank names, VPAs and opaque IDs aren't purchase evidence.
        text = meta.get("receiver") or ""
    else:
        text = " ".join(filter(None, [merchant, description]))
    return categorize_text(db, text, direction=direction)


def categorize_transaction(db: Session, txn: models.Transaction) -> tuple[Optional[int], str]:
    return categorize_statement_row(db, description=txn.description, merchant=txn.merchant,
                                    direction=txn.direction, account_id=txn.account_id)


def recategorize_all(db: Session, *, only_uncategorized: bool = False, overwrite_user: bool = False, account_id: int | None = None) -> int:
    """Recompute categories for every transaction. Returns count changed."""
    q = db.query(models.Transaction)
    if account_id is not None:
        q = q.filter(models.Transaction.account_id == account_id)
    if only_uncategorized:
        q = q.filter(or_(models.Transaction.category_id.is_(None), models.Transaction.category_source == "label_review"))
    if not overwrite_user:
        q = q.filter((models.Transaction.category_source != "user") | (models.Transaction.category_source.is_(None)))
    changed = 0
    for txn in q.all():
        label = extract_upi_metadata(txn.description).get("user_label")
        if label and not txn.note:
            txn.note = label
        new_cat, source = categorize_transaction(db, txn)
        if new_cat != txn.category_id or source != txn.category_source:
            txn.category_id = new_cat
            txn.category_source = source
            changed += 1
    db.commit()
    return changed
