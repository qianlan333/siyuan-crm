from __future__ import annotations

from .connection import (  # noqa: F401
    PostgresConnection,
    close_db,
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

    db = get_db()
    _init_postgres(db)

    # PG 上 DDL 失败会让事务进入 abort 状态，后续任何查询都会被忽略
    # （"current transaction is aborted, commands ignored"）。在 seed 之前
    # 强制 rollback 一次，确保连接是干净的。这是 seed 能跑的前提。
    import logging

    _logger = logging.getLogger(__name__)
    try:
        if hasattr(db, "rollback"):
            db.rollback()
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("pre-seed rollback skipped: %s", exc)

    # 启动期幂等 seed —— 系统默认分层 + 频次预算（已存在不覆盖）
    try:
        from ..domains.segments.service import seed_default_segments

        seed_default_segments()
    except Exception as exc:  # pragma: no cover - defensive: 不阻塞主流程
        _logger.warning("seed_default_segments skipped: %s", exc)
        # seed 失败也清一下事务，让 ensure_default_budgets 还能跑
        try:
            if hasattr(db, "rollback"):
                db.rollback()
        except Exception:
            pass
    try:
        from ..domains.marketing_automation.frequency_budget_service import (
            ensure_default_budgets,
        )

        ensure_default_budgets()
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("ensure_default_budgets skipped: %s", exc)
        try:
            if hasattr(db, "rollback"):
                db.rollback()
        except Exception:
            pass


def migrate_db() -> None:
    init_db()


def init_app(app) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        print("Initialized the database.")
