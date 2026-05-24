from __future__ import annotations

import json
from typing import Any

from ...db import get_db
from ._repo_helpers import *  # noqa: F401,F403  helpers + _AUTOMATION_SOP_POOL_LOCK_NAMESPACE constant
from .agents.repo import *  # noqa: F401,F403  agent_* repo functions extracted in 阶段 4.2
from ._repo_messaging import *  # noqa: F401,F403  message_activity / archived_messages — 阶段 4.3
from ._repo_sop import *  # noqa: F401,F403  sop_* — 阶段 4.4
from ._repo_focus_send import *  # noqa: F401,F403  focus_send_* — 阶段 4.4
from ._repo_reply_monitor import *  # noqa: F401,F403  reply_monitor_* — 阶段 4.4
from ._repo_laohuang import *  # noqa: F401,F403  laohuang_chat_* — 阶段 4.4
from ._repo_member import *  # noqa: F401,F403  member/person/stage/segment — 阶段 4.5
from ._repo_event import *  # noqa: F401,F403  event/ai_push_log/touch_delivery — 阶段 4.5
from ._repo_customer_acquisition import *  # noqa: F401,F403  WeCom 获客助手链接绑定

def list_app_setting_rows(keys: list[str]) -> list[dict[str, Any]]:
    normalized_keys = [_normalized_text(item) for item in keys if _normalized_text(item)]
    if not normalized_keys:
        return []
    placeholders = ",".join("?" for _ in normalized_keys)
    return _fetchall_dicts(
        f"""
        SELECT key, value, updated_at
        FROM app_settings
        WHERE key IN ({placeholders})
        ORDER BY updated_at DESC, key ASC
        """,
        tuple(normalized_keys),
    )


def get_default_channel(*, program_id: int | None = None, allow_legacy_fallback: bool = True) -> dict[str, Any] | None:
    if program_id is not None:
        row = _fetchone_dict(
            """
            SELECT *
            FROM automation_channel
            WHERE program_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(program_id),),
        )
        if row:
            return row
        if not allow_legacy_fallback:
            return None
        return _fetchone_dict(
            """
            SELECT *
            FROM automation_channel
            WHERE channel_code = ?
              AND program_id IS NULL
            LIMIT 1
            """,
            ("default_qrcode",),
        )
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE channel_code = 'default_qrcode'
        LIMIT 1
        """
    )


def list_channels_by_program(program_id: int, *, include_inactive: bool = True) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_channel
        WHERE program_id = ?
    """
    params: list[Any] = [int(program_id)]
    if not include_inactive:
        sql += " AND status IN ('active', 'configured')"
    sql += " ORDER BY updated_at DESC, id DESC"
    return _fetchall_dicts(sql, tuple(params))


def list_product_lead_channels() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT
            c.*,
            p.program_code,
            p.program_name,
            p.status AS program_status
        FROM automation_channel c
        LEFT JOIN automation_program p ON p.id = c.program_id
        WHERE c.qr_url <> ''
          AND c.status IN ('active', 'configured')
        ORDER BY c.updated_at DESC, c.id DESC
        """
    )


def get_channel_by_id(channel_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE id = ?
        LIMIT 1
        """,
        (int(channel_id),),
    )


def _normalize_positive_int_list(value: Any, *, max_count: int = 9) -> list[int]:
    if value in (None, ""):
        return []
    raw = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except (TypeError, ValueError):
            raw = [part.strip() for part in value.split(",")]
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
    return ids[:max_count]


def find_channel_by_scene_value(scene_value: str) -> dict[str, Any] | None:
    normalized = _normalized_text(scene_value)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE scene_value = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def save_channel(payload: dict[str, Any]) -> dict[str, Any]:
    program_id = int(payload.get("program_id") or 0) or None
    channel_code = _normalized_text(payload.get("channel_code"))
    if program_id and channel_code == "default_qrcode":
        channel_code = f"program_{program_id}_default_qrcode"
    is_default_channel_code = channel_code == "default_qrcode" or bool(
        program_id and channel_code == f"program_{program_id}_default_qrcode"
    )
    existing = get_default_channel(program_id=program_id, allow_legacy_fallback=False) if is_default_channel_code else None
    db = get_db()
    raw_attachment_ids = (
        payload.get("welcome_attachment_library_ids")
        if "welcome_attachment_library_ids" in payload
        else (existing or {}).get("welcome_attachment_library_ids")
    )
    welcome_attachment_library_ids = json.dumps(_normalize_positive_int_list(raw_attachment_ids), ensure_ascii=False)
    raw_miniprogram_ids = (
        payload.get("welcome_miniprogram_library_ids")
        if "welcome_miniprogram_library_ids" in payload
        else (existing or {}).get("welcome_miniprogram_library_ids")
    )
    welcome_miniprogram_library_ids = json.dumps(_normalize_positive_int_list(raw_miniprogram_ids), ensure_ascii=False)
    params = (
        program_id,
        channel_code,
        _normalized_text(payload.get("channel_name")),
        _normalized_text(payload.get("channel_type")) or "qrcode",
        _normalized_text(payload.get("carrier_type")) or "qrcode",
        _normalized_text(payload.get("qr_url")),
        _normalized_text(payload.get("qr_ticket")),
        _normalized_text(payload.get("scene_value")),
        _normalized_text(payload.get("customer_channel")),
        _normalized_text(payload.get("link_url")),
        _normalized_text(payload.get("final_url")),
        _normalized_text(payload.get("welcome_message")),
        welcome_miniprogram_library_ids,
        welcome_attachment_library_ids,
        _db_bool(bool(payload.get("auto_accept_friend"))),
        _normalized_text(payload.get("entry_tag_id")),
        _normalized_text(payload.get("entry_tag_name")),
        _normalized_text(payload.get("entry_tag_group_name")),
        _normalized_text(payload.get("owner_staff_id")),
        _normalized_text(payload.get("status")),
    )
    if existing:
        row = db.execute(
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
                welcome_miniprogram_library_ids = ?,
                welcome_attachment_library_ids = ?,
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
                program_id,
                channel_code,
                _normalized_text(payload.get("channel_name")),
                _normalized_text(payload.get("channel_type")) or "qrcode",
                _normalized_text(payload.get("carrier_type")) or "qrcode",
                _normalized_text(payload.get("qr_url")),
                _normalized_text(payload.get("qr_ticket")),
                _normalized_text(payload.get("scene_value")),
                _normalized_text(payload.get("customer_channel")),
                _normalized_text(payload.get("link_url")),
                _normalized_text(payload.get("final_url")),
                _normalized_text(payload.get("welcome_message")),
                welcome_miniprogram_library_ids,
                welcome_attachment_library_ids,
                _db_bool(bool(payload.get("auto_accept_friend"))),
                _normalized_text(payload.get("entry_tag_id")),
                _normalized_text(payload.get("entry_tag_name")),
                _normalized_text(payload.get("entry_tag_group_name")),
                _normalized_text(payload.get("owner_staff_id")),
                _normalized_text(payload.get("status")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_channel (
            program_id,
            channel_code,
            channel_name,
            channel_type,
            carrier_type,
            qr_url,
            qr_ticket,
            scene_value,
            customer_channel,
            link_url,
            final_url,
            welcome_message,
            welcome_miniprogram_library_ids,
            welcome_attachment_library_ids,
            auto_accept_friend,
            entry_tag_id,
            entry_tag_name,
            entry_tag_group_name,
            owner_staff_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def get_latest_questionnaire_submission(
    *,
    questionnaire_id: int,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
) -> dict[str, Any] | None:
    normalized_external_contact_ids = [
        _normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)
    ]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = [int(questionnaire_id)]
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    sql = """
    SELECT *
    FROM questionnaire_submissions
    WHERE questionnaire_id = ?
      AND (
    """
    sql += " OR ".join(filters)
    sql += """
      )
    ORDER BY submitted_at DESC, id DESC
    LIMIT 1
    """
    return _fetchone_dict(sql, tuple(params))


def get_latest_any_questionnaire_submission(
    *,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
) -> dict[str, Any] | None:
    normalized_external_contact_ids = [
        _normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)
    ]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    sql = """
    SELECT *
    FROM questionnaire_submissions
    WHERE (
    """
    sql += " OR ".join(filters)
    sql += """
      )
    ORDER BY submitted_at DESC, id DESC
    LIMIT 1
    """
    return _fetchone_dict(sql, tuple(params))


def list_questionnaire_submission_answers(submission_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM questionnaire_submission_answers
        WHERE submission_id = ?
        ORDER BY id ASC
        """,
        (int(submission_id),),
    )
