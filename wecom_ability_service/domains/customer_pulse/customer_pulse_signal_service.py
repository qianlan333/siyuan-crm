from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .service import (
    CUSTOMER_PULSE_RULES_VERSION,
    _HIGH_INTENT_MESSAGE_KEYWORDS,
    _HIGH_INTENT_SEGMENTS,
    _HIGH_INTENT_STAGE_KEYS,
    _HIGH_INTENT_TAG_KEYWORDS,
    _NEGATIVE_MESSAGE_KEYWORDS,
    _QUESTION_HINT_KEYWORDS,
    _SAFE_DISPATCH_STATUSES,
    _ai_assist_payload,
    _contains_any_keyword,
    _days_since,
    _followup_segment_from_marketing_state,
    _hours_since,
    _json_loads,
    _known_followup_due_at,
    _make_signal,
    _message_direction,
    _normalized_text,
    _parse_datetime,
    _resolved_tenant_context,
    _resolved_tenant_key,
    _safe_preview,
    _segment_label,
    _stage_label,
    repo,
)

__all__ = [
    "_build_rule_signals",
    "_load_context",
]


def _load_context(
    external_userid: str,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    """Internal owner for customer-pulse signal context assembly."""

    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    summary = repo.get_customer_pulse_customer_summary(external_userid)
    marketing_state = repo.get_customer_marketing_state_current(external_userid) or {}
    value_segment = repo.get_customer_value_segment_current(external_userid) or {}
    class_status = repo.get_class_user_status_current(external_userid) or {}
    owner_binding = repo.get_customer_owner_binding(external_userid) or {}
    reply_row = repo.get_latest_reply_monitor_row(external_userid) or {}
    ai_row = repo.get_latest_ai_output_row(external_userid) or {}
    tag_rows = repo.list_contact_tag_rows(external_userid, limit=20)
    messages = repo.list_recent_archived_message_rows(external_userid, limit=20)
    questionnaire_rows = repo.list_recent_questionnaire_rows(external_userid, limit=5)
    dispatch_rows = repo.list_recent_conversion_dispatch_rows(external_userid, limit=5)
    latest_snapshot = repo.get_latest_customer_pulse_snapshot_for_external_userid(
        external_userid,
        tenant_key=resolved_tenant_key,
    ) or {}
    existing_card = repo.get_latest_customer_pulse_card_for_external_userid(
        external_userid,
        tenant_key=resolved_tenant_key,
    ) or {}
    ai_assist = _ai_assist_payload(ai_row)
    return {
        "summary": summary,
        "marketing_state": marketing_state,
        "value_segment": value_segment,
        "class_status": class_status,
        "owner_binding": owner_binding,
        "reply_row": reply_row,
        "ai_row": ai_row,
        "ai_assist": ai_assist,
        "tag_rows": tag_rows,
        "messages": messages,
        "questionnaire_rows": questionnaire_rows,
        "dispatch_rows": dispatch_rows,
        "latest_snapshot": latest_snapshot,
        "existing_card": existing_card,
        "tenant_key": resolved_tenant_key,
        "tenant_context": resolved_context,
    }


def _build_rule_signals(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Internal owner for customer-pulse signal synthesis."""

    summary = context["summary"]
    marketing_state = context["marketing_state"]
    value_segment = context["value_segment"]
    class_status = context["class_status"]
    owner_binding = context["owner_binding"]
    reply_row = context["reply_row"]
    tag_rows = context["tag_rows"]
    messages = context["messages"]
    questionnaire_rows = context["questionnaire_rows"]
    dispatch_rows = context["dispatch_rows"]
    existing_card = context["existing_card"]

    tenant_key = _resolved_tenant_key(
        tenant_context=context.get("tenant_context"),
        tenant_key=_normalized_text(context.get("tenant_key")),
    )
    external_userid = _normalized_text(summary.get("external_userid"))
    owner_userid = _normalized_text(summary.get("owner_userid"))
    stage_key = "/".join(
        part
        for part in [
            _normalized_text(marketing_state.get("main_stage")),
            _normalized_text(marketing_state.get("sub_stage")),
        ]
        if part
    )
    value_segment_name = _normalized_text(value_segment.get("segment")).lower()
    current_followup_segment = _followup_segment_from_marketing_state(marketing_state)

    inbound_messages = [row for row in messages if _message_direction(row, external_userid=external_userid) == "inbound"]
    outbound_messages = [row for row in messages if _message_direction(row, external_userid=external_userid) == "outbound"]
    latest_inbound = inbound_messages[0] if inbound_messages else {}
    latest_outbound = outbound_messages[0] if outbound_messages else {}
    last_interaction_at = _normalized_text((messages[0] if messages else {}).get("send_time"))
    last_inbound_at = _normalized_text(latest_inbound.get("send_time"))
    last_outbound_at = _normalized_text(latest_outbound.get("send_time"))
    known_followup_due_at = _known_followup_due_at(marketing_state, existing_card)

    signals: list[dict[str, Any]] = []

    reply_status = _normalized_text(reply_row.get("status")).lower()
    reply_snapshot = _json_loads(reply_row.get("payload_snapshot_json"), default={})
    if not isinstance(reply_snapshot, dict):
        reply_snapshot = {}
    waiting_hours = _hours_since(reply_row.get("last_inbound_at") or reply_row.get("updated_at") or reply_row.get("created_at"))
    if reply_row and reply_status not in {"done", "resolved", "completed", "cancelled"}:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="unanswered_question",
                signal_source="automation_reply_monitor_queue",
                score=36 if (waiting_hours or 0) < 24 else 42,
                summary="客户存在未处理问题，当前应优先给出可确认的回复草稿。",
                source_ref_type="automation_reply_monitor_queue",
                source_ref_id=_normalized_text(reply_row.get("id")),
                source_updated_at=_normalized_text(reply_row.get("updated_at") or reply_row.get("created_at")),
                payload={
                    "reply_queue_status": reply_status or "pending",
                    "waiting_hours": round(float(waiting_hours or 0), 1),
                    "message_count": int(reply_row.get("message_count") or 0),
                    "not_before": _normalized_text(reply_row.get("not_before")),
                },
                evidence=[
                    {
                        "title": "待回复窗口",
                        "detail": _safe_preview(
                            reply_snapshot.get("latest_inbound_summary")
                            or reply_snapshot.get("last_message_summary")
                            or latest_inbound.get("content")
                            or "客户有待回复消息"
                        ),
                        "event_time": _normalized_text(reply_row.get("last_inbound_at") or reply_row.get("updated_at")),
                        "source": "automation_reply_monitor_queue",
                    }
                ],
                flag_bucket="risk",
                flag_key="unanswered_question",
                flag_label="存在未回复问题",
            )
        )
    elif latest_inbound:
        latest_inbound_time = _parse_datetime(latest_inbound.get("send_time"))
        latest_outbound_time = _parse_datetime(latest_outbound.get("send_time"))
        latest_inbound_content = _normalized_text(latest_inbound.get("content"))
        if (
            latest_inbound_time
            and latest_inbound_time >= datetime.now() - timedelta(hours=72)
            and (not latest_outbound_time or latest_inbound_time > latest_outbound_time)
            and _contains_any_keyword(latest_inbound_content, _QUESTION_HINT_KEYWORDS)
        ):
            signals.append(
                _make_signal(
                    tenant_key=tenant_key,
                    external_userid=external_userid,
                    owner_userid=owner_userid,
                    signal_type="unanswered_question",
                    signal_source="archived_messages",
                    score=30,
                    summary="最近一轮客户提问后尚未形成有效回复，建议先处理这条对话。",
                    source_ref_type="archived_messages",
                    source_ref_id=_normalized_text(latest_inbound.get("id") or latest_inbound.get("msgid")),
                    source_updated_at=_normalized_text(latest_inbound.get("send_time")),
                    payload={
                        "waiting_hours": round(float(_hours_since(latest_inbound.get("send_time")) or 0), 1),
                    },
                    evidence=[
                        {
                            "title": "最近一条客户消息",
                            "detail": _safe_preview(latest_inbound_content),
                            "event_time": _normalized_text(latest_inbound.get("send_time")),
                            "source": "archived_messages",
                        }
                    ],
                    flag_bucket="risk",
                    flag_key="unanswered_question",
                    flag_label="存在未回复问题",
                )
            )

    negative_message = next(
        (
            row
            for row in inbound_messages
            if _contains_any_keyword(row.get("content"), _NEGATIVE_MESSAGE_KEYWORDS)
            and (_parse_datetime(row.get("send_time")) or datetime.min) >= datetime.now() - timedelta(days=7)
        ),
        {},
    )
    if negative_message:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="negative_sentiment",
                signal_source="archived_messages",
                score=28,
                summary="客户近期表达了负向情绪或投诉倾向，建议先人工介入。",
                source_ref_type="archived_messages",
                source_ref_id=_normalized_text(negative_message.get("id") or negative_message.get("msgid")),
                source_updated_at=_normalized_text(negative_message.get("send_time")),
                payload={"matched_keywords": [item for item in _NEGATIVE_MESSAGE_KEYWORDS if item in _normalized_text(negative_message.get("content"))]},
                evidence=[
                    {
                        "title": "近期负向表达",
                        "detail": _safe_preview(negative_message.get("content")),
                        "event_time": _normalized_text(negative_message.get("send_time")),
                        "source": "archived_messages",
                    }
                ],
                flag_bucket="risk",
                flag_key="negative_sentiment",
                flag_label="近期负向情绪/投诉",
            )
        )

    latest_questionnaire = questionnaire_rows[0] if questionnaire_rows else {}
    questionnaire_status = _normalized_text(latest_questionnaire.get("scrm_apply_status")).lower()
    questionnaire_error = _normalized_text(latest_questionnaire.get("scrm_apply_error"))
    latest_dispatch = dispatch_rows[0] if dispatch_rows else {}
    dispatch_status = _normalized_text(latest_dispatch.get("dispatch_status")).lower()
    dispatch_age_hours = _hours_since(
        latest_dispatch.get("dispatched_at") or latest_dispatch.get("updated_at") or latest_dispatch.get("created_at")
    )
    class_sync_status = _normalized_text(class_status.get("wecom_tag_sync_status")).lower()
    service_exception_evidence: list[dict[str, Any]] = []
    service_exception_payload: dict[str, Any] = {}
    if questionnaire_status in {"failed", "error"} or questionnaire_error:
        service_exception_payload["questionnaire_apply_status"] = questionnaire_status or "failed"
        service_exception_payload["questionnaire_apply_error"] = questionnaire_error
        service_exception_evidence.append(
            {
                "title": "问卷结果回写异常",
                "detail": questionnaire_error or f"状态 {questionnaire_status}",
                "event_time": _normalized_text(latest_questionnaire.get("scrm_apply_at") or latest_questionnaire.get("submitted_at")),
                "source": "questionnaire_scrm_apply_logs",
            }
        )
    if dispatch_status not in _SAFE_DISPATCH_STATUSES and dispatch_status:
        service_exception_payload["dispatch_status"] = dispatch_status
        service_exception_evidence.append(
            {
                "title": "转化派发异常",
                "detail": _normalized_text(latest_dispatch.get("dispatch_note")) or f"状态 {dispatch_status}",
                "event_time": _normalized_text(latest_dispatch.get("updated_at") or latest_dispatch.get("created_at")),
                "source": "conversion_dispatch_log",
            }
        )
    elif dispatch_status in {"pending", "blocked_quiet_hours"} and (dispatch_age_hours or 0) >= 24:
        service_exception_payload["dispatch_status"] = dispatch_status
        service_exception_payload["dispatch_wait_hours"] = round(float(dispatch_age_hours or 0), 1)
        service_exception_evidence.append(
            {
                "title": "转化派发停留过久",
                "detail": f"状态 {dispatch_status} · 已等待 {round(float(dispatch_age_hours or 0), 1)} 小时",
                "event_time": _normalized_text(latest_dispatch.get("updated_at") or latest_dispatch.get("created_at")),
                "source": "conversion_dispatch_log",
            }
        )
    if class_sync_status == "failed":
        service_exception_payload["tag_sync_status"] = class_sync_status
        service_exception_payload["tag_sync_error"] = _normalized_text(class_status.get("wecom_tag_sync_error"))
        service_exception_evidence.append(
            {
                "title": "标签同步异常",
                "detail": _normalized_text(class_status.get("wecom_tag_sync_error")) or "报名/班级状态标签同步失败",
                "event_time": _normalized_text(class_status.get("updated_at") or class_status.get("set_at")),
                "source": "class_user_status_current",
            }
        )
    if service_exception_evidence:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="service_exception",
                signal_source=service_exception_evidence[0]["source"],
                score=24,
                summary="客户最近存在服务或派发异常，建议先人工确认并补动作。",
                source_ref_type=service_exception_evidence[0]["source"],
                source_ref_id=_normalized_text(
                    latest_questionnaire.get("id") or latest_dispatch.get("id") or class_status.get("external_userid")
                ),
                source_updated_at=_normalized_text(
                    latest_questionnaire.get("scrm_apply_at")
                    or latest_dispatch.get("updated_at")
                    or class_status.get("updated_at")
                    or latest_questionnaire.get("submitted_at")
                ),
                payload=service_exception_payload,
                evidence=service_exception_evidence,
                flag_bucket="risk",
                flag_key="service_exception",
                flag_label="订单/服务异常",
            )
        )

    detail_parts = []
    if stage_key:
        detail_parts.append(_stage_label(marketing_state.get("main_stage"), marketing_state.get("sub_stage")))
    if value_segment_name:
        detail_parts.append(f"价值分层 {_segment_label(value_segment_name)}")
    if value_segment_name in _HIGH_INTENT_SEGMENTS or stage_key in _HIGH_INTENT_STAGE_KEYS:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="high_intent_stage",
                signal_source="customer_marketing_state_current",
                score=18,
                summary="客户处于高优先级推进段，今天的推进收益更高。",
                source_ref_type="customer_marketing_state_current",
                source_ref_id=_normalized_text(marketing_state.get("id") or value_segment.get("id")),
                source_updated_at=_normalized_text(marketing_state.get("updated_at") or value_segment.get("updated_at")),
                payload={
                    "main_stage": _normalized_text(marketing_state.get("main_stage")),
                    "sub_stage": _normalized_text(marketing_state.get("sub_stage")),
                    "segment": value_segment_name,
                    "current_followup_segment": current_followup_segment,
                },
                evidence=[
                    {
                        "title": "当前推进阶段",
                        "detail": " · ".join(detail_parts) or "命中高意向阶段规则",
                        "event_time": _normalized_text(marketing_state.get("updated_at") or value_segment.get("updated_at")),
                        "source": "customer_marketing_state_current",
                    }
                ],
                flag_bucket="opportunity",
                flag_key="high_intent_stage",
                flag_label="高意向阶段",
            )
        )

    high_intent_tags = [
        _normalized_text(item.get("tag_name") or item.get("tag_id"))
        for item in tag_rows
        if any(keyword in _normalized_text(item.get("tag_name") or item.get("tag_id")) for keyword in _HIGH_INTENT_TAG_KEYWORDS)
    ]
    if high_intent_tags:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="high_intent_tag",
                signal_source="contact_tags",
                score=10,
                summary="客户标签显示当前仍需推进，可直接复用到行动卡解释。",
                source_ref_type="contact_tags",
                source_ref_id="",
                source_updated_at=_normalized_text((tag_rows[0] if tag_rows else {}).get("created_at")),
                payload={"tag_names": high_intent_tags},
                evidence=[
                    {
                        "title": "命中客户标签",
                        "detail": "、".join(high_intent_tags[:3]),
                        "event_time": _normalized_text((tag_rows[0] if tag_rows else {}).get("created_at")),
                        "source": "contact_tags",
                    }
                ],
                flag_bucket="opportunity",
                flag_key="high_intent_tag",
                flag_label="高意向标签",
            )
        )

    high_intent_message = next(
        (
            row
            for row in inbound_messages
            if _contains_any_keyword(row.get("content"), _HIGH_INTENT_MESSAGE_KEYWORDS)
            and (_parse_datetime(row.get("send_time")) or datetime.min) >= datetime.now() - timedelta(days=7)
        ),
        {},
    )
    latest_questionnaire_time = _parse_datetime(latest_questionnaire.get("submitted_at"))
    if high_intent_message or (
        latest_questionnaire
        and latest_questionnaire_time
        and latest_questionnaire_time >= datetime.now() - timedelta(days=7)
    ):
        evidence: list[dict[str, Any]] = []
        if high_intent_message:
            evidence.append(
                {
                    "title": "近期高意向表达",
                    "detail": _safe_preview(high_intent_message.get("content")),
                    "event_time": _normalized_text(high_intent_message.get("send_time")),
                    "source": "archived_messages",
                }
            )
        if latest_questionnaire:
            evidence.append(
                {
                    "title": "近期问卷提交",
                    "detail": f"{_normalized_text(latest_questionnaire.get('questionnaire_title') or latest_questionnaire.get('questionnaire_name')) or '问卷'} · score={latest_questionnaire.get('total_score') or 0}",
                    "event_time": _normalized_text(latest_questionnaire.get("submitted_at")),
                    "source": "questionnaire_submissions",
                }
            )
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="high_intent_behavior",
                signal_source="archived_messages" if high_intent_message else "questionnaire_submissions",
                score=16,
                summary="客户最近出现高意向行为，今天处理更容易推动下一步。",
                source_ref_type="archived_messages" if high_intent_message else "questionnaire_submissions",
                source_ref_id=_normalized_text(high_intent_message.get("id") or latest_questionnaire.get("id")),
                source_updated_at=_normalized_text(high_intent_message.get("send_time") or latest_questionnaire.get("submitted_at")),
                payload={
                    "questionnaire_score": latest_questionnaire.get("total_score"),
                    "has_high_intent_message": bool(high_intent_message),
                },
                evidence=evidence,
                flag_bucket="opportunity",
                flag_key="high_intent_behavior",
                flag_label="近期高意向行为",
            )
        )

    stage_anchor = (
        _normalized_text(marketing_state.get("entered_at"))
        or _normalized_text(marketing_state.get("updated_at"))
        or _normalized_text(marketing_state.get("last_message_at"))
    )
    stage_stalled_days = _days_since(stage_anchor)
    if stage_stalled_days is not None and stage_stalled_days >= 3 and stage_key != "converted/enrolled":
        points = 12 if stage_stalled_days < 7 else 20 if stage_stalled_days < 14 else 28
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="stage_stalled",
                signal_source="customer_marketing_state_current",
                score=points,
                summary=f"客户在当前阶段已停留 {stage_stalled_days} 天，推进节奏明显变慢。",
                source_ref_type="customer_marketing_state_current",
                source_ref_id=_normalized_text(marketing_state.get("id")),
                source_updated_at=_normalized_text(marketing_state.get("updated_at") or stage_anchor),
                payload={
                    "stage_stalled_days": stage_stalled_days,
                    "stage_key": stage_key,
                },
                evidence=[
                    {
                        "title": "阶段停滞",
                        "detail": f"{_stage_label(marketing_state.get('main_stage'), marketing_state.get('sub_stage'))} 已停留 {stage_stalled_days} 天",
                        "event_time": stage_anchor,
                        "source": "customer_marketing_state_current",
                    }
                ],
                flag_bucket="risk",
                flag_key="stage_stalled",
                flag_label="阶段停滞",
            )
        )

    if not known_followup_due_at and (
        any(item["signal_type"] == "high_intent_stage" for item in signals)
        or any(item["signal_type"] == "stage_stalled" for item in signals)
        or any(item["signal_type"] == "unanswered_question" for item in signals)
    ):
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="missing_followup_time",
                signal_source="customer_marketing_state_current",
                score=14,
                summary="当前客户没有明确的下一次跟进时间，容易继续停滞。",
                source_ref_type="customer_marketing_state_current",
                source_ref_id=_normalized_text(marketing_state.get("id") or existing_card.get("id")),
                source_updated_at=_normalized_text(marketing_state.get("updated_at") or existing_card.get("updated_at")),
                payload={"known_followup_due_at": known_followup_due_at},
                evidence=[
                    {
                        "title": "缺少下次跟进时间",
                        "detail": "营销状态与现有行动卡中都没有明确的下一次跟进时间",
                        "event_time": _normalized_text(marketing_state.get("updated_at") or existing_card.get("updated_at")),
                        "source": "customer_marketing_state_current",
                    }
                ],
                flag_bucket="risk",
                flag_key="missing_followup_time",
                flag_label="缺少下次跟进时间",
            )
        )

    interaction_gap_days = _days_since(last_interaction_at)
    if (
        interaction_gap_days is not None
        and interaction_gap_days >= 7
        and (
            value_segment_name in _HIGH_INTENT_SEGMENTS
            or stage_key in _HIGH_INTENT_STAGE_KEYS
            or bool(marketing_state.get("eligible_for_conversion"))
        )
    ):
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="interaction_stale",
                signal_source="archived_messages",
                score=12,
                summary=f"最近 {interaction_gap_days} 天没有新的有效互动，客户可能正在流失。",
                source_ref_type="archived_messages",
                source_ref_id=_normalized_text((messages[0] if messages else {}).get("id")),
                source_updated_at=last_interaction_at,
                payload={"interaction_gap_days": interaction_gap_days},
                evidence=[
                    {
                        "title": "最近互动时间",
                        "detail": last_interaction_at or "暂无消息记录",
                        "event_time": last_interaction_at,
                        "source": "archived_messages",
                    }
                ],
                flag_bucket="risk",
                flag_key="interaction_stale",
                flag_label="最近互动间隔过长",
            )
        )

    if interaction_gap_days is not None and interaction_gap_days <= 1 and (
        value_segment_name in _HIGH_INTENT_SEGMENTS or any(item["signal_type"] == "unanswered_question" for item in signals)
    ):
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="recent_engagement",
                signal_source="archived_messages",
                score=8,
                summary="客户最近 24 小时内仍在互动，及时处理更容易转成下一步动作。",
                source_ref_type="archived_messages",
                source_ref_id=_normalized_text((messages[0] if messages else {}).get("id")),
                source_updated_at=last_interaction_at,
                payload={"last_interaction_at": last_interaction_at},
                evidence=[
                    {
                        "title": "最近互动",
                        "detail": _safe_preview((messages[0] if messages else {}).get("content")),
                        "event_time": last_interaction_at,
                        "source": "archived_messages",
                    }
                ],
                flag_bucket="opportunity",
                flag_key="recent_engagement",
                flag_label="最近仍有互动",
            )
        )

    owner_change_days = _days_since(owner_binding.get("updated_at") or summary.get("binding_updated_at"))
    first_owner = _normalized_text(owner_binding.get("first_owner_userid") or summary.get("first_owner_userid"))
    last_owner = _normalized_text(owner_binding.get("last_owner_userid") or summary.get("last_owner_userid"))
    if first_owner and last_owner and first_owner != last_owner and owner_change_days is not None and owner_change_days <= 14:
        signals.append(
            _make_signal(
                tenant_key=tenant_key,
                external_userid=external_userid,
                owner_userid=owner_userid,
                signal_type="owner_changed_recently",
                signal_source="external_contact_bindings",
                score=8,
                summary="客户负责人近期发生变更，交接阶段容易漏掉跟进动作。",
                source_ref_type="external_contact_bindings",
                source_ref_id=external_userid,
                source_updated_at=_normalized_text(owner_binding.get("updated_at") or summary.get("binding_updated_at")),
                payload={
                    "first_owner_userid": first_owner,
                    "last_owner_userid": last_owner,
                    "owner_change_days": owner_change_days,
                },
                evidence=[
                    {
                        "title": "负责人变更",
                        "detail": f"{first_owner} -> {last_owner}",
                        "event_time": _normalized_text(owner_binding.get("updated_at") or summary.get("binding_updated_at")),
                        "source": "external_contact_bindings",
                    }
                ],
                flag_bucket="risk",
                flag_key="owner_changed_recently",
                flag_label="负责人近期变更",
            )
        )

    metrics = {
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "last_interaction_at": last_interaction_at,
        "last_inbound_at": last_inbound_at,
        "last_outbound_at": last_outbound_at,
        "interaction_gap_days": interaction_gap_days,
        "stage_stalled_days": stage_stalled_days,
        "known_followup_due_at": known_followup_due_at,
        "current_followup_segment": current_followup_segment,
        "stage_key": stage_key,
        "value_segment": value_segment_name,
    }
    return signals, metrics
