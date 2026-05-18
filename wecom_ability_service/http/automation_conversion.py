from __future__ import annotations

import json

import requests

from flask import Response, current_app, jsonify, redirect, request, url_for

from ..domains.automation_conversion.channel_service import (
    generate_default_channel_qr,
    get_default_channel_settings_payload,
    save_default_channel_settings,
)
from ..domains.automation_conversion.focus_send_service import (
    create_focus_send_batch,
    get_focus_send_batch_detail,
    run_due_focus_send_batches,
)
from ..domains.automation_conversion.laohuang_chat_service import (
    handle_laohuang_chat_result_callback,
    list_recent_laohuang_review_outputs,
    send_laohuang_review_output_via_webhook,
    send_laohuang_review_output_via_wecom,
)
from ..domains.automation_conversion.manual_send_service import (
    preview_stage_manual_send,
    send_stage_manual_message,
)
from ..domains.automation_conversion import member_segment_search_service
from ..domains.automation_conversion.action_template_service import (
    create_action_from_template,
    create_action_template,
    create_action_template_from_workflow,
    generate_action_template,
    list_action_templates,
)
from ..domains.automation_conversion.message_activity_service import run_message_activity_sync
from ..domains.automation_conversion.model_infra_service import (
    get_model_infra_payload,
    save_model_infra_settings,
    test_model_infra_connection,
)
from ..domains.automation_conversion.operation_task_service import (
    activate_operation_task,
    copy_operation_task,
    create_operation_task,
    create_task_group,
    delete_operation_task,
    delete_task_group,
    get_operation_task,
    list_operation_tasks,
    list_task_groups,
    pause_operation_task,
    preview_operation_task_audience,
    run_due_operation_tasks,
    update_operation_task,
    update_task_group,
)
from ..domains.automation_conversion.orchestration_service import (
    build_rejected_feedback_clipboard_payload,
    create_agent_config,
    create_agent_output_export_job,
    delete_agent_config,
    get_agent_config_detail,
    get_agent_output_detail,
    get_agent_output_export_file,
    get_agent_output_export_job,
    get_agent_replay_payload,
    get_agent_run_detail,
    handle_agent_router_callback,
    list_agent_outputs,
    list_pending_agent_prompt_publish_requests,
    list_router_pending_callbacks,
    publish_agent_config,
    replay_agent_run,
    replay_router_callback,
    review_agent_reply_output,
    run_router_pending_callback_check,
    save_agent_config_draft,
    validate_router_callback_signature,
)
from ..domains.automation_conversion.program_service import (
    copy_automation_program,
    create_automation_program,
    update_automation_program_basic_info,
    update_automation_program_status,
)
from ..domains.automation_conversion.program_setup_service import (
    build_publish_check,
    create_program_customer_acquisition_link,
    get_program_setup_payload,
    publish_entry,
    publish_full,
    save_audience_entry_rule,
    save_entry_channel,
    save_segmentation,
    save_setup_basic,
)
from ..domains.automation_conversion.reply_monitor_service import (
    run_due_reply_monitor,
    run_reply_monitor_capture,
    run_router_test_dispatch,
    save_reply_monitor_enabled,
)
from ..domains.automation_conversion.service import (
    get_member_detail,
    get_overview_payload,
    get_settings_payload,
    mark_won,
    put_in_pool,
    push_openclaw,
    remove_from_pool,
    run_registered_due_jobs,
    save_settings,
    set_follow_type,
    unmark_won,
)
from ..domains.automation_conversion.sop_service import (
    delete_sop_v1_template_day,
    get_sop_v1_config_payload,
    get_sop_v1_templates_payload,
    save_sop_v1_pool_config,
    save_sop_v1_template,
)
from ..domains.automation_conversion.workflow_service import (
    activate_conversion_workflow,
    apply_dashboard_signup_tag,
    create_conversion_profile_segment_template,
    create_conversion_workflow,
    create_conversion_workflow_node,
    delete_conversion_workflow,
    delete_conversion_workflow_node,
    get_conversion_dashboard_payload,
    get_conversion_profile_segment_template_bundle,
    get_conversion_workflow_detail_summary,
    get_conversion_workflow_execution_detail,
    get_conversion_workflow_execution_item_detail,
    get_conversion_workflow_model_bundle,
    list_conversion_agent_options,
    list_conversion_profile_segment_catalog,
    list_conversion_profile_segment_template_options,
    list_conversion_profile_segment_templates,
    list_conversion_workflow_execution_items,
    list_conversion_workflow_execution_records,
    list_conversion_workflow_nodes,
    list_conversion_workflow_registry,
    list_conversion_workflows,
    pause_conversion_workflow,
    send_agent_reply_output_via_bazhuayu,
    send_conversion_execution_item_via_bazhuayu,
    update_conversion_profile_segment_template,
    update_conversion_workflow,
    update_conversion_workflow_node,
)
from .internal_auth import require_internal_api_token, validate_admin_console_action_token


from ._routes_helpers import (  # noqa: F401  helpers for route handlers — 阶段 7.1
    _automation_conversion_workspace_tabs,
    _automation_program_workspace_tabs,
    _build_agent_config_workspace,
    _build_action_orchestration_workspace,
    _build_auto_reply_workspace,
    _build_execution_records_workspace,
    _build_flow_design_workspace,
    _build_member_ops_workspace,
    _build_operations_list_workspace,
    _build_overview_workspace,
    _build_profile_segment_workspace,
    _build_run_center_workspace,
    _build_workflow_editor_workspace,
    _build_workflow_nodes_workspace,
    _coerce_program_id,
    _default_program_id_or_none,
    _detect_stage_send_image_type,
    _flow_design_section,
    _json_bool,
    _load_program_or_404,
    _member_ops_panel,
    _member_ops_stage_key,
    _operations_page_api_urls,
    _operations_page_entry_urls,
    _operator_from_request,
    _overview_notice,
    _payload_program_id,
    _program_action_redirect,
    _program_api_params,
    _program_basic_info_payload,
    _program_context,
    _program_form_payload,
    _program_route,
    _program_route_or_main,
    _query_bool,
    _query_int,
    _query_text,
    _redirect_to_program,
    _render_agent_config_page,
    _render_action_orchestration_page,
    _render_auto_reply_page,
    _render_execution_records_page,
    _render_flow_design_page,
    _render_member_ops_page,
    _render_operations_page,
    _render_overview_page,
    _render_program_list_page,
    _render_program_setup_page,
    _render_run_center_page,
    _render_workflow_editor_page,
    _render_workflow_nodes_page,
    _request_program_id,
    _request_program_id_or_default,
    _run_center_agent_subtab,
    _run_center_tab,
    _stage_send_images_from_request,
    _wants_json_response,
)


def admin_automation_conversion():
    return _render_program_list_page()


def admin_automation_program_new():
    return redirect(url_for("api.admin_automation_conversion", create=1) + "#program-create-panel", code=302)


def admin_automation_program_create():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_program_list_page(page_error=action_token_error, show_create_form=True)
    try:
        result = create_automation_program(_program_form_payload(), operator_id=_operator_from_request())
    except ValueError as exc:
        return _render_program_list_page(page_error=str(exc), show_create_form=True)
    return redirect(
        url_for("api.admin_automation_program_setup", program_id=int((result.get("program") or {}).get("id") or 0)),
        code=302,
    )


def admin_automation_program_update(program_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_program_list_page(page_error=action_token_error, edit_program_id=int(program_id))
    try:
        update_automation_program_basic_info(
            int(program_id),
            _program_basic_info_payload(),
            operator_id=_operator_from_request(),
        )
    except (LookupError, ValueError) as exc:
        return _render_program_list_page(page_error=str(exc), edit_program_id=int(program_id))
    return _program_action_redirect(url_for("api.admin_automation_conversion", edit_program_id=int(program_id)) + f"#program-row-{int(program_id)}")


def admin_automation_program_copy(program_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_program_list_page(page_error=action_token_error)
    try:
        result = copy_automation_program(int(program_id), _program_form_payload(), operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return _render_program_list_page(page_error=str(exc))
    return redirect(
        url_for("api.admin_automation_program_setup", program_id=int((result.get("program") or {}).get("id") or 0)),
        code=302,
    )


def admin_automation_program_activate(program_id: int):
    return _program_status_action(program_id, "active")


def admin_automation_program_pause(program_id: int):
    return _program_status_action(program_id, "paused")


def admin_automation_program_archive(program_id: int):
    return _program_status_action(program_id, "archived")


def _program_status_action(program_id: int, status: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_program_list_page(page_error=action_token_error)
    try:
        update_automation_program_status(int(program_id), status=status, operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return _render_program_list_page(page_error=str(exc))
    return _program_action_redirect(url_for("api.admin_automation_conversion"))


def admin_automation_conversion_auto_reply():
    return _render_auto_reply_page()


def admin_automation_program_overview(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_overview_page(program=program)


def admin_automation_program_setup(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_program_setup_page(program=program, step=_query_text("step") or "basic")


def admin_automation_program_operations(program_id: int):
    workflow_id = _query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None
    params = {"step": "operations"}
    if workflow_id:
        params["workflow_id"] = workflow_id
    return redirect(url_for("api.admin_automation_program_setup", program_id=int(program_id), **params), code=302)


def admin_automation_program_workflows(program_id: int):
    return redirect(url_for("api.admin_automation_program_setup", program_id=int(program_id), step="operations"), code=302)


def admin_automation_program_workflow_new(program_id: int):
    return redirect(url_for("api.admin_automation_program_setup", program_id=int(program_id), step="operations"), code=302)


def admin_automation_program_workflow_edit(program_id: int, workflow_id: int):
    return redirect(
        url_for("api.admin_automation_program_setup", program_id=int(program_id), step="operations", workflow_id=int(workflow_id)),
        code=302,
    )


def admin_automation_program_workflow_nodes(program_id: int, workflow_id: int):
    return redirect(
        url_for("api.admin_automation_program_setup", program_id=int(program_id), step="operations", workflow_id=int(workflow_id)),
        code=302,
    )


def admin_automation_program_executions(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_execution_records_page(program=program)


def admin_automation_program_flow_design(program_id: int):
    return redirect(url_for("api.admin_automation_program_setup", program_id=int(program_id), step="segmentation"), code=302)


def admin_automation_program_member_ops(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_member_ops_page(program=program)


def admin_automation_conversion_shared_agents():
    return _render_agent_config_page()


def admin_automation_conversion_shared_profile_segments():
    program_id = _default_program_id_or_none()
    if program_id:
        return redirect(
            url_for(
                "api.admin_automation_program_flow_design",
                program_id=program_id,
                section="profile-segments",
            )
            + "#flow-profile-segments",
            code=302,
        )
    return redirect(url_for("api.admin_automation_conversion"), code=302)


def admin_automation_conversion_shared_model_infra():
    return _render_run_center_page(page_input={"tab": "model-infra"})


def admin_automation_conversion_runtime():
    return _render_run_center_page(page_notice=_query_text("notice"), page_input={"tab": "overview"})


def admin_automation_conversion_runtime_sync():
    return _render_run_center_page(page_input={"tab": "sync"})


def admin_automation_conversion_runtime_router():
    return _render_run_center_page(
        page_notice=_query_text("notice"),
        page_input={"tab": "agent-orchestration", "subtab": "router"},
    )


def admin_automation_conversion_runtime_logs():
    return _render_run_center_page(page_input={"tab": "logs"})


def admin_automation_conversion_runtime_debug():
    return _render_run_center_page(
        page_input={
            "tab": "debug",
            "external_contact_id": _query_text("external_contact_id"),
            "phone": _query_text("phone"),
        }
    )


def admin_automation_conversion_save_settings():
    section = str(request.form.get("section") or "questionnaire").strip() or "questionnaire"
    program_id = _request_program_id_or_default()
    action_token_error = validate_admin_console_action_token()
    page_input = dict(request.form or {})
    if action_token_error:
        return _render_flow_design_page(page_error=action_token_error, page_input=page_input)
    try:
        save_settings(dict(request.form or {}), program_id=program_id)
    except ValueError as exc:
        return _render_flow_design_page(page_error=str(exc), page_input=page_input)
    return redirect(
        _program_route_or_main(
            "api.admin_automation_program_flow_design",
            program_id=program_id,
            section=section,
            pool=str(request.values.get("pool") or "").strip() or None,
            day=str(request.values.get("day") or "").strip() or None,
            saved=1,
        ),
        code=302,
    )


def admin_automation_conversion_generate_default_channel():
    program_id = _request_program_id_or_default()
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_flow_design_page(page_error=action_token_error, page_input=dict(request.form or {}))
    result = generate_default_channel_qr(operator=_operator_from_request(), program_id=program_id)
    if not result.get("generated"):
        return _render_flow_design_page(
            page_error=str(result.get("error") or "二维码生成失败"),
            page_input=dict(request.form or {}),
        )
    return redirect(
        _program_route_or_main(
            "api.admin_automation_program_flow_design",
            program_id=program_id,
            section="channel",
            pool=str(request.values.get("pool") or "").strip() or None,
            day=str(request.values.get("day") or "").strip() or None,
            saved=1,
        ),
        code=302,
    )


def _stage_send_member_ops_params(stage_key: str, **notice_params) -> dict[str, object]:
    params: dict[str, object] = {
        "stage": str(stage_key or "").strip(),
        "panel": "send",
    }
    for key in ("keyword", "external_contact_id", "member", "phone"):
        value = str(request.values.get(key) or "").strip()
        if value:
            params[key] = value
    params.update({key: value for key, value in notice_params.items() if value is not None and value != ""})
    return params


def _handle_stage_send_post(stage_key: str, *, program: dict[str, object]):
    program_id = int(program.get("id") or 0)
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_member_ops_page(page_error=action_token_error, program=program)
    try:
        images = _stage_send_images_from_request()
        route_key = str(stage_key or "").strip()
        if route_key in {"inactive-focus", "active-focus"}:
            result = create_focus_send_batch(
                route_key=route_key,
                operator_id=_operator_from_request(),
                operator_type="user",
            )
            redirect_url = _program_route(
                "api.admin_automation_program_member_ops",
                program_id=program_id,
                **_stage_send_member_ops_params(
                    route_key,
                    focus_batch_notice="created",
                    focus_batch_id=int((result.get("batch") or {}).get("id") or 0),
                ),
            )
            if _wants_json_response():
                return jsonify({"ok": True, "redirect_url": redirect_url, "result": result})
            return redirect(redirect_url, code=302)
        result = send_stage_manual_message(
            route_key=route_key,
            content=str(request.form.get("content") or "").strip(),
            images=images,
            operator_id=_operator_from_request(),
        )
        redirect_url = _program_route(
            "api.admin_automation_program_member_ops",
            program_id=program_id,
            **_stage_send_member_ops_params(
                route_key,
                manual_send_notice="sent",
                record_id=int(result.get("record_id") or 0),
            ),
        )
        if _wants_json_response():
            return jsonify({"ok": True, "redirect_url": redirect_url, "result": result})
        return redirect(redirect_url, code=302)
    except ValueError as exc:
        if _wants_json_response():
            return jsonify({"ok": False, "error": str(exc)}), 400
        return _render_member_ops_page(page_error=str(exc), program=program)
    except Exception as exc:
        current_app.logger.exception("stage send failed: stage_key=%s program_id=%s", stage_key, program_id)
        error_message = f"发送任务异常: {type(exc).__name__}: {exc}"
        if _wants_json_response():
            return jsonify({"ok": False, "error": error_message}), 500
        return _render_member_ops_page(page_error=error_message, program=program)


def admin_automation_program_member_ops_stage_send(program_id: int, stage_key: str):
    program = _load_program_or_404(program_id)
    return _handle_stage_send_post(stage_key, program=program)


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
        return _render_run_center_page(page_error="variables_json must be valid JSON array", page_input={**page_input, "tab": "agent-orchestration", "subtab": "agents", "agent": agent_code})
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
    page_notice = "话术已标记为采用" if str(reviewed.get("applied_status") or reviewed.get("outcome_status") or "").strip() == "adopted" else "话术已标记为不采用"
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


def admin_automation_auto_reply_monitor_toggle():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    enabled = _json_bool(request.form.get("enabled") or request.values.get("enabled"))
    try:
        save_reply_monitor_enabled(enabled=enabled, operator_id=_operator_from_request())
    except ValueError as exc:
        if _wants_json_response():
            return jsonify({"ok": False, "error": str(exc)}), 400
        return _render_auto_reply_page(page_error=str(exc))
    status = "enabled" if enabled else "disabled"
    if _wants_json_response():
        return jsonify({"ok": True, "status": status, "message": "自动接话已开启" if enabled else "自动接话已关闭"})
    return redirect(
        url_for(
            "api.admin_automation_conversion_auto_reply",
            reply_monitor=status,
        ),
        code=302,
    )


def admin_automation_auto_reply_monitor_capture():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if _wants_json_response():
        status = str(result.get("status") or "").strip()
        ok = bool(result.get("ok")) or status in {"disabled", "idle", "throttled", "quiet_hours"}
        status_code = 200 if ok else 400
        return (
            jsonify(
                {
                    "ok": ok,
                    "status": status,
                    "message": str(result.get("message") or result.get("error") or "自动接话扫描已完成"),
                    "result": result,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_auto_reply", reply_monitor="captured"),
            code=302,
        )
    return _render_auto_reply_page(page_error=str(result.get("error") or "自动接话监控扫描失败"))


def admin_automation_auto_reply_monitor_run_due():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if _wants_json_response():
        status = str(result.get("status") or "").strip()
        ok = bool(result.get("ok")) or status in {"disabled", "idle", "throttled", "quiet_hours"}
        status_code = 200 if ok else 400
        return (
            jsonify(
                {
                    "ok": ok,
                    "status": status,
                    "message": str(result.get("message") or result.get("error") or "自动接话放行已完成"),
                    "result": result,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_auto_reply", reply_monitor="dispatched"),
            code=302,
        )
    return _render_auto_reply_page(page_error=str(result.get("error") or "自动接话监控放行失败"))


def admin_automation_program_overview_message_activity_sync_run(program_id: int):
    _load_program_or_404(program_id)
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="user",
        trigger_source="manual",
    )
    if _wants_json_response():
        overview_payload = get_overview_payload()
        message_activity_sync = dict(overview_payload.get("message_activity_sync") or {})
        status_code = 200 if result.get("ok") else 400
        return (
            jsonify(
                {
                    "ok": bool(result.get("ok")),
                    "message": "消息活跃同步已完成" if result.get("ok") else str(result.get("error") or "消息活跃同步失败"),
                    "run": result.get("run") or {},
                    "message_activity_sync": message_activity_sync,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            _program_route_or_main("api.admin_automation_program_overview", program_id=program_id, message_activity_sync=1),
            code=302,
        )
    return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)


def admin_automation_program_overview_signup_tag_apply(program_id: int):
    _load_program_or_404(program_id)
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    try:
        result = apply_dashboard_signup_tag(
            operator_id=_operator_from_request(),
            program_id=program_id,
        )
    except ValueError as exc:
        if _wants_json_response():
            return jsonify({"ok": False, "error": str(exc)}), 400
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    status_code = 200 if result.get("ok") else 502
    if _wants_json_response():
        return jsonify(result), status_code
    if result.get("ok"):
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    if result.get("status") == "not_configured":
        missing_keys = "、".join(result.get("missing_keys") or [])
        return _render_overview_page(page_error=f"消息库尚未配置，请先补齐 {missing_keys}")
    return _render_overview_page(page_error=str(result.get("error") or "消息活跃同步失败"))


def api_admin_automation_conversion_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "detail": get_member_detail(external_contact_id=external_contact_id, phone=phone)})


def _json_action_payload() -> dict[str, str]:
    payload = request.get_json(silent=True) or {}
    return {
        "external_contact_id": str(payload.get("external_contact_id") or "").strip(),
        "phone": str(payload.get("phone") or "").strip(),
        "operator_id": _operator_from_request(),
    }


def _run_member_action(action_fn):
    payload = _json_action_payload()
    try:
        result = action_fn(**payload)
        return jsonify({"ok": True, **result})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_put_in_pool():
    return _run_member_action(put_in_pool)


def api_admin_automation_conversion_remove_from_pool():
    return _run_member_action(remove_from_pool)


def api_admin_automation_conversion_set_focus():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="focus"))


def api_admin_automation_conversion_set_normal():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="normal"))


def api_admin_automation_conversion_mark_won():
    return _run_member_action(mark_won)


def api_admin_automation_conversion_unmark_won():
    return _run_member_action(unmark_won)


def api_admin_automation_conversion_push_openclaw():
    payload = _json_action_payload()
    try:
        result = push_openclaw(**payload)
        if result.get("accepted"):
            return jsonify({"ok": True, **result}), 202
        if result.get("status") == "cooldown_blocked":
            return jsonify({"ok": False, "error": f"OpenClaw 冷却中，还剩 {result.get('remaining_seconds') or 0} 秒", **result}), 429
        return jsonify({"ok": False, "error": str(result.get("error") or "OpenClaw 推送失败"), **result}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_stage_manual_send_preview(stage_key: str):
    try:
        images = _stage_send_images_from_request()
        payload = preview_stage_manual_send(
            route_key=stage_key,
            content=str(request.form.get("content") or request.values.get("content") or "").strip(),
            image_media_ids=list((request.form.getlist("image_media_ids") or request.values.getlist("image_media_ids") or [])),
            images=images,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def api_admin_automation_conversion_stage_manual_send(stage_key: str):
    payload = request.get_json(silent=True) if request.is_json else {}
    try:
        result = send_stage_manual_message(
            route_key=stage_key,
            content=str((payload or {}).get("content") or request.values.get("content") or "").strip(),
            image_media_ids=list((payload or {}).get("image_media_ids") or []),
            images=list((payload or {}).get("images") or []),
            attachments=list((payload or {}).get("attachments") or []),
            operator_id=_operator_from_request(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def _segment_broadcast_payload() -> dict:
    payload = request.get_json(silent=True) if request.is_json else None
    return payload if isinstance(payload, dict) else {}


def _request_segment_broadcast_keys(field: str, payload: dict | None = None) -> list[str]:
    """Read multi-select keys from JSON body (preferred) or form/query."""
    payload = _segment_broadcast_payload() if payload is None else payload
    if isinstance(payload, dict):
        raw = payload.get(field) or payload.get(f"{field}[]")
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str) and raw.strip():
            return [raw.strip()]
    raw_list = (
        request.values.getlist(field)
        or request.values.getlist(f"{field}[]")
    )
    return [str(item).strip() for item in raw_list if str(item).strip()]


def _request_segment_broadcast_keyword(payload: dict | None = None) -> str:
    payload = _segment_broadcast_payload() if payload is None else payload
    if payload.get("keyword") is not None:
        return str(payload.get("keyword") or "").strip()
    return str(request.values.get("keyword") or "").strip()


def api_admin_automation_program_member_segment_search(program_id: int):
    """List members by multi-dim segment filter + return chip metadata."""
    payload = _segment_broadcast_payload()
    pool_keys = _request_segment_broadcast_keys("pool_keys", payload)
    profile_keys = _request_segment_broadcast_keys("profile_keys", payload)
    behavior_keys = _request_segment_broadcast_keys("behavior_keys", payload)
    keyword = _request_segment_broadcast_keyword(payload)
    page = int(request.values.get("page") or 1)
    page_size = int(request.values.get("page_size") or 50)
    try:
        from ..domains.automation_conversion import workflow_service as _ws
        _ws._build_dashboard_audience_member_details(program_id=int(program_id or 0) or None)
    except Exception:
        pass
    try:
        result = member_segment_search_service.search_members(
            pool_keys=pool_keys,
            profile_keys=profile_keys,
            behavior_keys=behavior_keys,
            keyword=keyword,
            page=page,
            page_size=page_size,
            program_id=program_id,
        )
        metadata = member_segment_search_service.get_dimension_metadata(
            program_id=program_id,
        )
    except Exception as exc:
        current_app.logger.exception(
            "segment search failed: program_id=%s", program_id
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "metadata": metadata, **result})


def api_admin_automation_program_member_segment_broadcast(program_id: int):
    """Broadcast to the multi-dim filtered audience via the unified send pipeline."""
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = _segment_broadcast_payload()
    pool_keys = _request_segment_broadcast_keys("pool_keys", payload)
    profile_keys = _request_segment_broadcast_keys("profile_keys", payload)
    behavior_keys = _request_segment_broadcast_keys("behavior_keys", payload)
    keyword = _request_segment_broadcast_keyword(payload)
    content = str(payload.get("content") or request.values.get("content") or "").strip()
    images = list(payload.get("images") or [])
    try:
        try:
            from ..domains.automation_conversion import workflow_service as _ws
            _ws._build_dashboard_audience_member_details(program_id=int(program_id or 0) or None)
        except Exception:
            pass
        broadcast_targets = member_segment_search_service.list_broadcast_targets(
            pool_keys=pool_keys,
            profile_keys=profile_keys,
            behavior_keys=behavior_keys,
            keyword=keyword,
            program_id=program_id,
        )
        snapshot = member_segment_search_service.filter_snapshot(
            pool_keys=pool_keys,
            profile_keys=profile_keys,
            behavior_keys=behavior_keys,
            keyword=keyword,
        )
        result = send_stage_manual_message(
            members=broadcast_targets,
            filter_snapshot=snapshot,
            skip_delivery_tracking=True,
            content=content,
            images=images,
            operator_id=_operator_from_request(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception(
            "segment broadcast failed: program_id=%s", program_id
        )
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(result)


def api_admin_automation_conversion_focus_send_batch_create(stage_key: str):
    try:
        result = create_focus_send_batch(
            route_key=stage_key,
            operator_id=_operator_from_request(),
            operator_type="user",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result), 201


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


def api_admin_automation_conversion_router_pending_callbacks():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = list_router_pending_callbacks(
        older_than_minutes=_query_int("older_than_minutes", default=15, minimum=1, maximum=24 * 60),
        limit=_query_int("limit", default=20, minimum=1, maximum=100),
        visibility="full",
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_callback_replay(run_id: str):
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    try:
        payload = replay_router_callback(run_id, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_pending_callback_check():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_pending_callback_check(
        older_than_minutes=payload.get("older_than_minutes"),
        limit=int(payload.get("limit") or 100),
        operator_id=_operator_from_request(),
    )
    return jsonify(result)


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


def api_admin_automation_conversion_default_channel_settings():
    return jsonify({"ok": True, **get_default_channel_settings_payload(program_id=_request_program_id_or_default())})


def api_admin_automation_conversion_settings_payload():
    return jsonify({"ok": True, "settings": get_settings_payload(program_id=_request_program_id_or_default())})


def api_admin_automation_conversion_settings_save():
    payload = request.get_json(silent=True) or {}
    try:
        result = save_settings(payload, program_id=_payload_program_id(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "settings": result})


def api_admin_automation_conversion_default_channel_settings_save():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = save_default_channel_settings(payload, program_id=_payload_program_id(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_default_channel_generate_qr():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    result = generate_default_channel_qr(operator=_operator_from_request(), program_id=_payload_program_id(payload))
    status_code = int(result.get("status_code") or (200 if result.get("generated") else 400))
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_conversion_settings_default_channel_generate_qr():
    payload = request.get_json(silent=True) or {}
    result = generate_default_channel_qr(operator=_operator_from_request(), program_id=_payload_program_id(payload))
    status_code = int(result.get("status_code") or (200 if result.get("generated") else 400))
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_program_setup(program_id: int):
    try:
        payload = get_program_setup_payload(int(program_id), step=_query_text("step") or "basic")
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "setup": payload})


def api_admin_automation_program_setup_basic(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_setup_basic(int(program_id), payload, operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_entry_channel(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_entry_channel(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_segmentation(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_segmentation(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_audience_entry_rule(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_audience_entry_rule(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_publish_check(program_id: int):
    try:
        result = build_publish_check(int(program_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "publish_check": result})


def api_admin_automation_program_publish_entry(program_id: int):
    try:
        result = publish_entry(int(program_id), operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_publish_full(program_id: int):
    try:
        result = publish_full(int(program_id), operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_customer_acquisition_links(program_id: int):
    if request.method == "GET":
        from ..domains.automation_conversion.customer_acquisition_service import list_customer_acquisition_links

        status = str(request.args.get("status") or "").strip()
        return jsonify({"ok": True, "links": list_customer_acquisition_links(status=status, program_id=int(program_id))})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_program_customer_acquisition_link(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result}), 201


def _task_program_id_from_request() -> int:
    return _query_int("program_id", default=0, minimum=0, maximum=100000000) or _request_program_id_or_default()


def api_admin_automation_conversion_task_groups():
    program_id = _task_program_id_from_request()
    if request.method == "GET":
        return jsonify({"ok": True, **list_task_groups(int(program_id))})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_task_group(int(program_id), payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_task_group_update(group_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_task_group(int(group_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_group_delete(group_id: int):
    try:
        result = delete_task_group(int(group_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_tasks():
    program_id = _task_program_id_from_request()
    if request.method == "GET":
        payload = list_operation_tasks(
            int(program_id),
            group_id=_query_int("group_id", default=0, minimum=0, maximum=100000000) or None,
            keyword=_query_text("keyword"),
            status=_query_text("status"),
        )
        return jsonify({"ok": True, **payload})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_operation_task(int(program_id), payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_task_detail(task_id: int):
    if request.method == "GET":
        try:
            return jsonify({"ok": True, **get_operation_task(int(task_id))})
        except LookupError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
    payload = request.get_json(silent=True) or {}
    try:
        result = update_operation_task(int(task_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_copy(task_id: int):
    try:
        result = copy_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_task_activate(task_id: int):
    try:
        result = activate_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_pause(task_id: int):
    try:
        result = pause_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_delete(task_id: int):
    try:
        result = delete_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_preview_audience(task_id: int):
    payload = request.get_json(silent=True) or {}
    program_id = int(payload.get("program_id") or _task_program_id_from_request())
    try:
        if int(task_id or 0):
            task = get_operation_task(int(task_id))["task"]
            payload = {**task, **payload}
        result = preview_operation_task_audience(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_tasks_run_due():
    payload = request.get_json(silent=True) or {}
    try:
        result = run_due_operation_tasks(
            program_id=int(payload.get("program_id") or 0) or (_query_int("program_id", default=0, minimum=0, maximum=100000000) or None),
            operator_id=str(payload.get("operator") or _operator_from_request() or "operation_task_runner").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_model_settings():
    return jsonify({"ok": True, **get_model_infra_payload(limit_logs=10)})


def api_admin_automation_conversion_model_settings_save():
    payload = request.get_json(silent=True) or {}
    try:
        result = save_model_infra_settings(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "model_infra": result, **result})


def api_admin_automation_conversion_model_settings_test():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    result = test_model_infra_connection()
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


def api_admin_automation_conversion_profile_segment_catalog():
    return jsonify({"ok": True, **list_conversion_profile_segment_catalog()})


def api_admin_automation_conversion_profile_segment_templates():
    payload = list_conversion_profile_segment_templates(
        enabled_only=_query_bool("enabled_only", default=False),
        program_id=_request_program_id(),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_profile_segment_template_detail(template_id: int):
    try:
        payload = get_conversion_profile_segment_template_bundle(int(template_id))
        program_id = _request_program_id()
        template_program_id = int(((payload.get("template") or {}).get("program_id")) or 0) or None
        if program_id and template_program_id != int(program_id):
            raise LookupError("profile segment template not found")
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "template_bundle": payload, **payload})


def api_admin_automation_conversion_profile_segment_template_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_profile_segment_template(
            payload,
            operator_id=_operator_from_request(),
            program_id=_payload_program_id(payload),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_profile_segment_template_update(template_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_profile_segment_template(
            int(template_id),
            payload,
            operator_id=_operator_from_request(),
            program_id=_payload_program_id(payload),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_registry():
    return jsonify({"ok": True, **list_conversion_workflow_registry()})


def api_admin_automation_conversion_action_templates():
    if request.method == "GET":
        try:
            payload = list_action_templates(
                template_source=_query_text("source") or _query_text("template_source"),
                category=_query_text("category"),
                keyword=_query_text("keyword"),
                include_archived=_query_bool("include_archived", default=False),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, **payload})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_action_template(payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_action_template_generate():
    payload = request.get_json(silent=True) or {}
    try:
        result = generate_action_template(payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_action_template_from_workflow():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_action_template_from_workflow(payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_program_action_from_template(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_action_from_template(int(program_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflows():
    payload = list_conversion_workflows(
        include_archived=_query_bool("include_archived", default=False),
        status=_query_text("status"),
        program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_workflow_detail(workflow_id: int):
    try:
        payload = get_conversion_workflow_model_bundle(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "workflow_bundle": payload})


def api_admin_automation_conversion_dashboard():
    return jsonify(
        {
            "ok": True,
            "dashboard": get_conversion_dashboard_payload(
                program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
            ),
        }
    )


def api_admin_automation_conversion_workflow_summary(workflow_id: int):
    try:
        payload = get_conversion_workflow_detail_summary(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "summary": payload})


def api_admin_automation_conversion_workflow_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_workflow(
            payload,
            operator_id=_operator_from_request(),
            program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflow_update(workflow_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_workflow(int(workflow_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_activate(workflow_id: int):
    try:
        result = activate_conversion_workflow(int(workflow_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_pause(workflow_id: int):
    try:
        result = pause_conversion_workflow(int(workflow_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_delete(workflow_id: int):
    try:
        result = delete_conversion_workflow(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_node_list(workflow_id: int):
    try:
        payload = list_conversion_workflow_nodes(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_workflow_node_create(workflow_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_workflow_node(int(workflow_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflow_node_update(node_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_workflow_node(int(node_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_node_delete(node_id: int):
    try:
        result = delete_conversion_workflow_node(int(node_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_execution_batches():
    try:
        payload = list_conversion_workflow_execution_records(
            workflow_id=_query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None,
            node_id=_query_int("node_id", default=0, minimum=0, maximum=100000000) or None,
            program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
            limit=_query_int("limit", default=20, minimum=1, maximum=100),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_detail(execution_id: int):
    try:
        payload = get_conversion_workflow_execution_detail(int(execution_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_items(execution_id: int):
    try:
        payload = list_conversion_workflow_execution_items(int(execution_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_item_detail(execution_item_id: int):
    try:
        payload = get_conversion_workflow_execution_item_detail(int(execution_item_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_item_send_via_bazhuayu(execution_item_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        payload = send_conversion_execution_item_via_bazhuayu(
            int(execution_item_id),
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify(payload)


def api_admin_automation_conversion_profile_segment_template_options():
    return jsonify(
        {
            "ok": True,
            **list_conversion_profile_segment_template_options(
                enabled_only=_query_bool("enabled_only", default=True),
                program_id=_request_program_id(),
            ),
        }
    )


def api_admin_automation_conversion_review_outputs():
    payload = list_recent_laohuang_review_outputs(
        limit=_query_int("limit", default=20, minimum=1, maximum=50),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_review_output(output_id: str):
    payload = request.get_json(silent=True) or {}
    decision = _query_text("decision") or str(payload.get("decision") or "").strip()
    review_note = str(payload.get("review_note") or request.values.get("review_note") or "").strip()
    normalized_decision = decision.lower()
    is_rejected = normalized_decision in {"reject", "rejected", "not_adopted", "declined"}
    if is_rejected and not review_note:
        return jsonify({"ok": False, "error": "review_note is required when decision is rejected"}), 400
    try:
        reviewed_output = review_agent_reply_output(
            output_id,
            decision=decision,
            operator_id=_operator_from_request(),
            review_note=review_note,
            source="automation_conversion_auto_reply",
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    response_payload = {
        "ok": True,
        "reviewed_output": reviewed_output,
    }
    if is_rejected:
        response_payload["clipboard_text"] = build_rejected_feedback_clipboard_payload(
            output_id,
            not_adopted_reason=review_note,
        )
    return jsonify(response_payload)


def api_admin_automation_conversion_review_output_send_via_bazhuayu(output_id: str):
    return api_admin_automation_conversion_review_output_send_via_webhook(output_id)


def api_admin_automation_conversion_review_output_send_via_webhook(output_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        if str(output_id or "").strip().startswith("lhjob-") or str(output_id or "").strip().isdigit():
            payload = send_laohuang_review_output_via_webhook(
                output_id,
                operator_id=_operator_from_request(),
            )
        else:
            payload = send_agent_reply_output_via_bazhuayu(
                output_id,
                operator_id=_operator_from_request(),
            )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify(payload)


def api_admin_automation_conversion_review_output_send_via_wecom(output_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        payload = send_laohuang_review_output_via_wecom(
            output_id,
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload), 200 if payload.get("ok") else 502


def api_admin_automation_conversion_run_message_activity_sync():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="system",
        trigger_source=str(payload.get("trigger_source") or request.values.get("trigger_source") or "scheduled").strip() or "scheduled",
    )
    if result.get("ok"):
        status_code = 200
    elif result.get("status") == "not_configured":
        status_code = 400
    else:
        status_code = 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_capture():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 500),
    )
    status_code = 200 if result.get("ok") or result.get("status") == "disabled" else 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 20),
    )
    status_code = 200 if result.get("ok") or result.get("status") in {"disabled", "idle", "throttled", "quiet_hours"} else 502
    return jsonify(result), status_code


def api_internal_automation_conversion_lobster_results():
    auth_failure = require_internal_api_token(token_keys=("AUTOMATION_LOBSTER_CALLBACK_TOKEN",), require_configured=True)
    if auth_failure is not None:
        return auth_failure
    body_text = request.get_data(cache=True, as_text=True) or ""
    signature_ok, signature_error = validate_router_callback_signature(body_text=body_text, headers=dict(request.headers))
    if not signature_ok:
        return jsonify({"ok": False, "error": signature_error}), 401
    payload = request.get_json(silent=True) or {}
    result = handle_agent_router_callback(payload)
    if result.get("ok") and result.get("status") in {"applied", "idempotent"}:
        return jsonify(result), 200
    if result.get("status") == "rejected":
        status_code = 404 if result.get("error") == "request_not_found" else 409
        return jsonify(result), status_code
    return jsonify(result), 400


def api_internal_automation_conversion_laohuang_chat_results():
    payload = request.get_json(silent=True) or {}
    result = handle_laohuang_chat_result_callback(payload)
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


def api_internal_automation_conversion_router_test_dispatch():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_test_dispatch(
        external_contact_id=str(payload.get("external_contact_id") or request.values.get("external_contact_id") or "").strip(),
        phone=str(payload.get("phone") or request.values.get("phone") or "").strip(),
        operator_id=str(payload.get("operator") or _operator_from_request() or "").strip(),
        mode=str(payload.get("mode") or request.values.get("mode") or "").strip(),
        force_capture=_json_bool(payload.get("force_capture")) or str(request.values.get("force_capture") or "").strip().lower() in {"1", "true", "yes", "on"},
        force_run_due=_json_bool(payload.get("force_run_due")) or str(request.values.get("force_run_due") or "").strip().lower() in {"1", "true", "yes", "on"},
    )
    status_code = 200 if result.get("ok") else (404 if result.get("error") == "member_not_found" else 409)
    return jsonify(result), status_code


def api_admin_automation_conversion_jobs_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    try:
        result = run_registered_due_jobs(
            job_codes=list(payload.get("jobs") or []),
            operator_id=_operator_from_request(),
            operator_type="system",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def register_routes(bp):
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/programs/new", methods=["GET"])(admin_automation_program_new)
    bp.route("/admin/automation-conversion/programs", methods=["POST"])(admin_automation_program_create)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/update", methods=["POST"])(admin_automation_program_update)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/copy", methods=["POST"])(admin_automation_program_copy)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/activate", methods=["POST"])(admin_automation_program_activate)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/pause", methods=["POST"])(admin_automation_program_pause)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/archive", methods=["POST"])(admin_automation_program_archive)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/setup", methods=["GET"])(admin_automation_program_setup)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview", methods=["GET"])(admin_automation_program_overview)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations", methods=["GET"])(admin_automation_program_operations)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows", methods=["GET"])(admin_automation_program_workflows)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/new", methods=["GET"])(admin_automation_program_workflow_new)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/<int:workflow_id>/edit", methods=["GET"])(admin_automation_program_workflow_edit)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/<int:workflow_id>/nodes", methods=["GET"])(admin_automation_program_workflow_nodes)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/executions", methods=["GET"])(admin_automation_program_executions)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/flow-design", methods=["GET"])(admin_automation_program_flow_design)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/member-ops", methods=["GET"])(admin_automation_program_member_ops)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send", methods=["POST"])(admin_automation_program_member_ops_stage_send)
    bp.route(
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-search",
        methods=["GET", "POST"],
    )(api_admin_automation_program_member_segment_search)
    bp.route(
        "/api/admin/automation-conversion/programs/<int:program_id>/members/segment-broadcast",
        methods=["POST"],
    )(api_admin_automation_program_member_segment_broadcast)
    bp.route("/admin/automation-conversion/shared/agents", methods=["GET"])(admin_automation_conversion_shared_agents)
    bp.route("/admin/automation-conversion/shared/profile-segments", methods=["GET"])(admin_automation_conversion_shared_profile_segments)
    bp.route("/admin/automation-conversion/shared/model-infra", methods=["GET"])(admin_automation_conversion_shared_model_infra)
    bp.route("/admin/automation-conversion/runtime", methods=["GET"])(admin_automation_conversion_runtime)
    bp.route("/admin/automation-conversion/runtime/sync", methods=["GET"])(admin_automation_conversion_runtime_sync)
    bp.route("/admin/automation-conversion/runtime/router", methods=["GET"])(admin_automation_conversion_runtime_router)
    bp.route("/admin/automation-conversion/runtime/logs", methods=["GET"])(admin_automation_conversion_runtime_logs)
    bp.route("/admin/automation-conversion/runtime/debug", methods=["GET"])(admin_automation_conversion_runtime_debug)
    bp.route("/admin/automation-conversion/settings/save", methods=["POST"])(admin_automation_conversion_save_settings)
    bp.route("/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(admin_automation_conversion_generate_default_channel)
    bp.route("/admin/automation-conversion/auto-reply", methods=["GET"])(admin_automation_conversion_auto_reply)
    bp.route("/admin/automation-conversion/agent-orchestration/agents/<agent_code>/save-draft", methods=["POST"])(admin_automation_conversion_agent_orchestration_save_draft)
    bp.route("/admin/automation-conversion/agent-orchestration/outputs/<output_id>/review", methods=["POST"])(admin_automation_conversion_agent_orchestration_review_output)
    bp.route("/admin/automation-conversion/agent-orchestration/replay/<run_id>", methods=["POST"])(admin_automation_conversion_agent_orchestration_replay)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview/signup-tag/apply", methods=["POST"])(admin_automation_program_overview_signup_tag_apply)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview/message-activity-sync/run", methods=["POST"])(admin_automation_program_overview_message_activity_sync_run)
    bp.route("/admin/automation-conversion/auto-reply/reply-monitor/toggle", methods=["POST"])(admin_automation_auto_reply_monitor_toggle)
    bp.route("/admin/automation-conversion/auto-reply/reply-monitor/capture", methods=["POST"])(admin_automation_auto_reply_monitor_capture)
    bp.route("/admin/automation-conversion/auto-reply/reply-monitor/run-due", methods=["POST"])(admin_automation_auto_reply_monitor_run_due)

    bp.route("/api/admin/automation-conversion/member", methods=["GET"])(api_admin_automation_conversion_member)
    bp.route("/api/admin/automation-conversion/member/put-in-pool", methods=["POST"])(api_admin_automation_conversion_put_in_pool)
    bp.route("/api/admin/automation-conversion/member/remove-from-pool", methods=["POST"])(api_admin_automation_conversion_remove_from_pool)
    bp.route("/api/admin/automation-conversion/member/set-focus", methods=["POST"])(api_admin_automation_conversion_set_focus)
    bp.route("/api/admin/automation-conversion/member/set-normal", methods=["POST"])(api_admin_automation_conversion_set_normal)
    bp.route("/api/admin/automation-conversion/member/mark-won", methods=["POST"])(api_admin_automation_conversion_mark_won)
    bp.route("/api/admin/automation-conversion/member/unmark-won", methods=["POST"])(api_admin_automation_conversion_unmark_won)
    bp.route("/api/admin/automation-conversion/member/push-openclaw", methods=["POST"])(api_admin_automation_conversion_push_openclaw)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview", methods=["POST"])(api_admin_automation_conversion_stage_manual_send_preview)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send", methods=["POST"])(api_admin_automation_conversion_stage_manual_send)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches", methods=["POST"])(api_admin_automation_conversion_focus_send_batch_create)
    bp.route("/api/admin/automation-conversion/focus-send-batches/<batch_id>", methods=["GET"])(api_admin_automation_conversion_focus_send_batch_detail)
    bp.route("/api/admin/automation-conversion/focus-send-batches/run-due", methods=["POST"])(api_admin_automation_conversion_focus_send_batch_run_due)
    bp.route("/api/admin/automation-conversion/sop/config", methods=["GET"])(api_admin_automation_conversion_sop_config_list)
    bp.route("/api/admin/automation-conversion/sop/config/<pool_key>", methods=["PUT"])(api_admin_automation_conversion_sop_config_save)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>", methods=["GET"])(api_admin_automation_conversion_sop_templates)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", methods=["PUT"])(api_admin_automation_conversion_sop_template_save)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", methods=["DELETE"])(api_admin_automation_conversion_sop_template_delete)
    bp.route("/api/admin/automation-conversion/sop/run-due", methods=["POST"])(api_admin_automation_conversion_sop_run_due)
    bp.route("/api/admin/automation-conversion/dashboard", methods=["GET"])(api_admin_automation_conversion_dashboard)
    bp.route("/api/admin/automation-conversion/settings", methods=["GET"])(api_admin_automation_conversion_settings_payload)
    bp.route("/api/admin/automation-conversion/settings", methods=["POST"])(api_admin_automation_conversion_settings_save)
    bp.route("/api/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(api_admin_automation_conversion_settings_default_channel_generate_qr)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup", methods=["GET"])(api_admin_automation_program_setup)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/basic", methods=["POST"])(api_admin_automation_program_setup_basic)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/entry-channel", methods=["POST"])(api_admin_automation_program_setup_entry_channel)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/segmentation", methods=["POST"])(api_admin_automation_program_setup_segmentation)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/audience-entry-rule", methods=["POST"])(api_admin_automation_program_setup_audience_entry_rule)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/setup/publish-check", methods=["GET"])(api_admin_automation_program_setup_publish_check)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/publish-entry", methods=["POST"])(api_admin_automation_program_publish_entry)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/publish-full", methods=["POST"])(api_admin_automation_program_publish_full)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/customer-acquisition-links", methods=["GET", "POST"])(api_admin_automation_program_customer_acquisition_links)
    bp.route("/api/admin/automation-conversion/task-groups", methods=["GET", "POST"])(api_admin_automation_conversion_task_groups)
    bp.route("/api/admin/automation-conversion/task-groups/<int:group_id>", methods=["PUT"])(api_admin_automation_conversion_task_group_update)
    bp.route("/api/admin/automation-conversion/task-groups/<int:group_id>", methods=["DELETE"])(api_admin_automation_conversion_task_group_delete)
    bp.route("/api/admin/automation-conversion/tasks", methods=["GET", "POST"])(api_admin_automation_conversion_tasks)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>", methods=["GET", "PUT"])(api_admin_automation_conversion_task_detail)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/copy", methods=["POST"])(api_admin_automation_conversion_task_copy)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/activate", methods=["POST"])(api_admin_automation_conversion_task_activate)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/pause", methods=["POST"])(api_admin_automation_conversion_task_pause)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>", methods=["DELETE"])(api_admin_automation_conversion_task_delete)
    bp.route("/api/admin/automation-conversion/tasks/<int:task_id>/preview-audience", methods=["POST"])(api_admin_automation_conversion_task_preview_audience)
    bp.route("/api/admin/automation-conversion/tasks/run-due", methods=["POST"])(api_admin_automation_conversion_tasks_run_due)
    bp.route("/api/admin/automation-conversion/action-templates", methods=["GET", "POST"])(api_admin_automation_conversion_action_templates)
    bp.route("/api/admin/automation-conversion/action-templates/generate", methods=["POST"])(api_admin_automation_conversion_action_template_generate)
    bp.route("/api/admin/automation-conversion/action-templates/from-workflow", methods=["POST"])(api_admin_automation_conversion_action_template_from_workflow)
    bp.route("/api/admin/automation-conversion/programs/<int:program_id>/actions/from-template", methods=["POST"])(api_admin_automation_program_action_from_template)
    bp.route("/api/admin/automation-conversion/agent-outputs", methods=["GET"])(api_admin_automation_conversion_agent_outputs)
    bp.route("/api/admin/automation-conversion/agent-outputs/<output_id>", methods=["GET"])(api_admin_automation_conversion_agent_output_detail)
    bp.route("/api/admin/automation-conversion/agent-runs/<run_id>", methods=["GET"])(api_admin_automation_conversion_agent_run_detail)
    bp.route("/api/admin/automation-conversion/agent-outputs/export", methods=["POST"])(api_admin_automation_conversion_agent_outputs_export)
    bp.route("/api/admin/automation-conversion/agent-outputs/export/<job_id>", methods=["GET"])(api_admin_automation_conversion_agent_outputs_export_detail)
    bp.route("/api/admin/automation-conversion/agent-replay", methods=["GET"])(api_admin_automation_conversion_agent_replay)
    bp.route("/api/admin/automation-conversion/agent-orchestration/pending-publish", methods=["GET"])(api_admin_automation_conversion_pending_publish)
    bp.route("/api/admin/automation-conversion/agents", methods=["POST"])(api_admin_automation_conversion_agent_create)
    bp.route("/api/admin/automation-conversion/agents/options", methods=["GET"])(api_admin_automation_conversion_agent_options)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>", methods=["GET"])(api_admin_automation_conversion_agent_detail)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>", methods=["DELETE"])(api_admin_automation_conversion_agent_delete)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>/draft", methods=["POST"])(api_admin_automation_conversion_agent_draft)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>/publish", methods=["POST"])(api_admin_automation_conversion_agent_publish)
    bp.route("/api/admin/automation-conversion/default-channel-settings", methods=["GET"])(api_admin_automation_conversion_default_channel_settings)
    bp.route("/api/admin/automation-conversion/default-channel-settings", methods=["PUT"])(api_admin_automation_conversion_default_channel_settings_save)
    bp.route("/api/admin/automation-conversion/default-channel-settings/generate-qr", methods=["POST"])(api_admin_automation_conversion_default_channel_generate_qr)
    bp.route("/api/admin/automation-conversion/model-settings", methods=["GET"])(api_admin_automation_conversion_model_settings)
    bp.route("/api/admin/automation-conversion/model-settings", methods=["PUT"])(api_admin_automation_conversion_model_settings_save)
    bp.route("/api/admin/automation-conversion/model-settings/test", methods=["POST"])(api_admin_automation_conversion_model_settings_test)
    bp.route("/api/admin/automation-conversion/router-pending-callbacks", methods=["GET"])(api_admin_automation_conversion_router_pending_callbacks)
    bp.route("/api/admin/automation-conversion/router-callback-replay/<run_id>", methods=["POST"])(api_admin_automation_conversion_router_callback_replay)
    bp.route("/api/admin/automation-conversion/router-pending-callback-check", methods=["POST"])(api_admin_automation_conversion_router_pending_callback_check)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/catalog", methods=["GET"])(api_admin_automation_conversion_profile_segment_catalog)
    bp.route("/api/admin/automation-conversion/profile-segment-templates", methods=["GET"])(api_admin_automation_conversion_profile_segment_templates)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/options", methods=["GET"])(api_admin_automation_conversion_profile_segment_template_options)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", methods=["GET"])(api_admin_automation_conversion_profile_segment_template_detail)
    bp.route("/api/admin/automation-conversion/profile-segment-templates", methods=["POST"])(api_admin_automation_conversion_profile_segment_template_create)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", methods=["PUT"])(api_admin_automation_conversion_profile_segment_template_update)
    bp.route("/api/admin/automation-conversion/review-outputs", methods=["GET"])(api_admin_automation_conversion_review_outputs)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/review", methods=["POST"])(api_admin_automation_conversion_review_output)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/send-via-webhook", methods=["POST"])(api_admin_automation_conversion_review_output_send_via_webhook)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/send-via-wecom", methods=["POST"])(api_admin_automation_conversion_review_output_send_via_wecom)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/send-via-bazhuayu", methods=["POST"])(api_admin_automation_conversion_review_output_send_via_bazhuayu)
    bp.route("/api/admin/automation-conversion/workflows/registry", methods=["GET"])(api_admin_automation_conversion_workflow_registry)
    bp.route("/api/admin/automation-conversion/workflows", methods=["GET"])(api_admin_automation_conversion_workflows)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["GET"])(api_admin_automation_conversion_workflow_detail)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/summary", methods=["GET"])(api_admin_automation_conversion_workflow_summary)
    bp.route("/api/admin/automation-conversion/workflows", methods=["POST"])(api_admin_automation_conversion_workflow_create)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["PUT"])(api_admin_automation_conversion_workflow_update)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["DELETE"])(api_admin_automation_conversion_workflow_delete)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/activate", methods=["POST"])(api_admin_automation_conversion_workflow_activate)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/pause", methods=["POST"])(api_admin_automation_conversion_workflow_pause)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", methods=["GET"])(api_admin_automation_conversion_workflow_node_list)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", methods=["POST"])(api_admin_automation_conversion_workflow_node_create)
    bp.route("/api/admin/automation-conversion/workflow-nodes/<int:node_id>", methods=["PUT"])(api_admin_automation_conversion_workflow_node_update)
    bp.route("/api/admin/automation-conversion/workflow-nodes/<int:node_id>", methods=["DELETE"])(api_admin_automation_conversion_workflow_node_delete)
    bp.route("/api/admin/automation-conversion/executions", methods=["GET"])(api_admin_automation_conversion_execution_batches)
    bp.route("/api/admin/automation-conversion/executions/<int:execution_id>", methods=["GET"])(api_admin_automation_conversion_execution_detail)
    bp.route("/api/admin/automation-conversion/executions/<int:execution_id>/items", methods=["GET"])(api_admin_automation_conversion_execution_items)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>", methods=["GET"])(api_admin_automation_conversion_execution_item_detail)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>/send-via-bazhuayu", methods=["POST"])(api_admin_automation_conversion_execution_item_send_via_bazhuayu)
    bp.route("/api/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(api_admin_automation_conversion_run_message_activity_sync)
    bp.route("/api/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(api_admin_automation_conversion_reply_monitor_capture)
    bp.route("/api/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(api_admin_automation_conversion_reply_monitor_run_due)
    bp.route("/api/internal/automation-conversion/lobster-results", methods=["POST"])(api_internal_automation_conversion_lobster_results)
    bp.route("/api/internal/automation-conversion/laohuang-chat-results", methods=["POST"])(api_internal_automation_conversion_laohuang_chat_results)
    bp.route("/api/internal/automation-conversion/router-test-dispatch", methods=["POST"])(api_internal_automation_conversion_router_test_dispatch)
    bp.route("/api/admin/automation-conversion/jobs/run-due", methods=["POST"])(api_admin_automation_conversion_jobs_run_due)
