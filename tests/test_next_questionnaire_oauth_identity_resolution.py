from __future__ import annotations

from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import IdentityResolution, ResolvePersonIdentityRequest
from aicrm_next.questionnaire.application import ListQuestionnaireSubmissionsQuery
from aicrm_next.questionnaire.h5_write import QuestionnaireH5SubmitCommand, execute_questionnaire_h5_submit
from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state


def test_next_identity_resolution_query_uses_postgres_repository_when_production_ready(monkeypatch):
    class FakeFixtureRepository:
        def resolve(self, query):  # pragma: no cover - should not be used in this test
            raise AssertionError("fixture repository should not resolve production identity")

    class FakePostgresRepository:
        def resolve(self, query):
            assert query.unionid == "unionid_live_001"
            return IdentityResolution(
                person_id=None,
                external_userid="wm_live_001",
                mobile=None,
                openid="openid_live_001",
                unionid="unionid_live_001",
                binding_status="bound",
                owner_userid="owner_live_001",
                identity_map_id=75550,
                follow_user_userid="owner_live_001",
                matched_by="unionid",
            )

    monkeypatch.setattr("aicrm_next.identity_contact.application.production_data_ready", lambda: True)

    result = ResolvePersonIdentityQuery(
        repo=FakeFixtureRepository(),
        postgres_repo=FakePostgresRepository(),
    ).execute(ResolvePersonIdentityRequest(unionid=" unionid_live_001 "))

    assert result is not None
    assert result.external_userid == "wm_live_001"
    assert result.identity_map_id == 75550
    assert result.follow_user_userid == "owner_live_001"
    assert result.matched_by == "unionid"


def test_next_questionnaire_submission_persists_identity_map_resolution(monkeypatch):
    reset_questionnaire_fixture_state()

    class FakeResolvePersonIdentityQuery:
        def __call__(self, request):
            assert request.unionid == "unionid_live_001"
            return IdentityResolution(
                person_id=None,
                external_userid="wm_live_001",
                mobile=None,
                openid="openid_live_001",
                unionid="unionid_live_001",
                binding_status="bound",
                owner_userid="owner_live_001",
                identity_map_id=75550,
                follow_user_userid="owner_live_001",
                matched_by="unionid",
            )

    monkeypatch.setattr(
        "aicrm_next.questionnaire.h5_write.ResolvePersonIdentityQuery",
        FakeResolvePersonIdentityQuery,
    )

    result = execute_questionnaire_h5_submit(
        QuestionnaireH5SubmitCommand(
            questionnaire_slug="hxc-activation-v1",
            answers={"q_activation": "activated"},
            identity={"openid": "openid_live_001", "unionid": "unionid_live_001"},
            source={"source": "identity-map-resolution-test"},
            source_route="/s/hxc-activation-v1",
            idempotency_key="identity-map-resolution-next",
        )
    )

    assert result["ok"] is True
    assert result["external_userid"] == "wm_live_001"
    submissions = ListQuestionnaireSubmissionsQuery().execute(1, limit=10)
    created = [item for item in submissions["submissions"] if item["submission_id"] == result["submission_id"]][0]
    assert created["identity_map_id"] == 75550
    assert created["external_userid"] == "wm_live_001"
    assert created["follow_user_userid"] == "owner_live_001"
    assert created["matched_by"] == "unionid"
