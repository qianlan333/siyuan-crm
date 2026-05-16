from __future__ import annotations

from typing import Any

from flask import current_app

from ...db import get_db
from ...infra.wecom_runtime import get_contact_runtime_client
from ...wecom_client import WeComClientError
from ..questionnaire.service import list_available_wecom_tags
from ..tags import repo as tags_repo
from . import repo
from .provider import load_channel_provider
from .service import (
    CHANNEL_STATUS_ACTIVE,
    CHANNEL_STATUS_CONFIGURED,
    DEFAULT_CHANNEL_CODE,
    DEFAULT_CHANNEL_NAME,
    DEFAULT_OWNER_STAFF_ID,
    _normalize_bool,
    _normalized_text,
    _program_default_channel_code,
)


def _channel_status_is_generated(status: str) -> bool:
    return _normalized_text(status) == CHANNEL_STATUS_ACTIVE


def _default_channel_field_statuses(
    *,
    provider: Any,
    channel_status: str,
    welcome_message: str,
    auto_accept_friend: bool,
    entry_tag_name: str,
) -> dict[str, dict[str, Any]]:
    support = (
        dict(provider.get_default_channel_field_support() or {})
        if provider is not None and hasattr(provider, "get_default_channel_field_support")
        else {}
    )
    welcome_supported = bool(support.get("welcome_message"))
    auto_accept_supported = bool(support.get("auto_accept_friend"))
    generated = _channel_status_is_generated(channel_status)

    if welcome_message:
        if welcome_supported:
            welcome_status = "applied" if generated else "pending"
            welcome_detail = (
                "欢迎语会在企微回调携带 welcome_code 时，通过官方 send_welcome_msg 自动发送。"
                if generated
                else "保存后需重新生成默认二维码，欢迎语能力才会绑定到当前默认渠道。"
            )
        else:
            welcome_status = "unsupported"
            welcome_detail = "当前默认永久二维码 provider 不支持欢迎语透传。"
    else:
        welcome_status = "not_set"
        welcome_detail = "当前未配置欢迎语。"

    if auto_accept_supported:
        if auto_accept_friend:
            auto_accept_status = "applied" if generated else "pending"
            auto_accept_detail = (
                "免验证直接添加好友已在最近一次生成时透传。"
                if generated
                else "保存后需重新生成默认二维码，免验证开关才会真正生效。"
            )
        else:
            auto_accept_status = "applied" if generated else "not_set"
            auto_accept_detail = (
                "当前默认二维码继续走好友验证。"
                if generated
                else "当前未开启免验证直接添加好友。"
            )
    else:
        auto_accept_status = "unsupported" if auto_accept_friend else "not_set"
        auto_accept_detail = (
            "当前 provider 不支持免验证直接添加好友。"
            if auto_accept_friend
            else "当前未开启免验证直接添加好友。"
        )

    if entry_tag_name:
        entry_tag_status = "applied"
        entry_tag_detail = "扫码回调命中当前渠道码后，会直接给客户打上这个标签。"
    else:
        entry_tag_status = "not_set"
        entry_tag_detail = "当前未配置扫码自动打标签。"

    return {
        "welcome_message": {
            "status": welcome_status,
            "supported": welcome_supported,
            "detail": welcome_detail,
        },
        "auto_accept_friend": {
            "status": auto_accept_status,
            "supported": auto_accept_supported,
            "detail": auto_accept_detail,
        },
        "entry_tag": {
            "status": entry_tag_status,
            "supported": True,
            "detail": entry_tag_detail,
        },
    }


def _resolve_channel_entry_tag_payload(
    *,
    entry_tag_id: Any,
    entry_tag_name: Any,
    entry_tag_group_name: Any,
) -> dict[str, str]:
    normalized_tag_id = _normalized_text(entry_tag_id)
    normalized_tag_name = _normalized_text(entry_tag_name)
    normalized_group_name = _normalized_text(entry_tag_group_name)
    if not normalized_tag_id and not normalized_tag_name and not normalized_group_name:
        return {
            "entry_tag_id": "",
            "entry_tag_name": "",
            "entry_tag_group_name": "",
        }
    live_tags = list_available_wecom_tags()
    matched_tag: dict[str, Any] | None = None
    if normalized_tag_id:
        matched_tag = next((item for item in live_tags if _normalized_text(item.get("tag_id")) == normalized_tag_id), None)
        if not matched_tag:
            raise ValueError("扫码自动打标签未找到对应的企微标签 ID")
    else:
        matched_tags = [
            item
            for item in live_tags
            if _normalized_text(item.get("tag_name")) == normalized_tag_name
            and (not normalized_group_name or _normalized_text(item.get("group_name")) == normalized_group_name)
        ]
        if not matched_tags:
            raise ValueError("扫码自动打标签未找到对应的企微标签")
        if len(matched_tags) > 1:
            raise ValueError("存在多个同名企微标签，请补充标签分组")
        matched_tag = matched_tags[0]
    return {
        "entry_tag_id": _normalized_text((matched_tag or {}).get("tag_id")),
        "entry_tag_name": _normalized_text((matched_tag or {}).get("tag_name")),
        "entry_tag_group_name": _normalized_text((matched_tag or {}).get("group_name")),
    }


def _effective_channel_entry_tag_payload(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, str]:
    if any(key in payload for key in ("entry_tag_id", "entry_tag_name", "entry_tag_group_name")):
        return _resolve_channel_entry_tag_payload(
            entry_tag_id=payload.get("entry_tag_id"),
            entry_tag_name=payload.get("entry_tag_name"),
            entry_tag_group_name=payload.get("entry_tag_group_name"),
        )
    return {
        "entry_tag_id": _normalized_text(existing.get("entry_tag_id")),
        "entry_tag_name": _normalized_text(existing.get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(existing.get("entry_tag_group_name")),
    }


def _allow_legacy_channel_fallback(program_id: int | None) -> bool:
    if program_id is None:
        return True
    try:
        from .program_service import get_default_automation_program_id

        return int(program_id) == int(get_default_automation_program_id())
    except Exception:
        return False



def get_default_channel_settings_payload(*, program_id: int | None = None) -> dict[str, Any]:
    normalized_program_id = int(program_id or 0) or None
    if normalized_program_id is not None and not _allow_legacy_channel_fallback(normalized_program_id):
        provider = load_channel_provider()
        return {
            "default_channel": repo.get_default_channel(
                program_id=normalized_program_id,
                allow_legacy_fallback=False,
            )
            or {},
            "provider_available": bool(provider),
        }
    from .service import get_settings_payload

    payload = get_settings_payload(program_id=normalized_program_id)
    return {
        "default_channel": dict(payload.get("default_channel") or {}),
        "provider_available": bool(payload.get("provider_available")),
    }


def save_default_channel_settings(payload: dict[str, Any], *, program_id: int | None = None) -> dict[str, Any]:
    normalized_program_id = int(program_id or payload.get("program_id") or 0) or None
    existing = repo.get_default_channel(
        program_id=normalized_program_id,
        allow_legacy_fallback=_allow_legacy_channel_fallback(normalized_program_id),
    ) or {}
    entry_tag_payload = _effective_channel_entry_tag_payload(payload, existing)
    next_channel_name = _normalized_text(payload.get("channel_name")) or _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    next_welcome_message = (
        _normalized_text(payload.get("welcome_message"))
        if "welcome_message" in payload
        else _normalized_text(existing.get("welcome_message"))
    )
    next_auto_accept_friend = (
        _normalize_bool(payload.get("auto_accept_friend"))
        if "auto_accept_friend" in payload
        else _normalize_bool(existing.get("auto_accept_friend"))
    )
    next_owner_staff_id = (
        _normalized_text(payload.get("owner_staff_id"))
        or _normalized_text(existing.get("owner_staff_id"))
        or DEFAULT_OWNER_STAFF_ID
    )
    current_channel_name = _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    current_welcome_message = _normalized_text(existing.get("welcome_message"))
    current_auto_accept_friend = _normalize_bool(existing.get("auto_accept_friend"))
    channel_settings_changed = (
        next_channel_name != current_channel_name
        or next_welcome_message != current_welcome_message
        or next_auto_accept_friend != current_auto_accept_friend
        or entry_tag_payload["entry_tag_id"] != _normalized_text(existing.get("entry_tag_id"))
        or entry_tag_payload["entry_tag_name"] != _normalized_text(existing.get("entry_tag_name"))
        or entry_tag_payload["entry_tag_group_name"] != _normalized_text(existing.get("entry_tag_group_name"))
    )
    repo.save_channel(
        {
            "program_id": normalized_program_id,
            "channel_code": _program_default_channel_code(normalized_program_id),
            "channel_name": next_channel_name,
            "qr_url": _normalized_text(payload.get("qr_url")) or _normalized_text(existing.get("qr_url")),
            "qr_ticket": _normalized_text(payload.get("qr_ticket")) or _normalized_text(existing.get("qr_ticket")),
            "scene_value": _normalized_text(payload.get("scene_value")) or _normalized_text(existing.get("scene_value")),
            "welcome_message": next_welcome_message,
            "auto_accept_friend": next_auto_accept_friend,
            "entry_tag_id": entry_tag_payload["entry_tag_id"],
            "entry_tag_name": entry_tag_payload["entry_tag_name"],
            "entry_tag_group_name": entry_tag_payload["entry_tag_group_name"],
            "owner_staff_id": next_owner_staff_id,
            "status": (
                CHANNEL_STATUS_CONFIGURED
                if channel_settings_changed
                else (_normalized_text(payload.get("channel_status")) or _normalized_text(existing.get("status")) or CHANNEL_STATUS_CONFIGURED)
            ),
        }
    )
    get_db().commit()
    return get_default_channel_settings_payload(program_id=normalized_program_id)



def generate_default_channel_qr(*, operator: str = "", program_id: int | None = None) -> dict[str, Any]:
    provider = load_channel_provider()
    normalized_program_id = int(program_id or 0) or None
    existing = repo.get_default_channel(
        program_id=normalized_program_id,
        allow_legacy_fallback=_allow_legacy_channel_fallback(normalized_program_id),
    ) or {}
    if provider is None:
        return {
            "generated": False,
            "provider_available": False,
            "channel": existing,
            "error": "二维码 provider 未接入，当前仓库无法生成真实企微渠道二维码",
            "operator": _normalized_text(operator),
            "status_code": 501,
            "error_code": "provider_missing",
        }
    welcome_message = _normalized_text(existing.get("welcome_message"))
    auto_accept_friend = _normalize_bool(existing.get("auto_accept_friend"))
    entry_tag_id = _normalized_text(existing.get("entry_tag_id"))
    entry_tag_name = _normalized_text(existing.get("entry_tag_name"))
    entry_tag_group_name = _normalized_text(existing.get("entry_tag_group_name"))
    owner_staff_id = _normalized_text(existing.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID
    try:
        channel_payload = provider.create_default_channel(
            owner_staff_id=owner_staff_id,
            welcome_message=welcome_message,
            auto_accept_friend=auto_accept_friend,
        )
    except ValueError as exc:
        saved = repo.save_channel(
            {
                "channel_code": _normalized_text(existing.get("channel_code")) or DEFAULT_CHANNEL_CODE,
                "program_id": normalized_program_id,
                "channel_name": _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
                "qr_url": _normalized_text(existing.get("qr_url")),
                "qr_ticket": _normalized_text(existing.get("qr_ticket")),
                "scene_value": _normalized_text(existing.get("scene_value")),
                "welcome_message": welcome_message,
                "auto_accept_friend": auto_accept_friend,
                "entry_tag_id": entry_tag_id,
                "entry_tag_name": entry_tag_name,
                "entry_tag_group_name": entry_tag_group_name,
                "owner_staff_id": owner_staff_id,
                "status": "generation_failed",
            }
        )
        get_db().commit()
        return {
            "generated": False,
            "provider_available": True,
            "channel": saved,
            "error": str(exc),
            "operator": _normalized_text(operator),
            "status_code": 400,
            "error_code": "invalid_state",
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(saved.get("status")) or "generation_failed",
                welcome_message=welcome_message,
                auto_accept_friend=auto_accept_friend,
                entry_tag_name=entry_tag_name,
            ),
        }
    except WeComClientError as exc:
        saved = repo.save_channel(
            {
                "channel_code": _normalized_text(existing.get("channel_code")) or DEFAULT_CHANNEL_CODE,
                "program_id": normalized_program_id,
                "channel_name": _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
                "qr_url": _normalized_text(existing.get("qr_url")),
                "qr_ticket": _normalized_text(existing.get("qr_ticket")),
                "scene_value": _normalized_text(existing.get("scene_value")),
                "welcome_message": welcome_message,
                "auto_accept_friend": auto_accept_friend,
                "entry_tag_id": entry_tag_id,
                "entry_tag_name": entry_tag_name,
                "entry_tag_group_name": entry_tag_group_name,
                "owner_staff_id": owner_staff_id,
                "status": "config_incomplete" if "not configured" in str(exc).lower() else "generation_failed",
            }
        )
        get_db().commit()
        return {
            "generated": False,
            "provider_available": True,
            "channel": saved,
            "error": str(exc),
            "operator": _normalized_text(operator),
            "status_code": 400 if "not configured" in str(exc).lower() else 502,
            "error_code": (
                "config_incomplete"
                if "not configured" in str(exc).lower()
                else (_normalized_text(exc.category) or "generation_failed")
            ),
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(saved.get("status")) or "generation_failed",
                welcome_message=welcome_message,
                auto_accept_friend=auto_accept_friend,
                entry_tag_name=entry_tag_name,
            ),
        }
    saved = repo.save_channel(
        {
            "program_id": normalized_program_id,
            "channel_code": _program_default_channel_code(normalized_program_id),
            "channel_name": _normalized_text(channel_payload.get("channel_name")) or DEFAULT_CHANNEL_NAME,
            "qr_url": _normalized_text(channel_payload.get("qr_url")),
            "qr_ticket": _normalized_text(channel_payload.get("qr_ticket")),
            "scene_value": _normalized_text(channel_payload.get("scene_value")),
            "welcome_message": welcome_message,
            "auto_accept_friend": auto_accept_friend,
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
            "owner_staff_id": owner_staff_id,
            "status": _normalized_text(channel_payload.get("status")) or CHANNEL_STATUS_ACTIVE,
        }
    )
    get_db().commit()
    return {
        "generated": True,
        "provider_available": True,
        "channel": saved,
        "field_statuses": (
            dict(channel_payload.get("field_statuses") or {})
            or _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(saved.get("status")) or CHANNEL_STATUS_ACTIVE,
                welcome_message=welcome_message,
                auto_accept_friend=auto_accept_friend,
                entry_tag_name=entry_tag_name,
            )
        ),
    }
