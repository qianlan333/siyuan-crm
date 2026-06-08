from __future__ import annotations

from pathlib import Path


INVENTORY = Path("docs/architecture/wecom_tag_write_route_inventory.md")


def test_wecom_tag_write_inventory_covers_frontend_api_backend_matrix() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for marker in [
        "Frontend API Backend Contract Matrix",
        "/admin/wecom-tags",
        "config_wecom_tags.html",
        "wecom_tag_management.js",
        "/api/admin/wecom/tags",
        "/api/admin/wecom/tags/{tag_id}",
        "/api/admin/wecom/tags/sync",
        "/api/admin/wecom/tags/sync-due",
        "/api/admin/wecom/tag-groups",
        "/api/admin/wecom/tag-groups/{group_id}",
        "CreateWeComTagCommand",
        "UpdateWeComTagCommand",
        "DeleteWeComTagCommand",
        "CreateWeComTagGroupCommand",
        "UpdateWeComTagGroupCommand",
        "DeleteWeComTagGroupCommand",
        "execute_wecom_tag_catalog_sync",
        "WeComTagWriteRepository",
    ]:
        assert marker in text


def test_wecom_tag_write_inventory_marks_side_effects_and_legacy_deletion() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for marker in [
        "next_command",
        "legacy_fallback_allowed=false",
        "production_compat rollback removed",
        "deletion_locked",
        "replacement_status=locked",
        "SideEffectPlan",
        "adapter_mode=real_blocked",
        "real_external_call_executed=false",
        "next_live_catalog_sync",
        "sync_executed=true",
        "live_catalog_sync",
        "production_unavailable",
        "/api/admin/wecom/tags*",
        "/api/admin/wecom/tag-groups*",
        "No actual `/api/admin/wecom/tag-groups/sync` route exists",
    ]:
        assert marker in text
