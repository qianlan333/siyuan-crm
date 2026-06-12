from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFTEST = ROOT / "tests" / "conftest.py"


def _fixture_block(source: str, fixture_name: str) -> str:
    marker = f"def {fixture_name}("
    start = source.find(marker)
    assert start >= 0, f"missing fixture {fixture_name}"
    next_start = len(source)
    for candidate in ("\n@pytest.fixture", "\ndef "):
        pos = source.find(candidate, start + len(marker))
        if pos >= 0:
            next_start = min(next_start, pos + 1)
    return source[start:next_start]


def test_next_test_fixtures_exist_and_are_default() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    for fixture_name in ("next_app", "next_client", "next_pg_schema", "app", "client"):
        assert f"def {fixture_name}(" in source

    assert "return next_app" in _fixture_block(source, "app")
    assert "return next_client" in _fixture_block(source, "client")


def test_legacy_test_fixture_bridge_is_removed() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    for marker in (
        "build_legacy_pg_test_app",
        "build_pg_test_app",
        "_AppContextManager",
        "_build_app_context",
        "def legacy_app(",
        "def legacy_client(",
        "def legacy_app_context(",
        "def runtime_v2_pg_app(",
    ):
        assert marker not in source


def test_conftest_no_longer_imports_legacy_or_schema_bridge() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    assert "wecom_ability" + "_service" not in source
    assert "schema_postgres.sql" not in source
    assert "run_schema_with_forward_fk_retries" not in source
    assert "alembic" in source


def test_next_fixtures_do_not_import_legacy_package() -> None:
    source = CONFTEST.read_text(encoding="utf-8")

    assert "wecom_ability" + "_service" not in _fixture_block(source, "next_app")
    assert "wecom_ability" + "_service" not in _fixture_block(source, "next_client")
