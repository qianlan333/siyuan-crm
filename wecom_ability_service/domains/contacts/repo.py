from __future__ import annotations

from typing import Any

from ...db import get_db


def upsert_contacts(contacts: list[dict[str, Any]]) -> tuple[int, int]:
    db = get_db()
    inserted = 0
    updated = 0
    for item in contacts:
        if not item.get("external_userid"):
            continue
        existing = db.execute(
            """
            SELECT customer_name, owner_userid, remark, description
            FROM contacts
            WHERE external_userid = ?
            """,
            (item["external_userid"],),
        ).fetchone()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(external_userid) DO UPDATE SET
                customer_name = excluded.customer_name,
                owner_userid = excluded.owner_userid,
                remark = excluded.remark,
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                item["external_userid"],
                item.get("customer_name", ""),
                item.get("owner_userid", ""),
                item.get("remark", ""),
                item.get("description", ""),
            ),
        )
        if existing is None:
            inserted += 1
        elif (
            existing.get("customer_name") != item.get("customer_name", "")
            or existing.get("owner_userid") != item.get("owner_userid", "")
            or existing.get("remark") != item.get("remark", "")
            or existing.get("description") != item.get("description", "")
        ):
            updated += 1
    db.commit()
    return inserted, updated


def list_contacts(owner_userid: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
    """
    params: list[Any] = []
    if owner_userid:
        sql += " WHERE owner_userid = ?"
        params.append(owner_userid)
    sql += " ORDER BY updated_at DESC, id DESC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return list(rows)


def get_contact_row_by_external_userid(external_userid: str):
    return get_db().execute(
        """
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
        WHERE external_userid = ?
        """,
        (str(external_userid or "").strip(),),
    ).fetchone()


def update_contact_description_snapshot(external_userid: str, description: str) -> None:
    get_db().execute(
        """
        UPDATE contacts
        SET description = ?, updated_at = CURRENT_TIMESTAMP
        WHERE external_userid = ?
        """,
        (description, external_userid),
    )
    get_db().commit()


def count_contacts() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM contacts").fetchone()
    return int(row["total"]) if row else 0


def get_last_contacts_sync_time() -> str:
    row = get_db().execute("SELECT MAX(updated_at) AS updated_at FROM contacts").fetchone()
    return row["updated_at"] if row and row["updated_at"] else ""
