from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.customer_read_model.dto import (
    CustomerDetailRequest,
    CustomerTimelineRequest,
    ListCustomersRequest,
    RecentMessagesRequest,
)


class FakeNextCustomerReadRepository:
    def __init__(self) -> None:
        self.list_calls = 0
        self.list_args: list[tuple[dict, int | None, int]] = []
        self.count_args: list[dict] = []

    def list_customers(self, filters=None, *, limit=None, offset=0):
        self.list_calls += 1
        self.list_args.append((dict(filters or {}), limit, offset))
        rows = [
            {
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
        ]
        external_userid = str((filters or {}).get("external_userid") or "").strip()
        if external_userid:
            rows = [row for row in rows if row.get("external_userid") == external_userid]
        mobile = str((filters or {}).get("mobile") or "").strip()
        if mobile:
            rows = [row for row in rows if row.get("mobile") == mobile]
        return rows[offset:] if limit is None else rows[offset : offset + limit]

    def count_customers(self, filters=None):
        self.count_args.append(dict(filters or {}))
        rows = self.list_customers(filters, limit=None, offset=0)
        return len(rows)

    def get_customer(self, external_userid: str):
        return self.list_customers()[0] if external_userid == "wx_ext_001" else None

    get_customer_detail = get_customer

    def list_timeline(self, external_userid: str, filters=None, *, limit=None, offset=0):
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

    def customer_exists(self, external_userid: str) -> bool:
        return external_userid == "wx_ext_001"


class FakeLiveSourceCustomerReadRepository(FakeNextCustomerReadRepository):
    pass


class ClosableNextCustomerReadRepository(FakeNextCustomerReadRepository):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class EmptyClosableNextCustomerReadRepository(ClosableNextCustomerReadRepository):
    def list_customers(self, filters=None, *, limit=None, offset=0):
        self.list_calls += 1
        self.list_args.append((dict(filters or {}), limit, offset))
        return []

    def count_customers(self, filters=None):
        self.count_args.append(dict(filters or {}))
        return 0

    def get_customer(self, external_userid: str):
        return None

    get_customer_detail = get_customer


class MissingClosableCustomerReadRepository(ClosableNextCustomerReadRepository):
    def get_customer(self, external_userid: str):
        return None

    get_customer_detail = get_customer


class ListOnlyCustomerReadRepository(MissingClosableCustomerReadRepository):
    def customer_exists(self, external_userid: str) -> bool:
        return False

    def list_timeline(self, external_userid: str, filters=None, *, limit=None, offset=0):
        raise AssertionError("timeline snapshot should not be read when detail snapshot is missing")

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit=None):
        raise AssertionError("message snapshot should not be read when detail snapshot is missing")

    get_recent_messages = list_recent_messages


class FailingClosableCustomerReadRepository:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def list_customers(self, filters=None, *, limit=None, offset=0):
        raise RuntimeError("relation customer_list_index_next does not exist")


class FailingDetailClosableCustomerReadRepository(ClosableNextCustomerReadRepository):
    def get_customer(self, external_userid: str):
        raise RuntimeError("relation customer_detail_snapshot_next does not exist")

    get_customer_detail = get_customer


class ClosableLiveSourceCustomerReadRepository(FakeLiveSourceCustomerReadRepository):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self) -> None:
        self.rolled_back = False
        self.closed = False

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class SessionBackedRepository:
    def __init__(self) -> None:
        self._session = FakeSession()


def _production_env(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("CUSTOMER_READ_MODEL_NEXT_PRIMARY", raising=False)


def _patch_next_repo(monkeypatch, repo):
    from aicrm_next.customer_read_model import application

    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda *args, **kwargs: repo)


def _patch_live_source_repo(monkeypatch, repo):
    from aicrm_next.customer_read_model import application

    monkeypatch.setattr(application, "build_customer_live_source_repository", lambda *args, **kwargs: repo)


def test_next_primary_list_detail_timeline_and_recent_messages_do_not_call_legacy(monkeypatch):
    from aicrm_next.customer_read_model.application import (
        GetCustomerDetailQuery,
        GetCustomerTimelineQuery,
        ListCustomersQuery,
        ListRecentMessagesQuery,
    )

    _production_env(monkeypatch)
    repo = FakeNextCustomerReadRepository()
    _patch_next_repo(monkeypatch, repo)

    customers = ListCustomersQuery()(ListCustomersRequest(limit=10))
    detail = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid="wx_ext_001"))
    timeline = GetCustomerTimelineQuery()(CustomerTimelineRequest(external_userid="wx_ext_001", limit=10))
    messages = ListRecentMessagesQuery()(RecentMessagesRequest(external_userid="wx_ext_001", limit=10))

    for payload in [customers, detail, timeline, messages]:
        assert payload["ok"] is True
        assert payload["source_status"] == "next_read_model"
        assert payload["read_model_status"] == "primary"
        assert payload["fallback_used"] is False
        assert payload["route_owner"] == "ai_crm_next"
    assert customers["customers"][0]["external_userid"] == "wx_ext_001"
    assert detail["customer"]["binding_status"] == "bound"
    assert timeline["timeline"]["items"][0]["event_id"] == "evt-1"
    assert messages["messages"][0]["msgid"] == "msg-1"


def test_close_repository_rolls_back_and_closes_session_without_repo_close():
    from aicrm_next.customer_read_model.application import _close_repository

    repo = SessionBackedRepository()

    _close_repository(repo)

    assert repo._session.rolled_back is True
    assert repo._session.closed is True


def test_sqlalchemy_repositories_close_session_without_disposing_engine():
    from aicrm_next.customer_read_model.repo import LiveSourceCustomerReadRepository, SqlAlchemyCustomerReadModelRepository

    read_model_session = FakeSession()
    live_source_session = FakeSession()

    SqlAlchemyCustomerReadModelRepository(read_model_session).close()
    LiveSourceCustomerReadRepository(live_source_session).close()

    assert read_model_session.rolled_back is True
    assert read_model_session.closed is True
    assert live_source_session.rolled_back is True
    assert live_source_session.closed is True


def test_customer_list_closes_internal_repository_after_success(monkeypatch):
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    repo = ClosableNextCustomerReadRepository()
    _patch_next_repo(monkeypatch, repo)

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is True
    assert payload["source_status"] == "next_read_model"
    assert repo.closed is True


def test_customer_detail_closes_internal_repository_when_query_raises(monkeypatch):
    from aicrm_next.shared.errors import NotFoundError
    from aicrm_next.customer_read_model.application import GetCustomerDetailQuery

    _production_env(monkeypatch)
    repo = MissingClosableCustomerReadRepository()
    _patch_next_repo(monkeypatch, repo)

    try:
        GetCustomerDetailQuery()(CustomerDetailRequest(external_userid="missing"))
    except NotFoundError:
        pass
    else:
        raise AssertionError("expected NotFoundError")

    assert repo.closed is True


def test_customer_detail_falls_back_to_list_index_when_detail_snapshot_missing(monkeypatch):
    from aicrm_next.customer_read_model.application import GetCustomerDetailQuery

    _production_env(monkeypatch)
    repo = ListOnlyCustomerReadRepository()
    _patch_next_repo(monkeypatch, repo)

    payload = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid="wx_ext_001"))

    assert payload["ok"] is True
    assert payload["customer"]["external_userid"] == "wx_ext_001"
    assert payload["customer"]["customer_name"] == "客户一"
    assert payload["customer"]["mobile"] == "13800138000"
    assert payload["read_model_status"] == "list_index_fallback"
    assert payload["fallback_used"] is True
    assert repo.closed is True


def test_admin_profile_opens_when_customer_only_exists_in_list_index(monkeypatch):
    from aicrm_next.customer_read_model.application import GetAdminCustomerProfileQuery, GetCustomerContextQuery

    _production_env(monkeypatch)
    repo = ListOnlyCustomerReadRepository()

    payload = GetAdminCustomerProfileQuery(GetCustomerContextQuery(repo))(external_userid="wx_ext_001")

    assert payload["ok"] is True
    assert payload["profile"]["external_userid"] == "wx_ext_001"
    assert payload["profile"]["customer_name"] == "客户一"
    assert payload["profile"]["mobile"] == "13800138000"
    assert payload["source_status"] == "next_read_model"
    assert payload["read_model_status"] == "list_index_fallback"
    assert payload["fallback_used"] is True


def test_customer_list_does_not_close_injected_repository(monkeypatch):
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    repo = ClosableNextCustomerReadRepository()

    payload = ListCustomersQuery(repo)(ListCustomersRequest(limit=10))

    assert payload["ok"] is True
    assert repo.closed is False


def test_customer_list_query_passes_limit_offset_and_uses_count(monkeypatch):
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    repo = ClosableNextCustomerReadRepository()

    payload = ListCustomersQuery(repo)(ListCustomersRequest(mobile="13800138000", limit=5, offset=2))

    assert payload["ok"] is True
    assert set(payload) >= {"customers", "items", "total", "limit", "offset", "filters", "status_code"}
    assert payload["limit"] == 5
    assert payload["offset"] == 2
    assert repo.list_args[0][1:] == (5, 2)
    assert repo.list_args[0][0]["mobile"] == "13800138000"
    assert repo.count_args == [repo.list_args[0][0]]
    assert all(limit is not None for _, limit, _ in repo.list_args[:1])


def test_next_repository_unavailable_does_not_fallback_to_legacy(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: (_ for _ in ()).throw(RuntimeError("next repo offline")))
    monkeypatch.setattr(application, "build_customer_live_source_repository", lambda: (_ for _ in ()).throw(RuntimeError("live source offline")))

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is False
    assert payload["source_status"] == "production_unavailable"
    assert payload["read_model_status"] == "unavailable"
    assert payload["fallback_used"] is False
    assert "legacy_production_facade" not in str(payload)


def test_next_repository_unavailable_without_rollback_returns_production_unavailable(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    monkeypatch.setenv("CUSTOMER_READ_MODEL_LIVE_SOURCE_FALLBACK_ENABLED", "0")
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: (_ for _ in ()).throw(RuntimeError("next repo offline")))

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is False
    assert payload["source_status"] == "production_unavailable"
    assert payload["read_model_status"] == "unavailable"
    assert payload["fallback_used"] is False
    assert "local_contract" not in str(payload)


def test_next_repository_unavailable_uses_live_source_fallback(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import (
        GetCustomerDetailQuery,
        GetCustomerTimelineQuery,
        ListCustomersQuery,
        ListRecentMessagesQuery,
    )

    _production_env(monkeypatch)
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: (_ for _ in ()).throw(RuntimeError("relation customer_list_index_next does not exist")))
    _patch_live_source_repo(monkeypatch, FakeLiveSourceCustomerReadRepository())

    customers = ListCustomersQuery()(ListCustomersRequest(limit=10))
    detail = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid="wx_ext_001"))
    timeline = GetCustomerTimelineQuery()(CustomerTimelineRequest(external_userid="wx_ext_001", limit=10))
    messages = ListRecentMessagesQuery()(RecentMessagesRequest(external_userid="wx_ext_001", limit=10))

    for payload in [customers, detail, timeline, messages]:
        assert payload["ok"] is True
        assert payload["source_status"] == "live_source_fallback"
        assert payload["read_model_status"] == "fallback"
        assert payload["fallback_used"] is True
        assert payload["degraded"] is True
        assert payload["route_owner"] == "ai_crm_next"
        assert "relation customer_list_index_next does not exist" in payload["fallback_reason"]
        assert "legacy_production_facade" not in str(payload)
        assert "local_contract" not in str(payload)
    assert customers["customers"][0]["external_userid"] == "wx_ext_001"
    assert detail["customer"]["external_userid"] == "wx_ext_001"
    assert timeline["timeline"]["items"][0]["event_id"] == "evt-1"
    assert messages["messages"][0]["msgid"] == "msg-1"


def test_empty_primary_customer_list_uses_live_source_fallback_when_source_has_rows(monkeypatch):
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    primary_repo = EmptyClosableNextCustomerReadRepository()
    live_source_repo = ClosableLiveSourceCustomerReadRepository()
    _patch_next_repo(monkeypatch, primary_repo)
    _patch_live_source_repo(monkeypatch, live_source_repo)

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is True
    assert payload["source_status"] == "live_source_fallback"
    assert payload["read_model_status"] == "fallback"
    assert payload["fallback_used"] is True
    assert payload["customers"][0]["external_userid"] == "wx_ext_001"
    assert "primary returned 0" in payload["fallback_reason"]
    assert primary_repo.closed is True
    assert live_source_repo.closed is True
    assert "legacy_production_facade" not in str(payload)


def test_empty_primary_customer_list_stays_empty_when_live_source_has_no_match(monkeypatch):
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    primary_repo = EmptyClosableNextCustomerReadRepository()
    live_source_repo = ClosableLiveSourceCustomerReadRepository()
    _patch_next_repo(monkeypatch, primary_repo)
    _patch_live_source_repo(monkeypatch, live_source_repo)

    payload = ListCustomersQuery()(ListCustomersRequest(mobile="19900000000", limit=10))

    assert payload["ok"] is True
    assert payload["source_status"] == "next_read_model"
    assert payload["read_model_status"] == "primary"
    assert payload["fallback_used"] is False
    assert payload["customers"] == []
    assert payload["total"] == 0
    assert primary_repo.closed is True
    assert live_source_repo.closed is True


def test_customer_list_live_source_fallback_uses_limit_offset_and_count(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    live_source_repo = ClosableLiveSourceCustomerReadRepository()
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: (_ for _ in ()).throw(RuntimeError("relation customer_list_index_next does not exist")))
    _patch_live_source_repo(monkeypatch, live_source_repo)

    payload = ListCustomersQuery()(ListCustomersRequest(limit=5, offset=3))

    assert payload["ok"] is True
    assert payload["source_status"] == "live_source_fallback"
    assert live_source_repo.list_args[0][1:] == (5, 3)
    assert live_source_repo.count_args == [live_source_repo.list_args[0][0]]
    assert live_source_repo.closed is True


def test_customer_list_closes_primary_and_live_source_repositories(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    primary_repo = FailingClosableCustomerReadRepository()
    live_source_repo = ClosableLiveSourceCustomerReadRepository()
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: primary_repo)
    monkeypatch.setattr(application, "build_customer_live_source_repository", lambda: live_source_repo)

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is True
    assert payload["source_status"] == "live_source_fallback"
    assert primary_repo.closed is True
    assert live_source_repo.closed is True


def test_customer_detail_primary_query_failure_closes_before_live_source_fallback(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import GetCustomerDetailQuery

    _production_env(monkeypatch)
    primary_repo = FailingDetailClosableCustomerReadRepository()
    live_source_repo = ClosableLiveSourceCustomerReadRepository()
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: primary_repo)
    monkeypatch.setattr(application, "build_customer_live_source_repository", lambda: live_source_repo)

    payload = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid="wx_ext_001"))

    assert payload["ok"] is True
    assert payload["source_status"] == "live_source_fallback"
    assert payload["customer"]["external_userid"] == "wx_ext_001"
    assert primary_repo.closed is True
    assert live_source_repo.closed is True


def test_customer_context_closes_internally_created_repositories(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import GetCustomerContextQuery
    from aicrm_next.customer_read_model.dto import CustomerContextRequest

    _production_env(monkeypatch)
    created_repositories: list[ClosableNextCustomerReadRepository] = []

    def build_repo():
        repo = ClosableNextCustomerReadRepository()
        created_repositories.append(repo)
        return repo

    monkeypatch.setattr(application, "build_customer_read_model_repository", build_repo)

    payload = GetCustomerContextQuery()(CustomerContextRequest(external_userid="wx_ext_001"))

    assert payload["ok"] is True
    assert payload["source_status"] == "next_read_model"
    assert len(created_repositories) == 1
    assert all(repo.closed for repo in created_repositories)


def test_customer_api_and_admin_page_smoke_next_primary(monkeypatch):
    from aicrm_next.main import create_app

    _production_env(monkeypatch)
    _patch_next_repo(monkeypatch, FakeNextCustomerReadRepository())
    client = TestClient(create_app())

    list_response = client.get("/api/customers?limit=10")
    detail_response = client.get("/api/customers/wx_ext_001")
    timeline_response = client.get("/api/customers/wx_ext_001/timeline?limit=10")
    messages_response = client.get("/api/messages/wx_ext_001/recent?limit=10")
    admin_response = client.get("/admin/customers")

    assert list_response.status_code == 200
    assert list_response.json()["source_status"] == "next_read_model"
    assert detail_response.status_code == 200
    assert detail_response.json()["source_status"] == "next_read_model"
    assert timeline_response.status_code == 200
    assert timeline_response.json()["source_status"] == "next_read_model"
    assert messages_response.status_code == 200
    assert messages_response.json()["source_status"] == "next_read_model"
    assert admin_response.status_code == 200
    assert "客户列表" in admin_response.text
