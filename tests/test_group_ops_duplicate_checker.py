from __future__ import annotations

import pytest

from aicrm_next.automation_engine.group_ops.duplicate_checker import GroupOpsDuplicateChecker


def test_duplicate_checker_empty_key_is_false() -> None:
    called = {"fetcher": False}

    def fetcher(key: str) -> dict | None:
        called["fetcher"] = True
        return {"id": 1}

    checker = GroupOpsDuplicateChecker(fetch_job_by_idempotency_key=fetcher)

    assert checker.exists("") is False
    assert called["fetcher"] is False


def test_duplicate_checker_uses_injected_fetcher() -> None:
    keys: list[str] = []

    def fetcher(key: str) -> dict | None:
        keys.append(key)
        return {"id": 123}

    checker = GroupOpsDuplicateChecker(fetch_job_by_idempotency_key=fetcher)

    assert checker.exists("group_ops:k") is True
    assert keys == ["group_ops:k"]


def test_duplicate_checker_missing_row_is_false() -> None:
    checker = GroupOpsDuplicateChecker(fetch_job_by_idempotency_key=lambda key: None)

    assert checker.exists("group_ops:missing") is False


def test_duplicate_checker_uses_next_db_factory() -> None:
    class FakeCursor:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class FakeDb:
        def __init__(self):
            self.calls: list[dict] = []

        def execute(self, sql, params):
            self.calls.append({"sql": sql, "params": params})
            return FakeCursor({"id": 88})

    fake_db = FakeDb()

    assert GroupOpsDuplicateChecker(db_factory=lambda: fake_db).exists("group_ops:k") is True
    assert "FROM broadcast_jobs" in fake_db.calls[0]["sql"]
    assert "idempotency_key" in fake_db.calls[0]["sql"]
    assert fake_db.calls[0]["params"] == ("group_ops:k",)


def test_duplicate_checker_db_exception_bubbles() -> None:
    class FailingDb:
        def execute(self, sql, params):
            raise RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        GroupOpsDuplicateChecker(db_factory=lambda: FailingDb()).exists("group_ops:k")


def test_scheduler_default_duplicate_checker_uses_native_builder(monkeypatch) -> None:
    from aicrm_next.automation_engine.group_ops import scheduler

    calls: list[str] = []

    class FakeChecker:
        def exists(self, key: str) -> bool:
            calls.append(key)
            return True

    monkeypatch.setattr(scheduler, "build_group_ops_duplicate_checker", lambda: FakeChecker())

    assert scheduler._default_duplicate_checker("group_ops:k") is True
    assert calls == ["group_ops:k"]
