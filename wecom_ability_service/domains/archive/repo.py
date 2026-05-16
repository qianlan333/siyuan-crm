from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from ...db import get_db


def count_archived_messages() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM archived_messages").fetchone()
    return int(row["total"]) if row else 0


def insert_archived_messages(messages: list[dict[str, Any]], *, commit: bool = True) -> int:
    return len(insert_archived_messages_detailed(messages, commit=commit))


def insert_archived_messages_detailed(messages: list[dict[str, Any]], *, commit: bool = True) -> list[dict[str, Any]]:
    db = get_db()
    inserted_rows: list[dict[str, Any]] = []
    for normalized in messages:
        sql = """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                msgtype, content, send_time, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (msgid) DO NOTHING
        """
        cursor = db.execute(
            sql,
            (
                normalized["seq"],
                normalized["msgid"],
                normalized["chat_type"],
                normalized["external_userid"],
                normalized["owner_userid"],
                normalized["sender"],
                normalized["receiver"],
                normalized["msgtype"],
                normalized["content"],
                normalized["send_time"],
                normalized["raw_payload"],
            ),
        )
        if cursor.rowcount:
            inserted_rows.append(dict(normalized))
    if commit:
        db.commit()
    return inserted_rows


def create_sync_run(start_time: str, end_time: str, owner_userid: str, cursor: str) -> int:
    db = get_db()
    cursor_row = db.execute(
        """
        INSERT INTO sync_runs (status, start_time, end_time, owner_userid, cursor)
        VALUES ('running', ?, ?, ?, ?)
        RETURNING id
        """,
        (start_time, end_time, owner_userid, cursor),
    )
    row = cursor_row.fetchone()
    db.commit()
    return int(row["id"])


def finish_sync_run(
    run_id: int,
    status: str,
    fetched_count: int,
    inserted_count: int,
    raw_response: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE sync_runs
        SET status = ?, fetched_count = ?, inserted_count = ?, raw_response = ?,
            error_message = ?, finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            status,
            fetched_count,
            inserted_count,
            json.dumps(raw_response, ensure_ascii=False) if raw_response is not None else None,
            error_message,
            run_id,
        ),
    )
    db.commit()


def fetch_messages_by_user_rows(external_userid: str, chat_type: str | None = None):
    sql = """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ?
    """
    params: list[Any] = [external_userid]
    if chat_type:
        sql += " AND chat_type = ?"
        params.append(chat_type)
    sql += " ORDER BY send_time ASC, id ASC"
    return get_db().execute(sql, tuple(params)).fetchall()


def fetch_recent_messages_by_user_rows(external_userid: str, limit: int, chat_type: str | None = None):
    sql = """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ?
    """
    params: list[Any] = [external_userid]
    if chat_type:
        sql += " AND chat_type = ?"
        params.append(chat_type)
    sql += " ORDER BY send_time DESC, id DESC LIMIT ?"
    params.append(limit)
    return get_db().execute(sql, tuple(params)).fetchall()


def search_messages_rows(external_userid: str, keyword: str):
    return get_db().execute(
        """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ? AND content LIKE ?
        ORDER BY send_time ASC, id ASC
        """,
        (external_userid, f"%{keyword}%"),
    ).fetchall()


def list_archived_messages_by_window(start_time: str, end_time: str, owner_userid: str, cursor: str = "", limit: int = 100):
    db = get_db()
    offset = int(cursor or "0")
    rows = db.execute(
        """
        SELECT seq, msgid, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE send_time >= ? AND send_time <= ? AND owner_userid = ?
        ORDER BY send_time ASC, id ASC
        LIMIT ? OFFSET ?
        """,
        (start_time, end_time, owner_userid, limit + 1, offset),
    ).fetchall()
    return rows, offset


def get_archive_last_seq() -> int:
    row = get_db().execute("SELECT last_seq FROM archive_sync_state WHERE state_key = 'global'").fetchone()
    return int(row["last_seq"]) if row else 0


def set_archive_last_seq(last_seq: int, *, commit: bool = True) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO archive_sync_state (state_key, last_seq, updated_at)
        VALUES ('global', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(state_key) DO UPDATE SET
            last_seq = excluded.last_seq,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(last_seq),),
    )
    if commit:
        db.commit()


def get_last_sync_run():
    return get_db().execute(
        """
        SELECT id, status, owner_userid, fetched_count, inserted_count, error_message, created_at, finished_at
        FROM sync_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def _parse_send_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _batch_window_for_send_time(send_time: str, window_minutes: int = 3) -> tuple[str, str, str]:
    dt = _parse_send_time(send_time)
    floored_minute = (dt.minute // window_minutes) * window_minutes
    window_start_dt = dt.replace(minute=floored_minute, second=0, microsecond=0)
    window_end_dt = window_start_dt + timedelta(minutes=window_minutes) - timedelta(seconds=1)
    window_start = window_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    window_end = window_end_dt.strftime("%Y-%m-%d %H:%M:%S")
    batch_key = f"{window_start}->{window_end}"
    return window_start, window_end, batch_key


def materialize_message_batches(window_minutes: int = 3) -> dict[str, int]:
    db = get_db()
    rows = db.execute(
        """
        SELECT am.id, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.send_time, am.raw_payload
        FROM archived_messages am
        LEFT JOIN message_batch_items mbi ON mbi.message_id = am.id
        WHERE mbi.message_id IS NULL
        ORDER BY am.send_time ASC, am.id ASC
        """
    ).fetchall()
    if not rows:
        return {"created_batches": 0, "added_items": 0}
    created_batches = 0
    added_items = 0
    batch_cache: dict[str, int] = {}
    for row in rows:
        window_start, window_end, batch_key = _batch_window_for_send_time(row["send_time"], window_minutes=window_minutes)
        batch_id = batch_cache.get(batch_key)
        if batch_id is None:
            existing = db.execute("SELECT id FROM message_batches WHERE batch_key = ?", (batch_key,)).fetchone()
            if existing:
                batch_id = int(existing["id"])
            else:
                inserted = db.execute(
                    """
                    INSERT INTO message_batches (batch_key, window_start, window_end, status, message_count)
                    VALUES (?, ?, ?, 'pending', 0)
                    RETURNING id
                    """,
                    (batch_key, window_start, window_end),
                ).fetchone()
                batch_id = int(inserted["id"])
                created_batches += 1
            batch_cache[batch_key] = batch_id
        payload: dict[str, Any] = {}
        raw_payload = row.get("raw_payload")
        if isinstance(raw_payload, dict):
            payload = raw_payload
        elif raw_payload:
            try:
                payload = json.loads(raw_payload)
            except (TypeError, json.JSONDecodeError):
                payload = {}
        chat_id = ((payload.get("decrypted_message") or {}).get("roomid")) or ""
        cursor = db.execute(
            """
            INSERT INTO message_batch_items (
                batch_id, message_id, msgid, chat_type, chat_id, external_userid, owner_userid, send_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (message_id) DO NOTHING
            """,
            (
                batch_id,
                row["id"],
                row["msgid"],
                row.get("chat_type", "private"),
                chat_id,
                row.get("external_userid", ""),
                row.get("owner_userid", ""),
                row["send_time"],
            ),
        )
        if cursor.rowcount:
            added_items += 1
            db.execute(
                """
                UPDATE message_batches
                SET message_count = message_count + 1
                WHERE id = ?
                """,
                (batch_id,),
            )
    db.commit()
    return {"created_batches": created_batches, "added_items": added_items}


def list_message_batches(status: str = "pending", limit: int = 20, cursor: str = "") -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    cursor_id = int(cursor or 0)
    rows = get_db().execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE status = ? AND id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (status, cursor_id, safe_limit + 1),
    ).fetchall()
    items = list(rows[:safe_limit])
    next_cursor = str(items[-1]["id"]) if len(rows) > safe_limit and items else ""
    return {"items": items, "next_cursor": next_cursor}


def get_message_batch(batch_id: int, *, limit: int = 200, cursor: str = ""):
    db = get_db()
    batch = db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
    if not batch:
        return None
    safe_limit = max(1, min(int(limit), 500))
    cursor_id = int(cursor or 0)
    rows = db.execute(
        """
        SELECT am.seq, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.sender, am.receiver,
               am.msgtype, am.content, am.send_time, am.raw_payload, mbi.id AS batch_item_id
        FROM message_batch_items mbi
        JOIN archived_messages am ON am.id = mbi.message_id
        WHERE mbi.batch_id = ? AND mbi.id > ?
        ORDER BY mbi.id ASC
        LIMIT ?
        """,
        (int(batch_id), cursor_id, safe_limit + 1),
    ).fetchall()
    return batch, rows, safe_limit, str(cursor or "")


def ack_message_batch(batch_id: int, ack_note: str = "", acked_by: str = ""):
    db = get_db()
    existing = db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
    if not existing:
        return None
    db.execute(
        """
        UPDATE message_batches
        SET status = 'acked',
            acked_at = COALESCE(acked_at, CURRENT_TIMESTAMP),
            ack_note = CASE WHEN ? <> '' THEN ? ELSE COALESCE(ack_note, '') END,
            acked_by = CASE WHEN ? <> '' THEN ? ELSE COALESCE(acked_by, '') END
        WHERE id = ?
        """,
        (ack_note, ack_note, acked_by, acked_by, int(batch_id)),
    )
    db.commit()
    return db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
