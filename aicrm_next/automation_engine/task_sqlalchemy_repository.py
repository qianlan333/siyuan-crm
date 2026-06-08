from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aicrm_next.shared.errors import ContractError
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .repo import InMemoryAutomationRepository
from .state_machine import utc_now_iso
from .tasks import TASK_ROUTE_FAMILY, normalize_task_create_payload, task_projection, task_side_effect_safety


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


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _as_mapping(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    mapping = getattr(row, "_mapping", None)
    return dict(mapping or row)


class SqlAlchemyTaskRepository(InMemoryAutomationRepository):
    """Explicit test/staging DB adapter for task metadata only."""

    source_status = "sql_alchemy_task_repository"

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self._engine = engine

    def list_tasks(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        workflow_id = filters.get("workflow_id")
        node_id = filters.get("node_id")
        group_id = filters.get("group_id")
        task_type = str(filters.get("task_type") or "").strip()
        status = str(filters.get("status") or "").strip()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        try:
            with self._engine.connect() as conn:
                clauses = []
                params: dict[str, Any] = {"limit": limit, "offset": offset}
                for field, value in (
                    ("program_id", program_id),
                    ("workflow_id", workflow_id),
                    ("node_id", node_id),
                    ("group_id", group_id),
                ):
                    if value not in (None, ""):
                        clauses.append(f"{field} = :{field}")
                        params[field] = int(value)
                if task_type:
                    clauses.append("task_type = :task_type")
                    params["task_type"] = task_type
                if status:
                    clauses.append("status = :status")
                    params["status"] = status
                if not include_archived:
                    clauses.append("(archived_at IS NULL OR archived_at = '')")
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                rows = conn.execute(
                    text(
                        f"""
                        SELECT *
                        FROM automation_tasks
                        {where}
                        ORDER BY workflow_id ASC, node_id ASC, sort_order ASC, id ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                ).fetchall()
                total = conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*) AS total
                        FROM automation_tasks
                        {where}
                        """
                    ),
                    {key: value for key, value in params.items() if key not in {"limit", "offset"}},
                ).scalar_one()
            return [self._row_to_projection(_as_mapping(row) or {}) for row in rows], int(total or 0)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task repository unavailable: {exc}") from exc

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(text("SELECT * FROM automation_tasks WHERE id = :id"), {"id": int(task_id)}).fetchone()
            if not row:
                return None
            return self._row_to_projection(_as_mapping(row) or {})
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task repository unavailable: {exc}") from exc

    def create_task(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_task_create_payload({**payload, "operator": operator_id})
        request_hash = _request_hash(normalized)
        try:
            with self._engine.begin() as conn:
                replay = self._load_idempotency(conn, operator=operator_id, idempotency_key=key)
                if replay:
                    if replay.get("request_hash") != request_hash:
                        raise ContractError("idempotency key conflicts with a different request payload")
                    response = _json_loads(replay.get("response_snapshot"), {})
                    if isinstance(response, dict):
                        response["idempotent_replay"] = True
                        response["source_status"] = self.source_status
                        return response
                self._assert_unique_task_sql(conn, normalized)
                self._insert_idempotency_pending(conn, operator=operator_id, idempotency_key=key, request_hash=request_hash)
                saved = self._insert_task(conn, normalized)
                rollback_payload = {
                    "strategy": "archive_created_task_in_later_approved_phase",
                    "created_task_id": saved["id"],
                    "task_code": saved["task_code"],
                    "delete_approved": False,
                }
                audit_event = self._insert_audit_event(
                    conn,
                    operation="create",
                    operator=operator_id,
                    resource_id=int(saved["id"]),
                    before={},
                    after=saved,
                    request_payload=normalized,
                    rollback_payload=rollback_payload,
                )
                result = {
                    "source_status": self.source_status,
                    "task": deepcopy(saved),
                    "tasks": [deepcopy(saved)],
                    "audit_event": audit_event,
                    "rollback_payload": rollback_payload,
                    "idempotent_replay": False,
                }
                self._mark_idempotency_succeeded(
                    conn,
                    operator=operator_id,
                    idempotency_key=key,
                    resource_id=int(saved["id"]),
                    response_snapshot=result,
                )
                return deepcopy(result)
        except ContractError:
            raise
        except IntegrityError as exc:
            raise ContractError("task code already exists for workflow") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task repository unavailable: {exc}") from exc

    def update_task(self, task_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        operator_id = str(operator or payload.get("operator") or "system").strip() or "system"
        try:
            with self._engine.begin() as conn:
                before_row = conn.execute(text("SELECT * FROM automation_tasks WHERE id = :id"), {"id": int(task_id)}).fetchone()
                if not before_row:
                    raise ContractError("automation task not found")
                before = self._row_to_projection(_as_mapping(before_row) or {})
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else before.get("metadata") or {}
                config = payload.get("config") if isinstance(payload.get("config"), dict) else before.get("config") or {}
                conn.execute(
                    text(
                        """
                        UPDATE automation_tasks
                        SET metadata_json = :metadata_json,
                            config_json = :config_json,
                            updated_by = :updated_by,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": int(task_id),
                        "metadata_json": _json_dumps(metadata),
                        "config_json": _json_dumps(config),
                        "updated_by": operator_id,
                    },
                )
                after_row = conn.execute(text("SELECT * FROM automation_tasks WHERE id = :id"), {"id": int(task_id)}).fetchone()
                after = self._row_to_projection(_as_mapping(after_row) or {})
                audit_event = self._insert_audit_event(
                    conn,
                    operation="update",
                    operator=operator_id,
                    resource_id=int(task_id),
                    before=before,
                    after=after,
                    request_payload=payload,
                    rollback_payload={
                        "strategy": "restore_previous_task_config",
                        "task_id": int(task_id),
                        "previous_config": before.get("config") or {},
                        "delete_approved": False,
                    },
                )
            return {"source_status": self.source_status, "task": deepcopy(after), "audit_event": audit_event}
        except ContractError:
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task repository unavailable: {exc}") from exc

    def list_task_audit_events(self) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_task_audit_log
                        WHERE route_family = :route_family
                        ORDER BY created_at DESC, id DESC
                        LIMIT 50
                        """
                    ),
                    {"route_family": TASK_ROUTE_FAMILY},
                ).fetchall()
            return [self._audit_row_to_event(_as_mapping(row) or {}) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task repository unavailable: {exc}") from exc

    def _load_idempotency(self, conn: Any, *, operator: str, idempotency_key: str) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM automation_task_idempotency
                WHERE route_family = :route_family
                  AND operation = 'create'
                  AND operator = :operator
                  AND idempotency_key = :idempotency_key
                """
            ),
            {"route_family": TASK_ROUTE_FAMILY, "operator": operator, "idempotency_key": idempotency_key},
        ).fetchone()
        return _as_mapping(row)

    def _insert_idempotency_pending(self, conn: Any, *, operator: str, idempotency_key: str, request_hash: str) -> None:
        conn.execute(
            text(
                """
                INSERT INTO automation_task_idempotency (
                    route_family, operation, operator, idempotency_key, request_hash,
                    response_snapshot, resource_type, resource_id, status, created_at, updated_at
                )
                VALUES (
                    :route_family, 'create', :operator, :idempotency_key, :request_hash,
                    :response_snapshot, 'task', NULL, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "route_family": TASK_ROUTE_FAMILY,
                "operator": operator,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "response_snapshot": _json_dumps({}),
            },
        )

    def _mark_idempotency_succeeded(
        self,
        conn: Any,
        *,
        operator: str,
        idempotency_key: str,
        resource_id: int,
        response_snapshot: dict[str, Any],
    ) -> None:
        conn.execute(
            text(
                """
                UPDATE automation_task_idempotency
                SET response_snapshot = :response_snapshot,
                    resource_id = :resource_id,
                    status = 'succeeded',
                    updated_at = CURRENT_TIMESTAMP
                WHERE route_family = :route_family
                  AND operation = 'create'
                  AND operator = :operator
                  AND idempotency_key = :idempotency_key
                """
            ),
            {
                "route_family": TASK_ROUTE_FAMILY,
                "operator": operator,
                "idempotency_key": idempotency_key,
                "resource_id": resource_id,
                "response_snapshot": _json_dumps(response_snapshot),
            },
        )

    def _assert_unique_task_sql(self, conn: Any, normalized: dict[str, Any]) -> None:
        row = conn.execute(
            text(
                """
                SELECT id
                FROM automation_tasks
                WHERE workflow_id = :workflow_id
                  AND LOWER(task_code) = LOWER(:task_code)
                LIMIT 1
                """
            ),
            {"workflow_id": int(normalized["workflow_id"]), "task_code": normalized["task_code"]},
        ).fetchone()
        if row is not None:
            raise ContractError("task code already exists for workflow")

    def _insert_task(self, conn: Any, normalized: dict[str, Any]) -> dict[str, Any]:
        params = {
            "program_id": int(normalized["program_id"]),
            "workflow_id": int(normalized["workflow_id"]),
            "node_id": int(normalized["node_id"]),
            "group_id": int(normalized["group_id"]),
            "task_code": normalized["task_code"],
            "task_name": normalized["task_name"],
            "task_type": normalized["task_type"],
            "status": normalized["status"],
            "sort_order": int(normalized["sort_order"]),
            "metadata_json": _json_dumps(normalized.get("metadata") or {}),
            "config_json": _json_dumps(normalized.get("config") or {}),
            "enabled": bool(normalized["enabled"]),
            "created_by": normalized["created_by"],
            "updated_by": normalized["updated_by"],
        }
        result = conn.execute(
            text(
                """
                INSERT INTO automation_tasks (
                    program_id, workflow_id, node_id, group_id, task_code, task_name,
                    task_type, status, sort_order, metadata_json, config_json, enabled,
                    created_by, updated_by, created_at, updated_at
                )
                VALUES (
                    :program_id, :workflow_id, :node_id, :group_id, :task_code, :task_name,
                    :task_type, :status, :sort_order, :metadata_json, :config_json, :enabled,
                    :created_by, :updated_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            params,
        )
        inserted_id = int(result.lastrowid or 0)
        if not inserted_id:
            inserted_id = int(conn.execute(text("SELECT MAX(id) FROM automation_tasks")).scalar_one() or 0)
        row = conn.execute(text("SELECT * FROM automation_tasks WHERE id = :id"), {"id": inserted_id}).fetchone()
        return self._row_to_projection(_as_mapping(row) or {})

    def _insert_audit_event(
        self,
        conn: Any,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        conn.execute(
            text(
                """
                INSERT INTO automation_task_audit_log (
                    route_family, operation, operator, resource_type, resource_id,
                    before_snapshot, after_snapshot, request_payload, validation_result,
                    rollback_payload, side_effect_safety, created_at
                )
                VALUES (
                    :route_family, :operation, :operator, 'task', :resource_id,
                    :before_snapshot, :after_snapshot, :request_payload, :validation_result,
                    :rollback_payload, :side_effect_safety, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "route_family": TASK_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "resource_id": resource_id,
                "before_snapshot": _json_dumps(before),
                "after_snapshot": _json_dumps(after),
                "request_payload": _json_dumps(request_payload),
                "validation_result": _json_dumps({"ok": True}),
                "rollback_payload": _json_dumps(rollback_payload),
                "side_effect_safety": _json_dumps(task_side_effect_safety()),
            },
        )
        row = conn.execute(text("SELECT * FROM automation_task_audit_log WHERE id = (SELECT MAX(id) FROM automation_task_audit_log)")).fetchone()
        return self._audit_row_to_event(_as_mapping(row) or {})

    def _row_to_projection(self, row: dict[str, Any]) -> dict[str, Any]:
        return task_projection(
            {
                "id": row.get("id"),
                "program_id": row.get("program_id"),
                "workflow_id": row.get("workflow_id"),
                "node_id": row.get("node_id"),
                "group_id": row.get("group_id"),
                "task_code": row.get("task_code"),
                "task_name": row.get("task_name"),
                "task_type": row.get("task_type"),
                "status": row.get("status"),
                "sort_order": row.get("sort_order"),
                "metadata": _json_loads(row.get("metadata_json"), {}),
                "config": _json_loads(row.get("config_json"), {}),
                "enabled": row.get("enabled"),
                "created_by": row.get("created_by"),
                "updated_by": row.get("updated_by"),
                "created_at": str(row.get("created_at") or utc_now_iso()),
                "updated_at": str(row.get("updated_at") or utc_now_iso()),
                "archived_at": str(row.get("archived_at") or ""),
            }
        )

    def _audit_row_to_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "route_family": row.get("route_family") or TASK_ROUTE_FAMILY,
            "operation": row.get("operation") or "",
            "operator": row.get("operator") or "",
            "resource_type": row.get("resource_type") or "task",
            "resource_id": row.get("resource_id"),
            "before_snapshot": _json_loads(row.get("before_snapshot"), {}),
            "after_snapshot": _json_loads(row.get("after_snapshot"), {}),
            "request_payload": _json_loads(row.get("request_payload"), {}),
            "validation_result": _json_loads(row.get("validation_result"), {}),
            "rollback_payload": _json_loads(row.get("rollback_payload"), {}),
            "side_effect_safety": _json_loads(row.get("side_effect_safety"), task_side_effect_safety()),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "external_event_dispatched": False,
        }
