from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[models.Category]:
    return db.query(models.Category).order_by(models.Category.name).all()


@router.post("", response_model=schemas.CategoryOut)
def create_category(payload: schemas.CategoryOut, db: Session = Depends(get_db)) -> models.Category:
    existing = db.query(models.Category).filter_by(name=payload.name).first()
    if existing:
        raise HTTPException(409, "category exists")
    cat = models.Category(name=payload.name, icon=payload.icon, color=payload.color)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)) -> dict:
    cat = db.get(models.Category, category_id)
    if not cat:
        raise HTTPException(404, "category not found")
    db.delete(cat)
    db.commit()
    return {"ok": True}
