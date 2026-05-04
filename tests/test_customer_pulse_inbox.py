from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Mapping

import pytest
import requests  # type: ignore[import-untyped]

from wecom_ability_service import create_app
from wecom_ability_service.domains.customer_pulse.access import build_customer_pulse_legacy_tenant_context
from wecom_ability_service.domains.customer_pulse import repo as customer_pulse_repo
from wecom_ability_service.domains.customer_pulse.service import (
    build_customer_pulse_first_wave_review_report,
    build_customer_pulse_tenant_rollout_report,
    customer_pulse_rollout_whitelist_summary,
    execute_customer_pulse_card_action,
    undo_customer_pulse_card_action_execution,
)
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.infra.settings import set_settings


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "customer-pulse.sqlite3"
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
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "pulse-test-admin"
        sess["admin_session_break_glass_username"] = "pulse-test-admin"
    return client


def _fmt(moment: datetime) -> str:
    return moment.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _admin_action_token(client, path: str = "/admin/api-docs", headers: dict[str, str] | None = None) -> str:
    client.get(path, headers=headers or {})
    with client.session_transaction() as sess:
        return str(sess["admin_console_action_token"])


def _force_sync_customer_pulse(client, external_userids: list[str], *, headers: dict[str, str] | None = None) -> dict:
    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token", **(headers or {})},
        json={
            "external_userids": external_userids,
            "force_sync": True,
            "operator": "pulse-test",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    return payload["result"]


def _pulse_card_by_external_userid(client, external_userid: str, *, headers: dict[str, str] | None = None) -> dict:
    inbox_response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token", **(headers or {})},
    )
    assert inbox_response.status_code == 200
    inbox = inbox_response.get_json()["inbox"]
    return next(item for item in inbox["cards"] if item["external_userid"] == external_userid)


def _seed_owner_role(
    db,
    *,
    userid: str,
    role: str,
    display_name: str | None = None,
    active: int = 1,
) -> None:
    db.execute(
        """
        INSERT INTO owner_role_map (userid, display_name, role, active, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (userid, display_name or userid, role, active),
    )


def _request_scoped_headers(
    *,
    tenant_key: str,
    admin_userid: str,
    admin_role: str,
) -> dict[str, str]:
    return {
        "X-Tenant-Key": tenant_key,
        "X-Admin-Userid": admin_userid,
        "X-Admin-Role": admin_role,
    }


def _enable_request_scoped_customer_pulse(
    app,
    *,
    tenant_key: str,
    owner_userids: list[str],
    member_userids: list[str],
    viewer_roles: list[str] | None = None,
    operator_roles: list[str] | None = None,
    internal_roles: list[str] | None = None,
) -> None:
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": owner_userids,
                "member_userids": member_userids,
                "viewer_roles": viewer_roles or ["sales", "delivery", "ops", "admin"],
                "operator_roles": operator_roles or ["sales", "delivery", "ops", "admin"],
                "internal_roles": internal_roles or ["ops", "admin"],
            }
        },
    )


def _set_request_scoped_customer_pulse_policies(app, *, policy_map: Mapping[str, Mapping[str, Any]]) -> None:
    normalized_policy_map: dict[str, dict[str, Any]] = {}
    for tenant_key, policy in dict(policy_map or {}).items():
        normalized_policy_map[str(tenant_key)] = {
            "owner_userids": list(policy.get("owner_userids") or []),
            "member_userids": list(policy.get("member_userids") or []),
            "viewer_roles": list(policy.get("viewer_roles") or ["sales", "delivery", "ops", "admin"]),
            "operator_roles": list(policy.get("operator_roles") or ["sales", "delivery", "ops", "admin"]),
            "internal_roles": list(policy.get("internal_roles") or ["ops", "admin"]),
            "permissions_by_role": dict(policy.get("permissions_by_role") or {}),
            "permissions_by_userid": dict(policy.get("permissions_by_userid") or {}),
        }
    with app.app_context():
        set_settings(
            {
                "ai_customer_pulse": "true",
                "CUSTOMER_PULSE_TENANT_MODE": "request_scoped",
                "CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON": json.dumps(normalized_policy_map, ensure_ascii=False),
            }
        )


def _set_customer_pulse_flag_policy(app, policy: Mapping[str, Any] | None) -> None:
    with app.app_context():
        set_settings(
            {
                "CUSTOMER_PULSE_FLAG_POLICY_JSON": json.dumps(dict(policy or {}), ensure_ascii=False),
            }
        )


def _legacy_tenant_context(*, operator: str = "pulse-test", user_id: str = "", role: str = "") -> Mapping[str, Any]:
    return build_customer_pulse_legacy_tenant_context(
        operator=operator,
        user_id=user_id,
        role=role,
        source="legacy_internal_test",
    )


def _seed_customer_base(
    db,
    *,
    person_id: int,
    external_userid: str,
    customer_name: str,
    owner_userid: str,
    mobile: str,
    now: datetime,
    first_owner_userid: str | None = None,
    last_owner_userid: str | None = None,
    binding_updated_at: str | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            customer_name,
            owner_userid,
            "重点",
            "客户推进测试数据",
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            person_id,
            mobile,
            f"tp-{external_userid}",
            _fmt(now),
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT INTO external_contact_bindings (
            external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            person_id,
            owner_userid,
            first_owner_userid or owner_userid,
            last_owner_userid or owner_userid,
            _fmt(now - timedelta(days=14)),
            binding_updated_at or _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT INTO wecom_external_contact_identity_map (
            corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active', '{}', ?, ?)
        """,
        (
            "ww-test",
            external_userid,
            f"union-{external_userid}",
            f"openid-{external_userid}",
            owner_userid,
            customer_name,
            _fmt(now),
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT INTO wecom_external_contact_follow_users (
            corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user, created_at, updated_at
        )
        VALUES (?, ?, ?, 'active', 1, '主跟进', ?, '{}', ?, ?)
        """,
        (
            "ww-test",
            external_userid,
            owner_userid,
            customer_name,
            _fmt(now),
            _fmt(now),
        ),
    )


def _seed_marketing_state(
    db,
    *,
    person_id: int,
    external_userid: str,
    now: datetime,
    main_stage: str = "pool",
    sub_stage: str = "active_focus",
    last_message_at: datetime | None = None,
    entered_at: datetime | None = None,
    updated_at: datetime | None = None,
    followup_segment: str = "normal",
    extra_state: dict | None = None,
    eligible_for_conversion: int = 1,
) -> None:
    payload = {"followup_segment": followup_segment}
    payload.update(extra_state or {})
    db.execute(
        """
        INSERT INTO customer_marketing_state_current (
            person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
            eligible_for_conversion, lifecycle_status, last_message_at, entered_at, state_payload_json, created_at, updated_at
        )
        VALUES (?, ?, 'signup_conversion_v1', ?, ?, 1, 0, ?, 'pool', ?, ?, ?, ?, ?)
        """,
        (
            person_id,
            external_userid,
            main_stage,
            sub_stage,
            eligible_for_conversion,
            _fmt(last_message_at or now),
            _fmt(entered_at or now),
            json.dumps(payload, ensure_ascii=False),
            _fmt(now),
            _fmt(updated_at or now),
        ),
    )


def _seed_value_segment(
    db,
    *,
    external_userid: str,
    segment: str,
    score: int,
    now: datetime,
) -> None:
    db.execute(
        """
        INSERT INTO customer_value_segment_current (
            external_userid, segment, segment_rank, score, scoring_version, computed_reason,
            matched_question_ids_json, source_payload_json, evaluated_at, computed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'signup_conversion_question_hits_v1', 'seed', '[1,2]', '{}', ?, ?, ?, ?)
        """,
        (
            external_userid,
            segment,
            3 if segment in {"top", "core"} else 1,
            score,
            _fmt(now),
            _fmt(now),
            _fmt(now),
            _fmt(now),
        ),
    )


def _seed_tag(db, *, external_userid: str, owner_userid: str, tag_id: str, tag_name: str, created_at: datetime) -> None:
    db.execute(
        """
        INSERT INTO contact_tags (userid, external_userid, tag_id, tag_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            owner_userid,
            external_userid,
            tag_id,
            tag_name,
            _fmt(created_at),
        ),
    )


def _seed_message(
    db,
    *,
    msgid: str,
    seq: int,
    external_userid: str,
    owner_userid: str,
    sender: str,
    receiver: str,
    content: str,
    send_time: datetime,
) -> None:
    db.execute(
        """
        INSERT INTO archived_messages (
            seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
        )
        VALUES (?, ?, 'private', ?, ?, ?, ?, 'text', ?, ?, '{}', ?)
        """,
        (
            seq,
            msgid,
            external_userid,
            owner_userid,
            sender,
            receiver,
            content,
            _fmt(send_time),
            _fmt(send_time),
        ),
    )


def _seed_reply_queue(
    db,
    *,
    external_userid: str,
    owner_userid: str,
    last_inbound_at: datetime,
    not_before: datetime,
    summary: str,
) -> None:
    db.execute(
        """
        INSERT INTO automation_reply_monitor_queue (
            external_userid, owner_userid, status, message_ids_json, message_count,
            first_inbound_at, last_inbound_at, not_before, payload_snapshot_json, created_at, updated_at
        )
        VALUES (?, ?, 'pending', '["queue-msg-1"]', 1, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            owner_userid,
            _fmt(last_inbound_at),
            _fmt(last_inbound_at),
            _fmt(not_before),
            json.dumps({"latest_inbound_summary": summary}, ensure_ascii=False),
            _fmt(last_inbound_at),
            _fmt(not_before),
        ),
    )


def _seed_ai_output(
    db,
    *,
    external_userid: str,
    owner_userid: str,
    now: datetime,
    draft_reply: str,
    reason: str,
) -> None:
    db.execute(
        """
        INSERT INTO automation_agent_run (
            run_id, request_id, userid, external_contact_id, agent_code, agent_type,
            input_snapshot_json, status, source, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'sales_pulse', 'router', ?, 'success', 'test', ?, ?)
        """,
        (
            f"run-{external_userid}",
            f"req-{external_userid}",
            owner_userid,
            external_userid,
            json.dumps({"messages": [{"content": reason, "send_time": _fmt(now)}]}, ensure_ascii=False),
            _fmt(now),
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT INTO automation_agent_output (
            output_id, run_id, request_id, userid, external_contact_id, agent_code, output_type,
            raw_output_text, normalized_output_json, rendered_output_text, target_pool, confidence,
            reason, need_human_review, applied_status, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'sales_pulse', 'agent_reply_draft', ?, ?, ?, 'active_focus', 0.91, ?, 1, 'pending', ?)
        """,
        (
            f"output-{external_userid}",
            f"run-{external_userid}",
            f"req-{external_userid}",
            owner_userid,
            external_userid,
            reason,
            json.dumps({"draft_reply": draft_reply, "need_human_review": True}, ensure_ascii=False),
            draft_reply,
            reason,
            _fmt(now),
        ),
    )


def _seed_questionnaire_with_apply_failure(
    db,
    *,
    external_userid: str,
    owner_userid: str,
    questionnaire_id: int,
    submitted_at: datetime,
    error_message: str,
) -> None:
    db.execute(
        """
        INSERT INTO questionnaires (id, slug, name, title, description, is_disabled, redirect_url, external_push_enabled, external_push_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, '', 0, '', 0, '', ?, ?)
        """,
        (
            questionnaire_id,
            f"questionnaire-{questionnaire_id}",
            f"问卷{questionnaire_id}",
            f"测试问卷{questionnaire_id}",
            _fmt(submitted_at),
            _fmt(submitted_at),
        ),
    )
    db.execute(
        """
        INSERT INTO questionnaire_submissions (
            questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
            matched_by, mobile_snapshot, source_channel, campaign_id, staff_id, total_score, final_tags, redirect_url_snapshot, submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'external_contact', '', 'wecom', '', ?, 92, '["高意向"]', '', ?)
        """,
        (
            questionnaire_id,
            f"respondent-{external_userid}",
            f"openid-{external_userid}",
            f"union-{external_userid}",
            external_userid,
            owner_userid,
            owner_userid,
            _fmt(submitted_at),
        ),
    )
    submission_id = int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    db.execute(
        """
        INSERT INTO questionnaire_scrm_apply_logs (
            submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
        )
        VALUES (?, ?, ?, '["高意向"]', 'failed', ?, ?)
        """,
        (
            submission_id,
            external_userid,
            owner_userid,
            error_message,
            _fmt(submitted_at + timedelta(minutes=5)),
        ),
    )


def _seed_dispatch_log(
    db,
    *,
    batch_key: str,
    external_userid: str,
    created_at: datetime,
    dispatch_status: str,
) -> None:
    db.execute(
        """
        INSERT INTO message_batches (batch_key, window_start, window_end, status, message_count, created_at)
        VALUES (?, ?, ?, 'pending', 1, ?)
        """,
        (
            batch_key,
            _fmt(created_at - timedelta(hours=1)),
            _fmt(created_at),
            _fmt(created_at),
        ),
    )
    batch_id = int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    db.execute(
        """
        INSERT INTO conversion_dispatch_log (
            automation_key, batch_id, external_userid, dispatch_status, dispatch_channel, dispatch_payload_json,
            dispatch_note, dispatched_at, acked_at, created_at, updated_at
        )
        VALUES ('signup_conversion_v1', ?, ?, ?, 'text_message', '{}', 'seed dispatch', ?, '', ?, ?)
        """,
        (
            batch_id,
            external_userid,
            dispatch_status,
            _fmt(created_at),
            _fmt(created_at),
            _fmt(created_at),
        ),
    )


def _seed_class_status_sync_failure(db, *, external_userid: str, owner_userid: str, now: datetime) -> None:
    db.execute(
        """
        INSERT INTO class_user_status_current (
            external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot, mobile_snapshot,
            set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at, updated_at
        )
        VALUES (?, 'active', '报名中', '客户', ?, '', ?, ?, 'failed', 'wecom sync failed', '{}', ?, ?)
        """,
        (
            external_userid,
            owner_userid,
            owner_userid,
            _fmt(now),
            _fmt(now),
            _fmt(now),
        ),
    )


def _seed_reply_draft_candidate_scenario(app) -> str:
    now = datetime.now().replace(microsecond=0)
    external_userid = "ext-pulse-1"
    with app.app_context():
        db = get_db()
        _seed_customer_base(
            db,
            person_id=1,
            external_userid=external_userid,
            customer_name="推进客户一",
            owner_userid="owner-a",
            mobile="13800138000",
            now=now,
        )
        _seed_marketing_state(
            db,
            person_id=1,
            external_userid=external_userid,
            now=now,
            last_message_at=now - timedelta(minutes=3),
            entered_at=now - timedelta(days=1),
            updated_at=now - timedelta(minutes=1),
            followup_segment="normal",
        )
        _seed_value_segment(db, external_userid=external_userid, segment="top", score=4, now=now - timedelta(minutes=2))
        _seed_tag(db, external_userid=external_userid, owner_userid="owner-a", tag_id="tag-1", tag_name="高意向", created_at=now - timedelta(minutes=2))
        _seed_message(
            db,
            msgid="pulse-msg-1",
            seq=1,
            external_userid=external_userid,
            owner_userid="owner-a",
            sender=external_userid,
            receiver="owner-a",
            content="最近想了解报价",
            send_time=now - timedelta(minutes=6),
        )
        _seed_message(
            db,
            msgid="pulse-msg-2",
            seq=2,
            external_userid=external_userid,
            owner_userid="owner-a",
            sender="owner-a",
            receiver=external_userid,
            content="收到，我先给你整理方案",
            send_time=now - timedelta(minutes=4),
        )
        _seed_reply_queue(
            db,
            external_userid=external_userid,
            owner_userid="owner-a",
            last_inbound_at=now - timedelta(minutes=6),
            not_before=now,
            summary="客户最近在问价格",
        )
        _seed_ai_output(
            db,
            external_userid=external_userid,
            owner_userid="owner-a",
            now=now - timedelta(minutes=1),
            draft_reply="您好，我先把当前方案和报价范围发你确认。",
            reason="客户刚问价格，适合先给报价口径",
        )
        db.commit()
    return external_userid


def _seed_reply_candidate_without_legacy_ai(app, *, external_userid: str = "ext-pulse-ai-1") -> str:
    now = datetime.now().replace(microsecond=0)
    with app.app_context():
        db = get_db()
        _seed_customer_base(
            db,
            person_id=11,
            external_userid=external_userid,
            customer_name="AI 推荐客户",
            owner_userid="owner-ai",
            mobile="13800138111",
            now=now,
        )
        _seed_marketing_state(
            db,
            person_id=11,
            external_userid=external_userid,
            now=now,
            last_message_at=now - timedelta(minutes=4),
            entered_at=now - timedelta(days=1),
            updated_at=now - timedelta(minutes=2),
            followup_segment="normal",
        )
        _seed_value_segment(db, external_userid=external_userid, segment="top", score=5, now=now - timedelta(minutes=2))
        _seed_tag(
            db,
            external_userid=external_userid,
            owner_userid="owner-ai",
            tag_id="tag-ai-1",
            tag_name="高意向",
            created_at=now - timedelta(minutes=3),
        )
        _seed_message(
            db,
            msgid="ai-msg-1",
            seq=101,
            external_userid=external_userid,
            owner_userid="owner-ai",
            sender=external_userid,
            receiver="owner-ai",
            content="课程大概怎么收费，能先给我一个范围吗？",
            send_time=now - timedelta(minutes=8),
        )
        _seed_message(
            db,
            msgid="ai-msg-2",
            seq=102,
            external_userid=external_userid,
            owner_userid="owner-ai",
            sender="owner-ai",
            receiver=external_userid,
            content="我先看下你的情况。",
            send_time=now - timedelta(minutes=6),
        )
        _seed_reply_queue(
            db,
            external_userid=external_userid,
            owner_userid="owner-ai",
            last_inbound_at=now - timedelta(minutes=8),
            not_before=now - timedelta(minutes=1),
            summary="客户在追问价格范围",
        )
        db.commit()
    return external_userid


def _seed_stalled_followup_scenario(app) -> str:
    now = datetime.now().replace(microsecond=0)
    external_userid = "ext-pulse-2"
    with app.app_context():
        db = get_db()
        _seed_customer_base(
            db,
            person_id=2,
            external_userid=external_userid,
            customer_name="停滞客户二",
            owner_userid="owner-b",
            mobile="13800138001",
            now=now,
        )
        _seed_marketing_state(
            db,
            person_id=2,
            external_userid=external_userid,
            now=now,
            last_message_at=now - timedelta(days=8),
            entered_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=9),
            followup_segment="normal",
        )
        _seed_value_segment(db, external_userid=external_userid, segment="top", score=5, now=now - timedelta(days=9))
        _seed_message(
            db,
            msgid="stalled-msg-1",
            seq=11,
            external_userid=external_userid,
            owner_userid="owner-b",
            sender=external_userid,
            receiver="owner-b",
            content="我先看一下课程安排",
            send_time=now - timedelta(days=8),
        )
        db.commit()
    return external_userid


def _seed_manual_intervention_scenario(app) -> str:
    now = datetime.now().replace(microsecond=0)
    external_userid = "ext-pulse-3"
    with app.app_context():
        db = get_db()
        _seed_customer_base(
            db,
            person_id=3,
            external_userid=external_userid,
            customer_name="风险客户三",
            owner_userid="owner-b",
            mobile="13800138002",
            now=now,
            first_owner_userid="owner-a",
            last_owner_userid="owner-b",
            binding_updated_at=_fmt(now - timedelta(days=1)),
        )
        _seed_marketing_state(
            db,
            person_id=3,
            external_userid=external_userid,
            now=now,
            main_stage="pool",
            sub_stage="active_normal",
            last_message_at=now - timedelta(days=2),
            entered_at=now - timedelta(days=4),
            updated_at=now - timedelta(days=2),
            followup_segment="normal",
        )
        _seed_value_segment(db, external_userid=external_userid, segment="normal", score=2, now=now - timedelta(days=2))
        _seed_message(
            db,
            msgid="risk-msg-1",
            seq=21,
            external_userid=external_userid,
            owner_userid="owner-b",
            sender=external_userid,
            receiver="owner-b",
            content="这次服务有问题，我要投诉并考虑退款",
            send_time=now - timedelta(hours=5),
        )
        _seed_questionnaire_with_apply_failure(
            db,
            external_userid=external_userid,
            owner_userid="owner-b",
            questionnaire_id=103,
            submitted_at=now - timedelta(days=1),
            error_message="apply crm failed",
        )
        _seed_dispatch_log(
            db,
            batch_key="batch-risk-1",
            external_userid=external_userid,
            created_at=now - timedelta(days=2),
            dispatch_status="pending",
        )
        _seed_class_status_sync_failure(db, external_userid=external_userid, owner_userid="owner-b", now=now - timedelta(days=1))
        db.commit()
    return external_userid


def test_customer_pulse_page_shows_placeholder_when_flag_disabled(client):
    response = client.get("/admin/customer-pulse")
    html = response.get_data(as_text=True)

    assert response.status_code == 410
    assert "模块已下线" in html
    assert "第一阶段保留 自动化运营、客户、问卷、配置、API 文档" in html


def test_customer_pulse_entry_appears_in_admin_home_when_flag_enabled(app, client):
    app.config["ai_customer_pulse"] = True

    response = client.get("/admin")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion")


def test_customer_pulse_flag_policy_supports_tenant_and_role_rollout(app, client):
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="sales-a", role="sales", display_name="租户A销售")
        _seed_owner_role(db, userid="sales-b", role="sales", display_name="租户B销售")
        _seed_owner_role(db, userid="ops-b", role="ops", display_name="租户B运营")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            "tenant-alpha": {
                "owner_userids": ["sales-a"],
                "member_userids": ["sales-a", "ops-a"],
                "viewer_roles": ["sales", "ops", "admin"],
                "operator_roles": ["sales", "ops", "admin"],
                "internal_roles": ["ops", "admin"],
            },
            "tenant-beta": {
                "owner_userids": ["sales-b"],
                "member_userids": ["sales-b", "ops-b"],
                "viewer_roles": ["sales", "ops", "admin"],
                "operator_roles": ["sales", "ops", "admin"],
                "internal_roles": ["ops", "admin"],
            },
        },
    )
    _set_customer_pulse_flag_policy(
        app,
        {
            "default_enabled": False,
            "tenants": {
                "tenant-alpha": {"enabled": True, "roles": {"sales": True, "ops": True}},
                "tenant-beta": {"enabled": True, "roles": {"sales": False, "ops": True}},
            },
        },
    )

    alpha_api = client.get(
        "/api/admin/customer-pulse",
        headers=_request_scoped_headers(tenant_key="tenant-alpha", admin_userid="sales-a", admin_role="sales"),
    )
    beta_sales_api = client.get(
        "/api/admin/customer-pulse",
        headers=_request_scoped_headers(tenant_key="tenant-beta", admin_userid="sales-b", admin_role="sales"),
    )
    beta_ops_api = client.get(
        "/api/admin/customer-pulse",
        headers=_request_scoped_headers(tenant_key="tenant-beta", admin_userid="ops-b", admin_role="ops"),
    )

    assert alpha_api.status_code == 200
    assert beta_ops_api.status_code == 200
    assert beta_sales_api.status_code == 403
    assert beta_sales_api.get_json()["code"] == "feature_disabled"


def test_customer_pulse_rollout_whitelist_summary_requires_default_disabled_and_enabled_tenants(app):
    app.config["ai_customer_pulse"] = True
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            "tenant-alpha": {"owner_userids": ["sales-a"], "member_userids": ["sales-a", "ops-a"]},
            "tenant-beta": {"owner_userids": ["sales-b"], "member_userids": ["sales-b", "ops-b"]},
        },
    )
    _set_customer_pulse_flag_policy(
        app,
        {
            "default_enabled": False,
            "tenants": {
                "tenant-alpha": {"enabled": True},
                "tenant-beta": {"enabled": False},
            },
        },
    )

    with app.app_context():
        summary = customer_pulse_rollout_whitelist_summary()

    assert summary["global_enabled"] is True
    assert summary["default_enabled"] is False
    assert summary["enabled_tenants"] == ["tenant-alpha"]
    assert summary["disabled_tenants"] == ["tenant-beta"]
    assert summary["whitelist_ready"] is True


def test_customer_pulse_refresh_execute_and_feedback_flow(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    action_token = _admin_action_token(client)
    _force_sync_customer_pulse(client, [external_userid])

    inbox_response = client.get("/api/admin/customer-pulse")
    inbox_payload = inbox_response.get_json()

    assert inbox_response.status_code == 200
    assert inbox_payload["ok"] is True
    assert inbox_payload["inbox"]["enabled"] is True
    assert inbox_payload["inbox"]["counts"]["open"] == 1
    assert inbox_payload["inbox"]["filters"]["scope"] == "all"
    assert inbox_payload["inbox"]["matched_count"] == 1

    card = inbox_payload["inbox"]["cards"][0]
    assert card["suggested_action_type"] == "generate_reply_draft"
    assert card["customer_name"] == "推进客户一"
    assert card["priority_score"] >= 70
    assert any(flag["key"] == "unanswered_question" for flag in card["risk_flags"])
    assert any(flag["key"] == "high_intent_stage" for flag in card["opportunity_flags"])
    assert card["draft_editor_available"] is True
    assert card["owner_display_name"] == "owner-a"
    assert card["latest_event"]["detail"]

    filtered_response = client.get(
        "/api/admin/customer-pulse",
        query_string={"search": "推进客户一", "high_priority_only": "1"},
    )
    filtered_payload = filtered_response.get_json()

    assert filtered_response.status_code == 200
    assert filtered_payload["inbox"]["matched_count"] == 1
    assert filtered_payload["inbox"]["filters"]["high_priority_only"] is True
    assert filtered_payload["inbox"]["cards"][0]["customer_name"] == "推进客户一"

    preview_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        json={"action_type": "generate_reply_draft"},
    )
    preview_payload = preview_response.get_json()

    assert preview_response.status_code == 200
    assert preview_payload["ok"] is True
    assert preview_payload["preview"]["preview"]["auto_send"] is False
    assert "报价范围" in preview_payload["preview"]["preview"]["draft_message"]

    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": action_token,
            "action_type": "generate_reply_draft",
            "operator": "pulse-admin",
        },
    )
    execute_payload = execute_response.get_json()

    assert execute_response.status_code == 200
    assert execute_payload["ok"] is True
    assert execute_payload["card"]["card_status"] == "draft_ready"
    assert execute_payload["result"]["auto_send"] is False
    assert "报价范围" in execute_payload["result"]["draft_message"]

    feedback_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/feedback",
        json={
            "admin_action_token": action_token,
            "feedback_type": "complete",
            "operator": "pulse-admin",
        },
    )
    feedback_payload = feedback_response.get_json()

    assert feedback_response.status_code == 200
    assert feedback_payload["ok"] is True
    assert feedback_payload["card"]["card_status"] == "completed"

    with app.app_context():
        db = get_db()
        execution_count = db.execute("SELECT COUNT(*) AS total FROM customer_pulse_execution_logs").fetchone()["total"]
        feedback_count = db.execute("SELECT COUNT(*) AS total FROM customer_pulse_feedback_logs").fetchone()["total"]

    assert int(execution_count) == 1
    assert int(feedback_count) == 1


def test_customer_pulse_reply_draft_execution_writes_draft_timeline_and_supports_undo(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    action_token = _admin_action_token(client)

    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": action_token,
            "action_type": "generate_reply_draft",
            "operator": "pulse-admin",
            "draft_message": "这是 AI 草稿，请人工确认后发送。",
        },
    )
    execute_payload = execute_response.get_json()

    assert execute_response.status_code == 200
    assert execute_payload["ok"] is True
    assert execute_payload["card"]["card_status"] == "draft_ready"
    assert execute_payload["result"]["draft_message"] == "这是 AI 草稿，请人工确认后发送。"
    assert execute_payload["execution"]["undo_available"] is True
    assert execute_payload["execution"]["outbound_task_id"] > 0
    execution_id = int(execute_payload["execution"]["id"])
    outbound_task_id = int(execute_payload["execution"]["outbound_task_id"])

    with app.app_context():
        db = get_db()
        outbound_row = db.execute(
            "SELECT status, request_payload, response_payload FROM outbound_tasks WHERE id = ?",
            (outbound_task_id,),
        ).fetchone()
        execution_row = db.execute(
            """
            SELECT execution_status, idempotency_key, activity_log_id, outbound_task_id, undo_status
            FROM customer_pulse_execution_logs
            WHERE id = ?
            """,
            (execution_id,),
        ).fetchone()
        activity_rows = db.execute(
            """
            SELECT activity_type, activity_status, title
            FROM customer_pulse_activity_logs
            WHERE external_userid = ?
            ORDER BY id ASC
            """,
            (external_userid,),
        ).fetchall()

    saved_request_payload = json.loads(outbound_row["request_payload"])
    assert outbound_row["status"] == "draft"
    assert saved_request_payload["external_userid"] == [external_userid]
    assert saved_request_payload["text"]["content"] == "这是 AI 草稿，请人工确认后发送。"
    assert execution_row["execution_status"] == "confirmed"
    assert execution_row["idempotency_key"]
    assert int(execution_row["outbound_task_id"]) == outbound_task_id
    assert int(execution_row["activity_log_id"]) > 0
    assert execution_row["undo_status"] == "available"
    assert [(row["activity_type"], row["activity_status"]) for row in activity_rows] == [("reply_draft", "draft_ready")]

    timeline_response = client.get(f"/api/customers/{external_userid}/timeline?event_type=customer_pulse_activity")
    timeline_payload = timeline_response.get_json()

    assert timeline_response.status_code == 200
    assert timeline_payload["ok"] is True
    assert timeline_payload["timeline"]["count"] == 1
    assert timeline_payload["timeline"]["items"][0]["title"] == "已保存 AI 回复草稿"

    undo_response = client.post(
        f"/api/admin/customer-pulse/executions/{execution_id}/undo",
        json={
            "admin_action_token": action_token,
            "operator": "pulse-admin",
        },
    )
    undo_payload = undo_response.get_json()

    assert undo_response.status_code == 200
    assert undo_payload["ok"] is True
    assert undo_payload["card"]["card_status"] == "open"
    assert undo_payload["execution"]["undo_status"] == "undone"

    with app.app_context():
        db = get_db()
        cancelled_task = db.execute(
            "SELECT status, response_payload FROM outbound_tasks WHERE id = ?",
            (outbound_task_id,),
        ).fetchone()
        activity_rows = db.execute(
            """
            SELECT activity_type, activity_status, title
            FROM customer_pulse_activity_logs
            WHERE external_userid = ?
            ORDER BY id ASC
            """,
            (external_userid,),
        ).fetchall()

    cancelled_response_payload = json.loads(cancelled_task["response_payload"])
    assert cancelled_task["status"] == "cancelled"
    assert cancelled_response_payload["cancel_source"] == "customer_pulse_undo"
    assert [(row["activity_type"], row["activity_status"]) for row in activity_rows] == [
        ("reply_draft", "undone"),
        ("action_undo", "completed"),
    ]


def test_customer_pulse_followup_task_execution_is_idempotent_and_reminder_is_undoable(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_stalled_followup_scenario(app)
    action_token = _admin_action_token(client)

    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    execute_payload = {
        "admin_action_token": action_token,
        "action_type": "create_followup_task",
        "operator": "pulse-admin",
        "task_title": "今天回访停滞客户",
        "due_at": "2026-04-12 10:30:00",
    }
    first_response = client.post(f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute", json=execute_payload)
    second_response = client.post(f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute", json=execute_payload)
    first_payload = first_response.get_json()
    second_payload = second_response.get_json()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_payload["card"]["card_status"] == "completed"
    assert second_payload["result"]["deduplicated"] is True
    assert second_payload["execution"]["id"] == first_payload["execution"]["id"]

    with app.app_context():
        db = get_db()
        followup_execution_count = int(
            db.execute(
                """
                SELECT COUNT(*) AS total
                FROM customer_pulse_execution_logs
                WHERE card_id = ? AND action_type = 'create_followup_task'
                """,
                (card["id"],),
            ).fetchone()["total"]
        )
        followup_activity_count = int(
            db.execute(
                """
                SELECT COUNT(*) AS total
                FROM customer_pulse_activity_logs
                WHERE card_id = ? AND activity_type = 'followup_task'
                """,
                (card["id"],),
            ).fetchone()["total"]
        )

    assert followup_execution_count == 1
    assert followup_activity_count == 1

    reminder_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": action_token,
            "action_type": "set_followup_reminder",
            "operator": "pulse-admin",
            "due_at": "2026-04-13 09:00:00",
        },
    )
    reminder_payload = reminder_response.get_json()

    assert reminder_response.status_code == 200
    assert reminder_payload["card"]["card_status"] == "snoozed"
    assert reminder_payload["execution"]["undo_available"] is True

    undo_response = client.post(
        f"/api/admin/customer-pulse/executions/{reminder_payload['execution']['id']}/undo",
        json={
            "admin_action_token": action_token,
            "operator": "pulse-admin",
        },
    )
    undo_payload = undo_response.get_json()

    assert undo_response.status_code == 200
    assert undo_payload["card"]["card_status"] == "completed"
    assert undo_payload["execution"]["undo_status"] == "undone"

    with app.app_context():
        db = get_db()
        reminder_rows = db.execute(
            """
            SELECT activity_type, activity_status
            FROM customer_pulse_activity_logs
            WHERE card_id = ? AND activity_type IN ('followup_reminder', 'action_undo')
            ORDER BY id ASC
            """,
            (card["id"],),
        ).fetchall()

    assert [(row["activity_type"], row["activity_status"]) for row in reminder_rows] == [
        ("followup_reminder", "undone"),
        ("action_undo", "completed"),
    ]


def test_customer_pulse_segment_and_tag_execution_support_retry_and_undo(app, client, monkeypatch):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_stalled_followup_scenario(app)

    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    stage_calls: list[str] = []

    def flaky_set_manual_followup_segment(*, followup_segment, **kwargs):
        stage_calls.append(str(followup_segment))
        if len(stage_calls) == 1:
            raise RuntimeError("temporary stage error")
        return {
            "external_userid": kwargs["external_userid"],
            "followup_segment": followup_segment,
            "marketing_state": {"stage_key": f"pool/active_{followup_segment}"},
            "operator": kwargs["operator"],
            "source": kwargs["source"],
        }

    monkeypatch.setattr(
        "wecom_ability_service.domains.customer_pulse.service.set_manual_followup_segment",
        flaky_set_manual_followup_segment,
    )

    with app.app_context():
        with pytest.raises(RuntimeError):
            execute_customer_pulse_card_action(
                int(card["id"]),
                action_type="update_followup_segment",
                operator="pulse-admin",
                extra_payload={"followup_segment": "focus"},
                tenant_context=_legacy_tenant_context(operator="pulse-admin"),
            )

        success_payload = execute_customer_pulse_card_action(
            int(card["id"]),
            action_type="update_followup_segment",
            operator="pulse-admin",
            extra_payload={"followup_segment": "focus"},
            tenant_context=_legacy_tenant_context(operator="pulse-admin"),
        )
        db = get_db()
        stage_logs = db.execute(
            """
            SELECT execution_status, idempotency_key
            FROM customer_pulse_execution_logs
            WHERE card_id = ? AND action_type = 'update_followup_segment'
            ORDER BY id ASC
            """,
            (card["id"],),
        ).fetchall()

    assert success_payload["card"]["card_status"] == "completed"
    assert success_payload["result"]["safe_field_update_review_status"] == "human_confirmed"
    assert [row["execution_status"] for row in stage_logs] == ["failed", "confirmed"]
    assert stage_logs[0]["idempotency_key"] == stage_logs[1]["idempotency_key"]

    with app.app_context():
        db = get_db()
        _seed_tag(
            db,
            external_userid=external_userid,
            owner_userid="owner-b",
            tag_id="tag-old",
            tag_name="待清理旧标签",
            created_at=datetime.now().replace(microsecond=0),
        )
        tag_candidates = [
            {
                "action_type": "update_tags",
                "action_label": "更新客户标签",
                "title": "同步标签",
                "candidate_score": 9,
                "payload": {
                    "add_tag_ids": ["tag-new"],
                    "remove_tag_ids": ["tag-old"],
                },
            }
        ]
        db.execute(
            """
            UPDATE customer_pulse_cards
            SET suggested_action_candidates_json = ?
            WHERE id = ?
            """,
            (json.dumps(tag_candidates, ensure_ascii=False), int(card["id"])),
        )
        db.commit()

    tag_calls: list[tuple[str, list[str]]] = []

    def fake_mark_customer_tags(payload):
        tag_calls.append(("mark", list(payload.get("add_tag") or [])))
        return {"ok": True}

    def fake_unmark_customer_tags(payload):
        tag_calls.append(("unmark", list(payload.get("remove_tag") or [])))
        return {"ok": True}

    monkeypatch.setattr("wecom_ability_service.domains.customer_pulse.service.mark_customer_tags", fake_mark_customer_tags)
    monkeypatch.setattr("wecom_ability_service.domains.customer_pulse.service.unmark_customer_tags", fake_unmark_customer_tags)

    with app.app_context():
        tag_payload = execute_customer_pulse_card_action(
            int(card["id"]),
            action_type="update_tags",
            operator="pulse-admin",
            extra_payload={"add_tag_ids": ["tag-new"], "remove_tag_ids": ["tag-old"]},
            tenant_context=_legacy_tenant_context(operator="pulse-admin"),
        )
        undo_payload = undo_customer_pulse_card_action_execution(
            int(tag_payload["execution"]["id"]),
            operator="pulse-admin",
            tenant_context=_legacy_tenant_context(operator="pulse-admin"),
        )

    assert tag_payload["card"]["card_status"] == "completed"
    assert tag_payload["result"]["applied_add_tag_ids"] == ["tag-new"]
    assert tag_payload["result"]["applied_remove_tag_ids"] == ["tag-old"]
    assert undo_payload["card"]["card_status"] == "completed"
    assert undo_payload["execution"]["undo_status"] == "undone"
    assert tag_calls == [
        ("mark", ["tag-new"]),
        ("unmark", ["tag-old"]),
        ("unmark", ["tag-new"]),
        ("mark", ["tag-old"]),
    ]


def test_customer_pulse_rule_scoring_covers_three_realistic_scenarios(app, client):
    app.config["ai_customer_pulse"] = True
    scenario_one = _seed_reply_draft_candidate_scenario(app)
    scenario_two = _seed_stalled_followup_scenario(app)
    scenario_three = _seed_manual_intervention_scenario(app)

    refresh_response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={
            "external_userids": [scenario_one, scenario_two, scenario_three],
            "force_sync": True,
            "operator": "internal-audit",
        },
    )
    payload = refresh_response.get_json()

    assert refresh_response.status_code == 200
    assert payload["ok"] is True
    assert payload["result"]["processed_count"] == 3

    inbox_payload = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()["inbox"]
    card_by_external = {item["external_userid"]: item for item in inbox_payload["cards"]}

    reply_card = card_by_external[scenario_one]
    assert reply_card["priority_score"] >= 70
    assert reply_card["suggested_action_candidates"][0]["action_type"] == "generate_reply_draft"
    assert any(flag["key"] == "unanswered_question" for flag in reply_card["risk_flags"])

    stalled_card = card_by_external[scenario_two]
    assert stalled_card["priority_score"] >= 55
    assert any(flag["key"] == "stage_stalled" for flag in stalled_card["risk_flags"])
    assert any(flag["key"] == "missing_followup_time" for flag in stalled_card["risk_flags"])
    assert {"update_followup_segment", "set_followup_reminder", "create_followup_task"}.issuperset(
        {item["action_type"] for item in stalled_card["suggested_action_candidates"]}
    )

    risk_card = card_by_external[scenario_three]
    assert risk_card["priority_score"] >= 60
    assert risk_card["suggested_action_candidates"][0]["action_type"] == "create_followup_task"
    assert any(flag["key"] == "negative_sentiment" for flag in risk_card["risk_flags"])
    assert any(flag["key"] == "service_exception" for flag in risk_card["risk_flags"])
    assert any(flag["key"] == "owner_changed_recently" for flag in risk_card["risk_flags"])


def test_customer_pulse_internal_api_queue_and_force_sync_are_idempotent(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)

    enqueue_response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={
            "external_userid": external_userid,
            "delay_seconds": 0,
            "operator": "internal-queue",
            "trigger_source": "unit_test",
        },
    )
    enqueue_payload = enqueue_response.get_json()

    assert enqueue_response.status_code == 200
    assert enqueue_payload["ok"] is True
    assert enqueue_payload["jobs"][0]["scheduled"] is True

    run_due_response = client.post(
        "/api/internal/customer-pulse/run-due",
        headers={"Authorization": "Bearer internal-token"},
        json={"limit": 10, "rescan_limit": 10, "operator": "internal-cron"},
    )
    run_due_payload = run_due_response.get_json()

    assert run_due_response.status_code == 200
    assert run_due_payload["ok"] is True
    assert run_due_payload["result"]["queue"]["success_count"] >= 1

    first_sync = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={
            "external_userid": external_userid,
            "force_sync": True,
            "operator": "force-sync-1",
        },
    )
    second_sync = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={
            "external_userid": external_userid,
            "force_sync": True,
            "operator": "force-sync-2",
        },
    )

    assert first_sync.status_code == 200
    assert second_sync.status_code == 200

    detail_response = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    )
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    assert detail_payload["ok"] is True
    assert detail_payload["customer"]["external_userid"] == external_userid
    assert detail_payload["card"]["priority_score"] >= 70
    assert detail_payload["latest_snapshot"]["priority_score"] >= 70
    assert any(item["signal_type"] == "unanswered_question" for item in detail_payload["signals"])

    with app.app_context():
        db = get_db()
        snapshot_count = int(
            db.execute(
                "SELECT COUNT(*) AS total FROM customer_pulse_snapshots WHERE external_userid = ?",
                (external_userid,),
            ).fetchone()["total"]
        )
        card_count = int(
            db.execute(
                "SELECT COUNT(*) AS total FROM customer_pulse_cards WHERE external_userid = ?",
                (external_userid,),
            ).fetchone()["total"]
        )
        pending_jobs = int(
            db.execute(
                "SELECT COUNT(*) AS total FROM user_ops_deferred_jobs WHERE job_type = 'customer_pulse_recompute' AND external_userid = ? AND status = 'pending'",
                (external_userid,),
            ).fetchone()["total"]
        )

    assert snapshot_count == 1
    assert card_count == 1
    assert pending_jobs == 0


def test_customer_pulse_ai_recommendation_accepts_structured_output_and_persists_trace(app, client, monkeypatch):
    json_module = json
    app.config["ai_customer_pulse"] = True
    app.config["DEEPSEEK_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "dsk-test-customer-pulse"
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-accepted")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE archived_messages
            SET content = ?
            WHERE msgid = 'ai-msg-1'
            """,
            ("课程怎么收费，手机号 13800138111 可以直接联系我吗？",),
        )
        db.commit()

    def _fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer dsk-test-customer-pulse"
        assert json["response_format"] == {"type": "json_object"}

        class _FakeResponse:
            status_code = 200
            headers = {"x-request-id": "pulse-ai-req-001"}

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json_module.dumps(
                                    {
                                        "summary": "客户刚刚追问价格范围，适合先给一版克制草稿。",
                                        "actionType": "generate_reply_draft",
                                        "actionTitle": "先回应价格范围问题",
                                        "whyNow": "最近 10 分钟内客户继续追问价格，当前等待越久越容易流失。",
                                        "evidenceRefs": [
                                            {"sourceType": "archived_messages", "sourceId": "ai-msg-1"},
                                            {"sourceType": "automation_reply_monitor_queue", "sourceId": "1"},
                                        ],
                                        "draftText": "可以，我先把适合你的方案和价格区间整理成一版草稿给你确认。",
                                        "confidence": 0.91,
                                        "handoffSummary": "客户在最近 10 分钟内连续追问价格，建议由当前 owner 先用克制口径接住，再决定是否升级报价审批。",
                                        "safeFieldUpdates": {
                                            "followupSegment": "focus",
                                            "nextFollowupAt": "",
                                            "addTagIds": [],
                                            "removeTagIds": [],
                                        },
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }

            @property
            def text(self):
                return self.json()["choices"][0]["message"]["content"]

        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={"external_userid": external_userid, "force_sync": True, "operator": "ai-integration"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["result"]["processed_count"] == 1

    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()
    card = detail["card"]
    snapshot = detail["latest_snapshot"]

    assert card["draft_message"] == "可以，我先把适合你的方案和价格区间整理成一版草稿给你确认。"
    assert card["suggested_action_candidates"][0]["action_type"] == "generate_reply_draft"
    assert card["suggested_action_payload"]["ai_recommendation"]["confidence"] == 0.91
    assert snapshot["ai_payload"]["recommendation_status"] == "accepted"
    assert snapshot["ai_payload"]["provider"] == "deepseek"
    assert snapshot["ai_payload"]["request_id"] == "pulse-ai-req-001"
    assert snapshot["ai_payload"]["output_id"] != ""
    assert snapshot["ai_payload"]["recommendation"]["actionTitle"] == "先回应价格范围问题"
    assert snapshot["ai_payload"]["recommendation"]["handoffSummary"].startswith("客户在最近 10 分钟内连续追问价格")
    assert snapshot["ai_payload"]["guardrails"]["blocked"] is False
    assert snapshot["ai_payload"]["trace"]["tenant_context"]["tenant_key"] == "aicrm"
    assert snapshot["ai_payload"]["trace"]["actor"]["operator"] == "ai-integration"
    assert snapshot["ai_payload"]["audit_labels"] == ["ai_suggested"]
    assert card["evidence_refs"]
    assert all(set(item.keys()) == {"sourceType", "sourceId", "title", "eventTime"} for item in card["evidence_refs"])
    assert all("13800138111" not in item["title"] for item in card["evidence_refs"])

    preview = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        json={"action_type": "generate_reply_draft"},
    ).get_json()
    assert preview["ok"] is True
    assert preview["preview"]["preview"]["draft_message"] == "可以，我先把适合你的方案和价格区间整理成一版草稿给你确认。"

    evidence_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}/evidence")
    assert evidence_response.status_code == 200
    evidence_payload = evidence_response.get_json()
    assert evidence_payload["ok"] is True
    assert all("raw_payload" not in item for item in evidence_payload["evidence"])
    assert all("13800138111" not in item["title"] for item in evidence_payload["evidence"])
    assert all("13800138111" not in item["detail"] for item in evidence_payload["evidence"])

    with app.app_context():
        db = get_db()
        output_row = db.execute(
            """
            SELECT agent_code, request_id, output_type, confidence
            FROM automation_agent_output
            WHERE agent_code = 'customer_pulse_recommendation_agent'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        evidence_audit_row = db.execute(
            """
            SELECT action_type, before_json, after_json
            FROM admin_operation_logs
            WHERE target_type = 'customer_pulse_evidence' AND target_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(card["id"]),),
        ).fetchone()
        ai_success_metric = db.execute(
            """
            SELECT event_type, payload_json
            FROM customer_pulse_metric_events
            WHERE external_userid = ? AND event_type = 'ai_success'
            ORDER BY id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()

    assert output_row["agent_code"] == "customer_pulse_recommendation_agent"
    assert output_row["request_id"] == "pulse-ai-req-001"
    assert output_row["output_type"] == "next_action_suggestion"
    assert round(float(output_row["confidence"]), 2) == 0.91
    assert evidence_audit_row["action_type"] == "view_card_evidence"
    assert json.loads(evidence_audit_row["before_json"])["tenant_context"]["tenant_key"] == "aicrm"
    assert json.loads(evidence_audit_row["after_json"])["result"] == "ok"
    assert ai_success_metric["event_type"] == "ai_success"
    assert json.loads(ai_success_metric["payload_json"])["model_name"] == "deepseek-chat"


def test_customer_pulse_ai_recommendation_falls_back_when_provider_unavailable(app, client):
    app.config["ai_customer_pulse"] = True
    app.config["DEEPSEEK_ENABLED"] = False
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-fallback")

    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={"external_userid": external_userid, "force_sync": True, "operator": "ai-fallback"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()

    assert detail["latest_snapshot"]["ai_payload"]["recommendation_status"] == "fallback"
    assert detail["latest_snapshot"]["ai_payload"]["fallback_reason"] == "provider_error"
    assert "deepseek_disabled" in detail["latest_snapshot"]["ai_payload"]["error_message"]
    assert detail["card"]["suggested_action_type"] == "generate_reply_draft"
    assert detail["card"]["priority_score"] >= 70

    with app.app_context():
        db = get_db()
        fallback_metric = db.execute(
            """
            SELECT event_type, payload_json
            FROM customer_pulse_metric_events
            WHERE external_userid = ? AND event_type = 'fallback_count'
            ORDER BY id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()

    assert fallback_metric["event_type"] == "fallback_count"
    assert json.loads(fallback_metric["payload_json"])["fallback_reason"] == "provider_error"


def test_customer_pulse_ai_recommendation_falls_back_on_invalid_json_output(app, client, monkeypatch):
    app.config["ai_customer_pulse"] = True
    app.config["DEEPSEEK_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "dsk-test-invalid-json"
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-invalid-json")

    def _fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer dsk-test-invalid-json"
        assert json["response_format"] == {"type": "json_object"}

        class _FakeResponse:
            status_code = 200
            headers = {"x-request-id": "pulse-ai-req-invalid-json"}

            def json(self):
                return {"choices": [{"message": {"content": "{not valid json"}}]}

            @property
            def text(self):
                return self.json()["choices"][0]["message"]["content"]

        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)

    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={"external_userid": external_userid, "force_sync": True, "operator": "ai-invalid-json"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()

    assert detail["latest_snapshot"]["ai_payload"]["recommendation_status"] == "fallback"
    assert detail["latest_snapshot"]["ai_payload"]["fallback_reason"] == "provider_error"
    assert detail["latest_snapshot"]["ai_payload"]["error_message"] == "invalid_json_output"
    assert detail["card"]["draft_message"] != "{not valid json"


def test_customer_pulse_ai_recommendation_falls_back_on_provider_timeout(app, client, monkeypatch):
    app.config["ai_customer_pulse"] = True
    app.config["DEEPSEEK_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "dsk-test-timeout"
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-timeout")

    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("deepseek provider timeout")),
    )

    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={"external_userid": external_userid, "force_sync": True, "operator": "ai-timeout"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()

    assert detail["latest_snapshot"]["ai_payload"]["recommendation_status"] == "fallback"
    assert detail["latest_snapshot"]["ai_payload"]["fallback_reason"] == "provider_error"
    assert "deepseek provider timeout" in detail["latest_snapshot"]["ai_payload"]["error_message"]


def test_customer_pulse_ai_recommendation_degrades_on_low_confidence_and_guardrail_violation(app, client):
    app.config["ai_customer_pulse"] = True
    app.config["CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS"] = True
    app.config["CUSTOMER_PULSE_AI_PROVIDER"] = "mock"
    app.config["CUSTOMER_PULSE_AI_MOCK_RESPONSE"] = {
        "summary": "客户在询价，建议直接承诺最低价。",
        "actionType": "generate_reply_draft",
        "actionTitle": "立刻发最低价承诺",
        "whyNow": "现在就该用最低价承诺压单。",
        "evidenceRefs": [{"sourceType": "archived_messages", "sourceId": "ai-msg-1"}],
        "draftText": "我给你最低价，今天肯定保价，手机号 13800138111 直接联系我。",
        "confidence": 0.42,
        "safeFieldUpdates": {"followupSegment": "focus", "nextFollowupAt": "", "addTagIds": [], "removeTagIds": []},
    }
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-low-confidence")

    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={"external_userid": external_userid, "force_sync": True, "operator": "ai-low-confidence"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True

    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()
    ai_payload = detail["latest_snapshot"]["ai_payload"]

    assert ai_payload["recommendation_status"] == "fallback"
    assert ai_payload["fallback_reason"] == "low_confidence"
    assert "low_confidence" in ai_payload["guardrails"]["output_violations"]
    assert ai_payload["recommendation"]["draftText"] == ""
    assert detail["card"]["draft_message"] != "我给你最低价，今天肯定保价，手机号 13800138111 直接联系我。"
    assert detail["card"]["suggested_action_payload"]["draft_blocked_by_ai"] is True

    preview = client.post(
        f"/api/admin/customer-pulse/cards/{detail['card']['id']}/actions/preview",
        json={"action_type": "generate_reply_draft"},
    ).get_json()
    assert preview["ok"] is True
    assert preview["preview"]["preview"]["draft_message"] == ""
    assert preview["preview"]["preview"]["draft_blocked_by_ai"] is True

    blocked_execute = client.post(
        f"/api/admin/customer-pulse/cards/{detail['card']['id']}/actions/execute",
        json={
            "admin_action_token": _admin_action_token(client),
            "action_type": "generate_reply_draft",
            "operator": "ai-low-confidence",
        },
    )
    assert blocked_execute.status_code == 400


def test_customer_pulse_ai_recommendation_does_not_leak_evidence_for_viewer_without_evidence_permission(app, client, monkeypatch):
    json_module = json
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    app.config["DEEPSEEK_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "dsk-test-evidence-guard"
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-evidence-guard")
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-ai", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": ["owner-ai"],
                "member_userids": ["owner-ai", "ops-1"],
                "viewer_roles": ["sales"],
                "operator_roles": ["ops"],
                "permissions_by_role": {
                    "sales": ["page_visible", "inbox_view", "widget_view"],
                },
            }
        },
    )

    def _fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        assert json["response_format"] == {"type": "json_object"}

        class _FakeResponse:
            status_code = 200
            headers = {"x-request-id": "pulse-ai-req-evidence-guard"}

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json_module.dumps(
                                    {
                                        "summary": "客户连续询问价格范围，建议先发一版可编辑回复草稿。",
                                        "actionType": "generate_reply_draft",
                                        "actionTitle": "先接住价格问题",
                                        "whyNow": "最近 10 分钟内客户仍在追问价格，等待时间越长越容易流失。",
                                        "evidenceRefs": [
                                            {"sourceType": "archived_messages", "sourceId": "ai-msg-1"},
                                            {"sourceType": "automation_reply_monitor_queue", "sourceId": "1"},
                                        ],
                                        "draftText": "我先把适合你的方案和价格区间整理成一版给你确认。",
                                        "confidence": 0.9,
                                        "handoffSummary": "当前 owner 可以先用安全口径回复，再决定是否升级报价审批。",
                                        "safeFieldUpdates": {
                                            "followupSegment": "focus",
                                            "nextFollowupAt": "",
                                            "addTagIds": [],
                                            "removeTagIds": [],
                                        },
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }

            @property
            def text(self):
                return self.json()["choices"][0]["message"]["content"]

        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")
    sales_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-ai", admin_role="sales")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)
    card = _pulse_card_by_external_userid(client, external_userid, headers=sales_headers)

    detail_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}", headers=sales_headers)
    evidence_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}/evidence", headers=sales_headers)

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["card"]["permissions"]["evidence_view"] is False
    assert detail_payload["card"]["evidence"] == []
    assert detail_payload["card"]["evidence_refs"]
    assert all(set(item.keys()) == {"sourceType", "sourceId", "title", "eventTime"} for item in detail_payload["card"]["evidence_refs"])
    assert all("13800138111" not in item["title"] for item in detail_payload["card"]["evidence_refs"])
    assert evidence_response.status_code == 403
    assert evidence_response.get_json()["code"] == "evidence_view_forbidden"


def test_customer_pulse_ai_recommendation_keeps_outputs_isolated_across_tenants(app, client, monkeypatch):
    json_module = json
    tenant_a = "tenant-acme"
    tenant_b = "tenant-beta"
    app.config["ai_customer_pulse"] = True
    app.config["DEEPSEEK_ENABLED"] = True
    app.config["DEEPSEEK_API_KEY"] = "dsk-test-dual-tenant"
    external_userid_a = _seed_reply_draft_candidate_scenario(app)
    external_userid_b = _seed_stalled_followup_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-a", role="ops")
        _seed_owner_role(db, userid="ops-b", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_a: {"owner_userids": ["owner-a"], "member_userids": ["owner-a", "ops-a"]},
            tenant_b: {"owner_userids": ["owner-b"], "member_userids": ["owner-b", "ops-b"]},
        },
    )

    def _fake_post(url, headers=None, json=None, timeout=None):
        payload = json_module.loads(json["messages"][1]["content"])
        external_userid = payload["customer"]["externalUserId"]
        if external_userid == external_userid_a:
            body = {
                "summary": "tenant_a 客户适合先发回复草稿。",
                "actionType": "generate_reply_draft",
                "actionTitle": "先回应价格问题",
                "whyNow": "tenant_a 客户最近刚追问报价。",
                "evidenceRefs": [{"sourceType": "archived_messages", "sourceId": "pulse-msg-1"}],
                "draftText": "我先把适合你的方案和价格区间整理成草稿给你确认。",
                "confidence": 0.92,
                "handoffSummary": "tenant_a 继续由当前 owner 跟进。",
                "safeFieldUpdates": {"followupSegment": "focus", "nextFollowupAt": "", "addTagIds": [], "removeTagIds": []},
            }
            request_id = "pulse-ai-req-tenant-a"
        else:
            body = {
                "summary": "tenant_b 客户更适合创建跟进任务。",
                "actionType": "create_followup_task",
                "actionTitle": "补一个停滞跟进任务",
                "whyNow": "tenant_b 客户阶段停滞已超过一周。",
                "evidenceRefs": [{"sourceType": "archived_messages", "sourceId": "stalled-msg-1"}],
                "draftText": "",
                "confidence": 0.88,
                "handoffSummary": "tenant_b 需要经理关注阶段停滞风险。",
                "safeFieldUpdates": {"followupSegment": "", "nextFollowupAt": "", "addTagIds": [], "removeTagIds": []},
            }
            request_id = "pulse-ai-req-tenant-b"

        class _FakeResponse:
            status_code = 200
            headers = {"x-request-id": request_id}

            def json(self):
                return {"choices": [{"message": {"content": json_module.dumps(body, ensure_ascii=False)}}]}

            @property
            def text(self):
                return self.json()["choices"][0]["message"]["content"]

        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)
    ops_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="ops-a", admin_role="ops")
    ops_headers_b = _request_scoped_headers(tenant_key=tenant_b, admin_userid="ops-b", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid_a], headers=ops_headers_a)
    _force_sync_customer_pulse(client, [external_userid_b], headers=ops_headers_b)

    detail_a = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid_a}",
        headers={"Authorization": "Bearer internal-token", **ops_headers_a},
    ).get_json()
    detail_b = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid_b}",
        headers={"Authorization": "Bearer internal-token", **ops_headers_b},
    ).get_json()
    cross_tenant_detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid_a}",
        headers={"Authorization": "Bearer internal-token", **ops_headers_b},
    ).get_json()

    assert detail_a["latest_snapshot"]["ai_payload"]["provider"] == "deepseek"
    assert detail_a["latest_snapshot"]["ai_payload"]["request_id"] == "pulse-ai-req-tenant-a"
    assert detail_a["latest_snapshot"]["ai_payload"]["trace"]["tenant_context"]["tenant_key"] == tenant_a
    assert detail_a["latest_snapshot"]["ai_payload"]["recommendation"]["summary"] == "tenant_a 客户适合先发回复草稿。"
    assert detail_a["card"]["suggested_action_type"] == "generate_reply_draft"

    assert detail_b["latest_snapshot"]["ai_payload"]["provider"] == "deepseek"
    assert detail_b["latest_snapshot"]["ai_payload"]["request_id"] == "pulse-ai-req-tenant-b"
    assert detail_b["latest_snapshot"]["ai_payload"]["trace"]["tenant_context"]["tenant_key"] == tenant_b
    assert detail_b["latest_snapshot"]["ai_payload"]["recommendation"]["summary"] == "tenant_b 客户更适合创建跟进任务。"
    assert detail_b["card"]["suggested_action_type"] == "create_followup_task"

    assert cross_tenant_detail["ok"] is True
    assert cross_tenant_detail["has_card"] is False
    assert cross_tenant_detail["card"] is None
    assert cross_tenant_detail["latest_snapshot"] is None


def test_customer_pulse_execution_records_learning_feedback_and_writeback_metrics(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    preview = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        json={"action_type": "generate_reply_draft"},
    ).get_json()
    default_draft = preview["preview"]["preview"]["draft_message"]

    first_execute = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": _admin_action_token(client),
            "action_type": "generate_reply_draft",
            "operator": "ops-feedback",
            "draft_message": default_draft,
        },
    )
    assert first_execute.status_code == 200
    second_execute = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": _admin_action_token(client),
            "action_type": "generate_reply_draft",
            "operator": "ops-feedback",
            "draft_message": f"{default_draft} 我晚点再把细节也补给你。",
        },
    )
    assert second_execute.status_code == 200

    with app.app_context():
        db = get_db()
        feedback_rows = db.execute(
            """
            SELECT feedback_type
            FROM customer_pulse_action_feedback
            ORDER BY id DESC
            LIMIT 2
            """
        ).fetchall()
        metric_rows = db.execute(
            """
            SELECT event_type, COUNT(*) AS total_count
            FROM customer_pulse_metric_events
            GROUP BY event_type
            """
        ).fetchall()
        execution_rows = db.execute(
            """
            SELECT audit_labels_json, result_payload_json
            FROM customer_pulse_execution_logs
            WHERE action_type = 'generate_reply_draft'
            ORDER BY id DESC
            LIMIT 2
            """
        ).fetchall()

    assert [row["feedback_type"] for row in feedback_rows] == ["edited_then_sent", "adopted"]
    metric_map = {row["event_type"]: int(row["total_count"] or 0) for row in metric_rows}
    assert metric_map["draft_confirmed"] == 2
    assert metric_map["writeback_success"] == 2
    assert metric_map["action_executed"] == 2
    latest_labels = json.loads(execution_rows[0]["audit_labels_json"])
    first_labels = json.loads(execution_rows[1]["audit_labels_json"])
    latest_result = json.loads(execution_rows[0]["result_payload_json"])
    first_result = json.loads(execution_rows[1]["result_payload_json"])
    assert "human_edited" in latest_labels
    assert latest_result["draft_review_status"] == "human_edited"
    assert "human_confirmed" in first_labels
    assert first_result["draft_review_status"] == "human_confirmed"


def test_customer_pulse_feedback_api_records_misjudged_and_ignored_feedback(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_stalled_followup_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)
    token = _admin_action_token(client)

    misjudged_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/feedback",
        json={
            "admin_action_token": token,
            "feedback_type": "misjudged",
            "operator": "qa_feedback",
            "note": "这次不该优先提醒。",
        },
    )
    assert misjudged_response.status_code == 200
    assert misjudged_response.get_json()["card"]["card_status"] == "open"

    dismiss_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/feedback",
        json={
            "admin_action_token": token,
            "feedback_type": "dismiss",
            "operator": "qa_feedback",
            "note": "本轮先忽略。",
        },
    )
    assert dismiss_response.status_code == 200
    assert dismiss_response.get_json()["card"]["card_status"] == "dismissed"

    with app.app_context():
        db = get_db()
        feedback_rows = db.execute(
            """
            SELECT feedback_type
            FROM customer_pulse_action_feedback
            ORDER BY id DESC
            LIMIT 2
            """
        ).fetchall()
        ignored_count = int(
            db.execute(
                """
                SELECT COUNT(*) AS total_count
                FROM customer_pulse_metric_events
                WHERE event_type = 'card_ignored'
                """
            ).fetchone()["total_count"]
        )

    assert [row["feedback_type"] for row in feedback_rows] == ["ignored", "misjudged"]
    assert ignored_count == 1


def test_customer_pulse_inbox_exposure_and_click_metrics_are_recorded(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    inbox_response = client.get("/api/admin/customer-pulse")
    assert inbox_response.status_code == 200

    preview_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        json={
            "action_type": "generate_reply_draft",
            "track_click": True,
            "metric_source": "pytest_preview",
        },
    )
    assert preview_response.status_code == 200

    with app.app_context():
        db = get_db()
        metric_rows = db.execute(
            """
            SELECT event_type, COUNT(*) AS total_count
            FROM customer_pulse_metric_events
            GROUP BY event_type
            """
        ).fetchall()

    metric_map = {row["event_type"]: int(row["total_count"] or 0) for row in metric_rows}
    assert metric_map["card_exposed"] >= 1
    assert metric_map["card_clicked"] == 1


def test_customer_pulse_low_confidence_cards_can_be_hidden_by_setting(app, client):
    app.config["ai_customer_pulse"] = True
    app.config["CUSTOMER_PULSE_AI_PROVIDER"] = "mock"
    app.config["CUSTOMER_PULSE_AI_MOCK_RESPONSE"] = {
        "summary": "客户在询价，建议直接承诺最低价。",
        "actionType": "generate_reply_draft",
        "actionTitle": "立刻发最低价承诺",
        "whyNow": "现在就该用最低价承诺压单。",
        "evidenceRefs": [{"sourceType": "archived_messages", "sourceId": "ai-msg-1"}],
        "draftText": "我给你最低价，今天肯定保价。",
        "confidence": 0.42,
        "safeFieldUpdates": {"followupSegment": "focus", "nextFollowupAt": "", "addTagIds": [], "removeTagIds": []},
    }
    with app.app_context():
        set_settings({"CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS": "false"})
    external_userid = _seed_reply_candidate_without_legacy_ai(app, external_userid="ext-pulse-ai-hidden")

    response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token"},
        json={"external_userid": external_userid, "force_sync": True, "operator": "ai-low-confidence-hidden"},
    )
    assert response.status_code == 200

    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()
    inbox = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()["inbox"]

    assert detail["latest_snapshot"]["ai_payload"]["fallback_reason"] == "low_confidence"
    assert detail["card"] is None
    assert all(item["external_userid"] != external_userid for item in inbox["cards"])


def test_customer_pulse_runtime_settings_filter_allowed_actions(app, client):
    app.config["ai_customer_pulse"] = True
    with app.app_context():
        set_settings({"CUSTOMER_PULSE_ALLOWED_ACTION_TYPES": "generate_reply_draft"})

    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()
    card = detail["card"]

    assert detail["runtime_config"]["allowed_action_types"] == ["generate_reply_draft"]
    assert card["suggested_action_type"] == "generate_reply_draft"
    assert {item["action_type"] for item in card["supported_action_buttons"]} == {"generate_reply_draft"}

    blocked_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": _admin_action_token(client),
            "action_type": "update_tags",
            "operator": "ops-config",
        },
    )
    assert blocked_response.status_code == 400
    assert "禁用" in blocked_response.get_json()["error"]


def test_customer_pulse_high_priority_threshold_is_configurable(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_stalled_followup_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    baseline_detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()
    baseline_card = baseline_detail["card"]

    assert baseline_card["priority"] == "normal"
    assert baseline_card["priority_score"] > 35

    threshold = int(baseline_card["priority_score"]) - 5
    with app.app_context():
        set_settings({"CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD": str(threshold)})

    _force_sync_customer_pulse(client, [external_userid])
    detail = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token"},
    ).get_json()

    assert detail["runtime_config"]["high_priority_threshold"] == threshold
    assert detail["card"]["priority"] == "high"


def test_customer_pulse_card_exposes_why_now_and_evidence_refs(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])

    card = _pulse_card_by_external_userid(client, external_userid)

    assert card["why_now"]
    assert card["evidence_refs"]
    assert card["evidenceRefs"] == card["evidence_refs"]
    assert all(item["sourceType"] and item["sourceId"] for item in card["evidence_refs"])


def test_customer_pulse_customer_widget_payload_matches_inbox_card(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])

    inbox_card = _pulse_card_by_external_userid(client, external_userid)
    response = client.get(
        "/api/admin/customers/profile/pulse",
        query_string={"external_userid": external_userid},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True

    widget_card = payload["customer_pulse"]["card"]
    assert widget_card["id"] == inbox_card["id"]
    assert widget_card["why_now"] == inbox_card["why_now"]
    assert widget_card["suggested_action_type"] == inbox_card["suggested_action_type"]
    assert widget_card["evidence_refs"] == inbox_card["evidence_refs"]


def test_customer_pulse_permission_controls_block_execute_without_action_token(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    no_token_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={"action_type": "generate_reply_draft"},
    )
    assert no_token_response.status_code == 400
    assert "令牌无效" in no_token_response.get_json()["error"]

    missing_internal_token_response = client.get("/api/internal/customer-pulse/inbox")
    assert missing_internal_token_response.status_code == 401
    assert missing_internal_token_response.get_json()["error"] == "missing internal token"


def test_customer_pulse_request_scoped_mode_requires_tenant_context(app, client):
    app.config["ai_customer_pulse"] = True
    _enable_request_scoped_customer_pulse(
        app,
        tenant_key="tenant-acme",
        owner_userids=["owner-a"],
        member_userids=["owner-a", "ops-1"],
    )

    response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token"},
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["code"] == "tenant_context_required"


def test_customer_pulse_request_scoped_normal_request_exposes_tenant_context(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _enable_request_scoped_customer_pulse(
        app,
        tenant_key=tenant_key,
        owner_userids=["owner-a"],
        member_userids=["owner-a", "ops-1"],
    )
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)
    response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token", **ops_headers},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["inbox"]["tenant_context"]["tenant_key"] == tenant_key
    assert payload["inbox"]["tenant_context"]["auth_mode"] == "request_scoped"
    assert payload["inbox"]["tenant_context"]["user_id"] == "ops-1"
    assert payload["inbox"]["cards"][0]["external_userid"] == external_userid


def test_customer_pulse_request_scoped_mode_rejects_invalid_tenant(app, client):
    app.config["ai_customer_pulse"] = True
    _enable_request_scoped_customer_pulse(
        app,
        tenant_key="tenant-acme",
        owner_userids=["owner-a"],
        member_userids=["owner-a", "ops-1"],
    )

    response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={
            "Authorization": "Bearer internal-token",
            **_request_scoped_headers(tenant_key="tenant-ghost", admin_userid="ops-1", admin_role="ops"),
        },
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["code"] == "tenant_invalid"


def test_customer_pulse_request_scoped_mode_rejects_conflicting_tenant_values(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    _enable_request_scoped_customer_pulse(
        app,
        tenant_key=tenant_key,
        owner_userids=["owner-a"],
        member_userids=["owner-a", "ops-1"],
    )

    response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={
            "Authorization": "Bearer internal-token",
            **_request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops"),
        },
        query_string={"tenant_key": "tenant-other"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["code"] == "tenant_context_conflict"


def test_customer_pulse_legacy_internal_mode_request_is_explicitly_marked(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)

    _force_sync_customer_pulse(client, [external_userid])
    response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["inbox"]["tenant_context"]["auth_mode"] == "legacy_internal"
    assert payload["inbox"]["tenant_context"]["legacy_mode"] is True


def test_customer_pulse_external_request_scoped_guard_rejects_legacy_internal_mode(app, client):
    app.config["ai_customer_pulse"] = True
    app.config["CUSTOMER_PULSE_TENANT_MODE"] = "legacy_internal"
    app.config["CUSTOMER_PULSE_EXTERNAL_ENFORCE_REQUEST_SCOPED"] = True

    response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token"},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["code"] == "tenant_mode_misconfigured"
    assert "request-scoped tenant mode" in payload["error"]


def test_customer_pulse_request_scoped_sales_scope_and_cross_owner_action_denied(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid_a = _seed_reply_draft_candidate_scenario(app)
    external_userid_b = _seed_stalled_followup_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _enable_request_scoped_customer_pulse(
        app,
        tenant_key=tenant_key,
        owner_userids=["owner-a", "owner-b"],
        member_userids=["owner-a", "owner-b", "ops-1"],
    )
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")
    sales_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-a", admin_role="sales")
    _force_sync_customer_pulse(client, [external_userid_a, external_userid_b], headers=ops_headers)
    action_token = _admin_action_token(client, headers=sales_headers)

    inbox_response = client.get("/api/admin/customer-pulse", headers=sales_headers)

    assert inbox_response.status_code == 200
    inbox_payload = inbox_response.get_json()
    assert inbox_payload["ok"] is True
    assert [item["external_userid"] for item in inbox_payload["inbox"]["cards"]] == [external_userid_a]

    forbidden_owner_response = client.get(
        "/api/admin/customer-pulse",
        headers=sales_headers,
        query_string={"owner_userid": "owner-b"},
    )
    assert forbidden_owner_response.status_code == 403
    assert forbidden_owner_response.get_json()["code"] == "owner_scope_forbidden"

    card_b = _pulse_card_by_external_userid(client, external_userid_b, headers=ops_headers)
    preview_response = client.post(
        f"/api/admin/customer-pulse/cards/{card_b['id']}/actions/preview",
        headers=sales_headers,
        json={"action_type": card_b["suggested_action_type"]},
    )
    assert preview_response.status_code == 403
    assert preview_response.get_json()["code"] in {"owner_scope_forbidden", "cross_tenant_owner_scope"}

    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card_b['id']}/actions/execute",
        headers=sales_headers,
        json={
            "admin_action_token": action_token,
            "action_type": card_b["suggested_action_type"],
        },
    )
    assert execute_response.status_code == 403
    assert execute_response.get_json()["code"] in {"owner_scope_forbidden", "cross_tenant_owner_scope"}

    customer_pulse_response = client.get(
        "/api/admin/customers/profile/pulse",
        headers=sales_headers,
        query_string={"external_userid": external_userid_b},
    )
    assert customer_pulse_response.status_code == 404


def test_customer_pulse_request_scoped_rows_and_recompute_jobs_are_tenant_tagged(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _enable_request_scoped_customer_pulse(
        app,
        tenant_key=tenant_key,
        owner_userids=["owner-a"],
        member_userids=["owner-a", "ops-1"],
    )
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")

    enqueue_response = client.post(
        "/api/internal/customer-pulse/recompute",
        headers={"Authorization": "Bearer internal-token", **ops_headers},
        json={"external_userids": [external_userid], "force_sync": False, "operator": "ops-1"},
    )

    assert enqueue_response.status_code == 200
    jobs = enqueue_response.get_json()["jobs"]
    assert jobs[0]["job"]["tenant_key"] == tenant_key

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)

    with app.app_context():
        db = get_db()
        signal_rows = db.execute(
            "SELECT tenant_key, signal_key FROM customer_pulse_signal_events ORDER BY id ASC"
        ).fetchall()
        snapshot_rows = db.execute(
            "SELECT tenant_key FROM customer_pulse_snapshots ORDER BY id ASC"
        ).fetchall()
        card_rows = db.execute(
            "SELECT tenant_key, card_key FROM customer_pulse_cards ORDER BY id ASC"
        ).fetchall()
        job_rows = db.execute(
            "SELECT tenant_key FROM user_ops_deferred_jobs WHERE job_type = 'customer_pulse_recompute' ORDER BY id ASC"
        ).fetchall()

    assert signal_rows
    assert snapshot_rows
    assert card_rows
    assert job_rows
    assert all(row["tenant_key"] == tenant_key for row in signal_rows)
    assert all(row["tenant_key"] == tenant_key for row in snapshot_rows)
    assert all(row["tenant_key"] == tenant_key for row in card_rows)
    assert all(row["tenant_key"] == tenant_key for row in job_rows)
    assert all(str(row["signal_key"]).startswith(f"{tenant_key}:") for row in signal_rows)
    assert all(str(row["card_key"]).startswith(f"{tenant_key}:") for row in card_rows)


def test_customer_pulse_cross_tenant_card_detail_and_action_writeback_are_denied(app, client):
    tenant_a = "tenant-acme"
    tenant_b = "tenant-beta"
    app.config["ai_customer_pulse"] = True
    external_userid_a = _seed_reply_draft_candidate_scenario(app)
    external_userid_b = _seed_stalled_followup_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        _seed_owner_role(db, userid="ops-2", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_a: {"owner_userids": ["owner-a"], "member_userids": ["owner-a", "ops-1"]},
            tenant_b: {"owner_userids": ["owner-b"], "member_userids": ["owner-b", "ops-2"]},
        },
    )
    ops_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="ops-1", admin_role="ops")
    ops_headers_b = _request_scoped_headers(tenant_key=tenant_b, admin_userid="ops-2", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid_a], headers=ops_headers_a)
    _force_sync_customer_pulse(client, [external_userid_b], headers=ops_headers_b)

    card_a = _pulse_card_by_external_userid(client, external_userid_a, headers=ops_headers_a)
    inbox_b_response = client.get(
        "/api/internal/customer-pulse/inbox",
        headers={"Authorization": "Bearer internal-token", **ops_headers_b},
    )
    assert inbox_b_response.status_code == 200
    assert [item["external_userid"] for item in inbox_b_response.get_json()["inbox"]["cards"]] == [external_userid_b]

    action_token_b = _admin_action_token(client, headers=ops_headers_b)
    detail_response = client.get(f"/api/admin/customer-pulse/cards/{card_a['id']}", headers=ops_headers_b)
    preview_response = client.post(
        f"/api/admin/customer-pulse/cards/{card_a['id']}/actions/preview",
        headers=ops_headers_b,
        json={"action_type": card_a["suggested_action_type"]},
    )
    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card_a['id']}/actions/execute",
        headers=ops_headers_b,
        json={
            "admin_action_token": action_token_b,
            "action_type": card_a["suggested_action_type"],
        },
    )

    assert detail_response.status_code == 404
    assert preview_response.status_code == 404
    assert execute_response.status_code == 404

    with app.app_context():
        db = get_db()
        cross_tenant_execution_count = int(
            db.execute(
                """
                SELECT COUNT(*) AS total
                FROM customer_pulse_execution_logs
                WHERE tenant_key = ? AND card_id = ?
                """,
                (tenant_b, int(card_a["id"])),
            ).fetchone()["total"]
        )
    assert cross_tenant_execution_count == 0


def test_customer_pulse_stats_api_reports_metrics_and_security_counters(app, client):
    tenant_a = "tenant-acme"
    tenant_b = "tenant-beta"
    app.config["ai_customer_pulse"] = True
    external_userid_a = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-a", role="ops")
        _seed_owner_role(db, userid="ops-b", role="ops")
        _seed_owner_role(db, userid="delivery-a", role="delivery")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_a: {
                "owner_userids": ["owner-a"],
                "member_userids": ["owner-a", "ops-a", "delivery-a"],
                "viewer_roles": ["sales", "ops"],
                "operator_roles": ["sales", "ops"],
                "internal_roles": ["ops"],
            },
            tenant_b: {
                "owner_userids": ["owner-b"],
                "member_userids": ["owner-b", "ops-b"],
                "viewer_roles": ["sales", "ops"],
                "operator_roles": ["sales", "ops"],
                "internal_roles": ["ops"],
            },
        },
    )
    ops_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="ops-a", admin_role="ops")
    owner_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="owner-a", admin_role="sales")
    delivery_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="delivery-a", admin_role="delivery")
    ops_headers_b = _request_scoped_headers(tenant_key=tenant_b, admin_userid="ops-b", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid_a], headers=ops_headers_a)
    inbox_response = client.get("/api/admin/customer-pulse", headers=owner_headers_a)
    assert inbox_response.status_code == 200
    card = next(item for item in inbox_response.get_json()["inbox"]["cards"] if item["external_userid"] == external_userid_a)

    preview_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        headers=owner_headers_a,
        json={"action_type": "generate_reply_draft", "track_click": True},
    )
    assert preview_response.status_code == 200

    action_token_a = _admin_action_token(client, headers=owner_headers_a)
    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=owner_headers_a,
        json={
            "admin_action_token": action_token_a,
            "action_type": "generate_reply_draft",
            "operator": "owner-a",
        },
    )
    assert execute_response.status_code == 200

    unauthorized_response = client.get("/api/admin/customer-pulse", headers=delivery_headers_a)
    cross_tenant_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}", headers=ops_headers_b)
    stats_a_response = client.get("/api/admin/customer-pulse/stats?days=7", headers=ops_headers_a)
    stats_b_response = client.get("/api/admin/customer-pulse/stats?days=7", headers=ops_headers_b)

    assert unauthorized_response.status_code == 403
    assert unauthorized_response.get_json()["code"] == "inbox_view_forbidden"
    assert cross_tenant_response.status_code == 404
    assert stats_a_response.status_code == 200
    assert stats_b_response.status_code == 200

    stats_a = stats_a_response.get_json()["stats"]
    stats_b = stats_b_response.get_json()["stats"]

    assert stats_a["feature_gate"]["enabled"] is True
    assert "ai_success" in stats_a["counts"]
    assert stats_a["counts"]["card_exposed"] >= 1
    assert stats_a["counts"]["action_executed"] >= 1
    assert stats_a["counts"]["draft_preview_started"] >= 1
    assert stats_a["counts"]["draft_confirmed"] >= 1
    assert "fallback_count" in stats_a["counts"]
    assert stats_a["counts"]["writeback_success"] >= 1
    assert stats_a["counts"]["unauthorized_denied"] >= 1
    assert stats_a["rates"]["execution_rate"] > 0
    assert stats_a["rates"]["draft_confirm_rate"] > 0
    assert "fallback_rate" in stats_a["rates"]
    assert stats_a["rates"]["writeback_success_rate"] > 0
    assert stats_b["counts"]["cross_tenant_denied"] >= 1


def test_customer_pulse_tenant_rollout_report_aggregates_whitelisted_tenant_metrics(app, client):
    tenant_a = "tenant-acme"
    tenant_b = "tenant-beta"
    app.config["ai_customer_pulse"] = True
    external_userid_a = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-a", role="ops")
        _seed_owner_role(db, userid="ops-b", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_a: {
                "owner_userids": ["owner-a"],
                "member_userids": ["owner-a", "ops-a"],
                "viewer_roles": ["sales", "ops"],
                "operator_roles": ["sales", "ops"],
                "internal_roles": ["ops"],
            },
            tenant_b: {
                "owner_userids": ["owner-b"],
                "member_userids": ["owner-b", "ops-b"],
                "viewer_roles": ["sales", "ops"],
                "operator_roles": ["sales", "ops"],
                "internal_roles": ["ops"],
            },
        },
    )
    _set_customer_pulse_flag_policy(
        app,
        {
            "default_enabled": False,
            "tenants": {
                tenant_a: {"enabled": True},
                tenant_b: {"enabled": False},
            },
        },
    )
    ops_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="ops-a", admin_role="ops")
    owner_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="owner-a", admin_role="sales")
    ops_headers_b = _request_scoped_headers(tenant_key=tenant_b, admin_userid="ops-b", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid_a], headers=ops_headers_a)
    inbox_response = client.get("/api/admin/customer-pulse", headers=owner_headers_a)
    card = next(item for item in inbox_response.get_json()["inbox"]["cards"] if item["external_userid"] == external_userid_a)
    client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        headers=owner_headers_a,
        json={"action_type": "generate_reply_draft", "track_click": True},
    )
    client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=owner_headers_a,
        json={
            "admin_action_token": _admin_action_token(client, headers=owner_headers_a),
            "action_type": "generate_reply_draft",
            "operator": "owner-a",
        },
    )
    client.get(f"/api/admin/customer-pulse/cards/{card['id']}", headers=ops_headers_b)

    with app.app_context():
        report = build_customer_pulse_tenant_rollout_report(days=7)

    assert report["whitelist"]["default_enabled"] is False
    assert report["whitelist"]["enabled_tenants"] == [tenant_a]
    assert [item["tenant_key"] for item in report["tenants"]] == [tenant_a]
    tenant_report = report["tenants"][0]
    assert tenant_report["counts"]["draft_preview_started"] >= 1
    assert tenant_report["counts"]["draft_confirmed"] >= 1
    assert tenant_report["counts"]["writeback_success"] >= 1
    assert "draft_confirm_rate" in tenant_report["rates"]


def test_customer_pulse_first_wave_review_report_stays_hold_for_workspace_local_data(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="ops-a", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": ["owner-a"],
                "member_userids": ["owner-a", "ops-a"],
                "viewer_roles": ["sales", "ops"],
                "operator_roles": ["sales", "ops"],
                "internal_roles": ["ops"],
            }
        },
    )
    _set_customer_pulse_flag_policy(app, {"default_enabled": False, "tenants": {tenant_key: {"enabled": True}}})

    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-a", admin_role="ops")
    owner_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-a", admin_role="sales")
    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)
    card = client.get("/api/admin/customer-pulse", headers=owner_headers).get_json()["inbox"]["cards"][0]
    client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        headers=owner_headers,
        json={"action_type": "generate_reply_draft", "track_click": True},
    )
    client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=owner_headers,
        json={
            "admin_action_token": _admin_action_token(client, headers=owner_headers),
            "action_type": "generate_reply_draft",
            "operator": "owner-a",
        },
    )

    with app.app_context():
        report = build_customer_pulse_first_wave_review_report(days=7)

    assert report["data_source"]["production_evidence_verified"] is False
    assert report["final_decision"] == "hold"
    tenant_review = report["tenants"][0]
    assert tenant_review["rates"]["draft_confirm_rate"] >= 0
    assert tenant_review["status"] == "观察中，继续当前灰度"


def test_customer_pulse_cross_tenant_customer_detail_and_timeline_hide_other_tenant_evidence(app, client):
    tenant_a = "tenant-acme"
    tenant_b = "tenant-beta"
    app.config["ai_customer_pulse"] = True
    external_userid_a = _seed_reply_draft_candidate_scenario(app)
    external_userid_b = _seed_stalled_followup_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        _seed_owner_role(db, userid="ops-2", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_a: {"owner_userids": ["owner-a"], "member_userids": ["owner-a", "ops-1"]},
            tenant_b: {"owner_userids": ["owner-b"], "member_userids": ["owner-b", "ops-2"]},
        },
    )
    ops_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="ops-1", admin_role="ops")
    ops_headers_b = _request_scoped_headers(tenant_key=tenant_b, admin_userid="ops-2", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid_a], headers=ops_headers_a)
    _force_sync_customer_pulse(client, [external_userid_b], headers=ops_headers_b)
    card_a = _pulse_card_by_external_userid(client, external_userid_a, headers=ops_headers_a)
    action_token_a = _admin_action_token(client, headers=ops_headers_a)

    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card_a['id']}/actions/execute",
        headers=ops_headers_a,
        json={
            "admin_action_token": action_token_a,
            "action_type": "generate_reply_draft",
        },
    )
    assert execute_response.status_code == 200
    feedback_response = client.post(
        f"/api/admin/customer-pulse/cards/{card_a['id']}/feedback",
        headers=ops_headers_a,
        json={
            "admin_action_token": action_token_a,
            "feedback_type": "dismiss",
            "operator": "ops-1",
        },
    )
    assert feedback_response.status_code == 200

    tenant_a_timeline_response = client.get(
        f"/api/customers/{external_userid_a}/timeline?event_type=customer_pulse_activity",
        headers=ops_headers_a,
    )
    tenant_b_timeline_response = client.get(
        f"/api/customers/{external_userid_a}/timeline?event_type=customer_pulse_activity",
        headers=ops_headers_b,
    )
    tenant_b_detail_response = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid_a}",
        headers={"Authorization": "Bearer internal-token", **ops_headers_b},
    )

    assert tenant_a_timeline_response.status_code == 200
    assert tenant_a_timeline_response.get_json()["timeline"]["count"] == 1
    assert tenant_b_timeline_response.status_code == 200
    assert tenant_b_timeline_response.get_json()["timeline"]["count"] == 0
    assert tenant_b_detail_response.status_code == 200

    detail_payload = tenant_b_detail_response.get_json()
    assert detail_payload["ok"] is True
    assert detail_payload["customer"]["external_userid"] == external_userid_a
    assert detail_payload["has_card"] is False
    assert detail_payload["card"] is None
    assert detail_payload["latest_snapshot"] is None
    assert detail_payload["signals"] == []
    assert detail_payload["recent_activities"] == []
    assert detail_payload["recent_action_feedback"] == []


def test_customer_pulse_repo_tenant_filters_block_cross_tenant_snapshot_and_log_reads(app, client):
    tenant_a = "tenant-acme"
    tenant_b = "tenant-beta"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        _seed_owner_role(db, userid="ops-2", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_a: {"owner_userids": ["owner-a"], "member_userids": ["owner-a", "ops-1"]},
            tenant_b: {"owner_userids": ["owner-b"], "member_userids": ["owner-b", "ops-2"]},
        },
    )
    ops_headers_a = _request_scoped_headers(tenant_key=tenant_a, admin_userid="ops-1", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers_a)
    card = _pulse_card_by_external_userid(client, external_userid, headers=ops_headers_a)
    detail_response = client.get(
        f"/api/internal/customer-pulse/customers/{external_userid}",
        headers={"Authorization": "Bearer internal-token", **ops_headers_a},
    )
    assert detail_response.status_code == 200
    snapshot_id = int(detail_response.get_json()["latest_snapshot"]["id"])
    action_token_a = _admin_action_token(client, headers=ops_headers_a)

    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=ops_headers_a,
        json={
            "admin_action_token": action_token_a,
            "action_type": "generate_reply_draft",
        },
    )
    assert execute_response.status_code == 200
    execution_id = int(execute_response.get_json()["execution"]["id"])
    feedback_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/feedback",
        headers=ops_headers_a,
        json={
            "admin_action_token": action_token_a,
            "feedback_type": "misjudged",
            "operator": "ops-1",
        },
    )
    assert feedback_response.status_code == 200

    with app.app_context():
        assert customer_pulse_repo.get_customer_pulse_card(int(card["id"]), tenant_key=tenant_b) is None
        assert customer_pulse_repo.get_customer_pulse_snapshot(snapshot_id, tenant_key=tenant_b) is None
        assert customer_pulse_repo.list_customer_pulse_snapshots_by_ids([snapshot_id], tenant_key=tenant_b) == {}
        assert customer_pulse_repo.get_customer_pulse_execution_log(execution_id, tenant_key=tenant_b) is None
        assert customer_pulse_repo.list_customer_pulse_action_feedback(card_id=int(card["id"]), tenant_key=tenant_b) == []
        assert customer_pulse_repo.list_customer_pulse_activity_logs(external_userid, tenant_key=tenant_b) == []
        with pytest.raises(ValueError):
            customer_pulse_repo.get_customer_pulse_card(int(card["id"]), tenant_key="")


def test_customer_pulse_page_permission_hides_entry_and_rejects_inbox_api(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": ["owner-a"],
                "member_userids": ["owner-a", "ops-1"],
                "viewer_roles": ["sales"],
                "operator_roles": [],
                "permissions_by_role": {
                    "sales": ["widget_view"],
                },
            }
        },
    )
    sales_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-a", admin_role="sales")
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)

    admin_home = client.get("/admin", headers=sales_headers)
    inbox_page = client.get("/admin/customer-pulse", headers=sales_headers)
    inbox_api = client.get("/api/admin/customer-pulse", headers=sales_headers)
    customer_page = client.get(f"/admin/customers/{external_userid}", headers=sales_headers)
    widget_api = client.get(
        "/api/admin/customers/profile/pulse",
        headers=sales_headers,
        query_string={"external_userid": external_userid},
    )

    assert admin_home.status_code == 302
    assert admin_home.headers["Location"].endswith("/admin/automation-conversion")
    assert inbox_page.status_code == 410
    assert "模块已下线" in inbox_page.get_data(as_text=True)
    assert inbox_api.status_code == 403
    assert inbox_api.get_json()["code"] == "inbox_view_forbidden"
    assert customer_page.status_code == 200
    assert "客户档案" in customer_page.get_data(as_text=True)
    assert widget_api.status_code == 200
    assert widget_api.get_json()["customer_pulse"]["card"]["external_userid"] == external_userid


def test_customer_pulse_view_only_role_can_read_card_but_cannot_preview_or_execute(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": ["owner-a"],
                "member_userids": ["owner-a", "ops-1"],
                "viewer_roles": ["sales"],
                "operator_roles": [],
                "permissions_by_role": {
                    "sales": ["page_visible", "inbox_view", "widget_view"],
                },
            }
        },
    )
    sales_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-a", admin_role="sales")
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)
    action_token = _admin_action_token(client, headers=sales_headers)
    card = _pulse_card_by_external_userid(client, external_userid, headers=sales_headers)

    detail_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}", headers=sales_headers)
    preview_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        headers=sales_headers,
        json={"action_type": "generate_reply_draft"},
    )
    execute_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=sales_headers,
        json={
            "admin_action_token": action_token,
            "action_type": "generate_reply_draft",
        },
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["card"]["supported_action_buttons"] == []
    assert detail_payload["card"]["draft_editor_available"] is False
    assert detail_payload["card"]["permissions"]["can_execute_any"] is False
    assert preview_response.status_code == 403
    assert preview_response.get_json()["code"] == "action_permission_denied"
    assert execute_response.status_code == 403
    assert execute_response.get_json()["code"] == "action_permission_denied"


def test_customer_pulse_card_view_without_evidence_permission_cannot_expand_evidence(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-a", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": ["owner-a"],
                "member_userids": ["owner-a", "ops-1"],
                "viewer_roles": ["sales"],
                "operator_roles": [],
                "permissions_by_role": {
                    "sales": ["page_visible", "inbox_view"],
                },
            }
        },
    )
    sales_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-a", admin_role="sales")
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)
    card = _pulse_card_by_external_userid(client, external_userid, headers=sales_headers)

    detail_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}", headers=sales_headers)
    evidence_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}/evidence", headers=sales_headers)

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert detail_payload["card"]["evidence"] == []
    assert detail_payload["card"]["evidence_refs"]
    assert detail_payload["card"]["permissions"]["evidence_view"] is False
    assert detail_payload["card"]["evidence_expand_available"] is False
    assert evidence_response.status_code == 403
    assert evidence_response.get_json()["code"] == "evidence_view_forbidden"
    with app.app_context():
        db = get_db()
        audit_row = db.execute(
            """
            SELECT action_type, before_json, after_json
            FROM admin_operation_logs
            WHERE target_type = 'customer_pulse_evidence' AND target_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(card["id"]),),
        ).fetchone()
        denied_metric_count = int(
            db.execute(
                """
                SELECT COUNT(*) AS total_count
                FROM customer_pulse_metric_events
                WHERE tenant_key = ? AND event_type = 'access_denied'
                """,
                (tenant_key,),
            ).fetchone()["total_count"]
        )
    audit_before = json.loads(audit_row["before_json"])
    audit_after = json.loads(audit_row["after_json"])
    assert audit_row["action_type"] == "deny_card_evidence"
    assert audit_before["tenant_context"]["tenant_key"] == tenant_key
    assert audit_before["actor"]["actor_userid"] == "owner-a"
    assert audit_after["error_code"] == "evidence_view_forbidden"
    assert denied_metric_count >= 1


def test_customer_pulse_manual_draft_guardrail_block_records_failure_and_metric(app, client):
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_reply_draft_candidate_scenario(app)
    _force_sync_customer_pulse(client, [external_userid])
    card = _pulse_card_by_external_userid(client, external_userid)

    blocked_response = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        json={
            "admin_action_token": _admin_action_token(client),
            "action_type": "generate_reply_draft",
            "operator": "security-qa",
            "draft_message": "今天我给你最低价保证，手机号 13800138111 直接联系我。",
        },
    )

    assert blocked_response.status_code == 400
    assert "草稿命中安全风控" in blocked_response.get_json()["error"]

    with app.app_context():
        db = get_db()
        execution_row = db.execute(
            """
            SELECT execution_status, result_payload_json
            FROM customer_pulse_execution_logs
            WHERE card_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (card["id"],),
        ).fetchone()
        guardrail_metric_row = db.execute(
            """
            SELECT payload_json
            FROM customer_pulse_metric_events
            WHERE card_id = ? AND event_type = 'guardrail_blocked'
            ORDER BY id DESC
            LIMIT 1
            """,
            (card["id"],),
        ).fetchone()

    failure_payload = json.loads(execution_row["result_payload_json"])
    metric_payload = json.loads(guardrail_metric_row["payload_json"])
    assert execution_row["execution_status"] == "failed"
    assert "unauthorized_pricing_promise" in failure_payload["guardrails"]["text_guardrail_hits"]
    assert "pii_leak" in failure_payload["guardrails"]["text_guardrail_hits"]
    assert "unauthorized_pricing_promise" in metric_payload["text_guardrail_hits"]
    assert "pii_leak" in metric_payload["text_guardrail_hits"]


def test_customer_pulse_action_permissions_only_allow_authorized_action_types(app, client):
    tenant_key = "tenant-acme"
    app.config["ai_customer_pulse"] = True
    external_userid = _seed_stalled_followup_scenario(app)
    with app.app_context():
        db = get_db()
        _seed_owner_role(db, userid="owner-b", role="sales")
        _seed_owner_role(db, userid="ops-1", role="ops")
        db.commit()
    _set_request_scoped_customer_pulse_policies(
        app,
        policy_map={
            tenant_key: {
                "owner_userids": ["owner-b"],
                "member_userids": ["owner-b", "ops-1"],
                "viewer_roles": ["sales"],
                "operator_roles": [],
                "permissions_by_role": {
                    "sales": ["page_visible", "inbox_view", "create_followup_task"],
                },
            }
        },
    )
    sales_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="owner-b", admin_role="sales")
    ops_headers = _request_scoped_headers(tenant_key=tenant_key, admin_userid="ops-1", admin_role="ops")

    _force_sync_customer_pulse(client, [external_userid], headers=ops_headers)
    action_token = _admin_action_token(client, headers=sales_headers)
    card = _pulse_card_by_external_userid(client, external_userid, headers=sales_headers)

    detail_response = client.get(f"/api/admin/customer-pulse/cards/{card['id']}", headers=sales_headers)
    preview_allowed = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        headers=sales_headers,
        json={"action_type": "create_followup_task"},
    )
    preview_forbidden = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/preview",
        headers=sales_headers,
        json={"action_type": "set_followup_reminder"},
    )
    execute_allowed = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=sales_headers,
        json={
            "admin_action_token": action_token,
            "action_type": "create_followup_task",
            "task_title": "今天回访停滞客户",
            "due_at": "2026-04-12 10:30:00",
        },
    )
    execute_forbidden = client.post(
        f"/api/admin/customer-pulse/cards/{card['id']}/actions/execute",
        headers=sales_headers,
        json={
            "admin_action_token": action_token,
            "action_type": "set_followup_reminder",
            "due_at": "2026-04-12 10:30:00",
        },
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert [item["action_type"] for item in detail_payload["card"]["supported_action_buttons"]] == ["create_followup_task"]
    assert detail_payload["card"]["permissions"]["action_permissions"]["create_followup_task"] is True
    assert detail_payload["card"]["permissions"]["action_permissions"]["set_followup_reminder"] is False
    assert preview_allowed.status_code == 200
    assert preview_allowed.get_json()["preview"]["action_type"] == "create_followup_task"
    assert preview_forbidden.status_code == 403
    assert preview_forbidden.get_json()["code"] == "action_permission_denied"
    assert execute_allowed.status_code == 200
    assert execute_allowed.get_json()["execution"]["action_type"] == "create_followup_task"
    assert execute_forbidden.status_code == 403
    assert execute_forbidden.get_json()["code"] == "action_permission_denied"
