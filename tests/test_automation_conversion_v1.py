from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pytest
import requests

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.db.helpers import _sqlite_table_columns
from wecom_ability_service.domains.automation_conversion import (
    append_agent_output,
    apply_dashboard_signup_tag,
    backfill_missing_child_agent_replies,
    create_conversion_profile_segment_template,
    create_agent_run,
    create_conversion_workflow,
    create_conversion_workflow_node,
    ensure_agent_orchestration_defaults,
    get_all_agent_prompts,
    get_agent_config_detail,
    get_agent_output_detail,
    get_conversion_dashboard_payload,
    get_conversion_profile_segment_template_bundle,
    list_agent_configs,
    list_pending_agent_prompt_publish_requests,
    run_due_conversion_workflows,
    run_router_pending_callback_check,
    save_agent_config_draft,
    send_agent_reply_output_via_bazhuayu,
    send_conversion_execution_item_via_bazhuayu,
    save_agent_router_settings,
    submit_agent_prompt_for_publish,
    update_conversion_profile_segment_template,
)
from wecom_ability_service.domains.automation_conversion.agents.llm_client import (
    DeepSeekClientError,
    call_deepseek_agent,
)
from wecom_ability_service.domains.automation_conversion.service import (
    ensure_sop_v1_defaults,
    get_member_detail,
    get_overview_payload,
    get_stage_detail_payload,
    get_model_infra_payload,
    record_sop_pool_entry,
    run_due_reply_monitor,
    run_message_activity_sync,
    run_reply_monitor_capture,
    save_model_infra_prompt,
    save_model_infra_settings,
    save_reply_monitor_enabled,
    sync_member_activation,
)

try:
    from wecom_ability_service.domains.automation_conversion.service import run_due_sop
except ImportError:  # pragma: no cover - compatibility for environments where SOP runner export was removed
    run_due_sop = None

try:
    from wecom_ability_service.domains.automation_conversion.service import save_sop_v1_pool_config
except ImportError:  # pragma: no cover - compatibility for environments where SOP pool config export was removed
    save_sop_v1_pool_config = None

try:
    from wecom_ability_service.domains.automation_conversion.service import save_sop_v1_template
except ImportError:  # pragma: no cover - compatibility for environments where SOP template export was removed
    save_sop_v1_template = None

from wecom_ability_service.domains.automation_conversion.workflow_service import _normalize_node_payload


def _test_png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+b5f0AAAAASUVORK5CYII="
    )


def _build_stage_send_form_data(
    *,
    content: str = "",
    operator: str = "",
    images: list[tuple[str, bytes, str]] | None = None,
):
    payload = {"content": content, "operator": operator}
    if images:
        payload["images"] = [(BytesIO(file_bytes), file_name, mime_type) for file_name, file_bytes, mime_type in images]
    return payload


def _admin_action_token(client, path: str = "/admin/automation-conversion/runtime/router?subtab=agents") -> str:
    client.get(path, follow_redirects=True)
    with client.session_transaction() as session:
        return str(session["admin_console_action_token"])


def _default_program_id(app) -> int:
    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM automation_program WHERE program_code = 'signup_conversion_v1' LIMIT 1"
        ).fetchone()
        return int(row["id"])


def _login_admin_session(client) -> None:
    with client.session_transaction() as session:
        session["admin_session_user_id"] = 0
        session["admin_session_wecom_userid"] = ""
        session["admin_session_role_list"] = ["super_admin"]
        session["admin_session_login_type"] = "break_glass"
        session["admin_session_display_name"] = "test-admin"
        session["admin_session_break_glass_username"] = "test-admin"


def _mcp_call(client, name: str, arguments: dict[str, object]):
    return client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "automation-conversion-v1.sqlite3"
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
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    _login_admin_session(client)
    return client


def _sqlite_object_names(db, object_type: str) -> set[str]:
    rows = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = ?
        """,
        (object_type,),
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _seed_contact(app, *, external_userid: str, mobile: str = "", owner_userid: str = "sales_01", customer_name: str = "") -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name or external_userid, owner_userid),
        )
        if mobile:
            person_id = db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM people").fetchone()["next_id"]
            db.execute(
                """
                INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (person_id, mobile, f"tp-{person_id}"),
            )
            db.execute(
                """
                INSERT INTO external_contact_bindings (
                    external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (external_userid, person_id, owner_userid, owner_userid, owner_userid),
            )
        db.commit()


def _canonical_automation_pool(pool_key: str) -> str:
    return {
        "new_user": "pending_questionnaire",
        "inactive_normal": "operating",
        "inactive_focus": "operating",
        "active_normal": "operating",
        "active_focus": "operating",
        "silent": "operating",
        "won": "converted",
    }.get(str(pool_key or "").strip(), str(pool_key or "").strip())


def _seed_automation_member(
    app,
    *,
    external_contact_id: str,
    phone: str = "",
    owner_staff_id: str = "sales_01",
    in_pool: int = 1,
    current_pool: str = "active_normal",
    follow_type: str = "normal",
    activation_status: str = "active",
    questionnaire_status: str = "submitted",
    questionnaire_follow_type: str = "",
    decision_source: str = "manual",
    source_type: str = "manual",
    last_active_pool: str = "",
    joined_at: str = "2026-04-06 10:00:00",
) -> None:
    normalized_current_pool = _canonical_automation_pool(current_pool)
    normalized_last_active_pool = _canonical_automation_pool(last_active_pool)
    current_audience_code = (
        "converted"
        if normalized_current_pool == "converted"
        else "operating"
        if questionnaire_status == "submitted"
        else "pending_questionnaire"
    )
    if questionnaire_follow_type in {"normal", "focus"} and follow_type in {"", "normal"}:
        follow_type = questionnaire_follow_type
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                questionnaire_status, decision_source, source_type, last_active_pool,
                current_audience_code, current_audience_entered_at, joined_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                external_contact_id,
                phone,
                owner_staff_id,
                in_pool,
                normalized_current_pool,
                follow_type,
                questionnaire_status,
                decision_source,
                source_type,
                normalized_last_active_pool,
                current_audience_code,
                joined_at,
                joined_at,
            ),
        )
        db.commit()


def _seed_settings_questionnaire(app, *, questionnaire_id: int = 501) -> dict[str, object]:
    choice_question_id = questionnaire_id * 100 + 1
    mobile_question_id = questionnaire_id * 100 + 2
    option_ids = [questionnaire_id * 1000 + 1, questionnaire_id * 1000 + 2]
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"automation-settings-{questionnaire_id}",
                f"automation-settings-{questionnaire_id}",
                f"自动化设置问卷 {questionnaire_id}",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'single_choice', '你当前更关注什么？', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (choice_question_id, questionnaire_id),
        )
        db.executemany(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                (option_ids[0], choice_question_id, "效率", 1),
                (option_ids[1], choice_question_id, "成交", 2),
            ],
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '请填写手机号', 1, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "choice_question_id": choice_question_id,
        "option_ids": option_ids,
        "mobile_question_id": mobile_question_id,
    }


def _seed_profile_segment_template(
    app,
    *,
    questionnaire_id: int = 701,
    template_name: str = "测试画像模板",
    program_id: int | None = None,
) -> dict[str, object]:
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=questionnaire_id)
    with app.app_context():
        result = create_conversion_profile_segment_template(
            {
                "template_name": template_name,
                "questionnaire_id": questionnaire_seed["questionnaire_id"],
                "segmentation_question_id": questionnaire_seed["choice_question_id"],
                "categories": [
                    {
                        "category_key": "efficiency",
                        "category_name": "效率型",
                        "option_ids": [questionnaire_seed["option_ids"][0]],
                    },
                    {
                        "category_key": "closing",
                        "category_name": "成交型",
                        "option_ids": [questionnaire_seed["option_ids"][1]],
                    },
                ],
            },
            operator_id="tester",
            program_id=program_id,
        )
    return {
        **questionnaire_seed,
        "template_bundle": result["template_bundle"],
        "template_id": int(((result.get("template_bundle") or {}).get("template") or {}).get("id") or 0),
        "category_keys": ["efficiency", "closing"],
    }


def _save_signup_conversion_settings(
    app,
    *,
    questionnaire_id: int,
    question_id: int,
    hit_option_ids: list[int],
    core_threshold: int = 1,
) -> dict[str, object]:
    from wecom_ability_service.domains.marketing_automation.service import save_signup_conversion_config

    with app.app_context():
        return save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": questionnaire_id,
                "core_threshold": core_threshold,
                "top_threshold": core_threshold,
                "quiet_hour_start": 23,
                "day_start_hour": 9,
                "timezone": "Asia/Shanghai",
                "question_rules": [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": hit_option_ids,
                        "sort_order": 1,
                    }
                ],
                "silent_threshold_days_by_pool": {
                    "new_user": 7,
                    "inactive_normal": 7,
                    "inactive_focus": 7,
                    "active_normal": 7,
                    "active_focus": 7,
                },
            },
            enforce_required_mobile_question=True,
        )


def _configure_message_activity_db(app) -> None:
    app.config["MESSAGE_ACTIVITY_DB_HOST"] = "127.0.0.1"
    app.config["MESSAGE_ACTIVITY_DB_PORT"] = 3306
    app.config["MESSAGE_ACTIVITY_DB_NAME"] = "lobster"
    app.config["MESSAGE_ACTIVITY_DB_USER"] = "lobster_user"
    app.config["MESSAGE_ACTIVITY_DB_PASS"] = "lobster_pass"


def _mock_workflow_runtime_usage_counts(
    monkeypatch,
    *,
    usage_by_phone: dict[str, int] | None = None,
    configured: bool = True,
) -> None:
    usage_rows = [
        {
            "phone_prefix3": digits[:3],
            "phone_last4": digits[-4:],
            "phone_match_key": f"{digits[:3]}_{digits[-4:]}",
            "message_count": int(count),
        }
        for phone, count in (usage_by_phone or {}).items()
        for digits in ["".join(char for char in str(phone) if char.isdigit())]
        if len(digits) >= 7
    ]
    status_payload = {
        "configured": configured,
        "missing_keys": [] if configured else ["MESSAGE_ACTIVITY_DB_HOST"],
    }
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.get_message_activity_db_status",
        lambda: dict(status_payload),
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.query_message_activity_counts",
        lambda: list(usage_rows),
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_service.get_message_activity_db_status",
        lambda: dict(status_payload),
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_service.query_message_activity_counts",
        lambda: list(usage_rows),
    )


def _mock_workflow_runtime_now(monkeypatch, value: str) -> None:
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime._now_dt",
        lambda: datetime.strptime(value, "%Y-%m-%d %H:%M:%S"),
    )


class _FakeDeepSeekResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: dict[str, object] | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = dict(json_data or {})
        self.text = text
        self.headers = dict(headers or {})

    def json(self) -> dict[str, object]:
        return dict(self._json_data)


def _configure_reply_monitor(
    app,
    *,
    enabled: bool,
    last_capture_cursor: int = 0,
    last_capture_at: str = "",
    last_capture_status: str = "",
    last_dispatch_at: str = "",
    last_dispatch_status: str = "",
    last_error: str = "",
    quiet_hours_start: str = "23:00",
    quiet_hours_end: str = "09:00",
    dispatch_interval_seconds: int = 30,
) -> None:
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM automation_reply_monitor_config")
        db.execute(
            """
            INSERT INTO automation_reply_monitor_config (
                config_key, enabled, last_capture_cursor, last_capture_at, last_capture_status,
                last_capture_summary_json, last_dispatch_at, last_dispatch_status, last_dispatch_summary_json,
                last_error, quiet_hours_start, quiet_hours_end, dispatch_interval_seconds, created_at, updated_at
            )
            VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                1 if enabled else 0,
                last_capture_cursor,
                last_capture_at,
                last_capture_status,
                json.dumps({}, ensure_ascii=False),
                last_dispatch_at,
                last_dispatch_status,
                json.dumps({}, ensure_ascii=False),
                last_error,
                quiet_hours_start,
                quiet_hours_end,
                dispatch_interval_seconds,
            ),
        )
        db.commit()


def _seed_archived_message(
    app,
    *,
    msgid: str,
    seq: int,
    external_userid: str,
    owner_userid: str,
    sender: str,
    receiver: str = "",
    chat_type: str = "private",
    msgtype: str = "text",
    content: str = "",
    send_time: str = "2026-04-09 10:00:00",
) -> int:
    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                seq,
                msgid,
                chat_type,
                external_userid,
                owner_userid,
                sender,
                receiver,
                msgtype,
                content,
                send_time,
                "{}",
            ),
        ).fetchone()
        db.commit()
        return int(row["id"])


def _assign_member_to_current_audience(
    app,
    *,
    external_contact_id: str,
    audience_code: str,
    entered_at: str,
) -> None:
    with app.app_context():
        db = get_db()
        member = db.execute(
            """
            SELECT id
            FROM automation_member
            WHERE external_contact_id = ?
            LIMIT 1
            """,
            (external_contact_id,),
        ).fetchone()
        assert member is not None
        member_id = int(member["id"])
        db.execute(
            """
            UPDATE automation_member
            SET current_audience_code = ?, current_audience_entered_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (audience_code, entered_at, member_id),
        )
        db.execute(
            """
            INSERT INTO automation_member_audience_entry (
                member_id, audience_code, entered_at, exited_at, is_current,
                entry_source, entry_reason, source_snapshot_json, created_at, updated_at
            )
            VALUES (?, ?, ?, '', 1, 'test', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (member_id, audience_code, entered_at),
        )
        db.commit()


def _seed_questionnaire_submission_for_member(
    app,
    *,
    questionnaire_id: int,
    question_id: int,
    option_id: int,
    submission_id: int,
    external_userid: str,
    mobile_snapshot: str,
    submitted_at: str,
) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, 10, '[]', '', ?)
            """,
            (
                submission_id,
                questionnaire_id,
                f"overview-{submission_id}",
                external_userid,
                mobile_snapshot,
                submitted_at,
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (?, ?, 'single_choice', '概览分层题', ?, '[]', '[]', '[]', '', 10, CURRENT_TIMESTAMP)
            """,
            (
                submission_id,
                question_id,
                json.dumps([option_id], ensure_ascii=False),
            ),
        )
        db.commit()


def _patch_reply_monitor_payload_context(monkeypatch, *, external_userid: str, owner_display_name: str = "销售一") -> None:
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload",
        lambda *, external_userid=external_userid: {"tags": [{"tag_name": "高潜客户"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload",
        lambda *, external_userid="", mobile="": {"answers": [{"question": "预算", "answer": "999"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "messages": [
                {"sender": external_userid, "send_time": "2026-04-09 09:58:00", "content": "你好"},
                {"sender": "sales_01", "send_time": "2026-04-09 09:59:00", "content": "你好，我在"},
            ],
        },
    )


def _configure_sop_pool(
    app,
    *,
    pool_key: str,
    enabled: bool,
    send_time: str = "09:00",
) -> dict[str, object]:
    with app.app_context():
        return save_sop_v1_pool_config(
            pool_key=_canonical_automation_pool(pool_key),
            enabled=enabled,
            send_time=send_time,
        )


def _configure_only_sop_pool(
    app,
    *,
    pool_key: str,
    send_time: str = "09:00",
) -> None:
    selected_pool = _canonical_automation_pool(pool_key)
    for candidate_pool in ("pending_questionnaire", "operating", "converted"):
        _configure_sop_pool(
            app,
            pool_key=candidate_pool,
            enabled=candidate_pool == selected_pool,
            send_time=send_time if candidate_pool == selected_pool else "09:00",
        )


def _set_sop_pool_effective_start(app, *, pool_key: str, effective_start_at: str) -> None:
    with app.app_context():
        get_db().execute(
            """
            UPDATE automation_sop_pool_config
            SET effective_start_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE pool_key = ?
            """,
            (effective_start_at, _canonical_automation_pool(pool_key)),
        )
        get_db().commit()


def _create_test_workflow(
    app,
    *,
    workflow_name: str = "测试任务流",
    audiences: list[str] | None = None,
    status: str = "active",
    segmentation_basis: str = "none",
    generation_mode: str = "manual_layered",
    agent_bindings: list[dict[str, object]] | None = None,
    profile_segment_template_id: int | None = None,
    recipient_filter_basis: str | None = None,
    recipient_behavior_tier_keys: list[str] | None = None,
    content_segmentation_basis: str | None = None,
    content_profile_segment_template_id: int | None = None,
) -> dict[str, object]:
    with app.app_context():
        payload = {
            "workflow_name": workflow_name,
            "workflow_code": workflow_name,
            "description": "test workflow",
            "status": status,
            "segmentation_basis": segmentation_basis,
            "generation_mode": generation_mode,
            "profile_segment_template_id": profile_segment_template_id,
            "audiences": list(audiences or ["pending_questionnaire"]),
            "agent_bindings": list(agent_bindings or []),
        }
        if recipient_filter_basis is not None:
            payload["recipient_filter_basis"] = recipient_filter_basis
        if recipient_behavior_tier_keys is not None:
            payload["recipient_behavior_tier_keys"] = list(recipient_behavior_tier_keys)
        if content_segmentation_basis is not None:
            payload["content_segmentation_basis"] = content_segmentation_basis
        if content_profile_segment_template_id is not None:
            payload["content_profile_segment_template_id"] = content_profile_segment_template_id
        return create_conversion_workflow(payload, operator_id="tester")


def _seed_test_agent_config(app, *, agent_code: str, display_name: str = "") -> None:
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO automation_agent_config (
                agent_code,
                display_name,
                pool_keys_json,
                enabled,
                draft_role_prompt,
                draft_task_prompt,
                draft_variables_json,
                draft_output_schema_json,
                published_role_prompt,
                published_task_prompt,
                published_variables_json,
                published_output_schema_json,
                draft_version,
                published_version,
                last_change_summary,
                created_at,
                updated_at
            )
            VALUES (?, ?, '[]', 1, '', '', '[]', '[]', '', '', '[]', '[]', 1, 1, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(agent_code) DO UPDATE SET
                display_name = excluded.display_name,
                enabled = 1,
                published_version = MAX(automation_agent_config.published_version, 1),
                updated_at = CURRENT_TIMESTAMP
            """,
            (agent_code, display_name or agent_code),
        )
        get_db().commit()


def _seed_workflow_execution(
    app,
    *,
    workflow_id: int,
    execution_id: str,
    scheduled_for: str,
    status: str = "finished",
    success_count: int = 1,
    skipped_count: int = 0,
    failed_count: int = 0,
) -> None:
    total_count = success_count + skipped_count + failed_count
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO automation_workflow_execution (
                execution_id,
                workflow_id,
                node_id,
                trigger_type,
                audience_code,
                scheduled_for,
                status,
                total_count,
                success_count,
                skipped_count,
                failed_count,
                summary_json,
                created_at,
                updated_at,
                finished_at
            )
            VALUES (?, ?, NULL, 'scheduled_poll', 'pending_questionnaire', ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """,
            (
                execution_id,
                workflow_id,
                scheduled_for,
                status,
                total_count,
                success_count,
                skipped_count,
                failed_count,
                json.dumps({"source": "test"}, ensure_ascii=False),
                scheduled_for if status in {"finished", "partial_failed", "failed"} else "",
            ),
        )
        get_db().commit()


def test_init_db_adds_workflow_node_trigger_mode_column(app):
    with app.app_context():
        assert "trigger_mode" in _sqlite_table_columns(get_db(), "automation_workflow_node")


def test_create_workflow_supports_split_recipient_filter_and_content_segmentation(app):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=711, template_name="拆维度画像模板")
    _seed_test_agent_config(app, agent_code="efficiency_agent", display_name="效率 Agent")
    _seed_test_agent_config(app, agent_code="closing_agent", display_name="成交 Agent")

    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="拆维度任务流",
        status="draft",
        recipient_filter_basis="behavior",
        recipient_behavior_tier_keys=["lt_2"],
        content_segmentation_basis="profile",
        content_profile_segment_template_id=template_seed["template_id"],
        generation_mode="auto_layered_rewrite",
        agent_bindings=[
            {
                "binding_scope": "profile_category",
                "segment_key": "efficiency",
                "agent_code": "efficiency_agent",
            },
            {
                "binding_scope": "profile_category",
                "segment_key": "closing",
                "agent_code": "closing_agent",
            },
        ],
    )

    workflow = ((workflow_bundle.get("workflow_bundle") or {}).get("workflow")) or {}
    assert workflow["recipient_filter_basis"] == "behavior"
    assert workflow["recipient_behavior_tier_keys"] == ["lt_2"]
    assert workflow["content_segmentation_basis"] == "profile"
    assert workflow["content_profile_segment_template_id"] == template_seed["template_id"]
    assert workflow["segmentation_basis"] == "profile"
    assert workflow["profile_segment_template_id"] == template_seed["template_id"]
    assert json.loads(workflow["behavior_tier_scheme"]) == {
        "recipient_filter_basis": "behavior",
        "recipient_behavior_tier_keys": ["lt_2"],
    }


def test_run_due_conversion_workflows_filters_recipients_by_behavior_and_keeps_profile_content_segmentation(app, monkeypatch):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=712, template_name="行为筛选画像发内容")
    _seed_contact(app, external_userid="wm_profile_low_001", mobile="13800002221", owner_userid="sales_01", customer_name="低行为客户")
    _seed_contact(app, external_userid="wm_profile_high_001", mobile="13800002222", owner_userid="sales_01", customer_name="高行为客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_profile_low_001",
        phone="13800002221",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_profile_high_001",
        phone="13800002222",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="行为筛选画像内容",
        recipient_filter_basis="behavior",
        recipient_behavior_tier_keys=["lt_2"],
        content_segmentation_basis="profile",
        content_profile_segment_template_id=template_seed["template_id"],
        generation_mode="manual_layered",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "行为筛选画像内容节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "standard_content_text": "标准回退内容",
                "content_variants": [
                    {
                        "segment_key": "efficiency",
                        "content_text": "效率型定向内容",
                    },
                    {
                        "segment_key": "closing",
                        "content_text": "成交型定向内容",
                    },
                ],
                "enabled": True,
            },
            operator_id="tester",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime._resolve_profile_segment_match",
        lambda *, workflow_bundle, member: {
            "matched": True,
            "segment_key": "efficiency",
            "segment_label": "效率型",
            "reason": "",
        },
    )
    _mock_workflow_runtime_usage_counts(
        monkeypatch,
        usage_by_phone={
            "13800002221": 1,
            "13800002222": 8,
        },
    )
    for seq in range(1, 9):
        _seed_archived_message(
            app,
            msgid=f"profile-high-archive-{seq}",
            seq=seq,
            external_userid="wm_profile_low_001",
            owner_userid="sales_01",
            sender="wm_profile_low_001",
            content="旧口径高频客户消息",
        )
    _seed_archived_message(
        app,
        msgid="profile-low-archive-1",
        seq=101,
        external_userid="wm_profile_high_001",
        owner_userid="sales_01",
        sender="wm_profile_high_001",
        content="旧口径低频客户消息",
    )

    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 991, "wecom_result": {"msgid": "msg-991"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        item_rows = get_db().execute(
            """
            SELECT external_contact_id, rendered_content_text, status
            FROM automation_workflow_execution_item
            ORDER BY id ASC
            """
        ).fetchall()

    assert result["ok"] is True
    assert len(dispatched) == 1
    assert dispatched[0]["external_userid"] == ["wm_profile_low_001"]
    assert [dict(row) for row in item_rows] == [
        {
            "external_contact_id": "wm_profile_low_001",
            "rendered_content_text": "效率型定向内容",
            "status": "sent",
        }
    ]


def test_run_due_conversion_workflows_sends_pending_questionnaire_day1_day2_day3_in_sequence(app, monkeypatch):
    _seed_contact(app, external_userid="wm_pending_sequence_001", mobile="13800005551", owner_userid="sales_01", customer_name="问卷待填写序列客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_pending_sequence_001",
        phone="13800005551",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="问卷待填写三次推送", status="active")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        for day_offset, content_text in (
            (1, "第1天提醒填写问卷"),
            (2, "第2天继续提醒填写问卷"),
            (3, "第3天最后提醒填写问卷"),
        ):
            create_conversion_workflow_node(
                workflow_id,
                {
                    "node_name": f"问卷提醒 Day {day_offset}",
                    "target_audience_code": "pending_questionnaire",
                    "trigger_mode": "scheduled",
                    "day_offset": day_offset,
                    "send_time": "09:00",
                    "content_mode": "standard_direct",
                    "standard_content_text": content_text,
                    "enabled": True,
                },
                operator_id="tester",
            )

    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1100 + len(dispatched), "wecom_result": {"msgid": f"msg-{1100 + len(dispatched)}"}},
    )

    with app.app_context():
        _mock_workflow_runtime_now(monkeypatch, "2026-04-08 09:05:00")
        first = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        _mock_workflow_runtime_now(monkeypatch, "2026-04-09 09:05:00")
        second = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        _mock_workflow_runtime_now(monkeypatch, "2026-04-10 09:05:00")
        third = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_items = get_db().execute(
            """
            SELECT rendered_content_text, status
            FROM automation_workflow_execution_item
            ORDER BY id ASC
            """
        ).fetchall()

    assert first["total_success_count"] == 1
    assert second["total_success_count"] == 1
    assert third["total_success_count"] == 1
    assert [item["text"]["content"] for item in dispatched] == [
        "第1天提醒填写问卷",
        "第2天继续提醒填写问卷",
        "第3天最后提醒填写问卷",
    ]
    assert [dict(row) for row in execution_items] == [
        {"rendered_content_text": "第1天提醒填写问卷", "status": "sent"},
        {"rendered_content_text": "第2天继续提醒填写问卷", "status": "sent"},
        {"rendered_content_text": "第3天最后提醒填写问卷", "status": "sent"},
    ]


def test_run_due_conversion_workflows_supports_operating_audience_scheduled_node_with_timezone_entered_at(app, monkeypatch):
    _seed_contact(app, external_userid="wm_operating_scheduled_001", mobile="13800005552", owner_userid="sales_01", customer_name="运营中客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_operating_scheduled_001",
        phone="13800005552",
        owner_staff_id="sales_01",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
        joined_at="2026-04-08 08:00:00",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_operating_scheduled_001",
        audience_code="operating",
        entered_at="2026-04-08 08:00:00+08:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="运营中计划", audiences=["operating"], status="active")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "运营中定时触达",
                "target_audience_code": "operating",
                "trigger_mode": "scheduled",
                "day_offset": 1,
                "send_time": "09:00",
                "content_mode": "standard_direct",
                "standard_content_text": "运营中人群定时触达",
                "enabled": True,
            },
            operator_id="tester",
        )

    dispatched: list[dict[str, object]] = []
    _mock_workflow_runtime_now(monkeypatch, "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1201, "wecom_result": {"msgid": "msg-1201"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")

    assert result["total_success_count"] == 1
    assert len(dispatched) == 1
    assert dispatched[0]["external_userid"] == ["wm_operating_scheduled_001"]
    assert dispatched[0]["text"]["content"] == "运营中人群定时触达"


def test_run_due_conversion_workflows_does_not_backfill_missed_scheduled_day(app, monkeypatch):
    _seed_contact(app, external_userid="wm_backfill_existing_001", mobile="13800005553", owner_userid="sales_01", customer_name="存量客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_backfill_existing_001",
        phone="13800005553",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-05 08:00:00",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_backfill_existing_001",
        audience_code="pending_questionnaire",
        entered_at="2026-04-05 08:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="存量补发计划", status="active")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "第2天提醒",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "scheduled",
                "day_offset": 2,
                "send_time": "09:00",
                "content_mode": "standard_direct",
                "standard_content_text": "第2天当天提醒",
                "enabled": True,
            },
            operator_id="tester",
        )

    dispatched: list[dict[str, object]] = []
    _mock_workflow_runtime_now(monkeypatch, "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1301, "wecom_result": {"msgid": "msg-1301"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_rows = get_db().execute(
            """
            SELECT success_count, failed_count, summary_json
            FROM automation_workflow_execution
            ORDER BY id ASC
            """
        ).fetchall()

    assert result["total_success_count"] == 0
    assert dispatched == []
    summary = json.loads(execution_rows[0]["summary_json"])
    assert summary["result"]["success_count"] == 0
    assert summary["diagnostics"]["day_offset_miss_count"] == 1
    assert "day_offset_not_due" in summary["zero_hit_reasons"]


def test_run_due_conversion_workflows_daily_recurring_operating_nodes_patrol_current_low_usage_members(app, monkeypatch):
    members = (
        ("wm_operating_recurring_day3", "13800006531", "2026-04-18 08:00:00", "第3天激活提醒"),
        ("wm_operating_recurring_day4", "13800006541", "2026-04-17 08:00:00", "第4天使用场景激活"),
        ("wm_operating_recurring_day5", "13800006551", "2026-04-16 08:00:00", "第5天结果预期激活"),
        ("wm_operating_recurring_day6", "13800006571", "2026-04-15 08:00:00", ""),
    )
    for external_userid, mobile, entered_at, _expected_text in members:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_01", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_01",
            current_pool="active_normal",
            activation_status="active",
            questionnaire_status="submitted",
            questionnaire_follow_type="normal",
            decision_source="questionnaire",
            joined_at=entered_at,
        )
        _assign_member_to_current_audience(
            app,
            external_contact_id=external_userid,
            audience_code="operating",
            entered_at=entered_at,
        )

    _seed_contact(app, external_userid="wm_operating_recurring_too_early", mobile="13800006521", owner_userid="sales_01", customer_name="too-early")
    _seed_automation_member(
        app,
        external_contact_id="wm_operating_recurring_too_early",
        phone="13800006521",
        owner_staff_id="sales_01",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
        joined_at="2026-04-19 08:00:00",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_operating_recurring_too_early",
        audience_code="operating",
        entered_at="2026-04-19 08:00:00",
    )

    _seed_contact(app, external_userid="wm_operating_recurring_high_usage", mobile="13800006561", owner_userid="sales_01", customer_name="high-usage")
    _seed_automation_member(
        app,
        external_contact_id="wm_operating_recurring_high_usage",
        phone="13800006561",
        owner_staff_id="sales_01",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
        joined_at="2026-04-16 08:00:00",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_operating_recurring_high_usage",
        audience_code="operating",
        entered_at="2026-04-16 08:00:00",
    )

    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="运营中每日轮巡促活",
        audiences=["operating"],
        recipient_filter_basis="behavior",
        recipient_behavior_tier_keys=["lt_2"],
        status="active",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        for day_offset, node_name, content_text in (
            (3, "第3天激活提醒", "第3天激活提醒"),
            (4, "第4天使用场景激活", "第4天使用场景激活"),
            (5, "第5天结果预期激活", "第5天结果预期激活"),
        ):
            create_conversion_workflow_node(
                workflow_id,
                {
                    "node_name": node_name,
                    "target_audience_code": "operating",
                    "trigger_mode": "daily_recurring",
                    "day_offset": day_offset,
                    "send_time": "09:00",
                    "content_mode": "standard_direct",
                    "standard_content_text": content_text,
                    "enabled": True,
                },
                operator_id="tester",
            )

    dispatched: list[dict[str, object]] = []
    _mock_workflow_runtime_now(monkeypatch, "2026-04-20 09:05:00")
    _mock_workflow_runtime_usage_counts(
        monkeypatch,
        usage_by_phone={
            "13800006531": 1,
            "13800006541": 1,
            "13800006551": 1,
            "13800006571": 1,
            "13800006521": 1,
            "13800006561": 12,
        },
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1400 + len(dispatched), "wecom_result": {"msgid": f"msg-{1400 + len(dispatched)}"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_rows = get_db().execute(
            """
            SELECT execution_id, total_count, success_count, summary_json
            FROM automation_workflow_execution
            ORDER BY id ASC
            """
        ).fetchall()

    assert result["total_success_count"] == 3
    assert [item["text"]["content"] for item in dispatched] == [
        "第3天激活提醒",
        "第4天使用场景激活",
        "第5天结果预期激活",
    ]
    summaries = [json.loads(row["summary_json"]) for row in execution_rows]
    assert [summary["result"]["success_count"] for summary in summaries] == [1, 1, 1]
    assert summaries[0]["diagnostics"]["day_offset_miss_count"] == 5
    assert summaries[2]["diagnostics"]["recipient_filter_behavior_tier_miss_count"] == 1
    assert summaries[2]["diagnostics"]["day_offset_miss_count"] == 4


def test_run_due_conversion_workflows_daily_recurring_treats_operating_missing_usage_source_as_zero(app, monkeypatch):
    _seed_contact(app, external_userid="wm_operating_missing_usage_zero", mobile="13800006931", owner_userid="sales_01", customer_name="missing-usage-zero")
    _seed_automation_member(
        app,
        external_contact_id="wm_operating_missing_usage_zero",
        phone="13800006931",
        owner_staff_id="sales_01",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
        joined_at="2026-04-18 08:00:00",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_operating_missing_usage_zero",
        audience_code="operating",
        entered_at="2026-04-18 08:00:00",
    )

    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="运营中缺失使用源按0次轮巡",
        audiences=["operating"],
        recipient_filter_basis="behavior",
        recipient_behavior_tier_keys=["lt_2"],
        status="active",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "第3天激活提醒",
                "target_audience_code": "operating",
                "trigger_mode": "daily_recurring",
                "day_offset": 3,
                "send_time": "09:00",
                "content_mode": "standard_direct",
                "standard_content_text": "第3天激活提醒",
                "enabled": True,
            },
            operator_id="tester",
        )

    dispatched: list[dict[str, object]] = []
    _mock_workflow_runtime_now(monkeypatch, "2026-04-20 09:05:00")
    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={})
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1901, "wecom_result": {"msgid": "msg-1901"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_row = get_db().execute(
            """
            SELECT success_count, skipped_count, summary_json
            FROM automation_workflow_execution
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    summary = json.loads(execution_row["summary_json"])
    assert result["total_success_count"] == 1
    assert len(dispatched) == 1
    assert dispatched[0]["text"]["content"] == "第3天激活提醒"
    assert execution_row["success_count"] == 1
    assert execution_row["skipped_count"] == 0
    assert summary["zero_hit_reasons"] == []
    assert summary["result"]["success_count"] == 1


def test_run_due_conversion_workflows_legacy_manual_layered_none_workflow_still_renders_node_segment_content(app, monkeypatch):
    _seed_contact(app, external_userid="wm_legacy_layered_001", mobile="13800005554", owner_userid="sales_01", customer_name="legacy 脏配置客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_legacy_layered_001",
        phone="13800005554",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="legacy 手动分层脏配置",
        segmentation_basis="behavior",
        generation_mode="manual_layered",
        status="active",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "legacy 行为分层节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_variants": [
                    {"segment_key": "lt_2", "content_text": "低行为脏配置仍可发送"},
                    {"segment_key": "between_2_9", "content_text": "中行为脏配置仍可发送"},
                    {"segment_key": "gte_10", "content_text": "高行为脏配置仍可发送"},
                ],
                "enabled": True,
            },
            operator_id="tester",
        )
        get_db().execute(
            """
            UPDATE automation_workflow
            SET segmentation_basis = 'none', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (workflow_id,),
        )
        get_db().commit()

    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={"13800005554": 1})
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1401, "wecom_result": {"msgid": "msg-1401"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        item_row = get_db().execute(
            """
            SELECT rendered_content_text, content_snapshot_json, status
            FROM automation_workflow_execution_item
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()

    snapshot = json.loads(item_row["content_snapshot_json"])
    assert result["total_success_count"] == 1
    assert len(dispatched) == 1
    assert dict(item_row)["rendered_content_text"] == "低行为脏配置仍可发送"
    assert dict(item_row)["status"] == "sent"
    assert snapshot["workflow_segmentation_basis"] == "none"
    assert snapshot["node_segmentation_basis"] == "behavior"


def test_run_due_conversion_workflows_manual_layered_profile_node_can_fallback_to_standard_content(app, monkeypatch):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=739, template_name="画像分层 fallback 模板")
    _seed_contact(app, external_userid="wm_profile_fallback_001", mobile="13800005556", owner_userid="sales_01", customer_name="画像缺失 fallback 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_profile_fallback_001",
        phone="13800005556",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="画像 fallback 任务流",
        segmentation_basis="profile",
        generation_mode="manual_layered",
        profile_segment_template_id=int(template_seed["template_id"]),
        status="active",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        node_result = create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "画像 fallback 节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "standard_content_text": "没有命中画像时走标准 fallback",
                "fallback_to_standard_content": True,
                "content_variants": [
                    {"segment_key": "efficiency", "content_text": "效率型定制内容"},
                    {"segment_key": "closing", "content_text": "成交型定制内容"},
                ],
                "enabled": True,
            },
            operator_id="tester",
        )
        node_id = int(((node_result.get("node") or {}).get("id") or 0))
        get_db().execute(
            """
            UPDATE automation_workflow_node_content
            SET standard_content_text = ?, fallback_to_standard_content = 1, updated_at = CURRENT_TIMESTAMP
            WHERE node_id = ?
            """,
            ("没有命中画像时走标准 fallback", node_id),
        )
        get_db().commit()

    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 1451, "wecom_result": {"msgid": "msg-1451"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        item_row = get_db().execute(
            """
            SELECT rendered_content_text, content_snapshot_json, status
            FROM automation_workflow_execution_item
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()

    snapshot = json.loads(item_row["content_snapshot_json"])
    assert result["total_success_count"] == 1
    assert len(dispatched) == 1
    assert dict(item_row)["rendered_content_text"] == "没有命中画像时走标准 fallback"
    assert dict(item_row)["status"] == "sent"
    assert snapshot["content_source"] == "standard_content_fallback"
    assert snapshot["fallback_reason"] == "questionnaire_submission_missing"


def test_run_due_conversion_workflows_reports_message_activity_config_error_in_zero_hit_summary(app, monkeypatch):
    _seed_contact(app, external_userid="wm_usage_config_missing_001", mobile="13800005555", owner_userid="sales_01", customer_name="usage 配置缺失客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_usage_config_missing_001",
        phone="13800005555",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="usage 配置缺失",
        recipient_filter_basis="behavior",
        recipient_behavior_tier_keys=["lt_2"],
        status="active",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "usage 配置缺失节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_mode": "standard_direct",
                "standard_content_text": "不应执行发送",
                "enabled": True,
            },
            operator_id="tester",
        )

    _mock_workflow_runtime_usage_counts(monkeypatch, configured=False)

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")

    summary = dict((result.get("executions") or [])[0].get("summary") or {})
    assert result["total_success_count"] == 0
    assert summary["diagnostics"]["recipient_filter_usage_source_unavailable_count"] == 1
    assert summary["zero_hit_reasons"] == ["message_activity_db_not_configured"]


def test_create_workflow_remains_compatible_with_legacy_segmentation_basis_behavior_payload(app):
    _seed_test_agent_config(app, agent_code="behavior_lt_2_agent", display_name="低行为 Agent")
    _seed_test_agent_config(app, agent_code="behavior_2_9_agent", display_name="中行为 Agent")
    _seed_test_agent_config(app, agent_code="behavior_10_agent", display_name="高行为 Agent")

    with app.app_context():
        result = create_conversion_workflow(
            {
                "workflow_name": "旧版行为分层兼容",
                "workflow_code": "旧版行为分层兼容",
                "description": "legacy behavior payload",
                "status": "draft",
                "segmentation_basis": "behavior",
                "generation_mode": "auto_layered_rewrite",
                "audiences": ["pending_questionnaire"],
                "agent_bindings": [
                    {"binding_scope": "behavior_tier", "segment_key": "lt_2", "agent_code": "behavior_lt_2_agent"},
                    {"binding_scope": "behavior_tier", "segment_key": "between_2_9", "agent_code": "behavior_2_9_agent"},
                    {"binding_scope": "behavior_tier", "segment_key": "gte_10", "agent_code": "behavior_10_agent"},
                ],
            },
            operator_id="tester",
        )

    workflow = ((result.get("workflow_bundle") or {}).get("workflow")) or {}
    assert workflow["recipient_filter_basis"] == "none"
    assert workflow["recipient_behavior_tier_keys"] == []
    assert workflow["content_segmentation_basis"] == "behavior"
    assert workflow["segmentation_basis"] == "behavior"
    assert workflow["behavior_tier_scheme"] == "fixed_v1"
    assert [item["tier_code"] for item in ((result.get("workflow_bundle") or {}).get("behavior_tiers") or [])] == [
        "lt_2",
        "between_2_9",
        "gte_10",
    ]


def test_operations_list_page_renders_split_navigation_without_legacy_panels(app, client):
    program_id = _default_program_id(app)
    response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="admin-topbar"' not in html
    assert "当前页面只保留自动化运营列表和一级入口。" not in html
    assert "执行记录" in html
    assert "新建任务流" in html
    assert "编辑" in html
    assert "最近更新时间" not in html
    assert ">详情<" not in html

def test_workflow_nodes_page_removes_manual_layered_fallback_copy(app, client):
    workflow_bundle = _create_test_workflow(app, workflow_name="手动分层节点页")
    workflow_id = int((((workflow_bundle.get("workflow_bundle") or {}).get("workflow")) or {}).get("id") or 0)
    program_id = _default_program_id(app)

    response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations/workflows/{workflow_id}/nodes")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "标准版回退内容（可选）" not in html
    assert "当前任务流是手动分层录入，节点层只填写当前有效分层的内容明细。" in html
    assert "填写当前有效行为层级对应的节点内容，输入区会随行为层级配置动态变化。" in html
def test_conversion_dashboard_payload_aggregates_execution_counts_by_workflow(app):
    first_bundle = _create_test_workflow(app, workflow_name="任务流甲", status="active")
    second_bundle = _create_test_workflow(app, workflow_name="任务流乙", status="draft")
    first_workflow_id = int((((first_bundle.get("workflow_bundle") or {}).get("workflow")) or {}).get("id") or 0)
    second_workflow_id = int((((second_bundle.get("workflow_bundle") or {}).get("workflow")) or {}).get("id") or 0)

    _seed_workflow_execution(app, workflow_id=first_workflow_id, execution_id="exec-alpha-1", scheduled_for="2026-04-08 09:00:00")
    _seed_workflow_execution(app, workflow_id=first_workflow_id, execution_id="exec-alpha-2", scheduled_for="2026-04-09 09:00:00")
    _seed_workflow_execution(app, workflow_id=second_workflow_id, execution_id="exec-beta-1", scheduled_for="2026-04-07 09:00:00")

    with app.app_context():
        payload = get_conversion_dashboard_payload()

    summary = payload["task_execution_summary"]
    items = summary["items"]

    assert payload["active_workflow_count"] == 1
    assert summary["total"] == 2
    assert [item["workflow_name"] for item in items] == ["任务流甲", "任务流乙"]
    assert [item["execution_count"] for item in items] == [2, 1]
    assert items[0]["latest_execution_at"] == "2026-04-09 09:00:00"
    assert set(items[0].keys()) == {"workflow_name", "execution_count", "latest_execution_at"}
    assert "recent_send_summary" not in payload
    assert "recent_execution_summary" not in payload


def test_conversion_dashboard_payload_returns_empty_task_execution_summary_without_workflows(app):
    with app.app_context():
        payload = get_conversion_dashboard_payload()

    assert payload["task_execution_summary"] == {"items": [], "total": 0}


def test_conversion_dashboard_payload_includes_audience_member_details(app, monkeypatch):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=731, template_name="概览画像模板")
    _save_signup_conversion_settings(
        app,
        questionnaire_id=int(template_seed["questionnaire_id"]),
        question_id=int(template_seed["choice_question_id"]),
        hit_option_ids=[int(template_seed["option_ids"][1])],
        core_threshold=1,
    )

    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_operating_001",
        phone="13800008101",
        owner_staff_id="sales_overview",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_operating_001",
        audience_code="operating",
        entered_at="2026-04-10 10:00:00",
    )
    _seed_questionnaire_submission_for_member(
        app,
        questionnaire_id=int(template_seed["questionnaire_id"]),
        question_id=int(template_seed["choice_question_id"]),
        option_id=int(template_seed["option_ids"][0]),
        submission_id=73101,
        external_userid="wm_dashboard_operating_001",
        mobile_snapshot="13800008101",
        submitted_at="2026-04-10 09:58:00",
    )
    for seq in range(1, 4):
        _seed_archived_message(
            app,
            msgid=f"overview-operating-{seq}",
            seq=seq,
            external_userid="wm_dashboard_operating_001",
            owner_userid="sales_overview",
            sender="wm_dashboard_operating_001",
        )

    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_pending_001",
        phone="13800008102",
        owner_staff_id="sales_overview",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_pending_001",
        audience_code="pending_questionnaire",
        entered_at="2026-04-10 11:00:00",
    )

    _mock_workflow_runtime_usage_counts(
        monkeypatch,
        usage_by_phone={
            "13800008101": 1,
            "13800008102": 0,
        },
    )

    with app.app_context():
        payload = get_conversion_dashboard_payload()

    detail = payload["audience_member_details"]
    groups = {item["audience_code"]: item for item in detail["groups"]}

    assert detail["profile_segment_template"]["template_name"] == "概览画像模板"
    assert detail["total"] == 2
    assert groups["pending_questionnaire"]["count"] == 1
    assert groups["operating"]["count"] == 1
    assert groups["converted"]["count"] == 0

    pending_item = groups["pending_questionnaire"]["items"][0]
    expected_dashboard_item_keys = {
        "member_id",
        "external_contact_id",
        "phone",
        "audience_code",
        "audience_label",
        "questionnaire_status",
        "questionnaire_status_label",
        "profile_segment_key",
        "profile_segment_label",
        "behavior_segment_key",
        "behavior_segment_label",
        "conversation_count",
    }
    assert pending_item["external_contact_id"] == "wm_dashboard_pending_001"
    assert pending_item["questionnaire_status_label"] == "待提交"
    assert pending_item["profile_segment_label"] == ""
    assert pending_item["behavior_segment_label"] == "消息少于 2"
    assert pending_item["conversation_count"] == 0
    assert set(pending_item) == expected_dashboard_item_keys

    operating_item = groups["operating"]["items"][0]
    assert operating_item["external_contact_id"] == "wm_dashboard_operating_001"
    assert operating_item["profile_segment_label"] == "效率型"
    assert operating_item["behavior_segment_label"] == "消息少于 2"
    assert operating_item["conversation_count"] == 1
    assert set(operating_item) == expected_dashboard_item_keys


def test_conversion_dashboard_payload_treats_operating_members_without_message_activity_match_as_zero_usage(app, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_missing_usage_001",
        phone="13800008109",
        owner_staff_id="sales_overview",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_missing_usage_001",
        audience_code="operating",
        entered_at="2026-04-10 10:00:00",
    )
    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={"13800008108": 1})

    with app.app_context():
        payload = get_conversion_dashboard_payload()

    operating_item = next(
        item
        for group in payload["audience_member_details"]["groups"]
        if group["audience_code"] == "operating"
        for item in group["items"]
        if item["external_contact_id"] == "wm_dashboard_missing_usage_001"
    )

    assert operating_item["behavior_segment_key"] == "lt_2"
    assert operating_item["behavior_segment_label"] == "消息少于 2"
    assert operating_item["conversation_count"] == 0


def test_conversion_dashboard_payload_keeps_pending_members_without_message_activity_match_unbucketed(app, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_pending_missing_usage_001",
        phone="13800008119",
        owner_staff_id="sales_overview",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_pending_missing_usage_001",
        audience_code="pending_questionnaire",
        entered_at="2026-04-10 10:00:00",
    )
    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={"13800008108": 1})

    with app.app_context():
        payload = get_conversion_dashboard_payload()

    pending_item = next(
        item
        for group in payload["audience_member_details"]["groups"]
        if group["audience_code"] == "pending_questionnaire"
        for item in group["items"]
        if item["external_contact_id"] == "wm_dashboard_pending_missing_usage_001"
    )

    assert pending_item["behavior_segment_key"] == ""
    assert pending_item["behavior_segment_label"] == ""
    assert pending_item["conversation_count"] == 0


def test_dashboard_questionnaire_status_prefers_latest_submission_truth_over_stale_member_mirror(app):
    from wecom_ability_service.domains.automation_conversion.workflow_runtime import sync_conversion_member_audience

    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=732)
    _save_signup_conversion_settings(
        app,
        questionnaire_id=int(questionnaire_seed["questionnaire_id"]),
        question_id=int(questionnaire_seed["choice_question_id"]),
        hit_option_ids=[int(questionnaire_seed["option_ids"][0])],
        core_threshold=1,
    )
    _seed_contact(
        app,
        external_userid="wm_dashboard_truth_001",
        mobile="13800008103",
        owner_userid="sales_overview",
        customer_name="问卷真相客户",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_truth_001",
        phone="13800008103",
        owner_staff_id="sales_overview",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    _seed_questionnaire_submission_for_member(
        app,
        questionnaire_id=int(questionnaire_seed["questionnaire_id"]),
        question_id=int(questionnaire_seed["choice_question_id"]),
        option_id=int(questionnaire_seed["option_ids"][0]),
        submission_id=73201,
        external_userid="wm_dashboard_truth_001",
        mobile_snapshot="13800008103",
        submitted_at="2026-04-10 12:34:56",
    )

    with app.app_context():
        db = get_db()
        member = dict(
            db.execute(
                """
                SELECT *
                FROM automation_member
                WHERE external_contact_id = ?
                """,
                ("wm_dashboard_truth_001",),
            ).fetchone()
        )
        assert member["questionnaire_status"] == "pending"
        audience_sync = sync_conversion_member_audience(member)
        stale_row = db.execute(
            """
            SELECT questionnaire_status, current_audience_code
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_dashboard_truth_001",),
        ).fetchone()
        payload = get_conversion_dashboard_payload()
        detail = get_member_detail(external_contact_id="wm_dashboard_truth_001")

    groups = {item["audience_code"]: item for item in payload["audience_member_details"]["groups"]}
    operating_item = next(
        item
        for item in groups["operating"]["items"]
        if item["external_contact_id"] == "wm_dashboard_truth_001"
    )

    assert audience_sync["audience_code"] == "operating"
    assert stale_row["questionnaire_status"] == "pending"
    assert stale_row["current_audience_code"] == "operating"
    assert operating_item["questionnaire_status"] == "submitted"
    assert operating_item["questionnaire_status_label"] == "已提交"
    assert set(operating_item) == {
        "member_id",
        "external_contact_id",
        "phone",
        "audience_code",
        "audience_label",
        "activation_status",
        "activation_status_label",
        "questionnaire_status",
        "questionnaire_status_label",
        "profile_segment_key",
        "profile_segment_label",
        "behavior_segment_key",
        "behavior_segment_label",
        "conversation_count",
    }
    assert detail["questionnaire"]["status"] == "submitted"
    assert detail["questionnaire"]["status_label"] == "已提交"
    assert detail["questionnaire"]["matched_questions"] == ["你当前更关注什么？"]
    assert set(detail["questionnaire"]) == {
        "status",
        "status_label",
        "hit_count",
        "matched_questions",
        "submitted_at",
    }


def test_dashboard_questionnaire_status_uses_latest_any_submission_when_signup_settings_are_unconfigured(app):
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=7321)
    _seed_contact(
        app,
        external_userid="wm_dashboard_truth_fallback_001",
        mobile="13800008113",
        owner_userid="sales_overview",
        customer_name="问卷回落真相客户",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_truth_fallback_001",
        phone="13800008113",
        owner_staff_id="sales_overview",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_truth_fallback_001",
        audience_code="operating",
        entered_at="2026-04-10 12:30:00",
    )
    _seed_questionnaire_submission_for_member(
        app,
        questionnaire_id=int(questionnaire_seed["questionnaire_id"]),
        question_id=int(questionnaire_seed["choice_question_id"]),
        option_id=int(questionnaire_seed["option_ids"][0]),
        submission_id=732101,
        external_userid="wm_dashboard_truth_fallback_001",
        mobile_snapshot="13800008113",
        submitted_at="2026-04-10 12:34:56",
    )

    with app.app_context():
        payload = get_conversion_dashboard_payload()
        detail = get_member_detail(external_contact_id="wm_dashboard_truth_fallback_001")

    groups = {item["audience_code"]: item for item in payload["audience_member_details"]["groups"]}
    operating_item = next(
        item
        for item in groups["operating"]["items"]
        if item["external_contact_id"] == "wm_dashboard_truth_fallback_001"
    )

    assert operating_item["questionnaire_status"] == "submitted"
    assert operating_item["questionnaire_status_label"] == "已提交"
    assert detail["questionnaire"]["status"] == "submitted"
    assert detail["questionnaire"]["status_label"] == "已提交"
    assert detail["questionnaire"]["submitted_at"] == "2026-04-10 12:34:56"


def test_invalid_enabled_profile_segment_template_is_exposed_without_silent_dashboard_fallback(app):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=733, template_name="脏启用模板")
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_invalid_template_001",
        phone="13800008104",
        owner_staff_id="sales_overview",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_invalid_template_001",
        audience_code="operating",
        entered_at="2026-04-10 12:00:00",
    )
    _seed_questionnaire_submission_for_member(
        app,
        questionnaire_id=int(template_seed["questionnaire_id"]),
        question_id=int(template_seed["choice_question_id"]),
        option_id=int(template_seed["option_ids"][0]),
        submission_id=73301,
        external_userid="wm_dashboard_invalid_template_001",
        mobile_snapshot="13800008104",
        submitted_at="2026-04-10 11:55:00",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "DELETE FROM questionnaire_questions WHERE id = ?",
            (int(template_seed["choice_question_id"]),),
        )
        db.commit()
        template_bundle = get_conversion_profile_segment_template_bundle(int(template_seed["template_id"]))
        payload = get_conversion_dashboard_payload()

    detail = payload["audience_member_details"]
    groups = {item["audience_code"]: item for item in detail["groups"]}
    operating_item = groups["operating"]["items"][0]

    assert template_bundle["validity"]["is_valid"] is False
    assert "segmentation_question_missing" in template_bundle["validity"]["reason_codes"]
    assert "enabled_category_without_mappings" in template_bundle["validity"]["reason_codes"]
    assert detail["profile_segment_template"]["valid"] is False
    assert detail["profile_segment_template"]["selection_status"] == "no_valid_enabled_template"
    assert detail["profile_segment_template"]["skipped_invalid_enabled_template_count"] == 1
    assert operating_item["profile_segment_label"] == ""


def test_invalid_latest_enabled_profile_segment_template_is_skipped_in_dashboard_selection(app):
    valid_seed = _seed_profile_segment_template(app, questionnaire_id=734, template_name="有效模板")
    invalid_seed = _seed_profile_segment_template(app, questionnaire_id=735, template_name="后建脏模板")
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_profile_selection_001",
        phone="13800008105",
        owner_staff_id="sales_overview",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_profile_selection_001",
        audience_code="operating",
        entered_at="2026-04-10 13:00:00",
    )
    _seed_questionnaire_submission_for_member(
        app,
        questionnaire_id=int(valid_seed["questionnaire_id"]),
        question_id=int(valid_seed["choice_question_id"]),
        option_id=int(valid_seed["option_ids"][0]),
        submission_id=73401,
        external_userid="wm_dashboard_profile_selection_001",
        mobile_snapshot="13800008105",
        submitted_at="2026-04-10 12:58:00",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "DELETE FROM questionnaire_questions WHERE id = ?",
            (int(invalid_seed["choice_question_id"]),),
        )
        db.commit()
        payload = get_conversion_dashboard_payload()

    detail = payload["audience_member_details"]
    groups = {item["audience_code"]: item for item in detail["groups"]}
    operating_item = groups["operating"]["items"][0]

    assert detail["profile_segment_template"]["template_name"] == "有效模板"
    assert detail["profile_segment_template"]["valid"] is True
    assert detail["profile_segment_template"]["selection_status"] == "selected"
    assert detail["profile_segment_template"]["skipped_invalid_enabled_template_count"] == 1
    assert operating_item["profile_segment_label"] == "效率型"


def test_dashboard_profile_segment_selection_prefers_latest_valid_enabled_template(app):
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=736)
    with app.app_context():
        create_conversion_profile_segment_template(
            {
                "template_name": "旧模板",
                "questionnaire_id": questionnaire_seed["questionnaire_id"],
                "segmentation_question_id": questionnaire_seed["choice_question_id"],
                "enabled": True,
                "categories": [
                    {
                        "category_key": "efficiency_old",
                        "category_name": "效率型旧版",
                        "option_ids": [questionnaire_seed["option_ids"][0]],
                    },
                    {
                        "category_key": "closing_old",
                        "category_name": "成交型旧版",
                        "option_ids": [questionnaire_seed["option_ids"][1]],
                    },
                ],
            },
            operator_id="tester",
        )
        latest_template = create_conversion_profile_segment_template(
            {
                "template_name": "新模板",
                "questionnaire_id": questionnaire_seed["questionnaire_id"],
                "segmentation_question_id": questionnaire_seed["choice_question_id"],
                "enabled": True,
                "categories": [
                    {
                        "category_key": "efficiency",
                        "category_name": "效率型新版",
                        "option_ids": [questionnaire_seed["option_ids"][0]],
                    },
                    {
                        "category_key": "closing",
                        "category_name": "成交型新版",
                        "option_ids": [questionnaire_seed["option_ids"][1]],
                    },
                ],
            },
            operator_id="tester",
        )

    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_profile_latest_001",
        phone="13800008106",
        owner_staff_id="sales_overview",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_profile_latest_001",
        audience_code="operating",
        entered_at="2026-04-10 14:00:00",
    )
    _seed_questionnaire_submission_for_member(
        app,
        questionnaire_id=int(questionnaire_seed["questionnaire_id"]),
        question_id=int(questionnaire_seed["choice_question_id"]),
        option_id=int(questionnaire_seed["option_ids"][0]),
        submission_id=73601,
        external_userid="wm_dashboard_profile_latest_001",
        mobile_snapshot="13800008106",
        submitted_at="2026-04-10 13:58:00",
    )

    with app.app_context():
        payload = get_conversion_dashboard_payload()

    detail = payload["audience_member_details"]
    groups = {item["audience_code"]: item for item in detail["groups"]}
    operating_item = groups["operating"]["items"][0]

    assert detail["profile_segment_template"]["template_name"] == "新模板"
    assert detail["profile_segment_template"]["selection_strategy"] == "latest_valid_enabled"
    assert detail["profile_segment_template"]["selection_status"] == "selected"
    assert detail["profile_segment_template"]["id"] == int(
        (((latest_template.get("template_bundle") or {}).get("template") or {}).get("id") or 0)
    )
    assert operating_item["profile_segment_label"] == "效率型新版"


def test_update_invalid_profile_segment_template_can_disable_it_without_repairing_structure(app):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=737, template_name="待停用脏模板")

    with app.app_context():
        db = get_db()
        db.execute(
            "DELETE FROM questionnaire_questions WHERE id = ?",
            (int(template_seed["choice_question_id"]),),
        )
        db.commit()
        result = update_conversion_profile_segment_template(
            int(template_seed["template_id"]),
            {
                "template_name": "待停用脏模板",
                "enabled": False,
            },
            operator_id="tester",
        )

    assert result["template_bundle"]["template"]["enabled"] is False
    assert result["template_bundle"]["template"]["valid"] is False
    assert result["template_bundle"]["validity"]["is_valid"] is False


def test_create_enabled_profile_segment_template_requires_enabled_category_mappings(app):
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=738)

    with app.app_context():
        with pytest.raises(ValueError, match="must bind at least one option"):
            create_conversion_profile_segment_template(
                {
                    "template_name": "无映射启用模板",
                    "questionnaire_id": questionnaire_seed["questionnaire_id"],
                    "segmentation_question_id": questionnaire_seed["choice_question_id"],
                    "enabled": True,
                    "categories": [
                        {
                            "category_key": "efficiency",
                            "category_name": "效率型",
                            "option_ids": [],
                        }
                    ],
                },
                operator_id="tester",
            )


def test_apply_dashboard_signup_tag_marks_current_audience_members(app, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_tag_001",
        phone="13800009101",
        owner_staff_id="sales_tag_01",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_tag_001",
        audience_code="pending_questionnaire",
        entered_at="2026-04-17 09:00:00",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_dashboard_tag_002",
        phone="13800009102",
        owner_staff_id="sales_tag_02",
        current_pool="active_normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    _assign_member_to_current_audience(
        app,
        external_contact_id="wm_dashboard_tag_002",
        audience_code="operating",
        entered_at="2026-04-17 09:30:00",
    )

    captured_calls: list[dict[str, object]] = []

    class _StubClient:
        def mark_external_contact_tags(
            self,
            *,
            external_userid: str,
            follow_user_userid: str,
            add_tags: list[str],
            remove_tags: list[str],
        ) -> dict[str, object]:
            captured_calls.append(
                {
                    "external_userid": external_userid,
                    "follow_user_userid": follow_user_userid,
                    "add_tags": list(add_tags),
                    "remove_tags": list(remove_tags),
                }
            )
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_service.get_app_runtime_client",
        lambda: _StubClient(),
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active, updated_at)
            VALUES
                ('tag-lead', '报名引流品', 'lead', 1, CURRENT_TIMESTAMP),
                ('tag-paid', '已报名999', 'paid_999', 1, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        payload = apply_dashboard_signup_tag(operator_id="overview-admin")

        assert payload["ok"] is True
        assert payload["target_tag_id"] == "tag-lead"
        assert payload["success_count"] == 2
        assert payload["failed_count"] == 0
        assert payload["skipped_count"] == 0
        assert captured_calls == [
            {
                "external_userid": "wm_dashboard_tag_001",
                "follow_user_userid": "sales_tag_01",
                "add_tags": ["tag-lead"],
                "remove_tags": ["tag-paid"],
            },
            {
                "external_userid": "wm_dashboard_tag_002",
                "follow_user_userid": "sales_tag_02",
                "add_tags": ["tag-lead"],
                "remove_tags": ["tag-paid"],
            },
        ]
        tag_rows = db.execute(
            """
            SELECT external_userid, userid, tag_id, tag_name
            FROM contact_tags
            ORDER BY external_userid ASC
            """
        ).fetchall()
        assert [dict(row) for row in tag_rows] == [
            {
                "external_userid": "wm_dashboard_tag_001",
                "userid": "sales_tag_01",
                "tag_id": "tag-lead",
                "tag_name": "报名引流品",
            },
            {
                "external_userid": "wm_dashboard_tag_002",
                "userid": "sales_tag_02",
                "tag_id": "tag-lead",
                "tag_name": "报名引流品",
            },
        ]


def test_overview_page_keeps_only_core_sections_and_removes_duplicate_action_nav(app, client):
    program_id = _default_program_id(app)
    response = client.get(f"/admin/automation-conversion/programs/{program_id}/overview")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动化转化当前运行状态" in html
    assert "任务流执行摘要" in html
    assert "刷新模块状态" in html
    assert "最近执行节点摘要" not in html
    assert "最近发送成功 / 失败摘要" not in html
    assert "进入自动化运营" not in html
    assert "进入自动化应答" not in html
    assert "进入模型 / Agent 配置" not in html
    assert "池子用户明细" in html
    assert "自然画像分层、行为画像分层、对话次数以及当前状态" in html
    assert 'id="overview-member-groups"' in html
    assert html.index('id="overview-member-groups"') < html.index('id="overview-execution-body"')
    assert "先看三类大人群规模、池子用户列表、启用中任务流和任务流执行情况" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/operations"' in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/flow-design"' in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/member-ops"' in html


def test_admin_overview_apply_signup_tag_endpoint_returns_json(app, client, monkeypatch):
    program_id = _default_program_id(app)
    action_token = _admin_action_token(client, f"/admin/automation-conversion/programs/{program_id}/overview")
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.apply_dashboard_signup_tag",
        lambda operator_id: {
            "ok": True,
            "target_tag_name": "报名引流品",
            "message": "已处理 2 个用户，成功打标 2 个，跳过 0 个，失败 0 个。",
        },
    )

    response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/overview/signup-tag/apply",
        data={"admin_action_token": action_token},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["target_tag_name"] == "报名引流品"
    assert "成功打标 2 个" in payload["message"]


def test_operations_split_pages_render_new_workflow_edit_nodes_and_execution_shells(app, client):
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="拆页回归任务流",
        status="draft",
        generation_mode="manual_layered",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)
    program_id = _default_program_id(app)

    new_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations/workflows/new")
    new_html = new_response.get_data(as_text=True)
    assert new_response.status_code == 200
    assert 'class="admin-topbar"' not in new_html
    assert "新建任务流" in new_html
    assert "第一步" in new_html
    assert "第二步" in new_html
    assert "当前页面只承载任务流编辑骨架。" not in new_html
    assert "保存并进入节点配置" in new_html
    assert "workflow-nodes-entry-button" not in new_html

    edit_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations/workflows/{workflow_id}/edit")
    edit_html = edit_response.get_data(as_text=True)
    assert edit_response.status_code == 200
    assert 'class="admin-topbar"' not in edit_html
    assert "编辑任务流" in edit_html
    assert "保存任务流" in edit_html
    assert "进入节点配置" in edit_html
    assert "返回列表" in edit_html
    assert f'href="/admin/automation-conversion/programs/{program_id}/operations/workflows/{workflow_id}/nodes"' in edit_html
    assert "当前页面只承载任务流编辑骨架。" not in edit_html
    assert "execution-table-body" not in edit_html
    assert "execution-items-body" not in edit_html

    nodes_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations/workflows/{workflow_id}/nodes")
    nodes_html = nodes_response.get_data(as_text=True)
    assert nodes_response.status_code == 200
    assert "节点配置" in nodes_html
    assert "返回任务流编辑" in nodes_html
    assert "新增节点" in nodes_html
    assert "当前只保留节点配置上下文" in nodes_html
    assert "execution-table-body" not in nodes_html
    assert "execution-items-body" not in nodes_html

    executions_response = client.get(f"/admin/automation-conversion/programs/{program_id}/executions")
    executions_html = executions_response.get_data(as_text=True)
    assert executions_response.status_code == 200
    assert 'class="admin-topbar"' not in executions_html
    assert "执行记录" in executions_html
    assert "执行批次" in executions_html
    assert "批次详情" in executions_html
    assert "返回自动化运营" in executions_html
    assert ">操作<" in executions_html
    assert ">agent_code<" not in executions_html
    assert ">send_record_id<" not in executions_html
    assert ">生成摘要<" not in executions_html
    assert "Asia/Shanghai" in executions_html
    assert "复制内容" in executions_html
    assert "自动化发送" in executions_html
    assert "当前页面只承载执行记录骨架。" not in executions_html


def test_execution_records_api_exposes_counts_from_execution_items(app, client):
    workflow_bundle = _create_test_workflow(app, workflow_name="执行统计任务流")
    workflow = dict((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {})
    workflow_id = int(workflow.get("id") or 0)
    program_id = int(workflow.get("program_id") or 0) or _default_program_id(app)

    with app.app_context():
        node_result = create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "统计节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "scheduled",
                "day_offset": 1,
                "send_time": "09:00",
                "standard_content_text": "提醒提交问卷",
                "enabled": True,
            },
            operator_id="tester",
        )
        node_id = int((node_result.get("node") or {}).get("id") or 0)

    for index in range(4):
        _seed_automation_member(
            app,
            external_contact_id=f"wm_exec_count_{index}",
            phone=f"1380000800{index}",
            current_pool="inactive_normal",
            questionnaire_status="pending",
        )

    with app.app_context():
        db = get_db()
        member_rows = db.execute(
            """
            SELECT id, external_contact_id
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_exec_count_%'
            ORDER BY id ASC
            """
        ).fetchall()
        inserted = db.execute(
            """
            INSERT INTO automation_workflow_execution (
                execution_id,
                program_id,
                workflow_id,
                node_id,
                trigger_type,
                audience_code,
                scheduled_for,
                status,
                total_count,
                success_count,
                skipped_count,
                failed_count,
                summary_json,
                created_at,
                updated_at,
                finished_at
            )
            VALUES (?, ?, ?, ?, 'scheduled_poll', 'pending_questionnaire', ?, 'finished', 0, 0, 0, 0, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            RETURNING id
            """,
            (
                "exec-counts-from-items",
                program_id,
                workflow_id,
                node_id,
                "2026-04-30 09:00:00",
                "2026-04-30 09:00:10",
            ),
        ).fetchone()
        execution_row_id = int(inserted["id"])
        statuses = ["sent", "sent", "failed", "skipped"]
        db.executemany(
            """
            INSERT INTO automation_workflow_execution_item (
                execution_id,
                workflow_id,
                node_id,
                member_id,
                external_contact_id,
                rendered_content_text,
                content_snapshot_json,
                status,
                error_message,
                sent_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, '提醒提交问卷', '{}', ?, '', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                (
                    execution_row_id,
                    workflow_id,
                    node_id,
                    int(row["id"]),
                    row["external_contact_id"],
                    status,
                    "2026-04-30 09:00:05" if status == "sent" else "",
                )
                for row, status in zip(member_rows, statuses)
            ],
        )
        db.commit()

    response = client.get(f"/api/admin/automation-conversion/executions?program_id={program_id}&limit=10")
    payload = response.get_json()
    assert response.status_code == 200
    row = next(item for item in payload["items"] if item["execution_id"] == "exec-counts-from-items")
    assert row["total_count"] == 4
    assert row["hit_count"] == 4
    assert row["success_count"] == 2
    assert row["sent_count"] == 2
    assert row["failed_count"] == 1
    assert row["skipped_count"] == 1

    detail_response = client.get(f"/api/admin/automation-conversion/executions/{execution_row_id}")
    detail_payload = detail_response.get_json()
    assert detail_response.status_code == 200
    assert detail_payload["summary"] == {
        "hit_count": 4,
        "success_count": 2,
        "failed_count": 1,
        "skipped_count": 1,
    }


def test_agent_config_page_renders_delete_button_for_agent_rows(app, client):
    _seed_test_agent_config(app, agent_code="custom_delete_agent", display_name="待删 Agent")

    response = client.get("/admin/automation-conversion/shared/agents")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-agent-delete="custom_delete_agent"' in html


def test_agent_delete_api_removes_unreferenced_custom_agent(app, client):
    _seed_test_agent_config(app, agent_code="custom_delete_agent", display_name="待删 Agent")
    action_token = _admin_action_token(client, "/admin/automation-conversion/shared/agents")

    response = client.delete(
        "/api/admin/automation-conversion/agents/custom_delete_agent",
        json={"admin_action_token": action_token},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["deleted"] is True
    with app.app_context():
        row = get_db().execute(
            "SELECT agent_code FROM automation_agent_config WHERE agent_code = ?",
            ("custom_delete_agent",),
        ).fetchone()
    assert row is None


def test_agent_delete_api_blocks_referenced_agent_with_clear_message(app, client):
    _seed_test_agent_config(app, agent_code="bound_delete_agent", display_name="绑定 Agent")
    _create_test_workflow(
        app,
        workflow_name="引用删除校验任务流",
        generation_mode="personalized_single",
        agent_bindings=[
            {
                "binding_scope": "personalized",
                "segment_key": "",
                "agent_code": "bound_delete_agent",
            }
        ],
    )
    action_token = _admin_action_token(client, "/admin/automation-conversion/shared/agents")

    response = client.delete(
        "/api/admin/automation-conversion/agents/bound_delete_agent",
        json={"admin_action_token": action_token},
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert "当前 Agent 已被任务流引用" in payload["error"]
    assert "引用删除校验任务流" in payload["error"]


def test_create_workflow_node_supports_immediate_trigger_mode(app):
    workflow_bundle = _create_test_workflow(app, workflow_name="即时节点工作流")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        result = create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "进入人群立即发",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "standard_content_text": "欢迎进入",
                "enabled": True,
            },
            operator_id="tester",
        )

    node = result["node"]
    assert node["trigger_mode"] == "audience_entered"
    assert node["day_offset"] == 1
    assert node["send_time"] == "00:00"


def test_create_workflow_node_supports_daily_recurring_trigger_mode(app):
    workflow_bundle = _create_test_workflow(app, workflow_name="每日轮巡节点工作流", audiences=["operating"])
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        result = create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "每日轮巡提醒",
                "target_audience_code": "operating",
                "trigger_mode": "daily_recurring",
                "day_offset": 3,
                "send_time": "14:00",
                "standard_content_text": "从第 3 天起每日提醒",
                "enabled": True,
            },
            operator_id="tester",
        )

    node = result["node"]
    assert node["trigger_mode"] == "daily_recurring"
    assert node["day_offset"] == 3
    assert node["send_time"] == "14:00"


def test_create_workflow_node_supports_immediate_personalized_single_with_one_agent_binding(app):
    _seed_test_agent_config(app, agent_code="welcome_agent", display_name="Welcome Agent")
    workflow_bundle = _create_test_workflow(app, workflow_name="立即单人定制节点工作流")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        result = create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "问卷提交后立即个性化发送",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_mode": "personalized_single",
                "agent_bindings": [
                    {
                        "binding_scope": "personalized",
                        "segment_key": "",
                        "agent_code": "welcome_agent",
                    }
                ],
                "enabled": True,
            },
            operator_id="tester",
        )

        saved_node = result["node"]
        binding_rows = get_db().execute(
            """
            SELECT binding_scope, segment_key, agent_code
            FROM automation_workflow_agent_binding
            WHERE workflow_id = ? AND node_id = ?
            ORDER BY id ASC
            """,
            (workflow_id, int(saved_node["id"])),
        ).fetchall()
        content_row = get_db().execute(
            """
            SELECT standard_content_text, standard_content_payload_json
            FROM automation_workflow_node_content
            WHERE node_id = ?
            LIMIT 1
            """,
            (int(saved_node["id"]),),
        ).fetchone()

    assert saved_node["trigger_mode"] == "audience_entered"
    assert saved_node["content_mode"] == "personalized_single"
    assert saved_node["segmentation_basis"] == "none"
    assert saved_node["standard_content_text"] == ""
    assert saved_node["agent_bindings"] == [
        {
            "id": saved_node["agent_bindings"][0]["id"],
            "node_id": saved_node["id"],
            "binding_scope": "personalized",
            "segment_key": "",
            "agent_code": "welcome_agent",
            "agent": saved_node["agent_bindings"][0]["agent"],
        }
    ]
    assert [dict(row) for row in binding_rows] == [
        {
            "binding_scope": "personalized",
            "segment_key": "",
            "agent_code": "welcome_agent",
        }
    ]
    assert dict(content_row)["standard_content_text"] == ""
    assert json.loads(dict(content_row)["standard_content_payload_json"])["_automation_conversion_node_meta"] == {
        "content_mode": "personalized_single",
        "segmentation_basis": "none",
    }


def test_create_workflow_node_rejects_manual_layered_without_variants(app):
    workflow_bundle = _create_test_workflow(app, workflow_name="手动分层校验工作流", segmentation_basis="behavior")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        with pytest.raises(ValueError, match="content_variants is required for manual_layered"):
            create_conversion_workflow_node(
                workflow_id,
                {
                    "node_name": "手动分层节点",
                    "target_audience_code": "pending_questionnaire",
                    "trigger_mode": "scheduled",
                    "day_offset": 2,
                    "send_time": "10:30",
                    "content_mode": "manual_layered",
                    "segmentation_basis": "behavior",
                    "content_variants": [],
                    "enabled": True,
                },
                operator_id="tester",
            )


def test_normalize_node_payload_standard_direct_uses_only_standard_content():
    normalized = _normalize_node_payload(
        {
            "node_name": "统一内容节点",
            "target_audience_code": "pending_questionnaire",
            "trigger_mode": "scheduled",
            "day_offset": 2,
            "send_time": "10:30",
            "standard_content_text": "统一标准内容",
            "content_variants": [
                {"segment_key": "lt_2", "content_text": "不应继续保留"},
            ],
            "enabled": True,
        },
        {
            "workflow": {
                "generation_mode": "legacy_standard_direct",
                "segmentation_basis": "none",
            },
            "audiences": [{"audience_code": "pending_questionnaire"}],
            "nodes": [],
        },
    )

    assert normalized["content_mode"] == "standard_direct"
    assert normalized["standard_content_text"] == "统一标准内容"
    assert normalized["content_variants"] == []


def test_create_workflow_node_manual_layered_profile_requires_every_active_variant_and_clears_standard_content(app, client):
    template_seed = _seed_profile_segment_template(app, questionnaire_id=713, template_name="节点分层录入模板")
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="画像分层节点校验",
        segmentation_basis="profile",
        content_segmentation_basis="profile",
        profile_segment_template_id=template_seed["template_id"],
        content_profile_segment_template_id=template_seed["template_id"],
        generation_mode="manual_layered",
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    incomplete_response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "画像分层节点",
            "target_audience_code": "pending_questionnaire",
            "trigger_mode": "scheduled",
            "day_offset": 1,
            "send_time": "09:30",
            "standard_content_text": "历史标准内容",
            "content_variants": [
                {
                    "segment_key": "efficiency",
                    "content_text": "效率型内容",
                }
            ],
            "enabled": True,
            "operator": "tester-profile-node",
        },
    )
    incomplete_payload = incomplete_response.get_json()

    assert incomplete_response.status_code == 400
    assert incomplete_payload["error"] == "manual_layered requires content for every active segmentation target"

    create_response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "画像分层节点",
            "target_audience_code": "pending_questionnaire",
            "trigger_mode": "scheduled",
            "day_offset": 1,
            "send_time": "09:30",
            "standard_content_text": "历史标准内容",
            "content_variants": [
                {
                    "segment_key": "efficiency",
                    "content_text": "效率型内容",
                },
                {
                    "segment_key": "closing",
                    "content_text": "成交型内容",
                },
            ],
            "enabled": True,
            "operator": "tester-profile-node",
        },
    )
    create_payload = create_response.get_json()

    assert create_response.status_code == 201
    assert create_payload["node"]["content_mode"] == "manual_layered"
    assert create_payload["node"]["segmentation_basis"] == "profile"
    assert create_payload["node"]["standard_content_text"] == ""
    assert sorted(item["segment_key"] for item in create_payload["node"]["content_variants"]) == ["closing", "efficiency"]

    with app.app_context():
        content_row = get_db().execute(
            """
            SELECT id, standard_content_text, fallback_to_standard_content
            FROM automation_workflow_node_content
            WHERE node_id = ?
            """,
            (int(create_payload["node"]["id"]),),
        ).fetchone()
        variant_rows = get_db().execute(
            """
            SELECT segment_key, content_text
            FROM automation_workflow_node_content_variant
            WHERE node_content_id = ?
            ORDER BY id ASC
            """,
            (int(content_row["id"]),),
        ).fetchall()

    assert dict(content_row)["standard_content_text"] == ""
    assert not bool(content_row["fallback_to_standard_content"])
    assert [dict(row) for row in variant_rows] == [
        {"segment_key": "efficiency", "content_text": "效率型内容"},
        {"segment_key": "closing", "content_text": "成交型内容"},
    ]


def test_workflow_node_detail_masks_manual_layered_dirty_standard_content_and_resave_cleans_it(app, client):
    workflow_bundle = _create_test_workflow(app, workflow_name="手动分层脏数据清理", segmentation_basis="behavior")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    create_response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "行为分层节点",
            "target_audience_code": "pending_questionnaire",
            "trigger_mode": "scheduled",
            "day_offset": 2,
            "send_time": "10:20",
            "content_variants": [
                {"segment_key": "lt_2", "content_text": "低行为内容"},
                {"segment_key": "between_2_9", "content_text": "中行为内容"},
                {"segment_key": "gte_10", "content_text": "高行为内容"},
            ],
            "enabled": True,
            "operator": "tester-node-dirty",
        },
    )
    create_payload = create_response.get_json()
    node_id = int((create_payload.get("node") or {}).get("id") or 0)

    assert create_response.status_code == 201

    with app.app_context():
        get_db().execute(
            """
            UPDATE automation_workflow_node_content
            SET standard_content_text = ?, fallback_to_standard_content = 1
            WHERE node_id = ?
            """,
            ("历史脏标准内容", node_id),
        )
        get_db().commit()

    detail_response = client.get(f"/api/admin/automation-conversion/workflows/{workflow_id}")
    detail_payload = detail_response.get_json()
    reopened_node = next(
        item for item in (((detail_payload.get("workflow_bundle") or {}).get("nodes")) or [])
        if int(item.get("id") or 0) == node_id
    )

    assert detail_response.status_code == 200
    assert reopened_node["content_mode"] == "manual_layered"
    assert reopened_node["standard_content_text"] == ""

    update_response = client.put(
        f"/api/admin/automation-conversion/workflow-nodes/{node_id}",
        json={
            "node_name": "行为分层节点",
            "target_audience_code": "pending_questionnaire",
            "trigger_mode": "scheduled",
            "day_offset": 2,
            "send_time": "10:20",
            "content_variants": [
                {"segment_key": "lt_2", "content_text": "低行为新内容"},
                {"segment_key": "between_2_9", "content_text": "中行为新内容"},
                {"segment_key": "gte_10", "content_text": "高行为新内容"},
            ],
            "enabled": True,
            "operator": "tester-node-dirty",
        },
    )
    update_payload = update_response.get_json()

    assert update_response.status_code == 200
    assert update_payload["node"]["standard_content_text"] == ""

    with app.app_context():
        refreshed_row = get_db().execute(
            """
            SELECT standard_content_text, fallback_to_standard_content
            FROM automation_workflow_node_content
            WHERE node_id = ?
            """,
            (node_id,),
        ).fetchone()

    assert dict(refreshed_row)["standard_content_text"] == ""
    assert not bool(refreshed_row["fallback_to_standard_content"])


def test_create_workflow_node_rejects_layered_rewrite_without_full_agent_bindings(app):
    _seed_test_agent_config(app, agent_code="welcome_agent", display_name="Welcome Agent")
    workflow_bundle = _create_test_workflow(app, workflow_name="分层改写校验工作流")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        with pytest.raises(ValueError, match="agent_bindings does not match expected segmentation targets"):
            create_conversion_workflow_node(
                workflow_id,
                {
                    "node_name": "改写节点",
                    "target_audience_code": "pending_questionnaire",
                    "trigger_mode": "scheduled",
                    "day_offset": 1,
                    "send_time": "09:15",
                    "content_mode": "standard_layered_rewrite",
                    "segmentation_basis": "behavior",
                    "standard_content_text": "请根据问卷结果改写这条消息",
                    "agent_bindings": [
                        {
                            "binding_scope": "behavior_tier",
                            "segment_key": "lt_2",
                            "agent_code": "welcome_agent",
                        }
                    ],
                    "enabled": True,
                },
                operator_id="tester",
            )


def test_workflow_node_api_supports_operating_immediate_personalized_single_with_questionnaire_submit_agent(app, client):
    _seed_test_agent_config(app, agent_code="questionnaire_followup_agent", display_name="问卷提交 agent")
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="问卷提交后进入运营中立即触发",
        audiences=["operating"],
        status="active",
        generation_mode="personalized_single",
        agent_bindings=[
            {
                "binding_scope": "personalized",
                "segment_key": "",
                "agent_code": "questionnaire_followup_agent",
            }
        ],
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "问卷提交后进入运营中立即发送",
            "target_audience_code": "operating",
            "trigger_mode": "audience_entered",
            "enabled": True,
            "operator": "tester-node-api",
        },
    )
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["node"]["target_audience_code"] == "operating"
    assert payload["node"]["trigger_mode"] == "audience_entered"
    assert payload["node"]["content_mode"] == "personalized_single"
    assert payload["node"]["segmentation_basis"] == "none"
    assert payload["node"]["standard_content_text"] == ""
    assert payload["node"]["agent_bindings"] == []

    with app.app_context():
        binding_rows = get_db().execute(
            """
            SELECT binding_scope, segment_key, agent_code
            FROM automation_workflow_agent_binding
            WHERE workflow_id = ? AND node_id = ?
            ORDER BY id ASC
            """,
            (workflow_id, int(payload["node"]["id"])),
        ).fetchall()

    assert [dict(row) for row in binding_rows] == [
        {
            "binding_scope": "personalized",
            "segment_key": "",
            "agent_code": "questionnaire_followup_agent",
        }
    ]


def test_workflow_node_api_rejects_immediate_trigger_with_day_offset_and_send_time(app, client):
    _seed_test_agent_config(app, agent_code="questionnaire_followup_agent", display_name="问卷提交 agent")
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="立即触发节点非法时间字段",
        audiences=["operating"],
        status="active",
        generation_mode="personalized_single",
        agent_bindings=[
            {
                "binding_scope": "personalized",
                "segment_key": "",
                "agent_code": "questionnaire_followup_agent",
            }
        ],
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "立即触发节点",
            "target_audience_code": "operating",
            "trigger_mode": "audience_entered",
            "day_offset": 1,
            "send_time": "09:00",
            "enabled": True,
            "operator": "tester-node-api",
        },
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "day_offset and send_time are not allowed when trigger_mode is audience_entered"


def test_workflow_node_api_rejects_personalized_single_when_workflow_agent_binding_is_missing(app, client):
    _seed_test_agent_config(app, agent_code="questionnaire_followup_agent", display_name="问卷提交 agent")
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="缺失 Agent 绑定的单人定制任务流",
        audiences=["operating"],
        status="active",
        generation_mode="personalized_single",
        agent_bindings=[
            {
                "binding_scope": "personalized",
                "segment_key": "",
                "agent_code": "questionnaire_followup_agent",
            }
        ],
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        get_db().execute(
            "DELETE FROM automation_workflow_agent_binding WHERE workflow_id = ? AND node_id IS NULL",
            (workflow_id,),
        )
        get_db().commit()

    response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "立即触发问卷跟进",
            "target_audience_code": "operating",
            "trigger_mode": "audience_entered",
            "enabled": True,
            "operator": "tester-node-api",
        },
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "workflow personalized_single requires exactly 1 agent_binding"


def test_workflow_node_api_reopens_personalized_single_agent_binding_from_workflow_detail(app, client):
    _seed_test_agent_config(app, agent_code="questionnaire_followup_agent", display_name="问卷提交 agent")
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="问卷提交个性化节点回显",
        audiences=["operating"],
        status="active",
        generation_mode="personalized_single",
        agent_bindings=[
            {
                "binding_scope": "personalized",
                "segment_key": "",
                "agent_code": "questionnaire_followup_agent",
            }
        ],
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    create_response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "立即触发问卷跟进",
            "target_audience_code": "operating",
            "trigger_mode": "audience_entered",
            "content_mode": "personalized_single",
            "agent_bindings": [
                {
                    "binding_scope": "personalized",
                    "segment_key": "",
                    "agent_code": "questionnaire_followup_agent",
                }
            ],
            "enabled": True,
            "operator": "tester-node-detail-reopen",
        },
    )
    create_payload = create_response.get_json()

    assert create_response.status_code == 201
    node_id = int((create_payload.get("node") or {}).get("id") or 0)

    detail_response = client.get(f"/api/admin/automation-conversion/workflows/{workflow_id}")
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    reopened_node = next(
        item for item in (((detail_payload.get("workflow_bundle") or {}).get("nodes")) or [])
        if int(item.get("id") or 0) == node_id
    )
    assert reopened_node["content_mode"] == "personalized_single"
    assert reopened_node["trigger_mode"] == "audience_entered"
    assert reopened_node["agent_bindings"] == []
    assert ((detail_payload.get("workflow_bundle") or {}).get("agent_bindings") or []) == [
        {
            "id": ((detail_payload.get("workflow_bundle") or {}).get("agent_bindings") or [])[0]["id"],
            "node_id": None,
            "binding_scope": "personalized",
            "segment_key": "",
            "agent_code": "questionnaire_followup_agent",
            "agent": ((detail_payload.get("workflow_bundle") or {}).get("agent_bindings") or [])[0]["agent"],
        }
    ]


def test_workflow_node_api_reopens_behavior_layered_rewrite_agent_bindings_from_workflow_detail(app, client):
    _seed_test_agent_config(app, agent_code="behavior_lt_2_agent", display_name="低行为 Agent")
    _seed_test_agent_config(app, agent_code="behavior_2_9_agent", display_name="中行为 Agent")
    _seed_test_agent_config(app, agent_code="behavior_10_agent", display_name="高行为 Agent")
    workflow_bundle = _create_test_workflow(
        app,
        workflow_name="行为分层改写节点回显",
        status="active",
        segmentation_basis="behavior",
        generation_mode="auto_layered_rewrite",
        agent_bindings=[
            {
                "binding_scope": "behavior_tier",
                "segment_key": "lt_2",
                "agent_code": "behavior_lt_2_agent",
            },
            {
                "binding_scope": "behavior_tier",
                "segment_key": "between_2_9",
                "agent_code": "behavior_2_9_agent",
            },
            {
                "binding_scope": "behavior_tier",
                "segment_key": "gte_10",
                "agent_code": "behavior_10_agent",
            },
        ],
    )
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    create_response = client.post(
        f"/api/admin/automation-conversion/workflows/{workflow_id}/nodes",
        json={
            "node_name": "行为分层改写节点",
            "target_audience_code": "pending_questionnaire",
            "trigger_mode": "scheduled",
            "day_offset": 2,
            "send_time": "10:15",
            "content_mode": "standard_layered_rewrite",
            "segmentation_basis": "behavior",
            "standard_content_text": "请根据行为层级改写内容",
            "agent_bindings": [
                {
                    "binding_scope": "behavior_tier",
                    "segment_key": "lt_2",
                    "agent_code": "behavior_lt_2_agent",
                },
                {
                    "binding_scope": "behavior_tier",
                    "segment_key": "between_2_9",
                    "agent_code": "behavior_2_9_agent",
                },
                {
                    "binding_scope": "behavior_tier",
                    "segment_key": "gte_10",
                    "agent_code": "behavior_10_agent",
                },
            ],
            "enabled": True,
            "operator": "tester-node-detail-reopen",
        },
    )
    create_payload = create_response.get_json()

    assert create_response.status_code == 201
    node_id = int((create_payload.get("node") or {}).get("id") or 0)

    detail_response = client.get(f"/api/admin/automation-conversion/workflows/{workflow_id}")
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    reopened_node = next(
        item for item in (((detail_payload.get("workflow_bundle") or {}).get("nodes")) or [])
        if int(item.get("id") or 0) == node_id
    )
    workflow_bindings = ((detail_payload.get("workflow_bundle") or {}).get("agent_bindings")) or []
    reopened_bindings = {(item["binding_scope"], item["segment_key"]): item["agent_code"] for item in workflow_bindings}

    assert reopened_node["content_mode"] == "standard_layered_rewrite"
    assert reopened_node["segmentation_basis"] == "behavior"
    assert reopened_node["standard_content_text"] == "请根据行为层级改写内容"
    assert reopened_node["agent_bindings"] == []
    assert reopened_bindings == {
        ("behavior_tier", "lt_2"): "behavior_lt_2_agent",
        ("behavior_tier", "between_2_9"): "behavior_2_9_agent",
        ("behavior_tier", "gte_10"): "behavior_10_agent",
    }


def test_run_due_conversion_workflows_runs_immediate_node_once_per_audience_entry(app, monkeypatch):
    _seed_contact(app, external_userid="wm_workflow_immediate_001", mobile="13800001111", owner_userid="sales_01", customer_name="立即节点客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_workflow_immediate_001",
        phone="13800001111",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="立即触发任务流", segmentation_basis="behavior")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "入池即发",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_variants": [
                    {"segment_key": "lt_2", "content_text": "欢迎进入自动化任务流"},
                    {"segment_key": "between_2_9", "content_text": "欢迎进入自动化任务流"},
                    {"segment_key": "gte_10", "content_text": "欢迎进入自动化任务流"},
                ],
                "enabled": True,
            },
            operator_id="tester",
        )

    dispatched: list[dict[str, object]] = []
    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={"13800001111": 1})
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 901, "wecom_result": {"msgid": "msg-901"}},
    )

    with app.app_context():
        first = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        second = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_rows = get_db().execute(
            """
            SELECT execution_id, total_count, success_count, status, scheduled_for
            FROM automation_workflow_execution
            ORDER BY id ASC
            """
        ).fetchall()
        item_rows = get_db().execute(
            """
            SELECT status, audience_entry_id, rendered_content_text
            FROM automation_workflow_execution_item
            ORDER BY id ASC
            """
        ).fetchall()

    assert first["ok"] is True
    assert second["ok"] is True
    assert len(dispatched) == 1
    assert len(execution_rows) == 1
    assert execution_rows[0]["status"] == "finished"
    assert execution_rows[0]["success_count"] == 1
    assert execution_rows[0]["scheduled_for"] == "2026-04-08 10:00:00"
    assert len(item_rows) == 1
    assert item_rows[0]["status"] == "sent"
    assert item_rows[0]["audience_entry_id"] is not None
    assert item_rows[0]["rendered_content_text"] == "欢迎进入自动化任务流"

def test_run_due_conversion_workflows_manual_layered_does_not_fallback_to_standard_content(app, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_no_fallback_001", mobile="13800004444", owner_userid="sales_01", customer_name="纯分层客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_no_fallback_001",
        phone="13800004444",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="手动分层无回退", segmentation_basis="behavior")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "纯分层节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_variants": [
                    {"segment_key": "lt_2", "content_text": "低行为内容"},
                    {"segment_key": "between_2_9", "content_text": "中行为内容"},
                    {"segment_key": "gte_10", "content_text": "高行为内容"},
                ],
                "enabled": True,
            },
            operator_id="tester",
        )
        node_id = int(
            get_db().execute(
                """
                SELECT id
                FROM automation_workflow_node
                WHERE workflow_id = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (workflow_id,),
            ).fetchone()["id"]
        )
        get_db().execute(
            """
            UPDATE automation_workflow_node_content
            SET standard_content_text = ?, fallback_to_standard_content = 1
            WHERE node_id = ?
            """,
            ("历史回退内容", node_id),
        )
        get_db().commit()

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime._resolve_behavior_segment_match",
        lambda member: {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "segment_not_matched",
            "message_count": 0,
        },
    )

    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 902, "wecom_result": {"msgid": "msg-902"}},
    )

    with app.app_context():
        result = run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        item_row = get_db().execute(
            """
            SELECT status, error_message, rendered_content_text, content_snapshot_json
            FROM automation_workflow_execution_item
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()

    snapshot = json.loads(item_row["content_snapshot_json"])

    assert result["ok"] is True
    assert dispatched == []
    assert dict(item_row)["status"] == "failed"
    assert dict(item_row)["error_message"] == "rendered_content_empty"
    assert dict(item_row)["rendered_content_text"] == ""
    assert snapshot["standard_content_text"] == ""
    assert snapshot["fallback_reason"] == "segment_not_matched"
    assert snapshot["content_source"] == ""
def test_send_conversion_execution_item_via_bazhuayu_posts_signed_webhook_payload(app, monkeypatch):
    _seed_contact(app, external_userid="wm_bazhuayu_send_001", mobile="13800002222", owner_userid="sales_01", customer_name="八爪鱼发送客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_bazhuayu_send_001",
        phone="13800002222",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 10:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="八爪鱼发送任务流", segmentation_basis="behavior")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "入池后触发八爪鱼发送",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_variants": [
                    {"segment_key": "lt_2", "content_text": "欢迎体验自动化发送能力"},
                    {"segment_key": "between_2_9", "content_text": "欢迎体验自动化发送能力"},
                    {"segment_key": "gte_10", "content_text": "欢迎体验自动化发送能力"},
                ],
                "enabled": True,
            },
            operator_id="tester",
        )

    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={"13800002222": 1})
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 1001, "wecom_result": {"msgid": "msg-1001"}},
    )

    with app.app_context():
        run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_item_id = int(
            get_db().execute(
                """
                SELECT id
                FROM automation_workflow_execution_item
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()["id"]
        )

    recorded_requests: list[dict[str, object]] = []

    class _BazhuayuResponse:
        ok = True
        status_code = 200
        text = '{"code":0,"message":"ok"}'

        def json(self):
            return {"code": 0, "message": "ok"}

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        recorded_requests.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _BazhuayuResponse()

    fixed_timestamp = 1713241810
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.time.time", lambda: fixed_timestamp)
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.requests.post", _fake_post)

    with app.app_context():
        result = send_conversion_execution_item_via_bazhuayu(execution_item_id, operator_id="bazhuayu-tester")

    expected_timestamp = str(fixed_timestamp)
    expected_secret = "mPwS+MOxF0O9dyED6z5LlA=="
    expected_sign = base64.b64encode(
        hmac.new(f"{expected_timestamp}\n{expected_secret}".encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")

    assert len(recorded_requests) == 1
    assert recorded_requests[0]["url"] == "https://api-rpa.bazhuayu.com/api/v1/bots/webhooks/69cc9c20612e78c4472b2f4d/invoke"
    assert recorded_requests[0]["headers"] == {"Content-Type": "application/json"}
    assert recorded_requests[0]["timeout"] == 15
    assert recorded_requests[0]["json"] == {
        "sign": expected_sign,
        "params": {
            "userid": "wm_bazhuayu_send_001",
            "text": "欢迎体验自动化发送能力",
        },
        "timestamp": expected_timestamp,
    }
    assert result == {
        "ok": True,
        "execution_item_id": execution_item_id,
        "requested_by": "bazhuayu-tester",
        "request": {
            "userid": "wm_bazhuayu_send_001",
            "text": "欢迎体验自动化发送能力",
            "timestamp": expected_timestamp,
            "specified_bot": "",
        },
        "response": {"code": 0, "message": "ok"},
    }


def test_execution_item_send_via_bazhuayu_api_accepts_admin_action_token_and_returns_payload(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_bazhuayu_api_001", mobile="13800003333", owner_userid="sales_01", customer_name="八爪鱼接口客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_bazhuayu_api_001",
        phone="13800003333",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 11:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="八爪鱼接口任务流", segmentation_basis="behavior")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)

    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "接口发送节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_variants": [
                    {"segment_key": "lt_2", "content_text": "接口触发自动化发送"},
                    {"segment_key": "between_2_9", "content_text": "接口触发自动化发送"},
                    {"segment_key": "gte_10", "content_text": "接口触发自动化发送"},
                ],
                "enabled": True,
            },
            operator_id="tester",
        )

    _mock_workflow_runtime_usage_counts(monkeypatch, usage_by_phone={"13800003333": 1})
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 1002, "wecom_result": {"msgid": "msg-1002"}},
    )

    with app.app_context():
        run_due_conversion_workflows(operator_id="workflow-runner", operator_type="system")
        execution_item_id = int(
            get_db().execute(
                """
                SELECT id
                FROM automation_workflow_execution_item
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()["id"]
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_service.requests.post",
        lambda *args, **kwargs: type(
            "_BazhuayuResponse",
            (),
            {
                "ok": True,
                "status_code": 200,
                "text": '{"code":0,"message":"ok"}',
                "json": lambda self: {"code": 0, "message": "ok"},
            },
        )(),
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.time.time", lambda: 1713241999)

    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    response = client.post(
        f"/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
        json={
            "admin_action_token": "test-token",
            "operator": "console-user",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["execution_item_id"] == execution_item_id
    assert payload["requested_by"] == "console-user"
    assert payload["request"]["userid"] == "wm_bazhuayu_api_001"
    assert payload["request"]["text"] == "接口触发自动化发送"
    assert payload["response"] == {"code": 0, "message": "ok"}

def test_send_agent_reply_output_via_bazhuayu_posts_signed_webhook_payload(app, monkeypatch):
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-reply-bazhuayu-001",
                "request_id": "req-reply-bazhuayu-001",
                "userid": "sales_agent",
                "external_contact_id": "wm_reply_bazhuayu_send_001",
                "agent_code": "welcome_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "status": "success",
                "source": "test",
            }
        )
        output = append_agent_output(
            {
                "output_id": "aout-reply-bazhuayu-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wm_reply_bazhuayu_send_001",
                "agent_code": "welcome_agent",
                "output_type": "agent_reply_draft",
                "raw_output_text": "欢迎体验最近话术自动发送",
                "normalized_output": {"draft_reply": "欢迎体验最近话术自动发送"},
                "rendered_output_text": "欢迎体验最近话术自动发送",
                "target_agent_code": "welcome_agent",
                "target_pool": "new_user",
                "confidence": 0.91,
                "reason": "新用户欢迎",
                "applied_status": "generated",
            }
        )

    recorded_requests: list[dict[str, object]] = []

    class _BazhuayuResponse:
        ok = True
        status_code = 200
        text = '{"code":0,"message":"ok"}'

        def json(self):
            return {"code": 0, "message": "ok"}

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        recorded_requests.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _BazhuayuResponse()

    fixed_timestamp = 1713242888
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.time.time", lambda: fixed_timestamp)
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.requests.post", _fake_post)

    with app.app_context():
        result = send_agent_reply_output_via_bazhuayu(output["output_id"], operator_id="bazhuayu-tester")

    expected_timestamp = str(fixed_timestamp)
    expected_secret = "mPwS+MOxF0O9dyED6z5LlA=="
    expected_sign = base64.b64encode(
        hmac.new(f"{expected_timestamp}\n{expected_secret}".encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")

    assert len(recorded_requests) == 1
    assert recorded_requests[0]["url"] == "https://api-rpa.bazhuayu.com/api/v1/bots/webhooks/69cc9c20612e78c4472b2f4d/invoke"
    assert recorded_requests[0]["headers"] == {"Content-Type": "application/json"}
    assert recorded_requests[0]["timeout"] == 15
    assert recorded_requests[0]["json"] == {
        "sign": expected_sign,
        "params": {
            "userid": "wm_reply_bazhuayu_send_001",
            "text": "欢迎体验最近话术自动发送",
        },
        "timestamp": expected_timestamp,
    }
    assert result == {
        "ok": True,
        "output_id": "aout-reply-bazhuayu-001",
        "requested_by": "bazhuayu-tester",
        "request": {
            "userid": "wm_reply_bazhuayu_send_001",
            "text": "欢迎体验最近话术自动发送",
            "timestamp": expected_timestamp,
            "specified_bot": "",
        },
        "response": {"code": 0, "message": "ok"},
    }


def test_review_output_send_via_bazhuayu_api_accepts_admin_action_token_and_returns_payload(app, client, monkeypatch):
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-reply-api-001",
                "request_id": "req-reply-api-001",
                "userid": "sales_agent",
                "external_contact_id": "wm_reply_bazhuayu_api_001",
                "agent_code": "welcome_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "status": "success",
                "source": "test",
            }
        )
        output = append_agent_output(
            {
                "output_id": "aout-reply-api-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wm_reply_bazhuayu_api_001",
                "agent_code": "welcome_agent",
                "output_type": "agent_reply_draft",
                "raw_output_text": "接口触发最近话术自动发送",
                "normalized_output": {"draft_reply": "接口触发最近话术自动发送"},
                "rendered_output_text": "接口触发最近话术自动发送",
                "target_agent_code": "welcome_agent",
                "target_pool": "new_user",
                "confidence": 0.9,
                "reason": "欢迎语",
                "applied_status": "generated",
            }
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_service.requests.post",
        lambda *args, **kwargs: type(
            "_BazhuayuResponse",
            (),
            {
                "ok": True,
                "status_code": 200,
                "text": '{"code":0,"message":"ok"}',
                "json": lambda self: {"code": 0, "message": "ok"},
            },
        )(),
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.time.time", lambda: 1713242999)

    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    response = client.post(
        f"/api/admin/automation-conversion/review-outputs/{output['output_id']}/send-via-bazhuayu",
        json={
            "admin_action_token": "test-token",
            "operator": "console-user",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["output_id"] == output["output_id"]
    assert payload["requested_by"] == "console-user"
    assert payload["request"]["userid"] == "wm_reply_bazhuayu_api_001"
    assert payload["request"]["text"] == "接口触发最近话术自动发送"
    assert payload["response"] == {"code": 0, "message": "ok"}


def test_laohuang_review_outputs_api_lists_jobs_and_webhook_action_posts_payload(app, client, monkeypatch):
    with app.app_context():
        row = get_db().execute(
            """
            INSERT INTO automation_laohuang_chat_job (
                queue_id, member_id, external_contact_id, phone, external_message_id, external_session_id,
                laohuang_task_id, request_payload_json, accepted_payload_json, callback_payload_json,
                status, reply_text, send_channel, send_result_json, created_at, updated_at, finished_at
            )
            VALUES (NULL, NULL, 'wm_lh_webhook_001', '13800009213', 'ai-crm:reply-monitor:323:656',
                    'ai-crm:wm_lh_webhook_001', 'lh-task-webhook-001', '{}', '{}', '{}',
                    'callback_success', '推 webhook 的话术', 'private_message', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """
        ).fetchone()
        job_id = int(row["id"])
        get_db().commit()

    list_response = client.get("/api/admin/automation-conversion/review-outputs")
    list_payload = list_response.get_json()

    assert list_response.status_code == 200
    assert list_payload["source"] == "laohuang_chat_job"
    assert list_payload["rows"][0]["output_id"] == f"lhjob-{job_id}"
    assert list_payload["rows"][0]["agent_code"] == "laohuang_chat"
    assert list_payload["rows"][0]["rendered_output_text"] == "推 webhook 的话术"

    recorded_requests: list[dict[str, object]] = []

    class _BazhuayuResponse:
        ok = True
        status_code = 200
        text = '{"code":0,"message":"ok"}'

        def json(self):
            return {"code": 0, "message": "ok"}

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        recorded_requests.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _BazhuayuResponse()

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.requests.post", _fake_post)
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.workflow_service.time.time", lambda: 1713243999)

    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    webhook_response = client.post(
        f"/api/admin/automation-conversion/review-outputs/lhjob-{job_id}/send-via-webhook",
        json={
            "admin_action_token": "test-token",
            "operator": "console-user",
        },
    )
    webhook_payload = webhook_response.get_json()

    assert webhook_response.status_code == 200
    assert webhook_payload["ok"] is True
    assert webhook_payload["job_id"] == job_id
    assert webhook_payload["request"]["userid"] == "wm_lh_webhook_001"
    assert webhook_payload["request"]["text"] == "推 webhook 的话术"
    assert recorded_requests[0]["json"]["params"] == {
        "userid": "wm_lh_webhook_001",
        "text": "推 webhook 的话术",
    }
    with app.app_context():
        job_row = get_db().execute(
            "SELECT status, send_result_json FROM automation_laohuang_chat_job WHERE id = ? LIMIT 1",
            (job_id,),
        ).fetchone()
    assert dict(job_row)["status"] == "callback_success"
    assert json.loads(dict(job_row)["send_result_json"])["webhook"]["request"]["text"] == "推 webhook 的话术"


def _test_png_data_url() -> str:
    encoded = base64.b64encode(_test_png_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _save_sop_template(
    app,
    *,
    pool_key: str,
    day_index: int,
    content: str = "",
    images_json: list[dict[str, object]] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    with app.app_context():
        return save_sop_v1_template(
            pool_key=_canonical_automation_pool(pool_key),
            day_index=day_index,
            content=content,
            images_json=list(images_json or []),
            enabled=enabled,
        )


def _patch_live_context(
    monkeypatch,
    *,
    external_contact_id: str,
    phone: str,
    owner_staff_id: str = "sales_01",
    activation_status: str = "active",
    questionnaire_status: str = "submitted",
    questionnaire_follow_type: str = "normal",
):
    def _fake_build_live_context(request_external_contact_id: str = "", request_phone: str = "") -> dict:
        resolved_external_contact_id = external_contact_id or request_external_contact_id
        resolved_phone = phone or request_phone
        return {
            "lookup": {
                "external_contact_id": resolved_external_contact_id,
                "phone": resolved_phone,
                "master_customer_id": None,
                "external_contact_ids": [resolved_external_contact_id] if resolved_external_contact_id else [],
            },
            "profile": {
                "external_contact_id": resolved_external_contact_id,
                "phone": resolved_phone,
                "customer_name": resolved_external_contact_id or resolved_phone or "测试客户",
                "owner_staff_id": owner_staff_id,
                "owner_display_name": owner_staff_id,
                "unionid": "",
            },
            "activation": {
                "activation_status": activation_status,
                "last_activation_at": "2026-04-06 09:30:00" if activation_status == "active" else "",
            },
            "questionnaire": {
                "questionnaire_status": questionnaire_status,
                "resolved_follow_type": questionnaire_follow_type if questionnaire_status == "submitted" else "",
                "hit_count": 1 if questionnaire_follow_type == "focus" else 0,
                "matched_question_ids": [1] if questionnaire_follow_type == "focus" else [],
                "matched_questions": ["关键题"] if questionnaire_follow_type == "focus" else [],
                "answers": [],
                "submitted_at": "2026-04-06 09:00:00" if questionnaire_status == "submitted" else "",
                "questionnaire_id": 1 if questionnaire_status == "submitted" else None,
            },
        }

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service._build_live_context",
        _fake_build_live_context,
    )


def test_init_db_creates_automation_conversion_tables_and_indexes(app):
    with app.app_context():
        db = get_db()
        table_names = _sqlite_object_names(db, "table")
        index_names = _sqlite_object_names(db, "index")
        channel_columns = _sqlite_table_columns(db, "automation_channel")
        agent_output_columns = _sqlite_table_columns(db, "automation_agent_output")

        assert {
            "automation_channel",
            "automation_member",
            "automation_event",
            "automation_ai_push_log",
            "automation_agent_router_config",
            "automation_agent_config",
            "automation_agent_skill_registry",
            "automation_agent_run",
            "automation_agent_output",
            "automation_agent_output_export_job",
            "automation_agent_skill_call_audit",
            "automation_message_activity_sync_run",
            "automation_message_activity_sync_item",
            "automation_reply_monitor_config",
            "automation_reply_monitor_queue",
            "automation_laohuang_chat_job",
            "automation_focus_send_batch",
            "automation_focus_send_batch_item",
            "automation_touch_delivery_log",
            "automation_sop_pool_config",
            "automation_sop_template",
            "automation_sop_progress",
            "automation_sop_batch",
            "automation_sop_batch_item",
        }.issubset(table_names)
        assert {
            "uq_automation_member_external_non_empty",
                "idx_automation_member_phone",
                "idx_automation_member_pool",
                "idx_automation_event_member_created",
                "idx_automation_ai_push_log_status",
                "idx_automation_agent_router_config_updated",
                "idx_automation_agent_config_enabled",
                "idx_automation_agent_config_updated",
                "idx_automation_agent_skill_registry_enabled",
                "idx_automation_agent_run_request",
                "idx_automation_agent_run_user",
                "idx_automation_agent_run_agent_created",
                "idx_automation_agent_output_request",
                "idx_automation_agent_output_user",
                "idx_automation_agent_output_agent_type",
                "idx_automation_agent_output_applied",
                "idx_automation_agent_output_target_agent",
                "idx_automation_agent_output_outcome_status",
                "idx_automation_agent_output_export_job_status",
                "idx_automation_agent_skill_call_audit_skill_created",
            "idx_automation_message_activity_sync_run_finished",
            "idx_automation_message_activity_sync_item_run",
            "idx_automation_message_activity_sync_item_match_key",
            "idx_automation_reply_monitor_config_updated",
            "idx_automation_reply_monitor_queue_status_due",
            "idx_automation_reply_monitor_queue_external_updated",
            "uq_automation_reply_monitor_queue_active_external",
            "uq_automation_laohuang_chat_job_external_message",
            "idx_automation_laohuang_chat_job_task",
            "idx_automation_laohuang_chat_job_status_updated",
            "idx_automation_laohuang_chat_job_queue",
            "idx_automation_focus_send_batch_stage_status",
            "idx_automation_focus_send_batch_item_batch_position",
            "uq_automation_touch_delivery_active",
            "idx_automation_touch_delivery_external",
            "idx_automation_touch_delivery_source",
            "idx_automation_sop_pool_config_updated",
            "uq_automation_sop_template_pool_day",
            "uq_automation_sop_progress_member_pool",
            "idx_automation_sop_batch_status_scheduled",
            "idx_automation_sop_batch_item_batch_created",
            "uq_automation_sop_batch_item_member_pool_day_success",
        }.issubset(index_names)
        assert {"adopted_by", "adopted_action", "adopted_at", "outcome_status", "outcome_value"}.issubset(agent_output_columns)
        assert {"entry_tag_id", "entry_tag_name", "entry_tag_group_name"}.issubset(channel_columns)


def test_automation_overview_counts_only_from_automation_member(app, client):
    rows = [
        ("wm_overview_001", "13800001001", "sales_01", 1, "new_user", "", "unknown", "pending", "2026-04-06 09:00:00"),
        ("wm_overview_002", "13800001002", "sales_01", 1, "inactive_normal", "normal", "inactive", "submitted", "2026-04-06 09:10:00"),
        ("wm_overview_003", "13800001003", "sales_01", 1, "inactive_focus", "focus", "inactive", "submitted", "2026-04-05 09:20:00"),
        ("wm_overview_004", "13800001004", "sales_01", 1, "silent", "normal", "inactive", "submitted", "2026-04-05 09:30:00"),
        ("wm_overview_005", "13800001005", "sales_01", 0, "won", "focus", "active", "submitted", "2026-04-06 09:40:00"),
    ]
    for external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type, activation_status, questionnaire_status, joined_at in rows:
        _seed_automation_member(
            app,
            external_contact_id=external_contact_id,
            phone=phone,
            owner_staff_id=owner_staff_id,
            in_pool=in_pool,
            current_pool=current_pool,
            follow_type=follow_type,
            activation_status=activation_status,
            questionnaire_status=questionnaire_status,
            decision_source="system",
            source_type="system",
            joined_at=joined_at,
        )

    with app.app_context():
        payload = get_overview_payload()

    counts = payload["counts"]
    assert counts["in_pool_total"] == 4
    assert counts["questionnaire_pending"] == 1
    assert counts["operating_total"] == 3
    assert counts["converted_total"] == 1
    stage_totals = {item["pool"]: item["total_count"] for item in payload["stage_columns"]}
    assert stage_totals["pending_questionnaire"] == 1
    assert stage_totals["operating"] == 3
    assert stage_totals["converted"] == 1


def test_automation_member_actions_write_events(app, client):
    _seed_contact(app, external_userid="wm_action_001", mobile="13800002001", owner_userid="sales_11", customer_name="动作客户")

    put_response = client.post(
        "/api/admin/automation-conversion/member/put-in-pool",
        json={"external_contact_id": "wm_action_001", "operator": "tester"},
    )
    set_focus_response = client.post(
        "/api/admin/automation-conversion/member/set-focus",
        json={"external_contact_id": "wm_action_001", "operator": "tester"},
    )
    mark_won_response = client.post(
        "/api/admin/automation-conversion/member/mark-won",
        json={"external_contact_id": "wm_action_001", "operator": "tester"},
    )

    assert put_response.status_code == 200
    assert set_focus_response.status_code == 200
    assert mark_won_response.status_code == 200

    with app.app_context():
        db = get_db()
        member = db.execute(
            "SELECT * FROM automation_member WHERE external_contact_id = ?",
            ("wm_action_001",),
        ).fetchone()
        assert member is not None
        assert member["in_pool"] == 1
        assert member["current_pool"] == "converted"
        assert member["source_type"] == "manual"
        events = db.execute(
            """
            SELECT action, operator_type, operator_id
            FROM automation_event
            WHERE member_id = ?
            ORDER BY id ASC
            """,
            (member["id"],),
        ).fetchall()
        assert [row["action"] for row in events] == ["put_in_pool", "set_focus", "mark_won"]
        assert {row["operator_type"] for row in events} == {"user"}
        assert {row["operator_id"] for row in events} == {"tester"}


def test_openclaw_push_accepts_and_enforces_cooldown(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_ai_001", mobile="13800003001", owner_userid="sales_ai", customer_name="AI 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_ai_001",
        phone="13800003001",
        owner_staff_id="sales_ai",
        current_pool="active_focus",
        follow_type="focus",
        questionnaire_status="submitted",
        decision_source="manual",
        source_type="manual",
        joined_at="2026-04-06 10:00:00",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload",
        lambda *, external_userid: {"tags": [{"tag_name": "高潜客户"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload",
        lambda *, external_userid="", mobile="": {
            "answers": [{"question": "预算", "answer": "999"}],
        },
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "messages": [
                {"sender": "wm_ai_001", "send_time": "2026-04-06 10:01:00", "content": "我想看看方案"},
                {"sender": "sales_ai", "send_time": "2026-04-06 10:02:00", "content": "可以，先看这个版本"},
            ],
        },
    )

    captured = {}

    def _fake_send_outbound_webhook(*, event_type, payload, source_key, source_id):
        captured["event_type"] = event_type
        captured["payload"] = payload
        captured["source_key"] = source_key
        captured["source_id"] = source_id
        return {"ok": True, "delivery": {"id": 701}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook",
        _fake_send_outbound_webhook,
    )

    first = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wm_ai_001", "operator": "tester-ai"},
    )
    second = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wm_ai_001", "operator": "tester-ai"},
    )

    assert first.status_code == 202
    assert first.get_json()["status"] == "accepted"
    assert second.status_code == 429
    assert second.get_json()["status"] == "cooldown_blocked"
    assert captured["source_key"] == "automation_member"
    assert captured["source_id"].isdigit()
    assert captured["event_type"] == "openclaw_focus_message"
    assert set(captured["payload"].keys()) == {
        "externalContactId",
        "currentPool",
        "currentStage",
        "currentTarget",
        "tags",
        "questionnaire",
        "recentChats",
    }
    assert captured["payload"]["externalContactId"] == "wm_ai_001"
    assert captured["payload"]["tags"] == ["高潜客户"]
    assert captured["payload"]["questionnaire"]["answers"] == [{"question": "预算", "answer": "999"}]
    assert len(captured["payload"]["recentChats"]) == 2

    with app.app_context():
        db = get_db()
        member = db.execute(
            "SELECT last_ai_push_at, ai_cooldown_until FROM automation_member WHERE external_contact_id = ?",
            ("wm_ai_001",),
        ).fetchone()
        assert member["last_ai_push_at"]
        assert member["ai_cooldown_until"]
        logs = db.execute(
            "SELECT status, request_payload FROM automation_ai_push_log ORDER BY id ASC"
        ).fetchall()
        assert [row["status"] for row in logs] == ["accepted", "cooldown_blocked"]
        accepted_payload = json.loads(logs[0]["request_payload"])
        assert accepted_payload["externalContactId"] == "wm_ai_001"
        assert accepted_payload["currentPool"] == captured["payload"]["currentPool"]
        assert accepted_payload["currentStage"] == captured["payload"]["currentStage"]
        assert accepted_payload["currentTarget"] == captured["payload"]["currentTarget"]
        assert accepted_payload["questionnaire"]["answers"] == [{"question": "预算", "answer": "999"}]


def test_openclaw_push_uses_canonical_operating_member_before_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_ai_keep_001", mobile="13800003011", owner_userid="sales_ai", customer_name="AI 稳定客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_ai_keep_001",
        phone="13800003011",
        owner_staff_id="sales_ai",
        in_pool=1,
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
        decision_source="system",
        source_type="message_activity_sync",
        joined_at="2026-04-06 10:00:00",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_ai_keep_001",
        phone="13800003011",
        owner_staff_id="sales_ai",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload",
        lambda *, external_userid: {"tags": [{"tag_name": "重点客户"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload",
        lambda *, external_userid="", mobile="": {"answers": [{"question": "预算", "answer": "999"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "messages": [{"sender": "wm_ai_keep_001", "send_time": "2026-04-06 10:01:00", "content": "我想看看方案"}],
        },
    )

    captured = {}

    def _fake_send_outbound_webhook(*, event_type, payload, source_key, source_id):
        captured["payload"] = payload
        return {"ok": True, "delivery": {"id": 702}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook",
        _fake_send_outbound_webhook,
    )

    response = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wm_ai_keep_001", "operator": "tester-ai"},
    )
    payload = response.get_json()

    assert response.status_code == 202
    assert payload["status"] == "accepted"
    assert captured["payload"]["currentPool"] == "operating"
    assert captured["payload"]["currentStage"] == "operating_followup"
    assert captured["payload"]["currentTarget"] == "followup"

    with app.app_context():
        row = get_db().execute(
            """
            SELECT current_pool, follow_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_ai_keep_001",),
        ).fetchone()

    assert row["current_pool"] == "operating"
    assert row["follow_type"] == "focus"


def test_automation_member_detail_uses_sidebar_button_rules_for_won_members(app, client):
    _seed_contact(app, external_userid="wm_won_001", mobile="13800003099", owner_userid="sales_won", customer_name="已成交客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_won_001",
        phone="13800003099",
        owner_staff_id="sales_won",
        in_pool=1,
        current_pool="won",
        follow_type="focus",
        questionnaire_status="submitted",
        decision_source="manual",
        source_type="manual",
        last_active_pool="active_focus",
        joined_at="2026-04-06 10:00:00",
    )

    response = client.get(
        "/api/admin/automation-conversion/member",
        query_string={"external_contact_id": "wm_won_001"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    detail = payload["detail"]
    assert detail["member"]["current_pool"] == "converted"
    assert detail["actions"]["put_in_pool"]["enabled"] is False
    assert detail["actions"]["remove_from_pool"]["enabled"] is False
    assert detail["actions"]["set_focus"]["enabled"] is False
    assert detail["actions"]["set_normal"]["enabled"] is False
    assert detail["actions"]["mark_won"]["enabled"] is False
    assert detail["actions"]["unmark_won"]["enabled"] is True
    assert detail["actions"]["push_openclaw"]["enabled"] is True


def test_sync_member_activation_recomputes_pool_from_pending_questionnaire_to_operating(app, monkeypatch):
    _seed_contact(app, external_userid="wm_sync_active_001", mobile="13800003101", owner_userid="sales_sync", customer_name="激活刷新客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sync_active_001",
        phone="13800003101",
        owner_staff_id="sales_sync",
        in_pool=1,
        current_pool="new_user",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="focus",
        decision_source="questionnaire",
        source_type="manual",
        joined_at="2026-04-06 10:00:00",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_sync_active_001",
        phone="13800003101",
        owner_staff_id="sales_sync",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )

    with app.app_context():
        payload = sync_member_activation(
            external_contact_id="wm_sync_active_001",
            operator_id="activation_webhook",
        )
        row = get_db().execute(
            """
            SELECT current_pool, follow_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_sync_active_001",),
        ).fetchone()
        event = get_db().execute(
            """
            SELECT action, operator_type, operator_id, before_snapshot, after_snapshot
            FROM automation_event
            WHERE member_id = (
                SELECT id FROM automation_member WHERE external_contact_id = ?
            )
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_sync_active_001",),
        ).fetchone()

    assert payload["updated"] is True
    assert payload["member"]["current_pool"] == "operating"
    assert payload["member"]["follow_type"] == "focus"
    assert row["current_pool"] == "operating"
    assert row["follow_type"] == "focus"
    assert event["action"] == "member_refresh"
    assert event["operator_type"] == "system"
    assert event["operator_id"] == "activation_webhook"
    assert json.loads(event["before_snapshot"])["current_pool"] == "pending_questionnaire"
    assert json.loads(event["after_snapshot"])["current_pool"] == "operating"


def test_get_member_detail_view_sync_updates_questionnaire_pool(app, monkeypatch):
    _seed_contact(app, external_userid="wm_view_sync_001", mobile="13800003102", owner_userid="sales_view", customer_name="查看同步客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_view_sync_001",
        phone="13800003102",
        owner_staff_id="sales_view",
        in_pool=1,
        current_pool="new_user",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
        source_type="manual",
        joined_at="2026-04-06 10:00:00",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_view_sync_001",
        phone="13800003102",
        owner_staff_id="sales_view",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )

    with app.app_context():
        detail = get_member_detail(external_contact_id="wm_view_sync_001")
        row = get_db().execute(
            """
            SELECT current_pool, follow_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_view_sync_001",),
        ).fetchone()

    assert detail["member"]["current_pool"] == "operating"
    assert detail["member"]["follow_type"] == "normal"
    assert row["current_pool"] == "operating"
    assert row["follow_type"] == "normal"
    assert detail["actions"]["ai_push"]["enabled"] is True


def test_mark_won_and_unmark_restore_operating_normal(app, client, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_restore_normal_001",
        phone="13800005001",
        owner_staff_id="sales_restore",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_restore_normal_001",
        phone="13800005001",
        owner_staff_id="sales_restore",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )

    marked = client.post(
        "/api/admin/automation-conversion/member/mark-won",
        json={"external_contact_id": "wm_restore_normal_001", "operator": "tester"},
    )
    restored = client.post(
        "/api/admin/automation-conversion/member/unmark-won",
        json={"external_contact_id": "wm_restore_normal_001", "operator": "tester"},
    )

    assert marked.status_code == 200
    assert marked.get_json()["member"]["current_pool"] == "converted"
    assert marked.get_json()["member"]["last_active_pool"] == "operating"
    assert restored.status_code == 200
    assert restored.get_json()["member"]["current_pool"] == "operating"
    assert restored.get_json()["member"]["last_active_pool"] == "operating"

    with app.app_context():
        member = get_db().execute(
            "SELECT current_pool, in_pool, last_active_pool FROM automation_member WHERE external_contact_id = ?",
            ("wm_restore_normal_001",),
        ).fetchone()
        assert dict(member) == {
            "current_pool": "operating",
            "in_pool": 1,
            "last_active_pool": "operating",
        }


def test_mark_won_and_unmark_restore_operating_focus(app, client, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_restore_focus_001",
        phone="13800005002",
        owner_staff_id="sales_restore",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_restore_focus_001",
        phone="13800005002",
        owner_staff_id="sales_restore",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )

    marked = client.post(
        "/api/admin/automation-conversion/member/mark-won",
        json={"external_contact_id": "wm_restore_focus_001", "operator": "tester"},
    )
    restored = client.post(
        "/api/admin/automation-conversion/member/unmark-won",
        json={"external_contact_id": "wm_restore_focus_001", "operator": "tester"},
    )

    assert marked.status_code == 200
    assert marked.get_json()["member"]["current_pool"] == "converted"
    assert marked.get_json()["member"]["last_active_pool"] == "operating"
    assert restored.status_code == 200
    assert restored.get_json()["member"]["current_pool"] == "operating"
    assert restored.get_json()["member"]["last_active_pool"] == "operating"
    assert restored.get_json()["member"]["follow_type"] == "focus"

    with app.app_context():
        member = get_db().execute(
            "SELECT current_pool, in_pool, last_active_pool FROM automation_member WHERE external_contact_id = ?",
            ("wm_restore_focus_001",),
        ).fetchone()
        assert dict(member) == {
            "current_pool": "operating",
            "in_pool": 1,
            "last_active_pool": "operating",
        }


def test_unmark_won_falls_back_when_last_active_pool_missing(app, client, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_restore_fallback_001",
        phone="13800005003",
        owner_staff_id="sales_restore",
        in_pool=0,
        current_pool="won",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        last_active_pool="",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_restore_fallback_001",
        phone="13800005003",
        owner_staff_id="sales_restore",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )

    restored = client.post(
        "/api/admin/automation-conversion/member/unmark-won",
        json={"external_contact_id": "wm_restore_fallback_001", "operator": "tester"},
    )

    assert restored.status_code == 200
    assert restored.get_json()["member"]["current_pool"] == "operating"
    assert restored.get_json()["member"]["last_active_pool"] == "operating"

    with app.app_context():
        member = get_db().execute(
            "SELECT current_pool, in_pool, last_active_pool FROM automation_member WHERE external_contact_id = ?",
            ("wm_restore_fallback_001",),
        ).fetchone()
        assert dict(member) == {
            "current_pool": "operating",
            "in_pool": 1,
            "last_active_pool": "operating",
        }


def test_generate_default_channel_generates_real_channel_via_wecom_provider(app, client, monkeypatch):
    captured = {}
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=601)
    program_id = _default_program_id(app)

    class _FakeRuntimeClient:
        def create_contact_way(self, payload: dict) -> dict:
            captured["payload"] = payload
            return {
                "config_id": "cfg-001",
                "qr_code": "https://wecom.example/qr/cfg-001",
            }

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.get_contact_runtime_client",
        lambda: _FakeRuntimeClient(),
    )

    save_response = client.post(
        "/api/admin/automation-conversion/settings",
        json={
            "enabled": True,
            "questionnaire_id": questionnaire_seed["questionnaire_id"],
            "core_threshold": 1,
            "top_threshold": 1,
            "quiet_hour_start": 22,
            "timezone": "Asia/Shanghai",
            "welcome_message": "欢迎添加，稍后我会主动联系你。",
            "auto_accept_friend": True,
            "question_rules": [
                {
                    "questionnaire_question_id": questionnaire_seed["choice_question_id"],
                    "hit_option_ids_json": questionnaire_seed["option_ids"],
                    "sort_order": 1,
                }
            ],
            "silent_threshold_days_by_pool": {
                "new_user": 7,
                "inactive_normal": 7,
                "inactive_focus": 7,
                "active_normal": 7,
                "active_focus": 7,
            },
        },
    )
    assert save_response.status_code == 200

    response = client.post("/api/admin/automation-conversion/settings/default-channel/generate")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["generated"] is True
    assert payload["provider_available"] is True
    assert payload["channel"]["channel_code"] == f"program_{program_id}_default_qrcode"
    assert payload["channel"]["owner_staff_id"] == "HuangYouCan"
    assert payload["channel"]["qr_url"] == "https://wecom.example/qr/cfg-001"
    assert payload["channel"]["qr_ticket"] == "cfg-001"
    assert payload["channel"]["status"] == "active"
    assert payload["field_statuses"]["welcome_message"]["status"] == "applied"
    assert payload["field_statuses"]["auto_accept_friend"]["status"] == "applied"
    assert payload["channel"]["scene_value"].startswith("aqr_")
    assert len(payload["channel"]["scene_value"]) <= 30
    assert captured["payload"]["type"] == 1
    assert captured["payload"]["scene"] == 2
    assert captured["payload"]["style"] == 1
    assert captured["payload"]["skip_verify"] is True
    assert captured["payload"]["user"] == ["HuangYouCan"]
    assert captured["payload"]["state"] == payload["channel"]["scene_value"]
    assert "conclusions" not in captured["payload"]
    assert len(str(captured["payload"]["state"])) <= 30
    assert "_" in str(captured["payload"]["state"])

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            SELECT channel_code, owner_staff_id, qr_url, qr_ticket, scene_value, status, welcome_message, auto_accept_friend
            FROM automation_channel
            WHERE channel_code = ?
            """,
            (f"program_{program_id}_default_qrcode",),
        ).fetchone()
        assert row is not None
        assert row["channel_code"] == f"program_{program_id}_default_qrcode"
        assert row["owner_staff_id"] == "HuangYouCan"
        assert row["qr_url"] == "https://wecom.example/qr/cfg-001"
        assert row["qr_ticket"] == "cfg-001"
        assert str(row["scene_value"]).startswith("aqr_")
        assert len(str(row["scene_value"])) <= 30
        assert row["status"] == "active"
        assert row["welcome_message"] == "欢迎添加，稍后我会主动联系你。"
        assert bool(row["auto_accept_friend"]) is True


def test_default_channel_settings_save_and_readback_welcome_and_auto_accept(app, client):
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=602)
    response = client.post(
        "/api/admin/automation-conversion/settings",
        json={
            "enabled": True,
            "questionnaire_id": questionnaire_seed["questionnaire_id"],
            "core_threshold": 1,
            "top_threshold": 1,
            "quiet_hour_start": 22,
            "timezone": "Asia/Shanghai",
            "welcome_message": "这里是默认渠道欢迎语",
            "auto_accept_friend": True,
            "question_rules": [
                {
                    "questionnaire_question_id": questionnaire_seed["choice_question_id"],
                    "hit_option_ids_json": questionnaire_seed["option_ids"],
                    "sort_order": 1,
                }
            ],
            "silent_threshold_days_by_pool": {
                "new_user": 7,
                "inactive_normal": 7,
                "inactive_focus": 7,
                "active_normal": 7,
                "active_focus": 7,
            },
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["settings"]["default_channel"]["welcome_message"] == "这里是默认渠道欢迎语"
    assert payload["settings"]["default_channel"]["auto_accept_friend"] is True
    assert payload["settings"]["default_channel"]["field_statuses"]["welcome_message"]["status"] == "pending"
    assert payload["settings"]["default_channel"]["field_statuses"]["auto_accept_friend"]["status"] == "pending"

    program_id = _default_program_id(app)
    settings_page = client.get(
        f"/admin/automation-conversion/programs/{program_id}/flow-design",
        query_string={"section": "channel"},
    )
    html = settings_page.get_data(as_text=True)
    assert settings_page.status_code == 200
    assert "这里是默认渠道欢迎语" in html
    assert "免验证直接添加好友" in html

    with app.app_context():
        row = get_db().execute(
            """
            SELECT welcome_message, auto_accept_friend, status
            FROM automation_channel
            WHERE channel_code = ?
            """,
            (f"program_{program_id}_default_qrcode",),
        ).fetchone()
        assert row is not None
        assert row["welcome_message"] == "这里是默认渠道欢迎语"
        assert bool(row["auto_accept_friend"]) is True
        assert row["status"] == "configured"


def test_default_channel_settings_save_and_readback_entry_tag(app):
    from wecom_ability_service.domains.automation_conversion.service import save_default_channel_settings

    with app.app_context():
        saved_tags = [
            {"tag_id": "tag-channel-001", "tag_name": "渠道报名", "group_name": "渠道来源"},
        ]
        original = save_default_channel_settings.__globals__["list_available_wecom_tags"]
        save_default_channel_settings.__globals__["list_available_wecom_tags"] = lambda: list(saved_tags)
        try:
            payload = save_default_channel_settings(
                {
                    "channel_name": "默认渠道二维码",
                    "entry_tag_id": "tag-channel-001",
                }
            )
        finally:
            save_default_channel_settings.__globals__["list_available_wecom_tags"] = original

        default_channel = payload["default_channel"]
        assert default_channel["entry_tag_id"] == "tag-channel-001"
        assert default_channel["entry_tag_name"] == "渠道报名"
        assert default_channel["entry_tag_group_name"] == "渠道来源"
        assert default_channel["field_statuses"]["entry_tag"]["status"] == "applied"

        row = get_db().execute(
            """
            SELECT entry_tag_id, entry_tag_name, entry_tag_group_name
            FROM automation_channel
            WHERE channel_code = 'default_qrcode'
            """
        ).fetchone()
        assert dict(row) == {
            "entry_tag_id": "tag-channel-001",
            "entry_tag_name": "渠道报名",
            "entry_tag_group_name": "渠道来源",
        }


def test_generate_default_channel_reports_config_incomplete_when_wecom_config_missing(app, client, monkeypatch):
    from wecom_ability_service.wecom_client import WeComClientError

    class _BrokenRuntimeClient:
        def create_contact_way(self, payload: dict) -> dict:
            raise WeComClientError("WECOM_CORP_ID or WECOM_CONTACT_SECRET is not configured")

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.get_contact_runtime_client",
        lambda: _BrokenRuntimeClient(),
    )

    response = client.post("/api/admin/automation-conversion/settings/default-channel/generate")
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["provider_available"] is True
    assert payload["generated"] is False
    assert payload["channel"]["channel_code"] == f"program_{_default_program_id(app)}_default_qrcode"
    assert payload["channel"]["owner_staff_id"] == "HuangYouCan"
    assert payload["channel"]["status"] == "config_incomplete"
    assert payload["error_code"] == "config_incomplete"
    assert "WECOM_CORP_ID or WECOM_CONTACT_SECRET is not configured" in payload["error"]


def test_generate_default_channel_blocks_invalid_state_before_calling_wecom(app, client, monkeypatch):
    called = {"count": 0}

    class _FakeRuntimeClient:
        def create_contact_way(self, payload: dict) -> dict:
            called["count"] += 1
            return {
                "config_id": "cfg-002",
                "qr_code": "https://wecom.example/qr/cfg-002",
            }

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.get_contact_runtime_client",
        lambda: _FakeRuntimeClient(),
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.build_default_channel_state_token",
        lambda *, now=None: "aqr_invalid_state_token_length_more_than_30",
    )

    response = client.post("/api/admin/automation-conversion/settings/default-channel/generate")
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["generated"] is False
    assert payload["error_code"] == "invalid_state"
    assert "state 长度不能超过 30 个字符" in payload["error"]
    assert called["count"] == 0


def test_message_activity_sync_updates_activation_follow_type_and_pool(app, monkeypatch):
    _configure_message_activity_db(app)
    members = [
        ("wm_msg_sync_001", "13800001231", "inactive_normal"),
        ("wm_msg_sync_002", "13800001232", "inactive_normal"),
        ("wm_msg_sync_003", "13800001233", "active_focus"),
        ("wm_msg_sync_004", "13800001234", "active_normal"),
    ]
    for external_userid, mobile, current_pool in members:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_msg", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_msg",
            current_pool=current_pool,
            follow_type="normal",
            activation_status="inactive",
            questionnaire_status="submitted",
            questionnaire_follow_type="normal",
            decision_source="questionnaire",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "138", "phone_last4": "1231", "phone_match_key": "138_1231", "message_count": 15},
            {"phone_prefix3": "138", "phone_last4": "1232", "phone_match_key": "138_1232", "message_count": 10},
            {"phone_prefix3": "138", "phone_last4": "1233", "phone_match_key": "138_1233", "message_count": 1},
            {"phone_prefix3": "138", "phone_last4": "1234", "phone_match_key": "138_1234", "message_count": 0},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        rows = get_db().execute(
            """
            SELECT external_contact_id, follow_type, decision_source, current_pool, current_audience_code
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_msg_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()
        event_actions = get_db().execute(
            """
            SELECT action
            FROM automation_event
            WHERE action = 'message_activity_sync'
            ORDER BY id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["candidate_count"] == 4
    assert payload["run"]["matched_count"] == 4
    assert payload["run"]["updated_count"] == 2
    assert payload["run"]["focus_count"] == 1
    assert payload["run"]["normal_count"] == 3
    assert [dict(row) for row in rows] == [
        {
            "external_contact_id": "wm_msg_sync_001",
            "follow_type": "focus",
            "decision_source": "system",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_msg_sync_002",
            "follow_type": "normal",
            "decision_source": "system",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_msg_sync_003",
            "follow_type": "normal",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_msg_sync_004",
            "follow_type": "normal",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
    ]
    assert len(event_actions) == 2


def test_message_activity_sync_preserves_manual_follow_type(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_manual_sync_001", mobile="13800002221", owner_userid="sales_manual", customer_name="manual-1")
    _seed_contact(app, external_userid="wm_manual_sync_002", mobile="13800002222", owner_userid="sales_manual", customer_name="manual-2")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_sync_001",
        phone="13800002221",
        owner_staff_id="sales_manual",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
        decision_source="manual",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_sync_002",
        phone="13800002222",
        owner_staff_id="sales_manual",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="manual",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "138", "phone_last4": "2221", "phone_match_key": "138_2221", "message_count": 20},
            {"phone_prefix3": "138", "phone_last4": "2222", "phone_match_key": "138_2222", "message_count": 0},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        rows = get_db().execute(
            """
            SELECT external_contact_id, follow_type, decision_source, current_pool, current_audience_code
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_manual_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["candidate_count"] == 2
    assert payload["run"]["matched_count"] == 2
    assert [dict(row) for row in rows] == [
        {
            "external_contact_id": "wm_manual_sync_001",
            "follow_type": "focus",
            "decision_source": "system",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_manual_sync_002",
            "follow_type": "focus",
            "decision_source": "manual",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
    ]


def test_message_activity_sync_uses_follow_type_fallback_for_inactive_members(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_questionnaire_sync_001", mobile="13800002441", owner_userid="sales_questionnaire", customer_name="questionnaire-focus")
    _seed_contact(app, external_userid="wm_questionnaire_sync_002", mobile="13800002442", owner_userid="sales_questionnaire", customer_name="questionnaire-normal")
    _seed_automation_member(
        app,
        external_contact_id="wm_questionnaire_sync_001",
        phone="13800002441",
        owner_staff_id="sales_questionnaire",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
        decision_source="system",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_questionnaire_sync_002",
        phone="13800002442",
        owner_staff_id="sales_questionnaire",
        current_pool="inactive_focus",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="system",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "138", "phone_last4": "2441", "phone_match_key": "138_2441", "message_count": 1},
            {"phone_prefix3": "138", "phone_last4": "2442", "phone_match_key": "138_2442", "message_count": 0},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        rows = get_db().execute(
            """
            SELECT external_contact_id, follow_type, decision_source, current_pool, current_audience_code
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_questionnaire_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert [dict(row) for row in rows] == [
        {
            "external_contact_id": "wm_questionnaire_sync_001",
            "follow_type": "focus",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_questionnaire_sync_002",
            "follow_type": "normal",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
    ]


def test_message_activity_sync_skips_ambiguous_and_unmatched_members(app, monkeypatch):
    _configure_message_activity_db(app)
    rows = [
        ("wm_skip_sync_001", "13800003331"),
        ("wm_skip_sync_002", "13899993331"),
        ("wm_skip_sync_003", "13800003332"),
        ("wm_skip_sync_004", "13800003339"),
    ]
    for external_userid, mobile in rows:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_skip", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_skip",
            current_pool="inactive_normal",
            follow_type="normal",
            activation_status="inactive",
            questionnaire_status="submitted",
            questionnaire_follow_type="normal",
            decision_source="questionnaire",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "138", "phone_last4": "3331", "phone_match_key": "138_3331", "message_count": 9},
            {"phone_prefix3": "138", "phone_last4": "3332", "phone_match_key": "138_3332", "message_count": 3},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        items = get_db().execute(
            """
            SELECT external_contact_id, status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            (payload["run"]["id"],),
        ).fetchall()
        members = get_db().execute(
            """
            SELECT external_contact_id, follow_type, decision_source, current_pool, current_audience_code
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_skip_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["candidate_count"] == 4
    assert payload["run"]["matched_count"] == 1
    assert payload["run"]["updated_count"] == 1
    assert payload["run"]["skipped_ambiguous_count"] == 2
    assert payload["run"]["skipped_unmatched_count"] == 1
    assert [dict(item) for item in items] == [
        {
            "external_contact_id": "wm_skip_sync_001",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_3331 matched multiple automation members: wm_skip_sync_001,wm_skip_sync_002",
        },
        {
            "external_contact_id": "wm_skip_sync_002",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_3331 matched multiple automation members: wm_skip_sync_001,wm_skip_sync_002",
        },
        {
            "external_contact_id": "wm_skip_sync_004",
            "status": "skipped_unmatched",
            "detail": "phone_match_key=138_3339 not found in message activity source",
        },
        {
            "external_contact_id": "wm_skip_sync_003",
            "status": "updated",
            "detail": "rank=1/1; bucket=active_normal_threshold; effective_follow_type=normal; manual_preserved=no",
        },
    ]
    assert [dict(item) for item in members] == [
        {
            "external_contact_id": "wm_skip_sync_001",
            "follow_type": "normal",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_skip_sync_002",
            "follow_type": "normal",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_skip_sync_003",
            "follow_type": "normal",
            "decision_source": "system",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
        {
            "external_contact_id": "wm_skip_sync_004",
            "follow_type": "normal",
            "decision_source": "questionnaire",
            "current_pool": "operating",
            "current_audience_code": "operating",
        },
    ]


def test_message_activity_sync_requires_same_prefix3_and_last4(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_match_sync_001", mobile="13800005555", owner_userid="sales_match", customer_name="match")
    _seed_automation_member(
        app,
        external_contact_id="wm_match_sync_001",
        phone="13800005555",
        owner_staff_id="sales_match",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "139", "phone_last4": "5555", "phone_match_key": "139_5555", "message_count": 20},
            {"phone_prefix3": "138", "phone_last4": "5555", "phone_match_key": "138_5555", "message_count": 20},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        row = get_db().execute(
            """
            SELECT follow_type, decision_source, current_pool, current_audience_code
            FROM automation_member
            WHERE external_contact_id = 'wm_match_sync_001'
            """
        ).fetchone()

    assert payload["ok"] is True
    assert payload["run"]["matched_count"] == 1
    assert dict(row) == {
        "follow_type": "focus",
        "decision_source": "system",
        "current_pool": "operating",
        "current_audience_code": "operating",
    }


def test_message_activity_sync_same_last4_different_prefix_does_not_match(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_last4_sync_001", mobile="13800006666", owner_userid="sales_last4", customer_name="last4")
    _seed_automation_member(
        app,
        external_contact_id="wm_last4_sync_001",
        phone="13800006666",
        owner_staff_id="sales_last4",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "139", "phone_last4": "6666", "phone_match_key": "139_6666", "message_count": 9},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        item = get_db().execute(
            """
            SELECT status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (payload["run"]["id"],),
        ).fetchone()

    assert payload["ok"] is True
    assert payload["run"]["matched_count"] == 0
    assert dict(item) == {
        "status": "skipped_unmatched",
        "detail": "phone_match_key=138_6666 not found in message activity source",
    }


def test_message_activity_sync_skips_same_phone_match_key_as_ambiguous(app, monkeypatch):
    _configure_message_activity_db(app)
    for external_userid, mobile in [
        ("wm_key_sync_001", "13800007777"),
        ("wm_key_sync_002", "13899997777"),
    ]:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_key", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_key",
            current_pool="inactive_normal",
            follow_type="normal",
            activation_status="inactive",
            questionnaire_status="submitted",
            questionnaire_follow_type="normal",
            decision_source="questionnaire",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "138", "phone_last4": "7777", "phone_match_key": "138_7777", "message_count": 6},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        items = get_db().execute(
            """
            SELECT external_contact_id, status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY external_contact_id ASC
            """,
            (payload["run"]["id"],),
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["skipped_ambiguous_count"] == 2
    assert [dict(item) for item in items] == [
        {
            "external_contact_id": "wm_key_sync_001",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_7777 matched multiple automation members: wm_key_sync_001,wm_key_sync_002",
        },
        {
            "external_contact_id": "wm_key_sync_002",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_7777 matched multiple automation members: wm_key_sync_001,wm_key_sync_002",
        },
    ]


def test_message_activity_sync_skips_invalid_short_phone(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_short_sync_001", mobile="123456", owner_userid="sales_short", customer_name="short-phone")
    _seed_automation_member(
        app,
        external_contact_id="wm_short_sync_001",
        phone="123456",
        owner_staff_id="sales_short",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [
            {"phone_prefix3": "123", "phone_last4": "3456", "phone_match_key": "123_3456", "message_count": 20},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        item = get_db().execute(
            """
            SELECT status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (payload["run"]["id"],),
        ).fetchone()

    assert payload["ok"] is True
    assert payload["run"]["skipped_missing_phone_count"] == 1
    assert dict(item) == {
        "status": "skipped_missing_phone",
        "detail": "member phone is empty or shorter than 7 digits, cannot build phone_match_key",
    }


def test_message_activity_sync_api_requires_internal_token_and_returns_run(app, client, monkeypatch):
    _configure_message_activity_db(app)
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "sync-token"
    _seed_contact(app, external_userid="wm_sync_api_001", mobile="13800004441", owner_userid="sales_api", customer_name="sync-api")
    _seed_automation_member(
        app,
        external_contact_id="wm_sync_api_001",
        phone="13800004441",
        owner_staff_id="sales_api",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [{"phone_prefix3": "138", "phone_last4": "4441", "phone_match_key": "138_4441", "message_count": 5}],
    )

    unauthorized = client.post("/api/admin/automation-conversion/message-activity-sync/run", json={"trigger_source": "scheduled"})
    authorized = client.post(
        "/api/admin/automation-conversion/message-activity-sync/run",
        json={"trigger_source": "scheduled", "operator": "tester-sync-api"},
        headers={"Authorization": "Bearer sync-token"},
    )

    assert unauthorized.status_code == 401
    assert unauthorized.get_json()["error"] == "missing internal token"
    assert authorized.status_code == 200
    assert authorized.get_json()["ok"] is True
    assert authorized.get_json()["run"]["trigger_source"] == "scheduled"
    assert authorized.get_json()["run"]["matched_count"] == 1


def test_message_activity_sync_api_fails_closed_when_token_is_not_configured(app, client, monkeypatch):
    _configure_message_activity_db(app)
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_message_activity_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_message_activity_sync should not be called")),
    )

    response = client.post("/api/admin/automation-conversion/message-activity-sync/run", json={"trigger_source": "scheduled"})

    assert response.status_code == 503
    assert response.get_json()["error"] == "internal token not configured"


def test_automation_conversion_flow_design_page_focuses_on_settings_sections(app, client):
    program_id = _default_program_id(app)
    response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/flow-design",
        query_string={"section": "questionnaire"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "基础配置" in html
    assert "方案基础配置" in html
    assert "问卷分层" in html
    assert "基础画像分层模板" in html
    assert "欢迎语 / 标签 / 二维码" in html
    assert "方案入口二维码" in html
    assert "流程设计" not in html
    assert "阶段模型" not in html
    assert "入池与问卷规则" not in html
    assert "SOP 剧本" not in html
    assert "全局规则" not in html
    assert "发布管理" not in html
    assert "立即刷新一次" not in html
    assert "消息活跃同步已迁到运行中心" not in html
    assert "前往运行中心校验" not in html


def test_flow_design_page_renders_entry_tag_fields_for_program_channel(app, client):
    program_id = _default_program_id(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                program_id, channel_code, channel_name, entry_tag_id, entry_tag_name, entry_tag_group_name, owner_staff_id, status, created_at, updated_at
            )
            VALUES (?, ?, '默认渠道二维码', 'tag-channel-001', '渠道报名', '渠道来源', 'HuangYouCan', 'configured', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (program_id, f"program_{program_id}_default_qrcode"),
        )
        db.commit()

    response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/flow-design",
        query_string={"section": "channel"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="entry_tag_id"' in html
    assert 'name="entry_tag_id_manual"' in html
    assert "扫码自动打标签" in html
    assert "选择已有标签" in html
    assert "default-channel-tag-modal-overlay" in html
    assert "[hidden]" in html
    assert "display: none !important" in html
    assert "按标签组选择，确认后仅保存 tag_id" in html


def test_profile_segment_templates_and_channel_settings_are_scoped_by_program(app, client):
    default_program_id = _default_program_id(app)
    with app.app_context():
        cursor = get_db().execute(
            """
            INSERT INTO automation_program (program_code, program_name, status, config_json, created_at, updated_at)
            VALUES ('program_scoped_assets', '独立资源方案', 'draft', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        other_program_id = int(cursor.lastrowid)
        get_db().commit()

    default_seed = _seed_profile_segment_template(
        app,
        questionnaire_id=741,
        template_name="默认方案画像",
        program_id=default_program_id,
    )
    other_seed = _seed_profile_segment_template(
        app,
        questionnaire_id=742,
        template_name="独立方案画像",
        program_id=other_program_id,
    )

    default_list = client.get(
        "/api/admin/automation-conversion/profile-segment-templates",
        query_string={"program_id": default_program_id},
    ).get_json()
    other_list = client.get(
        "/api/admin/automation-conversion/profile-segment-templates",
        query_string={"program_id": other_program_id},
    ).get_json()

    assert [item["template"]["template_name"] for item in default_list["items"]] == ["默认方案画像"]
    assert [item["template"]["template_name"] for item in other_list["items"]] == ["独立方案画像"]
    assert default_list["items"][0]["template"]["program_id"] == default_program_id
    assert other_list["items"][0]["template"]["program_id"] == other_program_id

    default_detail = client.get(
        f"/api/admin/automation-conversion/profile-segment-templates/{default_seed['template_id']}",
        query_string={"program_id": default_program_id},
    )
    assert default_detail.status_code == 200
    assert default_detail.get_json()["template"]["program_id"] == default_program_id

    cross_detail = client.get(
        f"/api/admin/automation-conversion/profile-segment-templates/{default_seed['template_id']}",
        query_string={"program_id": other_program_id},
    )
    assert cross_detail.status_code == 404

    with app.app_context():
        from wecom_ability_service.domains.automation_conversion.service import (
            get_default_channel_settings_payload,
            save_default_channel_settings,
        )

        save_default_channel_settings(
            {"channel_name": "默认方案入口", "welcome_message": "默认方案欢迎语", "auto_accept_friend": True},
            program_id=default_program_id,
        )
        save_default_channel_settings(
            {"channel_name": "独立方案入口", "welcome_message": "独立方案欢迎语", "auto_accept_friend": False},
            program_id=other_program_id,
        )
        default_channel = get_default_channel_settings_payload(program_id=default_program_id)["default_channel"]
        other_channel = get_default_channel_settings_payload(program_id=other_program_id)["default_channel"]

    assert default_channel["welcome_message"] == "默认方案欢迎语"
    assert default_channel["auto_accept_friend"] is True
    assert other_channel["welcome_message"] == "独立方案欢迎语"
    assert other_channel["auto_accept_friend"] is False
    assert default_channel["channel_code"] != other_channel["channel_code"]
    assert other_seed["template_id"] != default_seed["template_id"]


def test_removed_admin_automation_conversion_routes_are_not_registered(app, client):
    rules = {rule.rule: rule.endpoint for rule in app.url_map.iter_rules()}
    rule_methods = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    endpoints = set(rules.values())

    removed_routes = {
        "/admin/automation-conversion/settings",
        "/admin/automation-conversion/sop",
        "/admin/automation-conversion/stage/<stage_key>",
        "/admin/automation-conversion/model-infra",
        "/admin/automation-conversion/debug",
        "/admin/automation-conversion/preview",
        "/admin/automation-conversion/agent-config",
        "/admin/automation-conversion/run-center",
        "/admin/automation-conversion/overview",
        "/admin/automation-conversion/operations",
        "/admin/automation-conversion/flow-design",
        "/admin/automation-conversion/member-ops",
        "/admin/automation-conversion/stage/<stage_key>/send",
        "/admin/automation-conversion/operations/workflows/new",
        "/admin/automation-conversion/operations/workflows/<int:workflow_id>/edit",
        "/admin/automation-conversion/operations/workflows/<int:workflow_id>/nodes",
        "/admin/automation-conversion/operations/executions",
        "/api/admin/automation-conversion/model-infra/settings",
    }
    removed_endpoint_names = {
        "settings",
        "sop",
        "stage",
        "model_infra",
        "debug",
        "preview",
        "agent_config",
        "run_center",
        "overview",
        "operations",
        "flow_design",
        "member_ops",
        "stage_send",
        "workflow_new",
        "workflow_edit",
        "workflow_nodes",
        "execution_records",
    }
    removed_endpoints = {
        f"api.admin_automation_conversion_{name}"
        for name in removed_endpoint_names
    }
    kept_routes = {
        "/admin/automation-conversion",
        "/admin/automation-conversion/programs/<int:program_id>/flow-design",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops",
        "/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send",
        "/admin/automation-conversion/shared/agents",
        "/admin/automation-conversion/shared/model-infra",
        "/admin/automation-conversion/runtime/debug",
        "/api/admin/automation-conversion/settings",
        "/api/admin/automation-conversion/sop/config",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send",
        "/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview",
        "/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches",
    }

    assert not (removed_routes & set(rules))
    assert not (removed_endpoints & endpoints)
    assert kept_routes <= set(rules)

    for path in [
        "/admin/automation-conversion/settings",
        "/admin/automation-conversion/sop",
        "/admin/automation-conversion/stage/new-user",
        "/admin/automation-conversion/model-infra",
        "/admin/automation-conversion/debug",
        "/admin/automation-conversion/preview",
        "/admin/automation-conversion/agent-config",
        "/admin/automation-conversion/run-center",
        "/admin/automation-conversion/overview",
        "/admin/automation-conversion/operations",
        "/admin/automation-conversion/flow-design",
        "/admin/automation-conversion/member-ops",
        "/admin/automation-conversion/stage/new-user/send",
        "/admin/automation-conversion/operations/workflows/new",
        "/admin/automation-conversion/operations/workflows/1/edit",
        "/admin/automation-conversion/operations/workflows/1/nodes",
        "/admin/automation-conversion/operations/executions",
    ]:
        assert client.get(path).status_code == 404

    program_id = _default_program_id(app)
    new_stage_send_rule = "/admin/automation-conversion/programs/<int:program_id>/member-ops/stage/<stage_key>/send"
    assert rules[new_stage_send_rule] == "api.admin_automation_program_member_ops_stage_send"
    assert "POST" in rule_methods[new_stage_send_rule]
    assert "GET" not in rule_methods[new_stage_send_rule]
    assert client.get(f"/admin/automation-conversion/programs/{program_id}/member-ops/stage/new-user/send").status_code in {404, 405}
    assert client.post("/admin/automation-conversion/stage/new-user/send").status_code in {404, 405}


def test_admin_automation_conversion_save_settings_redirects_back_to_current_flow_design_section(app, client, monkeypatch):
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.save_settings", lambda payload: payload)
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    program_id = _default_program_id(app)

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={"section": "global-rules"},
    )

    assert response.status_code == 302
    assert f"/admin/automation-conversion/programs/{program_id}/flow-design" in response.headers["Location"]
    assert "section=global-rules" in response.headers["Location"]
    assert "saved=1" in response.headers["Location"]


def test_admin_automation_conversion_save_settings_error_keeps_current_flow_design_section(app, client, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.save_settings",
        lambda payload, program_id=None: (_ for _ in ()).throw(ValueError("保存失败")),
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={"section": "channel", "welcome_message": "保留输入"},
    )
    html = response.get_data(as_text=True)
    program_id = _default_program_id(app)

    assert response.status_code == 200
    assert "保存失败" in html
    assert "保留输入" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/flow-design?section=channel#flow-channel">欢迎语 / 标签 / 二维码</a>' in html
    assert 'ac-section-link is-active' in html


def test_admin_automation_conversion_save_settings_requires_action_token_and_keeps_section(app, client):
    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={"section": "channel", "welcome_message": "未提交成功"},
    )
    html = response.get_data(as_text=True)
    program_id = _default_program_id(app)

    assert response.status_code == 200
    assert "后台动作令牌无效，请刷新页面后重试" in html
    assert "未提交成功" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/flow-design?section=channel#flow-channel">欢迎语 / 标签 / 二维码</a>' in html


def test_admin_generate_default_channel_error_keeps_channel_section(app, client, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.generate_default_channel_qr",
        lambda operator="", program_id=None: {"generated": False, "error": "二维码生成失败"},
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")

    response = client.post("/admin/automation-conversion/settings/default-channel/generate")
    html = response.get_data(as_text=True)
    program_id = _default_program_id(app)

    assert response.status_code == 200
    assert "二维码生成失败" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/flow-design?section=channel#flow-channel">欢迎语 / 标签 / 二维码</a>' in html
    assert 'ac-section-link is-active' in html


def test_admin_generate_default_channel_requires_action_token(app, client):
    response = client.post("/admin/automation-conversion/settings/default-channel/generate")
    html = response.get_data(as_text=True)
    program_id = _default_program_id(app)

    assert response.status_code == 200
    assert "后台动作令牌无效，请刷新页面后重试" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/flow-design?section=channel#flow-channel">欢迎语 / 标签 / 二维码</a>' in html


def test_model_infra_settings_save_and_mask_deepseek_api_key(app, client):
    response = client.put(
        "/api/admin/automation-conversion/model-settings",
        json={
            "enabled": True,
            "api_key": "dsk-automation-secret-12345",
            "base_url": "https://api.deepseek.com",
            "router_model": "deepseek-router-x",
            "execution_model": "deepseek-execution-x",
            "timeout_seconds": 45,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    deepseek = payload["model_infra"]["deepseek"]
    assert deepseek["enabled"] is True
    assert deepseek["api_key_configured"] is True
    assert deepseek["api_key_masked"] == "dsk***45"
    assert deepseek["base_url"] == "https://api.deepseek.com"
    assert deepseek["router_model"] == "deepseek-router-x"
    assert deepseek["execution_model"] == "deepseek-execution-x"
    assert deepseek["timeout_seconds"] == 45
    assert deepseek["updated_at"]

    with app.app_context():
        stored_key = get_db().execute(
            "SELECT value FROM app_settings WHERE key = 'DEEPSEEK_API_KEY'"
        ).fetchone()["value"]
        assert stored_key == "dsk-automation-secret-12345"

    page = client.get("/admin/automation-conversion/shared/model-infra", follow_redirects=True)
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    assert "DeepSeek 配置" in html
    assert "dsk-automation-secret-12345" not in html
    assert "dsk***45" in html


def test_model_infra_prompt_registry_seeds_and_saves_all_agent_prompts(app):
    expected_codes = [
        "central_router_agent",
        "welcome_agent",
        "pricing_agent",
        "proof_agent",
        "closing_agent",
    ]

    with app.app_context():
        initial_payload = get_model_infra_payload()
        assert [item["agent_code"] for item in initial_payload["prompts"]] == expected_codes

        saved_prompts = {}
        for agent_code in expected_codes:
            saved_prompts[agent_code] = save_model_infra_prompt(
                agent_code=agent_code,
                display_name=f"{agent_code}-display",
                prompt_text=f"{agent_code} prompt text v2",
                enabled=agent_code != "proof_agent",
            )

        payload = get_model_infra_payload()
        rows = get_db().execute(
            "SELECT agent_code, display_name, prompt_text, enabled, version FROM automation_agent_prompt_registry ORDER BY agent_code ASC"
        ).fetchall()

    prompt_map = {item["agent_code"]: item for item in payload["prompts"]}
    assert set(prompt_map.keys()) == set(expected_codes)
    assert len(rows) == 5
    for agent_code in expected_codes:
        assert saved_prompts[agent_code]["agent_code"] == agent_code
        assert saved_prompts[agent_code]["display_name"] == f"{agent_code}-display"
        assert saved_prompts[agent_code]["prompt_text"] == f"{agent_code} prompt text v2"
        assert saved_prompts[agent_code]["enabled"] is (agent_code != "proof_agent")
        assert saved_prompts[agent_code]["version"] == 2
        assert prompt_map[agent_code]["prompt_text"] == f"{agent_code} prompt text v2"


def test_save_model_infra_prompt_syncs_child_agent_draft_config(app):
    with app.app_context():
        ensure_agent_orchestration_defaults()
        before = get_agent_config_detail("welcome_agent")
        save_model_infra_prompt(
            agent_code="welcome_agent",
            display_name="欢迎接待 Agent v3",
            prompt_text="欢迎接待 Agent 的任务提示词 v3",
            enabled=True,
        )
        after = get_agent_config_detail("welcome_agent")

    assert before["display_name"] != after["display_name"]
    assert after["display_name"] == "欢迎接待 Agent v3"
    assert after["draft"]["task_prompt"] == "欢迎接待 Agent 的任务提示词 v3"
    assert after["published"]["task_prompt"] != "欢迎接待 Agent 的任务提示词 v3"


def test_deepseek_llm_client_success_logs_and_parses_json(app, monkeypatch):
    captured: dict[str, object] = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured.update(
            {
                "url": url,
                "headers": dict(headers or {}),
                "json": dict(json or {}),
                "timeout": timeout,
            }
        )
        return _FakeDeepSeekResponse(
            headers={"x-request-id": "deepseek-req-001"},
            json_data={
                "choices": [
                    {
                        "message": {
                            "content": json_module.dumps({"route": "welcome_agent", "confidence": 0.91})
                        }
                    }
                ]
            },
        )

    json_module = json
    monkeypatch.setattr("requests.post", _fake_post)

    with app.app_context():
        save_model_infra_settings(
            {
                "enabled": True,
                "api_key": "dsk-routing-key-556677",
                "base_url": "https://api.deepseek.com",
                "router_model": "deepseek-router-v1",
                "execution_model": "deepseek-execution-v1",
                "timeout_seconds": 21,
            }
        )
        result = call_deepseek_agent(
            agent_code="central_router_agent",
            system_prompt="router system prompt",
            user_input="客户刚回复了价格问题",
            json_output=True,
        )
        row = get_db().execute(
            """
            SELECT agent_code, model_name, request_id, status, latency_ms, error_message
            FROM automation_agent_llm_call_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert result["ok"] is True
    assert result["request_id"] == "deepseek-req-001"
    assert result["model_name"] == "deepseek-router-v1"
    assert result["parsed_output"] == {"route": "welcome_agent", "confidence": 0.91}
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer dsk-routing-key-556677"
    assert captured["json"]["model"] == "deepseek-router-v1"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["timeout"] == 21
    assert dict(row)["status"] == "success"
    assert dict(row)["agent_code"] == "central_router_agent"
    assert dict(row)["model_name"] == "deepseek-router-v1"
    assert dict(row)["request_id"] == "deepseek-req-001"
    assert dict(row)["error_message"] == ""


def test_deepseek_llm_client_request_error_is_logged(app, monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.RequestException("deepseek request timeout")),
    )

    with app.app_context():
        save_model_infra_settings(
            {
                "enabled": True,
                "api_key": "dsk-execution-key-778899",
                "base_url": "https://api.deepseek.com",
                "router_model": "deepseek-router-v2",
                "execution_model": "deepseek-execution-v2",
                "timeout_seconds": 18,
            }
        )
        with pytest.raises(DeepSeekClientError, match="deepseek request timeout"):
            call_deepseek_agent(
                agent_code="pricing_agent",
                system_prompt="pricing system prompt",
                user_input="给我价格说明",
                json_output=False,
            )
        row = get_db().execute(
            """
            SELECT agent_code, model_name, status, error_message
            FROM automation_agent_llm_call_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert dict(row) == {
        "agent_code": "pricing_agent",
        "model_name": "deepseek-execution-v2",
        "status": "request_error",
        "error_message": "deepseek request timeout",
    }


def test_model_infra_page_renders_and_homepage_keeps_existing_sections(app, client):
    model_infra_page = client.get("/admin/automation-conversion/shared/model-infra", follow_redirects=True)
    model_infra_html = model_infra_page.get_data(as_text=True)

    assert model_infra_page.status_code == 200
    assert "DeepSeek 配置" in model_infra_html
    assert "提示词注册表" in model_infra_html
    assert "智能体编排" in model_infra_html
    assert "中央路由不再在这里作为普通提示词文本框维护" in model_infra_html
    assert "最近模型调用日志" in model_infra_html
    assert "最近执行结果" not in model_infra_html

    home_page = client.get("/admin/automation-conversion")
    home_html = home_page.get_data(as_text=True)

    assert home_page.status_code == 200
    assert "当前所有可见自动化运营方案" in home_html
    assert "方案列表" in home_html


def test_run_center_agent_orchestration_router_subtab_uses_webhook_contract_not_prompt_box(app, client):
    response = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={"subtab": "router"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "智能体编排" in html
    assert "龙虾路由接入配置" in html
    assert "启用中央路由接入" in html
    assert "龙虾 webhook 地址" in html
    assert "请求签名 Token" in html
    assert "兜底处理" in html
    assert "请求 / 返回协议样例" in html
    assert 'name="prompt_text"' not in html


def test_run_center_agent_orchestration_router_subtab_uses_async_samples_even_with_legacy_saved_examples(app, client):
    with app.app_context():
        ensure_agent_orchestration_defaults()
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "request_sample": {
                    "request_id": "legacy-001",
                    "external_contact_id": "wm_legacy_001",
                    "member_snapshot": {"current_pool": "active_focus"},
                    "allowed_agents": ["pricing_agent"],
                },
                "response_sample": {
                    "request_id": "legacy-001",
                    "external_contact_id": "wm_legacy_001",
                    "agent_code": "pricing_agent",
                    "allowed_agents": ["pricing_agent"],
                },
            },
            operator_id="tester-router",
        )

    response = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={"subtab": "router"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "recent_messages" in html
    assert "target_pool" in html
    assert "member_snapshot" not in html
    assert "allowed_agents" not in html


def test_save_agent_router_settings_keeps_existing_secret_when_form_leaves_it_blank(app):
    with app.app_context():
        ensure_agent_orchestration_defaults()
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "router-token-001",
                "signature_secret": "router-secret-001",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 6,
                "retry_count": 2,
                "fallback_strategy": {"default_agent_code": "welcome_agent", "default_pool": "new_user"},
            },
            operator_id="tester",
        )
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router-v2",
                "signature_token": "",
                "signature_secret": "",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 7,
                "retry_count": 1,
                "fallback_strategy": {"default_agent_code": "pricing_agent", "default_pool": "inactive_normal"},
            },
            operator_id="tester-2",
        )
        row = get_db().execute(
            """
            SELECT webhook_url, signature_token, signature_secret, timeout_seconds, retry_count
            FROM automation_agent_router_config
            WHERE config_key = 'default'
            """
        ).fetchone()

    assert dict(row) == {
        "webhook_url": "https://lobster.example.com/router-v2",
        "signature_token": "router-token-001",
        "signature_secret": "router-secret-001",
        "timeout_seconds": 7,
        "retry_count": 1,
    }


def test_save_agent_router_settings_persists_callback_policy_and_cleans_legacy_samples(app):
    with app.app_context():
        ensure_agent_orchestration_defaults()
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "min_confidence": 0.93,
                    "human_review_target_pool": "silent",
                    "need_human_review": True,
                },
                "request_sample": {"legacy": True, "member_snapshot": {"current_pool": "active_focus"}},
                "response_sample": {"legacy": True, "allowed_agents": ["pricing_agent"]},
            },
            operator_id="tester-router",
        )
        row = get_db().execute(
            """
            SELECT fallback_strategy_json, request_sample_json, response_sample_json
            FROM automation_agent_router_config
            WHERE config_key = 'default'
            LIMIT 1
            """
        ).fetchone()

    fallback_strategy = json.loads(row["fallback_strategy_json"])
    request_sample = json.loads(row["request_sample_json"])
    response_sample = json.loads(row["response_sample_json"])

    assert fallback_strategy["min_confidence"] == pytest.approx(0.93)
    assert fallback_strategy["human_review_target_pool"] == "human_reply"
    assert set(request_sample.keys()) == {"request_id", "external_contact_id", "recent_messages"}
    assert "member_snapshot" not in request_sample
    assert set(response_sample.keys()) >= {"request_id", "external_contact_id", "target_pool", "agent_code"}
    assert "allowed_agents" not in response_sample


def test_run_center_agent_orchestration_agents_subtab_shows_split_prompt_layers(app, client):
    response = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={"subtab": "agents"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "子智能体列表" in html
    assert "智能体详情" in html
    assert "角色提示词" in html
    assert "任务 / 文本提示词" in html
    assert "变量配置（JSON）" in html
    assert "输出协议（JSON）" in html
    assert "草稿态 / 已发布态" in html
    assert "中央路由不在这里当普通提示词维护" in html


def test_run_center_agent_orchestration_metrics_subtab_renders_shadow_metrics(app, client):
    with app.app_context():
        create_agent_run(
            {
                "run_id": "arun-metrics-001",
                "request_id": "req-metrics-001",
                "external_contact_id": "wm_metrics_001",
                "userid": "sales_metrics",
                "agent_code": "central_router_agent",
                "agent_type": "router",
                "provider": "lobster_shadow",
                "input_snapshot": {"messages": [{"content": "课程怎么收费"}]},
                "variables_snapshot": {"current_pool": "inactive_normal"},
                "final_prompt_preview": "shadow_router_webhook",
                "role_prompt_version": "router-webhook",
                "task_prompt_version": "shadow-v1",
                "status": "success",
                "latency_ms": 180,
                "source": "test",
            }
        )
        append_agent_output(
            {
                "output_id": "aout-metrics-001",
                "run_id": "arun-metrics-001",
                "request_id": "req-metrics-001",
                "userid": "sales_metrics",
                "external_contact_id": "wm_metrics_001",
                "agent_code": "central_router_agent",
                "output_type": "route_decision",
                "raw_output_text": '{"agent_code":"pricing_agent"}',
                "normalized_output": {"agent_code": "pricing_agent", "confidence": 0.88, "reason": "价格问题"},
                "rendered_output_text": "价格问题",
                "target_agent_code": "pricing_agent",
                "target_pool": "inactive_normal",
                "confidence": 0.88,
                "reason": "价格问题",
                "applied_status": "shadow_observed",
                "outcome_status": "dispatch_success",
                "outcome_value": '{"queue_id":1}',
            }
        )

    response = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={"subtab": "metrics"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "最小指标" in html
    assert "调用量" in html
    assert "成功率" in html
    assert "兜底率" in html
    assert "协议非法率" in html
    assert "采纳率" in html
    assert "采纳后转化率" in html
    assert "pricing_agent" in html


def test_reply_monitor_dispatch_runs_router_shadow_mode_and_applies_async_callback(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_shadow_001", mobile="13800009181", owner_userid="sales_01", customer_name="shadow")
    _seed_automation_member(app, external_contact_id="wm_reply_shadow_001", phone="13800009181", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    for idx in range(1, 26):
        _seed_archived_message(
            app,
            msgid=f"msg-rm-shadow-{idx:03d}",
            seq=idx,
            external_userid="wm_reply_shadow_001",
            owner_userid="sales_01",
            sender="wm_reply_shadow_001" if idx % 2 else "sales_01",
            receiver="sales_01" if idx % 2 else "wm_reply_shadow_001",
            content=f"shadow message {idx}",
            send_time=f"2026-04-09 10:{idx:02d}:00",
        )
    _patch_reply_monitor_payload_context(monkeypatch, external_userid="wm_reply_shadow_001")

    captured_router: dict[str, object] = {}

    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _ShadowRouterResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    def _fake_router_post(url, data=None, headers=None, timeout=None):
        body = json.loads((data or b"{}").decode("utf-8"))
        captured_router.update(
            {
                "url": url,
                "body": body,
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        return _ShadowRouterResponse()

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", _fake_router_post)

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        queued_run = get_db().execute(
            """
            SELECT provider, agent_type, status, request_id
            FROM automation_agent_run
            WHERE agent_code = 'central_router_agent'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        queued_outputs = get_db().execute(
            """
            SELECT output_type, applied_status
            FROM automation_agent_output
            WHERE request_id = ?
            ORDER BY id ASC
            """
            ,
            (dict(queued_run)["request_id"],),
        ).fetchall()

    callback_payload = {
        "request_id": dict(queued_run)["request_id"],
        "external_contact_id": "wm_reply_shadow_001",
        "target_pool": "operating",
        "agent_code": "pricing_agent",
        "reason": "客户持续追问价格",
        "confidence": 0.91,
        "need_human_review": False,
        "completed_at": "2026-04-09 10:30:00",
    }
    callback_body = json.dumps(callback_payload, ensure_ascii=False)
    callback_signature = f"sha256={hmac.new(b'lobster-secret', callback_body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    callback_response = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=callback_body.encode("utf-8"),
        content_type="application/json",
        headers={
            "Authorization": "Bearer internal-token",
            "X-Lobster-Signature": callback_signature,
        },
    )

    with app.app_context():
        run_row = get_db().execute(
            """
            SELECT provider, agent_type, status, request_id
            FROM automation_agent_run
            WHERE agent_code = 'central_router_agent'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        output_row = get_db().execute(
            """
            SELECT output_type, target_agent_code, confidence, reason, need_human_review, applied_status, outcome_status, outcome_value
            FROM automation_agent_output
            WHERE agent_code = 'central_router_agent'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        member_row = get_db().execute(
            """
            SELECT current_pool, follow_type
            FROM automation_member
            WHERE external_contact_id = ?
            LIMIT 1
            """,
            ("wm_reply_shadow_001",),
        ).fetchone()

    assert dispatch["ok"] is True
    assert dispatch["shadow_router"]["shadow_called"] is True
    assert callback_response.status_code == 200
    assert callback_response.get_json()["status"] == "applied"
    assert captured_router["url"] == "https://lobster.example.com/router"
    assert captured_router["timeout"] == 5
    assert len(captured_router["body"]["recent_messages"]) == 20
    assert captured_router["body"]["external_contact_id"] == "wm_reply_shadow_001"
    assert set(captured_router["body"].keys()) == {"request_id", "external_contact_id", "recent_messages"}
    assert "userid" not in captured_router["body"]
    assert "messages" not in captured_router["body"]
    assert "member_snapshot" not in captured_router["body"]
    assert "allowed_agents" not in captured_router["body"]
    assert captured_router["headers"]["Authorization"] == "Bearer lobster-token"
    assert captured_router["headers"]["X-Shadow-Mode"] == "1"
    assert dict(run_row)["provider"] == "lobster_shadow"
    assert dict(run_row)["agent_type"] == "router"
    assert dict(run_row)["status"] == "applied"
    assert [dict(item)["output_type"] for item in queued_outputs] == [
        "route_ingress_sent",
        "route_ingress_acked",
    ]
    assert dict(output_row)["output_type"] == "route_decision"
    assert dict(output_row)["target_agent_code"] == "pricing_agent"
    assert dict(output_row)["confidence"] == pytest.approx(0.91)
    assert dict(output_row)["reason"] == "客户持续追问价格"
    assert dict(output_row)["need_human_review"] in {0, False}
    assert dict(output_row)["applied_status"] == "applied"
    assert dict(output_row)["outcome_status"] == "applied"
    assert '"final_target_pool": "operating"' in str(dict(output_row)["outcome_value"])
    assert dict(member_row) == {
        "current_pool": "operating",
        "follow_type": "normal",
    }


def test_reply_monitor_dispatch_posts_laohuang_chat_when_enabled(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    app.config["LAOHUANG_CHAT_ENABLED"] = "true"
    app.config["LAOHUANG_CHAT_WEBHOOK_URL"] = "https://ip.lhbl.com.cn/api/webhook/crm/chat"
    app.config["LAOHUANG_CHAT_TIMEOUT_SECONDS"] = 7
    _seed_contact(app, external_userid="wm_lh_dispatch_001", mobile="13800009201", owner_userid="sales_01", customer_name="lh-dispatch")
    _seed_automation_member(app, external_contact_id="wm_lh_dispatch_001", phone="13900009201", owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_status="submitted", decision_source="manual")
    last_message_id = _seed_archived_message(app, msgid="msg-lh-dispatch-001", seq=1, external_userid="wm_lh_dispatch_001", owner_userid="sales_01", sender="wm_lh_dispatch_001", receiver="sales_01", content="我想问下课程", send_time="2026-04-09 11:00:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.laohuang_chat_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "external_userid": external_userid,
            "mobile": "13800009201",
            "count": 3,
            "messages": [
                {"sender": "wm_lh_dispatch_001", "content": "用户消息", "send_time": "2026-04-09 10:58:00"},
                {"sender": "sales_01", "content": "历史员工回复", "send_time": "2026-04-09 10:59:00"},
                {"sender": "wm_lh_dispatch_001", "content": "用户最新消息", "send_time": "2026-04-09 11:00:00"},
            ],
        },
    )
    captured_requests: list[dict[str, object]] = []

    class _LaoHuangAcceptedResponse:
        ok = True
        status_code = 200
        text = '{"ok":true,"status":"accepted","task_id":"lh-task-001"}'

        def json(self):
            return {"ok": True, "status": "accepted", "task_id": "lh-task-001"}

    def _fake_post(url, json=None, timeout=None, **kwargs):
        captured_requests.append({"url": url, "json": json, "timeout": timeout, "kwargs": kwargs})
        return _LaoHuangAcceptedResponse()

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.laohuang_chat_service.requests.post", _fake_post)

    with app.app_context():
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        queue_row = get_db().execute(
            """
            SELECT status, payload_snapshot_json
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            LIMIT 1
            """,
            ("wm_lh_dispatch_001",),
        ).fetchone()
        job_row = get_db().execute(
            """
            SELECT queue_id, member_id, phone, external_message_id, external_session_id, laohuang_task_id,
                   request_payload_json, accepted_payload_json, status, send_channel
            FROM automation_laohuang_chat_job
            LIMIT 1
            """
        ).fetchone()

    request_body = captured_requests[0]["json"]
    assert capture["summary"]["created_queue_items"] == 1
    assert dispatch["ok"] is True
    assert dispatch["laohuang_chat"]["status"] == "accepted"
    assert captured_requests[0]["url"] == "https://ip.lhbl.com.cn/api/webhook/crm/chat"
    assert captured_requests[0]["timeout"] == 7
    assert "headers" not in captured_requests[0]["kwargs"]
    assert request_body["phone"] == "13900009201"
    assert request_body["messages"] == [
        {"role": "user", "content": "用户消息"},
        {"role": "assistant", "content": "历史员工回复"},
        {"role": "user", "content": "用户最新消息"},
    ]
    assert request_body["external_message_id"] == f"ai-crm:reply-monitor:1:{last_message_id}"
    assert request_body["external_session_id"] == "ai-crm:wm_lh_dispatch_001"
    assert request_body["source"] == "ai-crm"
    assert request_body["meta"]["queue_id"] == 1
    assert request_body["meta"]["external_contact_id"] == "wm_lh_dispatch_001"
    assert request_body["meta"]["owner_userid"] == "sales_01"
    assert dict(queue_row)["status"] == "dispatched"
    queue_snapshot = json.loads(dict(queue_row)["payload_snapshot_json"])
    assert queue_snapshot["bridge"] == "laohuang_chat"
    assert dict(job_row)["phone"] == "13900009201"
    assert dict(job_row)["external_message_id"] == f"ai-crm:reply-monitor:1:{last_message_id}"
    assert dict(job_row)["external_session_id"] == "ai-crm:wm_lh_dispatch_001"
    assert dict(job_row)["laohuang_task_id"] == "lh-task-001"
    assert dict(job_row)["status"] == "accepted"
    assert dict(job_row)["send_channel"] == "private_message"
    assert json.loads(dict(job_row)["request_payload_json"]) == request_body
    assert json.loads(dict(job_row)["accepted_payload_json"])["task_id"] == "lh-task-001"


def test_laohuang_chat_callback_stores_reply_without_auto_wecom_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_lh_callback_001", mobile="13800009211", owner_userid="sales_01", customer_name="lh-callback")
    _seed_automation_member(app, external_contact_id="wm_lh_callback_001", phone="13800009211", owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_status="submitted", decision_source="manual")
    with app.app_context():
        member = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ? LIMIT 1",
            ("wm_lh_callback_001",),
        ).fetchone()
        member_id = int(member["id"])
        get_db().execute(
            """
            INSERT INTO automation_laohuang_chat_job (
                queue_id, member_id, external_contact_id, phone, external_message_id, external_session_id,
                laohuang_task_id, request_payload_json, accepted_payload_json, callback_payload_json,
                status, send_channel, send_result_json, created_at, updated_at, finished_at
            )
            VALUES (NULL, ?, 'wm_lh_callback_001', '13800009211', 'ai-crm:reply-monitor:321:654',
                    'ai-crm:wm_lh_callback_001', 'lh-task-callback-001', '{}', '{}', '{}',
                    'accepted', 'private_message', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '')
            """,
            (member_id,),
        )
        get_db().commit()
    dispatched_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.laohuang_chat_service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": payload}),
    )
    callback_payload = {
        "task_id": "lh-task-callback-001",
        "source": "ai-crm",
        "external_session_id": "ai-crm:wm_lh_callback_001",
        "external_message_id": "ai-crm:reply-monitor:321:654",
        "status": "success",
        "phone": "13800009211",
        "user_id": "lh-user-001",
        "reply": "老黄 AI 生成的最终回复",
        "error_code": "",
        "error_message": "",
        "meta": {
            "queue_id": 321,
            "member_id": member_id,
            "external_contact_id": "wm_lh_callback_001",
            "owner_userid": "sales_01",
        },
    }

    response = client.post(
        "/api/internal/automation-conversion/laohuang-chat-results",
        json=callback_payload,
    )

    with app.app_context():
        job_row = get_db().execute(
            """
            SELECT status, reply_text, callback_payload_json, send_record_id, send_result_json, error_code, error_message, finished_at
            FROM automation_laohuang_chat_job
            WHERE external_message_id = ?
            LIMIT 1
            """,
            ("ai-crm:reply-monitor:321:654",),
        ).fetchone()
        send_record_total = int(get_db().execute("SELECT COUNT(*) AS total FROM user_ops_send_records").fetchone()["total"])

    assert response.status_code == 200
    assert response.get_json()["status"] == "callback_success"
    assert dispatched_payloads == []
    assert dict(job_row)["status"] == "callback_success"
    assert dict(job_row)["reply_text"] == "老黄 AI 生成的最终回复"
    assert dict(job_row)["error_code"] == ""
    assert dict(job_row)["error_message"] == ""
    assert dict(job_row)["finished_at"]
    assert json.loads(dict(job_row)["callback_payload_json"])["task_id"] == "lh-task-callback-001"
    assert json.loads(dict(job_row)["send_result_json"]) == {}
    assert dict(job_row)["send_record_id"] is None
    assert send_record_total == 0


def test_laohuang_review_output_wecom_send_api_records_send_result(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_lh_manual_send_001", mobile="13800009212", owner_userid="sales_01", customer_name="lh-manual-send")
    _seed_automation_member(app, external_contact_id="wm_lh_manual_send_001", phone="13800009212", owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_status="submitted", decision_source="manual")
    with app.app_context():
        member = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ? LIMIT 1",
            ("wm_lh_manual_send_001",),
        ).fetchone()
        member_id = int(member["id"])
        row = get_db().execute(
            """
            INSERT INTO automation_laohuang_chat_job (
                queue_id, member_id, external_contact_id, phone, external_message_id, external_session_id,
                laohuang_task_id, request_payload_json, accepted_payload_json, callback_payload_json,
                status, reply_text, send_channel, send_result_json, created_at, updated_at, finished_at
            )
            VALUES (NULL, ?, 'wm_lh_manual_send_001', '13800009212', 'ai-crm:reply-monitor:322:655',
                    'ai-crm:wm_lh_manual_send_001', 'lh-task-manual-send-001', '{}', '{}',
                    '{"meta":{"external_contact_id":"wm_lh_manual_send_001","owner_userid":"sales_01"},"reply":"手动推企微的话术"}',
                    'callback_success', '手动推企微的话术', 'private_message', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (member_id,),
        ).fetchone()
        job_id = int(row["id"])
        get_db().commit()
    dispatched_payloads: list[dict[str, object]] = []

    def _fake_dispatch(task_type, fn_name, payload):
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": payload})
        return {"task_id": 8802, "wecom_result": {"msgid": "wecom-msg-002", "fail_list": []}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.laohuang_chat_service.dispatch_wecom_task", _fake_dispatch)
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    response = client.post(
        f"/api/admin/automation-conversion/review-outputs/lhjob-{job_id}/send-via-wecom",
        json={
            "admin_action_token": "test-token",
            "operator": "console-user",
        },
    )
    payload = response.get_json()

    with app.app_context():
        job_row = get_db().execute(
            """
            SELECT status, send_record_id, send_result_json
            FROM automation_laohuang_chat_job
            WHERE id = ?
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        send_record = get_db().execute(
            """
            SELECT id, content_preview, selected_count, eligible_count, sent_count, status, filter_snapshot_json, operator
            FROM user_ops_send_records
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "send_success"
    assert dispatched_payloads == [
        {
            "task_type": "private_message",
            "fn_name": "create_private_message_task",
            "payload": {
                "sender": "sales_01",
                "external_userid": ["wm_lh_manual_send_001"],
                "text": {"content": "手动推企微的话术"},
            },
        }
    ]
    assert dict(job_row)["status"] == "send_success"
    assert int(dict(job_row)["send_record_id"]) == int(dict(send_record)["id"])
    assert json.loads(dict(job_row)["send_result_json"])["send_record_id"] == int(dict(send_record)["id"])
    assert dict(send_record)["content_preview"] == "手动推企微的话术"
    assert dict(send_record)["selected_count"] == 1
    assert dict(send_record)["eligible_count"] == 1
    assert dict(send_record)["sent_count"] == 1
    assert dict(send_record)["status"] == "sent"
    assert dict(send_record)["operator"] == "console-user"
    assert json.loads(dict(send_record)["filter_snapshot_json"])["source"] == "laohuang_chat_manual_wecom"


def test_router_callback_is_idempotent_after_first_apply(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_idempotent_001", mobile="13800009182", owner_userid="sales_01", customer_name="idempotent")
    _seed_automation_member(app, external_contact_id="wm_reply_idempotent_001", phone="13800009182", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-idempotent-001", seq=1, external_userid="wm_reply_idempotent_001", owner_userid="sales_01", sender="wm_reply_idempotent_001", receiver="sales_01", content="我想继续了解", send_time="2026-04-09 11:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        request_id = dispatch["router_ingress"]["request_id"]

    first_payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_idempotent_001",
        "target_pool": "operating",
        "agent_code": "pricing_agent",
        "reason": "继续咨询价格",
        "confidence": 0.88,
        "need_human_review": False,
    }
    first_body = json.dumps(first_payload, ensure_ascii=False)
    signature_1 = f"sha256={hmac.new(b'lobster-secret', first_body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    first = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=first_body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature_1},
    )
    second_payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_idempotent_001",
        "target_pool": "converted",
        "agent_code": "closing_agent",
        "reason": "重复回调",
        "confidence": 0.95,
        "need_human_review": False,
    }
    second_body = json.dumps(second_payload, ensure_ascii=False)
    signature_2 = f"sha256={hmac.new(b'lobster-secret', second_body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    second = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=second_body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature_2},
    )

    with app.app_context():
        outputs = get_db().execute(
            """
            SELECT output_type
            FROM automation_agent_output
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (request_id,),
        ).fetchall()
        member_row = get_db().execute(
            """
            SELECT current_pool
            FROM automation_member
            WHERE external_contact_id = ?
            LIMIT 1
            """,
            ("wm_reply_idempotent_001",),
        ).fetchone()

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["status"] == "idempotent"
    assert dict(member_row)["current_pool"] == "operating"
    assert [dict(item)["output_type"] for item in outputs] == [
        "route_ingress_sent",
        "route_ingress_acked",
        "callback_received",
        "callback_validated",
        "route_decision",
    ]


def test_router_callback_stores_reply_draft_output_when_payload_contains_reply_text(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_draft_001", mobile="13800009187", owner_userid="sales_01", customer_name="draft")
    _seed_automation_member(app, external_contact_id="wm_reply_draft_001", phone="13800009187", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-draft-001", seq=1, external_userid="wm_reply_draft_001", owner_userid="sales_01", sender="wm_reply_draft_001", receiver="sales_01", content="价格怎么安排", send_time="2026-04-09 11:30:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        request_id = dispatch["router_ingress"]["request_id"]

    payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_draft_001",
        "target_pool": "operating",
        "agent_code": "pricing_agent",
        "reason": "客户在追问价格",
        "confidence": 0.93,
        "need_human_review": False,
        "next_action": "quote_explain",
        "reply_draft": "我先把课程方案和价格区间给你拆开说明，你可以先看下更关注哪一档。",
    }
    body = json.dumps(payload, ensure_ascii=False)
    signature = f"sha256={hmac.new(b'lobster-secret', body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    response = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature},
    )

    with app.app_context():
        reply_output = get_db().execute(
            """
            SELECT agent_code, output_type, rendered_output_text, normalized_output_json, request_id
            FROM automation_agent_output
            WHERE request_id = ? AND output_type = 'agent_reply_draft'
            ORDER BY id DESC
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()

    assert response.status_code == 200
    assert reply_output is not None
    assert dict(reply_output)["agent_code"] == "pricing_agent"
    assert dict(reply_output)["rendered_output_text"] == "我先把课程方案和价格区间给你拆开说明，你可以先看下更关注哪一档。"
    assert json.loads(reply_output["normalized_output_json"])["draft_reply"] == "我先把课程方案和价格区间给你拆开说明，你可以先看下更关注哪一档。"


def test_router_callback_generates_child_reply_draft_when_callback_only_routes(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_autodraft_001", mobile="13800009188", owner_userid="sales_01", customer_name="auto-draft")
    _seed_automation_member(app, external_contact_id="wm_reply_autodraft_001", phone="13800009188", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-autodraft-001", seq=1, external_userid="wm_reply_autodraft_001", owner_userid="sales_01", sender="wm_reply_autodraft_001", receiver="sales_01", content="能说下价格吗", send_time="2026-04-09 11:45:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    def _fake_generate_child_agent_reply_output(**kwargs):
        with app.app_context():
            return append_agent_output(
                {
                    "run_id": kwargs["request_id"],
                    "request_id": kwargs["request_id"],
                    "userid": kwargs["userid"],
                    "external_contact_id": kwargs["external_contact_id"],
                    "agent_code": kwargs["agent_code"],
                    "output_type": "agent_reply_draft",
                    "raw_output_text": "自动补的一条价格说明草稿",
                    "normalized_output": {
                        "agent_code": kwargs["agent_code"],
                        "target_pool": kwargs["target_pool"],
                        "draft_reply": "自动补的一条价格说明草稿",
                        "reason": kwargs["reason"],
                    },
                    "rendered_output_text": "自动补的一条价格说明草稿",
                    "target_agent_code": kwargs["agent_code"],
                    "target_pool": kwargs["target_pool"],
                    "confidence": kwargs["confidence"],
                    "reason": kwargs["reason"],
                    "applied_status": "generated",
                }
            )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.orchestration_service._generate_child_agent_reply_output",
        _fake_generate_child_agent_reply_output,
    )

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        request_id = dispatch["router_ingress"]["request_id"]

    payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_autodraft_001",
        "target_pool": "operating",
        "agent_code": "pricing_agent",
        "reason": "客户需要价格说明",
        "confidence": 0.91,
        "need_human_review": False,
    }
    body = json.dumps(payload, ensure_ascii=False)
    signature = f"sha256={hmac.new(b'lobster-secret', body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    response = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature},
    )

    with app.app_context():
        reply_output = get_db().execute(
            """
            SELECT output_type, rendered_output_text
            FROM automation_agent_output
            WHERE request_id = ? AND output_type = 'agent_reply_draft'
            ORDER BY id DESC
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()

    assert response.status_code == 200
    assert response.get_json()["reply_output_id"]
    assert dict(reply_output)["rendered_output_text"] == "自动补的一条价格说明草稿"


def test_backfill_missing_child_agent_replies_generates_once_for_historical_route_decision(app, monkeypatch):
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-backfill-route-001",
                "request_id": "req-backfill-route-001",
                "userid": "sales_backfill",
                "external_contact_id": "wm_backfill_001",
                "agent_code": "central_router_agent",
                "agent_type": "router",
                "provider": "lobster",
                "status": "completed",
                "source": "test",
            }
        )
        append_agent_output(
            {
                "output_id": "aout-backfill-route-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_backfill",
                "external_contact_id": "wm_backfill_001",
                "agent_code": "central_router_agent",
                "output_type": "route_decision",
                "raw_output_text": '{"agent_code":"pricing_agent"}',
                "normalized_output": {
                    "agent_code": "pricing_agent",
                    "target_pool": "inactive_focus",
                    "confidence": 0.92,
                    "reason": "客户在追问价格",
                    "need_human_review": False,
                },
                "rendered_output_text": "pricing_agent -> inactive_focus",
                "target_agent_code": "pricing_agent",
                "target_pool": "inactive_focus",
                "confidence": 0.92,
                "reason": "客户在追问价格",
                "applied_status": "applied",
            }
        )

    def _fake_generate_child_agent_reply_output(**kwargs):
        with app.app_context():
            return append_agent_output(
                {
                    "run_id": "arun-backfill-generated-001",
                    "request_id": kwargs["request_id"],
                    "userid": kwargs["userid"],
                    "external_contact_id": kwargs["external_contact_id"],
                    "agent_code": kwargs["agent_code"],
                    "output_type": "agent_reply_draft",
                    "raw_output_text": "这是历史补生成的话术",
                    "normalized_output": {
                        "agent_code": kwargs["agent_code"],
                        "target_pool": kwargs["target_pool"],
                        "draft_reply": "这是历史补生成的话术",
                    },
                    "rendered_output_text": "这是历史补生成的话术",
                    "target_agent_code": kwargs["agent_code"],
                    "target_pool": kwargs["target_pool"],
                    "confidence": kwargs["confidence"],
                    "reason": kwargs["reason"],
                    "applied_status": "generated",
                }
            )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.orchestration_service._generate_child_agent_reply_output",
        _fake_generate_child_agent_reply_output,
    )

    with app.app_context():
        first = backfill_missing_child_agent_replies(operator_id="tester-backfill", request_id="req-backfill-route-001", limit=10)
        second = backfill_missing_child_agent_replies(operator_id="tester-backfill", request_id="req-backfill-route-001", limit=10)
        rows = get_db().execute(
            """
            SELECT output_type, rendered_output_text
            FROM automation_agent_output
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            ("req-backfill-route-001",),
        ).fetchall()

    assert first["created_count"] == 1
    assert first["failed_count"] == 0
    assert second["created_count"] == 0
    assert second["skipped_count"] >= 1
    assert [dict(row)["output_type"] for row in rows] == ["route_decision", "agent_reply_draft"]
    assert dict(rows[-1])["rendered_output_text"] == "这是历史补生成的话术"


def test_router_callback_rejects_invalid_target_pool_and_records_error(app, client, monkeypatch):
    _configure_reply_monitor(
        app,
        enabled=True,
        last_capture_cursor=0,
        quiet_hours_start="02:00",
        quiet_hours_end="03:00",
    )
    _seed_contact(app, external_userid="wm_reply_invalid_pool_001", mobile="13800009183", owner_userid="sales_01", customer_name="invalid-pool")
    _seed_automation_member(app, external_contact_id="wm_reply_invalid_pool_001", phone="13800009183", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-invalid-pool-001", seq=1, external_userid="wm_reply_invalid_pool_001", owner_userid="sales_01", sender="wm_reply_invalid_pool_001", receiver="sales_01", content="给我个方案", send_time="2026-04-09 12:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        request_id = dispatch["router_ingress"]["request_id"]

    payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_invalid_pool_001",
        "target_pool": "unknown_pool",
        "agent_code": "pricing_agent",
        "reason": "非法池子",
        "confidence": 0.92,
        "need_human_review": False,
    }
    body = json.dumps(payload, ensure_ascii=False)
    signature = f"sha256={hmac.new(b'lobster-secret', body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    response = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature},
    )

    with app.app_context():
        run_row = get_db().execute(
            """
            SELECT status, error_code
            FROM automation_agent_run
            WHERE request_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()
        member_row = get_db().execute(
            """
            SELECT current_pool
            FROM automation_member
            WHERE external_contact_id = ?
            LIMIT 1
            """,
            ("wm_reply_invalid_pool_001",),
        ).fetchone()
        outputs = get_db().execute(
            """
            SELECT output_type
            FROM automation_agent_output
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (request_id,),
        ).fetchall()

    assert response.status_code == 409
    assert response.get_json()["error"] == "invalid_target_pool"
    assert dict(run_row) == {
        "status": "rejected",
        "error_code": "invalid_target_pool",
    }
    assert [dict(item)["output_type"] for item in outputs] == [
        "route_ingress_sent",
        "route_ingress_acked",
        "callback_received",
        "callback_rejected",
    ]
    assert dict(member_row)["current_pool"] == "operating"


def test_router_pending_callbacks_api_lists_acked_runs_without_callback(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_pending_001", mobile="13800009184", owner_userid="sales_01", customer_name="pending")
    _seed_automation_member(app, external_contact_id="wm_reply_pending_001", phone="13800009184", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-pending-001", seq=1, external_userid="wm_reply_pending_001", owner_userid="sales_01", sender="wm_reply_pending_001", receiver="sales_01", content="我想再了解一下", send_time="2026-04-09 13:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        get_db().execute(
            "UPDATE automation_agent_run SET updated_at = '2026-04-09 12:00:00' WHERE run_id = ?",
            (dispatch["router_ingress"]["run_id"],),
        )
        get_db().commit()

    response = client.get(
        "/api/admin/automation-conversion/router-pending-callbacks",
        query_string={"older_than_minutes": 1, "limit": 10},
        headers={"Authorization": "Bearer internal-token"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["total"] >= 1
    assert any(item["run"]["request_id"] == dispatch["router_ingress"]["request_id"] for item in payload["rows"])


def test_router_callback_uses_optional_metadata_and_configurable_review_pool(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_meta_001", mobile="13800009185", owner_userid="sales_01", customer_name="meta")
    _seed_automation_member(app, external_contact_id="wm_reply_meta_001", phone="13800009185", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-meta-001", seq=1, external_userid="wm_reply_meta_001", owner_userid="sales_01", sender="wm_reply_meta_001", receiver="sales_01", content="这个方案需要人工讲一下", send_time="2026-04-09 14:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "min_confidence": 0.95,
                    "human_review_target_pool": "silent",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        request_id = dispatch["router_ingress"]["request_id"]

    callback_payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_meta_001",
        "target_pool": "operating",
        "agent_code": "pricing_agent",
        "reason": "建议转人工看方案",
        "confidence": 0.96,
        "need_human_review": True,
        "trace_id": "trace-meta-001",
        "processing_latency_ms": 1820,
        "prompt_version_used": "pricing_agent@draft_v3",
        "mcp_tools_used": ["crm.get_member_basic", "get_all_agent_prompts"],
        "completed_at": "2026-04-09 14:05:00",
    }
    body = json.dumps(callback_payload, ensure_ascii=False)
    signature = f"sha256={hmac.new(b'lobster-secret', body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    response = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature},
    )

    with app.app_context():
        run_row = get_db().execute(
            "SELECT variables_snapshot_json FROM automation_agent_run WHERE request_id = ? LIMIT 1",
            (request_id,),
        ).fetchone()
        output_row = get_db().execute(
            "SELECT normalized_output_json FROM automation_agent_output WHERE request_id = ? AND output_type = 'route_decision' LIMIT 1",
            (request_id,),
        ).fetchone()
        member_row = get_db().execute(
            "SELECT current_pool FROM automation_member WHERE external_contact_id = ? LIMIT 1",
            ("wm_reply_meta_001",),
        ).fetchone()

    assert response.status_code == 200
    assert dict(member_row)["current_pool"] == "human_reply"
    assert json.loads(run_row["variables_snapshot_json"])["callback_meta"] == {
        "trace_id": "trace-meta-001",
        "processing_latency_ms": 1820,
        "prompt_version_used": "pricing_agent@draft_v3",
        "mcp_tools_used": ["crm.get_member_basic", "get_all_agent_prompts"],
        "completed_at": "2026-04-09 14:05:00",
    }
    structured_result = json.loads(output_row["normalized_output_json"])["structured_result"]
    assert structured_result["trace_id"] == "trace-meta-001"
    assert structured_result["processing_latency_ms"] == 1820
    assert structured_result["prompt_version_used"] == "pricing_agent@draft_v3"


def test_router_callback_replay_api_replays_stored_callback_payload(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_replay_001", mobile="13800009186", owner_userid="sales_01", customer_name="replay")
    _seed_automation_member(app, external_contact_id="wm_reply_replay_001", phone="13800009186", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-replay-001", seq=1, external_userid="wm_reply_replay_001", owner_userid="sales_01", sender="wm_reply_replay_001", receiver="sales_01", content="我要价格", send_time="2026-04-09 15:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        request_id = dispatch["router_ingress"]["request_id"]
        run_id = dispatch["router_ingress"]["run_id"]

    callback_payload = {
        "request_id": request_id,
        "external_contact_id": "wm_reply_replay_001",
        "target_pool": "operating",
        "agent_code": "pricing_agent",
        "reason": "价格意图明确",
        "confidence": 0.92,
        "need_human_review": False,
    }
    body = json.dumps(callback_payload, ensure_ascii=False)
    signature = f"sha256={hmac.new(b'lobster-secret', body.encode('utf-8'), hashlib.sha256).hexdigest()}"
    callback_response = client.post(
        "/api/internal/automation-conversion/lobster-results",
        data=body.encode("utf-8"),
        content_type="application/json",
        headers={"Authorization": "Bearer internal-token", "X-Lobster-Signature": signature},
    )
    replay_response = client.post(
        f"/api/admin/automation-conversion/router-callback-replay/{run_id}",
        headers={"Authorization": "Bearer internal-token"},
    )

    assert callback_response.status_code == 200
    assert replay_response.status_code == 200
    assert replay_response.get_json()["ok"] is True
    assert replay_response.get_json()["replayed"] is True
    assert replay_response.get_json()["result"]["status"] == "applied"
    assert "callback-replay" in replay_response.get_json()["request_id"]


def test_special_router_pools_are_recognized_by_crm_stage_payloads(app, client):
    _seed_contact(app, external_userid="wm_router_no_reply_001", mobile="13800009801", owner_userid="sales_router", customer_name="无需回复客户")
    _seed_contact(app, external_userid="wm_router_human_001", mobile="13800009802", owner_userid="sales_router", customer_name="人工回复客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_router_no_reply_001",
        phone="13800009801",
        owner_staff_id="sales_router",
        current_pool="no_reply",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="system",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_router_human_001",
        phone="13800009802",
        owner_staff_id="sales_router",
        current_pool="human_reply",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="system",
    )

    with app.app_context():
        no_reply_detail = get_member_detail(external_contact_id="wm_router_no_reply_001")
        human_reply_detail = get_member_detail(external_contact_id="wm_router_human_001")
        no_reply_stage = get_stage_detail_payload(route_key="no-reply", limit=10, offset=0)
        human_reply_stage = get_stage_detail_payload(route_key="human-reply", limit=10, offset=0)

    assert no_reply_detail["member"]["current_pool_label"] == "不回复池"
    assert no_reply_detail["member"]["current_stage_label"] == "不回复待观察"
    assert human_reply_detail["member"]["current_pool_label"] == "人工回复池"
    assert human_reply_detail["member"]["current_target_label"] == "转人工回复"
    assert no_reply_stage["stage"]["pool"] == "no_reply"
    assert no_reply_stage["stage"]["label"] == "不回复池"
    assert no_reply_stage["pagination"]["total"] == 1
    assert human_reply_stage["stage"]["pool"] == "human_reply"
    assert human_reply_stage["stage"]["label"] == "人工回复池"
    assert human_reply_stage["pagination"]["total"] == 1


def test_automation_conversion_home_stage_cards_route_renders_program_list_without_legacy_actions(app, client):
    program_id = _default_program_id(app)
    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "方案列表" in html
    assert "方案总数" in html
    assert "当前所有可见自动化运营方案" in html
    assert f"/admin/automation-conversion/programs/{program_id}/overview" in html
    assert "编辑" in html
    assert "消息活跃同步" not in html
    assert "立即刷新一次" not in html
    assert 'data-message-activity-sync-root' not in html
    assert 'data-message-activity-sync-button' not in html
    assert "阶段漏斗" not in html
    assert "进入成员运营" not in html
    assert "创建群发" not in html


def test_automation_conversion_home_page_renders_message_activity_sync_summary(app, client, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_home_sync_001", mobile="13800009441", owner_userid="sales_home", customer_name="首页同步客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_home_sync_001",
        phone="13800009441",
        owner_staff_id="sales_home",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [{"phone_prefix3": "138", "phone_last4": "9441", "phone_match_key": "138_9441", "message_count": 6}],
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service._iso_now",
        lambda: "2026-04-08 10:30:00",
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="home-sync",
            operator_type="user",
            trigger_source="manual",
        )
        assert payload["ok"] is True

    program_id = _default_program_id(app)
    response = client.get(f"/admin/automation-conversion/programs/{program_id}/overview")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "刷新模块状态" in html
    assert "消息活跃同步" in html
    assert f"/admin/automation-conversion/programs/{program_id}/overview/message-activity-sync/run" in html
    assert "顺序执行消息活跃同步、自动接话扫描、自动接话放行" in html


def test_admin_automation_program_overview_message_activity_sync_returns_json(app, client, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_home_run_001", mobile="13800009442", owner_userid="sales_home", customer_name="首页运行客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_home_run_001",
        phone="13800009442",
        owner_staff_id="sales_home",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.message_activity_service.query_message_activity_counts",
        lambda: [{"phone_prefix3": "138", "phone_last4": "9442", "phone_match_key": "138_9442", "message_count": 8}],
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service._iso_now",
        lambda: "2026-04-08 10:40:00",
    )

    program_id = _default_program_id(app)
    response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/overview/message-activity-sync/run",
        data={"admin_action_token": "ok", "operator": "homepage-sync"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["message"] == "消息活跃同步已完成"
    assert payload["run"]["updated_count"] == 1
    assert payload["message_activity_sync"]["last_run"]["status_label"] == "成功"
    assert payload["message_activity_sync"]["last_run"]["finished_at"] == "2026-04-08 10:40:00"
    assert payload["message_activity_sync"]["last_run"]["updated_count"] == 1
    assert payload["message_activity_sync"]["last_run"]["skipped_count"] == 0


def test_automation_conversion_home_page_renders_reply_monitor_section(app, client):
    _configure_reply_monitor(app, enabled=False)

    response = client.get("/admin/automation-conversion/auto-reply")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动接话监控" in html
    assert "已关闭" in html
    assert "开启监控" in html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/toggle" in html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/capture" in html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/run-due" in html
    assert "/admin/automation-conversion/reply-monitor/toggle" not in html
    assert "/admin/automation-conversion/reply-monitor/capture" not in html
    assert "/admin/automation-conversion/reply-monitor/run-due" not in html


def test_automation_browser_post_legacy_routes_are_removed(app, client):
    old_routes = {
        "/admin/automation-conversion/overview/signup-tag/apply",
        "/admin/automation-conversion/message-activity-sync/run",
        "/admin/automation-conversion/reply-monitor/toggle",
        "/admin/automation-conversion/reply-monitor/capture",
        "/admin/automation-conversion/reply-monitor/run-due",
    }
    old_endpoints = {
        f"api.admin_automation_conversion_{suffix}"
        for suffix in (
            "apply_overview_signup_tag",
            "run_message_activity_sync",
            "reply_monitor_toggle",
            "reply_monitor_capture",
            "reply_monitor_run_due",
        )
    }
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    endpoints = set(app.view_functions.keys())

    assert old_routes.isdisjoint(rules)
    assert old_endpoints.isdisjoint(endpoints)
    for path in sorted(old_routes):
        assert client.post(path).status_code in {404, 405}


def test_automation_browser_post_routes_require_admin_action_token(app, client, monkeypatch):
    program_id = _default_program_id(app)
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.apply_dashboard_signup_tag",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("apply_dashboard_signup_tag should not be called")),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_message_activity_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_message_activity_sync should not be called")),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.save_reply_monitor_enabled",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("save_reply_monitor_enabled should not be called")),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_reply_monitor_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_reply_monitor_capture should not be called")),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_due_reply_monitor",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_due_reply_monitor should not be called")),
    )
    headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
    paths = [
        f"/admin/automation-conversion/programs/{program_id}/overview/signup-tag/apply",
        f"/admin/automation-conversion/programs/{program_id}/overview/message-activity-sync/run",
        "/admin/automation-conversion/auto-reply/reply-monitor/toggle",
        "/admin/automation-conversion/auto-reply/reply-monitor/capture",
        "/admin/automation-conversion/auto-reply/reply-monitor/run-due",
    ]

    for path in paths:
        response = client.post(path, data={"enabled": "1"}, headers=headers)
        assert response.status_code == 400
        assert "令牌" in response.get_json()["error"]


def test_automation_pages_use_browser_safe_post_urls_not_internal_apis(app, client):
    program_id = _default_program_id(app)

    overview_response = client.get(f"/admin/automation-conversion/programs/{program_id}/overview")
    overview_html = overview_response.get_data(as_text=True)

    assert overview_response.status_code == 200
    assert f"/admin/automation-conversion/programs/{program_id}/overview/signup-tag/apply" in overview_html
    assert f"/admin/automation-conversion/programs/{program_id}/overview/message-activity-sync/run" in overview_html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/capture" in overview_html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/run-due" in overview_html
    assert "/api/admin/automation-conversion/message-activity-sync/run" not in overview_html
    assert "/api/admin/automation-conversion/reply-monitor/capture" not in overview_html
    assert "/api/admin/automation-conversion/reply-monitor/run-due" not in overview_html

    auto_reply_response = client.get("/admin/automation-conversion/auto-reply")
    auto_reply_html = auto_reply_response.get_data(as_text=True)

    assert auto_reply_response.status_code == 200
    assert "/admin/automation-conversion/auto-reply/reply-monitor/toggle" in auto_reply_html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/capture" in auto_reply_html
    assert "/admin/automation-conversion/auto-reply/reply-monitor/run-due" in auto_reply_html
    assert "/api/admin/automation-conversion/reply-monitor/capture" not in auto_reply_html
    assert "/api/admin/automation-conversion/reply-monitor/run-due" not in auto_reply_html


def test_automation_internal_apis_require_internal_token_when_configured(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_message_activity_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_message_activity_sync should not be called")),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_reply_monitor_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_reply_monitor_capture should not be called")),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_due_reply_monitor",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_due_reply_monitor should not be called")),
    )

    paths = [
        "/api/admin/automation-conversion/message-activity-sync/run",
        "/api/admin/automation-conversion/reply-monitor/capture",
        "/api/admin/automation-conversion/reply-monitor/run-due",
    ]

    for path in paths:
        response = client.post(path, json={"limit": 10, "trigger_source": "scheduled"})
        assert response.status_code == 401
        assert response.get_json()["error"] == "missing internal token"


def test_automation_auto_reply_monitor_browser_routes_return_json(app, client, monkeypatch):
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.save_reply_monitor_enabled",
        lambda *, enabled, operator_id: calls.append(("toggle", enabled)),
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_reply_monitor_capture",
        lambda *, operator_id, operator_type: {"ok": True, "status": "captured", "message": "扫描完成"},
    )
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_due_reply_monitor",
        lambda *, operator_id, operator_type: {"ok": True, "status": "idle", "message": "本次无到期项"},
    )
    headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}

    toggle = client.post(
        "/admin/automation-conversion/auto-reply/reply-monitor/toggle",
        data={"admin_action_token": "ok", "enabled": "1"},
        headers=headers,
    )
    capture = client.post(
        "/admin/automation-conversion/auto-reply/reply-monitor/capture",
        data={"admin_action_token": "ok"},
        headers=headers,
    )
    run_due = client.post(
        "/admin/automation-conversion/auto-reply/reply-monitor/run-due",
        data={"admin_action_token": "ok"},
        headers=headers,
    )

    assert toggle.status_code == 200
    assert toggle.get_json()["ok"] is True
    assert toggle.get_json()["status"] == "enabled"
    assert calls == [("toggle", True)]
    assert capture.status_code == 200
    assert capture.get_json()["ok"] is True
    assert capture.get_json()["status"] == "captured"
    assert run_due.status_code == 200
    assert run_due.get_json()["ok"] is True
    assert run_due.get_json()["status"] == "idle"


def test_reply_monitor_capture_filters_private_inbound_messages_and_groups_by_user(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_001", mobile="13800009101", owner_userid="sales_01", customer_name="reply-1")
    _seed_contact(app, external_userid="wm_reply_002", mobile="13800009102", owner_userid="sales_01", customer_name="reply-2")
    _seed_contact(app, external_userid="wm_reply_003", mobile="13800009103", owner_userid="sales_01", customer_name="reply-3")
    _seed_automation_member(app, external_contact_id="wm_reply_001", phone="13800009101", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_follow_type="focus", decision_source="questionnaire")
    _seed_automation_member(app, external_contact_id="wm_reply_002", phone="13800009102", owner_staff_id="sales_01", current_pool="active_normal", follow_type="normal", activation_status="active", questionnaire_follow_type="normal", decision_source="questionnaire")

    _seed_archived_message(app, msgid="msg-rm-001", seq=1, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", content="你好 1", send_time="2026-04-09 10:00:01")
    _seed_archived_message(app, msgid="msg-rm-002", seq=2, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", content="你好 2", send_time="2026-04-09 10:00:02")
    _seed_archived_message(app, msgid="msg-rm-003", seq=3, external_userid="wm_reply_001", owner_userid="sales_01", sender="sales_01", receiver="wm_reply_001", content="客服回复", send_time="2026-04-09 10:00:03")
    _seed_archived_message(app, msgid="msg-rm-004", seq=4, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", chat_type="group", content="群聊消息", send_time="2026-04-09 10:00:04")
    _seed_archived_message(app, msgid="msg-rm-005", seq=5, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", msgtype="event", content="系统事件", send_time="2026-04-09 10:00:05")
    _seed_archived_message(app, msgid="msg-rm-006", seq=6, external_userid="wm_reply_002", owner_userid="sales_01", sender="wm_reply_002", receiver="sales_01", content="另一个客户", send_time="2026-04-09 10:00:06")
    _seed_archived_message(app, msgid="msg-rm-007", seq=7, external_userid="wm_reply_003", owner_userid="sales_01", sender="wm_reply_003", receiver="sales_01", content="非自动化用户", send_time="2026-04-09 10:00:07")

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:05:00")

    with app.app_context():
        payload = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        queue_rows = get_db().execute(
            """
            SELECT external_userid, owner_userid, status, message_count, message_ids_json
            FROM automation_reply_monitor_queue
            ORDER BY external_userid ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["summary"] == {
        "cursor_from": 0,
        "cursor_to": 7,
        "scanned_new_messages": 7,
        "candidate_messages": 4,
        "hit_users": 2,
        "created_queue_items": 2,
        "merged_queue_items": 0,
    }
    assert [dict(row) for row in queue_rows] == [
        {
            "external_userid": "wm_reply_001",
            "owner_userid": "sales_01",
            "status": "pending",
            "message_count": 2,
            "message_ids_json": json.dumps([1, 2]),
        },
        {
            "external_userid": "wm_reply_002",
            "owner_userid": "sales_01",
            "status": "pending",
            "message_count": 1,
            "message_ids_json": json.dumps([6]),
        },
    ]


def test_reply_monitor_capture_merges_new_messages_into_existing_pending_item(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_merge_001", mobile="13800009111", owner_userid="sales_01", customer_name="reply-merge")
    _seed_automation_member(app, external_contact_id="wm_reply_merge_001", phone="13800009111", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_follow_type="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-merge-001", seq=1, external_userid="wm_reply_merge_001", owner_userid="sales_01", sender="wm_reply_merge_001", receiver="sales_01", content="第一条", send_time="2026-04-09 10:00:01")

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:01:00")
    with app.app_context():
        first = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
    assert first["summary"]["created_queue_items"] == 1

    _seed_archived_message(app, msgid="msg-rm-merge-002", seq=2, external_userid="wm_reply_merge_001", owner_userid="sales_01", sender="wm_reply_merge_001", receiver="sales_01", content="第二条", send_time="2026-04-09 10:02:01")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:03:00")

    with app.app_context():
        second = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        row = get_db().execute(
            """
            SELECT status, message_count, message_ids_json
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_reply_merge_001",),
        ).fetchone()

    assert second["summary"]["created_queue_items"] == 0
    assert second["summary"]["merged_queue_items"] == 1
    assert dict(row) == {
        "status": "pending",
        "message_count": 2,
        "message_ids_json": json.dumps([1, 2]),
    }


def test_reply_monitor_capture_and_dispatch_respect_quiet_hours(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="23:00", quiet_hours_end="09:00")
    _seed_contact(app, external_userid="wm_reply_quiet_001", mobile="13800009121", owner_userid="sales_01", customer_name="reply-quiet")
    _seed_automation_member(app, external_contact_id="wm_reply_quiet_001", phone="13800009121", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_follow_type="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-quiet-001", seq=1, external_userid="wm_reply_quiet_001", owner_userid="sales_01", sender="wm_reply_quiet_001", receiver="sales_01", content="夜间消息", send_time="2026-04-09 23:14:00")

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 23:15:00")
    sent_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook",
        lambda **kwargs: sent_payloads.append(kwargs) or {"ok": True, "delivery": {"id": 9001}},
    )

    with app.app_context():
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        queue_row = get_db().execute(
            """
            SELECT status, not_before, message_count
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            """,
            ("wm_reply_quiet_001",),
        ).fetchone()
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="user")

    assert capture["ok"] is True
    assert dict(queue_row) == {
        "status": "deferred_quiet_hours",
        "not_before": "2026-04-10 09:00:00",
        "message_count": 1,
    }
    assert dispatch["ok"] is True
    assert dispatch["status"] == "quiet_hours"
    assert dispatch["summary"]["deferred_count"] == 0
    assert sent_payloads == []


def test_reply_monitor_dispatch_releases_due_items_one_by_one_with_30_second_gap(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, dispatch_interval_seconds=30)
    for external_userid, mobile in [("wm_reply_due_001", "13800009131"), ("wm_reply_due_002", "13800009132")]:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_01", customer_name=external_userid)
        _seed_automation_member(app, external_contact_id=external_userid, phone=mobile, owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_follow_type="focus", decision_source="manual")
    _seed_archived_message(app, msgid="msg-rm-due-001", seq=1, external_userid="wm_reply_due_001", owner_userid="sales_01", sender="wm_reply_due_001", receiver="sales_01", content="白天发送一", send_time="2026-04-09 23:29:01")
    _seed_archived_message(app, msgid="msg-rm-due-002", seq=2, external_userid="wm_reply_due_002", owner_userid="sales_01", sender="wm_reply_due_002", receiver="sales_01", content="白天发送二", send_time="2026-04-09 23:29:02")
    _patch_reply_monitor_payload_context(monkeypatch, external_userid="wm_reply_due_001")
    router_requests: list[dict[str, object]] = []

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    def _fake_router_post(url, data=None, headers=None, timeout=None):
        router_requests.append({"url": url, "body": json.loads((data or b"{}").decode("utf-8"))})
        return _AckResponse()

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", _fake_router_post)

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 23:30:00")
    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        queued = get_db().execute(
            """
            SELECT external_userid, status, not_before
            FROM automation_reply_monitor_queue
            ORDER BY id ASC
            """
        ).fetchall()
    assert capture["summary"]["created_queue_items"] == 2
    assert [dict(item) for item in queued] == [
        {"external_userid": "wm_reply_due_001", "status": "deferred_quiet_hours", "not_before": "2026-04-10 09:00:00"},
        {"external_userid": "wm_reply_due_002", "status": "deferred_quiet_hours", "not_before": "2026-04-10 09:00:30"},
    ]

    monkeypatch.setattr("wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload", lambda *, external_userid: {"tags": [{"tag_name": "高潜客户"}]})
    monkeypatch.setattr("wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload", lambda *, external_userid="", mobile="": {"answers": [{"question": "预算", "answer": "999"}]})
    monkeypatch.setattr("wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload", lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {"messages": []})

    with app.app_context():
        monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:00")
        first = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:10")
        throttled = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:31")
        second = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")

    assert first["ok"] is True
    assert first["status"] == "success"
    assert throttled["ok"] is True
    assert throttled["status"] == "throttled"
    assert second["ok"] is True
    assert second["status"] == "success"
    assert len(router_requests) == 2


def test_reply_monitor_disabled_does_not_create_queue_items(app):
    _configure_reply_monitor(app, enabled=False, last_capture_cursor=0)
    _seed_archived_message(app, msgid="msg-rm-disabled-001", seq=1, external_userid="wm_reply_disabled_001", owner_userid="sales_01", sender="wm_reply_disabled_001", receiver="sales_01", content="消息仍然入库", send_time="2026-04-09 10:10:00")

    with app.app_context():
        payload = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        archived_count = get_db().execute("SELECT COUNT(*) AS count FROM archived_messages").fetchone()["count"]
        queue_count = get_db().execute("SELECT COUNT(*) AS count FROM automation_reply_monitor_queue").fetchone()["count"]

    assert payload["status"] == "disabled"
    assert archived_count == 1
    assert queue_count == 0


def test_reply_monitor_reenable_starts_from_current_cursor_without_history_replay(app, monkeypatch):
    _seed_archived_message(app, msgid="msg-rm-reenable-001", seq=1, external_userid="wm_reply_reenable_001", owner_userid="sales_01", sender="wm_reply_reenable_001", receiver="sales_01", content="旧消息", send_time="2026-04-09 09:00:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:00:00")

    with app.app_context():
        enabled_payload = save_reply_monitor_enabled(enabled=True, operator_id="tester-reply-monitor")
        assert enabled_payload["enabled"] is True
        first_capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")

    assert first_capture["summary"]["scanned_new_messages"] == 0

    _seed_contact(app, external_userid="wm_reply_reenable_001", mobile="13800009141", owner_userid="sales_01", customer_name="reenable")
    _seed_automation_member(app, external_contact_id="wm_reply_reenable_001", phone="13800009141", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_follow_type="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-reenable-002", seq=2, external_userid="wm_reply_reenable_001", owner_userid="sales_01", sender="wm_reply_reenable_001", receiver="sales_01", content="新消息", send_time="2026-04-09 10:02:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:03:00")

    with app.app_context():
        second_capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")

    assert second_capture["summary"]["scanned_new_messages"] == 1
    assert second_capture["summary"]["created_queue_items"] == 1


def test_reply_monitor_capture_uses_storage_cursor_instead_of_send_time(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_cursor_001", mobile="13800009151", owner_userid="sales_01", customer_name="cursor")
    _seed_automation_member(app, external_contact_id="wm_reply_cursor_001", phone="13800009151", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_follow_type="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-cursor-001", seq=1, external_userid="wm_reply_cursor_001", owner_userid="sales_01", sender="wm_reply_cursor_001", receiver="sales_01", content="较新 send_time", send_time="2026-04-09 10:05:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:06:00")

    with app.app_context():
        first = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
    assert first["summary"]["created_queue_items"] == 1

    _seed_archived_message(app, msgid="msg-rm-cursor-002", seq=2, external_userid="wm_reply_cursor_001", owner_userid="sales_01", sender="wm_reply_cursor_001", receiver="sales_01", content="晚到但 send_time 更早", send_time="2026-04-09 10:01:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:07:00")

    with app.app_context():
        second = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        row = get_db().execute(
            """
            SELECT message_count, message_ids_json
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            """,
            ("wm_reply_cursor_001",),
        ).fetchone()

    assert second["summary"]["scanned_new_messages"] == 1
    assert second["summary"]["merged_queue_items"] == 1
    assert dict(row) == {
        "message_count": 2,
        "message_ids_json": json.dumps([1, 2]),
    }


def test_reply_monitor_dispatch_ingress_payload_contains_only_async_minimal_fields(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_payload_001", mobile="13800009161", owner_userid="sales_01", customer_name="payload")
    _seed_automation_member(app, external_contact_id="wm_reply_payload_001", phone="13800009161", owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_follow_type="focus", decision_source="manual")
    _seed_archived_message(app, msgid="msg-rm-payload-001", seq=1, external_userid="wm_reply_payload_001", owner_userid="sales_01", sender="wm_reply_payload_001", receiver="sales_01", content="我要继续了解", send_time="2026-04-09 10:20:00")
    _patch_reply_monitor_payload_context(monkeypatch, external_userid="wm_reply_payload_001")
    captured: dict[str, object] = {}

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    def _fake_router_post(url, data=None, headers=None, timeout=None):
        body = json.loads((data or b"{}").decode("utf-8"))
        captured.update({
            "url": url,
            "payload": body,
            "headers": dict(headers or {}),
        })
        return _AckResponse()

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", _fake_router_post)
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:21:00")

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")

    assert capture["ok"] is True
    assert dispatch["ok"] is True
    assert captured["url"] == "https://lobster.example.com/router"
    assert set(captured["payload"].keys()) == {"request_id", "external_contact_id", "recent_messages"}
    assert captured["payload"]["external_contact_id"] == "wm_reply_payload_001"
    assert captured["payload"]["recent_messages"] == [
        {
            "role": "customer",
            "content": "我要继续了解",
            "created_at": "2026-04-09 10:20:00",
        }
    ]


def test_reply_monitor_capture_api_fails_closed_when_token_is_not_configured(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_reply_monitor_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_reply_monitor_capture should not be called")),
    )

    response = client.post("/api/admin/automation-conversion/reply-monitor/capture", json={"limit": 10})

    assert response.status_code == 503
    assert response.get_json()["error"] == "internal token not configured"


def test_reply_monitor_run_due_api_fails_closed_when_token_is_not_configured(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_due_reply_monitor",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_due_reply_monitor should not be called")),
    )

    response = client.post("/api/admin/automation-conversion/reply-monitor/run-due", json={"limit": 10})

    assert response.status_code == 503
    assert response.get_json()["error"] == "internal token not configured"


def test_router_test_dispatch_api_requires_internal_token(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.run_router_test_dispatch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_router_test_dispatch should not be called")),
    )

    response = client.post("/api/internal/automation-conversion/router-test-dispatch", json={"external_contact_id": "wm_test_001"})

    assert response.status_code == 401
    assert response.get_json()["error"] == "missing internal token"


def test_router_test_dispatch_api_triggers_router_request_id_for_specific_member(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_router_test_001", mobile="13800009199", owner_userid="sales_01", customer_name="router-test")
    _seed_automation_member(app, external_contact_id="wm_router_test_001", phone="13800009199", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-router-test-001", seq=1, external_userid="wm_router_test_001", owner_userid="sales_01", sender="wm_router_test_001", receiver="sales_01", content="我想再了解一下方案", send_time="2026-04-09 15:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )

    response = client.post(
        "/api/internal/automation-conversion/router-test-dispatch",
        json={
            "external_contact_id": "wm_router_test_001",
            "operator": "lobster-smoke",
            "force_capture": True,
            "force_run_due": True,
        },
        headers={"Authorization": "Bearer internal-token"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["request_id"].startswith("router-shadow-")
    assert payload["member_id"] > 0
    assert payload["run_due_result"]["router_ingress"]["request_id"] == payload["request_id"]
    with app.app_context():
        run_row = get_db().execute(
            """
            SELECT status, request_id
            FROM automation_agent_run
            WHERE request_id = ?
            LIMIT 1
            """,
            (payload["request_id"],),
        ).fetchone()
        queue_row = get_db().execute(
            """
            SELECT status
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_router_test_001",),
        ).fetchone()

    assert dict(run_row)["status"] == "acked"
    assert dict(queue_row)["status"] == "dispatched"


def test_insert_archived_messages_does_not_trigger_legacy_openclaw_chain_by_default(app, monkeypatch):
    from wecom_ability_service.domains.archive.service import insert_archived_messages

    captured: list[list[dict[str, object]]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.marketing_automation.service.process_inbound_messages_for_openclaw",
        lambda rows: captured.append(list(rows)),
    )

    with app.app_context():
        inserted_count = insert_archived_messages(
            [
                {
                    "seq": 1,
                    "msgid": "legacy-openclaw-disabled-001",
                    "chat_type": "private",
                    "external_userid": "wm_legacy_disabled_001",
                    "owner_userid": "sales_01",
                    "sender": "wm_legacy_disabled_001",
                    "receiver": "sales_01",
                    "msgtype": "text",
                    "content": "这条消息不应再自动倒到旧龙虾链路",
                    "send_time": "2026-04-10 09:00:00",
                    "raw_payload": "{}",
                }
            ]
        )

    assert inserted_count == 1
    assert captured == []


def test_process_inbound_messages_for_openclaw_skips_automation_scope_users(app, monkeypatch):
    from wecom_ability_service.domains.marketing_automation.service import process_inbound_messages_for_openclaw

    _seed_contact(app, external_userid="wm_reply_scope_001", mobile="13800009171", owner_userid="sales_01", customer_name="scope-1")
    _seed_contact(app, external_userid="wm_reply_scope_002", mobile="13800009172", owner_userid="sales_01", customer_name="scope-2")
    _seed_automation_member(app, external_contact_id="wm_reply_scope_001", phone="13800009171", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_follow_type="focus", decision_source="questionnaire")

    triggered: list[str] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.marketing_automation.message_dispatch_service.trigger_openclaw_focus_message_webhook",
        lambda *, external_userid: triggered.append(external_userid) or {"sent": True, "external_userid": external_userid},
    )

    with app.app_context():
        result = process_inbound_messages_for_openclaw(
            [
                {
                    "external_userid": "wm_reply_scope_001",
                    "chat_type": "private",
                    "sender": "wm_reply_scope_001",
                    "send_time": "2026-04-09 10:30:00",
                },
                {
                    "external_userid": "wm_reply_scope_002",
                    "chat_type": "private",
                    "sender": "wm_reply_scope_002",
                    "send_time": "2026-04-09 10:31:00",
                },
            ]
        )

    assert triggered == ["wm_reply_scope_002"]
    assert result["processed_count"] == 1
    assert result["skipped_automation_scope_count"] == 1


def test_automation_conversion_stage_detail_keeps_only_total_and_today_new_metrics(app, client):
    _seed_contact(app, external_userid="wm_stage_new_user_001", mobile="13800009111", customer_name="阶段页客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_stage_new_user_001",
        phone="13800009111",
        current_pool="new_user",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )

    program_id = _default_program_id(app)
    response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/member-ops",
        query_string={"stage": "new-user", "panel": "members"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "方案成员运营" in html
    assert "automation_conversion_workspace.css" in html
    assert "池子概览" in html
    assert "批量触达" in html
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops?stage=pending-questionnaire&amp;panel=send" in html
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops?stage=operating&amp;panel=send" in html
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops?stage=converted&amp;panel=send" in html
    assert "成员列表" in html
    assert '<div class="admin-card-label">池内人数</div>' not in html
    assert '<div class="admin-card-label">今日新增</div>' not in html
    assert '<div class="admin-card-label">重点跟进</div>' not in html
    assert '<div class="admin-card-label">普通跟进</div>' not in html


def test_member_ops_page_links_members_to_unified_customer_detail(app, client):
    _seed_contact(app, external_userid="wm_member_ops_001", mobile="13800009131", owner_userid="sales_member", customer_name="成员运营客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_member_ops_001",
        phone="13800009131",
        owner_staff_id="sales_member",
        current_pool="operating",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="system",
    )

    program_id = _default_program_id(app)
    response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/member-ops",
        query_string={"stage": "operating", "panel": "members", "member": "wm_member_ops_001"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "成员列表" in html
    assert "成员运营客户" in html
    assert "13800009131" in html
    assert "当前阶段" in html
    assert "查看档案" in html
    assert "/admin/customers/wm_member_ops_001" in html
    assert "单客状态" not in html
    assert "问卷状态" not in html
    assert "<th>负责人</th>" not in html
    assert "<th>目标</th>" not in html
    assert "<th>最近更新</th>" not in html
    assert "转化为重点跟进" not in html
    assert "当前目标" not in html
    assert "最近人工动作" not in html
    assert "panel=members&amp;member=wm_member_ops_001" not in html
    assert "set_focus" not in html


def test_automation_conversion_stage_send_page_switches_between_manual_and_focus_modes(app, client):
    program_id = _default_program_id(app)
    normal_response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/member-ops",
        query_string={"stage": "new-user", "panel": "send"},
    )
    focus_response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/member-ops",
        query_string={"stage": "inactive-focus", "panel": "send"},
    )

    normal_html = normal_response.get_data(as_text=True)
    focus_html = focus_response.get_data(as_text=True)

    assert normal_response.status_code == 200
    assert "批量群发" in normal_html
    assert "群发内容" in normal_html
    assert 'id="stage-send-image-input"' in normal_html
    assert 'name="images" multiple' in normal_html
    assert 'enctype="multipart/form-data"' in normal_html
    assert 'name="admin_action_token"' in normal_html
    assert "data-member-send-form" in normal_html
    assert "创建群发任务" in normal_html
    assert "已提交，正在创建任务，请勿重复点击。" in normal_html
    assert "/manual-send/preview" not in normal_html
    assert "/api/admin/automation-conversion/stage/new-user/manual-send" not in normal_html
    assert "/api/admin/automation-conversion/stage/new-user/focus-send-batches" not in normal_html
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops/stage/new-user/send" in normal_html
    assert f'action="/admin/automation-conversion/programs/{program_id}/member-ops/stage/new-user/send"' in normal_html
    assert 'action="/api/admin/automation-conversion/stage/new-user/manual-send' not in normal_html
    assert "/admin/automation-conversion/stage/new-user/send" not in normal_html

    assert focus_response.status_code == 200
    assert "AI 批量处理" in focus_html
    assert "data-member-send-form" in focus_html
    assert "创建 AI 批任务" in focus_html
    assert "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches" not in focus_html
    assert "/api/admin/automation-conversion/stage/inactive-focus/manual-send" not in focus_html
    assert "/api/admin/automation-conversion/focus-send-batches/" not in focus_html


def test_member_ops_send_panel_contains_batch_placeholder_actions_for_both_modes(app, client):
    program_id = _default_program_id(app)
    normal_response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/member-ops",
        query_string={"stage": "new-user", "panel": "send"},
    )
    focus_response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/member-ops",
        query_string={"stage": "inactive-focus", "panel": "send"},
    )

    normal_html = normal_response.get_data(as_text=True)
    focus_html = focus_response.get_data(as_text=True)

    assert normal_response.status_code == 200
    assert "动作只作用于当前池子" in normal_html
    assert "批量群发" in normal_html
    assert "AI 批量处理" not in normal_html

    assert focus_response.status_code == 200
    assert "动作只作用于当前池子" in focus_html
    assert "AI 批量处理" in focus_html


def test_automation_conversion_stage_send_api_surfaces_validation_and_placeholder_states(app, client):
    manual = client.post("/api/admin/automation-conversion/stage/new-user/manual-send", json={"operator": "tester"})
    focus = client.post("/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches")
    detail = client.get("/api/admin/automation-conversion/focus-send-batches/batch-001")

    assert manual.status_code == 400
    assert manual.get_json()["error"] == "content, images, or attachments is required"
    assert focus.status_code == 201
    assert focus.get_json()["ok"] is True
    assert focus.get_json()["batch"]["stage_key"] == "inactive-focus"
    assert detail.status_code == 400
    assert detail.get_json()["error"] == "invalid batch_id"


def test_focus_send_batch_can_be_created_for_inactive_focus_stage(app, client):
    _seed_contact(app, external_userid="wm_focus_batch_001", mobile="13800009301", owner_userid="sales_focus", customer_name="重点客户一")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_batch_001",
        phone="13800009301",
        owner_staff_id="sales_focus",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches",
        json={"operator": "tester"},
    )
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["status"] == "created"
    assert payload["batch"]["stage_key"] == "inactive-focus"
    assert payload["batch"]["total_count"] == 1
    assert payload["batch"]["remaining_count"] == 1
    assert payload["items"][0]["status"] == "pending"

    detail = client.get(f"/api/admin/automation-conversion/focus-send-batches/{payload['batch']['id']}")
    detail_payload = detail.get_json()
    assert detail.status_code == 200
    assert detail_payload["ok"] is True
    assert detail_payload["batch"]["stage_key"] == "inactive-focus"


def test_focus_send_batch_can_be_created_for_active_focus_stage(app, client):
    _seed_contact(app, external_userid="wm_focus_batch_002", mobile="13800009302", owner_userid="sales_focus", customer_name="重点客户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_batch_002",
        phone="13800009302",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    )
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["batch"]["stage_key"] == "active-focus"
    assert payload["batch"]["total_count"] == 1
    assert payload["items"][0]["status"] == "pending"


def test_focus_send_batch_runner_only_advances_due_items_and_updates_next_run_at(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "focus-token"
    _seed_contact(app, external_userid="wm_focus_run_001", mobile="13800009311", owner_userid="sales_focus", customer_name="重点客户一")
    _seed_contact(app, external_userid="wm_focus_run_002", mobile="13800009312", owner_userid="sales_focus", customer_name="重点客户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_run_001",
        phone="13800009311",
        owner_staff_id="sales_focus",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_run_002",
        phone="13800009312",
        owner_staff_id="sales_focus",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    times = iter(
        [
            "2026-04-07 10:00:00",
            "2026-04-07 10:00:00",
            "2026-04-07 10:00:10",
            "2026-04-07 10:00:20",
        ]
    )
    push_calls: list[str] = []
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: next(times))
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.push_openclaw",
        lambda **payload: (
            push_calls.append(str(payload.get("external_contact_id") or "")),
            {"accepted": True, "status": "accepted", "member": {"external_contact_id": payload.get("external_contact_id")}},
        )[1],
    )

    created = client.post(
        "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    batch_id = created["batch"]["id"]

    first = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    second = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    third = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()

    assert first["processed_count"] == 1
    assert first["batches"][0]["batch"]["sent_count"] == 1
    assert first["batches"][0]["batch"]["remaining_count"] == 1
    assert first["batches"][0]["batch"]["next_run_at"] == "2026-04-07 10:00:20"
    assert second["processed_count"] == 0
    assert third["processed_count"] == 1
    assert third["batches"][0]["batch"]["sent_count"] == 2
    assert third["batches"][0]["batch"]["remaining_count"] == 0
    assert third["batches"][0]["batch"]["status"] == "finished"
    assert sorted(push_calls) == ["wm_focus_run_001", "wm_focus_run_002"]

    detail = client.get(f"/api/admin/automation-conversion/focus-send-batches/{batch_id}").get_json()
    assert detail["batch"]["sent_count"] == 2
    assert [item["status"] for item in detail["items"]] == ["sent", "sent"]


def test_focus_send_batch_runner_item_failure_does_not_block_batch(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "focus-token"
    _seed_contact(app, external_userid="wm_focus_fail_001", mobile="13800009321", owner_userid="sales_focus", customer_name="重点客户一")
    _seed_contact(app, external_userid="wm_focus_fail_002", mobile="13800009322", owner_userid="sales_focus", customer_name="重点客户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_fail_001",
        phone="13800009321",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_fail_002",
        phone="13800009322",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    times = iter(
        [
            "2026-04-07 11:00:00",
            "2026-04-07 11:00:00",
            "2026-04-07 11:00:20",
        ]
    )
    call_index = {"value": 0}

    def fake_push_openclaw(**payload):
        call_index["value"] += 1
        if call_index["value"] == 1:
            return {"accepted": False, "status": "failed", "error": "openclaw webhook failed"}
        return {"accepted": True, "status": "accepted", "member": {"external_contact_id": payload.get("external_contact_id")}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: next(times))
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.push_openclaw", fake_push_openclaw)

    created = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    batch_id = created["batch"]["id"]

    first = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    second = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()

    assert first["batches"][0]["batch"]["failed_count"] == 1
    assert first["batches"][0]["batch"]["remaining_count"] == 1
    assert second["batches"][0]["batch"]["sent_count"] == 1
    assert second["batches"][0]["batch"]["failed_count"] == 1
    assert second["batches"][0]["batch"]["remaining_count"] == 0
    assert second["batches"][0]["batch"]["status"] == "finished"

    detail = client.get(f"/api/admin/automation-conversion/focus-send-batches/{batch_id}").get_json()
    assert [item["status"] for item in detail["items"]] == ["failed", "sent"]


def test_focus_send_batch_does_not_requeue_already_sent_member(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "focus-token"
    _seed_contact(app, external_userid="wm_focus_once_001", mobile="13800009341", owner_userid="sales_focus", customer_name="重点客户一次")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_once_001",
        phone="13800009341",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    times = iter(["2026-04-07 12:00:00", "2026-04-07 12:00:00", "2026-04-07 12:01:00", "2026-04-07 12:01:00"])
    push_calls: list[str] = []
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: next(times))
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.push_openclaw",
        lambda **payload: (
            push_calls.append(str(payload.get("external_contact_id") or "")),
            {"accepted": True, "status": "accepted", "member": {"external_contact_id": payload.get("external_contact_id")}},
        )[1],
    )

    first_created = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    first_run = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    second_created = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    second_run = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()

    assert first_created["batch"]["total_count"] == 1
    assert first_run["batches"][0]["batch"]["status"] == "finished"
    assert second_created["batch"]["status"] == "finished"
    assert second_created["batch"]["total_count"] == 1
    assert second_created["batch"]["skipped_count"] == 1
    assert second_created["batch"]["remaining_count"] == 0
    assert second_created["items"] == []
    assert second_created["skipped_reasons"] == {"already_touched": 1}
    assert second_run["processed_count"] == 0
    assert push_calls == ["wm_focus_once_001"]

    with app.app_context():
        rows = get_db().execute(
            """
            SELECT touch_surface, rule_key, external_contact_id, status
            FROM automation_touch_delivery_log
            WHERE external_contact_id = ?
            ORDER BY id ASC
            """,
            ("wm_focus_once_001",),
        ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "touch_surface": "focus_send",
            "rule_key": "operating",
            "external_contact_id": "wm_focus_once_001",
            "status": "sent",
        }
    ]


def test_focus_send_batch_respects_historical_sent_items_before_touch_log(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_focus_history_001", mobile="13800009342", owner_userid="sales_focus", customer_name="历史重点客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_history_001",
        phone="13800009342",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_focus_send_batch (
                stage_key, pool_key, operator_type, operator_id, status, total_count, sent_count,
                failed_count, skipped_count, cancelled_count, next_run_at, last_run_at, created_at, updated_at, finished_at
            )
            VALUES ('active-focus', 'operating', 'system', 'legacy', 'finished', 1, 1, 0, 0, 0, '', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        batch_id = int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        db.execute(
            """
            INSERT INTO automation_focus_send_batch_item (
                batch_id, member_id, external_contact_id, phone, position_index, status, detail,
                result_payload, created_at, updated_at, started_at, finished_at
            )
            VALUES (?, NULL, 'wm_focus_history_001', '13800009342', 1, 'sent', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (batch_id,),
        )
        db.commit()
    push_calls: list[str] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.push_openclaw",
        lambda **payload: push_calls.append(str(payload.get("external_contact_id") or "")) or {"accepted": True, "status": "accepted"},
    )

    created = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()

    assert created["batch"]["status"] == "finished"
    assert created["batch"]["skipped_count"] == 1
    assert created["items"] == []
    assert created["skipped_reasons"] == {"already_touched": 1}
    assert push_calls == []


def test_focus_send_batch_reuses_active_batch_across_legacy_route_aliases(app, client):
    _seed_contact(app, external_userid="wm_focus_alias_001", mobile="13800009343", owner_userid="sales_focus", customer_name="重点别名客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_alias_001",
        phone="13800009343",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )

    first_created = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    second_created = client.post(
        "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()

    assert first_created["status"] == "created"
    assert second_created["status"] == "existing"
    assert second_created["batch"]["id"] == first_created["batch"]["id"]



def test_manual_send_new_user_stage_uses_single_sender_without_owner_buckets(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_new_001", mobile="13800009201", owner_userid="sales_01", customer_name="新用户一")
    _seed_contact(app, external_userid="wm_manual_new_002", mobile="13800009202", owner_userid="sales_02", customer_name="新用户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_new_001",
        phone="13800009201",
        owner_staff_id="sales_01",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_new_002",
        phone="13800009202",
        owner_staff_id="sales_02",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": dict(payload)})
        return {"task_id": 701, "wecom_result": {"msgid": "msg-701"}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "欢迎先看问卷", "image_media_ids": ["img-media-001", "img-media-002"], "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stage_key"] == "new-user"
    assert payload["total_target_count"] == 2
    assert payload["sent_count"] == 2
    assert payload["skipped_count"] == 0
    assert payload["task_ids"] == [701]
    assert len(dispatched_payloads) == 1
    assert dispatched_payloads[0]["task_type"] == "private_message"
    assert dispatched_payloads[0]["fn_name"] == "create_private_message_task"
    assert dispatched_payloads[0]["payload"]["sender"] == "HuangYouCan"
    assert sorted(dispatched_payloads[0]["payload"]["external_userid"]) == ["wm_manual_new_001", "wm_manual_new_002"]
    assert dispatched_payloads[0]["payload"]["image_media_ids"] == ["img-media-001", "img-media-002"]
    assert "attachments" not in dispatched_payloads[0]["payload"]

    with app.app_context():
        row = get_db().execute(
            """
            SELECT filter_snapshot_json, sender_userids_json, selected_count, eligible_count, sent_count
            FROM user_ops_send_records
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        filter_snapshot = json.loads(row["filter_snapshot_json"])
        assert filter_snapshot["selection_mode"] == "automation_conversion_stage"
        assert filter_snapshot["stage_key"] == "new-user"
        assert filter_snapshot["pool_key"] == "pending_questionnaire"
        assert "owner_userid" not in filter_snapshot
        assert json.loads(row["sender_userids_json"]) == ["HuangYouCan"]
        assert row["selected_count"] == 2
        assert row["eligible_count"] == 2
        assert row["sent_count"] == 2


def test_manual_send_skips_already_touched_member_on_repeat(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_once_001", mobile="13800009203", owner_userid="sales_01", customer_name="新用户一次")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_once_001",
        phone="13800009203",
        owner_staff_id="sales_01",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append(dict(payload))
        return {"task_id": 706, "wecom_result": {"msgid": "msg-706"}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task", fake_dispatch)

    first_response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "第一次触达", "operator": "tester"},
    )
    second_response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "第二次触达", "operator": "tester"},
    )

    first_payload = first_response.get_json()
    second_payload = second_response.get_json()
    assert first_response.status_code == 200
    assert first_payload["sent_count"] == 1
    assert first_payload["skipped_count"] == 0
    assert second_response.status_code == 200
    assert second_payload["sent_count"] == 0
    assert second_payload["eligible_count"] == 0
    assert second_payload["skipped_count"] == 1
    assert second_payload["skipped_reasons"] == {"already_touched": 1}
    assert len(dispatched_payloads) == 1
    assert dispatched_payloads[0]["external_userid"] == ["wm_manual_once_001"]

    with app.app_context():
        row = get_db().execute(
            """
            SELECT touch_surface, rule_key, external_contact_id, status, send_record_id
            FROM automation_touch_delivery_log
            WHERE external_contact_id = ?
            LIMIT 1
            """,
            ("wm_manual_once_001",),
        ).fetchone()
    assert dict(row)["touch_surface"] == "stage_manual_send"
    assert dict(row)["rule_key"] == "pending-questionnaire"
    assert dict(row)["status"] == "sent"
    assert int(dict(row)["send_record_id"]) == int(first_payload["record_id"])


def test_manual_send_respects_historical_send_records_before_touch_log(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_history_001", mobile="13800009206", owner_userid="sales_01", customer_name="历史新用户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_history_001",
        phone="13800009206",
        owner_staff_id="sales_01",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    with app.app_context():
        get_db().execute(
            """
            INSERT INTO user_ops_send_records (
                task_type, outbound_task_ids_json, task_results_json, selected_count, eligible_count,
                sent_count, skipped_count, skipped_reasons_json, include_do_not_disturb, content_preview,
                image_count, sender_userids_json, filter_snapshot_json, operator, status, created_at
            )
            VALUES ('private_message', '[708]', ?, 1, 1, 1, 0, '{}', 0, '历史触达', 0, '["HuangYouCan"]', ?, 'legacy', 'sent', CURRENT_TIMESTAMP)
            """,
            (
                json.dumps(
                    [
                        {
                            "status": "created",
                            "external_userids": ["wm_manual_history_001"],
                            "target_count": 1,
                        }
                    ],
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "selection_mode": "automation_conversion_stage",
                        "stage_key": "new-user",
                        "pool_key": "pending_questionnaire",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        get_db().commit()
    dispatched_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched_payloads.append(dict(payload)) or {"task_id": 709, "wecom_result": {"msgid": "msg-709"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "再次触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["sent_count"] == 0
    assert payload["eligible_count"] == 0
    assert payload["skipped_reasons"] == {"already_touched": 1}
    assert dispatched_payloads == []


def test_manual_send_operating_stage_uses_current_audience_not_pool_status(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_pool_001", mobile="13800009204", owner_userid="sales_01", customer_name="运营中")
    _seed_contact(app, external_userid="wm_manual_pool_002", mobile="13800009205", owner_userid="sales_01", customer_name="待问卷")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_pool_001",
        phone="13800009204",
        owner_staff_id="sales_01",
        in_pool=1,
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                questionnaire_status, decision_source, source_type, last_active_pool,
                current_audience_code, current_audience_entered_at, joined_at, created_at, updated_at
            )
            VALUES ('wm_manual_pool_002', '13800009205', 'sales_01', 1, 'active_normal', 'normal',
                    'pending', 'legacy', 'manual', '', 'pending_questionnaire',
                    '2026-04-06 10:00:00', '2026-04-06 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()
    dispatched_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched_payloads.append(dict(payload)) or {"task_id": 707, "wecom_result": {"msgid": "msg-707"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/active-normal/manual-send",
        json={"content": "运营池触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["total_target_count"] == 1
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 0
    assert dispatched_payloads[0]["external_userid"] == ["wm_manual_pool_001"]


def test_manual_send_operating_stage_includes_legacy_pool_aliases(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_alias_001", mobile="13800009207", owner_userid="sales_01", customer_name="旧池普通")
    _seed_contact(app, external_userid="wm_manual_alias_002", mobile="13800009208", owner_userid="sales_01", customer_name="旧池重点")
    with app.app_context():
        db = get_db()
        for external_contact_id, phone, current_pool, follow_type in [
            ("wm_manual_alias_001", "13800009207", "active_normal", "normal"),
            ("wm_manual_alias_002", "13800009208", "active_focus", "focus"),
        ]:
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                    questionnaire_status, decision_source, source_type, last_active_pool,
                    current_audience_code, current_audience_entered_at, joined_at, created_at, updated_at
                )
                VALUES (?, ?, 'sales_01', 1, ?, ?, 'submitted', 'legacy', 'manual', '', 'operating',
                        '2026-04-06 10:00:00', '2026-04-06 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (external_contact_id, phone, current_pool, follow_type),
            )
        db.commit()
    dispatched_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched_payloads.append(dict(payload)) or {"task_id": 710, "wecom_result": {"msgid": "msg-710"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/active-normal/manual-send",
        json={"content": "旧池兼容触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["total_target_count"] == 2
    assert payload["sent_count"] == 2
    assert sorted(dispatched_payloads[0]["external_userid"]) == ["wm_manual_alias_001", "wm_manual_alias_002"]


def test_manual_send_operating_stage_treats_legacy_terminal_pool_as_audience_metadata(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_terminal_001", mobile="13800009209", owner_userid="sales_01", customer_name="旧人工状态")
    _seed_contact(app, external_userid="wm_manual_terminal_002", mobile="13800009210", owner_userid="sales_01", customer_name="旧不回复状态")
    with app.app_context():
        db = get_db()
        for external_contact_id, phone, current_pool in [
            ("wm_manual_terminal_001", "13800009209", "human_reply"),
            ("wm_manual_terminal_002", "13800009210", "no_reply"),
        ]:
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                    questionnaire_status, decision_source, source_type, last_active_pool,
                    current_audience_code, current_audience_entered_at, joined_at, created_at, updated_at
                )
                VALUES (?, ?, 'sales_01', 1, ?, '', 'submitted', 'legacy', 'manual', '', 'operating',
                        '2026-04-06 10:00:00', '2026-04-06 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (external_contact_id, phone, current_pool),
            )
        db.commit()
    with app.app_context():
        stage_detail = get_stage_detail_payload(route_key="operating", limit=10, offset=0)
    assert stage_detail["pagination"]["total"] == 2
    assert sorted(item["external_userid"] for item in stage_detail["customers"]) == [
        "wm_manual_terminal_001",
        "wm_manual_terminal_002",
    ]
    dispatched_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched_payloads.append(dict(payload)) or {"task_id": 711, "wecom_result": {"msgid": "msg-711"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/operating/manual-send",
        json={"content": "按当前人群触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["total_target_count"] == 2
    assert payload["sent_count"] == 2
    assert sorted(dispatched_payloads[0]["external_userid"]) == ["wm_manual_terminal_001", "wm_manual_terminal_002"]


def test_manual_send_preview_supports_local_images_and_uses_qianlan_sender(app, client):
    _seed_contact(app, external_userid="wm_manual_preview_001", mobile="13800009291", owner_userid="WangWei", customer_name="预览客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_preview_001",
        phone="13800009291",
        owner_staff_id="WangWei",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send/preview",
        data=_build_stage_send_form_data(
            content="图片预览🙂",
            images=[("hello.png", _test_png_bytes(), "image/png")],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["content_preview"] == "图片预览🙂"
    assert payload["image_count"] == 1
    assert payload["eligible_count"] == 1
    assert payload["final_targets"][0]["owner_userid"] == "HuangYouCan"
    assert payload["final_targets"][0]["owner_display_name"] == "HuangYouCan"


def test_manual_send_preview_rejects_fourth_local_image(app, client):
    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send/preview",
        data=_build_stage_send_form_data(
            images=[(f"img-{index}.png", _test_png_bytes(), "image/png") for index in range(1, 5)],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["error"] == "at most 3 images are allowed"


def test_manual_send_silent_stage_can_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_silent_001", mobile="13800009211", owner_userid="sales_silent", customer_name="沉默客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_silent_001",
        phone="13800009211",
        owner_staff_id="sales_silent",
        current_pool="silent",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 702, "wecom_result": {"msgid": "msg-702"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/silent/manual-send",
        json={"content": "沉默池唤醒触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stage_key"] == "silent"
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["task_ids"] == [702]


def test_manual_send_won_stage_can_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_won_001", mobile="13800009221", owner_userid="sales_won", customer_name="已成交客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_won_001",
        phone="13800009221",
        owner_staff_id="sales_won",
        in_pool=0,
        current_pool="won",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        last_active_pool="active_normal",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 703, "wecom_result": {"msgid": "msg-703"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/won/manual-send",
        json={"content": "已成交后续维护", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stage_key"] == "won"
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["task_ids"] == [703]


def test_manual_send_skips_members_missing_external_userid(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_skip_001", mobile="13800009231", owner_userid="sales_skip", customer_name="可发送客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_skip_001",
        phone="13800009231",
        owner_staff_id="sales_skip",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )
    _seed_automation_member(
        app,
        external_contact_id="",
        phone="13800009232",
        owner_staff_id="sales_skip",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
    )
    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append(dict(payload))
        return {"task_id": 704, "wecom_result": {"msgid": "msg-704"}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/automation-conversion/stage/active-normal/manual-send",
        json={"content": "激活普通池统一触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["total_target_count"] == 2
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 1
    assert payload["skipped_reasons"] == {"missing_external_userid": 1}
    assert dispatched_payloads[0]["external_userid"] == ["wm_manual_skip_001"]


def test_admin_stage_send_program_route_requires_action_token(app, client):
    program_id = _default_program_id(app)

    response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/member-ops/stage/new-user/send",
        data={"content": "缺少 token", "stage": "new-user", "panel": "send"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "后台动作令牌无效，请刷新页面后重试" in html
    assert "方案成员运营" in html
    assert "批量群发" in html


def test_admin_stage_send_page_shows_manual_send_summary(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_page_001", mobile="13800009241", owner_userid="sales_page", customer_name="页面客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_page_001",
        phone="13800009241",
        owner_staff_id="sales_page",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: captured_payloads.append(dict(payload)) or {"task_id": 705, "wecom_result": {"msgid": "msg-705"}},
    )
    captured_payloads: list[dict[str, object]] = []
    program_id = _default_program_id(app)
    action_token = _admin_action_token(
        client,
        f"/admin/automation-conversion/programs/{program_id}/member-ops?stage=new-user&panel=send",
    )
    form_data = _build_stage_send_form_data(
        content="页面触达",
        operator="tester",
        images=[("page.png", _test_png_bytes(), "image/png")],
    )
    form_data["admin_action_token"] = action_token

    redirect_response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/member-ops/stage/new-user/send",
        data=form_data,
        content_type="multipart/form-data",
    )
    assert redirect_response.status_code == 302
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops" in redirect_response.headers["Location"]
    assert "stage=new-user" in redirect_response.headers["Location"]
    assert "panel=send" in redirect_response.headers["Location"]
    assert "manual_send_notice=sent" in redirect_response.headers["Location"]

    response = client.get(redirect_response.headers["Location"], follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "群发任务已创建" in html
    assert "发送记录 ID" in html
    assert 'id="stage-send-image-input"' in html
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["sender"] == "HuangYouCan"
    assert "images" in captured_payloads[0]
    assert "image_media_ids" not in captured_payloads[0]


def test_admin_stage_send_program_route_returns_json_for_ajax_submit(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_ajax_001", mobile="13800009242", owner_userid="sales_page", customer_name="异步页面客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_ajax_001",
        phone="13800009242",
        owner_staff_id="sales_page",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )
    captured_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: captured_payloads.append(dict(payload)) or {"task_id": 706, "wecom_result": {"msgid": "msg-706"}},
    )
    program_id = _default_program_id(app)
    action_token = _admin_action_token(
        client,
        f"/admin/automation-conversion/programs/{program_id}/member-ops?stage=new-user&panel=send",
    )
    form_data = _build_stage_send_form_data(content="异步页面触达", operator="tester")
    form_data["admin_action_token"] = action_token

    response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/member-ops/stage/new-user/send",
        data=form_data,
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops" in payload["redirect_url"]
    assert "stage=new-user" in payload["redirect_url"]
    assert "panel=send" in payload["redirect_url"]
    assert "manual_send_notice=sent" in payload["redirect_url"]
    assert "record_id=" in payload["redirect_url"]
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["external_userid"] == ["wm_manual_ajax_001"]


def test_admin_stage_send_page_shows_focus_batch_summary(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_focus_page_001", mobile="13800009331", owner_userid="sales_page", customer_name="重点页面客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_page_001",
        phone="13800009331",
        owner_staff_id="sales_page",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
    )
    program_id = _default_program_id(app)
    action_token = _admin_action_token(
        client,
        f"/admin/automation-conversion/programs/{program_id}/member-ops?stage=inactive-focus&panel=send",
    )

    redirect_response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/member-ops/stage/inactive-focus/send",
        data={"operator": "tester", "admin_action_token": action_token, "stage": "inactive-focus", "panel": "send"},
    )
    assert redirect_response.status_code == 302
    assert f"/admin/automation-conversion/programs/{program_id}/member-ops" in redirect_response.headers["Location"]
    assert "stage=inactive-focus" in redirect_response.headers["Location"]
    assert "panel=send" in redirect_response.headers["Location"]
    assert "focus_batch_notice=created" in redirect_response.headers["Location"]
    assert "focus_batch_id=" in redirect_response.headers["Location"]

    response = client.get(redirect_response.headers["Location"], follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 批任务已创建" in html
    assert "任务总数" in html
    assert "剩余数量" in html


def test_message_activity_sync_returns_not_configured_without_creating_run(app):
    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        run_count = get_db().execute("SELECT COUNT(*) AS count FROM automation_message_activity_sync_run").fetchone()["count"]

    assert payload["ok"] is False
    assert payload["status"] == "not_configured"
    assert payload["error"] == "message activity db is not configured"
    assert payload["missing_keys"] == [
        "MESSAGE_ACTIVITY_DB_HOST",
        "MESSAGE_ACTIVITY_DB_NAME",
        "MESSAGE_ACTIVITY_DB_USER",
        "MESSAGE_ACTIVITY_DB_PASS",
    ]
    assert payload["run"] == {}
    assert run_count == 0


def test_message_activity_sync_api_returns_400_when_db_not_configured(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "sync-token"

    response = client.post(
        "/api/admin/automation-conversion/message-activity-sync/run",
        json={"trigger_source": "scheduled", "operator": "tester-sync-api"},
        headers={"Authorization": "Bearer sync-token"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["status"] == "not_configured"
    assert body["missing_keys"] == [
        "MESSAGE_ACTIVITY_DB_HOST",
        "MESSAGE_ACTIVITY_DB_NAME",
        "MESSAGE_ACTIVITY_DB_USER",
        "MESSAGE_ACTIVITY_DB_PASS",
    ]


def test_automation_conversion_run_center_sync_tab_shows_real_message_activity_env_names(app, client):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_message_activity_sync_run (
                trigger_source, operator_type, operator_id, status, candidate_count, matched_count, updated_count,
                skipped_ambiguous_count, skipped_unmatched_count, skipped_missing_phone_count, focus_count, normal_count,
                error_message, summary_json, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, ?, '{}', ?, ?)
            """,
            (
                "manual",
                "user",
                "tester",
                "failed",
                "message activity db is not configured",
                "2026-04-07 19:16:56",
                "2026-04-07 19:16:56",
            ),
        )
        db.commit()

    response = client.get("/admin/automation-conversion/runtime/sync")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MESSAGE_ACTIVITY_DB_NAME" in html
    assert "MESSAGE_ACTIVITY_DB_PASS" in html
    assert "MESSAGE_ACTIVITY_DB_DATABASE" not in html
    assert "MESSAGE_ACTIVITY_DB_PASSWORD" not in html
    assert "数据同步" in html
    assert "立即刷新一次" in html
    assert "未配置" in html
    assert "最近一次同步失败" not in html
    assert ">failed<" not in html


def test_automation_conversion_run_center_logs_tab_uses_canonical_query(app, client):
    response = client.get("/admin/automation-conversion/runtime/logs")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "执行日志 / 审计" in html
    assert "最近同步任务摘要" in html
    assert "最近失败任务提示" in html
    assert "/admin/automation-conversion/runtime/logs" in html


def test_automation_conversion_run_center_overview_tab_avoids_heavy_operation_forms(app, client):
    response = client.get("/admin/automation-conversion/runtime")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "运行概况" in html
    assert "数据同步" in html
    assert "智能体编排" in html
    assert "调试" in html
    assert "立即刷新一次" not in html
    assert "保存 DeepSeek 配置" not in html


def test_admin_agent_config_draft_validation_keeps_raw_json_on_error(app, client):
    action_token = _admin_action_token(
        client,
        "/admin/automation-conversion/runtime/router?subtab=agents&agent=welcome_agent",
    )

    response = client.post(
        "/admin/automation-conversion/agent-orchestration/agents/welcome_agent/save-draft",
        data={
            "admin_action_token": action_token,
            "display_name": "欢迎接待 Agent",
            "enabled": "1",
            "role_prompt": "你是欢迎接待 Agent。",
            "task_prompt": "请生成欢迎回复。",
            "variables_json": '[{"variable_key":"recent_messages"}',
            "output_schema_json": '[{"field":"draft_reply"}]',
            "change_summary": "测试保留非法 JSON 输入",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "variables_json must be valid JSON array" in html
    assert 'name="variables_json"' in html
    assert "recent_messages" in html
    assert "输出协议（JSON）" in html


def test_agent_output_ledger_api_supports_filter_detail_export_and_replay(app, client):
    _seed_contact(app, external_userid="wm_agent_ledger_001", mobile="13800009701", owner_userid="sales_agent", customer_name="账本客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_agent_ledger_001",
        phone="13800009701",
        owner_staff_id="sales_agent",
        current_pool="new_user",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
    )

    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-test-ledger-001",
                "request_id": "req-ledger-001",
                "batch_id": "batch-ledger-001",
                "userid": "sales_agent",
                "external_contact_id": "wm_agent_ledger_001",
                "agent_code": "welcome_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "input_snapshot": {"messages": ["你好"], "member_snapshot": {"current_pool": "pending_questionnaire"}},
                "variables_snapshot": {"current_pool": "pending_questionnaire", "recent_messages": ["你好"]},
                "final_prompt_preview": "角色+任务+变量",
                "role_prompt_version": "v2",
                "task_prompt_version": "v5",
                "status": "success",
                "source": "test",
            }
        )
        output = append_agent_output(
            {
                "output_id": "aout-test-ledger-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wm_agent_ledger_001",
                "agent_code": "welcome_agent",
                "output_type": "agent_reply_draft",
                "raw_output_text": "欢迎联系我",
                "normalized_output": {
                    "agent_code": "welcome_agent",
                    "userid": "sales_agent",
                    "target_pool": "pending_questionnaire",
                    "confidence": 0.93,
                    "reason": "新用户需要欢迎回复",
                    "draft_reply": "欢迎联系我",
                    "need_human_review": False,
                },
                "rendered_output_text": "欢迎联系我",
                "target_agent_code": "welcome_agent",
                "target_pool": "pending_questionnaire",
                "confidence": 0.93,
                "reason": "新用户需要欢迎回复",
                "applied_status": "applied",
                "applied_at": "2026-04-10 12:00:00",
            }
        )
        append_agent_output(
            {
                "output_id": "aout-test-ledger-002",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wm_agent_ledger_001",
                "agent_code": "welcome_agent",
                "output_type": "error_output",
                "raw_output_text": "timeout",
                "normalized_output": {"status": "timeout"},
                "rendered_output_text": "timeout",
                "target_pool": "pending_questionnaire",
                "confidence": 0.1,
                "reason": "请求超时",
                "applied_status": "pending",
                "error_code": "timeout",
                "error_message": "请求超时",
            }
        )

    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "agent-token"
    list_response = client.get(
        "/api/admin/automation-conversion/agent-outputs",
        query_string={
            "request_id": "req-ledger-001",
            "current_pool": "pending_questionnaire",
            "min_confidence": "0.9",
            "has_error": "0",
        },
        headers={"Authorization": "Bearer agent-token"},
    )
    list_payload = list_response.get_json()
    assert list_response.status_code == 200
    assert list_payload["ok"] is True
    assert list_payload["total"] == 1
    assert list_payload["rows"][0]["output_id"] == output["output_id"]
    assert list_payload["rows"][0]["raw_output_text"] == "欢迎联系我"

    detail_response = client.get(
        f"/api/admin/automation-conversion/agent-outputs/{output['output_id']}",
        headers={"Authorization": "Bearer agent-token"},
    )
    detail_payload = detail_response.get_json()
    assert detail_response.status_code == 200
    assert detail_payload["ok"] is True
    assert detail_payload["output"]["output_type"] == "agent_reply_draft"
    assert detail_payload["run"]["request_id"] == "req-ledger-001"
    assert detail_payload["output"]["raw_output_text"] == "欢迎联系我"
    assert detail_payload["run"]["input_snapshot"]["messages"] == ["你好"]

    run_response = client.get(
        f"/api/admin/automation-conversion/agent-runs/{run['run_id']}",
        headers={"Authorization": "Bearer agent-token"},
    )
    run_payload = run_response.get_json()
    assert run_response.status_code == 200
    assert run_payload["ok"] is True
    assert run_payload["run"]["run_id"] == run["run_id"]
    assert len(run_payload["run"]["outputs"]) == 2

    export_response = client.post(
        "/api/admin/automation-conversion/agent-outputs/export",
        json={"filters": {"request_id": "req-ledger-001"}, "requested_by": "tester"},
        headers={"Authorization": "Bearer agent-token"},
    )
    export_payload = export_response.get_json()
    assert export_response.status_code == 202
    assert export_payload["ok"] is True
    assert export_payload["job"]["status"] == "completed"

    export_job_id = export_payload["job"]["job_id"]
    export_job_response = client.get(
        f"/api/admin/automation-conversion/agent-outputs/export/{export_job_id}",
        headers={"Authorization": "Bearer agent-token"},
    )
    assert export_job_response.status_code == 200
    assert export_job_response.get_json()["job"]["has_file"] is True

    export_file_response = client.get(
        f"/api/admin/automation-conversion/agent-outputs/export/{export_job_id}",
        query_string={"download": 1},
        headers={"Authorization": "Bearer agent-token"},
    )
    assert export_file_response.status_code == 200
    assert export_file_response.mimetype == "application/vnd.ms-excel"
    assert b"req-ledger-001" in export_file_response.data

    replay_response = client.get(
        "/api/admin/automation-conversion/agent-replay",
        query_string={"request_id": "req-ledger-001"},
        headers={"Authorization": "Bearer agent-token"},
    )
    replay_payload = replay_response.get_json()
    assert replay_response.status_code == 200
    assert replay_payload["ok"] is True
    assert replay_payload["selected_run"]["run_id"] == "arun-test-ledger-001"
    assert replay_payload["final_output"]["output_id"] == "aout-test-ledger-001"

    action_token = _admin_action_token(
        client,
        "/admin/automation-conversion/runtime/router?subtab=replay&request_id=req-ledger-001",
    )
    replay_admin = client.post(
        "/admin/automation-conversion/agent-orchestration/replay/arun-test-ledger-001",
        data={"admin_action_token": action_token},
        follow_redirects=True,
    )
    replay_html = replay_admin.get_data(as_text=True)
    assert replay_admin.status_code == 200
    assert "已生成回放副本" in replay_html
    assert "req-ledger-001" in replay_html

    page_response = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={
            "subtab": "outputs",
            "request_id": "req-ledger-001",
            "date_from": "2026-04-10 00:00:00",
            "date_to": "2026-04-10 23:59:59",
        },
    )
    page_html = page_response.get_data(as_text=True)
    assert page_response.status_code == 200
    assert "输出记录" in page_html
    assert "用户 ID" in page_html
    assert "查看全部历史话术" in page_html
    assert "详情区" not in page_html
    assert "req-ledger-001" in page_html
    assert "欢迎联系我" in page_html
    assert "这里默认直接展示历史生成话术" in page_html

    default_scripts_page = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={"subtab": "outputs"},
    )
    default_scripts_html = default_scripts_page.get_data(as_text=True)
    assert default_scripts_page.status_code == 200
    assert "用户 ID" in default_scripts_html
    assert "查看全部历史话术" in default_scripts_html
    assert "欢迎联系我" in default_scripts_html

    detail_page = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={"subtab": "outputs", "output_id": output["output_id"]},
    )
    detail_html = detail_page.get_data(as_text=True)
    assert detail_page.status_code == 200
    assert "话术详情" in detail_html
    assert "关闭" in detail_html


def test_run_center_output_console_formats_user_datetime_and_unicode_text(app, client):
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-console-001",
                "request_id": "req-console-001",
                "userid": "sales_agent",
                "external_contact_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ",
                "agent_code": "pricing_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "input_snapshot": {
                    "completed_at": "2026-04-13T04:52:22.164229+00:00",
                    "reason": "\\u7528\\u6237\\u6700\\u8fd1\\u8fde\\u7eed\\u5728\\u95ee\\u4ed8\\u8d39\\u65b9\\u5f0f",
                },
                "variables_snapshot": {
                    "last_touch_at": "2026-04-13T13:36:14.217516+08:00",
                    "latest_agent_outputs": ["\\u4f60\\u597d\\uff0c\\u6211\\u5728"],
                },
                "role_prompt_version": "published-v5",
                "task_prompt_version": "draft-v5",
                "status": "success",
                "source": "test",
            }
        )
        output = append_agent_output(
            {
                "output_id": "aout-console-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ",
                "agent_code": "pricing_agent",
                "output_type": "agent_reply_draft",
                "raw_output_text": json.dumps(
                    {
                        "reason": "\\u7528\\u6237\\u6700\\u8fd1\\u8fde\\u7eed\\u5728\\u95ee\\u4ed8\\u8d39\\u65b9\\u5f0f",
                        "completed_at": "2026-04-13T04:52:22.164229+00:00",
                    },
                    ensure_ascii=False,
                ),
                "normalized_output": {
                    "reason": "\\u7528\\u6237\\u6700\\u8fd1\\u8fde\\u7eed\\u5728\\u95ee\\u4ed8\\u8d39\\u65b9\\u5f0f",
                    "draft_reply": "你好，这里是中文话术。",
                },
                "rendered_output_text": "你好，这里是中文话术。",
                "target_agent_code": "pricing_agent",
                "target_pool": "operating",
                "confidence": 0.92,
                "reason": "\\u7528\\u6237\\u6700\\u8fd1\\u8fde\\u7eed\\u5728\\u95ee\\u4ed8\\u8d39\\u65b9\\u5f0f",
                "applied_status": "generated",
            }
        )
        get_db().execute(
            "UPDATE automation_agent_output SET created_at = ? WHERE output_id = ?",
            ("2026-04-13T14:38:53.831499+08:00", output["output_id"]),
        )
        get_db().commit()
        detail = get_agent_output_detail(output["output_id"], visibility="console")

    assert detail["output"]["external_contact_id"] == "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"
    assert detail["output"]["created_at"] == "2026-04-13 14:38:53"
    assert detail["output"]["applied_status_label"] == "已生成未采用"
    assert "\\u7528" not in detail["output"]["normalized_output_pretty"]
    assert "用户最近连续在问付费方式" in detail["output"]["normalized_output_pretty"]
    assert "\\u4f60" not in detail["run"]["variables_snapshot_pretty"]
    assert "你好，我在" in detail["run"]["variables_snapshot_pretty"]
    assert "2026-04-13 13:36:14" in detail["run"]["variables_snapshot_pretty"]

    page_response = client.get(
        "/admin/automation-conversion/runtime/router",
        query_string={
            "subtab": "outputs",
            "external_contact_id": "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ",
            "output_id": output["output_id"],
            "scripts_only": 1,
        },
    )
    page_html = page_response.get_data(as_text=True)
    assert page_response.status_code == 200
    assert "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ" in page_html
    assert "wmbN***" not in page_html
    assert ".831499+08:00" not in page_html
    assert "采用状态" in page_html
    assert "已生成未采用" in page_html
    assert "\\u7528" not in page_html
    assert "用户最近连续在问付费方式" in page_html


def test_admin_can_review_generated_reply_and_feedback_is_visible_in_output_queries(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "agent-token"
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-review-001",
                "request_id": "req-review-001",
                "userid": "sales_agent",
                "external_contact_id": "wm_review_target_001",
                "agent_code": "pricing_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "status": "success",
                "source": "test",
            }
        )
        output = append_agent_output(
            {
                "output_id": "aout-review-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wm_review_target_001",
                "agent_code": "pricing_agent",
                "output_type": "agent_reply_draft",
                "raw_output_text": "建议先确认价格问题。",
                "normalized_output": {"draft_reply": "建议先确认价格问题。"},
                "rendered_output_text": "建议先确认价格问题。",
                "target_agent_code": "pricing_agent",
                "target_pool": "active_focus",
                "confidence": 0.88,
                "reason": "用户在问价格",
                "applied_status": "generated",
            }
        )

    action_token = _admin_action_token(
        client,
        "/admin/automation-conversion/runtime/router?subtab=outputs&external_contact_id=wm_review_target_001&scripts_only=1",
    )
    rejected_response = client.post(
        f"/admin/automation-conversion/agent-orchestration/outputs/{output['output_id']}/review",
        data={
            "admin_action_token": action_token,
            "decision": "rejected",
            "review_note": "这条话术太硬了，改得更自然一点",
            "external_contact_id": "wm_review_target_001",
            "scripts_only": "1",
        },
        follow_redirects=True,
    )
    rejected_html = rejected_response.get_data(as_text=True)
    assert rejected_response.status_code == 200
    assert "话术已标记为不采用" in rejected_html
    assert "已拒绝" in rejected_html
    assert "这条话术太硬了，改得更自然一点" in rejected_html

    detail_response = client.get(
        f"/api/admin/automation-conversion/agent-outputs/{output['output_id']}",
        headers={"Authorization": "Bearer agent-token"},
    )
    detail_payload = detail_response.get_json()
    assert detail_response.status_code == 200
    assert detail_payload["output"]["applied_status"] == "rejected"
    assert detail_payload["output"]["review_note"] == "这条话术太硬了，改得更自然一点"
    assert detail_payload["output"]["review_decision"] == "rejected"

    action_token = _admin_action_token(
        client,
        "/admin/automation-conversion/runtime/router?subtab=outputs&external_contact_id=wm_review_target_001&scripts_only=1",
    )
    adopted_response = client.post(
        f"/admin/automation-conversion/agent-orchestration/outputs/{output['output_id']}/review",
        data={
            "admin_action_token": action_token,
            "decision": "adopted",
            "external_contact_id": "wm_review_target_001",
            "scripts_only": "1",
        },
        follow_redirects=True,
    )
    adopted_html = adopted_response.get_data(as_text=True)
    assert adopted_response.status_code == 200
    assert "话术已标记为采用" in adopted_html
    assert "已采用" in adopted_html

    outputs_by_user = _mcp_call(
        client,
        "get_agent_outputs_by_user",
        {"userid": "wm_review_target_001", "limit": 10},
    )
    outputs_payload = json.loads(outputs_by_user.get_json()["result"]["content"][0]["text"])
    assert outputs_by_user.status_code == 200
    assert outputs_payload["rows"][0]["applied_status"] == "adopted"
    assert outputs_payload["rows"][0]["review_note"] == "这条话术太硬了，改得更自然一点"


def test_auto_reply_page_exposes_copy_send_and_reject_actions_without_adopt_button(app, client):
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-auto-reply-page-001",
                "request_id": "req-auto-reply-page-001",
                "userid": "sales_agent",
                "external_contact_id": "wm_auto_reply_page_001",
                "agent_code": "welcome_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "status": "success",
                "source": "test",
            }
        )
        append_agent_output(
            {
                "output_id": "aout-auto-reply-page-001",
                "run_id": run["run_id"],
                "request_id": run["request_id"],
                "userid": "sales_agent",
                "external_contact_id": "wm_auto_reply_page_001",
                "agent_code": "welcome_agent",
                "output_type": "agent_reply_draft",
                "raw_output_text": "页面动作测试话术",
                "normalized_output": {"draft_reply": "页面动作测试话术"},
                "rendered_output_text": "页面动作测试话术",
                "target_agent_code": "welcome_agent",
                "target_pool": "new_user",
                "confidence": 0.87,
                "reason": "页面动作测试",
                "applied_status": "generated",
            }
        )

    with client.session_transaction() as session:
        session["admin_session_user_id"] = 0
        session["admin_session_wecom_userid"] = ""
        session["admin_session_role_list"] = ["super_admin"]
        session["admin_session_login_type"] = "break_glass"
        session["admin_session_display_name"] = "test-admin"
        session["admin_session_break_glass_username"] = "test-admin"

    response = client.get("/admin/automation-conversion/auto-reply")
    html = response.get_data(as_text=True)
    outputs_js = Path("wecom_ability_service/static/admin_console/automation_auto_reply_outputs.js").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert "automation_auto_reply_outputs.js" in html
    assert "复制话术" in outputs_js
    assert "一键 webhook" in outputs_js
    assert "一键推企微群发" in outputs_js
    assert 'data-review-action="adopted"' not in html
    assert 'data-review-action="adopted"' not in outputs_js
    assert "review_output_webhook_send_base" in html
    assert "review_output_wecom_send_base" in html


def test_agent_output_ledger_api_requires_internal_token_and_export_is_rate_limited(app, client):
    with app.app_context():
        create_agent_run(
            {
                "run_id": "arun-auth-001",
                "request_id": "req-auth-001",
                "agent_code": "central_router_agent",
                "agent_type": "router",
                "provider": "lobster_shadow",
                "status": "success",
                "source": "test",
            }
        )
        append_agent_output(
            {
                "output_id": "aout-auth-001",
                "run_id": "arun-auth-001",
                "request_id": "req-auth-001",
                "agent_code": "central_router_agent",
                "output_type": "route_decision",
                "raw_output_text": '{"agent_code":"welcome_agent"}',
                "normalized_output": {"agent_code": "welcome_agent"},
                "rendered_output_text": "welcome_agent",
                "target_agent_code": "welcome_agent",
                "target_pool": "new_user",
                "applied_status": "shadow_recorded",
            }
        )
        db = get_db()
        for idx in range(5):
            db.execute(
                """
                INSERT INTO automation_agent_output_export_job (
                    job_id, requested_by, filters_json, status, total_count, exported_count, file_name, file_content_base64, error_message, created_at, updated_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '')
                """,
                (
                    f"aexp-rate-limit-{idx}",
                    "tester",
                    "{}",
                    "completed",
                    1,
                    1,
                    f"agent-outputs-{idx}.xls",
                    "",
                    "",
                ),
            )
        db.commit()

    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "agent-token"
    unauthorized = client.get("/api/admin/automation-conversion/agent-outputs")
    assert unauthorized.status_code == 401

    limited = client.post(
        "/api/admin/automation-conversion/agent-outputs/export",
        json={"filters": {"request_id": "req-auth-001"}, "requested_by": "tester"},
        headers={"Authorization": "Bearer agent-token"},
    )
    assert limited.status_code == 429
    assert limited.get_json()["error"] == "export rate limited, please retry later"


def test_mcp_agent_orchestration_tools_list_and_call_outputs(app, client):
    _seed_contact(app, external_userid="wm_agent_tool_001", mobile="13800009702", owner_userid="sales_tool", customer_name="技能客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_agent_tool_001",
        phone="13800009702",
        owner_staff_id="sales_tool",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
    )
    with app.app_context():
        run = create_agent_run(
            {
                "run_id": "arun-test-tool-001",
                "request_id": "req-tool-001",
                "userid": "sales_tool",
                "external_contact_id": "wm_agent_tool_001",
                "agent_code": "pricing_agent",
                "agent_type": "child_agent",
                "provider": "deepseek",
                "input_snapshot": {"messages": ["报价多少"]},
                "variables_snapshot": {"current_pool": "inactive_normal"},
                "final_prompt_preview": "prompt",
                "role_prompt_version": "v1",
                "task_prompt_version": "v1",
                "status": "success",
                "source": "test",
            }
        )
        output = append_agent_output(
            {
                "output_id": "aout-test-tool-001",
                "run_id": run["run_id"],
                "request_id": "req-tool-001",
                "userid": "sales_tool",
                "external_contact_id": "wm_agent_tool_001",
                "agent_code": "pricing_agent",
                "output_type": "next_action_suggestion",
                "raw_output_text": "建议继续报价解释",
                "normalized_output": {"next_action": "followup"},
                "rendered_output_text": "建议继续报价解释",
                "target_pool": "inactive_normal",
                "confidence": 0.78,
                "reason": "用户正在询价",
                "applied_status": "suggested",
            }
        )

    tools_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    tool_names = {tool["name"] for tool in tools_response.get_json()["result"]["tools"]}
    assert {
        "crm.get_member_basic",
        "crm.get_member_stage",
        "crm.get_member_snapshot",
        "list_agent_configs",
        "get_all_agent_prompts",
        "list_pending_agent_prompt_publish_requests",
        "script.list_items",
        "script.update_draft",
        "script.diff_draft",
        "script.submit_for_publish",
        "get_pool_snapshot",
        "get_agent_config",
        "diff_agent_prompt",
        "submit_agent_prompt_for_publish",
        "list_agent_outputs",
        "get_agent_output",
        "export_agent_outputs",
    }.issubset(tool_names)

    basic_payload = _mcp_call(client, "crm.get_member_basic", {"external_contact_id": "wm_agent_tool_001"}).get_json()["result"]["structuredContent"]
    assert basic_payload["member_exists"] is True
    assert basic_payload["basic"]["external_contact_id"] == "wm_agent_tool_001"

    stage_payload = _mcp_call(client, "crm.get_member_stage", {"external_contact_id": "wm_agent_tool_001"}).get_json()["result"]["structuredContent"]
    assert stage_payload["member_exists"] is True
    assert stage_payload["stage"]["current_pool"] in {"pending_questionnaire", "operating"}
    assert stage_payload["stage"]["current_pool_label"] in {"未填问卷人群", "运营中人群"}
    assert stage_payload["stage"]["current_stage_label"] in {"等待提交问卷", "运营中跟进"}

    snapshot_payload = _mcp_call(client, "crm.get_member_snapshot", {"external_contact_id": "wm_agent_tool_001"}).get_json()["result"]["structuredContent"]
    assert snapshot_payload["member_exists"] is True
    assert snapshot_payload["stage"]["current_pool"] in {"pending_questionnaire", "operating"}

    current_pool = snapshot_payload["stage"]["current_pool"] or "operating"
    pool_snapshot_payload = _mcp_call(client, "get_pool_snapshot", {"pool_key": current_pool, "limit": 5}).get_json()["result"]["structuredContent"]
    assert pool_snapshot_payload["pool_key"] == current_pool
    assert pool_snapshot_payload["member_count"] >= 1

    configs_payload = _mcp_call(client, "list_agent_configs", {"enabled_only": True, "request_id": "req-mcp-list-001"}).get_json()["result"]["structuredContent"]
    assert configs_payload["total"] >= 1
    assert any(item["agent_code"] == "pricing_agent" for item in configs_payload["items"])
    assert configs_payload["bundle_version"].startswith("bundle-")
    assert len(configs_payload["bundle_hash"]) == 64

    all_prompts_payload = _mcp_call(client, "get_all_agent_prompts", {"enabled_only": True, "request_id": "req-mcp-all-001"}).get_json()["result"]["structuredContent"]
    pricing_prompt = next(item for item in all_prompts_payload["items"] if item["agent_code"] == "pricing_agent")
    assert all_prompts_payload["bundle_version"] == configs_payload["bundle_version"]
    assert all_prompts_payload["bundle_hash"] == configs_payload["bundle_hash"]
    assert "role_prompt" in pricing_prompt["draft"]
    assert "task_prompt" in pricing_prompt["draft"]
    assert isinstance(pricing_prompt["draft"]["variables"], list)
    assert isinstance(pricing_prompt["draft"]["output_schema"], list)

    outputs_payload = _mcp_call(client, "list_agent_outputs", {"external_contact_id": "wm_agent_tool_001", "page": 1, "page_size": 10}).get_json()["result"]["structuredContent"]
    assert outputs_payload["total"] >= 1
    assert any(item["output_id"] == output["output_id"] for item in outputs_payload["rows"])
    assert any(item["raw_output_text"] == "建议继续报价解释" for item in outputs_payload["rows"])

    output_payload = _mcp_call(client, "get_agent_output", {"output_id": output["output_id"]}).get_json()["result"]["structuredContent"]
    assert output_payload["output"]["output_id"] == output["output_id"]
    assert output_payload["output"]["raw_output_text"] == "建议继续报价解释"

    script_list_payload = _mcp_call(client, "script.list_items", {"query": "pricing"}).get_json()["result"]["structuredContent"]
    assert any(item["agent_code"] == "pricing_agent" for item in script_list_payload["rows"])

    script_update_payload = _mcp_call(
        client,
        "script.update_draft",
        {
            "agent_code": "pricing_agent",
            "task_prompt": "请输出更克制的价格说明",
            "change_summary": "lobster 调整价格话术草稿",
            "operator": "lobster_test",
        },
    ).get_json()["result"]["structuredContent"]
    assert script_update_payload["updated"] is True
    assert script_update_payload["agent"]["draft"]["task_prompt"] == "请输出更克制的价格说明"

    partial_save_payload = _mcp_call(
        client,
        "save_agent_prompt_draft",
        {
            "agent_code": "pricing_agent",
            "task_prompt": "请只输出简洁的价格澄清",
            "change_summary": "partial patch 更新任务提示词",
            "request_id": "req-mcp-save-001",
            "operator": "lobster_test",
            "idempotency_key": "draft-patch-001",
        },
    ).get_json()["result"]["structuredContent"]
    assert partial_save_payload["agent"]["draft"]["task_prompt"] == "请只输出简洁的价格澄清"

    script_diff_payload = _mcp_call(client, "script.diff_draft", {"agent_code": "pricing_agent"}).get_json()["result"]["structuredContent"]
    assert script_diff_payload["fields"]["task_prompt_changed"] is True

    diff_payload = _mcp_call(client, "diff_agent_prompt", {"agent_code": "pricing_agent", "request_id": "req-mcp-diff-001"}).get_json()["result"]["structuredContent"]
    assert diff_payload["fields"]["task_prompt_changed"] is True

    script_submit_payload = _mcp_call(
        client,
        "script.submit_for_publish",
        {"agent_code": "pricing_agent", "operator": "lobster_test"},
    ).get_json()["result"]["structuredContent"]
    assert script_submit_payload["submitted"] is True
    assert script_submit_payload["status"] == "pending_manual_publish"

    submit_prompt_payload = _mcp_call(
        client,
        "submit_agent_prompt_for_publish",
        {"agent_code": "pricing_agent", "change_summary": "提交 child agent 草稿", "request_id": "req-mcp-submit-001", "operator": "lobster_test"},
    ).get_json()["result"]["structuredContent"]
    assert submit_prompt_payload["submitted"] is True
    assert submit_prompt_payload["status"] == "pending_manual_publish"

    pending_publish_payload = _mcp_call(
        client,
        "list_pending_agent_prompt_publish_requests",
        {"agent_code": "pricing_agent", "page": 1, "page_size": 10, "request_id": "req-mcp-pending-001"},
    ).get_json()["result"]["structuredContent"]
    assert pending_publish_payload["total"] >= 1
    assert pending_publish_payload["items"][0]["agent_code"] == "pricing_agent"
    assert pending_publish_payload["items"][0]["submitted_for_publish"] is True

    config_payload = _mcp_call(client, "get_agent_config", {"agent_code": "pricing_agent"}).get_json()["result"]["structuredContent"]
    assert config_payload["agent"]["agent_code"] == "pricing_agent"

    with app.app_context():
        audit_rows = get_db().execute(
            "SELECT skill_code, status FROM automation_agent_skill_call_audit ORDER BY id DESC LIMIT 32"
        ).fetchall()
    assert {row["skill_code"] for row in audit_rows}.issuperset(
        {
            "crm.get_member_basic",
            "crm.get_member_snapshot",
            "script.list_items",
            "script.update_draft",
            "script.diff_draft",
            "script.submit_for_publish",
            "list_agent_configs",
            "get_all_agent_prompts",
            "list_pending_agent_prompt_publish_requests",
            "get_pool_snapshot",
            "list_agent_outputs",
            "get_agent_output",
            "get_agent_config",
            "save_agent_prompt_draft",
            "diff_agent_prompt",
            "submit_agent_prompt_for_publish",
        }
    )


def test_agent_prompt_bundle_version_is_stable_and_changes_on_child_prompt_update(app):
    with app.app_context():
        before_configs = list_agent_configs(enabled_only=True)
        before_prompts = get_all_agent_prompts(enabled_only=True)
        assert before_configs["bundle_version"] == before_prompts["bundle_version"]
        assert before_configs["bundle_hash"] == before_prompts["bundle_hash"]

        repeated_configs = list_agent_configs(enabled_only=True)
        repeated_prompts = get_all_agent_prompts(enabled_only=True)
        assert before_configs["bundle_version"] == repeated_configs["bundle_version"]
        assert before_configs["bundle_hash"] == repeated_configs["bundle_hash"]
        assert before_prompts["bundle_version"] == repeated_prompts["bundle_version"]
        assert before_prompts["bundle_hash"] == repeated_prompts["bundle_hash"]

        save_agent_config_draft(
            "pricing_agent",
            {
                "task_prompt": "新的价格提示词 bundle change",
                "change_summary": "bundle test update",
            },
            operator_id="bundle_tester",
            source="test",
        )

        after_configs = list_agent_configs(enabled_only=True)
        after_prompts = get_all_agent_prompts(enabled_only=True)

    assert after_configs["bundle_hash"] != before_configs["bundle_hash"]
    assert after_configs["bundle_version"] != before_configs["bundle_version"]
    assert after_prompts["bundle_hash"] == after_configs["bundle_hash"]
    assert after_prompts["bundle_version"] == after_configs["bundle_version"]


def test_save_agent_prompt_draft_rejects_stale_expected_version_and_writes_skill_audit(app, client):
    with app.app_context():
        stale_version = int(get_agent_config_detail("pricing_agent")["draft_version"])
        save_agent_config_draft(
            "pricing_agent",
            {
                "task_prompt": "先把版本推进到下一版",
                "change_summary": "seed new version",
            },
            operator_id="seed_updater",
            source="test",
        )

    response = _mcp_call(
        client,
        "save_agent_prompt_draft",
        {
            "agent_code": "pricing_agent",
            "task_prompt": "这次保存应该冲突",
            "expected_draft_version": stale_version,
            "operator": "lobster_test",
            "request_id": "req-conflict-save-001",
            "idempotency_key": "conflict-save-001",
        },
    )
    payload = response.get_json()

    with app.app_context():
        audit_row = get_db().execute(
            """
            SELECT status, error_code, response_payload_json
            FROM automation_agent_skill_call_audit
            WHERE skill_code = 'save_agent_prompt_draft'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert response.status_code == 200
    assert payload["error"]["message"].startswith("draft_version_conflict:")
    assert dict(audit_row)["status"] == "error"
    assert dict(audit_row)["error_code"] == "draft_version_conflict"
    detail = json.loads(audit_row["response_payload_json"])["detail"]
    assert detail["expected_draft_version"] == stale_version
    assert detail["current_draft_version"] == stale_version + 1


def test_submit_agent_prompt_for_publish_rejects_stale_expected_version_and_writes_skill_audit(app, client):
    with app.app_context():
        stale_version = int(get_agent_config_detail("pricing_agent")["draft_version"])
        save_agent_config_draft(
            "pricing_agent",
            {
                "task_prompt": "推进版本后再提交",
                "change_summary": "seed publish conflict",
            },
            operator_id="seed_updater",
            source="test",
        )

    response = _mcp_call(
        client,
        "submit_agent_prompt_for_publish",
        {
            "agent_code": "pricing_agent",
            "expected_draft_version": stale_version,
            "operator": "lobster_test",
            "request_id": "req-conflict-submit-001",
            "idempotency_key": "conflict-submit-001",
        },
    )
    payload = response.get_json()

    with app.app_context():
        audit_row = get_db().execute(
            """
            SELECT status, error_code, response_payload_json
            FROM automation_agent_skill_call_audit
            WHERE skill_code = 'submit_agent_prompt_for_publish'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert response.status_code == 200
    assert payload["error"]["message"].startswith("draft_version_conflict:")
    assert dict(audit_row)["status"] == "error"
    assert dict(audit_row)["error_code"] == "draft_version_conflict"
    detail = json.loads(audit_row["response_payload_json"])["detail"]
    assert detail["expected_draft_version"] == stale_version
    assert detail["current_draft_version"] == stale_version + 1


def test_pending_publish_query_lists_submitted_child_agent_requests(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"
    with app.app_context():
        save_agent_config_draft(
            "pricing_agent",
            {
                "task_prompt": "待发布查询测试",
                "change_summary": "pending publish query",
            },
            operator_id="pending_tester",
            source="test",
        )
        submit_agent_prompt_for_publish(
            "pricing_agent",
            operator_id="pending_tester",
            change_summary="提交发布申请",
            expected_draft_version=get_agent_config_detail("pricing_agent")["draft_version"],
        )
        payload = list_pending_agent_prompt_publish_requests(agent_code="pricing_agent", page=1, page_size=20)

    assert payload["total"] == 1
    assert payload["items"][0]["agent_code"] == "pricing_agent"
    assert payload["items"][0]["submitted_for_publish"] is True
    assert payload["items"][0]["has_unpublished_changes"] is True

    response = client.get(
        "/api/admin/automation-conversion/agent-orchestration/pending-publish",
        query_string={"agent_code": "pricing_agent"},
        headers={"Authorization": "Bearer internal-token"},
    )
    api_payload = response.get_json()

    assert response.status_code == 200
    assert api_payload["ok"] is True
    assert api_payload["total"] == 1
    assert api_payload["items"][0]["submitted_for_publish"] is True


def test_router_pending_callback_check_creates_alert_output_without_duplicate_alerts(app, client, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, quiet_hours_start="00:00", quiet_hours_end="00:00")
    _seed_contact(app, external_userid="wm_reply_alert_001", mobile="13800009187", owner_userid="sales_01", customer_name="alert")
    _seed_automation_member(app, external_contact_id="wm_reply_alert_001", phone="13800009187", owner_staff_id="sales_01", current_pool="inactive_normal", follow_type="normal", activation_status="inactive", questionnaire_status="submitted", questionnaire_follow_type="normal", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-alert-001", seq=1, external_userid="wm_reply_alert_001", owner_userid="sales_01", sender="wm_reply_alert_001", receiver="sales_01", content="今天怎么还没回我", send_time="2026-04-09 16:00:00")
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"

    class _AckResponse:
        status_code = 200
        text = '{"ok":true,"accepted":true}'

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.orchestration_service.requests.post", lambda *args, **kwargs: _AckResponse())

    with app.app_context():
        save_agent_router_settings(
            {
                "enabled": True,
                "webhook_url": "https://lobster.example.com/router",
                "signature_token": "lobster-token",
                "signature_secret": "lobster-secret",
                "signature_header": "X-Lobster-Signature",
                "timeout_seconds": 5,
                "retry_count": 0,
                "fallback_strategy": {
                    "default_agent_code": "welcome_agent",
                    "default_pool": "new_user",
                    "pending_callback_timeout_minutes": 1,
                    "need_human_review": True,
                    "fail_closed": True,
                },
            },
            operator_id="tester-router",
        )
        run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        get_db().execute(
            "UPDATE automation_agent_run SET updated_at = '2026-04-09 12:00:00' WHERE run_id = ?",
            (dispatch["router_ingress"]["run_id"],),
        )
        get_db().commit()

        result = run_router_pending_callback_check(operator_id="router_checker")
        rerun_result = run_router_pending_callback_check(operator_id="router_checker")
        rows = get_db().execute(
            """
            SELECT output_type, applied_status, normalized_output_json
            FROM automation_agent_output
            WHERE request_id = ? AND output_type = 'pending_callback_alert'
            ORDER BY id ASC
            """,
            (dispatch["router_ingress"]["request_id"],),
        ).fetchall()

    assert result["alerted_count"] == 1
    assert rerun_result["alerted_count"] == 0
    assert rerun_result["existing_alert_count"] >= 1
    assert len(rows) == 1
    assert dict(rows[0])["applied_status"] == "alerted"
    assert json.loads(rows[0]["normalized_output_json"])["threshold_minutes"] == 1

    response = client.post(
        "/api/admin/automation-conversion/router-pending-callback-check",
        json={"older_than_minutes": 1, "limit": 10},
        headers={"Authorization": "Bearer internal-token"},
    )
    api_payload = response.get_json()

    assert response.status_code == 200
    assert api_payload["ok"] is True
    assert api_payload["alerted_count"] == 0


def test_sop_v1_defaults_seed_three_pool_configs_and_day1_only(app):
    with app.app_context():
        payload = ensure_sop_v1_defaults()
        configs = {item["pool_key"]: item for item in payload["configs"]}

    assert set(configs.keys()) == {"pending_questionnaire", "operating", "converted"}
    assert all(config["enabled"] is True for config in configs.values())
    assert all(config["send_time"] == "09:00" for config in configs.values())
    assert all(config["max_day_count"] == 1 for config in configs.values())
    assert all(len(payload["templates"][pool_key]) == 1 for pool_key in configs)
    assert all(payload["templates"][pool_key][0]["day_index"] == 1 for pool_key in configs)

    with app.app_context():
        timezones = [
            row["timezone"]
            for row in get_db().execute(
                "SELECT timezone FROM automation_sop_pool_config ORDER BY pool_key ASC"
            ).fetchall()
        ]
    assert timezones == ["Asia/Shanghai", "Asia/Shanghai", "Asia/Shanghai"]


def test_admin_automation_conversion_basic_config_page_omits_sop_publish_placeholders(app, client):
    with app.app_context():
        ensure_sop_v1_defaults()
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_sop_batch (
                pool_key, day_index, template_id, scheduled_for, status,
                total_count, success_count, skipped_count, failed_count, summary_json,
                created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "operating",
                1,
                "2026-04-08 09:00:00",
                "finished",
                8,
                5,
                2,
                1,
                json.dumps({"source": "test"}, ensure_ascii=False),
            ),
        )
        db.commit()

    program_id = _default_program_id(app)
    response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/flow-design",
        query_string={"section": "sop", "pool": "operating", "day": 1},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "基础配置" in html
    assert "问卷分层" in html
    assert "欢迎语 / 标签 / 二维码" in html
    assert "方案入口二维码" in html
    assert "SOP 剧本" not in html
    assert "池子 / 阶段选择" not in html
    assert "当前 Day 编辑器" not in html
    assert "新增一天" not in html
    assert "保存池子配置" not in html
    assert "发布管理" not in html
    assert "成功 5 / 跳过 2 / 失败 1" not in html
    assert "暂无执行记录" not in html
    assert "重复进同池不重来" not in html
    assert "离池期间错过的 SOP 不补发" not in html
    assert "最近 SOP 执行批次" not in html
    assert "最大 day 数" not in html
    assert 'name="timezone"' not in html


def test_api_admin_automation_conversion_sop_config_no_timezone_required(app, client):
    response = client.put(
        "/api/admin/automation-conversion/sop/config/new_user",
        json={"enabled": False, "send_time": "08:30"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["config"]["pool_key"] == "pending_questionnaire"
    assert payload["config"]["enabled"] is False
    assert payload["config"]["send_time"] == "08:30"
    assert payload["template_count"] == 1

    listing = client.get("/api/admin/automation-conversion/sop/config")
    listing_payload = listing.get_json()
    config_by_pool = {item["pool_key"]: item for item in listing_payload["configs"]}
    assert config_by_pool["pending_questionnaire"]["send_time"] == "08:30"

    with app.app_context():
        row = get_db().execute(
            "SELECT timezone FROM automation_sop_pool_config WHERE pool_key = ?",
            (_canonical_automation_pool("new_user"),),
        ).fetchone()
    assert row["timezone"] == "Asia/Shanghai"


def test_api_admin_automation_conversion_sop_template_save_reads_back_structured_local_images(app, client):
    local_image = {
        "file_name": "welcome.png",
        "content_type": "image/png",
        "data_url": _test_png_data_url(),
    }
    response = client.put(
        "/api/admin/automation-conversion/sop/templates/new_user/1",
        json={
            "content": "day1 欢迎文案",
            "enabled": True,
            "images_json": [local_image],
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["template"]["content"] == "day1 欢迎文案"
    assert payload["template"]["image_count"] == 1
    assert payload["template"]["images_json"][0]["file_name"] == "welcome.png"
    assert payload["template"]["images_json"][0]["data_url"] == local_image["data_url"]
    assert payload["template"]["images_json"][0]["preview_url"] == local_image["data_url"]

    templates_response = client.get("/api/admin/automation-conversion/sop/templates/new_user", query_string={"day": 1})
    templates_payload = templates_response.get_json()
    assert templates_response.status_code == 200
    assert templates_payload["selected_template"]["images_json"][0]["file_name"] == "welcome.png"

    with app.app_context():
        raw_row = get_db().execute(
            "SELECT images_json FROM automation_sop_template WHERE pool_key = ? AND day_index = ?",
            (_canonical_automation_pool("new_user"), 1),
        ).fetchone()
    assert json.loads(raw_row["images_json"]) == [local_image]


def test_api_admin_automation_conversion_sop_delete_day_reorders_following_templates(app, client):
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2")
    _save_sop_template(app, pool_key="new_user", day_index=3, content="day3")
    _save_sop_template(app, pool_key="new_user", day_index=4, content="day4")

    response = client.delete("/api/admin/automation-conversion/sop/templates/new_user/2")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["template_count"] == 3
    assert payload["selected_day_index"] == 2
    assert payload["selected_template"]["content"] == "day3"

    with app.app_context():
        rows = get_db().execute(
            "SELECT day_index, content FROM automation_sop_template WHERE pool_key = ? ORDER BY day_index ASC",
            (_canonical_automation_pool("new_user"),),
        ).fetchall()

    assert [(row["day_index"], row["content"]) for row in rows] == [
        (1, "day1"),
        (2, "day3"),
        (3, "day4"),
    ]


def test_sop_run_due_uses_natural_calendar_day_two_after_entry(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2 跟进")
    _seed_contact(app, external_userid="wm_sop_day2_001", mobile="13800009511", owner_userid="sales_sop", customer_name="SOP Day2 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_day2_001",
        phone="13800009511",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:30:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 801, "wecom_result": {"msgid": "msg-801"}},
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch = get_db().execute("SELECT day_index FROM automation_sop_batch ORDER BY id DESC LIMIT 1").fetchone()
        progress = get_db().execute(
            "SELECT sop_anchor_date, last_sent_day, last_sent_at FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert result["ok"] is True
    assert result["created_batch_count"] == 1
    assert result["total_success_count"] == 1
    assert dispatched[0]["text"]["content"] == "day2 跟进"
    assert batch["day_index"] == 2
    assert progress["sop_anchor_date"] == "2026-04-08"
    assert progress["last_sent_day"] == 2
    assert progress["last_sent_at"] == "2026-04-09 09:05:00"


def test_sop_run_due_entry_after_send_time_starts_day1_next_day(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_day1_late", mobile="13800009512", owner_userid="sales_sop", customer_name="SOP Day1 晚入池")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_day1_late",
        phone="13800009512",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 09:00:00",
    )
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 802, "wecom_result": {"msgid": "msg-802"}},
    )

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    with app.app_context():
        first = run_due_sop(operator_id="sop-runner", operator_type="system")

    assert first["created_batch_count"] == 0
    assert first["total_success_count"] == 0
    assert dispatched == []

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 09:05:00")
    with app.app_context():
        second = run_due_sop(operator_id="sop-runner", operator_type="system")
        progress = get_db().execute(
            "SELECT sop_anchor_date, last_sent_day FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert second["total_success_count"] == 1
    assert len(dispatched) == 1
    assert progress["sop_anchor_date"] == "2026-04-09"
    assert progress["last_sent_day"] == 1


def test_sop_run_due_groups_same_day_candidates_into_one_dispatch(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_group_001", mobile="13800009513", owner_userid="sales_sop", customer_name="SOP 分组客户1")
    _seed_contact(app, external_userid="wm_sop_group_002", mobile="13800009514", owner_userid="sales_sop", customer_name="SOP 分组客户2")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_group_001",
        phone="13800009513",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_group_002",
        phone="13800009514",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:10:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 810, "wecom_result": {"msgid": "msg-810", "fail_list": []}},
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch = get_db().execute(
            "SELECT total_count, success_count, failed_count FROM automation_sop_batch ORDER BY id DESC LIMIT 1"
        ).fetchone()
        item_rows = get_db().execute(
            "SELECT external_userid, status, sent_record_id FROM automation_sop_batch_item ORDER BY external_userid ASC"
        ).fetchall()

    assert result["created_batch_count"] == 1
    assert result["total_success_count"] == 2
    assert len(dispatched) == 1
    assert sorted(dispatched[0]["external_userid"]) == ["wm_sop_group_001", "wm_sop_group_002"]
    assert dict(batch) == {"total_count": 2, "success_count": 2, "failed_count": 0}
    assert [(row["external_userid"], row["status"]) for row in item_rows] == [
        ("wm_sop_group_001", "success"),
        ("wm_sop_group_002", "success"),
    ]
    assert len({row["sent_record_id"] for row in item_rows}) == 1


def test_record_sop_pool_entry_reentry_preserves_anchor_date(app):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _seed_contact(app, external_userid="wm_sop_progress_001", mobile="13800009501", owner_userid="sales_sop", customer_name="SOP 进度客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_progress_001",
        phone="13800009501",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )

    with app.app_context():
        member_id = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm_sop_progress_001",),
        ).fetchone()["id"]
        first = record_sop_pool_entry(member_id=member_id, pool_key="new_user", entered_at="2026-04-08 08:00:00")
        second = record_sop_pool_entry(member_id=member_id, pool_key="new_user", entered_at="2026-04-10 08:30:00")
        row = get_db().execute(
            """
            SELECT COUNT(*) AS total, sop_anchor_date, first_effective_in_pool_at, last_in_pool_at
            FROM automation_sop_progress
            WHERE member_id = ? AND pool_key = ?
            """,
            (member_id, _canonical_automation_pool("new_user")),
        ).fetchone()

    assert first["id"] == second["id"]
    assert row["total"] == 1
    assert row["sop_anchor_date"] == "2026-04-08"
    assert row["first_effective_in_pool_at"] == "2026-04-08 08:00:00"
    assert row["last_in_pool_at"] == "2026-04-10 08:30:00"


def test_sop_run_due_reentry_keeps_anchor_and_does_not_backfill(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="inactive_normal", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="inactive_normal", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="inactive_normal", day_index=2, content="")
    _save_sop_template(app, pool_key="inactive_normal", day_index=3, content="day3 跟进")
    _seed_contact(app, external_userid="wm_sop_reenter_001", mobile="13800009521", owner_userid="sales_sop", customer_name="SOP 重入客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_reenter_001",
        phone="13800009521",
        owner_staff_id="sales_sop",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_follow_type="normal",
        decision_source="questionnaire",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 803, "wecom_result": {"msgid": "msg-803"}},
    )

    with app.app_context():
        member_id = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm_sop_reenter_001",),
        ).fetchone()["id"]
        record_sop_pool_entry(member_id=member_id, pool_key="inactive_normal", entered_at="2026-04-08 08:00:00")
        record_sop_pool_entry(member_id=member_id, pool_key="inactive_normal", entered_at="2026-04-10 08:30:00")
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch = get_db().execute("SELECT day_index FROM automation_sop_batch ORDER BY id DESC LIMIT 1").fetchone()
        progress = get_db().execute(
            "SELECT sop_anchor_date, last_sent_day, last_in_pool_at FROM automation_sop_progress WHERE member_id = ? AND pool_key = ?",
            (member_id, _canonical_automation_pool("inactive_normal")),
        ).fetchone()

    assert result["total_success_count"] == 1
    assert dispatched[0]["text"]["content"] == "day3 跟进"
    assert batch["day_index"] == 3
    assert progress["sop_anchor_date"] == "2026-04-08"
    assert progress["last_sent_day"] == 3
    assert progress["last_in_pool_at"] == "2026-04-10 08:30:00"


def test_manual_send_does_not_change_sop_anchor_or_progress(app, client, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _seed_contact(app, external_userid="wm_sop_manual_001", mobile="13800009566", owner_userid="sales_sop", customer_name="SOP 手工群发客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_manual_001",
        phone="13800009566",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 900, "wecom_result": {"msgid": "msg-900"}},
    )

    with app.app_context():
        member_id = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm_sop_manual_001",),
        ).fetchone()["id"]
        record_sop_pool_entry(member_id=member_id, pool_key="new_user", entered_at="2026-04-08 08:00:00")
        before = dict(
            get_db().execute(
                """
                SELECT sop_anchor_date, first_effective_in_pool_at, last_in_pool_at, last_sent_day, last_sent_at
                FROM automation_sop_progress
                WHERE member_id = ? AND pool_key = ?
                """,
                (member_id, _canonical_automation_pool("new_user")),
            ).fetchone()
        )

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "手工先发一条", "operator": "tester"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with app.app_context():
        after = dict(
            get_db().execute(
                """
                SELECT sop_anchor_date, first_effective_in_pool_at, last_in_pool_at, last_sent_day, last_sent_at
                FROM automation_sop_progress
                WHERE member_id = ? AND pool_key = ?
                """,
                (member_id, _canonical_automation_pool("new_user")),
            ).fetchone()
        )

    assert after == before


def test_sop_run_due_template_empty_skips_today_and_moves_to_next_day(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2 继续跟进")
    _seed_contact(app, external_userid="wm_sop_empty_001", mobile="13800009561", owner_userid="sales_sop", customer_name="SOP 空模板客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_empty_001",
        phone="13800009561",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 806, "wecom_result": {"msgid": "msg-806"}},
    )

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    with app.app_context():
        first = run_due_sop(operator_id="sop-runner", operator_type="system")
        first_item = get_db().execute(
            "SELECT status, error_message FROM automation_sop_batch_item ORDER BY id ASC LIMIT 1"
        ).fetchone()
        first_progress = get_db().execute(
            "SELECT last_sent_day FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert first["total_success_count"] == 0
    assert first["total_skipped_count"] == 1
    assert dispatched == []
    assert (first_item["status"], first_item["error_message"]) == ("skipped", "template_empty")
    assert first_progress["last_sent_day"] == 1

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 09:05:00")
    with app.app_context():
        second = run_due_sop(operator_id="sop-runner", operator_type="system")
        second_progress = get_db().execute(
            "SELECT last_sent_day FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert second["total_success_count"] == 1
    assert len(dispatched) == 1
    assert dispatched[0]["text"]["content"] == "day2 继续跟进"
    assert second_progress["last_sent_day"] == 2


def test_sop_historical_member_uses_real_entry_date_and_clamps_to_last_day(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2 跟进消息")
    _save_sop_template(app, pool_key="new_user", day_index=3, content="day3 最后一条消息")
    _seed_contact(app, external_userid="wm_sop_history_001", mobile="13800009571", owner_userid="sales_sop", customer_name="SOP 历史客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_history_001",
        phone="13800009571",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-01 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 807, "wecom_result": {"msgid": "msg-807"}},
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        progress = get_db().execute(
            """
            SELECT sop_anchor_date, first_effective_in_pool_at, last_sent_day
            FROM automation_sop_progress
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()

    assert result["total_success_count"] == 1
    assert dispatched[0]["text"]["content"] == "day3 最后一条消息"
    assert progress["sop_anchor_date"] == "2026-04-01"
    assert progress["first_effective_in_pool_at"] == "2026-04-01 08:00:00"
    assert progress["last_sent_day"] == 3


def test_recent_execution_summary_appears_on_pool_cards(app, client):
    with app.app_context():
        ensure_sop_v1_defaults()
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_sop_batch (
                pool_key, day_index, template_id, scheduled_for, status,
                total_count, success_count, skipped_count, failed_count, summary_json,
                created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "operating",
                2,
                "2026-04-08 10:00:00",
                "finished",
                6,
                3,
                2,
                1,
                json.dumps({"source": "test"}, ensure_ascii=False),
            ),
        )
        db.commit()

    program_id = _default_program_id(app)
    response = client.get(
        f"/admin/automation-conversion/programs/{program_id}/flow-design",
        query_string={"section": "sop", "pool": "operating", "day": 1},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2026-04-08 10:00:00" in html
    assert "成功 3 / 跳过 2 / 失败 1" in html


def test_sop_run_due_api_requires_token_and_returns_batches(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "sop-token"
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_api_001", mobile="13800009581", owner_userid="sales_sop", customer_name="SOP API 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_api_001",
        phone="13800009581",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 808, "wecom_result": {"msgid": "msg-808"}},
    )

    unauthorized = client.post("/api/admin/automation-conversion/sop/run-due", json={"operator": "tester"})
    authorized = client.post(
        "/api/admin/automation-conversion/sop/run-due",
        json={"operator": "tester"},
        headers={"Authorization": "Bearer sop-token"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    payload = authorized.get_json()
    assert payload["ok"] is True
    assert payload["requested_job_codes"] == ["sop"]
    assert payload["executed_job_count"] == 1
    assert payload["jobs"][0]["job_code"] == "sop"
    assert payload["jobs"][0]["result"]["scanned_pool_count"] == 1
    assert payload["jobs"][0]["result"]["created_batch_count"] == 1
    assert payload["total_success_count"] == 1
    assert len(payload["batch_ids"]) == 1


def test_sop_run_due_api_fails_closed_when_token_is_not_configured(app, client, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_api_closed_001", mobile="13800009582", owner_userid="sales_sop", customer_name="SOP API 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_api_closed_001",
        phone="13800009582",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")

    response = client.post("/api/admin/automation-conversion/sop/run-due", json={"operator": "tester"})

    assert response.status_code == 503
    assert response.get_json()["error"] == "internal token not configured"
    with app.app_context():
        batch_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch").fetchone()["total"]
    assert batch_total == 0


def test_due_jobs_api_runs_registered_sop_job(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "runner-token"
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_due_runner_001", mobile="13800009591", owner_userid="sales_sop", customer_name="Due Runner 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_due_runner_001",
        phone="13800009591",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 819, "wecom_result": {"msgid": "msg-819"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"operator": "due-runner", "jobs": ["sop"]},
        headers={"Authorization": "Bearer runner-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["requested_job_codes"] == ["sop"]
    assert payload["jobs"][0]["job_code"] == "sop"
    assert payload["jobs"][0]["result"]["created_batch_count"] == 1
    assert payload["total_success_count"] == 1


def test_due_jobs_api_runs_registered_conversion_workflow_job(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "runner-token"
    _seed_contact(app, external_userid="wm_due_workflow_job_001", mobile="13800009592", owner_userid="sales_01", customer_name="任务流 Runner 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_due_workflow_job_001",
        phone="13800009592",
        owner_staff_id="sales_01",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    workflow_bundle = _create_test_workflow(app, workflow_name="due job 任务流", status="active")
    workflow_id = int(((workflow_bundle.get("workflow_bundle") or {}).get("workflow") or {}).get("id") or 0)
    with app.app_context():
        create_conversion_workflow_node(
            workflow_id,
            {
                "node_name": "runner 立即触发节点",
                "target_audience_code": "pending_questionnaire",
                "trigger_mode": "audience_entered",
                "content_mode": "standard_direct",
                "standard_content_text": "jobs/run-due 触发任务流",
                "enabled": True,
            },
            operator_id="tester",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.workflow_runtime.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 1820, "wecom_result": {"msgid": "msg-1820"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"operator": "due-runner", "jobs": ["conversion_workflow"]},
        headers={"Authorization": "Bearer runner-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["requested_job_codes"] == ["conversion_workflow"]
    assert payload["jobs"][0]["job_code"] == "conversion_workflow"
    assert payload["jobs"][0]["result"]["total_success_count"] == 1
    assert payload["total_success_count"] == 1


def test_due_jobs_api_rejects_invalid_internal_token_for_conversion_workflow_job(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "runner-token"

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"jobs": ["conversion_workflow"]},
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "invalid internal token"


def test_due_jobs_api_rejects_unknown_job_code(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "runner-token"

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"jobs": ["unknown-job"]},
        headers={"Authorization": "Bearer runner-token"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "unsupported due jobs: unknown-job"


def test_sop_run_due_second_pass_does_not_create_duplicate_empty_batch(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_dup_001", mobile="13800009583", owner_userid="sales_sop", customer_name="SOP 重复客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_dup_001",
        phone="13800009583",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 809, "wecom_result": {"msgid": "msg-809"}},
    )

    with app.app_context():
        first = run_due_sop(operator_id="sop-runner", operator_type="system")
        second = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch").fetchone()["total"]
        item_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch_item").fetchone()["total"]

    assert first["created_batch_count"] == 1
    assert first["total_success_count"] == 1
    assert second["created_batch_count"] == 0
    assert second["total_success_count"] == 0
    assert second["total_skipped_count"] == 0
    assert batch_total == 1
    assert item_total == 1
    assert len(dispatched) == 1


def test_sop_run_due_skips_pool_when_lock_is_held(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_lock_001", mobile="13800009584", owner_userid="sales_sop", customer_name="SOP 锁客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_lock_001",
        phone="13800009584",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_follow_type="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.repo.try_acquire_sop_pool_run_lock",
        lambda *, pool_key: False,
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch").fetchone()["total"]

    assert result["scanned_pool_count"] == 1
    assert result["created_batch_count"] == 0
    assert result["total_success_count"] == 0
    assert batch_total == 0


def test_qrcode_callback_creates_member_and_event(app):
    from wecom_ability_service.domains.automation_conversion.service import handle_qrcode_enter_from_callback

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-default', 'HuangYouCan', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_001",
            phone="13800004001",
            payload_json={"state": "scene-default"},
            operator_id="callback-user",
        )

        assert result["handled"] is True
        member = db.execute(
            """
            SELECT external_contact_id, phone, owner_staff_id, in_pool, current_pool, source_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_qrcode_001",),
        ).fetchone()
        assert dict(member) == {
            "external_contact_id": "wm_qrcode_001",
            "phone": "13800004001",
            "owner_staff_id": "HuangYouCan",
            "in_pool": 1,
            "current_pool": "pending_questionnaire",
            "source_type": "qrcode",
        }
        event = db.execute(
            "SELECT action, operator_type, operator_id FROM automation_event ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(event) == {
            "action": "qrcode_enter",
            "operator_type": "system",
            "operator_id": "callback-user",
        }

def test_qrcode_callback_sends_official_welcome_message(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import service as automation_service

    captured: dict[str, object] = {}

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            captured["payload"] = payload
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(automation_service, "get_contact_runtime_client", lambda: _StubClient())

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, welcome_message, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-welcome', 'HuangYouCan', '欢迎加入', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = automation_service.handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_002",
            phone="13800004002",
            payload_json={"state": "scene-welcome", "WelcomeCode": "welcome-001"},
            operator_id="callback-user",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["welcome_message"]["sent"] is True
        assert captured["payload"] == {
            "welcome_code": "welcome-001",
            "text": {"content": "欢迎加入"},
        }
        events = db.execute(
            "SELECT action FROM automation_event ORDER BY id DESC LIMIT 2"
        ).fetchall()
        assert [str(row["action"]) for row in events] == ["qrcode_welcome_sent", "qrcode_enter"]


def test_qrcode_callback_welcome_message_requires_welcome_code(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import service as automation_service

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            raise AssertionError("send_welcome_msg should not be called without welcome_code")

    monkeypatch.setattr(automation_service, "get_contact_runtime_client", lambda: _StubClient())

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, welcome_message, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-no-code', 'HuangYouCan', '欢迎加入', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = automation_service.handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_003",
            phone="13800004003",
            payload_json={"state": "scene-no-code"},
            operator_id="callback-user",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["welcome_message"]["sent"] is False
        assert result["welcome_message"]["error"] == "missing_welcome_code"
        event = db.execute(
            "SELECT action, remark FROM automation_event ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(event) == {
            "action": "qrcode_welcome_failed",
            "remark": "missing_welcome_code",
        }


def test_qrcode_callback_applies_entry_tag_and_persists_snapshot(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import service as automation_service

    captured: dict[str, object] = {}

    class _StubClient:
        def mark_external_contact_tags(
            self,
            *,
            external_userid: str,
            follow_user_userid: str,
            add_tags: list[str],
            remove_tags: list[str],
        ) -> dict[str, object]:
            captured["payload"] = {
                "external_userid": external_userid,
                "follow_user_userid": follow_user_userid,
                "add_tags": list(add_tags),
                "remove_tags": list(remove_tags),
            }
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(automation_service, "get_app_runtime_client", lambda: _StubClient())

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, entry_tag_id, entry_tag_name, entry_tag_group_name, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-tag', 'HuangYouCan', 'tag-channel-001', '渠道报名', '渠道来源', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = automation_service.handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_tag_001",
            phone="13800004004",
            payload_json={"state": "scene-tag"},
            operator_id="callback-user",
        )

        assert result["handled"] is True
        assert result["entry_tag"]["applied"] is True
        assert result["entry_tag"]["entry_tag_id"] == "tag-channel-001"
        assert captured["payload"] == {
            "external_userid": "wm_qrcode_tag_001",
            "follow_user_userid": "HuangYouCan",
            "add_tags": ["tag-channel-001"],
            "remove_tags": [],
        }

        snapshot = db.execute(
            """
            SELECT external_userid, userid, tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ?
            LIMIT 1
            """,
            ("wm_qrcode_tag_001",),
        ).fetchone()
        assert dict(snapshot) == {
            "external_userid": "wm_qrcode_tag_001",
            "userid": "HuangYouCan",
            "tag_id": "tag-channel-001",
            "tag_name": "渠道报名",
        }
        events = db.execute(
            "SELECT action, remark FROM automation_event ORDER BY id DESC LIMIT 2"
        ).fetchall()
        assert [dict(row) for row in events] == [
            {"action": "qrcode_entry_tag_applied", "remark": "渠道报名"},
            {"action": "qrcode_enter", "remark": ""},
        ]


def test_qrcode_callback_continues_welcome_and_tag_when_sop_progress_sync_fails(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import service as automation_service

    sent_payloads: dict[str, dict[str, object]] = {}

    class _StubContactClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            sent_payloads["welcome"] = payload
            return {"errcode": 0, "errmsg": "ok"}

    class _StubAppClient:
        def mark_external_contact_tags(
            self,
            *,
            external_userid: str,
            follow_user_userid: str,
            add_tags: list[str],
            remove_tags: list[str],
        ) -> dict[str, object]:
            sent_payloads["tag"] = {
                "external_userid": external_userid,
                "follow_user_userid": follow_user_userid,
                "add_tags": list(add_tags),
                "remove_tags": list(remove_tags),
            }
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(automation_service, "get_contact_runtime_client", lambda: _StubContactClient())
    monkeypatch.setattr(automation_service, "get_app_runtime_client", lambda: _StubAppClient())
    monkeypatch.setattr(
        automation_service,
        "_sync_sop_progress_for_transition",
        lambda before, after: (_ for _ in ()).throw(RuntimeError("sop progress write failed")),
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, welcome_message,
                entry_tag_id, entry_tag_name, entry_tag_group_name, status, created_at, updated_at
            )
            VALUES (
                'default_qrcode', '默认渠道二维码', 'scene-non-blocking', 'HuangYouCan', '欢迎加入',
                'tag-channel-002', '渠道报名', '渠道来源', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()

        result = automation_service.handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_non_blocking_001",
            phone="13800004005",
            payload_json={"state": "scene-non-blocking", "WelcomeCode": "welcome-non-blocking-001"},
            operator_id="callback-user",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["welcome_message"]["sent"] is True
        assert result["entry_tag"]["applied"] is True
        assert sent_payloads["welcome"] == {
            "welcome_code": "welcome-non-blocking-001",
            "text": {"content": "欢迎加入"},
        }
        assert sent_payloads["tag"] == {
            "external_userid": "wm_qrcode_non_blocking_001",
            "follow_user_userid": "HuangYouCan",
            "add_tags": ["tag-channel-002"],
            "remove_tags": [],
        }

        member = db.execute(
            """
            SELECT external_contact_id, owner_staff_id, in_pool, source_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_qrcode_non_blocking_001",),
        ).fetchone()
        assert dict(member) == {
            "external_contact_id": "wm_qrcode_non_blocking_001",
            "owner_staff_id": "HuangYouCan",
            "in_pool": 1,
            "source_type": "qrcode",
        }
        events = db.execute(
            "SELECT action FROM automation_event ORDER BY id DESC LIMIT 3"
        ).fetchall()
        assert [str(row["action"]) for row in events] == [
            "qrcode_entry_tag_applied",
            "qrcode_welcome_sent",
            "qrcode_enter",
        ]
