from __future__ import annotations

from pathlib import Path


def test_questionnaire_oauth_inventory_documents_group_10_routes() -> None:
    text = Path("docs/architecture/questionnaire_oauth_route_inventory.md").read_text(encoding="utf-8")

    for route in [
        "/api/h5/wechat/oauth/start",
        "/api/h5/wechat/oauth/callback",
        "/api/h5/wechat/oauth/{path:path}",
        "/auth/wecom/{path:path}",
    ]:
        assert route in text
    assert "signed state" in text
    assert "real_blocked" in text
    assert "locked the exact start/callback legacy rollback closed" in text
    assert "does not delete OAuth/auth wildcard rollback" in text
