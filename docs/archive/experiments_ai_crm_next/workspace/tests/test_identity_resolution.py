from __future__ import annotations

from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest


def test_resolve_person_identity_by_mobile() -> None:
    result = ResolvePersonIdentityQuery()(ResolvePersonIdentityRequest(mobile="13800138000"))
    assert result is not None
    assert result.person_id == "person_001"
    assert result.external_userid == "wx_ext_001"
    assert result.binding_status == "bound"
    assert result.owner_userid == "ZhaoYanFang"
    assert result.contact_points
