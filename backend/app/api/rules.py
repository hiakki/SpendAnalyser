from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..categorize.service import recategorize_all
from ..db import get_db

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[schemas.RuleOut])
def list_rules(db: Session = Depends(get_db)) -> list[models.Rule]:
    return db.query(models.Rule).order_by(models.Rule.priority).all()


@router.post("", response_model=schemas.RuleOut)
def create_rule(payload: schemas.RuleIn, db: Session = Depends(get_db)) -> models.Rule:
    rule = models.Rule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=schemas.RuleOut)
def update_rule(rule_id: int, payload: schemas.RuleIn, db: Session = Depends(get_db)) -> models.Rule:
    rule = db.get(models.Rule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump().items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> dict:
    rule = db.get(models.Rule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/recategorize")
def recategorize(
    only_uncategorized: bool = False,
    overwrite_user: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    changed = recategorize_all(db, only_uncategorized=only_uncategorized, overwrite_user=overwrite_user)
    return {"changed": changed}
