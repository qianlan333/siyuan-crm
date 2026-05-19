from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_overview_segment_cards_are_rendered_from_program_dashboard_only():
    template = (
        ROOT
        / "wecom_ability_service"
        / "templates"
        / "admin_console"
        / "automation_conversion_overview_workspace.html"
    ).read_text(encoding="utf-8")
    renderer = (
        ROOT
        / "wecom_ability_service"
        / "static"
        / "admin_console"
        / "automation_overview_renderers.js"
    ).read_text(encoding="utf-8")

    assert "/api/admin/cloud-orchestrator/segments" not in template
    assert "segmentsFromDashboard" in template
    assert "automation-overview:dashboard-rendered" in template
    assert "automation-overview:dashboard-rendered" in renderer
