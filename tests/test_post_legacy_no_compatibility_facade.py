from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.post_legacy_baseline import (
    API_CONTRACT_CASES,
    assert_no_compatibility_facade,
    baseline_env,
)


REPRESENTATIVE_RESPONSE_CASES = (
    "customers_read",
    "questionnaire_h5_submit",
    "wecom_tags_read",
    "cloud_campaigns_run_due_preview",
    "automation_member_put_in_pool",
    "hxc_dashboard_refresh",
    "checkout_wechat_fake",
    "admin_payment_unknown_closed",
    "h5_payment_unknown_closed",
)


def test_representative_post_legacy_responses_do_not_emit_compatibility_facade(monkeypatch) -> None:
    baseline_env(monkeypatch)
    client = TestClient(create_app())
    by_key = {case.key: case for case in API_CONTRACT_CASES}

    for key in REPRESENTATIVE_RESPONSE_CASES:
        case = by_key[key]
        response = client.request(case.method, case.path, json=case.json, content=case.content, params=case.params)
        assert response.status_code in case.expected_statuses
        assert_no_compatibility_facade(response)
        assert "X-AICRM-Compatibility-Facade" not in response.text


def test_post_legacy_runtime_no_production_compat_routes(monkeypatch) -> None:
    baseline_env(monkeypatch)
    app = create_app()

    compat_routes = [
        route
        for route in app.routes
        if getattr(getattr(route, "endpoint", None), "__module__", "") == "aicrm_next.production_compat.api"
    ]

    assert compat_routes == []
