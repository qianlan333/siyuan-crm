from __future__ import annotations

from typing import Any, Mapping

from .mission_sync_service import _batch_group_key, _collect_evidence_refs
from .service import (
    FOLLOWUP_ORCHESTRATOR_BATCH_MIN_SIZE,
    FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD,
    FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
    FOLLOWUP_ORCHESTRATOR_STABLE_ITEM_STATES,
    FOLLOWUP_ORCHESTRATOR_STABLE_MISSION_STATES,
    _normalized_text,
    _sha_token,
)


def _stable_item_status(existing_item: Mapping[str, Any] | None) -> str:
    """Internal only: preserve stable followup mission-item statuses during resync."""
    existing_status = _normalized_text((existing_item or {}).get("item_status"))
    if existing_status in FOLLOWUP_ORCHESTRATOR_STABLE_ITEM_STATES:
        return existing_status
    return ""


def _stable_mission_status(existing_mission: Mapping[str, Any] | None) -> str:
    """Internal only: preserve stable followup mission statuses during resync."""
    existing_status = _normalized_text((existing_mission or {}).get("mission_status"))
    if existing_status in FOLLOWUP_ORCHESTRATOR_STABLE_MISSION_STATES:
        return existing_status
    return ""


def _determine_assignment(card: Mapping[str, Any], signals: Mapping[str, Any], *, can_view_all: bool) -> dict[str, Any]:
    """Internal only: compute mission assignment suggestion from current signals."""
    owner_userid = _normalized_text(card.get("owner_userid"))
    available_handoffs = [dict(item) for item in (signals.get("team_available_handoffs") or []) if isinstance(item, dict)]
    target_owner = dict(available_handoffs[0] if available_handoffs else {})
    target_owner_userid = _normalized_text(target_owner.get("owner_userid"))
    target_owner_display_name = _normalized_text(target_owner.get("owner_display_name")) or target_owner_userid
    if not owner_userid:
        return {
            "decision_type": "claim",
            "assignment_status": "suggested",
            "needs_manager_approval": False,
            "suggested_assignee_userid": target_owner_userid,
            "suggested_assignee_display_name": target_owner_display_name,
            "reason": "当前客户没有 owner，建议由团队内负载较低的负责人认领。",
            "confidence": 0.72 if target_owner_userid else 0.48,
        }
    if bool((signals.get("owner_workload") or {}).get("is_overloaded")) and can_view_all and target_owner_userid:
        return {
            "decision_type": "reassign",
            "assignment_status": "suggested",
            "needs_manager_approval": True,
            "suggested_assignee_userid": target_owner_userid,
            "suggested_assignee_display_name": target_owner_display_name,
            "reason": "当前 owner 待办负载偏高，建议由同团队内负载更低的负责人接力。",
            "confidence": 0.63,
        }
    return {
        "decision_type": "",
        "assignment_status": "kept",
        "needs_manager_approval": False,
        "suggested_assignee_userid": owner_userid,
        "suggested_assignee_display_name": _normalized_text(card.get("owner_display_name")) or owner_userid,
        "reason": "当前 owner 仍可继续处理，不建议转派。",
        "confidence": 0.55,
    }


def _escalation_reason(card: Mapping[str, Any], signals: Mapping[str, Any]) -> dict[str, Any]:
    """Internal only: compute escalation reason from risk and untreated state."""
    reasons: list[str] = []
    high_risk = bool(signals.get("high_risk"))
    repeated_unhandled = int(signals.get("repeat_unhandled_count") or 0) >= FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD
    overdue = bool((signals.get("due") or {}).get("is_overdue"))
    if high_risk:
        reasons.append("命中高风险客户信号")
    if high_risk and overdue:
        reasons.append("已超 SLA")
    if repeated_unhandled:
        reasons.append("连续多次未处理")
    if not (high_risk or repeated_unhandled):
        return {"needs_escalation": False, "reason": "", "confidence": 0.0}
    return {
        "needs_escalation": True,
        "reason": "；".join(reasons),
        "confidence": 0.68 if high_risk else 0.52,
    }


def _mission_type_for_card(
    card: Mapping[str, Any],
    signals: Mapping[str, Any],
    *,
    batch_group_sizes: Mapping[str, int],
    can_view_all: bool,
) -> str:
    """Internal only: classify a card into the orchestrator mission bucket."""
    batch_group_key = _batch_group_key(card, signals)
    if bool(_escalation_reason(card, signals).get("needs_escalation")):
        return "risk_escalation_wave"
    if not bool(signals.get("has_owner")):
        return "claim_queue"
    assignment = _determine_assignment(card, signals, can_view_all=can_view_all)
    if _normalized_text(assignment.get("decision_type")) == "reassign":
        return "handoff_wave"
    if bool(signals.get("batchable")) and int(batch_group_sizes.get(batch_group_key) or 0) >= FOLLOWUP_ORCHESTRATOR_BATCH_MIN_SIZE:
        return "batch_draft_wave"
    return "priority_wave"


def _mission_key_for_card(
    card: Mapping[str, Any],
    signals: Mapping[str, Any],
    *,
    mission_type: str,
    scope_key: str,
    assignment: Mapping[str, Any],
) -> str:
    """Internal only: build a stable mission key for the card classification result."""
    if mission_type == "claim_queue":
        return f"mission:claim:{scope_key}"
    if mission_type == "handoff_wave":
        from_owner = _normalized_text(card.get("owner_userid")) or "unassigned"
        to_owner = _normalized_text(assignment.get("suggested_assignee_userid")) or "unassigned"
        return f"mission:handoff:{scope_key}:{from_owner}:{to_owner}"
    if mission_type == "risk_escalation_wave":
        return f"mission:escalation:{scope_key}"
    if mission_type == "batch_draft_wave":
        return f"mission:batch:{scope_key}:{_sha_token(_batch_group_key(card, signals), length=14)}"
    return f"mission:priority:{scope_key}"


def _mission_title(mission_type: str) -> str:
    """Internal only: render the title for a normalized mission type."""
    mapping = {
        "claim_queue": "待认领客户队列",
        "handoff_wave": "团队接力转派波次",
        "risk_escalation_wave": "风险升级波次",
        "batch_draft_wave": "批量草稿波次",
        "priority_wave": "今日优先推进任务包",
    }
    return mapping.get(_normalized_text(mission_type), "团队任务包")


def _mission_summary(mission_type: str, *, item_count: int, scope_label: str) -> str:
    """Internal only: render the summary copy for a mission."""
    mapping = {
        "claim_queue": f"{scope_label}内共有 {item_count} 位无 owner 客户待认领。",
        "handoff_wave": f"{scope_label}内共有 {item_count} 位客户建议转派接力。",
        "risk_escalation_wave": f"{scope_label}内共有 {item_count} 位客户需要升级处理。",
        "batch_draft_wave": f"{scope_label}内共有 {item_count} 位客户适合成批预生成草稿。",
        "priority_wave": f"{scope_label}内共有 {item_count} 位客户进入高优先级推进序列。",
    }
    return mapping.get(_normalized_text(mission_type), f"{scope_label}内共有 {item_count} 位客户进入团队任务包。")


def _mission_payload(
    mission_type: str,
    *,
    cards: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    assignment_suggestions: list[dict[str, Any]],
    escalation_suggestions: list[dict[str, Any]],
    batch_group_key: str = "",
    scope_key: str,
) -> dict[str, Any]:
    """Internal only: assemble the mission payload persisted by sync projection."""
    return {
        "rules_version": FOLLOWUP_ORCHESTRATOR_RULES_VERSION,
        "mission_type": mission_type,
        "scope_key": scope_key,
        "card_ids": [int(card.get("id") or 0) for card in cards],
        "pulse_snapshot_ids": [int((card.get("snapshot") or {}).get("id") or 0) for card in cards],
        "batch_group_key": _normalized_text(batch_group_key),
        "assignment_suggestions": assignment_suggestions,
        "escalation_suggestions": escalation_suggestions,
        "signals": signals,
        "evidence_refs": _collect_evidence_refs(cards, limit=8),
    }


def _summarize_mission_items(items: list[dict[str, Any]]) -> tuple[str, int]:
    """Internal only: summarize mission item statuses into a mission-level status."""
    if not items:
        return "suggested", 0
    statuses = {_normalized_text(item.get("item_status")) for item in items if _normalized_text(item.get("item_status"))}
    if statuses <= {"completed"}:
        return "completed", len(items)
    if "executing" in statuses:
        return "executing", len(items)
    if "approved" in statuses and statuses <= {"approved", "completed"}:
        return "approved", len(items)
    if "accepted" in statuses and statuses <= {"accepted", "completed"}:
        return "accepted", len(items)
    if "escalated" in statuses and statuses <= {"escalated", "completed", "skipped"}:
        return "escalated", len(items)
    if statuses <= {"skipped", "completed"}:
        return "skipped", len(items)
    if "unassigned" in statuses:
        return "unassigned", len(items)
    return "suggested", len(items)


__all__ = [
    "_determine_assignment",
    "_escalation_reason",
    "_mission_key_for_card",
    "_mission_payload",
    "_mission_summary",
    "_mission_title",
    "_mission_type_for_card",
    "_stable_item_status",
    "_stable_mission_status",
    "_summarize_mission_items",
]
