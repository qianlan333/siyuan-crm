from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PICKER_JS = ROOT / "aicrm_next/frontend_compat/static/admin_console/operation_member_picker.js"
PICKER_CSS = ROOT / "aicrm_next/frontend_compat/static/admin_console/admin_console.css"
BASE_TEMPLATE = ROOT / "aicrm_next/frontend_compat/templates/admin_console/base.html"
LEGACY_BASE_TEMPLATE = ROOT / "wecom_ability_service/templates/admin_console/base.html"
GROUP_OPS_JS = ROOT / "aicrm_next/automation_engine/group_ops/static/admin_console/group_ops.js"
CHANNEL_FORM = ROOT / "aicrm_next/automation_engine/templates/admin_console/channel_code_form.html"
CHANNEL_JS = ROOT / "aicrm_next/automation_engine/static/admin_console/channel_admission_pages.js"
CHANNEL_CENTER_JS = ROOT / "aicrm_next/automation_engine/static/admin_console/channel_code_center_next.js"
CHANNEL_CENTER_TEMPLATE = ROOT / "aicrm_next/automation_engine/templates/admin_console/channel_code_center.html"
OPERATIONS_TEMPLATE = ROOT / "aicrm_next/frontend_compat/templates/admin_console/operations.html"
JOBS_TEMPLATE = ROOT / "aicrm_next/frontend_compat/templates/admin_console/jobs.html"
ADMIN_JOBS_TEMPLATE = ROOT / "aicrm_next/admin_jobs/templates/admin_console/jobs.html"
ADMIN_JOBS_BASE = ROOT / "aicrm_next/admin_jobs/templates/admin_console/base.html"
AI_ASSISTANT_SOURCES = [
    ROOT / "aicrm_next/frontend_compat/static/admin_console/automation_agent_config.js",
    ROOT / "aicrm_next/frontend_compat/static/admin_console/automation_agent_config_channel_model.js",
    ROOT / "aicrm_next/frontend_compat/templates/admin_console/automation_agent_config.html",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operation_member_picker_modal_is_simplified_and_searches_common_api():
    source = _read(PICKER_JS)

    assert "/api/admin/common/operation-members" in source
    assert "function ensureStyles()" in source
    assert "ensureStyles();" in source
    assert "data-operation-member-picker-style" in source
    assert "position: fixed" in source
    assert "z-index: 10000" in source
    assert "display: none !important" in source
    assert "选择运营人员" in source
    assert "搜索姓名或 userID，选择后回填到当前页面。" in source
    assert "data-operation-member-search" in source
    assert "data-operation-member-clear" in source
    assert "data-operation-member-list" in source
    assert "data-operation-member-cancel" in source
    assert "data-operation-member-confirm" in source
    assert "operation-member-picker__close" in source
    assert ">关闭<" in source
    assert "data-operation-member-search-button" not in source
    assert "全部来源" not in source
    assert "当前选择" not in source
    assert "来源" not in source
    assert "部门" not in source
    assert "角色" not in source
    assert "绑定数量" not in source
    assert "data-operation-member-current" not in source


def test_operation_member_picker_rows_only_show_identity_avatar_and_select_button():
    source = _read(PICKER_JS)
    css = _read(PICKER_CSS)

    assert "displayName" in source
    assert "userId" in source
    assert "member.avatar_url" in source
    assert "operation-member-picker__avatar" in source
    assert "operation-member-picker__identity" in source
    assert "data-operation-member-row-select" in source
    assert "已选" in source
    assert "选择" in source
    assert "avatarUrl ? `" in source
    assert "ui-avatars" not in source
    assert "initial" not in source.lower()
    assert "首字母" not in source
    assert "fake" not in source.lower()
    assert "source" not in source
    assert "department_name" not in source
    assert "member.role" not in source
    assert ".role" not in source
    assert "operation-member-picker__select" in css
    assert "width: min(820px, 100%)" in css
    assert "grid-template-columns: 1fr 110px" in css
    assert "background: var(--panel-strong, #fff)" in css
    assert "box-shadow: var(--shadow-lg, 0 18px 54px rgba(15, 23, 42, 0.18))" in css
    assert "display: none !important" in css


def test_operation_member_picker_error_empty_debounce_clear_cancel_confirm_contract():
    source = _read(PICKER_JS)

    assert "人员加载失败，请稍后重试" in source
    assert "没有找到匹配人员" in source
    assert "setTimeout(() => load(), 260)" in source
    assert 'searchInput?.addEventListener("input"' in source
    assert "clearTimeout(state.debounceTimer)" in source
    assert "if (input) input.value = \"\";" in source
    assert "state.selected = state.confirmed" in source
    assert "if (!state.selected) return;" in source
    assert "state.onSelect(state.selected)" in source
    assert "confirmButton.disabled = !state.selected" in source
    assert 'event.key === "Escape"' in source
    assert "url.searchParams.set(\"q\", q)" in source
    assert 'url.searchParams.set("scope", state.scope)' in source
    assert 'url.searchParams.set("page_size", state.pageSize)' in source
    assert 'url.searchParams.set("include_inactive", state.includeInactive ? "true" : "false")' in source
    assert "includeInactive" in source


def test_business_pages_use_operation_member_picker_instead_of_visible_userid_inputs():
    group_ops = _read(GROUP_OPS_JS)
    channel_form = _read(CHANNEL_FORM)
    channel_js = _read(CHANNEL_JS)
    operations = _read(OPERATIONS_TEMPLATE)
    jobs = _read(JOBS_TEMPLATE)
    admin_jobs = _read(ADMIN_JOBS_TEMPLATE)
    admin_jobs_base = _read(ADMIN_JOBS_BASE)
    base_template = _read(BASE_TEMPLATE)
    legacy_base_template = _read(LEGACY_BASE_TEMPLATE)

    assert "OperationMemberPicker.open" in group_ops
    assert "OperationMemberPicker.open" in channel_js
    assert "OperationMemberPicker.open" in operations
    assert "OperationMemberPicker.open" in jobs
    assert "OperationMemberPicker.open" in admin_jobs
    assert "operation_member_picker.js') }}?v=operation-member-picker-fix-20260527" in base_template
    assert "operation_member_picker.js') }}?v=operation-member-picker-fix-20260527" in legacy_base_template
    assert "operation_member_picker.js') }}?v=operation-member-picker-fix-20260527" in admin_jobs_base
    assert "admin_console.css') }}?v=operation-member-picker-fix-20260527" in base_template
    assert "admin_console.css') }}?v=operation-member-picker-fix-20260527" in legacy_base_template
    for source in [group_ops, channel_js, operations, jobs, admin_jobs]:
        assert "value:" in source
        assert "onSelect:" in source
        assert "selectedUserId:" not in source
    for source in [group_ops, operations, jobs, admin_jobs]:
        assert "onConfirm:" not in source
    assert "AICRMWeComTagPicker.open" in channel_js
    assert 'scope: "group_ops"' in group_ops
    assert "page_size: 100" in group_ops
    for source in [channel_js, operations, jobs, admin_jobs]:
        assert "scope:" not in source
    assert "data-channel-owner-modal" not in channel_form + channel_js
    assert "data-channel-owner-pick " not in channel_form + channel_js
    assert "data-channel-owner-pick]" not in channel_form + channel_js
    assert "owner_candidates" not in channel_form

    for source in [operations, jobs, admin_jobs]:
        assert 'type="hidden" name="owner_userid"' in source
        assert 'type="text" name="owner_userid"' not in source
        assert "请输入 userID" not in source
        assert "请输入 userid" not in source.lower()

    assert 'type="hidden" name="owner_staff_id"' in channel_form
    assert 'type="text" name="owner_staff_id"' not in channel_form
    assert 'placeholder="sales_01"' not in channel_form


def test_ai_assistant_has_no_private_operation_member_picker_or_visible_owner_inputs():
    combined = "\n".join(_read(path) for path in AI_ASSISTANT_SOURCES if path.exists())

    for forbidden in [
        "owner_userid",
        "follow_user_userid",
        "operator_userid",
        "member_userid",
        "选择负责人",
        "选择运营成员",
        "OperationMemberPicker.open",
        "data-operation-member",
        "请输入 userID",
    ]:
        assert forbidden not in combined
    assert "channel.owner_staff_id" in combined


def test_channel_center_list_keeps_edit_links_and_nonblocking_clicks():
    source = _read(CHANNEL_CENTER_JS)
    template = _read(CHANNEL_CENTER_TEMPLATE)

    assert "channel_code_center_next.js" in template
    assert "搜索渠道名称" in template
    assert "渠道编码 / 场景值" not in template
    assert '"/api/admin/channels?limit=300"' in source
    assert "Array.isArray(data.channels)" in source
    assert "String(channel.channel_name || \"\").toLowerCase()" in source
    assert "channel.channel_code" not in source
    assert "channel.scene_value" not in source
    assert "历史回调 State" not in source
    assert "/admin/channels/${encodeURIComponent(channel.id)}/edit" in source
    assert "data-open-channel-drawer" in source
    assert "data-copy-channel-link" in source
    assert "data-share-channel-link" in source
    assert "data-disabled-reason=\"owner_staff_id_required\"" in source
    assert "请先编辑渠道并选择负责人，再生成二维码" in source
    assert "parseJsonResponse" in source
    assert "content-type" in source
    assert "preventDefault" not in source
