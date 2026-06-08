from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_h5_payment_wildcard_inventory_covers_final_closeout_matrix() -> None:
    text = (ROOT / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md").read_text(encoding="utf-8")

    for phrase in [
        "Route <-> Caller <-> Backend <-> Decision Matrix",
        "/api/admin/wechat-pay/{path:path}",
        "/api/admin/alipay/{path:path}",
        "/api/h5/wechat-pay/{path:path}",
        "/api/h5/alipay/{path:path}",
        "products/lead-channels",
        "orders/{order_id}/refunds",
        "order-exports",
        "transactions/{order_no}",
        "/api/checkout/wechat",
        "/api/wechat-pay/notify",
        "unknown child path",
        "production_compat wildcard removed",
        "final no legacy fallback",
        "admin WeChat refund exact route is the explicit exception",
        "real_refund_executed=true",
        "real_refund_executed=false",
        "real_external_call_executed=false",
    ]:
        assert phrase in text
