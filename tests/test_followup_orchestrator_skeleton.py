from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.infra.settings import set_settings


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "followup-orchestrator.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "MCP_BEARER_TOKEN": "mcp-token",
            "AUTOMATION_INTERNAL_API_TOKEN": "internal-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _fmt(moment: datetime) -> str:
    return moment.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _enable_flags(app) -> None:
    with app.app_context():
        set_settings(
            {
                "ai_customer_pulse": "true",
                "ai_followup_orchestrator": "true",
            }
        )


def _set_request_scoped_followup_policy(
    app,
    *,
    tenant_key: str,
    owner_userids: list[str],
    member_userids: list[str],
) -> None:
    with app.app_context():
        set_settings(
            {
                "ai_customer_pulse": "true",
                "ai_followup_orchestrator": "true",
                "CUSTOMER_PULSE_TENANT_MODE": "request_scoped",
                "CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON": json.dumps(
                    {
                        tenant_key: {
                            "owner_userids": owner_userids,
                            "member_userids": member_userids,
                            "viewer_roles": ["sales", "ops", "admin"],
                            "operator_roles": ["sales", "ops", "admin"],
                            "internal_roles": ["ops", "admin"],
                        }
                    },
                    ensure_ascii=False,
                ),
            }
        )


def _seed_owner_role(db, *, userid: str, display_name: str, role: str = "sales") -> None:
    db.execute(
        """
        INSERT INTO owner_role_map (userid, display_name, role, active, updated_at)
        VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
        """,
        (userid, display_name, role),
    )


def _seed_contact(
    db,
    *,
    external_userid: str,
    customer_name: str,
    owner_userid: str,
) -> None:
    db.execute(
        """
        INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
        VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
        """,
        (external_userid, customer_name, owner_userid),
    )


def _insert_snapshot_and_card(
    db,
    *,
    external_userid: str,
    customer_name: str,
    owner_userid: str,
    owner_display_name: str,
    title: str,
    summary: str,
    priority_score: int,
    priority: str,
    due_at: str,
    source_updated_at: str,
    suggested_action_type: str,
    suggested_action_label: str,
    draft_message: str,
    why_now: str,
    evidence_title: str,
    evidence_detail: str,
    marketing_main_stage: str,
    marketing_sub_stage: str,
    risk_flags: list[dict] | None = None,
    tenant_key: str = "aicrm",
) -> int:
    risk_flags = list(risk_flags or [])
    evidence_refs = [
        {
            "sourceType": "archived_message",
            "sourceId": f"msg-{external_userid}",
            "title": evidence_title,
            "eventTime": source_updated_at,
        }
    ]
    evidence = [
        {
            "title": evidence_title,
            "detail": evidence_detail,
            "event_time": source_updated_at,
            "source": "archived_message",
        }
    ]
    action_payload = {"draft_message": draft_message} if suggested_action_type == "generate_reply_draft" else {}
    candidate_payload = {
        "action_type": suggested_action_type,
        "action_label": suggested_action_label,
        "payload": action_payload,
        "why_now": why_now,
    }
    snapshot_cursor = db.execute(
        """
        INSERT INTO customer_pulse_snapshots (
            tenant_key, external_userid, owner_userid, snapshot_status, confidence, priority_score,
            summary, recommended_action_type, recommended_action_label,
            evidence_json, ai_payload_json, signals_json, risk_flags_json, opportunity_flags_json,
            suggested_action_candidates_json, score_breakdown_json, source_updated_at, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, 'visible', 0.84, ?, ?, ?, ?, ?, ?, '[]', ?, '[]', ?, ?, ?, 'pytest', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            tenant_key,
            external_userid,
            owner_userid,
            priority_score,
            summary,
            suggested_action_type,
            suggested_action_label,
            json.dumps(evidence, ensure_ascii=False),
            json.dumps(
                {
                    "recommendation": {
                        "summary": summary,
                        "actionType": suggested_action_type,
                        "actionTitle": suggested_action_label,
                        "whyNow": why_now,
                        "evidenceRefs": evidence_refs,
                        "draftText": draft_message if suggested_action_type == "generate_reply_draft" else "",
                        "confidence": 0.84,
                        "safeFieldUpdates": {},
                    }
                },
                ensure_ascii=False,
            ),
            json.dumps(risk_flags, ensure_ascii=False),
            json.dumps([candidate_payload], ensure_ascii=False),
            json.dumps([{"key": "priority", "score": priority_score}], ensure_ascii=False),
            source_updated_at,
        ),
    )
    snapshot_id = int(snapshot_cursor.lastrowid)
    card_cursor = db.execute(
        """
        INSERT INTO customer_pulse_cards (
            snapshot_id, card_key, tenant_key, external_userid, customer_name, mobile,
            owner_userid, owner_display_name, card_type, card_status, priority, priority_score,
            title, summary, suggested_action_type, suggested_action_payload_json,
            suggested_action_candidates_json, evidence_json, risk_flags_json, opportunity_flags_json,
            score_breakdown_json, marketing_main_stage, marketing_sub_stage, value_segment,
            due_at, source_updated_at, need_human_confirmation, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'followup', 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, 'focus', ?, ?, 1, CURRENT_TIMESTAMP)
        """,
        (
            snapshot_id,
            f"card-{external_userid}",
            tenant_key,
            external_userid,
            customer_name,
            "13800000000",
            owner_userid,
            owner_display_name,
            priority,
            priority_score,
            title,
            summary,
            suggested_action_type,
            json.dumps(action_payload, ensure_ascii=False),
            json.dumps([candidate_payload], ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False),
            json.dumps(risk_flags, ensure_ascii=False),
            json.dumps([{"key": "priority", "score": priority_score}], ensure_ascii=False),
            marketing_main_stage,
            marketing_sub_stage,
            due_at,
            source_updated_at,
        ),
    )
    return int(card_cursor.lastrowid)


def _seed_previous_unresolved_item(db, *, external_userid: str, tenant_key: str = "aicrm") -> None:
    mission_cursor = db.execute(
        """
        INSERT INTO followup_orchestrator_missions (
            tenant_key, mission_key, mission_type, mission_status, owner_userid, team_scope_key,
            source_type, summary, priority_score, item_count, requires_manager_approval, payload_json, created_by
        )
        VALUES (?, ?, 'priority_wave', 'suggested', '', 'history', 'customer_pulse_rule_engine', 'history', 10, 1, 0, '{}', 'pytest')
        """,
        (tenant_key, f"history-{external_userid}-{datetime.now().timestamp()}"),
    )
    mission_id = int(mission_cursor.lastrowid)
    db.execute(
        """
        INSERT INTO followup_orchestrator_mission_items (
            mission_id, tenant_key, mission_item_key, item_status, assignment_status, external_userid,
            customer_name, owner_userid, suggested_assignee_userid, pulse_card_id, pulse_snapshot_id,
            payload_json, evidence_refs_json
        )
        VALUES (?, ?, ?, 'suggested', 'suggested', ?, '历史客户', '', '', NULL, NULL, '{}', '[]')
        """,
        (mission_id, tenant_key, f"history-item-{external_userid}-{datetime.now().timestamp()}", external_userid),
    )


def _seed_rule_scenarios(app, *, tenant_key: str = "aicrm") -> dict[str, str]:
    now = datetime.now().replace(microsecond=0)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="sales_01", display_name="销售一")
        _seed_owner_role(db, userid="sales_02", display_name="销售二")
        _seed_owner_role(db, userid="sales_03", display_name="销售三")
        _seed_owner_role(db, userid="manager_01", display_name="经理一", role="admin")

        _seed_contact(db, external_userid="wm_normal_01", customer_name="正常客户", owner_userid="sales_03")
        _insert_snapshot_and_card(
            db,
            external_userid="wm_normal_01",
            customer_name="正常客户",
            owner_userid="sales_03",
            owner_display_name="销售三",
            title="正常推进任务",
            summary="客户已表达继续了解意向，需要常规推进。",
            priority_score=68,
            priority="medium",
            due_at=_fmt(now + timedelta(hours=20)),
            source_updated_at=_fmt(now - timedelta(hours=2)),
            suggested_action_type="create_followup_task",
            suggested_action_label="创建跟进任务",
            draft_message="",
            why_now="客户刚完成体验课，需要在 24 小时内安排下一次回访。",
            evidence_title="体验课完成",
            evidence_detail="客户表示愿意继续了解课程方案。",
            marketing_main_stage="pool",
            marketing_sub_stage="active_focus",
            tenant_key=tenant_key,
        )

        for index in range(1, 7):
            external_userid = f"wm_overload_{index:02d}"
            _seed_contact(db, external_userid=external_userid, customer_name=f"过载客户{index}", owner_userid="sales_01")
            _insert_snapshot_and_card(
                db,
                external_userid=external_userid,
                customer_name=f"过载客户{index}",
                owner_userid="sales_01",
                owner_display_name="销售一",
                title="超 SLA 跟进任务",
                summary="客户已超出预期跟进窗口，需要团队补位。",
                priority_score=92 - index,
                priority="high",
                due_at=_fmt(now - timedelta(hours=6 + index)),
                source_updated_at=_fmt(now - timedelta(hours=10 + index)),
                suggested_action_type="create_followup_task",
                suggested_action_label="创建跟进任务",
                draft_message="",
                why_now="客户已超 SLA，当前 owner 待办负载过高，需要团队接力。",
                evidence_title="超时未跟进",
                evidence_detail="该客户在约定回访窗口后仍未得到处理。",
                marketing_main_stage="deal",
                marketing_sub_stage="proposal",
                tenant_key=tenant_key,
            )

        _seed_contact(db, external_userid="wm_unowned_01", customer_name="待认领客户", owner_userid="")
        _insert_snapshot_and_card(
            db,
            external_userid="wm_unowned_01",
            customer_name="待认领客户",
            owner_userid="",
            owner_display_name="",
            title="待认领客户",
            summary="客户刚进入高意向池，但还没有 owner。",
            priority_score=83,
            priority="high",
            due_at=_fmt(now + timedelta(hours=12)),
            source_updated_at=_fmt(now - timedelta(hours=1)),
            suggested_action_type="create_followup_task",
            suggested_action_label="创建跟进任务",
            draft_message="",
            why_now="客户已进入高意向池但尚未分配负责人，建议立即认领。",
            evidence_title="进入高意向池",
            evidence_detail="客户在问卷和聊天中表现出明确报名意愿。",
            marketing_main_stage="pool",
            marketing_sub_stage="unassigned",
            tenant_key=tenant_key,
        )

        _seed_contact(db, external_userid="wm_risk_01", customer_name="风险客户", owner_userid="sales_02")
        _insert_snapshot_and_card(
            db,
            external_userid="wm_risk_01",
            customer_name="风险客户",
            owner_userid="sales_02",
            owner_display_name="销售二",
            title="高风险投诉客户",
            summary="客户近期表达负向情绪，需要升级处理。",
            priority_score=88,
            priority="high",
            due_at=_fmt(now - timedelta(hours=30)),
            source_updated_at=_fmt(now - timedelta(hours=3)),
            suggested_action_type="generate_reply_draft",
            suggested_action_label="生成回复草稿",
            draft_message="老师您好，我先核对服务问题并给您一个明确回复。",
            why_now="客户最近出现投诉表达且已超 SLA，需要优先升级处理。",
            evidence_title="近期负向表达",
            evidence_detail="客户消息中出现“很失望”“没人跟进”。",
            marketing_main_stage="deal",
            marketing_sub_stage="risk_review",
            risk_flags=[{"key": "negative_sentiment", "label": "近期负向情绪/投诉"}],
            tenant_key=tenant_key,
        )
        _seed_previous_unresolved_item(db, external_userid="wm_risk_01", tenant_key=tenant_key)
        _seed_previous_unresolved_item(db, external_userid="wm_risk_01", tenant_key=tenant_key)

        for index in range(1, 3):
            external_userid = f"wm_batch_{index:02d}"
            _seed_contact(db, external_userid=external_userid, customer_name=f"批量客户{index}", owner_userid="sales_02")
            _insert_snapshot_and_card(
                db,
                external_userid=external_userid,
                customer_name=f"批量客户{index}",
                owner_userid="sales_02",
                owner_display_name="销售二",
                title="同模板批量草稿",
                summary="同一阶段客户适合统一预生成草稿。",
                priority_score=74,
                priority="medium",
                due_at=_fmt(now + timedelta(hours=8)),
                source_updated_at=_fmt(now - timedelta(hours=4)),
                suggested_action_type="generate_reply_draft",
                suggested_action_label="生成回复草稿",
                draft_message="老师您好，这边把试听课后的学习建议整理给您，请确认是否方便本周继续沟通。",
                why_now="这批客户处于相同阶段且近期都询问试听后的下一步安排。",
                evidence_title="试听后追问",
                evidence_detail="客户询问试听后的正式报名安排。",
                marketing_main_stage="pool",
                marketing_sub_stage="active_focus",
                tenant_key=tenant_key,
            )
        db.commit()
    return {
        "normal": "wm_normal_01",
        "unowned": "wm_unowned_01",
        "risk": "wm_risk_01",
        "batch_a": "wm_batch_01",
        "batch_b": "wm_batch_02",
    }


def _internal_headers() -> dict[str, str]:
    return {"Authorization": "Bearer internal-token"}


def _request_scoped_headers(*, tenant_key: str, admin_userid: str, admin_role: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer internal-token",
        "X-Tenant-Key": tenant_key,
        "X-Admin-Userid": admin_userid,
        "X-Admin-Role": admin_role,
    }


def _admin_action_token(client) -> str:
    page_response = client.get("/admin/followup-orchestrator")
    assert page_response.status_code == 200
    with client.session_transaction() as session:
        return str(session["admin_console_action_token"])


def test_followup_orchestrator_page_and_api_render_from_real_customer_pulse_cards(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)

    page_response = client.get("/admin/followup-orchestrator")
    api_response = client.get("/api/admin/followup-orchestrator")

    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "AI 团队跟进编排器" in page_html
    assert "我的任务包" in page_html
    assert "团队指挥台" in page_html
    assert "data-followup-orchestrator-root" in page_html

    assert api_response.status_code == 200
    payload = api_response.get_json()
    assert payload["ok"] is True
    orchestrator = payload["orchestrator"]
    assert orchestrator["summary_cards"][0]["value"] >= 11
    assert orchestrator["summary_cards"][1]["value"] >= 4
    assert orchestrator["mission_candidates"]


def test_internal_team_board_generates_rule_based_missions_and_signals(app, client):
    _enable_flags(app)
    seeded = _seed_rule_scenarios(app)

    response = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    team_board = payload["team_board"]

    missions_by_type = {item["mission_type"]: item for item in team_board["missions"]}
    assert {"priority_wave", "handoff_wave", "claim_queue", "risk_escalation_wave", "batch_draft_wave"} <= set(missions_by_type)

    priority_mission = missions_by_type["priority_wave"]
    assert any(item["external_userid"] == seeded["normal"] for item in priority_mission["items"])

    handoff_mission = missions_by_type["handoff_wave"]
    assert handoff_mission["requires_manager_approval"] is True
    assert handoff_mission["item_count"] >= 6
    overload_item = handoff_mission["items"][0]
    assert overload_item["decision"]["decision_type"] == "reassign"
    assert overload_item["suggested_assignee_userid"] != "sales_01"
    assert "owner_overloaded" in overload_item["rule_reasons"]
    assert overload_item["signals"]["owner_workload"]["is_overloaded"] is True

    claim_mission = missions_by_type["claim_queue"]
    claim_item = claim_mission["items"][0]
    assert claim_item["external_userid"] == seeded["unowned"]
    assert claim_item["decision"]["decision_type"] == "claim"
    assert claim_item["item_status"] == "unassigned"
    assert "missing_owner" in claim_item["rule_reasons"]

    risk_mission = missions_by_type["risk_escalation_wave"]
    risk_item = next(item for item in risk_mission["items"] if item["external_userid"] == seeded["risk"])
    assert risk_item["batchable"] is False
    assert "high_risk" in risk_item["rule_reasons"]
    assert "repeat_unhandled=2" in risk_item["rule_reasons"]
    assert risk_item["signals"]["due"]["is_overdue"] is True
    assert risk_item["escalation_reason"]

    batch_mission = missions_by_type["batch_draft_wave"]
    batch_external_ids = {item["external_userid"] for item in batch_mission["items"]}
    assert {seeded["batch_a"], seeded["batch_b"]} <= batch_external_ids
    assert all(item["batchable"] is True for item in batch_mission["items"])
    assert len({item["batch_group_key"] for item in batch_mission["items"]}) == 1

    for mission in team_board["missions"]:
        for item in mission["items"]:
            assert item["why_now"]
            assert item["evidence_refs"]


def test_internal_my_missions_filters_for_actor(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)

    response = client.get(
        "/api/internal/followup-orchestrator/my-missions?actor_userid=sales_01",
        headers=_internal_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    my_missions = payload["my_missions"]
    assert my_missions["actor_userid"] == "sales_01"
    assert my_missions["missions"]
    assert any(mission["mission_type"] == "handoff_wave" for mission in my_missions["missions"])


def test_internal_claim_action_updates_status_and_execution_log(app, client):
    _enable_flags(app)
    seeded = _seed_rule_scenarios(app)

    board_response = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers())
    board_payload = board_response.get_json()["team_board"]
    claim_mission = next(item for item in board_payload["missions"] if item["mission_type"] == "claim_queue")
    claim_item = next(item for item in claim_mission["items"] if item["external_userid"] == seeded["unowned"])

    action_response = client.post(
        f"/api/internal/followup-orchestrator/missions/{claim_mission['mission_key']}/actions/claim",
        headers=_internal_headers(),
        json={
            "actor_userid": "sales_02",
            "actor_role": "sales",
            "mission_item_key": claim_item["mission_item_key"],
            "note": "销售二认领该客户",
        },
    )

    assert action_response.status_code == 200
    action_payload = action_response.get_json()
    assert action_payload["ok"] is True
    updated_mission = action_payload["result"]["mission"]
    updated_item = next(item for item in updated_mission["items"] if item["mission_item_key"] == claim_item["mission_item_key"])
    assert updated_item["item_status"] == "accepted"
    assert updated_item["assignment_status"] == "accepted"

    detail_response = client.get(
        f"/api/internal/followup-orchestrator/missions/{claim_mission['mission_key']}",
        headers=_internal_headers(),
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()["mission"]
    assert detail_payload["execution_logs"]
    latest_log = detail_payload["execution_logs"][0]
    assert latest_log["action_type"] == "claim"
    assert latest_log["actor_userid"] == "sales_02"
    assert latest_log["tenant_key"] == "aicrm"

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM followup_orchestrator_execution_logs
            WHERE tenant_key = 'aicrm' AND action_type = 'claim'
            """
        ).fetchone()
        assert int(row["total"] or 0) >= 1


def test_internal_complete_action_marks_item_completed(app, client):
    _enable_flags(app)
    seeded = _seed_rule_scenarios(app)

    board_response = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers())
    board_payload = board_response.get_json()["team_board"]
    priority_mission = next(item for item in board_payload["missions"] if item["mission_type"] == "priority_wave")
    target_item = next(item for item in priority_mission["items"] if item["external_userid"] == seeded["normal"])

    action_response = client.post(
        f"/api/internal/followup-orchestrator/missions/{priority_mission['mission_key']}/actions/complete",
        headers=_internal_headers(),
        json={
            "actor_userid": "sales_03",
            "actor_role": "sales",
            "mission_item_key": target_item["mission_item_key"],
            "note": "已完成本轮跟进",
        },
    )

    assert action_response.status_code == 200
    updated_mission = action_response.get_json()["result"]["mission"]
    updated_item = next(item for item in updated_mission["items"] if item["mission_item_key"] == target_item["mission_item_key"])
    assert updated_item["item_status"] == "completed"


def test_admin_action_endpoint_executes_instead_of_returning_not_implemented(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)
    team_board = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers()).get_json()["team_board"]
    batch_mission = next(item for item in team_board["missions"] if item["mission_type"] == "batch_draft_wave")
    batch_item = batch_mission["items"][0]
    action_token = _admin_action_token(client)

    response = client.post(
        f"/api/admin/followup-orchestrator/missions/{batch_mission['mission_key']}/actions/prebuild_batch_draft",
        json={
            "admin_action_token": action_token,
            "operator": "manager_01",
            "actor_userid": "manager_01",
            "actor_role": "admin",
            "mission_item_key": batch_item["mission_item_key"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    updated_item = next(item for item in payload["result"]["mission"]["items"] if item["mission_item_key"] == batch_item["mission_item_key"])
    assert updated_item["item_status"] == "executing"
    assert updated_item["execution_state"] == "draft_ready"
    assert updated_item["latest_pulse_execution"]["action_type"] == "generate_reply_draft"


def test_admin_mission_item_preview_execute_and_undo_flow(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)
    team_board = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers()).get_json()["team_board"]
    batch_mission = next(item for item in team_board["missions"] if item["mission_type"] == "batch_draft_wave")
    batch_item = batch_mission["items"][0]
    action_token = _admin_action_token(client)

    preview_response = client.post(
        f"/api/admin/followup-orchestrator/missions/{batch_mission['mission_key']}/items/{batch_item['mission_item_key']}/actions/preview",
        json={"action_type": "generate_reply_draft"},
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.get_json()
    assert preview_payload["ok"] is True
    assert preview_payload["preview"]["preview"]["action_type"] == "generate_reply_draft"
    assert preview_payload["preview"]["item"]["mission_item_key"] == batch_item["mission_item_key"]

    execute_response = client.post(
        f"/api/admin/followup-orchestrator/missions/{batch_mission['mission_key']}/items/{batch_item['mission_item_key']}/actions/execute",
        json={
            "admin_action_token": action_token,
            "operator": "manager_01",
            "actor_userid": "manager_01",
            "actor_role": "admin",
            "action_type": "generate_reply_draft",
            "extra_payload": {"draft_message": "老师您好，这里先给您一版任务包草稿，请确认是否继续沟通。"},
        },
    )

    assert execute_response.status_code == 200
    execute_payload = execute_response.get_json()
    assert execute_payload["ok"] is True
    result = execute_payload["result"]
    assert result["action_type"] == "generate_reply_draft"
    assert int(result["pulse_execution"]["id"] or 0) > 0
    updated_item = next(item for item in result["mission"]["items"] if item["mission_item_key"] == batch_item["mission_item_key"])
    assert updated_item["execution_state"] == "draft_ready"
    assert updated_item["execution_state_label"] == "已生成草稿"
    assert updated_item["latest_pulse_execution"]["action_type"] == "generate_reply_draft"

    with app.app_context():
        db = get_db()
        activity_row = db.execute(
            """
            SELECT activity_type, activity_status
            FROM customer_pulse_activity_logs
            WHERE tenant_key = 'aicrm'
              AND card_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (batch_item["pulse_card_id"],),
        ).fetchone()
        assert activity_row is not None
        assert activity_row["activity_type"] == "reply_draft"
        orchestrator_log = db.execute(
            """
            SELECT action_type, execution_status
            FROM followup_orchestrator_execution_logs
            WHERE tenant_key = 'aicrm'
              AND mission_item_id = (
                SELECT id
                FROM followup_orchestrator_mission_items
                WHERE tenant_key = 'aicrm' AND mission_item_key = ?
              )
            ORDER BY id DESC
            LIMIT 1
            """,
            (batch_item["mission_item_key"],),
        ).fetchone()
        assert orchestrator_log is not None
        assert orchestrator_log["action_type"] == "execute_generate_reply_draft"

    undo_response = client.post(
        f"/api/admin/followup-orchestrator/missions/{batch_mission['mission_key']}/items/{batch_item['mission_item_key']}/actions/undo",
        json={
            "admin_action_token": action_token,
            "operator": "manager_01",
            "actor_userid": "manager_01",
            "actor_role": "admin",
            "execution_id": int(result["pulse_execution"]["id"]),
        },
    )

    assert undo_response.status_code == 200
    undo_payload = undo_response.get_json()
    assert undo_payload["ok"] is True
    undone_item = next(item for item in undo_payload["result"]["mission"]["items"] if item["mission_item_key"] == batch_item["mission_item_key"])
    assert undone_item["execution_state"] == "not_started"
    assert int(undo_payload["result"]["execution"]["id"] or 0) == int(result["pulse_execution"]["id"])


def test_request_scoped_handoff_approval_generates_packet_and_new_owner_can_accept(app, client):
    tenant_key = "tenant-acme"
    _set_request_scoped_followup_policy(
        app,
        tenant_key=tenant_key,
        owner_userids=["sales_01", "sales_02", "sales_03"],
        member_userids=["sales_01", "sales_02", "sales_03", "ops_1"],
    )
    _seed_rule_scenarios(app, tenant_key=tenant_key)

    manager_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops_1", admin_role="ops")
    team_board = client.get("/api/internal/followup-orchestrator/team-board", headers=manager_headers).get_json()["team_board"]
    handoff_mission = next(item for item in team_board["missions"] if item["mission_type"] == "handoff_wave")
    handoff_item = next(item for item in handoff_mission["items"] if item["suggested_assignee_userid"] and item["suggested_assignee_userid"] != item["owner_userid"])

    approval_response = client.post(
        f"/api/internal/followup-orchestrator/missions/{handoff_mission['mission_key']}/actions/request_manager_approval",
        headers=manager_headers,
        json={
            "actor_userid": "ops_1",
            "actor_role": "ops",
            "mission_item_key": handoff_item["mission_item_key"],
            "note": "批准按负载分流，由新 owner 接力。",
        },
    )

    assert approval_response.status_code == 200
    approval_payload = approval_response.get_json()
    approved_item = next(item for item in approval_payload["result"]["mission"]["items"] if item["mission_item_key"] == handoff_item["mission_item_key"])
    assert approved_item["item_status"] == "approved"
    assert approved_item["execution_state"] == "executed"
    assert approved_item["handoff_packet"]["evidence_refs"]
    assert approved_item["handoff_packet"]["decision"]["suggested_owner_userid"] == approved_item["suggested_assignee_userid"]

    new_owner_headers = _request_scoped_headers(
        tenant_key=tenant_key,
        admin_userid=approved_item["suggested_assignee_userid"],
        admin_role="sales",
    )
    detail_response = client.get(
        f"/api/internal/followup-orchestrator/missions/{handoff_mission['mission_key']}",
        headers=new_owner_headers,
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()["mission"]
    accepted_item = next(item for item in detail_payload["items"] if item["mission_item_key"] == handoff_item["mission_item_key"])
    assert accepted_item["handoff_packet"]["recent_key_events"] is not None

    accept_response = client.post(
        f"/api/internal/followup-orchestrator/missions/{handoff_mission['mission_key']}/actions/accept",
        headers=new_owner_headers,
        json={
            "actor_userid": approved_item["suggested_assignee_userid"],
            "actor_role": "sales",
            "mission_item_key": handoff_item["mission_item_key"],
            "note": "新 owner 已接手。",
        },
    )

    assert accept_response.status_code == 200
    accept_payload = accept_response.get_json()["result"]["mission"]
    accepted_item = next(item for item in accept_payload["items"] if item["mission_item_key"] == handoff_item["mission_item_key"])
    assert accepted_item["item_status"] == "accepted"
    assert accepted_item["execution_state"] == "not_started"
    assert accepted_item["active_assignee_userid"] == approved_item["suggested_assignee_userid"]

    with app.app_context():
        db = get_db()
        activity_types = [
            row["activity_type"]
            for row in db.execute(
                """
                SELECT activity_type
                FROM customer_pulse_activity_logs
                WHERE tenant_key = ?
                  AND card_id = ?
                ORDER BY id DESC
                LIMIT 5
                """,
                (tenant_key, handoff_item["pulse_card_id"]),
            ).fetchall()
        ]
        assert "orchestrator_handoff_approved" in activity_types
        assert "orchestrator_accept" in activity_types


def test_internal_team_board_requires_internal_token(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)

    response = client.get("/api/internal/followup-orchestrator/team-board")

    assert response.status_code == 401
    assert response.get_json()["error"] == "missing internal token"


def test_followup_orchestrator_ai_enhancement_success_generates_handoff_and_batch_drafts(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)
    app.config["FOLLOWUP_ORCHESTRATOR_AI_PROVIDER"] = "mock"
    app.config["FOLLOWUP_ORCHESTRATOR_AI_MOCK_RESPONSE"] = {
        "missionTitle": "本周试听后批量跟进波次",
        "missionSummary": "这批客户处于同阶段，可先统一生成草稿，再由销售逐条确认。",
        "assignmentWhy": "",
        "escalationWhy": "",
        "handoffSummary": "无需转派，建议由当前 owner 统一检查后发送。",
            "perItemDrafts": [
                {
                    "missionItemKey": "mission-item:card:10",
                    "externalUserid": "wm_batch_01",
                    "draftText": "老师您好，试听后的学习建议我整理好了，方便今天确认下后续安排吗？",
                    "confidence": 0.88,
                    "evidenceRefs": [{"sourceType": "archived_message", "sourceId": "msg-wm_batch_01"}],
                },
                {
                    "missionItemKey": "mission-item:card:11",
                    "externalUserid": "wm_batch_02",
                    "draftText": "老师您好，试听后的课程建议已整理，今天方便继续聊下正式班安排吗？",
                    "confidence": 0.86,
                    "evidenceRefs": [{"sourceType": "archived_message", "sourceId": "msg-wm_batch_02"}],
                },
        ],
        "confidence": 0.9,
        "evidenceRefs": [
            {"sourceType": "archived_message", "sourceId": "msg-wm_batch_01"},
            {"sourceType": "archived_message", "sourceId": "msg-wm_batch_02"},
        ],
    }

    response = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers())

    assert response.status_code == 200
    team_board = response.get_json()["team_board"]
    batch_mission = next(item for item in team_board["missions"] if item["mission_type"] == "batch_draft_wave")
    assert batch_mission["title"] == "本周试听后批量跟进波次"
    assert batch_mission["summary"] == "这批客户处于同阶段，可先统一生成草稿，再由销售逐条确认。"
    assert batch_mission["handoff_summary"] == "无需转派，建议由当前 owner 统一检查后发送。"
    assert batch_mission["ai_enhancement"]["status"] == "accepted"
    assert batch_mission["ai_enhancement"]["recommendation"]["confidence"] == 0.9
    batch_items = {item["external_userid"]: item for item in batch_mission["items"]}
    assert batch_items["wm_batch_01"]["ai_draft_suggestion"]["draftText"]
    assert batch_items["wm_batch_02"]["ai_draft_suggestion"]["evidenceRefs"][0]["sourceId"] == "msg-wm_batch_02"

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM automation_agent_run
            WHERE agent_code = 'followup_orchestrator_ai_agent'
            """
        ).fetchone()
        assert int(row["total"] or 0) >= 1


def test_followup_orchestrator_ai_enhancement_falls_back_on_provider_error(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)
    app.config["FOLLOWUP_ORCHESTRATOR_AI_PROVIDER"] = "mock"
    app.config["FOLLOWUP_ORCHESTRATOR_AI_MOCK_ERROR"] = "mock provider down"

    response = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers())

    assert response.status_code == 200
    team_board = response.get_json()["team_board"]
    mission = next(item for item in team_board["missions"] if item["mission_type"] == "handoff_wave")
    assert mission["ai_enhancement"]["status"] == "fallback"
    assert mission["ai_enhancement"]["fallback_reason"] == "provider_error"
    assert "mock provider down" in mission["ai_enhancement"]["error_message"]
    assert mission["title"] == "团队接力转派波次"


def test_followup_orchestrator_ai_enhancement_degrades_on_low_confidence(app, client):
    _enable_flags(app)
    _seed_rule_scenarios(app)
    app.config["FOLLOWUP_ORCHESTRATOR_AI_PROVIDER"] = "mock"
    app.config["FOLLOWUP_ORCHESTRATOR_AI_MOCK_RESPONSE"] = {
        "missionTitle": "低置信度批量波次",
        "missionSummary": "可以试着一起发。",
        "assignmentWhy": "",
        "escalationWhy": "",
        "handoffSummary": "",
        "perItemDrafts": [
            {
                "missionItemKey": "mission-item:card:9",
                "externalUserid": "wm_batch_01",
                "draftText": "我给你最低价，手机号 13800138111。",
                "confidence": 0.92,
                "evidenceRefs": [{"sourceType": "archived_message", "sourceId": "msg-wm_batch_01"}],
            }
        ],
        "confidence": 0.42,
        "evidenceRefs": [{"sourceType": "archived_message", "sourceId": "msg-wm_batch_01"}],
    }

    response = client.get("/api/internal/followup-orchestrator/team-board", headers=_internal_headers())

    assert response.status_code == 200
    team_board = response.get_json()["team_board"]
    batch_mission = next(item for item in team_board["missions"] if item["mission_type"] == "batch_draft_wave")
    assert batch_mission["ai_enhancement"]["status"] == "fallback"
    assert batch_mission["ai_enhancement"]["fallback_reason"] == "low_confidence"
    assert "low_confidence" in batch_mission["ai_enhancement"]["guardrails"]["output_violations"]
    assert batch_mission["title"] == "批量草稿波次"
    assert all(not item["ai_draft_suggestion"] for item in batch_mission["items"])


def test_followup_orchestrator_request_scoped_mission_detail_denies_unrelated_actor_without_ai_run(app, client):
    tenant_key = "tenant-acme"
    _set_request_scoped_followup_policy(
        app,
        tenant_key=tenant_key,
        owner_userids=["sales_01", "sales_02", "sales_03"],
        member_userids=["sales_01", "sales_02", "sales_03", "sales_04", "ops_1"],
    )
    _seed_rule_scenarios(app, tenant_key=tenant_key)
    app.config["FOLLOWUP_ORCHESTRATOR_AI_PROVIDER"] = "mock"
    app.config["FOLLOWUP_ORCHESTRATOR_AI_MOCK_RESPONSE"] = {
        "missionTitle": "团队接力说明",
        "missionSummary": "sales_01 过载，建议转派给 sales_03。",
        "assignmentWhy": "sales_01 当前高优先卡片过多。",
        "escalationWhy": "",
        "handoffSummary": "由 sales_03 接力处理超 SLA 客户。",
        "perItemDrafts": [],
        "confidence": 0.86,
        "evidenceRefs": [{"sourceType": "archived_message", "sourceId": "msg-wm_overload_01"}],
    }

    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops_1", admin_role="ops")
    board_response = client.get("/api/internal/followup-orchestrator/team-board", headers=ops_headers)
    assert board_response.status_code == 200
    handoff_mission = next(item for item in board_response.get_json()["team_board"]["missions"] if item["mission_type"] == "handoff_wave")

    with app.app_context():
        db = get_db()
        before = int(
            db.execute(
                """
                SELECT COUNT(*) AS total
                FROM automation_agent_run
                WHERE agent_code = 'followup_orchestrator_ai_agent'
                """
            ).fetchone()["total"]
            or 0
        )

    unrelated_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="sales_04", admin_role="sales")
    denied_response = client.get(
        f"/api/internal/followup-orchestrator/missions/{handoff_mission['mission_key']}",
        headers=unrelated_headers,
    )

    assert denied_response.status_code == 403
    assert denied_response.get_json()["code"] in {"owner_scope_forbidden", "actor_owner_scope_forbidden"}

    with app.app_context():
        db = get_db()
        after = int(
            db.execute(
                """
                SELECT COUNT(*) AS total
                FROM automation_agent_run
                WHERE agent_code = 'followup_orchestrator_ai_agent'
                """
            ).fetchone()["total"]
            or 0
        )
        assert after == before
