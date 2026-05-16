"""Phone formatting helpers shared by user-ops read/write services."""
from __future__ import annotations

from typing import Any


def phone_digits(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def phone_match_key(value: Any) -> str:
    digits = phone_digits(value)
    if len(digits) < 7:
        return ""
    return f"{digits[:3]}_{digits[-4:]}"


def mask_mobile(value: Any) -> str:
    digits = phone_digits(value)
    if len(digits) < 7:
        return str(value or "")
    return f"{digits[:3]}****{digits[-4:]}"
