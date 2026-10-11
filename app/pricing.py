from decimal import Decimal, ROUND_HALF_UP

from app.models import MarkupRule


def apply_markup(source_price: int, markup_percent: Decimal) -> int:
    """Apply markup and round only fractional minor units."""
    if source_price <= 0:
        raise ValueError("Price must be positive")
    if markup_percent < 0 or markup_percent > 100:
        raise ValueError("Markup must be between 0 and 100 percent")

    multiplier = (Decimal("100") + markup_percent) / Decimal("100")
    return int((Decimal(source_price) * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def apply_fixed_markup(source_price: int, amount: int) -> int:
    """Add a fixed amount in minor currency units on top of the source price."""
    if source_price <= 0:
        raise ValueError("Price must be positive")
    if amount < 0:
        raise ValueError("Fixed markup cannot be negative")
    return source_price + amount


def apply_markup_rule(source_price: int, rule: MarkupRule) -> int:
    if rule.kind == "fixed":
        return apply_fixed_markup(source_price, int(rule.value))
    return apply_markup(source_price, rule.value)

