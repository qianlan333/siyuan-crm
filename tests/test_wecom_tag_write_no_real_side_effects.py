from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

import aicrm_next.customer_tags.admin_write as admin_write
import aicrm_next.customer_tags.api as api
import aicrm_next.customer_tags.write_repo as write_repo
from aicrm_next.main import create_app


def test_wecom_tag_write_sources_do_not_call_legacy_or_real_wecom() -> None:
    sources = "\n".join(
        inspect.getsource(obj)
        for obj in [
            api.sync_admin_wecom_tags_command,
            api.create_admin_wecom_tag_group_command,
            api.mutate_admin_wecom_tag_group_command,
            api.create_admin_wecom_tag_command,
            api.mutate_admin_wecom_tag_command,
            admin_write.execute_wecom_tag_write,
            admin_write._create_side_effect_plan,
            write_repo.WeComTagWriteRepository,
            write_repo.PostgresWeComTagWriteRepository,
        ]
    )

    forbidden = [
        "forward_to_legacy_flask",
        "legacy_flask_facade",
        "X-AICRM-Compatibility-Facade",
        "requests.",
        "httpx.",
        "WeComTagLiveGateway",
        "list_wecom_tags_live",
        "mark_tags_live",
        "mark_external_contact_tags",
    ]
    for marker in forbidden:
        assert marker not in sources


def test_wecom_tag_write_requests_record_side_effect_plan_without_real_call(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-no-real-side-effects")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)

    client = TestClient(create_app(), raise_server_exceptions=False)

    payloads = [
        client.post("/api/admin/wecom/tags", json={"group_id": "group_fixture_lifecycle", "tag_name": "无真实副作用"}).json(),
        client.patch("/api/admin/wecom/tags/tag_fixture_active", json={"tag_name": "无真实副作用更新"}).json(),
    ]

    for payload in payloads:
        assert payload["source_status"] == "next_command"
        assert payload["fallback_used"] is False
        assert payload["real_external_call_executed"] is False
        assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
        assert payload["side_effect_plan"]["real_external_call_executed"] is False


def test_wecom_tag_write_blocks_production_fixture_claims(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-production-block")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/wecom/tags",
        json={"group_id": "group_fixture_lifecycle", "tag_name": "生产阻断"},
    )

    assert response.status_code == 503
    assert response.json()["source_status"] == "production_unavailable"
    assert response.json()["fallback_used"] is False
    assert response.json()["real_external_call_executed"] is False


def test_wecom_tag_write_uses_postgres_projection_in_production_data_mode(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-production-postgres")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod_user:prod_pass@db.internal:5432/prod_crm")
    admin_write.reset_wecom_tag_write_fixture_state()

    class FakePostgresWeComTagWriteRepository:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create_tag(self, *, command_id: str, group_id: str, tag_name: str) -> dict:
            self.calls.append({"command_id": command_id, "group_id": group_id, "tag_name": tag_name})
            return {
                "tag_id": "tag_next_prod",
                "tag_group_id": group_id,
                "tag_name": tag_name,
                "group_id": group_id,
                "group_name": "AI-CRM 专用",
                "order": 3,
                "status": "active",
                "source": "production_postgres_tag_catalog",
            }

    fake_repo = FakePostgresWeComTagWriteRepository()
    monkeypatch.setattr(admin_write, "PostgresWeComTagWriteRepository", lambda: fake_repo)

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/wecom/tags",
        json={"group_id": "group_prod", "tag_name": "AI联盟用户"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source_status"] == "next_command"
    assert payload["write_model_status"] == "local_projection_updated"
    assert payload["target_id"] == "tag_next_prod"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert fake_repo.calls[0]["group_id"] == "group_prod"
