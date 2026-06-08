from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
SETUP_TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "automation_program_setup_next.html"
OP_TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "_automation_operation_orchestration_panel.html"
OP_JS = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console" / "automation_operation_orchestration_panel.js"
CHANNEL_JS = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console" / "channel_admission_pages.js"
ADMIN_PAGES = ROOT / "aicrm_next" / "automation_engine" / "admin_pages.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _client_with_setup(monkeypatch) -> TestClient:
    import aicrm_next.automation_engine.admin_pages as automation_admin_pages
    from aicrm_next.automation_engine.programs import SETUP_STEPS

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "setup-ui-redesign-test")

    program_data = {
        "program": {
            "id": 7,
            "program_name": "9.9已经付费引流方案",
            "program_code": "paid_99",
            "status": "active",
            "description": "生产方案",
            "config_json": {},
        },
        "summary": {"channel_count": 1, "workflow_count": 1, "latest_execution_at": "2026-05-23 09:00:00"},
    }
    setup_payload = {
        **program_data,
        "step": "basic",
        "steps": SETUP_STEPS,
        "is_default_program": False,
        "basic": {},
        "entry": {
            "channels": [
                {
                    "id": 31,
                    "binding_id": 101,
                    "channel_name": "默认渠道二维码",
                    "channel_code": "aqr_260521_b91c",
                    "channel_type": "qrcode",
                    "carrier_type": "qrcode",
                    "status": "active",
                    "binding_status": "active",
                    "scene_value": "aqr_260521_b91c",
                    "qr_url": "https://wework.qpic.cn/example",
                }
            ],
            "candidate_channels": [
                {
                    "id": 33,
                    "channel_name": "候选渠道二维码",
                    "channel_code": "aqr_260522_cand",
                    "channel_type": "qrcode",
                    "carrier_type": "qrcode",
                    "status": "active",
                    "scene_value": "aqr_260522_cand",
                    "qr_url": "https://wework.qpic.cn/candidate",
                }
            ],
            "api_urls": {
                "bindings": "/api/admin/automation-conversion/programs/7/channel-bindings",
                "binding_base": "/api/admin/automation-conversion/programs/7/channel-bindings/0",
            },
        },
        "segmentation": {
            "questionnaire_id": 9,
            "available_questionnaires": [
                {
                    "id": 9,
                    "title": "信息收集测试",
                    "status": "published",
                    "question_count": 1,
                    "questions": [{"id": 19, "title": "你当前最关注什么", "options": [{"id": 1, "option_text": "先了解"}]}],
                }
            ],
            "question_rows": [{"id": 19, "title": "你当前最关注什么", "options": [{"id": 1, "option_text": "先了解"}]}],
            "selected_questionnaire": {"title": "信息收集测试"},
            "default_strategy": "normal_question_rules",
            "normal_question_rules": {
                "segmentation_question_id": 19,
                "category_rows": [{"category_key": "intro", "category_name": "入门用户", "option_snapshots": [{"id": 1, "option_text": "先了解"}]}],
                "unassigned_options": [],
            },
            "score_segments": {"enabled": True, "rows": [{"segment_name": "高意向", "segment_key": "high", "min_score": 80, "max_score": 100}]},
            "profile_dimension": {"template_id": 9, "available_templates": [{"id": 9, "template_name": "画像模板"}]},
        },
        "audience_entry_rule": {
            "order_review": {"enabled": False},
            "questionnaire_review": {"enabled": True, "selected_questionnaire_id": 9, "selected_questionnaire_snapshot": {"title": "信息收集测试"}},
            "conversion_review": {"enabled": False},
            "next_steps": {"scan_enter": "问卷审核", "questionnaire_review": "运营中", "operating": "结束"},
            "available_products": [],
            "available_questionnaires": [{"id": 9, "title": "信息收集测试", "status": "published", "question_count": 1}],
        },
        "operations": {"active_count": 1, "tasks": []},
        "publish_check": {
            "entry": {"passed": True, "items": [{"label": "至少有一个当前方案入口", "passed": True, "message": "已完成"}]},
            "full": {"passed": True, "items": [{"label": "存在启用中的运营任务", "passed": True, "message": "已完成"}]},
        },
    }

    monkeypatch.setattr(automation_admin_pages, "get_automation_program_with_summary", lambda program_id: program_data)
    monkeypatch.setattr(
        automation_admin_pages,
        "get_automation_program_setup_payload",
        lambda program_id, *, step="basic": {**setup_payload, "step": step},
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _setup_page(client: TestClient, step: str) -> str:
    response = client.get(f"/admin/automation-conversion/programs/7/setup?step={step}")
    assert response.status_code == 200
    return response.text


def test_setup_page_removes_global_duplicate_ui(monkeypatch) -> None:
    client = _client_with_setup(monkeypatch)

    basic = _setup_page(client, "basic")
    assert '<h2>配置向导</h2>' not in basic
    assert "setup-guide" not in basic
    assert "setup-titlebar" not in basic
    assert basic.count('class="admin-page-title"') == 1
    assert basic.count("按方案配置基础信息、入口渠道、分层规则、入池规则、运营编排和发布检查。") == 1
    assert "setup-topbar-tabs" in basic
    assert 'class="setup-action" href="/admin/automation-conversion/programs/7">概览</a>' not in basic

    assert "保存草稿" not in _setup_page(client, "entry-rule")
    assert ">下一步</a>" not in _setup_page(client, "operations")
    publish = _setup_page(client, "publish")
    assert "发布入口" not in publish
    assert "查看概览" not in publish
    assert publish.count("发布完整自动化") == 1


def test_entry_step_exposes_real_channel_binding_controls(monkeypatch) -> None:
    html = _setup_page(_client_with_setup(monkeypatch), "entry")

    assert "绑定已有渠道码" in html
    assert "已绑定渠道数量" in html
    assert "可绑定候选" in html
    assert "渠道码中心" in html
    assert "候选渠道二维码" in html
    assert "data-open-bind-modal" in html
    assert "data-confirm-bind" in html
    assert "data-bind-channel-checkbox" in html
    assert "data-unbind-channel" in html
    assert '"candidate_channels"' in html
    assert '"api_urls"' in html
    assert "/api/admin/automation-conversion/programs/7/channel-bindings" in html
    assert "/api/admin/automation-conversion/programs/7/channel-bindings/0" in html


def test_segmentation_step_matches_dense_builder_contract(monkeypatch) -> None:
    html = _setup_page(_client_with_setup(monkeypatch), "segmentation")
    template = _read(SETUP_TEMPLATE)
    routes = _read(ADMIN_PAGES)

    assert "分类说明" not in html
    assert "默认方式" not in html
    assert "应用示例三档" not in html
    assert "新增分类" in html
    assert "删除分类" in html
    assert "setup-chip" in html
    assert "setup-category-grid" in html
    assert "setup-seg-toolbar" in html
    assert "urls.segmentation" in template
    assert "setup/segmentation" in routes
    assert "postJson(urls.segmentation" in template


def test_operations_step_uses_single_real_task_workspace(monkeypatch) -> None:
    html = _setup_page(_client_with_setup(monkeypatch), "operations")

    assert "读取当前方案已有运营任务" not in html
    assert "直接编辑运营任务、分组、触发条件和内容模式；所有操作走当前 Next 任务 API。" not in html
    assert "<th>任务</th><th>分组</th><th>状态</th><th>触发</th><th>目标人群</th><th>内容模式</th><th>更新时间</th>" not in html
    assert "data-operation-task-root" in html
    assert "data-task-search" in html
    assert "data-group-filter" in html
    assert "data-create-task" in html
    assert "data-create-group" in html
    assert "data-task-list" in html
    assert "任务基础信息" in html
    assert "触发与对象" in html
    assert "op-task-grid--wide" in html
    assert ".op-task-panel[hidden], .op-task-empty[hidden]" in html
    assert "统一内容" in html
    assert "按画像分层群发" in html
    assert "按消息数分层群发" in html
    assert "Agent 改写 / 个性化" in html
    assert "data-save-task" in html
    assert ".setup-panel--operations { padding: 0; border: 0; background: transparent; box-shadow: none; }" in html
    assert ".op-task-panel { display: grid; gap: 16px; padding: 0; border: 0; background: transparent; }" in html
    assert ">下一步</a>" not in html


def test_publish_step_has_single_full_publish_action(monkeypatch) -> None:
    html = _setup_page(_client_with_setup(monkeypatch), "publish")
    template = _read(SETUP_TEMPLATE)

    assert "发布入口" not in html
    assert "查看概览" not in html
    assert html.count("发布完整自动化") == 1
    assert "data-publish-full" in html
    assert "/api/admin/automation-conversion/programs/7/publish-full" in html
    assert "bindPublish(\"[data-publish-full]\", \"publish_full\"" in template
    assert "data-publish-entry" not in template


def test_setup_js_uses_real_api_urls_and_no_fake_button_selectors() -> None:
    template = _read(SETUP_TEMPLATE)
    operation_template = _read(OP_TEMPLATE)
    operation_js = _read(OP_JS)
    channel_js = _read(CHANNEL_JS)

    assert "root.dataset.apiBindings" in channel_js
    assert "(bootstrap.api_urls || {}).binding_base" in channel_js
    assert "method: \"DELETE\"" in channel_js
    assert "postJson(urls.segmentation" in template
    assert "postJson(urls.audience_entry_rule" in template
    assert "window.__automationOperationSaveCurrent" in operation_js
    assert "operation_task_base" in operation_js
    assert "task_activate_base" in operation_js
    assert "task_pause_base" in operation_js
    assert "task_delete_base" in operation_js
    assert "taskPreviewAudienceBase" in operation_js
    assert "data-save-task" in operation_template
    assert "data-apply-category-presets" not in template
    assert "data-publish-entry" not in template
