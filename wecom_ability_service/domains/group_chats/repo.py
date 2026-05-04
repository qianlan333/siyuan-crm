from __future__ import annotations

from typing import Any

from ...db import get_db


def upsert_group_chats(group_chats: list[dict[str, Any]]) -> tuple[int, int]:
    db = get_db()
    inserted = 0
    updated = 0
    for item in group_chats:
        chat_id = item.get("chat_id", "")
        if not chat_id:
            continue
        existing = db.execute(
            """
            SELECT group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload
            FROM group_chats
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO group_chats (
                chat_id, group_name, owner_userid, notice, member_count, status,
                create_time, dismissed_at, raw_payload, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                group_name = excluded.group_name,
                owner_userid = excluded.owner_userid,
                notice = excluded.notice,
                member_count = excluded.member_count,
                status = excluded.status,
                create_time = excluded.create_time,
                dismissed_at = excluded.dismissed_at,
                raw_payload = excluded.raw_payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                chat_id,
                item.get("group_name", ""),
                item.get("owner_userid", ""),
                item.get("notice", ""),
                int(item.get("member_count", 0)),
                item.get("status", "active"),
                item.get("create_time", ""),
                item.get("dismissed_at", ""),
                item.get("raw_payload", "{}"),
            ),
        )
        if existing is None:
            inserted += 1
        elif any(
            [
                existing.get("group_name") != item.get("group_name", ""),
                existing.get("owner_userid") != item.get("owner_userid", ""),
                existing.get("notice") != item.get("notice", ""),
                int(existing.get("member_count") or 0) != int(item.get("member_count", 0)),
                existing.get("status") != item.get("status", "active"),
                existing.get("create_time") != item.get("create_time", ""),
                existing.get("dismissed_at") != item.get("dismissed_at", ""),
                existing.get("raw_payload") != item.get("raw_payload", "{}"),
            ]
        ):
            updated += 1
    db.commit()
    return inserted, updated


def get_group_chat_by_chat_id(chat_id: str):
    return get_db().execute(
        """
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
        WHERE chat_id = ?
        """,
        (chat_id,),
    ).fetchone()


def get_group_chat_map(chat_ids: list[str]) -> dict[str, dict[str, Any]]:
    unique_ids = [chat_id for chat_id in dict.fromkeys(chat_ids) if chat_id]
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    rows = get_db().execute(
        f"""
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
        WHERE chat_id IN ({placeholders})
        """,
        tuple(unique_ids),
    ).fetchall()
    return {row["chat_id"]: row for row in rows}


def list_group_chats(status: str | None = None):
    sql = """
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
    """
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY updated_at DESC, id DESC"
    return get_db().execute(sql, tuple(params)).fetchall()


def count_group_chats() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM group_chats").fetchone()
    return int(row["total"]) if row else 0
