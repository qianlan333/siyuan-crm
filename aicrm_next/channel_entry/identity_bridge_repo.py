from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Protocol

from aicrm_next.shared.postgres_connection import get_db


class IdentityBridgeRepositoryError(RuntimeError):
    pass


class IdentityBridgeRepository(Protocol):
    def identity_bridge_state(self, external_userid: str) -> dict[str, Any]: ...

    def normalize_external_contact_identity(
        self,
        corp_id: str,
        detail: dict[str, Any],
        follow_user_userid: str,
        status: str = "active",
    ) -> dict[str, Any]: ...

    def upsert_external_contact_identity(self, record: dict[str, Any]) -> int: ...

    def replace_external_contact_follow_users(
        self,
        corp_id: str,
        external_userid: str,
        follow_users: list[dict[str, Any]],
        preferred_userid: str = "",
    ) -> None: ...

    def refresh_external_contact_identity_owner(self, corp_id: str, external_userid: str) -> None: ...

    def get_contact_binding_status(self, external_userid: str, owner_userid: str = "") -> dict[str, Any]: ...

    def get_unique_mobile_candidate_from_identity_sources(self, external_userid: str) -> dict[str, Any] | None: ...

    def list_unbound_external_userids_with_identity_sources(self, limit: int = 500) -> list[str]: ...

    def get_or_create_person_for_mobile(self, mobile: str) -> tuple[int, str]: ...

    def upsert_external_contact_binding_record(
        self,
        *,
        external_userid: str,
        person_id: int,
        bind_by_userid: str,
        owner_userid: str,
        force_rebind: bool = False,
    ) -> dict[str, Any]: ...

    def resolve_binding_owner_userid(self, external_userid: str, owner_userid: str = "") -> str: ...

    def merge_lead_pool_after_mobile_bind(self, *, external_userid: str, mobile: str, owner_userid: str) -> dict[str, Any]: ...

    def backfill_questionnaire_submissions_for_mobile_binding(
        self,
        *,
        external_userid: str,
        mobile: str,
        follow_user_userid: str = "",
    ) -> dict[str, Any]: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str)


def _normalize_mobile(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) == 13 and digits.startswith("86"):
        digits = digits[2:]
    return digits if re.fullmatch(r"1[3-9][0-9]{9}", digits) else ""


def _mask_mobile(value: Any) -> str:
    digits = _normalize_mobile(value)
    if not digits:
        return ""
    return f"{digits[:3]}****{digits[-4:]}"


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row or {})


def _now_sql() -> str:
    return "NOW()"


class PostgresIdentityBridgeRepository:
    def identity_bridge_state(self, external_userid: str) -> dict[str, Any]:
        row = get_db().execute(
            """
            SELECT im.external_userid,
                   COALESCE(im.unionid, '') AS unionid,
                   COALESCE(im.openid, '') AS openid,
                   im.updated_at,
                   CASE WHEN b.external_userid IS NULL THEN FALSE ELSE TRUE END AS mobile_bound
            FROM wecom_external_contact_identity_map im
            LEFT JOIN external_contact_bindings b
              ON b.external_userid = im.external_userid
            WHERE im.external_userid = ?
            ORDER BY im.updated_at DESC, im.id DESC
            LIMIT 1
            """,
            (_text(external_userid),),
        ).fetchone()
        if not row:
            return {"exists": False, "reason": "identity_missing"}
        payload = _row_dict(row)
        payload["exists"] = True
        payload["unionid_present"] = bool(_text(payload.get("unionid")))
        payload["openid_present"] = bool(_text(payload.get("openid")))
        payload["mobile_bound"] = bool(payload.get("mobile_bound"))
        return payload

    def normalize_external_contact_identity(
        self,
        corp_id: str,
        detail: dict[str, Any],
        follow_user_userid: str,
        status: str = "active",
    ) -> dict[str, Any]:
        payload = dict(detail or {})
        contact = dict(payload.get("external_contact") or payload)
        follow_users = list(payload.get("follow_user") or [])
        selected_follow_user: dict[str, Any] = {}
        preferred = _text(follow_user_userid)
        for item in follow_users:
            candidate = dict(item or {})
            if preferred and _text(candidate.get("userid")) == preferred:
                selected_follow_user = candidate
                break
        if not selected_follow_user and follow_users:
            selected_follow_user = dict(follow_users[0] or {})
        selected_userid = preferred or _text(selected_follow_user.get("userid"))
        return {
            "corp_id": _text(corp_id),
            "external_userid": _text(contact.get("external_userid")),
            "unionid": _text(contact.get("unionid")),
            "openid": _text(contact.get("openid")),
            "follow_user_userid": selected_userid,
            "name": _text(contact.get("name")),
            "type": contact.get("type"),
            "avatar": _text(contact.get("avatar")),
            "gender": contact.get("gender"),
            "status": _text(status) or "active",
            "raw_profile": _json_dumps(payload),
        }

    def upsert_external_contact_identity(self, record: dict[str, Any]) -> int:
        external_userid = _text(record.get("external_userid"))
        if not external_userid:
            raise IdentityBridgeRepositoryError("external_userid is required")
        row = get_db().execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid,
                name, type, avatar, gender, status, raw_profile,
                first_seen_at, last_seen_at, created_at, updated_at
            ) VALUES (
                ?, ?, NULLIF(?, ''), NULLIF(?, ''), NULLIF(?, ''),
                NULLIF(?, ''), ?, NULLIF(?, ''), ?, NULLIF(?, ''), ?::jsonb,
                NOW(), NOW(), NOW(), NOW()
            )
            ON CONFLICT (corp_id, external_userid) DO UPDATE SET
                unionid = COALESCE(NULLIF(EXCLUDED.unionid, ''), wecom_external_contact_identity_map.unionid),
                openid = COALESCE(NULLIF(EXCLUDED.openid, ''), wecom_external_contact_identity_map.openid),
                follow_user_userid = COALESCE(NULLIF(EXCLUDED.follow_user_userid, ''), wecom_external_contact_identity_map.follow_user_userid),
                name = COALESCE(NULLIF(EXCLUDED.name, ''), wecom_external_contact_identity_map.name),
                type = EXCLUDED.type,
                avatar = COALESCE(NULLIF(EXCLUDED.avatar, ''), wecom_external_contact_identity_map.avatar),
                gender = EXCLUDED.gender,
                status = COALESCE(NULLIF(EXCLUDED.status, ''), wecom_external_contact_identity_map.status),
                raw_profile = EXCLUDED.raw_profile,
                last_seen_at = NOW(),
                updated_at = NOW()
            RETURNING id
            """,
            (
                _text(record.get("corp_id")),
                external_userid,
                _text(record.get("unionid")),
                _text(record.get("openid")),
                _text(record.get("follow_user_userid")),
                _text(record.get("name")),
                record.get("type"),
                _text(record.get("avatar")),
                record.get("gender"),
                _text(record.get("status")) or "active",
                _text(record.get("raw_profile")) or "{}",
            ),
        ).fetchone()
        get_db().commit()
        return int((row or {}).get("id") or 0)

    def replace_external_contact_follow_users(
        self,
        corp_id: str,
        external_userid: str,
        follow_users: list[dict[str, Any]],
        preferred_userid: str = "",
    ) -> None:
        db = get_db()
        corp = _text(corp_id)
        external = _text(external_userid)
        normalized = [dict(item or {}) for item in list(follow_users or []) if _text((item or {}).get("userid"))]
        existing_primary = db.execute(
            """
            SELECT user_id
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND external_userid = ? AND is_primary = TRUE
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp, external),
        ).fetchone()
        userids = {_text(item.get("userid")) for item in normalized}
        preferred = _text(preferred_userid)
        old_primary = _text((existing_primary or {}).get("user_id"))
        if preferred and preferred in userids:
            primary = preferred
        elif old_primary and old_primary in userids:
            primary = old_primary
        elif normalized:
            primary = _text(normalized[0].get("userid"))
        else:
            primary = ""

        db.execute(
            """
            UPDATE wecom_external_contact_follow_users
            SET relation_status = 'inactive',
                is_primary = FALSE,
                updated_at = NOW()
            WHERE corp_id = ? AND external_userid = ?
            """,
            (corp, external),
        )
        for item in normalized:
            userid = _text(item.get("userid"))
            db.execute(
                """
                INSERT INTO wecom_external_contact_follow_users (
                    corp_id, external_userid, user_id, relation_status, is_primary,
                    remark, description, add_way, state, oper_userid, createtime,
                    raw_follow_user, created_at, updated_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?::jsonb, NOW(), NOW())
                ON CONFLICT (corp_id, external_userid, user_id) DO UPDATE SET
                    relation_status = 'active',
                    is_primary = EXCLUDED.is_primary,
                    remark = EXCLUDED.remark,
                    description = EXCLUDED.description,
                    add_way = EXCLUDED.add_way,
                    state = EXCLUDED.state,
                    oper_userid = EXCLUDED.oper_userid,
                    createtime = EXCLUDED.createtime,
                    raw_follow_user = EXCLUDED.raw_follow_user,
                    updated_at = NOW()
                """,
                (
                    corp,
                    external,
                    userid,
                    userid == primary,
                    _text(item.get("remark")),
                    _text(item.get("description")),
                    item.get("add_way"),
                    _text(item.get("state")),
                    _text(item.get("oper_userid")),
                    item.get("createtime"),
                    _json_dumps(item),
                ),
            )
        db.commit()

    def refresh_external_contact_identity_owner(self, corp_id: str, external_userid: str) -> None:
        db = get_db()
        row = db.execute(
            """
            SELECT user_id
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND external_userid = ? AND relation_status = 'active'
            ORDER BY is_primary DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (_text(corp_id), _text(external_userid)),
        ).fetchone()
        owner = _text((row or {}).get("user_id"))
        if owner:
            db.execute(
                """
                UPDATE wecom_external_contact_identity_map
                SET follow_user_userid = ?,
                    status = 'active',
                    last_seen_at = NOW(),
                    updated_at = NOW()
                WHERE corp_id = ? AND external_userid = ?
                """,
                (owner, _text(corp_id), _text(external_userid)),
            )
            db.commit()

    def get_contact_binding_status(self, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
        external = _text(external_userid)
        row = get_db().execute(
            """
            SELECT b.external_userid,
                   b.person_id,
                   b.first_bound_by_userid,
                   b.first_owner_userid,
                   b.last_owner_userid,
                   b.created_at,
                   b.updated_at,
                   p.mobile,
                   p.third_party_user_id,
                   c.owner_userid,
                   c.customer_name,
                   c.remark
            FROM external_contact_bindings b
            JOIN people p ON p.id = b.person_id
            LEFT JOIN contacts c ON c.external_userid = b.external_userid
            WHERE b.external_userid = ?
            LIMIT 1
            """,
            (external,),
        ).fetchone()
        if row:
            payload = _row_dict(row)
            payload["is_bound"] = True
            payload["display_name"] = _text(payload.get("customer_name")) or _text(payload.get("remark")) or external
            return payload
        contact = get_db().execute(
            """
            SELECT external_userid, owner_userid, customer_name, remark
            FROM contacts
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (external,),
        ).fetchone()
        payload = _row_dict(contact)
        return {
            "is_bound": False,
            "person_id": None,
            "external_userid": external,
            "owner_userid": _text(owner_userid) or _text(payload.get("owner_userid")),
            "customer_name": _text(payload.get("customer_name")),
            "remark": _text(payload.get("remark")),
            "display_name": _text(payload.get("customer_name")) or _text(payload.get("remark")) or external,
            "mobile": "",
            "third_party_user_id": "",
            "first_bound_by_userid": "",
            "first_owner_userid": "",
            "last_owner_userid": "",
            "created_at": None,
            "updated_at": None,
        }

    def _identity_sources(self, external_userid: str) -> tuple[list[str], list[str]]:
        rows = get_db().execute(
            """
            SELECT COALESCE(openid, '') AS openid, COALESCE(unionid, '') AS unionid
            FROM wecom_external_contact_identity_map
            WHERE external_userid = ?
            """,
            (_text(external_userid),),
        ).fetchall()
        openids = sorted({_text(row.get("openid")) for row in rows if _text(row.get("openid"))})
        unionids = sorted({_text(row.get("unionid")) for row in rows if _text(row.get("unionid"))})
        return openids, unionids

    def get_unique_mobile_candidate_from_identity_sources(self, external_userid: str) -> dict[str, Any] | None:
        external = _text(external_userid)
        openids, unionids = self._identity_sources(external)
        row = get_db().execute(
            """
            WITH candidates AS (
                SELECT
                    CASE
                        WHEN LENGTH(regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g')) = 13
                             AND regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g') LIKE '86%'
                        THEN SUBSTRING(regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g') FROM 3)
                        ELSE regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g')
                    END AS mobile,
                    'wechat_pay_orders' AS source,
                    created_at AS matched_at
                FROM wechat_pay_orders
                WHERE COALESCE(mobile_snapshot, '') <> ''
                  AND (status = 'paid' OR trade_state = 'SUCCESS')
                  AND (
                    external_userid = ?
                    OR payer_openid = ANY(?::text[])
                    OR unionid = ANY(?::text[])
                    OR respondent_key = ANY(?::text[])
                  )
                UNION ALL
                SELECT
                    CASE
                        WHEN LENGTH(regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g')) = 13
                             AND regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g') LIKE '86%'
                        THEN SUBSTRING(regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g') FROM 3)
                        ELSE regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g')
                    END AS mobile,
                    'questionnaire_submissions' AS source,
                    submitted_at AS matched_at
                FROM questionnaire_submissions
                WHERE COALESCE(mobile_snapshot, '') <> ''
                  AND (
                    external_userid = ?
                    OR openid = ANY(?::text[])
                    OR unionid = ANY(?::text[])
                    OR respondent_key = ANY(?::text[])
                    OR respondent_key = ANY(?::text[])
                  )
            ),
            grouped AS (
                SELECT mobile,
                       COUNT(*) AS matched_count,
                       MAX(matched_at) AS latest_matched_at,
                       ARRAY_AGG(DISTINCT source ORDER BY source) AS sources
                FROM candidates
                WHERE mobile ~ '^1[3-9][0-9]{9}$'
                GROUP BY mobile
            )
            SELECT *
            FROM grouped
            ORDER BY latest_matched_at DESC NULLS LAST
            """,
            (
                external,
                openids,
                unionids,
                unionids,
                external,
                openids,
                unionids,
                unionids,
                openids,
            ),
        ).fetchall()
        if len(row) != 1:
            return None
        return _row_dict(row[0])

    def list_unbound_external_userids_with_identity_sources(self, limit: int = 500) -> list[str]:
        rows = get_db().execute(
            """
            SELECT DISTINCT im.external_userid
            FROM wecom_external_contact_identity_map im
            LEFT JOIN external_contact_bindings b ON b.external_userid = im.external_userid
            WHERE b.external_userid IS NULL
              AND im.external_userid IS NOT NULL
              AND im.external_userid <> ''
              AND (COALESCE(im.unionid, '') <> '' OR COALESCE(im.openid, '') <> '')
            ORDER BY im.external_userid
            LIMIT ?
            """,
            (max(1, int(limit or 500)),),
        ).fetchall()
        return [_text(row.get("external_userid")) for row in rows if _text(row.get("external_userid"))]

    def get_or_create_person_for_mobile(self, mobile: str) -> tuple[int, str]:
        normalized = _normalize_mobile(mobile)
        if not normalized:
            raise IdentityBridgeRepositoryError("valid mobile is required")
        row = get_db().execute(
            "SELECT id, mobile FROM people WHERE mobile = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row:
            return int(row.get("id") or 0), _text(row.get("mobile"))
        inserted = get_db().execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, '', NOW(), NOW())
            RETURNING id, mobile
            """,
            (normalized,),
        ).fetchone()
        return int((inserted or {}).get("id") or 0), _text((inserted or {}).get("mobile"))

    def upsert_external_contact_binding_record(
        self,
        *,
        external_userid: str,
        person_id: int,
        bind_by_userid: str,
        owner_userid: str,
        force_rebind: bool = False,
    ) -> dict[str, Any]:
        db = get_db()
        external = _text(external_userid)
        existing = db.execute(
            """
            SELECT external_userid, person_id
            FROM external_contact_bindings
            WHERE external_userid = ?
            LIMIT 1
            """,
            (external,),
        ).fetchone()
        if existing and force_rebind:
            db.execute(
                """
                UPDATE external_contact_bindings
                SET person_id = ?,
                    last_owner_userid = ?,
                    updated_at = NOW()
                WHERE external_userid = ?
                """,
                (int(person_id), _text(owner_userid), external),
            )
        elif not existing:
            db.execute(
                """
                INSERT INTO external_contact_bindings (
                    external_userid, person_id, first_bound_by_userid,
                    first_owner_userid, last_owner_userid, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NOW(), NOW())
                """,
                (external, int(person_id), _text(bind_by_userid), _text(owner_userid), _text(owner_userid)),
            )
        db.commit()
        return self.get_contact_binding_status(external, owner_userid)

    def resolve_binding_owner_userid(self, external_userid: str, owner_userid: str = "") -> str:
        owner = _text(owner_userid)
        if owner:
            return owner
        external = _text(external_userid)
        row = get_db().execute(
            """
            SELECT owner_userid
            FROM contacts
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (external,),
        ).fetchone()
        owner = _text((row or {}).get("owner_userid"))
        if owner:
            return owner
        row = get_db().execute(
            """
            SELECT follow_user_userid
            FROM wecom_external_contact_identity_map
            WHERE external_userid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (external,),
        ).fetchone()
        owner = _text((row or {}).get("follow_user_userid"))
        if owner:
            return owner
        row = get_db().execute(
            """
            SELECT user_id
            FROM wecom_external_contact_follow_users
            WHERE external_userid = ? AND relation_status = 'active'
            ORDER BY is_primary DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (external,),
        ).fetchone()
        return _text((row or {}).get("user_id"))

    def table_columns(self, table_name: str) -> set[str]:
        try:
            rows = get_db().execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = ?
                """,
                (_text(table_name),),
            ).fetchall()
            return {_text(row.get("column_name")) for row in rows if _text(row.get("column_name"))}
        except Exception:
            get_db().rollback()
            return set()

    def merge_lead_pool_after_mobile_bind(self, *, external_userid: str, mobile: str, owner_userid: str) -> dict[str, Any]:
        columns = self.table_columns("user_ops_pool_current")
        required = {"external_userid"}
        writable = [name for name in ("mobile", "owner_userid", "updated_at") if name in columns]
        if not required.issubset(columns) or not writable:
            return {"status": "skipped", "reason": "table_or_column_missing", "updated_count": 0}
        assignments: list[str] = []
        params: list[Any] = []
        if "mobile" in writable:
            assignments.append("mobile = ?")
            params.append(_normalize_mobile(mobile))
        if "owner_userid" in writable:
            assignments.append("owner_userid = ?")
            params.append(_text(owner_userid))
        if "updated_at" in writable:
            assignments.append(f"updated_at = {_now_sql()}")
        params.append(_text(external_userid))
        cursor = get_db().execute(
            f"""
            UPDATE user_ops_pool_current
            SET {", ".join(assignments)}
            WHERE external_userid = ?
            """,
            tuple(params),
        )
        get_db().commit()
        return {"status": "updated", "updated_count": max(0, int(cursor.rowcount or 0))}

    def backfill_questionnaire_submissions_for_mobile_binding(
        self,
        *,
        external_userid: str,
        mobile: str,
        follow_user_userid: str = "",
    ) -> dict[str, Any]:
        external = _text(external_userid)
        normalized = _normalize_mobile(mobile)
        if not external or not normalized:
            return {"status": "skipped", "reason": "invalid_external_userid_or_mobile", "updated_count": 0}
        openids, unionids = self._identity_sources(external)
        ids = get_db().execute(
            """
            WITH candidates AS (
                SELECT id
                FROM questionnaire_submissions
                WHERE COALESCE(external_userid, '') = ''
                  AND (
                    CASE
                        WHEN LENGTH(regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g')) = 13
                             AND regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g') LIKE '86%'
                        THEN SUBSTRING(regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g') FROM 3)
                        ELSE regexp_replace(COALESCE(mobile_snapshot, ''), '[^0-9]', '', 'g')
                    END = ?
                    OR openid = ANY(?::text[])
                    OR unionid = ANY(?::text[])
                    OR respondent_key = ANY(?::text[])
                    OR respondent_key = ANY(?::text[])
                  )
                ORDER BY submitted_at DESC NULLS LAST, id DESC
                LIMIT 200
            )
            UPDATE questionnaire_submissions qs
            SET external_userid = ?,
                follow_user_userid = CASE
                    WHEN COALESCE(qs.follow_user_userid, '') = '' THEN ?
                    ELSE qs.follow_user_userid
                END,
                matched_by = CASE
                    WHEN COALESCE(qs.matched_by, '') = '' THEN 'mobile'
                    ELSE qs.matched_by
                END
            FROM candidates
            WHERE qs.id = candidates.id
            RETURNING qs.id
            """,
            (
                normalized,
                openids,
                unionids,
                unionids,
                openids,
                external,
                _text(follow_user_userid),
            ),
        ).fetchall()
        get_db().commit()
        count = len(ids)
        return {
            "status": "updated" if count else "skipped",
            "reason": "" if count else "no_matching_submission",
            "updated_count": count,
            "external_userid": external,
            "mobile_masked": _mask_mobile(normalized),
        }


def build_identity_bridge_repository() -> IdentityBridgeRepository:
    return PostgresIdentityBridgeRepository()
