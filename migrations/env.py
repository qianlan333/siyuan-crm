from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


ALEMBIC_VERSION_NUM_LENGTH = 128


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required for Alembic migrations")

    # 项目用 psycopg(3)，但 SQLAlchemy 默认 PG dialect 期望 psycopg2。
    # 把 postgresql:// / postgres:// 显式改成 postgresql+psycopg://，
    # 让 SQLAlchemy 用 psycopg3 driver。
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def run_migrations_offline() -> None:
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    url = _get_database_url()
    connectable = create_engine(url)

    with connectable.connect() as connection:
        _ensure_wide_alembic_version_table(connection)
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


def _ensure_wide_alembic_version_table(connection: Connection) -> None:
    """Keep Alembic's version table wide enough for deployed revision IDs."""

    if connection.dialect.name != "postgresql":
        return

    with connection.begin():
        connection.exec_driver_sql(
            f"""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR({ALEMBIC_VERSION_NUM_LENGTH}) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
            """
        )
        connection.exec_driver_sql(
            f"""
            ALTER TABLE alembic_version
            ALTER COLUMN version_num TYPE VARCHAR({ALEMBIC_VERSION_NUM_LENGTH})
            """
        )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
