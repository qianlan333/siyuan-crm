"""Shared helpers for automation_conversion/repo.py.

Extracted from repo.py to reduce its line count and to make the data-access
helpers explicitly shareable across future repo split files (planned in
docs/refactor/automation-conversion-split-blueprint.md).

These helpers are private to the automation_conversion package — names stay
underscore-prefixed and are explicitly re-exported via ``__all__`` so callers
can ``from ._repo_helpers import *`` and pick them all up.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ...infra.helpers import db_bool as _db_bool
from ...infra.json_utils import json_dumps, safe_json_loads

_AUTOMATION_SOP_POOL_LOCK_NAMESPACE = 41017


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


def _json_loads(value: Any, *, default: Any) -> Any:
    return safe_json_loads(value, default=default)


def _row_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _sop_pool_lookup_keys(pool_key: str) -> tuple[str, ...]:
    normalized_pool_key = _normalized_text(pool_key)
    if not normalized_pool_key:
        return ()
    alias_groups = {
        "pending_questionnaire": ("pending_questionnaire", "new_user"),
        "operating": (
            "operating",
            "inactive_normal",
            "inactive_focus",
            "active_normal",
            "active_focus",
            "silent",
        ),
        "converted": ("converted", "won"),
    }
    return alias_groups.get(normalized_pool_key, (normalized_pool_key,))


def _stage_route_lookup_keys(route_key: str) -> tuple[str, ...]:
    normalized_route_key = _normalized_text(route_key)
    if not normalized_route_key:
        return ()
    alias_groups = {
        "pending-questionnaire": ("pending-questionnaire", "new-user"),
        "new-user": ("pending-questionnaire", "new-user"),
        "operating": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "inactive-normal": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "inactive-focus": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "active-normal": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "active-focus": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "silent": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "converted": ("converted", "won"),
        "won": ("converted", "won"),
    }
    return alias_groups.get(normalized_route_key, (normalized_route_key,))


__all__ = [
    "_AUTOMATION_SOP_POOL_LOCK_NAMESPACE",
    "_db_bool",
    "_normalized_text",
    "_json_dumps",
    "_json_loads",
    "_row_bool",
    "_fetchone_dict",
    "_fetchall_dicts",
    "_sop_pool_lookup_keys",
    "_stage_route_lookup_keys",
]
