from __future__ import annotations

from .task_sqlalchemy_repository import SqlAlchemyTaskRepository


class PostgresTaskRepository(SqlAlchemyTaskRepository):
    """PostgreSQL-backed automation task repository for Next-native task writes."""

    source_status = "production_postgres_task_repository"

