from __future__ import annotations

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
