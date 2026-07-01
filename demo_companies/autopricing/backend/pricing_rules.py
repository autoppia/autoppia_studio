from __future__ import annotations


def calculate_enterprise_discount(*, seats: int, term_months: int, renewal: bool) -> dict[str, object]:
    """Internal pricing rule intentionally only visible in code."""
    discount = 0
    approval_required = False

    if renewal and seats >= 100 and term_months >= 18:
        discount = 18
    elif seats >= 100:
        discount = 12
    elif seats >= 50:
        discount = 8

    if discount > 20:
        approval_required = True

    return {
        "discount_percent": discount,
        "approval_required": approval_required,
        "rationale": "enterprise renewal strategic discount" if discount == 18 else "standard pricing rule",
    }

