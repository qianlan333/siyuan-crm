"""Multi-dimensional member search & broadcast targeting.

This is the data backbone for the redesigned 「成员运营」 page: it lets the admin
filter automation members by any combination of pool × 自然画像分层 × 行为画像分层
and either browse the result, or use it as the broadcast target list.

The previous 成员运营 page only supported single-pool filtering. To make
multi-dim filtering work at the SQL layer (instead of recomputing segment keys
per row at render time), profile_segment_key / behavior_tier_key are
materialized onto ``automation_member`` and refreshed by
``workflow_service._build_dashboard_audience_member_details``.
"""
from __future__ import annotations

from typing import Any

from . import repo, workflow_service
from .workflow_definitions import (
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    list_supported_behavior_tiers,
    list_supported_conversion_audiences,
)


_UNCATEGORIZED_KEY = "__uncategorized__"
_UNCATEGORIZED_PROFILE_LABEL = "未命中画像"
_UNCATEGORIZED_BEHAVIOR_LABEL = "未采集行为"


def _normalized_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalize_key_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        items = [values]
    else:
        try:
            items = list(values)
        except TypeError:
            return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _normalized_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _resolve_storage_keys(keys: list[str]) -> list[str]:
    """Translate UI-facing keys (which may include the synthetic
    "__uncategorized__" sentinel) into the storage representation: an empty
    string is the way ``automation_member`` records "no segment yet"."""
    out: list[str] = []
    for key in keys:
        if key == _UNCATEGORIZED_KEY:
            out.append("")
        else:
            out.append(key)
    return out


def _profile_segment_label_map(*, program_id: int | None = None) -> dict[str, str]:
    return workflow_service.profile_segment_label_map_for_program(program_id=program_id)


def _program_scope_options(*, program_id: int | None = None) -> dict[str, Any]:
    effective_program_id = (
        workflow_service._effective_program_id(program_id) if program_id is not None else None
    )
    if effective_program_id is None:
        return {"program_id": None, "include_unscoped": False}
    default_program_id = workflow_service.program_service.get_default_automation_program_id()
    return {
        "program_id": effective_program_id,
        "include_unscoped": effective_program_id == default_program_id,
    }


def _behavior_tier_label_map() -> dict[str, str]:
    return {
        _normalized_text(item.get("tier_code")): _normalized_text(item.get("label"))
        for item in list_supported_behavior_tiers()
        if _normalized_text(item.get("tier_code"))
    }


def _audience_label_map() -> dict[str, str]:
    return {
        _normalized_text(item.get("audience_code")): _normalized_text(item.get("label"))
        for item in list_supported_conversion_audiences()
    }


def get_dimension_metadata(*, program_id: int | None = None) -> dict[str, Any]:
    """Return chip options + counts per dimension for the filter UI."""
    audience_labels = _audience_label_map()
    profile_labels = _profile_segment_label_map(program_id=program_id)
    behavior_labels = _behavior_tier_label_map()
    aggregates = repo.aggregate_member_segment_dimensions(**_program_scope_options(program_id=program_id))

    pool_count_by_key: dict[str, int] = {
        item["key"]: item["total"] for item in aggregates.get("pools") or []
    }
    profile_count_by_key: dict[str, int] = {
        item["key"]: item["total"] for item in aggregates.get("profiles") or []
    }
    behavior_count_by_key: dict[str, int] = {
        item["key"]: item["total"] for item in aggregates.get("behaviors") or []
    }

    pools_payload: list[dict[str, Any]] = []
    for code in (AUDIENCE_PENDING_QUESTIONNAIRE, AUDIENCE_OPERATING, AUDIENCE_CONVERTED):
        pools_payload.append(
            {
                "key": code,
                "label": audience_labels.get(code, code),
                "total": int(pool_count_by_key.get(code, 0)),
            }
        )

    profiles_payload: list[dict[str, Any]] = []
    for key, label in profile_labels.items():
        profiles_payload.append(
            {
                "key": key,
                "label": label,
                "total": int(profile_count_by_key.get(key, 0)),
            }
        )
    # 兜底: 任何配置中未声明、但库里已有的 key 也展示出来，方便排查脏数据
    for key, total in profile_count_by_key.items():
        if key and key not in profile_labels:
            profiles_payload.append({"key": key, "label": key, "total": int(total)})
    if profile_count_by_key.get("", 0):
        profiles_payload.append(
            {
                "key": _UNCATEGORIZED_KEY,
                "label": _UNCATEGORIZED_PROFILE_LABEL,
                "total": int(profile_count_by_key.get("", 0)),
            }
        )

    behaviors_payload: list[dict[str, Any]] = []
    for key, label in behavior_labels.items():
        behaviors_payload.append(
            {
                "key": key,
                "label": label,
                "total": int(behavior_count_by_key.get(key, 0)),
            }
        )
    if behavior_count_by_key.get("", 0):
        behaviors_payload.append(
            {
                "key": _UNCATEGORIZED_KEY,
                "label": _UNCATEGORIZED_BEHAVIOR_LABEL,
                "total": int(behavior_count_by_key.get("", 0)),
            }
        )

    return {
        "pools": pools_payload,
        "profiles": profiles_payload,
        "behaviors": behaviors_payload,
    }


def _serialize_member_for_search(
    row: dict[str, Any],
    *,
    audience_labels: dict[str, str],
    profile_labels: dict[str, str],
    behavior_labels: dict[str, str],
) -> dict[str, Any]:
    audience_code = _normalized_text(row.get("current_audience_code"))
    profile_key = _normalized_text(row.get("profile_segment_key"))
    behavior_key = _normalized_text(row.get("behavior_tier_key"))
    return {
        "member_id": int(row.get("id") or 0) or None,
        "external_contact_id": _normalized_text(row.get("external_contact_id")),
        "phone": _normalized_text(row.get("phone")),
        "customer_name": _normalized_text(row.get("customer_name")),
        "audience_code": audience_code,
        "audience_label": audience_labels.get(audience_code, audience_code),
        "profile_segment_key": profile_key,
        "profile_segment_label": profile_labels.get(profile_key, profile_key) if profile_key else _UNCATEGORIZED_PROFILE_LABEL,
        "behavior_tier_key": behavior_key,
        "behavior_tier_label": behavior_labels.get(behavior_key, behavior_key) if behavior_key else _UNCATEGORIZED_BEHAVIOR_LABEL,
        "owner_staff_id": _normalized_text(row.get("owner_staff_id")),
        "updated_at": _normalized_text(row.get("updated_at")),
        "segment_refreshed_at": _normalized_text(row.get("segment_refreshed_at")),
    }


def search_members(
    *,
    pool_keys: list[str] | None = None,
    profile_keys: list[str] | None = None,
    behavior_keys: list[str] | None = None,
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
    program_id: int | None = None,
) -> dict[str, Any]:
    """Paginated multi-dim search. Returns rows + pagination + total."""
    page = max(int(page or 1), 1)
    page_size = max(min(int(page_size or 50), 200), 1)
    offset = (page - 1) * page_size

    storage_pools = _normalize_key_list(pool_keys)
    storage_profiles = _resolve_storage_keys(_normalize_key_list(profile_keys))
    storage_behaviors = _resolve_storage_keys(_normalize_key_list(behavior_keys))

    rows = repo.list_members_by_segment_filter(
        pool_keys=storage_pools,
        profile_keys=storage_profiles,
        behavior_keys=storage_behaviors,
        keyword=keyword,
        offset=offset,
        limit=page_size,
        **_program_scope_options(program_id=program_id),
    )
    total = repo.count_members_by_segment_filter(
        pool_keys=storage_pools,
        profile_keys=storage_profiles,
        behavior_keys=storage_behaviors,
        keyword=keyword,
        **_program_scope_options(program_id=program_id),
    )

    audience_labels = _audience_label_map()
    profile_labels = _profile_segment_label_map(program_id=program_id)
    behavior_labels = _behavior_tier_label_map()
    items = [
        _serialize_member_for_search(
            row,
            audience_labels=audience_labels,
            profile_labels=profile_labels,
            behavior_labels=behavior_labels,
        )
        for row in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "filters": {
            "pool_keys": _normalize_key_list(pool_keys),
            "profile_keys": _normalize_key_list(profile_keys),
            "behavior_keys": _normalize_key_list(behavior_keys),
            "keyword": _normalized_text(keyword),
        },
    }


def list_broadcast_targets(
    *,
    pool_keys: list[str] | None = None,
    profile_keys: list[str] | None = None,
    behavior_keys: list[str] | None = None,
    keyword: str = "",
    program_id: int | None = None,
) -> list[dict[str, Any]]:
    """Full unpaginated target list for broadcast — order matches list view."""
    storage_pools = _normalize_key_list(pool_keys)
    storage_profiles = _resolve_storage_keys(_normalize_key_list(profile_keys))
    storage_behaviors = _resolve_storage_keys(_normalize_key_list(behavior_keys))

    rows = repo.list_members_by_segment_filter(
        pool_keys=storage_pools,
        profile_keys=storage_profiles,
        behavior_keys=storage_behaviors,
        keyword=keyword,
        offset=0,
        limit=10_000,
        **_program_scope_options(program_id=program_id),
    )
    audience_labels = _audience_label_map()
    profile_labels = _profile_segment_label_map(program_id=program_id)
    behavior_labels = _behavior_tier_label_map()
    return [
        _serialize_member_for_search(
            row,
            audience_labels=audience_labels,
            profile_labels=profile_labels,
            behavior_labels=behavior_labels,
        )
        for row in rows
    ]


def filter_snapshot(
    *,
    pool_keys: list[str] | None,
    profile_keys: list[str] | None,
    behavior_keys: list[str] | None,
    keyword: str,
) -> dict[str, Any]:
    """Canonical filter snapshot for audit / 执行记录 traceability."""
    return {
        "selection_mode": "automation_conversion_segment_search",
        "pool_keys": _normalize_key_list(pool_keys),
        "profile_keys": _normalize_key_list(profile_keys),
        "behavior_keys": _normalize_key_list(behavior_keys),
        "keyword": _normalized_text(keyword),
    }
