from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    GROUP_OPS_MESSAGE_LOOPBACK,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    ExternalEffectService,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.repo import build_external_effect_repository
from aicrm_next.platform_foundation.push_center.projection import BroadcastJobAdapter, PushCenterProjectionService
from aicrm_next.platform_foundation.push_center.repository import PushCenterRepository
from aicrm_next.platform_foundation.push_center.section_mapper import effect_types_for_section, label_for_section, section_for_job
from aicrm_next.platform_foundation.push_center.view_model import (
    build_job_detail_payload,
    build_job_reconciliation_payload,
    build_jobs_payload,
    build_stats_payload,
)
from tests.group_ops_test_helpers import group_ops_api_client


class _FakeBroadcastJobAdapter(BroadcastJobAdapter):
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def list_jobs(self, filters: dict | None = None, *, limit: int = 1000) -> list[dict]:
        return list(self.rows[:limit])

    def get_job(self, job_id: int) -> dict | None:
        return next((row for row in self.rows if int(row["id"]) == int(job_id)), None)


def _projection_repo(*, broadcast_rows: list[dict]) -> PushCenterRepository:
    return PushCenterRepository(service=PushCenterProjectionService(broadcast_adapter=_FakeBroadcastJobAdapter(broadcast_rows)))


def _context(trace_id: str = "trace-push-center", source_route: str = "/pytest/push-center") -> CommandContext:
    return CommandContext(actor_id="pytest", actor_type="system", request_id=trace_id, trace_id=trace_id, source_route=source_route)


def _plan_job(
    *,
    effect_type: str,
    business_type: str,
    business_id: str,
    target_type: str = "external_user",
    target_id: str = "wm_fixture_a",
    status: str = "queued",
    execution_mode: str = "execute",
    payload: dict | None = None,
    payload_summary: dict | None = None,
    trace_id: str = "trace-push-center",
    idempotency_key: str = "",
) -> dict:
    return ExternalEffectService().plan_effect(
        effect_type=effect_type,
        adapter_name="wecom_private_message" if effect_type == WECOM_MESSAGE_PRIVATE_SEND else "outbound_webhook",
        operation="send" if effect_type == WECOM_MESSAGE_PRIVATE_SEND else "post",
        target_type=target_type,
        target_id=target_id,
        business_type=business_type,
        business_id=business_id,
        payload=payload or {"owner_userid": "HuangYouCan", "external_userids": [target_id], "token": "secret-token"},
        payload_summary=payload_summary or {"owner_userid": "HuangYouCan", "external_userid": target_id, "token": "secret-token"},
        context=_context(trace_id=trace_id),
        source_module="pytest.push_center",
        source_event_id=business_id,
        source_command_id=idempotency_key or business_id,
        risk_level="medium",
        execution_mode=execution_mode,
        status=status,
        idempotency_key=idempotency_key or f"push-center:{effect_type}:{business_id}:{target_id}",
    )


def test_section_mapper_routes_effect_types_by_business_type() -> None:
    reset_external_effect_fixture_state()
    ai_job = _plan_job(effect_type=WECOM_MESSAGE_PRIVATE_SEND, business_type="ai_assist_campaign", business_id="camp_1")
    private_job = _plan_job(effect_type=WECOM_MESSAGE_PRIVATE_SEND, business_type="private_broadcast", business_id="broadcast_1", target_id="wm_fixture_b")
    group_job = _plan_job(
        effect_type=WECOM_MESSAGE_GROUP_SEND,
        business_type="group_ops_plan",
        business_id="12",
        target_type="group_ops_webhook_event",
        target_id="17",
        payload={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_ids": ["chat_1"]},
        payload_summary={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_count": 1},
    )

    assert section_for_job(ai_job) == "ai_assist"
    assert section_for_job(private_job) == "private_broadcast"
    assert section_for_job(group_job) == "group_ops"
    assert WECOM_MESSAGE_GROUP_SEND in effect_types_for_section("group_ops")
    assert label_for_section("questionnaire") == "问卷外推"


def test_push_center_jobs_filters_and_payload_redaction(next_client: TestClient) -> None:
    reset_external_effect_fixture_state()
    _plan_job(effect_type=WECOM_MESSAGE_PRIVATE_SEND, business_type="ai_assist_campaign", business_id="camp_1", trace_id="trace-ai")
    _plan_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        business_type="questionnaire",
        business_id="q_1",
        target_type="questionnaire_submission",
        target_id="sub_1",
        trace_id="trace-questionnaire",
        status="planned",
        execution_mode="shadow",
    )

    response = next_client.get("/api/admin/push-center/jobs?section=ai_assist&external_userid=wm_fixture_a")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["total"] == 1
    assert body["items"][0]["section"] == "ai_assist"
    assert body["items"][0]["business_id"] == "camp_1"
    assert body["items"][0]["payload_summary"]["token"] == "[redacted]"
    assert "payload_json" not in body["items"][0]

    planned = next_client.get("/api/admin/push-center/jobs?section=questionnaire&status=pending").json()
    assert planned["total"] == 1
    assert planned["items"][0]["status"] == "pending"
    assert planned["items"][0]["status_label"] == "待执行"
    assert planned["items"][0]["raw_status"] == "planned"
    assert {item["key"] for item in planned["status_definitions"]} == {
        "pending",
        "running",
        "sent",
        "failed",
        "sent_with_shadow_warning",
        "shadow_failed_not_business_failed",
    }


def test_push_center_group_ops_shadow_failed_with_sent_broadcast_is_warning_not_failed() -> None:
    reset_external_effect_fixture_state()
    job = _plan_job(
        effect_type=GROUP_OPS_MESSAGE_LOOPBACK,
        business_type="group_ops_plan",
        business_id="11",
        target_type="group_ops_webhook_event",
        target_id="23",
        status="failed_terminal",
        trace_id="group-ops-legacy-bundle:11:23:daily-lesson",
        idempotency_key="group-ops-legacy-bundle:11:23:daily-lesson",
        payload_summary={"plan_id": 11, "trigger_event_id": "23", "chat_count": 8, "webhook_key": "正式群运营计划测试-584571"},
    )
    repo = build_external_effect_repository()
    job_obj = repo.get_job(job["id"])
    assert job_obj is not None
    repo.record_attempt(
        job=job_obj,
        status="failed_terminal",
        adapter_mode="execute",
        request_summary={"effect_type": GROUP_OPS_MESSAGE_LOOPBACK, "target_id": "23"},
        response_summary={"blocked": True, "execution_gate": "group_ops_loopback_requires_test_receiver", "real_external_call_executed": False},
        error_code="group_ops_loopback_requires_test_receiver",
        error_message="Webhook adapter execution is blocked by external effect execution gates.",
    )
    broadcast_rows = [
        {
            "id": 3642,
            "source_type": "workflow",
            "source_id": "11:webhook:23",
            "source_table": "automation_group_ops_plans",
            "scheduled_for": "2026-06-18T00:57:15Z",
            "batch_key": "",
            "business_domain": "",
            "channel": "wecom_customer_group",
            "target_kind": "chat_id",
            "failure_type": "",
            "status": "sent",
            "target_count": 0,
            "target_summary": "8 customer groups",
            "content_type": "text",
            "content_summary": "6月18日思考",
            "attempt_count": 1,
            "last_error": "",
            "outbound_task_id": 3925,
            "sent_count": 8,
            "failed_count": 0,
            "trace_id": "group_ops:11:webhook:23:2026-06-18T08:57:15.390408+08:00",
            "idempotency_key": "group_ops:11:webhook:23:2026-06-18T08:57:15.390408+08:00",
            "created_by": "group_ops_webhook",
            "created_at": "2026-06-18T00:57:10Z",
            "updated_at": "2026-06-18T00:58:04Z",
            "claimed_at": "2026-06-18T00:58:01Z",
            "sent_at": "2026-06-18T00:58:04Z",
            "outbound_task_status": "created",
            "outbound_task_type": "broadcast_job/group_ops",
            "outbound_task_wecom_task_id": "msgbNXyCwAAv7rCQ6fHkZwegoawyRNWqQ",
            "outbound_task_response_payload": '{"result":{"errcode":0,"errmsg":"ok","msgid":"msgbNXyCwAAv7rCQ6fHkZwegoawyRNWqQ"},"ok":true,"side_effect_executed":true,"exact_target_verified":true}',
            "outbound_task_trace_id": "group_ops:11:webhook:23:2026-06-18T08:57:15.390408+08:00",
            "outbound_task_created_at": "2026-06-18T00:58:04Z",
        }
    ]
    projection_repo = _projection_repo(broadcast_rows=broadcast_rows)

    body = build_jobs_payload({"section": "group_ops"}, repository=projection_repo)
    item = body["items"][0]
    stats = build_stats_payload({"section": "group_ops"}, repository=projection_repo)
    detail = build_job_detail_payload(item["projection_id"], repository=projection_repo)
    reconciliation = build_job_reconciliation_payload(item["projection_id"], repository=projection_repo)

    assert item["effective_status"] == "sent_with_shadow_warning"
    assert item["status"] == "sent_with_shadow_warning"
    assert item["status_label"] == "已发送 · 影子链路异常"
    assert "linked_records" not in item
    assert item["linked_record_counts"] == {
        "external_effect_jobs": 1,
        "external_effect_attempts": 1,
        "broadcast_jobs": 1,
        "outbound_tasks": 1,
    }
    assert stats["counts"]["sent"] == 1
    assert stats["counts"]["failed"] == 0
    assert detail is not None
    assert len(detail["linked_records"]["external_effect_jobs"]) == 1
    assert len(detail["linked_records"]["external_effect_attempts"]) == 1
    assert len(detail["linked_records"]["broadcast_jobs"]) == 1
    assert detail["linked_records"]["outbound_tasks"][0]["response_payload"]["result"]["errcode"] == 0
    assert reconciliation is not None
    assert reconciliation["reconciliation"]["effective_status"] == "sent_with_shadow_warning"
    assert reconciliation["reconciliation"]["retryable"] is False
    assert reconciliation["reconciliation"]["operator_action_required"] is True
    assert reconciliation["reconciliation"]["next_action_label"] == "检查影子链路"
    assert "不要把它误判为业务发送失败" in reconciliation["reconciliation"]["business_explanation"]


def test_push_center_group_ops_shadow_failed_without_primary_is_not_business_failed() -> None:
    reset_external_effect_fixture_state()
    _plan_job(
        effect_type=GROUP_OPS_MESSAGE_LOOPBACK,
        business_type="group_ops_plan",
        business_id="11",
        target_type="group_ops_webhook_event",
        target_id="24",
        status="failed_terminal",
        trace_id="group-ops-legacy-bundle:11:24:daily-lesson",
        idempotency_key="group-ops-legacy-bundle:11:24:daily-lesson",
        payload_summary={"plan_id": 11, "trigger_event_id": "24", "chat_count": 1},
    )
    projection_repo = _projection_repo(broadcast_rows=[])

    body = build_jobs_payload({"section": "group_ops"}, repository=projection_repo)
    failed = build_jobs_payload({"section": "group_ops", "status": "failed"}, repository=projection_repo)
    stats = build_stats_payload({"section": "group_ops"}, repository=projection_repo)

    assert body["items"][0]["effective_status"] == "shadow_failed_not_business_failed"
    assert body["items"][0]["status_label"] == "影子链路失败，未发现主发送记录"
    assert failed["total"] == 0
    assert stats["counts"]["failed"] == 0
    assert stats["counts"]["shadow_warning"] == 1


def test_push_center_detail_includes_attempts_without_full_payload(next_client: TestClient) -> None:
    reset_external_effect_fixture_state()
    job = _plan_job(effect_type=AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK, business_type="ai_assist_campaign", business_id="camp_loop", status="blocked", execution_mode="shadow")
    repo = build_external_effect_repository()
    job_obj = repo.get_job(job["id"])
    assert job_obj is not None
    repo.record_attempt(
        job=job_obj,
        status="blocked",
        adapter_mode="shadow",
        request_summary={"Authorization": "Bearer secret", "effect_type": job_obj.effect_type},
        response_summary={"access_token": "secret", "blocked": True},
        error_code="shadow_only",
        error_message="blocked by test",
    )

    response = next_client.get(f"/api/admin/push-center/jobs/{job['id']}")
    body = response.json()

    assert response.status_code == 200
    assert body["job"]["projection_id"] == f"external_effect_job:{job['id']}"
    assert body["job"]["source_record_id"] == job["id"]
    assert "payload_json" not in body["job"]
    assert body["attempts"][0]["request_summary"]["Authorization"] == "[redacted]"
    assert body["attempts"][0]["response_summary"]["access_token"] == "[redacted]"


def test_push_center_sections_stats_retry_cancel_auth(next_client: TestClient, monkeypatch) -> None:
    reset_external_effect_fixture_state()
    failed = _plan_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        business_type="questionnaire",
        business_id="q_failed",
        target_type="questionnaire_submission",
        target_id="sub_failed",
        status="failed_retryable",
        execution_mode="execute",
        trace_id="trace-failed",
    )
    queued = _plan_job(
        effect_type=WECOM_MESSAGE_GROUP_SEND,
        business_type="group_ops_plan",
        business_id="12",
        target_type="group_ops_webhook_event",
        target_id="17",
        status="queued",
        execution_mode="execute",
        trace_id="trace-group",
        payload={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_ids": ["chat_1"]},
        payload_summary={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_count": 1},
    )
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "pytest-internal-token")

    sections = next_client.get("/api/admin/push-center/sections").json()
    stats = next_client.get("/api/admin/push-center/stats").json()
    reconciliation = next_client.get(f"/api/admin/push-center/jobs/{failed['id']}/reconciliation")
    rejected = next_client.post(f"/api/admin/push-center/jobs/{failed['id']}/retry", json={})
    retried = next_client.post(
        f"/api/admin/push-center/jobs/{failed['id']}/retry",
        headers={"Authorization": "Bearer pytest-internal-token"},
        json={},
    )
    cancelled = next_client.post(
        f"/api/admin/push-center/jobs/{queued['id']}/cancel",
        headers={"Authorization": "Bearer pytest-internal-token"},
        json={},
    )

    assert any(item["key"] == "questionnaire" and item["count"] == 1 for item in sections["sections"])
    assert stats["counts"]["failed"] == 1
    assert reconciliation.status_code == 200
    assert reconciliation.json()["reconciliation"]["effective_status"] == "failed"
    assert reconciliation.json()["reconciliation"]["retryable"] is True
    assert reconciliation.json()["reconciliation"]["operator_action_required"] is True
    assert reconciliation.json()["reconciliation"]["next_action_label"] == "重试"
    assert reconciliation.json()["reconciliation"]["linked_record_counts"]["external_effect_jobs"] == 1
    assert rejected.status_code == 401
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "pending"
    assert retried.json()["job"]["raw_status"] == "queued"
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "failed"
    assert cancelled.json()["job"]["raw_status"] == "cancelled"


def test_push_center_page_smoke(next_client: TestClient) -> None:
    reset_external_effect_fixture_state()
    _plan_job(effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, business_type="questionnaire", business_id="q_page", target_type="questionnaire_submission", target_id="sub_page")

    response = next_client.get("/admin/push-center")

    assert response.status_code == 200
    assert "推送中心" in response.text
    assert 'id="statsGrid"' in response.text
    assert 'id="sectionTabs"' in response.text
    assert 'id="filterForm"' in response.text
    assert 'id="pushCenterTable"' in response.text
    assert 'id="detailModal"' in response.text
    assert 'id="detailPanel"' in response.text
    assert 'data-close-detail' in response.text
    assert 'role="dialog"' in response.text
    assert 'aria-modal="true"' in response.text
    assert 'aria-hidden="true"' in response.text
    assert "push-center-modal" in response.text
    assert "push-center-modal-card" in response.text
    assert "push-center-detail-card" not in response.text
    assert "openDetailModal" in response.text
    assert "closeDetailModal" in response.text
    assert "is-open" in response.text
    assert 'event.key === "Escape"' in response.text
    assert 'class="push-center-header"' not in response.text
    assert "push-center-title" not in response.text
    assert 'href="#refresh"' in response.text
    assert 'href="#export"' in response.text
    assert "<colgroup>" in response.text
    assert "push-center-col-section" in response.text
    assert "push-center-section-label" in response.text
    assert "push-center-ellipsis" in response.text
    assert "STATUS_LABELS" in response.text
    assert "EFFECT_TYPE_LABELS" in response.text
    assert "TARGET_TYPE_LABELS" in response.text
    assert "BUSINESS_TYPE_LABELS" in response.text
    assert "formatBeijingTime" in response.text
    assert 'timeZone: "Asia/Shanghai"' in response.text
    assert "push-center-time-date" in response.text
    assert "push-center-time-clock" in response.text
    assert "已计划" not in response.text
    assert "失败可重试" not in response.text
    assert "失败不可重试" not in response.text
    assert 'id="legacyDeprecationsPanel"' not in response.text
    assert 'id="legacyDeprecationsList"' not in response.text
    assert "/api/admin/push-center/legacy-deprecations" not in response.text
    assert "旧链路下线状态" not in response.text
    assert "下次删除" not in response.text
    assert "/api/admin/push-center/stats" in response.text
    assert "/api/admin/push-center/jobs" in response.text
    assert 'data-action="retry"' in response.text
    assert 'data-action="cancel"' in response.text
    assert "问卷外推" in response.text
    assert "外部动作队列" not in response.text
    assert "payload_json" not in response.text
    assert "token" not in response.text.lower()
    assert "secret" not in response.text.lower()
    assert "Authorization" not in response.text
    assert "access_token" not in response.text
    assert "secret-token" not in response.text


def test_questionnaire_default_external_push_is_queue_first(client: TestClient, monkeypatch) -> None:
    from aicrm_next.questionnaire.repo import build_questionnaire_repository

    monkeypatch.delenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE", raising=False)
    repo = build_questionnaire_repository()
    existing = repo.get_questionnaire_by_slug("hxc-activation-v1")
    questionnaire = repo.save_questionnaire(
        {
            "slug": "hxc-activation-v1",
            "name": "黄小璨激活问卷",
            "title": "黄小璨激活问卷",
            "enabled": True,
            "external_push_config": {"enabled": True, "webhook_url": "https://hooks.example.com/should-not-send"},
            "questions": [{"id": "q_mobile", "type": "mobile", "title": "手机号", "required": True, "options": []}],
        },
        questionnaire_id=int(existing["id"]) if existing else None,
    )
    phone_question_id = str(questionnaire["questions"][0].get("id") or "q_mobile")

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {phone_question_id: "test_phone_default_queue"}},
        headers={"Idempotency-Key": "push-center-questionnaire-default-queue"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["external_push_mode"] == "queue"
    assert body["external_push"]["status"] == "queued"
    assert body["external_push"]["attempted"] is False
    assert body["real_external_call_executed"] is False
    assert body["external_effect_job_status"] == "queued"


def test_group_ops_default_webhook_uses_external_effect_not_legacy_gateway(group_ops_api_client, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_GROUP_OPS_OUTBOUND_MODE", raising=False)
    monkeypatch.delenv("AICRM_GROUP_OPS_EXTERNAL_EFFECT_SEND_MODE", raising=False)
    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "push-center-default-group-ops-external-effect",
            "send_mode": "queued",
            "content": {"text": "synthetic group ops default external effect", "attachments": []},
        },
    )
    body = response.json()

    assert response.status_code == 202
    assert body["outbound_mode"] == "external_effect"
    assert body["legacy_outbound_disabled"] is True
    assert body["external_effect_required"] is True
    assert body["broadcast_job_ids"] == []
    assert body["legacy_broadcast_job_ids"] == []
    assert body["external_effect_job_ids"]
