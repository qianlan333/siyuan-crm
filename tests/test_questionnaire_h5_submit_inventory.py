from __future__ import annotations

from pathlib import Path


def test_questionnaire_h5_submit_inventory_documents_group_9_scope() -> None:
    text = Path("docs/architecture/questionnaire_h5_submit_route_inventory.md").read_text(encoding="utf-8")

    for route in [
        "/api/h5/questionnaires/{slug}/submit",
        "/api/h5/questionnaires/{slug}/client-diagnostics",
        "/api/h5/wechat/oauth/start",
        "/api/h5/wechat/oauth/callback",
        "/auth/wecom/*",
    ]:
        assert route in text

    assert "questionnaire.h5.submit" in text
    assert "questionnaire.h5.client_diagnostics" in text
    assert "Next CommandBus only" in text
    assert "legacy rollback removed" in text
    assert "deletion_locked" in text
    assert "adapter_mode=real_enabled" in text
    assert "configured external push is attempted" in text
    assert "real_external_call_executed=false" in text
    assert "production_unavailable" in text
    assert "admin read/write" in text
