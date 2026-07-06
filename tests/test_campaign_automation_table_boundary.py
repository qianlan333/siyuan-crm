from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
BOUNDARY_DOC = ROOT / "docs" / "architecture" / "campaign_automation_table_boundary.md"

CAMPAIGN_TABLES = {
    "campaigns",
    "campaign_segments",
    "campaign_steps",
    "campaign_members",
}
GROUP_OPS_TABLES = {
    "automation_group_ops_plans",
    "automation_group_ops_plan_groups",
    "automation_group_ops_plan_nodes",
    "automation_group_ops_webhook_events",
    "automation_group_ops_plan_member",
    "automation_group_ops_trigger_event",
    "automation_group_ops_execution_log",
}
RETIRED_PROGRAM_TABLES = {
    "automation_program",
    "automation_program_member",
    "automation_workflow",
    "automation_workflow_execution",
}


def _tables() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert isinstance(data.get("tables"), dict)
    return data["tables"]


def test_campaign_tables_remain_active_until_command_bus_convergence() -> None:
    tables = _tables()
    for table_name in CAMPAIGN_TABLES:
        entry = tables[table_name]
        assert entry["domain"] == "campaign"
        assert entry["lifecycle"] in {"canonical", "queue"}
        assert entry["drop_candidate"] is False
        assert entry.get("replacement")

    for table_name in ("campaigns", "campaign_members"):
        assert "external_effect_job" in str(tables[table_name].get("replacement", ""))


def test_group_ops_tables_are_active_automation_boundary() -> None:
    tables = _tables()
    for table_name in GROUP_OPS_TABLES:
        entry = tables[table_name]
        assert entry["domain"] == "automation_group_ops"
        assert entry["drop_candidate"] is False
        assert entry.get("write_owner")


def test_legacy_program_tables_are_retired_and_guarded() -> None:
    tables = _tables()
    for table_name in RETIRED_PROGRAM_TABLES:
        entry = tables[table_name]
        assert entry["lifecycle"] == "retired"
        assert entry["drop_after"] == "0053_retire_legacy_automation_tables"
        assert entry["runtime_entrypoints"] == []


def test_boundary_doc_names_all_campaign_automation_roles() -> None:
    source = BOUNDARY_DOC.read_text(encoding="utf-8")
    for phrase in (
        "campaigns",
        "campaign_members",
        "automation_group_ops_plans",
        "external_effect_job",
        "automation_program",
        "marketing_automation_configs",
    ):
        assert phrase in source
