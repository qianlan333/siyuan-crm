from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_old_automation_conversion_fixtures_are_removed() -> None:
    assert not (ROOT / "tests" / "fixtures" / "old_automation_conversion").exists()
    assert not (ROOT / "experiments" / "ai_crm_next" / "tests" / "fixtures" / "old_automation_conversion").exists()


def test_old_automation_conversion_experiment_parity_tools_are_removed() -> None:
    retired_paths = [
        ROOT / "experiments" / "ai_crm_next" / "tools" / "compare_automation_conversion_parity.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "automation_readonly_gray_smoke.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_6_automation_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "seed_old_flask_automation_sample.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_automation_conversion_parity.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_automation_readonly_gray_smoke.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_6_automation_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_seed_old_flask_automation_sample.py",
    ]
    for path in retired_paths:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_retired_reply_monitor_readiness_tool_is_removed() -> None:
    assert not (ROOT / "tools" / "check_reply_monitor_run_due_readiness.py").exists()


def test_retired_experiment_canary_readiness_tools_are_removed() -> None:
    retired_paths = [
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_1_media_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_1_media_production_signoff_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_2_product_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_3_customer_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_4_user_ops_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_5_questionnaire_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_production_canary_approval_package.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "generate_gray_release_report.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_1_media_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_1_media_production_signoff_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_2_product_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_3_customer_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_4_user_ops_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_5_questionnaire_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_gray_release_runbook.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_production_canary_approval_package.py",
    ]
    for path in retired_paths:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_experiment_remaining_work_queue_is_archived() -> None:
    assert not (ROOT / "experiments" / "ai_crm_next" / "docs" / "remaining_work_queue.md").exists()
    assert (ROOT / "docs" / "archive" / "experiments_ai_crm_next" / "docs" / "remaining_work_queue.md").exists()


def test_retired_experiment_local_evidence_helpers_are_removed() -> None:
    retired_paths = [
        ROOT / "experiments" / "ai_crm_next" / "tools" / "capture_frontend_screenshots.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "readonly_http_dual_run.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "seed_old_flask_customer_sample.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "seed_old_flask_questionnaire_sample.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_frontend_route_smoke.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_readonly_http_dual_run.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_seed_old_flask_customer_sample.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_seed_old_flask_questionnaire_sample.py",
    ]
    for path in retired_paths:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_historical_experiment_planning_docs_are_archived() -> None:
    archived_docs = [
        "customer_read_model_sample_data_checklist.md",
        "feature_parity_matrix.md",
        "final_gap_analysis.md",
        "migration_strategy.md",
        "module_status_matrix.md",
        "questionnaire_readonly_sample_and_fake_checklist.md",
        "readonly_http_dual_run_strategy.md",
        "real_postgres_integration_run.md",
        "route_level_proxy_template.md",
    ]
    for filename in archived_docs:
        active_path = ROOT / "experiments" / "ai_crm_next" / "docs" / filename
        archive_path = ROOT / "docs" / "archive" / "experiments_ai_crm_next" / "docs" / filename
        assert not active_path.exists(), str(active_path.relative_to(ROOT))
        assert archive_path.exists(), str(archive_path.relative_to(ROOT))


def test_historical_experiment_route_and_parity_docs_are_archived() -> None:
    archived_docs = [
        "commerce_parity_strategy.md",
        "customer_read_model_parity_strategy.md",
        "customer_read_model_route_cutover_manifest.md",
        "frontend_route_manifest.md",
        "media_library_parity_strategy.md",
        "media_library_route_cutover_manifest.md",
        "product_management_route_cutover_manifest.md",
        "questionnaire_parity_strategy.md",
        "questionnaire_readonly_route_cutover_manifest.md",
        "user_ops_parity_strategy.md",
        "user_ops_readonly_route_cutover_manifest.md",
        "user_ops_readonly_sample_and_drift_checklist.md",
    ]
    for filename in archived_docs:
        active_path = ROOT / "experiments" / "ai_crm_next" / "docs" / filename
        archive_path = ROOT / "docs" / "archive" / "experiments_ai_crm_next" / "docs" / filename
        assert not active_path.exists(), str(active_path.relative_to(ROOT))
        assert archive_path.exists(), str(archive_path.relative_to(ROOT))


def test_experiment_workspace_snapshot_is_archived() -> None:
    active_root = ROOT / "experiments" / "ai_crm_next"
    archive_root = ROOT / "docs" / "archive" / "experiments_ai_crm_next"
    archived_docs = [
        "api_contracts.md",
        "architecture.md",
        "frontend_parity_plan.md",
        "postgres_integration_testing.md",
    ]
    archived_workspace_entries = [
        ".gitignore",
        "alembic.ini",
        "pyproject.toml",
        "migrations/env.py",
        "scripts/run_postgres_integration_tests.sh",
        "tools/doc_paths.py",
        "tests/test_commerce_contract.py",
        "tests/fixtures/old_user_ops/overview.default.json",
    ]

    assert (active_root / "README.md").exists()
    for child in ("docs", "tests", "tools", "scripts", "migrations"):
        assert not any((active_root / child).rglob("*")), str((active_root / child).relative_to(ROOT))
    assert not (active_root / "pyproject.toml").exists()
    assert not (active_root / "alembic.ini").exists()
    for filename in archived_docs:
        assert (archive_root / "docs" / filename).exists(), filename
    for filename in archived_workspace_entries:
        assert (archive_root / "workspace" / filename).exists(), filename


def test_retired_automation_conversion_split_blueprint_is_removed() -> None:
    assert not (ROOT / "docs" / "refactor" / "automation-conversion-split-blueprint.md").exists()
