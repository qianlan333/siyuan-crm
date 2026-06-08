from __future__ import annotations

from wecom_ability_service import create_app


def test_legacy_flask_responses_mark_route_owner():
    app = create_app({"TESTING": True, "RELEASE_SHA": "test-sha"})
    client = app.test_client()

    response = client.get("/favicon.ico")

    assert response.headers["X-AICRM-Route-Owner"] == "legacy_flask"
    assert response.headers["X-AICRM-App"] == "ai_crm_legacy_flask"
    assert response.headers["X-AICRM-Release-SHA"] == "test-sha"
