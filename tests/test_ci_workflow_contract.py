from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
REQUIRED_SMOKE_TESTS = (
    "tests/test_broadcast_jobs_service.py",
    "tests/test_run_broadcast_queue_worker.py",
    "tests/test_broadcast_jobs_wecom_private_dispatch.py",
)
SPECIALIZED_TEST_MARKERS = (
    "post_legacy",
    "post_closeout",
    "campaigns_due_calc",
    "send_task",
    "campaign_hard_delete",
    "deploy_workflow_contract",
    "ci_workflow_contract",
    "admin_auth_route_precedence",
    "wechat_pay",
    "hxc",
    "user_ops",
    "admin_shell",
    "cloud_orchestrator_external_agent",
)
REMOVED_PR_SMOKE_TESTS = (
    "tests/test_post_closeout_production_contract.py",
    "tests/test_campaigns_due_calc.py",
    "tests/test_send_task.py",
    "tests/test_campaign_hard_delete.py",
    "tests/test_ci_workflow_contract.py",
    "tests/test_deploy_workflow_contract.py",
    "tests/test_admin_auth_route_precedence.py",
    "tests/test_admin_shell_native.py",
    "tests/test_wechat_pay_products.py",
    "tests/test_wechat_pay_admin_transactions.py",
    "tests/test_cloud_orchestrator_external_agent.py",
)
REMOVED_MAIN_SMOKE_TESTS = (
    "tests/test_post_closeout_production_contract.py",
    "tests/test_next_source_consolidation.py",
    "tests/test_marketing_schema_init.py",
    "tests/test_campaigns_due_calc.py",
    "tests/test_send_task.py",
    "tests/test_campaign_hard_delete.py",
    "tests/test_ci_workflow_contract.py",
    "tests/test_deploy_workflow_contract.py",
    "tests/test_user_ops_import_parsers.py",
    "tests/test_user_ops_page_service_helpers.py",
    "tests/test_hxc_dashboard_api_contract.py",
    "tests/test_admin_auth_route_precedence.py",
    "tests/test_admin_shell_native.py",
    "tests/test_wechat_pay_products.py",
    "tests/test_wechat_pay_admin_transactions.py",
    "tests/test_cloud_orchestrator_external_agent.py",
)


def _ci_source() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _job_block(source: str, job_name: str, next_job_name: str | None = None) -> str:
    start = source.index(f"{job_name}:")
    if next_job_name is None:
        return source[start:]
    return source[start:source.index(f"{next_job_name}:")]


def _smoke_pytest_test_paths(job_block: str) -> set[str]:
    return set(re.findall(r"tests/test_[A-Za-z0-9_]+\.py", job_block))


def test_main_push_uses_smoke_not_full_regression():
    source = _ci_source()

    main_smoke_block = _job_block(source, "main-smoke", "full-test")
    full_test_block = _job_block(source, "full-test")

    assert "if: github.event_name == 'push'" in main_smoke_block
    assert "Run main smoke tests (business-only, no PG)" in main_smoke_block
    assert "python -m pytest \\" in main_smoke_block
    assert "if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in full_test_block
    assert "python -m pytest tests/ -n auto" in full_test_block


def test_full_test_keeps_complete_regression_only():
    source = _ci_source()
    full_test_block = _job_block(source, "full-test")

    assert "if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in full_test_block
    assert "python -m pytest tests/ -n auto" in full_test_block
    assert "scripts/check_no_new_legacy.py" not in full_test_block
    assert "tools/generate_legacy_replacement_backlog.py" not in full_test_block


def test_pr_and_main_smoke_skip_architecture_guards_and_specialized_tests():
    source = _ci_source()
    smoke_blocks = (
        _job_block(source, "pr-smoke", "main-smoke"),
        _job_block(source, "main-smoke", "full-test"),
    )

    for smoke_block in smoke_blocks:
        assert "scripts/check_no_new_legacy.py" not in smoke_block
        assert "scripts/check_no_duplicate_next_source.sh" not in smoke_block
        assert "tools/generate_legacy_replacement_backlog.py" not in smoke_block
        for marker in SPECIALIZED_TEST_MARKERS:
            assert marker not in smoke_block


def test_pr_and_main_smoke_do_not_boot_pg_or_xdist_workers():
    source = _ci_source()
    smoke_blocks = (
        _job_block(source, "pr-smoke", "main-smoke"),
        _job_block(source, "main-smoke", "full-test"),
    )

    for smoke_block in smoke_blocks:
        assert "postgres:" not in smoke_block
        assert "DATABASE_URL" not in smoke_block
        assert "-n auto" not in smoke_block
        assert "--dist=loadfile" not in smoke_block
        assert "timeout-minutes: 2" in smoke_block


def test_pr_smoke_excludes_specialized_contract_and_domain_suites():
    source = _ci_source()
    pr_smoke_block = _job_block(source, "pr-smoke", "main-smoke")

    assert _smoke_pytest_test_paths(pr_smoke_block) == set(REQUIRED_SMOKE_TESTS)
    for test_path in REMOVED_PR_SMOKE_TESTS:
        assert test_path not in pr_smoke_block


def test_main_smoke_excludes_specialized_contract_and_domain_suites():
    source = _ci_source()
    main_smoke_block = _job_block(source, "main-smoke", "full-test")

    assert _smoke_pytest_test_paths(main_smoke_block) == set(REQUIRED_SMOKE_TESTS)
    for test_path in REMOVED_MAIN_SMOKE_TESTS:
        assert test_path not in main_smoke_block


def test_pr_and_main_smoke_keep_broadcast_business_smoke_tests():
    source = _ci_source()
    smoke_blocks = (
        _job_block(source, "pr-smoke", "main-smoke"),
        _job_block(source, "main-smoke", "full-test"),
    )

    for smoke_block in smoke_blocks:
        assert _smoke_pytest_test_paths(smoke_block) == set(REQUIRED_SMOKE_TESTS)
        for test_path in REQUIRED_SMOKE_TESTS:
            assert test_path in smoke_block
