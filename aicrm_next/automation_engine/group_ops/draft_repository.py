from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.errors import ContractError, NotFoundError
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


class GroupOpsWorkspaceDraftRepository:
    source_status = "postgres_group_ops_workspace_draft_repository"

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    def list_drafts(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        status = str(filters.get("status") or "").strip()
        source_plan_id = str(filters.get("source_plan_id") or "").strip()
        limit = max(1, min(200, _int(filters.get("limit")) or 50))
        offset = max(0, _int(filters.get("offset")))
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            clauses.append("draft_status = :status")
            params["status"] = status
        if source_plan_id:
            clauses.append("source_plan_id = :source_plan_id")
            params["source_plan_id"] = source_plan_id
        where = " AND ".join(clauses)
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        f"""
                        SELECT *
                        FROM group_ops_workspace_drafts
                        WHERE {where}
                        ORDER BY updated_at DESC, id DESC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                ).fetchall()
                total = conn.execute(
                    text(f"SELECT COUNT(*) FROM group_ops_workspace_drafts WHERE {where}"),
                    {k: v for k, v in params.items() if k not in {"limit", "offset"}},
                ).scalar_one()
                return [self._row_to_draft(_as_mapping(row) or {}, items=[]) for row in rows], int(total or 0)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                return self._get_draft_sql(conn, draft_id)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def find_by_idempotency_key(self, *, tenant_id: str, admin_scope: str, idempotency_key: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM group_ops_workspace_drafts
                        WHERE tenant_id = :tenant_id
                          AND admin_scope = :admin_scope
                          AND idempotency_key = :idempotency_key
                        LIMIT 1
                        """
                    ),
                    {"tenant_id": tenant_id, "admin_scope": admin_scope, "idempotency_key": idempotency_key},
                ).fetchone()
                if not row:
                    return None
                return self._get_draft_sql(conn, str((_as_mapping(row) or {}).get("draft_id") or ""))
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def create_draft(self, payload: dict[str, Any], *, audit_metadata: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO group_ops_workspace_drafts (
                            draft_id, tenant_id, admin_scope, source_plan_id, draft_status,
                            version, idempotency_key, snapshot_hash, sanitized_payload_json,
                            guardrail_summary_json, approval_requirements_json, created_by, updated_by
                        )
                        VALUES (
                            :draft_id, :tenant_id, :admin_scope, :source_plan_id, 'draft',
                            1, :idempotency_key, :snapshot_hash, CAST(:sanitized_payload_json AS jsonb),
                            CAST(:guardrail_summary_json AS jsonb), CAST(:approval_requirements_json AS jsonb),
                            :actor_id, :actor_id
                        )
                        """
                    ),
                    {
                        **payload,
                        "sanitized_payload_json": _json_dumps(payload.get("sanitized_payload")),
                        "guardrail_summary_json": _json_dumps(payload.get("guardrail_summary")),
                        "approval_requirements_json": _json_dumps(payload.get("approval_requirements")),
                    },
                )
                self._replace_items_sql(conn, payload["draft_id"], payload.get("items") or [])
                self._insert_audit_sql(
                    conn,
                    draft_id=payload["draft_id"],
                    action="create",
                    actor_id=payload["actor_id"],
                    actor_label=payload.get("actor_label", ""),
                    actor_metadata=payload.get("actor_metadata", {}),
                    version=1,
                    snapshot_hash=payload["snapshot_hash"],
                    before_metadata={},
                    after_metadata=audit_metadata,
                )
                return self._get_draft_sql(conn, payload["draft_id"]) or {}
        except IntegrityError as exc:
            raise ContractError("draft idempotency key or draft_id already exists") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def update_draft(
        self,
        draft_id: str,
        payload: dict[str, Any],
        *,
        expected_version: int,
        before_metadata: dict[str, Any],
        after_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                current = self._get_draft_sql(conn, draft_id)
                if not current:
                    raise NotFoundError("draft not found")
                if current["draft_status"] == "archived":
                    raise ContractError("archived draft cannot be updated")
                if int(current["version"]) != int(expected_version):
                    raise ContractError("draft version conflict")
                next_version = int(current["version"]) + 1
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_drafts
                        SET source_plan_id = :source_plan_id,
                            version = :version,
                            idempotency_key = :idempotency_key,
                            snapshot_hash = :snapshot_hash,
                            sanitized_payload_json = CAST(:sanitized_payload_json AS jsonb),
                            guardrail_summary_json = CAST(:guardrail_summary_json AS jsonb),
                            approval_requirements_json = CAST(:approval_requirements_json AS jsonb),
                            updated_by = :actor_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE draft_id = :draft_id
                        """
                    ),
                    {
                        **payload,
                        "draft_id": draft_id,
                        "version": next_version,
                        "sanitized_payload_json": _json_dumps(payload.get("sanitized_payload")),
                        "guardrail_summary_json": _json_dumps(payload.get("guardrail_summary")),
                        "approval_requirements_json": _json_dumps(payload.get("approval_requirements")),
                    },
                )
                self._replace_items_sql(conn, draft_id, payload.get("items") or [])
                self._insert_audit_sql(
                    conn,
                    draft_id=draft_id,
                    action="update",
                    actor_id=payload["actor_id"],
                    actor_label=payload.get("actor_label", ""),
                    actor_metadata=payload.get("actor_metadata", {}),
                    version=next_version,
                    snapshot_hash=payload["snapshot_hash"],
                    before_metadata=before_metadata,
                    after_metadata=after_metadata,
                )
                return self._get_draft_sql(conn, draft_id) or {}
        except (ContractError, NotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def archive_draft(
        self,
        draft_id: str,
        *,
        expected_version: int,
        actor_id: str,
        actor_label: str,
        actor_metadata: dict[str, Any],
        before_metadata: dict[str, Any],
        after_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                current = self._get_draft_sql(conn, draft_id)
                if not current:
                    raise NotFoundError("draft not found")
                if int(current["version"]) != int(expected_version):
                    raise ContractError("draft version conflict")
                if current["draft_status"] != "archived":
                    conn.execute(
                        text(
                            """
                            UPDATE group_ops_workspace_drafts
                            SET draft_status = 'archived',
                                updated_by = :actor_id,
                                updated_at = CURRENT_TIMESTAMP,
                                archived_at = CURRENT_TIMESTAMP
                            WHERE draft_id = :draft_id
                            """
                        ),
                        {"draft_id": draft_id, "actor_id": actor_id},
                    )
                self._insert_audit_sql(
                    conn,
                    draft_id=draft_id,
                    action="archive",
                    actor_id=actor_id,
                    actor_label=actor_label,
                    actor_metadata=actor_metadata,
                    version=int(current["version"]),
                    snapshot_hash=str(current.get("snapshot_hash") or ""),
                    before_metadata=before_metadata,
                    after_metadata=after_metadata,
                )
                return self._get_draft_sql(conn, draft_id) or {}
        except (ContractError, NotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def request_review_draft(
        self,
        draft_id: str,
        *,
        expected_version: int,
        actor_id: str,
        actor_label: str,
        actor_metadata: dict[str, Any],
        before_metadata: dict[str, Any],
        after_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            with self._engine.begin() as conn:
                current = self._get_draft_sql(conn, draft_id)
                if not current:
                    raise NotFoundError("draft not found")
                if int(current["version"]) != int(expected_version):
                    raise ContractError("draft version conflict")
                if current["draft_status"] != "draft":
                    raise ContractError("draft status cannot request review")
                next_version = int(current["version"]) + 1
                conn.execute(
                    text(
                        """
                        UPDATE group_ops_workspace_drafts
                        SET draft_status = 'ready_for_review',
                            version = :version,
                            updated_by = :actor_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE draft_id = :draft_id
                        """
                    ),
                    {"draft_id": draft_id, "version": next_version, "actor_id": actor_id},
                )
                self._insert_audit_sql(
                    conn,
                    draft_id=draft_id,
                    action="request_review",
                    actor_id=actor_id,
                    actor_label=actor_label,
                    actor_metadata=actor_metadata,
                    version=next_version,
                    snapshot_hash=str(current.get("snapshot_hash") or ""),
                    before_metadata=before_metadata,
                    after_metadata={**after_metadata, "version": next_version},
                )
                return self._get_draft_sql(conn, draft_id) or {}
        except (ContractError, NotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def find_request_review_audit(self, *, draft_id: str, idempotency_key: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM group_ops_workspace_draft_audit_logs
                        WHERE draft_id = :draft_id
                          AND action = 'request_review'
                          AND after_metadata_json ->> 'request_review_idempotency_key' = :idempotency_key
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"draft_id": draft_id, "idempotency_key": idempotency_key},
                ).fetchone()
                return self._row_to_audit(_as_mapping(row) or {}) if row else None
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def count_audit_logs(self, draft_id: str) -> int:
        try:
            with self._engine.connect() as conn:
                return int(
                    conn.execute(
                        text("SELECT COUNT(*) FROM group_ops_workspace_draft_audit_logs WHERE draft_id = :draft_id"),
                        {"draft_id": draft_id},
                    ).scalar_one()
                    or 0
                )
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"group ops workspace draft repository unavailable: {exc}") from exc

    def _get_draft_sql(self, conn: Any, draft_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            text("SELECT * FROM group_ops_workspace_drafts WHERE draft_id = :draft_id LIMIT 1"),
            {"draft_id": draft_id},
        ).fetchone()
        if not row:
            return None
        item_rows = conn.execute(
            text(
                """
                SELECT *
                FROM group_ops_workspace_draft_items
                WHERE draft_id = :draft_id
                ORDER BY item_order ASC, id ASC
                """
            ),
            {"draft_id": draft_id},
        ).fetchall()
        return self._row_to_draft(_as_mapping(row) or {}, items=[self._row_to_item(_as_mapping(item) or {}) for item in item_rows])

    def _replace_items_sql(self, conn: Any, draft_id: str, items: list[dict[str, Any]]) -> None:
        conn.execute(text("DELETE FROM group_ops_workspace_draft_items WHERE draft_id = :draft_id"), {"draft_id": draft_id})
        for index, item in enumerate(items):
            conn.execute(
                text(
                    """
                    INSERT INTO group_ops_workspace_draft_items (
                        draft_id, item_type, item_ref_id, item_order,
                        sanitized_item_json, guardrail_summary_json
                    )
                    VALUES (
                        :draft_id, :item_type, :item_ref_id, :item_order,
                        CAST(:sanitized_item_json AS jsonb), CAST(:guardrail_summary_json AS jsonb)
                    )
                    """
                ),
                {
                    "draft_id": draft_id,
                    "item_type": str(item.get("item_type") or "").strip(),
                    "item_ref_id": str(item.get("item_ref_id") or "").strip(),
                    "item_order": int(item.get("item_order") if item.get("item_order") is not None else index),
                    "sanitized_item_json": _json_dumps(item.get("sanitized_item")),
                    "guardrail_summary_json": _json_dumps(item.get("guardrail_summary")),
                },
            )

    def _insert_audit_sql(
        self,
        conn: Any,
        *,
        draft_id: str,
        action: str,
        actor_id: str,
        actor_label: str,
        actor_metadata: dict[str, Any],
        version: int,
        snapshot_hash: str,
        before_metadata: dict[str, Any],
        after_metadata: dict[str, Any],
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO group_ops_workspace_draft_audit_logs (
                    draft_id, action, actor_id, actor_label, actor_metadata_json,
                    version, snapshot_hash, before_metadata_json, after_metadata_json
                )
                VALUES (
                    :draft_id, :action, :actor_id, :actor_label, CAST(:actor_metadata_json AS jsonb),
                    :version, :snapshot_hash, CAST(:before_metadata_json AS jsonb), CAST(:after_metadata_json AS jsonb)
                )
                """
            ),
            {
                "draft_id": draft_id,
                "action": action,
                "actor_id": actor_id,
                "actor_label": actor_label,
                "actor_metadata_json": _json_dumps(actor_metadata),
                "version": int(version),
                "snapshot_hash": snapshot_hash,
                "before_metadata_json": _json_dumps(before_metadata),
                "after_metadata_json": _json_dumps(after_metadata),
            },
        )

    def _row_to_draft(self, row: dict[str, Any], *, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": _int(row.get("id")),
            "draft_id": str(row.get("draft_id") or ""),
            "tenant_id": str(row.get("tenant_id") or ""),
            "admin_scope": str(row.get("admin_scope") or ""),
            "source_plan_id": str(row.get("source_plan_id") or ""),
            "draft_status": str(row.get("draft_status") or ""),
            "version": _int(row.get("version")),
            "idempotency_key": str(row.get("idempotency_key") or ""),
            "snapshot_hash": str(row.get("snapshot_hash") or ""),
            "sanitized_payload": _json_loads(row.get("sanitized_payload_json"), {}),
            "guardrail_summary": _json_loads(row.get("guardrail_summary_json"), {}),
            "approval_requirements": _json_loads(row.get("approval_requirements_json"), {}),
            "created_by": str(row.get("created_by") or ""),
            "updated_by": str(row.get("updated_by") or ""),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "archived_at": _iso(row.get("archived_at")),
            "items": items,
        }

    def _row_to_item(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _int(row.get("id")),
            "draft_id": str(row.get("draft_id") or ""),
            "item_type": str(row.get("item_type") or ""),
            "item_ref_id": str(row.get("item_ref_id") or ""),
            "item_order": _int(row.get("item_order")),
            "sanitized_item": _json_loads(row.get("sanitized_item_json"), {}),
            "guardrail_summary": _json_loads(row.get("guardrail_summary_json"), {}),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }

    def _row_to_audit(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _int(row.get("id")),
            "draft_id": str(row.get("draft_id") or ""),
            "action": str(row.get("action") or ""),
            "actor_id": str(row.get("actor_id") or ""),
            "actor_label": str(row.get("actor_label") or ""),
            "actor_metadata": _json_loads(row.get("actor_metadata_json"), {}),
            "version": _int(row.get("version")),
            "snapshot_hash": str(row.get("snapshot_hash") or ""),
            "before_metadata": _json_loads(row.get("before_metadata_json"), {}),
            "after_metadata": _json_loads(row.get("after_metadata_json"), {}),
            "created_at": _iso(row.get("created_at")),
        }


def build_group_ops_workspace_draft_repository() -> GroupOpsWorkspaceDraftRepository:
    return GroupOpsWorkspaceDraftRepository()
