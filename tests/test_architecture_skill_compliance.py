from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_architecture_skill_compliance.py"
spec = importlib.util.spec_from_file_location("architecture_skill_compliance", CHECKER_PATH)
checker = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(checker)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_current_repo_passes_architecture_skill_compliance() -> None:
    report = checker.build_report(ROOT)

    assert report["ok"], report["blockers"]
    assert report["blockers"] == []


def test_blocks_openclaw_live_path_and_import(tmp_path: Path) -> None:
    (tmp_path / "openclaw_service").mkdir()
    write(tmp_path / "aicrm_next/integration_gateway/api.py", "import openclaw_service\n")

    blockers = checker.check_openclaw(tmp_path)

    reasons = {item["reason"] for item in blockers}
    assert "openclaw_service_live_path_exists" in reasons
    assert "imports_openclaw_service" in reasons


def test_allows_historical_openclaw_doc_context(tmp_path: Path) -> None:
    write(
        tmp_path / "docs/history.md",
        "Historical note: `openclaw_service/` was deleted and must not be reintroduced.\n",
    )

    assert checker.check_openclaw(tmp_path) == []


def test_blocks_frontend_compat_database_driver_and_sql(tmp_path: Path) -> None:
    write(
        tmp_path / "aicrm_next/frontend_compat/legacy_routes.py",
        "import psycopg\nQUERY = 'SELECT * FROM customers'\n",
    )

    blockers = checker.check_frontend_compat_sql(tmp_path)

    assert len(blockers) >= 2
    assert {item["reason"] for item in blockers} == {"frontend_compat_sql_or_driver"}


def test_blocks_api_importing_other_context_repo(tmp_path: Path) -> None:
    write(
        tmp_path / "aicrm_next/questionnaire/api.py",
        "from aicrm_next.customer_read_model.repo import CustomerRepository\n",
    )

    blockers = checker.check_api_cross_context_repo_imports(tmp_path)

    assert blockers == [
        {
            "path": "aicrm_next/questionnaire/api.py",
            "line": 1,
            "reason": "api_imports_other_context_repo_or_service",
            "module": "aicrm_next.customer_read_model.repo",
        }
    ]


def test_pr_template_requires_sections_and_checker(tmp_path: Path) -> None:
    write(tmp_path / "docs/development/codex_task_template.md", "## Summary\n")

    blockers = checker.check_pr_template(tmp_path)

    reasons = {item["reason"] for item in blockers}
    missing_sections = {item.get("section") for item in blockers}
    assert "template_missing_pr_section" in reasons
    assert "template_missing_compliance_checker" in reasons
    assert {"Architecture boundary", "Safety", "Verification", "Rollback"} <= missing_sections


def test_blocks_fixture_as_production_data_in_live_doc(tmp_path: Path) -> None:
    write(tmp_path / "docs/live.md", "Production data can use local_contract rows for success.\n")

    blockers = checker.check_fixture_production_docs(tmp_path)

    assert blockers == [
        {
            "path": "docs/live.md",
            "line": 1,
            "reason": "fixture_described_as_production_data",
        }
    ]
