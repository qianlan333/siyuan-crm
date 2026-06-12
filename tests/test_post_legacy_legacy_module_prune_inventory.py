from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/post_legacy_legacy_module_prune_inventory.md"
HTTP_INIT = ROOT / "wecom_ability_service/http/__init__.py"

DELETED_MODULES = [
    "wecom_ability_service/http/admin_hxc_dashboard.py",
    "wecom_ability_service/http/admin_auth_routes.py",
    "wecom_ability_service/http/cloud_orchestrator_campaigns.py",
    "wecom_ability_service/http/cloud_orchestrator_campaign_details.py",
    "wecom_ability_service/http/cloud_orchestrator_media.py",
    "wecom_ability_service/http/cloud_orchestrator_endpoint.py",
    "wecom_ability_service/http/cloud_orchestrator_pages.py",
    "wecom_ability_service/http/cloud_orchestrator_plans.py",
    "wecom_ability_service/http/cloud_orchestrator_segments.py",
    "wecom_ability_service/http/automation_conversion.py",
    "wecom_ability_service/http/automation_conversion_runtime_api.py",
    "wecom_ability_service/http/automation_conversion_task_runtime.py",
    "wecom_ability_service/http/automation_conversion_execution_outbound.py",
    "wecom_ability_service/http/automation_conversion_member_api.py",
    "wecom_ability_service/http/automation_conversion_compat.py",
    "wecom_ability_service/http/automation_conversion_delivery.py",
    "wecom_ability_service/http/customer_automation.py",
]


def test_prune_inventory_exists_and_has_required_columns() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for phrase in ["legacy module / package", "原用途", "替代 Next 模块", "当前引用", "删除决策", "测试"]:
        assert phrase in text


def test_deleted_legacy_modules_are_removed_and_not_registered() -> None:
    inventory_text = INVENTORY.read_text(encoding="utf-8")
    http_init_text = HTTP_INIT.read_text(encoding="utf-8")

    for module in DELETED_MODULES:
        assert f"`{module}`" in inventory_text
        assert not (ROOT / module).exists()
        assert f'"{Path(module).stem}"' not in http_init_text
        assert f".{Path(module).stem} import" not in http_init_text


def test_pr9_deleted_legacy_modules_are_marked_deleted_in_inventory() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for module in DELETED_MODULES:
        assert f"`{module}`" in text
        assert not (ROOT / module).exists()
    assert "deleted_in_pr9" in text
    assert "PR-9 test migration" in text
