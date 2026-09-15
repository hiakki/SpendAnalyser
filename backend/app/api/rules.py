from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.sqlite import insert
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


@router.get("/labels", response_model=list[schemas.LabelRuleOut])
def list_label_rules(account_id: int | None = None, db: Session = Depends(get_db)) -> list[models.StatementLabelRule]:
    query = db.query(models.StatementLabelRule)
    if account_id is not None:
        if db.get(models.Account, account_id) is None:
            raise HTTPException(404, "account not found")
        query = query.filter_by(account_id=account_id)
    return query.order_by(models.StatementLabelRule.account_id, models.StatementLabelRule.label, models.StatementLabelRule.direction).all()


@router.post("/labels", response_model=schemas.LabelRuleOut)
def upsert_label_rule(payload: schemas.LabelRuleIn, db: Session = Depends(get_db)) -> models.StatementLabelRule:
    if db.get(models.Account, payload.account_id) is None:
        raise HTTPException(404, "account not found")
    if db.get(models.Category, payload.category_id) is None:
        raise HTTPException(404, "category not found")
    # SQLite's atomic upsert preserves the existing mapping ID and handles two
    # requests confirming the same scoped label without duplicate inserts.
    statement = insert(models.StatementLabelRule).values(**payload.model_dump())
    statement = statement.on_conflict_do_update(
        index_elements=["account_id", "label", "direction"],
        set_={"category_id": payload.category_id},
    )
    db.execute(statement)
    db.commit()
    return db.query(models.StatementLabelRule).populate_existing().filter_by(
        account_id=payload.account_id, label=payload.label, direction=payload.direction,
    ).one()


@router.delete("/labels/{label_rule_id}")
def delete_label_rule(label_rule_id: int, db: Session = Depends(get_db)) -> dict:
    rule = db.get(models.StatementLabelRule, label_rule_id)
    if rule is None:
        raise HTTPException(404, "label rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}


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
    account_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    changed = recategorize_all(db, only_uncategorized=only_uncategorized, overwrite_user=overwrite_user, account_id=account_id)
    return {"changed": changed}
