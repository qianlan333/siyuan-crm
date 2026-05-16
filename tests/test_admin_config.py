from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.admin_auth import save_admin_user
from wecom_ability_service.services import get_signup_conversion_config


def _asia_shanghai_today() -> datetime.date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        SECRET_KEY="test-secret-key",
        ADMIN_AUTH_MODE="wecom_sso",
    ) as app:
        yield app


@pytest.fixture()
def client(app):
    with app.app_context():
        save_admin_user(
            {
                "wecom_userid": "root.admin",
                "wecom_corpid": app.config["WECOM_CORP_ID"],
                "display_name": "Root Admin",
                "role_codes": ["super_admin"],
                "is_active": "1",
            },
            operator="test-suite",
        )
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin_session_user_id"] = 1
        session["admin_session_wecom_userid"] = "root.admin"
        session["admin_session_role_list"] = ["super_admin"]
        session["admin_session_login_type"] = "wecom_qr"
        session["admin_session_display_name"] = "Root Admin"
    return client


def _admin_action_token(client, path: str = "/admin/automation-conversion") -> str:
    client.get(path, follow_redirects=True)
    with client.session_transaction() as session:
        return str(session["admin_console_action_token"])


def _seed_signup_conversion_questionnaire(
    app,
    *,
    questionnaire_id: int = 71,
    question_count: int = 5,
) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"marketing-automation-{questionnaire_id}",
                "自动化转化初判问卷",
                "自动化转化初判问卷",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, question_count + 1):
            question_id = questionnaire_id * 100 + index
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, true, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, questionnaire_id, f"关键问题{index}", index),
            )
            option_ids: list[int] = []
            for option_index in range(1, 3):
                option_id = question_id * 10 + option_index
                option_ids.append(option_id)
                db.execute(
                    """
                    INSERT INTO questionnaire_options (
                        id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        option_id,
                        question_id,
                        f"问题{index}-选项{option_index}",
                        option_index * 10,
                        option_index,
                    ),
                )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = option_ids
        mobile_question_id = questionnaire_id * 100 + question_count + 1
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '手机号', true, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id, question_count + 1),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
        "mobile_question_id": mobile_question_id,
    }


def _signup_conversion_config_payload(
    questionnaire_seed: dict[str, object],
    *,
    enabled: bool = True,
    core_threshold: int = 3,
    top_threshold: int = 4,
    day_start_hour: int = 9,
    quiet_hour_start: int = 23,
    timezone: str = "Asia/Shanghai",
    question_ids: list[int] | None = None,
    hit_option_ids_by_question: dict[int, list[int]] | None = None,
    silent_threshold_days_by_pool: dict[str, int] | None = None,
) -> dict[str, object]:
    selected_question_ids = list(question_ids or questionnaire_seed["question_ids"])
    option_ids_by_question = dict(questionnaire_seed["option_ids_by_question"])
    return {
        "enabled": enabled,
        "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
        "core_threshold": core_threshold,
        "top_threshold": top_threshold,
        "day_start_hour": day_start_hour,
        "quiet_hour_start": quiet_hour_start,
        "timezone": timezone,
        "silent_threshold_days_by_pool": silent_threshold_days_by_pool
        or {
            "new_user": 7,
            "inactive_normal": 7,
            "inactive_focus": 7,
            "active_normal": 7,
            "active_focus": 7,
        },
        "question_rules": [
            {
                "questionnaire_question_id": question_id,
                "hit_option_ids_json": list(
                    hit_option_ids_by_question.get(question_id, [option_ids_by_question[question_id][0]])
                    if hit_option_ids_by_question
                    else [option_ids_by_question[question_id][0]]
                ),
                "sort_order": index,
            }
            for index, question_id in enumerate(selected_question_ids, start=1)
        ],
    }


def _seed_marketing_dispatch_history(app) -> None:
    with app.app_context():
        db = get_db()
        today = _asia_shanghai_today().isoformat()
        rows = [
            {
                "batch_id": 9101,
                "external_userid": "wm_dispatch_pending",
                "owner_userid": "sales_dispatch_01",
                "segment": "focus",
                "main_stage": "pool",
                "sub_stage": "inactive_focus",
                "dispatch_status": "pending",
                "created_at": f"{today} 10:01:00",
                "acked_at": "",
            },
            {
                "batch_id": 9102,
                "external_userid": "wm_dispatch_blocked",
                "owner_userid": "sales_dispatch_02",
                "segment": "focus",
                "main_stage": "pool",
                "sub_stage": "active_focus",
                "dispatch_status": "blocked_quiet_hours",
                "created_at": f"{today} 10:02:00",
                "acked_at": "",
            },
            {
                "batch_id": 9103,
                "external_userid": "wm_dispatch_acked",
                "owner_userid": "sales_dispatch_03",
                "segment": "normal",
                "main_stage": "pool",
                "sub_stage": "active_normal",
                "dispatch_status": "acked",
                "created_at": f"{today} 10:03:00",
                "acked_at": f"{today} 10:05:00",
            },
            {
                "batch_id": 9104,
                "external_userid": "wm_dispatch_converted",
                "owner_userid": "sales_dispatch_04",
                "segment": "focus",
                "main_stage": "converted",
                "sub_stage": "enrolled",
                "dispatch_status": "converted_before_dispatch",
                "created_at": f"{today} 10:04:00",
                "acked_at": "",
            },
    ]
        for item in rows:
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
                VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
                """,
                (item["external_userid"], item["external_userid"], item["owner_userid"]),
            )
            db.execute(
                """
                INSERT INTO message_batches (
                    id, batch_key, window_start, window_end, status, message_count, created_at
                )
                VALUES (?, ?, ?, ?, 'pending', 1, CURRENT_TIMESTAMP)
                """,
                (
                    item["batch_id"],
                    f"dispatch-batch-{item['batch_id']}",
                    f"{today} 10:00:00",
                    f"{today} 10:10:00",
                ),
            )
            db.execute(
                """
                INSERT INTO customer_marketing_state_current (
                    external_userid, automation_key, main_stage, sub_stage, activated, converted,
                    eligible_for_conversion, lifecycle_status, last_activation_at, last_conversion_marked_at,
                    last_message_at, last_batch_id, last_batch_status, last_batch_window_start, last_batch_window_end,
                    last_trigger_message_at, entered_at, exited_at, exit_reason, state_payload_json, created_at, updated_at
                )
                VALUES (?, 'signup_conversion_v1', ?, ?, false, ?, false, ?, '', '', '', ?, ?, '', '', '', ?, NULL, '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["main_stage"],
                    item["sub_stage"],
                    item["main_stage"] == "converted",
                    item["main_stage"],
                    item["batch_id"],
                    item["dispatch_status"],
                    item["created_at"],
                ),
            )
            db.execute(
                """
                UPDATE customer_marketing_state_current
                SET state_payload_json = ?
                WHERE external_userid = ?
                """,
                (
                    json.dumps({"followup_segment": item["segment"]}, ensure_ascii=False),
                    item["external_userid"],
                ),
            )
            db.execute(
                """
                INSERT INTO conversion_dispatch_log (
                    automation_key, batch_id, external_userid, dispatch_status, dispatch_channel,
                    dispatch_payload_json, dispatch_note, dispatched_at, acked_at, created_at, updated_at
                )
                VALUES ('signup_conversion_v1', ?, ?, ?, 'text_message', '{}', 'seed', ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    item["batch_id"],
                    item["external_userid"],
                    item["dispatch_status"],
                    item["created_at"],
                    item["acked_at"] or None,
                    item["created_at"],
                ),
            )
        db.commit()


def _seed_automation_conversion_stage_board(app) -> None:
    today_date = _asia_shanghai_today()
    today = today_date.isoformat()
    yesterday = (today_date - timedelta(days=1)).isoformat()
    rows = [
        {
            "external_userid": "wm_stage_new_001",
            "owner_userid": "sales_stage_01",
            "phone": "13800000001",
            "follow_type": "",
            "current_pool": "pending_questionnaire",
            "in_pool": True,
            "current_audience_code": "pending_questionnaire",
            "questionnaire_status": "pending",
            "joined_at": f"{today} 09:00:00",
        },
        {
            "external_userid": "wm_stage_inactive_normal_001",
            "owner_userid": "sales_stage_02",
            "phone": "13800000002",
            "follow_type": "normal",
            "current_pool": "operating",
            "in_pool": True,
            "current_audience_code": "operating",
            "questionnaire_status": "submitted",
            "joined_at": f"{today} 10:00:00",
        },
        {
            "external_userid": "wm_stage_inactive_focus_001",
            "owner_userid": "sales_stage_03",
            "phone": "13800000003",
            "follow_type": "focus",
            "current_pool": "operating",
            "in_pool": True,
            "current_audience_code": "operating",
            "questionnaire_status": "submitted",
            "joined_at": f"{yesterday} 11:00:00",
        },
        {
            "external_userid": "wm_stage_active_normal_001",
            "owner_userid": "sales_stage_04",
            "phone": "13800000004",
            "follow_type": "normal",
            "current_pool": "operating",
            "in_pool": True,
            "current_audience_code": "operating",
            "questionnaire_status": "submitted",
            "joined_at": f"{today} 12:00:00",
        },
        {
            "external_userid": "wm_stage_active_focus_001",
            "owner_userid": "sales_stage_05",
            "phone": "13800000005",
            "follow_type": "focus",
            "current_pool": "operating",
            "in_pool": True,
            "current_audience_code": "operating",
            "questionnaire_status": "submitted",
            "joined_at": f"{yesterday} 13:00:00",
        },
        {
            "external_userid": "wm_stage_silent_001",
            "owner_userid": "sales_stage_06",
            "phone": "13800000006",
            "follow_type": "normal",
            "current_pool": "operating",
            "in_pool": True,
            "current_audience_code": "operating",
            "questionnaire_status": "submitted",
            "joined_at": f"{yesterday} 14:00:00",
        },
        {
            "external_userid": "wm_stage_won_001",
            "owner_userid": "sales_stage_07",
            "phone": "13800000007",
            "follow_type": "focus",
            "current_pool": "converted",
            "in_pool": False,
            "current_audience_code": "converted",
            "questionnaire_status": "submitted",
            "joined_at": f"{today} 15:00:00",
        },
        ]
    with app.app_context():
        db = get_db()
        for item in rows:
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
                VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
                """,
                (item["external_userid"], item["external_userid"], item["owner_userid"]),
            )
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                    questionnaire_status, decision_source, source_type,
                    current_audience_code, current_audience_entered_at,
                    joined_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'system', 'system', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["phone"],
                    item["owner_userid"],
                    item["in_pool"],
                    item["current_pool"],
                    item["follow_type"],
                    item["questionnaire_status"],
                    item["current_audience_code"],
                    item["joined_at"],
                    item["joined_at"],
                ),
            )
        db.commit()


def _mcp_list_tools(client, token: str = "mcp-token"):
    response = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    return response.get_json()


def _visible_text(html: str) -> str:
    without_scripts = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return " ".join(without_tags.split())


def _contains_standalone_token(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", text) is not None


def test_admin_config_pages_render(client):
    expected = {
        "/admin/config": "配置中心",
        "/admin/wecom-tags": "企微标签管理",
        "/admin/automation-conversion": "自动化转化",
        "/admin/config/app-settings": "系统设置",
        "/admin/config/login-access": "登录与权限",
    }
    for path, marker in expected.items():
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert marker in html
        if path.startswith("/admin/config"):
            assert "配置中心" in html

    tags_html = client.get("/admin/wecom-tags").get_data(as_text=True)
    assert "统一后台配置模式" not in tags_html
    assert "/admin/config/wecom-tags" not in client.get("/admin/config").get_data(as_text=True)

    legacy_response = client.get("/admin/config/wecom-tags")
    assert legacy_response.status_code == 302
    assert legacy_response.headers["Location"].endswith("/admin/wecom-tags")

    overview_html = client.get("/admin/config").get_data(as_text=True)
    assert "企微标签管理" in overview_html
    assert "渠道 / 分配规则" not in overview_html
    assert "报名标签规则" not in overview_html
    assert "班期标签规则" not in overview_html


def test_legacy_config_module_routes_are_removed(client):
    removed_paths = [
        "/admin/config/routing",
        "/admin/config/routing/owner-role",
        "/admin/config/routing/rule",
        "/admin/config/signup-tags",
        "/admin/config/signup-tags/save",
        "/admin/config/class-term-tags",
        "/admin/config/class-term-tags/save",
        "/api/admin/config/routing",
        "/api/admin/config/routing/owner-role",
        "/api/admin/config/routing/rule",
        "/api/admin/config/signup-tags",
        "/api/admin/config/class-term-tags",
    ]

    for path in removed_paths:
        response = client.post(path) if path.endswith(("owner-role", "rule", "save")) else client.get(path)
        assert response.status_code == 404

def test_admin_marketing_automation_legacy_route_redirects_to_new_page(client):
    response = client.get("/admin/marketing-automation/ui", query_string={"status": "blocked_quiet_hours"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion?status=blocked_quiet_hours")


def test_routing_services_wrappers_route_through_application(monkeypatch):
    from wecom_ability_service import services as services_module
    from wecom_ability_service.application.routing_config import queries as routing_queries
    from wecom_ability_service.application.routing_config.dto import (
        GetOwnerRoleMapQueryDTO,
        GetOwnerRoleQueryDTO,
        GetRoutingRuleConfigQueryDTO,
        ResolveContactRoutingContextQueryDTO,
    )

    calls: dict[str, object] = {}

    class FakeGetOwnerRoleQuery:
        def __call__(self, dto):
            calls["get_owner_role"] = dto
            return {"userid": "sales_01", "role": "sales", "active": True}

    class FakeGetOwnerRoleMapQuery:
        def __call__(self, dto):
            calls["list_owner_role_map"] = dto
            return [{"userid": "sales_01", "role": "sales", "active": True}]

    class FakeGetRoutingRuleConfigQuery:
        def __call__(self, dto):
            calls["get_routing_config"] = dto
            return {
                "owner_role_map": [{"userid": "sales_01", "role": "sales", "active": True}],
                "signup_tag_rules": {"items": []},
                "routing_rules": {"lead": {"routing_target": "sales_handle"}},
            }

    class FakeResolveContactRoutingContextQuery:
        def __call__(self, dto):
            calls["resolve_contact_routing_context"] = dto
            return {"routing_target": "manual_review", "reason": ""}

    monkeypatch.setattr(routing_queries, "GetOwnerRoleQuery", FakeGetOwnerRoleQuery)
    monkeypatch.setattr(routing_queries, "GetOwnerRoleMapQuery", FakeGetOwnerRoleMapQuery)
    monkeypatch.setattr(routing_queries, "GetRoutingRuleConfigQuery", FakeGetRoutingRuleConfigQuery)
    monkeypatch.setattr(routing_queries, "ResolveContactRoutingContextQuery", FakeResolveContactRoutingContextQuery)
    monkeypatch.setattr(services_module, "get_signup_tag_rules_config", lambda: {"items": []})
    monkeypatch.setattr(
        services_module,
        "get_signup_status_definition",
        lambda signup_status: {"signup_status": signup_status, "routing_alias": "lead"},
    )

    assert services_module.get_owner_role("sales_01") == {
        "userid": "sales_01",
        "role": "sales",
        "active": True,
    }
    assert services_module.list_owner_role_map(active_only=True) == [
        {"userid": "sales_01", "role": "sales", "active": True}
    ]
    assert services_module.get_routing_config()["routing_rules"]["lead"]["routing_target"] == "sales_handle"
    assert services_module.resolve_contact_routing_context("sales_01", "sales", "lead") == {
        "routing_target": "manual_review",
        "reason": "",
    }

    assert isinstance(calls["get_owner_role"], GetOwnerRoleQueryDTO)
    assert isinstance(calls["list_owner_role_map"], GetOwnerRoleMapQueryDTO)
    assert isinstance(calls["get_routing_config"], GetRoutingRuleConfigQueryDTO)
    assert isinstance(calls["resolve_contact_routing_context"], ResolveContactRoutingContextQueryDTO)


def test_admin_config_settings_keep_secrets_masked_and_write_audit(app, client):
    update_response = client.put(
        "/api/settings",
        json={
            "settings": {
                "WECOM_SECRET": "secret-123456",
                "WECOM_API_BASE": "https://qyapi.example.test",
            },
            "operator": "tester-settings",
            "confirm": True,
        },
    )
    compat_payload = update_response.get_json()
    admin_payload = client.get("/api/admin/config/app-settings").get_json()

    assert update_response.status_code == 200
    assert compat_payload["ok"] is True
    assert compat_payload["settings"]["WECOM_SECRET"] != "secret-123456"
    assert "***" in compat_payload["settings"]["WECOM_SECRET"]
    assert compat_payload["settings"]["WECOM_API_BASE"] == "https://qyapi.example.test"

    secret_row = next(
        item for item in admin_payload["config"]["rows"] if item["key"] == "WECOM_SECRET"
    )
    assert secret_row["value"] == ""
    assert secret_row["display_value"] != "secret-123456"
    assert secret_row["configured"] is True

    with app.app_context():
        logs = get_db().execute(
            """
            SELECT target_id, operator
            FROM admin_operation_logs
            WHERE target_type = 'app_setting'
            ORDER BY id ASC
            """
        ).fetchall()
        assert any(row["target_id"] == "WECOM_SECRET" for row in logs)
        assert any(row["target_id"] == "WECOM_API_BASE" for row in logs)
        assert all(row["operator"] == "tester-settings" for row in logs)


def test_admin_config_settings_require_confirmation(client):
    response = client.put(
        "/api/settings",
        json={
            "settings": {
                "WECOM_API_BASE": "https://qyapi.example.test",
            },
            "operator": "tester-settings",
        },
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "confirm is required before saving app settings"


def test_admin_config_mcp_tool_settings_control_runtime(client):
    before = _mcp_list_tools(client)
    before_names = [item["name"] for item in before["result"]["tools"]]
    assert "get_owner_role_map" in before_names

    save_response = client.post(
        "/api/admin/config/mcp-tools",
        json={
            "tool_name": "get_owner_role_map",
            "tool_group": "config",
            "display_name": "Get Owner Role Map",
            "description_override": "disabled for test",
            "enabled": False,
            "visible_in_console": True,
            "show_sample_args": False,
            "show_sample_output": False,
            "sort_order": 99,
            "operator": "tester-mcp",
        },
    )
    assert save_response.status_code == 200

    after = _mcp_list_tools(client)
    after_names = [item["name"] for item in after["result"]["tools"]]
    assert "get_owner_role_map" not in after_names

    call_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_owner_role_map", "arguments": {}},
        },
    )
    payload = call_response.get_json()
    assert payload["error"]["code"] == -32000
    assert "tool is disabled" in payload["error"]["message"]


def test_admin_automation_conversion_page_renders_saved_config_and_preview_panel(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=81)
    _seed_automation_conversion_stage_board(app)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(
            seed,
            core_threshold=2,
            top_threshold=5,
            silent_threshold_days_by_pool={
                "new_user": 3,
                "inactive_normal": 4,
                "inactive_focus": 5,
                "active_normal": 6,
                "active_focus": 7,
            },
        ),
    )
    assert save_response.status_code == 200

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)
    with app.app_context():
        default_program_id = int(
            get_db()
            .execute("SELECT id FROM automation_program WHERE program_code = 'signup_conversion_v1' LIMIT 1")
            .fetchone()["id"]
        )
    overview_response = client.get(f"/admin/automation-conversion/programs/{default_program_id}/overview")
    overview_html = overview_response.get_data(as_text=True)
    overview_text = _visible_text(overview_html)

    assert response.status_code == 200
    assert "方案列表" in visible_text
    assert "默认自动化转化方案" in visible_text
    assert f"/admin/automation-conversion/programs/{default_program_id}/overview" in html
    assert overview_response.status_code == 200
    assert "运行概况" in overview_text
    assert "任务流执行" in overview_text
    assert "未填问卷人群" in overview_text
    assert "运营中人群" in overview_text
    assert "已转化人群" in overview_text
    assert f"/admin/automation-conversion/programs/{default_program_id}/operations" in overview_html
    assert "/admin/automation-conversion/shared/agents" not in overview_html



def test_admin_marketing_automation_dispatch_history_api_supports_status_filter(app, client):
    _seed_marketing_dispatch_history(app)

    response = client.get("/api/admin/marketing-automation/dispatch-history")
    blocked_response = client.get(
        "/api/admin/marketing-automation/dispatch-history",
        query_string={"status": "blocked_quiet_hours"},
    )

    payload = response.get_json()
    blocked_payload = blocked_response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["dispatch_history"]["count"] == 4
    statuses = {item["dispatch_status"] for item in payload["dispatch_history"]["items"]}
    assert {"pending", "blocked_quiet_hours", "acked", "converted_before_dispatch"} <= statuses

    assert blocked_response.status_code == 200
    assert blocked_payload["dispatch_history"]["status"] == "blocked_quiet_hours"
    assert blocked_payload["dispatch_history"]["count"] == 1
    assert blocked_payload["dispatch_history"]["items"][0]["external_userid"] == "wm_dispatch_blocked"
    assert blocked_payload["dispatch_history"]["items"][0]["stage"] == "pool/active_focus"
