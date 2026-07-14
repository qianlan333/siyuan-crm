from __future__ import annotations

from aicrm_next.external_effect_composition import build_external_effect_continuation_registry
from aicrm_next.external_push import external_effect_continuation
from aicrm_next.platform_foundation.external_effects.models import (
    WEBHOOK_ORDER_PAID_PUSH,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)


class _FakeRepository:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def mark_delivery_succeeded_from_external_effect(self, delivery_id: str, **kwargs):
        self.calls.append({"delivery_id": delivery_id, **kwargs})
        return {"delivery_id": delivery_id, "status": "success", "response_status": kwargs.get("response_status")}


def test_external_push_success_projects_legacy_delivery_without_another_webhook(monkeypatch) -> None:
    repository = _FakeRepository()
    monkeypatch.setattr(external_effect_continuation.repo, "build_external_push_repository", lambda: repository)
    job = ExternalEffectJob(
        id=42,
        effect_type=WEBHOOK_ORDER_PAID_PUSH,
        adapter_name="outbound_webhook",
        target_type="external_push_delivery",
        target_id="deliv_success_42",
    )
    dispatch = ExternalEffectDispatchResult(
        status="succeeded",
        adapter_mode="execute",
        response_summary={"status_code": 204},
        real_external_call_executed=True,
        provider_result_received=True,
    )

    result = build_external_effect_continuation_registry().run(job, dispatch)

    assert result == {
        "applicable": True,
        "continuation": "external_push_delivery",
        "ok": True,
        "projection_type": "external_push_delivery",
        "delivery_status": "success",
        "response_status": 204,
    }
    assert repository.calls == [
        {
            "delivery_id": "deliv_success_42",
            "external_effect_job_id": 42,
            "response_status": 204,
        }
    ]


def test_external_push_continuation_does_not_match_unrelated_webhook(monkeypatch) -> None:
    repository = _FakeRepository()
    monkeypatch.setattr(external_effect_continuation.repo, "build_external_push_repository", lambda: repository)
    job = ExternalEffectJob(
        id=43,
        effect_type=WEBHOOK_ORDER_PAID_PUSH,
        adapter_name="outbound_webhook",
        target_type="wechat_pay_order",
        target_id="43",
    )
    dispatch = ExternalEffectDispatchResult(status="succeeded", response_summary={"status_code": 200})

    result = build_external_effect_continuation_registry().run(job, dispatch)

    assert result == {"applicable": False, "reason": "no_registered_continuation"}
    assert repository.calls == []
