from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_checkout_orders_inventory_covers_required_boundaries() -> None:
    text = (ROOT / "docs/architecture/checkout_orders_route_inventory.md").read_text(encoding="utf-8")

    for phrase in (
        "API <-> Backend <-> Payment Adapter Contract Matrix",
        "POST checkout wechat",
        "POST checkout alipay",
        "/api/checkout/wechat",
        "/api/checkout/alipay",
        "/api/orders/{order_no}",
        "/api/orders/{order_no}/status",
        "/api/checkout/{unknown_path}",
        "/api/orders/{unknown_child_path}",
        "/api/wechat-pay/*",
        "/api/alipay/*",
        "admin payment",
        "H5 payment",
        "production_compat wildcard removed",
        "payment_request_executed=false",
        "real_external_call_executed=false",
    ):
        assert phrase in text


def test_checkout_orders_inventory_declares_out_of_scope_provider_routes() -> None:
    text = (ROOT / "docs/architecture/checkout_orders_route_inventory.md").read_text(encoding="utf-8")

    assert "provider notify/return" in text
    assert "real WeChat Pay" in text
    assert "real Alipay" in text
    assert "real callbacks remain out of scope" in text
