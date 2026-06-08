from __future__ import annotations

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.questionnaire import (
    backfill_questionnaire_submission_identities,
    replay_questionnaire_sidebar_profile_mappings,
)


def _seed_questionnaire(app) -> int:
    questionnaire_id = 710
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, 'identity-backfill-710', '身份回填问卷', '身份回填问卷', '', false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (questionnaire_id,),
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (71001, ?, 'mobile', '手机号', true, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (questionnaire_id,),
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, sidebar_profile_field, required, sort_order, created_at, updated_at
            )
            VALUES (71002, ?, 'textarea', '跟进诉求', 'needs_blockers_followup', false, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (questionnaire_id,),
        )
        db.commit()
    return questionnaire_id


def _seed_orphan_submissions(app, questionnaire_id: int) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid,
                name, status, raw_profile, first_seen_at, last_seen_at, created_at, updated_at
            )
            VALUES (
                'ww-test', 'wm_backfill_union_001', 'union-backfill-001', '', 'sales_union',
                'UnionID 回填客户', 'active', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES ('wm_backfill_mobile_001', '待回填客户', 'sales_backfill', '', '', CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (710001, '13800137100', 'tp-710001', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES ('wm_backfill_mobile_001', 710001, 'sales_backfill', 'sales_backfill', 'sales_backfill', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, unionid, external_userid, mobile_snapshot,
                total_score, final_tags, assessment_result_snapshot, redirect_url_snapshot, submitted_at
            )
            VALUES (
                710100, ?, 'union-backfill-001', 'union-backfill-001', '', '',
                0, '[]', '{}', '', '2026-05-23 10:09:21+08'
            )
            """,
            (questionnaire_id,),
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (710100, 71002, 'textarea', '跟进诉求', '[]', '[]', '[]', '[]', 'UnionID 直接同步', 0, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, external_userid, mobile_snapshot,
                total_score, final_tags, assessment_result_snapshot, redirect_url_snapshot, submitted_at
            )
            VALUES (
                710101, ?, 'openid-backfill-001', 'openid-backfill-001', '', '13800137100',
                0, '[]', '{}', '', '2026-05-23 11:37:35+08'
            )
            """,
            (questionnaire_id,),
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (710101, 71001, 'mobile', '手机号', '[]', '[]', '[]', '[]', '13800137100', 0, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (710101, 71002, 'textarea', '跟进诉求', '[]', '[]', '[]', '[]', '需要侧边栏同步', 0, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, external_userid, mobile_snapshot,
                total_score, final_tags, assessment_result_snapshot, redirect_url_snapshot, submitted_at
            )
            VALUES (
                710102, ?, 'openid-backfill-002', 'openid-backfill-002', '', '13800137101',
                0, '[]', '{}', '', '2026-05-23 13:09:21+08'
            )
            """,
            (questionnaire_id,),
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (710102, 71002, 'textarea', '跟进诉求', '[]', '[]', '[]', '[]', '暂无客户绑定', 0, CURRENT_TIMESTAMP)
            """
        )
        db.commit()


def test_questionnaire_identity_backfill_dry_run_reports_without_writing(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        questionnaire_id = _seed_questionnaire(app)
        _seed_orphan_submissions(app, questionnaire_id)

        with app.app_context():
            payload = backfill_questionnaire_submission_identities(
                questionnaire_id=questionnaire_id,
                since="2026-05-23 00:00:00+08",
                until="2026-05-23 23:59:59+08",
                apply=False,
            )
            assert payload["ok"] is True
            assert payload["dry_run"] is True
            assert payload["summary"] == {
                "candidate_count": 3,
                "resolvable_count": 2,
                "unionid_resolvable_count": 1,
                "mobile_resolvable_count": 1,
                "unresolved_count": 1,
                "applied_count": 0,
            }
            assert [item["status"] for item in payload["items"]] == ["resolvable", "resolvable", "unresolved"]
            by_id = {item["submission_id"]: item for item in payload["items"]}
            assert by_id[710100]["reason"] == "resolvable_by_unionid"
            assert by_id[710100]["unionid_status"] == "resolved"
            assert by_id[710101]["reason"] == "resolvable_by_mobile"
            assert by_id[710101]["unionid_status"] == "missing"
            assert by_id[710102]["unionid_status"] == "missing"
            assert by_id[710101]["sidebar_mapping_fields"] == ["needs_blockers_followup"]
            assert by_id[710101]["mobile_masked"] == "13***00"
            assert "13800137100" not in str(payload)
            row = get_db().execute(
                "SELECT external_userid, matched_by FROM questionnaire_submissions WHERE id = 710101"
            ).fetchone()
            assert row["external_userid"] == ""
            assert row["matched_by"] == ""


def test_questionnaire_identity_backfill_apply_updates_submission_and_sidebar_profile(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        questionnaire_id = _seed_questionnaire(app)
        _seed_orphan_submissions(app, questionnaire_id)

        with app.app_context():
            payload = backfill_questionnaire_submission_identities(
                questionnaire_id=questionnaire_id,
                since="2026-05-23 00:00:00+08",
                until="2026-05-23 23:59:59+08",
                apply=True,
            )
            assert payload["ok"] is True
            assert payload["dry_run"] is False
            assert payload["summary"] == {
                "candidate_count": 3,
                "resolvable_count": 2,
                "unionid_resolvable_count": 1,
                "mobile_resolvable_count": 1,
                "unresolved_count": 1,
                "applied_count": 2,
            }
            by_id = {item["submission_id"]: item for item in payload["items"]}
            assert by_id[710100]["status"] == "applied"
            assert by_id[710100]["reason"] == "applied_by_unionid"
            assert by_id[710101]["status"] == "applied"
            assert by_id[710101]["reason"] == "applied_by_mobile"
            assert by_id[710101]["sidebar_profile_mapping"] == {
                "applied": True,
                "reason": "",
                "fields": ["needs_blockers_followup"],
            }
            union_resolved = get_db().execute(
                """
                SELECT external_userid, matched_by, follow_user_userid
                FROM questionnaire_submissions
                WHERE id = 710100
                """
            ).fetchone()
            resolved = get_db().execute(
                """
                SELECT external_userid, matched_by, follow_user_userid
                FROM questionnaire_submissions
                WHERE id = 710101
                """
            ).fetchone()
            unresolved = get_db().execute(
                "SELECT external_userid, matched_by FROM questionnaire_submissions WHERE id = 710102"
            ).fetchone()
            union_profile = get_db().execute(
                """
                SELECT needs_blockers_followup, updated_by
                FROM sidebar_customer_profile_fields
                WHERE external_userid = 'wm_backfill_union_001'
                """
            ).fetchone()
            profile = get_db().execute(
                """
                SELECT needs_blockers_followup, updated_by
                FROM sidebar_customer_profile_fields
                WHERE external_userid = 'wm_backfill_mobile_001'
                """
            ).fetchone()
            assert union_resolved["external_userid"] == "wm_backfill_union_001"
            assert union_resolved["matched_by"] == "unionid"
            assert union_resolved["follow_user_userid"] == "sales_union"
            assert resolved["external_userid"] == "wm_backfill_mobile_001"
            assert resolved["matched_by"] == "mobile"
            assert resolved["follow_user_userid"] == "sales_backfill"
            assert unresolved["external_userid"] == ""
            assert unresolved["matched_by"] == ""
            assert union_profile["needs_blockers_followup"] == "UnionID 直接同步"
            assert union_profile["updated_by"] == "questionnaire_submit"
            assert profile["needs_blockers_followup"] == "需要侧边栏同步"
            assert profile["updated_by"] == "questionnaire_submit"


def test_questionnaire_sidebar_profile_replay_matches_recreated_questions_by_title(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        questionnaire_id = _seed_questionnaire(app)
        with app.app_context():
            db = get_db()
            db.execute(
                """
                INSERT INTO questionnaire_submissions (
                    id, questionnaire_id, respondent_key, external_userid, mobile_snapshot,
                    total_score, final_tags, assessment_result_snapshot, redirect_url_snapshot, submitted_at
                )
                VALUES (
                    710201, ?, 'resp-recreated-question', 'wm_recreated_question_001', '13800137201',
                    0, '[]', '{}', '', '2026-05-23 14:00:00+08'
                )
                """,
                (questionnaire_id,),
            )
            db.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                    selected_option_tags_snapshot, text_value, score_contribution, created_at
                )
                VALUES (
                    710201, 999002, 'textarea', '跟进诉求',
                    '[]', '[]', '[]', '[]', '旧题 ID 的答案也要同步', 0, CURRENT_TIMESTAMP
                )
                """
            )
            db.commit()

            dry_run = replay_questionnaire_sidebar_profile_mappings(
                questionnaire_id=questionnaire_id,
                submission_id=710201,
                apply=False,
            )
            assert dry_run["summary"] == {
                "candidate_count": 1,
                "applicable_count": 1,
                "applied_count": 0,
                "skipped_count": 0,
            }
            assert dry_run["items"][0]["patch_fields"] == ["needs_blockers_followup"]
            assert (
                get_db()
                .execute(
                    """
                    SELECT needs_blockers_followup
                    FROM sidebar_customer_profile_fields
                    WHERE external_userid = 'wm_recreated_question_001'
                    """
                )
                .fetchone()
                is None
            )

            applied = replay_questionnaire_sidebar_profile_mappings(
                questionnaire_id=questionnaire_id,
                submission_id=710201,
                apply=True,
            )
            assert applied["summary"]["applied_count"] == 1
            profile = get_db().execute(
                """
                SELECT needs_blockers_followup, updated_by
                FROM sidebar_customer_profile_fields
                WHERE external_userid = 'wm_recreated_question_001'
                """
            ).fetchone()
            assert profile["needs_blockers_followup"] == "旧题 ID 的答案也要同步"
            assert profile["updated_by"] == "questionnaire_submit"


def test_signed_sidebar_context_submit_binds_questionnaire_and_profile(client, app, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.domains.user_ops.service._resolve_third_party_user_id_by_mobile",
        lambda mobile: f"tp_{mobile}",
    )
    questionnaire_id = _seed_questionnaire(app)
    with app.app_context():
        from wecom_ability_service.http.questionnaire_support import build_sidebar_questionnaire_context_token

        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES ('wm_signed_sidebar_001', '签名上下文客户', 'sales_01', '', '')
            """
        )
        db.commit()
        token = build_sidebar_questionnaire_context_token(
            external_userid="wm_signed_sidebar_001",
            owner_userid="sales_01",
            follow_user_userid="sales_01",
            bind_by_userid="sales_01",
        )

    response = client.post(
        "/api/h5/questionnaires/identity-backfill-710/submit",
        json={
            "sidebar_context_token": token,
            "external_userid": "wm_spoofed_payload_should_not_win",
            "answers": {
                "71001": "13800137188",
                "71002": "侧边栏提交后立即同步",
            },
        },
        headers={"User-Agent": "Mozilla/5.0 MicroMessenger"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    questionnaires = client.get(
        "/api/sidebar/v2/questionnaires",
        query_string={"external_userid": "wm_signed_sidebar_001"},
    )
    assert questionnaires.status_code == 200
    assert questionnaires.get_json()["questionnaires"][0]["answers"] == [
        {"question": "手机号", "answer": "13800137188"},
        {"question": "跟进诉求", "answer": "侧边栏提交后立即同步"},
    ]

    with app.app_context():
        submission = get_db().execute(
            """
            SELECT external_userid, follow_user_userid, matched_by, mobile_snapshot
            FROM questionnaire_submissions
            WHERE questionnaire_id = ?
            """,
            (questionnaire_id,),
        ).fetchone()
        profile = get_db().execute(
            """
            SELECT needs_blockers_followup, updated_by
            FROM sidebar_customer_profile_fields
            WHERE external_userid = 'wm_signed_sidebar_001'
            """
        ).fetchone()
        assert dict(submission) == {
            "external_userid": "wm_signed_sidebar_001",
            "follow_user_userid": "sales_01",
            "matched_by": "signed_sidebar_context",
            "mobile_snapshot": "13800137188",
        }
        assert dict(profile) == {
            "needs_blockers_followup": "侧边栏提交后立即同步",
            "updated_by": "questionnaire_submit",
        }
