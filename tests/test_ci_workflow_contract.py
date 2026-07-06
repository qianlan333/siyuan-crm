from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_FAST_WORKFLOW = ROOT / ".github" / "workflows" / "ci-fast.yml"
FULL_REGRESSION_WORKFLOW = ROOT / ".github" / "workflows" / "full-regression.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
LEGACY_CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_fast_uses_selector_and_single_required_result() -> None:
    source = _source(CI_FAST_WORKFLOW)

    assert "pull_request:" in source
    assert "push:" in source
    assert "scripts/ci/select_test_scope.py --github-output" in source
    assert "python -m pytest tests/ -n auto" not in source
    assert "ci-fast-result:" in source
    assert "NEEDS_JSON: ${{ toJson(needs) }}" in source
    assert "job[\"result\"] not in {\"success\", \"skipped\"}" in source
    assert "needs.select.outputs.python_tests != ''" in source
    assert "needs.select.outputs.needs_postgres == 'true'" in source
    assert "needs.select.outputs.needs_postgres != 'true'" in source
    assert "needs.select.outputs.frontend_tests != ''" in source
    assert "needs.select.outputs.needs_frontend_build == 'true'" in source
    assert "Prepare PostgreSQL compatibility database" in source
    assert "CREATE ROLE aicrm_next LOGIN PASSWORD" in source
    assert "bash scripts/ci/run_architecture_gates.sh --mode" in source
    assert "force_full != 'true'" not in source
    assert not LEGACY_CI_WORKFLOW.exists()


def test_full_regression_owns_full_pytest_and_full_frontend() -> None:
    source = _source(FULL_REGRESSION_WORKFLOW)

    assert "name: Full Regression" in source
    assert "workflow_dispatch:" in source
    assert 'cron: "0 18 * * *"' in source
    assert "python -m pytest tests/ -n auto --dist=loadfile" in source
    assert "bash scripts/ci/run_architecture_gates.sh --mode full" in source
    assert "npm run typecheck" in source
    assert "npm run build:frontend" in source
    assert "npm run test:frontend:all" in source


def test_deploy_waits_for_successful_ci_fast_on_main() -> None:
    source = _source(DEPLOY_WORKFLOW)

    if "workflow_run:" in source:
        assert 'workflows: ["CI Fast"]' in source
        assert "types: [completed]" in source
        assert "github.event.workflow_run.conclusion == 'success'" in source
        assert "github.event.workflow_run.head_branch == 'main'" in source
        assert "push:" not in source
    else:
        assert "push:" in source
        assert "branches:" in source
        assert "- main" in source
        assert "Deploy via SSH" in source


def test_architecture_gate_script_has_fast_db_and_full_modes() -> None:
    script = _source(ROOT / "scripts" / "ci" / "run_architecture_gates.sh")

    assert "MODE=\"full\"" in script
    assert "run_fast()" in script
    assert "run_db()" in script
    assert "run_full_only()" in script
    assert "tools/check_route_ownership_manifest.py" in script
    assert "tools/check_repository_ownership.py" in script
    assert "tools/check_admin_route_auth.py" in script
    assert "tools/check_db_access_boundary.py" in script
    assert "tools/check_sql_static_guard.py" in script
    assert "tests/test_alembic_revision_chain.py" in script
    assert "tools/check_background_job_contract.py" in script
    assert "Unknown architecture gate mode" in script


def test_frontend_scripts_are_split_for_scoped_ci() -> None:
    package_json = _source(ROOT / "package.json")

    assert "\"test:frontend\": \"npm run test:frontend:all\"" in package_json
    assert "\"test:frontend:push-center\"" in package_json
    assert "\"test:frontend:group-ops\"" in package_json
    assert "\"test:frontend:ops-plan\"" in package_json
    assert "\"test:frontend:wecom\"" in package_json
    assert "\"test:frontend:preview\"" in package_json
    assert "\"test:frontend:business-pages\"" in package_json
