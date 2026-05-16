from __future__ import annotations

import pytest

from wecom_ability_service.db.migrations.postgres_migrations import _run_schema_with_forward_fk_retries
from wecom_ability_service.db.migrations.schema_runner import split_schema_statements


class _FakeSchemaDb:
    def __init__(self, failing_statements: dict[str, int]) -> None:
        self._remaining_failures = dict(failing_statements)
        self.executed: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, stmt: str) -> None:
        self.executed.append(stmt)
        remaining = int(self._remaining_failures.get(stmt) or 0)
        if remaining > 0:
            self._remaining_failures[stmt] = remaining - 1
            raise RuntimeError(f"fail {stmt}")

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_schema_retry_eventually_runs_deferred_statement():
    db = _FakeSchemaDb({"create child": 1})

    _run_schema_with_forward_fk_retries(db, "create parent; create child;", max_passes=3)

    assert db.executed == ["create parent", "create child", "create child"]
    assert db.commits == 2
    assert db.rollbacks == 1


def test_schema_splitter_omits_empty_statements():
    assert split_schema_statements(" create parent; ;\n create child ;") == [
        "create parent",
        "create child",
    ]


def test_schema_retry_raises_when_pending_remains_after_max_passes():
    db = _FakeSchemaDb({"create child": 2})

    with pytest.raises(RuntimeError, match="fail create child"):
        _run_schema_with_forward_fk_retries(db, "create parent; create child;", max_passes=1)

    assert db.executed == ["create parent", "create child", "create child"]
