"""Shared helpers for marketing_automation/repo.py.

Extracted from repo.py (阶段 5.2 marketing_automation repo cleanup).

Private to the marketing_automation package — names stay underscore-prefixed
and are explicitly re-exported via ``__all__``. Callers should import via
explicit names (`from ._repo_helpers import _normalized_text, ...`) rather
than star imports, to avoid ruff F405 warnings if/when ruff is configured
for this domain.
"""

from __future__ import annotations

import json
from typing import Any

from ...db import get_db, get_db_backend


def _db_bool(value: bool) -> bool:
    return bool(value)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_timestamp_text(value: Any) -> str | None:
    normalized = _normalized_text(value)
    return normalized or None


def _json_dumps(value: Any) -> str:
    return json.dumps({} if value is None else value, ensure_ascii=False)


__all__ = [
    "_db_bool",
    "_fetchone_dict",
    "_fetchall_dicts",
    "_normalized_text",
    "_nullable_timestamp_text",
    "_json_dumps",
]
