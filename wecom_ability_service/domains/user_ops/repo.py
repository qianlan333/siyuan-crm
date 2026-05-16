from __future__ import annotations

from ...db import get_db


def db():
    return get_db()


def get_deferred_job_counts() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END), 0) AS running_count,
            COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) AS success_count,
            COALESCE(SUM(CASE WHEN status = 'conflict' THEN 1 ELSE 0 END), 0) AS conflict_count,
            COALESCE(SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped_count,
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
        FROM user_ops_deferred_jobs
        """
    ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0),
        "pending_count": int(row["pending_count"] or 0),
        "running_count": int(row["running_count"] or 0),
        "success_count": int(row["success_count"] or 0),
        "conflict_count": int(row["conflict_count"] or 0),
        "skipped_count": int(row["skipped_count"] or 0),
        "failed_count": int(row["failed_count"] or 0),
    }
