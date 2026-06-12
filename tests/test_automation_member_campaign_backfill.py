from __future__ import annotations

from typing import Any

from aicrm_next.background_jobs.automation_member_backfill import run_automation_member_backfill


class FakeBackfillRepo:
    def __init__(self) -> None:
        self.rows = [
            {"external_userid": "wm_backfill_1", "mobile": "13800138000", "person_id": 1, "owner_userid": "owner_1"},
            {"external_userid": "wm_backfill_2", "mobile": "13800138001", "person_id": 2, "owner_userid": "owner_2"},
        ]
        self.writes: list[tuple[dict[str, Any], bool]] = []

    def list_sidebar_bound_contacts(self, *, limit: int, offset: int = 0, external_userid: str = "") -> list[dict[str, Any]]:
        rows = [row for row in self.rows if not external_userid or row["external_userid"] == external_userid]
        return rows[offset : offset + limit]

    def upsert_campaign_ready_member(self, row: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        self.writes.append((row, dry_run))
        return {"ok": True, "status": "insert" if row["external_userid"] == "wm_backfill_1" else "update"}


def test_member_campaign_backfill_uses_next_repository_contract() -> None:
    repo = FakeBackfillRepo()

    result = run_automation_member_backfill(limit=10, dry_run=True, repo=repo)

    assert result["ok"] is True
    assert result["processed"] == 2
    assert result["created"] == 1
    assert result["updated"] == 1
    assert all(dry_run for _row, dry_run in repo.writes)


def test_member_campaign_backfill_filters_external_userid() -> None:
    result = run_automation_member_backfill(limit=10, external_userid="wm_backfill_2", dry_run=True, repo=FakeBackfillRepo())

    assert result["ok"] is True
    assert result["processed"] == 1
    assert result["updated"] == 1
