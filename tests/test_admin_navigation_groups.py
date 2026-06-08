from __future__ import annotations

import re

from flask import Blueprint, Flask, render_template

from wecom_ability_service.domains.admin_dashboard import service as admin_dashboard_service
from wecom_ability_service.http.admin_console import _navigation_with_hrefs
from tools.check_next_admin_ui_data_parity import TARGET_NAV_GROUPS


def test_admin_navigation_groups_and_marks_active_item(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["super_admin"])

    groups = admin_dashboard_service.list_admin_navigation("wechat_pay_transactions")

    assert [group["title"] for group in groups] == ["运营", "交易", "素材", "配置及后台"]
    operations = groups[0]["items"]
    operations_by_key = {item["key"]: item["label"] for item in operations}
    assert [item["label"] for item in operations] == TARGET_NAV_GROUPS[0][1]
    assert operations_by_key["group_ops"] == "群运营计划"
    assert operations_by_key["user_ops_funnel"] == "漏斗 / 数据看板"
    assert "owner_migration" not in operations_by_key
    assert {item["key"]: item["label"] for item in groups[3]["items"]}["jobs"] == "同步任务配置 / 同步任务"
    assert [item["key"] for item in groups[3]["items"]] == ["jobs", "owner_migration", "config", "api_docs"]
    trade_group = groups[1]
    assert trade_group["active"] is True
    assert [item["key"] for item in trade_group["items"]] == ["wechat_pay_transactions", "wechat_pay_products"]
    assert {item["key"]: item["active"] for item in trade_group["items"]} == {
        "wechat_pay_transactions": True,
        "wechat_pay_products": False,
    }
    assert [item["label"] for item in groups[2]["items"]] == ["图片素材库", "小程序素材库", "附件素材库"]


def test_admin_navigation_filters_empty_groups_by_role(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["questionnaire_admin"])

    groups = admin_dashboard_service.list_admin_navigation("questionnaires")

    assert [group["title"] for group in groups] == ["运营", "配置及后台"]
    assert groups[0]["active"] is True
    assert groups[0]["items"] == [
        {
            "key": "questionnaires",
            "label": "问卷",
            "endpoint": "api.admin_console_questionnaires",
            "active": True,
        }
    ]
    assert [item["key"] for item in groups[1]["items"]] == ["api_docs"]


def test_automation_admin_navigation_includes_material_and_product_entries(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["automation_admin"])

    groups = admin_dashboard_service.list_admin_navigation("attachment_library")

    assert [group["title"] for group in groups] == ["运营", "素材", "配置及后台"]
    assert [item["key"] for item in groups[0]["items"]] == [
        "automation_conversion",
        "group_ops",
        "channels",
        "cloud_orchestrator",
        "customers",
        "user_ops_funnel",
        "radar_links",
    ]
    material_group = groups[1]
    assert material_group["active"] is True
    assert [item["key"] for item in material_group["items"]] == ["image_library", "miniprogram_library", "attachment_library"]
    assert {item["key"]: item["active"] for item in material_group["items"]}["attachment_library"] is True


def test_admin_base_template_renders_grouped_navigation():
    app = Flask(
        __name__,
        template_folder="../wecom_ability_service/templates",
        static_folder="../wecom_ability_service/static",
    )
    api = Blueprint("api", __name__)
    for endpoint, path in {
        "admin_dashboard_shell_context": "/api/admin/dashboard/shell-context",
        "admin_automation_conversion": "/admin/automation-conversion",
        "admin_group_ops_ui": "/admin/automation-conversion/group-ops/ui",
        "admin_channels_page": "/admin/channels",
        "admin_cloud_orchestrator_workspace": "/admin/cloud-orchestrator",
        "admin_console_customers": "/admin/customers",
        "admin_hxc_dashboard_workspace": "/admin/user-ops",
        "admin_console_questionnaires": "/admin/questionnaires",
        "admin_radar_links": "/admin/radar-links",
        "admin_wecom_tags_page": "/admin/wecom-tags",
        "admin_wechat_pay_transactions_page": "/admin/wechat-pay/transactions",
        "admin_wechat_pay_products_page": "/admin/wechat-pay/products",
        "admin_image_library_workspace": "/admin/image-library",
        "admin_miniprogram_library_workspace": "/admin/miniprogram-library",
        "admin_attachment_library_workspace": "/admin/attachment-library",
        "admin_console_jobs": "/admin/jobs",
        "admin_owner_migration_page": "/admin/owner-migration",
        "admin_config_home": "/admin/config",
        "admin_console_api_docs": "/admin/api-docs",
    }.items():
        api.add_url_rule(path, endpoint, lambda: "")
    app.register_blueprint(api)

    with app.test_request_context("/admin/wechat-pay/transactions"):
        html = render_template(
            "admin_console/base.html",
            page_title="交易管理",
            page_summary="",
            breadcrumbs=[],
            nav_items=admin_dashboard_service.list_admin_navigation("wechat_pay_transactions"),
            shell_status={},
            current_admin_user=None,
            show_shell_meta=False,
            page_notice="",
            page_error="",
        )

    assert re.search(
        r'class="admin-nav-section is-active">\s*<div class="admin-nav-section-title">交易</div>',
        html,
    )
    assert re.search(r'class="admin-nav-link is-active"\s+href="/admin/wechat-pay/transactions"', html)
    assert '<div class="admin-nav-section-title">运营</div>' in html
    assert "自动化运营" in html
    assert "群运营计划" in html
    assert "渠道码中心" in html
    assert "AI 助手" in html
    assert "客户激活 / 客户列表" in html
    assert "漏斗 / 数据看板" in html
    assert "内容雷达" in html
    assert "企微标签管理" in html
    assert "同步任务配置 / 同步任务" in html
    assert "负责人迁移" in html
    operations_section = html.split('<div class="admin-nav-section-title">运营</div>', 1)[1].split(
        '<div class="admin-nav-section-title">交易</div>',
        1,
    )[0]
    config_section = html.split('<div class="admin-nav-section-title">配置及后台</div>', 1)[1]
    assert "负责人迁移" not in operations_section
    assert "负责人迁移" in config_section
    assert "图片素材库" in html
    assert "小程序素材库" in html
    assert "附件素材库" in html
    assert "商品管理" in html


def test_legacy_admin_navigation_resolves_retired_next_owned_links(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["super_admin"])
    app = Flask(__name__)
    api = Blueprint("api", __name__)
    api.add_url_rule("/admin/automation-conversion", "admin_automation_conversion", lambda: "")
    app.register_blueprint(api)

    with app.test_request_context("/admin/automation-conversion/programs/3/setup"):
        groups = _navigation_with_hrefs("automation_conversion")

    links = {item["endpoint"]: item["href"] for group in groups for item in group["items"]}
    assert links["api.admin_automation_conversion"] == "/admin/automation-conversion"
    assert links["api.admin_group_ops_ui"] == "/admin/automation-conversion/group-ops/ui"
    assert links["api.admin_console_customers"] == "/admin/customers"
    assert links["api.admin_console_questionnaires"] == "/admin/questionnaires"
    assert links["api.admin_radar_links"] == "/admin/radar-links"
    assert links["api.admin_console_jobs"] == "/admin/jobs"
    assert links["api.admin_owner_migration_page"] == "/admin/owner-migration"


def test_legacy_admin_navigation_user_ops_keeps_target_operation_group(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["super_admin"])

    groups = admin_dashboard_service.list_admin_navigation("user_ops_funnel")

    assert [item["label"] for item in groups[0]["items"]] == TARGET_NAV_GROUPS[0][1]
    assert {item["key"]: item["active"] for item in groups[0]["items"]}["user_ops_funnel"] is True


def test_legacy_admin_navigation_user_ops_keeps_owner_migration_visible_in_config(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["super_admin"])

    groups = admin_dashboard_service.list_admin_navigation("user_ops_funnel")

    operations_group = next(group for group in groups if group["title"] == "运营")
    config_group = next(group for group in groups if group["title"] == "配置及后台")
    assert {item["key"]: item["active"] for item in operations_group["items"]}["user_ops_funnel"] is True
    assert [item["key"] for item in config_group["items"]] == ["jobs", "owner_migration", "config", "api_docs"]
    assert {item["key"]: item["active"] for item in config_group["items"]}["owner_migration"] is False


def test_legacy_admin_navigation_owner_migration_marks_config_group_active(monkeypatch):
    monkeypatch.setattr(admin_dashboard_service, "_current_admin_role_codes", lambda: ["super_admin"])

    groups = admin_dashboard_service.list_admin_navigation("owner_migration")

    config_group = next(group for group in groups if group["title"] == "配置及后台")
    assert config_group["active"] is True
    assert {item["key"]: item["active"] for item in config_group["items"]}["owner_migration"] is True
