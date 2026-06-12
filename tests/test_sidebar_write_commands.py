from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.sidebar_write import get_sidebar_write_audit_events


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_command", "expected_write_status"),
    [
        (
            "post",
            "/api/sidebar/bind-mobile",
            {"external_userid": "wx_ext_002", "mobile": "13800138123"},
            "sidebar.bind_mobile",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/lead-pool/upsert-class-term",
            {"external_userid": "wx_ext_001", "class_term": "term-2026-06", "status": "active"},
            "sidebar.upsert_lead_pool_class_term",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/signup-tags/mark",
            {"external_userid": "wx_ext_001", "tag_name": "trial-active", "marked": True},
            "sidebar.mark_signup_tag",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/marketing-status/set-followup-segment",
            {"external_userid": "wx_ext_001", "segment": "high_intent"},
            "sidebar.set_followup_segment",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/marketing-status/mark-enrolled",
            {"external_userid": "wx_ext_001"},
            "sidebar.mark_enrolled",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/marketing-status/unmark-enrolled",
            {"external_userid": "wx_ext_001"},
            "sidebar.unmark_enrolled",
            "updated",
        ),
        (
            "put",
            "/api/sidebar/v2/profile",
            {"external_userid": "wx_ext_001", "remark": "followup ready"},
            "sidebar.update_profile",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/v2/materials/send",
            {"external_userid": "wx_ext_001", "material_id": "mat-001"},
            "sidebar.plan_material_send",
            "planned",
        ),
    ],
)
def test_sidebar_write_routes_execute_next_commandbus(
    client: TestClient,
    method: str,
    path: str,
    payload: dict,
    expected_command: str,
    expected_write_status: str,
) -> None:
    response = getattr(client, method)(path, json=payload, headers={"Idempotency-Key": f"test-{path}"})

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    body = response.json()
    assert body["ok"] is True
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["source_status"] == "next_command"
    assert body["command_name"] == expected_command
    assert body["write_model_status"] == expected_write_status
    assert body["audit_recorded"] is True
    assert body["real_external_call_executed"] is False
    assert body["command_id"]

    audit_events = get_sidebar_write_audit_events()
    assert any(event["command_id"] == body["command_id"] for event in audit_events)


def test_sidebar_write_routes_return_controlled_errors(client: TestClient) -> None:
    missing_external = client.post("/api/sidebar/bind-mobile", json={"mobile": "13800138123"})
    assert missing_external.status_code == 400
    assert missing_external.json()["source_status"] == "input_error"
    assert missing_external.json()["fallback_used"] is False

    missing_payload = client.post("/api/sidebar/bind-mobile", json={"external_userid": "wx_ext_001"})
    assert missing_payload.status_code == 400
    assert missing_payload.json()["source_status"] == "input_error"

    unknown_customer = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wx_ext_missing", "mobile": "13800138123"},
    )
    assert unknown_customer.status_code == 404
    assert unknown_customer.json()["source_status"] == "not_found"
    assert unknown_customer.json()["fallback_used"] is False


def test_sidebar_write_production_unavailable_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://sidebar-write:sidebar-write@127.0.0.1:1/aicrm_sidebar")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    client = TestClient(create_app())
    response = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wx_ext_001", "mobile": "13800138123"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["source_status"] == "production_unavailable"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False


def test_sidebar_bind_mobile_executes_postgres_binding_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://sidebar-write:sidebar-write@127.0.0.1:5432/aicrm_sidebar")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")

    class FakeResult:
        def __init__(self, row=None):
            self._row = row

        def fetchone(self):
            return self._row

    class FakeConnection:
        def __init__(self):
            self.people = [
                {"id": 3, "mobile": "13800138123", "third_party_user_id": "tp_old"},
                {"id": 7, "mobile": "17380533527", "third_party_user_id": "tp_existing"},
            ]
            self.bindings = {
                "wm_prod_sidebar_001": {
                    "external_userid": "wm_prod_sidebar_001",
                    "person_id": 3,
                    "first_bound_by_userid": "sales_old",
                    "first_owner_userid": "sales_old",
                    "last_owner_userid": "sales_old",
                    "created_at": "2026-06-01T00:00:00Z",
                    "updated_at": "2026-06-01T00:00:00Z",
                }
            }
            self.contacts = {
                "wm_prod_sidebar_001": {
                    "customer_name": "生产侧边栏客户",
                    "owner_userid": "sales_09",
                    "remark": "侧边栏",
                }
            }
            self.lead_pool = [{"id": 11, "mobile": "", "external_userid": "wm_prod_sidebar_001"}]
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            compact_sql = " ".join(sql.split())
            if "FROM contacts" in compact_sql:
                return FakeResult(self.contacts.get(params[0]))
            if "FROM external_contact_bindings b JOIN people p" in compact_sql:
                binding = self.bindings.get(params[0])
                if not binding:
                    return FakeResult(None)
                person = next(item for item in self.people if item["id"] == binding["person_id"])
                return FakeResult({**binding, "mobile": person["mobile"], "third_party_user_id": person["third_party_user_id"]})
            if "FROM people WHERE mobile" in compact_sql:
                return FakeResult(next((item for item in self.people if item["mobile"] == params[0]), None))
            if compact_sql.startswith("INSERT INTO people"):
                row = {"id": len(self.people) + 1, "mobile": params[0], "third_party_user_id": ""}
                self.people.append(row)
                return FakeResult({"id": row["id"], "third_party_user_id": row["third_party_user_id"]})
            if compact_sql.startswith("UPDATE external_contact_bindings"):
                binding = self.bindings[params[2]]
                binding["person_id"] = params[0]
                binding["last_owner_userid"] = params[1]
                binding["updated_at"] = "2026-06-10T13:25:00Z"
                return FakeResult(None)
            if "FROM user_ops_lead_pool_current WHERE external_userid" in compact_sql:
                return FakeResult(next((item for item in self.lead_pool if item.get("external_userid") == params[0]), None))
            if "FROM user_ops_lead_pool_current WHERE mobile" in compact_sql:
                return FakeResult(next((item for item in self.lead_pool if item.get("mobile") == params[0]), None))
            if compact_sql.startswith("UPDATE user_ops_lead_pool_current"):
                row = next(item for item in self.lead_pool if item["id"] == params[4])
                row.update(
                    {
                        "mobile": params[0],
                        "external_userid": params[1],
                        "customer_name": params[2],
                        "owner_userid": params[3],
                        "is_wecom_added": True,
                        "is_mobile_bound": True,
                    }
                )
                return FakeResult(None)
            raise AssertionError(f"unexpected SQL: {compact_sql}")

        def commit(self):
            self.commits += 1

    connections: list[FakeConnection] = []

    def connect(*_args, **_kwargs):
        connection = FakeConnection()
        connections.append(connection)
        return connection

    psycopg = types.ModuleType("psycopg")
    psycopg.connect = connect
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)

    client = TestClient(create_app())
    response = client.post(
        "/api/sidebar/bind-mobile",
        json={
            "external_userid": "wm_prod_sidebar_001",
            "owner_userid": "sales_09",
            "bind_by_userid": "sales_09",
            "mobile": "17380533527",
            "force_rebind": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_command"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["binding"]["mobile"] == "17380533527"
    assert body["binding"]["owner_userid"] == "sales_09"
    assert body["lead_pool_merge"]["action_type"] == "lead_pool_update"
    assert "production-ready for command execution" not in response.text
    assert connections[0].commits == 1
