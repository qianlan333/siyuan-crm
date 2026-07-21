from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .dto import IdentityResolveResult, ResolvePersonIdentityRequest
from .resolver import resolved_unionid


def _text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class WechatUnionIdAccessDecision:
    allowed: bool
    identity: dict[str, str]
    error: str = ""
    status_code: int = 200
    oauth_start_url: str = ""
    message: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "ok": self.allowed,
            "identity_ready": self.allowed,
            "error": self.error,
            "message": self.message,
        }


class _IdentityQuery(Protocol):
    def execute_result(self, query: ResolvePersonIdentityRequest) -> IdentityResolveResult: ...


def canonical_unionid_from_trusted_identity(identity: Mapping[str, Any] | None) -> str:
    """Return a UnionID only from a caller-owned, server-verified container."""

    return _text((identity or {}).get("unionid"))


def resolve_oauth_unionid(
    identity: Mapping[str, Any] | None,
    *,
    identity_query: _IdentityQuery | None = None,
) -> str:
    explicit_unionid = canonical_unionid_from_trusted_identity(identity)
    if explicit_unionid:
        return explicit_unionid
    openid = _text((identity or {}).get("openid"))
    if not openid or identity_query is None:
        return ""
    return resolved_unionid(identity_query.execute_result(ResolvePersonIdentityRequest(openid=openid)))


def evaluate_wechat_unionid_access(
    identity: Mapping[str, Any] | None,
    *,
    is_wechat_browser: bool,
    oauth_start_url: str,
) -> WechatUnionIdAccessDecision:
    trusted = {
        key: _text((identity or {}).get(key))
        for key in ("openid", "unionid", "respondent_key", "external_userid")
        if _text((identity or {}).get(key))
    }
    provider_verified = bool((identity or {}).get("unionid_verified")) and _text(
        (identity or {}).get("identity_source")
    ) == "wechat_oauth_provider"
    if canonical_unionid_from_trusted_identity(trusted) and provider_verified:
        return WechatUnionIdAccessDecision(allowed=True, identity=trusted)
    if not is_wechat_browser:
        return WechatUnionIdAccessDecision(
            allowed=False,
            identity={},
            error="wechat_browser_required",
            status_code=403,
            message="请在微信中打开后完成授权。",
        )
    return WechatUnionIdAccessDecision(
        allowed=False,
        identity={},
        error="unionid_oauth_required",
        status_code=401,
        oauth_start_url=_text(oauth_start_url),
        message="请先完成微信授权，获取稳定身份后继续。",
    )


__all__ = [
    "WechatUnionIdAccessDecision",
    "canonical_unionid_from_trusted_identity",
    "evaluate_wechat_unionid_access",
    "resolve_oauth_unionid",
]
