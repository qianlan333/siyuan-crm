from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def reset_db_cache():
    from aicrm_next.shared.db_session import reset_engine_cache_for_tests

    reset_engine_cache_for_tests()
    yield
    reset_engine_cache_for_tests()


def _production_postgres_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://masked_user@127.0.0.1:5432/masked_db")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)


def test_repository_provider_blocks_fixture_repo_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from aicrm_next.ops_enrollment.repo import InMemoryUserOpsRepository
    from aicrm_next.shared.repository_provider import RepositoryProviderError, assert_repository_allowed

    _production_postgres_env(monkeypatch)

    with pytest.raises(RepositoryProviderError, match="fixture_repository_blocked_in_production|production_data_ready=true"):
        assert_repository_allowed(InMemoryUserOpsRepository(), capability_owner="ops_enrollment")


def test_user_ops_production_defaults_to_sqlalchemy_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    from aicrm_next.ops_enrollment import repo as repo_module

    _production_postgres_env(monkeypatch)
    monkeypatch.delenv("USER_OPS_REPO_BACKEND", raising=False)

    class FakeSession:
        pass

    session = FakeSession()
    calls: list[object] = []

    def fake_get_session_factory(*, settings):
        calls.append(settings)
        return lambda: session

    monkeypatch.setattr(repo_module, "get_session_factory", fake_get_session_factory)

    repository = repo_module.build_user_ops_repository()

    assert repository.__class__.__name__ == "SqlAlchemyUserOpsRepository"
    assert repository._session is session
    assert calls


def test_user_ops_overview_empty_sql_tables_returns_ok(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from aicrm_next.main import create_app
    from aicrm_next.schema_init import init_next_schema_safe

    database_url = f"sqlite:///{tmp_path / 'user_ops_next.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("USER_OPS_REPO_BACKEND", "sqlalchemy")

    init_next_schema_safe(prefer_sql_file=False)
    response = TestClient(create_app()).get("/api/admin/user-ops/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["metrics"] == {"lead_pool_total_count": 0, "filtered_total": 0}
    assert payload["cards"]


def test_user_ops_overview_missing_sql_tables_returns_schema_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from aicrm_next.main import create_app

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'missing_user_ops_next.db'}")
    monkeypatch.setenv("USER_OPS_REPO_BACKEND", "sqlalchemy")

    response = TestClient(create_app()).get("/api/admin/user-ops/overview")

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["source_status"] == "schema_missing"
    assert payload["error_code"] == "user_ops_schema_missing"
    assert "fixture_repository_blocked_in_production" not in str(payload)


def test_safe_next_schema_init_creates_customer_detail_snapshot_table(tmp_path) -> None:
    from aicrm_next.schema_init import init_next_schema_safe

    engine = create_engine(f"sqlite:///{tmp_path / 'safe_schema.db'}", future=True)

    first = init_next_schema_safe(engine, prefer_sql_file=False)
    second = init_next_schema_safe(engine, prefer_sql_file=False)

    table_names = set(inspect(engine).get_table_names())
    assert "customer_detail_snapshot_next" in table_names
    assert "customer_list_index_next" in table_names
    assert "user_ops_pool_current_next" in table_names
    assert first == second


def test_customer_sidebar_routes_do_not_503_after_safe_schema_init(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from aicrm_next.customer_read_model import application as customer_application
    from aicrm_next.main import create_app
    from aicrm_next.schema_init import init_next_schema_safe
    from aicrm_next.shared.db_session import get_db, get_session_factory

    database_url = f"sqlite:///{tmp_path / 'customer_next.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("CUSTOMER_READ_MODEL_REPO_BACKEND", "sqlalchemy")
    monkeypatch.setattr(customer_application, "_production_customer_data_required", lambda: True)
    monkeypatch.setattr(customer_application, "_customer_read_model_live_source_fallback_enabled", lambda: False)

    init_next_schema_safe(prefer_sql_file=False)
    session_factory = get_session_factory()

    def override_get_db() -> Iterator:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    responses = [
        client.get("/api/customers/external_user_masked_001"),
        client.get("/api/customers/external_user_masked_001/timeline"),
        client.get("/api/sidebar/customer-context?external_userid=external_user_masked_001"),
        client.get("/api/sidebar/profile?external_userid=external_user_masked_001"),
    ]

    assert all(response.status_code != 503 for response in responses)
    assert {response.status_code for response in responses} <= {400, 404}
