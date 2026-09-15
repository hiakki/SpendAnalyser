from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _serialize(t: models.Transaction) -> schemas.TransactionOut:
    return schemas.TransactionOut(
        id=t.id,
        account_id=t.account_id,
        account_name=t.account.name if t.account else None,
        posted_at=t.posted_at,
        value_at=t.value_at,
        description=t.description,
        merchant=t.merchant,
        amount=t.raw_amount,
        currency=t.currency,
        direction=t.direction,
        category_id=t.category_id,
        category_name=t.category.name if t.category else None,
        category_color=t.category.color if t.category else None,
        category_source=t.category_source,
        note=t.note,
    )


@router.get("", response_model=list[schemas.TransactionOut])
def list_transactions(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    direction: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, le=5000),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[schemas.TransactionOut]:
    query = db.query(models.Transaction).options(
        joinedload(models.Transaction.account),
        joinedload(models.Transaction.category),
    )
    if start:
        query = query.filter(models.Transaction.posted_at >= start)
    if end:
        query = query.filter(models.Transaction.posted_at <= end)
    if account_id:
        query = query.filter(models.Transaction.account_id == account_id)
    if category_id is not None:
        if category_id == 0:
            query = query.filter(or_(models.Transaction.category_id.is_(None), models.Transaction.category_source == "label_review"))
        else:
            query = query.filter(models.Transaction.category_id == category_id)
    if direction:
        query = query.filter(models.Transaction.direction == direction)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                models.Transaction.description.ilike(like),
                models.Transaction.merchant.ilike(like),
            )
        )
    items = (
        query.order_by(models.Transaction.posted_at.desc(), models.Transaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_serialize(t) for t in items]


@router.patch("/{txn_id}", response_model=schemas.TransactionOut)
def update_transaction(txn_id: int, payload: schemas.TransactionPatch, db: Session = Depends(get_db)) -> schemas.TransactionOut:
    txn = db.get(models.Transaction, txn_id)
    if not txn:
        raise HTTPException(404, "not found")
    if payload.category_id is not None:
        txn.category_id = payload.category_id
        txn.category_source = "user"
    if payload.note is not None:
        txn.note = payload.note
    if payload.merchant is not None:
        txn.merchant = payload.merchant
    db.commit()
    db.refresh(txn)
    return _serialize(txn)


@router.post("/bulk-categorize", response_model=dict)
def bulk_categorize(ids: list[int], category_id: int, db: Session = Depends(get_db)) -> dict:
    if not ids:
        return {"updated": 0}
    txns = db.query(models.Transaction).filter(models.Transaction.id.in_(ids)).all()
    for t in txns:
        t.category_id = category_id
        t.category_source = "user"
    db.commit()
    return {"updated": len(txns)}


@router.delete("/{txn_id}")
def delete_transaction(txn_id: int, db: Session = Depends(get_db)) -> dict:
    t = db.get(models.Transaction, txn_id)
    if not t:
        raise HTTPException(404, "not found")
    db.delete(t)
    db.commit()
    return {"ok": True}
