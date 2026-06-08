from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import UUID

from aicrm_next.shared.runtime import raw_database_url

from .domain import text


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _connect():
    url = _psycopg_url(raw_database_url())
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL is required for channel_entry production repository")
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(url, row_factory=dict_row)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(json_safe(value if value is not None else {}), ensure_ascii=False)


def _json(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(json_safe(value if value is not None else {}), dumps=_json_dumps)


def find_channel_by_scene_value(scene_value: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM automation_channel
            WHERE scene_value = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (text(scene_value),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def find_channel_by_scene_alias(corp_id: str, scene_value: str) -> dict[str, Any] | None:
    sql = """
        SELECT c.*,
               a.id AS scene_alias_id,
               a.corp_id AS scene_alias_corp_id,
               a.scene_value AS scene_alias_value,
               a.status AS scene_alias_status,
               a.source AS scene_alias_source
        FROM automation_channel_scene_alias a
        JOIN automation_channel c ON c.id = a.channel_id
        WHERE a.corp_id = %s
          AND a.scene_value = %s
          AND a.status <> 'revoked'
        ORDER BY CASE WHEN a.status = 'active' THEN 0 ELSE 1 END, a.updated_at DESC, a.id DESC
        LIMIT 1
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (text(corp_id), text(scene_value)))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute(sql, ("", text(scene_value)))
        row = cur.fetchone()
        return dict(row) if row else None


def find_confirmed_channel_by_scene_alias(corp_id: str, scene_value: str) -> dict[str, Any] | None:
    allowed_sources = ("next_create_contact_way", "legacy_import_confirmed", "admin_repair_confirmed")
    sql = """
        SELECT c.*,
               a.id AS scene_alias_id,
               a.corp_id AS scene_alias_corp_id,
               a.scene_value AS scene_alias_value,
               a.status AS scene_alias_status,
               a.source AS scene_alias_source
        FROM automation_channel_scene_alias a
        JOIN automation_channel c ON c.id = a.channel_id
        WHERE a.corp_id = %s
          AND a.scene_value = %s
          AND a.status IN ('active', 'retired')
          AND a.source = ANY(%s)
        ORDER BY CASE WHEN a.status = 'active' THEN 0 ELSE 1 END, a.updated_at DESC, a.id DESC
        LIMIT 1
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (text(corp_id), text(scene_value), list(allowed_sources)))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute(sql, ("", text(scene_value), list(allowed_sources)))
        row = cur.fetchone()
        return dict(row) if row else None


def find_channel_by_historical_scene_value(scene_value: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH scene_events AS (
                SELECT external_userid, created_at
                FROM wecom_external_contact_event_logs
                WHERE change_type = 'add_external_contact'
                  AND external_userid <> ''
                  AND COALESCE(NULLIF(payload_json->>'State', ''), NULLIF(payload_json->>'state', '')) = %s
            ),
            channel_votes AS (
                SELECT m.source_channel_id AS channel_id, COUNT(*) AS vote_count, MAX(e.created_at) AS latest_event_at
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
            (text(scene_value),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def qrcode_asset_hash(qr_url: str) -> str:
    value = text(qr_url)
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def get_active_qrcode_asset(channel_id: int) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM automation_channel_qrcode_asset
            WHERE channel_id = %s
              AND status = 'active'
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (int(channel_id),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_channel_qrcode_assets(channel_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM automation_channel_qrcode_asset
            WHERE channel_id = %s
            ORDER BY generated_at DESC, id DESC
            LIMIT %s
            """,
            (int(channel_id), max(1, min(int(limit or 20), 100))),
        )
        return [dict(row) for row in cur.fetchall() or []]


def find_qrcode_asset_by_scene(corp_id: str, scene_value: str) -> dict[str, Any] | None:
    sql = """
        SELECT a.*,
               c.id AS channel_row_id,
               c.channel_code,
               c.channel_name,
               c.channel_type,
               c.carrier_type,
               c.scene_value AS channel_scene_value,
               c.qr_url AS channel_qr_url,
               c.status AS channel_status,
               c.owner_staff_id,
               c.welcome_message,
               c.welcome_image_library_ids,
               c.welcome_miniprogram_library_ids,
               c.welcome_attachment_library_ids,
               c.entry_tag_id,
               c.entry_tag_name,
               c.entry_tag_group_name
        FROM automation_channel_qrcode_asset a
        JOIN automation_channel c ON c.id = a.channel_id
        WHERE a.corp_id = %s
          AND a.scene_value = %s
        ORDER BY CASE a.status WHEN 'active' THEN 0 WHEN 'retired' THEN 1 ELSE 2 END,
                 a.generated_at DESC,
                 a.id DESC
        LIMIT 1
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (text(corp_id), text(scene_value)))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute(sql, ("", text(scene_value)))
        row = cur.fetchone()
        return dict(row) if row else None


def retire_active_qrcode_assets(channel_id: int, *, except_asset_id: int | None = None) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel_qrcode_asset
            SET status = 'retired',
                retired_at = COALESCE(retired_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE channel_id = %s
              AND status = 'active'
              AND (%s IS NULL OR id <> %s)
            """,
            (int(channel_id), except_asset_id, except_asset_id),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count


def mark_qrcode_asset_stale(channel_id: int, *, reason: str = "channel_owner_changed") -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel_qrcode_asset
            SET status = 'stale',
                provider_payload_json = provider_payload_json || %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE channel_id = %s
              AND status = 'active'
            """,
            (_json({"stale_reason": text(reason)}), int(channel_id)),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count


def insert_qrcode_asset(
    *,
    channel_id: int,
    scene_value: str,
    config_id: str,
    qr_url: str,
    corp_id: str = "",
    provider_name: str = "wecom_contact_way",
    provider_payload_json: dict[str, Any] | None = None,
    status: str = "active",
    generation_source: str = "",
    created_by: str = "",
) -> dict[str, Any]:
    normalized_status = text(status) or "active"
    if normalized_status not in {"active", "retired", "revoked", "stale", "quarantined"}:
        normalized_status = "active"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_channel_qrcode_asset (
                corp_id, channel_id, scene_value, config_id, qr_url, qr_url_hash,
                provider_name, provider_payload_json, status, generation_source,
                created_by, generated_at, retired_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP,
                    CASE WHEN %s = 'retired' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (corp_id, scene_value) DO UPDATE
            SET config_id = CASE WHEN EXCLUDED.config_id <> '' THEN EXCLUDED.config_id ELSE automation_channel_qrcode_asset.config_id END,
                qr_url = CASE WHEN EXCLUDED.qr_url <> '' THEN EXCLUDED.qr_url ELSE automation_channel_qrcode_asset.qr_url END,
                qr_url_hash = CASE WHEN EXCLUDED.qr_url_hash <> '' THEN EXCLUDED.qr_url_hash ELSE automation_channel_qrcode_asset.qr_url_hash END,
                provider_name = EXCLUDED.provider_name,
                provider_payload_json = EXCLUDED.provider_payload_json,
                status = EXCLUDED.status,
                generation_source = CASE WHEN EXCLUDED.generation_source <> '' THEN EXCLUDED.generation_source ELSE automation_channel_qrcode_asset.generation_source END,
                created_by = CASE WHEN EXCLUDED.created_by <> '' THEN EXCLUDED.created_by ELSE automation_channel_qrcode_asset.created_by END,
                retired_at = CASE WHEN EXCLUDED.status = 'retired' AND automation_channel_qrcode_asset.retired_at IS NULL THEN CURRENT_TIMESTAMP WHEN EXCLUDED.status <> 'retired' THEN NULL ELSE automation_channel_qrcode_asset.retired_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE automation_channel_qrcode_asset.channel_id = EXCLUDED.channel_id
            RETURNING *
            """,
            (
                text(corp_id),
                int(channel_id),
                text(scene_value),
                text(config_id),
                text(qr_url),
                qrcode_asset_hash(qr_url),
                text(provider_name) or "wecom_contact_way",
                _json(provider_payload_json or {}),
                normalized_status,
                text(generation_source),
                text(created_by),
                normalized_status,
            ),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                SELECT *, TRUE AS conflict, 'qrcode_asset_scene_channel_conflict' AS reason
                FROM automation_channel_qrcode_asset
                WHERE corp_id = %s AND scene_value = %s
                LIMIT 1
                """,
                (text(corp_id), text(scene_value)),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def touch_qrcode_asset_callback(asset_id: int) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel_qrcode_asset
            SET last_callback_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (int(asset_id),),
        )
        conn.commit()


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
    normalized_status = text(status) or "active"
    if normalized_status not in {"active", "retired", "revoked"}:
        normalized_status = "active"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM automation_channel_scene_alias WHERE corp_id = %s AND scene_value = %s FOR UPDATE", (text(corp_id), text(scene_value)))
        existing = cur.fetchone()
        if existing and int(existing.get("channel_id") or 0) != int(channel_id):
            return {
                **dict(existing),
                "conflict": True,
                "reason": "scene_alias_channel_conflict",
                "attempted_channel_id": int(channel_id),
            }
        if existing:
            cur.execute(
                """
                UPDATE automation_channel_scene_alias
                SET config_id = CASE WHEN %s <> '' THEN %s ELSE config_id END,
                    qr_url = CASE WHEN %s <> '' THEN %s ELSE qr_url END,
                    carrier_type = %s,
                    provider_name = %s,
                    status = CASE WHEN status = 'revoked' THEN status ELSE %s END,
                    source = CASE WHEN %s <> '' THEN %s ELSE source END,
                    last_seen_at = CURRENT_TIMESTAMP,
                    retired_at = CASE WHEN %s = 'retired' AND retired_at IS NULL THEN CURRENT_TIMESTAMP WHEN %s <> 'retired' THEN NULL ELSE retired_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (
                    text(config_id),
                    text(config_id),
                    text(qr_url),
                    text(qr_url),
                    text(carrier_type) or "qrcode",
                    text(provider_name) or "wecom_contact_way",
                    normalized_status,
                    text(source),
                    text(source),
                    normalized_status,
                    normalized_status,
                    int(existing["id"]),
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO automation_channel_scene_alias (
                    corp_id, channel_id, scene_value, config_id, qr_url, carrier_type,
                    provider_name, status, source, first_seen_at, last_seen_at,
                    retired_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    CASE WHEN %s = 'retired' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING *
                """,
                (
                    text(corp_id),
                    int(channel_id),
                    text(scene_value),
                    text(config_id),
                    text(qr_url),
                    text(carrier_type) or "qrcode",
                    text(provider_name) or "wecom_contact_way",
                    normalized_status,
                    text(source),
                    normalized_status,
                ),
            )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def retire_channel_scene_alias(channel_id: int, scene_value: str) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel_scene_alias
            SET status = 'retired', retired_at = COALESCE(retired_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP
            WHERE channel_id = %s AND scene_value = %s AND status = 'active'
            """,
            (int(channel_id), text(scene_value)),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count


def revoke_channel_scene_alias(channel_id: int, scene_value: str) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel_scene_alias
            SET status = 'revoked', updated_at = CURRENT_TIMESTAMP
            WHERE channel_id = %s AND scene_value = %s
            """,
            (int(channel_id), text(scene_value)),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count


def list_channel_scene_aliases(channel_id: int) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM automation_channel_scene_alias
            WHERE channel_id = %s
            ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'retired' THEN 1 ELSE 2 END, updated_at DESC, id DESC
            """,
            (int(channel_id),),
        )
        return [dict(row) for row in cur.fetchall() or []]


def backfill_scene_alias_from_historical_vote(scene_value: str, channel_id: int) -> dict[str, Any]:
    channel = get_channel_by_id(int(channel_id)) or {}
    return upsert_channel_scene_alias(
        channel_id=int(channel_id),
        scene_value=text(scene_value),
        qr_url=text(channel.get("qr_url")),
        carrier_type=text(channel.get("carrier_type")) or "qrcode",
        status="active",
        source="historical_backfill",
    )


def update_alias_last_seen_at(corp_id: str, scene_value: str) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel_scene_alias
            SET last_seen_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE corp_id = %s AND scene_value = %s
            """,
            (text(corp_id), text(scene_value)),
        )
        count = int(cur.rowcount or 0)
        conn.commit()
        return count


def get_channel_by_id(channel_id: int) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM automation_channel WHERE id = %s LIMIT 1", (int(channel_id),))
        row = cur.fetchone()
        return dict(row) if row else None


def update_channel_qrcode(*, channel_id: int, scene_value: str, qr_url: str, config_id: str = "") -> dict[str, Any]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE automation_channel
            SET scene_value = %s,
                qr_url = %s,
                qr_ticket = %s,
                carrier_type = CASE WHEN carrier_type = '' THEN 'qrcode' ELSE carrier_type END,
                channel_type = CASE WHEN channel_type = '' THEN 'qrcode' ELSE channel_type END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
            """,
            (text(scene_value), text(qr_url), text(config_id), int(channel_id)),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def upsert_channel_contact(*, channel_id: int, external_contact_id: str, owner_staff_id: str, source_payload: dict[str, Any]) -> dict[str, Any]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_channel_contact (
                channel_id, external_contact_id, owner_staff_id, source_payload_json,
                first_channel_entered_at, last_channel_entered_at, enter_count, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (channel_id, external_contact_id) WHERE external_contact_id <> ''
            DO UPDATE SET owner_staff_id = EXCLUDED.owner_staff_id,
                source_payload_json = EXCLUDED.source_payload_json,
                last_channel_entered_at = CURRENT_TIMESTAMP,
                enter_count = automation_channel_contact.enter_count + 1,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (int(channel_id), text(external_contact_id), text(owner_staff_id), _json(source_payload)),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def get_channel_entry_effect_log(effect_type: str, idempotency_key: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM automation_channel_entry_effect_log WHERE effect_type = %s AND idempotency_key = %s LIMIT 1",
            (text(effect_type), text(idempotency_key)),
        )
        row = cur.fetchone()
        return dict(row) if row else None


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
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_channel_entry_effect_log (
                event_log_id, channel_id, scene_value, external_contact_id, owner_staff_id,
                effect_type, idempotency_key, status, reason, request_json, response_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                event_log_id,
                channel_id,
                text(scene_value),
                text(external_contact_id),
                text(owner_staff_id),
                text(effect_type),
                text(idempotency_key),
                text(status),
                text(reason),
                _json(request_json or {}),
                _json(response_json or {}),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def list_channel_entry_effect_logs(*, channel_id: int | None = None, scene_value: str = "", limit: int = 20) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if channel_id:
        clauses.append("channel_id = %s")
        params.append(int(channel_id))
    if text(scene_value):
        clauses.append("scene_value = %s")
        params.append(text(scene_value))
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(max(1, min(int(limit or 20), 100)))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM automation_channel_entry_effect_log
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return [dict(row) for row in cur.fetchall() or []]


def list_active_bindings_for_channel(channel_id: int) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.*, p.status AS program_status, p.program_name, p.program_code
            FROM automation_program_channel_binding b
            JOIN automation_program p ON p.id = b.program_id
            WHERE b.channel_id = %s AND b.binding_status = 'active'
            ORDER BY b.priority DESC, b.id DESC
            """,
            (int(channel_id),),
        )
        return [dict(row) for row in cur.fetchall() or []]


def insert_program_admission_attempt(
    *,
    program_id: int,
    channel_id: int,
    binding_id: int | None,
    external_contact_id: str,
    trigger_type: str,
    trigger_event_id: str = "",
    trigger_payload_json: dict[str, Any] | None = None,
    admission_status: str,
    entry_reason: str,
) -> dict[str, Any]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_program_admission_attempt (
                program_id, channel_id, binding_id, external_contact_id, trigger_type, trigger_event_id,
                trigger_payload_json, admission_status, pool_entered_at, stage_code, audience_code,
                stage_entered_at, entry_reason, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            (
                int(program_id),
                int(channel_id),
                binding_id,
                text(external_contact_id),
                text(trigger_type) or "channel_enter",
                text(trigger_event_id),
                _json(trigger_payload_json or {}),
                text(admission_status),
                "operating" if admission_status == "accepted" else "",
                "operating" if admission_status == "accepted" else "",
                text(entry_reason),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def upsert_program_member(*, program_id: int, channel_id: int, binding_id: int, external_contact_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO automation_program_member (
                program_id, external_contact_id, source_channel_id, source_binding_id,
                first_source_channel_id, latest_source_channel_id, in_program,
                current_stage_code, current_audience_code, current_stage_entered_at,
                pool_entered_at, state_payload_json, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, 'operating', 'operating', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (program_id, external_contact_id) WHERE external_contact_id <> ''
            DO UPDATE SET latest_source_channel_id = EXCLUDED.latest_source_channel_id,
                source_binding_id = EXCLUDED.source_binding_id,
                state_payload_json = EXCLUDED.state_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (int(program_id), text(external_contact_id), int(channel_id), int(binding_id), int(channel_id), int(channel_id), _json(payload)),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def log_external_contact_event(
    *,
    corp_id: str,
    event_type: str,
    change_type: str,
    external_userid: str,
    user_id: str,
    event_time: int,
    event_key: str,
    payload_xml: str,
    payload_json: dict[str, Any],
) -> dict[str, Any]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wecom_external_contact_event_logs (
                corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
                payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (event_key) DO UPDATE
            SET payload_json = EXCLUDED.payload_json, updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (
                text(corp_id),
                text(event_type),
                text(change_type),
                text(external_userid),
                text(user_id),
                int(event_time or 0),
                text(event_key),
                text(payload_xml),
                _json(payload_json),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


def get_external_contact_event_log(event_log_id: int) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM wecom_external_contact_event_logs WHERE id = %s LIMIT 1", (int(event_log_id),))
        row = cur.fetchone()
        return dict(row) if row else None


def mark_event_status(event_log_id: int, status: str, error_message: str = "") -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE wecom_external_contact_event_logs
            SET process_status = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (text(status), text(error_message), int(event_log_id)),
        )
        conn.commit()


def list_recent_events(scene_value: str, limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, change_type, external_userid, user_id, process_status, error_message, created_at
            FROM wecom_external_contact_event_logs
            WHERE COALESCE(NULLIF(payload_json->>'State', ''), NULLIF(payload_json->>'state', '')) = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (text(scene_value), max(1, min(int(limit or 20), 100))),
        )
        return [dict(row) for row in cur.fetchall() or []]


def save_tag_snapshot(owner_staff_id: str, external_contact_id: str, tag_ids: list[str], tag_names: dict[str, str]) -> None:
    if not tag_ids:
        return
    with _connect() as conn, conn.cursor() as cur:
        for tag_id in tag_ids:
            cur.execute(
                """
                INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (external_userid, userid, tag_id) DO UPDATE
                SET tag_name = EXCLUDED.tag_name
                """,
                (text(external_contact_id), text(owner_staff_id), text(tag_id), text(tag_names.get(tag_id))),
            )
        conn.commit()


def decode_payload_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}
