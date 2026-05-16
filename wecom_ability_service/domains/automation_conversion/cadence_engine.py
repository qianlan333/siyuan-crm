"""节奏引擎 — 评估 workflow_node_transition 决定下一步行动。

设计要点：
- 复用现有 ``automation_workflow_node`` / ``automation_workflow_execution_item`` 骨架
- 在每个 execution_item 完成（sent / failed / replied）后，按 ``automation_workflow_node_transition``
  规则评估"该走 to_node、还是停在沉默池、或升级人工"
- ``ai_decision`` kind 留给 Cloud 端介入（通过 MCP tool 由外部 Agent 评估）
- 这一层不主动调度，只提供推进函数；调度由 ``run_automation_sop.py`` 或
  ``run_cloud_orchestrator_scan.py`` 在合适时机触发

支持的 ``condition_kind``：
- ``reply_received``    — 用户在 ``automation_reply_monitor_queue`` 有最近 inbound
- ``no_reply_within_days`` — 自上次 sent 起 N 天无 inbound（payload: ``{"days": 7}``）
- ``budget_exhausted``  — 当前频次预算用尽
- ``profile_match``     — 画像匹配（payload: ``{"profile_segment_keys": [...]}``）
- ``ai_decision``       — Cloud 端 AI 评估（payload: ``{"agent_code": "..."}``）
- ``always``            — 无条件（默认 fallthrough）

支持的 ``action``：
- ``goto_node``         — 跳转到 to_node_id（写 execution_item.next_node_id）
- ``mark_silent``       — 把 member 移入静默池
- ``escalate_human``    — 标记需要人工接手（写 review queue）
- ``exit_workflow``     — 退出当前 workflow
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ...db import get_db


logger = logging.getLogger(__name__)


CONDITION_REPLY_RECEIVED = "reply_received"
CONDITION_NO_REPLY_WITHIN_DAYS = "no_reply_within_days"
CONDITION_BUDGET_EXHAUSTED = "budget_exhausted"
CONDITION_PROFILE_MATCH = "profile_match"
CONDITION_AI_DECISION = "ai_decision"
CONDITION_ALWAYS = "always"

ACTION_GOTO_NODE = "goto_node"
ACTION_MARK_SILENT = "mark_silent"
ACTION_ESCALATE_HUMAN = "escalate_human"
ACTION_EXIT_WORKFLOW = "exit_workflow"


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class TransitionDecision:
    """单次 transition 评估结果。"""

    transition_id: int
    condition_kind: str
    action: str
    to_node_id: int | None
    matched: bool
    reason: str
    payload: dict[str, Any]


def _load_transitions_for_node(node_id: int) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, from_node_id, to_node_id, condition_kind,
               condition_payload_json, action, priority
        FROM automation_workflow_node_transition
        WHERE from_node_id = ? AND enabled
        ORDER BY priority DESC, id ASC
        """,
        (int(node_id),),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def _has_recent_inbound(member_id: int, since_iso: str = "") -> bool:
    db = get_db()
    cur = db.cursor()
    if since_iso:
        cur.execute(
            """
            SELECT 1 FROM automation_reply_monitor_queue
            WHERE member_id = ? AND last_inbound_at >= ?
            ORDER BY id DESC LIMIT 1
            """,
            (int(member_id), str(since_iso)),
        )
    else:
        cur.execute(
            """
            SELECT 1 FROM automation_reply_monitor_queue
            WHERE member_id = ? AND last_inbound_at <> ''
            ORDER BY id DESC LIMIT 1
            """,
            (int(member_id),),
        )
    return cur.fetchone() is not None


def _last_outbound_at(member_id: int) -> str:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT MAX(sent_at) AS last_at FROM automation_touch_delivery_log
        WHERE member_id = ? AND status = 'sent'
        """,
        (int(member_id),),
    )
    row = cur.fetchone()
    return str(row["last_at"] or "") if row else ""


def _evaluate_condition(
    *,
    condition_kind: str,
    payload: dict[str, Any],
    member_id: int,
    member_row: dict[str, Any],
) -> tuple[bool, str]:
    if condition_kind == CONDITION_ALWAYS:
        return True, "always"
    if condition_kind == CONDITION_REPLY_RECEIVED:
        last_out = _last_outbound_at(member_id)
        ok = _has_recent_inbound(member_id, since_iso=last_out)
        return ok, ("reply_after_last_outbound" if ok else "no_reply_yet")
    if condition_kind == CONDITION_NO_REPLY_WITHIN_DAYS:
        days = int(payload.get("days") or 7)
        last_out = _last_outbound_at(member_id)
        if not last_out:
            return False, "never_sent"
        # 看 last_out 之后的 inbound
        if _has_recent_inbound(member_id, since_iso=last_out):
            return False, "reply_received"
        # 计算 last_out 是否已超 days
        try:
            cutoff = datetime.fromisoformat(last_out.replace("Z", "+00:00"))
        except ValueError:
            return False, f"invalid_last_outbound:{last_out}"
        if (_utc_now_naive() - cutoff.replace(tzinfo=None)) >= timedelta(days=days):
            return True, f"silence_for_{days}_days"
        return False, f"within_{days}_days"
    if condition_kind == CONDITION_BUDGET_EXHAUSTED:
        from ..marketing_automation.frequency_budget_service import check_member_budget

        external = str(member_row.get("external_contact_id") or "")
        verdict = check_member_budget(
            member_id=member_id,
            external_contact_id=external,
            channels=tuple(payload.get("channels") or ("wecom_private",)),
            program_codes=tuple(payload.get("program_codes") or ()),
            pool_keys=tuple(payload.get("pool_keys") or ()),
        )
        return (not verdict.allowed), verdict.skip_reason or "budget_ok"
    if condition_kind == CONDITION_PROFILE_MATCH:
        wanted = set(payload.get("profile_segment_keys") or [])
        actual = str(member_row.get("profile_segment_key") or "")
        ok = actual in wanted if wanted else False
        return ok, f"profile={actual}"
    if condition_kind == CONDITION_AI_DECISION:
        # 由 Cloud 端外部 Agent 通过 evaluate_transition tool 回写决策
        # 在没有回写时返回 False（待评估）
        decision = payload.get("ai_decision_cached")
        if isinstance(decision, dict):
            return bool(decision.get("matched")), str(decision.get("reason") or "ai_cached")
        return False, "pending_ai_decision"
    return False, f"unknown_condition:{condition_kind}"


def _load_member(member_id: int) -> dict[str, Any]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, external_contact_id, phone, current_pool, current_audience_code,
               profile_segment_key, behavior_tier_key
        FROM automation_member WHERE id = ?
        """,
        (int(member_id),),
    )
    row = cur.fetchone()
    return dict(row) if row else {}


def evaluate_node_transitions(
    *,
    member_id: int,
    from_node_id: int,
) -> TransitionDecision | None:
    """对一个完成的 node 评估其 transitions，返回第一个匹配的决策。

    transitions 按 (priority DESC, id ASC) 顺序，第一个 matched 即返回。
    若全部不匹配，返回 None（外层调用方决定是否原地等待 / fall-through）。
    """
    transitions = _load_transitions_for_node(from_node_id)
    if not transitions:
        return None
    member_row = _load_member(member_id)
    for t in transitions:
        try:
            payload = json.loads(t.get("condition_payload_json") or "{}")
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        matched, reason = _evaluate_condition(
            condition_kind=str(t.get("condition_kind") or ""),
            payload=payload,
            member_id=int(member_id),
            member_row=member_row,
        )
        if not matched:
            continue
        return TransitionDecision(
            transition_id=int(t["id"]),
            condition_kind=str(t.get("condition_kind") or ""),
            action=str(t.get("action") or ACTION_EXIT_WORKFLOW),
            to_node_id=(int(t["to_node_id"]) if t.get("to_node_id") else None),
            matched=True,
            reason=reason,
            payload=payload,
        )
    return None


def apply_transition_action(
    *,
    decision: TransitionDecision,
    member_id: int,
    execution_item_id: int | None = None,
) -> dict[str, Any]:
    """落地 transition 决策的副作用。

    返回 {"action": ..., "applied": bool, "details": {...}}
    """
    db = get_db()
    cur = db.cursor()
    if decision.action == ACTION_GOTO_NODE:
        if not decision.to_node_id:
            return {"action": decision.action, "applied": False, "details": {"reason": "no_to_node"}}
        if execution_item_id:
            cur.execute(
                "UPDATE automation_workflow_execution_item "
                "SET next_node_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(decision.to_node_id), int(execution_item_id)),
            )
            db.commit()
        return {
            "action": decision.action,
            "applied": True,
            "details": {"to_node_id": decision.to_node_id},
        }
    if decision.action == ACTION_MARK_SILENT:
        cur.execute(
            "UPDATE automation_member SET current_pool = 'silent', "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(member_id),),
        )
        db.commit()
        return {"action": decision.action, "applied": True, "details": {"member_id": member_id}}
    if decision.action == ACTION_ESCALATE_HUMAN:
        if execution_item_id:
            cur.execute(
                "UPDATE automation_workflow_execution_item "
                "SET status = 'failed', last_error_text = ?, last_error_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (f"escalated:{decision.reason}", int(execution_item_id)),
            )
            db.commit()
        return {"action": decision.action, "applied": True, "details": {"reason": decision.reason}}
    if decision.action == ACTION_EXIT_WORKFLOW:
        if execution_item_id:
            cur.execute(
                "UPDATE automation_workflow_execution_item "
                "SET status = 'skipped', last_error_text = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (f"exit:{decision.reason}", int(execution_item_id)),
            )
            db.commit()
        return {"action": decision.action, "applied": True, "details": {"reason": decision.reason}}
    return {"action": decision.action, "applied": False, "details": {"reason": "unknown_action"}}


def progress_execution_item(
    *,
    execution_item_id: int,
) -> dict[str, Any]:
    """高层入口：对一个完成的 execution_item，评估并落地下一步。

    返回 {"item_id": ..., "decision": {...} | None, "applied": {...}}
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, member_id, node_id, status
        FROM automation_workflow_execution_item WHERE id = ?
        """,
        (int(execution_item_id),),
    )
    row = cur.fetchone()
    if not row:
        return {"item_id": execution_item_id, "decision": None, "applied": None, "error": "not_found"}
    member_id = int(row["member_id"] or 0)
    from_node_id = int(row["node_id"] or 0)
    if not member_id or not from_node_id:
        return {"item_id": execution_item_id, "decision": None, "applied": None, "error": "missing_member_or_node"}
    decision = evaluate_node_transitions(
        member_id=member_id, from_node_id=from_node_id
    )
    if not decision:
        return {"item_id": execution_item_id, "decision": None, "applied": None}
    applied = apply_transition_action(
        decision=decision,
        member_id=member_id,
        execution_item_id=int(execution_item_id),
    )
    logger.info(
        "transition applied item_id=%s from_node=%s action=%s reason=%s",
        execution_item_id,
        from_node_id,
        decision.action,
        decision.reason,
    )
    return {
        "item_id": execution_item_id,
        "decision": {
            "transition_id": decision.transition_id,
            "condition_kind": decision.condition_kind,
            "action": decision.action,
            "to_node_id": decision.to_node_id,
            "reason": decision.reason,
        },
        "applied": applied,
    }


def cache_ai_decision(
    *,
    transition_id: int,
    matched: bool,
    reason: str = "",
) -> None:
    """让 Cloud 端 AI 把"该走 to_node 或不"的判断回写到 transition.condition_payload_json。

    下次 evaluate 时直接命中 ``ai_decision_cached``，避免每次都跑 AI。
    缓存默认有效一次（用完清空）；这里先写不清空，由调用方自管。
    """
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT condition_payload_json FROM automation_workflow_node_transition WHERE id = ?",
        (int(transition_id),),
    )
    row = cur.fetchone()
    if not row:
        return
    try:
        payload = json.loads(row["condition_payload_json"] or "{}")
    except (TypeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["ai_decision_cached"] = {
        "matched": bool(matched),
        "reason": reason or "",
        "decided_at": _utc_now_naive().isoformat(),
    }
    cur.execute(
        "UPDATE automation_workflow_node_transition SET condition_payload_json = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(payload, ensure_ascii=False), int(transition_id)),
    )
    db.commit()


__all__ = [
    "TransitionDecision",
    "evaluate_node_transitions",
    "apply_transition_action",
    "progress_execution_item",
    "cache_ai_decision",
    "CONDITION_REPLY_RECEIVED",
    "CONDITION_NO_REPLY_WITHIN_DAYS",
    "CONDITION_BUDGET_EXHAUSTED",
    "CONDITION_PROFILE_MATCH",
    "CONDITION_AI_DECISION",
    "CONDITION_ALWAYS",
    "ACTION_GOTO_NODE",
    "ACTION_MARK_SILENT",
    "ACTION_ESCALATE_HUMAN",
    "ACTION_EXIT_WORKFLOW",
]
