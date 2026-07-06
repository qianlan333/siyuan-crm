from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.errors import ContractError
from aicrm_next.shared.repository_provider import RepositoryProviderError


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return deepcopy(default)


def _as_mapping(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    mapping = getattr(row, "_mapping", None)
    return dict(mapping or row)


def _iso(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class GroupOpsWorkspaceGovernanceRepository:
    source_status = "postgres_group_ops_workspace_governance_repository"

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text("SELECT * FROM group_ops_workspace_drafts WHERE draft_id = :draft_id LIMIT 1"),
                    {"draft_id": draft_id},
                ).fetchone()
                return self._row_to_draft(_as_mapping(row) or {}) if row else None
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                return self._get_review_sql(conn, review_id)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def list_reviews_for_draft(self, draft_id: str) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT review_id
                        FROM group_ops_workspace_governance_reviews
                        WHERE draft_id = :draft_id
                        ORDER BY created_at DESC, id DESC
                        """
                    ),
                    {"draft_id": draft_id},
                ).fetchall()
                return [
                    review
                    for row in rows
                    if (review := self._get_review_sql(conn, str((_as_mapping(row) or {}).get("review_id") or "")))
                ]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def find_by_idempotency_key(self, *, draft_id: str, idempotency_key: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT review_id
                        FROM group_ops_workspace_governance_reviews
                        WHERE draft_id = :draft_id
                          AND idempotency_key = :idempotency_key
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"draft_id": draft_id, "idempotency_key": idempotency_key},
                ).fetchone()
                if not row:
                    return None
                return self._get_review_sql(conn, str((_as_mapping(row) or {}).get("review_id") or ""))
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def find_active_review_for_draft(self, draft_id: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT review_id
                        FROM group_ops_workspace_governance_reviews
                        WHERE draft_id = :draft_id
                          AND review_status IN (
                              'governance_not_started',
                              'approval_pending',
                              'allowlist_pending',
                              'gray_window_pending',
                              'governance_approved'
                          )
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"draft_id": draft_id},
                ).fetchone()
                if not row:
                    return None
                return self._get_review_sql(conn, str((_as_mapping(row) or {}).get("review_id") or ""))
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def transition_governance_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_governance_review_steps
                        SET step_status = :step_status,
                            actor_id = :actor_id,
                            actor_label = :actor_label,
                            idempotency_key = :idempotency_key,
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE review_id = :review_id
                          AND step_id = :step_id
                        """
                    ),
                    {
                        "review_id": payload["review_id"],
                        "step_id": payload["step_id"],
                        "step_status": payload["step_status"],
                        "actor_id": payload["actor_id"],
                        "actor_label": payload.get("actor_label", ""),
                        "idempotency_key": payload["idempotency_key"],
                        "metadata_json": _json_dumps(payload.get("metadata")),
                    },
                )
                if payload.get("gray_window_status"):
                    conn.execute(
                        text(
                            """
                            UPDATE group_ops_workspace_gray_window_approvals
                            SET window_status = :gray_window_status,
                                approved_by = CASE WHEN :gray_window_status = 'approved' THEN :actor_id ELSE approved_by END,
                                rejected_by = CASE WHEN :gray_window_status IN ('rejected', 'expired') THEN :actor_id ELSE rejected_by END,
                                metadata_json = CAST(:metadata_json AS jsonb),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE review_id = :review_id
                            """
                        ),
                        {
                            "review_id": payload["review_id"],
                            "gray_window_status": payload["gray_window_status"],
                            "actor_id": payload["actor_id"],
                            "metadata_json": _json_dumps(payload.get("metadata")),
                        },
                    )
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_governance_reviews
                        SET review_status = :review_status,
                            approved_by = CASE WHEN :review_status = 'governance_approved' THEN :actor_id ELSE approved_by END,
                            rejected_by = CASE WHEN :review_status = 'governance_rejected' THEN :actor_id ELSE rejected_by END,
                            audit_metadata_json = CAST(:audit_metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE review_id = :review_id
                        """
                    ),
                    {
                        "review_id": payload["review_id"],
                        "review_status": payload["review_status"],
                        "actor_id": payload["actor_id"],
                        "audit_metadata_json": _json_dumps(payload.get("audit_metadata")),
                    },
                )
                return self._get_review_sql(conn, payload["review_id"]) or {}
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def expire_governance_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_governance_review_steps
                        SET step_status = 'expired',
                            actor_id = :actor_id,
                            actor_label = :actor_label,
                            idempotency_key = CASE WHEN idempotency_key = '' THEN :idempotency_key ELSE idempotency_key END,
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE review_id = :review_id
                          AND step_status = 'pending'
                        """
                    ),
                    {
                        "review_id": payload["review_id"],
                        "actor_id": payload["actor_id"],
                        "actor_label": payload.get("actor_label", ""),
                        "idempotency_key": payload["idempotency_key"],
                        "metadata_json": _json_dumps(payload.get("metadata")),
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_gray_window_approvals
                        SET window_status = 'expired',
                            rejected_by = :actor_id,
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE review_id = :review_id
                        """
                    ),
                    {
                        "review_id": payload["review_id"],
                        "actor_id": payload["actor_id"],
                        "metadata_json": _json_dumps(payload.get("metadata")),
                    },
                )
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_governance_reviews
                        SET review_status = 'governance_expired',
                            audit_metadata_json = CAST(:audit_metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE review_id = :review_id
                        """
                    ),
                    {
                        "review_id": payload["review_id"],
                        "audit_metadata_json": _json_dumps(payload.get("audit_metadata")),
                    },
                )
                return self._get_review_sql(conn, payload["review_id"]) or {}
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def record_push_center_bridge(self, *, review_id: str, audit_metadata: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_governance_reviews
                        SET audit_metadata_json = CAST(:audit_metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE review_id = :review_id
                        """
                    ),
                    {
                        "review_id": review_id,
                        "audit_metadata_json": _json_dumps(audit_metadata),
                    },
                )
                return self._get_review_sql(conn, review_id) or {}
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def create_governance_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO group_ops_workspace_governance_reviews (
                            review_id, draft_id, review_status, requested_by, idempotency_key,
                            snapshot_hash, sanitized_payload_hash, audit_metadata_json, expires_at
                        )
                        VALUES (
                            :review_id, :draft_id, 'approval_pending', :requested_by, :idempotency_key,
                            :snapshot_hash, :sanitized_payload_hash, CAST(:audit_metadata_json AS jsonb), :expires_at
                        )
                        """
                    ),
                    {
                        **payload,
                        "audit_metadata_json": _json_dumps(payload.get("audit_metadata")),
                    },
                )
                for step in payload.get("steps") or []:
                    conn.execute(
                        text(
                            """
                            INSERT INTO group_ops_workspace_governance_review_steps (
                                review_id, step_id, step_type, step_status, actor_id, actor_label,
                                idempotency_key, snapshot_hash, metadata_json
                            )
                            VALUES (
                                :review_id, :step_id, :step_type, 'pending', :actor_id, :actor_label,
                                :idempotency_key, :snapshot_hash, CAST(:metadata_json AS jsonb)
                            )
                            """
                        ),
                        {
                            **step,
                            "review_id": payload["review_id"],
                            "actor_id": payload["requested_by"],
                            "actor_label": payload.get("actor_label", ""),
                            "idempotency_key": "",
                            "snapshot_hash": payload["snapshot_hash"],
                            "metadata_json": _json_dumps(step.get("metadata")),
                        },
                    )
                allowlist = payload.get("allowlist_snapshot") or {}
                conn.execute(
                    text(
                        """
                        INSERT INTO group_ops_workspace_allowlist_snapshots (
                            snapshot_id, review_id, allowlist_hash, allowlist_count,
                            allowlist_summary_json, source_reference_json, expires_at
                        )
                        VALUES (
                            :snapshot_id, :review_id, :allowlist_hash, :allowlist_count,
                            CAST(:allowlist_summary_json AS jsonb), CAST(:source_reference_json AS jsonb), :expires_at
                        )
                        """
                    ),
                    {
                        **allowlist,
                        "review_id": payload["review_id"],
                        "allowlist_summary_json": _json_dumps(allowlist.get("allowlist_summary")),
                        "source_reference_json": _json_dumps(allowlist.get("source_reference")),
                    },
                )
                gray_window = payload.get("gray_window") or {}
                conn.execute(
                    text(
                        """
                        INSERT INTO group_ops_workspace_gray_window_approvals (
                            approval_id, review_id, start_at, end_at, timezone, window_status, metadata_json
                        )
                        VALUES (
                            :approval_id, :review_id, :start_at, :end_at, :timezone, 'pending', CAST(:metadata_json AS jsonb)
                        )
                        """
                    ),
                    {
                        **gray_window,
                        "review_id": payload["review_id"],
                        "metadata_json": _json_dumps(gray_window.get("metadata")),
                    },
                )
                return self._get_review_sql(conn, payload["review_id"]) or {}
        except IntegrityError as exc:
            raise ContractError("governance review idempotency or review_id conflict") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace governance repository unavailable: {exc}") from exc

    def _get_review_sql(self, conn: Any, review_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            text("SELECT * FROM group_ops_workspace_governance_reviews WHERE review_id = :review_id LIMIT 1"),
            {"review_id": review_id},
        ).fetchone()
        if not row:
            return None
        review = self._row_to_review(_as_mapping(row) or {})
        steps = conn.execute(
            text(
                """
                SELECT *
                FROM group_ops_workspace_governance_review_steps
                WHERE review_id = :review_id
                ORDER BY id ASC
                """
            ),
            {"review_id": review_id},
        ).fetchall()
        allowlist = conn.execute(
            text(
                """
                SELECT *
                FROM group_ops_workspace_allowlist_snapshots
                WHERE review_id = :review_id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"review_id": review_id},
        ).fetchone()
        gray_window = conn.execute(
            text(
                """
                SELECT *
                FROM group_ops_workspace_gray_window_approvals
                WHERE review_id = :review_id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"review_id": review_id},
        ).fetchone()
        return {
            **review,
            "steps": [self._row_to_step(_as_mapping(step) or {}) for step in steps],
            "allowlist_summary": self._row_to_allowlist(_as_mapping(allowlist) or {}) if allowlist else {},
            "gray_window": self._row_to_gray_window(_as_mapping(gray_window) or {}) if gray_window else {},
        }

    def _row_to_draft(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "draft_id": str(row.get("draft_id") or ""),
            "tenant_id": str(row.get("tenant_id") or ""),
            "admin_scope": str(row.get("admin_scope") or ""),
            "source_plan_id": str(row.get("source_plan_id") or ""),
            "draft_status": str(row.get("draft_status") or ""),
            "version": _int(row.get("version")),
            "snapshot_hash": str(row.get("snapshot_hash") or ""),
            "sanitized_payload": _json_loads(row.get("sanitized_payload_json"), {}),
            "guardrail_summary": _json_loads(row.get("guardrail_summary_json"), {}),
            "approval_requirements": _json_loads(row.get("approval_requirements_json"), {}),
            "created_by": str(row.get("created_by") or ""),
            "updated_by": str(row.get("updated_by") or ""),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "archived_at": _iso(row.get("archived_at")),
        }

    def _row_to_review(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _int(row.get("id")),
            "review_id": str(row.get("review_id") or ""),
            "draft_id": str(row.get("draft_id") or ""),
            "review_status": str(row.get("review_status") or ""),
            "requested_by": str(row.get("requested_by") or ""),
            "approved_by": str(row.get("approved_by") or ""),
            "rejected_by": str(row.get("rejected_by") or ""),
            "idempotency_key": str(row.get("idempotency_key") or ""),
            "snapshot_hash": str(row.get("snapshot_hash") or ""),
            "sanitized_payload_hash": str(row.get("sanitized_payload_hash") or ""),
            "audit_metadata": _json_loads(row.get("audit_metadata_json"), {}),
            "expires_at": _iso(row.get("expires_at")),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }

    def _row_to_step(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "step_id": str(row.get("step_id") or ""),
            "step_type": str(row.get("step_type") or ""),
            "step_status": str(row.get("step_status") or ""),
            "actor_id": str(row.get("actor_id") or ""),
            "actor_label": str(row.get("actor_label") or ""),
            "idempotency_key": str(row.get("idempotency_key") or ""),
            "snapshot_hash": str(row.get("snapshot_hash") or ""),
            "metadata": _json_loads(row.get("metadata_json"), {}),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }

    def _row_to_allowlist(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "snapshot_id": str(row.get("snapshot_id") or ""),
            "allowlist_hash": str(row.get("allowlist_hash") or ""),
            "allowlist_count": _int(row.get("allowlist_count")),
            "allowlist_summary": _json_loads(row.get("allowlist_summary_json"), {}),
            "source_reference": _json_loads(row.get("source_reference_json"), {}),
            "expires_at": _iso(row.get("expires_at")),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }

    def _row_to_gray_window(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "approval_id": str(row.get("approval_id") or ""),
            "start_at": _iso(row.get("start_at")),
            "end_at": _iso(row.get("end_at")),
            "timezone": str(row.get("timezone") or ""),
            "window_status": str(row.get("window_status") or ""),
            "approved_by": str(row.get("approved_by") or ""),
            "rejected_by": str(row.get("rejected_by") or ""),
            "metadata": _json_loads(row.get("metadata_json"), {}),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }


def build_group_ops_workspace_governance_repository() -> GroupOpsWorkspaceGovernanceRepository:
    return GroupOpsWorkspaceGovernanceRepository()
