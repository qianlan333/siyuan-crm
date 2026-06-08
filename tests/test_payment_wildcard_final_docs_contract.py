from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payment_final_docs_describe_known_deprecated_and_replacement_paths() -> None:
    text = (ROOT / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md").read_text(encoding="utf-8")

    for phrase in [
        "products/lead-plans",
        "replacement `products/lead-channels`",
        "order-exports/{job_id}",
        "replacement `order-exports`",
        "legacy Alipay admin APIs",
        "public replacements are `/api/checkout/wechat`, `/api/orders/{order_no}`, `/api/wechat-pay/notify`",
        "public replacements are `/api/checkout/alipay`, `/api/orders/{order_no}`, `/api/alipay/notify`, `/api/alipay/return`",
        "No route in this inventory falls back to `production_compat`",
    ]:
        assert phrase in text


def test_payment_final_contract_notes_refund_provider_exception() -> None:
    text = (ROOT / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md").read_text(encoding="utf-8")

    for phrase in [
        "no route performs real signature verification",
        "admin WeChat refund exact route is the explicit exception",
        "calls the WeChat Pay refund provider",
        "payment_request_executed=false",
        "provider_signature_verified=false",
        "real_external_call_executed=true",
        "real_refund_executed=true",
        "real_refund_executed=false",
        "Unknown child path responses are controlled by Next",
    ]:
        assert phrase in text
