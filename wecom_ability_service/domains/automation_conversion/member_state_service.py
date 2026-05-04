from __future__ import annotations

from typing import Any

from . import service as _legacy


def _resolve_existing_member(external_contact_id: str = "", phone: str = "") -> dict[str, Any] | None:
    normalized_external_contact_id = _legacy._normalized_text(external_contact_id)
    normalized_phone = _legacy._normalized_text(phone)
    return _legacy.repo.get_member_by_external_contact_id(normalized_external_contact_id) or _legacy.repo.get_member_by_phone(
        normalized_phone
    )


def get_member_detail(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    _legacy.refresh_expired_silent_members()
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if member:
        member = _legacy._touch_member_from_sources(member, action="system_view_sync", persist_event=False)
    context = _legacy._build_live_context(external_contact_id, phone)
    profile = context["profile"]
    if member:
        serialized_member = _legacy._serialize_member(member)
    else:
        preview_payload = _legacy._member_payload_from_context(
            None,
            {**context, "settings": _legacy.get_signup_conversion_config()},
            in_pool=False,
            source_type=_legacy.SOURCE_TYPE_SYSTEM,
        )
        preview_payload["current_pool"] = _legacy.POOL_REMOVED
        serialized_member = _legacy._serialize_member(preview_payload)
    resolved_questionnaire = _legacy.resolve_member_questionnaire_truth(
        external_contact_ids=context["lookup"].get("external_contact_ids") or [],
        phone=_legacy._normalized_text(profile.get("phone")) or serialized_member["phone"],
        member=serialized_member,
    )
    latest_manual_event = _legacy.repo.get_latest_manual_event(int(member["id"])) if member else None
    cooldown_until = _legacy._parse_timestamp(serialized_member.get("ai_cooldown_until"))
    cooldown_remaining_seconds = (
        max(0, int((cooldown_until - _legacy.datetime.now()).total_seconds())) if cooldown_until else 0
    )
    return {
        "member_exists": bool(member),
        "member": serialized_member,
        "profile": {
            "customer_name": _legacy._normalized_text(profile.get("customer_name"))
            or serialized_member["external_contact_id"]
            or "未命名客户",
            "owner_staff_id": _legacy._normalized_text(profile.get("owner_staff_id")) or serialized_member["owner_staff_id"],
            "owner_display_name": _legacy._normalized_text(profile.get("owner_display_name"))
            or _legacy._normalized_text(profile.get("owner_staff_id")),
            "external_contact_id": serialized_member["external_contact_id"],
            "phone": serialized_member["phone"],
            "unionid": _legacy._normalized_text(profile.get("unionid")),
        },
        "questionnaire": {
            "status": resolved_questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"],
            "status_label": _legacy._questionnaire_status_label(
                resolved_questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"]
            ),
            "hit_count": int(resolved_questionnaire.get("hit_count") or 0),
            "matched_questions": resolved_questionnaire.get("matched_questions") or [],
            "submitted_at": _legacy._normalized_text(resolved_questionnaire.get("submitted_at")),
        },
        "latest_manual_action": (
            {
                "action": _legacy._normalized_text(latest_manual_event.get("action")),
                "action_label": _legacy._automation_action_label(latest_manual_event.get("action")),
                "operator_id": _legacy._normalized_text(latest_manual_event.get("operator_id")),
                "remark": _legacy._normalized_text(latest_manual_event.get("remark")),
                "created_at": _legacy._normalized_text(latest_manual_event.get("created_at")),
            }
            if latest_manual_event
            else {}
        ),
        "last_ai_push_at": serialized_member["last_ai_push_at"],
        "ai_cooldown_until": serialized_member["ai_cooldown_until"],
        "ai_cooldown_remaining_seconds": cooldown_remaining_seconds,
        "actions": _legacy.local_projection.button_state(
            current_pool=_legacy._normalized_text(serialized_member.get("current_pool")),
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
    context = _legacy._build_live_context(external_contact_id, phone)
    before = _legacy._serialize_member(
        member
        or _legacy._member_payload_from_context(None, {**context, "settings": _legacy.get_signup_conversion_config()}, in_pool=False)
    )
    current = _legacy._member_payload_from_context(member, {**context, "settings": _legacy.get_signup_conversion_config()})
    if not current.get("joined_at") and action == "put_in_pool":
        current["joined_at"] = _legacy._iso_now()
    mutation_result = mutate(current, context)
    if isinstance(mutation_result, tuple) and len(mutation_result) == 3:
        next_payload, remark, should_recompute_pool = mutation_result
    else:
        next_payload, remark = mutation_result
        should_recompute_pool = True
    if should_recompute_pool:
        next_payload["current_pool"] = _legacy.recompute_pool(
            next_payload,
            {**context, "settings": _legacy.get_signup_conversion_config()},
            action=action,
        )
    saved = _legacy._persist_member(member, next_payload)
    after = _legacy._serialize_member(saved)
    _legacy._write_event(
        member_id=int(saved["id"]),
        action=action,
        operator_type=operator_type,
        operator_id=operator_id,
        before_snapshot=_legacy._member_snapshot(before),
        after_snapshot=_legacy._member_snapshot(after),
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
        "new_user": _legacy.POOL_PENDING_QUESTIONNAIRE,
        "inactive_normal": _legacy.POOL_OPERATING,
        "inactive_focus": _legacy.POOL_OPERATING,
        "active_normal": _legacy.POOL_OPERATING,
        "active_focus": _legacy.POOL_OPERATING,
        "silent": _legacy.POOL_OPERATING,
        "won": _legacy.POOL_CONVERTED,
    }
    normalized_target_pool = legacy_target_pool_aliases.get(
        _legacy._normalized_text(target_pool),
        _legacy._normalized_text(target_pool),
    )
    allowed_pools = {
        _legacy.POOL_PENDING_QUESTIONNAIRE,
        _legacy.POOL_OPERATING,
        _legacy.POOL_WON,
        _legacy.POOL_NO_REPLY,
        _legacy.POOL_HUMAN_REPLY,
    }
    if normalized_target_pool not in allowed_pools:
        raise ValueError("invalid target_pool")

    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        previous_pool = _legacy._normalized_text(current.get("current_pool"))
        if previous_pool not in {
            _legacy.POOL_REMOVED,
            _legacy.POOL_WON,
            _legacy.POOL_NO_REPLY,
            _legacy.POOL_HUMAN_REPLY,
        }:
            current["last_active_pool"] = previous_pool

        current["source_type"] = _legacy.SOURCE_TYPE_SYSTEM
        current["decision_source"] = _legacy.DECISION_SOURCE_SYSTEM
        current["joined_at"] = current.get("joined_at") or _legacy._iso_now()

        if normalized_target_pool == _legacy.POOL_WON:
            current["in_pool"] = True
            current["current_pool"] = _legacy.POOL_WON
            current["questionnaire_status"] = _legacy.QUESTIONNAIRE_SUBMITTED
            return current, f"router_target_pool={normalized_target_pool}", False

        current["in_pool"] = True
        current["current_pool"] = normalized_target_pool

        if normalized_target_pool == _legacy.POOL_OPERATING:
            current["follow_type"] = _legacy.FOLLOWUP_NORMAL
            current["questionnaire_status"] = _legacy.QUESTIONNAIRE_SUBMITTED
        elif normalized_target_pool == _legacy.POOL_PENDING_QUESTIONNAIRE:
            current["questionnaire_status"] = _legacy.QUESTIONNAIRE_PENDING

        return current, f"router_target_pool={normalized_target_pool}", False

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="router_apply_pool",
        operator_id=_legacy._normalized_text(operator_id) or "lobster_callback",
        operator_type=_legacy._normalized_text(operator_type) or "system",
        include_detail=False,
        mutate=mutate,
    )


def put_in_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        if _legacy._normalized_text(current.get("current_pool")) == _legacy.POOL_WON:
            current["in_pool"] = False
            return current, "已成交客户保持已成交状态，不自动恢复到活跃池"
        current["in_pool"] = True
        current["source_type"] = _legacy.SOURCE_TYPE_MANUAL
        current["joined_at"] = current.get("joined_at") or _legacy._iso_now()
        if not current.get("decision_source"):
            current["decision_source"] = _legacy.DECISION_SOURCE_SYSTEM
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="put_in_pool",
        operator_id=_legacy._normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def remove_from_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        current["in_pool"] = False
        current["current_pool"] = _legacy.POOL_REMOVED
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="remove_from_pool",
        operator_id=_legacy._normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def set_follow_type(
    *,
    external_contact_id: str = "",
    phone: str = "",
    follow_type: str,
    operator_id: str = "",
) -> dict[str, Any]:
    normalized_follow_type = _legacy._normalized_text(follow_type)
    if normalized_follow_type not in {_legacy.FOLLOWUP_NORMAL, _legacy.FOLLOWUP_FOCUS}:
        raise ValueError("follow_type must be normal or focus")

    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        current["follow_type"] = normalized_follow_type
        current["decision_source"] = _legacy.DECISION_SOURCE_MANUAL
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="set_focus" if normalized_follow_type == _legacy.FOLLOWUP_FOCUS else "set_normal",
        operator_id=_legacy._normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def mark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        del context
        current["last_active_pool"] = (
            _legacy._normalized_text(current.get("current_pool"))
            if _legacy._normalized_text(current.get("current_pool")) not in {_legacy.POOL_WON, _legacy.POOL_REMOVED}
            else _legacy._normalized_text(current.get("last_active_pool"))
        )
        current["in_pool"] = True
        current["current_pool"] = _legacy.POOL_WON
        current["questionnaire_status"] = _legacy.QUESTIONNAIRE_SUBMITTED
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="mark_won",
        operator_id=_legacy._normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def unmark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        current["in_pool"] = True
        restore_pool = _legacy._normalized_text(current.get("last_active_pool"))
        if restore_pool and restore_pool != _legacy.POOL_WON:
            current["current_pool"] = restore_pool
            current["last_active_pool"] = restore_pool
        else:
            current["current_pool"] = _legacy.recompute_pool(
                {**current, "current_pool": _legacy.POOL_REMOVED},
                {**context, "settings": _legacy.get_signup_conversion_config()},
                action="unmark_won",
            )
            current["last_active_pool"] = _legacy._normalized_text(current.get("current_pool"))
        return current, "", False

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="unmark_won",
        operator_id=_legacy._normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def sync_member_from_questionnaire_submission(
    *,
    external_contact_id: str = "",
    phone: str = "",
    operator_id: str = "system",
) -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        return {"updated": False, "reason": "member_not_found"}
    before = _legacy._serialize_member(member)
    saved = _legacy._touch_member_from_sources(
        member,
        action="questionnaire_update",
        operator_type="system",
        operator_id=_legacy._normalized_text(operator_id) or "questionnaire",
        persist_event=True,
    )
    after = _legacy._serialize_member(saved)
    return {"updated": before != after, "member": after}


def sync_member_activation(*, external_contact_id: str = "", phone: str = "", operator_id: str = "system") -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        return {"updated": False, "reason": "member_not_found"}
    before = _legacy._serialize_member(member)
    saved = _legacy._touch_member_from_sources(
        member,
        action="member_refresh",
        operator_type="system",
        operator_id=_legacy._normalized_text(operator_id) or "member_refresh",
        persist_event=True,
    )
    after = _legacy._serialize_member(saved)
    return {"updated": before != after, "member": after}


def _extract_channel_scene(payload_json: dict[str, Any]) -> str:
    payload = _legacy._json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("state", "State", "scene", "scene_value", "channel_code"):
        value = _legacy._normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _extract_welcome_code(payload_json: dict[str, Any]) -> str:
    payload = _legacy._json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("welcome_code", "WelcomeCode", "welcomeCode"):
        value = _legacy._normalized_text(payload.get(key))
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
    welcome_message = _legacy._normalized_text(channel.get("welcome_message"))
    welcome_code = _extract_welcome_code(payload_json or {})
    serialized_member = _legacy._serialize_member(member)
    if not welcome_message:
        return {"attempted": False, "sent": False, "reason": "not_configured"}
    if not welcome_code:
        _legacy._write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_legacy._member_snapshot(serialized_member),
            after_snapshot=_legacy._member_snapshot(serialized_member),
            remark="missing_welcome_code",
        )
        return {"attempted": True, "sent": False, "error": "missing_welcome_code"}

    request_payload = {
        "welcome_code": welcome_code,
        "text": {"content": welcome_message},
    }
    try:
        wecom_result = _legacy.get_contact_runtime_client().send_welcome_msg(request_payload)
    except (_legacy.WeComClientError, AttributeError, ValueError) as exc:
        _legacy._write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_legacy._member_snapshot(serialized_member),
            after_snapshot=_legacy._member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}

    _legacy._write_event(
        member_id=int(member["id"]),
        action="qrcode_welcome_sent",
        operator_type="system",
        operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_legacy._member_snapshot(serialized_member),
        after_snapshot=_legacy._member_snapshot(serialized_member),
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
    entry_tag_id = _legacy._normalized_text(channel.get("entry_tag_id"))
    entry_tag_name = _legacy._normalized_text(channel.get("entry_tag_name"))
    entry_tag_group_name = _legacy._normalized_text(channel.get("entry_tag_group_name"))
    serialized_member = _legacy._serialize_member(member)
    external_contact_id = _legacy._normalized_text(serialized_member.get("external_contact_id"))
    owner_staff_id = _legacy._normalized_text(serialized_member.get("owner_staff_id"))
    if not entry_tag_id:
        return {"attempted": False, "applied": False, "reason": "not_configured"}
    if not external_contact_id:
        return {"attempted": False, "applied": False, "reason": "missing_external_contact_id"}
    if not owner_staff_id:
        return {"attempted": False, "applied": False, "reason": "missing_owner_staff_id"}
    try:
        wecom_result = _legacy.get_app_runtime_client().mark_external_contact_tags(
            external_userid=external_contact_id,
            follow_user_userid=owner_staff_id,
            add_tags=[entry_tag_id],
            remove_tags=[],
        )
        _legacy.tags_repo.save_tag_snapshot(owner_staff_id, external_contact_id, [entry_tag_id], {entry_tag_id: entry_tag_name})
    except (_legacy.WeComClientError, AttributeError, ValueError) as exc:
        _legacy._write_event(
            member_id=int(member["id"]),
            action="qrcode_entry_tag_failed",
            operator_type="system",
            operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_legacy._member_snapshot(serialized_member),
            after_snapshot=_legacy._member_snapshot(serialized_member),
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
    _legacy._write_event(
        member_id=int(member["id"]),
        action="qrcode_entry_tag_applied",
        operator_type="system",
        operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_legacy._member_snapshot(serialized_member),
        after_snapshot=_legacy._member_snapshot(serialized_member),
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


def handle_qrcode_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    send_welcome_message: bool = False,
) -> dict[str, Any]:
    channel_scene = _extract_channel_scene(payload_json or {})
    if not channel_scene:
        return {"handled": False, "reason": "missing_channel_scene"}
    channel = _legacy.repo.find_channel_by_scene_value(channel_scene)
    if not channel:
        return {"handled": False, "reason": "channel_not_found"}
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    context = _legacy._build_live_context(external_contact_id, phone)
    before = _legacy._serialize_member(
        member
        or _legacy._member_payload_from_context(None, {**context, "settings": _legacy.get_signup_conversion_config()}, in_pool=False)
    )
    current = _legacy._member_payload_from_context(
        member,
        {**context, "settings": _legacy.get_signup_conversion_config()},
        source_type=_legacy.SOURCE_TYPE_QRCODE,
        source_channel_id=int(channel["id"]),
        in_pool=True,
    )
    current["owner_staff_id"] = _legacy.DEFAULT_OWNER_STAFF_ID
    current["joined_at"] = current.get("joined_at") or _legacy._iso_now()
    if before["current_pool"] == _legacy.POOL_WON:
        saved = _legacy._persist_member(member, {**current, "in_pool": False, "current_pool": _legacy.POOL_WON})
        _legacy._write_event(
            member_id=int(saved["id"]),
            action="qrcode_enter",
            operator_type="system",
            operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_legacy._member_snapshot(before),
            after_snapshot=_legacy._member_snapshot(saved),
            remark="member already won; qrcode entry only recorded",
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
            "member": _legacy._serialize_member(saved),
            "won_kept": True,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
        }
    current["current_pool"] = _legacy.recompute_pool(
        current,
        {**context, "settings": _legacy.get_signup_conversion_config()},
        action="qrcode_enter",
    )
    saved = _legacy._persist_member(member, current)
    _legacy._write_event(
        member_id=int(saved["id"]),
        action="qrcode_enter",
        operator_type="system",
        operator_id=_legacy._normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_legacy._member_snapshot(before),
        after_snapshot=_legacy._member_snapshot(saved),
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
        "member": _legacy._serialize_member(saved),
        "welcome_message": welcome_result,
        "entry_tag": entry_tag_result,
    }


__all__ = [
    "_apply_channel_entry_tag",
    "_extract_channel_scene",
    "_extract_welcome_code",
    "_mutate_member",
    "_resolve_existing_member",
    "_send_channel_welcome_message",
    "apply_router_target_pool",
    "get_member_detail",
    "handle_qrcode_enter_from_callback",
    "mark_won",
    "put_in_pool",
    "remove_from_pool",
    "set_follow_type",
    "sync_member_activation",
    "sync_member_from_questionnaire_submission",
    "unmark_won",
]
