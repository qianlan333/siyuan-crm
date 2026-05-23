from __future__ import annotations

from flask import url_for

from ..domains.automation_conversion.admission_service import list_admission_attempts
from ..domains.automation_conversion.channel_binding_service import (
    ensure_legacy_program_channel_bindings,
    list_channels,
    list_program_channel_bindings,
)
from ..domains.automation_conversion.program_service import list_automation_programs
from ._routes_helpers import (
    _program_route_or_main,
    _query_bool,
    _query_int,
)
from .automation_conversion_workspaces import (
    _automation_conversion_workspace_tabs,
    _automation_program_workspace_tabs,
    _build_action_orchestration_workspace,
    _build_agent_config_workspace,
    _build_auto_reply_workspace,
    _build_execution_records_workspace,
    _build_flow_design_workspace,
    _build_member_ops_workspace,
    _build_overview_workspace,
    _build_program_setup_workspace,
    _build_run_center_workspace,
    _overview_notice,
    _program_context,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token


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


def _render_entry_channels_page(*, page_error: str = "", program: dict[str, object] | None = None):
    program_id = int((program or {}).get("id") or 0)
    legacy_binding_report = ensure_legacy_program_channel_bindings()
    channels = list_channels(limit=300)
    bindings = list_program_channel_bindings(program_id) if program_id else []
    display_bindings = [
        {
            "id": item.get("id"),
            "program_id": item.get("program_id"),
            "channel_id": item.get("channel_id"),
            "binding_status": item.get("binding_status"),
            "bound_at": item.get("bound_at"),
            "unbound_at": item.get("unbound_at"),
            "channel": item.get("channel") or {},
        }
        for item in bindings
    ]
    bound_channel_ids = {
        int(((item.get("channel") or {}).get("id") or item.get("channel_id") or 0))
        for item in display_bindings
        if str(item.get("binding_status") or "") == "active"
    }
    candidate_channels = [
        item
        for item in channels
        if not item.get("bound_program_id") and int(item.get("id") or 0) not in bound_channel_ids
    ]
    return _render_admin_template(
        "automation_conversion_entry_channels.html",
        active_nav="automation_conversion",
        page_title="入口渠道",
        page_summary="在当前自动化运营方案内绑定已有渠道。普通二维码和企微获客助手链接都可以入池，但一个渠道同一时间只能 active 绑定一个方案。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化运营方案", url_for("api.admin_automation_conversion")),
            ((program or {}).get("program_name") or "自动化运营", url_for("api.admin_automation_program_overview", program_id=program_id) if program_id else None),
            ("入口渠道", None),
        ),
        page_actions=[
            {"label": "渠道码中心", "href": url_for("api.admin_channels_page"), "variant": "secondary"},
        ],
        workspace_tabs=_automation_program_workspace_tabs(program_id, "entry_channels") if program_id else [],
        program_context=_program_context(program, active_key="entry_channels") if program else None,
        entry_channels_payload={
            "program": program or {},
            "bindings": display_bindings,
            "channels": channels,
            "candidate_channels": candidate_channels,
            "admission_attempts": list_admission_attempts(program_id, limit=30) if program_id else [],
            "legacy_binding_report": legacy_binding_report,
            "api_urls": {
                "bindings": url_for("api.api_admin_program_channel_bindings", program_id=program_id),
                "binding_base": url_for("api.api_admin_program_channel_binding_detail", program_id=program_id, binding_id=0),
                "member_stage_summary_base": url_for("api.api_admin_program_channel_binding_member_stage_summary", program_id=program_id, binding_id=0),
                "import": url_for("api.api_admin_program_channel_bindings_import", program_id=program_id),
                "attempts": url_for("api.api_admin_program_admission_attempts", program_id=program_id),
                "channels": url_for("api.api_admin_channels"),
            },
        },
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        show_shell_meta=False,
    )


def _render_channel_center_page(*, page_error: str = "", page_notice: str = ""):
    legacy_binding_report = ensure_legacy_program_channel_bindings()
    channels = list_channels(limit=300)
    return _render_admin_template(
        "channel_code_center.html",
        active_nav="channels",
        page_title="渠道码中心",
        page_summary="渠道是独立获客资源。普通二维码下载二维码图片；企微获客助手是链接型渠道，只复制或分享链接。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("渠道码中心", None),
        ),
        page_actions=[
            {"label": "新建渠道", "href": url_for("api.admin_channel_new_page"), "variant": "primary"},
        ],
        channel_center_payload={
            "channels": channels,
            "legacy_binding_report": legacy_binding_report,
            "api_urls": {
                "channels": url_for("api.api_admin_channels"),
                "detail_base": url_for("api.api_admin_channel_detail", channel_id=0),
                "contacts_base": url_for("api.api_admin_channel_contacts", channel_id=0),
                "bindings_base": url_for("api.api_admin_channel_bindings", channel_id=0),
                "qrcode_download_base": url_for("api.api_admin_channel_qrcode_download", channel_id=0),
                "share_link_base": url_for("api.api_admin_channel_share_link", channel_id=0),
            },
        },
        page_error=page_error,
        page_notice=page_notice,
        admin_action_token=ensure_admin_console_action_token(),
        show_shell_meta=False,
    )


def _render_channel_form_page(*, channel: dict[str, object] | None = None, page_error: str = ""):
    is_edit = bool(channel)
    return _render_admin_template(
        "channel_code_form.html",
        active_nav="channels",
        page_title="编辑渠道" if is_edit else "新建渠道",
        page_summary="创建渠道资产本身，不在渠道中心绑定自动化运营。普通二维码和企微获客助手链接按载体类型显示不同操作。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("渠道码中心", url_for("api.admin_channels_page")),
            ("编辑渠道" if is_edit else "新建渠道", None),
        ),
        channel_form_payload={
            "channel": channel or {
                "channel_type": "qrcode",
                "carrier_type": "qrcode",
                "status": "active",
                "welcome_miniprogram_library_ids": [],
                "welcome_attachment_library_ids": [],
            },
            "is_edit": is_edit,
            "api_urls": {
                "channels": url_for("api.api_admin_channels"),
                "detail": url_for("api.api_admin_channel_detail", channel_id=int((channel or {}).get("id") or 0)) if is_edit else "",
                "qrcode_download": url_for("api.api_admin_channel_qrcode_download", channel_id=int((channel or {}).get("id") or 0)) if is_edit else "",
                "share_link": url_for("api.api_admin_channel_share_link", channel_id=int((channel or {}).get("id") or 0)) if is_edit else "",
                "welcome_materials": url_for("api.api_admin_channel_welcome_materials"),
            },
        },
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
        show_shell_meta=False,
    )


def _render_program_setup_page(
    *,
    page_error: str = "",
    program: dict[str, object] | None = None,
    step: str = "basic",
    audience_picker: str = "",
):
    program_id = int((program or {}).get("id") or 0)
    workspace_tabs = []
    if program_id:
        workspace_tabs = [
            item
            for item in _automation_program_workspace_tabs(program_id, "setup")
            if item.get("key") in {"overview", "member_ops", "executions"}
        ]
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
        workspace_tabs=workspace_tabs,
        program_context=_program_context(program, active_key="setup") if program else None,
        setup_workspace=_build_program_setup_workspace(program_id, step=step, audience_picker=audience_picker) if program_id else {},
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
