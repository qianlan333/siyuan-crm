from __future__ import annotations

from tests.group_ops_test_helpers import error_code, group_ops_api_client


class RecordingQueueGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_group_message(self, **kwargs):
        self.calls.append(kwargs)
        return 1200 + len(self.calls)


def _install_recording_gateway(monkeypatch) -> RecordingQueueGateway:
    from aicrm_next.integration_gateway import wecom_group_adapter

    gateway = RecordingQueueGateway()
    monkeypatch.setattr(wecom_group_adapter, "build_group_ops_queue_gateway", lambda: gateway)
    return gateway


def test_standard_run_due_preview_does_not_enqueue_broadcast_jobs(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due/preview",
        json={"operator": "pytest", "max_outbound_tasks": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview"
    assert body["items"][0]["content_payload"]["channel"] == "wecom_customer_group"
    assert body["items"][0]["content_payload"]["sender"] == "owner_001"
    assert body["items"][0]["chat_ids"] == ["wrOgAAA001", "wrOgAAA002"]
    assert gateway.calls == []


def test_standard_run_due_requires_allowlist_before_queue(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        json={"operator": "pytest", "max_outbound_tasks": 10},
    )

    assert response.status_code == 400
    assert error_code(response) == "allowlist_required"
    assert gateway.calls == []


def test_standard_run_due_with_allow_node_ids_enqueues_broadcast_job(group_ops_api_client, monkeypatch):
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        json={"operator": "pytest", "allow_node_ids": [1], "max_outbound_tasks": 1},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["broadcast_job_ids"] == [1201]
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call["source_id"] == "1:node:1"
    assert call["created_by"] == "pytest"
    assert call["chat_ids"] == ["wrOgAAA001", "wrOgAAA002"]
    assert call["content_payload"]["channel"] == "wecom_customer_group"
    assert call["content_payload"]["sender"] == "owner_001"
