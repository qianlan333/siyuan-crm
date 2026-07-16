from __future__ import annotations

from datetime import timedelta

from aicrm_next.customer_read_model.repo import _coerce_datetime
from aicrm_next.customer_read_model.refresh import CustomerReadModelRefreshService


class _Source:
    def __init__(self, customers: list[dict]) -> None:
        self.customers = customers

    def count_customers(self, filters=None) -> int:
        return len(self.customers)

    def list_customers(self, filters=None, *, limit=None, offset=0) -> list[dict]:
        return list(self.customers[offset : offset + limit if limit is not None else None])

    def snapshot_recent_messages_by_unionid(self, unionids, *, per_customer_limit=100):
        assert unionids == ["union_1", "union_2"]
        assert per_customer_limit == 100
        return {
            "union_1": [
                {
                    "msgid": "message_1",
                    "unionid": "union_1",
                    "msgtype": "text",
                    "content": "hello",
                    "send_time": "2026-07-13T00:00:00+00:00",
                    "source_id": "10",
                }
            ]
        }


class _Target:
    def __init__(self, count: int = 1) -> None:
        self.count = count
        self.replace_calls: list[dict] = []

    def count_customers(self, filters=None) -> int:
        return self.count

    def replace_all(self, **kwargs) -> None:
        self.replace_calls.append(kwargs)
        self.count = len(kwargs["customers"])


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute(self, statement, params) -> None:
        self.calls.append({"sql": str(statement), "params": dict(params)})


class _BeginContext:
    def __init__(self, session: _RecordingSession) -> None:
        self.session = session

    def __enter__(self) -> _RecordingSession:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionFactory:
    def __init__(self) -> None:
        self.session = _RecordingSession()

    def begin(self) -> _BeginContext:
        return _BeginContext(self.session)


def _customers() -> list[dict]:
    return [
        {
            "unionid": "union_1",
            "external_userid": "external_1",
            "customer_name": "one",
            "updated_at": "2026-07-13T00:00:00+00:00",
            "created_at": "2026-07-13T00:00:00+00:00",
        },
        {
            "unionid": "union_2",
            "external_userid": "",
            "customer_name": "two",
            "updated_at": "2026-07-13T00:00:00+00:00",
            "created_at": "2026-07-13T00:00:00+00:00",
        },
    ]


def test_customer_read_model_refresh_is_dry_run_by_default() -> None:
    source = _Source(_customers())
    target = _Target(count=1)
    sessions = _SessionFactory()

    result = CustomerReadModelRefreshService(
        source_repo=source,
        target_repo=target,
        session_factory=sessions,
    ).run()

    assert result.ok is True
    assert result.dry_run is True
    assert result.source_count == 2
    assert result.target_count_before == 1
    assert result.target_count_after == 1
    assert target.replace_calls == []
    assert sessions.session.calls == []


def test_customer_read_model_refresh_replaces_projection_and_records_count_only_state() -> None:
    source = _Source(_customers())
    target = _Target(count=1)
    sessions = _SessionFactory()

    result = CustomerReadModelRefreshService(
        source_repo=source,
        target_repo=target,
        session_factory=sessions,
    ).run(dry_run=False)

    assert result.ok is True
    assert result.dry_run is False
    assert result.source_count == result.target_count_after == 2
    assert len(target.replace_calls) == 1
    replacement = target.replace_calls[0]
    assert replacement["messages_by_external_userid"]["external_1"][0]["msgid"] == "message_1"
    assert replacement["messages_by_external_userid"]["union_2"] == []
    assert replacement["timeline_by_external_userid"]["external_1"][0]["event_type"] == "message"
    assert len(sessions.session.calls) == 1
    assert sessions.session.calls[0]["params"]["source_count"] == 2
    assert sessions.session.calls[0]["params"]["target_count"] == 2
    assert "customer_read_model_refresh_state" in sessions.session.calls[0]["sql"]


def test_customer_read_model_refresh_refuses_duplicate_or_empty_unionid() -> None:
    duplicate = _customers()
    duplicate[1]["unionid"] = "union_1"
    empty = _customers()
    empty[1]["unionid"] = ""

    for customers, reason in (
        (duplicate, "customer_read_model_source_contains_duplicate_unionid"),
        (empty, "customer_read_model_source_contains_empty_unionid"),
    ):
        service = CustomerReadModelRefreshService(
            source_repo=_Source(customers),
            target_repo=_Target(),
            session_factory=_SessionFactory(),
        )
        try:
            service.run(dry_run=False)
        except RuntimeError as exc:
            assert str(exc) == reason
        else:  # pragma: no cover - fail closed contract
            raise AssertionError("refresh must reject invalid identity keys")


def test_customer_read_model_accepts_postgres_whole_hour_timezone_offset() -> None:
    value = _coerce_datetime("2026-07-16 18:02:25.720198+08")

    assert value.utcoffset() == timedelta(hours=8)
    assert value.isoformat() == "2026-07-16T18:02:25.720198+08:00"
