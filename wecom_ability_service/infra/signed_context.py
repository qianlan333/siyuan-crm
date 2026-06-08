from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer

SIDEBAR_PRODUCT_CONTEXT_SOURCE = "sidebar_product_link"
SIDEBAR_PRODUCT_CONTEXT_RESOLVED_SOURCE = "signed_sidebar_product_link"
SIDEBAR_PRODUCT_CONTEXT_SALT = "aicrm-sidebar-product-context-v1"
DEFAULT_SIDEBAR_PRODUCT_CONTEXT_TTL_SECONDS = 30 * 86400


def _text(value: Any) -> str:
    return str(value or "").strip()


def _setting(name: str, default: str = "") -> str:
    try:
        from flask import current_app

        if current_app:
            value = current_app.config.get(name)
            if value not in (None, ""):
                return _text(value)
    except RuntimeError:
        pass
    return _text(os.getenv(name, default))


def _secret() -> str:
    return (
        _setting("AICRM_NEXT_ACTION_TOKEN_SECRET")
        or _setting("SECRET_KEY")
        or "aicrm-sidebar-context-dev-secret"
    )


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(_secret(), salt=SIDEBAR_PRODUCT_CONTEXT_SALT)


def sidebar_product_context_ttl_seconds() -> int:
    raw = (
        _setting("SIDEBAR_PRODUCT_CONTEXT_TOKEN_TTL_SECONDS")
        or _setting("SIDEBAR_CONTEXT_TOKEN_TTL_SECONDS")
    )
    try:
        value = int(raw or DEFAULT_SIDEBAR_PRODUCT_CONTEXT_TTL_SECONDS)
    except (TypeError, ValueError):
        value = DEFAULT_SIDEBAR_PRODUCT_CONTEXT_TTL_SECONDS
    return max(3600, min(value, 180 * 86400))


def build_sidebar_product_context_token(
    *,
    external_userid: str,
    owner_userid: str = "",
    bind_by_userid: str = "",
    ttl_seconds: int | None = None,
) -> str:
    normalized_external = _text(external_userid)
    if not normalized_external:
        raise ValueError("external_userid is required")
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = int(ttl_seconds or sidebar_product_context_ttl_seconds())
    payload = {
        "external_userid": normalized_external,
        "owner_userid": _text(owner_userid),
        "bind_by_userid": _text(bind_by_userid) or _text(owner_userid),
        "source": SIDEBAR_PRODUCT_CONTEXT_SOURCE,
        "issued_at": now,
        "expires_at": now + max(60, ttl),
    }
    return _serializer().dumps(payload)


def load_sidebar_product_context_token(token: str) -> dict[str, Any]:
    normalized_token = _text(token)
    if not normalized_token:
        return {"ok": False, "status": "missing", "context": {}}
    try:
        payload = _serializer().loads(normalized_token)
    except (BadSignature, ValueError, TypeError):
        return {"ok": False, "status": "invalid", "context": {}}
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    external_userid = _text(source.get("external_userid"))
    if _text(source.get("source")) != SIDEBAR_PRODUCT_CONTEXT_SOURCE or not external_userid:
        return {"ok": False, "status": "invalid", "context": {}}
    now = int(datetime.now(timezone.utc).timestamp())
    try:
        expires_at = int(source.get("expires_at") or 0)
    except (TypeError, ValueError):
        expires_at = 0
    if expires_at and expires_at < now:
        return {"ok": False, "status": "expired", "context": {}}
    context = {
        "external_userid": external_userid,
        "owner_userid": _text(source.get("owner_userid")),
        "bind_by_userid": _text(source.get("bind_by_userid")) or _text(source.get("owner_userid")),
        "source": SIDEBAR_PRODUCT_CONTEXT_RESOLVED_SOURCE,
        "issued_at": int(source.get("issued_at") or 0),
        "expires_at": expires_at,
    }
    return {"ok": True, "status": "valid", "context": context}


def append_ctx_query(path: str, token: str) -> str:
    normalized_path = _text(path)
    normalized_token = _text(token)
    if not normalized_path or not normalized_token:
        return normalized_path
    separator = "&" if "?" in normalized_path else "?"
    from urllib.parse import quote

    return f"{normalized_path}{separator}ctx={quote(normalized_token, safe='')}"
