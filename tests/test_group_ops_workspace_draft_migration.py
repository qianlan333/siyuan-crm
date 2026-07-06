from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "migrations" / "versions" / "0047_group_ops_workspace_drafts.py"
REQUEST_REVIEW_MIGRATION_PATH = ROOT / "migrations" / "versions" / "0048_group_ops_workspace_request_review_audit_action.py"


def _migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _request_review_migration_source() -> str:
    return REQUEST_REVIEW_MIGRATION_PATH.read_text(encoding="utf-8")


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("group_ops_workspace_drafts_migration", MIGRATION_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_group_ops_workspace_draft_migration_is_executable_in_postgres_offline_mode(monkeypatch) -> None:
    module = _load_migration_module()
    buffer = StringIO()
    context = MigrationContext.configure(
        url="postgresql://",
        opts={"as_sql": True, "output_buffer": buffer},
    )
    operations = Operations(context)

    monkeypatch.setattr(module, "op", operations)

    module.upgrade()

    generated_sql = buffer.getvalue()
    assert "CREATE TABLE IF NOT EXISTS group_ops_workspace_drafts" in generated_sql
    assert "CREATE TABLE IF NOT EXISTS group_ops_workspace_draft_items" in generated_sql
    assert "CREATE TABLE IF NOT EXISTS group_ops_workspace_draft_audit_logs" in generated_sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_drafts_draft_id" in generated_sql


def test_group_ops_workspace_draft_migration_revision_chain() -> None:
    source = _migration_source()
    request_review_source = _request_review_migration_source()

    assert 'revision = "0047_group_ops_workspace_drafts"' in source
    assert 'down_revision = "0046_ai_audience_publish_and_subscription_dedupe"' in source
    assert 'revision = "0048_group_ops_workspace_request_review_audit_action"' in request_review_source
    assert 'down_revision = "0047_group_ops_workspace_drafts"' in request_review_source


def test_group_ops_workspace_draft_tables_fields_indexes_and_constraints() -> None:
    source = _migration_source()

    for expected in [
        "CREATE TABLE IF NOT EXISTS group_ops_workspace_drafts",
        "CREATE TABLE IF NOT EXISTS group_ops_workspace_draft_items",
        "CREATE TABLE IF NOT EXISTS group_ops_workspace_draft_audit_logs",
        "draft_id TEXT NOT NULL",
        "tenant_id TEXT NOT NULL DEFAULT 'aicrm'",
        "admin_scope TEXT NOT NULL DEFAULT ''",
        "source_plan_id TEXT NOT NULL DEFAULT ''",
        "draft_status TEXT NOT NULL DEFAULT 'draft'",
        "CHECK (draft_status IN ('draft', 'ready_for_review', 'archived', 'rejected'))",
        "version INTEGER NOT NULL DEFAULT 1",
        "idempotency_key TEXT NOT NULL DEFAULT ''",
        "snapshot_hash TEXT NOT NULL DEFAULT ''",
        "sanitized_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "guardrail_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "approval_requirements_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "created_by TEXT NOT NULL DEFAULT ''",
        "updated_by TEXT NOT NULL DEFAULT ''",
        "archived_at TIMESTAMPTZ",
        "item_type TEXT NOT NULL",
        "item_ref_id TEXT NOT NULL DEFAULT ''",
        "item_order INTEGER NOT NULL DEFAULT 0",
        "sanitized_item_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "action TEXT NOT NULL",
        "CHECK (action IN ('create', 'update', 'archive', 'request-review', 'reject'))",
        "actor_id TEXT NOT NULL DEFAULT ''",
        "actor_label TEXT NOT NULL DEFAULT ''",
        "actor_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "before_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "after_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "uq_group_ops_workspace_drafts_draft_id",
        "uq_group_ops_workspace_drafts_tenant_idempotency",
        "idx_group_ops_workspace_drafts_status",
        "idx_group_ops_workspace_drafts_source_plan",
        "idx_group_ops_workspace_drafts_created_at",
        "idx_group_ops_workspace_drafts_updated_at",
        "idx_group_ops_workspace_draft_items_draft",
        "idx_group_ops_workspace_draft_items_type",
        "idx_group_ops_workspace_draft_audit_logs_draft",
        "idx_group_ops_workspace_draft_audit_logs_action",
        "REFERENCES group_ops_workspace_drafts(draft_id) ON DELETE CASCADE",
    ]:
        assert expected in source


def test_group_ops_workspace_draft_schema_uses_only_sanitized_payload_columns() -> None:
    source = _migration_source()
    schema_sql = source.split("def upgrade", 1)[1]

    for expected in [
        "sanitized_payload_json",
        "sanitized_item_json",
        "guardrail_summary_json",
        "approval_requirements_json",
        "before_metadata_json",
        "after_metadata_json",
    ]:
        assert expected in source

    forbidden_schema_fragments = [
        "raw_receiver",
        "receiver_plaintext",
        "raw_external_userid",
        "external_userid TEXT",
        "phone_number",
        "mobile TEXT",
        "raw_chat_id",
        "raw_member_id",
        "openid",
        "unionid",
        "token TEXT",
        "secret TEXT",
        "authorization_header",
        "raw_message_body",
        "raw_callback_body",
        "target_list_json",
        "external_effect_job",
        "push_center_job",
    ]
    lowered = schema_sql.lower()
    assert {fragment for fragment in forbidden_schema_fragments if fragment in lowered} == set()


def test_group_ops_workspace_draft_migration_does_not_add_runtime_writers() -> None:
    migration_source = _migration_source()
    request_review_migration_source = _request_review_migration_source()
    for forbidden in [
        "external_effect_job",
        "external_effect_attempt",
        "broadcast_job",
        "push_center_job",
        "requests.post",
        "httpx.",
    ]:
        assert forbidden not in migration_source
        assert forbidden not in request_review_migration_source


def test_group_ops_workspace_request_review_migration_allows_underscore_audit_action() -> None:
    source = _request_review_migration_source()

    assert "group_ops_workspace_draft_audit_logs_action_check" in source
    assert "'request_review'" in source
    assert "'request-review'" in source
    assert "ADD CONSTRAINT group_ops_workspace_draft_audit_logs_action_check" in source
