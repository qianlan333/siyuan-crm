from __future__ import annotations

from typing import Any, Callable

from aicrm_next.shared.postgres_connection import get_db


class GroupOpsDuplicateChecker:
    def __init__(
        self,
        fetch_job_by_idempotency_key: Callable[[str], dict[str, Any] | None] | None = None,
        db_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._fetch_job_by_idempotency_key = fetch_job_by_idempotency_key
        self._db_factory = db_factory or get_db

    def exists(self, idempotency_key: str) -> bool:
        key = str(idempotency_key or "").strip()
        if not key:
            return False
        if self._fetch_job_by_idempotency_key is not None:
            return bool(self._fetch_job_by_idempotency_key(key))
        row = self._db_factory().execute(
            """
            SELECT id
            FROM broadcast_jobs
            WHERE idempotency_key = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (key,),
        ).fetchone()
        return bool(row)


def build_group_ops_duplicate_checker() -> GroupOpsDuplicateChecker:
    return GroupOpsDuplicateChecker()
