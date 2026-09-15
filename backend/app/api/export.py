from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..db import get_db

router = APIRouter(prefix="/export", tags=["export"])


def _spreadsheet_text(value: str | None) -> str:
    """Keep statement-controlled text from becoming a spreadsheet formula."""
    text = value or ""
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


@router.get("/csv")
def export_csv(
    start: Optional[date] = None,
    end: Optional[date] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    direction: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
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
        query = query.filter(
            or_(models.Transaction.category_id.is_(None), models.Transaction.category_source == "label_review")
            if category_id == 0 else models.Transaction.category_id == category_id
        )
    if direction:
        query = query.filter(models.Transaction.direction == direction)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(
            models.Transaction.description.ilike(like),
            models.Transaction.merchant.ilike(like),
        ))
    txns = query.order_by(models.Transaction.posted_at.asc(), models.Transaction.id.asc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "date", "account", "description", "merchant", "amount", "currency",
        "direction", "category", "category_source", "note",
    ])
    for t in txns:
        writer.writerow([
            t.posted_at.isoformat(),
            _spreadsheet_text(t.account.name if t.account else ""),
            _spreadsheet_text(t.description),
            _spreadsheet_text(t.merchant),
            f"{t.raw_amount:.2f}",
            _spreadsheet_text(t.currency),
            _spreadsheet_text(t.direction),
            _spreadsheet_text(t.category.name if t.category else ""),
            _spreadsheet_text(t.category_source),
            _spreadsheet_text(t.note),
        ])
    buf.seek(0)
    fname = "transactions"
    if start or end:
        fname += f"_{start or 'all'}_{end or 'now'}"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}.csv"},
    )
