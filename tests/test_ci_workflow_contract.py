from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _ci_source() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def test_main_push_uses_smoke_not_full_regression():
    source = _ci_source()

    main_smoke_index = source.index("main-smoke:")
    full_test_index = source.index("full-test:")
    main_smoke_block = source[main_smoke_index:full_test_index]
    full_test_block = source[full_test_index:]

    assert "if: github.event_name == 'push'" in main_smoke_block
    assert "Run main smoke tests (PG-only, targeted)" in main_smoke_block
    assert "python -m pytest \\" in main_smoke_block
    assert "if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in full_test_block
    assert "python -m pytest tests/ -n auto" in full_test_block


def test_main_smoke_keeps_recently_touched_critical_paths():
    source = _ci_source()
    main_smoke_block = source[source.index("main-smoke:"):source.index("full-test:")]

    for test_path in (
        "tests/test_postgres_schema_retry.py",
        "tests/test_user_ops_import_parsers.py",
        "tests/test_user_ops_page_service_helpers.py",
        "tests/test_hxc_dashboard_snapshot.py",
        "tests/test_send_task.py",
        "tests/test_admin_navigation_groups.py",
        "tests/test_wechat_pay_products.py",
        "tests/test_wechat_pay_admin_transactions.py",
    ):
        assert test_path in main_smoke_block


def test_pr_smoke_covers_admin_navigation_and_wechat_pay_splits():
    source = _ci_source()
    pr_smoke_block = source[source.index("pr-smoke:"):source.index("main-smoke:")]

    assert "bash scripts/check_no_duplicate_next_source.sh" in pr_smoke_block

    for test_path in (
        "tests/test_admin_navigation_groups.py",
        "tests/test_wechat_pay_products.py",
        "tests/test_wechat_pay_admin_transactions.py",
    ):
        assert test_path in pr_smoke_block
