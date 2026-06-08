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


def find_channel_by_historical_scene_value(scene_value: str) -> dict[str, Any] | None:
    normalized = _normalized_text(scene_value)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        WITH scene_events AS (
            SELECT external_userid, created_at
            FROM wecom_external_contact_event_logs
            WHERE change_type = 'add_external_contact'
              AND external_userid <> ''
              AND COALESCE(NULLIF(payload_json->>'State', ''), NULLIF(payload_json->>'state', '')) = ?
        ),
        channel_votes AS (
            SELECT
                m.source_channel_id AS channel_id,
                COUNT(*) AS vote_count,
                MAX(e.created_at) AS latest_event_at
            FROM scene_events e
            JOIN automation_member m ON m.external_contact_id = e.external_userid
            WHERE m.source_channel_id IS NOT NULL
            GROUP BY m.source_channel_id
        )
        SELECT c.*
        FROM channel_votes votes
        JOIN automation_channel c ON c.id = votes.channel_id
        ORDER BY votes.vote_count DESC, votes.latest_event_at DESC, c.updated_at DESC, c.id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def upsert_channel_scene_alias(
    *,
    channel_id: int,
    scene_value: str,
    corp_id: str = "",
    config_id: str = "",
    qr_url: str = "",
    carrier_type: str = "qrcode",
    provider_name: str = "wecom_contact_way",
    status: str = "active",
    source: str = "",
) -> dict[str, Any]:
    normalized_scene = _normalized_text(scene_value)
    normalized_status = _normalized_text(status) or "active"
    if not normalized_scene:
        return {}
    if normalized_status not in {"active", "retired", "revoked"}:
        normalized_status = "active"
    row = get_db().execute(
        """
        INSERT INTO automation_channel_scene_alias (
            corp_id, channel_id, scene_value, config_id, qr_url, carrier_type,
            provider_name, status, source, first_seen_at, last_seen_at,
            retired_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
            CASE WHEN ? = 'retired' THEN CURRENT_TIMESTAMP ELSE NULL END,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (corp_id, scene_value) DO UPDATE
        SET channel_id = EXCLUDED.channel_id,
            config_id = CASE WHEN EXCLUDED.config_id <> '' THEN EXCLUDED.config_id ELSE automation_channel_scene_alias.config_id END,
            qr_url = CASE WHEN EXCLUDED.qr_url <> '' THEN EXCLUDED.qr_url ELSE automation_channel_scene_alias.qr_url END,
            carrier_type = EXCLUDED.carrier_type,
            provider_name = EXCLUDED.provider_name,
            status = CASE
                WHEN automation_channel_scene_alias.status = 'revoked' THEN automation_channel_scene_alias.status
                ELSE EXCLUDED.status
            END,
            source = CASE WHEN EXCLUDED.source <> '' THEN EXCLUDED.source ELSE automation_channel_scene_alias.source END,
            last_seen_at = CURRENT_TIMESTAMP,
            retired_at = CASE
                WHEN EXCLUDED.status = 'retired' AND automation_channel_scene_alias.retired_at IS NULL THEN CURRENT_TIMESTAMP
                WHEN EXCLUDED.status <> 'retired' THEN NULL
                ELSE automation_channel_scene_alias.retired_at
            END,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            _normalized_text(corp_id),
            int(channel_id),
            normalized_scene,
            _normalized_text(config_id),
            _normalized_text(qr_url),
            _normalized_text(carrier_type) or "qrcode",
            _normalized_text(provider_name) or "wecom_contact_way",
            normalized_status,
            _normalized_text(source),
            normalized_status,
        ),
    ).fetchone()
    return dict(row) if row else {}


def find_channel_by_scene_alias(corp_id: str, scene_value: str) -> dict[str, Any] | None:
    normalized_scene = _normalized_text(scene_value)
    if not normalized_scene:
        return None
    row = _fetchone_dict(
        """
        SELECT c.*,
               a.id AS scene_alias_id,
               a.corp_id AS scene_alias_corp_id,
               a.scene_value AS scene_alias_value,
               a.status AS scene_alias_status,
               a.source AS scene_alias_source
        FROM automation_channel_scene_alias a
        JOIN automation_channel c ON c.id = a.channel_id
        WHERE a.corp_id = ?
          AND a.scene_value = ?
          AND a.status <> 'revoked'
        ORDER BY CASE WHEN a.status = 'active' THEN 0 ELSE 1 END,
                 a.updated_at DESC,
                 a.id DESC
        LIMIT 1
        """,
        (_normalized_text(corp_id), normalized_scene),
    )
    if row:
        return row
    return _fetchone_dict(
        """
        SELECT c.*,
               a.id AS scene_alias_id,
               a.corp_id AS scene_alias_corp_id,
               a.scene_value AS scene_alias_value,
               a.status AS scene_alias_status,
               a.source AS scene_alias_source
        FROM automation_channel_scene_alias a
        JOIN automation_channel c ON c.id = a.channel_id
        WHERE a.corp_id = ''
          AND a.scene_value = ?
          AND a.status <> 'revoked'
        ORDER BY CASE WHEN a.status = 'active' THEN 0 ELSE 1 END,
                 a.updated_at DESC,
                 a.id DESC
        LIMIT 1
        """,
        (normalized_scene,),
    )


def retire_previous_scene_aliases(channel_id: int, except_scene_value: str) -> int:
    normalized_scene = _normalized_text(except_scene_value)
    result = get_db().execute(
        """
        UPDATE automation_channel_scene_alias
        SET status = 'retired',
            retired_at = COALESCE(retired_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE channel_id = ?
          AND scene_value <> ?
          AND status = 'active'
        """,
        (int(channel_id), normalized_scene),
    )
    return int(getattr(result, "rowcount", 0) or 0)


def backfill_scene_alias_from_historical_vote(scene_value: str, channel_id: int) -> dict[str, Any]:
    channel = get_channel_by_id(int(channel_id)) or {}
    return upsert_channel_scene_alias(
        channel_id=int(channel_id),
        scene_value=scene_value,
        qr_url=_normalized_text(channel.get("qr_url")),
        carrier_type=_normalized_text(channel.get("carrier_type")) or "qrcode",
        status="active",
        source="historical_backfill",
    )


def get_channel_scene_aliases(channel_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_channel_scene_alias
        WHERE channel_id = ?
        ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'retired' THEN 1 ELSE 2 END,
                 updated_at DESC,
                 id DESC
        """,
        (int(channel_id),),
    )


def get_channel_entry_effect_log(effect_type: str, idempotency_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel_entry_effect_log
        WHERE effect_type = ?
          AND idempotency_key = ?
        LIMIT 1
        """,
        (_normalized_text(effect_type), _normalized_text(idempotency_key)),
    )


def upsert_channel_entry_effect_log(
    *,
    effect_type: str,
    idempotency_key: str,
    status: str,
    event_log_id: int | None = None,
    channel_id: int | None = None,
    scene_value: str = "",
    external_contact_id: str = "",
    owner_staff_id: str = "",
    reason: str = "",
    request_json: dict[str, Any] | None = None,
    response_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = _normalized_text(status) or "attempted"
    if normalized_status not in {"skipped", "attempted", "success", "failed"}:
        normalized_status = "attempted"
    row = get_db().execute(
        """
        INSERT INTO automation_channel_entry_effect_log (
            event_log_id, channel_id, scene_value, external_contact_id, owner_staff_id,
            effect_type, idempotency_key, status, reason, request_json, response_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (effect_type, idempotency_key) DO UPDATE
        SET event_log_id = COALESCE(EXCLUDED.event_log_id, automation_channel_entry_effect_log.event_log_id),
            channel_id = COALESCE(EXCLUDED.channel_id, automation_channel_entry_effect_log.channel_id),
            scene_value = CASE WHEN EXCLUDED.scene_value <> '' THEN EXCLUDED.scene_value ELSE automation_channel_entry_effect_log.scene_value END,
            external_contact_id = CASE WHEN EXCLUDED.external_contact_id <> '' THEN EXCLUDED.external_contact_id ELSE automation_channel_entry_effect_log.external_contact_id END,
            owner_staff_id = CASE WHEN EXCLUDED.owner_staff_id <> '' THEN EXCLUDED.owner_staff_id ELSE automation_channel_entry_effect_log.owner_staff_id END,
            status = EXCLUDED.status,
            reason = EXCLUDED.reason,
            request_json = EXCLUDED.request_json,
            response_json = EXCLUDED.response_json,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            int(event_log_id) if event_log_id else None,
            int(channel_id) if channel_id else None,
            _normalized_text(scene_value),
            _normalized_text(external_contact_id),
            _normalized_text(owner_staff_id),
            _normalized_text(effect_type),
            _normalized_text(idempotency_key),
            normalized_status,
            _normalized_text(reason),
            json.dumps(request_json or {}, ensure_ascii=False, default=str),
            json.dumps(response_json or {}, ensure_ascii=False, default=str),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_channel_entry_effect_logs(
    *,
    channel_id: int | None = None,
    scene_value: str = "",
    external_contact_id: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if int(channel_id or 0) > 0:
        filters.append("channel_id = ?")
        params.append(int(channel_id or 0))
    if _normalized_text(scene_value):
        filters.append("scene_value = ?")
        params.append(_normalized_text(scene_value))
    if _normalized_text(external_contact_id):
        filters.append("external_contact_id = ?")
        params.append(_normalized_text(external_contact_id))
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_channel_entry_effect_log
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params + [int(limit or 20)]),
    )


def find_entry_tag_by_historical_scene_value(scene_value: str, *, owner_staff_id: str = "") -> dict[str, str]:
    normalized = _normalized_text(scene_value)
    normalized_owner = _normalized_text(owner_staff_id)
    if not normalized:
        return {}

    def _find_tag(owner: str = "") -> dict[str, Any] | None:
        owner_filter = "AND t.userid = ?" if owner else ""
        params: tuple[Any, ...] = (normalized, owner) if owner else (normalized,)
        return _fetchone_dict(
            f"""
            WITH scene_events AS (
                SELECT external_userid, created_at
                FROM wecom_external_contact_event_logs
                WHERE change_type = 'add_external_contact'
                  AND external_userid <> ''
                  AND COALESCE(NULLIF(payload_json->>'State', ''), NULLIF(payload_json->>'state', '')) = ?
            )
            SELECT
                t.tag_id AS entry_tag_id,
                COALESCE(NULLIF(t.tag_name, ''), t.tag_id) AS entry_tag_name,
                '' AS entry_tag_group_name,
                COUNT(*) AS usage_count,
                MAX(e.created_at) AS latest_event_at
            FROM scene_events e
            JOIN contact_tags t ON t.external_userid = e.external_userid
            WHERE t.tag_id <> ''
              {owner_filter}
            GROUP BY t.tag_id, COALESCE(NULLIF(t.tag_name, ''), t.tag_id)
            ORDER BY usage_count DESC, latest_event_at DESC, entry_tag_name ASC, entry_tag_id ASC
            LIMIT 1
            """,
            params,
        )

    row = _find_tag(normalized_owner) if normalized_owner else None
    if not row:
        row = _find_tag()
    return dict(row) if row else {}


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
    raw_image_ids = (
        payload.get("welcome_image_library_ids")
        if "welcome_image_library_ids" in payload
        else (existing or {}).get("welcome_image_library_ids")
    )
    welcome_image_library_ids = json.dumps(_normalize_positive_int_list(raw_image_ids), ensure_ascii=False)
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
        welcome_image_library_ids,
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
                welcome_image_library_ids = ?,
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
                welcome_image_library_ids,
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
        saved = dict(row) if row else {}
        if saved:
            old_scene = _normalized_text((existing or {}).get("scene_value"))
            new_scene = _normalized_text(saved.get("scene_value"))
            if old_scene:
                upsert_channel_scene_alias(
                    channel_id=int(saved["id"]),
                    scene_value=old_scene,
                    qr_url=_normalized_text((existing or {}).get("qr_url")),
                    carrier_type=_normalized_text((existing or {}).get("carrier_type")) or "qrcode",
                    status="active",
                    source="generated" if _normalized_text((existing or {}).get("qr_url")) else "manual",
                )
            if new_scene:
                upsert_channel_scene_alias(
                    channel_id=int(saved["id"]),
                    scene_value=new_scene,
                    qr_url=_normalized_text(saved.get("qr_url")),
                    carrier_type=_normalized_text(saved.get("carrier_type")) or "qrcode",
                    status="active",
                    source="generated" if _normalized_text(saved.get("qr_url")) else "manual",
                )
        return saved
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
            welcome_image_library_ids,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    saved = dict(row) if row else {}
    if saved and _normalized_text(saved.get("scene_value")):
        upsert_channel_scene_alias(
            channel_id=int(saved["id"]),
            scene_value=_normalized_text(saved.get("scene_value")),
            qr_url=_normalized_text(saved.get("qr_url")),
            carrier_type=_normalized_text(saved.get("carrier_type")) or "qrcode",
            status="active",
            source="generated" if _normalized_text(saved.get("qr_url")) else "manual",
        )
    return saved


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
