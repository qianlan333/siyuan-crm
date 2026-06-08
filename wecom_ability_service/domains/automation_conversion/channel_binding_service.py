from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from ...db import get_db
from . import program_repo, repo
from ._repo_helpers import _fetchall_dicts, _fetchone_dict, _json_dumps, _normalized_text
from .service import DEFAULT_CHANNEL_CODE, DEFAULT_CHANNEL_NAME, DEFAULT_OWNER_STAFF_ID

ACTIVE_BINDING = "active"
PAUSED_BINDING = "paused"
ARCHIVED_BINDING = "archived"
VALID_BINDING_STATUSES = {ACTIVE_BINDING, PAUSED_BINDING, ARCHIVED_BINDING}
VALID_AUDIENCE_CODES = {"pending_questionnaire", "operating", "converted"}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return _normalized_text(value)


def _normalize_id_list(value: Any) -> list[int]:
    raw = _json_loads(value, default=[]) if isinstance(value, str) else value
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raw = [raw]
    ids: list[int] = []
    for item in raw:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in ids:
            ids.append(item_id)
    return ids[:9]


def _customer_acquisition_final_url(link_url: str, customer_channel: str) -> str:
    normalized_url = _normalized_text(link_url)
    normalized_channel = _normalized_text(customer_channel)
    if not normalized_url or not normalized_channel:
        return normalized_url
    parts = urlsplit(normalized_url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "customer_channel"
    ]
    query_items.append(("customer_channel", normalized_channel))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_items), parts.fragment))


def _new_standalone_channel_code() -> str:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%y%m%d")
    return f"channel_{today}_{secrets.token_hex(2)}"


def _serialize_channel(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    item["id"] = int(item.get("id") or 0)
    item["program_id"] = int(item.get("program_id") or 0) or None
    item["welcome_image_library_ids"] = _normalize_id_list(item.get("welcome_image_library_ids"))
    item["welcome_attachment_library_ids"] = _normalize_id_list(item.get("welcome_attachment_library_ids"))
    item["welcome_miniprogram_library_ids"] = _normalize_id_list(item.get("welcome_miniprogram_library_ids"))
    item["auto_accept_friend"] = bool(item.get("auto_accept_friend"))
    wca_customer_channel = _normalized_text(item.get("wca_customer_channel"))
    wca_link_url = _normalized_text(item.get("wca_link_url"))
    wca_final_url = _normalized_text(item.get("wca_final_url"))
    channel_type = _normalized_text(item.get("channel_type")) or "qrcode"
    carrier_type = _normalized_text(item.get("carrier_type")) or "qrcode"
    if wca_customer_channel or wca_link_url or channel_type == "wecom_customer_acquisition":
        channel_type = "wecom_customer_acquisition"
        carrier_type = "link"
    item["channel_type"] = channel_type
    item["carrier_type"] = carrier_type
    item["customer_channel"] = _normalized_text(item.get("customer_channel")) or wca_customer_channel
    item["link_url"] = _normalized_text(item.get("link_url")) or wca_link_url
    final_url = _normalized_text(item.get("final_url")) or wca_final_url
    if channel_type == "wecom_customer_acquisition" and not final_url:
        final_url = _customer_acquisition_final_url(
            item["link_url"] or _normalized_text(item.get("qr_url")),
            item["customer_channel"] or _normalized_text(item.get("scene_value")),
        )
    item["final_url"] = final_url
    item["share_url"] = final_url if carrier_type == "link" else ""
    item["copy_text"] = final_url if carrier_type == "link" else ""
    item["qr_download_url"] = f"/api/admin/channels/{item['id']}/qrcode/download" if carrier_type != "link" else ""
    item["qr_download_ready"] = carrier_type != "link"
    item["welcome_message_configured"] = bool(_normalized_text(item.get("welcome_message")))
    item["welcome_attachment_count"] = (
        len(item["welcome_image_library_ids"])
        + len(item["welcome_attachment_library_ids"])
        + len(item["welcome_miniprogram_library_ids"])
    )
    item["entry_tag_configured"] = bool(_normalized_text(item.get("entry_tag_id")) or _normalized_text(item.get("entry_tag_name")))
    item["channel_contact_count"] = int(item.get("channel_contact_count") or 0)
    item["bound_program_id"] = int(item.get("bound_program_id") or 0) or None
    item["bound_program_name"] = _normalized_text(item.get("bound_program_name"))
    item["bound_binding_id"] = int(item.get("bound_binding_id") or 0) or None
    item["binding_status"] = _normalized_text(item.get("binding_status"))
    for key in ("created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    item["latest_channel_entered_at"] = _dt_text(item.get("latest_channel_entered_at"))
    return item


def _serialize_binding(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    for key in ("id", "program_id", "channel_id", "priority"):
        item[key] = int(item.get(key) or 0)
    item["auto_enter_pool"] = bool(item.get("auto_enter_pool"))
    item["entry_rule_json"] = _json_loads(item.get("entry_rule_json"), default={})
    for key in ("bound_at", "unbound_at", "created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    if "channel" not in item:
        channel = {
            "id": item.get("channel_id"),
            "channel_code": item.get("channel_code"),
            "channel_name": item.get("channel_name"),
            "scene_value": item.get("scene_value"),
            "customer_channel": item.get("customer_channel"),
            "channel_type": item.get("channel_type"),
            "carrier_type": item.get("carrier_type"),
            "link_url": item.get("link_url"),
            "final_url": item.get("final_url"),
            "status": item.get("channel_status"),
            "owner_staff_id": item.get("channel_owner_staff_id"),
        }
        if channel["id"]:
            item["channel"] = _serialize_channel(channel)
    return item


def _serialize_channel_contact(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    for key in ("id", "channel_id", "enter_count"):
        item[key] = int(item.get(key) or 0)
    item["master_customer_id"] = int(item.get("master_customer_id") or 0) or None
    item["source_payload_json"] = _json_loads(item.get("source_payload_json"), default={})
    for key in ("first_channel_entered_at", "last_channel_entered_at", "created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    return item


def list_channels(*, status: str = "", limit: int = 100, available_for_program_id: int | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_parts: list[str] = []
    normalized_status = _normalized_text(status)
    if normalized_status:
        where_parts.append("c.status = ?")
        params.append(normalized_status)
    if int(available_for_program_id or 0) > 0:
        where_parts.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM automation_program_channel_binding active_b
                WHERE active_b.channel_id = c.id
                  AND active_b.binding_status = 'active'
            )
            """
        )
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    rows = _fetchall_dicts(
        f"""
        SELECT c.*,
               COALESCE(contact_stats.channel_contact_count, 0) AS channel_contact_count,
               contact_stats.latest_channel_entered_at,
               b.id AS bound_binding_id,
               b.binding_status,
               b.program_id AS bound_program_id,
               p.program_name AS bound_program_name,
               wca.customer_channel AS wca_customer_channel,
               wca.link_url AS wca_link_url,
               wca.final_url AS wca_final_url
        FROM automation_channel c
        LEFT JOIN (
            SELECT channel_id,
                   COUNT(*) AS channel_contact_count,
                   MAX(last_channel_entered_at) AS latest_channel_entered_at
            FROM automation_channel_contact
            GROUP BY channel_id
        ) contact_stats ON contact_stats.channel_id = c.id
        LEFT JOIN automation_program_channel_binding b
          ON b.channel_id = c.id AND b.binding_status = 'active'
        LEFT JOIN automation_program p ON p.id = b.program_id
        LEFT JOIN wecom_customer_acquisition_links wca
          ON wca.automation_channel_id = c.id AND wca.status = 'active'
        {where}
        ORDER BY c.updated_at DESC, c.id DESC
        LIMIT ?
        """,
        (*params, max(1, min(int(limit or 100), 500))),
    )
    return [_serialize_channel(row) for row in rows]


def get_channel(channel_id: int) -> dict[str, Any] | None:
    row = repo.get_channel_by_id(int(channel_id))
    return _serialize_channel(row) if row else None


def save_channel_resource(payload: dict[str, Any], *, channel_id: int | None = None) -> dict[str, Any]:
    existing = repo.get_channel_by_id(int(channel_id or 0)) if channel_id else {}
    if channel_id and not existing:
        raise LookupError("channel_not_found")
    channel_code = _normalized_text(payload.get("channel_code")) or _normalized_text((existing or {}).get("channel_code"))
    if not channel_code:
        channel_code = f"channel_{int(channel_id)}" if channel_id else _new_standalone_channel_code()
    channel_payload = {
        "program_id": payload.get("program_id", (existing or {}).get("program_id")),
        "channel_code": channel_code,
        "channel_name": _normalized_text(payload.get("channel_name")) or _normalized_text((existing or {}).get("channel_name")) or DEFAULT_CHANNEL_NAME,
        "channel_type": _normalized_text(payload.get("channel_type")) or _normalized_text((existing or {}).get("channel_type")) or "qrcode",
        "carrier_type": _normalized_text(payload.get("carrier_type")) or _normalized_text((existing or {}).get("carrier_type")) or "qrcode",
        "qr_url": _normalized_text(payload.get("qr_url")) or _normalized_text((existing or {}).get("qr_url")),
        "qr_ticket": _normalized_text(payload.get("qr_ticket")) or _normalized_text((existing or {}).get("qr_ticket")),
        "scene_value": _normalized_text(payload.get("scene_value")) or _normalized_text((existing or {}).get("scene_value")),
        "customer_channel": _normalized_text(payload.get("customer_channel")) or _normalized_text((existing or {}).get("customer_channel")),
        "link_url": _normalized_text(payload.get("link_url")) or _normalized_text((existing or {}).get("link_url")),
        "final_url": _normalized_text(payload.get("final_url")) or _normalized_text((existing or {}).get("final_url")),
        "welcome_message": _normalized_text(payload.get("welcome_message")) if "welcome_message" in payload else _normalized_text((existing or {}).get("welcome_message")),
        "welcome_image_library_ids": payload.get("welcome_image_library_ids", (existing or {}).get("welcome_image_library_ids") or []),
        "welcome_miniprogram_library_ids": payload.get("welcome_miniprogram_library_ids", (existing or {}).get("welcome_miniprogram_library_ids") or []),
        "welcome_attachment_library_ids": payload.get("welcome_attachment_library_ids", (existing or {}).get("welcome_attachment_library_ids") or []),
        "auto_accept_friend": _truthy(payload.get("auto_accept_friend"), default=bool((existing or {}).get("auto_accept_friend"))),
        "entry_tag_id": _normalized_text(payload.get("entry_tag_id")) if "entry_tag_id" in payload else _normalized_text((existing or {}).get("entry_tag_id")),
        "entry_tag_name": _normalized_text(payload.get("entry_tag_name")) if "entry_tag_name" in payload else _normalized_text((existing or {}).get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(payload.get("entry_tag_group_name")) if "entry_tag_group_name" in payload else _normalized_text((existing or {}).get("entry_tag_group_name")),
        "owner_staff_id": _normalized_text(payload.get("owner_staff_id")) or _normalized_text((existing or {}).get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
        "status": _normalized_text(payload.get("status")) or _normalized_text((existing or {}).get("status")) or "inactive",
    }
    if channel_payload["channel_type"] == "wecom_customer_acquisition":
        channel_payload["carrier_type"] = "link"
        if not channel_payload["customer_channel"]:
            channel_payload["customer_channel"] = channel_payload["scene_value"]
        if not channel_payload["scene_value"]:
            channel_payload["scene_value"] = channel_payload["customer_channel"]
        if not channel_payload["final_url"]:
            channel_payload["final_url"] = _customer_acquisition_final_url(
                channel_payload["link_url"] or channel_payload["qr_url"],
                channel_payload["customer_channel"],
            )
        if not channel_payload["qr_url"]:
            channel_payload["qr_url"] = channel_payload["final_url"]
    if existing:
        saved = get_db().execute(
            """
            UPDATE automation_channel
            SET program_id = ?,
                channel_code = ?,
                channel_name = ?,
                channel_type = ?,
                carrier_type = ?,
                qr_url = ?,
                qr_ticket = ?,
                scene_value = ?,
                customer_channel = ?,
                link_url = ?,
                final_url = ?,
                welcome_message = ?,
                welcome_image_library_ids = CAST(? AS jsonb),
                welcome_miniprogram_library_ids = CAST(? AS jsonb),
                welcome_attachment_library_ids = CAST(? AS jsonb),
                auto_accept_friend = ?,
                entry_tag_id = ?,
                entry_tag_name = ?,
                entry_tag_group_name = ?,
                owner_staff_id = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                int(channel_payload.get("program_id") or 0) or None,
                channel_payload["channel_code"],
                channel_payload["channel_name"],
                channel_payload["channel_type"],
                channel_payload["carrier_type"],
                channel_payload["qr_url"],
                channel_payload["qr_ticket"],
                channel_payload["scene_value"],
                channel_payload["customer_channel"],
                channel_payload["link_url"],
                channel_payload["final_url"],
                channel_payload["welcome_message"],
                _json_dumps(_normalize_id_list(channel_payload["welcome_image_library_ids"] or [])),
                _json_dumps(_normalize_id_list(channel_payload["welcome_miniprogram_library_ids"] or [])),
                _json_dumps(channel_payload["welcome_attachment_library_ids"] or []),
                bool(channel_payload["auto_accept_friend"]),
                channel_payload["entry_tag_id"],
                channel_payload["entry_tag_name"],
                channel_payload["entry_tag_group_name"],
                channel_payload["owner_staff_id"],
                channel_payload["status"],
                int(existing["id"]),
            ),
        ).fetchone()
        get_db().commit()
        return _serialize_channel(dict(saved) if saved else {})
    saved = repo.save_channel(
        channel_payload
    )
    get_db().commit()
    return _serialize_channel(saved)


def list_program_channel_bindings(program_id: int) -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT b.*, c.channel_code, c.channel_name, c.channel_type, c.carrier_type, c.scene_value,
               c.customer_channel, c.link_url, c.final_url, c.status AS channel_status,
               c.owner_staff_id AS channel_owner_staff_id
        FROM automation_program_channel_binding b
        INNER JOIN automation_channel c ON c.id = b.channel_id
        WHERE b.program_id = ?
        ORDER BY
            CASE b.binding_status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
            b.priority DESC,
            b.updated_at DESC,
            b.id DESC
        """,
        (int(program_id),),
    )
    return [_serialize_binding(row) for row in rows]


def list_channel_bindings(channel_id: int) -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT b.*, p.program_code, p.program_name, p.status AS program_status
        FROM automation_program_channel_binding b
        INNER JOIN automation_program p ON p.id = b.program_id
        WHERE b.channel_id = ?
        ORDER BY
            CASE b.binding_status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
            b.priority DESC,
            b.updated_at DESC,
            b.id DESC
        """,
        (int(channel_id),),
    )
    return [_serialize_binding(row) for row in rows]


def get_program_channel_binding(program_id: int, binding_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT b.*, c.channel_code, c.channel_name, c.channel_type, c.carrier_type, c.scene_value,
               c.customer_channel, c.link_url, c.final_url, c.status AS channel_status,
               c.owner_staff_id AS channel_owner_staff_id
        FROM automation_program_channel_binding b
        INNER JOIN automation_channel c ON c.id = b.channel_id
        WHERE b.program_id = ?
          AND b.id = ?
        LIMIT 1
        """,
        (int(program_id), int(binding_id)),
    )
    return _serialize_binding(row) if row else None


def list_active_bindings_for_channel(channel_id: int) -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT b.*, c.channel_code, c.channel_name, c.channel_type, c.carrier_type, c.scene_value,
               c.customer_channel, c.link_url, c.final_url, c.status AS channel_status,
               c.owner_staff_id AS channel_owner_staff_id
        FROM automation_program_channel_binding b
        INNER JOIN automation_channel c ON c.id = b.channel_id
        WHERE b.channel_id = ?
          AND b.binding_status = 'active'
        ORDER BY b.priority DESC, b.bound_at DESC, b.id DESC
        """,
        (int(channel_id),),
    )
    return [_serialize_binding(row) for row in rows]


def get_program_channel_binding_member_stage_summary(program_id: int, binding_id: int, *, limit: int = 200) -> dict[str, Any]:
    binding = get_program_channel_binding(int(program_id), int(binding_id))
    if not binding:
        raise LookupError("binding_not_found")
    channel_id = int(binding.get("channel_id") or 0)
    rows = _fetchall_dicts(
        """
        SELECT pm.id AS program_member_id,
               pm.external_contact_id,
               COALESCE(c.customer_name, '') AS display_name,
               COALESCE(c.customer_name, '') AS name,
               pm.current_stage_code,
               pm.current_audience_code,
               pm.current_stage_entered_at,
               pm.pool_entered_at,
               pm.in_program,
               pm.exited_at
        FROM automation_program_member pm
        LEFT JOIN contacts c ON c.external_userid = pm.external_contact_id
        WHERE pm.program_id = ?
          AND (
              pm.source_binding_id = ?
              OR pm.source_channel_id = ?
              OR pm.first_source_channel_id = ?
          )
        ORDER BY pm.in_program DESC, pm.current_stage_entered_at DESC NULLS LAST, pm.id DESC
        LIMIT ?
        """,
        (int(program_id), int(binding_id), channel_id, channel_id, max(1, min(int(limit or 200), 1000))),
    )
    summary = {
        "total": 0,
        "order_review": 0,
        "questionnaire_review": 0,
        "operating": 0,
        "converted": 0,
        "finished": 0,
        "exited": 0,
    }
    members = []
    for row in rows:
        item = dict(row)
        in_program = bool(item.get("in_program"))
        stage_code = _normalized_text(item.get("current_stage_code")) or _normalized_text(item.get("current_audience_code"))
        if not in_program:
            summary["exited"] += 1
        elif stage_code in summary:
            summary[stage_code] += 1
        summary["total"] += 1
        members.append(
            {
                "program_member_id": int(item.get("program_member_id") or 0),
                "external_contact_id": _normalized_text(item.get("external_contact_id")),
                "display_name": _normalized_text(item.get("display_name")) or _normalized_text(item.get("name")),
                "name": _normalized_text(item.get("name")) or _normalized_text(item.get("display_name")),
                "current_stage_code": stage_code,
                "current_audience_code": _normalized_text(item.get("current_audience_code")),
                "pool_entered_at": _dt_text(item.get("pool_entered_at")),
                "stage_entered_at": _dt_text(item.get("current_stage_entered_at")),
                "in_program": in_program,
                "exited_at": _dt_text(item.get("exited_at")),
            }
        )
    return {
        "binding": binding,
        "summary": summary,
        "members": members,
        "reason": "binding_member_stage_summary_loaded",
    }


def assert_channel_active_binding_available(channel_id: int, program_id: int, *, exclude_binding_id: int | None = None) -> None:
    params: list[Any] = [int(channel_id), int(program_id)]
    extra_sql = ""
    if exclude_binding_id:
        extra_sql = " AND id <> ?"
        params.append(int(exclude_binding_id))
    row = _fetchone_dict(
        f"""
        SELECT id, program_id
        FROM automation_program_channel_binding
        WHERE channel_id = ?
          AND binding_status = 'active'
          AND program_id <> ?
          {extra_sql}
        LIMIT 1
        """,
        tuple(params),
    )
    if row:
        raise ValueError("Phase 1 暂不支持一个渠道码同时绑定多个自动化运营方案")


def _legacy_binding_status(*, channel_status: str = "", link_status: str = "", source: str = "") -> str:
    normalized_channel_status = _normalized_text(channel_status)
    normalized_link_status = _normalized_text(link_status)
    if source == "wecom_customer_acquisition_links.program_id":
        return ACTIVE_BINDING if normalized_link_status == "active" and normalized_channel_status == "active" else PAUSED_BINDING
    return ACTIVE_BINDING if normalized_channel_status in {"active", "configured"} else PAUSED_BINDING


def _legacy_bound_at(row: dict[str, Any]) -> str:
    return _dt_text(row.get("created_at") or row.get("updated_at"))


def _candidate_item(
    *,
    program_id: int,
    channel_id: int,
    channel_code: str,
    source: str,
    binding_status: str,
    bound_at: str,
) -> dict[str, Any]:
    return {
        "program_id": int(program_id),
        "channel_id": int(channel_id),
        "channel_code": _normalized_text(channel_code),
        "source": source,
        "binding_status": binding_status if binding_status in VALID_BINDING_STATUSES else PAUSED_BINDING,
        "bound_at": _normalized_text(bound_at),
    }


def _walk_entry_channel_payload(value: Any) -> tuple[set[int], set[int]]:
    channel_ids: set[int] = set()
    link_ids: set[int] = set()
    if isinstance(value, dict):
        for key, raw in value.items():
            normalized_key = _normalized_text(key)
            if normalized_key in {"channel_id", "automation_channel_id", "default_channel_id"}:
                try:
                    channel_id = int(raw or 0)
                except (TypeError, ValueError):
                    channel_id = 0
                if channel_id > 0:
                    channel_ids.add(channel_id)
                continue
            if normalized_key in {"channel_ids", "automation_channel_ids"}:
                raw_items = raw if isinstance(raw, list) else [raw]
                for item in raw_items:
                    try:
                        channel_id = int(item or 0)
                    except (TypeError, ValueError):
                        channel_id = 0
                    if channel_id > 0:
                        channel_ids.add(channel_id)
                continue
            if normalized_key in {"customer_acquisition_link_id", "wecom_customer_acquisition_link_id"}:
                try:
                    link_id = int(raw or 0)
                except (TypeError, ValueError):
                    link_id = 0
                if link_id > 0:
                    link_ids.add(link_id)
                continue
            if normalized_key in {"customer_acquisition_link_ids", "wecom_customer_acquisition_link_ids"}:
                raw_items = raw if isinstance(raw, list) else [raw]
                for item in raw_items:
                    try:
                        link_id = int(item or 0)
                    except (TypeError, ValueError):
                        link_id = 0
                    if link_id > 0:
                        link_ids.add(link_id)
                continue
            nested_channels, nested_links = _walk_entry_channel_payload(raw)
            channel_ids.update(nested_channels)
            link_ids.update(nested_links)
    elif isinstance(value, list):
        for item in value:
            nested_channels, nested_links = _walk_entry_channel_payload(item)
            channel_ids.update(nested_channels)
            link_ids.update(nested_links)
    return channel_ids, link_ids


def _legacy_entry_channel_candidates(*, channel_id: int | None = None) -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT program_id, payload_json, created_at, updated_at
        FROM automation_program_config_block
        WHERE block_key = 'entry_channel'
        ORDER BY updated_at ASC, id ASC
        """
    )
    candidates: list[dict[str, Any]] = []
    requested_channel_id = int(channel_id or 0)
    for row in rows:
        program_id = int(row.get("program_id") or 0)
        payload = _json_loads(row.get("payload_json"), default={})
        channel_ids, link_ids = _walk_entry_channel_payload(payload)
        for link_id in sorted(link_ids):
            link = _fetchone_dict(
                """
                SELECT l.*, c.channel_code, c.status AS channel_status
                FROM wecom_customer_acquisition_links l
                INNER JOIN automation_channel c ON c.id = l.automation_channel_id
                WHERE l.id = ?
                LIMIT 1
                """,
                (int(link_id),),
            )
            if not link:
                continue
            channel_ids.add(int(link.get("automation_channel_id") or 0))
        for cid in sorted(channel_ids):
            if requested_channel_id and cid != requested_channel_id:
                continue
            channel = repo.get_channel_by_id(int(cid))
            if not channel:
                continue
            candidates.append(
                _candidate_item(
                    program_id=program_id,
                    channel_id=int(channel["id"]),
                    channel_code=_normalized_text(channel.get("channel_code")),
                    source="automation_program_config_block.entry_channel",
                    binding_status=_legacy_binding_status(channel_status=_normalized_text(channel.get("status"))),
                    bound_at=_legacy_bound_at(row),
                )
            )
    return candidates


def ensure_legacy_program_channel_bindings(*, channel_id: int | None = None) -> dict[str, Any]:
    requested_channel_id = int(channel_id or 0)
    params: list[Any] = []
    channel_filter = ""
    if requested_channel_id:
        channel_filter = "AND c.id = ?"
        params.append(requested_channel_id)
    channel_rows = _fetchall_dicts(
        f"""
        SELECT c.*
        FROM automation_channel c
        INNER JOIN automation_program p ON p.id = c.program_id
        WHERE c.program_id IS NOT NULL
          {channel_filter}
        ORDER BY c.id ASC
        """,
        tuple(params),
    )
    candidates: list[dict[str, Any]] = [
        _candidate_item(
            program_id=int(row["program_id"]),
            channel_id=int(row["id"]),
            channel_code=_normalized_text(row.get("channel_code")),
            source="automation_channel.program_id",
            binding_status=_legacy_binding_status(channel_status=_normalized_text(row.get("status"))),
            bound_at=_legacy_bound_at(row),
        )
        for row in channel_rows
    ]

    params = []
    channel_filter = ""
    if requested_channel_id:
        channel_filter = "AND l.automation_channel_id = ?"
        params.append(requested_channel_id)
    link_rows = _fetchall_dicts(
        f"""
        SELECT l.*, c.channel_code, c.status AS channel_status
        FROM wecom_customer_acquisition_links l
        INNER JOIN automation_channel c ON c.id = l.automation_channel_id
        INNER JOIN automation_program p ON p.id = l.program_id
        WHERE l.program_id IS NOT NULL
          AND l.automation_channel_id IS NOT NULL
          {channel_filter}
        ORDER BY l.id ASC
        """,
        tuple(params),
    )
    candidates.extend(
        _candidate_item(
            program_id=int(row["program_id"]),
            channel_id=int(row["automation_channel_id"]),
            channel_code=_normalized_text(row.get("channel_code")),
            source="wecom_customer_acquisition_links.program_id",
            binding_status=_legacy_binding_status(
                channel_status=_normalized_text(row.get("channel_status")),
                link_status=_normalized_text(row.get("status")),
                source="wecom_customer_acquisition_links.program_id",
            ),
            bound_at=_legacy_bound_at(row),
        )
        for row in link_rows
    )
    candidates.extend(_legacy_entry_channel_candidates(channel_id=requested_channel_id or None))

    report = {
        "created_binding_count": 0,
        "skipped_existing_count": 0,
        "conflict_count": 0,
        "items": [],
        "conflicts": [],
    }
    chosen_by_channel: dict[int, dict[str, Any]] = {}
    programs_by_channel: dict[int, set[int]] = {}
    for candidate in candidates:
        cid = int(candidate.get("channel_id") or 0)
        pid = int(candidate.get("program_id") or 0)
        if cid <= 0 or pid <= 0:
            continue
        programs_by_channel.setdefault(cid, set()).add(pid)
        if cid not in chosen_by_channel:
            chosen_by_channel[cid] = candidate
            continue
        current = chosen_by_channel[cid]
        if current["source"] != "automation_channel.program_id" and candidate["source"] == "automation_channel.program_id":
            chosen_by_channel[cid] = candidate

    db = get_db()
    try:
        for cid, chosen in chosen_by_channel.items():
            candidate_program_ids = sorted(programs_by_channel.get(cid) or {int(chosen["program_id"])})
            if len(candidate_program_ids) > 1:
                report["conflicts"].append(
                    {
                        "channel_id": cid,
                        "channel_code": chosen.get("channel_code") or "",
                        "candidate_program_ids": candidate_program_ids,
                        "chosen_program_id": int(chosen["program_id"]),
                        "reason": "automation_channel.program_id takes precedence"
                        if chosen.get("source") == "automation_channel.program_id"
                        else "first legacy relation takes precedence",
                    }
                )
            existing = _fetchone_dict(
                """
                SELECT *
                FROM automation_program_channel_binding
                WHERE program_id = ?
                  AND channel_id = ?
                LIMIT 1
                """,
                (int(chosen["program_id"]), cid),
            )
            if existing:
                report["skipped_existing_count"] += 1
                report["items"].append(
                    {
                        **chosen,
                        "binding_id": int(existing["id"]),
                        "created": False,
                    }
                )
                continue
            if chosen["binding_status"] == ACTIVE_BINDING:
                active_other = _fetchone_dict(
                    """
                    SELECT id, program_id
                    FROM automation_program_channel_binding
                    WHERE channel_id = ?
                      AND binding_status = 'active'
                      AND program_id <> ?
                    LIMIT 1
                    """,
                    (cid, int(chosen["program_id"])),
                )
                if active_other:
                    report["conflicts"].append(
                        {
                            "channel_id": cid,
                            "channel_code": chosen.get("channel_code") or "",
                            "candidate_program_ids": sorted({int(chosen["program_id"]), int(active_other["program_id"])}),
                            "chosen_program_id": int(active_other["program_id"]),
                            "reason": "existing active binding takes precedence",
                        }
                    )
                    continue
            row = db.execute(
                """
                INSERT INTO automation_program_channel_binding (
                    program_id, channel_id, binding_status, auto_enter_pool,
                    initial_audience_code, entry_rule_json, priority, bound_by,
                    bound_at, unbound_at, created_at, updated_at
                )
                VALUES (?, ?, ?, TRUE, 'pending_questionnaire', '{}'::jsonb, 0, 'legacy_migration',
                        COALESCE(NULLIF(?, '')::timestamptz, CURRENT_TIMESTAMP),
                        CASE WHEN ? = 'active' THEN NULL ELSE COALESCE(NULLIF(?, '')::timestamptz, CURRENT_TIMESTAMP) END,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING *
                """,
                (
                    int(chosen["program_id"]),
                    cid,
                    chosen["binding_status"],
                    _normalized_text(chosen.get("bound_at")),
                    chosen["binding_status"],
                    _normalized_text(chosen.get("bound_at")),
                ),
            ).fetchone()
            report["created_binding_count"] += 1
            report["items"].append(
                {
                    **chosen,
                    "binding_id": int((row or {}).get("id") or 0),
                    "created": True,
                }
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    report["conflict_count"] = len(report["conflicts"])
    return report


def _normalize_binding_payload(payload: dict[str, Any], *, operator_id: str = "") -> dict[str, Any]:
    status = _normalized_text(payload.get("binding_status")) or ACTIVE_BINDING
    if status not in VALID_BINDING_STATUSES:
        raise ValueError("invalid_binding_status")
    audience_code = _normalized_text(payload.get("initial_audience_code")) or "pending_questionnaire"
    if audience_code not in VALID_AUDIENCE_CODES:
        raise ValueError("invalid_initial_audience_code")
    return {
        "binding_status": status,
        "auto_enter_pool": _truthy(payload.get("auto_enter_pool"), default=True),
        "initial_audience_code": audience_code,
        "entry_rule_json": dict(payload.get("entry_rule_json") or {}),
        "priority": int(payload.get("priority") or 0),
        "bound_by": _normalized_text(operator_id) or _normalized_text(payload.get("bound_by")),
    }


def bind_channels_to_program(
    program_id: int,
    channel_ids: list[int],
    payload: dict[str, Any] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    program = program_repo.get_program_row(int(program_id))
    if not program:
        raise LookupError("program_not_found")
    normalized_ids = []
    for channel_id in channel_ids:
        cid = int(channel_id or 0)
        if cid > 0 and cid not in normalized_ids:
            normalized_ids.append(cid)
    if not normalized_ids:
        raise ValueError("channel_ids_required")
    data = _normalize_binding_payload(dict(payload or {}), operator_id=operator_id)
    db = get_db()
    bindings: list[dict[str, Any]] = []
    try:
        for channel_id in normalized_ids:
            if not repo.get_channel_by_id(channel_id):
                raise LookupError("channel_not_found")
            if data["binding_status"] == ACTIVE_BINDING:
                assert_channel_active_binding_available(channel_id, int(program_id))
            row = db.execute(
                """
                INSERT INTO automation_program_channel_binding (
                    program_id, channel_id, binding_status, auto_enter_pool,
                    initial_audience_code, entry_rule_json, priority, bound_by,
                    bound_at, unbound_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (program_id, channel_id) DO UPDATE
                SET binding_status = EXCLUDED.binding_status,
                    auto_enter_pool = EXCLUDED.auto_enter_pool,
                    initial_audience_code = EXCLUDED.initial_audience_code,
                    entry_rule_json = EXCLUDED.entry_rule_json,
                    priority = EXCLUDED.priority,
                    bound_by = EXCLUDED.bound_by,
                    bound_at = CASE
                        WHEN automation_program_channel_binding.binding_status <> 'active'
                         AND EXCLUDED.binding_status = 'active' THEN CURRENT_TIMESTAMP
                        ELSE automation_program_channel_binding.bound_at
                    END,
                    unbound_at = CASE WHEN EXCLUDED.binding_status = 'active' THEN NULL ELSE automation_program_channel_binding.unbound_at END,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                (
                    int(program_id),
                    channel_id,
                    data["binding_status"],
                    bool(data["auto_enter_pool"]),
                    data["initial_audience_code"],
                    _json_dumps(data["entry_rule_json"]),
                    data["priority"],
                    data["bound_by"],
                ),
            ).fetchone()
            bindings.append(_serialize_binding(dict(row) if row else {}))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "bindings": bindings,
        "reason": "channels_bound",
        "history_imported": False,
        "history_import_reason": "binding_does_not_import_historical_channel_contacts",
    }


def update_program_channel_binding(program_id: int, binding_id: int, payload: dict[str, Any], operator_id: str = "") -> dict[str, Any]:
    existing = _fetchone_dict(
        "SELECT * FROM automation_program_channel_binding WHERE id = ? AND program_id = ? LIMIT 1",
        (int(binding_id), int(program_id)),
    )
    if not existing:
        raise LookupError("binding_not_found")
    merged = {**existing, **dict(payload or {})}
    data = _normalize_binding_payload(merged, operator_id=operator_id)
    if data["binding_status"] == ACTIVE_BINDING:
        assert_channel_active_binding_available(
            int(existing["channel_id"]),
            int(program_id),
            exclude_binding_id=int(binding_id),
        )
    row = get_db().execute(
        """
        UPDATE automation_program_channel_binding
        SET binding_status = ?,
            auto_enter_pool = ?,
            initial_audience_code = ?,
            entry_rule_json = CAST(? AS jsonb),
            priority = ?,
            bound_by = CASE WHEN ? <> '' THEN ? ELSE bound_by END,
            unbound_at = CASE WHEN ? = 'active' THEN NULL ELSE COALESCE(unbound_at, CURRENT_TIMESTAMP) END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND program_id = ?
        RETURNING *
        """,
        (
            data["binding_status"],
            bool(data["auto_enter_pool"]),
            data["initial_audience_code"],
            _json_dumps(data["entry_rule_json"]),
            data["priority"],
            data["bound_by"],
            data["bound_by"],
            data["binding_status"],
            int(binding_id),
            int(program_id),
        ),
    ).fetchone()
    get_db().commit()
    return {"binding": _serialize_binding(dict(row) if row else {}), "reason": "binding_updated"}


def archive_program_channel_binding(program_id: int, binding_id: int, operator_id: str = "") -> dict[str, Any]:
    db = get_db()
    row = db.execute(
        """
        UPDATE automation_program_channel_binding
        SET binding_status = 'archived',
            bound_by = CASE WHEN ? <> '' THEN ? ELSE bound_by END,
            unbound_at = COALESCE(unbound_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND program_id = ?
        RETURNING *
        """,
        (_normalized_text(operator_id), _normalized_text(operator_id), int(binding_id), int(program_id)),
    ).fetchone()
    if not row:
        raise LookupError("binding_not_found")
    binding = dict(row)
    exit_result = db.execute(
        """
        UPDATE automation_program_member
        SET in_program = FALSE,
            exited_at = COALESCE(exited_at, CURRENT_TIMESTAMP),
            exit_reason = CASE WHEN exit_reason <> '' THEN exit_reason ELSE 'channel_binding_archived' END,
            updated_at = CURRENT_TIMESTAMP
        WHERE program_id = ?
          AND in_program = TRUE
          AND (
              source_channel_id = ?
              OR first_source_channel_id = ?
              OR latest_source_channel_id = ?
          )
        """,
        (
            int(program_id),
            int(binding.get("channel_id") or 0),
            int(binding.get("channel_id") or 0),
            int(binding.get("channel_id") or 0),
        ),
    )
    exited_member_count = int(getattr(exit_result, "rowcount", 0) or 0)
    db.commit()
    return {
        "binding": _serialize_binding(binding),
        "reason": "binding_archived",
        "channel_deleted": False,
        "exited_member_count": exited_member_count,
    }


def upsert_channel_contact(
    *,
    channel_id: int,
    external_contact_id: str = "",
    master_customer_id: int | None = None,
    owner_staff_id: str = "",
    source_payload: dict[str, Any] | None = None,
    entered_at: str = "",
) -> dict[str, Any]:
    entered_at = _normalized_text(entered_at) or "CURRENT_TIMESTAMP"
    external_contact_id = _normalized_text(external_contact_id)
    row = get_db().execute(
        """
        INSERT INTO automation_channel_contact (
            channel_id, external_contact_id, master_customer_id, owner_staff_id,
            first_channel_entered_at, last_channel_entered_at, enter_count,
            source_payload_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, COALESCE(NULLIF(?, '')::timestamptz, CURRENT_TIMESTAMP), COALESCE(NULLIF(?, '')::timestamptz, CURRENT_TIMESTAMP), 1, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (channel_id, external_contact_id) WHERE external_contact_id <> '' DO UPDATE
        SET master_customer_id = COALESCE(EXCLUDED.master_customer_id, automation_channel_contact.master_customer_id),
            owner_staff_id = CASE WHEN EXCLUDED.owner_staff_id <> '' THEN EXCLUDED.owner_staff_id ELSE automation_channel_contact.owner_staff_id END,
            last_channel_entered_at = EXCLUDED.last_channel_entered_at,
            enter_count = automation_channel_contact.enter_count + 1,
            source_payload_json = EXCLUDED.source_payload_json,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            int(channel_id),
            external_contact_id,
            int(master_customer_id or 0) or None,
            _normalized_text(owner_staff_id),
            entered_at if entered_at != "CURRENT_TIMESTAMP" else "",
            entered_at if entered_at != "CURRENT_TIMESTAMP" else "",
            _json_dumps(source_payload or {}),
        ),
    ).fetchone()
    return _serialize_channel_contact(dict(row) if row else {})


def list_channel_contacts(channel_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT *
        FROM automation_channel_contact
        WHERE channel_id = ?
        ORDER BY last_channel_entered_at DESC, id DESC
        LIMIT ?
        """,
        (int(channel_id), max(1, min(int(limit or 100), 500))),
    )
    return [_serialize_channel_contact(row) for row in rows]
