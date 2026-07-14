"""add the private-deployment authentication boundary.

Revision ID: 0104_auth_platform
Revises: 0103_broadcast_delivery_state_machine
"""

from __future__ import annotations

from alembic import op


revision = "0104_auth_platform"
down_revision = "0103_broadcast_delivery_state_machine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE auth_api_clients (
            client_id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            principal_type TEXT NOT NULL CHECK (principal_type IN ('api_client','service')),
            purpose TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            secret_hash TEXT NOT NULL,
            audiences_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            allowed_cidrs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            corp_id TEXT NOT NULL DEFAULT '',
            owner_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            auth_version BIGINT NOT NULL DEFAULT 1 CHECK (auth_version > 0),
            token_ttl_seconds INTEGER NOT NULL DEFAULT 1800 CHECK (token_ttl_seconds BETWEEN 60 AND 3600),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_rotated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (jsonb_typeof(audiences_json) = 'array'),
            CHECK (jsonb_typeof(scopes_json) = 'array'),
            CHECK (jsonb_typeof(capabilities_json) = 'array'),
            CHECK (jsonb_typeof(allowed_cidrs_json) = 'array'),
            CHECK (jsonb_typeof(owner_scope_json) = 'object')
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_auth_api_clients_enabled ON auth_api_clients (enabled, client_id)"
    )
    op.execute(
        """
        CREATE TABLE auth_webhook_clients (
            client_id TEXT PRIMARY KEY,
            principal_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            secret_reference TEXT NOT NULL CHECK (secret_reference LIKE 'secretref:file:%'),
            capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            allowed_cidrs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            corp_id TEXT NOT NULL DEFAULT '',
            owner_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            auth_version BIGINT NOT NULL DEFAULT 1 CHECK (auth_version > 0),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_rotated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (jsonb_typeof(capabilities_json) = 'array'),
            CHECK (jsonb_typeof(allowed_cidrs_json) = 'array'),
            CHECK (jsonb_typeof(owner_scope_json) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE auth_webhook_replay (
            client_id TEXT NOT NULL REFERENCES auth_webhook_clients(client_id) ON DELETE CASCADE,
            event_id_hash TEXT NOT NULL CHECK (length(event_id_hash) = 64),
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (client_id, event_id_hash)
        )
        """
    )
    op.execute("CREATE INDEX idx_auth_webhook_replay_expiry ON auth_webhook_replay (expires_at)")
    op.execute(
        """
        CREATE TABLE auth_sessions (
            session_id TEXT PRIMARY KEY,
            session_secret_hash TEXT NOT NULL UNIQUE CHECK (length(session_secret_hash) = 64),
            csrf_token_hash TEXT NOT NULL CHECK (length(csrf_token_hash) = 64),
            principal_id TEXT NOT NULL,
            admin_user_id BIGINT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
            corp_id TEXT NOT NULL DEFAULT '',
            session_version BIGINT NOT NULL CHECK (session_version > 0),
            scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            owner_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            auth_time TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            revoked_reason TEXT NOT NULL DEFAULT '',
            last_seen_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (expires_at > auth_time),
            CHECK (jsonb_typeof(scopes_json) = 'array'),
            CHECK (jsonb_typeof(capabilities_json) = 'array'),
            CHECK (jsonb_typeof(owner_scope_json) = 'object')
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_auth_sessions_active_expiry ON auth_sessions (expires_at) WHERE revoked_at IS NULL"
    )
    op.execute(
        """
        CREATE TABLE auth_security_events (
            id BIGSERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            client_id TEXT NOT NULL DEFAULT '',
            principal_id TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL CHECK (outcome IN ('allowed','denied','revoked','failed')),
            reason TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_auth_security_events_lookup ON auth_security_events (created_at DESC, event_type)"
    )

    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_token")
    op.execute("ALTER TABLE IF EXISTS external_effect_test_receipt RENAME COLUMN receiver_token TO event_id")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_event ON external_effect_test_receipt (event_id)")

    # Delete every route-local credential column after the centralized registries exist.
    op.execute("ALTER TABLE IF EXISTS automation_agent_runtime_config DROP COLUMN IF EXISTS inbound_webhook_token")
    op.execute("ALTER TABLE IF EXISTS automation_agent_runtime_config DROP COLUMN IF EXISTS inbound_webhook_secret")
    op.execute("ALTER TABLE IF EXISTS ai_audience_package DROP COLUMN IF EXISTS inbound_webhook_secret")
    op.execute("ALTER TABLE IF EXISTS ai_audience_outbound_subscription DROP COLUMN IF EXISTS signing_secret")
    op.execute("ALTER TABLE IF EXISTS automation_group_ops_plans DROP COLUMN IF EXISTS webhook_token_hash")
    op.execute("ALTER TABLE IF EXISTS automation_group_ops_plans DROP COLUMN IF EXISTS signature_secret_hash")
    op.execute("ALTER TABLE IF EXISTS automation_group_ops_plans DROP COLUMN IF EXISTS last_rotated_at")


def downgrade() -> None:
    # Rollback restores only the historical column shapes; secret material is never reconstructed.
    op.execute("ALTER TABLE IF EXISTS automation_agent_runtime_config ADD COLUMN IF NOT EXISTS inbound_webhook_token TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_agent_runtime_config ADD COLUMN IF NOT EXISTS inbound_webhook_secret TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS ai_audience_package ADD COLUMN IF NOT EXISTS inbound_webhook_secret TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS ai_audience_outbound_subscription ADD COLUMN IF NOT EXISTS signing_secret TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_group_ops_plans ADD COLUMN IF NOT EXISTS webhook_token_hash TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_group_ops_plans ADD COLUMN IF NOT EXISTS signature_secret_hash TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_group_ops_plans ADD COLUMN IF NOT EXISTS last_rotated_at TIMESTAMPTZ")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_test_receipt_event")
    op.execute("ALTER TABLE IF EXISTS external_effect_test_receipt RENAME COLUMN event_id TO receiver_token")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_effect_test_receipt_token ON external_effect_test_receipt (receiver_token)")

    op.execute("DROP TABLE IF EXISTS auth_security_events")
    op.execute("DROP TABLE IF EXISTS auth_sessions")
    op.execute("DROP TABLE IF EXISTS auth_webhook_replay")
    op.execute("DROP TABLE IF EXISTS auth_webhook_clients")
    op.execute("DROP TABLE IF EXISTS auth_api_clients")
