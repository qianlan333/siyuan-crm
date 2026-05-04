from __future__ import annotations

from .connection import (  # noqa: F401
    PostgresConnection,
    close_db,
    dict_factory,
    get_db,
    get_db_backend,
)
from .dialect import (  # noqa: F401
    cast_text,
    coalesce_text,
    is_postgres,
    is_sqlite,
    nonempty,
    upsert_clause,
)


def init_db() -> None:
    from .migrations.postgres_migrations import _init_postgres
    from .migrations.sqlite_migrations import _init_sqlite

    db = get_db()
    if get_db_backend() == "postgres":
        _init_postgres(db)
    else:
        _init_sqlite(db)


def migrate_db() -> None:
    init_db()


def init_app(app) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized the database.")
