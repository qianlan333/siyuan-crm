from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.customer_acquisition_service import (
    build_customer_acquisition_final_url,
    generate_customer_channel,
    handle_customer_acquisition_event,
)
from wecom_ability_service.domains.callbacks.service import log_external_contact_event
from wecom_ability_service.routes import _process_external_contact_event


def _create_binding(client, **overrides):
    payload = {
        "link_id": overrides.pop("link_id", "link-ca-001"),
        "link_name": overrides.pop("link_name", "五月获客链接"),
        "link_url": overrides.pop("link_url", "https://work.weixin.qq.com/ca/test-link"),
        "program_id": overrides.pop("program_id", 1),
        "workflow_id": overrides.pop("workflow_id", 2),
        "initial_audience_code": overrides.pop("initial_audience_code", "operating"),
    }
    payload.update(overrides)
    response = client.post("/api/admin/wecom-customer-acquisition-links", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["ok"] is True
    return data


def _process_customer_acquisition_callback(app, *, event_key: str, payload: dict):
    with app.app_context():
        logged = log_external_contact_event(
            corp_id="ww-test",
            event_type="customer_acquisition",
            change_type=str(payload.get("ChangeType") or payload.get("change_type") or "customer_add"),
            external_userid=str(payload.get("ExternalUserID") or payload.get("external_userid") or ""),
            user_id=str(payload.get("UserID") or payload.get("userid") or payload.get("user_id") or ""),
            event_time=1775001000,
            event_key=event_key,
            payload_xml="<xml></xml>",
            payload_json=payload,
        )
        return _process_external_contact_event(int(logged["id"]))


def _member_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS total FROM automation_member").fetchone()["total"]


def test_customer_channel_generation_stays_within_wecom_state_limit():
    channel = generate_customer_channel(
        corp_id="ww-test",
        program_id=123456789,
        link_id="very-long-link-id-" * 20,
    )
    assert len(channel.encode("utf-8")) <= 64
    assert channel.replace("_", "").replace("-", "").isalnum()


def test_customer_acquisition_final_url_appends_replaces_and_preserves_fragment():
    no_query = build_customer_acquisition_final_url("https://work.weixin.qq.com/ca/a", "wca_abc")
    with_query = build_customer_acquisition_final_url("https://work.weixin.qq.com/ca/a?foo=1", "wca_abc")
    with_fragment = build_customer_acquisition_final_url("https://work.weixin.qq.com/ca/a?foo=1#frag", "wca_abc")
    existing = build_customer_acquisition_final_url(
        "https://work.weixin.qq.com/ca/a?customer_channel=old&foo=1#frag",
        "wca_abc",
    )

    assert parse_qs(urlsplit(no_query).query)["customer_channel"] == ["wca_abc"]
    assert parse_qs(urlsplit(with_query).query) == {"foo": ["1"], "customer_channel": ["wca_abc"]}
    assert urlsplit(with_fragment).fragment == "frag"
    assert parse_qs(urlsplit(existing).query) == {"foo": ["1"], "customer_channel": ["wca_abc"]}


def test_customer_acquisition_handler_enables_channel_welcome_message(monkeypatch):
    from wecom_ability_service.domains.automation_conversion import customer_acquisition_service

    captured: dict[str, object] = {}

    class _DummyDb:
        def commit(self) -> None:
            captured["committed"] = True

    monkeypatch.setattr(customer_acquisition_service, "get_db", lambda: _DummyDb())
    monkeypatch.setattr(
        customer_acquisition_service.repo,
        "find_customer_acquisition_link_by_channel",
        lambda *, corp_id, customer_channel: {
            "id": 11,
            "automation_channel_id": 22,
            "status": "active",
            "channel_status": "active",
            "initial_audience_code": "operating",
        },
    )
    monkeypatch.setattr(
        customer_acquisition_service.repo,
        "find_customer_acquisition_link_by_link_id",
        lambda *, corp_id, link_id: None,
    )
    monkeypatch.setattr(customer_acquisition_service.repo, "touch_customer_acquisition_link_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        customer_acquisition_service.repo,
        "get_channel_by_id",
        lambda channel_id: {"id": channel_id, "scene_value": "wca_welcome", "welcome_message": "新版欢迎语"},
    )

    def _capture_channel_enter(**kwargs):
        captured.update(kwargs)
        return {"handled": True, "welcome_message": {"sent": True}}

    monkeypatch.setattr(customer_acquisition_service, "handle_channel_enter_from_callback", _capture_channel_enter)

    result = handle_customer_acquisition_event(
        corp_id="ww-test",
        event_data={
            "Event": "customer_acquisition",
            "State": "wca_welcome",
            "UserID": "sales_01",
            "ExternalUserID": "wm_ca_welcome_001",
            "WelcomeCode": "welcome-ca-001",
        },
    )

    assert result["handled"] is True
    assert captured["send_welcome_message"] is True
    assert captured["payload_json"]["WelcomeCode"] == "welcome-ca-001"


def test_create_customer_acquisition_binding_writes_link_and_channel(app, client):
    app.config["WECOM_CORP_ID"] = "ww-test"
    data = _create_binding(client, link_id="link-create-001")
    link = data["link"]

    with app.app_context():
        row = get_db().execute(
            """
            SELECT l.link_id, l.customer_channel, l.final_url, l.workflow_id, c.scene_value, c.status, c.channel_code
            FROM wecom_customer_acquisition_links l
            INNER JOIN automation_channel c ON c.id = l.automation_channel_id
            WHERE l.id = ?
            """,
            (int(link["id"]),),
        ).fetchone()
        assert row["link_id"] == "link-create-001"
        assert row["customer_channel"] == row["scene_value"]
        assert "customer_channel=" in row["final_url"]
        assert int(row["workflow_id"]) == 2
        assert row["status"] == "active"
        assert row["channel_code"].startswith("wecom_customer_acquisition_")


def test_customer_acquisition_callback_enters_pool_by_state(app, client):
    app.config["WECOM_CORP_ID"] = "ww-test"
    binding = _create_binding(client, link_id="link-state-001")
    channel = binding["link"]["customer_channel"]

    result = _process_customer_acquisition_callback(
        app,
        event_key="customer-acquisition-state-001",
        payload={
            "Event": "customer_acquisition",
            "ChangeType": "customer_add",
            "LinkId": "link-state-001",
            "State": channel,
            "UserID": "sales_01",
            "ExternalUserID": "wm_ca_state_001",
        },
    )

    assert result["ok"] is True
    with app.app_context():
        member = get_db().execute(
            """
            SELECT external_contact_id, owner_staff_id, in_pool, source_type, source_channel_id, current_audience_code
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_ca_state_001",),
        ).fetchone()
        assert member["external_contact_id"] == "wm_ca_state_001"
        assert member["owner_staff_id"] == "sales_01"
        assert bool(member["in_pool"]) is True
        assert member["source_type"] == "wecom_customer_acquisition"
        assert int(member["source_channel_id"]) == int(binding["link"]["automation_channel_id"])
        assert member["current_audience_code"] == "operating"


def test_customer_acquisition_callback_sends_channel_welcome_message(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import member_state_service

    app.config["WECOM_CORP_ID"] = "ww-test"
    binding = _create_binding(client, link_id="link-welcome-001")
    channel = binding["link"]["customer_channel"]
    captured: dict[str, object] = {}

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            captured["payload"] = payload
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(member_state_service.service_seams, "get_contact_runtime_client", lambda: _StubClient())
    with app.app_context():
        get_db().execute(
            "UPDATE automation_channel SET welcome_message = ? WHERE id = ?",
            ("新版欢迎语", int(binding["link"]["automation_channel_id"])),
        )
        get_db().commit()

    result = _process_customer_acquisition_callback(
        app,
        event_key="customer-acquisition-welcome-001",
        payload={
            "Event": "customer_acquisition",
            "ChangeType": "customer_add",
            "LinkId": "link-welcome-001",
            "State": channel,
            "UserID": "sales_01",
            "ExternalUserID": "wm_ca_welcome_001",
            "WelcomeCode": "welcome-ca-001",
        },
    )

    assert result["ok"] is True
    assert result["customer_acquisition"]["welcome_message"]["sent"] is True
    assert captured["payload"] == {
        "welcome_code": "welcome-ca-001",
        "text": {"content": "新版欢迎语"},
    }


def test_customer_acquisition_callback_enters_pool_by_link_id_fallback(app, client):
    app.config["WECOM_CORP_ID"] = "ww-test"
    _create_binding(client, link_id="link-fallback-001")

    result = _process_customer_acquisition_callback(
        app,
        event_key="customer-acquisition-fallback-001",
        payload={
            "event": "customer_acquisition",
            "change_type": "customer_add",
            "link_id": "link-fallback-001",
            "userid": "sales_02",
            "external_userid": "wm_ca_fallback_001",
        },
    )

    assert result["ok"] is True
    assert _member_count(app) == 1


def test_customer_acquisition_callback_missing_external_userid_only_records_event(app, client):
    app.config["WECOM_CORP_ID"] = "ww-test"
    binding = _create_binding(client, link_id="link-missing-external-001")

    result = _process_customer_acquisition_callback(
        app,
        event_key="customer-acquisition-missing-external-001",
        payload={
            "Event": "customer_acquisition",
            "LinkId": "link-missing-external-001",
            "State": binding["link"]["customer_channel"],
            "UserID": "sales_01",
        },
    )

    assert result["ok"] is True
    assert result["customer_acquisition"]["reason"] == "missing_external_userid_or_userid"
    assert _member_count(app) == 0


def test_customer_acquisition_disabled_link_does_not_enter_pool(app, client):
    app.config["WECOM_CORP_ID"] = "ww-test"
    binding = _create_binding(client, link_id="link-disabled-001")
    response = client.post(f"/api/admin/wecom-customer-acquisition-links/{binding['link']['id']}/disable")
    assert response.status_code == 200

    result = _process_customer_acquisition_callback(
        app,
        event_key="customer-acquisition-disabled-001",
        payload={
            "Event": "customer_acquisition",
            "LinkId": "link-disabled-001",
            "State": binding["link"]["customer_channel"],
            "UserID": "sales_01",
            "ExternalUserID": "wm_ca_disabled_001",
        },
    )

    assert result["ok"] is True
    assert result["customer_acquisition"]["reason"] == "link_disabled"
    assert _member_count(app) == 0


def test_customer_acquisition_duplicate_callback_is_idempotent(app, client):
    app.config["WECOM_CORP_ID"] = "ww-test"
    binding = _create_binding(client, link_id="link-idempotent-001")
    payload = {
        "Event": "customer_acquisition",
        "LinkId": "link-idempotent-001",
        "State": binding["link"]["customer_channel"],
        "UserID": "sales_01",
        "ExternalUserID": "wm_ca_idempotent_001",
    }

    first = _process_customer_acquisition_callback(app, event_key="customer-acquisition-idempotent-001", payload=payload)
    second = _process_customer_acquisition_callback(app, event_key="customer-acquisition-idempotent-002", payload=payload)

    assert first["ok"] is True
    assert second["ok"] is True
    with app.app_context():
        member_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM automation_member WHERE external_contact_id = ?",
            ("wm_ca_idempotent_001",),
        ).fetchone()["total"]
        entry_total = get_db().execute(
            """
            SELECT COUNT(*) AS total
            FROM automation_member_audience_entry ae
            INNER JOIN automation_member m ON m.id = ae.member_id
            WHERE m.external_contact_id = ?
            """,
            ("wm_ca_idempotent_001",),
        ).fetchone()["total"]
        assert member_total == 1
        assert entry_total == 1
