from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from .. import models


@dataclass
class RuleHit:
    category_id: int
    pattern: str
    priority: int


def match_rule(db: Session, text: str) -> Optional[RuleHit]:
    """Return the highest-priority rule that matches the given text.
    Lower priority number = higher precedence (10 beats 90)."""
    if not text:
        return None
    text_lc = text.lower()
    rules = db.query(models.Rule).order_by(models.Rule.priority.asc()).all()
    for r in rules:
        if r.is_regex:
            try:
                if re.search(r.pattern, text, re.IGNORECASE):
                    return RuleHit(category_id=r.category_id, pattern=r.pattern, priority=r.priority)
            except re.error:
                continue
        else:
            if r.pattern.lower() in text_lc:
                return RuleHit(category_id=r.category_id, pattern=r.pattern, priority=r.priority)
    return None
