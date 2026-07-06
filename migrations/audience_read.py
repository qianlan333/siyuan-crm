from __future__ import annotations

from alembic import op
from sqlalchemy import text


def ensure_audience_read_schema() -> bool:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE SCHEMA IF NOT EXISTS audience_read;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'audience_read schema unavailable; skipping audience_read views';
        END $$;
        """
    )
    return audience_read_schema_available()


def audience_read_schema_available() -> bool:
    return bool(op.get_bind().execute(text("SELECT to_regnamespace('audience_read') IS NOT NULL")).scalar())
