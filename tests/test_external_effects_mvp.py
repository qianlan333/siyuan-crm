from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi.testclient import TestClient

from aicrm_next.admin_jobs.routes import ensure_admin_action_token
from aicrm_next.customer_tags.live_mutation import execute_wecom_tag_mutation, reset_wecom_tag_live_mutation_fixture_state
from aicrm_next.customer_tags.mutation_commands import PlanWeComTagMarkCommand, PlanWeComTagUnmarkCommand
from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    ExternalEffectDispatchResult,
    ExternalEffectService,
    PAYMENT_WECHAT_REFUND_REQUEST,
    WEBHOOK_GENERIC_PUSH,
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    WECOM_WELCOME_MESSAGE_SEND,
    WECOM_PROFILE_UPDATE,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.repo import InMemoryExternalEffectRepository, _public_job, build_external_effect_repository
from aicrm_next.platform_foundation.external_effects.retry_policy import classify_error_code, retry_delay_seconds
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.platform_foundation.external_effects.adapters import DEFAULT_ADAPTER_REGISTRY, ExternalEffectAdapterRegistry, WeChatPaymentAdapter, WeComContactTagAdapter, WeComProfileUpdateAdapter, WebhookAdapter
from aicrm_next.commerce import external_push_admin
from aicrm_next.integration_gateway.wechat_pay_client import WeChatPayClientError
from aicrm_next.public_product import h5_wechat_pay
from aicrm_next.public_product.h5_wechat_pay import _apply_transaction
from aicrm_next.questionnaire import external_push
from aicrm_next.questionnaire.repo import build_questionnaire_repository


class _ExternalPushResponse:
    status_code = 200
    text = "ok"


class _AdapterResponse:
    def __init__(self, status_code: int, text: str = "adapter-response"):
        self.status_code = status_code
        self.text = text


class _SucceededAgentWebhookAdapter:
    def dispatch(self, job):
        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary={"effect_type": job.effect_type},
            response_summary={
                "status_code": 200,
                "automation_agent_batch_id": "agent_batch_unit_001",
                "real_external_call_executed": True,
            },
            real_external_call_executed=True,
        )


class _QuestionnaireRepoOverride:
    def __init__(self, repo, questionnaire: dict):
        self._repo = repo
        self._questionnaire = deepcopy(questionnaire)

    def get_questionnaire_by_slug(self, slug: str):
        if str(slug or "").strip() == str(self._questionnaire.get("slug") or ""):
            return deepcopy(self._questionnaire)
        return self._repo.get_questionnaire_by_slug(slug)

    def __getattr__(self, name: str):
        return getattr(self._repo, name)


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _ApplyTransactionConn:
    def __init__(self):
        self.queries: list[str] = []
        self.delivery: dict | None = None

    def execute(self, query, params):
        self.queries.append(query)
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT * FROM wechat_pay_orders"):
            return _FakeCursor({"status": "paying", "trade_state": "NOTPAY"})
        if "UPDATE wechat_pay_orders" in query:
            return _FakeCursor(
                {
                    "id": 7,
                    "out_trade_no": params[-1],
                    "status": "paid",
                    "trade_state": "SUCCESS",
                    "product_code": "subscription_trial_month",
                    "paid_at": "2026-06-13T10:00:00+08:00",
                }
            )
        if "FROM wechat_pay_products" in query:
            return _FakeCursor({"id": 3, "product_code": "subscription_trial_month", "name": "黄小璨首月体验", "amount_total": 990})
        if "FROM external_push_config" in query:
            return _FakeCursor(
                {
                    "id": 5,
                    "tenant_id": "aicrm",
                    "target_type": "product",
                    "target_id": "3",
                    "event_type": "transaction.paid",
                    "enabled": True,
                    "webhook_url": "https://example.com/order-paid",
                    "secret": "order-secret",
                    "push_type": "paid_notify",
                    "day": 7,
                    "frequency": 1,
                    "remark": "测试外推",
                    "custom_params": {},
                }
            )
        if "INSERT INTO external_push_delivery" in query:
            self.delivery = {
                "id": 8,
                "tenant_id": params[0],
                "config_id": params[1],
                "event_type": params[2],
                "delivery_id": params[3],
                "target_type": "product",
                "target_id": params[4],
                "order_id": params[5],
                "product_id": params[6],
                "status": "pending",
                "attempt_count": 0,
                "request_url": params[7],
            }
            return _FakeCursor(dict(self.delivery))
        if "UPDATE external_push_delivery" in query:
            assert self.delivery is not None
            self.delivery.update(
                {
                    "status": params[0],
                    "attempt_count": params[1],
                    "request_url": params[2],
                    "request_headers": params[3],
                    "request_body": params[4],
                    "response_status": params[5],
                    "response_body": params[6],
                    "error_message": params[7],
                    "next_retry_at": params[8],
                    "delivery_id": params[9],
                }
            )
            return _FakeCursor(dict(self.delivery))
        raise AssertionError(query)


def _service(repo: InMemoryExternalEffectRepository) -> ExternalEffectService:
    return ExternalEffectService(repo)


def _sample_context(trace_id: str = "trace-external-effect") -> CommandContext:
    return CommandContext(
        actor_id="tester",
        actor_type="system",
        request_id="req-external-effect",
        trace_id=trace_id,
        source_route="/tests/external-effects",
    )


def _registry_with_post(fake_post) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["outbound_webhook"] = WebhookAdapter(http_post=fake_post)  # type: ignore[attr-defined]
    registry._adapters["webhook"] = WebhookAdapter(http_post=fake_post)  # type: ignore[attr-defined]
    return registry


def _install_loopback_http_adapter(monkeypatch, client: TestClient) -> list[dict]:
    calls: list[dict] = []

    def loopback_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        parsed = urlparse(url)
        return client.post(parsed.path, json=json, headers=headers)

    monkeypatch.setitem(DEFAULT_ADAPTER_REGISTRY._adapters, "outbound_webhook", WebhookAdapter(http_post=loopback_post))  # type: ignore[attr-defined]
    monkeypatch.setitem(DEFAULT_ADAPTER_REGISTRY._adapters, "webhook", WebhookAdapter(http_post=loopback_post))  # type: ignore[attr-defined]
    return calls


def _seed_hxc_questionnaire(monkeypatch, external_push_config: dict) -> tuple[dict, str]:
    from aicrm_next.questionnaire import h5_write

    repo = build_questionnaire_repository()
    existing = repo.get_questionnaire_by_slug("hxc-activation-v1")
    standard_config = {
        "enabled": bool(external_push_config.get("enabled")),
        "webhook_url": str(external_push_config.get("webhook_url") or ""),
        "custom_params": list(external_push_config.get("custom_params") or []),
    }
    questionnaire = repo.save_questionnaire(
        {
            "slug": "hxc-activation-v1",
            "name": "黄小璨激活问卷",
            "title": "黄小璨激活问卷",
            "enabled": True,
            "external_push_config": standard_config,
            "questions": [{"id": "q_mobile", "type": "mobile", "title": "手机号", "required": True, "options": []}],
        },
        questionnaire_id=int(existing["id"]) if existing else None,
    )
    patched = deepcopy(questionnaire)
    patched["external_push_config"] = {**dict(patched.get("external_push_config") or {}), **external_push_config}
    patched["external_push_enabled"] = bool(external_push_config.get("enabled"))
    monkeypatch.setattr(h5_write, "build_questionnaire_repository", lambda: _QuestionnaireRepoOverride(repo, patched))
    return patched, str((patched.get("questions") or [{}])[0].get("id") or "q_mobile")


def _queued_webhook_job(
    service: ExternalEffectService,
    *,
    effect_type: str = WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    idempotency_key: str = "queued-webhook-execute",
    payload: dict | None = None,
    max_attempts: int = 5,
) -> dict:
    return service.plan_effect(
        effect_type=effect_type,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission" if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH else "wechat_pay_order",
        target_id=idempotency_key,
        business_type="questionnaire" if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH else "commerce_order",
        business_id=idempotency_key,
        payload=payload or {"webhook_url": "https://hooks.example.test/effect", "body": {"id": idempotency_key}},
        context=_sample_context(f"trace-{idempotency_key}"),
        idempotency_key=idempotency_key,
        status="queued",
        execution_mode="execute",
        max_attempts=max_attempts,
    )


def _submit_questionnaire_queue_loopback_job(
    client: TestClient,
    monkeypatch,
    *,
    idempotency_key: str,
    phone: str,
    receiver_token: str,
    response_status: int,
) -> dict:
    _questionnaire, phone_question_id = _seed_hxc_questionnaire(
        monkeypatch,
        {
            "enabled": True,
            "webhook_url": f"https://crm.example.test/api/external-effects/test-receiver/{receiver_token}",
            "receiver_token": receiver_token,
            "receiver_response_status": response_status,
        },
    )

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {phone_question_id: phone}},
        headers={"Idempotency-Key": idempotency_key},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["external_push_mode"] == "queue"
    assert body["external_push"]["attempted"] is False
    assert body["real_external_call_executed"] is False
    assert body["external_effect_job"]["status"] == "queued"
    assert body["external_effect_job"]["execution_mode"] == "execute"
    assert body["external_effect_job"]["payload_json"]["execution_scope"] == "test_loopback"
    assert body["external_effect_job"]["payload_json"]["receiver_token"] == receiver_token
    return body["external_effect_job"]


def test_external_effect_service_idempotency_filters_retry_and_cancel() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)

    first = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="sub-1",
        business_type="questionnaire",
        business_id="q-1",
        payload={"token": "secret", "value": 1},
        context=_sample_context(),
        idempotency_key="same-shadow-job",
        status="blocked",
    )
    second = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="sub-1",
        business_type="questionnaire",
        business_id="q-1",
        payload={"value": 2},
        context=_sample_context(),
        idempotency_key="same-shadow-job",
    )

    assert first["id"] == second["id"]
    items, total = service.list_jobs(
        {
            "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            "status": "blocked",
            "target_type": "questionnaire_submission",
            "target_id": "sub-1",
            "business_type": "questionnaire",
            "trace_id": "trace-external-effect",
        }
    )
    assert total == 1
    assert items[0].payload_summary_json["token"] == "[redacted]"

    retried = service.retry(first["id"])
    assert retried is not None
    assert retried.status == "queued"
    cancelled = service.cancel(first["id"])
    assert cancelled is not None
    assert cancelled.status == "cancelled"


def test_external_effect_migration_contract_contains_required_tables_indexes_and_idempotency() -> None:
    source = Path("migrations/versions/0039_external_effect_queue.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS external_effect_job" in source
    assert "CREATE TABLE IF NOT EXISTS external_effect_attempt" in source
    assert "uq_external_effect_job_tenant_idempotency" in source
    assert "ON external_effect_job (tenant_id, idempotency_key)" in source
    for index_name in [
        "idx_external_effect_job_due",
        "idx_external_effect_job_target",
        "idx_external_effect_job_business",
        "idx_external_effect_job_trace",
        "idx_external_effect_job_effect_type",
        "idx_external_effect_attempt_job",
        "idx_external_effect_attempt_trace",
    ]:
        assert index_name in source


def test_business_outbound_entrypoints_do_not_directly_call_external_networks() -> None:
    monitored_files = [
        "aicrm_next/questionnaire/external_push.py",
        "aicrm_next/questionnaire/external_push_logs.py",
        "aicrm_next/admin_jobs/application.py",
        "aicrm_next/admin_jobs/notification_settings.py",
        "aicrm_next/commerce/admin_transactions.py",
        "aicrm_next/commerce/external_push_admin.py",
        "aicrm_next/customer_tags/live_mutation.py",
        "aicrm_next/automation_engine/group_ops/application.py",
        "aicrm_next/channel_entry/application.py",
    ]
    forbidden_fragments = [
        "requests.post(",
        "requests.request(",
        "requests.get(",
        "httpx.",
        "urlopen(",
        "urllib.request",
        ".create_refund(",
        "query_refund_by_out_refund_no(",
        ".send_welcome_msg(",
        ".mark_external_contact_tags(",
    ]

    violations: list[str] = []
    for file_name in monitored_files:
        text = Path(file_name).read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{file_name}: {fragment}")

    assert violations == []


def test_retry_policy_classifies_retryable_terminal_and_blocked_errors() -> None:
    assert classify_error_code("timeout") == "retryable"
    assert classify_error_code("", status_code=503) == "retryable"
    assert classify_error_code("", status_code=403) == "terminal"
    assert classify_error_code("payload_invalid") == "terminal"
    assert classify_error_code("adapter_blocked") == "blocked"
    assert retry_delay_seconds(0) == 60
    assert retry_delay_seconds(3) == 3600


def test_run_due_preview_dry_run_and_disabled_adapter_do_not_execute_real_call() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="sub-queued",
        payload={"webhook_url": "https://hooks.example.invalid/shadow"},
        context=_sample_context("trace-run-due"),
        idempotency_key="queued-shadow-job",
        status="queued",
        execution_mode="execute",
    )
    worker = ExternalEffectWorker(repo)

    preview = worker.preview_due(batch_size=10)
    dry_run = worker.run_due(batch_size=10)
    blocked = worker.run_due(batch_size=10, dry_run=False)

    assert preview["counts"]["candidate_count"] == 1
    assert dry_run["dry_run"] is True
    assert dry_run["real_external_call_executed"] is False
    assert blocked["counts"]["failed_count"] == 1
    assert blocked["real_external_call_executed"] is False
    updated = repo.get_job(job["id"])
    assert updated is not None
    assert updated.status == "failed_terminal"
    assert repo.list_attempts(job["id"])[0].error_code == "execution_disabled"


def test_complete_record_only_archives_historical_shadow_without_external_call() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    historical = service.plan_effect(
        effect_type=WECOM_CONTACT_TAG_MARK,
        adapter_name="wecom_tag",
        operation="mark",
        target_type="external_user",
        target_id="wx_record_only",
        business_type="wecom_tag",
        business_id="tag_record_only",
        payload={"tag_ids": ["tag_a"]},
        context=_sample_context("trace-record-only"),
        idempotency_key="record-only-shadow",
        status="planned",
        execution_mode="shadow",
    )
    failed = service.plan_effect(
        effect_type=WECOM_CONTACT_TAG_MARK,
        adapter_name="wecom_tag",
        operation="mark",
        target_type="external_user",
        target_id="wx_failed",
        business_type="wecom_tag",
        business_id="tag_failed",
        payload={"tag_ids": ["tag_a"]},
        context=_sample_context("trace-record-only-failed"),
        idempotency_key="record-only-failed",
        status="failed_terminal",
        execution_mode="execute",
    )

    dry_run = service.complete_record_only(dry_run=True, limit=10, operator="pytest")
    execute = service.complete_record_only(dry_run=False, limit=10, operator="pytest")
    updated = repo.get_job(historical["id"])
    untouched = repo.get_job(failed["id"])
    attempts = repo.list_attempts(historical["id"])

    assert dry_run["candidate_count"] == 1
    assert dry_run["completed_count"] == 0
    assert execute["completed_count"] == 1
    assert execute["real_external_call_executed"] is False
    assert updated is not None
    assert updated.status == "succeeded"
    assert untouched is not None
    assert untouched.status == "failed_terminal"
    assert attempts[0].status == "succeeded"
    assert attempts[0].adapter_mode == "historical_record_only"
    assert attempts[0].response_summary_json["historical_record_completed"] is True
    assert attempts[0].response_summary_json["real_external_call_executed"] is False


def test_explicit_wecom_execution_disabled_blocks_planning_admin_and_worker(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "disabled")

    blocked_at_plan = service.plan_effect(
        effect_type=WECOM_CONTACT_TAG_MARK,
        adapter_name="wecom_tag",
        operation="mark",
        target_type="external_user",
        target_id="wx_disabled_plan",
        business_type="wecom_tag",
        business_id="tag_disabled_plan",
        payload={"external_userid": "wx_disabled_plan", "tag_ids": ["tag_a"]},
        context=_sample_context("trace-wecom-disabled-plan"),
        idempotency_key="wecom-disabled-plan",
        status="queued",
        execution_mode="execute",
    )

    assert blocked_at_plan["status"] == "blocked"
    assert blocked_at_plan["execution_mode"] == "disabled"
    assert blocked_at_plan["payload_summary_json"]["execution_gate"] == "wecom_execution_disabled"
    assert repo.list_due_jobs(limit=10) == []

    monkeypatch.delenv("AICRM_WECOM_EXECUTION_MODE", raising=False)
    planned = service.plan_effect(
        effect_type=WECOM_CONTACT_TAG_MARK,
        adapter_name="wecom_tag",
        operation="mark",
        target_type="external_user",
        target_id="wx_disabled_approve",
        business_type="wecom_tag",
        business_id="tag_disabled_approve",
        payload={"external_userid": "wx_disabled_approve", "tag_ids": ["tag_a"]},
        context=_sample_context("trace-wecom-disabled-approve"),
        idempotency_key="wecom-disabled-approve",
        requires_approval=True,
    )
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "disabled")

    approved = service.approve(planned["id"])

    assert approved is not None
    assert approved.status == "blocked"
    assert repo.list_attempts(planned["id"])[0].error_code == "wecom_execution_disabled"

    class _ExplodingWeComAdapter:
        calls = 0

        def dispatch(self, job):
            self.calls += 1
            raise AssertionError("adapter should be blocked by AICRM_WECOM_EXECUTION_MODE before dispatch")

    worker_repo = InMemoryExternalEffectRepository()
    worker_service = _service(worker_repo)
    monkeypatch.delenv("AICRM_WECOM_EXECUTION_MODE", raising=False)
    queued = worker_service.plan_effect(
        effect_type=WECOM_CONTACT_TAG_MARK,
        adapter_name="wecom_tag",
        operation="mark",
        target_type="external_user",
        target_id="wx_disabled_worker",
        business_type="wecom_tag",
        business_id="tag_disabled_worker",
        payload={"external_userid": "wx_disabled_worker", "tag_ids": ["tag_a"]},
        context=_sample_context("trace-wecom-disabled-worker"),
        idempotency_key="wecom-disabled-worker",
        status="queued",
        execution_mode="execute",
    )
    adapter = _ExplodingWeComAdapter()
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wecom_tag"] = adapter  # type: ignore[attr-defined]
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "disabled")

    result = ExternalEffectWorker(worker_repo, registry).run_due(batch_size=10, dry_run=False)
    updated = worker_repo.get_job(queued["id"])

    assert result["counts"]["blocked_count"] == 1
    assert result["counts"]["failed_count"] == 0
    assert result["real_external_call_executed"] is False
    assert adapter.calls == 0
    assert updated is not None
    assert updated.status == "blocked"
    assert worker_repo.list_attempts(queued["id"])[0].error_code == "wecom_execution_disabled"


def test_webhook_adapter_default_config_dry_run_and_allowlist_gate_never_send(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    _queued_webhook_job(service, idempotency_key="webhook-gates-default")
    calls: list[dict] = []

    def fake_post(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return _AdapterResponse(204)

    registry = _registry_with_post(fake_post)
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", raising=False)
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", raising=False)

    dry_run = ExternalEffectWorker(repo, registry).run_due(batch_size=10, dry_run=True)
    blocked = ExternalEffectWorker(repo, registry).run_due(batch_size=10, dry_run=False)

    assert dry_run["real_external_call_executed"] is False
    assert blocked["real_external_call_executed"] is False
    assert calls == []
    assert repo.list_attempts(1)[0].error_code == "execution_disabled"

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    _queued_webhook_job(service, idempotency_key="webhook-gates-allowlist")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_ORDER_PAID_PUSH)
    not_allowed = ExternalEffectWorker(repo, registry).run_due(batch_size=10, dry_run=False)

    assert not_allowed["real_external_call_executed"] is False
    assert calls == []
    assert repo.list_attempts(1)[0].error_code == "effect_type_not_allowed"


def test_webhook_adapter_enabled_allowlisted_2xx_succeeds_and_records_attempt(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(
        service,
        idempotency_key="webhook-2xx",
        payload={
            "webhook_url": "https://hooks.example.test/success",
            "body": {"event": "ok"},
            "signature_secret": "test-secret",
        },
    )
    calls: list[dict] = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _AdapterResponse(204, "")

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
    result = ExternalEffectWorker(repo, _registry_with_post(fake_post)).run_due(batch_size=10, dry_run=False)
    attempts = repo.list_attempts(job["id"])
    updated = repo.get_job(job["id"])

    assert result["real_external_call_executed"] is True
    assert updated is not None
    assert updated.status == "succeeded"
    assert len(calls) == 1
    assert calls[0]["url"] == "https://hooks.example.test/success"
    assert calls[0]["json"] == {"event": "ok"}
    assert calls[0]["headers"]["X-AICRM-External-Effect-Signature"]
    assert attempts[0].status == "succeeded"
    assert attempts[0].request_summary_json["signature_configured"] is True
    assert attempts[0].response_summary_json["real_external_call_executed"] is True


def test_external_effect_worker_continues_automation_agent_webhook_batch(monkeypatch) -> None:
    from aicrm_next.automation_agents.worker import AutomationAgentWorker

    seen: dict[str, str] = {}

    def fake_continue(self, batch_id: str, *, operator: str):
        seen["batch_id"] = batch_id
        seen["operator"] = operator
        return {
            "ok": True,
            "batch_id": batch_id,
            "batch": {"status": "succeeded", "succeeded_count": 1, "failed_count": 0},
            "broadcast_enqueue": {"approved_count": 1, "failed_count": 0},
        }

    monkeypatch.setattr(AutomationAgentWorker, "run_batch_and_enqueue_broadcast_jobs", fake_continue)
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = service.plan_effect(
        effect_type=WEBHOOK_GENERIC_PUSH,
        adapter_name="unit_agent_webhook",
        operation="post",
        target_type="automation_agent_audience_webhook",
        target_id="activation_agent",
        payload={"webhook_url": "https://www.youcangogogo.com/api/ai/agents/activation_agent/audience-webhook?token=hidden"},
        context=_sample_context("trace-agent-webhook-continuation"),
        idempotency_key="agent-webhook-continuation-unit",
        status="queued",
        execution_mode="execute",
    )
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["unit_agent_webhook"] = _SucceededAgentWebhookAdapter()  # type: ignore[attr-defined]

    result = ExternalEffectWorker(repo, registry).run_due(batch_size=1, dry_run=False, effect_types=[WEBHOOK_GENERIC_PUSH])
    attempts = repo.list_attempts(job["id"])

    assert seen == {"batch_id": "agent_batch_unit_001", "operator": "external_effect_agent_continuation"}
    assert result["counts"]["succeeded_count"] == 1
    continuation = result["items"][0]["post_success_continuation"]
    assert continuation["ok"] is True
    assert continuation["broadcast_enqueue"]["approved_count"] == 1
    response_summary = attempts[0].response_summary_json
    if isinstance(response_summary, str):
        response_summary = json.loads(response_summary)
    continuation_summary = response_summary["post_success_continuation"]
    assert continuation_summary == "dict" or continuation_summary == continuation


def test_webhook_adapter_retryable_statuses_and_timeout_set_next_retry(monkeypatch) -> None:
    for status_code, error_code in [(500, "http_5xx"), (429, "http_429")]:
        repo = InMemoryExternalEffectRepository()
        service = _service(repo)
        job = _queued_webhook_job(service, idempotency_key=f"webhook-retryable-{status_code}")

        def fake_post(url, *, json, headers, timeout, _status_code=status_code):
            return _AdapterResponse(_status_code, "retry later")

        monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
        monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
        ExternalEffectWorker(repo, _registry_with_post(fake_post)).run_due(batch_size=10, dry_run=False)
        updated = repo.get_job(job["id"])
        attempts = repo.list_attempts(job["id"])

        assert updated is not None
        assert updated.status == "failed_retryable"
        assert updated.next_retry_at
        assert datetime.fromisoformat(updated.next_retry_at.replace("Z", "+00:00"))
        assert attempts[0].error_code == error_code
        assert attempts[0].response_summary_json["status_code"] == status_code

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="webhook-timeout")

    def timeout_post(url, *, json, headers, timeout):
        raise requests.Timeout("slow hook")

    ExternalEffectWorker(repo, _registry_with_post(timeout_post)).run_due(batch_size=10, dry_run=False)
    updated = repo.get_job(job["id"])
    attempts = repo.list_attempts(job["id"])

    assert updated is not None
    assert updated.status == "failed_retryable"
    assert updated.next_retry_at
    assert attempts[0].error_code == "timeout"
    assert attempts[0].response_summary_json["real_external_call_executed"] is True


def test_webhook_adapter_terminal_statuses_and_max_attempts(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
    for status_code in [400, 401, 403, 404]:
        repo = InMemoryExternalEffectRepository()
        service = _service(repo)
        job = _queued_webhook_job(service, idempotency_key=f"webhook-terminal-{status_code}")

        def fake_post(url, *, json, headers, timeout, _status_code=status_code):
            return _AdapterResponse(_status_code, "terminal")

        ExternalEffectWorker(repo, _registry_with_post(fake_post)).run_due(batch_size=10, dry_run=False)
        updated = repo.get_job(job["id"])
        attempts = repo.list_attempts(job["id"])

        assert updated is not None
        assert updated.status == "failed_terminal"
        assert attempts[0].error_code == f"http_{status_code}"

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="webhook-max-attempts", max_attempts=1)

    def retryable_post(url, *, json, headers, timeout):
        return _AdapterResponse(500, "final retry")

    ExternalEffectWorker(repo, _registry_with_post(retryable_post)).run_due(batch_size=10, dry_run=False)
    updated = repo.get_job(job["id"])

    assert updated is not None
    assert updated.status == "failed_terminal"
    assert updated.last_error_code == "http_5xx"


def test_cancelled_job_is_not_scanned_by_run_due_preview() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="webhook-cancelled-not-due")
    cancelled = service.cancel(job["id"])
    preview = ExternalEffectWorker(repo).preview_due(batch_size=10)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert preview["counts"]["candidate_count"] == 0


def test_external_effect_admin_api_lists_previews_retries_and_cancels(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "effect-token")
    service = ExternalEffectService()
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="api-sub-1",
        business_type="questionnaire",
        business_id="api-q-1",
        payload={},
        context=_sample_context("trace-api"),
        idempotency_key="api-external-effect-job",
        status="blocked",
    )

    listed = next_client.get("/api/admin/external-effects/jobs", params={"effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH})
    detail = next_client.get(f"/api/admin/external-effects/jobs/{job['id']}")
    unauthorized = next_client.post("/api/admin/external-effects/run-due/preview", json={"batch_size": 10})
    preview = next_client.post(
        "/api/admin/external-effects/run-due/preview",
        headers={"Authorization": "Bearer effect-token"},
        json={"batch_size": 10},
    )
    dry_run = next_client.post(
        "/api/admin/external-effects/run-due",
        headers={"Authorization": "Bearer effect-token"},
        json={"batch_size": 10},
    )
    retried = next_client.post(
        f"/api/admin/external-effects/jobs/{job['id']}/retry",
        json={"admin_action_token": ensure_admin_action_token()},
    )
    cancelled = next_client.post(
        f"/api/admin/external-effects/jobs/{job['id']}/cancel",
        json={"admin_action_token": ensure_admin_action_token()},
    )
    unauthorized_cancel = next_client.post(f"/api/admin/external-effects/jobs/{job['id']}/cancel", json={})
    diagnostics = next_client.get("/api/admin/external-effects/diagnostics")

    assert listed.status_code == 200
    assert listed.json()["route_owner"] == "ai_crm_next"
    assert listed.json()["total"] >= 1
    assert detail.status_code == 200
    assert detail.json()["job"]["id"] == job["id"]
    assert unauthorized.status_code == 401
    assert preview.status_code == 200
    assert preview.json()["real_external_call_executed"] is False
    assert dry_run.status_code == 200
    assert dry_run.json()["dry_run"] is True
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "queued"
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    assert unauthorized_cancel.status_code == 401
    assert diagnostics.status_code == 200
    assert diagnostics.json()["schema_contract"]["idempotency_constraint"] == "UNIQUE (tenant_id, idempotency_key)"
    assert diagnostics.json()["real_external_call_executed"] is False
    assert diagnostics.json()["webhook_execution"]["enabled"] is False
    assert diagnostics.json()["real_execution_enabled"] is False
    assert diagnostics.json()["execution_mode"] == "disabled"
    assert diagnostics.json()["wecom_execution"]["execution_mode"] == "disabled"


def test_wecom_execution_diagnostics_reports_unified_config(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "execute")
    monkeypatch.setenv("AICRM_WECOM_ENABLED_EFFECT_TYPES", f"{WECOM_CONTACT_TAG_MARK},{WECOM_WELCOME_MESSAGE_SEND}")
    monkeypatch.setenv("WECOM_CORP_ID", "ww_fixture")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret_fixture")
    monkeypatch.setenv("AICRM_WECOM_DEFAULT_SENDER_USERID", "owner_fixture")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS", "legacy_owner")

    response = next_client.get("/api/admin/wecom/execution-diagnostics")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["execution_mode"] == "execute"
    assert body["corp_id_present"] is True
    assert body["contact_secret_present"] is True
    assert body["default_sender_userid_present"] is True
    assert body["enabled_effect_types"] == [WECOM_CONTACT_TAG_MARK, WECOM_WELCOME_MESSAGE_SEND]
    assert body["deprecated_settings_present"] == ["AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS"]
    assert body["blocking_reasons"] == []


def test_external_effect_public_job_ignores_forward_schema_columns() -> None:
    job = _public_job(
        {
            "id": 42,
            "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            "payload_json": '{"token":"secret-token"}',
            "payload_summary_json": '{"token":"secret-token"}',
            "target_unionids_json": '["future-column"]',
        }
    )

    assert job is not None
    assert job.id == 42
    assert job.effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH
    assert job.payload_json == {"token": "secret-token"}


def test_external_effect_approval_moves_planned_job_to_due_queue() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="approval-sub-1",
        business_type="questionnaire",
        business_id="approval-q-1",
        payload={"webhook_url": "https://hooks.example.test/approval", "body": {"ok": True}},
        context=_sample_context("trace-approval"),
        idempotency_key="approval-state-machine",
        requires_approval=True,
    )

    assert job["status"] == "planned"
    assert repo.list_due_jobs(limit=10) == []

    approved = service.approve(job["id"])
    assert approved is not None
    assert approved.status == "queued"
    assert [item.id for item in repo.list_due_jobs(limit=10)] == [job["id"]]


def test_external_effect_diagnostics_metrics_execution_mode_and_allowed_types(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", raising=False)
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", raising=False)
    service = ExternalEffectService()
    old = datetime.now(timezone.utc) - timedelta(seconds=180)
    for status, suffix in [
        ("queued", "queued"),
        ("dispatching", "dispatching"),
        ("failed_retryable", "retryable"),
        ("failed_terminal", "terminal"),
    ]:
        service.plan_effect(
            effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            adapter_name="outbound_webhook",
            operation="post",
            target_type="questionnaire_submission",
            target_id=f"diag-{suffix}",
            business_type="questionnaire",
            business_id=f"diag-{suffix}",
            payload={"webhook_url": "https://hooks.example.test/diag", "body": {"id": suffix}},
            context=_sample_context(f"trace-diag-{suffix}"),
            idempotency_key=f"diag-{suffix}",
            status=status,
            execution_mode="execute",
            scheduled_at=old,
        )

    disabled = next_client.get("/api/admin/external-effects/diagnostics")
    body = disabled.json()
    assert disabled.status_code == 200
    assert body["real_execution_enabled"] is False
    assert body["execution_mode"] == "disabled"
    assert body["allowed_effect_types"] == []
    assert body["eligible_due_count"] == 2
    assert body["dispatching_count"] == 1
    assert body["failed_retryable_count"] == 1
    assert body["failed_terminal_count"] == 1
    assert body["oldest_queued_age_seconds"] >= 120
    assert body["oldest_failed_retryable_age_seconds"] >= 120
    assert body["queue_metrics"]["eligible_due_count"] == 2

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_ORDER_PAID_PUSH)
    enabled = next_client.get("/api/admin/external-effects/diagnostics")
    enabled_body = enabled.json()

    assert enabled_body["real_execution_enabled"] is True
    assert enabled_body["execution_mode"] == "executable"
    assert enabled_body["allowed_effect_types"] == [WEBHOOK_ORDER_PAID_PUSH]


def test_external_effect_due_queue_reclaims_stale_dispatching_jobs() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="stale-dispatching-reclaim")
    repo.mark_dispatching(job["id"], locked_by="worker-that-crashed")
    row = repo._find(job["id"])  # type: ignore[attr-defined]
    assert row is not None
    row["locked_at"] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()

    metrics = repo.queue_metrics()
    due = repo.list_due_jobs(limit=10)
    acquired = repo.acquire_due_jobs(limit=10, locked_by="replacement-worker")
    updated = repo.get_job(job["id"])

    assert metrics["eligible_due_count"] == 1
    assert [item.id for item in due] == [job["id"]]
    assert [item.id for item in acquired] == [job["id"]]
    assert updated is not None
    assert updated.status == "queued"
    assert updated.locked_by == "replacement-worker"
    assert updated.locked_at


def test_external_effect_sql_due_queue_reclaims_stale_dispatching_jobs() -> None:
    source = (Path(__file__).resolve().parents[1] / "aicrm_next/platform_foundation/external_effects/repo.py").read_text(encoding="utf-8")

    assert "status = 'dispatching' AND locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'" in source
    assert "SET status = CASE WHEN j.status = 'dispatching' THEN 'queued' ELSE j.status END" in source


def test_external_effect_admin_page_is_removed_and_troubleshooting_api_covers_queue_debug(next_client: TestClient) -> None:
    service = ExternalEffectService()
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-sub-1",
        business_type="questionnaire",
        business_id="page-q-1",
        payload={},
        context=_sample_context("trace-page"),
        idempotency_key="page-external-effect-job",
        status="queued",
        payload_summary={"token": "secret-token", "safe": "visible"},
    )
    repo = build_external_effect_repository()
    job_obj = repo.get_job(job["id"])
    assert job_obj is not None
    repo.record_attempt(
        job=job_obj,
        status="blocked",
        adapter_mode="disabled",
        request_summary={"Authorization": "Bearer secret", "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH},
        response_summary={"access_token": "secret", "blocked": True},
        error_code="shadow_only",
        error_message="blocked by test",
    )
    for effect_type, target_type, target_id, business_type, business_id in [
        (WEBHOOK_ORDER_PAID_PUSH, "wechat_pay_order", "page-order-1", "commerce_order", "page-order-1"),
        (WECOM_CONTACT_TAG_MARK, "external_user", "page-wx-ext-1", "wecom_tag", "page-wx-ext-1"),
    ]:
        service.plan_effect(
            effect_type=effect_type,
            adapter_name="outbound_webhook" if effect_type.startswith("webhook.") else "wecom",
            operation="post",
            target_type=target_type,
            target_id=target_id,
            business_type=business_type,
            business_id=business_id,
            payload={},
            context=_sample_context(f"trace-{target_id}"),
            idempotency_key=f"page-{effect_type}-{target_id}",
            status="planned",
        )
    worker = ExternalEffectWorker()
    worker.run_due(batch_size=10, dry_run=False, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH])
    service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-backlog-sub",
        business_type="questionnaire",
        business_id="page-backlog-q",
        payload={},
        context=_sample_context("trace-page-backlog"),
        idempotency_key="page-backlog-external-effect-job",
        status="queued",
    )
    service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-failed-retryable",
        business_type="questionnaire",
        business_id="page-failed-retryable",
        payload={},
        context=_sample_context("trace-page-failed-retryable"),
        idempotency_key="page-failed-retryable-job",
        status="failed_retryable",
    )
    service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-failed-terminal",
        business_type="questionnaire",
        business_id="page-failed-terminal",
        payload={},
        context=_sample_context("trace-page-failed-terminal"),
        idempotency_key="page-failed-terminal-job",
        status="failed_terminal",
    )

    page = next_client.get("/admin/external-effects")
    push_center = next_client.get("/admin/push-center")
    summary = next_client.get("/api/admin/external-effects/troubleshooting/summary").json()
    jobs = next_client.get(
        "/api/admin/external-effects/troubleshooting/jobs",
        params={"problem_only": "false", "trace_id": "trace-page"},
    ).json()
    detail = next_client.get(f"/api/admin/external-effects/troubleshooting/jobs/{job['id']}").json()

    assert page.status_code == 404
    assert push_center.status_code == 200
    assert summary["purpose"] == "external_effect_queue_troubleshooting"
    assert summary["real_external_call_executed"] is False
    assert summary["problem_count"] >= 1
    assert jobs["total"] == 1
    assert jobs["items"][0]["payload_summary_json"]["token"] == "[redacted]"
    assert "payload_json" not in jobs["items"][0]
    assert detail["job"]["id"] == job["id"]
    assert detail["job"]["payload_summary_json"]["token"] == "[redacted]"
    assert detail["attempts"][0]["request_summary_json"]["Authorization"] == "[redacted]"
    assert detail["attempts"][0]["response_summary_json"]["access_token"] == "[redacted]"


def test_external_effect_gray_runbook_documents_disabled_preview_dry_run_real_batch_and_rollback() -> None:
    source = Path("docs/queue/external-effect-queue-gray-runbook.md").read_text(encoding="utf-8")

    for text in [
        "Default Disabled Configuration",
        "AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0",
        "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
        "Run-Due Preview",
        '"dry_run": true',
        "Batch Size 1 Real Execution",
        '"batch_size": 1',
        "Rollback To Disabled",
        "Manual Retry",
        "Manual Cancel",
        "Do not enable real execution for WeCom",
    ]:
        assert text in source


def test_external_effect_test_receiver_disabled_returns_404(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", raising=False)

    response = next_client.post("/api/external-effects/test-receiver/missing", json={"synthetic": True})

    assert response.status_code == 404
    assert response.json()["error"] == "test_receiver_disabled"


def test_external_effect_test_loopback_job_uses_current_host_and_rejects_unsafe_inputs(next_client: TestClient) -> None:
    token = ensure_admin_action_token()
    created = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={"admin_action_token": token, "scenario": "questionnaire_submission_push_success", "response_status": 200},
    )
    blocked_host = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "127.0.0.1"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_success", "response_status": 200},
    )
    arbitrary_url = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={
            "admin_action_token": ensure_admin_action_token(),
            "scenario": "questionnaire_submission_push_success",
            "response_status": 200,
            "webhook_url": "https://attacker.example/hook",
        },
    )

    body = created.json()
    assert created.status_code == 200
    assert body["receiver_url"].startswith("https://crm.example.test/api/external-effects/test-receiver/")
    assert body["job"]["payload_json"]["execution_scope"] == "test_loopback"
    assert body["job"]["payload_json"]["is_test"] is True
    assert "webhook_url" not in body["runbook_next_steps"][0]
    assert blocked_host.status_code == 400
    assert blocked_host.json()["error"] == "invalid_host"
    assert arbitrary_url.status_code == 400
    assert arbitrary_url.json()["error"] == "webhook_url_not_allowed"


def test_external_effect_loopback_allowed_base_hosts_accepts_configured_hosts(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_BASE_HOSTS", "www.youcangogogo.com")

    forwarded = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "www.youcangogogo.com"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_success", "response_status": 200},
    )
    host_fallback = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "Host": "www.youcangogogo.com"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_success", "response_status": 200},
    )

    assert forwarded.status_code == 200
    assert forwarded.json()["receiver_url"].startswith("https://www.youcangogogo.com/api/external-effects/test-receiver/")
    assert host_fallback.status_code == 200
    assert host_fallback.json()["receiver_url"].startswith("https://www.youcangogogo.com/api/external-effects/test-receiver/")


def test_external_effect_loopback_allowed_base_hosts_rejects_forged_forwarded_host(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_BASE_HOSTS", "www.youcangogogo.com")

    created = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "attacker.example.com"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_success", "response_status": 200},
    )
    diagnostics = next_client.get(
        "/api/admin/external-effects/diagnostics",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "attacker.example.com"},
    )
    jobs = next_client.get("/api/admin/external-effects/jobs")

    assert created.status_code == 400
    assert created.json()["error"] == "host_not_allowed"
    assert diagnostics.status_code == 200
    assert diagnostics.json()["current_base_url_detected"] == ""
    assert "attacker.example.com" not in diagnostics.text
    assert jobs.json()["total"] == 0


def test_external_effect_receiver_enabled_records_receipt(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    created = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_success", "response_status": 200},
    ).json()
    token = created["job"]["payload_json"]["receiver_token"]

    response = next_client.post(f"/api/external-effects/test-receiver/{token}", json=created["job"]["payload_json"]["body"], headers={"Authorization": "Bearer secret"})
    receipts = next_client.get("/api/admin/external-effects/test-receipts", params={"job_id": created["job"]["id"]})

    assert response.status_code == 200
    assert response.json()["received"] is True
    assert receipts.json()["total"] == 1
    receipt = receipts.json()["items"][0]
    assert receipt["headers_summary_json"]["authorization"] == "[redacted]"
    assert receipt["payload_hash"] == created["job"]["payload_json"]["expected_payload_hash"]
    assert receipt["signature_valid"] is False


def test_external_effect_loopback_questionnaire_and_order_success_create_receipts(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", f"{WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH},{WEBHOOK_ORDER_PAID_PUSH}")
    calls = _install_loopback_http_adapter(monkeypatch, next_client)

    created_jobs = []
    for scenario in ("questionnaire_submission_push_success", "order_paid_push_success"):
        created = next_client.post(
            "/api/admin/external-effects/test-loopback/jobs",
            headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
            json={"admin_action_token": ensure_admin_action_token(), "scenario": scenario, "response_status": 200},
        ).json()
        created_jobs.append(created["job"])
        preview = next_client.post(
            "/api/admin/external-effects/run-due/preview",
            headers={"Authorization": "Bearer effect-token"},
            json={},
        )
        assert preview.status_code == 401
        dry_run = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[created["job"]["effect_type"]], test_only=True)
        assert dry_run["real_external_call_executed"] is False
        executed = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[created["job"]["effect_type"]], test_only=True)
        assert executed["real_external_call_executed"] is True
        assert executed["counts"]["succeeded_count"] == 1

    service = ExternalEffectService()
    receipts, total = service.list_test_receipts({}, limit=10)
    assert len(calls) == 2
    assert total == 2
    by_job_id = {receipt.job_id: receipt for receipt in receipts}
    for job in created_jobs:
        updated = service.get(job["id"])
        assert updated is not None
        assert updated.status == "succeeded"
        assert by_job_id[job["id"]].trace_id == job["trace_id"]
        assert by_job_id[job["id"]].payload_hash == job["payload_json"]["expected_payload_hash"]


def test_external_effect_loopback_500_retryable_and_400_terminal(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", f"{WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH},{WEBHOOK_ORDER_PAID_PUSH}")
    _install_loopback_http_adapter(monkeypatch, next_client)

    retry_job = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_retry_500", "response_status": 500},
    ).json()["job"]
    terminal_job = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "order_paid_push_terminal_400", "response_status": 400},
    ).json()["job"]

    retry_result = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[retry_job["effect_type"]], test_only=True)
    terminal_result = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[terminal_job["effect_type"]], test_only=True)
    service = ExternalEffectService()
    retry_updated = service.get(retry_job["id"])
    terminal_updated = service.get(terminal_job["id"])
    receipts, total = service.list_test_receipts({}, limit=10)

    assert retry_result["counts"]["failed_count"] == 1
    assert terminal_result["counts"]["failed_count"] == 1
    assert retry_updated is not None
    assert retry_updated.status == "failed_retryable"
    assert retry_updated.next_retry_at
    assert terminal_updated is not None
    assert terminal_updated.status == "failed_terminal"
    assert terminal_updated.next_retry_at == ""
    assert total == 2
    assert sorted(receipt.response_status for receipt in receipts) == [400, 500]


def test_external_effect_loopback_dry_run_allowlist_miss_and_test_only_gate(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_ORDER_PAID_PUSH)
    calls = _install_loopback_http_adapter(monkeypatch, next_client)

    created = next_client.post(
        "/api/admin/external-effects/test-loopback/jobs",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={"admin_action_token": ensure_admin_action_token(), "scenario": "questionnaire_submission_push_success", "response_status": 200},
    ).json()["job"]

    dry_run = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[created["effect_type"]], test_only=True)
    blocked = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[created["effect_type"]], test_only=True)
    receipts, total = ExternalEffectService().list_test_receipts({}, limit=10)

    assert dry_run["real_external_call_executed"] is False
    assert blocked["counts"]["failed_count"] == 1
    assert blocked["real_external_call_executed"] is False
    assert calls == []
    assert total == 0
    assert receipts == []

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    non_test = _queued_webhook_job(service, idempotency_key="non-test-blocked-by-test-only")
    rejected = ExternalEffectWorker(repo).run_due(batch_size=1, dry_run=False, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH], test_only=False)
    direct = ExternalEffectWorker(repo).dispatch_one(non_test["id"])

    assert rejected["ok"] is False
    assert rejected["error"] == "test_only_required"
    assert direct["job"]["status"] == "failed_terminal"
    assert direct["attempt"]["error_code"] == "test_execution_only_required"
    assert repo.test_receipt_metrics()["non_test_execution_blocked_count"] == 1


def test_external_effect_diagnostics_and_api_docs_show_virtual_test_state(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)

    diagnostics = next_client.get(
        "/api/admin/external-effects/diagnostics",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
    ).json()
    docs = next_client.get("/admin/api-docs")

    assert diagnostics["test_receiver_enabled"] is True
    assert diagnostics["test_execution_only"] is True
    assert diagnostics["current_base_url_detected"] == "https://crm.example.test"
    assert diagnostics["allowed_effect_types"] == [WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH]
    assert diagnostics["real_execution_enabled"] is True
    html = docs.text
    for text in [
        "外部动作队列排障",
        "/api/admin/external-effects/troubleshooting/summary",
        "/api/admin/external-effects/troubleshooting/jobs",
        "/api/admin/external-effects/troubleshooting/jobs/{job_id}",
    ]:
        assert text in html


def test_questionnaire_submit_queues_external_push_without_legacy_call(client: TestClient, monkeypatch) -> None:
    _questionnaire, phone_question_id = _seed_hxc_questionnaire(
        monkeypatch,
        {"enabled": True, "webhook_url": "https://hooks.example.com/questionnaire"},
    )

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {phone_question_id: "13770938680"}},
        headers={"Idempotency-Key": "questionnaire-shadow-effect"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["external_push_mode"] == "queue"
    assert body["external_push"]["status"] == "queued"
    assert body["real_external_call_executed"] is False
    assert body["external_effect_job"]["effect_type"] == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH
    assert body["external_effect_job"]["execution_mode"] == "execute"
    assert body["external_effect_job"]["status"] == "queued"
    assert body["external_effect_job_id"]


def test_questionnaire_external_push_is_queue_only(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE", "legacy")
    _questionnaire, phone_question_id = _seed_hxc_questionnaire(
        monkeypatch,
        {"enabled": True, "webhook_url": "https://hooks.example.com/questionnaire/queue-only"},
    )
    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {phone_question_id: "13800001001"}},
        headers={"Idempotency-Key": "queue-only-questionnaire-effect"},
    )
    body = response.json()

    assert external_push.QUESTIONNAIRE_EXTERNAL_PUSH_MODE == "queue"
    assert response.status_code == 200
    assert body["external_push_mode"] == "queue"
    assert body["external_effect_job_id"]
    assert body["external_effect_job_status"] == "queued"
    assert body["external_effect_job"]["execution_mode"] == "execute"
    assert body["external_effect_job"]["status"] == "queued"
    assert body["real_external_call_executed"] is False
    assert body["external_push"]["attempted"] is False
    assert body["external_push"]["status"] == "queued"
    assert "external_push.queued" in body["side_effect_plan"]["payload"]["planned_effects"]


def test_questionnaire_queue_mode_preview_dry_run_and_loopback_execute_2xx(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE", "queue")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET", "questionnaire-loopback-secret")
    calls = _install_loopback_http_adapter(monkeypatch, next_client)

    job = _submit_questionnaire_queue_loopback_job(
        next_client,
        monkeypatch,
        idempotency_key="questionnaire-queue-loopback-2xx",
        phone="13800001002",
        receiver_token="eert_questionnaire_queue_2xx",
        response_status=200,
    )

    preview = ExternalEffectWorker().preview_due(batch_size=1, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH], test_only=True)
    dry_run = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH], test_only=True)
    receipts_before, total_before = ExternalEffectService().list_test_receipts({"job_id": job["id"]}, limit=10)
    executed = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH], test_only=True)

    service = ExternalEffectService()
    updated = service.get(job["id"])
    attempts = service.list_attempts(job["id"])
    receipts, total = service.list_test_receipts({"job_id": job["id"]}, limit=10)

    assert preview["counts"]["candidate_count"] >= 1
    assert dry_run["real_external_call_executed"] is False
    assert receipts_before == []
    assert total_before == 0
    assert executed["real_external_call_executed"] is True
    assert updated is not None
    assert updated.status == "succeeded"
    assert attempts[0].status == "succeeded"
    assert total == 1
    assert len(calls) == 1
    assert receipts[0].trace_id == job["trace_id"]
    assert receipts[0].signature_valid is True
    assert receipts[0].payload_hash == job["payload_json"]["expected_payload_hash"]


def test_questionnaire_queue_mode_loopback_500_retryable_and_400_terminal(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE", "queue")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET", "questionnaire-loopback-secret")
    _install_loopback_http_adapter(monkeypatch, next_client)

    retry_job = _submit_questionnaire_queue_loopback_job(
        next_client,
        monkeypatch,
        idempotency_key="questionnaire-queue-loopback-500",
        phone="13800001003",
        receiver_token="eert_questionnaire_queue_500",
        response_status=500,
    )
    terminal_job = _submit_questionnaire_queue_loopback_job(
        next_client,
        monkeypatch,
        idempotency_key="questionnaire-queue-loopback-400",
        phone="13800001004",
        receiver_token="eert_questionnaire_queue_400",
        response_status=400,
    )

    retry_result = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH], test_only=True)
    terminal_result = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH], test_only=True)
    service = ExternalEffectService()
    retry_updated = service.get(retry_job["id"])
    terminal_updated = service.get(terminal_job["id"])
    retry_attempts = service.list_attempts(retry_job["id"])
    terminal_attempts = service.list_attempts(terminal_job["id"])
    receipts, total = service.list_test_receipts({}, limit=10)

    assert retry_result["counts"]["failed_count"] == 1
    assert terminal_result["counts"]["failed_count"] == 1
    assert retry_updated is not None
    assert retry_updated.status == "failed_retryable"
    assert retry_updated.next_retry_at
    assert retry_attempts[0].response_summary_json["status_code"] == 500
    assert terminal_updated is not None
    assert terminal_updated.status == "failed_terminal"
    assert terminal_updated.next_retry_at == ""
    assert terminal_attempts[0].response_summary_json["status_code"] == 400
    assert total >= 2
    assert {receipt.job_id for receipt in receipts} >= {retry_job["id"], terminal_job["id"]}


def test_questionnaire_queue_mode_job_creation_failure_does_not_fail_submission(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE", "queue")
    _questionnaire, phone_question_id = _seed_hxc_questionnaire(
        monkeypatch,
        {"enabled": True, "webhook_url": "https://hooks.example.com/questionnaire/fail-plan"},
    )

    class _BrokenExternalEffectService:
        def plan_effect(self, **_kwargs):
            raise RuntimeError("external effect unavailable")

    monkeypatch.setattr(external_push, "ExternalEffectService", _BrokenExternalEffectService)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {phone_question_id: "13800001005"}},
        headers={"Idempotency-Key": "questionnaire-queue-plan-failure"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["external_push_mode"] == "queue"
    assert body["real_external_call_executed"] is False
    assert body["external_effect_job_id"] is None


def test_payment_paid_keeps_outbox_and_creates_configured_order_paid_job(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    outbox_calls: list[dict] = []

    def fake_enqueue(conn, order):
        outbox_calls.append(dict(order))
        return {"id": 9}

    monkeypatch.setattr(h5_wechat_pay, "enqueue_transaction_paid_outbox", fake_enqueue)
    monkeypatch.setattr(external_push_admin, "resolve_and_validate_public_https_url", lambda url: url)

    order = _apply_transaction(
        _ApplyTransactionConn(),
        {
            "out_trade_no": "WXP_SHADOW_PAID",
            "trade_state": "SUCCESS",
            "transaction_id": "wx_tx_shadow",
            "success_time": "2026-06-13T10:00:00+08:00",
            "amount": {"payer_total": 990},
            "payer": {"openid": "openid_shadow"},
        },
    )

    items, total = ExternalEffectService().list_jobs({"effect_type": WEBHOOK_ORDER_PAID_PUSH, "business_id": "7"})
    assert order["status"] == "paid"
    assert len(outbox_calls) == 1
    assert total == 1
    assert items[0].target_type == "external_push_delivery"
    assert items[0].execution_mode == "execute"
    assert items[0].status == "queued"
    assert items[0].payload_json["webhook_url"] == "https://example.com/order-paid"
    assert items[0].payload_json["body"]["event"] == "transaction.paid"
    assert items[0].payload_json["body"]["order"]["out_trade_no"] == "WXP_SHADOW_PAID"
    assert items[0].payload_json["headers"]["X-AICRM-Event"] == "transaction.paid"

def test_wecom_tag_adapter_registry_dispatches_contact_tag_mark_and_unmark(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeWeComAdapter:
        def mark_external_contact_tags(self, **payload):
            calls.append(payload)
            return {"errcode": 0}

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", f"{WECOM_CONTACT_TAG_MARK},{WECOM_CONTACT_TAG_UNMARK}")
    repo = InMemoryExternalEffectRepository()
    mark_job = _service(repo).plan_effect(
        effect_type=WECOM_CONTACT_TAG_MARK,
        adapter_name="wecom_tag",
        operation="mark",
        target_type="external_user",
        target_id="wx_ext_tag_dispatch",
        business_type="channel_entry",
        business_id="channel-1",
        payload={
            "external_userid": "wx_ext_tag_dispatch",
            "follow_user_userid": "owner-a",
            "add_tags": ["tag_a"],
            "remove_tags": [],
        },
        context=_sample_context("trace-wecom-tag-dispatch"),
        idempotency_key="wecom-tag-dispatch",
    )
    unmark_job = _service(repo).plan_effect(
        effect_type=WECOM_CONTACT_TAG_UNMARK,
        adapter_name="wecom_tag",
        operation="unmark",
        target_type="external_user",
        target_id="wx_ext_tag_dispatch",
        business_type="wecom_tag",
        business_id="wx_ext_tag_dispatch",
        payload={
            "external_userid": "wx_ext_tag_dispatch",
            "follow_user_userid": "owner-a",
            "tag_ids": ["tag_b"],
        },
        context=_sample_context("trace-wecom-tag-unmark-dispatch"),
        idempotency_key="wecom-tag-unmark-dispatch",
    )
    registry = ExternalEffectAdapterRegistry()
    assert isinstance(registry._adapters["wecom_tag"], WeComContactTagAdapter)  # type: ignore[attr-defined]
    registry._adapters["wecom_tag"] = WeComContactTagAdapter(adapter_factory=lambda: FakeWeComAdapter())  # type: ignore[attr-defined]

    result = ExternalEffectWorker(repo, registry).run_due(
        batch_size=2,
        dry_run=False,
        effect_types=[WECOM_CONTACT_TAG_MARK, WECOM_CONTACT_TAG_UNMARK],
    )

    assert result["counts"]["succeeded_count"] == 2
    assert result["items"][0]["job"]["status"] == "succeeded"
    assert result["real_external_call_executed"] is True
    assert calls == [
        {
            "external_userid": "wx_ext_tag_dispatch",
            "follow_user_userid": "owner-a",
            "add_tags": ["tag_a"],
            "remove_tags": [],
        },
        {
            "external_userid": "wx_ext_tag_dispatch",
            "follow_user_userid": "owner-a",
            "add_tags": [],
            "remove_tags": ["tag_b"],
        }
    ]
    assert mark_job["adapter_name"] == "wecom_tag"
    assert unmark_job["adapter_name"] == "wecom_tag"


def test_wecom_profile_adapter_registry_dispatches_description_update(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeWeComAdapter:
        def update_external_contact_remark(self, payload):
            calls.append(payload)
            return {"errcode": 0}

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_PROFILE_UPDATE)
    repo = InMemoryExternalEffectRepository()
    job = _service(repo).plan_effect(
        effect_type=WECOM_PROFILE_UPDATE,
        adapter_name="wecom_profile",
        operation="update_description",
        target_type="external_user",
        target_id="wx_ext_profile",
        business_type="channel_entry",
        business_id="channel-1",
        payload={
            "external_userid": "wx_ext_profile",
            "follow_user_userid": "owner-a",
            "description": "wx_ext_profile",
        },
        context=_sample_context("trace-wecom-profile-dispatch"),
        idempotency_key="wecom-profile-dispatch",
    )
    registry = ExternalEffectAdapterRegistry()
    assert isinstance(registry._adapters["wecom_profile"], WeComProfileUpdateAdapter)  # type: ignore[attr-defined]
    registry._adapters["wecom_profile"] = WeComProfileUpdateAdapter(adapter_factory=lambda: FakeWeComAdapter())  # type: ignore[attr-defined]

    result = ExternalEffectWorker(repo, registry).run_due(batch_size=1, dry_run=False, effect_types=[WECOM_PROFILE_UPDATE])

    assert result["counts"]["succeeded_count"] == 1
    assert result["items"][0]["job"]["status"] == "succeeded"
    assert result["real_external_call_executed"] is True
    assert calls == [
        {
            "userid": "owner-a",
            "external_userid": "wx_ext_profile",
            "description": "wx_ext_profile",
        }
    ]
    assert job["adapter_name"] == "wecom_profile"


def test_wechat_payment_adapter_registry_dispatches_refund_and_syncs_result(monkeypatch) -> None:
    create_calls: list[dict] = []
    sync_calls: list[dict] = []

    class FakeWeChatPayClient:
        def create_refund(self, payload):
            create_calls.append(payload)
            return {
                "refund_id": "503000000020260626",
                "out_refund_no": payload["out_refund_no"],
                "status": "PROCESSING",
            }

    def sync_refund_result(payload):
        sync_calls.append(payload)
        return {"ok": True, "order_refund_status": ""}

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", PAYMENT_WECHAT_REFUND_REQUEST)
    repo = InMemoryExternalEffectRepository()
    job = _service(repo).plan_effect(
        effect_type=PAYMENT_WECHAT_REFUND_REQUEST,
        adapter_name="wechat_payment",
        operation="refund_request",
        target_type="wechat_pay_refund",
        target_id="WXRTESTPAY001",
        business_type="commerce_order",
        business_id="WXPTESTPAY001",
        payload={
            "out_trade_no": "WXPTESTPAY001",
            "transaction_id": "420000TESTPAY",
            "out_refund_no": "WXRTESTPAY001",
            "request_payload": {
                "transaction_id": "420000TESTPAY",
                "out_refund_no": "WXRTESTPAY001",
                "reason": "客户主动申请退款",
                "amount": {"refund": 9900, "total": 9900, "currency": "CNY"},
            },
        },
        context=_sample_context("trace-wechat-refund-dispatch"),
        idempotency_key="wechat-refund-dispatch",
    )
    registry = ExternalEffectAdapterRegistry()
    assert isinstance(registry._adapters["wechat_payment"], WeChatPaymentAdapter)  # type: ignore[attr-defined]
    registry._adapters["wechat_payment"] = WeChatPaymentAdapter(  # type: ignore[attr-defined]
        client_factory=lambda: FakeWeChatPayClient(),
        refund_result_sync=sync_refund_result,
    )

    result = ExternalEffectWorker(repo, registry).run_due(batch_size=1, dry_run=False, effect_types=[PAYMENT_WECHAT_REFUND_REQUEST])

    assert result["counts"]["succeeded_count"] == 1
    assert result["items"][0]["job"]["status"] == "succeeded"
    assert result["real_external_call_executed"] is True
    assert create_calls == [job["payload_json"]["request_payload"]]
    assert sync_calls[0]["refund_id"] == "503000000020260626"
    assert sync_calls[0]["out_refund_no"] == "WXRTESTPAY001"
    assert sync_calls[0]["refund_status"] == "PROCESSING"


def test_wechat_payment_adapter_gate_failure_marks_refund_failed(monkeypatch) -> None:
    failure_sync_calls: list[dict] = []

    def sync_failure(out_refund_no, *, error_code, error_message, response_payload):
        failure_sync_calls.append(
            {
                "out_refund_no": out_refund_no,
                "error_code": error_code,
                "error_message": error_message,
                "response_payload": response_payload,
            }
        )
        return {"ok": True}

    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE", raising=False)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", PAYMENT_WECHAT_REFUND_REQUEST)
    repo = InMemoryExternalEffectRepository()
    _service(repo).plan_effect(
        effect_type=PAYMENT_WECHAT_REFUND_REQUEST,
        adapter_name="wechat_payment",
        operation="refund_request",
        target_type="wechat_pay_refund",
        target_id="WXRTESTPAYGATE",
        business_type="commerce_order",
        business_id="WXPTESTPAYGATE",
        payload={
            "transaction_id": "420000TESTPAY",
            "out_refund_no": "WXRTESTPAYGATE",
            "request_payload": {
                "transaction_id": "420000TESTPAY",
                "out_refund_no": "WXRTESTPAYGATE",
                "amount": {"refund": 9900, "total": 9900, "currency": "CNY"},
            },
        },
        context=_sample_context("trace-wechat-refund-gate"),
        idempotency_key="wechat-refund-gate",
    )
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wechat_payment"] = WeChatPaymentAdapter(refund_failure_sync=sync_failure)  # type: ignore[attr-defined]

    result = ExternalEffectWorker(repo, registry).run_due(batch_size=1, dry_run=False, effect_types=[PAYMENT_WECHAT_REFUND_REQUEST])

    assert result["counts"]["failed_count"] == 1
    assert result["items"][0]["job"]["status"] == "failed_terminal"
    assert result["items"][0]["attempt"]["error_code"] == "payment_execution_disabled"
    assert result["real_external_call_executed"] is False
    assert failure_sync_calls[0]["out_refund_no"] == "WXRTESTPAYGATE"
    assert failure_sync_calls[0]["error_code"] == "payment_execution_disabled"


def test_wechat_payment_adapter_terminal_provider_failure_marks_refund_failed(monkeypatch) -> None:
    failure_sync_calls: list[dict] = []

    class FakeWeChatPayClient:
        def create_refund(self, payload):
            raise WeChatPayClientError("invalid refund amount", status_code=400, payload={"code": "PARAM_ERROR"})

    def sync_failure(out_refund_no, *, error_code, error_message, response_payload):
        failure_sync_calls.append(
            {
                "out_refund_no": out_refund_no,
                "error_code": error_code,
                "error_message": error_message,
                "response_payload": response_payload,
            }
        )
        return {"ok": True}

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", PAYMENT_WECHAT_REFUND_REQUEST)
    repo = InMemoryExternalEffectRepository()
    _service(repo).plan_effect(
        effect_type=PAYMENT_WECHAT_REFUND_REQUEST,
        adapter_name="wechat_payment",
        operation="refund_request",
        target_type="wechat_pay_refund",
        target_id="WXRTESTPAY400",
        business_type="commerce_order",
        business_id="WXPTESTPAY400",
        payload={
            "transaction_id": "420000TESTPAY400",
            "out_refund_no": "WXRTESTPAY400",
            "request_payload": {
                "transaction_id": "420000TESTPAY400",
                "out_refund_no": "WXRTESTPAY400",
                "amount": {"refund": 9900, "total": 9900, "currency": "CNY"},
            },
        },
        context=_sample_context("trace-wechat-refund-400"),
        idempotency_key="wechat-refund-400",
    )
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wechat_payment"] = WeChatPaymentAdapter(  # type: ignore[attr-defined]
        client_factory=lambda: FakeWeChatPayClient(),
        refund_failure_sync=sync_failure,
    )

    result = ExternalEffectWorker(repo, registry).run_due(batch_size=1, dry_run=False, effect_types=[PAYMENT_WECHAT_REFUND_REQUEST])

    assert result["counts"]["failed_count"] == 1
    assert result["items"][0]["job"]["status"] == "failed_terminal"
    assert result["items"][0]["attempt"]["error_code"] == "http_400"
    assert result["real_external_call_executed"] is True
    assert failure_sync_calls[0]["out_refund_no"] == "WXRTESTPAY400"
    assert failure_sync_calls[0]["error_code"] == "http_400"
    assert failure_sync_calls[0]["response_payload"]["real_external_call_executed"] is True


def test_wecom_tag_mark_and_unmark_create_shadow_jobs() -> None:
    reset_external_effect_fixture_state()
    reset_wecom_tag_live_mutation_fixture_state()
    mark = execute_wecom_tag_mutation(
        PlanWeComTagMarkCommand(
            idempotency_key="wecom-tag-mark-shadow",
            external_userid="wx_ext_tag_001",
            tag_ids=["tag_a"],
            source_route="/api/admin/customer-tags/live/mark",
        )
    )
    unmark = execute_wecom_tag_mutation(
        PlanWeComTagUnmarkCommand(
            idempotency_key="wecom-tag-unmark-shadow",
            external_userid="wx_ext_tag_001",
            tag_ids=["tag_a"],
            source_route="/api/admin/customer-tags/live/unmark",
        )
    )

    assert mark["real_external_call_executed"] is False
    assert mark["wecom_api_called"] is False
    assert mark["external_effect_job"]["effect_type"] == WECOM_CONTACT_TAG_MARK
    assert unmark["external_effect_job"]["effect_type"] == WECOM_CONTACT_TAG_UNMARK
    assert unmark["external_effect_job"]["execution_mode"] == "execute"
    assert unmark["external_effect_job"]["status"] == "queued"
