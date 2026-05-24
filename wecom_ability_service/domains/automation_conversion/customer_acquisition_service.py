from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import current_app

from ...db import get_db
from . import repo
from .member_state_service import handle_channel_enter_from_callback
from .service import (
    DEFAULT_OWNER_STAFF_ID,
    SOURCE_TYPE_WECOM_CUSTOMER_ACQUISITION,
    _normalized_text,
)

CUSTOMER_CHANNEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_INITIAL_AUDIENCE_CODE = "pending_questionnaire"
ALLOWED_INITIAL_AUDIENCE_CODES = {"pending_questionnaire", "operating", "converted"}


def _normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _config_flag_enabled(config: Mapping[str, Any]) -> bool:
    raw = config.get("WECOM_CUSTOMER_ACQUISITION_ENABLED", True)
    if isinstance(raw, bool):
        return raw
    return _normalized_text(raw).lower() not in {"0", "false", "no", "off", "disabled"}


def generate_customer_channel(*, corp_id: str = "", program_id: int | None = None, link_id: str = "") -> str:
    source = "|".join(
        [
            _normalized_text(corp_id),
            str(int(program_id or 0)),
            _normalized_text(link_id),
        ]
    )
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:20]
    prefix = f"wca_p{int(program_id or 0)}_"
    channel = f"{prefix}{digest}"
    if len(channel.encode("utf-8")) > 64:
        channel = f"wca_{digest}"
    if not CUSTOMER_CHANNEL_RE.match(channel) or len(channel.encode("utf-8")) > 64:
        raise ValueError("customer_channel generation failed")
    return channel


def build_customer_acquisition_final_url(link_url: str, customer_channel: str) -> str:
    normalized_url = _normalized_text(link_url)
    normalized_channel = _normalized_text(customer_channel)
    if not normalized_url:
        raise ValueError("link_url is required")
    if not CUSTOMER_CHANNEL_RE.match(normalized_channel):
        raise ValueError("invalid customer_channel")
    parts = urlsplit(normalized_url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "customer_channel"
    ]
    query_items.append(("customer_channel", normalized_channel))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _corp_id_from_config() -> str:
    return _normalized_text(current_app.config.get("WECOM_CORP_ID")) or "default"


def _initial_audience_code(payload: Mapping[str, Any]) -> str:
    code = _normalized_text(payload.get("initial_audience_code")) or DEFAULT_INITIAL_AUDIENCE_CODE
    if code not in ALLOWED_INITIAL_AUDIENCE_CODES:
        raise ValueError("invalid initial_audience_code")
    return code


def _owner_staff_id_from_link_payload(payload: Mapping[str, Any]) -> str:
    explicit_owner = _normalized_text(payload.get("owner_staff_id"))
    if explicit_owner:
        return explicit_owner
    range_user_list = payload.get("range_user_list") or []
    if isinstance(range_user_list, str):
        range_user_list = [item.strip() for item in range_user_list.split(",")]
    for item in list(range_user_list or []):
        if isinstance(item, Mapping):
            owner = _normalized_text(item.get("userid") or item.get("user_id") or item.get("id"))
        else:
            owner = _normalized_text(item)
        if owner:
            return owner
    return DEFAULT_OWNER_STAFF_ID


def create_customer_acquisition_link(payload: Mapping[str, Any]) -> dict[str, Any]:
    link_id = _normalized_text(payload.get("link_id"))
    link_url = _normalized_text(payload.get("link_url"))
    if not link_id:
        raise ValueError("link_id is required")
    if not link_url:
        raise ValueError("link_url is required")
    corp_id = _normalized_text(payload.get("corp_id")) or _corp_id_from_config()
    program_id = int(payload.get("program_id") or 0) or None
    workflow_id = int(payload.get("workflow_id") or 0) or None
    link_name = _normalized_text(payload.get("link_name")) or link_id
    initial_audience_code = _initial_audience_code(payload)
    owner_staff_id = _owner_staff_id_from_link_payload(payload)
    customer_channel = generate_customer_channel(corp_id=corp_id, program_id=program_id, link_id=link_id)
    final_url = build_customer_acquisition_final_url(link_url, customer_channel)

    db = get_db()
    try:
        channel = repo.save_channel(
            {
                "program_id": program_id,
                "channel_code": f"wecom_customer_acquisition_{customer_channel}",
                "channel_name": link_name,
                "channel_type": "wecom_customer_acquisition",
                "carrier_type": "link",
                "qr_url": final_url,
                "qr_ticket": link_id,
                "scene_value": customer_channel,
                "customer_channel": customer_channel,
                "link_url": link_url,
                "final_url": final_url,
                "welcome_message": "",
                "auto_accept_friend": False,
                "entry_tag_id": "",
                "entry_tag_name": "",
                "entry_tag_group_name": "",
                "owner_staff_id": owner_staff_id,
                "status": "active",
            }
        )
        link = repo.insert_customer_acquisition_link(
            {
                "corp_id": corp_id,
                "automation_channel_id": int(channel["id"]),
                "program_id": program_id,
                "workflow_id": workflow_id,
                "initial_audience_code": initial_audience_code,
                "link_id": link_id,
                "link_name": link_name,
                "link_url": link_url,
                "customer_channel": customer_channel,
                "final_url": final_url,
                "skip_verify": _normalized_bool(payload.get("skip_verify")),
                "range_user_list": payload.get("range_user_list") or [],
                "range_department_list": payload.get("range_department_list") or [],
                "priority_option": payload.get("priority_option") or {},
                "status": "active",
            }
        )
        if program_id:
            from .channel_binding_service import bind_channels_to_program

            bind_channels_to_program(
                int(program_id),
                [int(channel["id"])],
                {
                    "binding_status": "active",
                    "auto_enter_pool": True,
                    "initial_audience_code": initial_audience_code,
                    "entry_rule_json": {"source": "wecom_customer_acquisition_link"},
                },
                operator_id="wecom_customer_acquisition",
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"link": repo.get_customer_acquisition_link(int(link["id"])) or link, "channel": channel}


def list_customer_acquisition_links(*, status: str = "", program_id: int | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in repo.list_customer_acquisition_links(status=status, program_id=program_id)]


def set_customer_acquisition_link_enabled(link_row_id: int, *, enabled: bool) -> dict[str, Any]:
    status = "active" if enabled else "disabled"
    db = get_db()
    try:
        link = repo.update_customer_acquisition_link_status(int(link_row_id), status=status)
        if not link:
            raise LookupError("wecom customer acquisition link not found")
        repo.update_customer_acquisition_channel_status(int(link["automation_channel_id"]), status=status)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return repo.get_customer_acquisition_link(int(link_row_id)) or link


def _pick_event_field(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = _normalized_text(payload.get(name))
        if value:
            return value
    lower_payload = {str(key).lower(): value for key, value in payload.items()}
    for name in names:
        value = _normalized_text(lower_payload.get(name.lower()))
        if value:
            return value
    return ""


def normalize_customer_acquisition_event(payload: Mapping[str, Any]) -> dict[str, str]:
    event_payload = dict(payload or {})
    return {
        "event": _pick_event_field(event_payload, "Event", "event"),
        "change_type": _pick_event_field(event_payload, "ChangeType", "change_type"),
        "link_id": _pick_event_field(event_payload, "LinkId", "link_id"),
        "state": _pick_event_field(event_payload, "State", "state"),
        "follow_user_userid": _pick_event_field(event_payload, "UserID", "userid", "user_id"),
        "external_userid": _pick_event_field(
            event_payload,
            "ExternalUserID",
            "external_userid",
            "external_user_id",
        ),
        "chat_key": _pick_event_field(event_payload, "ChatKey", "chat_key"),
        "chat_status": _pick_event_field(event_payload, "ChatStatus", "chat_status"),
    }


def _lookup_customer_acquisition_link(*, corp_id: str, normalized_event: Mapping[str, str]) -> dict[str, Any] | None:
    state = _normalized_text(normalized_event.get("state"))
    link_id = _normalized_text(normalized_event.get("link_id"))
    if state:
        row = repo.find_customer_acquisition_link_by_channel(corp_id=corp_id, customer_channel=state)
        if row:
            return row
    if link_id:
        return repo.find_customer_acquisition_link_by_link_id(corp_id=corp_id, link_id=link_id)
    return None


def handle_customer_acquisition_event(
    *,
    corp_id: str,
    event_data: Mapping[str, Any],
    event_log_id: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_customer_acquisition_event(event_data)
    matched_link = _lookup_customer_acquisition_link(
        corp_id=_normalized_text(corp_id) or _corp_id_from_config(),
        normalized_event=normalized,
    )
    if not matched_link:
        return {
            "handled": False,
            "reason": "link_mapping_not_found",
            "event_log_id": int(event_log_id or 0),
            "event": normalized,
        }
    link_id = int(matched_link["id"])
    if _normalized_text(matched_link.get("status")) != "active" or _normalized_text(matched_link.get("channel_status")) != "active":
        repo.touch_customer_acquisition_link_event(link_id, last_error="link_or_channel_disabled")
        get_db().commit()
        return {"handled": False, "reason": "link_disabled", "link": matched_link, "event": normalized}
    external_userid = _normalized_text(normalized.get("external_userid"))
    follow_user_userid = _normalized_text(normalized.get("follow_user_userid"))
    if not external_userid or not follow_user_userid:
        repo.touch_customer_acquisition_link_event(link_id, last_error="missing_external_userid_or_userid")
        get_db().commit()
        return {"handled": False, "reason": "missing_external_userid_or_userid", "link": matched_link, "event": normalized}
    repo.touch_customer_acquisition_link_event(link_id, last_error="")
    get_db().commit()
    channel = repo.get_channel_by_id(int(matched_link["automation_channel_id"])) or {
        "id": matched_link["automation_channel_id"],
        "scene_value": matched_link.get("customer_channel"),
    }
    return handle_channel_enter_from_callback(
        external_contact_id=external_userid,
        phone="",
        payload_json=dict(event_data or {}),
        operator_id=follow_user_userid or "wecom_customer_acquisition",
        channel=channel,
        source_type=SOURCE_TYPE_WECOM_CUSTOMER_ACQUISITION,
        follow_user_userid=follow_user_userid,
        initial_audience_code=_normalized_text(matched_link.get("initial_audience_code")) or DEFAULT_INITIAL_AUDIENCE_CODE,
        event_action="customer_acquisition_enter",
        send_welcome_message=False,
    )


def build_customer_acquisition_preflight_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    enabled = _config_flag_enabled(config)
    secret_present = bool(_normalized_text(config.get("WECOM_CUSTOMER_ACQUISITION_SECRET")) or _normalized_text(config.get("WECOM_CONTACT_SECRET")))
    mapping_table_ok = False
    mapping_table_error = ""
    try:
        get_db().execute("SELECT 1 FROM wecom_customer_acquisition_links LIMIT 1").fetchone()
        mapping_table_ok = True
    except Exception as exc:
        mapping_table_error = str(exc)
        try:
            get_db().rollback()
        except Exception:
            pass
    handler_ok = callable(handle_customer_acquisition_event)
    configured = enabled and bool(_normalized_text(config.get("WECOM_CORP_ID"))) and secret_present
    payload = {
        "wecom_customer_acquisition_enabled": enabled,
        "wecom_customer_acquisition_configured": configured,
        "wecom_customer_acquisition_secret_present": secret_present,
        "wecom_customer_acquisition_mapping_table_ok": mapping_table_ok,
        "wecom_customer_acquisition_callback_handler_ok": handler_ok,
    }
    if mapping_table_error:
        payload["wecom_customer_acquisition_mapping_table_error"] = mapping_table_error
    return payload


__all__ = [
    "build_customer_acquisition_final_url",
    "build_customer_acquisition_preflight_payload",
    "create_customer_acquisition_link",
    "generate_customer_channel",
    "handle_customer_acquisition_event",
    "list_customer_acquisition_links",
    "normalize_customer_acquisition_event",
    "set_customer_acquisition_link_enabled",
]
