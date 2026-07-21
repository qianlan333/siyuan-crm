from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aicrm_next.questionnaire.continuation import (
    ACTION_AGENT_FOLLOWUP,
    QuestionnaireContinuationService,
)
from aicrm_next.questionnaire.continuation_repo import InMemoryQuestionnaireContinuationRepository
from aicrm_next.shared.sensitive_data import redact_sensitive_data


class FakeQuestionnaireRepository:
    def __init__(self) -> None:
        self.submission = {
            "id": 483,
            "submission_id": "483",
            "questionnaire_id": 13,
            "unionid": "unionid-continuation-001",
            "external_userid": "",
            "follow_user_userid": "",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "final_tags": [],
        }

    def get_submission_by_record_id(self, _submission_id: str):
        return dict(self.submission)

    def get_questionnaire(self, questionnaire_id: int):
        return {"id": questionnaire_id, "slug": "salon-questionnaire"}


class FakeAudienceRepository:
    def __init__(self, updated_count: int = 1, scheduled_count: int | None = None) -> None:
        self.updated_count = updated_count
        self.scheduled_count = updated_count if scheduled_count is None else scheduled_count
        self.counts: list[tuple[str, str]] = []
        self.pokes: list[tuple[str, str]] = []
        self.rewinds: list[tuple[str, str, datetime]] = []

    def count_dependencies(self, *, source_type: str, source_key: str = "") -> int:
        self.counts.append((source_type, source_key))
        return self.updated_count

    def poke_dependencies(self, *, source_type: str, source_key: str = "") -> int:
        self.pokes.append((source_type, source_key))
        return self.updated_count

    def poke_dependencies_since(
        self,
        *,
        source_type: str,
        source_key: str = "",
        since_at: datetime,
    ) -> int:
        self.rewinds.append((source_type, source_key, since_at))
        self.pokes.append((source_type, source_key))
        return self.scheduled_count


class FakeOwnerCandidatesQuery:
    def __init__(self, owners: set[str]) -> None:
        self.owners = owners

    def execute(self, *, external_userid: str):
        assert external_userid
        return set(self.owners)


def test_continuation_waits_for_identity_then_dispatches_agent_once() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    audience_repo = FakeAudienceRepository()
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=audience_repo,
    )

    first = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-questionnaire-483",
        identity_ready=False,
    )
    duplicate = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-questionnaire-483-duplicate",
        identity_ready=False,
    )

    assert first["job"]["id"] == duplicate["job"]["id"]
    assert first["job"]["status"] == "waiting_identity"
    assert "mobile" not in first["job"]
    assert "openid" not in first["job"]
    assert "answers" not in first["job"]
    assert service.agent_dependency_count(13) == 1
    assert audience_repo.pokes == []

    questionnaire_repo.submission.update(
        {
            "external_userid": "wm_external_continuation_001",
            "follow_user_userid": "staff_continuation_001",
        }
    )
    wake = service.wake_by_identity("unionid-continuation-001", source_event_id="iev-identity-ready")
    repeated = service.wake_by_identity("unionid-continuation-001", source_event_id="iev-identity-ready-duplicate")
    rows, counts = continuation_repo.list_operations(13)

    assert wake["dispatched_count"] == 1
    assert repeated["claimed_count"] == 0
    assert counts == {"dispatched": 1}
    assert rows[0]["downstream_ref_type"] == "ai_audience_dependency_refresh"
    assert audience_repo.pokes == [("questionnaire_submission", "questionnaire:13")]
    assert audience_repo.rewinds[0][2] == datetime.fromisoformat(
        questionnaire_repo.submission["submitted_at"]
    )


def test_continuation_expires_after_seven_day_deadline_without_dispatch() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    questionnaire_repo.submission["submitted_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=FakeAudienceRepository(),
    )
    service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-old-submission",
        identity_ready=False,
    )

    expired_count = continuation_repo.expire_due()
    wake = service.wake_by_identity("unionid-continuation-001")
    rows, counts = continuation_repo.list_operations(13)

    assert expired_count == 1
    assert wake["claimed_count"] == 0
    assert counts == {"expired": 1}
    assert rows[0]["last_error_code"] == "continuation_expired"


def test_agent_dispatch_fails_closed_when_questionnaire_dependency_was_removed() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    questionnaire_repo.submission.update(
        {
            "external_userid": "wm_external_continuation_001",
            "follow_user_userid": "staff_continuation_001",
        }
    )
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=FakeAudienceRepository(updated_count=0),
    )
    registered = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-questionnaire-ready",
        identity_ready=True,
    )

    result = service.dispatch_registered_job(registered["job"])
    rows, counts = continuation_repo.list_operations(13)

    assert result == {
        "ok": False,
        "reason": "agent_dependency_not_configured",
        "job_id": registered["job"]["id"],
    }
    assert counts == {"failed_terminal": 1}
    assert rows[0]["last_error_code"] == "agent_dependency_not_configured"


def test_immediate_duplicate_agent_event_does_not_refresh_dependency_twice() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    questionnaire_repo.submission.update(
        {
            "external_userid": "wm_external_continuation_001",
            "follow_user_userid": "staff_continuation_001",
        }
    )
    audience_repo = FakeAudienceRepository()
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=audience_repo,
    )

    first_job = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-immediate-first",
        identity_ready=True,
    )["job"]
    first_dispatch = service.dispatch_registered_job(first_job)
    duplicate_job = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-immediate-duplicate",
        identity_ready=True,
    )["job"]
    duplicate_dispatch = service.dispatch_registered_job(duplicate_job)

    assert first_dispatch["dispatched"] is True
    assert duplicate_dispatch["already_dispatched"] is True
    assert audience_repo.pokes == [("questionnaire_submission", "questionnaire:13")]
    assert len(audience_repo.rewinds) == 1


def test_agent_dispatch_retries_when_dependency_package_is_currently_leased() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    questionnaire_repo.submission.update(
        {
            "external_userid": "wm_external_continuation_001",
            "follow_user_userid": "staff_continuation_001",
        }
    )
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=FakeAudienceRepository(updated_count=1, scheduled_count=0),
    )
    job = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-package-leased",
        identity_ready=True,
    )["job"]

    result = service.dispatch_registered_job(job)
    rows, counts = continuation_repo.list_operations(13)

    assert result["retryable"] is True
    assert result["reason"] == "agent_dependency_refresh_busy"
    assert counts == {"waiting_identity": 1}
    assert rows[0]["last_error_code"] == "agent_dependency_refresh_busy"


def test_reconciliation_blocks_ambiguous_owner_without_callback_owner_hint() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    questionnaire_repo.submission.update(
        {
            "external_userid": "wm-external-owner-conflict",
            "follow_user_userid": "",
        }
    )
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=FakeAudienceRepository(),
        owner_candidates_query=FakeOwnerCandidatesQuery({"owner-a", "owner-b"}),
    )
    registered = service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-owner-conflict",
        identity_ready=False,
    )

    result = service.dispatch_registered_job(registered["job"])
    rows, counts = continuation_repo.list_operations(13)

    assert result["reason"] == "owner_ambiguous"
    assert counts == {"blocked_conflict": 1}
    assert rows[0]["last_error_code"] == "owner_ambiguous"


def test_identity_ready_callback_uses_its_valid_follow_owner_when_multiple_exist() -> None:
    continuation_repo = InMemoryQuestionnaireContinuationRepository()
    questionnaire_repo = FakeQuestionnaireRepository()
    service = QuestionnaireContinuationService(
        repository=continuation_repo,
        questionnaire_repository=questionnaire_repo,
        audience_repository=FakeAudienceRepository(),
        owner_candidates_query=FakeOwnerCandidatesQuery({"owner-a", "owner-b"}),
    )
    service.register(
        submission=questionnaire_repo.submission,
        action_type=ACTION_AGENT_FOLLOWUP,
        source_event_id="iev-owner-ready",
        identity_ready=False,
    )

    result = service.wake_by_identity(
        questionnaire_repo.submission["unionid"],
        source_event_id="iev-owner-ready-callback",
        identity_hint={
            "unionid": questionnaire_repo.submission["unionid"],
            "external_userid": "wm-owner-ready",
            "follow_user_userid": "owner-b",
        },
    )

    assert result["dispatched_count"] == 1


def test_continuation_migration_contract_is_additive_and_unionid_keyed() -> None:
    source = open(
        "migrations/versions/0124_questionnaire_continuation_jobs.py",
        encoding="utf-8",
    ).read()

    assert "CREATE TABLE IF NOT EXISTS questionnaire_continuation_job" in source
    assert "UNIQUE (submission_id, action_type)" in source
    assert "(unionid, status, expires_at, id)" in source
    assert "mobile" not in source
    assert "openid" not in source
    assert "answers" not in source
    assert "unionid_verification_source" in source
    assert "unionid_verified_at" in source


def test_backfill_query_requires_recent_server_verified_unionid_and_no_mobile_match() -> None:
    source = open(
        "aicrm_next/questionnaire/continuation_repo.py",
        encoding="utf-8",
    ).read()
    query = source.split("WITH eligible AS (", 1)[1].split('"""', 1)[0]

    assert "INTERVAL '7 days'" in query
    assert "unionid_verification_source = 'wechat_oauth_signed_session'" in query
    assert "unionid_verified_at IS NOT NULL" in query
    assert "effect.status = 'succeeded'" in query
    assert "item.status IN ('generated', 'callback_succeeded')" in query
    assert "mobile" not in query.lower()
    assert "openid" not in query.lower()


def test_unionid_cutover_preflight_requires_recent_real_oauth_proof_without_mutation() -> None:
    source = open(
        "scripts/ops/check_questionnaire_unionid_cutover.py",
        encoding="utf-8",
    ).read()

    assert "WECHAT_MP_OAUTH_SCOPE" in source
    assert "snsapi_userinfo" in source
    assert "customer.wecom_identity_ready" in source
    assert '"internal_events_enabled": _text(os.getenv("AICRM_INTERNAL_EVENTS_ENABLED"))' in source
    assert "'/api/h5/wechat/oauth/callback'" in source
    assert '"ready_to_enable_identity_gate": ready' in source
    assert '"real_oauth_identity_proof": proof' in source
    assert "ready_to_enable_unionid_gate" not in source
    assert "real_oauth_unionid_proof" not in source
    assert '"internal_events_enabled"' not in source.split("checks = {", 1)[1].split("current_cutover_state", 1)[0]
    assert '"database_mutation_performed": False' in source
    assert "INSERT INTO" not in source.upper()
    assert "UPDATE " not in source.upper()
    assert "DELETE FROM" not in source.upper()


def test_unionid_cutover_preflight_control_fields_survive_output_redaction() -> None:
    output = redact_sensitive_data(
        {
            "ready_to_enable_identity_gate": True,
            "real_oauth_identity_proof": {
                "available": True,
                "unionid_hash": "0123456789abcdef",
                "openid_hash": "fedcba9876543210",
            },
        }
    )

    assert output["ready_to_enable_identity_gate"] is True
    assert output["real_oauth_identity_proof"] == {
        "available": True,
        "unionid_hash": "0123456789abcdef",
        "openid_hash": "fedcba9876543210",
    }
