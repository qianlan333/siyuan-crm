from __future__ import annotations

from typing import Any, Mapping

from ..customer_pulse.access import (
    customer_pulse_template_access_payload,
    customer_pulse_tenant_context_summary,
    resolve_customer_pulse_read_scope,
)
from . import repo
from .followup_ai_enhancement_service import apply_mission_ai_if_enabled
from .service import (
    FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
    FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS,
    FOLLOWUP_ORCHESTRATOR_MISSION_STATES,
    FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
    FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS,
    _assert_mission_items_accessible,
    _batch_group_key,
    _build_owner_workload,
    _card_signals,
    _decorate_item,
    _decorate_mission,
    _determine_assignment,
    _escalation_reason,
    _feature_gate_context,
    _mission_key_for_card,
    _mission_payload,
    _mission_status_label,
    _mission_summary,
    _mission_title,
    _mission_type_for_card,
    _normalized_text,
    _resolved_followup_read_scope,
    _safe_int,
    _sha_token,
    _stable_item_status,
    _stable_mission_status,
    _summarize_mission_items,
    _sync_scope_label,
    _team_candidate_owners,
    build_customer_pulse_inbox_payload,
    followup_orchestrator_feature_gate_summary,
)


def sync_followup_orchestrator_missions(
    *,
    scope: str = "team",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 50,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for followup mission sync/read projection."""
    context = _feature_gate_context(access_context)
    gate = followup_orchestrator_feature_gate_summary(context)
    if not gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
            "feature_gate": gate,
            "missions": [],
            "mission_items": [],
        }
    requested_scope = _normalized_text(scope) or "team"
    requested_owner_userid = _normalized_text(owner_userid)
    if requested_scope == "mine":
        requested_owner_userid = _normalized_text(context.get("actor_userid") or context.get("user_id")) or requested_owner_userid
    read_scope = resolve_customer_pulse_read_scope(
        requested_owner_userid=requested_owner_userid,
        access_context=context,
    )
    tenant_key = _normalized_text(read_scope.get("tenant_key"))
    scope_key = _normalized_text(read_scope.get("owner_userid_filter")) if requested_scope == "mine" else _sync_scope_label(read_scope, requested_scope)
    pulse_payload = build_customer_pulse_inbox_payload(
        limit=max(1, min(int(limit or 50), FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS)),
        owner_userid=_normalized_text(read_scope.get("owner_userid_filter")),
        external_userid=_normalized_text(external_userid),
        operator=_normalized_text(read_scope.get("operator")),
        scope="all",
        track_metrics=False,
        metric_source="followup_orchestrator_sync",
        tenant_context=read_scope.get("tenant_context"),
        tenant_key=tenant_key,
        allowed_owner_userids=read_scope.get("allowed_owner_userids") or [],
    )
    cards = [dict(item) for item in (pulse_payload.get("cards") or []) if isinstance(item, dict)]
    owner_workload = _build_owner_workload(cards)
    owner_workload_map = {
        _normalized_text(item.get("owner_userid")): item
        for item in owner_workload
        if _normalized_text(item.get("owner_userid"))
    }
    team_candidates = _team_candidate_owners(read_scope, owner_workload)
    untreated_counts = repo.list_followup_orchestrator_unresolved_counts(
        tenant_key=tenant_key,
        external_userids=[_normalized_text(card.get("external_userid")) for card in cards],
    )
    signals_by_card_id: dict[int, dict[str, Any]] = {}
    batch_group_sizes: dict[str, int] = {}
    for card in cards:
        card_id = int(card.get("id") or 0)
        signals = _card_signals(
            card,
            owner_workload_map=owner_workload_map,
            team_candidates=team_candidates,
            untreated_counts=untreated_counts,
        )
        signals_by_card_id[card_id] = signals
        if bool(signals.get("batchable")):
            group_key = _batch_group_key(card, signals)
            batch_group_sizes[group_key] = int(batch_group_sizes.get(group_key) or 0) + 1

    mission_specs: dict[str, dict[str, Any]] = {}
    persisted_items: list[dict[str, Any]] = []
    persisted_decisions: list[dict[str, Any]] = []
    can_view_all = bool(read_scope.get("can_view_all"))
    for card in sorted(cards, key=lambda item: -float((signals_by_card_id.get(int(item.get("id") or 0)) or {}).get("schedule_score") or 0)):
        card_id = int(card.get("id") or 0)
        signals = dict(signals_by_card_id.get(card_id) or {})
        assignment = _determine_assignment(card, signals, can_view_all=can_view_all)
        escalation = _escalation_reason(card, signals)
        mission_type = _mission_type_for_card(
            card,
            signals,
            batch_group_sizes=batch_group_sizes,
            can_view_all=can_view_all,
        )
        mission_key = _mission_key_for_card(
            card,
            signals,
            mission_type=mission_type,
            scope_key=_sha_token(scope_key or "team", length=10) or "team",
            assignment=assignment,
        )
        existing_mission = repo.get_followup_orchestrator_mission_by_key(mission_key, tenant_key=tenant_key) or {}
        stable_mission_status = _stable_mission_status(existing_mission)
        batch_group_key = _batch_group_key(card, signals)
        mission_entry = mission_specs.setdefault(
            mission_key,
            {
                "mission_key": mission_key,
                "mission_type": mission_type,
                "mission_status": stable_mission_status or ("unassigned" if mission_type == "claim_queue" else "suggested"),
                "owner_userid": _normalized_text(assignment.get("suggested_assignee_userid")) if mission_type in {"claim_queue", "handoff_wave"} else _normalized_text(card.get("owner_userid")),
                "team_scope_key": scope_key,
                "source_type": "customer_pulse_rule_engine",
                "summary": "",
                "priority_score": 0.0,
                "item_count": 0,
                "requires_manager_approval": False,
                "payload_cards": [],
                "payload_signals": [],
                "payload_assignments": [],
                "payload_escalations": [],
                "batch_group_key": batch_group_key if mission_type == "batch_draft_wave" else "",
                "created_by": _normalized_text(read_scope.get("operator")) or "system",
                "items": [],
            },
        )
        mission_entry["payload_cards"].append(card)
        mission_entry["payload_signals"].append(signals)
        if _normalized_text(assignment.get("decision_type")):
            mission_entry["payload_assignments"].append(
                {
                    "card_id": card_id,
                    "external_userid": _normalized_text(card.get("external_userid")),
                    "decision_type": _normalized_text(assignment.get("decision_type")),
                    "current_owner_userid": _normalized_text(card.get("owner_userid")),
                    "suggested_owner_userid": _normalized_text(assignment.get("suggested_assignee_userid")),
                    "reason": _normalized_text(assignment.get("reason")),
                    "needs_manager_approval": bool(assignment.get("needs_manager_approval")),
                    "confidence": float(assignment.get("confidence") or 0),
                }
            )
        if bool(escalation.get("needs_escalation")):
            mission_entry["payload_escalations"].append(
                {
                    "card_id": card_id,
                    "external_userid": _normalized_text(card.get("external_userid")),
                    "reason": _normalized_text(escalation.get("reason")),
                    "confidence": float(escalation.get("confidence") or 0),
                }
            )
        mission_entry["priority_score"] = max(float(mission_entry["priority_score"] or 0), float(signals.get("schedule_score") or 0))
        mission_entry["item_count"] = int(mission_entry["item_count"] or 0) + 1
        mission_entry["requires_manager_approval"] = bool(mission_entry["requires_manager_approval"]) or bool(assignment.get("needs_manager_approval"))
        existing_item = repo.get_followup_orchestrator_mission_item_by_key(f"mission-item:card:{card_id}", tenant_key=tenant_key) or {}
        stable_item_status = _stable_item_status(existing_item)
        item_status = stable_item_status or ("unassigned" if mission_type == "claim_queue" else "suggested")
        assignment_status = _normalized_text(existing_item.get("assignment_status"))
        if not assignment_status:
            if _normalized_text(assignment.get("decision_type")):
                assignment_status = "suggested"
            else:
                assignment_status = "kept"
        existing_payload = dict(existing_item.get("payload") or {})
        payload = {
            **existing_payload,
            "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
            "title": _normalized_text(card.get("title")),
            "why_now": _normalized_text(card.get("why_now")),
            "current_judgement": _normalized_text(card.get("current_judgement") or card.get("summary")),
            "suggested_action_type": _normalized_text(card.get("suggested_action_type")),
            "suggested_action_label": _normalized_text(card.get("suggested_action_label")),
            "priority_score": round(float(card.get("priority_score") or 0), 2),
            "schedule_score": round(float(signals.get("schedule_score") or 0), 2),
            "signals": signals,
            "rule_reasons": list(signals.get("rule_reasons") or []),
            "stage_key": _normalized_text(card.get("stage_key")),
            "stage_label": _normalized_text(card.get("stage_label")),
            "owner_display_name": _normalized_text(card.get("owner_display_name")),
            "risk_flags": list(card.get("risk_flags") or []),
            "opportunity_flags": list(card.get("opportunity_flags") or []),
            "draft_blocked_by_ai": bool(card.get("draft_blocked_by_ai")),
            "batchable": bool(signals.get("batchable")),
            "batch_group_key": batch_group_key if mission_type == "batch_draft_wave" else "",
            "escalation_reason": _normalized_text(escalation.get("reason")),
            "mission_type": mission_type,
        }
        mission_entry["items"].append(
            {
                "mission_item_key": f"mission-item:card:{card_id}",
                "item_status": item_status,
                "assignment_status": assignment_status,
                "external_userid": _normalized_text(card.get("external_userid")),
                "customer_name": _normalized_text(card.get("customer_name")),
                "owner_userid": _normalized_text(card.get("owner_userid")),
                "suggested_assignee_userid": _normalized_text(assignment.get("suggested_assignee_userid")),
                "pulse_card_id": card_id,
                "pulse_snapshot_id": int((card.get("snapshot") or {}).get("id") or 0),
                "payload": payload,
                "evidence_refs": list(card.get("evidence_refs") or []),
                "decision_type": _normalized_text(assignment.get("decision_type")),
                "decision_status": _normalized_text(existing_item.get("assignment_status")) if _normalized_text(existing_item.get("assignment_status")) in {"accepted", "approved", "rejected"} else ("suggested" if _normalized_text(assignment.get("decision_type")) else ""),
                "decision_reason": _normalized_text(assignment.get("reason")),
                "needs_manager_approval": bool(assignment.get("needs_manager_approval")),
            }
        )

    persisted_missions: list[dict[str, Any]] = []
    for mission_spec in mission_specs.values():
        mission_spec["summary"] = _mission_summary(
            _normalized_text(mission_spec.get("mission_type")),
            item_count=int(mission_spec.get("item_count") or 0),
            scope_label=scope_key,
        )
        mission_spec["payload"] = _mission_payload(
            _normalized_text(mission_spec.get("mission_type")),
            cards=list(mission_spec.get("payload_cards") or []),
            signals=list(mission_spec.get("payload_signals") or []),
            assignment_suggestions=list(mission_spec.get("payload_assignments") or []),
            escalation_suggestions=list(mission_spec.get("payload_escalations") or []),
            batch_group_key=_normalized_text(mission_spec.get("batch_group_key")),
            scope_key=scope_key,
        )
        persisted_mission = repo.upsert_followup_orchestrator_mission(
            tenant_key=tenant_key,
            mission_key=_normalized_text(mission_spec.get("mission_key")),
            mission_type=_normalized_text(mission_spec.get("mission_type")),
            mission_status=_normalized_text(mission_spec.get("mission_status")),
            owner_userid=_normalized_text(mission_spec.get("owner_userid")),
            team_scope_key=_normalized_text(mission_spec.get("team_scope_key")),
            source_type="customer_pulse_rule_engine",
            summary=_normalized_text(mission_spec.get("summary")),
            priority_score=float(mission_spec.get("priority_score") or 0),
            item_count=int(mission_spec.get("item_count") or 0),
            requires_manager_approval=bool(mission_spec.get("requires_manager_approval")),
            payload=mission_spec.get("payload") or {},
            created_by=_normalized_text(mission_spec.get("created_by")),
        )
        active_item_keys: list[str] = []
        mission_items_for_summary: list[dict[str, Any]] = []
        decisions_for_summary: list[dict[str, Any]] = []
        for item_spec in mission_spec.get("items") or []:
            if not isinstance(item_spec, dict):
                continue
            active_item_keys.append(_normalized_text(item_spec.get("mission_item_key")))
            persisted_item = repo.upsert_followup_orchestrator_mission_item(
                tenant_key=tenant_key,
                mission_id=int(persisted_mission.get("id") or 0),
                mission_item_key=_normalized_text(item_spec.get("mission_item_key")),
                item_status=_normalized_text(item_spec.get("item_status")),
                assignment_status=_normalized_text(item_spec.get("assignment_status")),
                external_userid=_normalized_text(item_spec.get("external_userid")),
                customer_name=_normalized_text(item_spec.get("customer_name")),
                owner_userid=_normalized_text(item_spec.get("owner_userid")),
                suggested_assignee_userid=_normalized_text(item_spec.get("suggested_assignee_userid")),
                pulse_card_id=int(item_spec.get("pulse_card_id") or 0) or None,
                pulse_snapshot_id=int(item_spec.get("pulse_snapshot_id") or 0) or None,
                payload=item_spec.get("payload") or {},
                evidence_refs=item_spec.get("evidence_refs") or [],
            )
            persisted_items.append(persisted_item)
            mission_items_for_summary.append(persisted_item)
            decision_type = _normalized_text(item_spec.get("decision_type"))
            if decision_type:
                persisted_decision = repo.upsert_followup_orchestrator_assignment_decision(
                    tenant_key=tenant_key,
                    mission_id=int(persisted_mission.get("id") or 0),
                    mission_item_id=int(persisted_item.get("id") or 0),
                    decision_type=decision_type,
                    decision_status=_normalized_text(item_spec.get("decision_status")) or "suggested",
                    current_owner_userid=_normalized_text(item_spec.get("owner_userid")),
                    suggested_owner_userid=_normalized_text(item_spec.get("suggested_assignee_userid")),
                    payload={
                        "reason": _normalized_text(item_spec.get("decision_reason")),
                        "needs_manager_approval": bool(item_spec.get("needs_manager_approval")),
                    },
                )
                persisted_decisions.append(persisted_decision)
                decisions_for_summary.append(persisted_decision)
        repo.mark_followup_orchestrator_missing_items_stale(
            mission_id=int(persisted_mission.get("id") or 0),
            tenant_key=tenant_key,
            active_item_keys=active_item_keys,
        )
        refreshed_items = repo.list_followup_orchestrator_mission_items(
            tenant_key=tenant_key,
            mission_id=int(persisted_mission.get("id") or 0),
            limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
        )
        refreshed_status, refreshed_count = _summarize_mission_items(refreshed_items)
        if _stable_mission_status(persisted_mission):
            refreshed_status = _normalized_text(persisted_mission.get("mission_status"))
        persisted_mission = repo.update_followup_orchestrator_mission(
            int(persisted_mission.get("id") or 0),
            tenant_key=tenant_key,
            mission_status=refreshed_status,
            item_count=refreshed_count,
        )
        persisted_missions.append(persisted_mission)

    mission_detail_map: dict[str, dict[str, Any]] = {}
    for mission in persisted_missions:
        mission_id = int(mission.get("id") or 0)
        items = repo.list_followup_orchestrator_mission_items(
            tenant_key=tenant_key,
            mission_id=mission_id,
            limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
        )
        decisions = repo.list_followup_orchestrator_assignment_decisions(
            tenant_key=tenant_key,
            mission_id=mission_id,
            limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
        )
        decision_map = {
            int(item.get("mission_item_id") or 0): item
            for item in decisions
            if int(item.get("mission_item_id") or 0) > 0
        }
        decorated_items = [_decorate_item(item, decision=decision_map.get(int(item.get("id") or 0))) for item in items]
        mission_logs = repo.list_followup_orchestrator_execution_logs(
            tenant_key=tenant_key,
            mission_id=mission_id,
            limit=50,
        )
        mission_detail_map[_normalized_text(mission.get("mission_key"))] = _decorate_mission(
            mission,
            items=decorated_items,
            decisions=decisions,
            logs=mission_logs,
        )

    return {
        "enabled": True,
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "feature_gate": gate,
        "tenant_context": customer_pulse_tenant_context_summary(context),
        "access": customer_pulse_template_access_payload(context),
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "rules": dict(FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS),
        "filters": {
            "scope": requested_scope,
            "owner_userid": _normalized_text(read_scope.get("owner_userid_filter")) if requested_scope == "mine" else requested_owner_userid,
            "external_userid": _normalized_text(external_userid),
        },
        "owner_workload": owner_workload,
        "team_candidate_count": len(team_candidates),
        "cards": cards,
        "missions": [mission_detail_map[_normalized_text(mission.get("mission_key"))] for mission in persisted_missions if _normalized_text(mission.get("mission_key")) in mission_detail_map],
        "mission_items": persisted_items,
        "decisions": persisted_decisions,
    }


def build_followup_orchestrator_overview_payload(
    *,
    scope: str = "team",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for overview/team board projections."""
    context = _feature_gate_context(access_context)
    gate = followup_orchestrator_feature_gate_summary(context)
    if not gate["enabled"]:
        return {
            "enabled": False,
            "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
            "feature_gate": gate,
            "missions": [],
            "mission_items": [],
        }
    synced = sync_followup_orchestrator_missions(
        scope=scope,
        owner_userid=owner_userid,
        external_userid=external_userid,
        limit=limit,
        access_context=context,
    ) if auto_sync else {
        "enabled": True,
        "feature_gate": gate,
        "tenant_context": customer_pulse_tenant_context_summary(context),
        "access": customer_pulse_template_access_payload(context),
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "rules": dict(FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS),
        "cards": [],
        "missions": [],
        "mission_items": [],
        "owner_workload": [],
        "team_candidate_count": 0,
        "filters": {"scope": _normalized_text(scope) or "team", "owner_userid": _normalized_text(owner_userid), "external_userid": _normalized_text(external_userid)},
    }
    synced_missions = synced.get("missions")
    synced_items = synced.get("mission_items")
    synced_cards = synced.get("cards")
    missions = [dict(item) for item in synced_missions if isinstance(item, dict)] if isinstance(synced_missions, list) else []
    missions = [apply_mission_ai_if_enabled(item) for item in missions]
    mission_items = [dict(item) for item in synced_items if isinstance(item, dict)] if isinstance(synced_items, list) else []
    card_count = len(synced_cards) if isinstance(synced_cards, list) else 0
    assignment_suggestions: list[dict[str, Any]] = []
    escalation_suggestions: list[dict[str, Any]] = []
    batch_draft_suggestions: list[dict[str, Any]] = []
    mission_candidates: list[dict[str, Any]] = []
    for mission in missions:
        payload = dict(mission.get("payload") or {})
        ai_enhancement = dict(mission.get("ai_enhancement") or {}) if isinstance(mission.get("ai_enhancement"), dict) else {}
        ai_recommendation = dict(ai_enhancement.get("recommendation") or {}) if isinstance(ai_enhancement.get("recommendation"), dict) else {}
        mission_candidates.append(
            {
                "mission_key": _normalized_text(mission.get("mission_key")),
                "mission_type": _normalized_text(mission.get("mission_type")),
                "mission_status": _normalized_text(mission.get("mission_status")),
                "mission_status_label": _mission_status_label(mission.get("mission_status")),
                "title": _normalized_text(mission.get("title")) or _mission_title(_normalized_text(mission.get("mission_type"))),
                "summary": _normalized_text(mission.get("summary")),
                "item_count": int(mission.get("item_count") or 0),
                "priority_score": round(float(mission.get("priority_score") or 0), 2),
                "reason": _normalized_text(ai_recommendation.get("missionSummary")) or _normalized_text(mission.get("summary")),
                "confidence": round(float(ai_recommendation.get("confidence") or 0), 4),
                "evidence_refs": list(ai_recommendation.get("evidenceRefs") or payload.get("evidence_refs") or []),
                "assignment_why": _normalized_text(mission.get("assignment_why")),
                "escalation_why": _normalized_text(mission.get("escalation_why")),
                "handoff_summary": _normalized_text(mission.get("handoff_summary")),
                "ai_enhancement": ai_enhancement,
                "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
                "customer_items": [
                    {
                        "card_id": int((item.get("payload") or {}).get("pulse_card_id") or item.get("pulse_card_id") or 0),
                        "external_userid": _normalized_text(item.get("external_userid")),
                        "customer_name": _normalized_text(item.get("customer_name")),
                        "owner_userid": _normalized_text(item.get("owner_userid")),
                        "owner_display_name": _normalized_text((item.get("payload") or {}).get("owner_display_name")),
                        "why_now": _normalized_text((item.get("payload") or {}).get("why_now")),
                        "suggested_action_type": _normalized_text((item.get("payload") or {}).get("suggested_action_type")),
                        "suggested_action_label": _normalized_text((item.get("payload") or {}).get("suggested_action_label")),
                        "ai_draft_suggestion": dict(item.get("ai_draft_suggestion") or {}) if isinstance(item.get("ai_draft_suggestion"), dict) else {},
                    }
                    for item in (mission.get("items") or [])[:5]
                    if isinstance(item, dict)
                ],
            }
        )
        for assignment in payload.get("assignment_suggestions") or []:
            if isinstance(assignment, dict):
                assignment_suggestions.append(dict(assignment))
        for escalation in payload.get("escalation_suggestions") or []:
            if isinstance(escalation, dict):
                escalation_suggestions.append(dict(escalation))
        if _normalized_text(mission.get("mission_type")) == "batch_draft_wave":
            batch_draft_suggestions.append(
                {
                    "batch_key": _normalized_text(mission.get("mission_key")),
                    "title": _normalized_text(mission.get("title")) or _mission_title("batch_draft_wave"),
                    "item_count": int(mission.get("item_count") or 0),
                    "reason": _normalized_text(mission.get("summary")),
                    "confidence": round(float(ai_recommendation.get("confidence") or 0), 4),
                    "evidence_refs": list(ai_recommendation.get("evidenceRefs") or payload.get("evidence_refs") or []),
                    "ai_enhancement": ai_enhancement,
                    "cards": [
                        {
                            "card_id": int(item.get("pulse_card_id") or 0),
                            "external_userid": _normalized_text(item.get("external_userid")),
                            "customer_name": _normalized_text(item.get("customer_name")),
                            "owner_userid": _normalized_text(item.get("owner_userid")),
                            "why_now": _normalized_text(item.get("why_now")),
                            "ai_draft_suggestion": dict(item.get("ai_draft_suggestion") or {}) if isinstance(item.get("ai_draft_suggestion"), dict) else {},
                        }
                        for item in (mission.get("items") or [])
                        if isinstance(item, dict)
                    ],
                }
            )
    return {
        "enabled": True,
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "feature_gate": synced.get("feature_gate") or gate,
        "tenant_context": synced.get("tenant_context"),
        "access": synced.get("access"),
        "filters": synced.get("filters") or {},
        "states": list(FOLLOWUP_ORCHESTRATOR_MISSION_STATES),
        "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "rules": dict(FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS),
        "summary_cards": [
            {"key": "open_action_cards", "label": "可编排卡片", "value": card_count, "description": "来自 customer_pulse action cards"},
            {"key": "mission_candidates", "label": "任务包", "value": len(missions), "description": "按优先级、认领、转派、升级和成批规则生成"},
            {"key": "assignment_suggestions", "label": "转派建议", "value": len(assignment_suggestions), "description": "owner 过载时优先建议接力"},
            {"key": "batch_draft_suggestions", "label": "批量草稿建议", "value": len(batch_draft_suggestions), "description": "仅对低风险且同模板的回复类卡片生效"},
        ],
        "owner_workload": synced.get("owner_workload") or [],
        "mission_candidates": mission_candidates,
        "missions": missions,
        "mission_items": mission_items,
        "stored_mission_items": mission_items,
        "assignment_suggestions": assignment_suggestions,
        "escalation_suggestions": escalation_suggestions,
        "batch_draft_suggestions": batch_draft_suggestions,
        "team_candidate_count": _safe_int(synced.get("team_candidate_count"), default=0),
        "reused_capabilities": [
            "customer_pulse_cards",
            "pulse_snapshots",
            "tenant_scoped_access",
            "customer_pulse_rbac",
            "customer_pulse_audit",
            "customer_pulse_execution_log",
            "customer_pulse_activity_writeback",
        ],
    }


def build_followup_orchestrator_customer_payload(
    *,
    external_userid: str,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for customer-scoped followup view."""
    overview = build_followup_orchestrator_overview_payload(
        scope="team",
        external_userid=external_userid,
        limit=50,
        access_context=access_context,
    )
    if not overview.get("enabled"):
        return overview
    mission_items = [
        item
        for item in (overview.get("mission_items") or [])
        if _normalized_text((item or {}).get("external_userid")) == _normalized_text(external_userid)
    ]
    assignment_suggestions = [
        item
        for item in (overview.get("assignment_suggestions") or [])
        if _normalized_text((item or {}).get("external_userid")) == _normalized_text(external_userid)
    ]
    escalation_suggestions = [
        item
        for item in (overview.get("escalation_suggestions") or [])
        if _normalized_text((item or {}).get("external_userid")) == _normalized_text(external_userid)
    ]
    batch_draft_suggestions = []
    for suggestion in overview.get("batch_draft_suggestions") or []:
        if not isinstance(suggestion, dict):
            continue
        if any(_normalized_text((card or {}).get("external_userid")) == _normalized_text(external_userid) for card in (suggestion.get("cards") or [])):
            batch_draft_suggestions.append(dict(suggestion))
    return {
        "enabled": True,
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "feature_gate": overview.get("feature_gate"),
        "tenant_context": overview.get("tenant_context"),
        "access": overview.get("access"),
        "external_userid": _normalized_text(external_userid),
        "mission_items": mission_items,
        "assignment_suggestions": assignment_suggestions,
        "escalation_suggestions": escalation_suggestions,
        "batch_draft_suggestions": batch_draft_suggestions,
        "states": list(FOLLOWUP_ORCHESTRATOR_MISSION_STATES),
        "supported_action_types": list(FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS),
    }


def build_followup_orchestrator_my_missions_payload(
    *,
    actor_userid: str,
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for actor-scoped mission list projection."""
    context = _feature_gate_context(access_context)
    overview = build_followup_orchestrator_overview_payload(
        scope="team",
        limit=limit,
        auto_sync=auto_sync,
        access_context=context,
    )
    if not overview.get("enabled"):
        return overview
    tenant_key = _normalized_text((overview.get("tenant_context") or {}).get("tenant_key"))
    actor_value = _normalized_text(actor_userid) or _normalized_text(context.get("actor_userid") or context.get("user_id"))
    missions = repo.list_followup_orchestrator_missions_for_actor(
        tenant_key=tenant_key,
        actor_userid=actor_value,
        limit=limit,
    )
    mission_details = [get_followup_orchestrator_mission_detail_payload(mission_key=_normalized_text(item.get("mission_key")), access_context=context, tenant_key=tenant_key) for item in missions]
    return {
        **overview,
        "missions": [item for item in mission_details if item],
        "actor_userid": actor_value,
        "filters": {
            **dict(overview.get("filters") or {}),
            "scope": "mine",
            "owner_userid": actor_value,
        },
    }


def build_followup_orchestrator_team_board_payload(
    *,
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal owner for team-board projection."""
    return build_followup_orchestrator_overview_payload(
        scope="team",
        limit=limit,
        auto_sync=auto_sync,
        access_context=access_context,
    )


def get_followup_orchestrator_mission_detail_payload(
    *,
    mission_key: str,
    access_context: Mapping[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    """Internal owner for mission detail projection."""
    read_scope = _resolved_followup_read_scope(access_context=access_context)
    context = _feature_gate_context(access_context)
    resolved_tenant_key = _normalized_text(tenant_key) or _normalized_text(read_scope.get("tenant_key")) or _normalized_text(context.get("tenant_key")) or "aicrm"
    mission = repo.get_followup_orchestrator_mission_by_key(_normalized_text(mission_key), tenant_key=resolved_tenant_key)
    if not mission:
        raise LookupError("mission not found")
    items = repo.list_followup_orchestrator_mission_items(
        tenant_key=resolved_tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    _assert_mission_items_accessible(items, read_scope=read_scope)
    decisions = repo.list_followup_orchestrator_assignment_decisions(
        tenant_key=resolved_tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS,
    )
    decision_map = {
        int(item.get("mission_item_id") or 0): item
        for item in decisions
        if int(item.get("mission_item_id") or 0) > 0
    }
    decorated_items = [_decorate_item(item, decision=decision_map.get(int(item.get("id") or 0))) for item in items]
    logs = repo.list_followup_orchestrator_execution_logs(
        tenant_key=resolved_tenant_key,
        mission_id=int(mission.get("id") or 0),
        limit=50,
    )
    return apply_mission_ai_if_enabled(
        _decorate_mission(mission, items=decorated_items, decisions=decisions, logs=logs),
    )
