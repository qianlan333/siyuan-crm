from __future__ import annotations

from collections.abc import Callable


def split_schema_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def run_schema_with_forward_fk_retries(
    script: str,
    *,
    execute: Callable[[str], object],
    commit: Callable[[], object],
    rollback: Callable[[], object],
    max_passes: int = 4,
) -> None:
    """Run SQL DDL while tolerating forward FK references.

    ``schema_postgres.sql`` still has a few ``CREATE TABLE`` statements whose
    foreign keys point to tables defined later in the file. A single sequential
    run can fail on a fresh database; this runner keeps retrying only the
    deferred statements until the referenced tables have been created.
    """
    pending = split_schema_statements(script)
    for _ in range(max_passes):
        if not pending:
            return
        next_pending: list[str] = []
        for statement in pending:
            try:
                execute(statement)
                commit()
            except Exception:
                rollback()
                next_pending.append(statement)
        if len(next_pending) == len(pending):
            _raise_first_pending_statement(next_pending, execute=execute, commit=commit)
            return
        pending = next_pending
    _raise_first_pending_statement(pending, execute=execute, commit=commit)


def _raise_first_pending_statement(
    pending: list[str],
    *,
    execute: Callable[[str], object],
    commit: Callable[[], object],
) -> None:
    for statement in pending:
        execute(statement)
        commit()
