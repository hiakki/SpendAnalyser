from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Account(Base):
    """A bank / credit-card account whose statements we ingest."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="bank")  # bank | credit_card | wallet
    institution: Mapped[Optional[str]] = mapped_column(String(120))
    last4: Mapped[Optional[str]] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account", cascade="all,delete")
    statement_label_rules: Mapped[list["StatementLabelRule"]] = relationship(back_populates="account", cascade="all,delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(32))
    color: Mapped[Optional[str]] = mapped_column(String(16))

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    statement_label_rules: Mapped[list["StatementLabelRule"]] = relationship(back_populates="category", cascade="all,delete-orphan")


class Rule(Base):
    """User-editable categorization rule. Pattern is a case-insensitive substring or regex."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    note: Mapped[Optional[str]] = mapped_column(String(255))

    category: Mapped[Category] = relationship()


class StatementLabelRule(Base):
    """Confirmed label meaning for one account and money-flow direction."""

    __tablename__ = "statement_label_rules"
    __table_args__ = (
        UniqueConstraint("account_id", "label", "direction", name="uq_statement_label_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    account: Mapped[Account] = relationship(back_populates="statement_label_rules")
    category: Mapped[Category] = relationship(back_populates="statement_label_rules")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "fingerprint", name="uq_tx_account_fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    posted_at: Mapped[date] = mapped_column(Date, nullable=False)
    value_at: Mapped[Optional[date]] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    merchant: Mapped[Optional[str]] = mapped_column(String(255))
    raw_amount: Mapped[float] = mapped_column(Float, nullable=False)  # positive = credit, negative = debit
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # debit | credit
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    category_source: Mapped[Optional[str]] = mapped_column(String(16))  # rule | llm | user | upi_label
    note: Mapped[Optional[str]] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    statement_id: Mapped[Optional[int]] = mapped_column(ForeignKey("statements.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped[Account] = relationship(back_populates="transactions")
    category: Mapped[Optional[Category]] = relationship(back_populates="transactions")
    statement: Mapped[Optional["Statement"]] = relationship(back_populates="transactions")


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(16))  # pdf | xlsx | xls | csv
    detected_format: Mapped[Optional[str]] = mapped_column(String(64))
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    n_parsed: Mapped[int] = mapped_column(Integer, default=0)
    n_inserted: Mapped[int] = mapped_column(Integer, default=0)
    n_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    parse_log: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transactions: Mapped[list[Transaction]] = relationship(back_populates="statement")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("category_id", "month", name="uq_budget_cat_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM ; "*" for recurring monthly
    amount: Mapped[float] = mapped_column(Float, nullable=False)

    category: Mapped[Category] = relationship()


class LLMCache(Base):
    """Cache of merchant -> (category, confidence) decisions from the LLM."""

    __tablename__ = "llm_cache"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)  # normalized merchant
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
