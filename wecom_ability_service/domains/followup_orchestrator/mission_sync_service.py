from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from .service import (
    FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS,
    FOLLOWUP_ORCHESTRATOR_HIGH_RISK_KEYS,
    FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD,
    FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD,
    FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD,
    FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS,
    _normalized_text,
    _parse_datetime,
    _sha_token,
)


def _collect_evidence_refs(cards: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    """Internal only: normalize and de-duplicate followup evidence refs."""
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for card in cards:
        for item in card.get("evidence_refs") or []:
            if not isinstance(item, dict):
                continue
            source_type = _normalized_text(item.get("sourceType"))
            source_id = _normalized_text(item.get("sourceId"))
            if not source_type or not source_id:
                continue
            dedupe_key = (source_type, source_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            refs.append(
                {
                    "sourceType": source_type,
                    "sourceId": source_id,
                    "title": _normalized_text(item.get("title")),
                    "eventTime": _normalized_text(item.get("eventTime")),
                }
            )
            if len(refs) >= limit:
                return refs
    return refs


def _build_owner_workload(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal only: materialize owner workload stats for sync/assignment."""
    grouped: dict[str, dict[str, Any]] = {}
    for card in cards:
        owner_userid = _normalized_text(card.get("owner_userid")) or "unassigned"
        entry = grouped.setdefault(
            owner_userid,
            {
                "owner_userid": owner_userid,
                "owner_display_name": _normalized_text(card.get("owner_display_name")) or owner_userid,
                "open_card_count": 0,
                "high_priority_count": 0,
                "overdue_count": 0,
                "draft_candidate_count": 0,
            },
        )
        entry["open_card_count"] += 1
        if _normalized_text(card.get("priority")) == "high":
            entry["high_priority_count"] += 1
        if bool(card.get("is_overdue")):
            entry["overdue_count"] += 1
        if _normalized_text(card.get("suggested_action_type")) == "generate_reply_draft":
            entry["draft_candidate_count"] += 1
    result = []
    for item in grouped.values():
        result.append(
            {
                **item,
                "is_overloaded": (
                    int(item.get("open_card_count") or 0) >= FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD
                    or int(item.get("high_priority_count") or 0)
                    >= FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD
                ),
            }
        )
    return sorted(
        result,
        key=lambda item: (
            -int(item.get("open_card_count") or 0),
            -int(item.get("high_priority_count") or 0),
            _normalized_text(item.get("owner_display_name")),
        ),
    )


def _team_candidate_owners(read_scope: Mapping[str, Any], owner_workload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal only: resolve team candidates for assignment decisions."""
    allowed_owner_userids = {
        _normalized_text(item)
        for item in (read_scope.get("allowed_owner_userids") or [])
        if _normalized_text(item)
    }
    if not allowed_owner_userids:
        allowed_owner_userids = {
            _normalized_text(item.get("owner_userid"))
            for item in owner_workload
            if _normalized_text(item.get("owner_userid")) and _normalized_text(item.get("owner_userid")) != "unassigned"
        }
    items = [
        item
        for item in owner_workload
        if _normalized_text(item.get("owner_userid")) in allowed_owner_userids
        and _normalized_text(item.get("owner_userid")) != "unassigned"
    ]
    return sorted(
        items,
        key=lambda item: (
            int(item.get("open_card_count") or 0),
            int(item.get("high_priority_count") or 0),
            _normalized_text(item.get("owner_userid")),
        ),
    )


def _first_signal_key(items: list[dict[str, Any]], *, field: str) -> str:
    """Internal only: return the first normalized signal key from structured flags."""
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalized_text(item.get(field))
        if normalized:
            return normalized
    return ""


def _card_intent_key(card: Mapping[str, Any]) -> str:
    """Internal only: derive a stable intent key for batching and assignment."""
    risk_key = _first_signal_key(card.get("risk_flags") or [], field="key")
    if risk_key:
        return f"risk:{risk_key}"
    opportunity_key = _first_signal_key(card.get("opportunity_flags") or [], field="key")
    if opportunity_key:
        return f"opportunity:{opportunity_key}"
    return _normalized_text(card.get("suggested_action_type")) or "general_followup"


def _batch_template_key(card: Mapping[str, Any]) -> str:
    """Internal only: derive a stable batch template hash from suggested action payload."""
    payload = dict(card.get("suggested_action_payload") or {})
    draft_message = _normalized_text(payload.get("draft_message"))
    if draft_message:
        return _sha_token(draft_message[:80], length=10)
    return _sha_token(_normalized_text(card.get("suggested_action_label")), length=10) or "generic"


def _is_high_risk_card(card: Mapping[str, Any]) -> bool:
    """Internal only: classify whether a pulse card hits followup high-risk keys."""
    return any(
        isinstance(item, dict) and _normalized_text(item.get("key")) in FOLLOWUP_ORCHESTRATOR_HIGH_RISK_KEYS
        for item in (card.get("risk_flags") or [])
    )


def _is_batchable_card(card: Mapping[str, Any]) -> bool:
    """Internal only: identify draft-batchable pulse cards."""
    if _is_high_risk_card(card):
        return False
    if _normalized_text(card.get("suggested_action_type")) != "generate_reply_draft":
        return False
    return not bool(card.get("draft_blocked_by_ai"))


def _due_urgency(card: Mapping[str, Any]) -> dict[str, Any]:
    """Internal only: calculate SLA urgency points for mission sync."""
    due_at = _parse_datetime(card.get("due_at") or card.get("snooze_until"))
    if not due_at:
        return {
            "due_at": "",
            "is_overdue": False,
            "is_due_soon": False,
            "sla_urgency_points": 0,
            "sla_urgency_label": "none",
        }
    now = datetime.now()
    if due_at <= now:
        return {
            "due_at": _normalized_text(card.get("due_at") or card.get("snooze_until")),
            "is_overdue": True,
            "is_due_soon": False,
            "sla_urgency_points": FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["overdue_bonus"],
            "sla_urgency_label": "overdue",
        }
    if due_at <= now + timedelta(hours=FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS):
        return {
            "due_at": _normalized_text(card.get("due_at") or card.get("snooze_until")),
            "is_overdue": False,
            "is_due_soon": True,
            "sla_urgency_points": FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["due_soon_bonus"],
            "sla_urgency_label": "due_soon",
        }
    return {
        "due_at": _normalized_text(card.get("due_at") or card.get("snooze_until")),
        "is_overdue": False,
        "is_due_soon": False,
        "sla_urgency_points": 0,
        "sla_urgency_label": "scheduled",
    }


def _card_signals(
    card: Mapping[str, Any],
    *,
    owner_workload_map: Mapping[str, Mapping[str, Any]],
    team_candidates: list[dict[str, Any]],
    untreated_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Internal only: derive mission sync/assignment signals from a pulse card."""
    owner_userid = _normalized_text(card.get("owner_userid"))
    due_signal = _due_urgency(card)
    current_owner_workload = dict(owner_workload_map.get(owner_userid) or {})
    high_risk = _is_high_risk_card(card)
    repeated_unhandled_count = int(untreated_counts.get(_normalized_text(card.get("external_userid"))) or 0)
    batchable = _is_batchable_card(card)
    schedule_score = float(card.get("priority_score") or 0) * FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["base_priority_multiplier"]
    reason_parts = [f"action_card_priority={round(float(card.get('priority_score') or 0), 2)}"]
    if due_signal["sla_urgency_points"]:
        schedule_score += due_signal["sla_urgency_points"]
        reason_parts.append(f"sla={due_signal['sla_urgency_label']}")
    if not owner_userid:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["missing_owner_bonus"]
        reason_parts.append("missing_owner")
    if bool(current_owner_workload.get("is_overloaded")):
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["owner_overload_bonus"]
        reason_parts.append("owner_overloaded")
    if high_risk:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["high_risk_bonus"]
        reason_parts.append("high_risk")
    if repeated_unhandled_count >= FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["repeat_unhandled_bonus"]
        reason_parts.append(f"repeat_unhandled={repeated_unhandled_count}")
    if batchable:
        schedule_score += FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS["batchable_bonus"]
        reason_parts.append("batchable")
    available_handoff_candidates = [
        item
        for item in team_candidates
        if _normalized_text(item.get("owner_userid")) != owner_userid and not bool(item.get("is_overloaded"))
    ]
    return {
        "priority_score": round(float(card.get("priority_score") or 0), 2),
        "schedule_score": round(schedule_score, 2),
        "due": due_signal,
        "has_owner": bool(owner_userid),
        "owner_userid": owner_userid,
        "owner_workload": current_owner_workload,
        "team_available_handoff_count": len(available_handoff_candidates),
        "team_available_handoffs": available_handoff_candidates[:5],
        "high_risk": high_risk,
        "batchable": batchable,
        "repeat_unhandled_count": repeated_unhandled_count,
        "rule_reasons": reason_parts,
        "intent_key": _card_intent_key(card),
        "template_key": _batch_template_key(card),
    }


def _batch_group_key(card: Mapping[str, Any], signals: Mapping[str, Any]) -> str:
    """Internal only: derive a stable batch grouping key for draft missions."""
    return "|".join(
        [
            _normalized_text(card.get("stage_key")) or "unknown_stage",
            _normalized_text(card.get("suggested_action_type")) or "unknown_action",
            _normalized_text(signals.get("intent_key")) or "general",
            _normalized_text(signals.get("template_key")) or "generic",
        ]
    )


def _sync_scope_label(read_scope: Mapping[str, Any], requested_scope: str) -> str:
    """Internal only: convert followup read scope into a stable sync scope label."""
    if _normalized_text(requested_scope) == "mine":
        actor_userid = _normalized_text(read_scope.get("actor_userid"))
        return actor_userid or "我的任务包"
    allowed_owner_userids = [_normalized_text(item) for item in (read_scope.get("allowed_owner_userids") or []) if _normalized_text(item)]
    if allowed_owner_userids:
        return f"团队({len(allowed_owner_userids)}人)"
    return "团队"


__all__ = [
    "_batch_group_key",
    "_batch_template_key",
    "_build_owner_workload",
    "_card_intent_key",
    "_card_signals",
    "_collect_evidence_refs",
    "_due_urgency",
    "_first_signal_key",
    "_is_batchable_card",
    "_is_high_risk_card",
    "_sync_scope_label",
    "_team_candidate_owners",
]
