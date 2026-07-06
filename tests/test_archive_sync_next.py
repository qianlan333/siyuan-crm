from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.message_archive.sync_service import execute_archive_sync


class FakeArchiveClient:
    def __init__(self) -> None:
        self.closed = False
        self.fetch_calls: list[dict[str, int]] = []

    def health(self) -> dict:
        return {"ok": True, "mode": "fake-sdk"}

    def fetch_page(self, *, seq: int, limit: int) -> dict:
        self.fetch_calls.append({"seq": seq, "limit": limit})
        return {
            "chatdata": [
                {"seq": 30652, "msgid": "encrypted-1"},
                {"seq": 30653, "msgid": "encrypted-2"},
            ]
        }

    def decrypt_record(self, record: dict) -> dict:
        if int(record["seq"]) == 30653:
            return {"msgid": "image-1", "msgtype": "image", "from": "wm_ext_001", "tolist": ["HuangYouCan"], "msgtime": 1780240000}
        return {
            "msgid": "text-1",
            "msgtype": "text",
            "from": "wm_ext_001",
            "tolist": ["HuangYouCan"],
            "text": {"content": "断点后的第一条"},
            "msgtime": 1780240000,
        }

    def close(self) -> None:
        self.closed = True


class FakeArchiveRepo:
    def __init__(self) -> None:
        self.finished: dict | None = None
        self.inserted: list[dict] = []
        self.last_seq = 30651

    def create_sync_run(self, *, start_time: str, end_time: str, owner_userid: str, cursor: str) -> int:
        assert owner_userid == "HuangYouCan"
        assert cursor == ""
        return 42

    def finish_sync_run(self, run_id: int, *, status: str, fetched_count: int, inserted_count: int, raw_response=None, error_message: str = "") -> None:
        self.finished = {
            "run_id": run_id,
            "status": status,
            "fetched_count": fetched_count,
            "inserted_count": inserted_count,
            "raw_response": raw_response,
            "error_message": error_message,
        }

    def get_archive_last_seq(self) -> int:
        return self.last_seq

    def insert_messages_and_advance_seq(self, messages: list[dict], *, last_seq: int) -> int:
        self.last_seq = last_seq
        self.inserted.extend(messages)
        return len(messages)


def test_execute_archive_sync_fetches_from_last_seq_and_only_persists_archive(monkeypatch) -> None:
    monkeypatch.setenv("WECOM_DEFAULT_OWNER_USERID", "HuangYouCan")
    repo = FakeArchiveRepo()
    client = FakeArchiveClient()

    result = execute_archive_sync(repo=repo, client=client, owner_userid="HuangYouCan", limit=100)

    assert result["ok"] is True
    assert result["fetched_count"] == 2
    assert result["accepted_count"] == 1
    assert result["inserted_count"] == 1
    assert result["last_seq"] == 30653
    assert result["reply_monitor_skipped"] is True
    assert result["contacts_sync_skipped"] is True
    assert repo.inserted[0]["msgid"] == "text-1"
    assert repo.last_seq == 30653
    assert repo.finished and repo.finished["status"] == "success"
    assert client.fetch_calls == [{"seq": 30651, "limit": 100}]
    assert client.closed is True


def test_archive_sync_route_requires_internal_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "archive-token")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from aicrm_next.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)

    missing = client.post("/api/archive/sync", json={"owner_userid": "HuangYouCan"})
    assert missing.status_code == 401
    assert missing.json()["error_code"] == "missing_internal_token"


def test_archive_sync_route_passes_archive_request_without_reply_queue(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "archive-token")
    monkeypatch.setenv("AICRM_ENABLE_IN_PROCESS_ARCHIVE_SYNC", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    captured: dict = {}

    def fake_execute(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "fetched_count": 1,
            "inserted_count": 1,
            "last_seq": 30652,
            "reply_monitor_skipped": True,
            "route_owner": "ai_crm_next",
            "source_status": "next_archive_sync",
        }

    monkeypatch.setattr("aicrm_next.message_archive.api.execute_archive_sync", fake_execute)
    from aicrm_next.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/archive/sync",
        json={"owner_userid": "HuangYouCan", "cursor": "30651", "limit": 50, "max_pages": 2},
        headers={"Authorization": "Bearer archive-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_status"] == "next_archive_sync"
    assert payload["reply_monitor_skipped"] is True
    assert captured["owner_userid"] == "HuangYouCan"
    assert captured["cursor"] == "30651"
    assert captured["limit"] == 50
    assert captured["max_pages"] == 2


def test_archive_sync_route_defaults_to_runner_only(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "archive-token")
    monkeypatch.delenv("AICRM_ENABLE_IN_PROCESS_ARCHIVE_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from aicrm_next.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/archive/sync",
        json={"owner_userid": "HuangYouCan", "cursor": "30651"},
        headers={"Authorization": "Bearer archive-token"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["error_code"] == "in_process_archive_sync_disabled"
    assert payload["runner"] == "scripts/run_incremental_archive_sync.py"
    assert payload["reply_monitor_skipped"] is True
