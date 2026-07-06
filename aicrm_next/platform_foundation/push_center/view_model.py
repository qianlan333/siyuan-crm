from __future__ import annotations

from typing import Any

from . import ROUTE_OWNER
from .projection import EFFECTIVE_STATUS_LABELS
from .repository import PushCenterRepository
from .status_mapper import status_definitions_payload

FILTER_KEYS = (
    "section",
    "effect_type",
    "status",
    "business_type",
    "business_id",
    "target_type",
    "target_id",
    "external_userid",
    "owner_userid",
    "trace_id",
    "idempotency_key",
    "source_module",
    "source_route",
    "created_from",
    "created_to",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def push_center_filters(params: dict[str, Any] | None = None) -> dict[str, str]:
    raw = dict(params or {})
    return {key: _text(raw.get(key)) for key in FILTER_KEYS}


def public_filters(filters: dict[str, Any]) -> dict[str, str]:
    return {key: _text(value) for key, value in filters.items() if _text(value)}


def job_list_item(job: dict[str, Any], *, include_linked_records: bool = False) -> dict[str, Any]:
    payload = dict(job)
    if not include_linked_records:
        payload.pop("linked_records", None)
    payload.setdefault("effective_status", payload.get("status"))
    payload.setdefault("effective_status_label", EFFECTIVE_STATUS_LABELS.get(_text(payload.get("effective_status")), _text(payload.get("status_label"))))
    payload.setdefault("status_label", payload.get("effective_status_label"))
    return payload


def build_sections_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    return {
        "ok": True,
        "sections": repository.sections(filters),
        "status_definitions": status_definitions_payload(),
        "filters": public_filters(filters),
        "route_owner": ROUTE_OWNER,
    }


def build_jobs_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    limit = _int((params or {}).get("limit"), default=50, minimum=1, maximum=200)
    offset = _int((params or {}).get("offset"), default=0, minimum=0, maximum=100000)
    jobs, total = repository.list_jobs(filters, limit=limit, offset=offset)
    return {
        "ok": True,
        "items": [job_list_item(job) for job in jobs],
        "total": total,
        "counts": repository.counts(filters),
        "sections": repository.sections(filters),
        "status_definitions": status_definitions_payload(),
        "filters": public_filters(filters),
        "limit": limit,
        "offset": offset,
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_stats_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    return {
        "ok": True,
        "counts": repository.counts(filters),
        "sections": repository.sections(filters),
        "status_definitions": status_definitions_payload(),
        "filters": public_filters(filters),
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_job_detail_payload(job_id: int | str, *, repository: PushCenterRepository | None = None) -> dict[str, Any] | None:
    repository = repository or PushCenterRepository()
    job = repository.get_job(job_id)
    if not job:
        return None
    job_payload = job_list_item(job, include_linked_records=True)
    linked_records = job_payload.get("linked_records") if isinstance(job_payload.get("linked_records"), dict) else {}
    return {
        "ok": True,
        "job": job_payload,
        "attempts": list(linked_records.get("external_effect_attempts") or repository.list_attempts(job_id)),
        "linked_records": linked_records,
        "source": {
            "source_type": "push_center_projection",
            "external_effect_job_missing": False,
            "legacy_readonly": False,
        },
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def _raw_statuses(records: list[dict[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for record in records:
        status = _text(record.get("raw_status") or record.get("status"))
        if status:
            statuses.append(status)
    return statuses


def _last_error(job: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, str]:
    for source in [job, *list(reversed(attempts))]:
        code = _text(source.get("last_error_code") or source.get("error_code"))
        message = _text(source.get("last_error_message") or source.get("error_message"))
        if code or message:
            return {"code": code, "message": message}
    return {"code": "", "message": ""}


def _reconciliation_decision(job: dict[str, Any], attempts: list[dict[str, Any]], linked_records: dict[str, Any]) -> dict[str, Any]:
    effective_status = _text(job.get("effective_status") or job.get("status"))
    raw_statuses = {
        "external_effect_jobs": _raw_statuses(list(linked_records.get("external_effect_jobs") or [])),
        "broadcast_jobs": _raw_statuses(list(linked_records.get("broadcast_jobs") or [])),
        "attempts": _raw_statuses(attempts),
    }
    retryable = "failed_retryable" in raw_statuses["external_effect_jobs"] or "failed_retryable" in raw_statuses["attempts"]
    has_broadcast_sent = "sent" in raw_statuses["broadcast_jobs"]
    has_attempt_failure = any(status in {"failed", "failed_retryable", "failed_terminal", "blocked", "cancelled"} for status in raw_statuses["attempts"])

    if effective_status == "sent":
        return {
            "business_explanation": "主发送链路已完成，当前不需要运营处理。",
            "retryable": False,
            "operator_action_required": False,
            "next_action_label": "无需操作",
        }
    if effective_status == "sent_with_shadow_warning":
        return {
            "business_explanation": "主发送链路已完成，但影子链路或观测链路存在异常；不要把它误判为业务发送失败。",
            "retryable": False,
            "operator_action_required": True,
            "next_action_label": "检查影子链路",
        }
    if effective_status == "shadow_failed_not_business_failed":
        return {
            "business_explanation": "仅发现影子链路失败，尚未发现对应主发送记录；需要确认主发送是否由其他链路完成。",
            "retryable": False,
            "operator_action_required": True,
            "next_action_label": "确认主发送记录",
        }
    if effective_status == "failed":
        return {
            "business_explanation": "主发送或外部动作未成功完成；请根据错误原因决定重试或人工处理。",
            "retryable": retryable,
            "operator_action_required": True,
            "next_action_label": "重试" if retryable else "人工处理",
        }
    if effective_status == "running":
        return {
            "business_explanation": "任务已被调度器或外部动作 worker 领取，等待执行结果。",
            "retryable": False,
            "operator_action_required": False,
            "next_action_label": "等待执行完成",
        }
    return {
        "business_explanation": "任务已进入推送中心，等待调度器扫描、审批或前置条件满足。",
        "retryable": False,
        "operator_action_required": bool(has_attempt_failure and not has_broadcast_sent),
        "next_action_label": "等待调度",
    }


def build_job_reconciliation_payload(job_id: int | str, *, repository: PushCenterRepository | None = None) -> dict[str, Any] | None:
    detail = build_job_detail_payload(job_id, repository=repository)
    if not detail:
        return None
    job = dict(detail.get("job") or {})
    linked_records = dict(detail.get("linked_records") or {})
    attempts = list(detail.get("attempts") or [])
    decision = _reconciliation_decision(job, attempts, linked_records)
    linked_record_counts = dict(job.get("linked_record_counts") or {})
    external_jobs = list(linked_records.get("external_effect_jobs") or [])
    broadcast_jobs = list(linked_records.get("broadcast_jobs") or [])
    outbound_tasks = list(linked_records.get("outbound_tasks") or [])
    return {
        "ok": True,
        "reconciliation": {
            "projection_id": job.get("projection_id") or job.get("id"),
            "display_id": job.get("display_id") or "",
            "effective_status": job.get("effective_status") or job.get("status"),
            "effective_status_label": job.get("effective_status_label") or job.get("status_label") or "",
            "business_explanation": decision["business_explanation"],
            "retryable": decision["retryable"],
            "operator_action_required": decision["operator_action_required"],
            "next_action_label": decision["next_action_label"],
            "last_error": _last_error(job, attempts),
            "business_context": {
                "section": job.get("section") or "",
                "section_label": job.get("section_label") or "",
                "effect_type": job.get("effect_type") or "",
                "business_type": job.get("business_type") or "",
                "business_id": job.get("business_id") or "",
                "target_type": job.get("target_type") or "",
                "target_id": job.get("target_id") or "",
                "trace_id": job.get("trace_id") or "",
                "idempotency_key": job.get("idempotency_key") or "",
                "source_module": job.get("source_module") or "",
                "source_route": job.get("source_route") or "",
            },
            "linked_record_counts": linked_record_counts,
            "evidence": {
                "external_effect_jobs": [
                    {
                        "id": item.get("id"),
                        "status": item.get("raw_status") or item.get("status"),
                        "execution_mode": item.get("execution_mode") or "",
                        "effect_type": item.get("effect_type") or "",
                        "last_error_code": item.get("last_error_code") or "",
                        "last_error_message": item.get("last_error_message") or "",
                    }
                    for item in external_jobs
                ],
                "external_effect_attempts": [
                    {
                        "id": item.get("id"),
                        "status": item.get("raw_status") or item.get("status"),
                        "adapter_mode": item.get("adapter_mode") or "",
                        "error_code": item.get("error_code") or "",
                        "error_message": item.get("error_message") or "",
                    }
                    for item in attempts
                ],
                "broadcast_jobs": [
                    {
                        "id": item.get("id"),
                        "status": item.get("raw_status") or item.get("status"),
                        "source_id": item.get("source_id") or "",
                        "trace_id": item.get("trace_id") or "",
                        "sent_count": item.get("sent_count"),
                        "failed_count": item.get("failed_count"),
                        "last_error": item.get("last_error_message") or item.get("last_error") or "",
                    }
                    for item in broadcast_jobs
                ],
                "outbound_tasks": [
                    {
                        "id": item.get("id"),
                        "status": item.get("status") or "",
                        "task_type": item.get("task_type") or "",
                        "trace_id": item.get("trace_id") or "",
                    }
                    for item in outbound_tasks
                ],
            },
        },
        "source": detail.get("source") or {},
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }
