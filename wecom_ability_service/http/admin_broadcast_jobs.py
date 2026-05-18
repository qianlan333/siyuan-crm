from __future__ import annotations

from flask import jsonify, request, url_for

from .admin_console import _breadcrumb_items, _render_admin_template
from .admin_jobs import _operator_from_request, _request_payload
from .internal_auth import require_internal_api_token


def _broadcast_job_filters() -> dict[str, object]:
    args = request.args.to_dict(flat=True)
    statuses = [s for s in str(args.get("status") or "").split(",") if s.strip()] or None
    source_types = [s for s in str(args.get("source_type") or "").split(",") if s.strip()] or None
    limit = min(int(args.get("limit") or 50), 200)
    offset = int(args.get("offset") or 0)
    return {
        "statuses": statuses,
        "source_types": source_types,
        "limit": limit,
        "offset": offset,
    }


def _broadcast_job_list_payload() -> dict[str, object]:
    from ..domains.broadcast_jobs import service as queue_service

    filters = _broadcast_job_filters()
    jobs = queue_service.list_jobs(
        statuses=filters["statuses"],
        source_types=filters["source_types"],
        limit=filters["limit"],
        offset=filters["offset"],
    )
    counts = queue_service.count_by_status()
    return {"filters": filters, "jobs": jobs, "counts": counts}


def admin_console_broadcast_jobs():
    payload = _broadcast_job_list_payload()
    return _render_admin_template(
        "broadcast_jobs.html",
        active_nav="jobs",
        page_title="群发任务队列",
        page_summary="统一群发任务队列 — 按时间线展示所有来源的群发批次。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("同步任务", url_for("api.admin_console_jobs")),
            ("群发队列", None),
        ),
        jobs=payload["jobs"],
        counts=payload["counts"],
        filters=payload["filters"],
    )


def api_admin_broadcast_jobs():
    payload = _broadcast_job_list_payload()
    return jsonify({"ok": True, "jobs": payload["jobs"], "counts": payload["counts"]})


def api_admin_broadcast_jobs_cancel(job_id: int):
    from ..domains.broadcast_jobs import service as queue_service

    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    reason = str(payload.get("reason") or "").strip()
    operator = _operator_from_request() or "admin"
    ok = queue_service.cancel_job(job_id, cancelled_by=operator, reason=reason)
    if not ok:
        return jsonify({"ok": False, "error": "job not cancelable (not queued or waiting_approval)"}), 400
    return jsonify({"ok": True, "cancelled": True, "job_id": job_id})


def api_admin_broadcast_jobs_approve(job_id: int):
    from ..domains.broadcast_jobs import service as queue_service

    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    operator = _operator_from_request() or "admin"
    ok = queue_service.approve_job(job_id, approved_by=operator)
    if not ok:
        return jsonify({"ok": False, "error": "job not approvable (not waiting_approval)"}), 400
    return jsonify({"ok": True, "approved": True, "job_id": job_id})


def register_routes(bp):
    bp.route("/admin/broadcast-jobs", methods=["GET"])(admin_console_broadcast_jobs)
    bp.route("/api/admin/broadcast-jobs", methods=["GET"])(api_admin_broadcast_jobs)
    bp.route("/api/admin/broadcast-jobs/<int:job_id>/cancel", methods=["POST"])(api_admin_broadcast_jobs_cancel)
    bp.route("/api/admin/broadcast-jobs/<int:job_id>/approve", methods=["POST"])(api_admin_broadcast_jobs_approve)
