from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0096_admin_wecom_directory_members.py"


def _migration_text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_admin_wecom_directory_members_migration_upgrades_existing_legacy_table() -> None:
    source = _migration_text()

    assert "CREATE TABLE IF NOT EXISTS admin_wecom_directory_members" in source
    for column in (
        "ADD COLUMN IF NOT EXISTS corp_id",
        "ADD COLUMN IF NOT EXISTS department_name",
        "ADD COLUMN IF NOT EXISTS mobile",
        "ADD COLUMN IF NOT EXISTS avatar_url",
        "ADD COLUMN IF NOT EXISTS first_seen_at",
        "ADD COLUMN IF NOT EXISTS last_synced_at",
        "ADD COLUMN IF NOT EXISTS updated_by",
    ):
        assert column in source

    assert "attname = 'wecom_corpid'" in source
    assert "NULLIF(wecom_corpid" in source
    assert "attname = 'synced_at'" in source
    assert "synced_at" in source


def test_admin_wecom_directory_members_migration_keeps_runtime_indexes() -> None:
    source = _migration_text()

    assert "ux_admin_wecom_directory_members_corp_userid" in source
    assert "ON admin_wecom_directory_members (corp_id, wecom_userid)" in source
    assert "ix_admin_wecom_directory_members_active" in source
    assert "ix_admin_wecom_directory_members_synced" in source
