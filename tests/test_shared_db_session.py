from __future__ import annotations

import logging

import pytest

from aicrm_next.shared import db_session


@pytest.fixture(autouse=True)
def reset_engine_cache():
    db_session.reset_engine_cache_for_tests()
    yield
    db_session.reset_engine_cache_for_tests()


def test_get_engine_and_session_factory_reuse_cached_engine(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'shared.db'}"

    engine = db_session.get_engine(database_url)
    assert db_session.get_engine(database_url) is engine

    session_factory = db_session.get_session_factory(database_url)
    assert db_session.get_session_factory(database_url) is session_factory
    assert session_factory.kw["bind"] is engine


def test_postgres_engine_uses_pool_env_and_application_name(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeEngine:
        def dispose(self) -> None:
            pass

    def fake_create_engine(url: str, **kwargs):
        calls.append((url, kwargs))
        return FakeEngine()

    monkeypatch.setattr(db_session, "create_engine", fake_create_engine)
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "2")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "3.5")
    monkeypatch.setenv("DB_POOL_RECYCLE", "600")
    monkeypatch.setenv("DB_APPLICATION_NAME", "aicrm-next-test")

    engine = db_session.get_engine("postgres://user:pass@db.internal:5432/aicrm")

    assert engine is not None
    assert calls == [
        (
            "postgresql+psycopg://user:pass@db.internal:5432/aicrm",
            {
                "future": True,
                "pool_pre_ping": True,
                "pool_size": 7,
                "max_overflow": 2,
                "pool_timeout": 3.5,
                "pool_recycle": 600,
                "connect_args": {"application_name": "aicrm-next-test"},
            },
        )
    ]


def test_get_pool_settings_redacts_database_url_and_uses_env(monkeypatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "9")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "1")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "4")
    monkeypatch.setenv("DB_POOL_RECYCLE", "900")
    monkeypatch.setenv("DB_APPLICATION_NAME", "aicrm-next-diagnostics")

    settings = db_session.get_pool_settings("postgres://user:super-secret@db.internal:5432/aicrm")

    assert settings == {
        "database_scheme": "postgresql+psycopg",
        "is_sqlite": False,
        "application_name": "aicrm-next-diagnostics",
        "pool_size": 9,
        "max_overflow": 1,
        "pool_timeout": 4.0,
        "pool_recycle": 900,
    }
    assert "super-secret" not in str(settings)
    assert "db.internal" not in str(settings)
    assert "user" not in str(settings)


def test_engine_initialization_log_does_not_include_database_secret(monkeypatch, caplog) -> None:
    class FakeEngine:
        def dispose(self) -> None:
            pass

    monkeypatch.setattr(db_session, "create_engine", lambda url, **kwargs: FakeEngine())
    monkeypatch.setenv("DB_APPLICATION_NAME", "aicrm-next-test")

    with caplog.at_level(logging.INFO):
        db_session.get_engine("postgresql://user:super-secret@db.internal:5432/aicrm")

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "initializing SQLAlchemy engine" in log_text
    assert "aicrm-next-test" in log_text
    assert "super-secret" not in log_text
    assert "db.internal" not in log_text
    assert "postgresql://user" not in log_text


def test_sqlite_engine_does_not_receive_postgres_pool_kwargs(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeEngine:
        def dispose(self) -> None:
            pass

    def fake_create_engine(url: str, **kwargs):
        calls.append((url, kwargs))
        return FakeEngine()

    monkeypatch.setattr(db_session, "create_engine", fake_create_engine)

    db_session.get_engine("sqlite:///:memory:")

    assert calls == [("sqlite:///:memory:", {"future": True})]


def test_reset_engine_cache_disposes_cached_engines(monkeypatch) -> None:
    disposed: list[bool] = []

    class FakeEngine:
        def dispose(self) -> None:
            disposed.append(True)

    monkeypatch.setattr(db_session, "create_engine", lambda url, **kwargs: FakeEngine())

    db_session.get_engine("postgresql://user:pass@db.internal:5432/aicrm")
    db_session.reset_engine_cache_for_tests()

    assert disposed == [True]


def test_session_scope_cleanup_error_does_not_mask_business_exception(monkeypatch) -> None:
    class FailingCleanupSession:
        def rollback(self) -> None:
            raise RuntimeError("rollback failed")

        def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(db_session, "get_session_factory", lambda *args, **kwargs: lambda: FailingCleanupSession())

    with pytest.raises(RuntimeError, match="business failed"):
        with db_session.session_scope():
            raise RuntimeError("business failed")


def test_get_db_cleanup_error_does_not_mask_business_exception(monkeypatch) -> None:
    class FailingCleanupSession:
        def rollback(self) -> None:
            raise RuntimeError("rollback failed")

        def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(db_session, "get_session_factory", lambda *args, **kwargs: lambda: FailingCleanupSession())
    dependency = db_session.get_db()
    next(dependency)

    with pytest.raises(RuntimeError, match="business failed"):
        dependency.throw(RuntimeError("business failed"))
