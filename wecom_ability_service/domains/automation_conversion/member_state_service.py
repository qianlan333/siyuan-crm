from __future__ import annotations

from datetime import datetime
from typing import Any

from ...wecom_client import WeComClientError
from ..tags import repo as tags_repo
from . import service as service_seams
from . import local_projection, repo
from .admission_service import admit_channel_contact_to_program, record_standalone_channel_attempt
from .channel_binding_service import (
    ensure_legacy_program_channel_bindings,
    list_active_bindings_for_channel,
    upsert_channel_contact,
)
from .service import (
    DECISION_SOURCE_MANUAL,
    DECISION_SOURCE_QUESTIONNAIRE,
    DECISION_SOURCE_SYSTEM,
    DEFAULT_OWNER_STAFF_ID,
    FOLLOWUP_FOCUS,
    FOLLOWUP_NORMAL,
    POOL_CONVERTED,
    POOL_HUMAN_REPLY,
    POOL_NO_REPLY,
    POOL_OPERATING,
    POOL_PENDING_QUESTIONNAIRE,
    POOL_REMOVED,
    POOL_WON,
    QUESTIONNAIRE_PENDING,
    QUESTIONNAIRE_SUBMITTED,
    SOURCE_TYPE_MANUAL,
    SOURCE_TYPE_QRCODE,
    SOURCE_TYPE_WECOM_CUSTOMER_ACQUISITION,
    SOURCE_TYPE_SYSTEM,
    _automation_action_label,
    _json_loads,
    _member_payload_from_context,
    _member_snapshot,
    _normalized_text,
    _parse_timestamp,
    _persist_member,
    _questionnaire_status_label,
    _serialize_member,
    _touch_member_from_sources,
    _write_event,
    get_signup_conversion_config,
    recompute_pool,
    refresh_expired_silent_members,
    resolve_member_questionnaire_truth,
)


def _resolve_existing_member(external_contact_id: str = "", phone: str = "") -> dict[str, Any] | None:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    return repo.get_member_by_external_contact_id(normalized_external_contact_id) or repo.get_member_by_phone(
        normalized_phone
    )


def get_member_detail(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    refresh_expired_silent_members()
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if member:
        member = _touch_member_from_sources(member, action="system_view_sync", persist_event=False)
    context = service_seams._build_live_context(external_contact_id, phone)
    profile = context["profile"]
    if member:
        serialized_member = _serialize_member(member)
    else:
        preview_payload = _member_payload_from_context(
            None,
            {**context, "settings": get_signup_conversion_config()},
            in_pool=False,
            source_type=SOURCE_TYPE_SYSTEM,
        )
        preview_payload["current_pool"] = POOL_REMOVED
        serialized_member = _serialize_member(preview_payload)
    resolved_questionnaire = resolve_member_questionnaire_truth(
        external_contact_ids=context["lookup"].get("external_contact_ids") or [],
        phone=_normalized_text(profile.get("phone")) or serialized_member["phone"],
        member=serialized_member,
    )
    latest_manual_event = repo.get_latest_manual_event(int(member["id"])) if member else None
    cooldown_until = _parse_timestamp(serialized_member.get("ai_cooldown_until"))
    cooldown_remaining_seconds = (
        max(0, int((cooldown_until - datetime.now()).total_seconds())) if cooldown_until else 0
    )
    return {
        "member_exists": bool(member),
        "member": serialized_member,
        "profile": {
            "customer_name": _normalized_text(profile.get("customer_name"))
            or serialized_member["external_contact_id"]
            or "未命名客户",
            "owner_staff_id": _normalized_text(profile.get("owner_staff_id")) or serialized_member["owner_staff_id"],
            "owner_display_name": _normalized_text(profile.get("owner_display_name"))
            or _normalized_text(profile.get("owner_staff_id")),
            "external_contact_id": serialized_member["external_contact_id"],
            "phone": serialized_member["phone"],
            "unionid": _normalized_text(profile.get("unionid")),
        },
        "questionnaire": {
            "status": resolved_questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"],
            "status_label": _questionnaire_status_label(
                resolved_questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"]
            ),
            "hit_count": int(resolved_questionnaire.get("hit_count") or 0),
            "matched_questions": resolved_questionnaire.get("matched_questions") or [],
            "submitted_at": _normalized_text(resolved_questionnaire.get("submitted_at")),
        },
        "latest_manual_action": (
            {
                "action": _normalized_text(latest_manual_event.get("action")),
                "action_label": _automation_action_label(latest_manual_event.get("action")),
                "operator_id": _normalized_text(latest_manual_event.get("operator_id")),
                "remark": _normalized_text(latest_manual_event.get("remark")),
                "created_at": _normalized_text(latest_manual_event.get("created_at")),
            }
            if latest_manual_event
            else {}
        ),
        "last_ai_push_at": serialized_member["last_ai_push_at"],
        "ai_cooldown_until": serialized_member["ai_cooldown_until"],
        "ai_cooldown_remaining_seconds": cooldown_remaining_seconds,
        "actions": local_projection.button_state(
            current_pool=_normalized_text(serialized_member.get("current_pool")),
            in_pool=bool(serialized_member.get("in_pool")),
        ),
    }


def _mutate_member(
    *,
    external_contact_id: str = "",
    phone: str = "",
    action: str,
    operator_id: str,
    operator_type: str = "user",
    include_detail: bool = True,
    mutate,
) -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member and action != "put_in_pool":
        raise LookupError("automation member not found")
    context = service_seams._build_live_context(external_contact_id, phone)
    before = _serialize_member(
        member
        or _member_payload_from_context(None, {**context, "settings": get_signup_conversion_config()}, in_pool=False)
    )
    current = _member_payload_from_context(member, {**context, "settings": get_signup_conversion_config()})
    if not current.get("joined_at") and action == "put_in_pool":
        current["joined_at"] = service_seams._iso_now()
    mutation_result = mutate(current, context)
    if isinstance(mutation_result, tuple) and len(mutation_result) == 3:
        next_payload, remark, should_recompute_pool = mutation_result
    else:
        next_payload, remark = mutation_result
        should_recompute_pool = True
    if should_recompute_pool:
        next_payload["current_pool"] = recompute_pool(
            next_payload,
            {**context, "settings": get_signup_conversion_config()},
            action=action,
        )
    saved = _persist_member(member, next_payload)
    after = _serialize_member(saved)
    _write_event(
        member_id=int(saved["id"]),
        action=action,
        operator_type=operator_type,
        operator_id=operator_id,
        before_snapshot=_member_snapshot(before),
        after_snapshot=_member_snapshot(after),
        remark=remark,
    )
    return {
        "member": after,
        "remark": remark,
        "detail": (
            get_member_detail(external_contact_id=after["external_contact_id"], phone=after["phone"])
            if include_detail
            else {}
        ),
    }


def apply_router_target_pool(
    *,
    external_contact_id: str = "",
    phone: str = "",
    target_pool: str,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    legacy_target_pool_aliases = {
        "new_user": POOL_PENDING_QUESTIONNAIRE,
        "inactive_normal": POOL_OPERATING,
        "inactive_focus": POOL_OPERATING,
        "active_normal": POOL_OPERATING,
        "active_focus": POOL_OPERATING,
        "silent": POOL_OPERATING,
        "won": POOL_CONVERTED,
    }
    normalized_target_pool = legacy_target_pool_aliases.get(
        _normalized_text(target_pool),
        _normalized_text(target_pool),
    )
    allowed_pools = {
        POOL_PENDING_QUESTIONNAIRE,
        POOL_OPERATING,
        POOL_WON,
        POOL_NO_REPLY,
        POOL_HUMAN_REPLY,
    }
    if normalized_target_pool not in allowed_pools:
        raise ValueError("invalid target_pool")

    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        previous_pool = _normalized_text(current.get("current_pool"))
        if previous_pool not in {
            POOL_REMOVED,
            POOL_WON,
            POOL_NO_REPLY,
            POOL_HUMAN_REPLY,
        }:
            current["last_active_pool"] = previous_pool

        current["source_type"] = SOURCE_TYPE_SYSTEM
        current["decision_source"] = DECISION_SOURCE_SYSTEM
        current["joined_at"] = current.get("joined_at") or service_seams._iso_now()

        if normalized_target_pool == POOL_WON:
            current["in_pool"] = True
            current["current_pool"] = POOL_WON
            current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
            return current, f"router_target_pool={normalized_target_pool}", False

        current["in_pool"] = True
        current["current_pool"] = normalized_target_pool

        if normalized_target_pool == POOL_OPERATING:
            current["follow_type"] = FOLLOWUP_NORMAL
            current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
        elif normalized_target_pool == POOL_PENDING_QUESTIONNAIRE:
            current["questionnaire_status"] = QUESTIONNAIRE_PENDING

        return current, f"router_target_pool={normalized_target_pool}", False

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="router_apply_pool",
        operator_id=_normalized_text(operator_id) or "lobster_callback",
        operator_type=_normalized_text(operator_type) or "system",
        include_detail=False,
        mutate=mutate,
    )


def put_in_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        if _normalized_text(current.get("current_pool")) == POOL_WON:
            current["in_pool"] = False
            return current, "已成交客户保持已成交状态，不自动恢复到活跃池"
        current["in_pool"] = True
        current["source_type"] = SOURCE_TYPE_MANUAL
        current["joined_at"] = current.get("joined_at") or service_seams._iso_now()
        if not current.get("decision_source"):
            current["decision_source"] = DECISION_SOURCE_SYSTEM
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="put_in_pool",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def remove_from_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        current["in_pool"] = False
        current["current_pool"] = POOL_REMOVED
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="remove_from_pool",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def set_follow_type(
    *,
    external_contact_id: str = "",
    phone: str = "",
    follow_type: str,
    operator_id: str = "",
) -> dict[str, Any]:
    normalized_follow_type = _normalized_text(follow_type)
    if normalized_follow_type not in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
        raise ValueError("follow_type must be normal or focus")

    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        current["follow_type"] = normalized_follow_type
        current["decision_source"] = DECISION_SOURCE_MANUAL
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="set_focus" if normalized_follow_type == FOLLOWUP_FOCUS else "set_normal",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def mark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        current["last_active_pool"] = (
            _normalized_text(current.get("current_pool"))
            if _normalized_text(current.get("current_pool")) not in {POOL_WON, POOL_REMOVED}
            else _normalized_text(current.get("last_active_pool"))
        )
        current["in_pool"] = True
        current["current_pool"] = POOL_WON
        current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="mark_won",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def unmark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        current["in_pool"] = True
        restore_pool = _normalized_text(current.get("last_active_pool"))
        if restore_pool and restore_pool != POOL_WON:
            current["current_pool"] = restore_pool
            current["last_active_pool"] = restore_pool
        else:
            current["current_pool"] = recompute_pool(
                {**current, "current_pool": POOL_REMOVED},
                {**context, "settings": get_signup_conversion_config()},
                action="unmark_won",
            )
            current["last_active_pool"] = _normalized_text(current.get("current_pool"))
        return current, "", False

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="unmark_won",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def sync_member_from_questionnaire_submission(
    *,
    external_contact_id: str = "",
    phone: str = "",
    questionnaire_id: int | None = None,
    operator_id: str = "system",
) -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        return {"updated": False, "reason": "member_not_found"}
    before = _serialize_member(member)
    saved = _touch_member_from_sources(
        member,
        action="questionnaire_update",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "questionnaire",
        persist_event=True,
    )
    if int(questionnaire_id or 0) > 0 and _normalized_text(saved.get("questionnaire_status")) != QUESTIONNAIRE_SUBMITTED:
        def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
            del context
            current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
            current["decision_source"] = DECISION_SOURCE_QUESTIONNAIRE
            current["in_pool"] = True
            current["joined_at"] = current.get("joined_at") or service_seams._iso_now()
            if _normalized_text(current.get("current_pool")) != POOL_WON:
                current["current_pool"] = POOL_OPERATING
                current["follow_type"] = current.get("follow_type") or FOLLOWUP_NORMAL
            return current, f"questionnaire_id={int(questionnaire_id or 0)}", False

        saved = _mutate_member(
            external_contact_id=external_contact_id,
            phone=phone,
            action="questionnaire_update",
            operator_id=_normalized_text(operator_id) or "questionnaire",
            operator_type="system",
            include_detail=False,
            mutate=mutate,
        )
    after = _serialize_member(saved)
    return {"updated": before != after, "member": after}


def sync_member_activation(*, external_contact_id: str = "", phone: str = "", operator_id: str = "system") -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        return {"updated": False, "reason": "member_not_found"}
    before = _serialize_member(member)
    saved = _touch_member_from_sources(
        member,
        action="member_refresh",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "member_refresh",
        persist_event=True,
    )
    after = _serialize_member(saved)
    return {"updated": before != after, "member": after}


def _extract_channel_scene(payload_json: dict[str, Any]) -> str:
    payload = _json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("state", "State", "scene", "scene_value", "channel_code"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _extract_welcome_code(payload_json: dict[str, Any]) -> str:
    payload = _json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("welcome_code", "WelcomeCode", "welcomeCode"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _send_channel_welcome_message(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    welcome_message = _normalized_text(channel.get("welcome_message"))
    welcome_code = _extract_welcome_code(payload_json or {})
    serialized_member = _serialize_member(member)
    if not welcome_message:
        return {"attempted": False, "sent": False, "reason": "not_configured"}
    if not welcome_code:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark="missing_welcome_code",
        )
        return {"attempted": True, "sent": False, "error": "missing_welcome_code"}

    request_payload: dict[str, Any] = {
        "welcome_code": welcome_code,
        "text": {"content": welcome_message},
    }
    welcome_library_ids: list[int] = []
    raw_library_ids = channel.get("welcome_miniprogram_library_ids") or []
    if isinstance(raw_library_ids, str):
        try:
            import json as _json

            raw_library_ids = _json.loads(raw_library_ids)
        except (ValueError, TypeError):
            raw_library_ids = []
    for value in raw_library_ids or []:
        try:
            welcome_library_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if welcome_library_ids:
        from .. import miniprogram_library as _miniprogram_library

        welcome_attachments: list[dict[str, Any]] = []
        for lid in welcome_library_ids:
            welcome_attachments.append(
                _miniprogram_library.materialize_miniprogram_attachment(lid)
            )
        if welcome_attachments:
            request_payload["attachments"] = welcome_attachments
    try:
        raw_image_ids = channel.get("welcome_image_library_ids") or []
        raw_attachment_ids = channel.get("welcome_attachment_library_ids") or []
        if raw_image_ids or raw_attachment_ids:
            from .. import attachment_library as _attachment_library, image_library as _image_library

            welcome_attachments = list(request_payload.get("attachments") or [])
            for iid in _attachment_library._normalize_id_list(raw_image_ids):
                welcome_attachments.append(
                    {"msgtype": "image", "image": {"media_id": _image_library.resolve_image_media_id(iid)}}
                )
            for aid in _attachment_library._normalize_id_list(raw_attachment_ids):
                welcome_attachments.append(_attachment_library.materialize_file_attachment(aid))
            if len(welcome_attachments) > 9:
                raise ValueError("welcome message supports at most 9 attachments")
            if welcome_attachments:
                request_payload["attachments"] = welcome_attachments
    except (ValueError, RuntimeError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}
    try:
        wecom_result = service_seams.get_contact_runtime_client().send_welcome_msg(request_payload)
    except (WeComClientError, AttributeError, ValueError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}

    _write_event(
        member_id=int(member["id"]),
        action="qrcode_welcome_sent",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(serialized_member),
        after_snapshot=_member_snapshot(serialized_member),
        remark="official_send_welcome_msg",
    )
    return {
        "attempted": True,
        "sent": True,
        "welcome_code": welcome_code,
        "wecom_result": dict(wecom_result or {}),
    }


def _apply_channel_entry_tag(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    operator_id: str = "",
) -> dict[str, Any]:
    entry_tag_id = _normalized_text(channel.get("entry_tag_id"))
    entry_tag_name = _normalized_text(channel.get("entry_tag_name"))
    entry_tag_group_name = _normalized_text(channel.get("entry_tag_group_name"))
    serialized_member = _serialize_member(member)
    external_contact_id = _normalized_text(serialized_member.get("external_contact_id"))
    owner_staff_id = _normalized_text(serialized_member.get("owner_staff_id"))
    if not entry_tag_id:
        return {"attempted": False, "applied": False, "reason": "not_configured"}
    if not external_contact_id:
        return {"attempted": False, "applied": False, "reason": "missing_external_contact_id"}
    if not owner_staff_id:
        return {"attempted": False, "applied": False, "reason": "missing_owner_staff_id"}
    try:
        wecom_result = service_seams.get_app_runtime_client().mark_external_contact_tags(
            external_userid=external_contact_id,
            follow_user_userid=owner_staff_id,
            add_tags=[entry_tag_id],
            remove_tags=[],
        )
        tags_repo.save_tag_snapshot(owner_staff_id, external_contact_id, [entry_tag_id], {entry_tag_id: entry_tag_name})
    except (WeComClientError, AttributeError, ValueError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_entry_tag_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {
            "attempted": True,
            "applied": False,
            "error": str(exc),
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
        }
    _write_event(
        member_id=int(member["id"]),
        action="qrcode_entry_tag_applied",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(serialized_member),
        after_snapshot=_member_snapshot(serialized_member),
        remark=entry_tag_name or entry_tag_id,
    )
    return {
        "attempted": True,
        "applied": True,
        "entry_tag_id": entry_tag_id,
        "entry_tag_name": entry_tag_name,
        "entry_tag_group_name": entry_tag_group_name,
        "wecom_result": dict(wecom_result or {}),
    }


def _send_channel_welcome_message_for_contact(
    *,
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    welcome_message = _normalized_text(channel.get("welcome_message"))
    welcome_code = _extract_welcome_code(payload_json or {})
    if not welcome_message:
        return {"attempted": False, "sent": False, "reason": "not_configured"}
    if not welcome_code:
        return {"attempted": True, "sent": False, "error": "missing_welcome_code"}
    try:
        result = service_seams.get_contact_runtime_client().send_welcome_msg(
            {"welcome_code": welcome_code, "text": {"content": welcome_message}}
        )
    except (WeComClientError, AttributeError, ValueError) as exc:
        return {"attempted": True, "sent": False, "error": str(exc)}
    return {"attempted": True, "sent": True, "welcome_code": welcome_code, "wecom_result": dict(result or {})}


def _apply_channel_entry_tag_for_contact(
    *,
    external_contact_id: str,
    owner_staff_id: str,
    channel: dict[str, Any],
) -> dict[str, Any]:
    entry_tag_id = _normalized_text(channel.get("entry_tag_id"))
    entry_tag_name = _normalized_text(channel.get("entry_tag_name"))
    entry_tag_group_name = _normalized_text(channel.get("entry_tag_group_name"))
    if not entry_tag_id:
        return {"attempted": False, "applied": False, "reason": "not_configured"}
    if not _normalized_text(external_contact_id):
        return {"attempted": False, "applied": False, "reason": "missing_external_contact_id"}
    if not _normalized_text(owner_staff_id):
        return {"attempted": False, "applied": False, "reason": "missing_owner_staff_id"}
    try:
        result = service_seams.get_app_runtime_client().mark_external_contact_tags(
            external_userid=_normalized_text(external_contact_id),
            follow_user_userid=_normalized_text(owner_staff_id),
            add_tags=[entry_tag_id],
            remove_tags=[],
        )
        tags_repo.save_tag_snapshot(_normalized_text(owner_staff_id), _normalized_text(external_contact_id), [entry_tag_id], {entry_tag_id: entry_tag_name})
    except (WeComClientError, AttributeError, ValueError) as exc:
        return {
            "attempted": True,
            "applied": False,
            "error": str(exc),
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
        }
    return {
        "attempted": True,
        "applied": True,
        "entry_tag_id": entry_tag_id,
        "entry_tag_name": entry_tag_name,
        "entry_tag_group_name": entry_tag_group_name,
        "wecom_result": dict(result or {}),
    }


def _channel_with_historical_entry_tag(
    channel: dict[str, Any],
    *,
    channel_scene: str = "",
    owner_staff_id: str = "",
) -> dict[str, Any]:
    if _normalized_text(channel.get("entry_tag_id")):
        return channel
    historical_tag = repo.find_entry_tag_by_historical_scene_value(
        channel_scene,
        owner_staff_id=_normalized_text(owner_staff_id),
    )
    if not _normalized_text(historical_tag.get("entry_tag_id")):
        return channel
    return {
        **channel,
        "entry_tag_id": _normalized_text(historical_tag.get("entry_tag_id")),
        "entry_tag_name": _normalized_text(historical_tag.get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(historical_tag.get("entry_tag_group_name")),
    }


def _all_bindings_rejected_for_archived_program(admission_results: list[dict[str, Any]]) -> bool:
    if not admission_results:
        return False
    for item in admission_results:
        if item.get("legacy_member"):
            return False
        if _normalized_text(item.get("admission_status")) != "rejected":
            return False
        if "program_archived" not in _normalized_text(item.get("reason")):
            return False
    return True


def handle_channel_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    channel: dict[str, Any] | None = None,
    source_type: str = SOURCE_TYPE_QRCODE,
    follow_user_userid: str = "",
    initial_audience_code: str = "",
    event_action: str = "qrcode_enter",
    send_welcome_message: bool = False,
    event_log_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    raise RuntimeError("Legacy channel entry is retired. Use aicrm_next.channel_entry.")

    channel_scene = ""
    if not channel:
        channel_scene = _extract_channel_scene(payload_json or {})
        if not channel_scene:
            return {"handled": False, "reason": "missing_channel_scene"}
        channel = repo.find_channel_by_scene_value(channel_scene)
        if not channel:
            channel = repo.find_channel_by_historical_scene_value(channel_scene)
            if not channel:
                return {"handled": False, "reason": "channel_not_found"}
    if (
        source_type == SOURCE_TYPE_WECOM_CUSTOMER_ACQUISITION
        and _normalized_text(channel.get("status")) != "active"
    ):
        return {"handled": False, "reason": "channel_disabled"}
    trigger_time = service_seams._iso_now()
    owner_staff_id = _normalized_text(follow_user_userid) or _normalized_text(channel.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID
    channel = _channel_with_historical_entry_tag(
        channel,
        channel_scene=channel_scene,
        owner_staff_id=owner_staff_id,
    )
    master_customer_id = repo.lookup_person_id_by_external_contact_id(external_contact_id)
    channel_contact = upsert_channel_contact(
        channel_id=int(channel["id"]),
        external_contact_id=external_contact_id,
        master_customer_id=master_customer_id,
        owner_staff_id=owner_staff_id,
        source_payload=payload_json or {},
        entered_at=trigger_time,
    )
    active_bindings = list_active_bindings_for_channel(int(channel["id"]))
    legacy_binding_report = {}
    if not active_bindings:
        legacy_binding_report = ensure_legacy_program_channel_bindings(channel_id=int(channel["id"]))
        active_bindings = list_active_bindings_for_channel(int(channel["id"]))
    if not active_bindings:
        standalone_attempt = record_standalone_channel_attempt(
            channel_id=int(channel["id"]),
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=event_action,
            trigger_payload={**dict(payload_json or {}), "source_type": source_type},
        )
        welcome_result = (
            _send_channel_welcome_message_for_contact(channel=channel, payload_json=payload_json)
            if send_welcome_message
            else {"attempted": False, "sent": False, "reason": "disabled"}
        )
        entry_tag_result = _apply_channel_entry_tag_for_contact(
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            channel=channel,
        )
        return {
            "handled": True,
            "mode": "standalone_channel",
            "reason": "channel_without_active_binding",
            "channel": {"id": int(channel["id"]), "scene_value": _normalized_text(channel.get("scene_value"))},
            "channel_contact": channel_contact,
            "admission_attempt": standalone_attempt,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
            "program_member_written": False,
            "legacy_binding_report": legacy_binding_report,
        }
    admission_results = [
        admit_channel_contact_to_program(
            int(binding["program_id"]),
            int(channel["id"]),
            int(binding["id"]),
            external_contact_id,
            follow_user_userid=owner_staff_id,
            trigger_payload={**dict(payload_json or {}), "source_type": source_type},
            trigger_time=trigger_time,
            trigger_type=event_action,
        )
        for binding in active_bindings
    ]
    projected_member = next((item.get("legacy_member") for item in admission_results if item.get("legacy_member")), None)
    if projected_member:
        welcome_result = (
            _send_channel_welcome_message(
                member=projected_member,
                channel=channel,
                payload_json=payload_json,
                operator_id=operator_id,
            )
            if send_welcome_message
            else {"attempted": False, "sent": False, "reason": "disabled"}
        )
        entry_tag_result = _apply_channel_entry_tag(
            member=projected_member,
            channel=channel,
            operator_id=operator_id,
        )
        return {
            "handled": True,
            "mode": "program_admission",
            "member": _serialize_member(projected_member),
            "channel_contact": channel_contact,
            "admission_results": admission_results,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
            "legacy_binding_report": legacy_binding_report,
        }
    if (
        _normalized_text(channel.get("status")) == "active"
        and _all_bindings_rejected_for_archived_program(admission_results)
    ):
        welcome_result = (
            _send_channel_welcome_message_for_contact(channel=channel, payload_json=payload_json)
            if send_welcome_message
            else {"attempted": False, "sent": False, "reason": "disabled"}
        )
        entry_tag_result = _apply_channel_entry_tag_for_contact(
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            channel=channel,
        )
        return {
            "handled": True,
            "mode": "standalone_channel_archived_program_fallback",
            "reason": "program_archived_fallback_to_channel",
            "channel": {
                "id": int(channel["id"]),
                "scene_value": _normalized_text(channel.get("scene_value")),
                "matched_scene": _normalized_text(channel_scene),
            },
            "channel_contact": channel_contact,
            "admission_results": admission_results,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
            "program_member_written": False,
            "legacy_binding_report": legacy_binding_report,
        }
    return {
        "handled": True,
        "mode": "program_admission",
        "reason": "no_legacy_projection",
        "channel_contact": channel_contact,
        "admission_results": admission_results,
        "welcome_message": {"attempted": False, "sent": False, "reason": "legacy_member_missing"},
        "entry_tag": {"attempted": False, "applied": False, "reason": "legacy_member_missing"},
        "legacy_binding_report": legacy_binding_report,
    }

    # Legacy single-pool behavior below is intentionally retained as dead fallback for
    # monkeypatched tests that bypass the new admission path.
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    context = service_seams._build_live_context(external_contact_id, phone)
    before = _serialize_member(
        member
        or _member_payload_from_context(None, {**context, "settings": get_signup_conversion_config()}, in_pool=False)
    )
    current = _member_payload_from_context(
        member,
        {**context, "settings": get_signup_conversion_config()},
        source_type=source_type,
        source_channel_id=int(channel["id"]),
        in_pool=True,
    )
    current["owner_staff_id"] = _normalized_text(follow_user_userid) or DEFAULT_OWNER_STAFF_ID
    current["joined_at"] = current.get("joined_at") or service_seams._iso_now()
    normalized_initial_audience = _normalized_text(initial_audience_code)
    if (
        source_type == SOURCE_TYPE_WECOM_CUSTOMER_ACQUISITION
        and normalized_initial_audience in {POOL_PENDING_QUESTIONNAIRE, POOL_OPERATING, POOL_CONVERTED}
    ):
        current["current_audience_code"] = normalized_initial_audience
    if before["current_pool"] == POOL_WON:
        saved = _persist_member(member, {**current, "in_pool": False, "current_pool": POOL_WON})
        _write_event(
            member_id=int(saved["id"]),
            action=event_action,
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(before),
            after_snapshot=_member_snapshot(saved),
            remark=(
                "member already won; qrcode entry only recorded"
                if source_type == SOURCE_TYPE_QRCODE
                else "member already won; channel entry only recorded"
            ),
        )
        welcome_result = (
            _send_channel_welcome_message(
                member=saved,
                channel=channel,
                payload_json=payload_json,
                operator_id=operator_id,
            )
            if send_welcome_message
            else {"attempted": False, "sent": False, "reason": "disabled"}
        )
        entry_tag_result = _apply_channel_entry_tag(
            member=saved,
            channel=channel,
            operator_id=operator_id,
        )
        return {
            "handled": True,
            "member": _serialize_member(saved),
            "won_kept": True,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
        }
    current["current_pool"] = recompute_pool(
        current,
        {**context, "settings": get_signup_conversion_config()},
        action=event_action,
    )
    saved = _persist_member(member, current)
    _write_event(
        member_id=int(saved["id"]),
        action=event_action,
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(before),
        after_snapshot=_member_snapshot(saved),
    )
    welcome_result = (
        _send_channel_welcome_message(
            member=saved,
            channel=channel,
            payload_json=payload_json,
            operator_id=operator_id,
        )
        if send_welcome_message
        else {"attempted": False, "sent": False, "reason": "disabled"}
    )
    entry_tag_result = _apply_channel_entry_tag(
        member=saved,
        channel=channel,
        operator_id=operator_id,
    )
    return {
        "handled": True,
        "member": _serialize_member(saved),
        "welcome_message": welcome_result,
        "entry_tag": entry_tag_result,
    }


def handle_qrcode_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    follow_user_userid: str = "",
    send_welcome_message: bool = False,
    event_log_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    return handle_channel_enter_from_callback(
        external_contact_id=external_contact_id,
        phone=phone,
        payload_json=payload_json,
        operator_id=operator_id,
        follow_user_userid=follow_user_userid,
        source_type=SOURCE_TYPE_QRCODE,
        event_action="qrcode_enter",
        send_welcome_message=send_welcome_message,
        event_log_id=event_log_id,
        dry_run=dry_run,
    )


__all__ = [
    "_apply_channel_entry_tag",
    "_extract_channel_scene",
    "_extract_welcome_code",
    "_mutate_member",
    "_resolve_existing_member",
    "_send_channel_welcome_message",
    "apply_router_target_pool",
    "get_member_detail",
    "handle_channel_enter_from_callback",
    "handle_qrcode_enter_from_callback",
    "mark_won",
    "put_in_pool",
    "remove_from_pool",
    "set_follow_type",
    "sync_member_activation",
    "sync_member_from_questionnaire_submission",
    "unmark_won",
]
