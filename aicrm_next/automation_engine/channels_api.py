from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from aicrm_next.common_operation_members import search_operation_members
from aicrm_next.channel_entry import repo as channel_entry_repo
from aicrm_next.shared.runtime import raw_database_url

router = APIRouter()

_FIXTURE_CHANNELS: dict[int, dict[str, Any]] = {}
_FIXTURE_PROGRAM_BINDINGS: dict[int, dict[str, Any]] = {}
_FIXTURE_CHANNEL_ASSIGNEES: dict[int, list[dict[str, Any]]] = {}
_FIXTURE_ASSIGNMENT_EVENTS: list[dict[str, Any]] = []
_FIXTURE_WE_COM_LINKS: list[dict[str, Any]] = []
_NEXT_ID = 1
_NEXT_BINDING_ID = 1
_NEXT_ASSIGNEE_ID = 1
_NEXT_ASSIGNMENT_EVENT_ID = 1
_NEXT_WE_COM_LINK_ID = 1


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


def _uses_postgres() -> bool:
    database_url = _psycopg_url(raw_database_url())
    return database_url.startswith(("postgresql://", "postgres://"))


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


def _json_dict(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


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


def _assignment_mode(value: Any) -> str:
    mode = _text(value) or "single_owner"
    return mode if mode in {"single_owner", "multi_staff"} else "single_owner"


def _assignment_strategy(value: Any) -> str:
    strategy = _text(value) or "ratio"
    return strategy if strategy in {"ratio", "cap_switch"} else "ratio"


def _serialize_assignment_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "channel_id": int(row.get("channel_id") or 0),
        "assignee_staff_id": _text(row.get("assignee_staff_id")),
        "strategy": _text(row.get("strategy")),
        "reason": _text(row.get("reason")),
        "status": _text(row.get("status")) or "assigned",
        "external_contact_id": _text(row.get("external_contact_id")),
        "wecom_user_id": _text(row.get("wecom_user_id")),
        "assigned_at": _iso(row.get("assigned_at")),
    }


def _fixture_assignees(channel_id: int, *, active_only: bool = False) -> list[dict[str, Any]]:
    rows = [dict(item) for item in _FIXTURE_CHANNEL_ASSIGNEES.get(int(channel_id), [])]
    if active_only:
        rows = [item for item in rows if _text(item.get("status")) == "active"]
    return sorted(rows, key=lambda item: (int(item.get("priority") or 0), int(item.get("id") or 0)))


def _fixture_stats_24h(channel_id: int) -> list[dict[str, Any]]:
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    counts: dict[str, int] = {}
    for event in _FIXTURE_ASSIGNMENT_EVENTS:
        if int(event.get("channel_id") or 0) != int(channel_id) or _text(event.get("status")) != "assigned":
            continue
        assigned_at = event.get("assigned_at")
        if isinstance(assigned_at, str):
            try:
                assigned_at = datetime.fromisoformat(assigned_at)
            except ValueError:
                assigned_at = datetime.now(timezone.utc)
        if isinstance(assigned_at, datetime) and assigned_at.tzinfo is None:
            assigned_at = assigned_at.replace(tzinfo=timezone.utc)
        if isinstance(assigned_at, datetime) and assigned_at < cutoff:
            continue
        staff_id = _text(event.get("assignee_staff_id"))
        counts[staff_id] = counts.get(staff_id, 0) + 1
    return [
        {
            "staff_id": item["staff_id"],
            "assignee_staff_id": item["staff_id"],
            "assigned_count": counts.get(item["staff_id"], 0),
            "window": "24h",
        }
        for item in _fixture_assignees(int(channel_id), active_only=True)
    ]


def _fixture_save_channel_assignees(
    channel_id: int,
    *,
    assignment_mode: str,
    assignment_strategy: str,
    assignees: list[dict[str, Any]] | None,
    overflow_policy: str = "",
) -> dict[str, Any]:
    global _NEXT_ASSIGNEE_ID
    if int(channel_id) not in _FIXTURE_CHANNELS:
        raise LookupError("channel_not_found")
    normalized_mode = _assignment_mode(assignment_mode or "multi_staff")
    normalized_strategy = _assignment_strategy(assignment_strategy)
    normalized = channel_entry_repo.normalize_channel_assignees(assignees or [], strategy=normalized_strategy)
    rows = _FIXTURE_CHANNEL_ASSIGNEES.setdefault(int(channel_id), [])
    existing_by_staff = {_text(item.get("staff_id")): item for item in rows}
    active_staff = {item["staff_id"] for item in normalized if item["status"] == "active"}
    for item in normalized:
        row = existing_by_staff.get(item["staff_id"])
        if row is None:
            row = {"id": _NEXT_ASSIGNEE_ID, "channel_id": int(channel_id), "created_at": datetime.now(timezone.utc).isoformat()}
            _NEXT_ASSIGNEE_ID += 1
            rows.append(row)
        row.update(
            {
                "channel_id": int(channel_id),
                "staff_id": item["staff_id"],
                "display_name": item["display_name"],
                "display_name_snapshot": item["display_name_snapshot"],
                "priority": item["priority"],
                "ratio_percent": item.get("ratio_percent"),
                "max_scans_24h": item.get("max_scans_24h"),
                "status": item["status"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    for row in rows:
        if _text(row.get("status")) == "active" and _text(row.get("staff_id")) not in active_staff:
            row["status"] = "archived"
            row["updated_at"] = datetime.now(timezone.utc).isoformat()
    channel = _FIXTURE_CHANNELS[int(channel_id)]
    channel["assignment_mode"] = normalized_mode
    channel["assignment_strategy"] = normalized_strategy
    channel["overflow_policy"] = _text(overflow_policy) or "least_loaded"
    channel["updated_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "channel_id": int(channel_id),
        "assignment_mode": normalized_mode,
        "assignment_strategy": normalized_strategy,
        "overflow_policy": channel["overflow_policy"],
        "assignees": _fixture_assignees(int(channel_id)),
    }


def _fixture_insert_assignment_event(
    *,
    channel_id: int,
    assignee_staff_id: str,
    strategy: str,
    reason: str,
    external_contact_id: str = "",
    wecom_user_id: str = "",
    source_payload_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    global _NEXT_ASSIGNMENT_EVENT_ID
    now = datetime.now(timezone.utc)
    event = {
        "id": _NEXT_ASSIGNMENT_EVENT_ID,
        "channel_id": int(channel_id),
        "assignee_staff_id": _text(assignee_staff_id),
        "strategy": _text(strategy),
        "reason": _text(reason),
        "status": "assigned",
        "external_contact_id": _text(external_contact_id),
        "wecom_user_id": _text(wecom_user_id),
        "source_payload_json": dict(source_payload_json or {}),
        "assigned_at": now,
        "created_at": now,
        "updated_at": now,
    }
    _NEXT_ASSIGNMENT_EVENT_ID += 1
    _FIXTURE_ASSIGNMENT_EVENTS.append(event)
    return _serialize_assignment_event(event)


def _fixture_assignment_counts(channel_id: int, staff_ids: list[str], *, window_24h: bool = False) -> dict[str, int]:
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    counts = {staff_id: 0 for staff_id in staff_ids}
    for event in _FIXTURE_ASSIGNMENT_EVENTS:
        if int(event.get("channel_id") or 0) != int(channel_id):
            continue
        staff_id = _text(event.get("assignee_staff_id"))
        if staff_id not in counts or _text(event.get("status")) != "assigned":
            continue
        assigned_at = event.get("assigned_at")
        if isinstance(assigned_at, str):
            try:
                assigned_at = datetime.fromisoformat(assigned_at)
            except ValueError:
                assigned_at = datetime.now(timezone.utc)
        if isinstance(assigned_at, datetime) and assigned_at.tzinfo is None:
            assigned_at = assigned_at.replace(tzinfo=timezone.utc)
        if window_24h and isinstance(assigned_at, datetime) and assigned_at < cutoff:
            continue
        counts[staff_id] += 1
    return counts


def _fixture_choose_channel_assignee(
    channel_id: int,
    *,
    external_contact_id: str = "",
    wecom_user_id: str = "",
    write_event: bool = False,
    source_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    channel = _FIXTURE_CHANNELS.get(int(channel_id))
    if not channel:
        raise LookupError("channel_not_found")
    strategy = _assignment_strategy(channel.get("assignment_strategy"))
    assignees = _fixture_assignees(int(channel_id), active_only=True)
    channel_entry_repo.normalize_channel_assignees(assignees, strategy=strategy)
    staff_ids = [item["staff_id"] for item in assignees]
    selected: dict[str, Any] | None = None
    reason = ""
    if strategy == "ratio":
        counts = _fixture_assignment_counts(int(channel_id), staff_ids)
        total = sum(counts.values())
        ranked = []
        for item in assignees:
            expected = (total + 1) * int(item.get("ratio_percent") or 0) / 100
            deficit = expected - int(counts.get(item["staff_id"], 0))
            ranked.append((deficit, int(item.get("priority") or 0), int(item.get("id") or 0), item))
        ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
        selected = ranked[0][3] if ranked else None
        reason = "ratio_deficit_selected"
    elif strategy == "cap_switch":
        counts = _fixture_assignment_counts(int(channel_id), staff_ids, window_24h=True)
        for item in assignees:
            if int(counts.get(item["staff_id"], 0)) < int(item.get("max_scans_24h") or 0):
                selected = item
                reason = "cap_switch_priority_available"
                break
        if selected is None:
            return {
                "ok": False,
                "channel_id": int(channel_id),
                "assignment_strategy": strategy,
                "reason": "all_assignees_reached_24h_cap",
                "source": "ai_crm_next",
            }
    if selected is None:
        raise ValueError("active_assignees_required")
    event = None
    if write_event:
        event = _fixture_insert_assignment_event(
            channel_id=int(channel_id),
            assignee_staff_id=selected["staff_id"],
            strategy=strategy,
            reason=reason,
            external_contact_id=external_contact_id,
            wecom_user_id=wecom_user_id,
            source_payload_json=source_payload or {},
        )
    return {
        "ok": True,
        "channel_id": int(channel_id),
        "assignment_strategy": strategy,
        "assignee_staff_id": selected["staff_id"],
        "assignee": selected,
        "reason": reason,
        "event": event,
        "source": "ai_crm_next",
    }


def _list_channel_assignees_resource(channel_id: int, *, active_only: bool = False) -> list[dict[str, Any]]:
    if not _uses_postgres():
        return _fixture_assignees(int(channel_id), active_only=active_only)
    return channel_entry_repo.list_channel_assignees(int(channel_id), active_only=active_only)


def _list_assignment_stats_24h_resource(channel_id: int) -> list[dict[str, Any]]:
    if not _uses_postgres():
        return _fixture_stats_24h(int(channel_id))
    return channel_entry_repo.list_assignment_stats_24h(int(channel_id))


def _save_channel_assignees_resource(
    channel_id: int,
    *,
    assignment_mode: str,
    assignment_strategy: str,
    assignees: list[dict[str, Any]] | None,
    overflow_policy: str = "",
) -> dict[str, Any]:
    if not _uses_postgres():
        return _fixture_save_channel_assignees(
            int(channel_id),
            assignment_mode=assignment_mode,
            assignment_strategy=assignment_strategy,
            assignees=assignees,
            overflow_policy=overflow_policy,
        )
    return channel_entry_repo.save_channel_assignees(
        int(channel_id),
        assignment_mode=assignment_mode,
        assignment_strategy=assignment_strategy,
        assignees=assignees,
        overflow_policy=overflow_policy,
    )


def _list_assignment_events_resource(channel_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 50), 200))
    if not _uses_postgres():
        rows = [
            _serialize_assignment_event(item)
            for item in _FIXTURE_ASSIGNMENT_EVENTS
            if int(item.get("channel_id") or 0) == int(channel_id)
        ]
        rows.sort(key=lambda item: (_text(item.get("assigned_at")), int(item.get("id") or 0)), reverse=True)
        return rows[:safe_limit]
    return channel_entry_repo.list_assignment_events(int(channel_id), limit=safe_limit)


def _choose_channel_assignee_resource(
    channel_id: int,
    *,
    external_contact_id: str = "",
    wecom_user_id: str = "",
    write_event: bool = False,
    source_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _uses_postgres():
        return _fixture_choose_channel_assignee(
            int(channel_id),
            external_contact_id=external_contact_id,
            wecom_user_id=wecom_user_id,
            write_event=write_event,
            source_payload=source_payload or {},
        )
    return channel_entry_repo.choose_channel_assignee(
        int(channel_id),
        external_contact_id=external_contact_id,
        wecom_user_id=wecom_user_id,
        write_event=write_event,
        source_payload=source_payload or {},
    )


def _attach_assignment_payload(channel: dict[str, Any], *, include_assignees: bool = True) -> dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    if not channel_id:
        return channel
    if include_assignees:
        assignees = _list_channel_assignees_resource(channel_id, active_only=False)
        channel["assignees"] = assignees
        channel["assignment_stats_24h"] = _list_assignment_stats_24h_resource(channel_id)
        channel["assignee_count"] = len([item for item in assignees if _text(item.get("status")) == "active"])
    else:
        channel["assignee_count"] = len(_list_channel_assignees_resource(channel_id, active_only=True))
    return channel


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
    channel["assignment_mode"] = _assignment_mode(channel.get("assignment_mode"))
    channel["assignment_strategy"] = _assignment_strategy(channel.get("assignment_strategy"))
    channel["overflow_policy"] = _text(channel.get("overflow_policy")) or "least_loaded"
    channel["assignment_config_json"] = _json_dict(channel.get("assignment_config_json"))
    channel["assignees"] = list(channel.get("assignees") or [])
    channel["assignment_stats_24h"] = list(channel.get("assignment_stats_24h") or [])
    channel["assignee_count"] = int(channel.get("assignee_count") or 0)
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
        "assignment_mode": "single_owner",
        "assignment_strategy": "ratio",
        "overflow_policy": "least_loaded",
        "assignment_config_json": {},
        "assignees": [],
        "assignment_stats_24h": [],
        "assignee_count": 0,
        "welcome_image_library_ids": [],
        "welcome_miniprogram_library_ids": [],
        "welcome_attachment_library_ids": [],
        "auto_accept_friend": False,
    }


def get_channel_resource(channel_id: int) -> dict[str, Any] | None:
    conn = _connect()
    if conn is None:
        channel = _FIXTURE_CHANNELS.get(int(channel_id))
        return _attach_assignment_payload(_serialize_channel(channel), include_assignees=True) if channel else None
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
    return _attach_assignment_payload(_serialize_channel(dict(row)), include_assignees=True) if row else None


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
        return [_attach_assignment_payload(item, include_assignees=False) for item in sorted(channels, key=lambda item: int(item.get("id") or 0), reverse=True)[:limit]]
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
            return [_attach_assignment_payload(_serialize_channel(dict(row)), include_assignees=False) for row in cur.fetchall() or []]


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
    conn = _connect()
    if conn is not None:
        conn.close()
        from aicrm_next.automation_runtime_v2.channel_binding_service import bind_channels_to_program

        operator_id = _text(payload.get("operator_id") or payload.get("bound_by")) or "next_admin"
        result = bind_channels_to_program(
            int(program_id),
            normalized_ids,
            payload,
            operator_id=operator_id,
        )
        result["bindings"] = list_program_channel_bindings_resource(int(program_id))
        return result
    initial_audience_code = _text(payload.get("initial_audience_code")) or "pending_questionnaire"
    if initial_audience_code not in {"pending_questionnaire", "operating", "converted"}:
        raise ValueError("invalid_initial_audience_code")
    priority = int(payload.get("priority") or 0)
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


def _payload_value(payload: dict[str, Any], existing: dict[str, Any], key: str, *, partial: bool) -> Any:
    if partial and key not in payload:
        return existing.get(key)
    return payload.get(key)


def _coerce_channel_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None, partial: bool = False) -> dict[str, Any]:
    existing = existing or {}
    type_source = {**existing, **payload} if partial else payload
    channel_type, carrier_type = _channel_type(type_source)
    customer_channel = _text(_payload_value(payload, existing, "customer_channel", partial=partial) or _payload_value(payload, existing, "scene_value", partial=partial))
    channel_code = _text(_payload_value(payload, existing, "channel_code", partial=partial)) or _text(existing.get("channel_code"))
    scene_payload = _text(payload.get("scene_value")) if "scene_value" in payload else ""
    qr_payload = _text(payload.get("qr_url")) if "qr_url" in payload else ""
    if carrier_type != "link" and scene_payload and scene_payload != _text(existing.get("scene_value")):
        raise ValueError("scene_value_is_system_managed")
    if carrier_type != "link" and qr_payload and qr_payload != _text(existing.get("qr_url")):
        raise ValueError("qr_url_is_system_managed")
    scene_value = customer_channel if carrier_type == "link" else _text(existing.get("scene_value"))
    qr_url = _text(existing.get("qr_url")) if carrier_type != "link" else _text(_payload_value(payload, existing, "qr_url", partial=partial))
    final_url = _text(_payload_value(payload, existing, "final_url", partial=partial))
    link_url = _text(_payload_value(payload, existing, "link_url", partial=partial))
    if carrier_type == "link" and link_url and customer_channel and not final_url:
        separator = "&" if "?" in link_url else "?"
        final_url = f"{link_url}{separator}customer_channel={customer_channel}"
    assignment_config_value = _payload_value(payload, existing, "assignment_config_json", partial=partial)
    return {
        "channel_type": channel_type,
        "carrier_type": carrier_type,
        "channel_name": _text(_payload_value(payload, existing, "channel_name", partial=partial)) or channel_code or "未命名渠道",
        "channel_code": channel_code,
        "scene_value": scene_value,
        "qr_url": qr_url,
        "status": _text(_payload_value(payload, existing, "status", partial=partial)) or "active",
        "owner_staff_id": _text(_payload_value(payload, existing, "owner_staff_id", partial=partial)),
        "customer_channel": customer_channel if carrier_type == "link" else "",
        "link_url": link_url if carrier_type == "link" else "",
        "final_url": final_url if carrier_type == "link" else "",
        "welcome_message": _text(_payload_value(payload, existing, "welcome_message", partial=partial)),
        "welcome_image_library_ids": _json_list(_payload_value(payload, existing, "welcome_image_library_ids", partial=partial)),
        "welcome_miniprogram_library_ids": _json_list(_payload_value(payload, existing, "welcome_miniprogram_library_ids", partial=partial)),
        "welcome_attachment_library_ids": _json_list(_payload_value(payload, existing, "welcome_attachment_library_ids", partial=partial)),
        "auto_accept_friend": _bool(_payload_value(payload, existing, "auto_accept_friend", partial=partial), default=_bool(existing.get("auto_accept_friend"))),
        "entry_tag_id": _text(_payload_value(payload, existing, "entry_tag_id", partial=partial)),
        "entry_tag_name": _text(_payload_value(payload, existing, "entry_tag_name", partial=partial)),
        "entry_tag_group_name": _text(_payload_value(payload, existing, "entry_tag_group_name", partial=partial)),
        "assignment_mode": _assignment_mode(_payload_value(payload, existing, "assignment_mode", partial=partial)),
        "assignment_strategy": _assignment_strategy(_payload_value(payload, existing, "assignment_strategy", partial=partial)),
        "overflow_policy": _text(_payload_value(payload, existing, "overflow_policy", partial=partial)) or "least_loaded",
        "assignment_config_json": _json_dict(assignment_config_value),
    }


def _save_fixture_channel(payload: dict[str, Any], channel_id: int | None = None) -> dict[str, Any]:
    global _NEXT_ID, _FIXTURE_ASSIGNMENT_EVENTS
    existing = _FIXTURE_CHANNELS.get(int(channel_id or 0), {}) if channel_id else {}
    data = _coerce_channel_payload(payload, existing=existing, partial=bool(channel_id))
    if channel_id is None:
        channel_id = _NEXT_ID
        _NEXT_ID += 1
        _FIXTURE_CHANNEL_ASSIGNEES.pop(int(channel_id), None)
        _FIXTURE_ASSIGNMENT_EVENTS = [item for item in _FIXTURE_ASSIGNMENT_EVENTS if int(item.get("channel_id") or 0) != int(channel_id)]
    now = datetime.now(timezone.utc).isoformat()
    channel = {**existing, **data, "id": int(channel_id), "updated_at": now, "created_at": existing.get("created_at") or now}
    _FIXTURE_CHANNELS[int(channel_id)] = channel
    if "assignees" in payload:
        _fixture_save_channel_assignees(
            int(channel_id),
            assignment_mode=data["assignment_mode"],
            assignment_strategy=data["assignment_strategy"],
            overflow_policy=data["overflow_policy"],
            assignees=payload.get("assignees") or [],
        )
    return get_channel_resource(int(channel_id)) or _serialize_channel(channel)


def _save_postgres_channel(payload: dict[str, Any], channel_id: int | None = None) -> dict[str, Any]:
    existing = get_channel_resource(int(channel_id)) if channel_id else None
    if channel_id and not existing:
        raise LookupError("channel_not_found")
    data = _coerce_channel_payload(payload, existing=existing, partial=bool(channel_id))
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
        "assignment_mode",
        "assignment_strategy",
        "overflow_policy",
        "assignment_config_json",
    ]
    values = [Jsonb(data[key]) if key.endswith("_ids") else data[key] for key in columns]
    values = [Jsonb(data[key]) if key in {"assignment_config_json"} else value for key, value in zip(columns, values)]
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
    if "assignees" in payload:
        _save_channel_assignees_resource(
            saved_id,
            assignment_mode=data["assignment_mode"],
            assignment_strategy=data["assignment_strategy"],
            overflow_policy=data["overflow_policy"],
            assignees=payload.get("assignees") or [],
        )
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


_WE_COM_LINK_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
}


def reset_wecom_customer_acquisition_link_fixture_state() -> None:
    global _FIXTURE_WE_COM_LINKS, _NEXT_WE_COM_LINK_ID
    _NEXT_WE_COM_LINK_ID = 1
    now = datetime.now(timezone.utc).isoformat()
    _FIXTURE_WE_COM_LINKS = [
        {
            "id": 1,
            "link_id": "next_fixture_link",
            "link_name": "Next Fixture",
            "name": "Next Fixture",
            "description": "safe-mode local fixture",
            "link_url": "https://work.weixin.qq.com/ca/next-fixture",
            "customer_channel": "wca_next_fixture",
            "final_url": "https://work.weixin.qq.com/ca/next-fixture?customer_channel=wca_next_fixture",
            "program_id": None,
            "workflow_id": None,
            "initial_audience_code": "pending_questionnaire",
            "status": "active",
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "real_external_call_executed": False,
            "created_at": now,
            "updated_at": now,
        }
    ]
    _NEXT_WE_COM_LINK_ID = 2


def _wecom_link_common_payload(source_status: str) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": source_status,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


def _wecom_link_json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_WE_COM_LINK_HEADERS)


def _wecom_link_options(source_status: str) -> JSONResponse:
    payload = _wecom_link_common_payload(source_status)
    payload.update({"allowed": True})
    return _wecom_link_json(payload)


def _wecom_customer_channel(*, link_id: str, name: str) -> str:
    seed = _text(link_id) or _text(name) or uuid.uuid4().hex
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in seed).strip("_")
    return f"wca_{normalized[:48] or uuid.uuid4().hex[:12]}"


def _wecom_final_url(link_url: str, customer_channel: str) -> str:
    base = _text(link_url) or "https://work.weixin.qq.com/ca/next-local"
    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["customer_channel"] = customer_channel
    return urlunsplit(
        (
            parsed.scheme or "https",
            parsed.netloc or "work.weixin.qq.com",
            parsed.path or "/ca/next-local",
            urlencode(query),
            parsed.fragment,
        )
    )


async def _wecom_link_payload(request: Request) -> dict[str, Any]:
    if request.method.upper() == "GET":
        return dict(request.query_params)
    if "application/json" in _text(request.headers.get("content-type")).lower():
        body = await request.json()
        return dict(body or {}) if isinstance(body, dict) else {}
    form = await request.form()
    return dict(form)


def _wecom_link_view(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _find_wecom_link(link_id: str) -> dict[str, Any] | None:
    normalized = _text(link_id)
    for row in _FIXTURE_WE_COM_LINKS:
        if str(row.get("id")) == normalized or _text(row.get("link_id")) == normalized:
            return row
    return None


@router.api_route("/api/admin/wecom-customer-acquisition-links", methods=["GET", "POST", "OPTIONS"])
async def wecom_customer_acquisition_links(request: Request) -> JSONResponse:
    global _NEXT_WE_COM_LINK_ID
    source_status = "next_wecom_customer_acquisition_links" if request.method.upper() == "GET" else "next_command"
    if request.method.upper() == "OPTIONS":
        return _wecom_link_options(source_status)
    if request.method.upper() == "GET":
        status = _text(request.query_params.get("status"))
        links = [_wecom_link_view(row) for row in _FIXTURE_WE_COM_LINKS if not status or _text(row.get("status")) == status]
        payload = _wecom_link_common_payload(source_status)
        payload.update(
            {
                "items": links,
                "links": links,
                "count": len(links),
                "adapter_mode": "real_blocked",
                "wecom_api_called": False,
                "degraded": False,
                "warnings": [],
            }
        )
        return _wecom_link_json(payload)

    body = await _wecom_link_payload(request)
    now = datetime.now(timezone.utc).isoformat()
    link_id = _text(body.get("link_id")) or f"next_link_{_NEXT_WE_COM_LINK_ID}"
    link_name = _text(body.get("link_name")) or _text(body.get("name")) or link_id
    link_url = _text(body.get("link_url")) or "https://work.weixin.qq.com/ca/next-local"
    customer_channel = _wecom_customer_channel(link_id=link_id, name=link_name)
    row = {
        "id": _NEXT_WE_COM_LINK_ID,
        "link_id": link_id,
        "link_name": link_name,
        "name": link_name,
        "description": _text(body.get("description")),
        "link_url": link_url,
        "customer_channel": customer_channel,
        "final_url": _wecom_final_url(link_url, customer_channel),
        "program_id": int(body["program_id"]) if _text(body.get("program_id")).isdigit() else None,
        "workflow_id": int(body["workflow_id"]) if _text(body.get("workflow_id")).isdigit() else None,
        "initial_audience_code": _text(body.get("initial_audience_code")) or "pending_questionnaire",
        "status": "active",
        "adapter_mode": "real_blocked",
        "wecom_api_called": False,
        "real_external_call_executed": False,
        "created_at": now,
        "updated_at": now,
    }
    _FIXTURE_WE_COM_LINKS.insert(0, row)
    _NEXT_WE_COM_LINK_ID += 1
    payload = _wecom_link_common_payload(source_status)
    payload.update(
        {
            "command_id": f"cmd_wecom_ca_{uuid.uuid4().hex}",
            "command_name": "wecom_customer_acquisition_link.create.plan",
            "idempotency_key": _text(request.headers.get("Idempotency-Key")),
            "link": _wecom_link_view(row),
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "side_effect_plan": {
                "kind": "wecom_customer_acquisition_link_create",
                "status": "blocked",
                "reason": "real_wecom_api_blocked_by_default",
            },
        }
    )
    return _wecom_link_json(payload)


@router.api_route(
    "/api/admin/wecom-customer-acquisition-links/{link_id}",
    methods=["GET", "PATCH", "DELETE", "OPTIONS"],
)
async def wecom_customer_acquisition_link_detail(request: Request, link_id: str) -> JSONResponse:
    if request.method.upper() == "OPTIONS":
        return _wecom_link_options("next_wecom_customer_acquisition_links")
    row = _find_wecom_link(link_id)
    if not row:
        payload = _wecom_link_common_payload("next_wecom_customer_acquisition_links")
        payload.update({"ok": False, "error_code": "wecom_customer_acquisition_link_not_found", "link": {}})
        return _wecom_link_json(payload, status_code=404)
    if request.method.upper() == "GET":
        payload = _wecom_link_common_payload("next_wecom_customer_acquisition_links")
        payload.update({"link": _wecom_link_view(row), "adapter_mode": "real_blocked", "wecom_api_called": False})
        return _wecom_link_json(payload)
    if request.method.upper() == "DELETE":
        row["status"] = "disabled"
    elif request.method.upper() == "PATCH":
        body = await _wecom_link_payload(request)
        for key in ("link_name", "name", "description", "initial_audience_code"):
            if key in body:
                row[key] = _text(body.get(key))
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload = _wecom_link_common_payload("next_command")
    payload.update(
        {
            "command_id": f"cmd_wecom_ca_{uuid.uuid4().hex}",
            "link": _wecom_link_view(row),
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "side_effect_plan": {"kind": "wecom_customer_acquisition_link_mutation", "status": "blocked"},
        }
    )
    return _wecom_link_json(payload)


@router.api_route(
    "/api/admin/wecom-customer-acquisition-links/{link_id}/{action}",
    methods=["POST", "OPTIONS"],
)
async def wecom_customer_acquisition_link_action(request: Request, link_id: str, action: str) -> JSONResponse:
    if request.method.upper() == "OPTIONS":
        return _wecom_link_options("next_command")
    normalized_action = _text(action)
    row = _find_wecom_link(link_id)
    if not row:
        payload = _wecom_link_common_payload("next_command")
        payload.update({"ok": False, "error_code": "wecom_customer_acquisition_link_not_found"})
        return _wecom_link_json(payload, status_code=404)
    if normalized_action not in {"enable", "disable", "sync"}:
        payload = _wecom_link_common_payload("next_command")
        payload.update(
            {
                "ok": False,
                "error_code": "wecom_customer_acquisition_action_deprecated",
                "replacement": "/api/admin/wecom-customer-acquisition-links/{link_id}",
            }
        )
        return _wecom_link_json(payload, status_code=410)
    if normalized_action == "enable":
        row["status"] = "active"
    elif normalized_action == "disable":
        row["status"] = "disabled"
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload = _wecom_link_common_payload("next_command")
    payload.update(
        {
            "command_id": f"cmd_wecom_ca_{uuid.uuid4().hex}",
            "command_name": f"wecom_customer_acquisition_link.{normalized_action}.plan",
            "link": _wecom_link_view(row),
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "sync_executed": False,
            "side_effect_plan": {
                "kind": f"wecom_customer_acquisition_link_{normalized_action}",
                "status": "blocked",
                "reason": "real_wecom_api_blocked_by_default",
            },
        }
    )
    return _wecom_link_json(payload)


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


CHANNEL_STATUS_ONLY_PATCH_VALUES = {"active", "inactive", "archived"}


@router.patch("/api/admin/channels/{channel_id:int}")
def update_channel(channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload.keys()) == {"status"} and _text(payload.get("status")) not in CHANNEL_STATUS_ONLY_PATCH_VALUES:
        raise HTTPException(status_code=400, detail="invalid_channel_status")
    try:
        channel = _save_postgres_channel(payload, int(channel_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "channel": channel, "reason": "channel_updated", "source": "ai_crm_next"}


@router.get("/api/admin/channels/{channel_id:int}/assignees")
def get_channel_assignees(channel_id: int) -> dict[str, Any]:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return {
        "ok": True,
        "channel_id": int(channel_id),
        "assignment_mode": channel.get("assignment_mode") or "single_owner",
        "assignment_strategy": channel.get("assignment_strategy") or "ratio",
        "overflow_policy": channel.get("overflow_policy") or "least_loaded",
        "assignees": channel.get("assignees") or [],
        "stats_24h": channel.get("assignment_stats_24h") or [],
        "reason": "channel_assignees_loaded",
        "source": "ai_crm_next",
    }


@router.put("/api/admin/channels/{channel_id:int}/assignees")
def put_channel_assignees(channel_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not get_channel_resource(int(channel_id)):
        raise HTTPException(status_code=404, detail="channel_not_found")
    try:
        result = _save_channel_assignees_resource(
            int(channel_id),
            assignment_mode=_text(payload.get("assignment_mode")) or "multi_staff",
            assignment_strategy=_text(payload.get("assignment_strategy")) or "ratio",
            overflow_policy=_text(payload.get("overflow_policy")) or "least_loaded",
            assignees=payload.get("assignees") or [],
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "channel_id": int(channel_id), "reason": str(exc), "source": "ai_crm_next"},
        )
    refreshed = get_channel_resource(int(channel_id)) or {}
    return {
        "ok": True,
        "channel_id": int(channel_id),
        "assignment_mode": result.get("assignment_mode") or refreshed.get("assignment_mode"),
        "assignment_strategy": result.get("assignment_strategy") or refreshed.get("assignment_strategy"),
        "overflow_policy": result.get("overflow_policy") or refreshed.get("overflow_policy"),
        "assignees": refreshed.get("assignees") or result.get("assignees") or [],
        "stats_24h": refreshed.get("assignment_stats_24h") or [],
        "reason": "channel_assignees_saved",
        "source": "ai_crm_next",
    }


@router.get("/api/admin/channels/{channel_id:int}/assignment-events")
def get_channel_assignment_events(channel_id: int, limit: int = Query(50)) -> dict[str, Any]:
    if not get_channel_resource(int(channel_id)):
        raise HTTPException(status_code=404, detail="channel_not_found")
    return {
        "ok": True,
        "channel_id": int(channel_id),
        "events": _list_assignment_events_resource(int(channel_id), limit=max(1, min(int(limit or 50), 200))),
        "reason": "channel_assignment_events_listed",
        "source": "ai_crm_next",
    }


@router.post("/api/admin/channels/{channel_id:int}/assignment/preview")
def preview_channel_assignment(channel_id: int, payload: dict[str, Any] | None = None) -> JSONResponse:
    payload = payload or {}
    try:
        result = _choose_channel_assignee_resource(
            int(channel_id),
            external_contact_id=_text(payload.get("external_contact_id")),
            wecom_user_id=_text(payload.get("wecom_user_id")),
            write_event=bool(payload.get("write_event")),
            source_payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "channel_id": int(channel_id), "reason": str(exc), "source": "ai_crm_next"},
        )
    status_code = 409 if result.get("reason") == "all_assignees_reached_24h_cap" else 200
    return JSONResponse(status_code=status_code, content=result)


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
def bind_program_channels(program_id: int, payload: dict[str, Any], response: Response) -> dict[str, Any]:
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
    if bool(result.get("requires_batch_import")):
        response.status_code = 200
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
