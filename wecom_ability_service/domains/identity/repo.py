from __future__ import annotations

import json

from ...db import get_db


def list_identity_external_userids_for_corp(corp_id: str) -> list[str]:
    rows = get_db().execute(
        """
        SELECT external_userid
        FROM wecom_external_contact_identity_map
        WHERE corp_id = ?
        ORDER BY external_userid ASC
        """,
        (corp_id,),
    ).fetchall()
    return [str(row.get("external_userid") or "").strip() for row in rows if str(row.get("external_userid") or "").strip()]


def replace_external_contact_follow_users(
    corp_id: str,
    external_userid: str,
    follow_users: list[dict[str, object]],
    *,
    preferred_userid: str = "",
) -> None:
    if not corp_id or not external_userid:
        return
    db = get_db()
    normalized_follow_users = [item for item in (follow_users or []) if item.get("userid")]
    preferred_found = any(item.get("userid") == preferred_userid for item in normalized_follow_users)
    existing_primary = db.execute(
        """
        SELECT user_id
        FROM wecom_external_contact_follow_users
        WHERE corp_id = ? AND external_userid = ? AND is_primary = TRUE
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (corp_id, external_userid),
    ).fetchone()
    existing_primary_userid = existing_primary["user_id"] if existing_primary else ""
    existing_primary_found = any(item.get("userid") == existing_primary_userid for item in normalized_follow_users)
    if preferred_found:
        primary_userid = preferred_userid
    elif existing_primary_found:
        primary_userid = existing_primary_userid
    else:
        primary_userid = normalized_follow_users[0].get("userid", "") if normalized_follow_users else ""

    db.execute(
        """
        UPDATE wecom_external_contact_follow_users
        SET relation_status = 'inactive',
            is_primary = FALSE,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (corp_id, external_userid),
    )

    for item in normalized_follow_users:
        user_id = item.get("userid", "")
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description,
                add_way, state, oper_userid, createtime, raw_follow_user, first_seen_at, last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(corp_id, external_userid, user_id) DO UPDATE SET
                relation_status = 'active',
                is_primary = excluded.is_primary,
                remark = excluded.remark,
                description = excluded.description,
                add_way = excluded.add_way,
                state = excluded.state,
                oper_userid = excluded.oper_userid,
                createtime = excluded.createtime,
                raw_follow_user = excluded.raw_follow_user,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                corp_id,
                external_userid,
                user_id,
                user_id == primary_userid,
                item.get("remark", "") or "",
                item.get("description", "") or "",
                item.get("add_way"),
                item.get("state", "") or "",
                item.get("oper_userid", "") or "",
                item.get("createtime"),
                json.dumps(item, ensure_ascii=False),
            ),
        )
    db.commit()


def mark_external_contact_follow_user_status(corp_id: str, external_userid: str, *, user_id: str = "", status: str) -> None:
    db = get_db()
    if user_id:
        db.execute(
            """
            UPDATE wecom_external_contact_follow_users
            SET relation_status = ?,
                is_primary = FALSE,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE corp_id = ? AND external_userid = ? AND user_id = ?
            """,
            (status, corp_id, external_userid, user_id),
        )
    else:
        db.execute(
            """
            UPDATE wecom_external_contact_follow_users
            SET relation_status = ?,
                is_primary = FALSE,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE corp_id = ? AND external_userid = ?
            """,
            (status, corp_id, external_userid),
        )
    db.commit()


def refresh_external_contact_identity_owner(corp_id: str, external_userid: str) -> None:
    db = get_db()
    active_primary = db.execute(
        """
        SELECT user_id
        FROM wecom_external_contact_follow_users
        WHERE corp_id = ? AND external_userid = ? AND relation_status = 'active'
        ORDER BY is_primary DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (corp_id, external_userid),
    ).fetchone()
    next_owner = active_primary["user_id"] if active_primary else ""
    next_status = "active" if next_owner else "inactive"
    db.execute(
        """
        UPDATE wecom_external_contact_identity_map
        SET follow_user_userid = ?,
            status = ?,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (next_owner, next_status, corp_id, external_userid),
    )
    db.commit()


def upsert_external_contact_identity(record: dict[str, object]) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO wecom_external_contact_identity_map (
            corp_id, external_userid, unionid, openid, follow_user_userid, name, type, avatar, gender,
            status, raw_profile, first_seen_at, last_seen_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(corp_id, external_userid) DO UPDATE SET
            unionid = CASE WHEN excluded.unionid <> '' THEN excluded.unionid ELSE wecom_external_contact_identity_map.unionid END,
            openid = CASE WHEN excluded.openid <> '' THEN excluded.openid ELSE wecom_external_contact_identity_map.openid END,
            follow_user_userid = CASE WHEN excluded.follow_user_userid <> '' THEN excluded.follow_user_userid ELSE wecom_external_contact_identity_map.follow_user_userid END,
            name = excluded.name,
            type = excluded.type,
            avatar = excluded.avatar,
            gender = excluded.gender,
            status = excluded.status,
            raw_profile = excluded.raw_profile,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (
            record.get("corp_id", ""),
            record.get("external_userid", ""),
            record.get("unionid", ""),
            record.get("openid", ""),
            record.get("follow_user_userid", ""),
            record.get("name", ""),
            record.get("type"),
            record.get("avatar", ""),
            record.get("gender"),
            record.get("status", "active"),
            record.get("raw_profile", "{}"),
        ),
    ).fetchone()
    db.commit()
    return int(row["id"])


def mark_external_contact_identity_status(corp_id: str, external_userid: str, *, status: str, follow_user_userid: str = "") -> None:
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_identity_map
        SET status = ?,
            follow_user_userid = CASE WHEN ? <> '' THEN ? ELSE follow_user_userid END,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (status, follow_user_userid, follow_user_userid, corp_id, external_userid),
    )
    db.commit()


def count_external_contact_identity_maps() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM wecom_external_contact_identity_map").fetchone()
    return int(row["total"]) if row else 0


def resolve_external_contact_identity_row(corp_id: str, *, unionid: str = "", openid: str = "", external_userid: str = ""):
    db = get_db()
    if unionid:
        row = db.execute(
            """
            SELECT id AS identity_map_id, external_userid, unionid, openid, follow_user_userid, status
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND unionid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, unionid),
        ).fetchone()
        if row:
            return row
    if openid:
        row = db.execute(
            """
            SELECT id AS identity_map_id, external_userid, unionid, openid, follow_user_userid, status
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND openid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, openid),
        ).fetchone()
        if row:
            return row
    if external_userid:
        return db.execute(
            """
            SELECT id AS identity_map_id, external_userid, unionid, openid, follow_user_userid, status
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND external_userid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, external_userid),
        ).fetchone()
    return None


def update_identity_openid_unionid(corp_id: str, external_userid: str, openid: str, unionid: str) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_identity_map
        SET openid = ?,
            unionid = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (openid, unionid, corp_id, external_userid),
    )
    db.commit()


def get_primary_follow_user_row(corp_id: str, external_userid: str, active_value: bool | int):
    return get_db().execute(
        """
        SELECT user_id
        FROM wecom_external_contact_follow_users
        WHERE corp_id = ? AND external_userid = ? AND relation_status = 'active' AND is_primary = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (corp_id, str(external_userid or "").strip(), active_value),
    ).fetchone()


def resolve_person_identity_row_by_external_userid(corp_id: str, external_userid: str):
    db = get_db()
    queries = [
        (
            """
            SELECT
                p.id AS person_id,
                p.mobile,
                b.external_userid,
                b.first_bound_by_userid,
                b.first_owner_userid,
                b.last_owner_userid,
                c.customer_name,
                c.owner_userid,
                c.remark,
                m.unionid,
                m.openid,
                m.follow_user_userid
            FROM external_contact_bindings b
            LEFT JOIN people p ON p.id = b.person_id
            LEFT JOIN contacts c ON c.external_userid = b.external_userid
            LEFT JOIN wecom_external_contact_identity_map m
              ON m.corp_id = ? AND m.external_userid = b.external_userid
            WHERE b.external_userid = ?
            ORDER BY m.updated_at DESC NULLS LAST, m.id DESC NULLS LAST
            LIMIT 1
            """,
            (corp_id, external_userid),
        ),
        (
            """
            SELECT
                NULL AS person_id,
                '' AS mobile,
                c.external_userid,
                '' AS first_bound_by_userid,
                '' AS first_owner_userid,
                '' AS last_owner_userid,
                c.customer_name,
                c.owner_userid,
                c.remark,
                COALESCE(m.unionid, '') AS unionid,
                COALESCE(m.openid, '') AS openid,
                COALESCE(m.follow_user_userid, '') AS follow_user_userid
            FROM contacts c
            LEFT JOIN wecom_external_contact_identity_map m
              ON m.corp_id = ? AND m.external_userid = c.external_userid
            WHERE c.external_userid = ?
            ORDER BY m.updated_at DESC NULLS LAST, m.id DESC NULLS LAST
            LIMIT 1
            """,
            (corp_id, external_userid),
        ),
        (
            """
            SELECT
                NULL AS person_id,
                '' AS mobile,
                external_userid,
                '' AS first_bound_by_userid,
                '' AS first_owner_userid,
                '' AS last_owner_userid,
                name AS customer_name,
                '' AS owner_userid,
                '' AS remark,
                COALESCE(unionid, '') AS unionid,
                COALESCE(openid, '') AS openid,
                COALESCE(follow_user_userid, '') AS follow_user_userid
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND external_userid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, external_userid),
        ),
    ]
    for sql, params in queries:
        row = db.execute(sql, params).fetchone()
        if row:
            return row
    return None


def resolve_person_identity_row_by_mobile(corp_id: str, mobile: str):
    return get_db().execute(
        """
        SELECT
            p.id AS person_id,
            p.mobile,
            COALESCE(b.external_userid, '') AS external_userid,
            COALESCE(b.first_bound_by_userid, '') AS first_bound_by_userid,
            COALESCE(b.first_owner_userid, '') AS first_owner_userid,
            COALESCE(b.last_owner_userid, '') AS last_owner_userid,
            COALESCE(c.customer_name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            COALESCE(c.remark, '') AS remark,
            COALESCE(m.unionid, '') AS unionid,
            COALESCE(m.openid, '') AS openid,
            COALESCE(m.follow_user_userid, '') AS follow_user_userid
        FROM people p
        LEFT JOIN external_contact_bindings b ON b.person_id = p.id
        LEFT JOIN contacts c ON c.external_userid = b.external_userid
        LEFT JOIN wecom_external_contact_identity_map m
          ON m.corp_id = ? AND m.external_userid = b.external_userid
        WHERE p.mobile = ?
        ORDER BY b.updated_at DESC NULLS LAST, m.updated_at DESC NULLS LAST, b.external_userid ASC
        LIMIT 1
        """,
        (corp_id, mobile),
    ).fetchone()


def resolve_person_identity_row_by_unionid(corp_id: str, unionid: str):
    return get_db().execute(
        """
        SELECT
            p.id AS person_id,
            p.mobile,
            m.external_userid,
            COALESCE(b.first_bound_by_userid, '') AS first_bound_by_userid,
            COALESCE(b.first_owner_userid, '') AS first_owner_userid,
            COALESCE(b.last_owner_userid, '') AS last_owner_userid,
            COALESCE(c.customer_name, m.name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            COALESCE(c.remark, '') AS remark,
            COALESCE(m.unionid, '') AS unionid,
            COALESCE(m.openid, '') AS openid,
            COALESCE(m.follow_user_userid, '') AS follow_user_userid
        FROM wecom_external_contact_identity_map m
        LEFT JOIN external_contact_bindings b ON b.external_userid = m.external_userid
        LEFT JOIN people p ON p.id = b.person_id
        LEFT JOIN contacts c ON c.external_userid = m.external_userid
        WHERE m.corp_id = ? AND m.unionid = ?
        ORDER BY b.updated_at DESC NULLS LAST, m.updated_at DESC NULLS LAST, m.id DESC
        LIMIT 1
        """,
        (corp_id, unionid),
    ).fetchone()


def get_contact_binding_row(external_userid: str):
    return get_db().execute(
        """
        SELECT
            b.external_userid,
            b.person_id,
            b.first_bound_by_userid,
            b.first_owner_userid,
            b.last_owner_userid,
            b.created_at,
            b.updated_at,
            p.mobile,
            p.third_party_user_id
        FROM external_contact_bindings b
        JOIN people p ON p.id = b.person_id
        WHERE b.external_userid = ?
        """,
        (str(external_userid or "").strip(),),
    ).fetchone()


def get_or_create_person_for_mobile(mobile: str) -> tuple[int, str]:
    db = get_db()
    person = db.execute(
        """
        SELECT id, third_party_user_id
        FROM people
        WHERE mobile = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (mobile,),
    ).fetchone()
    if person:
        return int(person["id"]), str(person.get("third_party_user_id") or "").strip()
    created = db.execute(
        """
        INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
        VALUES (?, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (mobile,),
    ).fetchone()
    return int(created["id"]), ""


def upsert_external_contact_binding_record(
    *,
    existing: dict[str, object],
    external_userid: str,
    owner_userid: str,
    bind_by_userid: str,
    person_id: int,
    force_rebind: bool,
) -> None:
    db = get_db()
    if existing.get("is_bound") and force_rebind:
        db.execute(
            """
            UPDATE external_contact_bindings
            SET person_id = ?,
                last_owner_userid = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE external_userid = ?
            """,
            (person_id, owner_userid, external_userid),
        )
        return
    db.execute(
        """
        INSERT INTO external_contact_bindings (
            external_userid,
            person_id,
            first_bound_by_userid,
            first_owner_userid,
            last_owner_userid,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (external_userid, person_id, bind_by_userid, owner_userid, owner_userid),
    )


def update_person_third_party_user_id(person_id: int, third_party_user_id: str) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE people
        SET third_party_user_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (third_party_user_id, person_id),
    )
    db.commit()
