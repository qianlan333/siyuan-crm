from __future__ import annotations

from flask import request, url_for

from ..domains.automation_conversion.focus_send_service import (
    get_focus_send_batch_detail,
    get_focus_send_batches_payload,
)
from ..domains.automation_conversion.model_infra_service import get_model_infra_payload
from ..domains.automation_conversion.orchestration_service import (
    get_agent_orchestration_payload,
    get_agent_replay_payload,
    list_agent_configs,
)
from ..domains.automation_conversion.program_setup_service import get_program_setup_payload, normalize_setup_step
from ..domains.automation_conversion.service import (
    get_debug_payload,
    get_overview_payload,
    get_settings_payload,
    get_stage_detail_payload,
)
from ..domains.automation_conversion.sop_service import get_sop_v1_batches_payload
from ..domains.automation_conversion.workflow_service import (
    list_conversion_agent_options,
    list_conversion_profile_segment_catalog,
    list_conversion_profile_segment_templates,
)
from ._routes_helpers import (
    _coerce_program_id,
    _default_program_id_or_none,
    _program_api_params,
    _program_route,
    _program_route_or_main,
    _query_bool,
    _query_int,
    _query_text,
)


FLOW_DESIGN_SECTIONS = ("profile-segments", "channel")
RUN_CENTER_TABS = ("overview", "sync", "logs", "model-infra", "agent-orchestration", "debug")
RUN_CENTER_AGENT_SUBTABS = ("router", "agents", "metrics", "outputs", "replay")

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


def _flow_design_section() -> str:
    section = _query_text("section") or str(request.values.get("section") or "").strip()
    return section if section in FLOW_DESIGN_SECTIONS else "profile-segments"


def _member_ops_stage_key() -> str:
    stage = _query_text("stage") or str(request.values.get("stage") or "").strip()
    return stage or "new-user"


def _member_ops_panel() -> str:
    panel = _query_text("panel") or str(request.values.get("panel") or "").strip()
    return panel or "members"


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
        "task_groups": url_for("api.api_admin_automation_conversion_task_groups", **program_params),
        "task_group_detail_base": url_for(
            "api.api_admin_automation_conversion_task_group_update",
            group_id=0,
            **program_params,
        ),
        "tasks": url_for("api.api_admin_automation_conversion_tasks", **program_params),
        "task_detail_base": url_for("api.api_admin_automation_conversion_task_detail", task_id=0, **program_params),
        "task_copy_base": url_for("api.api_admin_automation_conversion_task_copy", task_id=0, **program_params),
        "task_activate_base": url_for("api.api_admin_automation_conversion_task_activate", task_id=0, **program_params),
        "task_pause_base": url_for("api.api_admin_automation_conversion_task_pause", task_id=0, **program_params),
        "task_delete_base": url_for("api.api_admin_automation_conversion_task_delete", task_id=0, **program_params),
        "task_preview_audience_base": url_for(
            "api.api_admin_automation_conversion_task_preview_audience",
            task_id=0,
            **program_params,
        ),
        "tasks_run_due": url_for("api.api_admin_automation_conversion_tasks_run_due", **program_params),
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
        ("entry_channels", "入口渠道", "api.admin_automation_program_entry_channels"),
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


def _build_program_setup_workspace(program_id: int, *, step: str = "basic", audience_picker: str = "") -> dict[str, object]:
    normalized_step = normalize_setup_step(step)
    payload = get_program_setup_payload(int(program_id), step=normalized_step, audience_picker=audience_picker)
    base_url = url_for("api.admin_automation_program_setup", program_id=int(program_id))
    payload["urls"] = {
        "base": base_url,
        "basic": url_for("api.api_admin_automation_program_setup_basic", program_id=int(program_id)),
        "entry_channel": url_for("api.api_admin_automation_program_setup_entry_channel", program_id=int(program_id)),
        "entry_channel_generate_qr": url_for("api.api_admin_automation_conversion_settings_default_channel_generate_qr"),
        "segmentation": url_for("api.api_admin_automation_program_setup_segmentation", program_id=int(program_id)),
        "audience_entry_rule": url_for("api.api_admin_automation_program_setup_audience_entry_rule", program_id=int(program_id)),
        "publish_check": url_for("api.api_admin_automation_program_setup_publish_check", program_id=int(program_id)),
        "publish_entry": url_for("api.api_admin_automation_program_publish_entry", program_id=int(program_id)),
        "publish_full": url_for("api.api_admin_automation_program_publish_full", program_id=int(program_id)),
        "customer_acquisition_links": url_for("api.api_admin_automation_program_customer_acquisition_links", program_id=int(program_id)),
    }
    payload["operations_workspace"] = _build_action_orchestration_workspace(program_id=int(program_id))
    return payload


__all__ = [
    "_automation_conversion_workspace_tabs",
    "_automation_program_workspace_tabs",
    "_build_action_orchestration_workspace",
    "_build_agent_config_workspace",
    "_build_auto_reply_workspace",
    "_build_execution_records_workspace",
    "_build_flow_design_workspace",
    "_build_member_ops_workspace",
    "_build_overview_workspace",
    "_build_program_setup_workspace",
    "_build_run_center_workspace",
    "_overview_notice",
    "_program_context",
]
