from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import sessionmaker

from aicrm_next.customer_read_model.application import ListCustomersQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest
from aicrm_next.customer_read_model.models import customer_list_index_next
from aicrm_next.customer_read_model.repo import SqlAlchemyCustomerReadModelRepository


def _row(row_id: int, *, unionid: str = "", external_userid: str = "", owner_userid: str = "owner-a", mobile: str = "") -> dict:
    now = datetime(2026, 6, row_id, tzinfo=timezone.utc)
    return {
        "id": row_id,
        "unionid": unionid or f"union_customer_{row_id:03d}",
        "customer_name": f"客户{row_id}",
        "owner_userid": owner_userid,
        "owner_display_name": "顾问甲",
        "remark": "重点客户" if row_id == 2 else "",
        "description": "",
        "mobile": mobile,
        "is_bound": bool(mobile),
        "binding_status": "bound" if mobile else "unbound",
        "tags_json": ["重点跟进"] if row_id == 2 else [],
        "class_user_status_json": {"current_status": "lead"},
        "last_message_at": now,
        "last_touch_at": now,
        "updated_at": now,
        "created_at": now,
    }


def test_sqlalchemy_customer_list_uses_sql_limit_offset_and_count() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    customer_list_index_next.create(engine)
    session = sessionmaker(bind=engine, future=True)()
    session.execute(
        insert(customer_list_index_next),
        [
            _row(1, unionid="union_customer_001", owner_userid="owner-a", mobile="13800138001"),
            _row(2, unionid="union_customer_002", owner_userid="owner-a", mobile="13800138002"),
            _row(3, unionid="union_customer_003", owner_userid="owner-a", mobile="13800138003"),
            _row(4, unionid="union_customer_004", owner_userid="owner-b", mobile="13900139004"),
        ],
    )
    session.commit()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def record_statement(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    repo = SqlAlchemyCustomerReadModelRepository(session)

    rows = repo.list_customers({"owner_userid": "owner-a"}, limit=1, offset=1)
    total = repo.count_customers({"owner_userid": "owner-a"})

    assert [row["unionid"] for row in rows] == ["union_customer_002"]
    assert total == 3
    list_sql = next(statement for statement in statements if "FROM customer_list_index_next" in statement and "LIMIT" in statement.upper())
    assert "LIMIT" in list_sql.upper()
    assert "OFFSET" in list_sql.upper()


def test_list_customers_query_response_schema_uses_repo_page_and_total(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    class RecordingRepo:
        def __init__(self) -> None:
            self.list_calls: list[tuple[dict, int | None, int]] = []
            self.count_calls: list[dict] = []

        def list_customers(self, filters=None, *, limit=None, offset=0):
            self.list_calls.append((dict(filters or {}), limit, offset))
            return [_row(2, external_userid="wx_ext_002", owner_userid="owner-a", mobile="13800138002")]

        def count_customers(self, filters=None) -> int:
            self.count_calls.append(dict(filters or {}))
            return 12

    repo = RecordingRepo()

    payload = ListCustomersQuery(repo)(ListCustomersRequest(owner_userid="owner-a", limit=1, offset=1))

    assert set(payload) >= {"customers", "items", "count", "total", "limit", "offset", "filters", "status_code"}
    assert payload["customers"] == payload["items"]
    assert payload["count"] == 1
    assert payload["total"] == 12
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert repo.list_calls == [(payload["filters"], 1, 1)]
    assert repo.count_calls == [payload["filters"]]
