from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import service as customer_pulse_service_runtime
from .service import (
    CUSTOMER_PULSE_FLAG_KEY,
    CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE,
    CUSTOMER_PULSE_RESOURCE_CARD,
    CUSTOMER_PULSE_RULES_VERSION,
    CUSTOMER_PULSE_UNDO_WINDOW_MINUTES,
    _EXECUTION_AUDIT_HUMAN_CONFIRMED,
    _EXECUTION_AUDIT_HUMAN_EDITED,
    _action_allowed,
    _action_label,
    _action_requires_undo_window,
    _ai_audit_labels_from_candidate,
    _assert_action_scope,
    _build_action_idempotency_key,
    _build_execution_response,
    _build_rule_based_draft_message,
    _card_state_snapshot,
    _draft_execution_guardrail_hits,
    _edited_fields,
    _execution_audit_labels,
    _execution_key,
    _execution_rollback_payload,
    _existing_execution_response,
    _followup_segment_from_marketing_state,
    _guardrail_summary,
    _iso_now,
    _json_loads,
    _materialize_customer_pulse,
    _next_followup_time,
    _normalize_action_execution_payload,
    _normalized_text,
    _present_card,
    _present_execution_log,
    _record_action_feedback,
    _record_metric_event,
    _reply_draft_task_payload,
    _request_payload_audit_summary,
    _resolve_card_action_candidate,
    _resolved_tenant_context,
    _resolved_tenant_key,
    _restore_card_state,
    _result_payload_audit_summary,
    _segment_label,
    _undo_until,
    _unsafe_execution_input_fields,
    assert_customer_pulse_action_permission,
    customer_pulse_action_permission,
    customer_pulse_feature_gate_summary,
    customer_pulse_tenant_context_summary,
    is_customer_pulse_inbox_enabled,
    repo,
    save_local_private_message_draft,
    update_outbound_task_status,
)

__all__ = [
    "enqueue_customer_pulse_recompute",
    "execute_customer_pulse_card_action",
    "preview_customer_pulse_card_action",
    "refresh_customer_pulse_cards",
    "run_due_customer_pulse_recompute_jobs",
    "run_due_customer_pulse_snapshot_job",
    "undo_customer_pulse_card_action_execution",
]


def refresh_customer_pulse_cards(
    *,
    limit: int = 50,
    operator: str = "system",
    external_userids: list[str] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        return {
            "enabled": False,
            "feature_gate": feature_gate,
            "processed_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "cards": [],
        }
    candidate_external_userids = [
        _normalized_text(item)
        for item in (external_userids or repo.list_customer_pulse_candidate_external_userids(limit=limit))
        if _normalized_text(item)
    ]
    normalized_allowed_owner_userids = {
        _normalized_text(item)
        for item in (allowed_owner_userids or [])
        if _normalized_text(item)
    }
    if normalized_allowed_owner_userids:
        target_external_userids = [
            external_userid
            for external_userid in candidate_external_userids
            if _normalized_text(repo.get_customer_pulse_customer_summary(external_userid).get("owner_userid"))
            in normalized_allowed_owner_userids
        ]
    else:
        target_external_userids = candidate_external_userids
    processed_count = 0
    created_count = 0
    updated_count = 0
    skipped_count = 0
    refreshed_cards: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for external_userid in target_external_userids:
        result = _materialize_customer_pulse(
            external_userid,
            operator=operator,
            tenant_context=resolved_context,
        )
        items.append(result)
        if not result.get("processed"):
            skipped_count += 1
            continue
        processed_count += 1
        if result.get("action") == "created":
            created_count += 1
        elif result.get("action") == "updated":
            updated_count += 1
        else:
            skipped_count += 1
        if result.get("card"):
            refreshed_cards.append(result["card"])
    return {
        "enabled": True,
        "feature_gate": feature_gate,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "processed_count": processed_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "cards": refreshed_cards,
        "items": items,
        "generated_at": _iso_now(),
    }


def enqueue_customer_pulse_recompute(
    *,
    external_userid: str,
    owner_userid: str = "",
    delay_seconds: int = 0,
    operator: str = "",
    trigger_source: str = "",
    trigger_ref_type: str = "",
    trigger_ref_id: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return {"ok": True, "scheduled": False, "reason": "missing_external_userid"}
    if not feature_gate["enabled"]:
        return {"ok": True, "scheduled": False, "reason": "feature_disabled", "enabled": False, "feature_gate": feature_gate}
    now_dt = datetime.now()
    run_after = (now_dt + timedelta(seconds=max(int(delay_seconds or 0), 0))).strftime("%Y-%m-%d %H:%M:%S")
    resolved_owner = _normalized_text(owner_userid) or _normalized_text(
        repo.get_customer_pulse_customer_summary(normalized_external_userid).get("owner_userid")
    )
    payload = {
        "external_userid": normalized_external_userid,
        "owner_userid": resolved_owner,
        "trigger_source": _normalized_text(trigger_source),
        "trigger_ref_type": _normalized_text(trigger_ref_type),
        "trigger_ref_id": _normalized_text(trigger_ref_id),
        "scheduled_by": _normalized_text(operator) or "system",
        "scheduled_at": _iso_now(),
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
    }
    job = repo.upsert_customer_pulse_recompute_job(
        job_type=CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE,
        tenant_key=resolved_tenant_key,
        external_userid=normalized_external_userid,
        owner_userid=resolved_owner,
        run_after=run_after,
        payload=payload,
    )
    return {
        "ok": True,
        "enabled": True,
        "feature_gate": feature_gate,
        "scheduled": bool(job),
        "job": job,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
    }


def run_due_customer_pulse_recompute_jobs(
    *,
    limit: int = 20,
    operator: str = "system",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 20), 200))
    now = _iso_now()
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    due_jobs = repo.list_due_customer_pulse_recompute_jobs(
        job_type=CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE,
        due_at=now,
        tenant_key=resolved_tenant_key,
        owner_userids=allowed_owner_userids,
        limit=normalized_limit,
    )
    summary = {
        "ok": True,
        "limit": normalized_limit,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "scanned_count": len(due_jobs),
        "success_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "items": [],
    }
    for job in due_jobs:
        running_job = repo.mark_customer_pulse_recompute_job_running(int(job["id"]), tenant_key=resolved_tenant_key)
        if not running_job:
            continue
        try:
            result = _materialize_customer_pulse(
                _normalized_text(running_job.get("external_userid")),
                operator=operator,
                tenant_context=resolved_context,
            )
            status = "success" if result.get("processed") else "skipped"
        except Exception as exc:
            status = "failed"
            result = {
                "ok": False,
                "external_userid": _normalized_text(job.get("external_userid")),
                "error": str(exc),
            }
        repo.finish_customer_pulse_recompute_job(
            int(job["id"]),
            status=status,
            result_payload=result,
            tenant_key=resolved_tenant_key,
        )
        if status == "success":
            summary["success_count"] += 1
        elif status == "skipped":
            summary["skipped_count"] += 1
        else:
            summary["failed_count"] += 1
        summary["items"].append({"job_id": int(job["id"]), "status": status, **result})
    return summary


def run_due_customer_pulse_snapshot_job(
    *,
    limit: int = 20,
    rescan_limit: int = 20,
    operator: str = "system",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    queue_result = run_due_customer_pulse_recompute_jobs(
        limit=limit,
        operator=operator,
        tenant_context=resolved_context,
        allowed_owner_userids=allowed_owner_userids,
    )
    refresh_result = refresh_customer_pulse_cards(
        limit=max(1, min(int(rescan_limit or 0), 200)),
        operator=operator,
        tenant_context=resolved_context,
        allowed_owner_userids=allowed_owner_userids,
    )
    return {
        "ok": True,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "queue": queue_result,
        "refresh": refresh_result,
        "generated_at": _iso_now(),
    }


def preview_customer_pulse_card_action(
    card_id: int,
    *,
    action_type: str = "",
    track_click: bool = False,
    metric_source: str = "",
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    requested_action_type = _normalized_text(action_type)
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    presented = _present_card(card, access_context=resolved_context)
    if requested_action_type and not _action_allowed(requested_action_type):
        raise ValueError("当前动作已被系统配置禁用")
    if requested_action_type and customer_pulse_action_permission(requested_action_type):
        assert_customer_pulse_action_permission(requested_action_type, access_context=resolved_context)
    resolved_action_type, action_payload, candidate = _resolve_card_action_candidate(presented, action_type=requested_action_type)
    assert_customer_pulse_action_permission(resolved_action_type, access_context=resolved_context)
    if track_click:
        _record_metric_event(
            event_type="card_clicked",
            event_source=_normalized_text(metric_source) or "customer_pulse_preview",
            card=presented,
            action_type=resolved_action_type,
            operator=_normalized_text(operator),
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"surface": "action_preview"},
        )
    if resolved_action_type == "generate_reply_draft":
        _record_metric_event(
            event_type="draft_preview_started",
            event_source=_normalized_text(metric_source) or "customer_pulse_preview",
            card=presented,
            action_type=resolved_action_type,
            operator=_normalized_text(operator),
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"surface": "action_preview"},
        )
    preview_result = {
        "card_id": presented["id"],
        "external_userid": presented["external_userid"],
        "customer_name": presented["customer_name"],
        "action_type": resolved_action_type,
        "action_label": _action_label(resolved_action_type),
        "action_title": _normalized_text(candidate.get("title")) or _action_label(resolved_action_type),
        "why_now": _normalized_text(candidate.get("why_now") or candidate.get("reason")) or _normalized_text(presented.get("why_now")),
        "need_human_confirmation": True,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "undo_supported": _action_requires_undo_window(resolved_action_type),
        "undo_window_minutes": CUSTOMER_PULSE_UNDO_WINDOW_MINUTES if _action_requires_undo_window(resolved_action_type) else 0,
        "undo_notice": f"执行后 {CUSTOMER_PULSE_UNDO_WINDOW_MINUTES} 分钟内可撤销。"
        if _action_requires_undo_window(resolved_action_type)
        else "",
        "evidence": presented["evidence"],
        "effect_scope": "local_only",
        "preview": {},
    }
    if resolved_action_type == "generate_reply_draft":
        draft_blocked_by_ai = bool(action_payload.get("draft_blocked_by_ai"))
        preview_result["effect_scope"] = "draft_only"
        preview_result["preview"] = {
            "draft_message": ""
            if draft_blocked_by_ai
            else (
                presented["draft_message"]
                or _build_rule_based_draft_message(
                    customer_name=presented["customer_name"],
                    summary=presented["summary"],
                    evidence=presented["evidence"],
                )
            ),
            "channel_type": "existing_customer_channel",
            "auto_send": False,
            "draft_blocked_by_ai": draft_blocked_by_ai,
            "draft_notice": _normalized_text(action_payload.get("draft_notice"))
            or "所有外发消息默认只生成草稿，需人工确认后再发送。",
        }
    elif resolved_action_type == "update_followup_segment":
        followup_segment = _normalized_text(action_payload.get("followup_segment")) or "focus"
        preview_result["effect_scope"] = "marketing_state"
        preview_result["preview"] = {
            "followup_segment": followup_segment,
            "followup_segment_label": _segment_label(followup_segment),
        }
    elif resolved_action_type == "create_followup_task":
        preview_result["preview"] = {
            "task_title": _normalized_text(action_payload.get("task_title")) or _normalized_text(candidate.get("title")) or presented["title"],
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    elif resolved_action_type == "set_followup_reminder":
        preview_result["preview"] = {
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    elif resolved_action_type == "update_tags":
        preview_result["effect_scope"] = "contact_tags"
        preview_result["preview"] = {
            "add_tag_ids": action_payload.get("add_tag_ids") or [],
            "remove_tag_ids": action_payload.get("remove_tag_ids") or [],
        }
    else:
        raise ValueError("unsupported action_type")
    return preview_result


def execute_customer_pulse_card_action(
    card_id: int,
    *,
    action_type: str = "",
    operator: str = "",
    extra_payload: dict[str, Any] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    if not is_customer_pulse_inbox_enabled(access_context=resolved_context):
        raise ValueError("AI推进功能未启用")
    requested_action_type = _normalized_text(action_type)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not card:
        raise LookupError("card not found")
    presented = _present_card(card, access_context=resolved_context)
    if requested_action_type and not _action_allowed(requested_action_type):
        raise ValueError("当前动作已被系统配置禁用")
    if requested_action_type and customer_pulse_action_permission(requested_action_type):
        assert_customer_pulse_action_permission(requested_action_type, access_context=resolved_context)
    resolved_action_type, candidate_payload, candidate = _resolve_card_action_candidate(presented, action_type=requested_action_type)
    assert_customer_pulse_action_permission(resolved_action_type, access_context=resolved_context)
    if not _action_allowed(resolved_action_type):
        raise ValueError("当前动作已被系统配置禁用")
    extra_payload = dict(extra_payload or {})
    action_payload = {**candidate_payload, **extra_payload}
    normalized_operator = _normalized_text(operator) or "crm_console"
    reference_preview = preview_customer_pulse_card_action(
        card_id,
        action_type=resolved_action_type,
        track_click=False,
        tenant_context=resolved_context,
        tenant_key=resolved_tenant_key,
    )
    _assert_action_scope(presented, action_payload)
    normalized_execution_payload = _normalize_action_execution_payload(
        card=presented,
        action_type=resolved_action_type,
        candidate=candidate,
        action_payload=action_payload,
    )
    reference_execution_payload = _normalize_action_execution_payload(
        card=presented,
        action_type=resolved_action_type,
        candidate=candidate,
        action_payload=dict(reference_preview.get("preview") or {}),
    )
    edited_fields = _edited_fields(reference_execution_payload, normalized_execution_payload)
    learning_feedback_type = "edited_then_sent" if edited_fields else "adopted"
    base_execution_labels = _ai_audit_labels_from_candidate(candidate, candidate_payload)
    execution_audit_labels = _execution_audit_labels(base_labels=base_execution_labels, edited_fields=edited_fields)
    unsafe_input_fields = _unsafe_execution_input_fields(resolved_action_type, extra_payload)
    text_guardrail_hits = _draft_execution_guardrail_hits(resolved_action_type, normalized_execution_payload)
    request_payload_with_audit = {
        **normalized_execution_payload,
        "audit": _request_payload_audit_summary(
            action_type=resolved_action_type,
            request_payload=normalized_execution_payload,
            tenant_context=resolved_context,
            operator=normalized_operator,
            card=presented,
            execution_labels=base_execution_labels,
            unsafe_input_fields=unsafe_input_fields,
            text_guardrail_hits=text_guardrail_hits,
        ),
    }
    idempotency_key = _build_action_idempotency_key(card_id, resolved_action_type, normalized_execution_payload)
    existing_log = repo.get_latest_customer_pulse_execution_log_by_idempotency(
        card_id=card_id,
        action_type=resolved_action_type,
        idempotency_key=idempotency_key,
        tenant_key=resolved_tenant_key,
    )
    if existing_log and _normalized_text(existing_log.get("execution_status")) == "confirmed" and not _normalized_text(existing_log.get("undone_at")):
        return _existing_execution_response(
            existing_log,
            card_id=card_id,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )

    execution_key = _execution_key()
    pre_card_snapshot = _card_state_snapshot(presented)
    rollback_payload = _execution_rollback_payload(
        action_type=resolved_action_type,
        pre_card_snapshot=pre_card_snapshot,
        status="pending",
    )
    rollback_payload["resource_id"] = str(card_id)
    execution_log = repo.insert_customer_pulse_execution_log(
        card_id=card_id,
        external_userid=presented["external_userid"],
        action_type=resolved_action_type,
        execution_status="processing",
        channel_type="",
        operator=normalized_operator,
        actor_userid=_normalized_text(resolved_context.get("actor_userid") or resolved_context.get("user_id")),
        actor_role=_normalized_text(resolved_context.get("actor_role") or resolved_context.get("role")),
        resource_type=CUSTOMER_PULSE_RESOURCE_CARD,
        resource_id=str(card_id),
        tenant_key=resolved_tenant_key,
        execution_key=execution_key,
        idempotency_key=idempotency_key,
        request_payload=request_payload_with_audit,
        result_payload={},
        error_message="",
        tenant_context=customer_pulse_tenant_context_summary(resolved_context),
        audit_labels=base_execution_labels,
        rollback_payload=rollback_payload,
    )

    channel_type = ""
    try:
        if unsafe_input_fields:
            raise ValueError(f"检测到未授权字段更新：{', '.join(unsafe_input_fields)}")
        if text_guardrail_hits:
            raise ValueError(f"草稿命中安全风控：{', '.join(text_guardrail_hits)}")
        activity_log_id = 0
        outbound_task_id = 0
        undo_until = _undo_until() if _action_requires_undo_window(resolved_action_type) else ""
        updated_row: dict[str, Any]
        result_payload: dict[str, Any]

        if resolved_action_type == "generate_reply_draft":
            draft_blocked_by_ai = bool(action_payload.get("draft_blocked_by_ai"))
            explicit_draft_message = _normalized_text(normalized_execution_payload.get("draft_message"))
            if draft_blocked_by_ai and not explicit_draft_message:
                raise ValueError("当前 AI 置信度不足或命中风控，请人工编辑草稿后再保存。")
            draft_message = explicit_draft_message or presented["draft_message"] or _build_rule_based_draft_message(
                customer_name=presented["customer_name"],
                summary=presented["summary"],
                evidence=presented["evidence"],
            )
            draft_task = save_local_private_message_draft(
                _reply_draft_task_payload(presented, draft_message, execution_key),
                source=CUSTOMER_PULSE_FLAG_KEY,
            )
            outbound_task_id = int(draft_task.get("task_id") or 0)
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="draft_ready",
                draft_message=draft_message,
                need_human_confirmation=True,
                snooze_until="",
                resolved_at="",
                resolution_note="",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="reply_draft",
                activity_status="draft_ready",
                title="已保存 AI 回复草稿",
                summary=f"已为 {presented['customer_name']} 生成并保存可编辑草稿",
                operator=normalized_operator,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "draft_message": draft_message,
                    "outbound_task_id": outbound_task_id,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "existing_customer_channel"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "draft_message": draft_message,
                "auto_send": False,
                "need_human_confirmation": True,
                "stored_locally": True,
                "copy_text": draft_message,
                "outbound_task_id": outbound_task_id,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "create_followup_task":
            due_at = _normalized_text(normalized_execution_payload.get("due_at")) or _next_followup_time()
            task_title = _normalized_text(normalized_execution_payload.get("task_title")) or _normalized_text(candidate.get("title")) or presented["title"]
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="completed",
                due_at=due_at,
                resolved_at=_iso_now(),
                resolution_note="local_followup_task_created",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="followup_task",
                activity_status="open",
                title=task_title,
                summary=f"AI 建议已落地为跟进任务：{task_title}",
                operator=normalized_operator,
                due_at=due_at,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "task_title": task_title,
                    "due_at": due_at,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "local_task"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "task_title": task_title,
                "due_at": due_at,
                "stored_locally": True,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "update_followup_segment":
            followup_segment = _normalized_text(normalized_execution_payload.get("followup_segment")) or "focus"
            current_marketing_state = repo.get_customer_marketing_state_current(presented["external_userid"]) or {}
            before_followup_segment = _followup_segment_from_marketing_state(current_marketing_state) or "normal"
            marketing_result = customer_pulse_service_runtime.set_manual_followup_segment(
                external_userid=presented["external_userid"],
                followup_segment=followup_segment,
                owner_userid=presented["owner_userid"],
                operator=normalized_operator,
                source="customer_pulse_inbox",
            )
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="completed",
                resolved_at=_iso_now(),
                resolution_note=f"followup_segment:{followup_segment}",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="followup_segment_update",
                activity_status="applied",
                title="已更新跟进阶段",
                summary=f"{_segment_label(before_followup_segment)} -> {_segment_label(followup_segment)}",
                operator=normalized_operator,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "before_followup_segment": before_followup_segment,
                    "after_followup_segment": followup_segment,
                    "marketing_result": marketing_result,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "crm_console_mutation"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "marketing_result": marketing_result,
                "before_followup_segment": before_followup_segment,
                "after_followup_segment": followup_segment,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "update_tags":
            current_tag_rows = repo.list_contact_tag_rows(presented["external_userid"], limit=100)
            current_tag_ids = {
                _normalized_text(item.get("tag_id"))
                for item in current_tag_rows
                if _normalized_text(item.get("userid")) == presented["owner_userid"] and _normalized_text(item.get("tag_id"))
            }
            add_tag_ids = sorted(
                {
                    _normalized_text(item)
                    for item in (normalized_execution_payload.get("add_tag_ids") or [])
                    if _normalized_text(item)
                }
            )
            remove_tag_ids = sorted(
                {
                    _normalized_text(item)
                    for item in (normalized_execution_payload.get("remove_tag_ids") or [])
                    if _normalized_text(item)
                }
            )
            applied_add_tag_ids = [item for item in add_tag_ids if item not in current_tag_ids]
            applied_remove_tag_ids = [item for item in remove_tag_ids if item in current_tag_ids]
            if not applied_add_tag_ids and not applied_remove_tag_ids:
                raise ValueError("当前标签变更已存在，无需重复执行")
            if applied_add_tag_ids:
                customer_pulse_service_runtime.mark_customer_tags(
                    {
                        "userid": presented["owner_userid"],
                        "external_userid": presented["external_userid"],
                        "add_tag": applied_add_tag_ids,
                    }
                )
            if applied_remove_tag_ids:
                customer_pulse_service_runtime.unmark_customer_tags(
                    {
                        "userid": presented["owner_userid"],
                        "external_userid": presented["external_userid"],
                        "remove_tag": applied_remove_tag_ids,
                    }
                )
            after_tag_ids = sorted((current_tag_ids | set(applied_add_tag_ids)) - set(applied_remove_tag_ids))
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="completed",
                resolved_at=_iso_now(),
                resolution_note="customer_tags_updated",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="tag_update",
                activity_status="applied",
                title="已更新客户标签",
                summary=f"新增 {len(applied_add_tag_ids)} 个标签，移除 {len(applied_remove_tag_ids)} 个标签",
                operator=normalized_operator,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "before_tag_ids": sorted(current_tag_ids),
                    "applied_add_tag_ids": applied_add_tag_ids,
                    "applied_remove_tag_ids": applied_remove_tag_ids,
                    "after_tag_ids": after_tag_ids,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "contact_tags"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "applied_add_tag_ids": applied_add_tag_ids,
                "applied_remove_tag_ids": applied_remove_tag_ids,
                "after_tag_ids": after_tag_ids,
                "activity_log_id": activity_log_id,
            }
        elif resolved_action_type == "set_followup_reminder":
            due_at = _normalized_text(normalized_execution_payload.get("due_at")) or _next_followup_time()
            updated_row = repo.update_customer_pulse_card(
                card_id,
                tenant_key=resolved_tenant_key,
                card_status="snoozed",
                due_at=due_at,
                snooze_until=due_at,
                resolution_note="next_followup_reminder_set",
            )
            updated_card = _present_card(updated_row, access_context=resolved_context)
            activity = repo.insert_customer_pulse_activity_log(
                card_id=card_id,
                external_userid=presented["external_userid"],
                owner_userid=presented["owner_userid"],
                activity_type="followup_reminder",
                activity_status="scheduled",
                title="已设置下次跟进提醒",
                summary=f"提醒时间：{due_at}",
                operator=normalized_operator,
                due_at=due_at,
                activity_source=CUSTOMER_PULSE_FLAG_KEY,
                tenant_key=resolved_tenant_key,
                execution_key=execution_key,
                idempotency_key=idempotency_key,
                payload={
                    "due_at": due_at,
                    "card_before": pre_card_snapshot,
                    "card_after": _card_state_snapshot(updated_card),
                },
            )
            activity_log_id = int(activity.get("id") or 0)
            channel_type = "local_reminder"
            result_payload = {
                "card": updated_card,
                "card_before": pre_card_snapshot,
                "due_at": due_at,
                "stored_locally": True,
                "activity_log_id": activity_log_id,
            }
        else:
            raise ValueError("unsupported action_type")

        rollback_payload = _execution_rollback_payload(
            action_type=resolved_action_type,
            pre_card_snapshot=pre_card_snapshot,
            undo_until=undo_until,
            status="available" if undo_until else "completed",
            activity_log_id=activity_log_id,
        )
        rollback_payload["resource_id"] = str(card_id)
        result_payload["audit"] = _result_payload_audit_summary(
            action_type=resolved_action_type,
            card_before=pre_card_snapshot,
            card_after=_card_state_snapshot(updated_card),
            execution_labels=execution_audit_labels,
            edited_fields=edited_fields,
            status="confirmed",
            rollback_payload=rollback_payload,
        )
        result_payload["audit_labels"] = execution_audit_labels
        if resolved_action_type == "generate_reply_draft":
            result_payload["draft_review_status"] = (
                _EXECUTION_AUDIT_HUMAN_EDITED if edited_fields else _EXECUTION_AUDIT_HUMAN_CONFIRMED
            )
        if resolved_action_type in {"update_followup_segment", "update_tags", "set_followup_reminder"}:
            result_payload["safe_field_update_review_status"] = (
                _EXECUTION_AUDIT_HUMAN_EDITED if edited_fields else _EXECUTION_AUDIT_HUMAN_CONFIRMED
            )
        execution_log = repo.update_customer_pulse_execution_log(
            int(execution_log.get("id") or 0),
            tenant_key=resolved_tenant_key,
            execution_status="confirmed",
            channel_type=channel_type,
            activity_log_id=activity_log_id,
            outbound_task_id=outbound_task_id,
            undo_status="available" if undo_until else "",
            undo_until=undo_until,
            result_payload_json=result_payload,
            error_message="",
            audit_labels_json=execution_audit_labels,
            rollback_payload_json=rollback_payload,
        )
        _record_action_feedback(
            card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
            feedback_type=learning_feedback_type,
            feedback_source="action_execution",
            operator=normalized_operator,
            action_type=resolved_action_type,
            execution_log_id=int(execution_log.get("id") or 0),
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={
                "audit_labels": execution_audit_labels,
                "edited_fields": edited_fields,
                "reference_payload": reference_execution_payload,
                "executed_payload": normalized_execution_payload,
            },
        )
        _record_metric_event(
            event_type="action_executed",
            event_source="customer_pulse_execute",
            card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
            execution_log_id=int(execution_log.get("id") or 0),
            action_type=resolved_action_type,
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"edited_fields": edited_fields, "audit_labels": execution_audit_labels},
        )
        metric_type_map = {
            "generate_reply_draft": "draft_confirmed",
            "create_followup_task": "followup_task_created",
            "update_followup_segment": "followup_segment_updated",
        }
        metric_event_type = metric_type_map.get(resolved_action_type)
        if metric_event_type:
            _record_metric_event(
                event_type=metric_event_type,
                event_source="customer_pulse_execute",
                card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
                execution_log_id=int(execution_log.get("id") or 0),
                action_type=resolved_action_type,
                operator=normalized_operator,
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                payload={"edited_fields": edited_fields, "audit_labels": execution_audit_labels},
            )
        _record_metric_event(
            event_type="writeback_success",
            event_source="customer_pulse_execute",
            card=_present_card(repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}, access_context=resolved_context),
            execution_log_id=int(execution_log.get("id") or 0),
            action_type=resolved_action_type,
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )
        return _build_execution_response(
            card_id=card_id,
            action_type=resolved_action_type,
            result_payload=result_payload,
            execution_log=execution_log,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
        )
    except Exception as exc:
        failure_result_payload = {
            "retryable": True,
            "error_message": str(exc),
            "audit": _result_payload_audit_summary(
                action_type=resolved_action_type,
                card_before=pre_card_snapshot,
                card_after={},
                execution_labels=execution_audit_labels,
                edited_fields=edited_fields,
                status="failed",
                error_message=str(exc),
                rollback_payload=rollback_payload,
            ),
            "audit_labels": execution_audit_labels,
            "guardrails": _guardrail_summary(
                execution_labels=execution_audit_labels,
                unsafe_input_fields=unsafe_input_fields,
                text_guardrail_hits=text_guardrail_hits,
                ai_guardrails=((presented.get("snapshot") or {}).get("ai_payload") or {}).get("guardrails")
                if isinstance(((presented.get("snapshot") or {}).get("ai_payload") or {}), dict)
                else {},
            ),
        }
        repo.update_customer_pulse_execution_log(
            int(execution_log.get("id") or 0),
            tenant_key=resolved_tenant_key,
            execution_status="failed",
            channel_type=channel_type,
            result_payload_json=failure_result_payload,
            error_message=str(exc),
            audit_labels_json=execution_audit_labels,
            rollback_payload_json=rollback_payload,
        )
        if unsafe_input_fields or text_guardrail_hits:
            _record_metric_event(
                event_type="guardrail_blocked",
                event_source="customer_pulse_execute",
                card=presented,
                execution_log_id=int(execution_log.get("id") or 0),
                action_type=resolved_action_type,
                operator=normalized_operator,
                tenant_context=resolved_context,
                tenant_key=resolved_tenant_key,
                payload={
                    "unsafe_input_fields": unsafe_input_fields,
                    "text_guardrail_hits": text_guardrail_hits,
                    "error_message": str(exc),
                },
            )
        _record_metric_event(
            event_type="writeback_failed",
            event_source="customer_pulse_execute",
            card=presented,
            execution_log_id=int(execution_log.get("id") or 0),
            action_type=resolved_action_type,
            operator=normalized_operator,
            tenant_context=resolved_context,
            tenant_key=resolved_tenant_key,
            payload={"error_message": str(exc)},
        )
        raise


def undo_customer_pulse_card_action_execution(
    execution_id: int,
    *,
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    feature_gate = customer_pulse_feature_gate_summary(resolved_context)
    if not feature_gate["enabled"]:
        return {
            "key": "customer_pulse",
            "title": "AI推进收件箱",
            "count": 0,
            "description": "当前租户或角色未进入 Customer Pulse 灰度范围。",
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "tone": "ok",
            "items": [],
            "empty_title": "当前未开放 AI 推进灰度",
            "href": "/admin/customer-pulse",
        }
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    execution_log = repo.get_customer_pulse_execution_log(int(execution_id), tenant_key=resolved_tenant_key)
    if not execution_log:
        raise LookupError("execution not found")
    presented_execution = _present_execution_log(execution_log) or {}
    if presented_execution.get("execution_status") != "confirmed":
        raise ValueError("当前执行记录尚未成功，不能撤销")
    if not bool(presented_execution.get("undo_supported")):
        raise ValueError("当前动作不支持撤销")
    if _normalized_text(presented_execution.get("undone_at")):
        raise ValueError("该执行记录已撤销")
    if not bool(presented_execution.get("undo_available")):
        raise ValueError("撤销窗口已过期")
    latest_execution = repo.get_latest_customer_pulse_execution_log(
        int(presented_execution.get("card_id") or 0),
        tenant_key=resolved_tenant_key,
    )
    if latest_execution and int(latest_execution.get("id") or 0) != int(execution_id) and not _normalized_text(latest_execution.get("undone_at")):
        raise ValueError("当前卡片已有更新后的执行记录，不能撤销旧动作")

    normalized_operator = _normalized_text(operator) or "crm_console"
    result_payload = dict(presented_execution.get("result_payload") or {})
    pre_card_snapshot = dict(result_payload.get("card_before") or {})
    if not pre_card_snapshot:
        raise ValueError("缺少撤销所需的原始卡片状态")

    action_type = _normalized_text(presented_execution.get("action_type"))
    assert_customer_pulse_action_permission(action_type, access_context=resolved_context)
    external_userid = _normalized_text(presented_execution.get("external_userid"))
    card_id = int(presented_execution.get("card_id") or 0)
    current_card = repo.get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key)
    if not current_card:
        raise LookupError("card not found")
    presented_card = _present_card(current_card, access_context=resolved_context)
    now = _iso_now()

    if action_type == "generate_reply_draft":
        outbound_task_id = int(presented_execution.get("outbound_task_id") or result_payload.get("outbound_task_id") or 0)
        if outbound_task_id:
            existing_task = customer_pulse_service_runtime.get_outbound_task(outbound_task_id) or {}
            response_payload = _json_loads(existing_task.get("response_payload"), default={})
            if not isinstance(response_payload, dict):
                response_payload = {}
            response_payload.update(
                {
                    "draft_only": True,
                    "cancelled_at": now,
                    "cancelled_by": normalized_operator,
                    "cancel_source": "customer_pulse_undo",
                }
            )
            update_outbound_task_status(outbound_task_id, status="cancelled", response_payload=response_payload)
    elif action_type == "create_followup_task":
        pass
    elif action_type == "update_followup_segment":
        before_followup_segment = _normalized_text(result_payload.get("before_followup_segment"))
        if before_followup_segment not in {"normal", "focus"}:
            raise ValueError("原始跟进阶段不支持撤销")
        customer_pulse_service_runtime.set_manual_followup_segment(
            external_userid=external_userid,
            followup_segment=before_followup_segment,
            owner_userid=presented_card["owner_userid"],
            operator=normalized_operator,
            source="customer_pulse_undo",
        )
    elif action_type == "update_tags":
        applied_add_tag_ids = [
            _normalized_text(item)
            for item in (result_payload.get("applied_add_tag_ids") or [])
            if _normalized_text(item)
        ]
        applied_remove_tag_ids = [
            _normalized_text(item)
            for item in (result_payload.get("applied_remove_tag_ids") or [])
            if _normalized_text(item)
        ]
        if applied_add_tag_ids:
            customer_pulse_service_runtime.unmark_customer_tags(
                {
                    "userid": presented_card["owner_userid"],
                    "external_userid": external_userid,
                    "remove_tag": applied_add_tag_ids,
                }
            )
        if applied_remove_tag_ids:
            customer_pulse_service_runtime.mark_customer_tags(
                {
                    "userid": presented_card["owner_userid"],
                    "external_userid": external_userid,
                    "add_tag": applied_remove_tag_ids,
                }
            )
    elif action_type == "set_followup_reminder":
        pass
    else:
        raise ValueError("unsupported action_type")

    restored_row = _restore_card_state(
        card_id,
        pre_card_snapshot,
        tenant_context=resolved_context,
        tenant_key=resolved_tenant_key,
    )
    activity_log_id = int(presented_execution.get("activity_log_id") or result_payload.get("activity_log_id") or 0)
    if activity_log_id:
        repo.update_customer_pulse_activity_log(
            activity_log_id,
            tenant_key=resolved_tenant_key,
            activity_status="undone",
            undone_at=now,
        )
    undo_activity = repo.insert_customer_pulse_activity_log(
        card_id=card_id,
        external_userid=external_userid,
        owner_userid=presented_card["owner_userid"],
        activity_type="action_undo",
        activity_status="completed",
        title=f"已撤销{_action_label(action_type)}",
        summary=f"已撤销 AI 建议执行：{_action_label(action_type)}",
        operator=normalized_operator,
        activity_source=CUSTOMER_PULSE_FLAG_KEY,
        tenant_key=resolved_tenant_key,
        execution_key=_execution_key(),
        idempotency_key=f"undo-{presented_execution.get('execution_key')}",
        payload={
            "reverted_execution_id": int(execution_id),
            "reverted_action_type": action_type,
            "reverted_activity_log_id": activity_log_id,
        },
    )
    result_payload["undo_activity_log_id"] = int(undo_activity.get("id") or 0)
    result_payload["undone_at"] = now
    result_payload["undone_by"] = normalized_operator
    rollback_payload = dict(presented_execution.get("rollback_payload") or {})
    rollback_payload.update(
        {
            "resource_id": str(card_id),
            "status": "undone",
            "undone_at": now,
            "undo_activity_log_id": int(undo_activity.get("id") or 0),
        }
    )
    result_payload["audit"] = _result_payload_audit_summary(
        action_type=action_type,
        card_before=pre_card_snapshot,
        card_after=_card_state_snapshot(_present_card(restored_row, access_context=resolved_context)),
        execution_labels=[_normalized_text(item) for item in presented_execution.get("audit_labels") or [] if _normalized_text(item)],
        edited_fields=[],
        status="undone",
        rollback_payload=rollback_payload,
    )
    execution_log = repo.update_customer_pulse_execution_log(
        int(execution_id),
        tenant_key=resolved_tenant_key,
        undo_status="undone",
        undone_at=now,
        result_payload_json=result_payload,
        rollback_payload_json=rollback_payload,
    )
    return {
        "ok": True,
        "action_type": action_type,
        "action_label": _action_label(action_type),
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "card": _present_card(restored_row, access_context=resolved_context),
        "execution": _present_execution_log(execution_log),
        "undo_activity": {
            "id": int(undo_activity.get("id") or 0),
            "title": _normalized_text(undo_activity.get("title")),
            "summary": _normalized_text(undo_activity.get("summary")),
            "created_at": _normalized_text(undo_activity.get("created_at")),
        },
    }
