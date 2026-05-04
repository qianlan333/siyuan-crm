from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inventory_agent_config_workspace.py"
DOC = ROOT / "docs" / "refactor" / "js_api_phase8_agent_config_inventory.md"


def _run_inventory(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_inventory_agent_config_workspace_json_contract():
    result = _run_inventory("--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["root_contract"]["id"] == "automation-agent-config-root"
    assert "data-api-urls" in payload["root_contract"]["data_attributes"]
    assert "data-admin-action-token" in payload["root_contract"]["data_attributes"]
    assert "data-selected-template-id" in payload["root_contract"]["data_attributes"]
    assert "automation-agent-config-initial-agents" in payload["initial_json_blocks"]
    assert "automation-agent-config-initial-templates" not in payload["initial_json_blocks"]
    assert "automation-agent-config-initial-catalog" not in payload["initial_json_blocks"]
    assert "test_impact_inventory" in payload
    assert isinstance(payload["test_impact_inventory"], list)
    allowed_categories = {
        "html_contract_assertion",
        "api_contract_assertion",
        "static_js_expected_after_migration",
        "behavior_flow_test",
        "unknown",
    }
    for item in payload["test_impact_inventory"]:
        assert "file" in item
        assert "line_number" in item
        assert isinstance(item["line_number"], int)
        assert item["line_number"] > 0
        assert "matched_keyword" in item
        assert "matched_line" in item
        assert "category" in item
        assert item["category"] in allowed_categories
        assert "migration_note" in item
    assert payload["module_proposal"]
    assert payload["risk_flags"]


def test_inventory_agent_config_workspace_strict_mode_passes():
    result = _run_inventory("--strict")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Agent Config workspace inventory: OK" in result.stdout


def test_agent_config_phase8_inventory_doc_exists_with_required_sections():
    source = DOC.read_text(encoding="utf-8")

    required_sections = [
        "Phase 8A",
        "Phase 8A 非目标",
        "不拆 JS",
        "不改 API",
        "不改后端",
        "Root Contract",
        "API URL Inventory",
        "Inline JS Function Inventory",
        "Request/action Inventory",
        "State Inventory",
        "Test Impact Inventory",
        "Phase 8B Module Plan",
    ]

    for section in required_sections:
        assert section in source
