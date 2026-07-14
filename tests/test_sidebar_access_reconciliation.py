from scripts.ops.check_sidebar_questionnaire_access import redact_report


def test_access_reconciliation_report_is_fixed_count_only_schema() -> None:
    report = redact_report(
        {
            "ok": True,
            "phase": "preflight",
            "release_sha": "release-sha",
            "unsafe_count": 0,
            "counts": {
                "active_follow_relation_count": 12,
                "questionnaire_result_token_duplicate_group_count": 0,
                "unsafe_identity_value": "must-not-leak",
            },
            "external_userid": "must-not-leak",
            "answers": {"must": "not-leak"},
        }
    )

    assert report == (
        '{"count_digest":"","counts":{"active_follow_relation_count":12,'
        '"questionnaire_result_token_duplicate_group_count":0},"ok":true,'
        '"phase":"preflight","pii_included":false,"release_sha":"release-sha",'
        '"unsafe_count":0}'
    )
    assert "must-not-leak" not in report
