from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.admin_auth import save_admin_user


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, SECRET_KEY="test-secret-key", ADMIN_AUTH_MODE="wecom_sso") as app:
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _authorize_admin(app) -> None:
    with app.app_context():
        save_admin_user(
            {
                "wecom_userid": "root.admin",
                "display_name": "Root Admin",
                "wecom_corpid": app.config["WECOM_CORP_ID"],
                "role_codes": ["super_admin"],
                "is_active": "1",
            },
            operator="test-suite",
        )


def _login(client, app, monkeypatch) -> None:
    _authorize_admin(app)
    start_response = client.get("/auth/wecom/start?mode=qr&next=/admin/automation-conversion", follow_redirects=False)
    state = parse_qs(urlparse(start_response.headers["Location"]).query)["state"][0]
    monkeypatch.setattr(
        "wecom_ability_service.http.internal_auth.exchange_code_for_wecom_user",
        lambda code: {
            "wecom_userid": "root.admin",
            "display_name": "Root Admin",
            "wecom_corpid": app.config["WECOM_CORP_ID"],
            "raw_identity": {"UserId": "root.admin"},
        },
    )
    callback_response = client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)
    assert callback_response.status_code == 302


def _default_program_id(app) -> int:
    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM automation_program WHERE program_code = 'signup_conversion_v1' LIMIT 1"
        ).fetchone()
        return int(row["id"])


def _admin_action_token(html: str) -> str:
    match = re.search(r'name="admin_action_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


def _program_row(html: str, program_id: int) -> str:
    match = re.search(rf'<tr id="program-row-{program_id}".*?</tr>', html, flags=re.S)
    assert match
    return match.group(0)


def _seed_choice_questionnaire(app, *, slug: str = "segmentation-choice-case") -> dict[str, object]:
    with app.app_context():
        db = get_db()
        qid = int(
            db.execute(
                """
                INSERT INTO questionnaires (slug, name, title, description)
                VALUES (?, ?, ?, '')
                RETURNING id
                """,
                (slug, slug, "黄小璨AI内测申请"),
            ).fetchone()["id"]
        )
        question_id = int(
            db.execute(
                """
                INSERT INTO questionnaire_questions (questionnaire_id, type, title, sort_order)
                VALUES (?, 'single_choice', '以下哪个选项更贴合你目前的状态？', 1)
                RETURNING id
                """,
                (qid,),
            ).fetchone()["id"]
        )
        text_question_id = int(
            db.execute(
                """
                INSERT INTO questionnaire_questions (questionnaire_id, type, title, sort_order)
                VALUES (?, 'textarea', '请补充你的业务背景', 2)
                RETURNING id
                """,
                (qid,),
            ).fetchone()["id"]
        )
        option_ids = []
        for sort_order, option_text in enumerate(
            ["刚开始了解 AI", "已经尝试过几个工具", "已经在实际业务中使用"],
            start=1,
        ):
            option_ids.append(
                int(
                    db.execute(
                        """
                        INSERT INTO questionnaire_options (question_id, option_text, sort_order)
                        VALUES (?, ?, ?)
                        RETURNING id
                        """,
                        (question_id, option_text, sort_order),
                    ).fetchone()["id"]
                )
            )
        db.commit()
    return {
        "id": qid,
        "question_id": question_id,
        "text_question_id": text_question_id,
        "option_ids": option_ids,
    }


def test_operation_task_panel_uses_single_task_language():
    source = (REPO_ROOT / "wecom_ability_service/templates/admin_console/_automation_operation_orchestration_panel.html").read_text(
        encoding="utf-8"
    )

    assert "运营任务" in source
    assert "新增分组" in source
    assert "新增任务" in source
    assert "所属分组" in source
    assert "每天触发时间" in source
    assert "目标人群" in source
    assert "进入人群第 N 天" in source
    assert "行为过滤" in source
    assert "刷新人群预览" in source
    assert "统一内容" in source
    assert "按画像分层群发" in source
    assert "按消息数分层群发" in source
    assert "Agent 改写 / 个性化" in source
    assert "分层话术" in source
    assert "绑定图片" in source
    assert "绑定小程序" in source
    assert "执行节点" not in source
    assert "节点配置" not in source
    assert "任务流" not in source
    assert "入口来源" not in source
    assert "发送去重" not in source
    assert "检查与执行" not in source
    assert "从当前任务复制" not in source


def test_default_program_bootstraps_and_automation_entry_lists_programs(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)
    program_id = _default_program_id(app)
    default_row = _program_row(html, program_id)

    assert response.status_code == 200
    assert "自动化运营方案" in html
    assert "id=\"program-create-panel\" class=\"admin-card program-panel\" hidden" in html
    assert "共享资源" in html
    assert "/admin/automation-conversion/shared/agents" in html
    assert "运行时中心" in html
    assert "/admin/automation-conversion/runtime" in html
    assert "新建方案" in html
    assert "默认自动化转化方案" in html
    assert "方案列表" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/setup?step=basic">编辑</a>' in default_row
    assert "配置向导" not in default_row
    assert ">进入</a>" not in default_row
    assert "edit_program_id" not in default_row
    assert "复制" in html
    assert ("停用" in html) or ("启用" in html)
    assert "归档" in html


def test_program_routes_render_and_removed_legacy_routes_404(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    overview_response = client.get(f"/admin/automation-conversion/programs/{program_id}/overview")
    operations_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations")
    flow_design_response = client.get(f"/admin/automation-conversion/programs/{program_id}/flow-design")
    member_ops_response = client.get(f"/admin/automation-conversion/programs/{program_id}/member-ops")
    workflow_new_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations/workflows/new")
    executions_response = client.get(f"/admin/automation-conversion/programs/{program_id}/executions")
    legacy_overview = client.get("/admin/automation-conversion/overview", follow_redirects=False)
    legacy_operations = client.get("/admin/automation-conversion/operations", follow_redirects=False)
    legacy_flow_design = client.get("/admin/automation-conversion/flow-design", follow_redirects=False)
    legacy_member_ops = client.get("/admin/automation-conversion/member-ops", follow_redirects=False)

    assert overview_response.status_code == 200
    assert operations_response.status_code == 302
    assert operations_response.headers["Location"].endswith(f"/admin/automation-conversion/programs/{program_id}/setup?step=operations")
    assert flow_design_response.status_code == 302
    assert flow_design_response.headers["Location"].endswith(f"/admin/automation-conversion/programs/{program_id}/setup?step=segmentation")
    assert member_ops_response.status_code == 200
    assert workflow_new_response.status_code == 302
    assert executions_response.status_code == 200
    assert "默认自动化转化方案" in overview_response.get_data(as_text=True)
    assert legacy_overview.status_code == 404
    assert legacy_operations.status_code == 404
    assert legacy_flow_design.status_code == 404
    assert legacy_member_ops.status_code == 404

    assert client.get("/admin/automation-conversion/operations/workflows/new").status_code == 404
    assert client.get("/admin/automation-conversion/operations/workflows/1/edit").status_code == 404
    assert client.get("/admin/automation-conversion/operations/workflows/1/nodes").status_code == 404
    assert client.get("/admin/automation-conversion/operations/executions").status_code == 404


def test_setup_navigation_is_the_only_program_edit_entry(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    setup_response = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=basic")
    html = setup_response.get_data(as_text=True)

    assert setup_response.status_code == 200
    assert "配置向导" in html
    assert "概览" in html
    assert "成员运营" in html
    assert "执行记录" in html
    assert "基础配置" not in html
    assert f"/admin/automation-conversion/programs/{program_id}/flow-design" not in html
    assert f"/admin/automation-conversion/programs/{program_id}/operations" not in html


def test_setup_segmentation_and_entry_rule_hide_raw_json_inputs(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    segmentation_html = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=segmentation").get_data(as_text=True)
    entry_rule_html = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=entry-rule").get_data(as_text=True)

    assert "普通问卷规则" in segmentation_html
    assert "总分分层" in segmentation_html
    assert "多维画像" in segmentation_html
    assert "规则 JSON" not in segmentation_html
    assert "总分区间 JSON" not in segmentation_html
    assert "规则 JSON" not in entry_rule_html
    assert "命中选项 ID" not in segmentation_html
    assert "hit_option_ids" not in segmentation_html
    assert "入口进入后" in entry_rule_html
    assert "问卷提交后" in entry_rule_html


def test_setup_page_hides_inner_program_header(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    response = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=entry")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "setup-program-head" not in html
    assert html.count("<h1>自动化运营方案</h1>") <= 1
    assert "第 2 步" in html
    assert "入口渠道" in html


def test_setup_entry_channel_renders_qrcode_image(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import repo

    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)
    qr_url = "https://wework.qpic.cn/wwpic/current-program-qr.png"
    with app.app_context():
        repo.save_channel(
            {
                "program_id": program_id,
                "channel_code": "program_qr_image_case",
                "channel_name": "图片二维码",
                "qr_url": qr_url,
                "scene_value": "scene-current-program",
                "status": "active",
            }
        )
        get_db().commit()

    html = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=entry").get_data(as_text=True)

    assert '<img src="https://wework.qpic.cn/wwpic/current-program-qr.png" alt="当前方案渠道二维码"' in html
    assert "复制链接" in html
    assert "打开链接" in html
    assert "scene-current-program" in html


def test_blank_setup_entry_does_not_show_default_qrcode(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import repo
    from wecom_ability_service.domains.automation_conversion.program_service import create_automation_program

    _login(client, app, monkeypatch)
    default_program_id = _default_program_id(app)
    default_qr_url = "https://wework.qpic.cn/wwpic/default-program-qr.png"
    with app.app_context():
        repo.save_channel(
            {
                "program_id": default_program_id,
                "channel_code": "default_qr_isolation_case",
                "channel_name": "默认二维码",
                "qr_url": default_qr_url,
                "scene_value": "default-scene",
                "status": "active",
            }
        )
        blank = create_automation_program(
            {"program_name": "二维码空白隔离方案", "program_code": "blank_qr_isolation_case", "status": "draft"},
            operator_id="test",
        )["program"]
        get_db().commit()

    html = client.get(f"/admin/automation-conversion/programs/{blank['id']}/setup?step=entry").get_data(as_text=True)

    assert default_qr_url not in html
    assert "尚未生成二维码" in html or "还没有二维码配置" in html


def test_setup_segmentation_shows_question_and_option_text_without_option_id_field(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import program_repo

    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)
    questionnaire = _seed_choice_questionnaire(app, slug="segmentation-ui-choice-case")
    with app.app_context():
        program_repo.upsert_config_block_row(
            program_id,
            "questionnaire_segmentation",
            {"questionnaire_id": questionnaire["id"], "default_strategy": "normal_question_rules"},
            status="saved",
        )
        get_db().commit()

    html = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=segmentation").get_data(as_text=True)

    assert "以下哪个选项更贴合你目前的状态？" in html
    assert "刚开始了解 AI" in html
    assert "已经尝试过几个工具" in html
    assert "已经在实际业务中使用" in html
    assert "请补充你的业务背景" not in html
    assert "新增分类" in html
    assert "分类名称" in html
    assert "未分配选项" in html
    assert "可加入此分类的未分配选项" in html
    assert "已选择选项" in html
    assert "分配概览" not in html
    assert "当前题目选项" not in html
    assert "setup-option-checks" not in html
    assert "命中选项 ID" not in html
    assert "hit_option_ids" not in html


def test_setup_footer_saves_before_navigation(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    html = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=segmentation").get_data(as_text=True)

    assert ">下一步</a>" not in html
    assert ">下一步</button>" not in html
    assert "保存并下一步" in html
    assert "data-save-and-next" in html
    assert "data-next-step=\"entry-rule\"" in html
    assert "data-save-and-publish" in html
    assert "saveCurrentStep" in html
    assert "const nextStep = event.currentTarget?.dataset.nextStep || \"\";" in html
    assert "const nextStep = event.currentTarget.dataset.nextStep || \"\";" not in html


def test_program_basic_info_edit_updates_list_and_context_header(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)
    list_response = client.get("/admin/automation-conversion")
    token = _admin_action_token(list_response.get_data(as_text=True))

    update_response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/update",
        data={
            "admin_action_token": token,
            "program_name": "默认自动化转化方案 UI 已编辑",
            "description": "列表页编辑后的方案说明",
            "next": "/admin/automation-conversion",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    updated_list = client.get("/admin/automation-conversion").get_data(as_text=True)
    assert "默认自动化转化方案 UI 已编辑" in updated_list
    assert "列表页编辑后的方案说明" not in updated_list

    updated_setup = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=basic").get_data(as_text=True)
    assert "默认自动化转化方案 UI 已编辑" in updated_setup
    assert "列表页编辑后的方案说明" in updated_setup

    updated_context = client.get(f"/admin/automation-conversion/programs/{program_id}/overview").get_data(as_text=True)
    assert "默认自动化转化方案 UI 已编辑" in updated_context
    assert "列表页编辑后的方案说明" not in updated_context
    assert "编辑方案信息" not in updated_context
    assert "内部编码" not in updated_context


def test_archived_program_badge_renders(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_program (
                program_code, program_name, description, status, config_json, created_by, updated_by
            )
            VALUES ('archived_ui_case', '归档 UI 方案', '归档状态展示用例', 'archived', '{}', 'test', 'test')
            """
        )
        db.commit()

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "归档 UI 方案" in html
    assert "program-status--archived" in html
    assert ">归档</span>" in html


def test_removed_shared_and_runtime_legacy_routes_are_gone(app, client, monkeypatch):
    _login(client, app, monkeypatch)

    legacy_agent_config = client.get("/admin/automation-conversion/agent-config", follow_redirects=False)
    legacy_run_center = client.get("/admin/automation-conversion/run-center", follow_redirects=False)
    shared_agents = client.get("/admin/automation-conversion/shared/agents", follow_redirects=False)
    runtime = client.get("/admin/automation-conversion/runtime", follow_redirects=False)

    assert legacy_agent_config.status_code == 404
    assert legacy_run_center.status_code == 404
    assert shared_agents.status_code == 200
    assert runtime.status_code == 200


def test_workflow_list_filters_by_program_id(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    default_program_id = _default_program_id(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_program (program_code, program_name, status, config_json)
            VALUES ('secondary_program', '第二方案', 'active', '{}')
            """
        )
        second_program_id = int(db.execute("SELECT id FROM automation_program WHERE program_code = 'secondary_program'").fetchone()["id"])
        db.execute(
            """
            INSERT INTO automation_workflow (
                program_id, workflow_code, workflow_name, status, created_by, updated_by
            )
            VALUES
                (?, 'default_wf', '默认任务流', 'active', 'test', 'test'),
                (?, 'second_wf', '第二任务流', 'active', 'test', 'test')
            """,
            (default_program_id, second_program_id),
        )
        db.commit()

    default_response = client.get(f"/api/admin/automation-conversion/workflows?program_id={default_program_id}")
    second_response = client.get(f"/api/admin/automation-conversion/workflows?program_id={second_program_id}")

    default_codes = [item["workflow"]["workflow_code"] for item in default_response.get_json()["items"]]
    second_codes = [item["workflow"]["workflow_code"] for item in second_response.get_json()["items"]]
    assert default_codes == ["default_wf"]
    assert second_codes == ["second_wf"]


def test_setup_blank_program_does_not_read_default_config_block(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import program_repo
    from wecom_ability_service.domains.automation_conversion.program_service import create_automation_program

    _login(client, app, monkeypatch)
    default_program_id = _default_program_id(app)
    with app.app_context():
        program_repo.upsert_config_block_row(
            default_program_id,
            "questionnaire_segmentation",
            {
                "questionnaire_id": 99,
                "strategies": {
                    "normal_question_rules": {"enabled": True, "rules": [{"rule_name": "默认规则"}]},
                },
            },
            status="saved",
        )
        blank = create_automation_program(
            {"program_name": "空白隔离方案", "program_code": "blank_isolation_case", "status": "draft"},
            operator_id="test",
        )["program"]

    response = client.get(f"/api/admin/automation-conversion/programs/{blank['id']}/setup?step=segmentation")
    assert response.status_code == 200
    segmentation = response.get_json()["setup"]["segmentation"]
    assert segmentation["questionnaire_id"] is None
    assert segmentation["normal_question_rules"]["rows"] == []


def test_copy_program_copies_config_blocks_not_channels_or_links(app):
    from wecom_ability_service.domains.automation_conversion import program_repo, repo
    from wecom_ability_service.domains.automation_conversion.customer_acquisition_service import create_customer_acquisition_link
    from wecom_ability_service.domains.automation_conversion.program_service import copy_automation_program, create_automation_program

    app.config["WECOM_CORP_ID"] = "ww-test"
    with app.app_context():
        source = create_automation_program(
            {"program_name": "源方案", "program_code": "copy_source_case", "status": "draft"},
            operator_id="test",
        )["program"]
        program_repo.upsert_config_block_row(
            int(source["id"]),
            "questionnaire_segmentation",
            {"questionnaire_id": 321, "strategies": {"score_segments": {"enabled": True, "ranges": []}}},
            status="saved",
        )
        program_repo.upsert_config_block_row(
            int(source["id"]),
            "entry_channel",
            {
                "qrcode": {
                    "channel_name": "源渠道配置",
                    "qr_ticket": "ticket-from-source",
                    "qr_url": "https://example.com/source-qr",
                    "scene_value": "source-scene",
                },
                "customer_acquisition_link_ids": [999],
            },
            status="saved",
        )
        repo.save_channel(
            {
                "program_id": int(source["id"]),
                "channel_code": "program_source_channel",
                "channel_name": "源渠道",
                "status": "active",
            }
        )
        create_customer_acquisition_link(
            {
                "program_id": int(source["id"]),
                "link_id": "copy-source-link",
                "link_name": "源获客链接",
                "link_url": "https://work.weixin.qq.com/ca/copy-source",
            }
        )

        copied = copy_automation_program(
            int(source["id"]),
            {"program_name": "复制方案", "program_code": "copy_target_case"},
            operator_id="test",
        )["program"]
        copied_block = program_repo.get_config_block_row(int(copied["id"]), "questionnaire_segmentation")
        copied_entry_block = program_repo.get_config_block_row(int(copied["id"]), "entry_channel")
        target_channels = repo.list_channels_by_program(int(copied["id"]))
        target_links = repo.list_customer_acquisition_links(program_id=int(copied["id"]))

    assert copied_block
    assert copied_block["payload_json"]["questionnaire_id"] == 321
    assert copied_entry_block
    copied_qrcode = copied_entry_block["payload_json"]["qrcode"]
    assert copied_qrcode["channel_name"] == "源渠道配置"
    assert "qr_ticket" not in copied_qrcode
    assert "qr_url" not in copied_qrcode
    assert "scene_value" not in copied_qrcode
    assert "customer_acquisition_link_ids" not in copied_entry_block["payload_json"]
    assert target_channels == []
    assert target_links == []


def test_entry_publish_minimum_available_without_full_automation(app):
    from wecom_ability_service.domains.automation_conversion.program_service import create_automation_program
    from wecom_ability_service.domains.automation_conversion.program_setup_service import (
        build_publish_check,
        publish_entry,
        save_entry_channel,
        save_setup_basic,
    )

    with app.app_context():
        program = create_automation_program(
            {"program_name": "入口发布方案", "program_code": "entry_publish_case", "status": "draft"},
            operator_id="test",
        )["program"]
        save_setup_basic(int(program["id"]), {"program_name": "入口发布方案", "program_code": "entry_publish_case"}, operator_id="test")
        save_entry_channel(int(program["id"]), {"channel_name": "入口二维码", "welcome_message": "欢迎"})
        check = build_publish_check(int(program["id"]))
        result = publish_entry(int(program["id"]), operator_id="test")

    assert check["entry"]["passed"] is True
    assert check["full"]["passed"] is False
    assert result["program"]["status"] == "active"


def test_program_scoped_customer_acquisition_link(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    app.config["WECOM_CORP_ID"] = "ww-test"
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_program (program_code, program_name, status, config_json)
            VALUES ('ca_program_a', '获客方案 A', 'draft', '{}'),
                   ('ca_program_b', '获客方案 B', 'draft', '{}')
            """
        )
        program_a = int(db.execute("SELECT id FROM automation_program WHERE program_code = 'ca_program_a'").fetchone()["id"])
        program_b = int(db.execute("SELECT id FROM automation_program WHERE program_code = 'ca_program_b'").fetchone()["id"])
        db.commit()

    response = client.post(
        f"/api/admin/automation-conversion/programs/{program_a}/customer-acquisition-links",
        json={
            "link_id": "program-ca-a",
            "link_name": "方案 A 获客",
            "link_url": "https://work.weixin.qq.com/ca/program-a",
            "initial_audience_code": "pending_questionnaire",
        },
    )
    assert response.status_code == 201
    link = response.get_json()["link"]
    assert int(link["program_id"]) == program_a
    assert "customer_channel=" in link["final_url"]

    a_links = client.get(f"/api/admin/automation-conversion/programs/{program_a}/customer-acquisition-links").get_json()["links"]
    b_links = client.get(f"/api/admin/automation-conversion/programs/{program_b}/customer-acquisition-links").get_json()["links"]
    assert [item["link_id"] for item in a_links] == ["program-ca-a"]
    assert b_links == []
    with app.app_context():
        row = get_db().execute(
            """
            SELECT l.program_id AS link_program_id, c.program_id AS channel_program_id
            FROM wecom_customer_acquisition_links l
            INNER JOIN automation_channel c ON c.id = l.automation_channel_id
            WHERE l.id = ?
            """,
            (int(link["id"]),),
        ).fetchone()
    assert int(row["link_program_id"]) == program_a
    assert int(row["channel_program_id"]) == program_a


def test_setup_score_segmentation_validation_and_match():
    from wecom_ability_service.domains.automation_conversion.program_setup_service import (
        match_score_segment,
        validate_score_ranges,
    )

    payload = {
        "strategies": {
            "score_segments": {
                "enabled": True,
                "ranges": [
                    {"min_score": 45, "max_score": 64, "segment_key": "warm"},
                    {"min_score": 65, "max_score": 84, "segment_key": "hot"},
                ],
            }
        }
    }
    validate_score_ranges(payload)
    assert match_score_segment(payload, 72)["segment_key"] == "hot"

    overlap = {
        "strategies": {
            "score_segments": {
                "enabled": True,
                "ranges": [
                    {"min_score": 0, "max_score": 50, "segment_key": "a"},
                    {"min_score": 50, "max_score": 80, "segment_key": "b"},
                ],
            }
        }
    }
    with pytest.raises(ValueError, match="不能重叠"):
        validate_score_ranges(overlap)


def test_save_normal_question_option_categories(app):
    from wecom_ability_service.domains.automation_conversion import program_repo
    from wecom_ability_service.domains.automation_conversion.program_service import create_automation_program
    from wecom_ability_service.domains.automation_conversion.program_setup_service import save_segmentation

    questionnaire = _seed_choice_questionnaire(app, slug="save-option-category-case")
    with app.app_context():
        program = create_automation_program(
            {"program_name": "选项分类方案", "program_code": "option_category_case", "status": "draft"},
            operator_id="test",
        )["program"]
        option_ids = questionnaire["option_ids"]
        save_segmentation(
            int(program["id"]),
            {
                "questionnaire_id": questionnaire["id"],
                "default_strategy": "normal_question_rules",
                "normal_question_mode": "single_question_option_category",
                "segmentation_question_id": questionnaire["question_id"],
                "normal_question_categories": [
                    {
                        "category_key": "category_a",
                        "category_name": "入门用户",
                        "option_ids": option_ids[:2],
                    },
                    {
                        "category_key": "category_b",
                        "category_name": "进阶用户",
                        "option_ids": option_ids[2:],
                    },
                ],
            },
        )
        block = program_repo.get_config_block_row(int(program["id"]), "questionnaire_segmentation")

    payload = block["payload_json"]
    normal = payload["strategies"]["normal_question_rules"]
    assert normal["segmentation_question_id"] == questionnaire["question_id"]
    assert normal["mode"] == "single_question_option_category"
    assert normal["categories"][0]["category_name"] == "入门用户"
    assert normal["categories"][0]["option_ids"] == option_ids[:2]
    assert normal["categories"][0]["option_snapshots"][0]["option_text"] == "刚开始了解 AI"

    with app.app_context(), pytest.raises(ValueError, match="不能同时属于多个分类"):
        save_segmentation(
            int(program["id"]),
            {
                "questionnaire_id": questionnaire["id"],
                "default_strategy": "normal_question_rules",
                "normal_question_mode": "single_question_option_category",
                "segmentation_question_id": questionnaire["question_id"],
                "normal_question_categories": [
                    {"category_name": "A", "option_ids": [option_ids[0]]},
                    {"category_name": "B", "option_ids": [option_ids[0]]},
                ],
            },
        )


def test_operation_action_templates_and_from_template_create_current_workflow(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    templates_response = client.get("/api/admin/automation-conversion/action-templates")
    assert templates_response.status_code == 200
    templates_payload = templates_response.get_json()
    template_names = {item["template_name"] for item in templates_payload["items"]}
    assert {"问卷提交后跟进", "未填问卷提醒", "低互动用户唤醒"}.issubset(template_names)
    assert {item["template_source"] for item in templates_payload["items"]} >= {"builtin"}

    local_response = client.post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "本地提醒模板",
            "template_source": "crm_local",
            "category": "questionnaire",
            "description": "用于本地沉淀",
            "default_config": {
                "action_name": "本地提醒模板",
                "content_strategy": "standard_content",
                "standard_content_text": "请完成问卷",
            },
            "workflow_blueprint": {
                "audiences": ["pending_questionnaire"],
                "generation_mode": "manual_layered",
            },
            "node_blueprints": [
                {
                    "node_name": "本地提醒节点",
                    "target_audience_code": "pending_questionnaire",
                    "trigger_mode": "daily_recurring",
                    "day_offset": 1,
                    "send_time": "10:00",
                    "content_mode": "standard_direct",
                    "standard_content_text": "请完成问卷",
                }
            ],
        },
    )
    assert local_response.status_code == 201
    assert local_response.get_json()["template"]["template_source"] == "crm_local"

    create_response = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/actions/from-template",
        json={
            "template_code": "questionnaire_pending_reminder",
            "config": {
                "action_name": "提醒填写问卷动作",
                "content_strategy": "standard_content",
                "standard_content_text": "请先完成问卷，我会根据结果给你后续建议。",
                "status": "draft",
            },
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.get_json()
    workflow = created_payload["workflow_bundle"]["workflow"]
    nodes = created_payload["workflow_bundle"]["nodes"]
    assert workflow["workflow_name"] == "提醒填写问卷动作"
    assert workflow["generation_mode"] == "manual_layered"
    assert nodes[0]["node_name"] == "提醒用户填写问卷"
    assert nodes[0]["standard_content_text"] == "请先完成问卷，我会根据结果给你后续建议。"

    from_workflow_response = client.post(
        "/api/admin/automation-conversion/action-templates/from-workflow",
        json={
            "workflow_id": created_payload["workflow_id"],
            "template_name": "从动作保存模板",
            "description": "反向保存",
        },
    )
    assert from_workflow_response.status_code == 201
    saved_template = from_workflow_response.get_json()["template"]
    assert saved_template["template_source"] == "crm_local"
    assert saved_template["template_name"] == "从动作保存模板"


def test_action_orchestration_page_is_main_operations_entry(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    response = client.get(f"/admin/automation-conversion/programs/{program_id}/setup?step=operations")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<iframe" not in html
    assert "运营任务" in html
    assert "新增任务" in html
    assert "新增分组" in html
    assert "搜索任务标题" in html
    assert "保存草稿" in html
    assert "保存并发布" in html
    assert "保存并下一步" not in html
    assert "去检查发布" not in html
    assert "触发与对象" in html
    assert "发送策略" in html
    assert "分层话术" in html
    assert "每天触发时间" in html
    assert "进入人群第 N 天" in html
    assert "行为过滤" in html
    assert "刷新人群预览" in html
    assert "统一内容" in html
    assert "按画像分层群发" in html
    assert "按消息数分层群发" in html
    assert "Agent 改写 / 个性化" in html
    assert "绑定图片" in html
    assert "绑定小程序" in html
    assert "window.__automationOperationSaveDraft" in html
    assert "window.__automationOperationPublish" in html
    assert "task-groups" in html
    assert "preview-audience" in html
    assert "minmax(300px, 360px) minmax(0, 1fr)" in html
    assert "@media (max-width: 960px)" in html
    assert "执行节点" not in html
    assert "节点配置" not in html
    assert "任务流" not in html
    assert "入口来源" not in html
    assert "发送去重" not in html
    assert "检查与执行" not in html
    assert "@media (max-width: 1280px)" not in html


def test_operation_task_group_create_copy_filter_and_preview(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)
    with app.app_context():
        db = get_db()
        channel_id = int(
            db.execute(
                """
                INSERT INTO automation_channel (
                    program_id, channel_code, channel_name, owner_staff_id, status
                )
                VALUES (?, ?, '测试渠道', 'channel_sender_preview', 'active')
                RETURNING id
                """,
                (program_id, f"program_{program_id}_operation_task_preview"),
            ).fetchone()["id"]
        )
        member_id = int(
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, current_audience_code,
                    current_audience_entered_at, behavior_tier_key, source_channel_id
                )
                VALUES ('ext-operation-task-preview', '13800000000', 'operating', CURRENT_DATE::text, 'lt_2', ?)
                RETURNING id
                """,
                (channel_id,),
            ).fetchone()["id"]
        )
        db.execute(
            """
            INSERT INTO automation_member_audience_entry (
                member_id, audience_code, entered_at, is_current, entry_source
            )
            VALUES (?, 'operating', CURRENT_DATE::text, TRUE, 'test')
            """,
            (member_id,),
        )
        db.commit()

    group_response = client.post(
        f"/api/admin/automation-conversion/task-groups?program_id={program_id}",
        json={"group_name": "激活任务"},
    )
    assert group_response.status_code == 201
    group_id = group_response.get_json()["group"]["id"]

    create_response = client.post(
        f"/api/admin/automation-conversion/tasks?program_id={program_id}",
        json={
            "group_id": group_id,
            "task_name": "消息少于 2 次用户促活",
            "status": "draft",
            "send_time": "14:00",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "lt_2",
            "content_mode": "behavior_layered",
            "segment_contents_json": [
                {"segment_key": "lt_2", "segment_name": "消息少于 2", "content_text": "回来看看新的资料吧"},
            ],
        },
    )
    assert create_response.status_code == 201
    task = create_response.get_json()["task"]
    assert task["group_id"] == group_id

    list_response = client.get(f"/api/admin/automation-conversion/tasks?program_id={program_id}&group_id={group_id}")
    assert [item["task_name"] for item in list_response.get_json()["tasks"]] == ["消息少于 2 次用户促活"]

    preview_response = client.post(
        f"/api/admin/automation-conversion/tasks/{task['id']}/preview-audience?program_id={program_id}",
        json=task,
    )
    assert preview_response.status_code == 200
    preview = preview_response.get_json()["preview"]
    assert preview["target_count"] == 1
    assert preview["segment_counts"]["lt_2"] == 1

    copy_response = client.post(f"/api/admin/automation-conversion/tasks/{task['id']}/copy")
    assert copy_response.status_code == 201
    copied = copy_response.get_json()["task"]
    assert copied["group_id"] == group_id
    assert copied["status"] == "draft"
    assert copied["task_name"].endswith("/ 复制")


def test_operation_task_due_runner_enqueues_and_worker_handler_sends(app, monkeypatch):
    from datetime import datetime

    from wecom_ability_service.domains.automation_conversion.operation_task_service import (
        create_operation_task,
        run_due_operation_tasks,
    )
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    program_id = _default_program_id(app)
    captured: dict[str, object] = {}

    def fake_dispatch(task_type, fn_name, payload):
        captured["task_type"] = task_type
        captured["fn_name"] = fn_name
        captured["payload"] = payload
        return {"task_id": 7788, "wecom_result": {"errcode": 0, "fail_list": []}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.sync_all_conversion_member_audiences",
        lambda: None,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.private_message_dispatch.dispatch_wecom_task",
        fake_dispatch,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task",
        fake_dispatch,
    )

    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM automation_channel WHERE program_id = ?", (program_id,))
        channel_id = int(
            db.execute(
                """
                INSERT INTO automation_channel (
                    program_id, channel_code, channel_name, owner_staff_id, status
                )
                VALUES (?, ?, '群发渠道', 'channel_sender', 'active')
                RETURNING id
                """,
                (program_id, f"program_{program_id}_default_qrcode"),
            ).fetchone()["id"]
        )
        db.execute(
            """
            INSERT INTO automation_channel (
                program_id, channel_code, channel_name, owner_staff_id, status
            )
            VALUES (?, ?, '获客助手入口', 'other_channel_sender', 'active')
            """,
            (program_id, f"wecom_customer_acquisition_{program_id}_other"),
        )
        member_id = int(
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, current_audience_code,
                    current_audience_entered_at, behavior_tier_key, source_channel_id
                )
                VALUES ('ext-operation-task-send', '13800000001', 'member_owner_should_not_send', 'operating', CURRENT_DATE::text, 'lt_2', ?)
                RETURNING id
                """,
                (channel_id,),
            ).fetchone()["id"]
        )
        db.execute(
            """
            INSERT INTO automation_member_audience_entry (
                member_id, audience_code, entered_at, is_current, entry_source
            )
            VALUES (?, 'operating', CURRENT_DATE::text, TRUE, 'test')
            """,
            (member_id,),
        )
        task = create_operation_task(
            program_id,
            {
                "task_name": "到点群发测试",
                "status": "active",
                "send_time": "14:00",
                "target_audience_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "lt_2",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "今天记得回来看看"},
            },
            operator_id="pytest",
        )["task"]

        scheduled_now = datetime.now().replace(hour=14, minute=1, second=0, microsecond=0)
        due_result = run_due_operation_tasks(
            program_id=program_id,
            now=scheduled_now,
            operator_id="pytest-runner",
        )
        assert due_result["ok"] is True
        assert due_result["enqueued_count"] >= 1
        second_due_result = run_due_operation_tasks(
            program_id=program_id,
            now=scheduled_now,
            operator_id="pytest-runner",
        )
        assert second_due_result["ok"] is True
        assert second_due_result["enqueued_count"] == 0

        claimed = queue_service.claim_due_jobs(limit=10, now=scheduled_now.replace(minute=2))
        operation_jobs = [item for item in claimed if item["source_type"] == "operation_task"]
        assert len(operation_jobs) == 1
        job = operation_jobs[0]
        assert job["content_payload"]["pre_scheduled"] is True
        assert job["trace_id"].startswith(f"actask-{task['id']}-")
        assert job["content_payload"].get("fn_name") != "send_text"

        outcome = execute_job(job)
        assert outcome["ok"] is True, outcome
        assert outcome["sent_count"] == 1
        assert captured["fn_name"] == "create_private_message_task"
        assert captured["task_type"] == "private_message"
        assert captured["payload"]["sender"] == "channel_sender"
        assert captured["payload"]["external_userid"] == ["ext-operation-task-send"]
        assert captured["payload"]["text"]["content"] == "今天记得回来看看"

        item = db.execute(
            """
            SELECT status, send_record_id, error_message
            FROM automation_operation_task_execution_item
            WHERE task_id = ?
            LIMIT 1
            """,
            (task["id"],),
        ).fetchone()
        assert item["status"] == "sent"
        assert int(item["send_record_id"] or 0) > 0
        assert item["error_message"] == ""


def test_multiple_operation_tasks_due_at_same_time_send_independently(app, monkeypatch):
    from datetime import datetime

    from wecom_ability_service.domains.automation_conversion.operation_task_service import (
        create_operation_task,
        run_due_operation_tasks,
    )
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    program_id = _default_program_id(app)
    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type, fn_name, payload):
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": payload})
        return {"task_id": 8800 + len(dispatched_payloads), "wecom_result": {"errcode": 0, "fail_list": []}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.sync_all_conversion_member_audiences",
        lambda: None,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.private_message_dispatch.dispatch_wecom_task",
        fake_dispatch,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task",
        fake_dispatch,
    )

    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM automation_channel WHERE program_id = ?", (program_id,))
        channel_id = int(
            db.execute(
                """
                INSERT INTO automation_channel (
                    program_id, channel_code, channel_name, owner_staff_id, status
                )
                VALUES (?, ?, '并发群发渠道', 'concurrent_channel_sender', 'active')
                RETURNING id
                """,
                (program_id, f"program_{program_id}_default_qrcode"),
            ).fetchone()["id"]
        )
        member_id = int(
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, current_audience_code,
                    current_audience_entered_at, behavior_tier_key, source_channel_id
                )
                VALUES ('ext-operation-task-concurrent', '13800000002', 'member_owner_ignored', 'operating', CURRENT_DATE::text, 'lt_2', ?)
                RETURNING id
                """,
                (channel_id,),
            ).fetchone()["id"]
        )
        db.execute(
            """
            INSERT INTO automation_member_audience_entry (
                member_id, audience_code, entered_at, is_current, entry_source
            )
            VALUES (?, 'operating', CURRENT_DATE::text, TRUE, 'test')
            """,
            (member_id,),
        )
        task_a = create_operation_task(
            program_id,
            {
                "task_name": "同点任务 A",
                "status": "active",
                "send_time": "14:00",
                "target_audience_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "lt_2",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "A 内容"},
            },
            operator_id="pytest",
        )["task"]
        task_b = create_operation_task(
            program_id,
            {
                "task_name": "同点任务 B",
                "status": "active",
                "send_time": "14:00",
                "target_audience_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "lt_2",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "B 内容"},
            },
            operator_id="pytest",
        )["task"]

        scheduled_now = datetime.now().replace(hour=14, minute=1, second=0, microsecond=0)
        queue_service.enqueue_job(
            source_type="manual",
            source_id="manual-same-time",
            source_table="manual_test",
            scheduled_for=scheduled_now.replace(minute=0),
            target_external_userids=["ext-manual-same-time"],
            target_summary="1 人",
            content_type="private_message",
            content_payload={
                "fn_name": "create_private_message_task",
                "wecom_payload": {
                    "sender": "manual_sender",
                    "external_userid": ["ext-manual-same-time"],
                    "text": {"content": "手动队列内容"},
                },
            },
            content_summary="手动队列内容",
        )
        due_result = run_due_operation_tasks(program_id=program_id, now=scheduled_now, operator_id="pytest-runner")
        assert due_result["ok"] is True
        assert due_result["enqueued_count"] >= 2

        claimed = queue_service.claim_due_jobs(limit=10, now=scheduled_now.replace(minute=2))
        operation_jobs = [item for item in claimed if item["source_type"] == "operation_task"]
        manual_jobs = [item for item in claimed if item["source_type"] == "manual"]
        assert len(operation_jobs) == 2
        assert len(manual_jobs) == 1
        outcomes = [execute_job(job) for job in operation_jobs + manual_jobs]
        assert all(item["ok"] is True for item in outcomes)
        assert [item["sent_count"] for item in outcomes] == [1, 1, 1]

        rows = db.execute(
            """
            SELECT task_id, status, send_record_id
            FROM automation_operation_task_execution_item
            WHERE task_id IN (?, ?)
            ORDER BY task_id ASC
            """,
            (task_a["id"], task_b["id"]),
        ).fetchall()
        assert [dict(row)["task_id"] for row in rows] == [task_a["id"], task_b["id"]]
        assert all(dict(row)["status"] == "sent" for row in rows)
        assert all(int(dict(row)["send_record_id"] or 0) > 0 for row in rows)

    sent_texts = [
        dict(dict(item["payload"])["text"])["content"]
        for item in dispatched_payloads
    ]
    assert sorted(sent_texts) == ["A 内容", "B 内容", "手动队列内容"]
    operation_senders = {
        dict(item["payload"])["sender"]
        for item in dispatched_payloads
        if dict(dict(item["payload"])["text"])["content"] in {"A 内容", "B 内容"}
    }
    assert operation_senders == {"concurrent_channel_sender"}


def test_registered_due_jobs_include_operation_task(monkeypatch):
    from wecom_ability_service.domains.automation_conversion import due_jobs_service

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.operation_task_service.run_due_operation_tasks",
        lambda operator_id: {"ok": True, "ran": 1, "enqueued_count": 2, "failed_count": 0, "results": []},
    )

    codes = [item["job_code"] for item in due_jobs_service.list_registered_due_jobs()]
    assert "operation_task" in codes
    result = due_jobs_service.run_registered_due_jobs(job_codes=["operation_task"], operator_id="pytest")
    assert result["ok"] is True
    assert result["total_success_count"] == 2


def test_operation_task_panel_saves_single_task_payload():
    html = (
        REPO_ROOT
        / "wecom_ability_service/templates/admin_console/_automation_operation_orchestration_panel.html"
    ).read_text(encoding="utf-8")

    assert "function collectPayload" in html
    assert "group_id" in html
    assert "send_time" in html
    assert "target_audience_code" in html
    assert "audience_day_offset" in html
    assert "behavior_filter" in html
    assert "content_mode" in html
    assert "unified_content_json" in html
    assert "segment_contents_json" in html
    assert "agent_config_json" in html
    assert "withId(apiUrls.task_base, currentId())" in html
    assert "withId(apiUrls.task_copy_base, taskId)" in html
    assert "withId(apiUrls.task_preview_base, currentId())" in html
    assert "operation_config" not in html
    assert "loadExistingAction" not in html


def test_ai_action_template_generate_returns_chinese_error_when_model_unavailable(app, client, monkeypatch):
    _login(client, app, monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/action-templates/generate",
        json={
            "business_goal": "用户加入社群后，如果 3 天内没填问卷，就自动发提醒。",
            "preference": "尽量简单，一个节点优先",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "AI 模板生成失败，请稍后重试或改用 CRM 本地创建"
