from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from .llm import llm_categorize
from .rules import match_rule


def _other_category_id(db: Session) -> Optional[int]:
    other = db.query(models.Category).filter_by(name="Other").first()
    return other.id if other else None


def categorize_text(db: Session, text: str) -> tuple[Optional[int], str]:
    """Return (category_id, source) for a piece of text.
    source ∈ {rule, llm, fallback}."""
    cfg = get_settings()
    hit = match_rule(db, text)
    if hit:
        return hit.category_id, "rule"
    if cfg.llm_enabled:
        res = llm_categorize(db, text)
        if res and res[1] >= cfg.llm_min_confidence:
            return res[0], "llm"
    return _other_category_id(db), "fallback"


def categorize_transaction(db: Session, txn: models.Transaction) -> tuple[Optional[int], str]:
    text = " ".join(filter(None, [txn.merchant, txn.description]))
    return categorize_text(db, text)


def recategorize_all(db: Session, *, only_uncategorized: bool = False, overwrite_user: bool = False) -> int:
    """Recompute categories for every transaction. Returns count changed."""
    q = db.query(models.Transaction)
    if only_uncategorized:
        q = q.filter(models.Transaction.category_id.is_(None))
    if not overwrite_user:
        q = q.filter((models.Transaction.category_source != "user") | (models.Transaction.category_source.is_(None)))
    changed = 0
    for txn in q.all():
        new_cat, source = categorize_transaction(db, txn)
        if new_cat != txn.category_id:
            txn.category_id = new_cat
            txn.category_source = source
            changed += 1
    db.commit()
    return changed
