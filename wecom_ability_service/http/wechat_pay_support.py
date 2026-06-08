from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from flask import current_app, request, url_for

from ..infra.signed_context import append_ctx_query, load_sidebar_product_context_token
from ..infra.settings import get_setting
from .questionnaire_support import _external_base_url, _oauth_browser_error_page


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def safe_payment_return_url(value: str) -> str:
    normalized = _normalized_text(value)
    if not normalized or not normalized.startswith("/") or normalized.startswith("//"):
        return "/"
    return normalized


def payment_oauth_callback_url() -> str:
    return _external_base_url() + url_for("api.h5_wechat_pay_oauth_callback")


def payment_oauth_start_url(return_url: str) -> str:
    query = urlencode({"return_url": safe_payment_return_url(return_url)})
    return f"{url_for('api.h5_wechat_pay_oauth_start')}?{query}"


def request_sidebar_product_context() -> dict[str, Any]:
    token = _normalized_text(request.args.get("ctx"))
    result = load_sidebar_product_context_token(token)
    return {
        "token": token,
        "status": _normalized_text(result.get("status")) or "missing",
        "context": dict(result.get("context") or {}) if result.get("ok") else {},
    }


def product_path_with_ctx(prefix: str, product_code: str, context_token: str = "") -> str:
    path = f"/{prefix}/{product_code}" if product_code else f"/{prefix}"
    return append_ctx_query(path, context_token) if context_token else path


def wechat_pay_oauth_error_page(message: str, *, return_url: str = "/", status_code: int = 400):
    return _oauth_browser_error_page(
        title="微信支付授权未完成",
        message=message,
        return_url=safe_payment_return_url(return_url),
        button_label="返回商品页",
        status_code=status_code,
    )


def wechat_pay_oauth_scope() -> str:
    return (
        _normalized_text(get_setting("WECHAT_PAY_OAUTH_SCOPE") or current_app.config.get("WECHAT_PAY_OAUTH_SCOPE"))
        or "snsapi_userinfo"
    )
