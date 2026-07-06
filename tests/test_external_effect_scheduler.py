from __future__ import annotations

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    WECOM_CONTACT_TAG_MARK,
    ExternalEffectDispatchResult,
    ExternalEffectService,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry
from aicrm_next.platform_foundation.external_effects.jobs import (
    SCHEDULER_ENABLED_KEY,
    run_scheduled_external_effects,
)
from aicrm_next.platform_foundation.external_effects.repo import build_external_effect_repository


class _SucceedingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, job):
        self.calls += 1
        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary={"effect_type": job.effect_type},
            response_summary={"status_code": 200, "real_external_call_executed": False},
            real_external_call_executed=False,
        )


def _registry(adapter: _SucceedingAdapter) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["outbound_webhook"] = adapter  # type: ignore[attr-defined]
    return registry


def _context(trace_id: str) -> CommandContext:
    return CommandContext(actor_id="pytest", actor_type="system", request_id=trace_id, trace_id=trace_id, source_route="/pytest/external-effect-scheduler")


def _plan(effect_type: str, *, key: str) -> None:
    ExternalEffectService().plan_effect(
        effect_type=effect_type,
        adapter_name="wecom_tag" if effect_type == WECOM_CONTACT_TAG_MARK else "outbound_webhook",
        operation="post",
        target_type="external_user" if effect_type == WECOM_CONTACT_TAG_MARK else ("questionnaire_submission" if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH else "wechat_pay_order"),
        target_id=key,
        business_type="wecom_tag" if effect_type == WECOM_CONTACT_TAG_MARK else ("questionnaire" if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH else "commerce_order"),
        business_id=key,
        payload={"external_userid": key, "tag_ids": ["tag_a"]} if effect_type == WECOM_CONTACT_TAG_MARK else {"webhook_url": "https://hooks.example.test/effect", "body": {"id": key}},
        context=_context(f"trace-{key}"),
        idempotency_key=f"scheduler-{key}",
        status="queued",
        execution_mode="execute",
    )


def test_external_effect_scheduler_dry_run_previews_all_due_jobs() -> None:
    reset_external_effect_fixture_state()
    _plan(WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, key="q-preview")
    _plan(WEBHOOK_ORDER_PAID_PUSH, key="order-preview")

    result = run_scheduled_external_effects(dry_run=True, limit=10)

    assert result["dry_run"] is True
    assert result["counts"]["candidate_count"] == 2
    assert {item["effect_type"] for item in result["items"]} == {WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, WEBHOOK_ORDER_PAID_PUSH}
    assert result["real_external_call_executed"] is False


def test_external_effect_scheduler_execute_requires_global_scheduler_switch(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    monkeypatch.setenv(SCHEDULER_ENABLED_KEY, "0")
    _plan(WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, key="q-disabled")
    adapter = _SucceedingAdapter()

    result = run_scheduled_external_effects(
        dry_run=False,
        limit=10,
        repository=build_external_effect_repository(),
        adapter_registry=_registry(adapter),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "scheduler_disabled"
    assert adapter.calls == 0


def test_external_effect_scheduler_execute_scans_all_due_jobs_one_by_one(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    monkeypatch.setenv(SCHEDULER_ENABLED_KEY, "1")
    _plan(WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, key="q-execute")
    _plan(WEBHOOK_ORDER_PAID_PUSH, key="order-execute")
    adapter = _SucceedingAdapter()

    result = run_scheduled_external_effects(
        dry_run=False,
        limit=10,
        repository=build_external_effect_repository(),
        adapter_registry=_registry(adapter),
    )

    assert result["status"] == "ok"
    assert result["counts"]["processed_count"] == 2
    assert result["counts"]["succeeded_count"] == 2
    assert adapter.calls == 2


def test_external_effect_scheduler_respects_explicit_wecom_kill_switch(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    monkeypatch.delenv("AICRM_WECOM_EXECUTION_MODE", raising=False)
    monkeypatch.setenv(SCHEDULER_ENABLED_KEY, "1")
    _plan(WECOM_CONTACT_TAG_MARK, key="wx-scheduler-disabled")
    adapter = _SucceedingAdapter()
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wecom_tag"] = adapter  # type: ignore[attr-defined]
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "disabled")

    result = run_scheduled_external_effects(
        dry_run=False,
        limit=10,
        repository=build_external_effect_repository(),
        adapter_registry=registry,
    )

    assert result["status"] == "ok"
    assert result["counts"]["processed_count"] == 1
    assert result["counts"]["blocked_count"] == 1
    assert result["real_external_call_executed"] is False
    assert adapter.calls == 0
