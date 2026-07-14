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
    assert "bash scripts/ci/run_architecture_gates.sh --mode" in source
    assert "dependency-audit:" in source
    assert "python -m pip_audit -r requirements.lock --require-hashes --progress-spinner=off" in source
    assert "npm audit --audit-level=high" in source
    assert source.count("python -m pip install --require-hashes -r requirements.lock") == 4
    assert source.count("cache-dependency-path: requirements.lock") == 4
    assert "timeout-minutes: 8" in source
    assert "force_full != 'true'" not in source
    assert "full-regression:" in source
    assert "uses: ./.github/workflows/full-regression.yml" in source
    assert "needs.select.outputs.needs_full_ci == 'true'" in source
    assert source.count("needs.select.outputs.needs_full_ci != 'true'") == 2
    assert "- full-regression" in source
    assert "- dependency-audit" in source
    assert "full-regression={needs.get('full-regression', {}).get('result', 'missing')}_but_required" in source
    assert not LEGACY_CI_WORKFLOW.exists()


def test_full_regression_owns_full_pytest_and_full_frontend() -> None:
    source = _source(FULL_REGRESSION_WORKFLOW)

    assert "name: Full Regression" in source
    assert "workflow_dispatch:" in source
    assert "workflow_call:" in source
    assert 'cron: "0 18 * * *"' in source
    assert "full-python-shard:" in source
    assert "fail-fast: false" in source
    assert "max-parallel: 8" in source
    assert source.count("shard_index:") == 8
    for shard_index in range(8):
        assert f"shard_index: {shard_index}" in source
        assert f"shard_label: {shard_index + 1}-of-8" in source
    assert "python scripts/ci/select_pytest_shard.py" in source
    assert "--shard-total 8" in source
    assert "--duration-baseline docs/ci/pytest_duration_baseline.json" in source
    assert "set -o pipefail" in source
    assert "pytest_files=()" in source
    assert "while IFS= read -r test_file; do" in source
    assert 'pytest_files+=("$test_file")' in source
    assert 'done < "$RUNNER_TEMP/pytest-shard-files.txt"' in source
    assert "mapfile" not in source
    assert 'python -m pytest "${pytest_files[@]}" -n auto --dist=loadfile -q' in source
    assert "--junitxml=" in source
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source
    assert "timeout-minutes: 25" in source
    assert "bash scripts/ci/run_architecture_gates.sh --mode full" in source
    assert "python scripts/ci/check_dependency_security.py" in source
    assert "python -m pip_audit -r requirements.lock --require-hashes --progress-spinner=off" in source
    assert "python -m pip install --require-hashes -r requirements.lock" in source
    assert "performance-regression:" in source
    assert "python scripts/ops/bootstrap_database.py" in source
    assert "python tools/check_critical_read_performance.py" in source
    assert "critical-read-performance.json" in source
    assert "npm audit --audit-level=high" in source
    assert "npm run typecheck" in source
    assert "npm run build:frontend" in source
    assert "npm run test:frontend:all" in source


def test_full_regression_runs_governance_once_and_ci_fast_does_not_duplicate_it() -> None:
    full_source = _source(FULL_REGRESSION_WORKFLOW)
    ci_fast_source = _source(CI_FAST_WORKFLOW)

    assert full_source.count("run_governance:") == 2
    assert "type: boolean" in full_source
    assert "default: true" in full_source
    assert "full-governance:" in full_source
    assert "github.event_name == 'schedule' || inputs.run_governance == true" in full_source
    assert "github.event_name != 'workflow_call'" not in full_source
    assert full_source.count("python scripts/ci/check_dependency_security.py") == 1
    assert full_source.count("bash scripts/ci/run_architecture_gates.sh --mode full") == 1
    assert "uses: ./.github/workflows/full-regression.yml\n    with:\n      run_governance: false" in ci_fast_source


def test_siyuan_production_deploy_waits_for_successful_ci_fast_on_main() -> None:
    source = _source(DEPLOY_WORKFLOW)

    assert "name: Deploy to Production" in source
    assert "workflow_run:" in source
    assert 'workflows: ["CI Fast"]' in source
    assert "types: [completed]" in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "github.event.workflow_run.head_branch == 'main'" in source
    assert "push:" not in source
    assert "schedule:" not in source
    assert "secrets.DEPLOY_HOST" in source
    assert "secrets.DEPLOY_USER" in source
    assert "secrets.DEPLOY_SSH_KEY" in source
    assert "set -o pipefail" in source
    assert "printf '%s\\n' \"$after_sha\" > .release-sha" in source
    assert "python scripts/ops/check_admin_read_pages_smoke.py" in source
    assert "tee /tmp/aicrm-admin-read-pages-smoke.json" in source


def test_siyuan_overlay_does_not_add_upstream_manual_promotion_workflow() -> None:
    assert not (ROOT / ".github" / "workflows" / "promote-production.yml").exists()


def test_architecture_gate_script_has_fast_db_and_full_modes() -> None:
    script = _source(ROOT / "scripts" / "ci" / "run_architecture_gates.sh")

    assert "MODE=\"full\"" in script
    assert "run_fast()" in script
    assert "run_db()" in script
    assert "run_full_only()" in script
    assert "tools/check_route_ownership_manifest.py" in script
    assert "scripts/ci/update_route_policy_manifest.py --check" in script
    assert "tools/check_repository_ownership.py" in script
    assert "tools/check_admin_route_auth.py" in script
    assert "tools/check_db_access_boundary.py" in script
    assert "tools/check_sql_static_guard.py" in script
    assert "tests/test_alembic_revision_chain.py" in script
    assert "tools/check_background_job_contract.py" in script
    assert "scripts/ci/check_dependency_security.py" in script
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
