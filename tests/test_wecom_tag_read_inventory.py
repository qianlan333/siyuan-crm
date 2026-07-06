from __future__ import annotations

from pathlib import Path


INVENTORY = Path("docs/architecture/wecom_tag_read_route_inventory.md")


def test_wecom_tag_read_inventory_covers_read_write_selector_and_sync_scope() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for route in [
        "/api/admin/wecom/tags",
        "/api/admin/wecom/tags/{tag_id}",
        "/api/admin/wecom/tag-groups",
        "/api/admin/wecom/tag-groups/{group_id}",
        "/api/admin/wecom/tags*",
        "/api/admin/wecom/tag-groups*",
        "/api/sidebar/signup-tags/status",
    ]:
        assert route in text

    assert "questionnaire editor tag picker" in text
    assert "channel admission tag picker" in text
    assert "automation agent tag picker" in text
    assert "No separate sidebar tag catalog selector" in text
    assert "Write Out Of Scope" in text
    assert "External Side Effects Out Of Scope" in text
    assert "Frontend API Backend Contract Matrix" in text
    assert "deletion_locked" in text
    assert "legacy_fallback_allowed=false" in text
    assert "may execute real WeCom sync" in text
    assert "does not create/update/delete tags or groups" in text
    assert "does not mutate customer or questionnaire tags" in text
    assert "production_unavailable" in text
    assert "local_contract_probe" in text


def test_wecom_tag_read_inventory_marks_external_systems_out_of_scope() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Payment, storage, OpenClaw, and automation runtime remain out of scope" in text
    assert "Exact read routes do not call WeCom" in text
    assert "Empty production projection tables return an empty catalog rather than fixture data" in text


def test_wecom_tag_read_inventory_frontend_backend_matrix_covers_entry_pages() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for marker in [
        "/admin/wecom-tags",
        "/admin/questionnaires/new",
        "/admin/questionnaires/{questionnaire_id}",
        "/admin/channels",
        "/admin/channels/{channel_id}/edit",
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/{program_id}/setup",
        "removed old automation program setup page",
        "route now returns `404`",
        "config_wecom_tags.html",
        "wecom_tag_management.js",
        "admin_questionnaires.html",
        "channel_admission_pages.js",
        "automation_agent_config_tag_picker.js",
        "list_admin_wecom_tags_read_model",
        "PostgresTagCatalogRepository",
        "production_unavailable",
    ]:
        assert marker in text
