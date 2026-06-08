from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_runtime_has_no_active_frontend_button_contract():
    frontend_paths = [
        ROOT / "aicrm_next/frontend_compat/static",
        ROOT / "aicrm_next/frontend_compat/templates",
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for root in frontend_paths
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".js", ".html"}
    )

    assert "/api/admin/automation-conversion/tasks/run-due" not in combined
    assert "/api/admin/automation-conversion/execution-items/" not in combined or "send-via-bazhuayu" not in combined


def test_inventory_documents_api_only_and_out_of_scope_frontend_state():
    text = (ROOT / "docs/architecture/automation_workspace_runtime_route_inventory.md").read_text(encoding="utf-8")

    assert "API-only / timer-only" in text
    assert "No direct runtime caller found" in text
    assert "member/manual/focus/SOP" in text
    assert "not marked locked by this group" in text
