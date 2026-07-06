from __future__ import annotations

import json
import re
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
        mobile: str = "",
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
            SELECT primary_external_userid AS external_userid,
                   unionid,
                   primary_openid AS openid,
                   updated_at,
                   COALESCE(mobile, '') <> '' AS mobile_bound
            FROM crm_user_identity
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_text(external_userid), _text(external_userid)),
        ).fetchone()
        if not row:
            pending = get_db().execute(
                """
                SELECT external_userid, openid, reason, updated_at
                FROM crm_user_identity_resolution_queue
                WHERE external_userid = ? AND status = 'pending'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (_text(external_userid),),
            ).fetchone()
            if pending:
                payload = _row_dict(pending)
                return {
                    **payload,
                    "exists": False,
                    "unionid_present": False,
                    "openid_present": bool(_text(payload.get("openid"))),
                    "mobile_bound": False,
                    "reason": _text(payload.get("reason")) or "identity_pending_resolution",
                }
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
        unionid = _text(record.get("unionid"))
        if not unionid:
            self.enqueue_identity_resolution(record, reason="missing_unionid")
            return 0
        row = get_db().execute(
            """
            INSERT INTO crm_user_identity (
                unionid,
                openids_json,
                external_userids_json,
                customer_name,
                avatar,
                gender,
                profile_json,
                follow_users_json,
                primary_external_userid,
                primary_openid,
                primary_owner_userid,
                identity_status,
                unionid_resolved_at,
                last_polled_at,
                legacy_sources_json,
                first_seen_at,
                last_seen_at,
                created_at,
                updated_at
            ) VALUES (
                ?,
                CASE WHEN CAST(? AS text) = '' THEN '[]'::jsonb ELSE jsonb_build_array(CAST(? AS text)) END,
                jsonb_build_array(CAST(? AS text)),
                ?,
                ?,
                ?,
                jsonb_strip_nulls(jsonb_build_object(
                    'name', NULLIF(?, ''),
                    'avatar', NULLIF(?, ''),
                    'gender', CAST(? AS text),
                    'type', CAST(? AS text),
                    'raw_profile', ?::jsonb
                )),
                CASE WHEN CAST(? AS text) = '' THEN '[]'::jsonb ELSE jsonb_build_array(jsonb_build_object('userid', CAST(? AS text))) END,
                ?,
                ?,
                ?,
                ?,
                NOW(),
                NOW(),
                jsonb_build_object('wecom_external_contact_detail', TRUE),
                NOW(),
                NOW(),
                NOW(),
                NOW()
            )
            ON CONFLICT (unionid) DO UPDATE SET
                openids_json = (
                    SELECT COALESCE(jsonb_agg(DISTINCT value), '[]'::jsonb)
                    FROM jsonb_array_elements_text(crm_user_identity.openids_json || EXCLUDED.openids_json) AS merged(value)
                ),
                external_userids_json = (
                    SELECT COALESCE(jsonb_agg(DISTINCT value), '[]'::jsonb)
                    FROM jsonb_array_elements_text(crm_user_identity.external_userids_json || EXCLUDED.external_userids_json) AS merged(value)
                ),
                customer_name = COALESCE(NULLIF(EXCLUDED.customer_name, ''), crm_user_identity.customer_name),
                avatar = COALESCE(NULLIF(EXCLUDED.avatar, ''), crm_user_identity.avatar),
                gender = COALESCE(EXCLUDED.gender, crm_user_identity.gender),
                profile_json = crm_user_identity.profile_json || EXCLUDED.profile_json,
                follow_users_json = CASE
                    WHEN jsonb_array_length(EXCLUDED.follow_users_json) > 0 THEN EXCLUDED.follow_users_json
                    ELSE crm_user_identity.follow_users_json
                END,
                primary_external_userid = COALESCE(NULLIF(EXCLUDED.primary_external_userid, ''), crm_user_identity.primary_external_userid),
                primary_openid = COALESCE(NULLIF(EXCLUDED.primary_openid, ''), crm_user_identity.primary_openid),
                primary_owner_userid = COALESCE(NULLIF(EXCLUDED.primary_owner_userid, ''), crm_user_identity.primary_owner_userid),
                identity_status = COALESCE(NULLIF(EXCLUDED.identity_status, ''), crm_user_identity.identity_status),
                unionid_resolved_at = COALESCE(crm_user_identity.unionid_resolved_at, EXCLUDED.unionid_resolved_at),
                last_polled_at = NOW(),
                legacy_sources_json = crm_user_identity.legacy_sources_json || EXCLUDED.legacy_sources_json,
                last_seen_at = NOW(),
                updated_at = NOW()
            RETURNING 1 AS id
            """,
            (
                unionid,
                _text(record.get("openid")),
                _text(record.get("openid")),
                external_userid,
                _text(record.get("name")),
                _text(record.get("avatar")),
                record.get("gender"),
                _text(record.get("name")),
                _text(record.get("avatar")),
                record.get("gender"),
                record.get("type"),
                _text(record.get("raw_profile")) or "{}",
                _text(record.get("follow_user_userid")),
                _text(record.get("follow_user_userid")),
                external_userid,
                _text(record.get("openid")),
                _text(record.get("follow_user_userid")),
                _text(record.get("status")) or "active",
            ),
        ).fetchone()
        self.mark_identity_resolution_resolved(external_userid=external_userid, unionid=unionid)
        get_db().commit()
        return int((row or {}).get("id") or 0)

    def enqueue_identity_resolution(self, record: dict[str, Any], *, reason: str) -> None:
        external_userid = _text(record.get("external_userid"))
        source_key = external_userid or _text(record.get("openid")) or _text(record.get("mobile"))
        get_db().execute(
            """
            INSERT INTO crm_user_identity_resolution_queue (
                source_type,
                source_key,
                corp_id,
                external_userid,
                openid,
                mobile,
                payload_json,
                reason,
                status,
                first_seen_at,
                last_seen_at,
                created_at,
                updated_at
            ) VALUES (
                'wecom_external_contact',
                ?,
                ?,
                ?,
                ?,
                ?,
                ?::jsonb,
                ?,
                'pending',
                NOW(),
                NOW(),
                NOW(),
                NOW()
            )
            ON CONFLICT (source_type, source_key) WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
            DO UPDATE SET
                corp_id = COALESCE(NULLIF(EXCLUDED.corp_id, ''), crm_user_identity_resolution_queue.corp_id),
                external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                openid = COALESCE(NULLIF(EXCLUDED.openid, ''), crm_user_identity_resolution_queue.openid),
                mobile = COALESCE(NULLIF(EXCLUDED.mobile, ''), crm_user_identity_resolution_queue.mobile),
                payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                reason = EXCLUDED.reason,
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            (
                source_key,
                _text(record.get("corp_id")),
                external_userid,
                _text(record.get("openid")),
                _text(record.get("mobile")),
                _json_dumps(record),
                _text(reason) or "identity_unresolved",
            ),
        )
        get_db().commit()

    def mark_identity_resolution_resolved(self, *, external_userid: str, unionid: str) -> None:
        external = _text(external_userid)
        resolved_unionid = _text(unionid)
        if not external or not resolved_unionid:
            return
        get_db().execute(
            """
            UPDATE crm_user_identity_resolution_queue
            SET status = 'resolved',
                payload_json = payload_json || jsonb_build_object('resolved_unionid', CAST(? AS text)),
                resolved_unionid = ?,
                resolved_at = NOW(),
                last_seen_at = NOW(),
                updated_at = NOW()
            WHERE external_userid = ? AND status = 'pending'
            """,
            (resolved_unionid, resolved_unionid, external),
        )

    def replace_external_contact_follow_users(
        self,
        corp_id: str,
        external_userid: str,
        follow_users: list[dict[str, Any]],
        preferred_userid: str = "",
    ) -> None:
        db = get_db()
        external = _text(external_userid)
        normalized = [dict(item or {}) for item in list(follow_users or []) if _text((item or {}).get("userid"))]
        userids = {_text(item.get("userid")) for item in normalized}
        preferred = _text(preferred_userid)
        existing_primary = db.execute(
            """
            SELECT primary_owner_userid AS user_id
            FROM crm_user_identity
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (external, external),
        ).fetchone()
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
            UPDATE crm_user_identity
            SET follow_users_json = ?::jsonb,
                primary_owner_userid = COALESCE(NULLIF(?, ''), primary_owner_userid),
                updated_at = NOW()
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            """,
            (_json_dumps(normalized), primary, external, external),
        )
        db.commit()

    def refresh_external_contact_identity_owner(self, corp_id: str, external_userid: str) -> None:
        db = get_db()
        row = db.execute(
            """
            SELECT elem->>'userid' AS user_id
            FROM crm_user_identity,
                 jsonb_array_elements(follow_users_json) AS elem
            WHERE (primary_external_userid = ? OR jsonb_exists(external_userids_json, ?))
              AND COALESCE(elem->>'userid', '') <> ''
            LIMIT 1
            """,
            (_text(external_userid), _text(external_userid)),
        ).fetchone()
        owner = _text((row or {}).get("user_id"))
        if owner:
            db.execute(
                """
                UPDATE crm_user_identity
                SET primary_owner_userid = ?,
                    identity_status = 'active',
                    last_seen_at = NOW(),
                    updated_at = NOW()
                WHERE primary_external_userid = ?
                   OR jsonb_exists(external_userids_json, ?)
                """,
                (owner, _text(external_userid), _text(external_userid)),
            )
            db.commit()

    def get_contact_binding_status(self, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
        external = _text(external_userid)
        identity = get_db().execute(
            """
            SELECT unionid,
                   mobile,
                   primary_external_userid AS external_userid,
                   primary_owner_userid AS owner_userid,
                   customer_name,
                   remark
            FROM crm_user_identity
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (external, external),
        ).fetchone()
        if identity and _text(identity.get("mobile")):
            payload = _row_dict(identity)
            return {
                "is_bound": True,
                "person_id": "",
                "unionid": _text(payload.get("unionid")),
                "external_userid": external,
                "owner_userid": _text(owner_userid) or _text(payload.get("owner_userid")),
                "customer_name": _text(payload.get("customer_name")),
                "remark": _text(payload.get("remark")),
                "display_name": _text(payload.get("customer_name")) or external,
                "mobile": _text(payload.get("mobile")),
                "third_party_user_id": "",
                "first_bound_by_userid": "",
                "first_owner_userid": "",
                "last_owner_userid": _text(owner_userid) or _text(payload.get("owner_userid")),
                "created_at": None,
                "updated_at": None,
            }
        payload = _row_dict(identity)
        return {
            "is_bound": False,
            "person_id": "",
            "unionid": _text(payload.get("unionid")),
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
        identity = get_db().execute(
            """
            SELECT unionid, openids_json
            FROM crm_user_identity
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (_text(external_userid), _text(external_userid)),
        ).fetchone()
        if not identity:
            return [], []
        raw_openids = identity.get("openids_json") or []
        if isinstance(raw_openids, str):
            try:
                raw_openids = json.loads(raw_openids)
            except json.JSONDecodeError:
                raw_openids = []
        openids = sorted({_text(value) for value in raw_openids if _text(value)})
        unionids = [_text(identity.get("unionid"))] if _text(identity.get("unionid")) else []
        return openids, unionids

    def get_unique_mobile_candidate_from_identity_sources(self, external_userid: str) -> dict[str, Any] | None:
        external = _text(external_userid)
        row = get_db().execute(
            """
            SELECT mobile_normalized AS mobile,
                   1 AS matched_count,
                   last_seen_at AS latest_matched_at,
                   ARRAY['crm_user_identity'] AS sources
            FROM crm_user_identity
            WHERE (
                primary_external_userid = ?
                OR jsonb_exists(external_userids_json, ?)
            )
              AND COALESCE(mobile_normalized, '') ~ '^1[3-9][0-9]{9}$'
            ORDER BY last_seen_at DESC NULLS LAST, updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (external, external),
        ).fetchall()
        if len(row) != 1:
            return None
        return _row_dict(row[0])

    def list_unbound_external_userids_with_identity_sources(self, limit: int = 500) -> list[str]:
        rows = get_db().execute(
            """
            SELECT DISTINCT primary_external_userid AS external_userid
            FROM crm_user_identity
            WHERE COALESCE(primary_external_userid, '') <> ''
              AND COALESCE(mobile, '') = ''
            ORDER BY primary_external_userid
            LIMIT ?
            """,
            (max(1, int(limit or 500)),),
        ).fetchall()
        return [_text(row.get("external_userid")) for row in rows if _text(row.get("external_userid"))]

    def get_or_create_person_for_mobile(self, mobile: str) -> tuple[int, str]:
        normalized = _normalize_mobile(mobile)
        if not normalized:
            raise IdentityBridgeRepositoryError("valid mobile is required")
        return 0, normalized

    def upsert_external_contact_binding_record(
        self,
        *,
        external_userid: str,
        person_id: int,
        mobile: str = "",
        bind_by_userid: str,
        owner_userid: str,
        force_rebind: bool = False,
    ) -> dict[str, Any]:
        db = get_db()
        external = _text(external_userid)
        normalized_mobile = _normalize_mobile(mobile)
        db.execute(
            """
            UPDATE crm_user_identity
            SET mobile = COALESCE(NULLIF(?, ''), mobile),
                mobile_normalized = COALESCE(NULLIF(?, ''), mobile_normalized),
                mobile_verified = TRUE,
                mobile_source = COALESCE(NULLIF(mobile_source, ''), 'legacy_binding'),
                primary_owner_userid = COALESCE(NULLIF(?, ''), primary_owner_userid),
                legacy_person_id = COALESCE(NULLIF(legacy_person_id, ''), ?),
                updated_at = NOW()
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            """,
            (
                normalized_mobile,
                normalized_mobile,
                _text(owner_userid),
                str(person_id or ""),
                external,
                external,
            ),
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
            SELECT primary_owner_userid
            FROM crm_user_identity
            WHERE primary_external_userid = ?
               OR jsonb_exists(external_userids_json, ?)
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (external, external),
        ).fetchone()
        owner = _text((row or {}).get("primary_owner_userid"))
        if owner:
            return owner
        return ""

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
        return {
            "status": "skipped",
            "reason": "customer_mobile_bound_event_required",
            "updated_count": 0,
            "action_type": "customer_mobile_bound_event",
        }

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
        return {
            "status": "skipped",
            "reason": "questionnaire_submissions_unionid_only",
            "updated_count": 0,
            "external_userid": external,
            "mobile_masked": _mask_mobile(normalized),
        }


def build_identity_bridge_repository() -> IdentityBridgeRepository:
    return PostgresIdentityBridgeRepository()
