from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "docs/architecture/post_legacy_next_development_rules.md"
CONTRACT = ROOT / "docs/development/codex_post_legacy_development_contract.md"


def test_post_legacy_development_rules_document_exists_and_freezes_next_runtime() -> None:
    text = RULES.read_text(encoding="utf-8")

    for phrase in [
        "所有新功能必须 Next-owned",
        "禁止新增 production_compat",
        "禁止新增 legacy Flask forward",
        "禁止新增 compatibility facade",
        "route registry",
        "production route ownership manifest",
        "no-real-external",
    ]:
        assert phrase in text


def test_post_legacy_development_rules_require_reuse_of_existing_modules() -> None:
    text = RULES.read_text(encoding="utf-8")

    for phrase in [
        "aicrm_next.customer_read_model",
        "aicrm_next.identity_contact",
        "aicrm_next.common_operation_members",
        "aicrm_next.cloud_orchestrator",
        "aicrm_next.automation_engine",
        "aicrm_next.commerce",
        "aicrm_next.public_product",
        "aicrm_next.media_library",
        "aicrm_next.customer_tags",
        "aicrm_next.questionnaire",
    ]:
        assert phrase in text


def test_codex_post_legacy_contract_exists_and_blocks_drift() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    for phrase in [
        "每次开发前必须读取",
        "existing module search",
        "不允许恢复 `production_compat`",
        "不允许新增 `forward_to_legacy_flask`",
        "不允许新建 legacy facade",
        "不允许默认真实外部调用",
        "不允许页面/API 分离成壳",
        "不允许按钮先上、API 后补",
        "不允许不写 smoke",
        "不允许不登记 route owner",
        "不允许跳过 strict guard",
    ]:
        assert phrase in text
