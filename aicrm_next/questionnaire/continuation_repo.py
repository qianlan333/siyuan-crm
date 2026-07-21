from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any

from sqlalchemy import text

from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.runtime import production_data_ready


def _text(value: Any) -> str:
    return str(value or "").strip()


def _public_row(row: Any) -> dict[str, Any]:
    payload = dict(row or {})
    for key, value in list(payload.items()):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            payload[key] = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return payload


class QuestionnaireContinuationRepository:
    def register_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def mark_dispatched(self, job_id: int, *, downstream_ref_type: str, downstream_ref_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def mark_waiting(self, job_id: int, *, error_code: str = "", error_message: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def mark_terminal(self, job_id: int, *, status: str, error_code: str, error_message: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def claim_for_unionid(self, unionid: str, *, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    def claim_job(self, job_id: int) -> dict[str, Any]:
        raise NotImplementedError

    def claim_reconcilable(self, *, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    def expire_due(self) -> int:
        raise NotImplementedError

    def list_operations(self, questionnaire_id: int, *, limit: int = 100) -> tuple[list[dict[str, Any]], dict[str, int]]:
        raise NotImplementedError

    def list_backfill_candidates(self, *, limit: int = 200) -> list[dict[str, Any]]:
        raise NotImplementedError


class InMemoryQuestionnaireContinuationRepository(QuestionnaireContinuationRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", RLock()):
            self._rows: list[dict[str, Any]] = []
            self._next_id = 1

    def register_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            submission_id = _text(payload.get("submission_id"))
            action_type = _text(payload.get("action_type"))
            for row in self._rows:
                if _text(row["submission_id"]) == submission_id and row["action_type"] == action_type:
                    if row["status"] == "waiting_identity" and payload.get("identity_ready_at"):
                        row["identity_ready_at"] = payload.get("identity_ready_at")
                    row["updated_at"] = datetime.now(timezone.utc)
                    return _public_row(row)
            now = datetime.now(timezone.utc)
            row = {
                "id": self._next_id,
                "tenant_id": "aicrm",
                "attempt_count": 0,
                "max_attempts": 20,
                "next_attempt_at": None,
                "identity_ready_at": None,
                "dispatched_at": None,
                "downstream_ref_type": "",
                "downstream_ref_id": "",
                "last_error_code": "",
                "last_error_message": "",
                "source_event_id": "",
                "created_at": now,
                "updated_at": now,
                **payload,
            }
            self._next_id += 1
            self._rows.append(row)
            return _public_row(row)

    def _update(self, job_id: int, **changes: Any) -> dict[str, Any]:
        with self._lock:
            for row in self._rows:
                if int(row["id"]) == int(job_id):
                    row.update(changes)
                    row["updated_at"] = datetime.now(timezone.utc)
                    return _public_row(row)
        return {}

    def mark_dispatched(self, job_id: int, *, downstream_ref_type: str, downstream_ref_id: str) -> dict[str, Any]:
        return self._update(
            job_id,
            status="dispatched",
            dispatched_at=datetime.now(timezone.utc),
            downstream_ref_type=_text(downstream_ref_type),
            downstream_ref_id=_text(downstream_ref_id),
            last_error_code="",
            last_error_message="",
        )

    def mark_waiting(self, job_id: int, *, error_code: str = "", error_message: str = "") -> dict[str, Any]:
        return self._update(
            job_id,
            status="waiting_identity",
            last_error_code=_text(error_code),
            last_error_message=_text(error_message)[:500],
        )

    def mark_terminal(self, job_id: int, *, status: str, error_code: str, error_message: str = "") -> dict[str, Any]:
        return self._update(
            job_id,
            status=status,
            last_error_code=_text(error_code),
            last_error_message=_text(error_message)[:500],
        )

    def _claim(self, rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        claimed: list[dict[str, Any]] = []
        for row in rows:
            expires_at = row.get("expires_at")
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if isinstance(expires_at, datetime) and expires_at <= now:
                row["status"] = "expired"
                continue
            if row.get("status") != "waiting_identity":
                continue
            row["status"] = "dispatching"
            row["identity_ready_at"] = now
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
            claimed.append(_public_row(row))
            if len(claimed) >= limit:
                break
        return claimed

    def claim_for_unionid(self, unionid: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return self._claim([row for row in self._rows if row.get("unionid") == _text(unionid)], limit=limit)

    def claim_job(self, job_id: int) -> dict[str, Any]:
        with self._lock:
            claimed = self._claim(
                [row for row in self._rows if int(row.get("id") or 0) == int(job_id)],
                limit=1,
            )
        return dict(claimed[0]) if claimed else {}

    def claim_reconcilable(self, *, limit: int = 50) -> list[dict[str, Any]]:
        # Fixture tests call claim_for_unionid with an explicit ready identity.
        return []

    def expire_due(self) -> int:
        now = datetime.now(timezone.utc)
        count = 0
        with self._lock:
            for row in self._rows:
                expires_at = row.get("expires_at")
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if row.get("status") == "waiting_identity" and isinstance(expires_at, datetime) and expires_at <= now:
                    row["status"] = "expired"
                    row["last_error_code"] = "continuation_expired"
                    count += 1
        return count

    def list_operations(self, questionnaire_id: int, *, limit: int = 100) -> tuple[list[dict[str, Any]], dict[str, int]]:
        rows = [row for row in self._rows if int(row.get("questionnaire_id") or 0) == int(questionnaire_id)]
        rows = sorted(rows, key=lambda item: int(item["id"]), reverse=True)[:limit]
        counts: dict[str, int] = {}
        for row in self._rows:
            if int(row.get("questionnaire_id") or 0) == int(questionnaire_id):
                counts[row["status"]] = counts.get(row["status"], 0) + 1
        return [_public_row(row) for row in rows], counts

    def list_backfill_candidates(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return []


class PostgresQuestionnaireContinuationRepository(QuestionnaireContinuationRepository):
    def _write_one(self, sql: str, params: dict[str, Any]) -> dict[str, Any]:
        with get_session_factory()() as session:
            row = session.execute(text(sql), params).mappings().first()
            session.commit()
            return _public_row(row)

    def register_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._write_one(
            """
            INSERT INTO questionnaire_continuation_job (
                submission_id, questionnaire_id, unionid, action_type, status,
                expires_at, identity_ready_at, source_event_id, created_at, updated_at
            ) VALUES (
                :submission_id, :questionnaire_id, :unionid, :action_type, :status,
                :expires_at, :identity_ready_at, :source_event_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (submission_id, action_type) DO UPDATE SET
                unionid = EXCLUDED.unionid,
                identity_ready_at = COALESCE(questionnaire_continuation_job.identity_ready_at, EXCLUDED.identity_ready_at),
                source_event_id = COALESCE(NULLIF(questionnaire_continuation_job.source_event_id, ''), EXCLUDED.source_event_id),
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            payload,
        )

    def mark_dispatched(self, job_id: int, *, downstream_ref_type: str, downstream_ref_id: str) -> dict[str, Any]:
        return self._write_one(
            """
            UPDATE questionnaire_continuation_job
            SET status = 'dispatched', dispatched_at = CURRENT_TIMESTAMP,
                downstream_ref_type = :downstream_ref_type,
                downstream_ref_id = :downstream_ref_id,
                last_error_code = '', last_error_message = '', updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id
            RETURNING *
            """,
            {
                "job_id": int(job_id),
                "downstream_ref_type": _text(downstream_ref_type),
                "downstream_ref_id": _text(downstream_ref_id),
            },
        )

    def mark_waiting(self, job_id: int, *, error_code: str = "", error_message: str = "") -> dict[str, Any]:
        return self._write_one(
            """
            UPDATE questionnaire_continuation_job
            SET status = 'waiting_identity',
                next_attempt_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes',
                last_error_code = :error_code, last_error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id
            RETURNING *
            """,
            {"job_id": int(job_id), "error_code": _text(error_code), "error_message": _text(error_message)[:500]},
        )

    def mark_terminal(self, job_id: int, *, status: str, error_code: str, error_message: str = "") -> dict[str, Any]:
        return self._write_one(
            """
            UPDATE questionnaire_continuation_job
            SET status = :status, last_error_code = :error_code,
                last_error_message = :error_message, updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id
            RETURNING *
            """,
            {
                "job_id": int(job_id),
                "status": _text(status),
                "error_code": _text(error_code),
                "error_message": _text(error_message)[:500],
            },
        )

    def _claim(self, where_sql: str, params: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        with get_session_factory()() as session:
            rows = session.execute(
                text(
                    f"""
                    WITH candidates AS (
                        SELECT job.id
                        FROM questionnaire_continuation_job job
                        {where_sql}
                        ORDER BY job.created_at ASC, job.id ASC
                        FOR UPDATE OF job SKIP LOCKED
                        LIMIT :limit
                    )
                    UPDATE questionnaire_continuation_job job
                    SET status = 'dispatching', identity_ready_at = COALESCE(identity_ready_at, CURRENT_TIMESTAMP),
                        attempt_count = attempt_count + 1, next_attempt_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    FROM candidates
                    WHERE job.id = candidates.id
                    RETURNING job.*
                    """
                ),
                {**params, "limit": max(1, min(int(limit or 50), 200))},
            ).mappings().all()
            session.commit()
            return [_public_row(row) for row in rows]

    def claim_for_unionid(self, unionid: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._claim(
            """
            WHERE job.unionid = :unionid
              AND (
                    job.status = 'waiting_identity'
                    OR (job.status = 'dispatching' AND job.updated_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
              )
              AND job.expires_at > CURRENT_TIMESTAMP
              AND job.attempt_count < job.max_attempts
            """,
            {"unionid": _text(unionid)},
            limit=limit,
        )

    def claim_job(self, job_id: int) -> dict[str, Any]:
        rows = self._claim(
            """
            WHERE job.id = :job_id
              AND job.status = 'waiting_identity'
              AND job.expires_at > CURRENT_TIMESTAMP
              AND job.attempt_count < job.max_attempts
              AND (job.next_attempt_at IS NULL OR job.next_attempt_at <= CURRENT_TIMESTAMP)
            """,
            {"job_id": int(job_id)},
            limit=1,
        )
        return dict(rows[0]) if rows else {}

    def claim_reconcilable(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._claim(
            """
            JOIN crm_user_identity identity ON identity.unionid = job.unionid
            WHERE (
                    job.status = 'waiting_identity'
                    OR (job.status = 'dispatching' AND job.updated_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                  )
              AND job.expires_at > CURRENT_TIMESTAMP
              AND job.attempt_count < job.max_attempts
              AND COALESCE(identity.primary_external_userid, '') <> ''
              AND COALESCE(identity.primary_owner_userid, '') <> ''
              AND (job.next_attempt_at IS NULL OR job.next_attempt_at <= CURRENT_TIMESTAMP)
            """,
            {},
            limit=limit,
        )

    def expire_due(self) -> int:
        with get_session_factory()() as session:
            session.execute(
                text(
                    """
                    UPDATE questionnaire_continuation_job
                    SET status = 'failed_terminal', last_error_code = 'continuation_attempts_exhausted',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status IN ('waiting_identity', 'dispatching')
                      AND attempt_count >= max_attempts
                    """
                )
            )
            result = session.execute(
                text(
                    """
                    UPDATE questionnaire_continuation_job
                    SET status = 'expired', last_error_code = 'continuation_expired',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status IN ('waiting_identity', 'dispatching')
                      AND expires_at <= CURRENT_TIMESTAMP
                    """
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def list_operations(self, questionnaire_id: int, *, limit: int = 100) -> tuple[list[dict[str, Any]], dict[str, int]]:
        with get_session_factory()() as session:
            rows = session.execute(
                text(
                    """
                    SELECT
                        job.*,
                        submission.submitted_at,
                        CASE
                            WHEN job.action_type = 'wecom_tag' THEN COALESCE(effect.status, '')
                            ELSE COALESCE(agent_item.status, '')
                        END AS downstream_status,
                        CASE
                            WHEN job.action_type = 'wecom_tag' THEN COALESCE(effect.id::text, '')
                            ELSE COALESCE(agent_item.batch_id, '')
                        END AS downstream_execution_ref
                    FROM questionnaire_continuation_job job
                    JOIN questionnaire_submissions submission ON submission.id = job.submission_id
                    LEFT JOIN external_effect_job effect
                      ON job.action_type = 'wecom_tag'
                     AND job.downstream_ref_type = 'external_effect_job'
                     AND effect.id::text = job.downstream_ref_id
                    LEFT JOIN LATERAL (
                        SELECT item.status, item.batch_id
                        FROM automation_agent_webhook_item item
                        JOIN automation_agent_webhook_batch batch ON batch.batch_id = item.batch_id
                        JOIN ai_audience_package package ON package.package_key = batch.bound_package_key
                        JOIN ai_audience_package_dependency dependency ON dependency.package_id = package.id
                        WHERE job.action_type = 'questionnaire_agent_followup'
                          AND item.unionid = job.unionid
                          AND item.created_at >= submission.submitted_at
                          AND dependency.source_type = 'questionnaire_submission'
                          AND dependency.source_key = 'questionnaire:' || job.questionnaire_id::text
                        ORDER BY item.created_at DESC, item.id DESC
                        LIMIT 1
                    ) agent_item ON TRUE
                    WHERE job.questionnaire_id = :questionnaire_id
                    ORDER BY job.created_at DESC, job.id DESC
                    LIMIT :limit
                    """
                ),
                {"questionnaire_id": int(questionnaire_id), "limit": max(1, min(int(limit or 100), 500))},
            ).mappings().all()
            count_rows = session.execute(
                text(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM questionnaire_continuation_job
                    WHERE questionnaire_id = :questionnaire_id
                    GROUP BY status
                    """
                ),
                {"questionnaire_id": int(questionnaire_id)},
            ).mappings().all()
        return [_public_row(row) for row in rows], {_text(row["status"]): int(row["count"]) for row in count_rows}

    def list_backfill_candidates(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return only recent submissions with persisted server verification proof.

        The query intentionally does not select or compare mobile/openid/answers.
        Existing successful actions and already tracked continuation actions are
        excluded independently so partial historical completion is preserved.
        """

        with get_session_factory()() as session:
            rows = session.execute(
                text(
                    """
                    WITH eligible AS (
                        SELECT
                            submission.id AS submission_id,
                            submission.questionnaire_id,
                            submission.unionid,
                            submission.submitted_at,
                            (
                                jsonb_array_length(COALESCE(submission.final_tags, '[]'::jsonb)) > 0
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM external_effect_job effect
                                    WHERE effect.effect_type = 'wecom.contact.tag.mark'
                                      AND effect.business_type = 'questionnaire_submission'
                                      AND effect.business_id = submission.id::text
                                      AND effect.status = 'succeeded'
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM questionnaire_continuation_job job
                                    WHERE job.submission_id = submission.id
                                      AND job.action_type = 'wecom_tag'
                                )
                            ) AS tag_action_required,
                            (
                                EXISTS (
                                    SELECT 1
                                    FROM ai_audience_package_dependency dependency
                                    JOIN ai_audience_package package ON package.id = dependency.package_id
                                    WHERE dependency.source_type = 'questionnaire_submission'
                                      AND dependency.source_key = 'questionnaire:' || submission.questionnaire_id::text
                                      AND package.status = 'active'
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM automation_agent_webhook_item item
                                    JOIN automation_agent_webhook_batch batch ON batch.batch_id = item.batch_id
                                    JOIN ai_audience_package package ON package.package_key = batch.bound_package_key
                                    JOIN ai_audience_package_dependency dependency ON dependency.package_id = package.id
                                    WHERE item.unionid = submission.unionid
                                      AND item.created_at >= submission.submitted_at
                                      AND item.status IN ('generated', 'callback_succeeded')
                                      AND dependency.source_type = 'questionnaire_submission'
                                      AND dependency.source_key = 'questionnaire:' || submission.questionnaire_id::text
                                )
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM questionnaire_continuation_job job
                                    WHERE job.submission_id = submission.id
                                      AND job.action_type = 'questionnaire_agent_followup'
                                )
                            ) AS agent_action_required
                        FROM questionnaire_submissions submission
                        WHERE submission.submitted_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                          AND submission.submitted_at <= CURRENT_TIMESTAMP
                          AND BTRIM(submission.unionid) <> ''
                          AND submission.unionid_verification_source = 'wechat_oauth_signed_session'
                          AND submission.unionid_verified_at IS NOT NULL
                    )
                    SELECT *
                    FROM eligible
                    WHERE tag_action_required OR agent_action_required
                    ORDER BY submitted_at ASC, submission_id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 200), 500))},
            ).mappings().all()
        return [_public_row(row) for row in rows]


_MEMORY_REPOSITORY = InMemoryQuestionnaireContinuationRepository()


def build_questionnaire_continuation_repository() -> QuestionnaireContinuationRepository:
    if production_data_ready():
        return PostgresQuestionnaireContinuationRepository()
    return _MEMORY_REPOSITORY


def reset_questionnaire_continuation_fixture_state() -> None:
    _MEMORY_REPOSITORY.reset()


__all__ = [
    "InMemoryQuestionnaireContinuationRepository",
    "PostgresQuestionnaireContinuationRepository",
    "QuestionnaireContinuationRepository",
    "build_questionnaire_continuation_repository",
    "reset_questionnaire_continuation_fixture_state",
]
