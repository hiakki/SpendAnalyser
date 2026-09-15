from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _filter(q, *, start: Optional[date], end: Optional[date], account_id: Optional[int]):
    if start and end and start > end:
        raise HTTPException(422, "start must be on or before end")
    if start:
        q = q.filter(models.Transaction.posted_at >= start)
    if end:
        q = q.filter(models.Transaction.posted_at <= end)
    if account_id is not None:
        q = q.filter(models.Transaction.account_id == account_id)
    return q


@router.get("/summary")
def summary(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> dict:
    base = _filter(db.query(models.Transaction), start=start, end=end, account_id=account_id)
    rows = base.with_entities(models.Transaction.direction, func.sum(models.Transaction.raw_amount), func.count()).group_by(models.Transaction.direction).all()
    spend = 0.0
    income = 0.0
    n_tx = 0
    for direction, total, count in rows:
        n_tx += count or 0
        if direction == "debit":
            spend += abs(total or 0)
        else:
            income += total or 0
    net = income - spend
    return {
        "spend": round(spend, 2),
        "income": round(income, 2),
        "net": round(net, 2),
        "n_transactions": n_tx,
        "uncategorized_count": base.filter(or_(models.Transaction.category_id.is_(None), models.Transaction.category_source == "label_review")).count(),
    }


@router.get("/by-category")
def by_category(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    q = _filter(
        db.query(
            models.Transaction.category_id,
            models.Category.name,
            models.Category.color,
            func.sum(models.Transaction.raw_amount).label("total"),
            func.count().label("n"),
        ).outerjoin(models.Category, models.Transaction.category_id == models.Category.id),
        start=start,
        end=end,
        account_id=account_id,
    )
    rows = (
        q.filter(models.Transaction.direction == "debit")
        .group_by(models.Transaction.category_id, models.Category.name, models.Category.color)
        .all()
    )
    out = []
    for cid, name, color, total, n in rows:
        out.append({
            "category_id": cid or 0,
            "category_name": name or "Uncategorized",
            "color": color,
            "total": round(abs(total or 0), 2),
            "count": n,
        })
    out.sort(key=lambda x: x["total"], reverse=True)
    return out


@router.get("/by-category-month")
def by_category_month(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    q = _filter(
        db.query(
            func.strftime("%Y-%m", models.Transaction.posted_at).label("month"),
            models.Transaction.category_id,
            models.Category.name,
            models.Category.color,
            func.sum(models.Transaction.raw_amount).label("total"),
            func.count().label("n"),
        ).outerjoin(models.Category, models.Transaction.category_id == models.Category.id),
        start=start,
        end=end,
        account_id=account_id,
    )
    rows = (
        q.filter(models.Transaction.direction == "debit")
        .group_by("month", models.Transaction.category_id, models.Category.name, models.Category.color)
        .all()
    )
    buckets: dict[str, dict] = {}
    for month, cid, name, color, total, n in rows:
        if month not in buckets:
            buckets[month] = {"month": month, "total": 0.0, "count": 0, "categories": []}
        amount = round(abs(total or 0), 2)
        buckets[month]["total"] = round(buckets[month]["total"] + amount, 2)
        buckets[month]["count"] += n or 0
        buckets[month]["categories"].append({
            "category_id": cid or 0,
            "category_name": name or "Uncategorized",
            "color": color,
            "total": amount,
            "count": n,
        })

    out = []
    for bucket in buckets.values():
        bucket["categories"].sort(key=lambda x: x["total"], reverse=True)
        out.append(bucket)
    out.sort(key=lambda x: x["month"])
    return out


@router.get("/by-month")
def by_month(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    # Aggregate in SQLite instead of loading every transaction into Python.
    month = func.strftime("%Y-%m", models.Transaction.posted_at)
    rows = _filter(
        db.query(
            month.label("month"),
            func.sum(case((models.Transaction.direction == "debit", func.abs(models.Transaction.raw_amount)), else_=0)),
            func.sum(case((models.Transaction.direction == "credit", models.Transaction.raw_amount), else_=0)),
            func.count(),
        ),
        start=start, end=end, account_id=account_id,
    ).group_by(month).order_by(month).all()
    return [
        {"month": month, "spend": round(spend, 2), "income": round(income, 2),
         "net": round(income - spend, 2), "count": count}
        for month, spend, income, count in rows
    ]


@router.get("/top-merchants")
def top_merchants(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = _filter(
        db.query(
            models.Transaction.merchant,
            func.sum(models.Transaction.raw_amount).label("total"),
            func.count().label("n"),
        ),
        start=start,
        end=end,
        account_id=account_id,
    )
    rows = (
        q.filter(models.Transaction.direction == "debit", models.Transaction.merchant.isnot(None))
        .group_by(models.Transaction.merchant)
        .order_by(func.sum(models.Transaction.raw_amount).asc())
        .limit(limit)
        .all()
    )
    return [
        {"merchant": m or "Unknown", "total": round(abs(t or 0), 2), "count": n}
        for m, t, n in rows
    ]


@router.get("/by-account")
def by_account(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = (
        db.query(
            models.Account.id,
            models.Account.name,
            models.Account.kind,
            func.sum(models.Transaction.raw_amount).label("total"),
            func.count().label("n"),
        )
        .outerjoin(models.Transaction, models.Transaction.account_id == models.Account.id)
        .filter(models.Transaction.direction == "debit")
    )
    rows = _filter(rows, start=start, end=end, account_id=None)
    rows = rows.group_by(models.Account.id).all()
    return [
        {"account_id": i, "account_name": n, "kind": k, "spend": round(abs(t or 0), 2), "count": ct}
        for i, n, k, t, ct in rows
    ]
