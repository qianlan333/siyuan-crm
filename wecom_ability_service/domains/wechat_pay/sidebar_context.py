from __future__ import annotations

from typing import Any

from ...infra.signed_context import (
    SIDEBAR_PRODUCT_CONTEXT_RESOLVED_SOURCE,
    load_sidebar_product_context_token,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_mobile(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits


def resolve_sidebar_order_context(
    *,
    context_token: str = "",
    payment_identity: dict[str, Any] | None = None,
    product: dict[str, Any] | None = None,
    payload_mobile: str = "",
    existing_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token_result = load_sidebar_product_context_token(context_token)
    signed_context = dict(token_result.get("context") or {}) if token_result.get("ok") else {}
    identity = dict(payment_identity or {})
    binding = dict(existing_binding or {})
    mobile = _normalize_mobile(payload_mobile)
    mobile_source = "payload" if mobile else "none"
    if not mobile:
        mobile = _normalize_mobile(binding.get("mobile"))
        mobile_source = "existing_binding" if mobile else "none"
    external_userid = _text(signed_context.get("external_userid"))
    owner_userid = _text(signed_context.get("owner_userid"))
    bind_by_userid = _text(signed_context.get("bind_by_userid")) or owner_userid
    return {
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "bind_by_userid": bind_by_userid,
        "openid": _text(identity.get("openid")),
        "unionid": _text(identity.get("unionid")),
        "payer_name": _text(identity.get("payer_name")),
        "mobile": mobile,
        "context_source": SIDEBAR_PRODUCT_CONTEXT_RESOLVED_SOURCE if external_userid else "",
        "context_status": _text(token_result.get("status")) or "missing",
        "mobile_source": mobile_source,
        "require_mobile_effective": bool((product or {}).get("require_mobile")) and not mobile,
    }
