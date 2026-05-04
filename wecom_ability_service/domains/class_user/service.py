from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from ...infra.constants import CLASS_USER_ALLOWED_STATUSES
from . import repo


def get_class_user_status_definition(signup_status: str) -> dict[str, Any] | None:
    return CLASS_USER_ALLOWED_STATUSES.get(str(signup_status or "").strip())


def list_signup_scope_external_userids(corp_id: str) -> list[str]:
    return repo.list_signup_scope_external_userids(corp_id)


def list_class_user_live_base_rows(corp_id: str) -> list[dict[str, Any]]:
    return repo.list_class_user_live_base_rows(corp_id)


def get_class_user_snapshot(
    external_userid: str,
    owner_userid: str = "",
    *,
    contact_loader: Callable[[str], dict[str, Any] | None],
    person_identity_resolver: Callable[..., dict[str, Any]],
) -> dict[str, str]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    contact = contact_loader(normalized_external_userid) or {}
    person_identity = person_identity_resolver(external_userid=normalized_external_userid) if normalized_external_userid else {}
    mobile = str((person_identity or {}).get("mobile") or "").strip()
    customer_name = str(contact.get("customer_name") or "").strip() or str((person_identity or {}).get("customer_name") or "").strip()
    owner_snapshot = (
        normalized_owner_userid
        or str(contact.get("owner_userid") or "").strip()
        or str((person_identity or {}).get("owner_userid") or "").strip()
        or str((person_identity or {}).get("follow_user_userid") or "").strip()
    )
    return {
        "external_userid": normalized_external_userid,
        "customer_name_snapshot": customer_name,
        "owner_userid_snapshot": owner_snapshot,
        "mobile_snapshot": mobile,
    }


def get_class_user_status_current(external_userid: str) -> dict[str, Any] | None:
    row = repo.get_class_user_status_current(external_userid)
    return dict(row) if row else None


def upsert_class_user_status_current(**kwargs: Any) -> None:
    repo.upsert_class_user_status_current(**kwargs)


def append_class_user_status_history(**kwargs: Any) -> None:
    repo.append_class_user_status_history(**kwargs)


def clear_class_user_status_current(
    *,
    external_userid: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> None:
    existing = get_class_user_status_current(external_userid) or {}
    if not existing:
        return
    append_class_user_status_history(
        external_userid=external_userid,
        old_signup_status=str(existing.get("signup_status") or "").strip(),
        new_signup_status="",
        old_label_name=str(existing.get("signup_label_name") or "").strip(),
        new_label_name="",
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    repo.delete_class_user_status_current(external_userid)


def update_class_user_status_sync_result(
    external_userid: str,
    *,
    wecom_tag_sync_status: str,
    wecom_tag_sync_error: str = "",
) -> None:
    repo.update_class_user_status_sync_result(
        external_userid,
        wecom_tag_sync_status=wecom_tag_sync_status,
        wecom_tag_sync_error=wecom_tag_sync_error,
    )


def list_class_user_management_records(
    signup_status: str = "",
    *,
    get_signup_status_definitions: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    normalized_filter = str(signup_status or "").strip()
    status_definitions = get_signup_status_definitions()
    allowed_statuses = {item["signup_status"] for item in status_definitions}
    rows = repo.list_class_user_management_rows()
    counts = {item["signup_status"]: 0 for item in status_definitions}
    items: list[dict[str, Any]] = []
    for row in rows:
        row_payload = dict(row)
        status = str(row_payload.get("signup_status") or "").strip()
        if status in counts:
            counts[status] += 1
        if status not in allowed_statuses:
            continue
        if normalized_filter and status != normalized_filter:
            continue
        owner_userid = str(row_payload.get("owner_userid_snapshot") or "").strip() or str(row_payload.get("contact_owner_userid") or "").strip()
        customer_name = str(row_payload.get("customer_name_snapshot") or "").strip() or str(row_payload.get("contact_customer_name") or "").strip()
        mobile = str(row_payload.get("bound_mobile") or "").strip() or str(row_payload.get("mobile_snapshot") or "").strip()
        label_name = str(row_payload.get("signup_label_name") or "").strip()
        items.append(
            {
                "external_userid": str(row_payload.get("external_userid") or "").strip(),
                "customer_name": customer_name,
                "mobile": mobile,
                "follow_user_userid": owner_userid,
                "follow_user_display_name": str(row_payload.get("follow_user_display_name") or "").strip() or owner_userid,
                "updated_at": str(row_payload.get("current_updated_at") or row_payload.get("set_at") or "").strip(),
                "status_fields": {
                    "signup_status": status,
                    "current_tag_id": "",
                    "current_tag_name": label_name,
                    "matched_tags": [{"tag_id": "", "tag_name": label_name, "signup_status": status}],
                    "operation_flags": {
                        "action_executed": None,
                        "added_wecom": None,
                        "mobile_bound": bool(mobile),
                    },
                    "wecom_tag_sync_status": str(row_payload.get("wecom_tag_sync_status") or "").strip(),
                    "wecom_tag_sync_error": str(row_payload.get("wecom_tag_sync_error") or "").strip(),
                },
            }
        )
    status_stats = [
        {
            "signup_status": item["signup_status"],
            "label": item["label"],
            "count": counts[item["signup_status"]],
        }
        for item in status_definitions
    ]
    items.sort(key=lambda item: (item.get("updated_at", ""), item.get("external_userid", "")), reverse=True)
    return {
        "filter": normalized_filter,
        "status_definitions": status_definitions,
        "stats": status_stats,
        "items": items,
        "total": len(items),
        "meta": {
            "module": "class_user_management",
            "reserved_filters": ["action_executed", "added_wecom", "mobile_bound", "phone_compare_status"],
            "reserved_fields": ["operation_flags", "binding_flags", "compare_flags"],
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def export_class_user_management_records(
    signup_status: str = "",
    *,
    get_signup_status_definitions: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    result = list_class_user_management_records(signup_status=signup_status, get_signup_status_definitions=get_signup_status_definitions)
    headers = ["客户昵称", "手机号", "跟进人", "当前状态标签", "external_userid", "更新时间"]
    rows = [
        [
            item.get("customer_name", ""),
            item.get("mobile", ""),
            item.get("follow_user_display_name", ""),
            item.get("status_fields", {}).get("current_tag_name", ""),
            item.get("external_userid", ""),
            item.get("updated_at", ""),
        ]
        for item in result["items"]
    ]
    return {
        "headers": headers,
        "rows": rows,
        "filename": f"class-user-management-{result['filter'] or 'all'}-{datetime.now().strftime('%Y%m%d%H%M%S')}.xls",
    }


def list_class_user_status_history(limit: int = 100) -> dict[str, Any]:
    rows, normalized_limit = repo.list_class_user_status_history_rows(limit=limit)
    return {
        "items": [dict(row) for row in rows],
        "total": repo.count_class_user_status_history(),
        "limit": normalized_limit,
    }


def migrate_class_user_status_from_contact_tags(
    *,
    get_signup_status_definition_by_tag_name: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    rows = repo.list_contact_tag_signup_rows()
    by_external: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row_payload = dict(row)
        external_userid = str(row_payload.get("external_userid") or "").strip()
        if not external_userid:
            continue
        by_external.setdefault(external_userid, []).append(row_payload)

    migrated = 0
    for external_userid, candidates in by_external.items():
        candidates.sort(
            key=lambda item: (str(item.get("tag_created_at") or ""), str(item.get("tag_id") or "")),
            reverse=True,
        )
        chosen = candidates[0]
        definition = get_signup_status_definition_by_tag_name(str(chosen.get("tag_name") or "").strip())
        signup_status = str((definition or {}).get("signup_status") or "").strip()
        if not definition:
            continue
        existing = get_class_user_status_current(external_userid) or {}
        customer_name = str(chosen.get("customer_name") or "").strip()
        owner_userid = str(chosen.get("tag_userid") or "").strip() or str(chosen.get("owner_userid") or "").strip()
        mobile = str(chosen.get("mobile") or "").strip()
        upsert_class_user_status_current(
            external_userid=external_userid,
            signup_status=signup_status,
            signup_label_name=definition["label"],
            customer_name_snapshot=customer_name,
            owner_userid_snapshot=owner_userid,
            mobile_snapshot=mobile,
            set_by_userid=owner_userid,
            set_at=str(chosen.get("tag_created_at") or "").strip(),
            wecom_tag_sync_status="migrated",
            wecom_tag_sync_error="",
        )
        append_class_user_status_history(
            external_userid=external_userid,
            old_signup_status=str(existing.get("signup_status") or "").strip(),
            new_signup_status=signup_status,
            old_label_name=str(existing.get("signup_label_name") or "").strip(),
            new_label_name=definition["label"],
            customer_name_snapshot=customer_name,
            owner_userid_snapshot=owner_userid,
            mobile_snapshot=mobile,
            set_by_userid=owner_userid,
            set_at=str(chosen.get("tag_created_at") or "").strip(),
            wecom_tag_sync_status="migrated",
            wecom_tag_sync_error="",
        )
        migrated += 1
    return {"migrated_count": migrated}


def apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, Any]:
    definition = get_class_user_status_definition(signup_status)
    if not definition:
        raise ValueError("signup_status is invalid")
    existing = get_class_user_status_current(external_userid) or {}
    upsert_class_user_status_current(
        external_userid=external_userid,
        signup_status=signup_status,
        signup_label_name=definition["label"],
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    append_class_user_status_history(
        external_userid=external_userid,
        old_signup_status=str(existing.get("signup_status") or "").strip(),
        new_signup_status=signup_status,
        old_label_name=str(existing.get("signup_label_name") or "").strip(),
        new_label_name=definition["label"],
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    return get_class_user_status_current(external_userid) or {}
