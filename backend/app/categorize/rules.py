from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from .. import models


@dataclass
class RuleHit:
    category_id: int
    pattern: str
    priority: int


def match_rule(db: Session, text: str, *, direction: Optional[str] = None) -> Optional[RuleHit]:
    """Return the highest-priority rule that matches the given text.
    Lower priority number = higher precedence (10 beats 90)."""
    if not text:
        return None
    text_lc = text.lower()
    rules = db.query(models.Rule).options(joinedload(models.Rule.category)).order_by(models.Rule.priority.asc(), models.Rule.id.asc()).all()
    for r in rules:
        if r.note == "seed" and direction == "debit" and r.category.name in {"Salary", "Interest Income"}:
            continue  # A payment labelled salary is not salary received.
        # Old built-ins mapped bare "loan", "borrow" and person names to Loan
        # Given. Neither the word nor a name identifies which side lent money.
        # Keep user rules intact, and require an explicit outgoing "lend" hint
        # before using the built-in Loan Given category.
        if r.note == "seed" and r.category.name == "Loan Given":
            if r.pattern.lower() != "lend" or direction != "debit":
                continue
        if r.note in {"auto-grown (credit)", "auto-grown (debit)"}:
            if r.note != f"auto-grown ({direction})":
                continue
        if r.is_regex:
            try:
                if re.search(r.pattern, text, re.IGNORECASE):
                    return RuleHit(category_id=r.category_id, pattern=r.pattern, priority=r.priority)
            except re.error:
                continue
        elif r.note == "seed":
            # Built-in keywords identify words, not fragments of unrelated
            # merchants (for example ride inside Trident or lic inside Public).
            pattern = r"(?<!\w)" + re.escape(r.pattern) + r"(?!\w)"
            if re.search(pattern, text, re.IGNORECASE):
                return RuleHit(category_id=r.category_id, pattern=r.pattern, priority=r.priority)
        else:
            if r.pattern.lower() in text_lc:
                return RuleHit(category_id=r.category_id, pattern=r.pattern, priority=r.priority)
    return None
