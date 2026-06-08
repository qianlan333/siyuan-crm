from __future__ import annotations

from html import unescape
import re
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "aicrm_next/automation_engine/templates/admin_console/base.html"
ADMIN_PAGES = ROOT / "aicrm_next/automation_engine/admin_pages.py"
WORKSPACE_CSS = ROOT / "aicrm_next/automation_engine/static/admin_console/automation_conversion_workspace.css"
SETUP_TEMPLATE = ROOT / "aicrm_next/automation_engine/templates/admin_console/automation_program_setup_next.html"


def _client(monkeypatch) -> TestClient:
    import aicrm_next.automation_engine.admin_pages as admin_pages

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "automation-program-workspace-ui-test")

    program_data = {
        "program": {
            "id": 1,
            "program_name": "9.9已经付费引流方案",
            "program_code": "paid_99",
            "status": "active",
            "description": "生产方案",
            "config_json": {},
        },
        "summary": {"member_count": 152, "channel_count": 1, "workflow_count": 1},
    }
    setup_payload = {
        **program_data,
        "step": "basic",
        "steps": admin_pages.SETUP_STEPS,
        "is_default_program": False,
        "basic": {},
        "entry": {
            "channels": [],
            "candidate_channels": [],
            "api_urls": {
                "bindings": "/api/admin/automation-conversion/programs/1/channel-bindings",
                "binding_base": "/api/admin/automation-conversion/programs/1/channel-bindings/0",
            },
        },
        "segmentation": {
            "available_questionnaires": [],
            "question_rows": [],
            "normal_question_rules": {},
            "score_segments": {"enabled": False, "rows": []},
            "profile_dimension": {"available_templates": []},
        },
        "audience_entry_rule": {
            "order_review": {"enabled": False},
            "questionnaire_review": {"enabled": True},
            "conversion_review": {"enabled": False},
            "next_steps": {},
            "available_products": [],
            "available_questionnaires": [],
        },
        "operations": {"active_count": 0, "tasks": []},
        "publish_check": {
            "entry": {"passed": True, "items": [{"label": "至少有一个当前方案入口", "passed": True}]},
            "full": {"passed": True, "items": [{"label": "存在启用中的运营任务", "passed": True}]},
        },
    }
    overview_payload = {
        **program_data,
        "summary": {"member_count": 152},
        "stage_segments": [
            {
                "key": "operating",
                "label": "运营中",
                "count": 123,
                "list_url": "/admin/automation-conversion/programs/1/members?stage=operating&page=1&page_size=20",
            },
            {
                "key": "questionnaire_review",
                "label": "问卷审核",
                "count": 29,
                "list_url": "/admin/automation-conversion/programs/1/members?stage=questionnaire_review&page=1&page_size=20",
            },
        ],
    }
    members_payloads = {
        "all": {
            "ok": True,
            "program_id": 1,
            "program": program_data["program"],
            "stage_key": "all",
            "stage_label": "全部成员",
            "total": 152,
            "page": 1,
            "page_size": 20,
            "items": [],
            "pagination": {"has_prev": False, "has_next": False, "prev_url": "", "next_url": ""},
        },
        "operating": {
            "ok": True,
            "program_id": 1,
            "program": program_data["program"],
            "stage_key": "operating",
            "stage_label": "运营中",
            "total": 123,
            "page": 1,
            "page_size": 20,
            "items": [],
            "pagination": {"has_prev": False, "has_next": False, "prev_url": "", "next_url": ""},
        },
    }
    bindings = [
        {
            "id": 3,
            "binding_status": "active",
            "channel_id": 7,
            "channel": {
                "id": 7,
                "channel_name": "所有已经报名9.9的",
                "channel_code": "program_1_default_qrcode",
                "channel_type": "qrcode",
                "carrier_type": "qrcode",
                "status": "active",
                "scene_value": "aqr_260519_5811",
                "qr_url": "https://wework.qpic.cn/wwpic/current-program-qr.png",
            },
        }
    ]
    candidates = [
        {
            "id": 8,
            "channel_name": "私教版首月入口",
            "channel_code": "program_private_first_month",
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "status": "active",
            "customer_channel": "ca_260608_001",
            "link_url": "https://work.weixin.qq.com/ca/example",
        }
    ]

    monkeypatch.setattr(admin_pages, "get_automation_program_with_summary", lambda program_id: program_data)
    monkeypatch.setattr(admin_pages, "get_automation_program_overview_payload", lambda program_id: dict(overview_payload))
    monkeypatch.setattr(
        admin_pages,
        "get_automation_program_setup_payload",
        lambda program_id, *, step="basic": {**setup_payload, "step": step},
    )
    monkeypatch.setattr(
        admin_pages,
        "get_automation_program_members_payload",
        lambda program_id, *, stage_key, page, page_size, keyword=None: members_payloads.get(stage_key, members_payloads["all"]),
    )
    monkeypatch.setattr(admin_pages, "list_program_channel_bindings_resource", lambda program_id: bindings)
    monkeypatch.setattr(admin_pages, "list_program_entry_candidate_channels", lambda program_id: candidates)

    return TestClient(create_app(), raise_server_exceptions=False)


def _active_tab(html: str) -> str:
    matches = re.findall(r'<a class="setup-topbar-tab is-active" href="[^"]+">([^<]+)</a>', html)
    assert len(matches) == 1
    return matches[0]


def test_workspace_header_tabs_are_real_links_and_have_one_active_state(monkeypatch) -> None:
    client = _client(monkeypatch)
    pages = {
        "overview": ("/admin/automation-conversion/programs/1/overview", "数据概览"),
        "setup": ("/admin/automation-conversion/programs/1/setup", "配置向导"),
        "entry": ("/admin/automation-conversion/programs/1/entry-channels", "入口渠道"),
    }

    for _, (path, active_label) in pages.items():
        html = client.get(path).text
        assert "setup-topbar-tabs" in html
        assert "data-program-workspace-switcher" in html
        assert _active_tab(html) == active_label
        assert 'href="/admin/automation-conversion/programs/1/overview"' in html
        assert 'href="/admin/automation-conversion/programs/1/setup"' in html
        assert 'href="/admin/automation-conversion/programs/1/entry-channels"' in html
        assert 'href="#"' not in html


def test_workspace_routes_promote_tabs_into_shell_header() -> None:
    admin_pages = ADMIN_PAGES.read_text(encoding="utf-8")
    base = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert '"page_header_tabs": _automation_program_workspace_tabs(request, program_id, "overview")' in admin_pages
    assert '"page_header_tabs": _automation_program_workspace_tabs(request, program_id, "setup")' in admin_pages
    assert '"page_header_tabs": _automation_program_workspace_tabs(request, program_id, "entry_channels")' in admin_pages
    assert admin_pages.count('"page_header_tabs": _automation_program_workspace_tabs(request, program_id, "overview")') >= 2
    assert "fallback_workspace_tabs = workspace_tabs" in base
    assert "header_tabs = explicit_header_tabs if explicit_header_tabs else fallback_workspace_tabs" in base


def test_overview_uses_one_metric_row_structure_and_real_member_links(monkeypatch) -> None:
    html = _client(monkeypatch).get("/admin/automation-conversion/programs/1/overview").text
    decoded = unescape(html)

    assert "ac-workspace-tabs--program-hero" not in html
    assert "overview-card" not in html
    assert "当前方案总人数" in html
    assert "运营中" in html
    assert "问卷审核" in html
    assert "/admin/automation-conversion/programs/1/members?stage=all&page=1&page_size=20" in decoded
    assert "/admin/automation-conversion/programs/1/members?stage=operating&page=1&page_size=20" in decoded
    assert "/admin/automation-conversion/programs/1/members?stage=questionnaire_review&page=1&page_size=20" in decoded
    assert re.search(r'class="overview-row overview-row--total" data-stage-key="all".*当前方案总人数', html, re.S)
    assert re.search(r'class="overview-row" data-stage-key="operating".*运营中', html, re.S)
    assert html.count("查看 list") == 3


def test_entry_channels_keeps_real_binding_contract(monkeypatch) -> None:
    html = _client(monkeypatch).get("/admin/automation-conversion/programs/1/entry-channels").text

    assert "ac-workspace-tabs--program-hero" not in html
    assert 'data-channel-admission-page="entry-channels"' in html
    assert 'data-program-id="1"' in html
    assert 'data-api-bindings="/api/admin/automation-conversion/programs/1/channel-bindings"' in html
    assert "data-open-bind-modal" in html
    assert "data-close-bind-modal" in html
    assert "data-confirm-bind" in html
    assert "data-unbind-channel" in html
    assert "data-binding-id" in html
    assert "data-bind-candidate" in html
    assert "data-bind-channel-checkbox" in html
    assert "绑定已有渠道码" in html
    assert "私教版首月入口" in html


def test_setup_steps_and_data_urls_stay_wired(monkeypatch) -> None:
    client = _client(monkeypatch)
    html = client.get("/admin/automation-conversion/programs/1/setup").text
    operations = client.get("/admin/automation-conversion/programs/1/setup?step=operations").text

    assert "data-setup-root" in html
    assert "data-urls=" in html
    for step in ["basic", "entry", "segmentation", "entry-rule", "operations", "publish"]:
        assert f"/admin/automation-conversion/programs/1/setup?step={step}" in html
    for label in ["基础信息", "入口渠道", "分层规则", "入池规则", "运营编排", "检查并发布"]:
        assert label in html
    for key in ["publish_full", "segmentation", "audience_entry_rule"]:
        assert key in html
    for key in ["operation_tasks", "task_copy_base", "task_activate_base", "task_pause_base", "task_preview_audience_base"]:
        assert key in operations
    assert "operation-tasks" in operations


def test_publish_and_members_pages_render(monkeypatch) -> None:
    client = _client(monkeypatch)

    publish = client.get("/admin/automation-conversion/programs/1/setup?step=publish")
    members_all = client.get("/admin/automation-conversion/programs/1/members?stage=all&page=1&page_size=20")
    members_operating = client.get("/admin/automation-conversion/programs/1/members?stage=operating&page=1&page_size=20")

    assert publish.status_code == 200
    assert "检查并发布" in publish.text
    assert members_all.status_code == 200
    assert members_operating.status_code == 200
    assert "setup-topbar-tabs" in members_all.text
    assert _active_tab(members_all.text) == "数据概览"


def test_desktop_admin_width_contract_stays_protected() -> None:
    css = WORKSPACE_CSS.read_text(encoding="utf-8")
    setup_template = SETUP_TEMPLATE.read_text(encoding="utf-8")

    assert ".admin-layout" in css
    assert "min-width: 1180px" in css
    assert ".program-overview,\n.setup-shell,\n.channel-page" in css
    assert "min-width: 960px" in css
    assert ".setup-topbar-tab.is-active" in css
    assert "border: 1px solid #e5e7eb" in css
    assert "border-color: #bfdbfe" in css
    assert "@media (max-width: 1080px)" not in setup_template
