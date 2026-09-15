"""Synthetic rule matching tests; no statement files or persistent database."""

import atexit
import os
from pathlib import Path
import tempfile
import unittest

_scratch = tempfile.TemporaryDirectory(prefix=".test-rules-", dir=Path(__file__).resolve().parents[1])
atexit.register(_scratch.cleanup)
os.environ["SPENDA_DB_URL"] = "sqlite://"
os.environ["SPENDA_UPLOAD_DIR"] = _scratch.name
os.environ["SPENDA_LLM_ENABLED"] = "false"

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.categorize.rules import match_rule
from app.db import Base


class CategoryRuleMatchingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.category = models.Category(name="Synthetic category")
        self.alternate = models.Category(name="Synthetic alternate")
        self.db.add_all([self.category, self.alternate])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_rule(self, pattern, *, note="seed", category_id=None, **kwargs):
        rule = models.Rule(pattern=pattern, category_id=category_id or self.category.id, note=note, **kwargs)
        self.db.add(rule)
        self.db.commit()
        return rule

    def test_seed_keywords_do_not_match_unrelated_word_fragments(self):
        for pattern in ("ride", "ola", "lic", "rent", "cab"):
            self.add_rule(pattern)
        for text in ("Trident Hotel", "Chocolate Shop", "Public School", "Current Account", "Cabinet Shop"):
            with self.subTest(text=text):
                self.assertIsNone(match_rule(self.db, text))

    def test_seed_words_match_labels_and_punctuation_case_insensitively(self):
        self.add_rule("rent")
        self.add_rule("swiggy")
        for text, pattern in (("Rent", "rent"), ("UPI/RENT/reference", "rent"), ("SWIGGY ORDERS", "swiggy"), ("swiggy.com", "swiggy")):
            with self.subTest(text=text):
                hit = match_rule(self.db, text)
                self.assertIsNotNone(hit)
                self.assertEqual(hit.pattern, pattern)

    def test_seed_literals_escape_regex_punctuation(self):
        self.add_rule("cult.fit")
        self.assertIsNotNone(match_rule(self.db, "CULT.FIT monthly"))
        self.assertIsNone(match_rule(self.db, "cultXfit"))

    def test_custom_substring_rules_keep_existing_behavior(self):
        self.add_rule("ride", note="My custom substring")
        self.assertIsNotNone(match_rule(self.db, "Trident Hotel"))

    def test_custom_rule_without_note_keeps_substring_behavior(self):
        self.add_rule("ola", note=None)
        self.assertIsNotNone(match_rule(self.db, "Chocolate Shop"))

    def test_regex_rules_keep_regex_semantics_even_if_seeded(self):
        self.add_rule("ride", is_regex=True)
        self.assertIsNotNone(match_rule(self.db, "Trident Hotel"))
        self.add_rule("[", is_regex=True, priority=0)
        self.assertIsNotNone(match_rule(self.db, "Trident Hotel"))

    def test_priority_then_id_defines_deterministic_winner(self):
        self.add_rule("rent", id=20, priority=10)
        self.add_rule("rent", id=10, priority=10, category_id=self.alternate.id)
        self.assertEqual(match_rule(self.db, "Rent").category_id, self.alternate.id)
        self.add_rule("rent", id=30, priority=1)
        self.assertEqual(match_rule(self.db, "Rent").category_id, self.category.id)

    def test_auto_grown_rules_match_only_their_declared_direction(self):
        self.add_rule("synthetic merchant", note="auto-grown (credit)")
        self.add_rule("synthetic merchant", note="auto-grown (debit)", category_id=self.alternate.id)
        self.assertEqual(match_rule(self.db, "Synthetic Merchant", direction="credit").category_id, self.category.id)
        self.assertEqual(match_rule(self.db, "Synthetic Merchant", direction="debit").category_id, self.alternate.id)
        self.assertIsNone(match_rule(self.db, "Synthetic Merchant"))
        self.assertIsNone(match_rule(self.db, "Synthetic Merchant", direction="unknown"))

    def test_mismatched_auto_rule_does_not_block_an_eligible_rule(self):
        self.add_rule("synthetic merchant", note="auto-grown (credit)", priority=1)
        self.add_rule("merchant", category_id=self.alternate.id, priority=20)
        self.assertEqual(match_rule(self.db, "Synthetic Merchant", direction="debit").category_id, self.alternate.id)

    def test_legacy_loan_seeds_do_not_guess_which_side_lent_money(self):
        loan = models.Category(name="Loan Given")
        self.db.add(loan)
        self.db.commit()
        for pattern in ("loan", "borrow", "example person", "lend"):
            self.add_rule(pattern, category_id=loan.id)
        for text in ("Example loan", "return loan", "borrow", "example person"):
            for direction in ("debit", "credit"):
                with self.subTest(text=text, direction=direction):
                    self.assertIsNone(match_rule(self.db, text, direction=direction))
        self.assertIsNone(match_rule(self.db, "lend", direction="credit"))
        self.assertEqual(match_rule(self.db, "lend", direction="debit").category_id, loan.id)
        self.add_rule("example loan", category_id=loan.id, note="User confirmed")
        self.assertEqual(match_rule(self.db, "example loan", direction="debit").category_id, loan.id)

    def test_seed_income_rules_cannot_classify_outgoing_payments(self):
        salary = models.Category(name="Salary")
        self.db.add(salary)
        self.db.commit()
        self.add_rule("salary", category_id=salary.id)
        self.assertIsNone(match_rule(self.db, "salary payment", direction="debit"))
        self.assertEqual(match_rule(self.db, "salary", direction="credit").category_id, salary.id)


if __name__ == "__main__":
    unittest.main()
