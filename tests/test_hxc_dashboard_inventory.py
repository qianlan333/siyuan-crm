from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/hxc_dashboard_route_inventory.md"


def test_inventory_lists_hxc_route_family_and_side_effect_boundaries() -> None:
    source = INVENTORY.read_text(encoding="utf-8")

    for route in (
        "/admin/hxc-dashboard",
        "/admin/hxc-send-config",
        "/api/admin/hxc-dashboard",
        "/api/admin/hxc-dashboard/refresh",
        "/api/admin/hxc-dashboard/refresh-directory",
        "/api/admin/hxc-dashboard/send-config",
        "/api/admin/hxc-dashboard/send-config/{sender_userid}",
        "/api/admin/hxc-dashboard/broadcast",
        "/api/admin/hxc-dashboard/{unknown_path}",
    ):
        assert route in source

    assert "Current Next Ownership" in source
    assert "Existing HXC dashboard business tests cover" in source
    assert "real_external_call_executed=false" in source
    assert "hxc_refresh_executed=false" in source
    assert "directory_sync_executed=false" in source
    assert "hxc_broadcast_executed=false" in source
    assert "wecom_send_executed=false" in source
    assert "refresh_hxc_dashboard_snapshot" in source
    assert "sync_admin_wecom_directory_members" in source
    assert "broadcast_to_filtered_users" in source
