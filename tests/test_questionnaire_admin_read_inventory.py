from __future__ import annotations

from pathlib import Path


def test_questionnaire_admin_read_inventory_covers_read_write_and_public_out_of_scope() -> None:
    text = Path("docs/architecture/questionnaire_admin_read_route_inventory.md").read_text(encoding="utf-8")

    for route in [
        "/admin/questionnaires",
        "/admin/questionnaires/new",
        "/admin/questionnaires/{questionnaire_id}",
        "/api/admin/questionnaires",
        "/api/admin/questionnaires/{questionnaire_id}",
        "/api/admin/questionnaires/{questionnaire_id}/questions",
        "/api/admin/questionnaires/{questionnaire_id}/results",
        "/api/admin/questionnaires/{questionnaire_id}/submissions",
        "/api/h5/questionnaires/{slug}",
        "/api/h5/questionnaires/{slug}/submit",
        "/api/h5/wechat/oauth*",
        "/auth/wecom*",
    ]:
        assert route in text

    assert "admin readonly" in text
    assert "admin write" in text
    assert "out of scope" in text
    assert "production_unavailable" in text
    assert "write_executed" in text
