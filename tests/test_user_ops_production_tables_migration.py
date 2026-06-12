from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0029_user_ops_prod_tables.py"

TABLES = {
    "user_ops_pool_current_next": [
        "id",
        "person_id",
        "mobile",
        "external_userid",
        "customer_name",
        "owner_userid",
        "owner_display_name",
        "class_term_no",
        "class_term_label",
        "source_type",
        "activation_bucket",
        "activation_bucket_label",
        "is_mobile_bound",
        "auto_do_not_disturb_reasons_json",
        "created_at",
        "updated_at",
    ],
    "user_ops_do_not_disturb_next": [
        "id",
        "external_userid",
        "mobile",
        "source_type",
        "reason_code",
        "reason_text",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    ],
    "user_ops_send_records_next": [
        "id",
        "record_key",
        "task_type",
        "outbound_task_ids_json",
        "task_results_json",
        "selected_count",
        "eligible_count",
        "sent_count",
        "skipped_count",
        "skipped_reasons_json",
        "include_do_not_disturb",
        "content_preview",
        "image_count",
        "sender_userids_json",
        "filter_snapshot_json",
        "operator",
        "status",
        "status_label",
        "last_status_sync_at",
        "created_at",
    ],
}

INDEXES = [
    "ix_user_ops_pool_current_next_external_userid",
    "ix_user_ops_pool_current_next_mobile",
    "ix_user_ops_pool_current_next_owner_userid",
    "ix_user_ops_pool_current_next_class_term_no",
    "ix_user_ops_pool_current_next_activation_bucket",
    "ix_user_ops_dnd_next_external_userid",
    "ix_user_ops_dnd_next_mobile",
    "ix_user_ops_dnd_next_active_reason",
    "ix_user_ops_send_records_next_record_key",
    "ix_user_ops_send_records_next_created_at",
    "ix_user_ops_send_records_next_status",
]

FIXTURE_MARKERS = [
    "张" + "小蓝",
    "李" + "未绑",
    "wx_ext_" + "001",
    "fixture_record_" + "001",
]


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source, filename=str(MIGRATION))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} assignment not found")


def test_user_ops_production_tables_migration_metadata() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert MIGRATION.exists()
    assert _literal_assignment(source, "revision") == "0029_user_ops_prod_tables"
    assert len(_literal_assignment(source, "revision")) <= 32
    assert _literal_assignment(source, "down_revision") == "0028_owner_excel_sessions"


def test_user_ops_production_tables_migration_contains_schema_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for table, columns in TABLES.items():
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source
        for column in columns:
            assert column in source

    for index_name in INDEXES:
        assert index_name in source

    assert "JSONB NOT NULL DEFAULT '[]'::jsonb" in source
    assert "JSONB NOT NULL DEFAULT '{}'::jsonb" in source
    assert "BIGSERIAL PRIMARY KEY" in source
    assert "record_key VARCHAR(80) NOT NULL UNIQUE" in source


def test_user_ops_production_tables_migration_does_not_seed_fixture_data() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "INSERT INTO" not in source
    for marker in FIXTURE_MARKERS:
        assert marker not in source
