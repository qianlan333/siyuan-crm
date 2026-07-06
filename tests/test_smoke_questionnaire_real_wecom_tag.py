from __future__ import annotations

from tools import smoke_questionnaire_real_wecom_tag as smoke


def test_smoke_summary_accepts_real_mark_tag_success_with_response_mirror() -> None:
    body = {
        "submission_id": "sub_001",
        "questionnaire_id": 1,
        "slug": "activation",
        "result": {"final_tags": ["tag_real_001"]},
        "tag_apply": {
            "status": "succeeded",
            "wecom_api_called": True,
            "real_external_call_executed": True,
            "mark_tag_executed": True,
            "requires_approval": False,
            "execution_mode": "execute",
            "adapter_mode": "real_mark_tag",
            "contact_tags_mirror_status": "updated",
            "request_payload": {
                "userid": "owner-001",
                "external_userid": "wm_001",
                "add_tag": ["tag_real_001"],
            },
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
    assert summary["tag_apply"]["status"] == "succeeded"
    assert summary["tag_apply"]["wecom_api_called"] is True
    assert summary["tag_apply"]["real_external_call_executed"] is True
    assert summary["tag_apply"]["mark_tag_executed"] is True
    assert summary["contact_tags_mirror_written"] is True
    assert summary["checks"]["expected_tag_id_seen"] is True
    assert summary["manual_wecom_confirmation_required"] is True


def test_smoke_summary_fails_without_real_mark_tag_execution() -> None:
    body = {
        "submission_id": "sub_002",
        "slug": "activation",
        "result": {"final_tags": ["tag_real_001"]},
        "tag_apply": {
            "status": "failed",
            "error_code": "missing_external_userid",
            "wecom_api_called": False,
            "real_external_call_executed": False,
            "mark_tag_executed": False,
            "contact_tags_mirror_status": "skipped",
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
    assert summary["tag_apply"]["status"] == "failed"
    assert summary["tag_apply"]["error_code"] == "missing_external_userid"
    assert summary["checks"]["wecom_api_called"] is False
    assert summary["checks"]["contact_tags_db_mirror_found"] is False
    assert summary["contact_tags_mirror_written"] is False


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
