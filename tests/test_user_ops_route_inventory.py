from __future__ import annotations

from pathlib import Path


def test_user_ops_route_inventory_documents_group_6_routes() -> None:
    text = Path("docs/architecture/user_ops_route_inventory.md").read_text(encoding="utf-8")

    for route in [
        "/admin/user-ops",
        "/api/admin/user-ops/overview",
        "/api/admin/user-ops/cards",
        "/api/admin/user-ops/customers",
        "/api/admin/user-ops/customers/{external_userid}",
        "/api/admin/user-ops/customers/{external_userid}/timeline",
        "/api/admin/user-ops/filters",
        "/api/admin/user-ops/send-records",
        "/api/admin/user-ops/broadcast/preview",
        "/api/admin/user-ops/export/preview",
    ]:
        assert route in text

    assert "CommandBus" in text
    assert "AuditLedger" in text
    assert "SideEffectPlan" in text
    assert "real_external_call_executed: false" in text
    assert "deletion_locked / locked" in text
    assert "controlled default preview" in text
    assert "Real WeCom send" in text
    assert "not handled in group 6" in text
