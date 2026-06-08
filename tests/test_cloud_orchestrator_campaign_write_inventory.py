from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/cloud_orchestrator_campaign_write_route_inventory.md"


def _text() -> str:
    return INVENTORY.read_text(encoding="utf-8")


def test_campaign_write_inventory_exists_and_has_commandbus_matrix():
    assert INVENTORY.exists()
    text = _text()

    assert "Frontend API CommandBus Contract Matrix" in text
    assert "| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | CommandBus | SideEffectPlan | UI 状态 | Smoke |" in text
    assert "/admin/cloud-orchestrator/campaigns" in text
    assert "cloud_campaigns_workspace.html" in text


def test_campaign_write_inventory_covers_controls_steps_and_runtime_boundaries():
    text = _text()
    required = [
        "/api/admin/cloud-orchestrator/campaigns/batch-start",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/reject",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/start",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/pause",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps/{step_index}",
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        "/api/admin/cloud-orchestrator/campaigns/run-due/preview",
        "ApproveCloudCampaignCommand",
        "RejectCloudCampaignCommand",
        "StartCloudCampaignCommand",
        "PauseCloudCampaignCommand",
        "DeleteCloudCampaignCommand",
        "BatchStartCloudCampaignsCommand",
        "AddCloudCampaignStepCommand",
        "UpdateCloudCampaignStepCommand",
        "DeleteCloudCampaignStepCommand",
    ]
    for item in required:
        assert item in text

    assert "source_status=next_command" in text
    assert "adapter_mode=real_blocked" in text
    assert "real_external_call_executed=false" in text
    assert "campaign_execute_executed=false" in text
    assert "wecom_send_executed=false" in text
    assert "Deletion Closeout Status Matrix" in text
    assert "legacy_fallback_allowed=false" in text
    assert "deletion_locked" in text
    assert "legacy fallback removed" in text
    assert "run-due and preview are now separately deletion_locked" in text
