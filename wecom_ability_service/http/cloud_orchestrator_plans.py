from __future__ import annotations

from flask import Response, jsonify, request

from ..domains.cloud_orchestrator import (
    approval_token as approval_token_module,
    audit as audit_module,
    broadcast_planner,
)


def cloud_orchestrator_create_plan() -> Response:
    """不走 LLM、直接由前端选好筛选条件创建 plan（开箱即用兜底通道）。"""

    body = request.get_json(silent=True) or {}
    try:
        result = broadcast_planner.draft_broadcast_plan(
            intent=str(body.get("intent") or ""),
            selection=dict(body.get("selection") or {}),
            content_strategy=str(body.get("content_strategy") or "profile_layered"),
            content_template=str(body.get("content_template") or ""),
            personalization=list(body.get("personalization") or []),
            attachments=list(body.get("attachments") or []),
            max_recipients=int(body.get("max_recipients") or 0),
            operator=str(body.get("operator") or "ui_user"),
            scenario_code=str(body.get("scenario_code") or "bulk_activation"),
            auto_copy_workorder=bool(body.get("auto_copy_workorder", True)),
        )
        return jsonify({"ok": True, "plan": result})
    except (ValueError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_list_plans() -> Response:
    status = (request.args.get("status") or "").strip()
    limit = int(request.args.get("limit") or 20)
    rows = broadcast_planner.list_recent_plans(status=status, limit=limit)
    return jsonify({"ok": True, "plans": rows})


def cloud_orchestrator_get_plan(plan_id: str) -> Response:
    plan = broadcast_planner.get_plan(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    return jsonify({"ok": True, "plan": plan})


def cloud_orchestrator_simulate_plan(plan_id: str) -> Response:
    try:
        result = broadcast_planner.simulate_broadcast(plan_id=plan_id)
        return jsonify({"ok": True, "simulation": result})
    except (ValueError, LookupError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_approve_plan(plan_id: str) -> Response:
    body = request.get_json(silent=True) or {}
    operator = str(body.get("operator") or "").strip()
    if not operator:
        return jsonify({"ok": False, "error": "operator is required"}), 400
    plan = broadcast_planner.get_plan(plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    if plan["status"] not in ("draft", "simulated"):
        return jsonify(
            {"ok": False, "error": f"plan_not_approvable status={plan['status']}"}
        ), 400
    result = approval_token_module.issue_token(
        plan_id=plan_id,
        operator=operator,
        ttl_seconds=int(body.get("ttl_seconds") or 300),
        metadata={"intent": plan.get("intent", "")[:200]},
    )
    return jsonify({"ok": True, "approval": result})


def cloud_orchestrator_commit_plan(plan_id: str) -> Response:
    body = request.get_json(silent=True) or {}
    token = str(body.get("approval_token") or "").strip()
    approver = str(body.get("human_approver") or "").strip()
    confirm = bool(body.get("confirm"))
    if not token or not approver:
        return jsonify({"ok": False, "error": "approval_token and human_approver are required"}), 400
    if not confirm:
        return jsonify({"ok": False, "error": "confirm must be true"}), 400
    try:
        result = broadcast_planner.commit_broadcast_plan(
            plan_id=plan_id,
            confirm=confirm,
            human_approver=approver,
            approval_token_value=token,
        )
        return jsonify({"ok": True, "commit": result})
    except (ValueError, LookupError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def cloud_orchestrator_reject_plan(plan_id: str) -> Response:
    body = request.get_json(silent=True) or {}
    reason = str(body.get("reason") or "").strip()
    ok = broadcast_planner.reject_broadcast_plan(plan_id=plan_id, reason=reason)
    return jsonify({"ok": ok})


def cloud_orchestrator_audit() -> Response:
    session_id = (request.args.get("session_id") or "").strip()
    trace_id = (request.args.get("trace_id") or "").strip()
    limit = int(request.args.get("limit") or 500)
    rows = audit_module.list_recent_audit(
        session_id=session_id,
        trace_id=trace_id,
        limit=limit,
    )
    return jsonify({"ok": True, "audit": rows})


def cloud_orchestrator_observability() -> Response:
    """监控数据汇总：plan 漏斗 / 审计错误 / Cloud 调用延迟分位。"""

    return jsonify({"ok": True, **audit_module.build_observability_payload()})


__all__ = [
    "cloud_orchestrator_approve_plan",
    "cloud_orchestrator_audit",
    "cloud_orchestrator_commit_plan",
    "cloud_orchestrator_create_plan",
    "cloud_orchestrator_get_plan",
    "cloud_orchestrator_list_plans",
    "cloud_orchestrator_observability",
    "cloud_orchestrator_reject_plan",
    "cloud_orchestrator_simulate_plan",
]
