from __future__ import annotations

from typing import Any


PRODUCT_CODE_ALIASES = {
    "prd_20260518095708_9f77db": "subscription_trial_month",
    "prd_20260601055439_3c4f56": "premium_monthly_trial",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def canonical_product_code(product_code: Any) -> str:
    code = _normalized_text(product_code)
    return PRODUCT_CODE_ALIASES.get(code, code)


def product_code_filter_values(product_code: Any) -> list[str]:
    code = _normalized_text(product_code)
    if not code:
        return []
    canonical = canonical_product_code(code)
    values = {code, canonical}
    values.update(alias for alias, target in PRODUCT_CODE_ALIASES.items() if target == canonical)
    return sorted(value for value in values if value)
