from __future__ import annotations

from tools.doc_paths import read_experiment_doc


def _read_doc(name: str) -> str:
    return read_experiment_doc(name)


def test_fast_execution_plan_lists_all_batches() -> None:
    text = _read_doc("fast_readonly_replacement_execution_plan.md")
    for batch in (
        "media_readonly",
        "product_readonly",
        "customer_readonly",
        "user_ops_readonly",
        "questionnaire_readonly",
    ):
        assert batch in text
    assert "Retired Automation Conversion Readonly Batch" in text
    assert "automation_readonly" not in text


def test_fast_execution_plan_keeps_writes_excluded() -> None:
    text = _read_doc("fast_readonly_replacement_execution_plan.md")
    for forbidden in (
        "no old system write endpoint",
        "no Next write route with production effect",
        "cloud storage upload",
        "WeCom media upload",
        "checkout",
        "H5 submit",
        "workflow runtime",
    ):
        assert forbidden in text


def test_fast_execution_plan_has_rollbacks_for_all_batches() -> None:
    text = _read_doc("fast_readonly_replacement_execution_plan.md")
    for flag in (
        "AICRM_NEXT_ROUTE_MEDIA_READONLY=false",
        "AICRM_NEXT_ROUTE_PRODUCT_READONLY=false",
        "AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false",
        "AICRM_NEXT_ROUTE_USER_OPS_READONLY=false",
        "AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false",
    ):
        assert flag in text


def test_human_test_tasks_cover_all_batches() -> None:
    text = _read_doc("fast_readonly_human_test_tasks.md")
    for label in (
        "Batch 1: Media Library Readonly",
        "Batch 2: Product Management Readonly",
        "Batch 3: Customer Read Model Readonly",
        "Batch 4: User Ops Readonly",
        "Batch 5: Questionnaire Readonly",
    ):
        assert label in text
    assert "Retired Automation Conversion Readonly Batch" in text
    assert "overview\n- pools\n- members list" not in text


def test_fast_docs_do_not_mark_production_ready_or_approved() -> None:
    for name in ("fast_readonly_replacement_execution_plan.md", "fast_readonly_human_test_tasks.md"):
        text = _read_doc(name)
        assert "production_ready" not in text
        assert "production_approved" not in text
        assert "approved_for_production" not in text


def test_fast_docs_have_no_production_hosts_or_secrets() -> None:
    for name in ("fast_readonly_replacement_execution_plan.md", "fast_readonly_human_test_tasks.md"):
        lowered = _read_doc(name).lower()
        for forbidden in ("prod.example", "https://prod", "http://prod", "secret=", "password=", "api_key=", "token="):
            assert forbidden not in lowered
