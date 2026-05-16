from __future__ import annotations

from typing import Any


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def list_registered_due_jobs() -> list[dict[str, Any]]:
    return [
        {
            "job_code": "sop",
            "label": "自动化转化 SOP",
            "frequency_minutes": 15,
            "description": "轮询未填问卷人群、运营中人群、已转化人群的 SOP day 模板，到点后按自然日批量发送。",
        },
        {
            "job_code": "conversion_workflow",
            "label": "自动化转化任务流",
            "frequency_minutes": 15,
            "description": "轮询启用中的自动化转化任务流节点，到点后按当前大人群和第 N 天执行发送。",
        },
        {
            "job_code": "operation_task",
            "label": "自动化运营任务",
            "frequency_minutes": 15,
            "description": "轮询启用中的运营任务，到点后按任务条件筛选人群并写入群发队列。",
        },
    ]


def _run_due_job(job_code: str, *, operator_id: str, operator_type: str) -> dict[str, Any]:
    normalized_operator = _normalized_text(operator_id) or "automation_conversion_due_runner"
    if job_code == "sop":
        from .sop_service import run_due_sop

        return run_due_sop(operator_id=normalized_operator, operator_type=operator_type)
    if job_code == "conversion_workflow":
        from .workflow_runtime import run_due_conversion_workflows

        return run_due_conversion_workflows(operator_id=normalized_operator, operator_type=operator_type)
    if job_code == "operation_task":
        from .operation_task_service import run_due_operation_tasks

        return run_due_operation_tasks(operator_id=normalized_operator)
    raise ValueError(f"unsupported due job runner: {job_code}")


def _summarize_due_job_payload(payload: dict[str, Any]) -> dict[str, int]:
    success_count = int(payload.get("total_success_count") or 0)
    skipped_count = int(payload.get("total_skipped_count") or 0)
    failed_count = int(payload.get("total_failed_count") or 0)
    if not success_count and not skipped_count and not failed_count:
        success_count += int(payload.get("enqueued_count") or 0)
        skipped_count += int(payload.get("skipped_count") or 0)
        failed_count += int(payload.get("failed_count") or 0)
        for execution_result in payload.get("executions") or []:
            execution_row = dict((execution_result or {}).get("execution") or {})
            success_count += int(execution_row.get("success_count") or 0)
            skipped_count += int(execution_row.get("skipped_count") or 0)
            failed_count += int(execution_row.get("failed_count") or 0)
    return {
        "success_count": success_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
    }


def run_registered_due_jobs(
    *,
    job_codes: list[str] | None = None,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    registry = {item["job_code"]: dict(item) for item in list_registered_due_jobs()}
    default_job_codes = list(registry.keys())
    selected_job_codes = [
        _normalized_text(item)
        for item in (job_codes if job_codes is not None else default_job_codes)
        if _normalized_text(item)
    ]
    if not selected_job_codes:
        selected_job_codes = default_job_codes

    invalid_job_codes = [item for item in selected_job_codes if item not in registry]
    if invalid_job_codes:
        raise ValueError(f"unsupported due jobs: {', '.join(sorted(dict.fromkeys(invalid_job_codes)))}")

    jobs_payload: list[dict[str, Any]] = []
    executed_job_count = 0
    failed_job_count = 0
    total_success_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    batch_ids: list[int] = []

    for job_code in selected_job_codes:
        definition = registry[job_code]
        try:
            payload = _run_due_job(
                job_code,
                operator_id=operator_id,
                operator_type=_normalized_text(operator_type) or "system",
            )
        except Exception as exc:
            failed_job_count += 1
            jobs_payload.append({**definition, "ok": False, "error": str(exc)})
            continue

        executed_job_count += 1
        summary = _summarize_due_job_payload(payload)
        total_success_count += summary["success_count"]
        total_skipped_count += summary["skipped_count"]
        total_failed_count += summary["failed_count"]
        batch_ids.extend(int(item) for item in (payload.get("batch_ids") or []) if int(item or 0))
        jobs_payload.append({**definition, "ok": bool(payload.get("ok")), "result": payload})

    return {
        "ok": failed_job_count == 0,
        "operator_type": _normalized_text(operator_type) or "system",
        "operator_id": _normalized_text(operator_id) or "automation_conversion_due_runner",
        "requested_job_codes": selected_job_codes,
        "executed_job_count": executed_job_count,
        "failed_job_count": failed_job_count,
        "total_success_count": total_success_count,
        "total_skipped_count": total_skipped_count,
        "total_failed_count": total_failed_count,
        "batch_ids": list(dict.fromkeys(batch_ids)),
        "jobs": jobs_payload,
    }
