from __future__ import annotations

import base64
import json

import requests

from flask import Response, abort, current_app, jsonify, redirect, request, url_for

from ..domains.automation_conversion.channel_service import (
    generate_default_channel_qr,
    get_default_channel_settings_payload,
    save_default_channel_settings,
)
from ..domains.automation_conversion.focus_send_service import (
    create_focus_send_batch,
    get_focus_send_batch_detail,
    get_focus_send_batches_payload,
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
from ..domains.automation_conversion.message_activity_service import run_message_activity_sync
from ..domains.automation_conversion.model_infra_service import (
    get_model_infra_payload,
    save_model_infra_settings,
    test_model_infra_connection,
)
from ..domains.automation_conversion.orchestration_service import (
    build_rejected_feedback_clipboard_payload,
    create_agent_config,
    create_agent_output_export_job,
    delete_agent_config,
    diff_agent_prompt,
    get_agent_config_detail,
    get_agent_orchestration_payload,
    get_agent_output_detail,
    get_agent_output_export_file,
    get_agent_output_export_job,
    get_agent_replay_payload,
    get_agent_run_detail,
    handle_agent_router_callback,
    list_agent_configs,
    list_agent_outputs,
    list_pending_agent_prompt_publish_requests,
    list_recent_reviewable_agent_outputs,
    list_router_pending_callbacks,
    publish_agent_config,
    replay_agent_run,
    replay_router_callback,
    review_agent_reply_output,
    run_router_pending_callback_check,
    save_agent_config_draft,
    submit_agent_prompt_for_publish,
    validate_router_callback_signature,
)
from ..domains.automation_conversion.program_service import (
    copy_automation_program,
    create_automation_program,
    get_automation_program,
    get_default_automation_program,
    get_default_automation_program_id,
    list_automation_programs,
    update_automation_program_basic_info,
    update_automation_program_status,
)
from ..domains.automation_conversion.reply_monitor_service import (
    run_due_reply_monitor,
    run_reply_monitor_capture,
    run_router_test_dispatch,
    save_reply_monitor_enabled,
)
from ..domains.automation_conversion.service import (
    get_debug_payload,
    get_member_detail,
    get_overview_payload,
    get_settings_payload,
    get_stage_detail_payload,
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
    get_sop_v1_batches_payload,
    get_sop_v1_config_payload,
    get_sop_v1_templates_payload,
    run_due_sop,
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
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token, require_internal_api_token, validate_admin_console_action_token


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


MAX_STAGE_SEND_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_STAGE_SEND_IMAGE_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
FLOW_DESIGN_SECTIONS = ("profile-segments", "channel")
RUN_CENTER_TABS = ("overview", "sync", "logs", "model-infra", "agent-orchestration", "debug")
RUN_CENTER_AGENT_SUBTABS = ("router", "agents", "metrics", "outputs", "replay")


def _detect_stage_send_image_type(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if file_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "webp"
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
        if len(file_bytes) > MAX_STAGE_SEND_IMAGE_SIZE_BYTES:
            raise ValueError("image file is too large (max 5MB)")
        detected_type = ALLOWED_STAGE_SEND_IMAGE_TYPES.get(_detect_stage_send_image_type(file_bytes), "")
        if not detected_type:
            raise ValueError("only image files are allowed")
        images.append(
            {
                "file_name": file_name,
                "content_type": detected_type,
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
            "workflow_new": fallback,
            "workflow_edit_base": fallback,
            "workflow_nodes_base": fallback,
            "executions": fallback,
        }
    return {
        "list": _program_route("api.admin_automation_program_operations", normalized_program_id),
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
        return _program_route_or_main(
            "api.admin_automation_program_flow_design",
            program_id=program_id,
            section=section_key,
        ) + anchor

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
        ("overview", "概览", "api.admin_automation_program_overview"),
        ("flow_design", "基础配置", "api.admin_automation_program_flow_design"),
        ("member_ops", "成员运营", "api.admin_automation_program_member_ops"),
        ("operations", "运营编排", "api.admin_automation_program_operations"),
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
            ((program or {}).get("program_name") or "自动化运营", url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None),
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
        page_summary="当前方案内维护问卷分层、欢迎语、扫码标签和入口二维码；共享层只保留智能体与大模型底座。" if program else "兼容旧后台设置入口，当前统一映射到问卷分层、欢迎语、扫码标签和入口二维码配置。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            ((program or {}).get("program_name") or "自动化转化", url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None),
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
            ((program or {}).get("program_name") or "自动化转化", url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None),
            ("成员运营", None),
        ),
        workspace_tabs=_automation_program_workspace_tabs(program_id, "member_ops") if program_id else [],
        program_context=_program_context(program, active_key="member_ops") if program else None,
        member_ops_workspace=_build_member_ops_workspace(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
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
    return {
        "program_name": str(request.form.get("program_name") or "").strip(),
        "description": str(request.form.get("description") or "").strip(),
    }


def _program_action_redirect(default_path: str = ""):
    target = str(request.form.get("next") or "").strip() or default_path
    if not target.startswith("/admin/automation-conversion") or target.startswith("//"):
        target = default_path or url_for("api.admin_automation_conversion")
    return redirect(target, code=302)


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
        url_for("api.admin_automation_program_overview", program_id=int((result.get("program") or {}).get("id") or 0)),
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
        url_for("api.admin_automation_program_overview", program_id=int((result.get("program") or {}).get("id") or 0)),
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


def admin_automation_program_operations(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_operations_page(program=program)


def admin_automation_program_workflow_new(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_workflow_editor_page(program=program)


def admin_automation_program_workflow_edit(program_id: int, workflow_id: int):
    program = _load_program_or_404(program_id)
    return _render_workflow_editor_page(workflow_id=workflow_id, program=program)


def admin_automation_program_workflow_nodes(program_id: int, workflow_id: int):
    program = _load_program_or_404(program_id)
    return _render_workflow_nodes_page(workflow_id=workflow_id, program=program)


def admin_automation_program_executions(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_execution_records_page(program=program)


def admin_automation_program_flow_design(program_id: int):
    program = _load_program_or_404(program_id)
    return _render_flow_design_page(program=program)


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
        result = apply_dashboard_signup_tag(operator_id=_operator_from_request())
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
    bp.route("/admin/automation-conversion/programs/<int:program_id>/overview", methods=["GET"])(admin_automation_program_overview)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations", methods=["GET"])(admin_automation_program_operations)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/new", methods=["GET"])(admin_automation_program_workflow_new)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/<int:workflow_id>/edit", methods=["GET"])(admin_automation_program_workflow_edit)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/operations/workflows/<int:workflow_id>/nodes", methods=["GET"])(admin_automation_program_workflow_nodes)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/executions", methods=["GET"])(admin_automation_program_executions)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/flow-design", methods=["GET"])(admin_automation_program_flow_design)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/member-ops", methods=["GET"])(admin_automation_program_member_ops)
    bp.route("/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send", methods=["POST"])(admin_automation_program_member_ops_stage_send)
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
