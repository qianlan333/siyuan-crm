from __future__ import annotations

from pathlib import Path


def test_questionnaire_admin_write_inventory_covers_existing_and_added_write_routes() -> None:
    text = Path("docs/architecture/questionnaire_admin_write_route_inventory.md").read_text(encoding="utf-8")

    for route in [
        "/api/admin/questionnaires",
        "/api/admin/questionnaires/{questionnaire_id}",
        "/api/admin/questionnaires/{questionnaire_id}/duplicate",
        "/api/admin/questionnaires/{questionnaire_id}/publish",
        "/api/admin/questionnaires/{questionnaire_id}/enable",
        "/api/admin/questionnaires/{questionnaire_id}/disable",
        "/api/admin/questionnaires/{questionnaire_id}/export",
        "/api/admin/questionnaires/{questionnaire_id}/export/preview",
    ]:
        assert route in text

    assert "Next CommandBus" in text
    assert "Idempotency-Key" in text
    assert "source_status=next_command" in text
    assert "fallback_used=false" in text
    assert "legacy rollback removed" in text
    assert "runtime_owner=next_command" in text
    assert "legacy_fallback_allowed=false" in text
    assert "delete_status=deletion_locked" in text
    assert "replacement_status=locked" in text
    assert "real_external_call_executed=false" in text
    assert "/api/h5/questionnaires*" in text
    assert "/api/h5/wechat/oauth*" in text
