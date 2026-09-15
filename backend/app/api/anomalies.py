from __future__ import annotations

import statistics
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("")
def detect_anomalies(
    z_threshold: float = Query(2.5, description="z-score above which a tx is flagged"),
    min_amount: float = Query(500.0),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Per category, compute mean & stdev of debit amounts; flag rows with z > threshold."""
    txns = (
        db.query(models.Transaction)
        .filter(models.Transaction.direction == "debit")
        .all()
    )
    by_cat: dict[int | None, list[models.Transaction]] = defaultdict(list)
    for t in txns:
        by_cat[t.category_id].append(t)

    flagged = []
    for cat_id, items in by_cat.items():
        amounts = [abs(t.raw_amount) for t in items]
        if len(amounts) < 5:
            continue
        mean = statistics.mean(amounts)
        stdev = statistics.pstdev(amounts)
        if stdev == 0:
            continue
        for t in items:
            amt = abs(t.raw_amount)
            if amt < min_amount:
                continue
            z = (amt - mean) / stdev
            if z >= z_threshold:
                flagged.append(
                    {
                        "transaction_id": t.id,
                        "posted_at": t.posted_at.isoformat(),
                        "merchant": t.merchant,
                        "description": t.description[:120],
                        "amount": round(amt, 2),
                        "category_id": cat_id,
                        "category_name": t.category.name if t.category else "Uncategorized",
                        "category_mean": round(mean, 2),
                        "z_score": round(z, 2),
                    }
                )
    flagged.sort(key=lambda x: x["z_score"], reverse=True)
    return flagged
