from __future__ import annotations

import json

import aicrm_next.background_jobs.broadcast_queue_worker as worker
from aicrm_next.background_jobs.broadcast_queue_worker import SafeSkippedBroadcastDispatcher


class Adapter:
    def create_private_message_task(self, payload: dict, *, idempotency_key: str = "") -> dict:
        return {"ok": True, "wecom_msgid": "msg-ok", "result": {"msgid": "msg-ok"}}


def _job(sender: str, external_userids: list[str]) -> dict:
    content = f"【RuntimeV2真实链路测试】case=guard sender={sender}"
    return {
        "id": 1,
        "source_type": "automation_runtime_v2",
        "source_id": "v2:event:1:task:2:member:3",
        "idempotency_key": "v2:event:1:task:2:member:3",
        "trace_id": "v2:event:1:task:2:member:3",
        "channel": "wecom_private",
        "target_kind": "external_userid",
        "target_external_userids": json.dumps(external_userids),
        "target_count": len(external_userids),
        "content_payload": {
            "channel": "wecom_private",
            "sender_userid": sender,
            "target_external_userids": external_userids,
            "rendered_content": {"content_text": content},
        },
    }


def test_realtest_allows_huangyoucan(monkeypatch) -> None:
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: Adapter())
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 1)

    result = SafeSkippedBroadcastDispatcher().dispatch(_job("HuangYouCan", ["wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"]))

    assert result["ok"] is True


def test_realtest_allows_qianlan(monkeypatch) -> None:
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: Adapter())
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 1)

    result = SafeSkippedBroadcastDispatcher().dispatch(_job("QianLan", ["wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"]))

    assert result["ok"] is True


def test_realtest_blocks_unapproved_sender() -> None:
    result = SafeSkippedBroadcastDispatcher().dispatch(_job("SomeoneElse", ["wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"]))

    assert result["ok"] is False
    assert result["failure_type"] == "validation_failed"
    assert result["error"] == "realtest_sender_not_allowed"


def test_realtest_blocks_non_test_external_userid() -> None:
    result = SafeSkippedBroadcastDispatcher().dispatch(_job("HuangYouCan", ["wm_not_allowed"]))

    assert result["ok"] is False
    assert result["failure_type"] == "validation_failed"
    assert result["error"] == "realtest_target_not_allowed"
