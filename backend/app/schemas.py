from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountIn(BaseModel):
    name: str
    kind: str = "bank"
    institution: Optional[str] = None
    last4: Optional[str] = None
    currency: str = "INR"


class AccountOut(AccountIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CategoryOut(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None
    color: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class RuleIn(BaseModel):
    pattern: str
    is_regex: bool = False
    category_id: int
    priority: int = 100
    note: Optional[str] = None


class RuleOut(RuleIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class LabelRuleIn(BaseModel):
    account_id: int
    label: str = Field(min_length=1, max_length=255)
    direction: Literal["debit", "credit"]
    category_id: int

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value):
        return " ".join(value.split()).casefold() if isinstance(value, str) else value


class LabelRuleOut(LabelRuleIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TransactionOut(BaseModel):
    id: int
    account_id: int
    account_name: Optional[str] = None
    posted_at: date
    value_at: Optional[date] = None
    description: str
    merchant: Optional[str] = None
    amount: float
    currency: str
    direction: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_color: Optional[str] = None
    category_source: Optional[str] = None
    note: Optional[str] = None


class TransactionPatch(BaseModel):
    category_id: Optional[int] = None
    note: Optional[str] = None
    merchant: Optional[str] = None


class StatementOut(BaseModel):
    id: int
    account_id: int
    filename: str
    file_kind: Optional[str] = None
    detected_format: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    n_parsed: int
    n_inserted: int
    n_duplicates: int
    parse_log: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class BudgetIn(BaseModel):
    category_id: int
    month: str = Field(default="*", description="YYYY-MM or '*' for recurring monthly")
    amount: float


class BudgetOut(BudgetIn):
    id: int
    category_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class UploadResult(BaseModel):
    statement: StatementOut
    inserted: int
    duplicates: int
    warnings: list[str] = []
