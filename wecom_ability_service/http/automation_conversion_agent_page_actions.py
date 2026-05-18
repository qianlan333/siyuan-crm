from __future__ import annotations

import json

from flask import redirect, request, url_for

from ..domains.automation_conversion.orchestration_service import (
    replay_agent_run,
    review_agent_reply_output,
    save_agent_config_draft,
)
from ._routes_helpers import _json_bool, _operator_from_request
from .automation_conversion_render import _render_run_center_page
from .internal_auth import validate_admin_console_action_token


def admin_automation_conversion_agent_orchestration_save_draft(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    page_input = dict(request.form or {})
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error, page_input=page_input)
    payload = {
        "display_name": str(request.form.get("display_name") or "").strip(),
        "enabled": _json_bool(request.form.get("enabled")),
        "role_prompt": str(request.form.get("role_prompt") or "").strip(),
        "task_prompt": str(request.form.get("task_prompt") or "").strip(),
        "change_summary": str(request.form.get("change_summary") or "").strip(),
    }
    raw_variables_json = str(request.form.get("variables_json") or "").strip()
    raw_output_schema_json = str(request.form.get("output_schema_json") or "").strip()
    page_input = {**page_input, "variables_json": raw_variables_json, "output_schema_json": raw_output_schema_json}
    try:
        if raw_variables_json:
            parsed_variables = json.loads(raw_variables_json)
            if not isinstance(parsed_variables, list):
                raise ValueError("variables_json must be valid JSON array")
            payload["variables"] = parsed_variables
        if raw_output_schema_json:
            parsed_output_schema = json.loads(raw_output_schema_json)
            if not isinstance(parsed_output_schema, list):
                raise ValueError("output_schema_json must be valid JSON array")
            payload["output_schema"] = parsed_output_schema
        save_agent_config_draft(
            agent_code,
            payload,
            operator_id=_operator_from_request(),
            source="automation_conversion_run_center",
        )
    except json.JSONDecodeError:
        return _render_run_center_page(
            page_error="variables_json must be valid JSON array",
            page_input={
                **page_input,
                "tab": "agent-orchestration",
                "subtab": "agents",
                "agent": agent_code,
            },
        )
    except (LookupError, ValueError) as exc:
        query_params = dict(request.args.to_dict(flat=True))
        if not query_params:
            query_params = {"tab": "agent-orchestration", "subtab": "agents", "agent": agent_code}
        return _render_run_center_page(page_error=str(exc), page_input={**query_params, **payload})
    return redirect(
        url_for("api.admin_automation_conversion_runtime_router", subtab="agents", agent=agent_code, saved=1),
        code=302,
    )


def admin_automation_conversion_agent_orchestration_review_output(output_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error)
    decision = str(request.form.get("decision") or "").strip()
    review_note = str(request.form.get("review_note") or "").strip()
    try:
        reviewed = review_agent_reply_output(
            output_id,
            decision=decision,
            operator_id=_operator_from_request(),
            review_note=review_note,
            source="automation_conversion_run_center",
        )
    except (LookupError, ValueError) as exc:
        return _render_run_center_page(page_error=str(exc))
    applied_status = str(reviewed.get("applied_status") or reviewed.get("outcome_status") or "").strip()
    page_notice = "话术已标记为采用" if applied_status == "adopted" else "话术已标记为不采用"
    return redirect(
        url_for(
            "api.admin_automation_conversion_runtime_router",
            subtab="outputs",
            external_contact_id=str(request.form.get("external_contact_id") or "").strip() or None,
            scripts_only=str(request.form.get("scripts_only") or "").strip() or None,
            output_id=output_id,
            notice=page_notice,
        ),
        code=302,
    )


def admin_automation_conversion_agent_orchestration_replay(run_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error)
    try:
        replayed = replay_agent_run(run_id, operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return _render_run_center_page(page_error=str(exc))
    request_id = str(((replayed.get("run") or {}).get("request_id")) or request.args.get("request_id") or "").strip()
    return redirect(
        url_for("api.admin_automation_conversion_runtime_router", subtab="replay", request_id=request_id, replayed=1),
        code=302,
    )
