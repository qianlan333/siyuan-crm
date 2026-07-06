from __future__ import annotations

from pathlib import Path

import yaml

from tools.check_repository_ownership import check_repository_ownership


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "architecture" / "repository_ownership.yml"
MANIFEST_PATH = ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
ADMIN_READ_REPO_PATH = ROOT / "aicrm_next" / "admin_read_model" / "repo.py"


def test_repository_ownership_current_registry_passes() -> None:
    assert check_repository_ownership(
        root=ROOT,
        registry_path=REGISTRY_PATH,
        manifest_path=MANIFEST_PATH,
    ) == []


def test_repository_ownership_targeted_declarations_are_complete() -> None:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    repositories = registry["repositories"]
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert repositories["aicrm_next/admin_config/repository.py"]["table_reads"] == [
        "admin_login_audit",
        "admin_operation_logs",
        "admin_user_roles",
        "admin_users",
        "app_settings",
        "marketing_automation_configs",
        "marketing_automation_question_rules",
        "mcp_tool_settings",
        "questionnaire_options",
        "questionnaire_questions",
        "questionnaires",
    ]
    assert repositories["aicrm_next/admin_config/repository.py"]["table_writes"] == [
        "admin_login_audit",
        "admin_operation_logs",
        "admin_user_roles",
        "admin_users",
        "app_settings",
        "marketing_automation_configs",
        "marketing_automation_question_rules",
        "mcp_tool_settings",
    ]
    assert repositories["aicrm_next/admin_jobs/repository.py"]["table_reads"] == [
        "broadcast_job_events",
        "broadcast_jobs",
        "broadcast_queue_notification_settings",
        "outbound_tasks",
        "outbound_webhook_deliveries",
        "sync_runs",
        "wecom_external_contact_event_logs",
    ]
    assert repositories["aicrm_next/admin_jobs/repository.py"]["table_writes"] == [
        "admin_operation_logs",
        "broadcast_job_hourly_reports",
        "broadcast_jobs",
        "broadcast_queue_notification_settings",
        "outbound_webhook_deliveries",
    ]
    assert repositories["aicrm_next/admin_read_model/repo.py"]["table_reads"] == [
        "admin_operation_logs",
        "ai_audience_member_current",
        "archived_messages",
        "automation_agent_config",
        "automation_agent_llm_call_log",
        "automation_agent_output",
        "automation_agent_run",
        "broadcast_jobs",
        "external_effect_job",
        "internal_event",
        "outbound_tasks",
        "outbound_webhook_deliveries",
        "questionnaire_submissions",
        "reply_message_batch",
        "sync_runs",
        "wechat_pay_orders",
        "wecom_external_contact_event_logs",
        "wecom_external_contact_follow_users",
        "wecom_external_contact_identity_map",
    ]
    assert "aicrm_next.external_push.repo" in manifest["tables"]["domain_event_outbox"]["read_owners"]
    assert "aicrm_next.external_push.repo" in manifest["tables"]["external_push_delivery"]["read_owners"]
    assert repositories["aicrm_next/ai_assist/external_campaigns_repo.py"]["table_writes"] == [
        "broadcast_jobs",
    ]
    assert repositories["aicrm_next/ai_assist/external_campaigns_repo.py"]["table_reads"] == [
        "broadcast_jobs",
        "campaign_members",
        "campaign_segments",
        "campaign_steps",
        "campaigns",
        "crm_user_identity",
        "segments",
        "user_ops_do_not_disturb_next",
        "wecom_external_contact_follow_users",
        "wecom_external_contact_identity_map",
    ]
    assert repositories["aicrm_next/send_targets/repo.py"]["table_reads"] == [
        "crm_user_identity",
        "user_ops_do_not_disturb_next",
    ]
    assert repositories["aicrm_next/send_targets/repo.py"]["table_writes"] == []
    assert repositories["aicrm_next/external_push/repo.py"]["table_writes"] == [
        "domain_event_outbox",
        "external_push_delivery",
    ]


def test_admin_read_count_allowlist_excludes_retired_tables() -> None:
    source = ADMIN_READ_REPO_PATH.read_text(encoding="utf-8")

    assert '"user_ops_deferred_jobs"' not in source
    assert '"message_batches"' not in source
    assert '"message_batch_items"' not in source


def test_repository_ownership_requires_every_repo_file(tmp_path: Path) -> None:
    _write(tmp_path / "aicrm_next" / "demo" / "repo.py", "")
    registry = _write_registry(tmp_path, repositories={})
    manifest = _write_manifest(tmp_path)

    violations = check_repository_ownership(root=tmp_path, registry_path=registry, manifest_path=manifest)

    assert [violation.rule for violation in violations] == ["repository_missing_ownership_declaration"]


def test_repository_ownership_blocks_retired_reads(tmp_path: Path) -> None:
    _write(tmp_path / "aicrm_next" / "demo" / "repo.py", "")
    registry = _write_registry(
        tmp_path,
        repositories={
            "aicrm_next/demo/repo.py": {
                "capability_owner": "aicrm_next.demo",
                "table_reads": ["retired_table"],
                "table_writes": [],
            }
        },
    )
    manifest = _write_manifest(tmp_path)

    violations = check_repository_ownership(root=tmp_path, registry_path=registry, manifest_path=manifest)

    assert [violation.rule for violation in violations] == ["repository_reads_retired_table"]


def test_repository_ownership_blocks_write_owner_mismatch(tmp_path: Path) -> None:
    _write(tmp_path / "aicrm_next" / "demo" / "repo.py", "")
    registry = _write_registry(
        tmp_path,
        repositories={
            "aicrm_next/demo/repo.py": {
                "capability_owner": "aicrm_next.demo",
                "table_reads": [],
                "table_writes": ["active_table"],
            }
        },
    )
    manifest = _write_manifest(tmp_path)

    violations = check_repository_ownership(root=tmp_path, registry_path=registry, manifest_path=manifest)

    assert [violation.rule for violation in violations] == ["repository_write_owner_mismatch"]


def test_repository_ownership_accepts_manifest_write_owner_prefix(tmp_path: Path) -> None:
    _write(tmp_path / "aicrm_next" / "demo" / "repo.py", "")
    registry = _write_registry(
        tmp_path,
        repositories={
            "aicrm_next/demo/repo.py": {
                "capability_owner": "aicrm_next.demo",
                "table_reads": ["active_table"],
                "table_writes": ["active_table"],
            }
        },
    )
    manifest = _write_manifest(tmp_path, active_write_owner="aicrm_next.demo.repository")

    assert check_repository_ownership(root=tmp_path, registry_path=registry, manifest_path=manifest) == []


def test_repository_ownership_accepts_manifest_write_owners(tmp_path: Path) -> None:
    _write(tmp_path / "aicrm_next" / "demo" / "repo.py", "")
    registry = _write_registry(
        tmp_path,
        repositories={
            "aicrm_next/demo/repo.py": {
                "capability_owner": "aicrm_next.demo",
                "table_reads": [],
                "table_writes": ["active_table"],
            }
        },
    )
    manifest = _write_manifest(
        tmp_path,
        extra_active_table_lines="""
    write_owners:
      - aicrm_next.other.repository
      - aicrm_next.demo.repository
""",
    )

    assert check_repository_ownership(root=tmp_path, registry_path=registry, manifest_path=manifest) == []


def _write_registry(tmp_path: Path, *, repositories: dict) -> Path:
    registry = tmp_path / "docs" / "architecture" / "repository_ownership.yml"
    lines = ["version: 1", "repositories:"]
    if not repositories:
        lines[-1] = "repositories: {}"
    for path, entry in repositories.items():
        lines.append(f"  {path}:")
        lines.append(f"    capability_owner: {entry['capability_owner']}")
        lines.append("    table_reads:")
        for table in entry["table_reads"]:
            lines.append(f"      - {table}")
        if not entry["table_reads"]:
            lines[-1] = "    table_reads: []"
        lines.append("    table_writes:")
        for table in entry["table_writes"]:
            lines.append(f"      - {table}")
        if not entry["table_writes"]:
            lines[-1] = "    table_writes: []"
    _write(registry, "\n".join(lines) + "\n")
    return registry


def _write_manifest(
    tmp_path: Path,
    *,
    active_write_owner: str = "aicrm_next.other.repository",
    extra_active_table_lines: str = "",
) -> Path:
    manifest = tmp_path / "docs" / "architecture" / "data_table_lifecycle_manifest.yml"
    _write(
        manifest,
        f"""
version: 1
tables:
  active_table:
    domain: tests
    lifecycle: canonical
    write_owner: {active_write_owner}
{extra_active_table_lines.rstrip()}
    replacement: none
    drop_candidate: false
  retired_table:
    domain: tests
    lifecycle: retired
    replacement: active_table
    drop_candidate: false
""",
    )
    return manifest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
