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

    def list_external_contact_owner_userids(self, external_userid: str) -> set[str]:
        person = self.resolve(ResolvePersonIdentityRequest(external_userid=external_userid))
        if person is None:
            return set()
        return {
            owner
            for owner in {
                _text(person.owner_userid),
                _text(person.follow_user_userid),
            }
            if owner
        }


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
            ("mobile", _text(query.mobile)),
        ]
        with self._connect() as conn:
            for field, value in lookups:
                if not value:
                    continue
                if field == "unionid":
                    where_sql = "unionid = %s"
                    params: tuple[Any, ...] = (value,)
                elif field == "external_userid":
                    where_sql = "primary_external_userid = %s OR jsonb_exists(external_userids_json, %s)"
                    params = (value, value)
                elif field == "openid":
                    where_sql = "primary_openid = %s OR jsonb_exists(openids_json, %s)"
                    params = (value, value)
                else:
                    where_sql = "mobile = %s"
                    params = (value,)
                row = conn.execute(
                    f"""
                    SELECT unionid,
                           primary_external_userid AS external_userid,
                           primary_openid AS openid,
                           primary_owner_userid AS follow_user_userid,
                           primary_owner_userid AS owner_userid,
                           mobile,
                           identity_status AS status
                    FROM crm_user_identity
                    WHERE {where_sql}
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    params,
                ).fetchone()
                if row:
                    return self._from_user_identity(row, matched_by=field)
        return None

    def list_external_contact_owner_userids(self, external_userid: str) -> set[str]:
        normalized_external = _text(external_userid)
        if not normalized_external:
            return set()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT owner_userid
                FROM (
                    SELECT COALESCE(NULLIF(user_id, ''), NULLIF(raw_follow_user ->> 'userid', '')) AS owner_userid
                    FROM wecom_external_contact_follow_users
                    WHERE external_userid = %s
                      AND COALESCE(relation_status, 'active') = 'active'
                    UNION ALL
                    SELECT NULLIF(follow_user_userid, '') AS owner_userid
                    FROM wecom_external_contact_identity_map
                    WHERE external_userid = %s
                    UNION ALL
                    SELECT NULLIF(primary_owner_userid, '') AS owner_userid
                    FROM crm_user_identity
                    WHERE primary_external_userid = %s
                       OR jsonb_exists(external_userids_json, %s)
                    UNION ALL
                    SELECT NULLIF(first_owner_userid, '') AS owner_userid
                    FROM external_contact_bindings
                    WHERE external_userid = %s
                    UNION ALL
                    SELECT NULLIF(last_owner_userid, '') AS owner_userid
                    FROM external_contact_bindings
                    WHERE external_userid = %s
                ) owners
                WHERE COALESCE(owner_userid, '') <> ''
                """,
                (
                    normalized_external,
                    normalized_external,
                    normalized_external,
                    normalized_external,
                    normalized_external,
                    normalized_external,
                ),
            ).fetchall()
        return {_text(row.get("owner_userid")) for row in rows if _text(row.get("owner_userid"))}

    def _from_user_identity(self, row, *, matched_by: str) -> IdentityResolution:
        external_userid = _text(row.get("external_userid"))
        unionid = _text(row.get("unionid")) or None
        openid = _text(row.get("openid")) or None
        mobile = _text(row.get("mobile")) or None
        follow_user_userid = _text(row.get("follow_user_userid"))
        contact_points = []
        if unionid:
            contact_points.append(ContactPoint(type="wechat_unionid", value=unionid, verified=True))
        if external_userid:
            contact_points.append(ContactPoint(type="wecom_external_userid", value=external_userid, verified=True))
        if openid:
            contact_points.append(ContactPoint(type="wechat_openid", value=openid, verified=True))
        if mobile:
            contact_points.append(ContactPoint(type="mobile", value=mobile, verified=True))
        return IdentityResolution(
            person_id=None,
            external_userid=external_userid or None,
            mobile=mobile,
            openid=openid,
            unionid=unionid,
            binding_status="bound" if unionid else "unresolved",
            owner_userid=_text(row.get("owner_userid")) or follow_user_userid or None,
            identity_map_id=None,
            follow_user_userid=follow_user_userid or None,
            matched_by=matched_by,
            contact_points=contact_points,
        )

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
                self._record_mobile_identity_binding(
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
            SELECT
                im.external_userid,
                COALESCE(NULLIF(fu.user_id, ''), NULLIF(im.follow_user_userid, '')) AS owner_userid,
                COALESCE(NULLIF(im.name, ''), NULLIF(im.raw_profile ->> 'name', '')) AS customer_name,
                COALESCE(NULLIF(fu.remark, ''), NULLIF(im.raw_profile ->> 'remark', '')) AS remark
            FROM wecom_external_contact_identity_map im
            LEFT JOIN wecom_external_contact_follow_users fu
              ON fu.corp_id = im.corp_id
             AND fu.external_userid = im.external_userid
             AND COALESCE(fu.relation_status, 'active') = 'active'
            WHERE im.external_userid = %s
            ORDER BY fu.is_primary DESC NULLS LAST, fu.updated_at DESC NULLS LAST, im.updated_at DESC, im.id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()

    def _record_mobile_identity_binding(
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
        updated = cur.execute(
            """
            UPDATE crm_user_identity
            SET mobile = %s,
                mobile_normalized = %s,
                mobile_verified = TRUE,
                mobile_source = 'mobile_bind',
                primary_owner_userid = COALESCE(NULLIF(%s, ''), primary_owner_userid),
                customer_name = COALESCE(NULLIF(%s, ''), customer_name),
                legacy_person_id = COALESCE(NULLIF(%s, ''), legacy_person_id),
                profile_json = profile_json || %s::jsonb,
                updated_at = NOW()
            WHERE primary_external_userid = %s
               OR jsonb_exists(external_userids_json, %s)
            RETURNING unionid
            """,
            (
                mobile,
                mobile,
                owner_userid,
                customer_name,
                str(person_id),
                json.dumps(
                    {"mobile_bind": {"external_userid": external_userid, "operator": operator}},
                    ensure_ascii=False,
                    default=_json_default,
                ),
                external_userid,
                external_userid,
            ),
        ).fetchone()
        if updated:
            return

        cur.execute(
            """
            INSERT INTO crm_user_identity_resolution_queue (
                source_type, source_key, source_table, source_id,
                external_userid, mobile, payload_json, raw_payload_json,
                reason, status, last_seen_at, updated_at
            )
            VALUES (
                'identity_contact_mobile_bind', %s, 'external_contact_bindings', %s,
                %s, %s, %s::jsonb, %s::jsonb,
                'pending_unionid_for_mobile_bind', 'pending', NOW(), NOW()
            )
            ON CONFLICT (source_type, source_key)
            WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
            DO UPDATE SET
                external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                mobile = COALESCE(NULLIF(EXCLUDED.mobile, ''), crm_user_identity_resolution_queue.mobile),
                payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                raw_payload_json = crm_user_identity_resolution_queue.raw_payload_json || EXCLUDED.raw_payload_json,
                reason = EXCLUDED.reason,
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            (
                external_userid,
                external_userid,
                external_userid,
                mobile,
                json.dumps(
                    {
                        "external_userid": external_userid,
                        "mobile": mobile,
                        "person_id": str(person_id),
                        "owner_userid": owner_userid,
                        "customer_name": customer_name,
                    },
                    ensure_ascii=False,
                    default=_json_default,
                ),
                json.dumps(
                    {"operator": operator, "source": "identity_contact_mobile_bind"},
                    ensure_ascii=False,
                    default=_json_default,
                ),
            ),
        )


_DEFAULT_BINDING_REPO = FixtureIdentityBindingRepository()


def build_identity_binding_repository() -> IdentityBindingRepository:
    if database_mode() == "postgres":
        return PostgresIdentityBindingRepository()
    return _DEFAULT_BINDING_REPO
