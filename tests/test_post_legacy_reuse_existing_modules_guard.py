from __future__ import annotations

from pathlib import Path

from scripts.check_no_new_legacy import check_post_legacy_architecture_freeze, run_checks


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "docs/architecture/post_legacy_next_development_rules.md"
CONTRACT = ROOT / "docs/development/codex_post_legacy_development_contract.md"


def test_reuse_rules_cover_no_parallel_module_categories() -> None:
    combined = RULES.read_text(encoding="utf-8") + "\n" + CONTRACT.read_text(encoding="utf-8")

    for phrase in [
        "duplicate checkout",
        "duplicate media upload",
        "duplicate customer selector",
        "duplicate tag catalog",
        "duplicate broadcast sender",
        "成员选择先搜 customer/member/identity/ops",
        "群发先搜 cloud_orchestrator/automation/user_ops",
        "支付先搜 commerce/public_product/payment adapters",
        "媒体先搜 media_library",
        "标签先搜 customer_tags",
    ]:
        assert phrase in combined


def test_post_legacy_architecture_freeze_guard_passes_current_repo() -> None:
    assert check_post_legacy_architecture_freeze(ROOT) == []


def test_strict_guard_includes_post_legacy_architecture_freeze() -> None:
    result = run_checks(strict=True)

    assert result["ok"] is True
    assert result["violations"] == []
