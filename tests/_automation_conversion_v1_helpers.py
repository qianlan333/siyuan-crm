"""Shared helpers + fixtures used by tests/test_automation_conversion_v1.py.

Extracted from the historical 11.7k-line single test file (V1 wave 4 closeout
test bundle) to keep the test module focused on test bodies. Helpers stay
underscore-prefixed (private to tests/) but are explicitly re-exported via
``__all__`` so callers can ``from _automation_conversion_v1_helpers import *``.

Fixtures (``app``, ``client``) intentionally stay in the test module so pytest
discovery picks them up via the canonical ``@pytest.fixture`` decoration in the
collecting module.
"""

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




def _sqlite_object_names(db, object_type: str) -> set[str]:
    """PG-only：用 information_schema 替代 SQLite 的 sqlite_master。

    object_type 仅支持 ``'table'`` / ``'index'``（测试里只用到这两种）。
    """
    if object_type == "table":
        rows = db.execute(
            """
            SELECT table_name AS name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
    elif object_type == "index":
        rows = db.execute(
            """
            SELECT indexname AS name
            FROM pg_indexes
            WHERE schemaname = current_schema()
            """
        ).fetchall()
    else:
        rows = []
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
    in_pool: bool | int = True,
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
                bool(in_pool),
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
            VALUES (?, ?, ?, ?, '', false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
            VALUES (?, ?, 'single_choice', '你当前更关注什么？', true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
            VALUES (?, ?, 'mobile', '请填写手机号', true, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                bool(enabled),
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
            VALUES (?, ?, ?, '', true, 'test', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
            VALUES (?, ?, '[]', true, '', '', '[]', '[]', '', '', '[]', '[]', 1, 1, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(agent_code) DO UPDATE SET
                display_name = excluded.display_name,
                enabled = true,
                published_version = GREATEST(automation_agent_config.published_version, 1),
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




__all__ = [
    "_test_png_bytes",
    "_build_stage_send_form_data",
    "_admin_action_token",
    "_default_program_id",
    "_login_admin_session",
    "_mcp_call",
    "_sqlite_object_names",
    "_seed_contact",
    "_canonical_automation_pool",
    "_seed_automation_member",
    "_seed_settings_questionnaire",
    "_seed_profile_segment_template",
    "_save_signup_conversion_settings",
    "_configure_message_activity_db",
    "_mock_workflow_runtime_usage_counts",
    "_mock_workflow_runtime_now",
    "_FakeDeepSeekResponse",
    "_configure_reply_monitor",
    "_seed_archived_message",
    "_assign_member_to_current_audience",
    "_seed_questionnaire_submission_for_member",
    "_patch_reply_monitor_payload_context",
    "_configure_sop_pool",
    "_configure_only_sop_pool",
    "_set_sop_pool_effective_start",
    "_create_test_workflow",
    "_seed_test_agent_config",
    "_seed_workflow_execution",
]
