from __future__ import annotations

from typing import Any

from .customer_pulse_signal_service import _build_rule_signals, _load_context
from .service import (
    CUSTOMER_PULSE_RULES_VERSION,
    _EXECUTION_AUDIT_AI_SUGGESTED,
    _TERMINAL_CARD_STATUSES,
    _action_label,
    _apply_action_allowlist,
    _dedupe_evidence,
    _iso_now,
    _json_dump,
    _json_loads,
    _normalized_text,
    _present_card,
    _priority_from_score,
    _resolved_tenant_context,
    _resolved_tenant_key,
    _resource_summary,
    _actor_summary,
    customer_pulse_scoped_key,
    customer_pulse_tenant_context_summary,
    generate_customer_pulse_ai_recommendation,
    repo,
)

__all__ = [
    "_build_action_candidates",
    "_build_scoring",
    "_materialize_customer_pulse",
    "_merge_ai_recommendation_into_candidates",
    "_persist_signals",
    "_snapshot_matches",
    "_suppress_reply_draft_when_ai_is_untrusted",
    "_upsert_primary_card",
]


def _persist_signals(
    external_userid: str,
    *,
    signals: list[dict[str, Any]],
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> list[dict[str, Any]]:
    """Internal owner for persisting synthesized pulse signals."""

    persisted: list[dict[str, Any]] = []
    active_signal_keys: list[str] = []
    resolved_tenant_key = _resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key)
    for signal in signals:
        active_signal_keys.append(signal["signal_key"])
        persisted.append(
            repo.upsert_customer_pulse_signal_event(
                signal_key=signal["signal_key"],
                tenant_key=resolved_tenant_key,
                external_userid=signal["external_userid"],
                owner_userid=signal["owner_userid"],
                signal_type=signal["signal_type"],
                signal_source=signal["signal_source"],
                signal_status="open",
                priority=signal["priority"],
                evidence=signal["evidence"],
                source_ref_type=signal["source_ref_type"],
                source_ref_id=signal["source_ref_id"],
                source_updated_at=signal["source_updated_at"],
                score=float(signal.get("score") or 0),
                summary=signal["summary"],
                payload=signal["payload"],
            )
        )
    repo.resolve_customer_pulse_stale_signals_by_tenant(
        external_userid,
        active_signal_keys=active_signal_keys,
        tenant_key=resolved_tenant_key,
    )
    return persisted


def _build_scoring(signals: list[dict[str, Any]], *, metrics: dict[str, Any]) -> dict[str, Any]:
    """Internal owner for pulse priority/scoring projection."""

    if not signals:
        return {
            "priority_score": 0.0,
            "priority": "low",
            "risk_flags": [],
            "opportunity_flags": [],
            "score_breakdown": [],
            "confidence": None,
            "source_updated_at": "",
        }
    ordered_signals = sorted(
        signals,
        key=lambda item: (float(item.get("score") or 0), _normalized_text(item.get("source_updated_at"))),
        reverse=True,
    )
    raw_score = sum(float(item.get("score") or 0) for item in ordered_signals)
    priority_score = round(min(raw_score, 100.0), 2)
    risk_flags: list[dict[str, Any]] = []
    opportunity_flags: list[dict[str, Any]] = []
    score_breakdown: list[dict[str, Any]] = []
    seen_flag_keys: set[str] = set()
    risk_keys: set[str] = set()
    for signal in ordered_signals:
        payload = _json_loads(signal.get("payload_json") or signal.get("payload"), default={})
        if not isinstance(payload, dict):
            payload = {}
        flag_bucket = _normalized_text(payload.get("flag_bucket"))
        flag_key = _normalized_text(payload.get("flag_key"))
        flag_label = _normalized_text(payload.get("flag_label")) or flag_key or _normalized_text(signal.get("signal_type"))
        evidence = _dedupe_evidence(_json_loads(signal.get("evidence_json") or signal.get("evidence"), default=[]), limit=2)
        score_entry = {
            "signal_type": _normalized_text(signal.get("signal_type")),
            "label": flag_label,
            "category": flag_bucket or "neutral",
            "score": round(float(signal.get("score") or 0), 2),
            "summary": _normalized_text(signal.get("summary")),
            "evidence": evidence,
        }
        score_breakdown.append(score_entry)
        if not flag_key or flag_key in seen_flag_keys:
            continue
        seen_flag_keys.add(flag_key)
        flag_entry = {
            "key": flag_key,
            "label": flag_label,
            "score": round(float(signal.get("score") or 0), 2),
            "summary": _normalized_text(signal.get("summary")),
            "evidence": evidence,
        }
        if flag_bucket == "risk":
            risk_keys.add(flag_key)
            risk_flags.append(flag_entry)
        elif flag_bucket == "opportunity":
            opportunity_flags.append(flag_entry)

    priority = _priority_from_score(priority_score, risk_keys=risk_keys)
    confidence = round(min(0.98, max(priority_score / 100, 0.35)), 4)
    source_updated_at = max(
        [_normalized_text(item.get("source_updated_at")) for item in ordered_signals if _normalized_text(item.get("source_updated_at"))],
        default=_normalized_text(metrics.get("last_interaction_at")),
    )
    return {
        "priority_score": priority_score,
        "priority": priority,
        "risk_flags": risk_flags,
        "opportunity_flags": opportunity_flags,
        "score_breakdown": score_breakdown,
        "confidence": confidence,
        "source_updated_at": source_updated_at,
    }


def _build_action_candidates(context: dict[str, Any], *, scoring: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Internal owner for pulse action candidate projection."""

    from .service import (
        _action_label,
        _build_rule_based_draft_message,
        _followup_segment_from_marketing_state,
        _next_followup_time,
        _soon_followup_time,
    )

    summary = context["summary"]
    marketing_state = context["marketing_state"]
    value_segment = context["value_segment"]
    ai_assist = context["ai_assist"]
    risk_keys = {item["key"] for item in scoring["risk_flags"]}
    opportunity_keys = {item["key"] for item in scoring["opportunity_flags"]}
    evidence = _dedupe_evidence(
        [
            evidence_item
            for flag in [*scoring["risk_flags"], *scoring["opportunity_flags"]]
            for evidence_item in flag.get("evidence", [])
            if isinstance(evidence_item, dict)
        ],
        limit=4,
    )

    candidates: list[dict[str, Any]] = []
    seen_action_types: set[str] = set()

    def add_candidate(
        *,
        action_type: str,
        title: str,
        reason: str,
        payload: dict[str, Any],
        candidate_score: float,
        evidence_items: list[dict[str, Any]] | None = None,
    ) -> None:
        if action_type in seen_action_types:
            return
        seen_action_types.add(action_type)
        candidates.append(
            {
                "rank": len(candidates) + 1,
                "action_type": action_type,
                "action_label": _action_label(action_type),
                "title": _normalized_text(title) or _action_label(action_type),
                "reason": _normalized_text(reason),
                "candidate_score": round(float(candidate_score or 0), 2),
                "need_human_confirmation": True,
                "payload": dict(payload or {}),
                "evidence": _dedupe_evidence(list(evidence_items or evidence), limit=3),
            }
        )

    customer_name = _normalized_text(summary.get("customer_name")) or _normalized_text(summary.get("external_userid"))
    primary_reason = "；".join(
        [
            "、".join(item["label"] for item in scoring["risk_flags"][:2]) if scoring["risk_flags"] else "",
            "、".join(item["label"] for item in scoring["opportunity_flags"][:2]) if scoring["opportunity_flags"] else "",
        ]
    ).strip("；")

    if risk_keys.intersection({"negative_sentiment", "service_exception"}):
        add_candidate(
            action_type="create_followup_task",
            title="优先安排人工介入",
            reason=primary_reason or "客户当前存在投诉、异常或服务风险，需要人工先接住。",
            payload={
                "task_title": "人工跟进客户异常/投诉",
                "due_at": _soon_followup_time(hours=2),
            },
            candidate_score=scoring["priority_score"] + 5,
        )

    if "unanswered_question" in risk_keys:
        draft_message = _normalized_text(ai_assist.get("draft_message"))
        if not draft_message:
            draft_message = _build_rule_based_draft_message(
                customer_name=customer_name,
                summary=primary_reason or "客户近期有待处理问题",
                evidence=evidence,
            )
        add_candidate(
            action_type="generate_reply_draft",
            title="先生成一版回复草稿",
            reason=primary_reason or "客户最近的问题还没有被接住，先准备一版草稿供人工确认。",
            payload={
                "channel_type": "existing_customer_channel",
                "draft_message": draft_message,
                "draft_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
                "due_at": _normalized_text(context["reply_row"].get("not_before"))
                or _normalized_text(metrics.get("last_inbound_at"))
                or _normalized_text(scoring.get("source_updated_at")),
            },
            candidate_score=scoring["priority_score"] + (5 if ai_assist.get("available") else 0),
        )

    current_followup_segment = _followup_segment_from_marketing_state(marketing_state)
    value_segment_name = _normalized_text(value_segment.get("segment")).lower()
    if opportunity_keys.intersection({"high_intent_stage", "high_intent_behavior"}) and current_followup_segment != "focus" and value_segment_name in {"top", "core", "focus"}:
        add_candidate(
            action_type="update_followup_segment",
            title="升级为重点跟进",
            reason=primary_reason or "客户已进入高意向推进段，当前应切到重点跟进。",
            payload={"followup_segment": "focus"},
            candidate_score=scoring["priority_score"],
        )

    if risk_keys.intersection({"stage_stalled", "missing_followup_time", "interaction_stale"}):
        add_candidate(
            action_type="set_followup_reminder",
            title="补上下次跟进提醒",
            reason=primary_reason or "当前推进节奏已经变慢，需要明确下一次跟进时间。",
            payload={"due_at": _normalized_text(metrics.get("known_followup_due_at")) or _next_followup_time()},
            candidate_score=max(scoring["priority_score"] - 3, 0),
        )

    if (
        opportunity_keys.intersection({"high_intent_stage", "high_intent_behavior", "high_intent_tag"})
        and risk_keys.intersection({"stage_stalled", "interaction_stale", "missing_followup_time"})
    ):
        add_candidate(
            action_type="create_followup_task",
            title="补一个高优先级跟进任务",
            reason=primary_reason or "客户有推进价值，但最近缺少明确动作，建议先补任务。",
            payload={
                "task_title": "跟进高意向客户",
                "due_at": _next_followup_time(),
            },
            candidate_score=max(scoring["priority_score"] - 1, 0),
        )

    if not candidates and scoring["priority_score"] >= 25:
        add_candidate(
            action_type="set_followup_reminder",
            title="安排下一次跟进提醒",
            reason=primary_reason or "当前没有更强动作，先补一个明确提醒并等待人工确认。",
            payload={"due_at": _next_followup_time()},
            candidate_score=scoring["priority_score"],
        )
    return candidates


def _merge_ai_recommendation_into_candidates(
    *,
    candidates: list[dict[str, Any]],
    recommendation_result: dict[str, Any],
    default_evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Internal owner for AI recommendation merge into candidate list."""

    if _normalized_text(recommendation_result.get("status")) != "accepted":
        return candidates, default_evidence
    recommendation = recommendation_result.get("recommendation") or {}
    if not isinstance(recommendation, dict):
        return candidates, default_evidence
    action_type = _normalized_text(recommendation.get("actionType"))
    if not action_type:
        return candidates, default_evidence
    match_index = next(
        (index for index, item in enumerate(candidates) if _normalized_text(item.get("action_type")) == action_type),
        -1,
    )
    if match_index < 0:
        return candidates, default_evidence

    merged_candidates = [dict(item) for item in candidates]
    matched_candidate = dict(merged_candidates.pop(match_index))
    matched_candidate["source"] = "ai"
    matched_candidate["title"] = _normalized_text(recommendation.get("actionTitle")) or _normalized_text(matched_candidate.get("title"))
    matched_candidate["reason"] = _normalized_text(recommendation.get("whyNow")) or _normalized_text(recommendation.get("summary")) or _normalized_text(matched_candidate.get("reason"))
    matched_candidate["why_now"] = _normalized_text(recommendation.get("whyNow"))
    matched_candidate["ai_summary"] = _normalized_text(recommendation.get("summary"))
    matched_candidate["candidate_score"] = round(
        max(float(matched_candidate.get("candidate_score") or 0), float(recommendation.get("confidence") or 0) * 100),
        2,
    )
    matched_candidate["evidence"] = _dedupe_evidence(
        [
            *list(recommendation_result.get("resolved_evidence") or []),
            *list(matched_candidate.get("evidence") or []),
            *list(default_evidence or []),
        ],
        limit=4,
    )
    payload = dict(matched_candidate.get("payload") or {})
    safe_field_updates = recommendation.get("safeFieldUpdates") if isinstance(recommendation.get("safeFieldUpdates"), dict) else {}
    if action_type == "generate_reply_draft":
        draft_message = _normalized_text(recommendation.get("draftText"))
        if draft_message:
            payload["draft_message"] = draft_message
    if action_type == "update_followup_segment" and _normalized_text(safe_field_updates.get("followupSegment")):
        payload["followup_segment"] = _normalized_text(safe_field_updates.get("followupSegment"))
    if action_type in {"set_followup_reminder", "create_followup_task"} and _normalized_text(safe_field_updates.get("nextFollowupAt")):
        payload["due_at"] = _normalized_text(safe_field_updates.get("nextFollowupAt"))
    if action_type == "update_tags":
        payload["add_tag_ids"] = [
            _normalized_text(item) for item in (safe_field_updates.get("addTagIds") or []) if _normalized_text(item)
        ]
        payload["remove_tag_ids"] = [
            _normalized_text(item) for item in (safe_field_updates.get("removeTagIds") or []) if _normalized_text(item)
        ]
    payload["ai_recommendation"] = {
        "summary": _normalized_text(recommendation.get("summary")),
        "why_now": _normalized_text(recommendation.get("whyNow")),
        "confidence": round(float(recommendation.get("confidence") or 0), 4),
        "evidence_refs": recommendation.get("evidenceRefs") or [],
        "safe_field_updates": safe_field_updates,
        "provider": _normalized_text(recommendation_result.get("provider")),
    }
    matched_candidate["payload"] = payload
    merged_candidates.insert(0, matched_candidate)
    primary_evidence = _dedupe_evidence(
        [
            *list(recommendation_result.get("resolved_evidence") or []),
            *list(default_evidence or []),
        ],
        limit=6,
    )
    return merged_candidates, primary_evidence or default_evidence


def _suppress_reply_draft_when_ai_is_untrusted(
    *,
    candidates: list[dict[str, Any]],
    recommendation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Internal owner for fallback masking on reply-draft candidates."""

    if not candidates:
        return candidates
    if _normalized_text(recommendation_result.get("status")) != "fallback":
        return candidates
    fallback_reason = _normalized_text(recommendation_result.get("fallback_reason"))
    if fallback_reason not in {"low_confidence", "invalid_or_blocked_ai_output"}:
        return candidates
    first_candidate = dict(candidates[0])
    if _normalized_text(first_candidate.get("action_type")) != "generate_reply_draft":
        return candidates
    payload = dict(first_candidate.get("payload") or {})
    payload["draft_message"] = ""
    payload["draft_blocked_by_ai"] = True
    payload["draft_block_reason"] = fallback_reason
    payload["draft_notice"] = "AI 置信度不足或命中风控，当前不默认生成外发草稿，请人工编辑后再保存草稿。"
    first_candidate["payload"] = payload
    first_candidate["draft_blocked_by_ai"] = True
    return [first_candidate, *[dict(item) for item in candidates[1:]]]


def _card_title(primary_candidate: dict[str, Any]) -> str:
    if _normalized_text(primary_candidate.get("source")) == "ai" and _normalized_text(primary_candidate.get("title")):
        return _normalized_text(primary_candidate.get("title"))
    mapping = {
        "generate_reply_draft": "今天先处理客户回复",
        "create_followup_task": "优先安排客户跟进动作",
        "update_followup_segment": "建议升级为重点跟进",
        "set_followup_reminder": "安排下一次跟进提醒",
        "update_tags": "补齐客户标签",
    }
    action_type = _normalized_text(primary_candidate.get("action_type"))
    return mapping.get(action_type, _normalized_text(primary_candidate.get("title")) or "客户推进行动卡")


def _card_summary(scoring: dict[str, Any], *, primary_candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    if scoring["risk_flags"]:
        parts.append("风险：" + "、".join(item["label"] for item in scoring["risk_flags"][:2]))
    if scoring["opportunity_flags"]:
        parts.append("机会：" + "、".join(item["label"] for item in scoring["opportunity_flags"][:2]))
    primary_reason = _normalized_text(primary_candidate.get("why_now") or primary_candidate.get("reason"))
    if primary_reason:
        parts.append("建议：" + primary_reason)
    return "；".join(part for part in parts if part)


def _stable_ai_payload(value: Any) -> dict[str, Any]:
    payload = _json_loads(value, default={})
    if not isinstance(payload, dict):
        return {}
    stable_payload = dict(payload)
    for key in {"run_id", "request_id", "output_id", "generated_at", "trace"}:
        stable_payload.pop(key, None)
    recommendation = stable_payload.get("recommendation")
    if isinstance(recommendation, dict):
        stable_payload["recommendation"] = {
            "summary": _normalized_text(recommendation.get("summary")),
            "actionType": _normalized_text(recommendation.get("actionType")),
            "actionTitle": _normalized_text(recommendation.get("actionTitle")),
            "whyNow": _normalized_text(recommendation.get("whyNow")),
            "evidenceRefs": recommendation.get("evidenceRefs") or [],
            "draftText": _normalized_text(recommendation.get("draftText")),
            "confidence": round(float(recommendation.get("confidence") or 0), 4),
            "safeFieldUpdates": recommendation.get("safeFieldUpdates") or {},
        }
    return stable_payload


def _snapshot_matches(latest_snapshot: dict[str, Any], *, incoming: dict[str, Any]) -> bool:
    """Internal owner for snapshot dedupe / equality checks."""

    if not latest_snapshot:
        return False
    comparable_pairs = (
        (_normalized_text(latest_snapshot.get("snapshot_status")), _normalized_text(incoming.get("snapshot_status"))),
        (_normalized_text(latest_snapshot.get("summary")), _normalized_text(incoming.get("summary"))),
        (
            _normalized_text(latest_snapshot.get("recommended_action_type")),
            _normalized_text(incoming.get("recommended_action_type")),
        ),
        (_normalized_text(latest_snapshot.get("source_updated_at")), _normalized_text(incoming.get("source_updated_at"))),
    )
    if any(current != expected for current, expected in comparable_pairs):
        return False
    if round(float(latest_snapshot.get("priority_score") or 0), 2) != round(float(incoming.get("priority_score") or 0), 2):
        return False

    def _stable_signal_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stable_items: list[dict[str, Any]] = []
        for item in items:
            stable_items.append(
                {
                    "signal_key": _normalized_text(item.get("signal_key")),
                    "signal_type": _normalized_text(item.get("signal_type")),
                    "signal_source": _normalized_text(item.get("signal_source")),
                    "signal_status": _normalized_text(item.get("signal_status")),
                    "priority": _normalized_text(item.get("priority")),
                    "score": round(float(item.get("score") or 0), 2),
                    "summary": _normalized_text(item.get("summary")),
                    "payload": _json_loads(item.get("payload_json") or item.get("payload"), default={}),
                    "evidence": _json_loads(item.get("evidence_json") or item.get("evidence"), default=[]),
                    "source_ref_type": _normalized_text(item.get("source_ref_type")),
                    "source_ref_id": _normalized_text(item.get("source_ref_id")),
                    "source_updated_at": _normalized_text(item.get("source_updated_at")),
                }
            )
        return stable_items

    for column_name, value in (
        ("evidence_json", incoming.get("evidence")),
        ("risk_flags_json", incoming.get("risk_flags")),
        ("opportunity_flags_json", incoming.get("opportunity_flags")),
        ("suggested_action_candidates_json", incoming.get("suggested_action_candidates")),
        ("score_breakdown_json", incoming.get("score_breakdown")),
    ):
        current = _json_loads(latest_snapshot.get(column_name), default=[])
        if _json_dump(current) != _json_dump(value):
            return False
    current_signals = _json_loads(latest_snapshot.get("signals_json"), default=[])
    if _json_dump(_stable_signal_items(current_signals if isinstance(current_signals, list) else [])) != _json_dump(
        _stable_signal_items(incoming.get("signals") or [])
    ):
        return False
    return _json_dump(_stable_ai_payload(latest_snapshot.get("ai_payload_json"))) == _json_dump(
        _stable_ai_payload(incoming.get("ai_payload"))
    )


def _upsert_primary_card(
    *,
    context: dict[str, Any],
    scoring: dict[str, Any],
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """Internal owner for pulse primary-card materialization."""

    if not candidates:
        return None, "skipped"
    summary = context["summary"]
    marketing_state = context["marketing_state"]
    value_segment = context["value_segment"]
    ai_assist = context["ai_assist"]
    tenant_key = _resolved_tenant_key(
        tenant_context=context.get("tenant_context"),
        tenant_key=_normalized_text(context.get("tenant_key")),
    )
    scoped_card_key = customer_pulse_scoped_key(
        tenant_key=tenant_key,
        base_key=f"{_normalized_text(summary.get('external_userid'))}:primary",
    )
    existing = repo.get_customer_pulse_card_by_key(scoped_card_key, tenant_key=tenant_key) or {}
    primary_candidate = candidates[0]
    incoming_source_updated_at = _normalized_text(scoring.get("source_updated_at")) or _iso_now()
    existing_source_updated_at = _normalized_text(existing.get("source_updated_at"))

    next_status = "open"
    next_draft_message = ""
    if _normalized_text(primary_candidate.get("action_type")) == "generate_reply_draft":
        next_draft_message = _normalized_text(primary_candidate.get("payload", {}).get("draft_message")) or _normalized_text(
            ai_assist.get("draft_message")
        )
    next_snooze_until = ""
    next_resolved_at = ""
    next_resolution_note = ""
    if existing:
        existing_status = _normalized_text(existing.get("card_status"))
        if existing_status in _TERMINAL_CARD_STATUSES and incoming_source_updated_at and existing_source_updated_at >= incoming_source_updated_at:
            return repo.get_customer_pulse_card(int(existing.get("id") or 0), tenant_key=tenant_key) or existing, "skipped"
        if existing_status == "draft_ready" and existing_source_updated_at >= incoming_source_updated_at:
            next_status = "draft_ready"
            next_draft_message = _normalized_text(existing.get("draft_message")) or next_draft_message
        elif existing_status == "snoozed" and existing_source_updated_at >= incoming_source_updated_at:
            next_status = "snoozed"
            next_snooze_until = _normalized_text(existing.get("snooze_until"))
        elif existing_status in _TERMINAL_CARD_STATUSES and incoming_source_updated_at and existing_source_updated_at < incoming_source_updated_at:
            next_status = "open"

    card_payload = {
        "card_key": scoped_card_key,
        "tenant_key": tenant_key,
        "external_userid": _normalized_text(summary.get("external_userid")),
        "owner_userid": _normalized_text(summary.get("owner_userid")),
        "customer_name": _normalized_text(summary.get("customer_name")) or _normalized_text(summary.get("external_userid")),
        "mobile": _normalized_text(summary.get("mobile")),
        "owner_display_name": _normalized_text(summary.get("owner_display_name")) or _normalized_text(summary.get("owner_userid")),
        "marketing_main_stage": _normalized_text(marketing_state.get("main_stage")),
        "marketing_sub_stage": _normalized_text(marketing_state.get("sub_stage")),
        "value_segment": _normalized_text(value_segment.get("segment")).lower(),
        "snapshot_id": int(snapshot.get("id") or 0) or None,
        "card_status": next_status,
        "priority": _normalized_text(scoring.get("priority")),
        "priority_score": float(scoring.get("priority_score") or 0),
        "card_type": _normalized_text(primary_candidate.get("action_type")).replace("generate_", "").replace("set_", ""),
        "title": _card_title(primary_candidate),
        "summary": _card_summary(scoring, primary_candidate=primary_candidate),
        "suggested_action_type": _normalized_text(primary_candidate.get("action_type")),
        "suggested_action_payload": dict(primary_candidate.get("payload") or {}),
        "evidence": evidence,
        "risk_flags": scoring["risk_flags"],
        "opportunity_flags": scoring["opportunity_flags"],
        "suggested_action_candidates": candidates,
        "score_breakdown": scoring["score_breakdown"],
        "draft_message": next_draft_message,
        "need_human_confirmation": True,
        "due_at": _normalized_text(primary_candidate.get("payload", {}).get("due_at")) or incoming_source_updated_at,
        "snooze_until": next_snooze_until,
        "resolved_at": next_resolved_at,
        "resolution_note": next_resolution_note,
        "source_updated_at": incoming_source_updated_at,
    }

    unchanged = existing and all(
        [
            _normalized_text(existing.get("card_status")) == _normalized_text(card_payload["card_status"]),
            _normalized_text(existing.get("priority")) == _normalized_text(card_payload["priority"]),
            round(float(existing.get("priority_score") or 0), 2) == round(float(card_payload["priority_score"] or 0), 2),
            _normalized_text(existing.get("title")) == _normalized_text(card_payload["title"]),
            _normalized_text(existing.get("summary")) == _normalized_text(card_payload["summary"]),
            _normalized_text(existing.get("customer_name")) == _normalized_text(card_payload["customer_name"]),
            _normalized_text(existing.get("mobile")) == _normalized_text(card_payload["mobile"]),
            _normalized_text(existing.get("owner_display_name")) == _normalized_text(card_payload["owner_display_name"]),
            _normalized_text(existing.get("marketing_main_stage")) == _normalized_text(card_payload["marketing_main_stage"]),
            _normalized_text(existing.get("marketing_sub_stage")) == _normalized_text(card_payload["marketing_sub_stage"]),
            _normalized_text(existing.get("value_segment")) == _normalized_text(card_payload["value_segment"]),
            _normalized_text(existing.get("suggested_action_type")) == _normalized_text(card_payload["suggested_action_type"]),
            _normalized_text(existing.get("source_updated_at")) == _normalized_text(card_payload["source_updated_at"]),
            _json_dump(_json_loads(existing.get("risk_flags_json"), default=[])) == _json_dump(card_payload["risk_flags"]),
            _json_dump(_json_loads(existing.get("opportunity_flags_json"), default=[])) == _json_dump(card_payload["opportunity_flags"]),
            _json_dump(_json_loads(existing.get("suggested_action_candidates_json"), default=[]))
            == _json_dump(card_payload["suggested_action_candidates"]),
            _json_dump(_json_loads(existing.get("score_breakdown_json"), default=[])) == _json_dump(card_payload["score_breakdown"]),
            _json_dump(_json_loads(existing.get("evidence_json"), default=[])) == _json_dump(card_payload["evidence"]),
            _normalized_text(existing.get("draft_message")) == _normalized_text(card_payload["draft_message"]),
            _normalized_text(existing.get("due_at")) == _normalized_text(card_payload["due_at"]),
            _normalized_text(existing.get("snooze_until")) == _normalized_text(card_payload["snooze_until"]),
        ]
    )
    if unchanged:
        return repo.get_customer_pulse_card(int(existing.get("id") or 0), tenant_key=tenant_key) or existing, "skipped"
    card = repo.upsert_customer_pulse_card(**card_payload)
    return card, "updated" if existing else "created"


def _materialize_customer_pulse(
    external_userid: str,
    *,
    operator: str,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    """Internal owner for end-to-end pulse snapshot materialization."""

    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    context = _load_context(external_userid, tenant_context=resolved_context)
    summary = context["summary"]
    normalized_external_userid = _normalized_text(summary.get("external_userid") or external_userid)
    signals, metrics = _build_rule_signals(context)
    persisted_signals = _persist_signals(normalized_external_userid, signals=signals, tenant_key=resolved_tenant_key)
    scoring = _build_scoring(persisted_signals, metrics=metrics)
    candidates = _build_action_candidates(context, scoring=scoring, metrics=metrics)
    evidence = _dedupe_evidence(
        [
            evidence_item
            for signal in persisted_signals
            for evidence_item in _json_loads(signal.get("evidence_json"), default=[])
            if isinstance(evidence_item, dict)
        ],
        limit=6,
    )
    ai_recommendation = generate_customer_pulse_ai_recommendation(
        context=context,
        scoring=scoring,
        candidates=candidates,
        signals=persisted_signals,
    )
    candidates, card_evidence = _merge_ai_recommendation_into_candidates(
        candidates=candidates,
        recommendation_result=ai_recommendation,
        default_evidence=evidence,
    )
    candidates = _suppress_reply_draft_when_ai_is_untrusted(
        candidates=candidates,
        recommendation_result=ai_recommendation,
    )
    candidates = _apply_action_allowlist(candidates)
    primary_ai_recommendation = ai_recommendation.get("recommendation") if isinstance(ai_recommendation.get("recommendation"), dict) else {}
    ai_audit_labels = [_EXECUTION_AUDIT_AI_SUGGESTED] if _normalized_text(ai_recommendation.get("status")) == "accepted" else []
    ai_payload = {
        "rules_version": CUSTOMER_PULSE_RULES_VERSION,
        "assistant_draft_available": bool(context["ai_assist"].get("available")),
        "assistant_confidence": round(float(context["ai_assist"].get("confidence") or 0), 4),
        "assistant_reason": _normalized_text(context["ai_assist"].get("reason")),
        "assistant_output_type": _normalized_text(context["ai_assist"].get("output_type")),
        "assistant_output_id": _normalized_text(context["ai_assist"].get("output_id")),
        "recommendation_status": _normalized_text(ai_recommendation.get("status")) or "skipped",
        "provider": _normalized_text(ai_recommendation.get("provider")),
        "model_name": _normalized_text(ai_recommendation.get("model_name")),
        "run_id": _normalized_text(ai_recommendation.get("run_id")),
        "request_id": _normalized_text(ai_recommendation.get("request_id")),
        "output_id": _normalized_text(ai_recommendation.get("output_id")),
        "fallback_reason": _normalized_text(ai_recommendation.get("fallback_reason")),
        "error_message": _normalized_text(ai_recommendation.get("error_message")),
        "context_window": ai_recommendation.get("context_window") or {},
        "guardrails": ai_recommendation.get("guardrails") or {},
        "guardrail_summary": {
            "blocked": bool((ai_recommendation.get("guardrails") or {}).get("blocked")),
            "input_violations": list(((ai_recommendation.get("guardrails") or {}).get("input_violations") or [])),
            "output_violations": list(((ai_recommendation.get("guardrails") or {}).get("output_violations") or [])),
        },
        "trace": {
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "resource": _resource_summary(resource_type="customer", resource_id=normalized_external_userid),
            "actor": _actor_summary(tenant_context=resolved_context, operator=_normalized_text(operator)),
            "generated_at": _iso_now(),
        },
        "audit_labels": ai_audit_labels,
        "recommendation": primary_ai_recommendation,
        "last_interaction_at": _normalized_text(metrics.get("last_interaction_at")),
        "last_inbound_at": _normalized_text(metrics.get("last_inbound_at")),
        "last_outbound_at": _normalized_text(metrics.get("last_outbound_at")),
        "stage_stalled_days": metrics.get("stage_stalled_days"),
        "interaction_gap_days": metrics.get("interaction_gap_days"),
        "current_followup_segment": _normalized_text(metrics.get("current_followup_segment")),
    }
    repo.insert_customer_pulse_metric_event(
        event_type="ai_recommendation_completed",
        event_source="customer_pulse_snapshot_job",
        external_userid=normalized_external_userid,
        owner_userid=_normalized_text(summary.get("owner_userid")),
        action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
        tenant_key=resolved_tenant_key,
        operator=_normalized_text(operator),
        payload={
            "status": ai_payload["recommendation_status"],
            "fallback_reason": ai_payload["fallback_reason"],
            "provider": ai_payload["provider"],
            "model_name": ai_payload["model_name"],
            "request_id": ai_payload["request_id"],
            "output_id": ai_payload["output_id"],
            "guardrails": ai_payload["guardrail_summary"],
        },
    )
    if ai_payload["recommendation_status"] == "accepted":
        repo.insert_customer_pulse_metric_event(
            event_type="ai_success",
            event_source="customer_pulse_snapshot_job",
            external_userid=normalized_external_userid,
            owner_userid=_normalized_text(summary.get("owner_userid")),
            action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
            tenant_key=resolved_tenant_key,
            operator=_normalized_text(operator),
            payload={
                "provider": ai_payload["provider"],
                "model_name": ai_payload["model_name"],
                "request_id": ai_payload["request_id"],
                "output_id": ai_payload["output_id"],
            },
        )
    if ai_payload["recommendation_status"] == "fallback":
        repo.insert_customer_pulse_metric_event(
            event_type="fallback_count",
            event_source="customer_pulse_snapshot_job",
            external_userid=normalized_external_userid,
            owner_userid=_normalized_text(summary.get("owner_userid")),
            action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
            tenant_key=resolved_tenant_key,
            operator=_normalized_text(operator),
            payload={
                "fallback_reason": ai_payload["fallback_reason"],
                "provider": ai_payload["provider"],
                "model_name": ai_payload["model_name"],
            },
        )
    if ai_payload["recommendation_status"] == "fallback" and (
        _normalized_text(ai_payload["fallback_reason"]) or _normalized_text(ai_payload["error_message"])
    ):
        repo.insert_customer_pulse_metric_event(
            event_type="ai_error",
            event_source="customer_pulse_snapshot_job",
            external_userid=normalized_external_userid,
            owner_userid=_normalized_text(summary.get("owner_userid")),
            action_type=_normalized_text(primary_ai_recommendation.get("actionType")),
            tenant_key=resolved_tenant_key,
            operator=_normalized_text(operator),
            payload={
                "fallback_reason": ai_payload["fallback_reason"],
                "error_message": ai_payload["error_message"],
                "provider": ai_payload["provider"],
            },
        )

    if not persisted_signals or not candidates or float(scoring.get("priority_score") or 0) < 20:
        return {
            "ok": True,
            "external_userid": normalized_external_userid,
            "customer_name": _normalized_text(summary.get("customer_name")) or normalized_external_userid,
            "processed": False,
            "reason": "no_actionable_candidate",
            "priority_score": float(scoring.get("priority_score") or 0),
            "risk_flags": scoring["risk_flags"],
            "opportunity_flags": scoring["opportunity_flags"],
            "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
            "generated_at": _iso_now(),
        }

    primary_candidate = candidates[0]
    snapshot_payload = {
        "tenant_key": resolved_tenant_key,
        "external_userid": normalized_external_userid,
        "owner_userid": _normalized_text(summary.get("owner_userid")),
        "snapshot_status": "visible",
        "confidence": scoring["confidence"],
        "priority_score": float(scoring.get("priority_score") or 0),
        "summary": _card_summary(scoring, primary_candidate=primary_candidate),
        "recommended_action_type": _normalized_text(primary_candidate.get("action_type")),
        "recommended_action_label": _action_label(primary_candidate.get("action_type")),
        "evidence": card_evidence,
        "ai_payload": ai_payload,
        "signals": persisted_signals,
        "risk_flags": scoring["risk_flags"],
        "opportunity_flags": scoring["opportunity_flags"],
        "suggested_action_candidates": candidates,
        "score_breakdown": scoring["score_breakdown"],
        "source_updated_at": _normalized_text(scoring.get("source_updated_at")),
        "created_by": _normalized_text(operator) or "system",
    }
    latest_snapshot = context["latest_snapshot"]
    if _snapshot_matches(latest_snapshot, incoming=snapshot_payload):
        snapshot = latest_snapshot
    else:
        snapshot = repo.create_customer_pulse_snapshot(**snapshot_payload)

    card, card_action = _upsert_primary_card(
        context=context,
        scoring=scoring,
        evidence=card_evidence,
        candidates=candidates,
        snapshot=snapshot,
    )
    return {
        "ok": True,
        "external_userid": normalized_external_userid,
        "customer_name": _normalized_text(summary.get("customer_name")) or normalized_external_userid,
        "processed": bool(card),
        "snapshot": snapshot,
        "card": _present_card(card, snapshot_row=snapshot, access_context=context.get("tenant_context")) if card else None,
        "priority_score": float(scoring.get("priority_score") or 0),
        "priority": _normalized_text(scoring.get("priority")),
        "risk_flags": scoring["risk_flags"],
        "opportunity_flags": scoring["opportunity_flags"],
        "suggested_action_candidates": candidates,
        "score_breakdown": scoring["score_breakdown"],
        "metrics": metrics,
        "action": card_action,
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "generated_at": _iso_now(),
    }
