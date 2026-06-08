from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_provider_payment_inventory_covers_required_boundaries() -> None:
    text = (ROOT / "docs/architecture/provider_payment_notify_route_inventory.md").read_text(encoding="utf-8")

    for phrase in (
        "Provider Callback <-> API <-> Backend <-> Payment Adapter Matrix",
        "/api/wechat-pay/notify",
        "/api/alipay/notify",
        "/api/alipay/return",
        "/api/wechat-pay/{unknown_path}",
        "/api/alipay/{unknown_path}",
        "provider_signature_verified=false",
        "real_payment_notify_executed=false",
        "real_external_call_executed=false",
        "production_compat wildcard removed",
        "/api/admin/wechat-pay/*",
        "/api/admin/alipay/*",
        "/api/h5/wechat-pay/*",
        "/api/h5/alipay/*",
    ):
        assert phrase in text


def test_provider_payment_inventory_declares_no_real_provider_work() -> None:
    text = (ROOT / "docs/architecture/provider_payment_notify_route_inventory.md").read_text(encoding="utf-8")

    assert "does not perform real signature verification" in text
    assert "does not call WeChat Pay, Alipay, or any third-party provider" in text
    assert "Admin payment, H5 payment" in text
