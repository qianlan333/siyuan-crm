from __future__ import annotations

from pathlib import Path
from typing import Iterator

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.shared.db_session import get_db


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class RequestScopedCustomerRepo:
    def __init__(self, session: FakeSession, *, name: str = "read") -> None:
        self.session = session
        self.name = name
        self.closed = False
        self.calls: list[str] = []

    def close(self) -> None:
        self.closed = True

    def list_customers(self, filters=None, *, limit=None, offset=0):
        self.calls.append("list_customers")
        rows = [_customer()]
        mobile = str((filters or {}).get("mobile") or "").strip()
        if mobile:
            rows = [row for row in rows if row.get("mobile") == mobile]
        return rows[offset:] if limit is None else rows[offset : offset + limit]

    def get_customer(self, external_userid: str):
        self.calls.append("get_customer")
        return _customer() if external_userid == "wx_ext_001" else None

    get_customer_detail = get_customer

    def customer_exists(self, external_userid: str) -> bool:
        self.calls.append("customer_exists")
        return external_userid == "wx_ext_001"

    def list_timeline(self, external_userid: str, filters=None, *, limit=None, offset=0):
        self.calls.append("list_timeline")
        rows = [
            {
                "event_id": "evt-1",
                "event_type": "message",
                "event_time": "2026-06-01T08:00:00+00:00",
                "title": "客户消息",
                "summary": "客户问候",
                "source_table": "archived_messages",
                "source_id": "msg-1",
                "metadata": {"msgtype": "text"},
            }
        ]
        return rows[offset:] if limit is None else rows[offset : offset + limit]

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit=None):
        self.calls.append("list_recent_messages")
        rows = [
            {
                "msgid": "msg-1",
                "external_userid": external_userid,
                "msgtype": "text",
                "content": "你好",
                "send_time": "2026-06-01T08:00:00+00:00",
                "owner_userid": "owner-a",
                "chat_type": "single",
            }
        ]
        return rows if limit is None else rows[:limit]

    get_recent_messages = list_recent_messages


def _customer() -> dict:
    return {
        "external_userid": "wx_ext_001",
        "person_id": "person_001",
        "customer_name": "客户一",
        "remark": "重点客户",
        "description": "客户描述",
        "owner_userid": "owner-a",
        "owner_display_name": "顾问甲",
        "mobile": "13800138000",
        "binding": {"is_bound": True, "binding_status": "bound", "mobile": "13800138000"},
        "tags": ["重点跟进"],
        "class_user_status": {"current_status": "lead"},
        "last_message_at": "2026-06-01T08:00:00+00:00",
        "last_touch_at": "2026-06-01T08:10:00+00:00",
        "updated_at": "2026-06-01T08:10:00+00:00",
        "created_at": "2026-06-01T08:00:00+00:00",
        "identity": {"person_id": "person_001", "external_userid": "wx_ext_001", "mobile": "13800138000"},
        "follow_users": [{"userid": "owner-a", "display_name": "顾问甲", "is_primary": True}],
        "marketing_summary": {"main_stage": "lead"},
        "marketing_profile": {"stage_key": "lead"},
        "contact": {"external_userid": "wx_ext_001", "name": "客户一"},
        "sidebar_context": {"can_open_sidebar": True},
    }


def _production_env(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("CUSTOMER_READ_MODEL_REPO_BACKEND", raising=False)


def _client_with_request_scope(monkeypatch):
    from aicrm_next.customer_read_model import application

    _production_env(monkeypatch)
    session = FakeSession()
    read_repos: list[RequestScopedCustomerRepo] = []
    live_repos: list[RequestScopedCustomerRepo] = []

    def override_get_db() -> Iterator[FakeSession]:
        try:
            yield session
        finally:
            session.close()

    def build_read_repo(*, session):
        repo = RequestScopedCustomerRepo(session, name="read")
        read_repos.append(repo)
        return repo

    def build_live_repo(*, session):
        repo = RequestScopedCustomerRepo(session, name="live")
        live_repos.append(repo)
        return repo

    monkeypatch.setattr(application, "build_customer_read_model_repository", build_read_repo)
    monkeypatch.setattr(application, "build_customer_live_source_repository", build_live_repo)
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session, read_repos, live_repos


def test_customer_routes_use_request_scoped_session_and_do_not_close_injected_repo(monkeypatch) -> None:
    client, session, read_repos, live_repos = _client_with_request_scope(monkeypatch)

    responses = [
        client.get("/api/customers?limit=10"),
        client.get("/api/customers/wx_ext_001"),
        client.get("/api/customers/wx_ext_001/timeline?limit=10"),
        client.get("/api/messages/wx_ext_001/recent?limit=10"),
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert responses[0].json()["customers"][0]["external_userid"] == "wx_ext_001"
    assert responses[1].json()["customer"]["external_userid"] == "wx_ext_001"
    assert responses[2].json()["timeline"]["items"][0]["event_id"] == "evt-1"
    assert responses[3].json()["messages"][0]["msgid"] == "msg-1"
    assert session.closed is True
    assert len(read_repos) == 4
    assert len(live_repos) == 4
    assert all(repo.session is session for repo in read_repos + live_repos)
    assert all(repo.closed is False for repo in read_repos + live_repos)


def test_sidebar_customer_context_reuses_one_request_scoped_repo(monkeypatch) -> None:
    client, session, read_repos, live_repos = _client_with_request_scope(monkeypatch)

    response = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["context"]["customer"]["external_userid"] == "wx_ext_001"
    assert payload["context"]["recent_messages"][0]["msgid"] == "msg-1"
    assert payload["context"]["timeline"]["items"][0]["event_id"] == "evt-1"
    assert session.closed is True
    assert len(read_repos) == 1
    assert len(live_repos) == 1
    assert read_repos[0].session is session
    assert live_repos[0].session is session
    assert read_repos[0].closed is False
    assert set(read_repos[0].calls) >= {"get_customer", "customer_exists", "list_timeline", "list_recent_messages"}


def test_customer_read_model_api_has_no_naked_high_frequency_query_calls() -> None:
    source = Path("aicrm_next/customer_read_model/api.py").read_text(encoding="utf-8")

    forbidden = [
        "ListCustomersQuery()(",
        "GetCustomerDetailQuery()(",
        "GetCustomerTimelineQuery()(",
        "ListRecentMessagesQuery()(",
        "GetCustomerContextQuery()(",
    ]
    assert [pattern for pattern in forbidden if pattern in source] == []
