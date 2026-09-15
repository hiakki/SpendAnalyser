from __future__ import annotations

import shutil
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..categorize.autogrow import autogrow_categories
from ..categorize.service import categorize_text
from ..config import get_settings
from ..db import get_db
from ..parsers import parse_file

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=schemas.UploadResult)
async def upload_statement(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> schemas.UploadResult:
    cfg = get_settings()
    acct = db.get(models.Account, account_id)
    if not acct:
        raise HTTPException(404, "account not found")
    if not file.filename:
        raise HTTPException(400, "missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".xls", ".xlsx", ".csv", ".txt"}:
        raise HTTPException(400, f"unsupported file type {suffix}")

    upload_dir = Path(cfg.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}{suffix}"
    saved_path = upload_dir / saved_name
    with saved_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        parsed = parse_file(saved_path, password=password or None)
    except Exception as exc:  # noqa: BLE001
        saved_path.unlink(missing_ok=True)
        msg = str(exc).lower()
        if "password" in msg or "encrypted" in msg:
            raise HTTPException(401, "PDF is password-protected. Provide the password and re-upload.") from exc
        raise HTTPException(422, f"failed to parse: {exc}") from exc

    stmt = models.Statement(
        account_id=account_id,
        filename=file.filename,
        storage_path=str(saved_path),
        file_kind=suffix.lstrip("."),
        detected_format=parsed.detected_format,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
        n_parsed=len(parsed.rows),
        parse_log="\n".join(parsed.log + parsed.warnings) or None,
    )
    db.add(stmt)
    db.flush()

    inserted = 0
    dups = 0
    occurrences: dict[str, int] = defaultdict(int)
    for row in parsed.rows:
        natural_key = row.fingerprint_key()
        occurrences[natural_key] += 1
        fingerprint = row.fingerprint_for_occurrence(occurrences[natural_key])
        if db.query(models.Transaction.id).filter_by(account_id=account_id, fingerprint=fingerprint).first():
            dups += 1
            continue
        # If the user typed a comment in their UPI/banking app, treat it as the
        # primary categorisation signal — it's the most reliable thing we have.
        if row.user_label:
            cat_id, source = categorize_text(db, row.user_label)
            if cat_id is not None and source == "rule":
                source = "upi_label"
            else:
                # Fall back to full description so we don't lose merchant signal entirely.
                cat_id, source = categorize_text(
                    db, " ".join(filter(None, [row.user_label, row.merchant, row.description]))
                )
        else:
            cat_id, source = categorize_text(
                db, " ".join(filter(None, [row.merchant, row.description]))
            )
        txn = models.Transaction(
            account_id=account_id,
            posted_at=row.posted_at,
            value_at=row.value_at,
            description=row.description,
            merchant=row.merchant,
            raw_amount=row.amount,
            currency=row.currency or acct.currency,
            direction=row.direction,
            category_id=cat_id,
            category_source=source,
            note=row.user_label,
            fingerprint=fingerprint,
            statement_id=stmt.id,
        )
        try:
            # A duplicate must not roll back earlier rows or the statement.
            with db.begin_nested():
                db.add(txn)
                db.flush()
            inserted += 1
        except IntegrityError:
            # A concurrent import can insert the same fingerprint after our
            # lookup. Other integrity failures must remain visible as errors.
            if not db.query(models.Transaction.id).filter_by(account_id=account_id, fingerprint=fingerprint).first():
                raise
            dups += 1

    stmt.n_inserted = inserted
    stmt.n_duplicates = dups
    db.commit()
    db.refresh(stmt)

    # Auto-promote repetitive 'Other' merchants into their own categories so the
    # dashboard doesn't drown in 'Other'. Unknown one-off payments stay for review.
    if inserted > 0:
        try:
            grow = autogrow_categories(db, min_count=2)
            if grow["created_categories"] or grow["reassigned"] or grow["loan_assigned"]:
                parsed.warnings.append(
                    f"auto-grow: created {len(grow['created_categories'])} categories, "
                    f"reassigned {grow['reassigned']} txns"
                )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            parsed.warnings.append(f"auto-grow skipped: {exc}")

    return schemas.UploadResult(
        statement=schemas.StatementOut.model_validate(stmt),
        inserted=inserted,
        duplicates=dups,
        warnings=parsed.warnings,
    )


@router.get("/statements")
def list_statements(db: Session = Depends(get_db)) -> list[dict]:
    """List ingested statements with per-direction counts so the user can
    immediately spot 'no credits parsed' bugs."""
    from sqlalchemy import func

    stmts = db.query(models.Statement).order_by(models.Statement.created_at.desc()).all()
    counts: dict[tuple[int, str], int] = {}
    for sid, direction, cnt in (
        db.query(
            models.Transaction.statement_id,
            models.Transaction.direction,
            func.count(),
        )
        .group_by(models.Transaction.statement_id, models.Transaction.direction)
        .all()
    ):
        counts[(sid, direction)] = cnt

    out = []
    for s in stmts:
        out.append({
            "id": s.id,
            "account_id": s.account_id,
            "filename": s.filename,
            "file_kind": s.file_kind,
            "detected_format": s.detected_format,
            "period_start": s.period_start.isoformat() if s.period_start else None,
            "period_end": s.period_end.isoformat() if s.period_end else None,
            "n_parsed": s.n_parsed,
            "n_inserted": s.n_inserted,
            "n_duplicates": s.n_duplicates,
            "debit_count": counts.get((s.id, "debit"), 0),
            "credit_count": counts.get((s.id, "credit"), 0),
            "parse_log": s.parse_log,
        })
    return out


@router.get("/statements/{statement_id}/transactions")
def statement_transactions(statement_id: int, limit: int = 10, db: Session = Depends(get_db)) -> list[dict]:
    """First N parsed rows of a statement — helpful for diagnosing parser quirks
    ('all my credits came in as debits', 'descriptions are mangled', etc.)."""
    s = db.get(models.Statement, statement_id)
    if not s:
        raise HTTPException(404, "statement not found")
    txns = (
        db.query(models.Transaction)
        .filter(models.Transaction.statement_id == statement_id)
        .order_by(models.Transaction.posted_at.asc(), models.Transaction.id.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "posted_at": t.posted_at.isoformat(),
            "description": t.description,
            "merchant": t.merchant,
            "amount": t.raw_amount,
            "direction": t.direction,
            "note": t.note,
            "category_name": t.category.name if t.category else None,
            "category_source": t.category_source,
        }
        for t in txns
    ]
