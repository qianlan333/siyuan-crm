from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from flask import current_app

from ...infra.constants import DEFAULT_WECOM_CORP_TAG_LIMIT, SIGNUP_TAG_GROUP_NAME, SIGNUP_TAG_STATUS_DEFINITIONS
from ...infra.settings import get_setting
from ...wecom_client import WeComClient
from . import repo


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _synced_at_text() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()


def wecom_corp_tag_limit(payload: dict[str, Any] | None = None) -> int:
    raw_payload = payload or {}
    for key in ("tag_limit", "corp_tag_limit", "limit"):
        value = raw_payload.get(key)
        if value not in (None, ""):
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                break
    configured = get_setting("WECOM_CORP_TAG_LIMIT")
    if configured not in (None, ""):
        try:
            return max(1, int(configured or DEFAULT_WECOM_CORP_TAG_LIMIT))
        except (TypeError, ValueError):
            return DEFAULT_WECOM_CORP_TAG_LIMIT
    try:
        return max(1, int(current_app.config.get("WECOM_CORP_TAG_LIMIT", DEFAULT_WECOM_CORP_TAG_LIMIT)))
    except (TypeError, ValueError):
        return DEFAULT_WECOM_CORP_TAG_LIMIT


def build_wecom_tag_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    synced_at = _synced_at_text()
    usage_counts: dict[str, int] = {}
    raw_groups = list(payload.get("tag_group") or [])
    tag_ids = [
        _normalized_text((tag or {}).get("id") or (tag or {}).get("tag_id"))
        for group in raw_groups
        for tag in ((group or {}).get("tag") or [])
    ]
    if tag_ids:
        usage_counts = repo.count_contact_tag_usage_by_tag_ids(tag_ids)

    groups_by_key: dict[str, dict[str, Any]] = {}
    for group in raw_groups:
        group_id = _normalized_text((group or {}).get("group_id") or (group or {}).get("id"))
        group_name = _normalized_text((group or {}).get("group_name") or (group or {}).get("name")) or "未命名标签组"
        group_key = group_id or f"group-name:{group_name}"
        if group_key not in groups_by_key:
            groups_by_key[group_key] = {
                "group_key": group_key,
                "group_id": group_id,
                "group_name": group_name,
                "missing_group_id": not bool(group_id),
                "tag_count": 0,
                "tags": [],
            }
        for tag in (group or {}).get("tag") or []:
            tag_id = _normalized_text((tag or {}).get("id") or (tag or {}).get("tag_id"))
            tag_name = _normalized_text((tag or {}).get("name") or (tag or {}).get("tag_name")) or "未命名标签"
            if not tag_id and not tag_name:
                continue
            groups_by_key[group_key]["tags"].append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "group_id": group_id,
                    "group_name": group_name,
                    "usage_count": usage_counts.get(tag_id, 0) if tag_id else 0,
                    "synced_at": synced_at,
                    "missing_tag_id": not bool(tag_id),
                }
            )

    groups = sorted(
        groups_by_key.values(),
        key=lambda item: (_normalized_text(item.get("group_name")), _normalized_text(item.get("group_id"))),
    )
    for group in groups:
        group["tags"] = sorted(
            group["tags"],
            key=lambda item: (_normalized_text(item.get("tag_name")), _normalized_text(item.get("tag_id"))),
        )
        group["tag_count"] = len(group["tags"])

    items = sorted(
        [
            {
                "tag_id": tag["tag_id"],
                "tag_name": tag["tag_name"],
                "group_name": tag["group_name"],
                "group_id": tag["group_id"],
            }
            for group in groups
            for tag in group["tags"]
            if tag["tag_id"] and tag["tag_name"]
        ],
        key=lambda item: ((item.get("group_name") or ""), (item.get("tag_name") or ""), item["tag_id"]),
    )
    total_tags = len(items)
    return {
        "items": items,
        "groups": groups,
        "total_tags": total_tags,
        "tag_limit": wecom_corp_tag_limit(payload),
        "synced_at": synced_at,
    }


def signup_tag_group_name() -> str:
    return SIGNUP_TAG_GROUP_NAME


def get_signup_status_definitions() -> list[dict[str, Any]]:
    return [dict(item) for item in SIGNUP_TAG_STATUS_DEFINITIONS]


def get_signup_status_definition(signup_status: str) -> dict[str, Any] | None:
    normalized = str(signup_status or "").strip()
    return next((dict(item) for item in SIGNUP_TAG_STATUS_DEFINITIONS if item["signup_status"] == normalized), None)


def get_signup_status_definition_by_tag_name(tag_name: str) -> dict[str, Any] | None:
    normalized = str(tag_name or "").strip()
    return next((dict(item) for item in SIGNUP_TAG_STATUS_DEFINITIONS if item["tag_name"] == normalized), None)


def get_signup_tag_rules_config() -> dict[str, Any]:
    items = repo.list_signup_tag_rules(active_only=True)
    rules_by_status: dict[str, list[dict[str, Any]]] = {
        definition["signup_status"]: [] for definition in SIGNUP_TAG_STATUS_DEFINITIONS
    }
    for item in items:
        signup_status = str(item.get("signup_status") or "").strip()
        if signup_status in rules_by_status:
            rules_by_status[signup_status].append(item)
    derived_statuses = [{"signup_status": "pre_signup", "match_mode": "no_tag_match", "tag_ids": [], "tag_names": []}]
    for definition in SIGNUP_TAG_STATUS_DEFINITIONS:
        status = definition["signup_status"]
        derived_statuses.append(
            {
                "signup_status": status,
                "match_mode": "match_any",
                "tag_ids": [item.get("tag_id", "") for item in rules_by_status[status]],
                "tag_names": [item.get("tag_name", "") for item in rules_by_status[status]],
                "label": definition["label"],
            }
        )
    return {
        "tag_group_name": signup_tag_group_name(),
        "status_definitions": get_signup_status_definitions(),
        "items": items,
        "derived_statuses": derived_statuses
        + [
            {
                "signup_status": "unknown",
                "match_mode": "conflict",
                "tag_ids": sorted(
                    {
                        item.get("tag_id", "")
                        for status_items in rules_by_status.values()
                        for item in status_items
                        if item.get("tag_id")
                    }
                ),
                "tag_names": sorted(
                    {
                        item.get("tag_name", "")
                        for status_items in rules_by_status.values()
                        for item in status_items
                        if item.get("tag_name")
                    }
                ),
                "conflict_when_statuses": [item["signup_status"] for item in SIGNUP_TAG_STATUS_DEFINITIONS],
            },
        ],
    }


def save_signup_tag_rule_config(*, tag_id: str, tag_name: str, signup_status: str, active: Any) -> dict[str, Any]:
    normalized_tag_id = str(tag_id or "").strip()
    normalized_tag_name = str(tag_name or "").strip()
    normalized_signup_status = str(signup_status or "").strip()
    if not normalized_tag_id:
        raise ValueError("tag_id is required")
    if not normalized_tag_name:
        raise ValueError("tag_name is required")
    if not get_signup_status_definition(normalized_signup_status):
        allowed = ", ".join(item["signup_status"] for item in SIGNUP_TAG_STATUS_DEFINITIONS)
        raise ValueError(f"signup_status must be one of: {allowed}")
    repo.upsert_signup_tag_rule(
        normalized_tag_id,
        normalized_tag_name,
        normalized_signup_status,
        active=bool(active) if isinstance(active, bool) else str(active or "").strip().lower() in {"1", "true", "yes", "y", "on"},
    )
    matched = next(
        (item for item in repo.list_signup_tag_rules(active_only=False) if str(item.get("tag_id") or "").strip() == normalized_tag_id),
        {},
    )
    return dict(matched)


def resolve_signup_status_from_tags(tags: list[dict[str, Any]]) -> dict[str, Any]:
    rules = repo.list_signup_tag_rules(active_only=True)
    status_by_tag_id: dict[str, str] = {}
    tag_name_by_id: dict[str, str] = {}
    for rule in rules:
        tag_id = str(rule.get("tag_id") or "").strip()
        signup_status = str(rule.get("signup_status") or "").strip()
        if not tag_id or not signup_status:
            continue
        status_by_tag_id[tag_id] = signup_status
        tag_name_by_id[tag_id] = str(rule.get("tag_name") or "").strip()

    matched_statuses: set[str] = set()
    matched_rules: list[dict[str, Any]] = []
    for tag in tags:
        tag_id = str(tag.get("tag_id") or "").strip()
        if not tag_id or tag_id not in status_by_tag_id:
            continue
        signup_status = status_by_tag_id[tag_id]
        matched_statuses.add(signup_status)
        matched_rules.append(
            {
                "tag_id": tag_id,
                "tag_name": tag_name_by_id.get(tag_id, "") or str(tag.get("tag_name") or "").strip(),
                "signup_status": signup_status,
            }
        )
    if len(matched_statuses) > 1:
        signup_status = "unknown"
    elif matched_statuses:
        signup_status = next(iter(matched_statuses))
    else:
        signup_status = "pre_signup"
    return {
        "signup_status": signup_status,
        "matched_signup_rules": matched_rules,
        "matched_signup_rule_statuses": sorted(matched_statuses),
    }


def build_class_user_tag_view(tags: list[dict[str, Any]]) -> dict[str, Any]:
    signup_context = resolve_signup_status_from_tags(tags)
    status = signup_context["signup_status"]
    definition = get_signup_status_definition(status)
    matched_tags = [
        {
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
            "signup_status": str(item.get("signup_status") or "").strip(),
        }
        for item in signup_context.get("matched_signup_rules") or []
    ]
    current_tag_id = matched_tags[0]["tag_id"] if len(matched_tags) == 1 else ""
    current_tag_name = definition["label"] if definition else ("标签冲突" if status == "unknown" else "")
    return {
        "signup_status": status,
        "current_tag_id": current_tag_id,
        "current_tag_name": current_tag_name,
        "matched_tags": matched_tags,
    }


def get_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
    contact_loader: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {
            "detail": {},
            "owner_userid": normalized_owner_userid,
            "owner_found": False,
            "tags": [],
            "tag_ids": [],
            "tag_names": [],
            "external_contact_name": "",
        }
    detail = contact_loader(normalized_external_userid)
    follow_users = detail.get("follow_user") or []
    owner_tags: list[dict[str, str]] = []
    owner_found = False
    for follow_user in follow_users:
        follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
        if normalized_owner_userid and follow_user_userid != normalized_owner_userid:
            continue
        owner_found = True
        for tag in ((follow_user or {}).get("tags") or []):
            tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not tag_id:
                continue
            owner_tags.append({"tag_id": tag_id, "tag_name": tag_name})
    deduped_tags: list[dict[str, str]] = []
    seen_tag_ids: set[str] = set()
    for tag in owner_tags:
        tag_id = str(tag.get("tag_id") or "").strip()
        if tag_id in seen_tag_ids:
            continue
        seen_tag_ids.add(tag_id)
        deduped_tags.append({"tag_id": tag_id, "tag_name": str(tag.get("tag_name") or "").strip()})
    return {
        "detail": detail,
        "owner_userid": normalized_owner_userid,
        "owner_found": owner_found,
        "tags": deduped_tags,
        "tag_ids": [str(item.get("tag_id") or "").strip() for item in deduped_tags],
        "tag_names": [str(item.get("tag_name") or "").strip() for item in deduped_tags if str(item.get("tag_name") or "").strip()],
        "external_contact_name": str(((detail.get("external_contact") or {}).get("name") or "")).strip(),
    }


def persist_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
    tags: list[dict[str, str]],
) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid or not normalized_owner_userid:
        return
    tag_ids = sorted({str(item.get("tag_id") or "").strip() for item in tags if str(item.get("tag_id") or "").strip()})
    tag_name_map = {
        str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
        for item in tags
        if str(item.get("tag_id") or "").strip()
    }
    repo.save_tag_snapshot(normalized_owner_userid, normalized_external_userid, tag_ids, tag_name_map)
    existing_tag_ids = repo.list_contact_tag_ids_for_user(normalized_external_userid, normalized_owner_userid)
    removable_tag_ids = [tag_id for tag_id in existing_tag_ids if tag_id not in tag_ids]
    repo.remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, removable_tag_ids)


def list_wecom_tags(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    client = WeComClient.from_app()
    return client.list_tags(payload or {})


def list_wecom_tag_catalog(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_wecom_tag_catalog(list_wecom_tags(payload or {}))


def create_wecom_tag(payload: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    return client.create_tag(payload)


def create_wecom_tag_group(
    *,
    group_name: str,
    first_tag_name: str = "",
    tag_names: list[Any] | None = None,
) -> dict[str, Any]:
    normalized_group_name = _normalized_text(group_name)
    normalized_tag_names = [_normalized_text(item) for item in (tag_names or [])]
    normalized_tag_names = [item for item in normalized_tag_names if item]
    if not normalized_tag_names:
        normalized_first_tag_name = _normalized_text(first_tag_name)
        if normalized_first_tag_name:
            normalized_tag_names = [normalized_first_tag_name]
    if not normalized_group_name:
        raise ValueError("标签组名称不能为空")
    if not normalized_tag_names:
        raise ValueError("至少需要添加一个标签")
    return create_wecom_tag({"group_name": normalized_group_name, "tag": [{"name": item} for item in normalized_tag_names]})


def create_wecom_tag_in_group(*, group_id: str, group_name: str = "", tag_name: str) -> dict[str, Any]:
    normalized_group_id = _normalized_text(group_id)
    normalized_group_name = _normalized_text(group_name)
    normalized_tag_name = _normalized_text(tag_name)
    if not normalized_tag_name:
        raise ValueError("标签名称不能为空")
    if not normalized_group_id and not normalized_group_name:
        raise ValueError("必须选择标签组")
    payload: dict[str, Any] = {"tag": [{"name": normalized_tag_name}]}
    if normalized_group_id:
        payload["group_id"] = normalized_group_id
    else:
        payload["group_name"] = normalized_group_name
    return create_wecom_tag(payload)


def update_wecom_tag_group(*, group_id: str, group_name: str) -> dict[str, Any]:
    normalized_group_id = _normalized_text(group_id)
    normalized_group_name = _normalized_text(group_name)
    if not normalized_group_id:
        raise ValueError("当前标签组缺少 group_id，无法执行该操作，请先同步企微标签。")
    if not normalized_group_name:
        raise ValueError("标签组名称不能为空")
    client = WeComClient.from_app()
    return client.update_tag_group({"id": normalized_group_id, "name": normalized_group_name})


def delete_wecom_tag_group(*, group_id: str) -> dict[str, Any]:
    normalized_group_id = _normalized_text(group_id)
    if not normalized_group_id:
        raise ValueError("当前标签组缺少 group_id，无法执行该操作，请先同步企微标签。")
    client = WeComClient.from_app()
    return client.delete_tag_group({"group_id": [normalized_group_id]})


def update_wecom_tag(*, tag_id: str, tag_name: str) -> dict[str, Any]:
    normalized_tag_id = _normalized_text(tag_id)
    normalized_tag_name = _normalized_text(tag_name)
    if not normalized_tag_id:
        raise ValueError("当前标签缺少 tag_id，无法执行该操作，请先同步企微标签。")
    if not normalized_tag_name:
        raise ValueError("标签名称不能为空")
    client = WeComClient.from_app()
    return client.update_tag({"id": normalized_tag_id, "name": normalized_tag_name})


def delete_wecom_tag(*, tag_id: str) -> dict[str, Any]:
    normalized_tag_id = _normalized_text(tag_id)
    if not normalized_tag_id:
        raise ValueError("当前标签缺少 tag_id，无法执行该操作，请先同步企微标签。")
    client = WeComClient.from_app()
    return client.delete_tag({"tag_id": [normalized_tag_id]})


def mark_customer_tags(payload: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = client.mark_tag(payload)
    repo.save_tag_snapshot(
        str(payload.get("userid") or "").strip(),
        str(payload.get("external_userid") or "").strip(),
        [str(item or "").strip() for item in (payload.get("add_tag") or []) if str(item or "").strip()],
    )
    return result


def unmark_customer_tags(payload: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = client.mark_tag(payload)
    repo.remove_tag_snapshot(
        str(payload.get("userid") or "").strip(),
        str(payload.get("external_userid") or "").strip(),
        [str(item or "").strip() for item in (payload.get("remove_tag") or []) if str(item or "").strip()],
    )
    return result


def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
    contact_loader: Callable[[str], dict[str, Any]],
    list_active_class_term_mappings: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"ok": True, "refreshed": False, "reason": "missing_external_userid"}
    normalized_scoped_tag_ids = sorted({str(item or "").strip() for item in (scoped_tag_ids or []) if str(item or "").strip()})
    scoped_all_tags = not normalized_scoped_tag_ids
    tag_name_map: dict[str, str] = {}
    if not scoped_all_tags:
        scoped_mappings = [item for item in list_active_class_term_mappings() if str(item.get("tag_id") or "").strip()]
        known_tag_name_map = {
            str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
            for item in scoped_mappings
            if str(item.get("tag_id") or "").strip()
        }
        for tag_id in normalized_scoped_tag_ids:
            if tag_id in known_tag_name_map:
                tag_name_map[tag_id] = known_tag_name_map[tag_id]
    detail = contact_loader(normalized_external_userid)
    follow_users = detail.get("follow_user") or []
    refreshed_userids: list[str] = []
    snapshot_count = 0
    for follow_user in follow_users:
        follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
        if not follow_user_userid:
            continue
        if normalized_owner_userid and follow_user_userid != normalized_owner_userid:
            continue
        refreshed_userids.append(follow_user_userid)
        current_tag_ids: list[str] = []
        for tag in ((follow_user or {}).get("tags") or []):
            current_tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            current_tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not current_tag_id:
                continue
            if not scoped_all_tags and current_tag_id not in normalized_scoped_tag_ids:
                continue
            current_tag_ids.append(current_tag_id)
            if current_tag_name:
                tag_name_map[current_tag_id] = current_tag_name
        current_tag_ids = sorted(set(current_tag_ids))
        repo.save_tag_snapshot(follow_user_userid, normalized_external_userid, current_tag_ids, tag_name_map)
        existing_tag_ids = repo.list_contact_tag_ids_for_user(normalized_external_userid, follow_user_userid)
        removable_tag_ids = [
            tag_id for tag_id in existing_tag_ids if (scoped_all_tags or tag_id in normalized_scoped_tag_ids) and tag_id not in current_tag_ids
        ]
        repo.remove_tag_snapshot(follow_user_userid, normalized_external_userid, removable_tag_ids)
        snapshot_count += len(current_tag_ids)
    if normalized_owner_userid and normalized_owner_userid not in refreshed_userids:
        missing_owner_existing = repo.list_contact_tag_ids_for_user(normalized_external_userid, normalized_owner_userid)
        removable_missing_owner = [tag_id for tag_id in missing_owner_existing if scoped_all_tags or tag_id in normalized_scoped_tag_ids]
        repo.remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, removable_missing_owner)
    if scoped_all_tags:
        repo.remove_all_tag_snapshots_for_other_users(normalized_external_userid, refreshed_userids)
    return {
        "ok": True,
        "refreshed": True,
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "follow_user_count": len(follow_users),
        "refreshed_userids": refreshed_userids,
        "scoped_tag_count": len(normalized_scoped_tag_ids),
        "scoped_all_tags": scoped_all_tags,
        "snapshot_count": snapshot_count,
    }
