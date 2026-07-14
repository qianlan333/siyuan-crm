from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/versions/0104_auth_platform.py"


def test_auth_platform_migration_contains_only_private_deployment_security_tables() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "auth_api_clients",
        "auth_webhook_clients",
        "auth_webhook_replay",
        "auth_sessions",
        "auth_security_events",
    ):
        assert f"CREATE TABLE {table}" in source
    for forbidden in (
        "auth_principals",
        "auth_client_keys",
        "auth_authorization_codes",
        "auth_token_families",
        "auth_tokens",
        "auth_replay_nonces",
        "client_secret TEXT",
        "access_token TEXT",
        "refresh_token TEXT",
    ):
        assert forbidden not in source
    assert "secret_hash TEXT NOT NULL" in source
    assert "secret_reference TEXT NOT NULL" in source
    assert "admin_user_id BIGINT NOT NULL REFERENCES admin_users(id)" in source


def test_auth_platform_migration_follows_current_head() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0104_auth_platform"' in source
    assert 'down_revision = "0103_broadcast_delivery_state_machine"' in source
