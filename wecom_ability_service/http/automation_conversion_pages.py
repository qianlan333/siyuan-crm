from __future__ import annotations

from flask import redirect, url_for

from ..domains.automation_conversion.program_service import (
    copy_automation_program,
    create_automation_program,
    update_automation_program_basic_info,
    update_automation_program_status,
)
from ._routes_helpers import (
    _default_program_id_or_none,
    _load_program_or_404,
    _operator_from_request,
    _query_text,
)
from .automation_conversion_form_helpers import (
    _program_action_redirect,
    _program_basic_info_payload,
    _program_form_payload,
)
from .automation_conversion_render import (
    _render_agent_config_page,
    _render_auto_reply_page,
    _render_execution_records_page,
    _render_member_ops_page,
    _render_overview_page,
    _render_program_list_page,
    _render_program_setup_page,
    _render_run_center_page,
)
from .internal_auth import validate_admin_console_action_token


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


def _program_setup_redirect(program_id: int, step: str):
    return redirect(
        url_for("api.admin_automation_program_setup", program_id=int(program_id), step=step),
        code=302,
    )


def admin_automation_conversion_auto_reply():
    return _render_auto_reply_page()


def admin_automation_program_overview(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_overview_page(program=program)


def admin_automation_program_setup(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_program_setup_page(
        program=program,
        step=_query_text("step") or "basic",
        audience_picker=_query_text("audience_picker"),
    )


def admin_automation_program_operations(program_id: int):
    _load_program_or_404(program_id)
    return _program_setup_redirect(program_id, "operations")


def admin_automation_program_workflows(program_id: int):
    _load_program_or_404(program_id)
    return _program_setup_redirect(program_id, "operations")


def admin_automation_program_workflow_new(program_id: int):
    _load_program_or_404(program_id)
    return _program_setup_redirect(program_id, "operations")


def admin_automation_program_workflow_edit(program_id: int, workflow_id: int):
    _load_program_or_404(program_id)
    return _program_setup_redirect(program_id, "operations")


def admin_automation_program_workflow_nodes(program_id: int, workflow_id: int):
    _load_program_or_404(program_id)
    return _program_setup_redirect(program_id, "operations")


def admin_automation_program_executions(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_execution_records_page(program=program)


def admin_automation_program_flow_design(program_id: int):
    _load_program_or_404(program_id)
    return _program_setup_redirect(program_id, "segmentation")


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
