from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/cloud_orchestrator_run_due_route_inventory.md"


def _text() -> str:
    return INVENTORY.read_text(encoding="utf-8")


def test_run_due_inventory_exists_and_has_matrix():
    assert INVENTORY.exists()
    text = _text()

    assert "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix" in text
    assert "| 调用方 | 文件/入口 | 动作 | API | Method | Handler | CommandBus | Runtime 行为 | SideEffectPlan | Closeout 状态 | Smoke |" in text
    assert "API-only / timer-only" in text


def test_run_due_inventory_covers_callers_and_boundaries():
    text = _text()
    required = [
        "cron / timer caller",
        "manual admin caller",
        "tests / scripts caller",
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        "/api/admin/cloud-orchestrator/campaigns/run-due/preview",
        "api_plan_cloud_campaign_run_due",
        "api_preview_cloud_campaign_run_due",
        "PreviewCloudCampaignRunDueCommand",
        "PlanCloudCampaignRunDueCommand",
        "SideEffectPlan",
        "AuditLedger",
        "ExternalCallAttempt",
        "process_due_campaign_members",
        "production_compat rollback deleted",
        "legacy_fallback_allowed=false",
        "deletion_locked",
        "automation-conversion/jobs/run-due",
        "out-of-scope",
    ]
    for item in required:
        assert item in text

    assert "real_external_call_executed=false" in text
    assert "campaign_runtime_executed=false" in text
    assert "automation_runtime_executed=false" in text
    assert "wecom_send_executed=false" in text
