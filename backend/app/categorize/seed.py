"""Seed categories + default rules covering common Indian merchants."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models


DEFAULT_CATEGORIES: list[tuple[str, str, str]] = [
    ("Food & Dining", "utensils", "#ef4444"),
    ("Groceries", "shopping-basket", "#f59e0b"),
    ("Transport", "car", "#3b82f6"),
    ("Ride", "bike", "#60a5fa"),
    ("Travel", "plane", "#06b6d4"),
    ("Shopping", "shopping-bag", "#ec4899"),
    ("Entertainment", "tv", "#a855f7"),
    ("Bills & Utilities", "zap", "#10b981"),
    ("Water", "droplet", "#22d3ee"),
    ("Rent & Housing", "home", "#0ea5e9"),
    ("Medical Expenses", "heart-pulse", "#f43f5e"),
    ("Education", "graduation-cap", "#6366f1"),
    ("Insurance", "shield", "#14b8a6"),
    ("Investments", "trending-up", "#22c55e"),
    ("Salary", "wallet", "#84cc16"),
    ("Interest Income", "piggy-bank", "#16a34a"),
    ("Transfers", "arrow-right-left", "#94a3b8"),
    ("Loan Given", "hand-coins", "#a16207"),
    ("Cash & ATM", "banknote", "#64748b"),
    ("Fees & Charges", "receipt", "#dc2626"),
    ("Fuel", "fuel", "#f97316"),
    ("Subscriptions", "repeat", "#7c3aed"),
    ("Personal Care", "scissors", "#d946ef"),
    ("Gifts & Donations", "gift", "#fb7185"),
    ("Family", "users", "#0f766e"),
    ("Gardening", "flower-2", "#65a30d"),
    ("Flat Expenses", "building-2", "#0891b2"),
    ("Pooja", "flame", "#fbbf24"),
    ("Nariyal Pani", "leaf", "#84cc16"),
    ("Other", "circle", "#9ca3af"),
]


# Names that existed before but were renamed; mapping is old → new.
CATEGORY_RENAMES: dict[str, str] = {
    "Health": "Medical Expenses",
}


# (pattern_lowercase, category_name, priority)
DEFAULT_RULES: list[tuple[str, str, int]] = [
    # Food
    ("zomato", "Food & Dining", 10),
    ("swiggy", "Food & Dining", 10),
    ("eatfit", "Food & Dining", 20),
    ("dominos", "Food & Dining", 20),
    ("kfc", "Food & Dining", 20),
    ("mcdonald", "Food & Dining", 20),
    ("starbucks", "Food & Dining", 20),
    ("cafe", "Food & Dining", 60),
    ("restaurant", "Food & Dining", 60),
    ("biryani", "Food & Dining", 60),
    # Groceries
    ("bigbasket", "Groceries", 10),
    ("blinkit", "Groceries", 10),
    ("zepto", "Groceries", 10),
    ("dmart", "Groceries", 10),
    ("instamart", "Groceries", 10),
    ("reliance fresh", "Groceries", 10),
    ("more retail", "Groceries", 10),
    ("nature's basket", "Groceries", 10),
    # Transport
    ("uber", "Transport", 10),
    ("ola", "Transport", 10),
    ("rapido", "Transport", 10),
    ("namma yatri", "Transport", 10),
    ("blusmart", "Transport", 10),
    ("metro", "Transport", 40),
    # Travel
    ("makemytrip", "Travel", 10),
    ("goibibo", "Travel", 10),
    ("ixigo", "Travel", 10),
    ("yatra", "Travel", 10),
    ("irctc", "Travel", 10),
    ("indigo", "Travel", 10),
    ("vistara", "Travel", 10),
    ("air india", "Travel", 10),
    ("airbnb", "Travel", 10),
    ("oyo", "Travel", 10),
    ("booking.com", "Travel", 10),
    # Fuel
    ("indianoil", "Fuel", 10),
    ("hpcl", "Fuel", 10),
    ("bharat petroleum", "Fuel", 10),
    ("bpcl", "Fuel", 10),
    ("petrol", "Fuel", 30),
    ("fuel", "Fuel", 30),
    # Shopping
    ("amazon", "Shopping", 20),
    ("flipkart", "Shopping", 10),
    ("myntra", "Shopping", 10),
    ("ajio", "Shopping", 10),
    ("meesho", "Shopping", 10),
    ("nykaa", "Shopping", 10),
    ("decathlon", "Shopping", 10),
    ("ikea", "Shopping", 10),
    ("croma", "Shopping", 10),
    ("apple store", "Shopping", 10),
    # Entertainment / Subscriptions
    ("netflix", "Subscriptions", 10),
    ("spotify", "Subscriptions", 10),
    ("hotstar", "Subscriptions", 10),
    ("prime video", "Subscriptions", 10),
    ("youtube premium", "Subscriptions", 10),
    ("sonyliv", "Subscriptions", 10),
    ("zee5", "Subscriptions", 10),
    ("apple.com/bill", "Subscriptions", 10),
    ("google play", "Subscriptions", 10),
    ("bookmyshow", "Entertainment", 10),
    ("pvr", "Entertainment", 10),
    ("inox", "Entertainment", 10),
    # Bills & Utilities
    ("airtel", "Bills & Utilities", 20),
    ("jio", "Bills & Utilities", 20),
    ("vi postpaid", "Bills & Utilities", 20),
    ("vodafone", "Bills & Utilities", 20),
    ("bescom", "Bills & Utilities", 10),
    ("tata power", "Bills & Utilities", 10),
    ("adani electricity", "Bills & Utilities", 10),
    ("act fibernet", "Bills & Utilities", 10),
    ("electricity", "Bills & Utilities", 40),
    ("gas bill", "Bills & Utilities", 40),
    # Rent
    ("nobroker", "Rent & Housing", 10),
    ("rentpay", "Rent & Housing", 10),
    ("rent", "Rent & Housing", 60),
    # Medical
    ("apollo", "Medical Expenses", 20),
    ("1mg", "Medical Expenses", 10),
    ("pharmeasy", "Medical Expenses", 10),
    ("netmeds", "Medical Expenses", 10),
    ("practo", "Medical Expenses", 10),
    ("cult.fit", "Medical Expenses", 10),
    ("cultfit", "Medical Expenses", 10),
    ("medplus", "Medical Expenses", 10),
    # Education
    ("byjus", "Education", 10),
    ("unacademy", "Education", 10),
    ("coursera", "Education", 10),
    ("udemy", "Education", 10),
    # Insurance / Investments
    ("policybazaar", "Insurance", 10),
    ("hdfc life", "Insurance", 10),
    ("lic", "Insurance", 20),
    ("zerodha", "Investments", 10),
    ("groww", "Investments", 10),
    ("upstox", "Investments", 10),
    ("mutual fund", "Investments", 20),
    ("sip", "Investments", 50),
    # Salary / transfers
    ("salary", "Salary", 10),
    ("neft", "Transfers", 80),
    ("imps", "Transfers", 80),
    ("rtgs", "Transfers", 80),
    ("upi-", "Transfers", 90),
    # Cash / fees
    ("atm wdl", "Cash & ATM", 10),
    ("atm-cash", "Cash & ATM", 10),
    ("cash withdrawal", "Cash & ATM", 10),
    ("gst", "Fees & Charges", 60),
    ("late fee", "Fees & Charges", 10),
    ("finance charge", "Fees & Charges", 10),
    ("annual fee", "Fees & Charges", 10),
    # Personal care
    ("urban company", "Personal Care", 10),
    ("urbanclap", "Personal Care", 10),
    ("salon", "Personal Care", 30),

    # ---- User UPI-app labels (high precedence; these are notes the user typed themselves) ----
    # Food
    ("junk food", "Food & Dining", 5),
    ("lunch", "Food & Dining", 5),
    ("dinner", "Food & Dining", 5),
    ("breakfast", "Food & Dining", 5),
    ("snack", "Food & Dining", 5),
    ("tea", "Food & Dining", 8),
    ("coffee", "Food & Dining", 8),
    ("food", "Food & Dining", 9),
    ("dining", "Food & Dining", 8),
    ("eating out", "Food & Dining", 5),
    # Groceries
    ("groceries", "Groceries", 5),
    ("grocery", "Groceries", 5),
    ("vegetable", "Groceries", 5),
    ("vegetables", "Groceries", 5),
    ("veggies", "Groceries", 5),
    ("veg", "Groceries", 8),
    ("milk", "Groceries", 5),
    ("dairy", "Groceries", 5),
    ("fruit", "Groceries", 5),
    ("fruits", "Groceries", 5),
    ("meat", "Groceries", 5),
    ("chicken", "Groceries", 5),
    # Transport / Fuel
    ("petrol", "Fuel", 5),
    ("diesel", "Fuel", 5),
    ("auto", "Transport", 9),
    ("cab", "Transport", 8),
    ("taxi", "Transport", 8),
    ("parking", "Transport", 8),
    ("toll", "Transport", 8),
    # Travel
    ("us visa", "Travel", 5),
    ("visa", "Travel", 9),
    ("passport", "Travel", 5),
    ("flight", "Travel", 5),
    ("ticket", "Travel", 9),
    ("trip", "Travel", 8),
    ("hotel", "Travel", 5),
    ("stay", "Travel", 9),
    # Bills & Utilities
    ("electricity", "Bills & Utilities", 8),
    ("water bill", "Bills & Utilities", 5),
    ("internet", "Bills & Utilities", 8),
    ("wifi", "Bills & Utilities", 8),
    ("broadband", "Bills & Utilities", 8),
    ("mobile recharge", "Bills & Utilities", 5),
    ("recharge", "Bills & Utilities", 9),
    # Rent
    ("rent", "Rent & Housing", 5),
    ("maintenance", "Rent & Housing", 8),
    ("society", "Rent & Housing", 8),
    # Home / personal care
    ("gardening", "Gardening", 5),
    ("haircut", "Personal Care", 5),
    ("laundry", "Personal Care", 5),
    ("dry clean", "Personal Care", 5),
    # Medical / Health
    ("doctor", "Medical Expenses", 5),
    ("medicine", "Medical Expenses", 5),
    ("medicines", "Medical Expenses", 5),
    ("meds", "Medical Expenses", 5),
    ("med", "Medical Expenses", 6),
    ("hospital", "Medical Expenses", 5),
    ("pharmacy", "Medical Expenses", 5),
    ("gym", "Medical Expenses", 8),
    # Transfers
    ("self", "Transfers", 5),
    ("self transfer", "Transfers", 5),
    ("transfer", "Transfers", 9),
    ("mom", "Transfers", 9),
    ("dad", "Transfers", 9),
    ("family", "Family", 9),
    ("friend", "Transfers", 9),
    # Gifts & donations
    ("gift", "Gifts & Donations", 5),
    ("donation", "Gifts & Donations", 5),
    ("charity", "Gifts & Donations", 5),
    # Investments
    ("invest", "Investments", 8),
    ("mutual", "Investments", 8),
    # Shopping
    ("shopping", "Shopping", 3),
    ("clothes", "Shopping", 5),
    ("clothing", "Shopping", 5),
    # Education
    ("school fees", "Education", 5),
    ("tuition", "Education", 5),
    ("course", "Education", 8),
    ("books", "Education", 8),

    # ---- User-specific labels (top precedence) ----
    ("sbint", "Interest Income", 3),
    ("interest credit", "Interest Income", 3),
    ("int credit", "Interest Income", 3),
    ("savings interest", "Interest Income", 3),
    ("pooja", "Pooja", 4),
    ("puja", "Pooja", 4),
    ("pooja bh", "Shopping", 3),
    ("poojabh", "Shopping", 3),
    ("nariyal pani", "Nariyal Pani", 4),
    ("nariyal", "Nariyal Pani", 5),
    ("coconut water", "Nariyal Pani", 5),
    ("ride", "Ride", 2),
    ("rides", "Ride", 2),
    ("loan", "Loan Given", 4),
    ("lend", "Loan Given", 5),
    ("borrow", "Loan Given", 5),
    ("sahil gup", "Loan Given", 3),
    ("ssy account", "Family", 3),
    ("essy transaction", "Family", 3),
    ("sukanya", "Family", 3),
    ("sukanya samridhi", "Family", 3),
    ("sukanya samriddhi", "Family", 3),
    ("beti0110230000043", "Family", 3),
    ("star heal", "Family", 3),
    ("parents health insurance", "Family", 3),
    ("giva", "Shopping", 3),
    ("flat cook", "Flat Expenses", 3),
    ("flatcook", "Flat Expenses", 3),
    ("water", "Water", 6),
    ("waterb", "Water", 6),
    ("water bill", "Water", 4),
    ("movie", "Entertainment", 5),
    ("movies", "Entertainment", 4),
    ("moviesj", "Entertainment", 5),
    ("cinema", "Entertainment", 5),
    ("cook", "Personal Care", 7),
    ("maid", "Personal Care", 7),
    ("housekeeping", "Personal Care", 5),
    ("driver", "Transport", 7),
    ("auto rickshaw", "Transport", 5),
]


def seed_categories_and_rules(db: Session) -> None:
    # 1. Apply renames first so existing transactions/rules carry over
    for old_name, new_name in CATEGORY_RENAMES.items():
        cat = db.query(models.Category).filter_by(name=old_name).first()
        target = db.query(models.Category).filter_by(name=new_name).first()
        if cat and not target:
            cat.name = new_name
        elif cat and target and cat.id != target.id:
            # Both exist; move rules + transactions to the canonical target, then drop old.
            db.query(models.Rule).filter_by(category_id=cat.id).update({"category_id": target.id})
            db.query(models.Transaction).filter_by(category_id=cat.id).update({"category_id": target.id})
            db.delete(cat)
    db.flush()

    name_to_cat: dict[str, models.Category] = {}
    for name, icon, color in DEFAULT_CATEGORIES:
        cat = db.query(models.Category).filter_by(name=name).first()
        if not cat:
            cat = models.Category(name=name, icon=icon, color=color)
            db.add(cat)
            db.flush()
        name_to_cat[name] = cat

    existing_patterns = {(r.pattern, r.category_id) for r in db.query(models.Rule).all()}
    for pattern, cat_name, prio in DEFAULT_RULES:
        cat = name_to_cat.get(cat_name)
        if not cat:
            continue
        if (pattern, cat.id) in existing_patterns:
            continue
        db.add(models.Rule(pattern=pattern, is_regex=False, category_id=cat.id, priority=prio, note="seed"))
    db.commit()


def ensure_category(db: Session, name: str, *, icon: str = "tag", color: str = "#a3a3a3") -> models.Category:
    """Idempotently get-or-create a category by name."""
    cat = db.query(models.Category).filter_by(name=name).first()
    if cat:
        return cat
    cat = models.Category(name=name, icon=icon, color=color)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
