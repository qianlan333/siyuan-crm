from __future__ import annotations

from conftest import make_client


def test_next_responses_mark_route_owner():
    response = make_client().get("/api/admin/image-library")

    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-App"] == "ai_crm_next"
    assert response.headers["X-AICRM-Release-SHA"]
