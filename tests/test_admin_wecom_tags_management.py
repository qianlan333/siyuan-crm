from __future__ import annotations

from copy import deepcopy

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.tags import service as tags_service
from wecom_ability_service.wecom_client import WeComClientError


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, SECRET_KEY="admin-wecom-tags-test") as app:
        yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin_session_user_id"] = 1
        session["admin_session_wecom_userid"] = "admin_user"
        session["admin_session_role_list"] = ["super_admin"]
        session["admin_session_login_type"] = "break_glass"
        session["admin_session_display_name"] = "test-admin"
        session["admin_session_break_glass_username"] = "test-admin"
    return client


class FakeWeComTagClient:
    def __init__(self):
        self.catalog = {
            "errcode": 0,
            "tag_group": [
                {
                    "group_id": "group_a",
                    "group_name": "阶段",
                    "tag": [
                        {"id": "tag_a", "name": "已报名", "order": 1},
                        {"id": "tag_b", "name": "待跟进", "order": 2},
                    ],
                }
            ],
        }
        self.fail_list = False
        self.list_calls = 0
        self.create_calls = 0
        self.update_calls = 0
        self.delete_calls = 0

    def list_tags(self, payload=None):
        self.list_calls += 1
        if self.fail_list:
            raise WeComClientError("remote unavailable", stage="get_corp_tag_list", category="network")
        return deepcopy(self.catalog)

    def create_tag(self, payload):
        self.create_calls += 1
        group_id = str(payload.get("group_id") or "").strip()
        group_name = str(payload.get("group_name") or "").strip()
        raw_tags = list(payload.get("tag") or [])
        if not group_id:
            group_id = f"group_created_{self.create_calls}"
            group_name = group_name or str(payload.get("group_name") or "新增组")
            self.catalog["tag_group"].append({"group_id": group_id, "group_name": group_name, "tag": []})
        target = next(group for group in self.catalog["tag_group"] if group["group_id"] == group_id)
        for raw in raw_tags:
            target["tag"].append(
                {
                    "id": f"tag_created_{self.create_calls}_{len(target['tag']) + 1}",
                    "name": str(raw.get("name") or "").strip(),
                    "order": len(target["tag"]) + 1,
                }
            )
        return {"errcode": 0, "errmsg": "ok", "group_id": group_id}

    def update_tag_group(self, payload):
        self.update_calls += 1
        group_id = str(payload.get("id") or "").strip()
        for group in self.catalog["tag_group"]:
            if group["group_id"] == group_id:
                group["group_name"] = str(payload.get("name") or "").strip()
                for tag in group["tag"]:
                    tag["group_name"] = group["group_name"]
        return {"errcode": 0, "errmsg": "ok"}

    def delete_tag_group(self, payload):
        self.delete_calls += 1
        ids = {str(item or "").strip() for item in payload.get("group_id") or []}
        self.catalog["tag_group"] = [group for group in self.catalog["tag_group"] if group["group_id"] not in ids]
        return {"errcode": 0, "errmsg": "ok"}

    def update_tag(self, payload):
        self.update_calls += 1
        tag_id = str(payload.get("id") or "").strip()
        for group in self.catalog["tag_group"]:
            for tag in group["tag"]:
                if tag["id"] == tag_id:
                    tag["name"] = str(payload.get("name") or "").strip()
        return {"errcode": 0, "errmsg": "ok"}

    def delete_tag(self, payload):
        self.delete_calls += 1
        ids = {str(item or "").strip() for item in payload.get("tag_id") or []}
        for group in self.catalog["tag_group"]:
            group["tag"] = [tag for tag in group["tag"] if tag["id"] not in ids]
        return {"errcode": 0, "errmsg": "ok"}


@pytest.fixture()
def fake_wecom(monkeypatch):
    fake = FakeWeComTagClient()
    monkeypatch.setattr(tags_service.WeComClient, "from_app", staticmethod(lambda: fake))
    return fake


def _insert_contact_tags(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES ('wm_001', 'sales_01', 'tag_a', '已报名')
            """
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES ('wm_002', 'sales_01', 'tag_a', '已报名')
            """
        )
        db.commit()


def test_wecom_tags_api_syncs_remote_catalog_and_counts_usage(app, client, fake_wecom):
    _insert_contact_tags(app)

    response = client.get("/api/admin/wecom/tags")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source_status"] == "remote_synced"
    assert payload["total_tags"] == 2
    assert payload["tag_limit"] == 1000
    assert payload["synced_at"]
    assert payload["items"][0].keys() >= {"tag_id", "tag_name", "group_id", "group_name"}
    tag_a = payload["groups"][0]["tags"][0]
    assert tag_a["tag_id"] == "tag_a"
    assert tag_a["usage_count"] == 2

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS total FROM wecom_corp_tags").fetchone()["total"] == 2


def test_wecom_tags_api_falls_back_to_cached_catalog_on_remote_failure(client, fake_wecom):
    first = client.get("/api/admin/wecom/tags").get_json()
    assert first["ok"] is True

    fake_wecom.fail_list = True
    response = client.get("/api/admin/wecom/tags")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source_status"] == "cache_fallback"
    assert "remote unavailable" in payload["sync_error"]
    assert payload["total_tags"] == 2
    assert payload["groups"][0]["group_id"] == "group_a"


def test_wecom_tag_writes_call_remote_and_refresh_catalog(client, fake_wecom):
    assert client.get("/api/admin/wecom/tags").get_json()["ok"] is True
    initial_list_calls = fake_wecom.list_calls

    create_group = client.post(
        "/api/admin/wecom/tag-groups",
        json={"group_name": "新阶段", "first_tag_name": "新标签"},
    ).get_json()
    assert create_group["ok"] is True
    assert fake_wecom.create_calls == 1
    assert fake_wecom.list_calls == initial_list_calls + 2

    create_tag = client.post("/api/admin/wecom/tags", json={"group_id": "group_a", "tag_name": "复购"}).get_json()
    update_group = client.put("/api/admin/wecom/tag-groups/group_a", json={"group_name": "阶段更新"}).get_json()
    update_tag = client.put("/api/admin/wecom/tags/tag_a", json={"tag_name": "已报名更新"}).get_json()
    delete_tag = client.delete("/api/admin/wecom/tags/tag_b").get_json()
    delete_group = client.delete("/api/admin/wecom/tag-groups/group_created_1").get_json()

    assert create_tag["ok"] is True
    assert update_group["ok"] is True
    assert update_tag["ok"] is True
    assert delete_tag["ok"] is True
    assert delete_group["ok"] is True
    assert fake_wecom.create_calls == 2
    assert fake_wecom.update_calls == 2
    assert fake_wecom.delete_calls == 2
    assert fake_wecom.list_calls >= initial_list_calls + 7


def test_wecom_tag_sync_endpoint_is_idempotent_and_marks_missing_tags_deleted(app, client, fake_wecom):
    first = client.post("/api/admin/wecom/tags/sync").get_json()
    second = client.post("/api/admin/wecom/tags/sync-due").get_json()

    assert first["ok"] is True
    assert second["ok"] is True
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS total FROM wecom_corp_tags").fetchone()["total"] == 2

    fake_wecom.catalog["tag_group"][0]["tag"] = [{"id": "tag_a", "name": "已报名", "order": 1}]
    missing = client.post("/api/admin/wecom/tags/sync").get_json()

    assert missing["ok"] is True
    assert missing["marked_deleted_tags"] == 1
    with app.app_context():
        row = get_db().execute("SELECT deleted_at FROM wecom_corp_tags WHERE tag_id = 'tag_b'").fetchone()
        assert row["deleted_at"] is not None


def test_wecom_tag_sync_failure_records_run_and_page_reads_cache(app, client, fake_wecom):
    assert client.post("/api/admin/wecom/tags/sync").get_json()["ok"] is True
    fake_wecom.fail_list = True

    sync_response = client.post("/api/admin/wecom/tags/sync")
    sync_payload = sync_response.get_json()
    page_payload = client.get("/api/admin/wecom/tags").get_json()

    assert sync_response.status_code == 200
    assert sync_payload["ok"] is False
    assert sync_payload["source_status"] == "cache_fallback"
    assert "remote unavailable" in sync_payload["error_message"]
    assert page_payload["ok"] is True
    assert page_payload["source_status"] == "cache_fallback"
    with app.app_context():
        row = get_db().execute(
            "SELECT status, error_message FROM sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["status"] == "failed"
        assert "remote unavailable" in row["error_message"]
