from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.post_legacy_baseline import (
    ADMIN_PAGE_CASES,
    PUBLIC_H5_PAGE_CASES,
    assert_no_compatibility_facade,
    baseline_env,
    first_matching_route,
)


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    baseline_env(monkeypatch)
    return TestClient(create_app())


@pytest.mark.parametrize("case", ADMIN_PAGE_CASES + PUBLIC_H5_PAGE_CASES, ids=lambda case: case.key)
def test_post_legacy_pages_are_next_owned_and_nonblank(client: TestClient, case) -> None:
    response = client.get(case.path)

    assert response.status_code in case.expected_statuses
    assert_no_compatibility_facade(response)
    assert "X-AICRM-Compatibility-Facade" not in response.text
    assert "Traceback" not in response.text
    assert response.text.strip()


@pytest.mark.parametrize("case", ADMIN_PAGE_CASES + PUBLIC_H5_PAGE_CASES, ids=lambda case: case.key)
def test_post_legacy_page_routes_resolve_outside_production_compat(monkeypatch, case) -> None:
    baseline_env(monkeypatch)
    app = create_app()

    route = first_matching_route(app, "GET", case.path)

    assert route is not None
    endpoint_module = getattr(getattr(route, "endpoint", None), "__module__", "")
    assert endpoint_module != "aicrm_next.production_compat.api"
    assert case.owner in endpoint_module
