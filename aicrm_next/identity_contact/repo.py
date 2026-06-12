from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol

from aicrm_next.shared.runtime import database_mode, raw_database_url

from .dto import ContactPoint, IdentityResolution, ResolvePersonIdentityRequest


class IdentityBindingRepository(Protocol):
    def bind_mobile_to_external_contact(
        self,
        *,
        external_userid: str,
        mobile: str,
        owner_userid: str = "",
        bind_by_userid: str = "",
        customer_name: str = "",
        force_rebind: bool = False,
    ) -> dict[str, Any]: ...


class FixtureIdentityRepository:
    def __init__(self) -> None:
        self._people = [
            IdentityResolution(
                person_id="person_001",
                external_userid="wx_ext_001",
                mobile="13800138000",
                openid="openid_001",
                unionid="unionid_001",
                binding_status="bound",
                owner_userid="ZhaoYanFang",
                contact_points=[
                    ContactPoint(type="wecom_external_userid", value="wx_ext_001", verified=True),
                    ContactPoint(type="mobile", value="13800138000", verified=True),
                ],
            ),
            IdentityResolution(
                person_id="person_002",
                external_userid="wx_ext_002",
                mobile=None,
                openid="openid_002",
                unionid="unionid_002",
                binding_status="unbound",
                owner_userid="LiuXiao",
                contact_points=[ContactPoint(type="wecom_external_userid", value="wx_ext_002", verified=True)],
            ),
            IdentityResolution(
                person_id="person_003",
                external_userid=None,
                mobile="13900139000",
                binding_status="mobile_only",
                owner_userid=None,
                contact_points=[ContactPoint(type="mobile", value="13900139000", verified=False)],
            ),
        ]

    def resolve(self, query: ResolvePersonIdentityRequest) -> IdentityResolution | None:
        for person in self._people:
            if query.external_userid and person.external_userid == query.external_userid:
                return person
            if query.mobile and person.mobile == query.mobile:
                return person
            if query.openid and person.openid == query.openid:
                return person
            if query.unionid and person.unionid == query.unionid:
                return person
        return None


class FixtureIdentityBindingRepository:
    source_status = "fixture_identity_binding"

    def __init__(self) -> None:
        self._bindings: dict[str, dict[str, Any]] = {}

    def bind_mobile_to_external_contact(
        self,
        *,
        external_userid: str,
        mobile: str,
        owner_userid: str = "",
        bind_by_userid: str = "",
        customer_name: str = "",
        force_rebind: bool = False,
    ) -> dict[str, Any]:
        person_id = f"fixture_person_{mobile[-4:]}"
        self._bindings[external_userid] = {
            "person_id": person_id,
            "external_userid": external_userid,
            "mobile": mobile,
            "owner_userid": owner_userid,
            "bind_by_userid": bind_by_userid,
            "customer_name": customer_name,
        }
        return {
            "ok": True,
            "source_status": self.source_status,
            "external_userid": external_userid,
            "mobile": mobile,
            "person_id": person_id,
            "binding_status": "bound",
            "side_effect_executed": False,
        }


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class PostgresIdentityRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._database_url, row_factory=dict_row)

    def resolve(self, query: ResolvePersonIdentityRequest) -> IdentityResolution | None:
        lookups = [
            ("external_userid", _text(query.external_userid)),
            ("unionid", _text(query.unionid)),
            ("openid", _text(query.openid)),
        ]
        with self._connect() as conn:
            for field, value in lookups:
                if not value:
                    continue
                row = conn.execute(
                    f"""
                    SELECT id AS identity_map_id,
                           external_userid,
                           unionid,
                           openid,
                           follow_user_userid,
                           follow_user_userid AS owner_userid,
                           status
                    FROM wecom_external_contact_identity_map
                    WHERE {field} = %s
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (value,),
                ).fetchone()
                if row:
                    return self._from_identity_map(row, matched_by=field, mobile=_text(query.mobile))
            mobile = _text(query.mobile)
            if mobile:
                row = conn.execute(
                    """
                    SELECT b.person_id,
                           b.external_userid,
                           p.mobile,
                           b.last_owner_userid AS owner_userid,
                           im.id AS identity_map_id,
                           im.unionid,
                           im.openid,
                           im.follow_user_userid
                    FROM people p
                    JOIN external_contact_bindings b ON b.person_id = p.id
                    LEFT JOIN wecom_external_contact_identity_map im ON im.external_userid = b.external_userid
                    WHERE p.mobile = %s
                    ORDER BY b.updated_at DESC NULLS LAST, b.external_userid DESC
                    LIMIT 1
                    """,
                    (mobile,),
                ).fetchone()
                if row:
                    return self._from_identity_map(row, matched_by="mobile", mobile=mobile)
        return None

    def _from_identity_map(self, row, *, matched_by: str, mobile: str = "") -> IdentityResolution:
        external_userid = _text(row.get("external_userid"))
        unionid = _text(row.get("unionid")) or None
        openid = _text(row.get("openid")) or None
        follow_user_userid = _text(row.get("follow_user_userid"))
        contact_points = []
        if external_userid:
            contact_points.append(ContactPoint(type="wecom_external_userid", value=external_userid, verified=True))
        if unionid:
            contact_points.append(ContactPoint(type="wechat_unionid", value=unionid, verified=True))
        if openid:
            contact_points.append(ContactPoint(type="wechat_openid", value=openid, verified=True))
        if mobile:
            contact_points.append(ContactPoint(type="mobile", value=mobile, verified=True))
        return IdentityResolution(
            person_id=str(row.get("person_id")) if row.get("person_id") is not None else None,
            external_userid=external_userid or None,
            mobile=mobile or _text(row.get("mobile")) or None,
            openid=openid,
            unionid=unionid,
            binding_status="bound" if external_userid else "unresolved",
            owner_userid=_text(row.get("owner_userid")) or follow_user_userid or None,
            identity_map_id=int(row["identity_map_id"]) if row.get("identity_map_id") is not None else None,
            follow_user_userid=follow_user_userid or None,
            matched_by=matched_by,
            contact_points=contact_points,
        )


class PostgresIdentityBindingRepository:
    source_status = "production_postgres_identity_binding"

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self._database_url, row_factory=dict_row)

    def bind_mobile_to_external_contact(
        self,
        *,
        external_userid: str,
        mobile: str,
        owner_userid: str = "",
        bind_by_userid: str = "",
        customer_name: str = "",
        force_rebind: bool = False,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                person_id = self._get_or_create_person(cur, mobile=mobile, external_userid=external_userid)
                existing = self._fetch_binding(cur, external_userid=external_userid)
                if existing and int(existing["person_id"]) != int(person_id) and not force_rebind:
                    raise ValueError("external contact already bound to another person")
                self._upsert_binding(
                    cur,
                    external_userid=external_userid,
                    person_id=person_id,
                    owner_userid=owner_userid,
                    bind_by_userid=bind_by_userid,
                    customer_name=customer_name,
                )
                contact = self._fetch_contact_profile(cur, external_userid=external_userid)
                resolved_owner = owner_userid or _text(contact.get("owner_userid")) if contact else owner_userid
                resolved_name = customer_name or _text(contact.get("customer_name")) if contact else customer_name
                self._merge_lead_pool(
                    cur,
                    external_userid=external_userid,
                    mobile=mobile,
                    person_id=person_id,
                    owner_userid=resolved_owner,
                    customer_name=resolved_name,
                    operator=bind_by_userid,
                )
            conn.commit()
        return {
            "ok": True,
            "source_status": self.source_status,
            "external_userid": external_userid,
            "mobile": mobile,
            "person_id": str(person_id),
            "owner_userid": resolved_owner,
            "customer_name": resolved_name,
            "binding_status": "bound",
            "side_effect_executed": True,
        }

    def _get_or_create_person(self, cur, *, mobile: str, external_userid: str) -> int:
        row = cur.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (mobile) DO UPDATE SET updated_at = people.updated_at
            RETURNING id
            """,
            (mobile, external_userid),
        ).fetchone()
        return int(row["id"])

    def _fetch_binding(self, cur, *, external_userid: str) -> dict[str, Any] | None:
        return cur.execute(
            """
            SELECT external_userid, person_id, last_owner_userid
            FROM external_contact_bindings
            WHERE external_userid = %s
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()

    def _upsert_binding(
        self,
        cur,
        *,
        external_userid: str,
        person_id: int,
        owner_userid: str,
        bind_by_userid: str,
        customer_name: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid,
                first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (external_userid) DO UPDATE SET
                person_id = EXCLUDED.person_id,
                last_owner_userid = COALESCE(NULLIF(EXCLUDED.last_owner_userid, ''), external_contact_bindings.last_owner_userid),
                updated_at = NOW()
            """,
            (external_userid, person_id, bind_by_userid, owner_userid, owner_userid),
        )

    def _fetch_contact_profile(self, cur, *, external_userid: str) -> dict[str, Any] | None:
        return cur.execute(
            """
            SELECT external_userid, owner_userid, customer_name, remark
            FROM contacts
            WHERE external_userid = %s
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()

    def _merge_lead_pool(
        self,
        cur,
        *,
        external_userid: str,
        mobile: str,
        person_id: int,
        owner_userid: str,
        customer_name: str,
        operator: str,
    ) -> None:
        rows = list(
            cur.execute(
                """
                SELECT *
                FROM user_ops_lead_pool_current
                WHERE mobile = %s OR external_userid = %s
                ORDER BY
                    CASE WHEN mobile = %s THEN 0 ELSE 1 END,
                    updated_at DESC,
                    id DESC
                """,
                (mobile, external_userid, mobile),
            ).fetchall()
        )
        if not rows:
            cur.execute(
                """
                INSERT INTO user_ops_lead_pool_current (
                    mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
                    huangxiaocan_activation_state, class_term_no, class_term_label,
                    first_entry_source, last_entry_source, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, TRUE, TRUE, 'unknown', NULL, '', 'mobile_bind', 'mobile_bind', NOW(), NOW())
                """,
                (mobile, external_userid, customer_name, owner_userid),
            )
            self._write_lead_pool_history(
                cur,
                mobile=mobile,
                external_userid=external_userid,
                action_type="mobile_bind_insert",
                before=None,
                after={"external_userid": external_userid, "mobile": mobile},
                operator=operator,
            )
            return

        target = dict(rows[0])
        before = dict(target)
        cur.execute(
            """
            UPDATE user_ops_lead_pool_current
            SET external_userid = %s,
                mobile = %s,
                owner_userid = COALESCE(NULLIF(%s, ''), owner_userid),
                customer_name = COALESCE(NULLIF(%s, ''), customer_name),
                is_wecom_added = TRUE,
                is_mobile_bound = TRUE,
                last_entry_source = 'mobile_bind',
                updated_at = NOW()
            WHERE id = %s
            """,
            (external_userid, mobile, owner_userid, customer_name, target["id"]),
        )
        duplicate_ids = [int(row["id"]) for row in rows[1:] if row.get("id") is not None]
        if duplicate_ids:
            cur.execute("DELETE FROM user_ops_lead_pool_current WHERE id = ANY(%s)", (duplicate_ids,))
        after = {
            **target,
            "external_userid": external_userid,
            "mobile": mobile,
            "owner_userid": owner_userid or target.get("owner_userid"),
            "customer_name": customer_name or target.get("customer_name"),
            "merged_duplicate_ids": duplicate_ids,
        }
        self._write_lead_pool_history(
            cur,
            mobile=mobile,
            external_userid=external_userid,
            action_type="mobile_bind_merge" if duplicate_ids else "mobile_bind_update",
            before=before,
            after=after,
            operator=operator,
        )

    def _write_lead_pool_history(
        self,
        cur,
        *,
        mobile: str,
        external_userid: str,
        action_type: str,
        before: dict[str, Any] | None,
        after: dict[str, Any],
        operator: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO user_ops_lead_pool_history (
                mobile, external_userid, action_type, source_type, operator,
                before_json, after_json, remark, created_at
            )
            VALUES (%s, %s, %s, 'mobile_bind', %s, %s::jsonb, %s::jsonb, %s, NOW())
            """,
            (
                mobile,
                external_userid,
                action_type,
                operator,
                json.dumps(before or {}, ensure_ascii=False, default=_json_default),
                json.dumps(after, ensure_ascii=False, default=_json_default),
                f"bind mobile external_userid={external_userid}",
            ),
        )


_DEFAULT_BINDING_REPO = FixtureIdentityBindingRepository()


def build_identity_binding_repository() -> IdentityBindingRepository:
    if database_mode() == "postgres":
        return PostgresIdentityBindingRepository()
    return _DEFAULT_BINDING_REPO
