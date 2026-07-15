from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0116_questionnaire_operations_config.py"


def test_questionnaire_operations_migration_is_linear_nullable_and_reversible() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0116_questionnaire_operations_config"' in source
    assert 'down_revision = "0115_wecom_media_leases"' in source
    lead_column_line = next(line for line in source.splitlines() if "ADD COLUMN IF NOT EXISTS lead_channel_id" in line)
    assert "ADD COLUMN IF NOT EXISTS lead_channel_id BIGINT" in lead_column_line
    assert "NOT NULL" not in lead_column_line
    assert "FOREIGN KEY (lead_channel_id)" in source
    assert "REFERENCES automation_channel(id)" in source
    assert "ON DELETE SET NULL" in source
    assert "idx_questionnaires_lead_channel_id" in source
    assert "WHERE lead_channel_id IS NOT NULL" in source
    assert "DROP CONSTRAINT IF EXISTS fk_questionnaires_lead_channel" in source
    assert "DROP COLUMN IF EXISTS lead_channel_id" in source
    assert "UPDATE questionnaires" not in source
