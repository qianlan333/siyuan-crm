from __future__ import annotations

from .dto import ResolvePersonIdentityRequest


def normalize_identity_request(query: ResolvePersonIdentityRequest) -> ResolvePersonIdentityRequest:
    return ResolvePersonIdentityRequest(
        external_userid=(query.external_userid or "").strip() or None,
        mobile=(query.mobile or "").strip() or None,
        openid=(query.openid or "").strip() or None,
        unionid=(query.unionid or "").strip() or None,
    )
