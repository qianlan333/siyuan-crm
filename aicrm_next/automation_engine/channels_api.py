from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from aicrm_next.common_operation_members import search_operation_members
from aicrm_next.channel_entry import repo as channel_entry_repo
from aicrm_next.shared.runtime import raw_database_url

router = APIRouter()

_FIXTURE_CHANNELS: dict[int, dict[str, Any]] = {}
_FIXTURE_PROGRAM_BINDINGS: dict[int, dict[str, Any]] = {}
_NEXT_ID = 1
_NEXT_BINDING_ID = 1


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _connect():
    database_url = _psycopg_url(raw_database_url())
    if not database_url.startswith(("postgresql://", "postgres://")):
        return None
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(database_url, row_factory=dict_row)


def _iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_list(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        try:
            source = json.loads(value)
        except ValueError:
            source = []
    else:
        source = []
    result: list[int] = []
    for item in source:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in result:
            result.append(item_id)
    return result[:9]


def _json_text_list(value: Any, *, max_count: int = 12) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        try:
            source = json.loads(value)
        except ValueError:
            source = [part.strip() for part in value.split(",")]
    else:
        source = []
    result: list[str] = []
    for item in source:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result[:max_count]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _text(value).lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _channel_type(payload: dict[str, Any]) -> tuple[str, str]:
    channel_type = _text(payload.get("channel_type")) or "qrcode"
    carrier_type = _text(payload.get("carrier_type")) or ("link" if channel_type == "wecom_customer_acquisition" else "qrcode")
    if channel_type == "wecom_customer_acquisition" or carrier_type == "link":
        return "wecom_customer_acquisition", "link"
    return "qrcode", "qrcode"


def _serialize_channel(row: dict[str, Any]) -> dict[str, Any]:
    channel = dict(row)
    channel_type, carrier_type = _channel_type(channel)
    channel["id"] = int(channel.get("id") or 0)
    channel["channel_type"] = channel_type
    channel["carrier_type"] = carrier_type
    channel["channel_code"] = _text(channel.get("channel_code"))
    channel["channel_name"] = _text(channel.get("channel_name"))
    channel["scene_value"] = _text(channel.get("scene_value"))
    channel["historical_scene_values"] = [
        item for item in _json_text_list(channel.get("historical_scene_values")) if item != channel["scene_value"]
    ]
    channel["qr_url"] = _text(channel.get("qr_url"))
    channel["customer_channel"] = _text(channel.get("customer_channel"))
    channel["link_url"] = _text(channel.get("link_url"))
    channel["final_url"] = _text(channel.get("final_url"))
    if carrier_type == "link":
        channel["customer_channel"] = channel["customer_channel"] or _text(channel.get("wca_customer_channel"))
        channel["link_url"] = channel["link_url"] or _text(channel.get("wca_link_url"))
        channel["final_url"] = channel["final_url"] or _text(channel.get("wca_final_url"))
    channel["share_url"] = channel.get("share_url") or channel["final_url"] or channel["link_url"]
    channel["copy_text"] = channel.get("copy_text") or channel["share_url"] or channel["qr_url"]
    channel["welcome_message"] = _text(channel.get("welcome_message"))
    channel["welcome_image_library_ids"] = _json_list(channel.get("welcome_image_library_ids"))
    channel["welcome_miniprogram_library_ids"] = _json_list(channel.get("welcome_miniprogram_library_ids"))
    channel["welcome_attachment_library_ids"] = _json_list(channel.get("welcome_attachment_library_ids"))
    channel["welcome_attachment_count"] = len(channel["welcome_image_library_ids"]) + len(channel["welcome_miniprogram_library_ids"]) + len(channel["welcome_attachment_library_ids"])
    channel["welcome_message_configured"] = bool(channel["welcome_message"])
    channel["auto_accept_friend"] = bool(channel.get("auto_accept_friend", False))
    channel["entry_tag_id"] = _text(channel.get("entry_tag_id"))
    channel["entry_tag_name"] = _text(channel.get("entry_tag_name"))
    channel["entry_tag_group_name"] = _text(channel.get("entry_tag_group_name"))
    channel["entry_tag_configured"] = bool(channel["entry_tag_id"] or channel["entry_tag_name"])
    channel["status"] = _text(channel.get("status")) or "active"
    channel["owner_staff_id"] = _text(channel.get("owner_staff_id"))
    channel["channel_contact_count"] = int(channel.get("channel_contact_count") or 0)
    channel["latest_channel_entered_at"] = _iso(channel.get("latest_channel_entered_at"))
    channel["bound_program_name"] = _text(channel.get("bound_program_name"))
    channel["qr_download_url"] = f"/api/admin/channels/{channel['id']}/qrcode/download" if carrier_type != "link" and channel["id"] else ""
    channel["qrcode_status"] = _text(channel.get("qrcode_status")) or ("legacy_untracked" if channel["qr_url"] and channel["scene_value"] else "not_generated")
    channel["qrcode_asset_id"] = int(channel.get("qrcode_asset_id") or channel.get("active_qrcode_asset_id") or 0)
    channel["created_at"] = _iso(channel.get("created_at"))
    channel["updated_at"] = _iso(channel.get("updated_at"))
    return channel


def _serialize_program_binding(row: dict[str, Any]) -> dict[str, Any]:
    binding = {
        "id": int(row.get("id") or row.get("binding_id") or 0),
        "program_id": int(row.get("program_id") or 0),
        "channel_id": int(row.get("channel_id") or 0),
        "binding_status": _text(row.get("binding_status")) or "active",
        "auto_enter_pool": bool(row.get("auto_enter_pool", True)),
        "initial_audience_code": _text(row.get("initial_audience_code")) or "pending_questionnaire",
        "priority": int(row.get("priority") or 0),
        "bound_at": _iso(row.get("bound_at")),
        "unbound_at": _iso(row.get("unbound_at")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }
    channel = {
        "id": binding["channel_id"],
        "channel_code": row.get("channel_code"),
        "channel_name": row.get("channel_name"),
        "channel_type": row.get("channel_type"),
        "carrier_type": row.get("carrier_type"),
        "scene_value": row.get("scene_value"),
        "qr_url": row.get("qr_url"),
        "customer_channel": row.get("customer_channel") or row.get("wca_customer_channel"),
        "link_url": row.get("link_url") or row.get("wca_link_url"),
        "final_url": row.get("final_url") or row.get("wca_final_url"),
        "status": row.get("channel_status") or row.get("status"),
        "owner_staff_id": row.get("owner_staff_id"),
        "auto_accept_friend": row.get("auto_accept_friend"),
        "entry_tag_id": row.get("entry_tag_id"),
        "entry_tag_name": row.get("entry_tag_name"),
        "entry_tag_group_name": row.get("entry_tag_group_name"),
        "updated_at": row.get("channel_updated_at") or row.get("updated_at"),
        "created_at": row.get("channel_created_at") or row.get("created_at"),
    }
    binding["channel"] = _serialize_channel(channel)
    return binding


def _default_channel() -> dict[str, Any]:
    return {
        "channel_type": "qrcode",
        "carrier_type": "qrcode",
        "status": "active",
        "welcome_image_library_ids": [],
        "welcome_miniprogram_library_ids": [],
        "welcome_attachment_library_ids": [],
        "auto_accept_friend": False,
    }


def get_channel_resource(channel_id: int) -> dict[str, Any] | None:
    conn = _connect()
    if conn is None:
        channel = _FIXTURE_CHANNELS.get(int(channel_id))
        return _serialize_channel(channel) if channel else None
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*,
                       active_asset.id AS active_qrcode_asset_id,
                       active_asset.status AS qrcode_status,
                       COALESCE(contact_stats.channel_contact_count, 0) AS channel_contact_count,
                       contact_stats.latest_channel_entered_at,
                       binding.program_name AS bound_program_name,
                       wca.customer_channel AS wca_customer_channel,
                       wca.link_url AS wca_link_url,
                       wca.final_url AS wca_final_url,
                       COALESCE(historical_scenes.historical_scene_values, '[]'::jsonb) AS historical_scene_values
                FROM automation_channel c
                LEFT JOIN LATERAL (
                    SELECT id, status
                    FROM automation_channel_qrcode_asset qa
                    WHERE qa.channel_id = c.id
                      AND qa.status = 'active'
                    ORDER BY qa.generated_at DESC, qa.id DESC
                    LIMIT 1
                ) active_asset ON TRUE
                LEFT JOIN (
                    SELECT channel_id, count(*) AS channel_contact_count, max(last_channel_entered_at) AS latest_channel_entered_at
                    FROM automation_channel_contact
                    GROUP BY channel_id
                ) contact_stats ON contact_stats.channel_id = c.id
                LEFT JOIN (
                    SELECT DISTINCT ON (b.channel_id)
                           b.channel_id, p.program_name
                    FROM automation_program_channel_binding b
                    LEFT JOIN automation_program p ON p.id = b.program_id
                    WHERE b.binding_status = 'active'
                    ORDER BY b.channel_id, b.priority DESC, b.id DESC
                ) binding ON binding.channel_id = c.id
                LEFT JOIN wecom_customer_acquisition_links wca
                  ON wca.automation_channel_id = c.id AND wca.status = 'active'
                LEFT JOIN LATERAL (
                    SELECT jsonb_agg(a.scene_value ORDER BY a.updated_at DESC, a.id DESC) AS historical_scene_values
                    FROM automation_channel_scene_alias a
                    WHERE a.channel_id = c.id
                      AND a.scene_value <> c.scene_value
                      AND a.status <> 'revoked'
                    LIMIT 12
                ) historical_scenes ON TRUE
                WHERE c.id = %s
                """,
                (int(channel_id),),
            )
            row = cur.fetchone()
    return _serialize_channel(dict(row)) if row else None


def _list_channels_from_postgres(*, limit: int, status: str = "", available_for_program_id: int | None = None) -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        channels = [_serialize_channel(item) for item in _FIXTURE_CHANNELS.values()]
        if status:
            channels = [item for item in channels if item.get("status") == status]
        if int(available_for_program_id or 0) > 0:
            active_channel_ids = {
                int(item.get("channel_id") or 0)
                for item in _FIXTURE_PROGRAM_BINDINGS.values()
                if _text(item.get("binding_status")) == "active"
            }
            channels = [item for item in channels if int(item.get("id") or 0) not in active_channel_ids]
        return sorted(channels, key=lambda item: int(item.get("id") or 0), reverse=True)[:limit]
    params: list[Any] = []
    where = ""
    if status:
        where = "WHERE c.status = %s"
        params.append(status)
    if int(available_for_program_id or 0) > 0:
        where = where + (" AND " if where else "WHERE ")
        where += """
            NOT EXISTS (
                SELECT 1
                FROM automation_program_channel_binding active_b
                WHERE active_b.channel_id = c.id
                  AND active_b.binding_status = 'active'
            )
        """
    params.append(limit)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.*,
                       active_asset.id AS active_qrcode_asset_id,
                       active_asset.status AS qrcode_status,
                       COALESCE(contact_stats.channel_contact_count, 0) AS channel_contact_count,
                       contact_stats.latest_channel_entered_at,
                       binding.program_name AS bound_program_name,
                       wca.customer_channel AS wca_customer_channel,
                       wca.link_url AS wca_link_url,
                       wca.final_url AS wca_final_url,
                       COALESCE(historical_scenes.historical_scene_values, '[]'::jsonb) AS historical_scene_values
                FROM automation_channel c
                LEFT JOIN LATERAL (
                    SELECT id, status
                    FROM automation_channel_qrcode_asset qa
                    WHERE qa.channel_id = c.id
                      AND qa.status = 'active'
                    ORDER BY qa.generated_at DESC, qa.id DESC
                    LIMIT 1
                ) active_asset ON TRUE
                LEFT JOIN (
                    SELECT channel_id, count(*) AS channel_contact_count, max(last_channel_entered_at) AS latest_channel_entered_at
                    FROM automation_channel_contact
                    GROUP BY channel_id
                ) contact_stats ON contact_stats.channel_id = c.id
                LEFT JOIN (
                    SELECT DISTINCT ON (b.channel_id)
                           b.channel_id, p.program_name
                    FROM automation_program_channel_binding b
                    LEFT JOIN automation_program p ON p.id = b.program_id
                    WHERE b.binding_status = 'active'
                    ORDER BY b.channel_id, b.priority DESC, b.id DESC
                ) binding ON binding.channel_id = c.id
                LEFT JOIN wecom_customer_acquisition_links wca
                  ON wca.automation_channel_id = c.id AND wca.status = 'active'
                LEFT JOIN LATERAL (
                    SELECT jsonb_agg(a.scene_value ORDER BY a.updated_at DESC, a.id DESC) AS historical_scene_values
                    FROM automation_channel_scene_alias a
                    WHERE a.channel_id = c.id
                      AND a.scene_value <> c.scene_value
                      AND a.status <> 'revoked'
                    LIMIT 12
                ) historical_scenes ON TRUE
                {where}
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [_serialize_channel(dict(row)) for row in cur.fetchall() or []]


def list_program_channel_bindings_resource(program_id: int) -> list[dict[str, Any]]:
    conn = _connect()
    if conn is None:
        bindings = [
            _serialize_program_binding({**(_FIXTURE_CHANNELS.get(int(binding.get("channel_id") or 0), {})), **binding})
            for binding in _FIXTURE_PROGRAM_BINDINGS.values()
            if int(binding.get("program_id") or 0) == int(program_id) and _text(binding.get("binding_status")) != "archived"
        ]
        return sorted(bindings, key=lambda item: (int(item.get("priority") or 0), int(item.get("id") or 0)), reverse=True)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    b.id,
                    b.program_id,
                    b.channel_id,
                    b.binding_status,
                    b.auto_enter_pool,
                    b.initial_audience_code,
                    b.priority,
                    b.bound_at,
                    b.unbound_at,
                    b.created_at,
                    b.updated_at,
                    c.channel_code,
                    c.channel_name,
                    c.channel_type,
                    c.carrier_type,
                    c.scene_value,
                    c.qr_url,
                    c.customer_channel,
                    c.link_url,
                    c.final_url,
                    c.status AS channel_status,
                    c.owner_staff_id,
                    c.auto_accept_friend,
                    c.entry_tag_id,
                    c.entry_tag_name,
                    c.entry_tag_group_name,
                    c.updated_at AS channel_updated_at,
                    c.created_at AS channel_created_at,
                    wca.customer_channel AS wca_customer_channel,
                    wca.link_url AS wca_link_url,
                    wca.final_url AS wca_final_url
                FROM automation_program_channel_binding b
                JOIN automation_channel c ON c.id = b.channel_id
                LEFT JOIN wecom_customer_acquisition_links wca
                  ON wca.automation_channel_id = c.id AND wca.status = 'active'
                WHERE b.program_id = %s
                  AND b.binding_status <> 'archived'
                ORDER BY b.priority DESC, b.id DESC
                """,
                (int(program_id),),
            )
            return [_serialize_program_binding(dict(row)) for row in cur.fetchall() or []]


def list_program_entry_candidate_channels(program_id: int) -> list[dict[str, Any]]:
    return _list_channels_from_postgres(limit=200, status="", available_for_program_id=int(program_id))


def bind_channels_to_program_resource(program_id: int, channel_ids: list[int], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _NEXT_BINDING_ID
    normalized_ids: list[int] = []
    for item in channel_ids:
        channel_id = int(item or 0)
        if channel_id > 0 and channel_id not in normalized_ids:
            normalized_ids.append(channel_id)
    if not normalized_ids:
        raise ValueError("channel_ids_required")
    payload = payload or {}
    initial_audience_code = _text(payload.get("initial_audience_code")) or "pending_questionnaire"
    if initial_audience_code not in {"pending_questionnaire", "operating", "converted"}:
        raise ValueError("invalid_initial_audience_code")
    priority = int(payload.get("priority") or 0)
    conn = _connect()
    if conn is None:
        now = datetime.now(timezone.utc).isoformat()
        for channel_id in normalized_ids:
            if channel_id not in _FIXTURE_CHANNELS:
                raise LookupError("channel_not_found")
            active_conflict = next(
                (
                    item
                    for item in _FIXTURE_PROGRAM_BINDINGS.values()
                    if int(item.get("channel_id") or 0) == channel_id
                    and int(item.get("program_id") or 0) != int(program_id)
                    and _text(item.get("binding_status")) == "active"
                ),
                None,
            )
            if active_conflict:
                raise ValueError("channel_already_bound")
            existing_id = next(
                (
                    binding_id
                    for binding_id, item in _FIXTURE_PROGRAM_BINDINGS.items()
                    if int(item.get("program_id") or 0) == int(program_id) and int(item.get("channel_id") or 0) == channel_id
                ),
                None,
            )
            binding_id = int(existing_id or _NEXT_BINDING_ID)
            if existing_id is None:
                _NEXT_BINDING_ID += 1
            _FIXTURE_PROGRAM_BINDINGS[binding_id] = {
                "id": binding_id,
                "program_id": int(program_id),
                "channel_id": channel_id,
                "binding_status": "active",
                "auto_enter_pool": True,
                "initial_audience_code": initial_audience_code,
                "priority": priority,
                "bound_at": now,
                "created_at": now,
                "updated_at": now,
            }
        return {"bindings": list_program_channel_bindings_resource(int(program_id)), "reason": "program_channels_bound"}
    from psycopg.types.json import Jsonb

    with conn:
        with conn.cursor() as cur:
            for channel_id in normalized_ids:
                cur.execute("SELECT id FROM automation_channel WHERE id = %s LIMIT 1", (channel_id,))
                if not cur.fetchone():
                    raise LookupError("channel_not_found")
                cur.execute(
                    """
                    SELECT id
                    FROM automation_program_channel_binding
                    WHERE channel_id = %s
                      AND binding_status = 'active'
                      AND program_id <> %s
                    LIMIT 1
                    """,
                    (channel_id, int(program_id)),
                )
                if cur.fetchone():
                    raise ValueError("channel_already_bound")
                cur.execute(
                    """
                    INSERT INTO automation_program_channel_binding (
                        program_id,
                        channel_id,
                        binding_status,
                        auto_enter_pool,
                        initial_audience_code,
                        entry_rule_json,
                        priority,
                        bound_by
                    )
                    VALUES (%s, %s, 'active', TRUE, %s, %s, %s, %s)
                    ON CONFLICT (program_id, channel_id)
                    DO UPDATE SET
                        binding_status = 'active',
                        auto_enter_pool = TRUE,
                        initial_audience_code = EXCLUDED.initial_audience_code,
                        entry_rule_json = EXCLUDED.entry_rule_json,
                        priority = EXCLUDED.priority,
                        bound_by = EXCLUDED.bound_by,
                        bound_at = CASE
                            WHEN automation_program_channel_binding.binding_status <> 'active'
                            THEN CURRENT_TIMESTAMP
                            ELSE automation_program_channel_binding.bound_at
                        END,
                        unbound_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        int(program_id),
                        channel_id,
                        initial_audience_code,
                        Jsonb(dict(payload.get("entry_rule_json") or {})),
                        priority,
                        _text(payload.get("operator_id") or payload.get("bound_by")) or "next_admin",
                    ),
                )
        conn.commit()
    return {"bindings": list_program_channel_bindings_resource(int(program_id)), "reason": "program_channels_bound"}


def archive_program_channel_binding_resource(program_id: int, binding_id: int) -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        binding = _FIXTURE_PROGRAM_BINDINGS.get(int(binding_id))
        if not binding or int(binding.get("program_id") or 0) != int(program_id):
            raise LookupError("binding_not_found")
        binding["binding_status"] = "archived"
        binding["unbound_at"] = datetime.now(timezone.utc).isoformat()
        binding["updated_at"] = binding["unbound_at"]
        return {"binding": _serialize_program_binding({**(_FIXTURE_CHANNELS.get(int(binding.get("channel_id") or 0), {})), **binding}), "reason": "program_channel_unbound"}
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE automation_program_channel_binding
                SET binding_status = 'archived',
                    unbound_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND program_id = %s
                RETURNING id
                """,
                (int(binding_id), int(program_id)),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise LookupError("binding_not_found")
    return {"binding_id": int(binding_id), "reason": "program_channel_unbound"}


def _coerce_channel_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    channel_type, carrier_type = _channel_type(payload)
    existing = existing or {}
    customer_channel = _text(payload.get("customer_channel") or payload.get("scene_value"))
    channel_code = _text(payload.get("channel_code")) or _text(existing.get("channel_code"))
    if carrier_type != "link" and _text(payload.get("scene_value")) and _text(payload.get("scene_value")) != _text(existing.get("scene_value")):
        raise ValueError("scene_value_is_system_managed")
    if carrier_type != "link" and _text(payload.get("qr_url")) and _text(payload.get("qr_url")) != _text(existing.get("qr_url")):
        raise ValueError("qr_url_is_system_managed")
    scene_value = customer_channel if carrier_type == "link" else _text(existing.get("scene_value"))
    qr_url = _text(existing.get("qr_url")) if carrier_type != "link" else _text(payload.get("qr_url") or existing.get("qr_url"))
    final_url = _text(payload.get("final_url"))
    link_url = _text(payload.get("link_url"))
    if carrier_type == "link" and link_url and customer_channel and not final_url:
        separator = "&" if "?" in link_url else "?"
        final_url = f"{link_url}{separator}customer_channel={customer_channel}"
    return {
        "channel_type": channel_type,
        "carrier_type": carrier_type,
        "channel_name": _text(payload.get("channel_name")) or _text(existing.get("channel_name")) or channel_code or "未命名渠道",
        "channel_code": channel_code,
        "scene_value": scene_value,
        "qr_url": qr_url,
        "status": _text(payload.get("status")) or _text(existing.get("status")) or "active",
        "owner_staff_id": _text(payload.get("owner_staff_id") or existing.get("owner_staff_id")),
        "customer_channel": customer_channel if carrier_type == "link" else "",
        "link_url": link_url if carrier_type == "link" else "",
        "final_url": final_url if carrier_type == "link" else "",
        "welcome_message": _text(payload.get("welcome_message")),
        "welcome_image_library_ids": _json_list(payload.get("welcome_image_library_ids")),
        "welcome_miniprogram_library_ids": _json_list(payload.get("welcome_miniprogram_library_ids")),
        "welcome_attachment_library_ids": _json_list(payload.get("welcome_attachment_library_ids")),
        "auto_accept_friend": _bool(payload.get("auto_accept_friend"), default=_bool(existing.get("auto_accept_friend"))),
        "entry_tag_id": _text(payload.get("entry_tag_id")),
        "entry_tag_name": _text(payload.get("entry_tag_name")),
        "entry_tag_group_name": _text(payload.get("entry_tag_group_name")),
    }


def _save_fixture_channel(payload: dict[str, Any], channel_id: int | None = None) -> dict[str, Any]:
    global _NEXT_ID
    existing = _FIXTURE_CHANNELS.get(int(channel_id or 0), {}) if channel_id else {}
    data = _coerce_channel_payload(payload, existing=existing)
    if channel_id is None:
        channel_id = _NEXT_ID
        _NEXT_ID += 1
    now = datetime.now(timezone.utc).isoformat()
    channel = {**existing, **data, "id": int(channel_id), "updated_at": now, "created_at": existing.get("created_at") or now}
    _FIXTURE_CHANNELS[int(channel_id)] = channel
    return _serialize_channel(channel)


def _save_postgres_channel(payload: dict[str, Any], channel_id: int | None = None) -> dict[str, Any]:
    existing = get_channel_resource(int(channel_id)) if channel_id else None
    if channel_id and not existing:
        raise LookupError("channel_not_found")
    data = _coerce_channel_payload(payload, existing=existing)
    conn = _connect()
    if conn is None:
        return _save_fixture_channel(payload, channel_id)
    from psycopg.types.json import Jsonb

    columns = [
        "channel_type",
        "carrier_type",
        "channel_name",
        "channel_code",
        "scene_value",
        "qr_url",
        "status",
        "owner_staff_id",
        "customer_channel",
        "link_url",
        "final_url",
        "welcome_message",
        "welcome_image_library_ids",
        "welcome_miniprogram_library_ids",
        "welcome_attachment_library_ids",
        "auto_accept_friend",
        "entry_tag_id",
        "entry_tag_name",
        "entry_tag_group_name",
    ]
    values = [Jsonb(data[key]) if key.endswith("_ids") else data[key] for key in columns]
    owner_changed = bool(channel_id and _text((existing or {}).get("owner_staff_id")) and _text(data.get("owner_staff_id")) and _text((existing or {}).get("owner_staff_id")) != _text(data.get("owner_staff_id")))
    with conn:
        with conn.cursor() as cur:
            if channel_id:
                assignments = ", ".join(f"{column} = %s" for column in columns)
                cur.execute(
                    f"UPDATE automation_channel SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING id",
                    tuple(values + [int(channel_id)]),
                )
                saved_id = int((cur.fetchone() or {}).get("id") or channel_id)
            else:
                placeholders = ", ".join(["%s"] * len(columns))
                cur.execute(
                    f"INSERT INTO automation_channel ({', '.join(columns)}) VALUES ({placeholders}) RETURNING id",
                    tuple(values),
                )
                saved_id = int((cur.fetchone() or {}).get("id") or 0)
        conn.commit()
    if owner_changed:
        channel_entry_repo.mark_qrcode_asset_stale(saved_id, reason="owner_staff_id_changed")
    return get_channel_resource(saved_id) or {"id": saved_id, **data}


def get_channel_qrcode_status_resource(channel_id: int) -> dict[str, Any]:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise LookupError("channel_not_found")
    if channel.get("carrier_type") == "link" or channel.get("channel_type") == "wecom_customer_acquisition":
        return {"channel_id": int(channel_id), "downloadable": False, "reason": "link_channel_does_not_support_qrcode_download", "channel": channel}
    conn = _connect()
    if conn is None:
        raw_channel = _FIXTURE_CHANNELS.get(int(channel_id), {})
        asset = dict(raw_channel.get("_active_qrcode_asset") or {})
        aliases: list[dict[str, Any]] = list(raw_channel.get("_scene_aliases") or [])
        effects: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
    else:
        asset = channel_entry_repo.get_active_qrcode_asset(int(channel_id)) or {}
        aliases = channel_entry_repo.list_channel_scene_aliases(int(channel_id))
        effects = channel_entry_repo.list_channel_entry_effect_logs(channel_id=int(channel_id), limit=10)
        events = channel_entry_repo.list_recent_events(_text(channel.get("scene_value")), limit=10) if _text(channel.get("scene_value")) else []
    reason = "downloadable"
    downloadable = True
    if not asset:
        downloadable = False
        reason = "qrcode_not_generated"
    elif int(asset.get("channel_id") or 0) != int(channel_id):
        downloadable = False
        reason = "qrcode_asset_channel_mismatch"
    elif _text(asset.get("status")) != "active":
        downloadable = False
        reason = "qrcode_asset_not_downloadable"
    elif _text(asset.get("scene_value")) != _text(channel.get("scene_value")) or _text(asset.get("qr_url")) != _text(channel.get("qr_url")):
        downloadable = False
        reason = "qrcode_asset_mismatch"
    elif not _text(asset.get("qr_url")).startswith(("http://", "https://")):
        downloadable = False
        reason = "qrcode_asset_missing_url"
    return {
        "channel_id": int(channel_id),
        "channel_name": _text(channel.get("channel_name")),
        "active_qrcode_asset": asset,
        "channel_cached_scene": _text(channel.get("scene_value")),
        "channel_cached_qr_url": _text(channel.get("qr_url")),
        "consistency_status": "ok" if downloadable else reason,
        "downloadable": downloadable,
        "reason": reason,
        "aliases": aliases,
        "recent_callback_states": events,
        "recent_effect_logs": effects,
    }


def list_channel_owner_candidates() -> list[dict[str, Any]]:
    # Compatibility wrapper for older channel-code callers. The page-level picker
    # now calls /api/admin/common/operation-members directly.
    payload = search_operation_members(scope="channel_code", page_size=100)
    return [
        {
            "owner_staff_id": item["user_id"],
            "display_name": item["display_name"] or item["user_id"],
            "position": _text((item.get("extra") or {}).get("position") or (item.get("extra") or {}).get("role")),
            "source": item.get("source") or "",
        }
        for item in payload.get("items", [])
    ]


def default_channel_form_payload() -> dict[str, Any]:
    return _default_channel()


@router.get("/api/admin/channels")
def list_channels(limit: int = Query(100), status: str = "", available_for_program_id: int | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "channels": _list_channels_from_postgres(
            limit=max(1, min(int(limit or 100), 500)),
            status=_text(status),
            available_for_program_id=available_for_program_id,
        ),
        "reason": "channels_listed",
        "source": "ai_crm_next",
    }


@router.post("/api/admin/channels", status_code=201)
def create_channel(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        channel = _save_postgres_channel(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "channel": channel, "reason": "channel_created", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}")
def get_channel(channel_id: int) -> dict[str, Any]:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return {"ok": True, "channel": channel, "reason": "channel_loaded", "source": "ai_crm_next"}


@router.patch("/api/admin/channels/{channel_id:int}")
def update_channel(channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        channel = _save_postgres_channel(payload, int(channel_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "channel": channel, "reason": "channel_updated", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/contacts")
def list_channel_contacts(channel_id: int, limit: int = Query(100)) -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        return {"ok": True, "contacts": [], "reason": "channel_contacts_listed", "source": "ai_crm_next"}
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT external_contact_id, display_name, enter_count, last_channel_entered_at
                FROM automation_channel_contact
                WHERE channel_id = %s
                ORDER BY last_channel_entered_at DESC, id DESC
                LIMIT %s
                """,
                (int(channel_id), max(1, min(int(limit or 100), 500))),
            )
            contacts = [{**dict(row), "last_channel_entered_at": _iso(row.get("last_channel_entered_at"))} for row in cur.fetchall() or []]
    return {"ok": True, "contacts": contacts, "reason": "channel_contacts_listed", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/bindings")
def list_channel_bindings(channel_id: int) -> dict[str, Any]:
    conn = _connect()
    if conn is None:
        return {"ok": True, "bindings": [], "reason": "channel_bindings_listed", "source": "ai_crm_next"}
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.id, b.program_id, p.program_name, b.binding_status, b.priority
                FROM automation_program_channel_binding b
                LEFT JOIN automation_program p ON p.id = b.program_id
                WHERE b.channel_id = %s
                ORDER BY b.priority DESC, b.id DESC
                """,
                (int(channel_id),),
            )
            bindings = [dict(row) for row in cur.fetchall() or []]
    return {"ok": True, "bindings": bindings, "reason": "channel_bindings_listed", "source": "ai_crm_next"}


@router.get("/api/admin/automation-conversion/programs/{program_id:int}/channel-bindings")
def list_program_channel_bindings(program_id: int) -> dict[str, Any]:
    return {
        "ok": True,
        "bindings": list_program_channel_bindings_resource(int(program_id)),
        "reason": "program_channel_bindings_listed",
        "source": "ai_crm_next",
    }


@router.post("/api/admin/automation-conversion/programs/{program_id:int}/channel-bindings", status_code=201)
def bind_program_channels(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    channel_ids = payload.get("channel_ids") or payload.get("channel_id") or []
    if not isinstance(channel_ids, list):
        channel_ids = [channel_ids]
    try:
        result = bind_channels_to_program_resource(
            int(program_id),
            [int(item) for item in channel_ids if _text(item)],
            payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result, "source": "ai_crm_next"}


@router.delete("/api/admin/automation-conversion/programs/{program_id:int}/channel-bindings/{binding_id:int}")
def unbind_program_channel(program_id: int, binding_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        result = archive_program_channel_binding_resource(int(program_id), int(binding_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result, "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/share-link")
def get_channel_share_link(channel_id: int) -> dict[str, Any]:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    if channel.get("carrier_type") != "link" and channel.get("channel_type") != "wecom_customer_acquisition":
        raise HTTPException(status_code=400, detail="channel_is_not_link_carrier")
    share_url = _text(channel.get("share_url") or channel.get("copy_text") or channel.get("final_url") or channel.get("link_url"))
    return {"ok": True, "share_url": share_url, "copy_text": share_url, "reason": "share_link_loaded", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/qrcode/download")
def download_channel_qrcode(channel_id: int):
    try:
        status = get_channel_qrcode_status_resource(int(channel_id))
    except LookupError:
        raise HTTPException(status_code=404, detail="channel_not_found")
    if status.get("reason") == "link_channel_does_not_support_qrcode_download":
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "link channel does not support qrcode download", "reason": "link_channel_does_not_support_qrcode_download"},
        )
    if not status.get("downloadable"):
        return JSONResponse(
            status_code=409,
            content={"ok": False, "reason": status.get("reason"), "qrcode_status": status},
            headers={"Cache-Control": "no-store"},
        )
    asset = status.get("active_qrcode_asset") or {}
    qr_url = _text(asset.get("qr_url"))
    if qr_url.startswith(("http://", "https://")):
        return RedirectResponse(
            qr_url,
            status_code=302,
            headers={
                "Cache-Control": "no-store",
                "X-AICRM-Channel-ID": str(int(channel_id)),
                "X-AICRM-QR-Scene": _text(asset.get("scene_value")),
                "X-AICRM-QR-Asset-ID": str(int(asset.get("id") or 0)),
            },
        )
    raise HTTPException(status_code=404, detail="qrcode_not_ready")


@router.get("/api/admin/channels/{channel_id:int}/qrcode/status")
def get_channel_qrcode_status(channel_id: int) -> dict[str, Any]:
    try:
        return {"ok": True, **get_channel_qrcode_status_resource(int(channel_id)), "source": "ai_crm_next"}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/admin/channel-welcome-materials")
def list_channel_welcome_materials(type: str = "all", keyword: str = "", q: str = "") -> dict[str, Any]:
    material_type = _text(type).lower() or "all"
    keyword_text = (_text(keyword) or _text(q)).lower()
    conn = _connect()
    if conn is None:
        return {"ok": True, "materials": [], "reason": "channel_welcome_materials_listed", "source": "ai_crm_next"}
    items: list[dict[str, Any]] = []
    with conn:
        with conn.cursor() as cur:
            if material_type in {"all", "miniprogram"}:
                cur.execute("SELECT id, name, title, appid, pagepath FROM miniprogram_library WHERE enabled = TRUE ORDER BY updated_at DESC, id DESC LIMIT 200")
                for row in cur.fetchall() or []:
                    haystack = " ".join(_text(row.get(key)) for key in ("name", "title", "appid", "pagepath")).lower()
                    if keyword_text and keyword_text not in haystack:
                        continue
                    name = _text(row.get("title") or row.get("name"))
                    items.append({"id": int(row["id"]), "type": "miniprogram", "name": name, "title": name, "description": _text(row.get("pagepath") or row.get("appid"))})
            if material_type in {"all", "image"}:
                cur.execute("SELECT id, name, file_name, mime_type FROM image_library WHERE enabled = TRUE ORDER BY updated_at DESC, id DESC LIMIT 200")
                for row in cur.fetchall() or []:
                    haystack = " ".join(_text(row.get(key)) for key in ("name", "file_name", "mime_type")).lower()
                    if keyword_text and keyword_text not in haystack:
                        continue
                    name = _text(row.get("name") or row.get("file_name"))
                    items.append({"id": int(row["id"]), "type": "image", "library": "image_library", "name": name, "title": name, "description": _text(row.get("file_name") or row.get("mime_type")), "mime_type": _text(row.get("mime_type"))})
            if material_type in {"all", "pdf"}:
                cur.execute("SELECT id, name, file_name, mime_type FROM attachment_library WHERE enabled = TRUE ORDER BY updated_at DESC, id DESC LIMIT 200")
                for row in cur.fetchall() or []:
                    mime = _text(row.get("mime_type")).lower()
                    file_name = _text(row.get("file_name"))
                    is_pdf = mime == "application/pdf" or file_name.lower().endswith(".pdf")
                    if not is_pdf:
                        continue
                    haystack = " ".join([_text(row.get("name")), file_name, mime]).lower()
                    if keyword_text and keyword_text not in haystack:
                        continue
                    name = _text(row.get("name") or file_name)
                    items.append({"id": int(row["id"]), "type": "pdf", "library": "attachment_library", "name": name, "title": name, "description": _text(file_name or mime), "mime_type": mime})
    return {"ok": True, "materials": items, "reason": "channel_welcome_materials_listed", "source": "ai_crm_next"}
