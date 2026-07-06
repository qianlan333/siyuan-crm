from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RETIRED_TOOL_WRAPPERS = {
    "compare_commerce_parity.py",
    "compare_customer_read_model_parity.py",
    "compare_media_library_parity.py",
    "compare_questionnaire_parity.py",
    "compare_user_ops_parity.py",
    "customer_read_model_gray_smoke.py",
    "media_library_gray_smoke.py",
    "product_management_gray_smoke.py",
    "questionnaire_readonly_gray_smoke.py",
    "run_gray_rehearsal_batch.py",
    "user_ops_readonly_gray_smoke.py",
}

RETIRED_GRAY_SMOKE_TESTS = {
    "test_customer_read_model_gray_smoke.py",
    "test_media_library_gray_smoke.py",
    "test_product_management_gray_smoke.py",
    "test_questionnaire_readonly_gray_smoke.py",
    "test_gray_rehearsal_batch.py",
    "test_user_ops_readonly_gray_smoke.py",
}


def test_retired_experiment_tool_wrappers_are_absent() -> None:
    tools_dir = ROOT / "experiments" / "ai_crm_next" / "tools"
    for name in RETIRED_TOOL_WRAPPERS:
        assert not (tools_dir / name).exists()
    assert not (tools_dir / "_root_tool_wrapper.py").exists()


def test_retired_experiment_gray_smoke_tests_are_absent() -> None:
    tests_dir = ROOT / "experiments" / "ai_crm_next" / "tests"
    for name in RETIRED_GRAY_SMOKE_TESTS:
        assert not (tests_dir / name).exists()


def test_experiment_tools_do_not_use_root_tool_wrapper() -> None:
    tools_dir = ROOT / "experiments" / "ai_crm_next" / "tools"
    for path in tools_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "load_root_tool" not in text
        assert "_root_tool_wrapper" not in text
