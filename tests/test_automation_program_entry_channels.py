from __future__ import annotations

import json

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import service as automation_service
from wecom_ability_service.domains.automation_conversion import workflow_repo
from wecom_ability_service.domains.automation_conversion.admission_service import admit_channel_contact_to_program
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program
from wecom_ability_service.domains.automation_conversion.member_state_service import handle_channel_enter_from_callback
from wecom_ability_service.domains.automation_conversion.workflow_definitions import NODE_TRIGGER_MODE_AUDIENCE_ENTERED
from wecom_ability_service.domains.automation_conversion.workflow_runtime import _node_day_index_matches, _run_immediate_node
from wecom_ability_service.domains.automation_conversion.workflow_service import get_conversion_workflow_model_bundle

from automation_channel_admission_helpers import (
    create_channel,
    create_choice_questionnaire,
    create_program,
    disabled_entry_rule,
    save_audience_entry_rule,
    seed_questionnaire_submission,
    set_callback_now,
    table_count,
)


def test_workflow_runtime_uses_operating_entered_at_not_pre_pool_questionnaire_time(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("runtime_operating_channel")
        binding_id = int(bind_channels_to_program(program_id, [int(channel["id"])], {}, "pytest")["bindings"][0]["id"])
        questionnaire = create_choice_questionnaire("runtime_questionnaire")
        seed_questionnaire_submission(
            questionnaire_id=questionnaire["id"],
            external_contact_id="wm_runtime_001",
            submitted_at="2026-05-20 08:00:00",
        )
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire["id"]},
                "conversion_review": {"enabled": False},
            },
        )

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_001",
            trigger_time="2026-05-23 10:00:00",
        )

        assert result["program_member"]["current_stage_code"] == "operating"
        rows = workflow_repo.list_current_member_audience_rows("operating", program_id=program_id)
        assert len(rows) == 1
        assert rows[0]["member"]["external_contact_id"] == "wm_runtime_001"
        assert rows[0]["entered_at"] == "2026-05-23 10:00:00"
        assert _node_day_index_matches(
            entered_at=rows[0]["entered_at"],
            send_time="09:00",
            scheduled_for="2026-05-24 09:00:00",
            expected_day_offset=1,
        )
        assert not _node_day_index_matches(
            entered_at="2026-05-20 08:00:00",
            send_time="09:00",
            scheduled_for="2026-05-24 09:00:00",
            expected_day_offset=1,
        )


def test_workflow_runtime_excludes_order_review_waiting_from_operating_candidates(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("runtime_order_wait_channel")
        binding_id = int(bind_channels_to_program(program_id, [int(channel["id"])], {}, "pytest")["bindings"][0]["id"])
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": True, "selected_product_id": "product_A"},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": False},
            },
        )

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_002",
            trigger_time="2026-05-23 10:00:00",
        )

        assert result["program_member"]["current_stage_code"] == "order_review"
        assert workflow_repo.list_current_member_audience_rows("operating", program_id=program_id) == []
        pending_rows = workflow_repo.list_current_member_audience_rows("pending_questionnaire", program_id=program_id)
        assert len(pending_rows) == 1
        assert pending_rows[0]["entered_at"] == "2026-05-23 10:00:00"


def test_duplicate_scan_does_not_duplicate_audience_entered_immediate_execution(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("runtime_duplicate_immediate_channel")
        bind_channels_to_program(program_id, [int(channel["id"])], {}, "pytest")
        save_audience_entry_rule(program_id, disabled_entry_rule())

        workflow = workflow_repo.insert_workflow_row(
            {
                "program_id": program_id,
                "workflow_code": "runtime_immediate",
                "workflow_name": "Runtime Immediate",
                "status": "active",
                "segmentation_basis": "none",
                "generation_mode": "manual_layered",
                "enabled": True,
                "created_by": "pytest",
                "updated_by": "pytest",
            }
        )
        node = workflow_repo.insert_workflow_node_row(
            {
                "workflow_id": int(workflow["id"]),
                "node_code": "op_immediate",
                "node_name": "入群即时触达",
                "target_audience_code": "operating",
                "trigger_mode": NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
                "day_offset": 1,
                "send_time": "09:00",
                "enabled": True,
            }
        )
        workflow_repo.insert_workflow_node_content_row(
            {
                "node_id": int(node["id"]),
                "standard_content_text": "标准运营内容",
                "standard_content_payload_json": {},
                "fallback_to_standard_content": True,
            }
        )
        get_db().commit()

        set_callback_now(monkeypatch, "2026-05-23 10:00:00")
        first = handle_channel_enter_from_callback(
            external_contact_id="wm_runtime_003",
            payload_json={"state": channel["scene_value"]},
            channel=channel,
            follow_user_userid="sales_01",
        )
        bundle = get_conversion_workflow_model_bundle(int(workflow["id"]))
        first_run = _run_immediate_node(workflow_bundle=bundle, node=dict(bundle["nodes"][0]), operator_id="pytest")
        get_db().commit()

        set_callback_now(monkeypatch, "2026-05-24 10:00:00")
        second = handle_channel_enter_from_callback(
            external_contact_id="wm_runtime_003",
            payload_json={"state": channel["scene_value"]},
            channel=channel,
            follow_user_userid="sales_01",
        )
        second_run = _run_immediate_node(workflow_bundle=bundle, node=dict(bundle["nodes"][0]), operator_id="pytest")
        get_db().commit()

        assert first["admission_results"][0]["admission_status"] == "accepted"
        assert second["admission_results"][0]["admission_status"] == "duplicate_active"
        assert table_count("automation_member_audience_entry", "is_current = TRUE") == 1
        assert first_run["summary"]["diagnostics"]["candidate_audience_total"] == 1
        assert second_run["summary"]["diagnostics"]["candidate_audience_total"] == 1
        assert table_count("automation_workflow_execution") == 1
        assert table_count("broadcast_jobs", "source_type = 'workflow'") == 1


def test_qrcode_callback_resolves_stale_scene_from_history_and_applies_historical_entry_tag(app, monkeypatch):
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

    with app.app_context():
        program_id = create_program("program_stale_scene")
        channel = create_channel("runtime_stale_scene_channel")
        historical_scene = str(channel["scene_value"])
        bind_channels_to_program(program_id, [int(channel["id"])], {}, "pytest")
        save_audience_entry_rule(program_id, disabled_entry_rule())

        historical = handle_channel_enter_from_callback(
            external_contact_id="wm_history_stale_scene",
            payload_json={"State": historical_scene},
            channel=channel,
            follow_user_userid="HuangYouCan",
        )
        assert historical["handled"] is True
        assert historical["admission_results"][0]["admission_status"] == "accepted"

        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_event_logs (
                corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
                payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
            )
            VALUES (
                'ww-test', 'change_external_contact', 'add_external_contact',
                'wm_history_stale_scene', 'HuangYouCan', 1712023200, 'event-stale-scene-history',
                '<xml></xml>', CAST(? AS jsonb), 'success', 0, '',
                '2026-05-24 15:08:00', '2026-05-24 15:08:00'
            )
            """,
            (json.dumps({"State": historical_scene}),),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES ('wm_history_stale_scene', 'HuangYouCan', 'tag-signup-lead', '报名引流品')
            """
        )
        db.execute(
            """
            UPDATE automation_channel
            SET scene_value = 'scene_overwritten_by_admin_save',
                entry_tag_id = '',
                entry_tag_name = '',
                entry_tag_group_name = '',
                welcome_message = '欢迎加入报名渠道',
                owner_staff_id = 'HuangYouCan',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(channel["id"]),),
        )
        db.commit()

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_future_stale_scene",
            payload_json={"State": historical_scene, "WelcomeCode": "welcome-stale-scene"},
            follow_user_userid="HuangYouCan",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["mode"] == "program_admission"
        assert result["admission_results"][0]["admission_status"] == "accepted"
        assert result["member"]["source_channel_id"] == int(channel["id"])
        assert result["welcome_message"]["sent"] is True
        assert result["entry_tag"]["applied"] is True
        assert result["entry_tag"]["entry_tag_id"] == "tag-signup-lead"
        assert result["entry_tag"]["entry_tag_name"] == "报名引流品"
        assert sent_payloads["welcome"] == {
            "welcome_code": "welcome-stale-scene",
            "text": {"content": "欢迎加入报名渠道"},
        }
        assert sent_payloads["tag"] == {
            "external_userid": "wm_future_stale_scene",
            "follow_user_userid": "HuangYouCan",
            "add_tags": ["tag-signup-lead"],
            "remove_tags": [],
        }
        tag_snapshot = db.execute(
            """
            SELECT external_userid, userid, tag_id, tag_name
            FROM contact_tags
            WHERE external_userid = ?
            """,
            ("wm_future_stale_scene",),
        ).fetchone()
        assert dict(tag_snapshot) == {
            "external_userid": "wm_future_stale_scene",
            "userid": "HuangYouCan",
            "tag_id": "tag-signup-lead",
            "tag_name": "报名引流品",
        }
