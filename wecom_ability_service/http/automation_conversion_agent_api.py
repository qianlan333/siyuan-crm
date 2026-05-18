from __future__ import annotations

from flask import Response, jsonify, request

from ..domains.automation_conversion.orchestration_service import (
    create_agent_config,
    create_agent_output_export_job,
    delete_agent_config,
    get_agent_config_detail,
    get_agent_output_detail,
    get_agent_output_export_file,
    get_agent_output_export_job,
    get_agent_replay_payload,
    get_agent_run_detail,
    list_agent_outputs,
    list_pending_agent_prompt_publish_requests,
    publish_agent_config,
    save_agent_config_draft,
)
from ..domains.automation_conversion.workflow_service import list_conversion_agent_options
from ._routes_helpers import _operator_from_request, _query_bool, _query_int, _query_text
from .internal_auth import require_internal_api_token, validate_admin_console_action_token


def api_admin_automation_conversion_agent_outputs():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = list_agent_outputs(
        {
            "request_id": _query_text("request_id"),
            "batch_id": _query_text("batch_id"),
            "external_contact_id": _query_text("external_contact_id"),
            "userid": _query_text("userid"),
            "agent_code": _query_text("agent_code"),
            "output_type": _query_text("output_type"),
            "current_pool": _query_text("current_pool"),
            "target_pool": _query_text("target_pool"),
            "applied_status": _query_text("applied_status"),
            "date_from": _query_text("date_from"),
            "date_to": _query_text("date_to"),
            "min_confidence": _query_text("min_confidence"),
            "max_confidence": _query_text("max_confidence"),
            "has_error": _query_text("has_error"),
            "scripts_only": _query_bool("scripts_only", default=False),
        },
        page=_query_int("page", default=1, minimum=1, maximum=100000),
        page_size=_query_int("page_size", default=20, minimum=1, maximum=100),
        visibility="console",
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_agent_output_detail(output_id: str):
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    try:
        payload = get_agent_output_detail(output_id, visibility="console")
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_agent_run_detail(run_id: str):
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    try:
        payload = get_agent_run_detail(run_id, visibility="console")
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "run": payload})


def api_admin_automation_conversion_agent_outputs_export():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    try:
        job = create_agent_output_export_job(
            dict(payload.get("filters") or {}),
            requested_by=str(payload.get("requested_by") or _operator_from_request() or "crm_console").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 429
    return jsonify({"ok": True, "job": job}), 202


def api_admin_automation_conversion_agent_outputs_export_detail(job_id: str):
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    if _query_bool("download", default=False):
        export_file = get_agent_output_export_file(job_id)
        if not export_file:
            return jsonify({"ok": False, "error": "export job not found"}), 404
        return Response(
            bytes(export_file.get("content_bytes") or b""),
            mimetype="application/vnd.ms-excel",
            headers={"Content-Disposition": f"attachment; filename={str(export_file.get('file_name') or 'agent-outputs.xls')}"},
        )
    job = get_agent_output_export_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "export job not found"}), 404
    return jsonify({"ok": True, "job": job})


def api_admin_automation_conversion_agent_replay():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = get_agent_replay_payload(
        run_id=_query_text("run_id"),
        request_id=_query_text("request_id"),
        external_contact_id=_query_text("external_contact_id"),
        userid=_query_text("userid"),
        date_from=_query_text("date_from"),
        date_to=_query_text("date_to"),
        visibility="console",
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_pending_publish():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = list_pending_agent_prompt_publish_requests(
        agent_code=_query_text("agent_code"),
        page=_query_int("page", default=1, minimum=1, maximum=100000),
        page_size=_query_int("page_size", default=20, minimum=1, maximum=100),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_agent_options():
    return jsonify(
        {
            "ok": True,
            **list_conversion_agent_options(
                enabled_only=_query_bool("enabled_only", default=True),
            ),
        }
    )


def api_admin_automation_conversion_agent_detail(agent_code: str):
    try:
        payload = get_agent_config_detail(agent_code)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "item": payload})


def api_admin_automation_conversion_agent_create():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = create_agent_config(
            payload,
            operator_id=_operator_from_request(),
            source="automation_conversion_agent_config",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_agent_draft(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = save_agent_config_draft(
            agent_code,
            payload,
            operator_id=_operator_from_request(),
            source="automation_conversion_agent_config",
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_agent_publish(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        result = publish_agent_config(
            agent_code,
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_agent_delete(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        result = delete_agent_config(
            agent_code,
            operator_id=_operator_from_request(),
            source="automation_conversion_agent_config",
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})
