from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.focus_send_service import (
    get_focus_send_batch_detail,
    run_due_focus_send_batches,
)
from ..domains.automation_conversion.service import run_registered_due_jobs
from ..domains.automation_conversion.sop_service import (
    delete_sop_v1_template_day,
    get_sop_v1_config_payload,
    get_sop_v1_templates_payload,
    save_sop_v1_pool_config,
    save_sop_v1_template,
)
from ._routes_helpers import _json_bool, _operator_from_request, _query_int
from .internal_auth import require_internal_api_token


def api_admin_automation_conversion_focus_send_batch_detail(batch_id: str):
    try:
        normalized_batch_id = int(str(batch_id or "").strip())
    except ValueError:
        return jsonify({"ok": False, "error": "invalid batch_id"}), 400
    try:
        payload = get_focus_send_batch_detail(batch_id=normalized_batch_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_focus_send_batch_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_due_focus_send_batches(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 20),
    )
    return jsonify(result)


def api_admin_automation_conversion_sop_config_list():
    return jsonify({"ok": True, **get_sop_v1_config_payload()})


def api_admin_automation_conversion_sop_config_save(pool_key: str):
    payload = request.get_json(silent=True) or {}
    try:
        config = save_sop_v1_pool_config(
            pool_key=pool_key,
            enabled=_json_bool(payload.get("enabled")) if "enabled" in payload else True,
            send_time=str(payload.get("send_time") or "").strip() or "09:00",
            timezone=str(payload.get("timezone") or "").strip() or "Asia/Shanghai",
            effective_start_at=str(payload.get("effective_start_at") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    templates_payload = get_sop_v1_templates_payload(pool_key, selected_day_index=int(payload.get("day") or 1))
    return jsonify({"ok": True, "config": config, "template_count": int(templates_payload.get("template_count") or 0)})


def api_admin_automation_conversion_sop_templates(pool_key: str):
    try:
        payload = get_sop_v1_templates_payload(pool_key, selected_day_index=_query_int("day", default=1, minimum=1, maximum=1000))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_sop_template_save(pool_key: str, day_index: int):
    payload = request.get_json(silent=True) or {}
    try:
        template = save_sop_v1_template(
            pool_key=pool_key,
            day_index=day_index,
            content=str(payload.get("content") or "").strip(),
            images_json=list(payload.get("images_json") or []),
            enabled=_json_bool(payload.get("enabled")) if "enabled" in payload else True,
        )
        templates_payload = get_sop_v1_templates_payload(pool_key, selected_day_index=day_index)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "template": template, **templates_payload})


def api_admin_automation_conversion_sop_template_delete(pool_key: str, day_index: int):
    try:
        payload = delete_sop_v1_template_day(pool_key=pool_key, day_index=day_index)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_sop_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    result = run_registered_due_jobs(
        job_codes=["sop"],
        operator_id=_operator_from_request(),
        operator_type="system",
    )
    return jsonify(result)
