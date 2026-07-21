from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from aicrm_next.identity_contact.application import (
    ListExternalContactOwnerCandidatesQuery,
    ResolvePersonIdentityQuery,
)
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.internal_events.models import (
    InternalEvent,
    InternalEventConsumerResult,
    InternalEventConsumerRun,
)
from aicrm_next.shared.runtime_settings import runtime_bool

from .continuation_repo import (
    QuestionnaireContinuationRepository,
    build_questionnaire_continuation_repository,
)
from .repo import QuestionnaireRepository, build_questionnaire_repository


ACTION_WECOM_TAG = "wecom_tag"
ACTION_AGENT_FOLLOWUP = "questionnaire_agent_followup"
CONTINUATION_TTL_DAYS = 7


class AudienceDependencyPokePort(Protocol):
    def count_dependencies(self, *, source_type: str, source_key: str = "") -> int: ...

    def poke_dependencies(self, *, source_type: str, source_key: str = "") -> int: ...

    def poke_dependencies_since(
        self,
        *,
        source_type: str,
        source_key: str = "",
        since_at: datetime,
    ) -> int: ...


_AUDIENCE_REPOSITORY_FACTORY: Callable[[], AudienceDependencyPokePort] | None = None


def configure_questionnaire_continuation_audience_repository(
    factory: Callable[[], AudienceDependencyPokePort],
) -> None:
    global _AUDIENCE_REPOSITORY_FACTORY
    _AUDIENCE_REPOSITORY_FACTORY = factory


def _build_audience_repository() -> AudienceDependencyPokePort:
    if _AUDIENCE_REPOSITORY_FACTORY is None:
        raise RuntimeError("questionnaire continuation audience repository is not composed")
    return _AUDIENCE_REPOSITORY_FACTORY()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        raw = _text(value)
        try:
            result = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else datetime.now(timezone.utc)
        except ValueError:
            result = datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def questionnaire_continuation_enabled() -> bool:
    return runtime_bool("AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED", default=False)


class QuestionnaireContinuationService:
    def __init__(
        self,
        *,
        repository: QuestionnaireContinuationRepository | None = None,
        questionnaire_repository: QuestionnaireRepository | None = None,
        audience_repository=None,
        identity_query: ResolvePersonIdentityQuery | None = None,
        owner_candidates_query: ListExternalContactOwnerCandidatesQuery | None = None,
    ) -> None:
        self.repository = repository or build_questionnaire_continuation_repository()
        self.questionnaire_repository = questionnaire_repository or build_questionnaire_repository()
        self.audience_repository = audience_repository or _build_audience_repository()
        self.identity_query = identity_query or ResolvePersonIdentityQuery()
        self.owner_candidates_query = owner_candidates_query or ListExternalContactOwnerCandidatesQuery()

    def register(
        self,
        *,
        submission: dict[str, Any],
        action_type: str,
        source_event_id: str,
        identity_ready: bool,
    ) -> dict[str, Any]:
        unionid = _text(submission.get("unionid"))
        if not unionid:
            return {"ok": False, "reason": "missing_unionid"}
        submitted_at = _utc_datetime(submission.get("submitted_at") or submission.get("created_at"))
        raw_submission_id = submission.get("id") or submission.get("submission_id") or 0
        submission_id: int | str = int(raw_submission_id) if _text(raw_submission_id).isdigit() else _text(raw_submission_id)
        return {
            "ok": True,
            "job": self.repository.register_job(
                {
                    "submission_id": submission_id,
                    "questionnaire_id": int(submission.get("questionnaire_id") or 0),
                    "unionid": unionid,
                    "action_type": action_type,
                    "status": "waiting_identity",
                    "expires_at": submitted_at + timedelta(days=CONTINUATION_TTL_DAYS),
                    "identity_ready_at": datetime.now(timezone.utc) if identity_ready else None,
                    "source_event_id": _text(source_event_id),
                }
            ),
        }

    def agent_dependency_count(self, questionnaire_id: int) -> int:
        return int(
            self.audience_repository.count_dependencies(
                source_type="questionnaire_submission",
                source_key=f"questionnaire:{int(questionnaire_id)}",
            )
            or 0
        )

    def dispatch_agent_dependency_refresh(self, questionnaire_id: int, *, submitted_at: datetime) -> int:
        return int(
            self.audience_repository.poke_dependencies_since(
                source_type="questionnaire_submission",
                source_key=f"questionnaire:{int(questionnaire_id)}",
                since_at=submitted_at,
            )
            or 0
        )

    def dispatch_registered_job(
        self,
        job: dict[str, Any],
        *,
        source_event_id: str = "",
        identity_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = int(job.get("id") or 0)
        status = _text(job.get("status"))
        if status == "dispatched":
            return {
                "ok": True,
                "dispatched": True,
                "already_dispatched": True,
                "job_id": job_id,
                "action_type": _text(job.get("action_type")),
                "downstream_ref_type": _text(job.get("downstream_ref_type")),
                "downstream_ref_id": _text(job.get("downstream_ref_id")),
                "real_external_call_executed": False,
            }
        if status in {"expired", "blocked_conflict", "failed_terminal"}:
            return {"ok": False, "terminal": True, "reason": status, "job_id": job_id}
        if _utc_datetime(job.get("expires_at")) <= datetime.now(timezone.utc):
            self.repository.mark_terminal(
                job_id,
                status="expired",
                error_code="continuation_expired",
            )
            return {"ok": False, "terminal": True, "reason": "continuation_expired", "job_id": job_id}
        claimed = self.repository.claim_job(job_id)
        if not claimed:
            return {
                "ok": True,
                "dispatched": False,
                "pending_dispatch": True,
                "reason": "continuation_already_claimed",
                "job_id": job_id,
                "real_external_call_executed": False,
            }
        return self.dispatch_claimed_job(
            claimed,
            source_event_id=source_event_id,
            identity_hint=identity_hint,
        )

    def dispatch_claimed_job(
        self,
        job: dict[str, Any],
        *,
        source_event_id: str = "",
        identity_hint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = int(job.get("id") or 0)
        expires_at = _utc_datetime(job.get("expires_at"))
        if expires_at <= datetime.now(timezone.utc):
            self.repository.mark_terminal(
                job_id,
                status="expired",
                error_code="continuation_expired",
            )
            return {"ok": False, "terminal": True, "reason": "continuation_expired", "job_id": job_id}
        submission_id = _text(job.get("submission_id"))
        submission = self.questionnaire_repository.get_submission_by_record_id(submission_id)
        if not submission:
            self.repository.mark_waiting(job_id, error_code="submission_not_found", error_message="submission unavailable")
            return {"ok": False, "retryable": True, "reason": "submission_not_found", "job_id": job_id}
        questionnaire = self.questionnaire_repository.get_questionnaire(int(submission.get("questionnaire_id") or 0))
        if not questionnaire:
            self.repository.mark_terminal(
                job_id,
                status="failed_terminal",
                error_code="questionnaire_not_found",
            )
            return {"ok": False, "reason": "questionnaire_not_found", "job_id": job_id}
        job_unionid = _text(job.get("unionid"))
        if _text(submission.get("unionid")) != job_unionid:
            self.repository.mark_terminal(
                job_id,
                status="blocked_conflict",
                error_code="unionid_mismatch",
            )
            return {"ok": False, "reason": "unionid_mismatch", "job_id": job_id}

        effective_submission = dict(submission)
        try:
            resolved = self.identity_query.execute_result(ResolvePersonIdentityRequest(unionid=job_unionid))
        except Exception as exc:
            resolved = None
            identity_resolution_error = exc.__class__.__name__
        else:
            identity_resolution_error = ""
        if resolved is not None and _text(resolved.status) == "conflict":
            self.repository.mark_terminal(
                job_id,
                status="blocked_conflict",
                error_code=_text(resolved.reason) or "identity_conflict",
            )
            return {"ok": False, "reason": "identity_conflict", "job_id": job_id}
        canonical_identity = getattr(resolved, "identity", None) if resolved is not None else None
        if canonical_identity is not None:
            canonical_payload = (
                canonical_identity.model_dump()
                if hasattr(canonical_identity, "model_dump")
                else dict(canonical_identity)
            )
            if _text(canonical_payload.get("unionid")) != job_unionid:
                self.repository.mark_terminal(
                    job_id,
                    status="blocked_conflict",
                    error_code="canonical_unionid_mismatch",
                )
                return {"ok": False, "reason": "canonical_unionid_mismatch", "job_id": job_id}
            effective_submission.update(
                {
                    "external_userid": _text(canonical_payload.get("external_userid")),
                    "follow_user_userid": _text(
                        canonical_payload.get("follow_user_userid") or canonical_payload.get("owner_userid")
                    ),
                }
            )
        elif identity_hint and _text(identity_hint.get("unionid")) == job_unionid:
            # This hint is produced only by the server-side identity-ready event
            # immediately after canonical synchronization. Reconciliation never
            # relies on it and always resolves the canonical identity again.
            effective_submission.update(
                {
                    "external_userid": _text(identity_hint.get("external_userid")),
                    "follow_user_userid": _text(identity_hint.get("follow_user_userid")),
                }
            )
        effective_external = _text(effective_submission.get("external_userid"))
        if effective_external:
            try:
                owner_candidates = set(
                    self.owner_candidates_query.execute(external_userid=effective_external)
                )
            except Exception as exc:
                owner_candidates = set()
                identity_resolution_error = identity_resolution_error or exc.__class__.__name__
            if len(owner_candidates) > 1:
                hinted_owner = _text((identity_hint or {}).get("follow_user_userid"))
                if hinted_owner and hinted_owner in owner_candidates:
                    effective_submission["follow_user_userid"] = hinted_owner
                else:
                    self.repository.mark_terminal(
                        job_id,
                        status="blocked_conflict",
                        error_code="owner_ambiguous",
                    )
                    return {"ok": False, "reason": "owner_ambiguous", "job_id": job_id}
            elif len(owner_candidates) == 1:
                effective_submission["follow_user_userid"] = next(iter(owner_candidates))
        missing = [
            field
            for field in ("unionid", "external_userid", "follow_user_userid")
            if not _text(effective_submission.get(field))
        ]
        if missing:
            self.repository.mark_waiting(
                job_id,
                error_code="identity_resolution_failed" if identity_resolution_error else "identity_still_incomplete",
                error_message=identity_resolution_error or ",".join(missing),
            )
            return {
                "ok": False,
                "retryable": True,
                "reason": "identity_still_incomplete",
                "missing_identity_fields": missing,
                "job_id": job_id,
            }

        action_type = _text(job.get("action_type"))
        if action_type == ACTION_WECOM_TAG:
            from .event_consumers import plan_questionnaire_tag_action

            result = plan_questionnaire_tag_action(
                questionnaire=questionnaire,
                submission=effective_submission,
                source_event_id=_text(source_event_id) or _text(job.get("source_event_id")),
                source_command_id=f"questionnaire-continuation:{job_id}",
                context=CommandContext(
                    actor_id="questionnaire_continuation_worker",
                    actor_type="system",
                    request_id=f"questionnaire-continuation:{job_id}",
                    trace_id=f"questionnaire-continuation:{job_id}",
                    source_route="questionnaire.continuation.dispatch_tag",
                ),
            )
            if not result.get("ok"):
                self.repository.mark_waiting(
                    job_id,
                    error_code=_text(result.get("reason")) or "tag_effect_plan_failed",
                    error_message=_text(result.get("error")),
                )
                return {**result, "job_id": job_id, "retryable": True}
            downstream_id = _text(result.get("external_effect_job_id"))
            self.repository.mark_dispatched(
                job_id,
                downstream_ref_type="external_effect_job",
                downstream_ref_id=downstream_id,
            )
            return {**result, "dispatched": True, "job_id": job_id, "action_type": action_type}

        if action_type == ACTION_AGENT_FOLLOWUP:
            configured_count = self.agent_dependency_count(int(questionnaire.get("id") or 0))
            if configured_count <= 0:
                self.repository.mark_terminal(
                    job_id,
                    status="failed_terminal",
                    error_code="agent_dependency_not_configured",
                )
                return {"ok": False, "reason": "agent_dependency_not_configured", "job_id": job_id}
            updated_count = self.dispatch_agent_dependency_refresh(
                int(questionnaire.get("id") or 0),
                submitted_at=_utc_datetime(submission.get("submitted_at") or submission.get("created_at")),
            )
            if updated_count < configured_count:
                self.repository.mark_waiting(
                    job_id,
                    error_code="agent_dependency_refresh_busy",
                    error_message=f"scheduled={updated_count},configured={configured_count}",
                )
                return {
                    "ok": False,
                    "retryable": True,
                    "reason": "agent_dependency_refresh_busy",
                    "job_id": job_id,
                }
            self.repository.mark_dispatched(
                job_id,
                downstream_ref_type="ai_audience_dependency_refresh",
                downstream_ref_id=f"questionnaire:{int(questionnaire.get('id') or 0)}",
            )
            return {
                "ok": True,
                "dispatched": True,
                "job_id": job_id,
                "action_type": action_type,
                "updated_package_count": updated_count,
                "real_external_call_executed": False,
            }

        self.repository.mark_terminal(
            job_id,
            status="failed_terminal",
            error_code="continuation_action_unsupported",
        )
        return {"ok": False, "reason": "continuation_action_unsupported", "job_id": job_id}

    def wake_by_identity(
        self,
        unionid: str,
        *,
        source_event_id: str = "",
        identity_hint: dict[str, Any] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        normalized_unionid = _text(unionid)
        if not normalized_unionid:
            return {"ok": False, "reason": "unionid_missing", "processed_count": 0}
        jobs = self.repository.claim_for_unionid(normalized_unionid, limit=limit)
        results = [
            self.dispatch_claimed_job(
                job,
                source_event_id=source_event_id,
                identity_hint=identity_hint,
            )
            for job in jobs
        ]
        return {
            "ok": all(item.get("ok") or item.get("retryable") for item in results),
            "unionid_present": True,
            "claimed_count": len(jobs),
            "processed_count": len(results),
            "dispatched_count": len([item for item in results if item.get("dispatched")]),
            "results": results,
            "real_external_call_executed": False,
        }

    def reconcile(self, *, limit: int = 50) -> dict[str, Any]:
        expired_count = self.repository.expire_due()
        jobs = self.repository.claim_reconcilable(limit=limit)
        results = [self.dispatch_claimed_job(job, source_event_id="questionnaire-continuation-reconcile") for job in jobs]
        return {
            "ok": all(item.get("ok") or item.get("retryable") for item in results),
            "expired_count": expired_count,
            "claimed_count": len(jobs),
            "dispatched_count": len([item for item in results if item.get("dispatched")]),
            "results": results,
            "real_external_call_executed": False,
        }

    def backfill_recent_verified_submissions(
        self,
        *,
        apply: bool = False,
        limit: int = 200,
    ) -> dict[str, Any]:
        candidates = self.repository.list_backfill_candidates(limit=limit)
        planned_actions: list[dict[str, Any]] = []
        for candidate in candidates:
            submission = self.questionnaire_repository.get_submission_by_record_id(
                _text(candidate.get("submission_id"))
            )
            if not submission:
                planned_actions.append(
                    {
                        "submission_id": _text(candidate.get("submission_id")),
                        "status": "skipped",
                        "reason": "submission_not_found",
                    }
                )
                continue
            identity_ready = all(
                _text(submission.get(field))
                for field in ("unionid", "external_userid", "follow_user_userid")
            )
            action_types: list[str] = []
            if bool(candidate.get("tag_action_required")):
                action_types.append(ACTION_WECOM_TAG)
            if bool(candidate.get("agent_action_required")):
                action_types.append(ACTION_AGENT_FOLLOWUP)
            for action_type in action_types:
                action = {
                    "submission_id": _text(candidate.get("submission_id")),
                    "questionnaire_id": int(candidate.get("questionnaire_id") or 0),
                    "action_type": action_type,
                    "identity_ready": identity_ready,
                    "status": "planned" if not apply else "registered",
                }
                if apply:
                    registered = self.register(
                        submission=submission,
                        action_type=action_type,
                        source_event_id="questionnaire-continuation-backfill",
                        identity_ready=identity_ready,
                    )
                    job = dict(registered.get("job") or {})
                    action["continuation_job_id"] = int(job.get("id") or 0)
                    action["status"] = _text(job.get("status"))
                    if identity_ready and job:
                        dispatch = self.dispatch_registered_job(
                            job,
                            source_event_id="questionnaire-continuation-backfill",
                        )
                        action["status"] = "dispatched" if dispatch.get("ok") else _text(
                            dispatch.get("reason") or "dispatch_pending"
                        )
                planned_actions.append(action)
        return {
            "ok": True,
            "mode": "apply" if apply else "dry_run",
            "candidate_submission_count": len(candidates),
            "action_count": len(planned_actions),
            "actions": planned_actions,
            "database_mutation_performed": bool(apply and planned_actions),
            "mobile_identity_fallback_used": False,
            "real_external_call_executed": False,
        }


def questionnaire_identity_continuation_consumer(
    event: InternalEvent,
    run: InternalEventConsumerRun,
) -> InternalEventConsumerResult:
    if not questionnaire_continuation_enabled():
        return InternalEventConsumerResult(
            status="skipped",
            request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
            response_summary={
                "skipped": True,
                "reason": "questionnaire_continuation_disabled",
                "real_external_call_executed": False,
            },
            result_summary={"reason": "questionnaire_continuation_disabled"},
        )
    payload = dict(event.payload_json or {})
    identity = dict(payload.get("identity") or {}) if isinstance(payload.get("identity"), dict) else {}
    unionid = _text(identity.get("unionid") or event.aggregate_id)
    if not unionid:
        return InternalEventConsumerResult(
            status="failed_terminal",
            request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
            response_summary={"woken": False, "reason": "unionid_missing"},
            error_code="unionid_missing",
            error_message="identity-ready event requires unionid",
        )
    try:
        result = QuestionnaireContinuationService().wake_by_identity(
            unionid,
            source_event_id=event.event_id,
            identity_hint=identity,
        )
    except Exception as exc:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
            response_summary={"woken": False, "real_external_call_executed": False},
            error_code="questionnaire_continuation_wake_failed",
            error_message=str(exc)[:500],
            retry_after_seconds=300,
        )
    return InternalEventConsumerResult(
        status="succeeded" if result.get("ok") else "failed_retryable",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={
            "woken": True,
            "claimed_count": int(result.get("claimed_count") or 0),
            "dispatched_count": int(result.get("dispatched_count") or 0),
            "real_external_call_executed": False,
        },
        result_summary={
            "claimed_count": int(result.get("claimed_count") or 0),
            "dispatched_count": int(result.get("dispatched_count") or 0),
        },
        error_code="" if result.get("ok") else "questionnaire_continuation_wake_incomplete",
        error_message="" if result.get("ok") else "one or more continuation jobs remain pending",
        retry_after_seconds=None if result.get("ok") else 300,
    )

__all__ = [
    "ACTION_AGENT_FOLLOWUP",
    "ACTION_WECOM_TAG",
    "CONTINUATION_TTL_DAYS",
    "QuestionnaireContinuationService",
    "configure_questionnaire_continuation_audience_repository",
    "questionnaire_continuation_enabled",
    "questionnaire_identity_continuation_consumer",
]
