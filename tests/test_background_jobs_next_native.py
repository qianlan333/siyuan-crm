from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from aicrm_next.background_jobs.automation_member_backfill import run_automation_member_backfill
from aicrm_next.background_jobs.automation_ops_scheduler import run_automation_ops_scheduler
from aicrm_next.background_jobs.broadcast_queue_worker import run_broadcast_queue_worker
from aicrm_next.background_jobs.external_contact_sync import run_external_contact_sync


class FakeAutomationMemberRepo:
    def __init__(self) -> None:
        self.rows = [
            {"external_userid": "wm_1", "mobile": "13800138000", "person_id": 1, "owner_userid": "owner_1"},
            {"external_userid": "wm_2", "mobile": "13800138001", "person_id": 2, "owner_userid": "owner_2"},
        ]
        self.writes: list[tuple[dict[str, Any], bool]] = []

    def list_sidebar_bound_contacts(self, *, limit: int, offset: int = 0, external_userid: str = "") -> list[dict[str, Any]]:
        rows = [row for row in self.rows if not external_userid or row["external_userid"] == external_userid]
        return rows[offset : offset + limit]

    def upsert_campaign_ready_member(self, row: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        self.writes.append((row, dry_run))
        return {"ok": True, "status": "insert" if row["external_userid"] == "wm_1" else "update"}


class FakeBroadcastRepo:
    def __init__(self) -> None:
        self.jobs = [
            {
                "id": 11,
                "source_type": "manual",
                "target_external_userids": ["wm_a", "wm_b"],
                "scheduled_for": datetime.now(timezone.utc) - timedelta(minutes=1),
            }
        ]
        self.sent: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        return self.jobs[:limit]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0) -> None:
        self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count})

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None:
        self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type})


class FakeDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "outbound_task_id": 101, "sent_count": 2}


class FailingDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "status": "skipped", "reason": "adapter_disabled"}


class FakeContactClient:
    def list_follow_users(self) -> list[str]:
        return ["owner_1"]

    def list_contacts(self, owner_userid: str) -> list[str]:
        return ["wm_contact_1"]

    def get_contact(self, external_userid: str) -> dict[str, Any]:
        return {"external_userid": external_userid, "name": "测试客户", "unionid": "union_1"}


class PartiallyFailingContactClient(FakeContactClient):
    def list_follow_users(self) -> list[str]:
        return ["owner_1", "owner_broken"]

    def list_contacts(self, owner_userid: str) -> list[str]:
        if owner_userid == "owner_broken":
            raise RuntimeError("wecom_api_error")
        return super().list_contacts(owner_userid)


class FakeContactRepo:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def existing_external_userids(self, *, corp_id: str) -> set[str]:
        return set()

    def upsert_contact(self, *, corp_id: str, owner_userid: str, detail: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        self.upserts.append({"corp_id": corp_id, "owner_userid": owner_userid, "detail": detail, "dry_run": dry_run})
        return {"ok": True, "status": "upsert", "external_userid": detail["external_userid"]}

    def counts(self) -> dict[str, int]:
        return {"contacts_total": len(self.upserts), "identity_map_total": len(self.upserts)}


def test_automation_member_backfill_dry_run_uses_repo_without_external_calls() -> None:
    repo = FakeAutomationMemberRepo()
    result = run_automation_member_backfill(limit=10, dry_run=True, repo=repo)

    assert result["ok"] is True
    assert result["processed"] == 2
    assert result["created"] == 1
    assert result["updated"] == 1
    assert all(dry_run for _row, dry_run in repo.writes)


def test_automation_member_backfill_failure_is_structured() -> None:
    result = run_automation_member_backfill(limit=0, dry_run=True, repo=FakeAutomationMemberRepo())

    assert result["ok"] is False
    assert result["errors"][0]["code"] == "invalid_limit"


def test_automation_ops_scheduler_dry_run_returns_structured_skips() -> None:
    result = run_automation_ops_scheduler(dry_run=True, group_ops_runner=lambda **kwargs: {"component": "group_ops_scheduler", "status": "skipped", "reason": "dry_run"})

    assert result["ok"] is True
    assert {item["component"] for item in result["components"]} >= {
        "operation_task_scheduler",
        "legacy_hxc_refresh",
        "broadcast_feishu_hourly_report",
        "group_ops_scheduler",
    }


def test_broadcast_queue_worker_fake_dispatch_success() -> None:
    repo = FakeBroadcastRepo()
    result = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=FakeDispatcher())

    assert result["ok"] is True
    assert result["claimed"] == 1
    assert result["sent_ok"] == 1
    assert repo.sent == [{"job_id": 11, "outbound_task_id": 101, "sent_count": 2, "failed_count": 0}]


def test_broadcast_queue_worker_failure_path_is_structured() -> None:
    repo = FakeBroadcastRepo()
    result = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=FailingDispatcher())

    assert result["ok"] is True
    assert result["skipped"] == 1
    assert repo.failed[0]["failure_type"] == "next_native_dispatch_skipped"


def test_external_contact_sync_fake_client_success() -> None:
    repo = FakeContactRepo()
    result = run_external_contact_sync(full=True, dry_run=True, client=FakeContactClient(), repo=repo, corp_id="ww-test")

    assert result["ok"] is True
    assert result["processed"] == 1
    assert result["inserted_or_updated"] == 1
    assert repo.upserts[0]["dry_run"] is True


def test_external_contact_sync_owner_failure_does_not_abort_other_owners() -> None:
    repo = FakeContactRepo()
    result = run_external_contact_sync(full=True, dry_run=True, client=PartiallyFailingContactClient(), repo=repo, corp_id="ww-test")

    assert result["ok"] is True
    assert result["processed"] == 1
    assert result["inserted_or_updated"] == 1
    assert result["owners"][1]["ok"] is False
    assert result["warnings"][0]["code"] == "owner_contact_list_failed"


def test_external_contact_sync_missing_client_is_structured() -> None:
    result = run_external_contact_sync(full=False, dry_run=True)

    assert result["ok"] is True
    assert result["status"] == "skipped"
    assert result["skipped_components"][0]["reason"] == "missing_wecom_config"
