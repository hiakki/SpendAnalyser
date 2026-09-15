from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("")
def detect_recurring(db: Session = Depends(get_db)) -> list[dict]:
    """Detect likely subscriptions / recurring payments.
    Heuristic: 3+ debits with a similar merchant key, similar amount (<=15% stddev),
    and monthly cadence (28-35 days between consecutive)."""

    txns = (
        db.query(models.Transaction)
        .filter(models.Transaction.direction == "debit")
        .order_by(models.Transaction.posted_at.asc())
        .all()
    )
    groups: dict[str, list[models.Transaction]] = defaultdict(list)
    for t in txns:
        key = (t.merchant or t.description or "").lower().strip()[:32]
        if not key:
            continue
        # fuzzy collapse: find an existing group key that matches well
        merged_key = key
        for existing in list(groups.keys()):
            if fuzz.ratio(key, existing) >= 88:
                merged_key = existing
                break
        groups[merged_key].append(t)

    out = []
    today = date.today()
    for key, items in groups.items():
        if len(items) < 3:
            continue
        items.sort(key=lambda x: x.posted_at)
        gaps = [
            (items[i + 1].posted_at - items[i].posted_at).days for i in range(len(items) - 1)
        ]
        if not gaps:
            continue
        avg_gap = sum(gaps) / len(gaps)
        if not (20 <= avg_gap <= 45):
            continue
        amounts = [abs(t.raw_amount) for t in items]
        avg_amt = sum(amounts) / len(amounts)
        if avg_amt == 0:
            continue
        stdev = statistics.pstdev(amounts) if len(amounts) > 1 else 0
        if (stdev / avg_amt) > 0.25:
            continue
        last = items[-1].posted_at
        next_est = date.fromordinal(last.toordinal() + int(round(avg_gap)))
        out.append(
            {
                "key": key,
                "merchant": items[-1].merchant or items[-1].description[:40],
                "category_id": items[-1].category_id,
                "category_name": items[-1].category.name if items[-1].category else None,
                "count": len(items),
                "avg_amount": round(avg_amt, 2),
                "avg_cadence_days": round(avg_gap, 1),
                "amount_volatility_pct": round((stdev / avg_amt) * 100, 1),
                "last_seen": last.isoformat(),
                "next_estimated": next_est.isoformat(),
                "active": (today - last).days <= 45,
            }
        )
    out.sort(key=lambda x: x["avg_amount"], reverse=True)
    return out
