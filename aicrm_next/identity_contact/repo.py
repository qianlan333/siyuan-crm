from __future__ import annotations

from aicrm_next.shared.runtime import raw_database_url

from .dto import ContactPoint, IdentityResolution, ResolvePersonIdentityRequest


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


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


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
                    ORDER BY b.updated_at DESC, b.id DESC
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
