from __future__ import annotations

from fastapi.testclient import TestClient

import aicrm_next.customer_tags.admin_write as admin_write
from aicrm_next.customer_tags.admin_write import (
    get_wecom_tag_write_audit_events,
    get_wecom_tag_write_projection_events,
    get_wecom_tag_write_side_effect_plans,
)
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-command-test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next_command(payload: dict, command_name: str) -> None:
    assert payload["ok"] is True
    assert payload["command_name"] == command_name
    assert payload["source_status"] == "next_command"
    assert payload["write_model_status"] == "local_projection_updated"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["local_only"] is True
    assert payload["audit_recorded"] is True
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert payload["side_effect_plan"]["requires_approval"] is True
    assert payload["side_effect_plan"]["real_external_call_executed"] is False


def test_wecom_tag_crud_routes_execute_next_commands(monkeypatch) -> None:
    client = _client(monkeypatch)

    create = client.post(
        "/api/admin/wecom/tags",
        json={"group_id": "group_fixture_lifecycle", "tag_name": "第13组标签"},
        headers={"Idempotency-Key": "tag-create-13"},
    ).json()
    _assert_next_command(create, "wecom.tag.create")
    tag_id = create["tag"]["tag_id"]

    update = client.patch(f"/api/admin/wecom/tags/{tag_id}", json={"tag_name": "第13组标签更新"}).json()
    _assert_next_command(update, "wecom.tag.update")
    assert update["tag"]["tag_name"] == "第13组标签更新"

    delete = client.delete(f"/api/admin/wecom/tags/{tag_id}").json()
    _assert_next_command(delete, "wecom.tag.delete")
    assert delete["deleted"] is True

    write_types = {item["write_type"] for item in get_wecom_tag_write_projection_events()}
    assert {"tag_created", "tag_updated", "tag_deleted"}.issubset(write_types)


def test_wecom_tag_group_crud_and_sync_routes_execute_next_commands(monkeypatch) -> None:
    client = _client(monkeypatch)

    create = client.post(
        "/api/admin/wecom/tag-groups",
        json={"group_name": "第13组标签组", "first_tag_name": "首个标签"},
        headers={"Idempotency-Key": "group-create-13"},
    ).json()
    _assert_next_command(create, "wecom.tag_group.create")
    group_id = create["group"]["group_id"]
    assert create["tags"]

    update = client.put(f"/api/admin/wecom/tag-groups/{group_id}", json={"group_name": "第13组标签组更新"}).json()
    _assert_next_command(update, "wecom.tag_group.update")
    assert update["group"]["group_name"] == "第13组标签组更新"

    delete = client.delete(f"/api/admin/wecom/tag-groups/{group_id}").json()
    _assert_next_command(delete, "wecom.tag_group.delete")
    assert delete["deleted"] is True

    assert len(get_wecom_tag_write_audit_events()) >= 3
    assert len(get_wecom_tag_write_side_effect_plans()) >= 3


def test_wecom_tag_write_validation_errors_are_controlled(monkeypatch) -> None:
    client = _client(monkeypatch)

    bad_create = client.post("/api/admin/wecom/tags", json={"group_id": "", "tag_name": "x"})
    missing = client.patch("/api/admin/wecom/tags/missing_tag", json={"tag_name": "x"})

    assert bad_create.status_code == 400
    assert bad_create.json()["source_status"] == "next_command"
    assert bad_create.json()["error_code"] == "input_error"
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "not_found"


def test_wecom_tag_crud_live_switch_calls_wecom_and_refreshes_catalog(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-live-command-test")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod_user:prod_pass@db.internal:5432/prod_crm")
    monkeypatch.setenv("AICRM_WECOM_TAG_CRUD_LIVE_ENABLED", "1")

    calls: list[tuple[str, dict]] = []

    class FakeGateway:
        def create_tag_live(self, *, group_id: str = "", group_name: str = "", tag_name: str):
            calls.append(("create_tag", {"group_id": group_id, "group_name": group_name, "tag_name": tag_name}))
            return {"errcode": 0, "tag_group": {"group_id": group_id, "tag": [{"id": "tag_live_created", "name": tag_name}]}}

        def list_wecom_tags_live(self):
            calls.append(("list_tags", {}))
            return {
                "errcode": 0,
                "tag_group": [
                    {
                        "group_id": "group_live",
                        "group_name": "真实标签组",
                        "tag": [{"id": "tag_live_created", "name": "真实新增"}],
                    }
                ],
            }

    def fake_refresh(*, operator: str = "", gateway=None, repository=None):
        assert operator == "admin_user"
        assert gateway is not None
        payload = gateway.list_wecom_tags_live()
        return {
            "ok": True,
            "source_status": "next_live_remote_synced",
            "sync_model_status": "test_projection",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": True,
            "sync_executed": True,
            "fetched_groups": len(payload["tag_group"]),
            "fetched_tags": len(payload["tag_group"][0]["tag"]),
            "sync_run_id": 9,
        }

    monkeypatch.setattr(admin_write, "build_wecom_tag_live_gateway", lambda: FakeGateway())
    monkeypatch.setattr(admin_write, "execute_wecom_tag_catalog_sync", fake_refresh)

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/wecom/tags",
        json={"group_id": "group_live", "tag_name": "真实新增", "actor_id": "admin_user"},
        headers={"Idempotency-Key": "tag-live-create"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["source_status"] == "next_command"
    assert payload["write_model_status"] == "live_wecom_executed"
    assert payload["adapter_mode"] == "real_live"
    assert payload["local_only"] is False
    assert payload["real_external_call_executed"] is True
    assert payload["sync_executed"] is True
    assert payload["target_id"] == "tag_live_created"
    assert payload["side_effect_plan"]["adapter_mode"] == "real_live"
    assert payload["side_effect_plan"]["status"] == "executed"
    assert calls == [
        ("create_tag", {"group_id": "group_live", "group_name": "", "tag_name": "真实新增"}),
        ("list_tags", {}),
    ]
