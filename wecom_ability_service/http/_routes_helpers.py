"""Helpers for http/automation_conversion.py route handlers (阶段 7.1).

Extracted from automation_conversion.py to keep handler file focused.
All helpers are private (underscore-prefixed) — explicit re-export
via __all__ so callers can `from ._routes_helpers import (a, b, ...)`.
"""

from __future__ import annotations

import base64


from flask import abort, redirect, request, url_for

from ..domains.automation_conversion.focus_send_service import (
    get_focus_send_batch_detail,
    get_focus_send_batches_payload,
)
from ..domains.automation_conversion.model_infra_service import (
    get_model_infra_payload,
)
from ..domains.automation_conversion.orchestration_service import (
    get_agent_orchestration_payload,
    get_agent_replay_payload,
    list_agent_configs,
)
from ..domains.automation_conversion.program_service import (
    get_automation_program,
    get_default_automation_program_id,
    list_automation_programs,
)
from ..domains.automation_conversion.program_setup_service import get_program_setup_payload, normalize_setup_step
from ..domains.automation_conversion.service import (
    get_debug_payload,
    get_overview_payload,
    get_settings_payload,
    get_stage_detail_payload,
)
from ..domains.wecom_media_limits import (
    detect_wecom_image_mime_type,
    validate_wecom_image_upload,
)
from ..domains.automation_conversion.sop_service import (
    get_sop_v1_batches_payload,
)
from ..domains.automation_conversion.workflow_service import (
    list_conversion_agent_options,
    list_conversion_profile_segment_catalog,
    list_conversion_profile_segment_templates,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_int(name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _query_bool(name: str, *, default: bool = False) -> bool:
    raw_value = request.args.get(name)
    if raw_value is None:
        return bool(default)
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _overview_notice() -> str:
    reply_monitor_action = _query_text("reply_monitor")
    if reply_monitor_action == "enabled":
        return "自动接话已开启"
    if reply_monitor_action == "disabled":
        return "自动接话已关闭"
    if reply_monitor_action == "captured":
        return "自动接话扫描已完成"
    if reply_monitor_action == "dispatched":
        return "自动接话放行已执行"
    return ""


FLOW_DESIGN_SECTIONS = ("profile-segments", "channel")
RUN_CENTER_TABS = ("overview", "sync", "logs", "model-infra", "agent-orchestration", "debug")
RUN_CENTER_AGENT_SUBTABS = ("router", "agents", "metrics", "outputs", "replay")


def _detect_stage_send_image_type(file_bytes: bytes) -> str:
    detected = detect_wecom_image_mime_type(file_bytes)
    if detected == "image/png":
        return "png"
    if detected == "image/jpeg":
        return "jpeg"
    return ""


def _stage_send_images_from_request() -> list[dict[str, str]]:
    files = [item for item in list(request.files.getlist("images") or []) if getattr(item, "filename", "")]
    if len(files) > 3:
        raise ValueError("at most 3 images are allowed")
    images: list[dict[str, str]] = []
    for index, file_storage in enumerate(files, start=1):
        file_name = str(getattr(file_storage, "filename", "") or f"image-{index}.png").strip() or f"image-{index}.png"
        mime_type = str(getattr(file_storage, "mimetype", "") or "").strip().lower()
        if not mime_type.startswith("image/"):
            raise ValueError("only image files are allowed")
        file_bytes = file_storage.read()
        content_type = validate_wecom_image_upload(
            file_bytes,
            file_name=file_name,
            mime_type=mime_type,
        )
        images.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )
    return images


def _flow_design_section() -> str:
    section = _query_text("section") or str(request.values.get("section") or "").strip()
    return section if section in FLOW_DESIGN_SECTIONS else "profile-segments"


def _run_center_tab() -> str:
    tab = _query_text("tab") or str(request.values.get("tab") or "").strip()
    return tab if tab in RUN_CENTER_TABS else "overview"


def _run_center_agent_subtab() -> str:
    subtab = _query_text("subtab") or str(request.values.get("subtab") or "").strip()
    return subtab if subtab in RUN_CENTER_AGENT_SUBTABS else "router"


def _member_ops_stage_key() -> str:
    stage = _query_text("stage") or str(request.values.get("stage") or "").strip()
    return stage or "new-user"


def _member_ops_panel() -> str:
    panel = _query_text("panel") or str(request.values.get("panel") or "").strip()
    return panel or "members"


_AUTOMATION_CONVERSION_WORKSPACE_TABS = (
    {
        "key": "auto_reply",
        "label": "自动化应答",
        "summary": "模块级应答监控与话术处理底座",
        "endpoint": "api.admin_automation_conversion_auto_reply",
        "params": {},
    },
    {
        "key": "agent_config",
        "label": "模型与智能体配置",
        "summary": "共享智能体本体与大模型配置",
        "endpoint": "api.admin_automation_conversion_shared_agents",
        "params": {},
    },
)


def _coerce_program_id(program_id: object) -> int | None:
    try:
        normalized_program_id = int(program_id or 0)
    except (TypeError, ValueError):
        return None
    return normalized_program_id if normalized_program_id > 0 else None


def _request_program_id() -> int | None:
    return _coerce_program_id(request.values.get("program_id"))


def _request_program_id_or_default() -> int | None:
    return _request_program_id() or _default_program_id_or_none()


def _payload_program_id(payload: dict[str, object] | None = None) -> int | None:
    return _request_program_id() or _coerce_program_id((payload or {}).get("program_id")) or _default_program_id_or_none()


def _default_program_id_or_none() -> int | None:
    try:
        return _coerce_program_id(get_default_automation_program_id())
    except Exception:
        return None


def _program_route_or_main(endpoint: str, *, program_id: int | None = None, **params) -> str:
    normalized_program_id = _coerce_program_id(program_id) or _default_program_id_or_none()
    if not normalized_program_id:
        return url_for("api.admin_automation_conversion")
    compact_params = {key: value for key, value in params.items() if value is not None and value != ""}
    return url_for(endpoint, program_id=normalized_program_id, **compact_params)


def _redirect_to_program(endpoint: str, *, program_id: int | None = None, **params):
    return redirect(_program_route_or_main(endpoint, program_id=program_id, **params), code=302)


def _program_route(endpoint: str, program_id: int, **params) -> str:
    return url_for(endpoint, program_id=int(program_id), **params)


def _program_api_params(program_id: int | None = None) -> dict[str, int]:
    normalized_program_id = int(program_id or 0)
    return {"program_id": normalized_program_id} if normalized_program_id > 0 else {}


def _operations_page_api_urls(*, program_id: int | None = None) -> dict[str, str]:
    program_params = _program_api_params(program_id)
    return {
        "registry": url_for("api.api_admin_automation_conversion_workflow_registry"),
        "dashboard": url_for("api.api_admin_automation_conversion_dashboard", **program_params),
        "workflows": url_for("api.api_admin_automation_conversion_workflows", **program_params),
        "workflow_detail_base": url_for("api.api_admin_automation_conversion_workflow_detail", workflow_id=0, **program_params),
        "workflow_summary_base": url_for("api.api_admin_automation_conversion_workflow_summary", workflow_id=0, **program_params),
        "workflow_activate_base": url_for("api.api_admin_automation_conversion_workflow_activate", workflow_id=0, **program_params),
        "workflow_pause_base": url_for("api.api_admin_automation_conversion_workflow_pause", workflow_id=0, **program_params),
        "workflow_delete_base": url_for("api.api_admin_automation_conversion_workflow_delete", workflow_id=0, **program_params),
        "workflow_nodes_base": url_for("api.api_admin_automation_conversion_workflow_node_list", workflow_id=0),
        "workflow_node_base": url_for("api.api_admin_automation_conversion_workflow_node_update", node_id=0),
        "task_groups": url_for("api.api_admin_automation_conversion_task_groups", **program_params),
        "task_group_base": url_for("api.api_admin_automation_conversion_task_group_update", group_id=0),
        "tasks": url_for("api.api_admin_automation_conversion_tasks", **program_params),
        "task_base": url_for("api.api_admin_automation_conversion_task_detail", task_id=0),
        "task_copy_base": url_for("api.api_admin_automation_conversion_task_copy", task_id=0),
        "task_activate_base": url_for("api.api_admin_automation_conversion_task_activate", task_id=0),
        "task_pause_base": url_for("api.api_admin_automation_conversion_task_pause", task_id=0),
        "task_preview_base": url_for("api.api_admin_automation_conversion_task_preview_audience", task_id=0, **program_params),
        "tasks_run_due": url_for("api.api_admin_automation_conversion_tasks_run_due", **program_params),
        "action_templates": url_for("api.api_admin_automation_conversion_action_templates"),
        "action_template_generate": url_for("api.api_admin_automation_conversion_action_template_generate"),
        "action_template_from_workflow": url_for("api.api_admin_automation_conversion_action_template_from_workflow"),
        "action_from_template": _program_route_or_main(
            "api.api_admin_automation_program_action_from_template",
            program_id=program_id,
        ),
        "agents_options": url_for("api.api_admin_automation_conversion_agent_options", enabled_only=0),
        "profile_segment_templates_options": url_for("api.api_admin_automation_conversion_profile_segment_template_options", enabled_only=0, **program_params),
        "profile_segment_templates_catalog": url_for("api.api_admin_automation_conversion_profile_segment_catalog"),
        "profile_segment_template_detail_base": url_for("api.api_admin_automation_conversion_profile_segment_template_detail", template_id=0),
        "executions": url_for("api.api_admin_automation_conversion_execution_batches", **program_params),
        "execution_detail_base": url_for("api.api_admin_automation_conversion_execution_detail", execution_id=0, **program_params),
        "jobs_run_due": url_for("api.api_admin_automation_conversion_jobs_run_due"),
    }


def _operations_page_entry_urls(*, program_id: int | None = None) -> dict[str, str]:
    normalized_program_id = _coerce_program_id(program_id) or _default_program_id_or_none()
    if not normalized_program_id:
        fallback = url_for("api.admin_automation_conversion")
        return {
            "list": fallback,
            "action_orchestration": fallback,
            "workflow_list": fallback,
            "workflow_new": fallback,
            "workflow_edit_base": fallback,
            "workflow_nodes_base": fallback,
            "executions": fallback,
        }
    return {
        "list": _program_route("api.admin_automation_program_operations", normalized_program_id),
        "action_orchestration": _program_route("api.admin_automation_program_operations", normalized_program_id),
        "workflow_list": _program_route("api.admin_automation_program_workflows", normalized_program_id),
        "workflow_new": _program_route("api.admin_automation_program_workflow_new", normalized_program_id),
        "workflow_edit_base": _program_route("api.admin_automation_program_workflow_edit", normalized_program_id, workflow_id=0),
        "workflow_nodes_base": _program_route("api.admin_automation_program_workflow_nodes", normalized_program_id, workflow_id=0),
        "executions": _program_route("api.admin_automation_program_executions", normalized_program_id),
    }


def _build_operations_list_workspace(*, program_id: int | None = None) -> dict[str, object]:
    entry_urls = _operations_page_entry_urls(program_id=program_id)
    return {
        "page_mode": "list",
        "api_urls": _operations_page_api_urls(program_id=program_id),
        "entry_urls": entry_urls,
        "action_urls": {
            "workflow_new": entry_urls["workflow_new"],
            "execution_records": entry_urls["executions"],
        },
    }


def _build_action_orchestration_workspace(workflow_id: int | None = None, *, program_id: int | None = None) -> dict[str, object]:
    normalized_workflow_id = int(workflow_id or 0) or None
    entry_urls = _operations_page_entry_urls(program_id=program_id)
    return {
        "page_mode": "action_orchestration",
        "selected_workflow_id": normalized_workflow_id,
        "api_urls": _operations_page_api_urls(program_id=program_id),
        "entry_urls": entry_urls,
        "action_urls": {
            "list": entry_urls["list"],
            "workflow_list": entry_urls["workflow_list"],
            "workflow_edit": entry_urls["workflow_edit_base"].replace("/0/edit", f"/{normalized_workflow_id or 0}/edit"),
            "workflow_nodes": entry_urls["workflow_nodes_base"].replace("/0/nodes", f"/{normalized_workflow_id or 0}/nodes"),
            "execution_records": entry_urls["executions"],
        },
    }


def _build_workflow_editor_workspace(workflow_id: int | None = None, *, program_id: int | None = None) -> dict[str, object]:
    normalized_workflow_id = int(workflow_id or 0) or None
    page_mode = "workflow_edit" if normalized_workflow_id else "workflow_new"
    entry_urls = _operations_page_entry_urls(program_id=program_id)
    return {
        "page_mode": page_mode,
        "selected_workflow_id": normalized_workflow_id,
        "api_urls": _operations_page_api_urls(program_id=program_id),
        "entry_urls": entry_urls,
        "action_urls": {
            "list": entry_urls["list"],
            "workflow_edit": entry_urls["workflow_edit_base"].replace("/0/edit", f"/{normalized_workflow_id or 0}/edit"),
            "workflow_nodes": entry_urls["workflow_nodes_base"].replace("/0/nodes", f"/{normalized_workflow_id or 0}/nodes"),
            "execution_records": entry_urls["executions"],
        },
    }


def _build_workflow_nodes_workspace(workflow_id: int, *, program_id: int | None = None) -> dict[str, object]:
    normalized_workflow_id = int(workflow_id or 0) or None
    entry_urls = _operations_page_entry_urls(program_id=program_id)
    return {
        "page_mode": "nodes",
        "selected_workflow_id": normalized_workflow_id,
        "api_urls": _operations_page_api_urls(program_id=program_id),
        "entry_urls": entry_urls,
        "action_urls": {
            "list": entry_urls["list"],
            "workflow_edit": entry_urls["workflow_edit_base"].replace("/0/edit", f"/{normalized_workflow_id or 0}/edit"),
            "execution_records": entry_urls["executions"],
        },
    }


def _build_execution_records_workspace(*, program_id: int | None = None) -> dict[str, object]:
    workflow_id = _query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None
    execution_id = _query_int("execution_id", default=0, minimum=0, maximum=100000000) or None
    entry_urls = _operations_page_entry_urls(program_id=program_id)
    return {
        "page_mode": "executions",
        "selected_workflow_id": workflow_id,
        "selected_execution_id": execution_id,
        "api_urls": _operations_page_api_urls(program_id=program_id),
        "entry_urls": entry_urls,
        "action_urls": {
            "list": entry_urls["list"],
            "workflow_edit": entry_urls["workflow_edit_base"].replace("/0/edit", f"/{workflow_id or 0}/edit"),
            "workflow_nodes": entry_urls["workflow_nodes_base"].replace("/0/nodes", f"/{workflow_id or 0}/nodes"),
            "execution_item_bazhuayu_send_base": url_for(
                "api.api_admin_automation_conversion_execution_item_send_via_bazhuayu",
                execution_item_id=0,
            ),
        },
    }


def _build_overview_workspace(*, program_id: int | None = None) -> dict[str, object]:
    snapshot = get_overview_payload()
    return {
        "snapshot": snapshot,
        "api_urls": {
            "dashboard": url_for("api.api_admin_automation_conversion_dashboard", **_program_api_params(program_id)),
            "apply_signup_tag": _program_route_or_main("api.admin_automation_program_overview_signup_tag_apply", program_id=program_id),
            "message_activity_sync_run": _program_route_or_main(
                "api.admin_automation_program_overview_message_activity_sync_run",
                program_id=program_id,
            ),
            "reply_monitor_capture": url_for("api.admin_automation_auto_reply_monitor_capture"),
            "reply_monitor_run_due": url_for("api.admin_automation_auto_reply_monitor_run_due"),
        },
    }


def _build_auto_reply_workspace() -> dict[str, object]:
    overview_payload = get_overview_payload()
    reply_monitor = dict(overview_payload.get("reply_monitor") or {})
    agent_config_bundle = list_agent_configs()
    return {
        "reply_monitor": reply_monitor,
        "message_activity_sync": dict(overview_payload.get("message_activity_sync") or {}),
        "agent_configs": list(agent_config_bundle.get("items") or []),
        "agent_config_total": int(agent_config_bundle.get("total") or 0),
        "agent_config_href": url_for("api.admin_automation_conversion_shared_agents"),
        "action_urls": {
            "toggle": url_for("api.admin_automation_auto_reply_monitor_toggle"),
            "capture": url_for("api.admin_automation_auto_reply_monitor_capture"),
            "run_due": url_for("api.admin_automation_auto_reply_monitor_run_due"),
        },
        "api_urls": {
            "review_outputs": url_for("api.api_admin_automation_conversion_review_outputs"),
            "review_output_base": url_for("api.api_admin_automation_conversion_review_output", output_id="__OUTPUT_ID__"),
            "review_output_webhook_send_base": url_for("api.api_admin_automation_conversion_review_output_send_via_webhook", output_id="__OUTPUT_ID__"),
            "review_output_wecom_send_base": url_for("api.api_admin_automation_conversion_review_output_send_via_wecom", output_id="__OUTPUT_ID__"),
            "review_output_bazhuayu_send_base": url_for("api.api_admin_automation_conversion_review_output_send_via_bazhuayu", output_id="__OUTPUT_ID__"),
        },
    }


def _build_agent_config_workspace() -> dict[str, object]:
    return {
        "api_urls": {
            "registry": url_for("api.api_admin_automation_conversion_workflow_registry"),
            "agents_options": url_for("api.api_admin_automation_conversion_agent_options", enabled_only=0),
            "agent_create": url_for("api.api_admin_automation_conversion_agent_create"),
            "agent_detail_base": url_for("api.api_admin_automation_conversion_agent_detail", agent_code="__AGENT_CODE__"),
            "agent_draft_base": url_for("api.api_admin_automation_conversion_agent_draft", agent_code="__AGENT_CODE__"),
            "agent_delete_base": url_for("api.api_admin_automation_conversion_agent_delete", agent_code="__AGENT_CODE__"),
            "agent_publish_base": url_for("api.api_admin_automation_conversion_agent_publish", agent_code="__AGENT_CODE__"),
            "model_settings": url_for("api.api_admin_automation_conversion_model_settings"),
            "model_settings_test": url_for("api.api_admin_automation_conversion_model_settings_test"),
        },
        "entry_urls": {
            "operations": _program_route_or_main("api.admin_automation_program_operations"),
            "auto_reply": url_for("api.admin_automation_conversion_auto_reply"),
        },
        "selected_template_id": None,
        "available_agents": list(list_conversion_agent_options(enabled_only=False).get("items") or []),
        "initial_templates": [],
        "initial_template_catalog": [],
    }


def _build_profile_segment_workspace(*, program_id: int | None = None) -> dict[str, object]:
    program_params = _program_api_params(program_id)
    initial_templates = list(
        list_conversion_profile_segment_templates(
            enabled_only=False,
            program_id=program_id,
        ).get("items")
        or []
    )
    initial_catalog = list(list_conversion_profile_segment_catalog().get("items") or [])
    return {
        "api_urls": {
            "profile_segment_templates": url_for(
                "api.api_admin_automation_conversion_profile_segment_templates",
                enabled_only=0,
                **program_params,
            ),
            "profile_segment_template_detail_base": url_for(
                "api.api_admin_automation_conversion_profile_segment_template_detail",
                template_id=0,
                **program_params,
            ),
            "profile_segment_template_catalog": url_for("api.api_admin_automation_conversion_profile_segment_catalog"),
            "default_channel_settings": url_for(
                "api.api_admin_automation_conversion_default_channel_settings",
                **program_params,
            ),
            "default_channel_generate_qr": url_for(
                "api.api_admin_automation_conversion_default_channel_generate_qr",
                **program_params,
            ),
            "wecom_tags": "/api/admin/wecom/tags",
        },
        "selected_template_id": _query_int("template_id", default=0, minimum=0, maximum=100000000) or None,
        "initial_templates": initial_templates,
        "initial_template_catalog": initial_catalog,
    }


def _build_flow_design_workspace(*, page_input: dict[str, object] | None = None, program_id: int | None = None) -> dict[str, object]:
    settings_payload = get_settings_payload(program_id=program_id)
    section = _flow_design_section()
    input_payload = dict(page_input or {})
    default_channel = {
        **dict(settings_payload.get("default_channel") or {}),
        "welcome_message": str(input_payload.get("welcome_message") or dict(settings_payload.get("default_channel") or {}).get("welcome_message") or ""),
    }

    def _flow_href(section_key: str, anchor: str) -> str:
        return (
            _program_route_or_main(
                "api.admin_automation_program_flow_design",
                program_id=program_id,
                section=section_key,
            )
            + anchor
        )

    return {
        "section": section,
        "sections": [
            {"key": "profile-segments", "label": "问卷分层", "href": _flow_href("profile-segments", "#flow-profile-segments")},
            {"key": "channel", "label": "欢迎语 / 标签 / 二维码", "href": _flow_href("channel", "#flow-channel")},
        ],
        "settings": settings_payload,
        "default_channel": default_channel,
        "profile_segment_workspace": _build_profile_segment_workspace(program_id=program_id),
        "saved": _query_bool("saved", default=False),
        "page_input": input_payload,
    }


def _build_member_ops_workspace() -> dict[str, object]:
    stage_key = _member_ops_stage_key()
    panel = _member_ops_panel()
    stage_payload = get_stage_detail_payload(
        route_key=stage_key,
        keyword=_query_text("keyword"),
        limit=_query_int("limit", default=50, minimum=1, maximum=100),
        offset=_query_int("offset", default=0, minimum=0, maximum=1000000),
    )
    focus_batch_id = _query_int("focus_batch_id", default=0, minimum=0, maximum=100000000)
    focus_batch_detail = {}
    if focus_batch_id:
        try:
            focus_batch_detail = get_focus_send_batch_detail(batch_id=focus_batch_id)
        except LookupError:
            focus_batch_detail = {}
    active_pool = str(((stage_payload.get("stage") or {}).get("pool")) or "").strip()
    stage_tabs = []
    for tab_stage_key in ("pending-questionnaire", "operating", "converted"):
        tab_payload = get_stage_detail_payload(route_key=tab_stage_key, limit=1, offset=0)
        tab_stage = dict(tab_payload.get("stage") or {})
        tab_pool = str(tab_stage.get("pool") or "").strip()
        stage_tabs.append(
            {
                "key": tab_stage_key,
                "label": str(tab_stage.get("label") or ""),
                "description": str(tab_stage.get("description") or ""),
                "total_count": int(tab_stage.get("total_count") or 0),
                "today_new_count": int(tab_stage.get("today_new_count") or 0),
                "active": tab_pool == active_pool,
            }
        )
    return {
        "stage_key": stage_key,
        "panel": panel,
        "stage_tabs": stage_tabs,
        "detail": stage_payload,
        "manual_send_notice": _query_text("manual_send_notice"),
        "manual_send_record_id": _query_text("record_id"),
        "focus_batch_notice": _query_text("focus_batch_notice"),
        "focus_batch_detail": focus_batch_detail,
    }


def _build_run_center_workspace(*, page_input: dict[str, object] | None = None) -> dict[str, object]:
    raw_input = dict(page_input or {})
    tab = _query_text("tab") or str(raw_input.get("tab") or "").strip()
    if tab not in RUN_CENTER_TABS:
        tab = "overview"
    subtab = _query_text("subtab") or str(raw_input.get("subtab") or "").strip()
    if subtab not in RUN_CENTER_AGENT_SUBTABS:
        subtab = "router"
    settings_payload = get_settings_payload()
    overview_payload = get_overview_payload()
    context: dict[str, object] = {
        "tab": tab,
        "subtab": subtab,
        "tabs": [
            {"key": "overview", "label": "运行概况", "href": url_for("api.admin_automation_conversion_runtime")},
            {"key": "sync", "label": "数据同步", "href": url_for("api.admin_automation_conversion_runtime_sync")},
            {"key": "logs", "label": "执行日志 / 审计", "href": url_for("api.admin_automation_conversion_runtime_logs")},
            {"key": "model-infra", "label": "模型基础设施", "href": url_for("api.admin_automation_conversion_shared_model_infra")},
            {"key": "agent-orchestration", "label": "智能体编排", "href": url_for("api.admin_automation_conversion_runtime_router")},
            {"key": "debug", "label": "调试", "href": url_for("api.admin_automation_conversion_runtime_debug")},
        ],
        "overview": overview_payload,
        "settings": settings_payload,
        "sync": dict(settings_payload.get("message_activity_sync") or {}),
        "reply_monitor": dict(settings_payload.get("reply_monitor") or {}),
        "sop_batches": get_sop_v1_batches_payload(limit=10),
        "focus_batches": get_focus_send_batches_payload(limit=10),
        "page_input": raw_input,
    }
    context["tab_label"] = next((item["label"] for item in context["tabs"] if item["key"] == tab), "运行概况")
    if tab == "model-infra":
        context["model_infra"] = get_model_infra_payload(limit_logs=10)
    elif tab == "debug":
        context["debug"] = get_debug_payload(
            external_contact_id=_query_text("external_contact_id"),
            phone=_query_text("phone"),
        )
    elif tab == "agent-orchestration":
        orchestration_payload = get_agent_orchestration_payload(
            subtab=subtab,
            agent_code=_query_text("agent") or str(raw_input.get("agent") or "").strip(),
            output_id=_query_text("output_id") or str(raw_input.get("output_id") or "").strip(),
            run_id=_query_text("run_id") or str(raw_input.get("run_id") or "").strip(),
            request_id=_query_text("request_id") or str(raw_input.get("request_id") or "").strip(),
            external_contact_id=_query_text("external_contact_id") or str(raw_input.get("external_contact_id") or "").strip(),
            userid=_query_text("userid") or str(raw_input.get("userid") or "").strip(),
            date_from=_query_text("date_from") or str(raw_input.get("date_from") or "").strip(),
            date_to=_query_text("date_to") or str(raw_input.get("date_to") or "").strip(),
            output_type=_query_text("output_type") or str(raw_input.get("output_type") or "").strip(),
            target_pool=_query_text("target_pool") or str(raw_input.get("target_pool") or "").strip(),
            applied_status=_query_text("applied_status") or str(raw_input.get("applied_status") or "").strip(),
            batch_id=_query_text("batch_id") or str(raw_input.get("batch_id") or "").strip(),
            current_pool=_query_text("current_pool") or str(raw_input.get("current_pool") or "").strip(),
            min_confidence=_query_text("min_confidence") or str(raw_input.get("min_confidence") or "").strip(),
            max_confidence=_query_text("max_confidence") or str(raw_input.get("max_confidence") or "").strip(),
            has_error=_query_text("has_error") or str(raw_input.get("has_error") or "").strip(),
            scripts_only=_query_bool("scripts_only", default=False) or str(raw_input.get("scripts_only") or "").strip().lower() in {"1", "true", "yes", "on"},
            page=_query_int("page", default=int(str(raw_input.get("page") or "1") or "1"), minimum=1, maximum=100000),
            page_size=_query_int("page_size", default=int(str(raw_input.get("page_size") or "20") or "20"), minimum=1, maximum=100),
            export_job_id=_query_text("export_job_id") or str(raw_input.get("export_job_id") or "").strip(),
        )
        request_id_filter = str(((orchestration_payload.get("outputs") or {}).get("filters") or {}).get("request_id") or "").strip()
        if subtab == "outputs" and request_id_filter and not list((orchestration_payload.get("outputs") or {}).get("rows") or []):
            orchestration_payload["replay_fallback"] = get_agent_replay_payload(
                request_id=request_id_filter,
                external_contact_id=_query_text("external_contact_id") or str(raw_input.get("external_contact_id") or "").strip(),
                userid=_query_text("userid") or str(raw_input.get("userid") or "").strip(),
                visibility="console",
            )
        context["agent_orchestration"] = orchestration_payload
    return context


def _automation_conversion_workspace_tabs(active_key: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in _AUTOMATION_CONVERSION_WORKSPACE_TABS:
        program_endpoint = item.get("program_endpoint")
        if program_endpoint:
            href = _program_route_or_main(str(program_endpoint))
        else:
            href = url_for(str(item["endpoint"]), **dict(item.get("params") or {}))
        items.append(
            {
                **item,
                "href": href,
                "active": item["key"] == active_key,
            }
        )
    return items


def _automation_program_workspace_tabs(program_id: int, active_key: str) -> list[dict[str, object]]:
    normalized_program_id = int(program_id)
    tabs = (
        ("setup", "配置向导", "api.admin_automation_program_setup"),
        ("overview", "概览", "api.admin_automation_program_overview"),
        ("member_ops", "成员运营", "api.admin_automation_program_member_ops"),
        ("executions", "执行记录", "api.admin_automation_program_executions"),
    )
    return [
        {
            "key": key,
            "label": label,
            "summary": "",
            "href": url_for(endpoint, program_id=normalized_program_id),
            "active": key == active_key,
        }
        for key, label, endpoint in tabs
    ]


def _program_context(program: dict[str, object], *, active_key: str = "overview") -> dict[str, object]:
    program_id = int(program.get("id") or 0)
    return {
        "id": program_id,
        "program_code": str(program.get("program_code") or ""),
        "program_name": str(program.get("program_name") or ""),
        "description": str(program.get("description") or ""),
        "status": str(program.get("status") or ""),
        "list_href": url_for("api.admin_automation_conversion"),
        "overview_href": url_for("api.admin_automation_program_overview", program_id=program_id),
        "update_href": url_for("api.admin_automation_program_update", program_id=program_id),
        "copy_href": url_for("api.admin_automation_program_copy", program_id=program_id),
        "activate_href": url_for("api.admin_automation_program_activate", program_id=program_id),
        "pause_href": url_for("api.admin_automation_program_pause", program_id=program_id),
        "archive_href": url_for("api.admin_automation_program_archive", program_id=program_id),
        "active_key": active_key,
    }


def _load_program_or_404(program_id: int) -> dict[str, object]:
    try:
        return get_automation_program(int(program_id))
    except LookupError:
        abort(404)


def _wants_json_response() -> bool:
    accept = str(request.headers.get("Accept") or "").lower()
    requested_with = str(request.headers.get("X-Requested-With") or "").strip()
    return "application/json" in accept or requested_with == "XMLHttpRequest"


def _json_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _render_overview_page(*, page_error: str = "", program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_overview_workspace.html",
        active_nav="automation_conversion",
        page_title="自动化运营方案概览" if program else "自动化转化",
        page_summary="当前方案内的运行状态和任务流执行摘要。" if program else "先看五个一级入口、当前运行状态和任务流执行摘要，再进入对应工作面处理。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            ((program or {}).get("program_name") or "自动化转化", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "overview") if program_id else _automation_conversion_workspace_tabs("overview"),
        program_context=_program_context(program, active_key="overview") if program else None,
        overview_workspace=_build_overview_workspace(program_id=program_id),
        page_notice=_overview_notice(),
        page_error=page_error,
        show_shell_meta=False,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_operations_page(*, page_error: str = "", program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_operations_workspace.html",
        active_nav="automation_conversion",
        page_title="运营编排" if program else "自动化运营",
        page_summary="当前方案内的任务流、节点和执行入口。" if program else "模块内自动化运营工作面，先统一任务流、节点和执行入口，不再暴露旧运营概念。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化运营",
                url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None,
            ),
            ("运营编排", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "operations") if program_id else _automation_conversion_workspace_tabs("operations"),
        program_context=_program_context(program, active_key="operations") if program else None,
        operations_workspace=_build_operations_list_workspace(program_id=program_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        show_shell_meta=False,
        show_page_header=False,
    )


def _render_action_orchestration_page(
    *,
    workflow_id: int | None = None,
    page_error: str = "",
    program: dict[str, object] | None = None,
):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_action_orchestration.html",
        active_nav="automation_conversion",
        page_title="运营动作编排",
        page_summary="从运营动作模板开始，在同一页配置触发、对象、内容和执行节点。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化运营",
                url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None,
            ),
            ("运营动作编排", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "operations") if program_id else _automation_conversion_workspace_tabs("operations"),
        program_context=_program_context(program, active_key="operations") if program else None,
        operations_workspace=_build_action_orchestration_workspace(workflow_id=workflow_id, program_id=program_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        show_shell_meta=False,
        show_page_header=False,
    )


def _render_workflow_editor_page(*, workflow_id: int | None = None, page_error: str = "", program: dict[str, object] | None = None):
    is_new = int(workflow_id or 0) <= 0
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_workflow_editor.html",
        active_nav="automation_conversion",
        page_title="新建任务流" if is_new else "编辑任务流",
        page_summary="任务流层只负责适用人群、发给谁、怎么发、生成方式和智能体绑定，不再和节点配置混排。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化运营",
                _program_route_or_main("api.admin_automation_program_operations", program_id=program_id),
            ),
            ("新建任务流" if is_new else "编辑任务流", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "operations") if program_id else _automation_conversion_workspace_tabs("operations"),
        program_context=_program_context(program, active_key="operations") if program else None,
        operations_workspace=_build_workflow_editor_workspace(workflow_id=workflow_id, program_id=program_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        show_shell_meta=False,
        show_page_header=False,
    )


def _render_workflow_nodes_page(*, workflow_id: int, page_error: str = "", program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_workflow_nodes.html",
        active_nav="automation_conversion",
        page_title="节点配置",
        page_summary="节点层只负责节点名称、目标人群、触发方式和节点内容；任务流配置不再与节点编辑混排。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化运营",
                _program_route_or_main("api.admin_automation_program_operations", program_id=program_id),
            ),
            ("节点配置", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "operations") if program_id else _automation_conversion_workspace_tabs("operations"),
        program_context=_program_context(program, active_key="operations") if program else None,
        operations_workspace=_build_workflow_nodes_workspace(workflow_id=workflow_id, program_id=program_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        page_notice="当前页面只承载节点配置骨架。",
    )


def _render_execution_records_page(*, page_error: str = "", program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_execution_records.html",
        active_nav="automation_conversion",
        page_title="执行记录",
        page_summary="执行记录页只看批次与单用户执行明细，不再和任务流编辑、节点配置混排。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化运营",
                _program_route_or_main("api.admin_automation_program_executions", program_id=program_id),
            ),
            ("执行记录", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "executions") if program_id else _automation_conversion_workspace_tabs("operations"),
        program_context=_program_context(program, active_key="executions") if program else None,
        operations_workspace=_build_execution_records_workspace(program_id=program_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        show_shell_meta=False,
        show_page_header=False,
    )


def _render_auto_reply_page(*, page_error: str = "", page_notice: str = ""):
    return _render_admin_template(
        "automation_conversion_auto_reply_workspace.html",
        active_nav="automation_conversion",
        page_title="自动化应答",
        page_summary="复用现有自动化应答链路，只在模块内补稳定入口和状态壳子，不重做应答业务逻辑。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动化应答", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("auto_reply"),
        auto_reply_workspace=_build_auto_reply_workspace(),
        page_error=page_error,
        page_notice=page_notice,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_agent_config_page(*, page_error: str = ""):
    return _render_admin_template(
        "automation_conversion_agent_config_workspace.html",
        active_nav="automation_conversion",
        page_title="模型与智能体配置",
        page_summary="共享层只维护可跨方案复用的智能体本体和大模型配置；画像分层、欢迎语和二维码入口属于具体方案。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("模型与智能体配置", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("agent_config"),
        agent_config_workspace=_build_agent_config_workspace(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_flow_design_page(*, page_error: str = "", page_input: dict[str, object] | None = None, program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_flow_design_workspace.html",
        active_nav="automation_conversion",
        page_title="基础配置",
        page_summary="当前方案内维护问卷分层、欢迎语、扫码标签和入口二维码；共享层只保留智能体与大模型底座。"
        if program
        else "兼容旧后台设置入口，当前统一映射到问卷分层、欢迎语、扫码标签和入口二维码配置。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化转化",
                url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None,
            ),
            ("基础配置", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "flow_design") if program_id else [],
        program_context=_program_context(program, active_key="flow_design") if program else None,
        flow_design_workspace=_build_flow_design_workspace(page_input=page_input, program_id=program_id),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_member_ops_page(*, page_error: str = "", program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0) or None
    return _render_admin_template(
        "automation_conversion_member_ops_workspace.html",
        active_nav="automation_conversion",
        page_title="成员运营",
        page_summary="按当前方案查看池子成员并进入统一客户档案，或创建批量触达。" if program else "查看自动化成员池子、统一客户档案入口和批量触达入口。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            (
                (program or {}).get("program_name") or "自动化转化",
                url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None,
            ),
            ("成员运营", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "member_ops") if program_id else [],
        program_context=_program_context(program, active_key="member_ops") if program else None,
        member_ops_workspace=_build_member_ops_workspace(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _setup_step_url(program_id: int, step: str, **params: object) -> str:
    query = {"step": step, **{key: value for key, value in params.items() if value not in {None, ""}}}
    return url_for("api.admin_automation_program_setup", program_id=int(program_id), **query)


def _build_program_setup_workspace(program_id: int, *, step: str = "basic", workflow_id: int | None = None) -> dict[str, object]:
    normalized_step = normalize_setup_step(step)
    payload = get_program_setup_payload(int(program_id), step=normalized_step)
    base_url = url_for("api.admin_automation_program_setup", program_id=int(program_id))
    payload["urls"] = {
        "base": base_url,
        "basic": url_for("api.api_admin_automation_program_setup_basic", program_id=int(program_id)),
        "entry_channel": url_for("api.api_admin_automation_program_setup_entry_channel", program_id=int(program_id)),
        "entry_channel_generate_qr": url_for("api.api_admin_automation_conversion_default_channel_generate_qr"),
        "segmentation": url_for("api.api_admin_automation_program_setup_segmentation", program_id=int(program_id)),
        "audience_entry_rule": url_for("api.api_admin_automation_program_setup_audience_entry_rule", program_id=int(program_id)),
        "publish_check": url_for("api.api_admin_automation_program_setup_publish_check", program_id=int(program_id)),
        "publish_entry": url_for("api.api_admin_automation_program_publish_entry", program_id=int(program_id)),
        "publish_full": url_for("api.api_admin_automation_program_publish_full", program_id=int(program_id)),
        "customer_acquisition_links": url_for("api.api_admin_automation_program_customer_acquisition_links", program_id=int(program_id)),
        "operations": _setup_step_url(int(program_id), "operations", workflow_id=workflow_id or None),
        "flow_design_redirect": _setup_step_url(int(program_id), "segmentation"),
    }
    payload["operations_workspace"] = _build_action_orchestration_workspace(workflow_id=workflow_id, program_id=int(program_id))
    payload["operations_workspace"]["entry_urls"]["list"] = _setup_step_url(int(program_id), "operations")
    payload["operations_workspace"]["entry_urls"]["action_orchestration"] = _setup_step_url(int(program_id), "operations")
    payload["operations_workspace"]["entry_urls"]["workflow_list"] = _setup_step_url(int(program_id), "operations")
    return payload


def _render_program_setup_page(*, page_error: str = "", program: dict[str, object] | None = None, step: str = "basic"):
    program_id = int((program or {}).get("id") or 0)
    workflow_id = _query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None
    return _render_admin_template(
        "automation_program_setup_wizard.html",
        active_nav="automation_conversion",
        page_title="自动化运营方案",
        page_summary="",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            ((program or {}).get("program_name") or "方案配置向导", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "setup") if program_id else [],
        program_context=None,
        setup_workspace=_build_program_setup_workspace(program_id, step=step, workflow_id=workflow_id) if program_id else {},
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        show_shell_meta=False,
    )


def _render_run_center_page(*, page_error: str = "", page_notice: str = "", page_input: dict[str, object] | None = None):
    return _render_admin_template(
        "automation_conversion_run_center_workspace.html",
        active_nav="automation_conversion",
        page_title="运行中心",
        page_summary="兼容旧运行中心入口，当前收口到运行概况、数据同步、日志、模型基础设施、智能体编排和调试。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("运行中心", None),
        ),
        run_center_workspace=_build_run_center_workspace(page_input=page_input),
        page_error=page_error,
        page_notice=page_notice,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_program_list_page(*, page_error: str = "", page_notice: str = "", show_create_form: bool | None = None, edit_program_id: int | None = None):
    should_show_create = _query_bool("create", default=False) if show_create_form is None else bool(show_create_form)
    selected_edit_program_id = int(edit_program_id or _query_int("edit_program_id", default=0, minimum=0, maximum=10_000_000) or 0)
    program_list_payload = list_automation_programs(include_archived=True)
    return _render_admin_template(
        "automation_program_list.html",
        active_nav="automation_conversion",
        page_title="自动化运营方案",
        page_summary="自动化运营已升级为多方案顶层结构；先选择或创建方案，再进入方案内工作面。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", None),
        ),
        page_actions=[
            {"label": "共享资源", "href": url_for("api.admin_automation_conversion_shared_agents"), "variant": "secondary"},
            {"label": "运行时中心", "href": url_for("api.admin_automation_conversion_runtime"), "variant": "secondary"},
            {"label": "新建方案", "href": url_for("api.admin_automation_conversion", create=1) + "#program-create-panel", "variant": "primary"},
        ],
        program_list_payload=program_list_payload,
        show_create_form=should_show_create,
        edit_program_id=selected_edit_program_id,
        action_urls={
            "create": url_for("api.admin_automation_program_create"),
            "new": url_for("api.admin_automation_program_new"),
            "copy_base": url_for("api.admin_automation_program_copy", program_id=0),
            "activate_base": url_for("api.admin_automation_program_activate", program_id=0),
            "pause_base": url_for("api.admin_automation_program_pause", program_id=0),
            "archive_base": url_for("api.admin_automation_program_archive", program_id=0),
            "update_base": url_for("api.admin_automation_program_update", program_id=0),
            "overview_base": url_for("api.admin_automation_program_overview", program_id=0),
        },
        page_error=page_error,
        page_notice=page_notice,
        admin_action_token=ensure_admin_console_action_token(),
        show_shell_meta=False,
    )


def _program_form_payload() -> dict[str, object]:
    return {
        "program_code": str(request.form.get("program_code") or "").strip(),
        "program_name": str(request.form.get("program_name") or "").strip(),
        "description": str(request.form.get("description") or "").strip(),
        "status": str(request.form.get("status") or "draft").strip() or "draft",
        "copy_source_program_id": int(str(request.form.get("copy_source_program_id") or "0").strip() or 0),
    }


def _program_basic_info_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "program_name": str(request.form.get("program_name") or "").strip(),
    }
    if "description" in request.form:
        payload["description"] = str(request.form.get("description") or "").strip()
    return payload


def _program_action_redirect(default_path: str = ""):
    target = str(request.form.get("next") or "").strip() or default_path
    if not target.startswith("/admin/automation-conversion") or target.startswith("//"):
        target = default_path or url_for("api.admin_automation_conversion")
    return redirect(target, code=302)


__all__ = [
    "_automation_conversion_workspace_tabs",
    "_automation_program_workspace_tabs",
    "_build_agent_config_workspace",
    "_build_action_orchestration_workspace",
    "_build_auto_reply_workspace",
    "_build_execution_records_workspace",
    "_build_flow_design_workspace",
    "_build_member_ops_workspace",
    "_build_operations_list_workspace",
    "_build_overview_workspace",
    "_build_profile_segment_workspace",
    "_build_program_setup_workspace",
    "_build_run_center_workspace",
    "_build_workflow_editor_workspace",
    "_build_workflow_nodes_workspace",
    "_coerce_program_id",
    "_default_program_id_or_none",
    "_detect_stage_send_image_type",
    "_flow_design_section",
    "_json_bool",
    "_load_program_or_404",
    "_member_ops_panel",
    "_member_ops_stage_key",
    "_operations_page_api_urls",
    "_operations_page_entry_urls",
    "_operator_from_request",
    "_overview_notice",
    "_payload_program_id",
    "_program_action_redirect",
    "_program_api_params",
    "_program_basic_info_payload",
    "_program_context",
    "_program_form_payload",
    "_program_route",
    "_program_route_or_main",
    "_query_bool",
    "_query_int",
    "_query_text",
    "_redirect_to_program",
    "_render_agent_config_page",
    "_render_action_orchestration_page",
    "_render_auto_reply_page",
    "_render_execution_records_page",
    "_render_flow_design_page",
    "_render_member_ops_page",
    "_render_operations_page",
    "_render_overview_page",
    "_render_program_list_page",
    "_render_program_setup_page",
    "_render_run_center_page",
    "_render_workflow_editor_page",
    "_render_workflow_nodes_page",
    "_request_program_id",
    "_request_program_id_or_default",
    "_run_center_agent_subtab",
    "_run_center_tab",
    "_stage_send_images_from_request",
    "_wants_json_response",
]
