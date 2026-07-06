from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
INITIAL_PR10_TABLES = {
    "automation_member",
    "automation_execution_trace",
    "conversion_dispatch_log",
    "user_ops_lead_pool_current",
    "user_ops_lead_pool_history",
    "user_ops_pool_current",
    "user_ops_pool_history",
    "user_ops_send_records",
    "user_ops_deferred_jobs",
    "message_batches",
    "message_batch_items",
    "marketing_automation_question_rules",
    "marketing_automation_configs",
}
EVENT_EFFECT_TABLES = {
    "domain_event_outbox",
    "external_push_delivery",
    "outbound_webhook_deliveries",
    "outbound_event_outbox",
    "internal_event",
    "internal_event_consumer_run",
    "internal_event_consumer_attempt",
    "external_effect_job",
    "external_effect_attempt",
}
CAMPAIGN_AUTOMATION_BOUNDARY_TABLES = {
    "segments",
    "segment_member_snapshots",
    "campaigns",
    "campaign_segments",
    "campaign_steps",
    "campaign_members",
    "automation_group_ops_plans",
    "automation_group_ops_plan_groups",
    "automation_group_ops_plan_nodes",
    "automation_group_ops_webhook_events",
    "automation_group_ops_plan_scope",
    "automation_group_ops_plan_member",
    "automation_group_ops_plan_segmentation",
    "automation_group_ops_trigger_event",
    "automation_group_ops_execution_log",
    "audience_rule",
    "audience_rule_version",
    "audience_rule_result",
}
LEGACY_AUTOMATION_PROGRAM_TABLES = {
    "automation_workflow_execution_item",
    "automation_workflow_execution",
    "automation_workflow_node_content_variant",
    "automation_workflow_node_content",
    "automation_workflow_node_transition",
    "automation_workflow_node",
    "automation_workflow_goal",
    "automation_workflow",
    "automation_task_plan_v2",
    "automation_stage_entry_v2",
    "automation_membership_v2",
    "automation_event_v2",
    "automation_member_audience_entry",
    "automation_program_member_stage_history",
    "automation_program_member",
    "automation_program_admission_attempt",
    "automation_program_channel_binding",
    "automation_program_config_block",
    "automation_operation_task",
    "automation_event",
    "automation_program",
}
MATERIAL_LIBRARY_TABLES = {
    "image_library",
    "image_library_variants",
    "miniprogram_library",
    "attachment_library",
}
OWNED_LIFECYCLES = {"canonical", "read_model", "event", "queue", "config"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate data table lifecycle governance.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest).resolve()
    violations = check_data_table_lifecycle(root=root, manifest_path=manifest_path)
    if violations:
        print("Data table lifecycle check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Data table lifecycle check OK: {manifest_path}")
    return 0


def check_data_table_lifecycle(root: Path = ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> list[str]:
    manifest = _load_manifest(manifest_path)
    tables = manifest["tables"]
    violations: list[str] = []

    required_tables = (
        INITIAL_PR10_TABLES
        | EVENT_EFFECT_TABLES
        | CAMPAIGN_AUTOMATION_BOUNDARY_TABLES
        | LEGACY_AUTOMATION_PROGRAM_TABLES
        | MATERIAL_LIBRARY_TABLES
    )
    missing_initial = sorted(required_tables - set(tables))
    if missing_initial:
        violations.append(f"missing PR #10 lifecycle table registrations: {missing_initial}")

    for table_name, entry in sorted(tables.items()):
        if not entry.get("domain"):
            violations.append(f"{table_name}: missing domain")
        lifecycle = entry.get("lifecycle")
        if not lifecycle:
            violations.append(f"{table_name}: missing lifecycle")
        if "drop_candidate" not in entry:
            violations.append(f"{table_name}: missing drop_candidate")
        if lifecycle == "retired" and not entry.get("replacement"):
            violations.append(f"{table_name}: retired table must declare replacement")
        if lifecycle in OWNED_LIFECYCLES and not entry.get("write_owner"):
            violations.append(f"{table_name}: {lifecycle} table must declare write_owner")

    violations.extend(_retired_runtime_reference_violations(root, tables))
    violations.extend(_retired_fixture_policy_violations(root, tables))
    violations.extend(_future_create_table_registration_violations(root, manifest))
    return violations


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("tables"), dict):
        raise ValueError("data table lifecycle manifest must be a mapping with a tables mapping")
    return raw


def _retired_runtime_reference_violations(root: Path, tables: dict[str, dict[str, Any]]) -> list[str]:
    runtime_root = root / "aicrm_next"
    violations: list[str] = []
    runtime_files = sorted(runtime_root.rglob("*.py")) if runtime_root.exists() else []
    for table_name, entry in sorted(tables.items()):
        if entry.get("lifecycle") != "retired":
            continue
        patterns = _runtime_reference_patterns(table_name)
        for path in runtime_files:
            source = path.read_text(encoding="utf-8")
            for pattern in patterns:
                if pattern.search(source):
                    violations.append(f"{path.relative_to(root)} references retired table {table_name}")
                    break
    return violations


def _retired_fixture_policy_violations(root: Path, tables: dict[str, dict[str, Any]]) -> list[str]:
    conftest_path = root / "tests" / "conftest.py"
    if not conftest_path.exists():
        return []
    source = conftest_path.read_text(encoding="utf-8")
    return [
        f"{table_name}: retired table remains in tests/conftest.py without test_fixture_policy"
        for table_name, entry in sorted(tables.items())
        if entry.get("lifecycle") == "retired"
        and table_name in source
        and not entry.get("test_fixture_policy")
    ]


def _future_create_table_registration_violations(root: Path, manifest: dict[str, Any]) -> list[str]:
    tables = set(manifest["tables"])
    guard = manifest.get("migration_guard") or {}
    baseline_prefix = int(guard.get("migration_file_prefix_after") or 0)
    migrations_root = root / "migrations" / "versions"
    violations: list[str] = []
    for path in sorted(migrations_root.glob("*.py")):
        prefix = _migration_prefix(path)
        if prefix is None or prefix <= baseline_prefix:
            continue
        created_tables = _created_tables_from_migration(path.read_text(encoding="utf-8"))
        missing = sorted(created_tables - tables)
        if missing:
            violations.append(f"{path.relative_to(root)} creates unregistered tables: {missing}")
    return violations


def _runtime_reference_patterns(table_name: str) -> list[re.Pattern[str]]:
    table = re.escape(table_name)
    return [
        re.compile(rf"\bFROM\s+{table}\b", re.IGNORECASE),
        re.compile(rf"\bJOIN\s+{table}\b", re.IGNORECASE),
        re.compile(rf"\bINSERT\s+INTO\s+{table}\b", re.IGNORECASE),
        re.compile(rf"\bUPDATE\s+{table}\b", re.IGNORECASE),
        re.compile(rf"\bDELETE\s+FROM\s+{table}\b", re.IGNORECASE),
        re.compile(rf"\bTRUNCATE\s+{table}\b", re.IGNORECASE),
        re.compile(rf"_table_exists\([^)]*[\"']{table_name}[\"']", re.IGNORECASE),
    ]


def _created_tables_from_migration(source: str) -> set[str]:
    created = set()
    created.update(
        match.group(1)
        for match in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
            source,
            flags=re.IGNORECASE,
        )
    )
    created.update(
        match.group(1)
        for match in re.finditer(
            r"op\.create_table\(\s*[\"']([a-zA-Z_][a-zA-Z0-9_]*)[\"']",
            source,
        )
    )
    return created


def _migration_prefix(path: Path) -> int | None:
    match = re.match(r"(\d{4})_", path.name)
    if not match:
        return None
    return int(match.group(1))


if __name__ == "__main__":
    sys.exit(main())
