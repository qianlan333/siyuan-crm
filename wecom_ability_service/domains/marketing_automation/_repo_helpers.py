"""Shared helpers for the marketing_automation package.

Extracted from repo.py (阶段 5.2 marketing_automation repo cleanup).

Private to the marketing_automation package; names stay underscore-prefixed
and are explicitly re-exported via ``__all__``. Callers should import via
explicit names (`from ._repo_helpers import _normalized_text, ...`) rather
than star imports, to avoid ruff F405 warnings if/when ruff is configured
for this domain.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts as _db_fetchall_dicts
from ...db.helpers import fetchone_dict as _db_fetchone_dict
from ...db.helpers import placeholders as _db_placeholders
from ...infra.helpers import db_bool as _db_bool
from ...infra.json_utils import json_array, json_dumps


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    return _db_fetchone_dict(get_db(), sql, params)


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return _db_fetchall_dicts(get_db(), sql, params)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_text_list(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    return [text for item in values or () if (text := _normalized_text(item))]


def _normalized_json_text_list(value: Any) -> list[str]:
    return _normalized_text_list(json_array(value))


def _normalize_bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(
    value: Any,
    field_name: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
    allow_none: bool = False,
) -> int | None:
    if value in (None, ""):
        if allow_none:
            return None
        if default is not None:
            return int(default)
        raise ValueError(f"{field_name} is required")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if minimum is not None and normalized < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    if maximum is not None and normalized > maximum:
        raise ValueError(f"{field_name} must be <= {maximum}")
    return normalized


def _placeholders(values: list[Any] | tuple[Any, ...]) -> str:
    return _db_placeholders(values)


def _nullable_timestamp_text(value: Any) -> str | None:
    normalized = _normalized_text(value)
    return normalized or None


def _json_dumps(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


__all__ = [
    "_db_bool",
    "_fetchone_dict",
    "_fetchall_dicts",
    "_normalize_bool",
    "_normalize_int",
    "_normalized_json_text_list",
    "_normalized_text",
    "_normalized_text_list",
    "_placeholders",
    "_nullable_timestamp_text",
    "_json_dumps",
]
