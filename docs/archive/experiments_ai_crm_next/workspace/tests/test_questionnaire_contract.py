from __future__ import annotations

from conftest import make_client


def test_admin_questionnaires_frontend_routes_return_current_admin_shell() -> None:
    client = make_client()
    for path in ("/admin/questionnaires", "/admin/questionnaires/ui"):
        response = client.get(path)
        html = response.text
        assert response.status_code == 200
        assert "问卷管理" in html
        assert "admin-shell" in html
        assert "admin-nav" in html
        assert "群运营计划" in html
        for bad in ("New UI", "redesign", "TODO replace old frontend", "experimental replacement UI"):
            assert bad not in html


def test_admin_questionnaire_list_and_detail_contract() -> None:
    client = make_client()
    payload = client.get("/api/admin/questionnaires").json()
    assert payload["ok"] is True
    assert {"items", "questionnaires", "total", "limit", "offset"} <= set(payload)
    item = payload["items"][0]
    assert {"id", "slug", "title", "description", "enabled", "redirect_url", "created_at", "updated_at", "question_count"} <= set(item)

    detail = client.get(f"/api/admin/questionnaires/{item['id']}").json()
    assert detail["ok"] is True
    assert {"questionnaire", "questions", "external_push_config"} <= set(detail)
    assert {"id", "slug", "title", "description", "enabled", "redirect_url", "submit_button_text", "created_at", "updated_at"} <= set(detail["questionnaire"])
    assert {"id", "type", "title", "required", "options"} <= set(detail["questions"][0])
    assert {"id", "label", "value", "tag_codes"} <= set(detail["questions"][0]["options"][0])


def test_admin_questionnaire_create_update_disable_enable_delete_export_debug() -> None:
    client = make_client()
    create_payload = {
        "slug": "fixture-created",
        "title": "Fixture Created",
        "description": "fixture",
        "enabled": True,
        "redirect_url": "/done",
        "submit_button_text": "提交",
        "questions": [
            {
                "id": "q_created",
                "type": "single_choice",
                "title": "Created?",
                "required": True,
                "options": [{"id": "yes", "label": "Yes", "value": "yes", "tag_codes": ["tag_created"]}],
            }
        ],
    }
    created = client.post("/api/admin/questionnaires", json=create_payload)
    assert created.status_code == 200
    questionnaire_id = created.json()["questionnaire"]["id"]

    updated = client.put(f"/api/admin/questionnaires/{questionnaire_id}", json={**create_payload, "title": "Updated"})
    assert updated.status_code == 200
    assert updated.json()["questionnaire"]["title"] == "Updated"

    disabled = client.post(f"/api/admin/questionnaires/{questionnaire_id}/disable", json={"is_disabled": True}).json()
    assert disabled["questionnaire"]["enabled"] is False
    enabled = client.post(f"/api/admin/questionnaires/{questionnaire_id}/enable").json()
    assert enabled["questionnaire"]["enabled"] is True
    export = client.get(f"/api/admin/questionnaires/{questionnaire_id}/export")
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]
    assert "submission_id" in export.text
    assert "Created?" in export.text
    debug = client.get(f"/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug").json()
    assert debug["ok"] is True
    enabled_delete = client.delete(f"/api/admin/questionnaires/{questionnaire_id}").json()
    assert enabled_delete["ok"] is False
    assert "disabled before deletion" in enabled_delete["error"]
    client.post(f"/api/admin/questionnaires/{questionnaire_id}/disable", json={"is_disabled": True})
    deleted = client.delete(f"/api/admin/questionnaires/{questionnaire_id}").json()
    assert deleted["ok"] is True


def test_admin_questionnaire_preflight_contract() -> None:
    payload = make_client().get("/api/admin/questionnaires/preflight").json()
    assert payload["ok"] is True
    assert {
        "wechat_oauth_configured",
        "wecom_contact_configured",
        "debug_session_api_enabled",
        "questionnaire_admin_ui_enabled",
        "wecom_tags_api_available",
        "identity_map_available",
    } <= set(payload["checks"])


def test_public_questionnaire_get_submit_result_and_errors() -> None:
    client = make_client()
    assert client.get("/s/hxc-activation-v1").status_code == 200
    public_payload = client.get("/api/h5/questionnaires/hxc-activation-v1").json()
    assert public_payload["ok"] is True
    assert {"questionnaire", "questions"} <= set(public_payload)

    assert client.get("/api/h5/questionnaires/missing").status_code == 404
    assert client.get("/api/h5/questionnaires/disabled-demo").status_code == 404
    assert client.post("/api/h5/questionnaires/hxc-activation-v1/submit", json={"answers": {}, "respondent_identity": {}}).status_code == 400

    submitted = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"q_activation": "activated"}, "respondent_identity": {"mobile": "13800138000"}},
    )
    assert submitted.status_code == 200
    payload = submitted.json()
    assert payload["ok"] is True
    assert payload["person_id"] == "fixture_person_8000"
    assert payload["external_userid"] == "wx_ext_001"
    assert payload["score"] == 10
    assert "tag_hxc_activated" in payload["final_tags"]
    assert payload["real_external_call_executed"] is False
    assert payload["external_push"]["real_external_call_executed"] is False

    result = client.get(f"/api/h5/questionnaires/hxc-activation-v1/result/{payload['submission_id']}").json()
    assert result["ok"] is True
    assert result["result"]["submission_id"] == payload["submission_id"]


def test_public_submit_with_openid_unionid_uses_identity_boundary() -> None:
    response = make_client().post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"q_activation": "activated"}, "respondent_identity": {"openid": "openid_002", "unionid": "unionid_002"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["person_id"] == "person_002"
    assert payload["external_userid"] == "wx_ext_002"


def test_wechat_oauth_fake_contract() -> None:
    client = make_client()
    start = client.get(
        "/api/h5/wechat/oauth/start?slug=hxc-activation-v1&openid=openid_fake&unionid=unionid_fake&external_userid=external_fake"
    ).json()
    assert start["ok"] is True
    assert start["source_status"] == "next_oauth_adapter"
    assert start["adapter_mode"] == "fake"
    assert start["real_external_call_executed"] is False
    assert "redirect_url" in start

    callback = client.get(start["callback_url"]).json()
    assert callback["ok"] is True
    assert callback["redirect_url"] == "/s/hxc-activation-v1"
    assert callback["slug"] == "hxc-activation-v1"
    assert callback["source_status"] == "next_oauth_adapter"
    assert callback["adapter_mode"] == "fake"
    assert callback["real_external_call_executed"] is False
    missing_state = client.get("/api/h5/wechat/oauth/callback").json()
    assert missing_state["source_status"] == "state_error"
    assert missing_state["error"] == "state_missing"
