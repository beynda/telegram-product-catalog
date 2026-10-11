from decimal import Decimal
from unittest import TestCase

from app.models import MarkupRule
from app.pricing import apply_fixed_markup, apply_markup, apply_markup_rule


class PricingTests(TestCase):
    def test_adds_ten_percent_without_thousand_rounding(self) -> None:
        self.assertEqual(apply_markup(82_000, Decimal("10")), 90_200)

    def test_rounds_half_up_to_minor_unit(self) -> None:
        self.assertEqual(apply_markup(82_005, Decimal("10")), 90_206)

    def test_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            apply_markup(0, Decimal("10"))
        with self.assertRaises(ValueError):
            apply_markup(1_000, Decimal("-1"))


class FixedMarkupTests(TestCase):
    def test_adds_a_fixed_amount(self) -> None:
        self.assertEqual(apply_fixed_markup(82_000, 2_000), 84_000)

    def test_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            apply_fixed_markup(0, 2_000)
        with self.assertRaises(ValueError):
            apply_fixed_markup(1_000, -1)

    def test_apply_markup_rule_dispatches_by_kind(self) -> None:
        self.assertEqual(apply_markup_rule(82_000, MarkupRule("percent", Decimal("10"))), 90_200)
        self.assertEqual(apply_markup_rule(82_000, MarkupRule("fixed", Decimal("2000"))), 84_000)

