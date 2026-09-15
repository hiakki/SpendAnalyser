"""Auto-create categories for repetitive merchants currently sitting in 'Other'.

Repeated merchants can get their own bucket. A merchant's name does not establish
the purpose of a payment: unfamiliar one-off payments stay in Other for review.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from .seed import ensure_category


# Cycle-coloured palette for auto-created categories so the dashboard stays
# visually scannable as new buckets appear.
_PALETTE = [
    "#fb923c", "#fbbf24", "#facc15", "#a3e635", "#34d399", "#22d3ee",
    "#60a5fa", "#818cf8", "#a78bfa", "#c084fc", "#e879f9", "#f472b6",
    "#fb7185", "#f87171", "#fcd34d", "#86efac", "#7dd3fc", "#93c5fd",
]


def _pick_color(seed_text: str) -> str:
    return _PALETTE[sum(ord(c) for c in seed_text) % len(_PALETTE)]


def _normalize_merchant(s: str) -> str:
    """Group key for merchants: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def autogrow_categories(
    db: Session,
    *,
    min_count: int = 2,
    only_account_id: Optional[int] = None,
) -> dict:
    """Returns a summary dict of what changed.
       {created_categories: [...], reassigned: int, loan_assigned: int, skipped: int}"""
    other = db.query(models.Category).filter_by(name="Other").first()
    if not other:
        return {"created_categories": [], "reassigned": 0, "loan_assigned": 0, "skipped": 0}

    q = db.query(models.Transaction).filter(
        # treat both "Other" and unassigned as candidates
        (models.Transaction.category_id == other.id) | (models.Transaction.category_id.is_(None)),
        # A user's explicit choice of Other is still a deliberate category.
        (models.Transaction.category_source != "user") | (models.Transaction.category_source.is_(None)),
    )
    if only_account_id:
        q = q.filter(models.Transaction.account_id == only_account_id)
    candidates = q.all()

    # Bucket by (direction, normalized merchant) — we never want to mix incoming
    # and outgoing payments under one category since their semantics differ.
    groups: dict[tuple[str, str], list[models.Transaction]] = defaultdict(list)
    for t in candidates:
        key = _normalize_merchant(t.merchant or "")
        if not key or key in {"unknown", "na", "n/a"}:
            continue
        groups[(t.direction or "debit", key)].append(t)

    created: list[dict] = []
    reassigned = 0
    skipped = 0

    existing_cat_names = {c.name.lower() for c in db.query(models.Category).all()}
    existing_rules = {(r.pattern.lower(), r.category_id) for r in db.query(models.Rule).all()}

    for (direction, key), txns in groups.items():
        if len(txns) >= min_count:
            base_name = (txns[0].merchant or key).strip().title()
            # Suffix incoming-money buckets so dashboards distinguish them from
            # outgoing categories of the same person (e.g. you Venmo Sneh AND
            # Sneh sometimes sends money back).
            display_name = f"{base_name} (received)" if direction == "credit" else base_name
            if display_name.lower() in existing_cat_names:
                cat = db.query(models.Category).filter(func.lower(models.Category.name) == display_name.lower()).first()
            else:
                cat = ensure_category(db, display_name, icon="tag", color=_pick_color(display_name))
                existing_cat_names.add(display_name.lower())
                created.append({"name": display_name, "transactions": len(txns), "direction": direction})
            rule_key = (key, cat.id)
            if rule_key not in existing_rules:
                db.add(
                    models.Rule(
                        pattern=key, is_regex=False, category_id=cat.id, priority=15,
                        note=f"auto-grown ({direction})",
                    )
                )
                existing_rules.add(rule_key)
            for t in txns:
                t.category_id = cat.id
                t.category_source = "auto"
                reassigned += 1
        else:
            # Names alone cannot distinguish loans, purchases, gifts or fees.
            skipped += len(txns)

    db.commit()
    return {
        "created_categories": created,
        "reassigned": reassigned,
        "loan_assigned": 0,  # retained for API compatibility
        "skipped": skipped,
    }
