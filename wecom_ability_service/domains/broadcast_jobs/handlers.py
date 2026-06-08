"""broadcast_jobs handler registry — worker 按 source_type 路由到各 domain 的执行逻辑。

每种 source_type 注册一个 handler(job) → result dict。
handler 负责真发 + 写 side effect（delivery log / progress / batch counters），
caller（worker）只管 mark_sent / mark_failed。

result 约定：
  {"ok": True, "sent_count": N, "failed_count": M, "outbound_task_id": id_or_None}
  {"ok": False, "error": "reason"}
"""
from __future__ import annotations

from typing import Any, Callable


HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]

_REGISTRY: dict[str, HandlerFn] = {}


def register(source_type: str):
    def decorator(fn: HandlerFn) -> HandlerFn:
        _REGISTRY[source_type] = fn
        return fn
    return decorator


def execute_job(job: dict[str, Any]) -> dict[str, Any]:
    source_type = str(job.get("source_type") or "").strip()
    handler = _REGISTRY.get(source_type, _handle_generic)
    try:
        return handler(job)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Generic handler (fallback) — dispatch_wecom_task via content_payload
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_generic(job: dict[str, Any]) -> dict[str, Any]:
    from ..tasks.service import dispatch_wecom_task_with_intent

    payload = job.get("content_payload") or {}
    fn_name = str(payload.get("fn_name") or "").strip()
    wecom_payload = payload.get("wecom_payload") or {}
    if not fn_name or not isinstance(wecom_payload, dict):
        return {"ok": False, "error": "content_payload missing fn_name or wecom_payload"}

    task_type = f"broadcast_job/{job.get('source_type', 'manual')}"
    existing_outbound_task_id = int(job.get("outbound_task_id") or 0)
    if existing_outbound_task_id:
        return {
            "ok": True,
            "sent_count": int(job.get("target_count") or 0),
            "failed_count": 0,
            "outbound_task_id": existing_outbound_task_id,
        }
    result = dispatch_wecom_task_with_intent(
        task_type,
        fn_name,
        wecom_payload,
        broadcast_job_id=int(job.get("id") or 0) or None,
        trace_id=str(job.get("trace_id") or ""),
    )
    return {
        "ok": True,
        "sent_count": int(job.get("target_count") or 0),
        "failed_count": 0,
        "outbound_task_id": int(result.get("task_id") or 0) or None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# focus_send handler — 逐个 push_openclaw + update batch item status
# ═══════════════════════════════════════════════════════════════════════════════

@register("focus_send")
def _handle_focus_send(job: dict[str, Any]) -> dict[str, Any]:
    from ..automation_conversion.focus_send_service import run_focus_send_job

    payload = job.get("content_payload") or {}
    batch_id = int(payload.get("batch_id") or 0)
    if not batch_id:
        return {"ok": False, "error": "focus_send job missing batch_id"}
    result = run_focus_send_job(batch_id=batch_id)
    return {
        "ok": result.get("ok", False),
        "sent_count": int(result.get("sent_count") or 0),
        "failed_count": int(result.get("failed_count") or 0),
        "outbound_task_id": None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# campaign handler — dispatch batch via scheduler
# ═══════════════════════════════════════════════════════════════════════════════

@register("campaign")
def _handle_campaign(job: dict[str, Any]) -> dict[str, Any]:
    from ..campaigns.scheduler import run_campaign_batch

    payload = dict(job.get("content_payload") or {})
    payload["broadcast_job_id"] = int(job.get("id") or 0) or None
    payload["resume_outbound_task_id"] = int(job.get("outbound_task_id") or 0) or None
    # 预排期 job 没有 request_payload，run_campaign_batch 会现场 resolve
    if not payload.get("request_payload") and not payload.get("campaign"):
        return {"ok": False, "error": "campaign job missing request_payload"}
    return run_campaign_batch(batch_data=payload)


# ═══════════════════════════════════════════════════════════════════════════════
# SOP handler — dispatch batch + record items + finalize
# ═══════════════════════════════════════════════════════════════════════════════

@register("sop")
def _handle_sop(job: dict[str, Any]) -> dict[str, Any]:
    from ..automation_conversion.sop_service import run_sop_batch

    payload = job.get("content_payload") or {}
    if not payload.get("batch_id"):
        return {"ok": False, "error": "sop job missing batch_id"}
    return run_sop_batch(batch_data=payload)


# ═══════════════════════════════════════════════════════════════════════════════
# workflow handler
# ═══════════════════════════════════════════════════════════════════════════════

@register("workflow")
def _handle_workflow(job: dict[str, Any]) -> dict[str, Any]:
    from ..automation_conversion.workflow_runtime import run_workflow_execution, run_pre_scheduled_workflow_node
    from ..tasks.service import dispatch_wecom_group_task_with_intent

    payload = job.get("content_payload") or {}
    if str(payload.get("channel") or "").strip() == "wecom_customer_group":
        existing_outbound_task_id = int(job.get("outbound_task_id") or 0)
        if existing_outbound_task_id:
            from ..tasks.service import assert_group_outbound_exact_target_verified

            assert_group_outbound_exact_target_verified(existing_outbound_task_id)
            return {
                "ok": True,
                "sent_count": len(payload.get("chat_ids") or []),
                "failed_count": 0,
                "outbound_task_id": existing_outbound_task_id,
            }
        result = dispatch_wecom_group_task_with_intent(
            "broadcast_job/group_ops",
            payload,
            broadcast_job_id=int(job.get("id") or 0) or None,
            trace_id=str(job.get("trace_id") or ""),
        )
        return {
            "ok": True,
            "sent_count": len(payload.get("chat_ids") or []),
            "failed_count": 0,
            "outbound_task_id": int(result.get("task_id") or 0) or None,
        }
    # 预排期的 job 没有 execution_id，到期后走完整 node 执行流程
    if payload.get("pre_scheduled"):
        workflow_id = int(payload.get("workflow_id") or 0)
        node_id = int(payload.get("node_id") or 0)
        if not workflow_id or not node_id:
            return {"ok": False, "error": "pre_scheduled workflow job missing workflow_id or node_id"}
        return run_pre_scheduled_workflow_node(workflow_id=workflow_id, node_id=node_id)
    if not payload.get("execution_id"):
        return {"ok": False, "error": "workflow job missing execution_id"}
    return run_workflow_execution(execution_data=payload)


# ═══════════════════════════════════════════════════════════════════════════════
# operation_task handler — 单任务模型真发 + 回写执行明细
# ═══════════════════════════════════════════════════════════════════════════════

@register("operation_task")
def _handle_operation_task(job: dict[str, Any]) -> dict[str, Any]:
    from ..automation_conversion.operation_task_service import run_operation_task_broadcast_job

    return run_operation_task_broadcast_job(job)


# ═══════════════════════════════════════════════════════════════════════════════
# cloud_plan handler (same as campaign — after confirm it's a wecom dispatch)
# ═══════════════════════════════════════════════════════════════════════════════

@register("cloud_plan")
def _handle_cloud_plan(job: dict[str, Any]) -> dict[str, Any]:
    from ..cloud_orchestrator.broadcast_planner import execute_recipient_messages

    payload = job.get("content_payload") or {}
    plan_id = str(payload.get("plan_id") or "").strip()
    if not plan_id:
        return {"ok": False, "error": "cloud_plan job missing plan_id"}
    recipient_id = payload.get("recipient_id")
    if recipient_id:
        return execute_recipient_messages(
            plan_id=plan_id,
            recipient_id=int(recipient_id),
            broadcast_job_id=int(job.get("id") or 0) or None,
        )
    return {"ok": False, "error": "cloud_plan bulk job is disabled; approve an individual recipient"}


# ═══════════════════════════════════════════════════════════════════════════════
# deferred handler
# ═══════════════════════════════════════════════════════════════════════════════

@register("deferred")
def _handle_deferred(job: dict[str, Any]) -> dict[str, Any]:
    return _handle_generic(job)
