from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[schemas.AccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[models.Account]:
    return db.query(models.Account).order_by(models.Account.name).all()


@router.post("", response_model=schemas.AccountOut)
def create_account(payload: schemas.AccountIn, db: Session = Depends(get_db)) -> models.Account:
    existing = db.query(models.Account).filter_by(name=payload.name).first()
    if existing:
        raise HTTPException(409, f"account '{payload.name}' already exists")
    acct = models.Account(**payload.model_dump())
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)) -> dict:
    acct = db.get(models.Account, account_id)
    if not acct:
        raise HTTPException(404, "account not found")
    db.delete(acct)
    db.commit()
    return {"ok": True}
