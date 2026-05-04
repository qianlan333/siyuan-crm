from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ..customer_timeline.service import _get_customer_timeline_impl
from ..infra.settings import get_setting
from .repo import (
    fetch_customer_marketing_state_current,
    fetch_customer_value_segment_current,
    list_customer_agent_output_rows,
)

CUSTOMER_PULSE_FLAG_KEY = "ai_customer_pulse"
CUSTOMER_PULSE_MIN_CONFIDENCE = 0.75
CUSTOMER_PULSE_TIMELINE_LIMIT = 6
CUSTOMER_PULSE_AGENT_OUTPUT_LIMIT = 6

_HIGH_INTENT_SEGMENTS = {"focus", "top"}
_AI_OUTPUT_TYPES = {"next_action_suggestion", "agent_reply_draft", "agent_reply_final"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _setting_bool(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _display_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return round(confidence, 4)


def _safe_preview_text(value: Any, *, max_length: int = 60) -> str:
    text = _normalized_text(value)
    if not text:
        return ""
    if len(text) > max_length:
        return f"{text[:max_length]}..."
    return text


def _timeline_payload(external_userid: str) -> dict[str, Any]:
    timeline = _get_customer_timeline_impl(
        external_userid,
        {
            "normalized_limit": CUSTOMER_PULSE_TIMELINE_LIMIT,
            "normalized_offset": 0,
            "limit": CUSTOMER_PULSE_TIMELINE_LIMIT,
            "offset": 0,
            "event_type": "",
        },
    )
    return timeline or {
        "external_userid": external_userid,
        "items": [],
        "count": 0,
        "limit": CUSTOMER_PULSE_TIMELINE_LIMIT,
        "offset": 0,
        "filters": {"event_type": "", "limit": str(CUSTOMER_PULSE_TIMELINE_LIMIT), "offset": "0"},
        "total": 0,
    }


def _base_payload(*, enabled: bool) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "visible": False,
        "source": "",
        "source_label": "",
        "status": "hidden",
        "status_label": "暂不展示",
        "summary": "",
        "next_action": "",
        "confidence": None,
        "need_human_confirmation": True,
        "need_human_review": True,
        "draft_message": "",
        "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "evidence": [],
        "generated_at": "",
        "matched_output_id": "",
        "agent_code": "",
        "output_type": "",
        "degraded_from_ai": False,
        "degraded_reason": "",
        "hidden_reason": "",
    }


def _timeline_evidence_items(timeline: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in timeline.get("items") or []:
        title = _normalized_text(item.get("title")) or _normalized_text(item.get("event_type")) or "时间线事件"
        detail = _safe_preview_text(item.get("summary"))
        if not detail:
            continue
        evidence.append(
            {
                "title": title,
                "detail": detail,
                "event_type": _normalized_text(item.get("event_type")),
                "event_time": _normalized_text(item.get("event_time") or item.get("occurred_at")),
                "source": "timeline",
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def _run_message_evidence_items(messages: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    evidence: list[dict[str, Any]] = []
    for item in messages:
        if isinstance(item, dict):
            text = _safe_preview_text(item.get("content") or item.get("text") or item.get("summary"))
            event_time = _normalized_text(item.get("send_time") or item.get("created_at"))
        else:
            text = _safe_preview_text(item)
            event_time = ""
        if not text:
            continue
        evidence.append(
            {
                "title": "最近对话",
                "detail": text,
                "event_type": "message",
                "event_time": event_time,
                "source": "agent_input",
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def _marketing_evidence_item(marketing_state: dict[str, Any], value_segment: dict[str, Any]) -> dict[str, Any] | None:
    main_stage = _normalized_text(marketing_state.get("main_stage"))
    sub_stage = _normalized_text(marketing_state.get("sub_stage"))
    segment = _normalized_text(value_segment.get("segment"))
    score = value_segment.get("score")
    if not any([main_stage, sub_stage, segment]):
        return None
    detail = []
    if main_stage or sub_stage:
        detail.append("/".join(part for part in [main_stage, sub_stage] if part) or "unknown")
    if segment:
        detail.append(f"segment={segment}")
    if score not in (None, ""):
        detail.append(f"score={score}")
    return {
        "title": "当前营销状态",
        "detail": " · ".join(detail),
        "event_type": "marketing_state",
        "event_time": _normalized_text(marketing_state.get("updated_at")),
        "source": "marketing_state_current",
    }


def _dedupe_evidence(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            _normalized_text(item.get("title")),
            _normalized_text(item.get("detail")),
            _normalized_text(item.get("event_time")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _next_action_label(value: Any, *, target_pool: str = "") -> str:
    normalized = _normalized_text(value)
    mapping = {
        "followup": "继续人工跟进",
        "clarify_need": "先确认客户真实需求",
        "schedule_call": "优先约沟通 / 约演示",
        "send_proof": "补充案例与证据",
        "quote_explain": "解释价格与方案",
        "generate_reply_draft": "生成回复草稿",
        "create_followup_task": "创建跟进任务",
        "update_followup_segment": "更新跟进阶段",
        "update_tags": "更新客户标签",
        "set_followup_reminder": "设置下次跟进提醒",
    }
    if normalized in mapping:
        return mapping[normalized]
    if normalized:
        return normalized
    if _normalized_text(target_pool):
        return f"关注目标池：{_normalized_text(target_pool)}"
    return "人工确认后决定下一步"


def _select_draft_message(output_type: str, normalized_output: dict[str, Any], rendered_output_text: str) -> str:
    draft_reply = _normalized_text(normalized_output.get("draft_reply") or normalized_output.get("draftText"))
    if draft_reply:
        return draft_reply
    if output_type in {"agent_reply_draft", "agent_reply_final"}:
        return _normalized_text(rendered_output_text)
    return ""


def _ai_candidate_payload(
    row: dict[str, Any],
    *,
    timeline: dict[str, Any],
    marketing_state: dict[str, Any],
    value_segment: dict[str, Any],
) -> dict[str, Any] | None:
    output_type = _normalized_text(row.get("output_type"))
    if output_type not in _AI_OUTPUT_TYPES:
        return None
    normalized_output = _json_loads(row.get("normalized_output_json"), default={})
    if not isinstance(normalized_output, dict):
        normalized_output = {}
    confidence = _display_confidence(row.get("confidence", normalized_output.get("confidence")))
    if confidence is None or confidence < CUSTOMER_PULSE_MIN_CONFIDENCE:
        return None

    run_input = _json_loads(row.get("input_snapshot_json"), default={})
    if not isinstance(run_input, dict):
        run_input = {}

    evidence = _run_message_evidence_items(
        run_input.get("messages") or run_input.get("recent_messages") or run_input.get("newmessages"),
        limit=2,
    )
    evidence.extend(_timeline_evidence_items(timeline, limit=2))
    marketing_evidence = _marketing_evidence_item(marketing_state, value_segment)
    if marketing_evidence:
        evidence.append(marketing_evidence)
    evidence = _dedupe_evidence(evidence, limit=4)
    if not evidence:
        return None

    summary = (
        _normalized_text(row.get("reason"))
        or _normalized_text(normalized_output.get("reason"))
        or _normalized_text(normalized_output.get("summary"))
        or _normalized_text(normalized_output.get("whyNow"))
        or "已有 AI 判断，可供人工参考。"
    )
    next_action = _next_action_label(
        normalized_output.get("next_action") or normalized_output.get("actionType"),
        target_pool=_normalized_text(row.get("target_pool")),
    )
    draft_message = _select_draft_message(output_type, normalized_output, _normalized_text(row.get("rendered_output_text")))
    need_human_review = bool(row.get("need_human_review")) or bool(normalized_output.get("need_human_review"))
    return {
        "enabled": True,
        "visible": True,
        "source": "ai_output",
        "source_label": "AI 建议",
        "status": "ai_ready",
        "status_label": "AI 草稿待人工确认" if draft_message else "AI 建议待人工确认",
        "summary": summary,
        "next_action": next_action,
        "confidence": confidence,
        "need_human_confirmation": True,
        "need_human_review": need_human_review or bool(draft_message),
        "draft_message": draft_message,
        "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "evidence": evidence,
        "generated_at": _normalized_text(row.get("created_at") or row.get("run_created_at")),
        "matched_output_id": _normalized_text(row.get("output_id")),
        "agent_code": _normalized_text(row.get("agent_code")),
        "output_type": output_type,
        "degraded_from_ai": False,
        "degraded_reason": "",
        "hidden_reason": "",
    }


def _recent_message_within_hours(timeline: dict[str, Any], *, hours: int) -> bool:
    deadline = datetime.now() - timedelta(hours=hours)
    for item in timeline.get("items") or []:
        if _normalized_text(item.get("event_type")) != "message":
            continue
        event_time = _parse_datetime(item.get("event_time") or item.get("occurred_at"))
        if event_time and event_time >= deadline:
            return True
    return False


def _rule_based_payload(
    *,
    timeline: dict[str, Any],
    marketing_state: dict[str, Any],
    value_segment: dict[str, Any],
    degraded_from_ai: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _base_payload(enabled=True)
    segment = _normalized_text(value_segment.get("segment"))
    main_stage = _normalized_text(marketing_state.get("main_stage"))
    sub_stage = _normalized_text(marketing_state.get("sub_stage"))
    eligible = bool(marketing_state.get("eligible_for_conversion"))

    evidence = _timeline_evidence_items(timeline, limit=3)
    marketing_evidence = _marketing_evidence_item(marketing_state, value_segment)
    if marketing_evidence:
        evidence.append(marketing_evidence)
    evidence = _dedupe_evidence(evidence, limit=4)
    if not evidence:
        payload["hidden_reason"] = "insufficient_evidence"
        return payload

    payload.update(
        {
            "visible": True,
            "source": "rule_suggestion",
            "source_label": "规则建议",
            "status": "rule_ready",
            "status_label": "规则建议待人工判断",
            "need_human_confirmation": True,
            "need_human_review": True,
            "draft_message": "",
            "evidence": evidence,
            "generated_at": _normalized_text(evidence[0].get("event_time")),
        }
    )
    if degraded_from_ai:
        payload["degraded_from_ai"] = True
        payload["degraded_reason"] = "low_confidence"
        payload["confidence"] = _display_confidence(degraded_from_ai.get("confidence"))
        payload["matched_output_id"] = _normalized_text(degraded_from_ai.get("output_id"))
        payload["agent_code"] = _normalized_text(degraded_from_ai.get("agent_code"))
        payload["output_type"] = _normalized_text(degraded_from_ai.get("output_type"))

    if main_stage == "converted" or sub_stage == "enrolled":
        payload["summary"] = "客户已人工确认成交，当前不建议再生成外发话术。"
        payload["next_action"] = "无需外发，如需服务跟进请人工单独处理。"
        payload["status_label"] = "已成交，仅保留规则提示"
        return payload

    if segment in _HIGH_INTENT_SEGMENTS or eligible:
        payload["summary"] = "客户当前处于高优先级跟进段，建议负责人先人工确认需求，再决定是否采用草稿。"
        payload["next_action"] = "优先人工确认当前问题与成交意愿。"
        return payload

    if _recent_message_within_hours(timeline, hours=72):
        payload["summary"] = "客户最近 72 小时内有互动，建议先基于最近对话做人工跟进。"
        payload["next_action"] = "围绕最近一条有效对话人工回复。"
        return payload

    if any(_normalized_text(item.get("event_type")) == "questionnaire_submit" for item in timeline.get("items") or []):
        payload["summary"] = "客户最近提交过问卷，建议先核对问卷结论与当前阶段，再安排人工跟进。"
        payload["next_action"] = "先确认问卷结论是否仍然有效。"
        return payload

    payload["summary"] = "当前仅能给出规则级建议，暂不展示 AI 草稿。"
    payload["next_action"] = "人工结合最近证据决定是否继续跟进。"
    return payload


def is_customer_pulse_enabled() -> bool:
    return _setting_bool(CUSTOMER_PULSE_FLAG_KEY, default=False)


def build_customer_pulse(external_userid: str) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    enabled = is_customer_pulse_enabled()
    payload = _base_payload(enabled=enabled)
    if not enabled:
        payload["hidden_reason"] = "feature_disabled"
        return payload
    if not normalized_external_userid:
        payload["hidden_reason"] = "missing_external_userid"
        return payload

    timeline = _timeline_payload(normalized_external_userid)
    marketing_state = fetch_customer_marketing_state_current(normalized_external_userid) or {}
    value_segment = fetch_customer_value_segment_current(normalized_external_userid) or {}

    degraded_from_ai: dict[str, Any] | None = None
    for row in list_customer_agent_output_rows(normalized_external_userid, limit=CUSTOMER_PULSE_AGENT_OUTPUT_LIMIT):
        candidate = _ai_candidate_payload(
            row,
            timeline=timeline,
            marketing_state=marketing_state,
            value_segment=value_segment,
        )
        if candidate:
            return candidate
        if degraded_from_ai is None and _normalized_text(row.get("output_type")) in _AI_OUTPUT_TYPES:
            degraded_from_ai = row

    return _rule_based_payload(
        timeline=timeline,
        marketing_state=marketing_state,
        value_segment=value_segment,
        degraded_from_ai=degraded_from_ai,
    )
