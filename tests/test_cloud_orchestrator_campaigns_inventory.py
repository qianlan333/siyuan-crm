from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/cloud_orchestrator_campaigns_route_inventory.md"


def _text() -> str:
    return INVENTORY.read_text(encoding="utf-8")


def test_campaign_inventory_exists_and_has_contract_matrix():
    assert INVENTORY.exists()
    text = _text()

    assert "Frontend API Backend Contract Matrix" in text
    assert "Deletion Closeout Status Matrix" in text
    assert "| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | Repo/Read Model | 外部副作用 | 本组决策 | Smoke |" in text
    assert "| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | Closeout 状态 | Smoke |" in text
    assert "cloud_campaigns_workspace.html" in text
    assert "/admin/cloud-orchestrator/campaigns" in text


def test_campaign_inventory_covers_read_write_and_timer_boundaries():
    text = _text()
    required = [
        "/api/admin/cloud-orchestrator/campaigns",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps",
        "/api/admin/cloud-orchestrator/campaigns/batch-start",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/start",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/pause",
        "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/reject",
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        "/api/admin/cloud-orchestrator/campaigns/run-due/preview",
    ]
    for item in required:
        assert item in text

    assert "Next safe-mode planner" in text
    assert "production_compat rollback removed" in text
    assert "legacy_fallback_allowed=false" in text
    assert "legacy fallback removed" in text
    assert "locked: Next read model only" in text
    assert "Next CommandBus" in text
    assert "No real WeCom send" in text
    assert "No automation runtime" in text
    assert "Media upload remains locked" in text
