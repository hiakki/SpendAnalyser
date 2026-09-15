from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=list[schemas.BudgetOut])
def list_budgets(db: Session = Depends(get_db)) -> list[schemas.BudgetOut]:
    rows = db.query(models.Budget).all()
    out = []
    for b in rows:
        out.append(
            schemas.BudgetOut(
                id=b.id,
                category_id=b.category_id,
                month=b.month,
                amount=b.amount,
                category_name=b.category.name if b.category else None,
            )
        )
    return out


@router.post("", response_model=schemas.BudgetOut)
def upsert_budget(payload: schemas.BudgetIn, db: Session = Depends(get_db)) -> schemas.BudgetOut:
    existing = db.query(models.Budget).filter_by(category_id=payload.category_id, month=payload.month).first()
    if existing:
        existing.amount = payload.amount
        b = existing
    else:
        b = models.Budget(**payload.model_dump())
        db.add(b)
    db.commit()
    db.refresh(b)
    return schemas.BudgetOut(
        id=b.id,
        category_id=b.category_id,
        month=b.month,
        amount=b.amount,
        category_name=b.category.name if b.category else None,
    )


@router.delete("/{budget_id}")
def delete_budget(budget_id: int, db: Session = Depends(get_db)) -> dict:
    b = db.get(models.Budget, budget_id)
    if not b:
        raise HTTPException(404, "not found")
    db.delete(b)
    db.commit()
    return {"ok": True}


@router.get("/status")
def budget_status(month: str = Query(..., description="YYYY-MM"), db: Session = Depends(get_db)) -> list[dict]:
    """For a given month, return per-category budgeted vs actual spend."""
    try:
        y, m = month.split("-")
        y, m = int(y), int(m)
        period_start = date(y, m, 1)
        if m == 12:
            period_end = date(y + 1, 1, 1)
        else:
            period_end = date(y, m + 1, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"bad month '{month}': {exc}") from exc

    # spend per category for this month
    spend_rows = (
        db.query(
            models.Transaction.category_id,
            func.sum(models.Transaction.raw_amount),
        )
        .filter(
            models.Transaction.posted_at >= period_start,
            models.Transaction.posted_at < period_end,
            models.Transaction.direction == "debit",
        )
        .group_by(models.Transaction.category_id)
        .all()
    )
    spend_map = {cid: abs(total or 0) for cid, total in spend_rows}

    # budgets: month-specific overrides month="*"
    cats = db.query(models.Category).all()
    budgets = {
        (budget.category_id, budget.month): budget
        for budget in db.query(models.Budget).filter(models.Budget.month.in_([month, "*"])).all()
    }
    out = []
    for c in cats:
        budget = budgets.get((c.id, month)) or budgets.get((c.id, "*"))
        if not budget and c.id not in spend_map:
            continue
        amt = budget.amount if budget else 0
        actual = spend_map.get(c.id, 0)
        out.append(
            {
                "category_id": c.id,
                "category_name": c.name,
                "color": c.color,
                "budget": round(amt, 2),
                "actual": round(actual, 2),
                "remaining": round(amt - actual, 2),
                "percent": round((actual / amt * 100) if amt else 0, 1),
                "over": actual > amt and amt > 0,
            }
        )
    out.sort(key=lambda x: x["actual"], reverse=True)
    return out
