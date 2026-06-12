from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from starlette.requests import Request

from aicrm_next.public_product import h5_wechat_pay
from aicrm_next.public_product.signed_context import append_ctx_query, build_sidebar_product_context_token


def _request(path: str, query: str = "") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query.encode("utf-8"),
            "headers": [(b"host", b"pay.example.test")],
            "scheme": "https",
            "server": ("pay.example.test", 443),
            "client": ("testclient", 12345),
        }
    )


def test_checkout_page_state_preserves_ctx_in_pay_path(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ACTION_TOKEN_SECRET", "h5-pay-sidebar-context-secret")
    token = build_sidebar_product_context_token(
        external_userid="wm_ext_checkout_001",
        owner_userid="sales_01",
        bind_by_userid="advisor_01",
    )
    product = {
        "product_code": "demo",
        "title": "Demo product",
        "price_cents": 9900,
        "currency": "CNY",
        "require_mobile": False,
    }

    state = h5_wechat_pay.checkout_page_state(product, _request("/pay/demo", f"ctx={quote(token, safe='')}"))

    assert state["context_token"] == token
    assert state["context_status"] == "valid"
    parsed_start = urlparse(state["oauth_start_url"])
    assert parsed_start.path == "/api/h5/wechat-pay/oauth/start"
    assert parse_qs(parsed_start.query)["return_url"] == [append_ctx_query("/pay/demo", token)]


def test_h5_pay_runtime_uses_native_sidebar_context_imports() -> None:
    source = Path("aicrm_next/public_product/h5_wechat_pay.py").read_text(encoding="utf-8")
    forbidden = [
        "wecom_ability" + "_service.infra." + "signed_context",
        "wecom_ability" + "_service.domains.wechat_pay." + "sidebar_context",
    ]

    for marker in forbidden:
        assert marker not in source
    assert "from .signed_context import" in source
    assert "from .sidebar_order_context import" in source
