from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import current_app

from ..application.class_user.commands import (
    ApplyClassUserStatusChangeCommand,
    UpdateClassUserStatusSyncResultCommand,
)
from ..application.class_user.dto import (
    ApplyClassUserStatusChangeCommandDTO,
    GetClassUserSnapshotQueryDTO,
    GetClassUserStatusCurrentQueryDTO,
    UpdateClassUserStatusSyncResultCommandDTO,
)
from ..application.class_user.queries import (
    GetClassUserSnapshotQuery,
    GetClassUserStatusCurrentQuery,
    ListClassUserLiveBaseRowsQuery,
    ListSignupScopeExternalUseridsQuery,
)
from ..application.identity_contact.commands import (
    BuildExternalContactIdentityRecordCommand,
    RefreshExternalContactIdentityOwnerCommand,
    ReplaceFollowUsersCommand,
    UpsertExternalContactIdentityCommand,
)
from ..application.identity_contact.dto import (
    GetPrimaryFollowUserUseridQueryDTO,
    RefreshExternalContactIdentityOwnerCommandDTO,
    ReplaceFollowUsersCommandDTO,
    UpsertExternalContactIdentityCommandDTO,
)
from ..application.identity_contact.queries import (
    GetPrimaryFollowUserUseridQuery,
)
from ..domains.contacts.repo import upsert_contacts
from ..domains.contacts.service import normalize_contact_record
from ..domains.marketing_automation.service import mark_enrolled, unmark_enrolled
from ..domains.questionnaire.service import list_available_wecom_tags
from ..domains.tags.repo import (
    list_signup_tag_rules,
    remove_tag_snapshot,
    remove_tag_snapshots_for_other_users,
    save_tag_snapshot,
    upsert_signup_tag_rule,
)
from ..domains.tags.service import (
    build_class_user_tag_view,
    get_signup_status_definition,
    get_signup_status_definitions,
)
from ..infra.wecom_runtime import get_app_runtime_client
from ..wecom_client import WeComClientError
from .common import _corp_id, _log_wecom_client_error, wecom_logger


def _get_primary_follow_user_userid(external_userid: str) -> str:
    return GetPrimaryFollowUserUseridQuery()(
        GetPrimaryFollowUserUseridQueryDTO(external_userid=str(external_userid or "").strip())
    )


def _get_class_user_status_current(external_userid: str) -> dict[str, object] | None:
    return GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid=str(external_userid or "").strip())
    )


def _get_class_user_snapshot(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    return GetClassUserSnapshotQuery()(
        GetClassUserSnapshotQueryDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
        )
    )


def _apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, object]:
    return ApplyClassUserStatusChangeCommand()(
        ApplyClassUserStatusChangeCommandDTO(
            external_userid=str(external_userid or "").strip(),
            signup_status=str(signup_status or "").strip(),
            set_by_userid=str(set_by_userid or "").strip(),
            customer_name_snapshot=str(customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(mobile_snapshot or "").strip(),
        )
    )


def _update_class_user_status_sync_result(
    *,
    external_userid: str,
    wecom_tag_sync_status: str,
    wecom_tag_sync_error: str = "",
) -> None:
    return UpdateClassUserStatusSyncResultCommand()(
        UpdateClassUserStatusSyncResultCommandDTO(
            external_userid=str(external_userid or "").strip(),
            wecom_tag_sync_status=str(wecom_tag_sync_status or "").strip(),
            wecom_tag_sync_error=str(wecom_tag_sync_error or "").strip(),
        )
    )


def _list_signup_scope_external_userids(corp_id: str) -> list[str]:
    return ListSignupScopeExternalUseridsQuery()(str(corp_id or "").strip())


def _list_class_user_live_base_rows(corp_id: str) -> list[dict[str, object]]:
    return ListClassUserLiveBaseRowsQuery()(str(corp_id or "").strip())


def _build_external_contact_identity_record(
    *,
    corp_id: str,
    detail: dict[str, object],
    follow_user_userid: str = "",
    status: str = "",
) -> dict[str, object]:
    return BuildExternalContactIdentityRecordCommand()(
        corp_id=str(corp_id or "").strip(),
        detail=dict(detail or {}),
        follow_user_userid=str(follow_user_userid or "").strip(),
        status=str(status or "").strip(),
    )


def _upsert_external_contact_identity(record: dict[str, object]) -> int:
    return UpsertExternalContactIdentityCommand()(
        UpsertExternalContactIdentityCommandDTO(record=dict(record or {}))
    )


def _replace_external_contact_follow_users(
    *,
    corp_id: str,
    external_userid: str,
    follow_users: list[dict[str, object]],
    preferred_userid: str = "",
) -> None:
    return ReplaceFollowUsersCommand()(
        ReplaceFollowUsersCommandDTO(
            corp_id=str(corp_id or "").strip(),
            external_userid=str(external_userid or "").strip(),
            follow_users=list(follow_users or []),
            preferred_userid=str(preferred_userid or "").strip(),
        )
    )


def _refresh_external_contact_identity_owner(*, corp_id: str, external_userid: str) -> None:
    return RefreshExternalContactIdentityOwnerCommand()(
        RefreshExternalContactIdentityOwnerCommandDTO(
            corp_id=str(corp_id or "").strip(),
            external_userid=str(external_userid or "").strip(),
        )
    )


def _sidebar_person_detail_url(binding: dict[str, object] | None) -> str:
    if not binding:
        return ""
    template = str(current_app.config.get("SIDEBAR_PERSON_DETAIL_URL_TEMPLATE", "") or "").strip()
    if not template:
        return ""
    try:
        return template.format(
            person_id=binding.get("person_id", ""),
            external_userid=binding.get("external_userid", ""),
            owner_userid=binding.get("owner_userid", ""),
            mobile=binding.get("mobile", ""),
            third_party_user_id=binding.get("third_party_user_id", ""),
        )
    except Exception:
        return ""


def _normalize_jssdk_url(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("url is required")
    return normalized.split("#", 1)[0]



def _signup_tag_bootstrap_payload() -> dict[str, object]:
    definitions = get_signup_status_definitions()
    tag_items = list_available_wecom_tags()
    target_group_name = "AI 产品报名情况"
    existing_by_name = {
        str(item.get("tag_name") or "").strip(): item
        for item in tag_items
        if str(item.get("group_name") or "").strip() == target_group_name
    }
    missing_definitions = [item for item in definitions if item["tag_name"] not in existing_by_name]
    created_names: list[str] = []

    if missing_definitions:
        client = get_app_runtime_client()
        if existing_by_name:
            payload = {
                "group_id": next(iter(existing_by_name.values())).get("group_id", ""),
                "tag": [{"name": item["tag_name"]} for item in missing_definitions],
            }
        else:
            payload = {
                "group_name": target_group_name,
                "tag": [{"name": item["tag_name"]} for item in definitions],
            }
        client.create_tag(payload)
        created_names = [item["tag_name"] for item in missing_definitions] if existing_by_name else [item["tag_name"] for item in definitions]
        tag_items = list_available_wecom_tags()
        existing_by_name = {
            str(item.get("tag_name") or "").strip(): item
            for item in tag_items
            if str(item.get("group_name") or "").strip() == target_group_name
        }

    rules: list[dict[str, str]] = []
    for definition in definitions:
        matched = existing_by_name.get(definition["tag_name"])
        if not matched:
            continue
        upsert_signup_tag_rule(matched["tag_id"], matched["tag_name"], definition["signup_status"], active=True)
        rules.append(
            {
                "signup_status": definition["signup_status"],
                "tag_id": matched["tag_id"],
                "tag_name": matched["tag_name"],
                "group_id": matched.get("group_id", "") or "",
                "group_name": matched.get("group_name", "") or "",
            }
        )

    return {
        "group_name": target_group_name,
        "created_tag_names": created_names,
        "rules": rules,
        "definitions": definitions,
    }


def _configured_signup_tag_rules_payload() -> dict[str, object]:
    rules_by_status = {
        str(item.get("signup_status") or "").strip(): {
            "signup_status": str(item.get("signup_status") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
        }
        for item in list_signup_tag_rules(active_only=True)
        if str(item.get("signup_status") or "").strip()
    }
    definitions = get_signup_status_definitions()
    rules = [rules_by_status[item["signup_status"]] for item in definitions if item["signup_status"] in rules_by_status]
    missing_statuses = [item["signup_status"] for item in definitions if item["signup_status"] not in rules_by_status]
    return {
        "definitions": definitions,
        "rules": rules,
        "missing_statuses": missing_statuses,
        "initialized": not missing_statuses,
    }


def _refresh_class_user_management_live_data() -> dict[str, object]:
    configured = _configured_signup_tag_rules_payload()
    if not configured.get("initialized"):
        return {"refreshed": False, "reason": "signup_tags_not_initialized"}

    rules = configured.get("rules") or []
    signup_tag_ids = sorted({str(item.get("tag_id") or "").strip() for item in rules if str(item.get("tag_id") or "").strip()})
    tag_name_map = {
        str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
        for item in rules
        if str(item.get("tag_id") or "").strip()
    }
    if not signup_tag_ids:
        return {"refreshed": False, "reason": "no_signup_tag_rules"}

    corp_id = _corp_id()
    deduped_external_userids = _list_signup_scope_external_userids(corp_id)
    client = get_app_runtime_client()
    contact_records: list[dict[str, object]] = []
    refreshed_count = 0
    for external_userid in deduped_external_userids:
        try:
            detail = client.get_contact(external_userid)
        except WeComClientError as exc:
            _log_wecom_client_error(exc, external_userid=external_userid, stage="external_contact.get")
            continue

        follow_users = detail.get("follow_user") or []
        primary_follow_userid = ""
        if follow_users:
            primary_follow_userid = str((follow_users[0] or {}).get("userid") or "").strip()
        contact_records.append(normalize_contact_record(detail, owner_userid=primary_follow_userid or None))
        identity = _build_external_contact_identity_record(
            corp_id=corp_id,
            detail=detail,
            follow_user_userid=primary_follow_userid,
            status="active",
        )
        _upsert_external_contact_identity(identity)
        _replace_external_contact_follow_users(
            corp_id=corp_id,
            external_userid=external_userid,
            follow_users=follow_users,
            preferred_userid=primary_follow_userid,
        )
        _refresh_external_contact_identity_owner(corp_id=corp_id, external_userid=external_userid)

        current_follow_userids: list[str] = []
        for follow_user in follow_users:
            follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
            if not follow_user_userid:
                continue
            current_follow_userids.append(follow_user_userid)
            current_tag_ids = sorted(
                {
                    str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
                    for tag in ((follow_user or {}).get("tags") or [])
                    if str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip() in tag_name_map
                }
            )
            if current_tag_ids:
                save_tag_snapshot(follow_user_userid, external_userid, current_tag_ids, tag_name_map)
            remove_tag_snapshot(
                follow_user_userid,
                external_userid,
                [tag_id for tag_id in signup_tag_ids if tag_id not in current_tag_ids],
            )
        remove_tag_snapshots_for_other_users(external_userid, current_follow_userids, signup_tag_ids)
        refreshed_count += 1

    if contact_records:
        upsert_contacts(contact_records)

    return {
        "refreshed": True,
        "owner_count": 0,
        "external_user_count": len(deduped_external_userids),
        "refreshed_count": refreshed_count,
    }


def _list_class_user_management_records_live(signup_status: str = "") -> dict[str, object]:
    normalized_filter = str(signup_status or "").strip()
    status_definitions = get_signup_status_definitions()
    status_priority = {item["signup_status"]: index for index, item in enumerate(status_definitions)}
    configured = _configured_signup_tag_rules_payload()
    rules = configured.get("rules") or []
    rule_by_tag_id = {
        str(item.get("tag_id") or "").strip(): {
            "signup_status": str(item.get("signup_status") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
        }
        for item in rules
        if str(item.get("tag_id") or "").strip()
    }
    corp_id = _corp_id()
    base_rows = _list_class_user_live_base_rows(corp_id)
    base_by_external = {}
    for row in base_rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        follow_user_userid = (
            str(row.get("primary_follow_user_userid") or "").strip()
            or str(row.get("owner_userid") or "").strip()
            or str(row.get("identity_follow_user_userid") or "").strip()
        )
        base_by_external[external_userid] = {
            "external_userid": external_userid,
            "customer_name": str(row.get("customer_name") or "").strip(),
            "mobile": str(row.get("mobile") or "").strip(),
            "follow_user_userid": follow_user_userid,
            "follow_user_display_name": str(row.get("follow_user_display_name") or "").strip() or follow_user_userid,
            "updated_at": str(row.get("contact_updated_at") or "").strip(),
        }

    client = get_app_runtime_client()
    external_userids = list(base_by_external.keys())
    counts = {item["signup_status"]: 0 for item in status_definitions}
    items: list[dict[str, object]] = []

    def _fetch_live_signup_item(external_userid: str) -> dict[str, object] | None:
        detail = client.get_contact(external_userid)
        base_item = base_by_external.get(external_userid, {})
        preferred_userid = str(base_item.get("follow_user_userid") or "").strip()
        candidates = []
        for follow_user in detail.get("follow_user") or []:
            follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
            for tag in ((follow_user or {}).get("tags") or []):
                tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
                rule = rule_by_tag_id.get(tag_id)
                if not rule:
                    continue
                candidates.append(
                    {
                        "follow_user_userid": follow_user_userid,
                        "signup_status": rule["signup_status"],
                        "tag_id": rule["tag_id"],
                        "tag_name": rule["tag_name"],
                    }
                )
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                0 if preferred_userid and item["follow_user_userid"] == preferred_userid else 1,
                status_priority.get(item["signup_status"], 999),
                item["tag_id"],
            )
        )
        chosen = candidates[0]
        item_follow_user_userid = chosen["follow_user_userid"] or preferred_userid
        item_follow_user_display_name = base_item.get("follow_user_display_name", "") if item_follow_user_userid == preferred_userid else item_follow_user_userid
        return {
            "customer_name": base_item.get("customer_name", "") or str((detail.get("external_contact") or {}).get("name") or "").strip(),
            "external_userid": external_userid,
            "follow_user_display_name": item_follow_user_display_name or item_follow_user_userid,
            "follow_user_userid": item_follow_user_userid,
            "mobile": base_item.get("mobile", ""),
            "status_fields": {
                "signup_status": chosen["signup_status"],
                "current_tag_id": chosen["tag_id"],
                "current_tag_name": chosen["tag_name"],
                "matched_tags": [
                    {
                        "signup_status": chosen["signup_status"],
                        "tag_id": chosen["tag_id"],
                        "tag_name": chosen["tag_name"],
                    }
                ],
                "operation_flags": {
                    "action_executed": None,
                    "added_wecom": None,
                    "mobile_bound": bool(base_item.get("mobile", "")),
                },
            },
            "updated_at": base_item.get("updated_at", ""),
        }

    max_workers = min(16, max(4, len(external_userids) or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_live_signup_item, external_userid): external_userid for external_userid in external_userids}
        for future in as_completed(future_map):
            external_userid = future_map[future]
            try:
                item = future.result()
            except WeComClientError as exc:
                _log_wecom_client_error(exc, external_userid=external_userid, stage="external_contact.get")
                continue
            except Exception as exc:
                wecom_logger.exception("class user live query failed external_userid=%s error=%s", external_userid, exc)
                continue
            if not item:
                continue
            resolved_status = str(((item.get("status_fields") or {}).get("signup_status")) or "").strip()
            if resolved_status in counts:
                counts[resolved_status] += 1
            if normalized_filter and resolved_status != normalized_filter:
                continue
            items.append(item)

    items.sort(key=lambda item: (str(item.get("updated_at") or ""), str(item.get("external_userid") or "")), reverse=True)
    return {
        "filter": normalized_filter,
        "status_definitions": status_definitions,
        "stats": [
            {
                "signup_status": item["signup_status"],
                "label": item["label"],
                "count": counts[item["signup_status"]],
            }
            for item in status_definitions
        ],
        "items": items,
        "total": len(items),
        "meta": {
            "module": "class_user_management",
            "reserved_filters": ["action_executed", "added_wecom", "mobile_bound", "phone_compare_status"],
            "reserved_fields": ["operation_flags", "binding_flags", "compare_flags"],
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query_mode": "live_wecom_tags",
            "scope_external_user_count": len(external_userids),
        },
        "tag_initialization": configured,
        "live_refresh": {
            "refreshed": True,
            "mode": "live_wecom_tags",
            "external_user_count": len(external_userids),
            "matched_count": len(items) if normalized_filter else sum(counts.values()),
        },
    }


def _apply_signup_sidebar_tag(external_userid: str, owner_userid: str, signup_status: str) -> dict[str, object]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip() or _get_primary_follow_user_userid(normalized_external_userid)
    normalized_status = str(signup_status or "").strip()
    definition = get_signup_status_definition(normalized_status)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    if not definition:
        raise ValueError("signup_status is invalid")

    configured = _configured_signup_tag_rules_payload()
    rules = configured.get("rules") or []
    target_rule = next((item for item in rules if item.get("signup_status") == normalized_status), None)
    if not target_rule:
        raise ValueError("signup tags are not initialized, please initialize them in admin first")
    current_signup_status = str((_get_class_user_status_current(normalized_external_userid) or {}).get("signup_status") or "").strip()
    if normalized_status.startswith("signed_"):
        conversion_payload = mark_enrolled(
            external_userid=normalized_external_userid,
            owner_userid=normalized_owner_userid,
            operator=normalized_owner_userid,
            source="sidebar_manual",
            signup_status=normalized_status,
        )
        current_record = dict(conversion_payload.get("class_user_status") or {})
    elif current_signup_status.startswith("signed_"):
        conversion_payload = unmark_enrolled(
            external_userid=normalized_external_userid,
            owner_userid=normalized_owner_userid,
            operator=normalized_owner_userid,
            source="sidebar_manual",
            restore_signup_status=normalized_status,
        )
        current_record = dict(conversion_payload.get("class_user_status") or {})
    else:
        snapshot = _get_class_user_snapshot(normalized_external_userid, normalized_owner_userid)
        current_record = _apply_class_user_status_change(
            external_userid=normalized_external_userid,
            signup_status=normalized_status,
            set_by_userid=normalized_owner_userid,
            customer_name_snapshot=str(snapshot.get("customer_name_snapshot") or "").strip(),
            owner_userid_snapshot=str(snapshot.get("owner_userid_snapshot") or "").strip() or normalized_owner_userid,
            mobile_snapshot=str(snapshot.get("mobile_snapshot") or "").strip(),
        )
    remove_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in rules
            if str(item.get("tag_id") or "").strip() and str(item.get("signup_status") or "").strip() != normalized_status
        }
    )
    sync_status = "success"
    sync_error = ""
    result = {}
    try:
        client = get_app_runtime_client()
        result = client.mark_external_contact_tags(
            external_userid=normalized_external_userid,
            follow_user_userid=normalized_owner_userid,
            add_tags=[str(target_rule.get("tag_id") or "").strip()],
            remove_tags=remove_tag_ids,
        )
        save_tag_snapshot(
            normalized_owner_userid,
            normalized_external_userid,
            [str(target_rule.get("tag_id") or "").strip()],
            {str(target_rule.get("tag_id") or "").strip(): str(target_rule.get("tag_name") or "").strip()},
        )
        if remove_tag_ids:
            remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, remove_tag_ids)
    except WeComClientError as exc:
        sync_status = "failed"
        sync_error = str(exc)
        result = {
            "ok": False,
            "error": str(exc),
            "error_category": exc.category or "",
            "error_stage": exc.stage or "",
        }
    _update_class_user_status_sync_result(
        external_userid=normalized_external_userid,
        wecom_tag_sync_status=sync_status,
        wecom_tag_sync_error=sync_error,
    )
    tag_view = build_class_user_tag_view(
        [
            {
                "tag_id": str(target_rule.get("tag_id") or "").strip(),
                "tag_name": str(target_rule.get("tag_name") or "").strip(),
            }
        ]
    )
    return {
        "result": result,
        "signup_status": normalized_status,
        "current_tag": tag_view.get("current_tag_name", ""),
        "tag_id": str(target_rule.get("tag_id") or "").strip(),
        "removed_tag_ids": remove_tag_ids,
        "local_current": current_record,
        "wecom_tag_sync_status": sync_status,
        "wecom_tag_sync_error": sync_error,
    }
