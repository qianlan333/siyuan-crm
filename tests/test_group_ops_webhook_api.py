from __future__ import annotations

from tests.group_ops_test_helpers import error_code, group_ops_api_client


class RecordingQueueGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_group_message(self, **kwargs):
        self.calls.append(kwargs)
        return 900 + len(self.calls)


def _install_recording_gateway(monkeypatch) -> RecordingQueueGateway:
    from aicrm_next.integration_gateway import wecom_group_adapter

    gateway = RecordingQueueGateway()
    monkeypatch.setattr(wecom_group_adapter, "build_group_ops_queue_gateway", lambda: gateway)
    return gateway


def _bind_three_groups(client) -> None:
    for chat_id in ("wrOgAAA002", "wrOgAAA003"):
        response = client.post(
            "/api/admin/automation-conversion/group-ops/plans/2/groups",
            json={"chat_id": chat_id, "operator": "pytest"},
        )
        assert response.status_code == 201


def _webhook_payload(idempotency_key: str = "daily-lesson-2026-05-25") -> dict:
    return {
        "idempotency_key": idempotency_key,
        "send_mode": "queued",
        "scheduled_at": "2026-05-25T20:00:00+08:00",
        "content": {
            "text": "今天的日课已经更新，请大家在 21:00 前完成练习。",
            "attachments": [],
        },
    }


def test_webhook_accepts_and_queues_fixed_group_bundle(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)
    _bind_three_groups(group_ops_api_client)

    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json=_webhook_payload(),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["event"]["status"] == "queued"
    assert body["event"]["idempotency_key"] == "daily-lesson-2026-05-25"
    assert body["broadcast_job_ids"] == [901]
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call["owner_userid"] == "owner_001"
    assert call["chat_ids"] == ["wrOgAAA001", "wrOgAAA002", "wrOgAAA003"]
    assert call["content_payload"]["channel"] == "wecom_customer_group"
    assert call["content_payload"]["sender"] == "owner_001"
    assert call["content_payload"]["text"]["content"].startswith("今天的日课")


def test_webhook_idempotency_does_not_enqueue_twice(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)

    first = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json=_webhook_payload(),
    )
    duplicate = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json=_webhook_payload(),
    )

    assert first.status_code == 202
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["broadcast_job_ids"] == [901]
    assert len(gateway.calls) == 1


def test_webhook_auth_failure_writes_no_event_or_queue(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)

    missing = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        json=_webhook_payload("missing-token"),
    )
    wrong = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer wrong"},
        json=_webhook_payload("wrong-token"),
    )
    replay_probe = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json=_webhook_payload("missing-token"),
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert error_code(missing) == "invalid_webhook_token"
    assert error_code(wrong) == "invalid_webhook_token"
    assert replay_probe.status_code == 202
    assert replay_probe.json()["status"] == "queued"
    assert len(gateway.calls) == 1


def test_webhook_empty_content_is_rejected_before_queue(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "empty-content",
            "send_mode": "queued",
            "content": {"text": "", "attachments": []},
        },
    )

    assert response.status_code == 400
    assert error_code(response) == "content_required"
    assert gateway.calls == []


def test_webhook_inactive_plan_returns_409_without_queue(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)
    disabled = group_ops_api_client.put(
        "/api/admin/automation-conversion/group-ops/plans/2",
        json={"status": "disabled", "operator": "pytest"},
    )
    assert disabled.status_code == 200

    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json=_webhook_payload("inactive-plan"),
    )

    assert response.status_code == 409
    assert error_code(response) == "plan_not_active"
    assert gateway.calls == []
