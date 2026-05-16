from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.admin_jobs import (
    build_jobs_archive_sync_payload,
    build_jobs_callbacks_payload,
    build_jobs_deferred_jobs_payload,
    build_jobs_message_batch_detail_payload,
    build_jobs_message_batches_payload,
    build_jobs_payload,
    build_jobs_summary_payload,
    build_jobs_webhook_deliveries_payload,
    execute_jobs_action,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token, require_internal_api_token, validate_admin_console_action_token


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
    )


def _request_confirmed() -> bool:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.values.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
        or str(json_payload.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
    )


def _request_payload() -> dict:
    return request.get_json(silent=True) or {}


def _api_args() -> dict[str, str]:
    return request.args.to_dict(flat=True)


def _jobs_page(
    *,
    tab: str = "",
    page_notice: str = "",
    page_error: str = "",
    action_result: dict | None = None,
    query_overrides: dict[str, str] | None = None,
):
    args = request.args.to_dict(flat=True)
    if tab:
        args["tab"] = tab
    for key, value in (query_overrides or {}).items():
        if value != "":
            args[key] = value
    payload = build_jobs_payload(args)
    return _render_admin_template(
        "jobs.html",
        active_nav="jobs",
        page_title="同步任务",
        page_summary="在这里查看聊天同步、回调状态、消息批次和待处理作业。需要执行的操作会先让你确认。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("同步任务", None)),
        jobs_payload=payload,
        page_notice=page_notice,
        page_error=page_error,
        action_result=action_result or {},
        admin_action_token=ensure_admin_console_action_token(),
    )


def admin_console_jobs():
    return _jobs_page()


def admin_console_jobs_action():
    active_tab = str(request.form.get("return_tab") or request.args.get("tab") or "").strip()
    query_overrides = {
        "batch_id": str(request.form.get("batch_id") or "").strip(),
        "batch_status": str(request.form.get("batch_status") or "").strip(),
        "batch_limit": str(request.form.get("batch_limit") or "").strip(),
        "webhook_event_type": str(request.form.get("webhook_event_type") or "").strip(),
        "webhook_status": str(request.form.get("webhook_status") or "").strip(),
        "webhook_limit": str(request.form.get("webhook_limit") or "").strip(),
    }
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _jobs_page(
            tab=active_tab,
            page_error=action_token_error,
            query_overrides=query_overrides,
        )
    try:
        payload = execute_jobs_action(
            action=str(request.form.get("action") or "").strip(),
            form=request.form,
            operator=_operator_from_request(),
        )
        if payload.get("ok") is False:
            return _jobs_page(
                tab=active_tab,
                page_error=str(payload.get("error") or "action failed"),
                action_result=payload,
                query_overrides=query_overrides,
            )
        if payload.get("preview_only"):
            return _jobs_page(
                tab=active_tab,
                page_notice="这里会先展示操作预览，确认后才会真正执行同步。",
                action_result=payload,
                query_overrides=query_overrides,
            )
        return _jobs_page(
            tab=active_tab,
            page_notice="操作已完成，结果与审计已刷新。",
            action_result=payload,
            query_overrides=query_overrides,
        )
    except Exception as exc:
        return _jobs_page(
            tab=active_tab,
            page_error=str(exc),
            query_overrides=query_overrides,
        )


def api_admin_jobs_summary():
    return jsonify({"ok": True, "summary": build_jobs_summary_payload(_api_args())})


def api_admin_jobs_archive_sync():
    return jsonify({"ok": True, "archive_sync": build_jobs_archive_sync_payload(_api_args())})


def api_admin_jobs_archive_sync_run():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    params = {
        "start_time": str(payload.get("start_time") or request.values.get("start_time") or "").strip(),
        "end_time": str(payload.get("end_time") or request.values.get("end_time") or "").strip(),
        "owner_userid": str(payload.get("owner_userid") or request.values.get("owner_userid") or "").strip(),
        "cursor": str(payload.get("cursor") or request.values.get("cursor") or "").strip(),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="run-archive-sync", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    status_code = 200 if result.get("ok", False) else 502
    return jsonify(result), status_code


def api_admin_jobs_callbacks():
    return jsonify({"ok": True, "callbacks": build_jobs_callbacks_payload(_api_args())})


def api_admin_jobs_message_batches():
    return jsonify({"ok": True, "message_batches": build_jobs_message_batches_payload(_api_args())})


def api_admin_jobs_message_batch_detail(batch_id: int):
    payload = build_jobs_message_batch_detail_payload(batch_id, _api_args())
    if not payload.get("batch"):
        return jsonify({"ok": False, "error": "message batch not found"}), 404
    return jsonify({"ok": True, "message_batch": payload})


def api_admin_jobs_message_batch_ack(batch_id: int):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    params = {
        "batch_id": batch_id,
        "ack_note": str(payload.get("ack_note") or request.values.get("ack_note") or "").strip(),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="ack-message-batch", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not result.get("batch"):
        return jsonify({"ok": False, "error": "message batch not found"}), 404
    return jsonify(result)


def api_admin_jobs_deferred_jobs():
    return jsonify({"ok": True, "deferred_jobs": build_jobs_deferred_jobs_payload(_api_args())})


def api_admin_jobs_deferred_jobs_run():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    params = {
        "limit": payload.get("limit") if "limit" in payload else request.values.get("limit"),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="run-deferred-jobs", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    status_code = 200 if result.get("ok", False) else 502
    return jsonify(result), status_code


def api_admin_jobs_webhook_deliveries():
    return jsonify({"ok": True, "webhook_deliveries": build_jobs_webhook_deliveries_payload(_api_args())})


def api_admin_jobs_webhook_deliveries_run():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = _request_payload()
    params = {
        "limit": payload.get("limit") if "limit" in payload else request.values.get("limit"),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="run-webhook-retries", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    status_code = 200 if result.get("ok", False) else 502
    return jsonify(result), status_code


def api_admin_jobs_webhook_delivery_retry(delivery_id: int):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    params = {
        "delivery_id": delivery_id,
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="retry-webhook-delivery", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify(result)


def admin_console_broadcast_jobs():
    from ..domains.broadcast_jobs import service as queue_service

    args = request.args.to_dict(flat=True)
    statuses = [s for s in str(args.get("status") or "").split(",") if s.strip()] or None
    source_types = [s for s in str(args.get("source_type") or "").split(",") if s.strip()] or None
    limit = min(int(args.get("limit") or 50), 200)
    offset = int(args.get("offset") or 0)
    jobs = queue_service.list_jobs(
        statuses=statuses,
        source_types=source_types,
        limit=limit,
        offset=offset,
    )
    counts = queue_service.count_by_status()
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
        jobs=jobs,
        counts=counts,
        filters={"statuses": statuses, "source_types": source_types, "limit": limit, "offset": offset},
    )


def api_admin_broadcast_jobs():
    from ..domains.broadcast_jobs import service as queue_service

    args = request.args.to_dict(flat=True)
    statuses = [s for s in str(args.get("status") or "").split(",") if s.strip()] or None
    source_types = [s for s in str(args.get("source_type") or "").split(",") if s.strip()] or None
    limit = min(int(args.get("limit") or 50), 200)
    offset = int(args.get("offset") or 0)
    jobs = queue_service.list_jobs(
        statuses=statuses,
        source_types=source_types,
        limit=limit,
        offset=offset,
    )
    counts = queue_service.count_by_status()
    return jsonify({"ok": True, "jobs": jobs, "counts": counts})


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
    bp.route("/admin/jobs", methods=["GET"])(admin_console_jobs)
    bp.route("/admin/jobs/actions", methods=["POST"])(admin_console_jobs_action)
    bp.route("/admin/broadcast-jobs", methods=["GET"])(admin_console_broadcast_jobs)
    bp.route("/api/admin/jobs/summary", methods=["GET"])(api_admin_jobs_summary)
    bp.route("/api/admin/jobs/archive-sync", methods=["GET"])(api_admin_jobs_archive_sync)
    bp.route("/api/admin/jobs/archive-sync/run", methods=["POST"])(api_admin_jobs_archive_sync_run)
    bp.route("/api/admin/jobs/callbacks", methods=["GET"])(api_admin_jobs_callbacks)
    bp.route("/api/admin/jobs/message-batches", methods=["GET"])(api_admin_jobs_message_batches)
    bp.route("/api/admin/jobs/message-batches/<int:batch_id>", methods=["GET"])(api_admin_jobs_message_batch_detail)
    bp.route("/api/admin/jobs/message-batches/<int:batch_id>/ack", methods=["POST"])(api_admin_jobs_message_batch_ack)
    bp.route("/api/admin/jobs/deferred-jobs", methods=["GET"])(api_admin_jobs_deferred_jobs)
    bp.route("/api/admin/jobs/deferred-jobs/run", methods=["POST"])(api_admin_jobs_deferred_jobs_run)
    bp.route("/api/admin/jobs/webhook-deliveries", methods=["GET"])(api_admin_jobs_webhook_deliveries)
    bp.route("/api/admin/jobs/webhook-deliveries/run", methods=["POST"])(api_admin_jobs_webhook_deliveries_run)
    bp.route("/api/admin/jobs/webhook-deliveries/<int:delivery_id>/retry", methods=["POST"])(api_admin_jobs_webhook_delivery_retry)
    bp.route("/api/admin/broadcast-jobs", methods=["GET"])(api_admin_broadcast_jobs)
    bp.route("/api/admin/broadcast-jobs/<int:job_id>/cancel", methods=["POST"])(api_admin_broadcast_jobs_cancel)
    bp.route("/api/admin/broadcast-jobs/<int:job_id>/approve", methods=["POST"])(api_admin_broadcast_jobs_approve)
