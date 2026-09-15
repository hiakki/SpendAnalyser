from __future__ import annotations

import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..categorize.autogrow import autogrow_categories
from ..categorize.service import categorize_text, recategorize_all
from ..categorize.seed import seed_categories_and_rules
from ..db import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
def reset_db(db: Session = Depends(get_db)) -> dict:
    db.query(models.Transaction).delete()
    db.query(models.Statement).delete()
    db.query(models.Budget).delete()
    db.query(models.Rule).delete()
    db.query(models.Category).delete()
    db.query(models.Account).delete()
    db.query(models.LLMCache).delete()
    db.commit()
    seed_categories_and_rules(db)
    return {"ok": True}


@router.post("/seed-mock")
def seed_mock(months: int = 6, db: Session = Depends(get_db)) -> dict:
    """Create a couple of fake accounts and a few months of plausible transactions."""
    # ensure base categories/rules
    seed_categories_and_rules(db)

    accts: dict[str, models.Account] = {}
    for name, kind, inst in [
        ("HDFC Savings", "bank", "HDFC"),
        ("ICICI Amazon Pay CC", "credit_card", "ICICI"),
        ("Axis Bank Savings", "bank", "Axis"),
    ]:
        a = db.query(models.Account).filter_by(name=name).first()
        if not a:
            a = models.Account(name=name, kind=kind, institution=inst, currency="INR")
            db.add(a)
            db.flush()
        accts[name] = a

    today = date.today()
    start = (today.replace(day=1) - timedelta(days=30 * months)).replace(day=1)

    recurring_pool = [
        ("Netflix subscription", 649, "ICICI Amazon Pay CC", 28),
        ("Spotify Premium", 119, "ICICI Amazon Pay CC", 30),
        ("Apartment Rent NoBroker", 35000, "HDFC Savings", 30),
        ("ACT Fibernet", 1199, "HDFC Savings", 30),
        ("Cult.fit Live", 1499, "Axis Bank Savings", 30),
    ]
    discretionary_pool = [
        ("UPI-ZOMATO-zomato@hdfcbank", 250, 800, "HDFC Savings"),
        ("SWIGGY ORDERS", 200, 700, "HDFC Savings"),
        ("UBER INDIA SYSTEMS", 120, 550, "HDFC Savings"),
        ("OLA CABS", 80, 420, "HDFC Savings"),
        ("BLINKIT", 250, 900, "HDFC Savings"),
        ("BIGBASKET DAILY", 600, 2500, "HDFC Savings"),
        ("IRCTC RAIL TICKET", 800, 3200, "ICICI Amazon Pay CC"),
        ("INDIGO AIRLINES", 4500, 14000, "ICICI Amazon Pay CC"),
        ("AMAZON IN", 200, 4500, "ICICI Amazon Pay CC"),
        ("FLIPKART", 300, 7000, "ICICI Amazon Pay CC"),
        ("MYNTRA DESIGNS", 800, 5000, "ICICI Amazon Pay CC"),
        ("ATM-CASH WITHDRAWAL", 2000, 10000, "HDFC Savings"),
        ("HPCL PETROL PUMP", 1000, 3000, "ICICI Amazon Pay CC"),
        ("1MG TECHNOLOGIES", 200, 1800, "Axis Bank Savings"),
        ("BOOKMYSHOW PVR", 250, 1100, "ICICI Amazon Pay CC"),
        ("STARBUCKS COFFEE", 250, 600, "ICICI Amazon Pay CC"),
        ("DOMINOS PIZZA", 350, 1100, "HDFC Savings"),
        ("URBAN COMPANY", 400, 2000, "Axis Bank Savings"),
        ("AIRTEL POSTPAID", 999, 1500, "HDFC Savings"),
        ("BESCOM ELECTRICITY", 1200, 4500, "HDFC Savings"),
    ]

    rng = random.Random(42)
    cur = start
    inserted = 0
    while cur <= today:
        # salary on the 1st
        if cur.day == 1:
            acct = accts["HDFC Savings"]
            t = models.Transaction(
                account_id=acct.id,
                posted_at=cur,
                description="NEFT-SALARY CR-ACME PVT LTD",
                merchant="Salary",
                raw_amount=145000,
                currency="INR",
                direction="credit",
                fingerprint=f"mock-salary-{cur}",
            )
            cat_id, source = categorize_text(db, "salary")
            t.category_id = cat_id
            t.category_source = source
            db.add(t)
            inserted += 1
        # recurring monthly
        for desc, amt, acct_name, day in recurring_pool:
            if cur.day == min(day, 28):
                acct = accts[acct_name]
                jitter = rng.uniform(-0.02, 0.02) * amt
                t = models.Transaction(
                    account_id=acct.id,
                    posted_at=cur,
                    description=desc,
                    merchant=desc.split()[0].title() if desc else None,
                    raw_amount=-round(amt + jitter, 2),
                    currency="INR",
                    direction="debit",
                    fingerprint=f"mock-rec-{desc}-{cur}",
                )
                cat_id, source = categorize_text(db, desc)
                t.category_id = cat_id
                t.category_source = source
                db.add(t)
                inserted += 1

        # 0-4 discretionary per day
        n_today = rng.choices([0, 1, 2, 3, 4], weights=[3, 4, 3, 2, 1])[0]
        for _ in range(n_today):
            desc, lo, hi, acct_name = rng.choice(discretionary_pool)
            amt = round(rng.uniform(lo, hi), 2)
            acct = accts[acct_name]
            t = models.Transaction(
                account_id=acct.id,
                posted_at=cur,
                description=desc,
                merchant=desc.split()[0].title() if desc else None,
                raw_amount=-amt,
                currency="INR",
                direction="debit",
                fingerprint=f"mock-{desc}-{cur}-{rng.randrange(1_000_000)}",
            )
            cat_id, source = categorize_text(db, desc)
            t.category_id = cat_id
            t.category_source = source
            db.add(t)
            inserted += 1
        cur += timedelta(days=1)

    db.commit()
    recategorize_all(db, only_uncategorized=True)
    return {"inserted": inserted, "accounts": list(accts.keys())}


@router.post("/seed-categories")
def seed_categories(db: Session = Depends(get_db)) -> dict:
    seed_categories_and_rules(db)
    return {"ok": True}


# (name, kind, institution)
QUICK_ACCOUNTS = [
    ("ICICI Savings", "bank", "ICICI"),
    ("HDFC Savings", "bank", "HDFC"),
    ("SBI Savings", "bank", "SBI"),
    ("Canara Savings", "bank", "Canara"),
    ("ICICI Credit Card", "credit_card", "ICICI"),
    ("HDFC Credit Card", "credit_card", "HDFC"),
    ("Axis Credit Card", "credit_card", "Axis"),
    ("SBI Credit Card", "credit_card", "SBI"),
]


@router.post("/quick-setup")
def quick_setup(db: Session = Depends(get_db)) -> dict:
    """Create the user's bank + credit-card accounts (ICICI/HDFC/SBI/Canara
    savings + ICICI/HDFC/Axis/SBI credit cards). Idempotent."""
    created = []
    skipped = []
    for name, kind, inst in QUICK_ACCOUNTS:
        if db.query(models.Account).filter_by(name=name).first():
            skipped.append(name)
            continue
        db.add(models.Account(name=name, kind=kind, institution=inst, currency="INR"))
        created.append(name)
    db.commit()
    return {"created": created, "skipped": skipped}


@router.post("/auto-grow")
def auto_grow(
    min_count: int = 2,
    account_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Find merchants in 'Other' that appear `min_count` or more times and
    promote them into their own category (with a rule so future transactions
    catch automatically). Single-occurrence payments to what looks like a
    human name default to 'Loan Given'."""
    return autogrow_categories(db, min_count=min_count, only_account_id=account_id)


@router.post("/reparse-merchants")
def reparse_merchants(
    overwrite_user: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Re-extract merchant/user-label from every transaction's description and
    re-run categorization. Use this after improving parsers or adding rules.
    Won't overwrite categories the user manually set unless `overwrite_user=true`."""
    from ..parsers.utils import extract_merchant, extract_upi_metadata
    from ..categorize.service import categorize_text

    txns = db.query(models.Transaction).all()
    merchant_changed = 0
    label_set = 0
    cat_changed = 0
    for t in txns:
        meta = extract_upi_metadata(t.description)
        new_merchant = extract_merchant(t.description) or None
        if new_merchant and new_merchant != t.merchant:
            t.merchant = new_merchant
            merchant_changed += 1
        user_label = meta.get("user_label")
        if user_label and not t.note:
            t.note = user_label
            label_set += 1
        if not overwrite_user and t.category_source == "user":
            continue
        if user_label:
            new_cat, source = categorize_text(db, user_label)
            if new_cat is not None and source == "rule":
                source = "upi_label"
            else:
                new_cat, source = categorize_text(
                    db, " ".join(filter(None, [user_label, t.merchant, t.description]))
                )
        else:
            new_cat, source = categorize_text(
                db, " ".join(filter(None, [t.merchant, t.description]))
            )
        if new_cat != t.category_id:
            t.category_id = new_cat
            t.category_source = source
            cat_changed += 1
    db.commit()
    return {
        "transactions_scanned": len(txns),
        "merchants_updated": merchant_changed,
        "user_labels_set": label_set,
        "categories_changed": cat_changed,
    }
