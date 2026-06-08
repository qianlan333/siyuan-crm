from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/admin_auth_login_route_inventory.md"


def test_inventory_covers_login_logout_and_out_of_scope_boundaries() -> None:
    source = INVENTORY.read_text(encoding="utf-8")

    for phrase in (
        "GET 200, non-empty",
        "Invalid credential controlled",
        "legacy_fallback_allowed=false",
        "deletion_locked",
        "replacement_status=locked",
        "/login",
        "/logout",
        "/auth/wecom/start",
        "/auth/wecom/callback",
        "Do not enable real WeCom OAuth",
        "Do not change payment",
    ):
        assert phrase in source
