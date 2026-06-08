from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.post_legacy_baseline import (
    API_CONTRACT_CASES,
    assert_no_compatibility_facade,
    assert_no_legacy_flags,
    baseline_env,
    first_matching_route,
)


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    baseline_env(monkeypatch)
    return TestClient(create_app())


@pytest.mark.parametrize("case", API_CONTRACT_CASES, ids=lambda case: case.key)
def test_post_legacy_api_contract_cases_are_controlled_next_paths(client: TestClient, case) -> None:
    response = client.request(case.method, case.path, json=case.json, content=case.content, params=case.params)

    assert response.status_code in case.expected_statuses
    assert response.status_code != 500
    assert_no_compatibility_facade(response)
    if response.headers.get("content-type", "").startswith("application/json"):
        assert_no_legacy_flags(response.json())
    assert "X-AICRM-Compatibility-Facade" not in response.text


@pytest.mark.parametrize("case", API_CONTRACT_CASES, ids=lambda case: case.key)
def test_post_legacy_api_contract_routes_resolve_to_expected_next_modules(monkeypatch, case) -> None:
    baseline_env(monkeypatch)
    app = create_app()

    route = first_matching_route(app, case.method, case.path)

    assert route is not None
    endpoint_module = getattr(getattr(route, "endpoint", None), "__module__", "")
    assert endpoint_module != "aicrm_next.production_compat.api"
    assert case.owner in endpoint_module
