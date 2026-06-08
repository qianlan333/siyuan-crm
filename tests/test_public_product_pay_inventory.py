from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_product_pay_inventory_covers_required_boundaries() -> None:
    text = (ROOT / "docs/architecture/public_product_pay_route_inventory.md").read_text(encoding="utf-8")

    assert "Frontend <-> API <-> Backend Contract Matrix" in text
    for route in [
        "/p/{product_or_slug}",
        "/pay/{product_or_slug}",
        "/api/products/{path}",
        "/api/products/list",
        "/api/admin/wechat-pay/*",
        "/api/checkout/*",
        "/api/orders/*",
    ]:
        assert route in text
    for boundary in [
        "production_compat rollback removed",
        "wildcard_router rollback removed",
        "legacy_fallback_allowed=false",
        "deletion_locked",
        "Next-owned H5 WeChat Pay may create JSAPI orders",
        "Do not change admin/alipay/checkout/orders/provider ownership",
    ]:
        assert boundary in text
