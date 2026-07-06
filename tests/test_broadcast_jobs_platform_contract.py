from __future__ import annotations

from aicrm_next.background_jobs import broadcast_queue_worker
from aicrm_next.background_jobs.broadcast_queue_worker import SafeSkippedBroadcastDispatcher


def test_default_broadcast_dispatcher_skips_unknown_source_type() -> None:
    result = SafeSkippedBroadcastDispatcher().dispatch(
        {
            "id": 1,
            "source_type": "unknown",
            "source_table": "mystery_table",
            "content_type": "mystery",
            "channel": "",
            "target_kind": "",
            "content_payload": {"channel": "unknown_channel"},
        }
    )

    assert result == {
        "ok": False,
        "status": "skipped",
        "reason": "next_native_dispatcher_missing",
        "source_type": "unknown",
        "source_table": "mystery_table",
        "content_type": "mystery",
        "channel": "",
        "target_kind": "",
        "payload_channel": "unknown_channel",
    }


def test_group_broadcast_payload_uses_safe_adapter_result_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "disabled")
    monkeypatch.setattr(broadcast_queue_worker, "_record_outbound_task", lambda **kwargs: None)

    result = SafeSkippedBroadcastDispatcher().dispatch(
        {
            "id": 2,
            "source_type": "group_ops",
                "content_payload": {
                    "channel": "wecom_customer_group",
                    "sender": "owner_1",
                    "chat_ids": ["chat_a"],
                    "text": {"content": "hello"},
                },
            }
        )

    assert result["ok"] is False
    assert "disabled" in result["error"]
    assert result.get("outbound_task_id") is None


def test_group_broadcast_global_execution_mode_disabled_blocks_before_adapter(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "disabled")

    def fail_adapter():
        raise AssertionError("adapter should not be built when global WeCom execution is disabled")

    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_group_adapter.build_wecom_group_message_adapter", fail_adapter)

    result = SafeSkippedBroadcastDispatcher().dispatch(
        {
            "id": 3,
            "source_type": "group_ops",
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_1",
                "chat_ids": ["chat_a"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is False
    assert result["failure_type"] == "wecom_execution_disabled"
    assert result["side_effect_executed"] is False
