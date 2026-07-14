from __future__ import annotations

from tools import smoke_questionnaire_real_wecom_tag as smoke


def test_smoke_summary_accepts_durable_queue_without_request_path_provider_call() -> None:
    body = {
        "submission_id": "sub_001",
        "questionnaire_id": 1,
        "slug": "activation",
        "result": {"final_tags": ["tag_real_001"]},
        "durable_continuation_queued": True,
        "external_effect_job_status": "not_planned",
        "external_effect_job": None,
        "tag_apply": {
            "status": "queued",
            "wecom_api_called": False,
            "real_external_call_executed": False,
            "mark_tag_executed": False,
            "requires_approval": False,
            "execution_mode": "worker",
            "adapter_mode": "durable_internal_event",
            "durable_continuation_queued": True,
            "contact_tags_mirror_status": "skipped",
            "tag_ids": ["tag_real_001"],
        },
    }

    summary = smoke.summarize_response(
        http_status=200,
        body=body,
        raw_body="{}",
        expected_tag_id="tag_real_001",
        contact_tags_db_rows=None,
        contact_tags_db_error="",
        require_db_mirror=False,
    )

    assert summary["ok"] is True
    assert summary["submission_id"] == "sub_001"
    assert summary["tag_apply"]["status"] == "queued"
    assert summary["tag_apply"]["wecom_api_called"] is False
    assert summary["tag_apply"]["real_external_call_executed"] is False
    assert summary["tag_apply"]["mark_tag_executed"] is False
    assert summary["contact_tags_mirror_written"] is None
    assert summary["checks"]["durable_continuation_queued"] is True
    assert summary["checks"]["h5_did_not_plan_external_effect"] is True
    assert summary["checks"]["expected_tag_id_seen"] is True
    assert summary["manual_wecom_confirmation_required"] is True


def test_smoke_summary_rejects_synchronous_provider_success_in_h5_response() -> None:
    body = {
        "submission_id": "sub_002",
        "slug": "activation",
        "result": {"final_tags": ["tag_real_001"]},
        "durable_continuation_queued": True,
        "tag_apply": {
            "status": "succeeded",
            "wecom_api_called": True,
            "real_external_call_executed": True,
            "mark_tag_executed": True,
            "contact_tags_mirror_status": "updated",
        },
    }

    summary = smoke.summarize_response(
        http_status=200,
        body=body,
        raw_body="{}",
        expected_tag_id="tag_real_001",
        contact_tags_db_rows=[],
        contact_tags_db_error="",
        require_db_mirror=False,
    )

    assert summary["ok"] is False
    assert summary["tag_apply"]["status"] == "succeeded"
    assert summary["checks"]["h5_did_not_call_wecom"] is False
    assert summary["checks"]["h5_did_not_execute_external_call"] is False
    assert summary["contact_tags_mirror_written"] is False


def test_smoke_summary_requires_async_projection_when_requested() -> None:
    body = {
        "submission_id": "sub_003",
        "slug": "activation",
        "result": {"final_tags": ["tag_real_001"]},
        "durable_continuation_queued": True,
        "external_effect_job_status": "not_planned",
        "external_effect_job": None,
        "tag_apply": {
            "status": "queued",
            "wecom_api_called": False,
            "real_external_call_executed": False,
            "mark_tag_executed": False,
            "durable_continuation_queued": True,
            "tag_ids": ["tag_real_001"],
        },
    }

    summary = smoke.summarize_response(
        http_status=200,
        body=body,
        raw_body="{}",
        expected_tag_id="tag_real_001",
        contact_tags_db_rows=[],
        contact_tags_db_error="",
        require_db_mirror=True,
    )

    assert summary["ok"] is False
    assert summary["checks"]["contact_tags_db_mirror_found"] is False
    assert summary["manual_wecom_confirmation_required"] is True


def test_smoke_submission_payload_keeps_required_identity_fields() -> None:
    payload = smoke.build_submission_payload(
        answers={"q_activation": "activated"},
        unionid="union-001",
        external_userid="wm_001",
        follow_user_userid="owner-001",
        source_scene="unit",
    )

    assert payload == {
        "answers": {"q_activation": "activated"},
        "identity": {
            "unionid": "union-001",
            "external_userid": "wm_001",
            "follow_user_userid": "owner-001",
        },
        "source": {"scene": "unit"},
    }
