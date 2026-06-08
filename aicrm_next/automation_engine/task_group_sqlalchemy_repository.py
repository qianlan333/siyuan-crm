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
from .task_groups import TASK_GROUP_ROUTE_FAMILY, normalize_task_group_create_payload, task_group_projection, task_group_side_effect_safety


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


class SqlAlchemyTaskGroupRepository(InMemoryAutomationRepository):
    """Explicit test/staging DB adapter for task-group metadata only."""

    source_status = "sql_alchemy_task_group_repository"

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self._engine = engine

    def list_task_groups(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        program_id = filters.get("program_id")
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        try:
            with self._engine.connect() as conn:
                clauses = []
                params: dict[str, Any] = {"limit": limit, "offset": offset}
                if program_id not in (None, ""):
                    clauses.append("program_id = :program_id")
                    params["program_id"] = int(program_id)
                if not include_archived:
                    clauses.append("(archived_at IS NULL OR archived_at = '')")
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                rows = conn.execute(
                    text(
                        f"""
                        SELECT *
                        FROM automation_task_groups
                        {where}
                        ORDER BY sort_order ASC, id ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                ).fetchall()
                total = conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*) AS total
                        FROM automation_task_groups
                        {where}
                        """
                    ),
                    {key: value for key, value in params.items() if key not in {"limit", "offset"}},
                ).scalar_one()
            return [self._row_to_projection(_as_mapping(row) or {}) for row in rows], int(total or 0)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task group repository unavailable: {exc}") from exc

    def create_task_group(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_task_group_create_payload({**payload, "operator": operator_id})
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
                self._assert_unique_task_group_sql(conn, normalized)
                self._insert_idempotency_pending(conn, operator=operator_id, idempotency_key=key, request_hash=request_hash)
                saved = self._insert_task_group(conn, normalized)
                rollback_payload = {
                    "strategy": "archive_created_group_in_later_approved_phase",
                    "created_group_id": saved["id"],
                    "group_code": saved["group_code"],
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
                    "group": deepcopy(saved),
                    "groups": [deepcopy(saved)],
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
            raise ContractError("task group name or code already exists for program") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task group repository unavailable: {exc}") from exc

    def list_task_group_audit_events(self) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_task_group_audit_log
                        WHERE route_family = :route_family
                        ORDER BY created_at DESC, id DESC
                        LIMIT 50
                        """
                    ),
                    {"route_family": TASK_GROUP_ROUTE_FAMILY},
                ).fetchall()
            return [self._audit_row_to_event(_as_mapping(row) or {}) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"task group repository unavailable: {exc}") from exc

    def _load_idempotency(self, conn: Any, *, operator: str, idempotency_key: str) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM automation_task_group_idempotency
                WHERE route_family = :route_family
                  AND operation = 'create'
                  AND operator = :operator
                  AND idempotency_key = :idempotency_key
                """
            ),
            {
                "route_family": TASK_GROUP_ROUTE_FAMILY,
                "operator": operator,
                "idempotency_key": idempotency_key,
            },
        ).fetchone()
        return _as_mapping(row)

    def _insert_idempotency_pending(self, conn: Any, *, operator: str, idempotency_key: str, request_hash: str) -> None:
        conn.execute(
            text(
                """
                INSERT INTO automation_task_group_idempotency (
                    route_family, operation, operator, idempotency_key, request_hash,
                    response_snapshot, resource_type, resource_id, status, created_at, updated_at
                )
                VALUES (
                    :route_family, 'create', :operator, :idempotency_key, :request_hash,
                    :response_snapshot, 'task_group', NULL, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "route_family": TASK_GROUP_ROUTE_FAMILY,
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
                UPDATE automation_task_group_idempotency
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
                "route_family": TASK_GROUP_ROUTE_FAMILY,
                "operator": operator,
                "idempotency_key": idempotency_key,
                "resource_id": resource_id,
                "response_snapshot": _json_dumps(response_snapshot),
            },
        )

    def _assert_unique_task_group_sql(self, conn: Any, normalized: dict[str, Any]) -> None:
        row = conn.execute(
            text(
                """
                SELECT id
                FROM automation_task_groups
                WHERE program_id = :program_id
                  AND (
                    LOWER(group_name) = LOWER(:group_name)
                    OR LOWER(group_code) = LOWER(:group_code)
                  )
                LIMIT 1
                """
            ),
            {
                "program_id": int(normalized["program_id"]),
                "group_name": normalized["group_name"],
                "group_code": normalized["group_code"],
            },
        ).fetchone()
        if row is not None:
            raise ContractError("task group name or code already exists for program")

    def _insert_task_group(self, conn: Any, normalized: dict[str, Any]) -> dict[str, Any]:
        params = {
            "program_id": int(normalized["program_id"]),
            "group_code": normalized["group_code"],
            "group_name": normalized["group_name"],
            "sort_order": int(normalized["sort_order"]),
            "metadata_json": _json_dumps(normalized.get("metadata") or {}),
            "created_by": normalized["created_by"],
            "updated_by": normalized["updated_by"],
        }
        result = conn.execute(
            text(
                """
                INSERT INTO automation_task_groups (
                    program_id, group_code, group_name, sort_order, metadata_json,
                    created_by, updated_by, created_at, updated_at
                )
                VALUES (
                    :program_id, :group_code, :group_name, :sort_order, :metadata_json,
                    :created_by, :updated_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            params,
        )
        inserted_id = int(result.lastrowid or 0)
        if not inserted_id:
            inserted_id = int(conn.execute(text("SELECT MAX(id) FROM automation_task_groups")).scalar_one() or 0)
        row = conn.execute(text("SELECT * FROM automation_task_groups WHERE id = :id"), {"id": inserted_id}).fetchone()
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
                INSERT INTO automation_task_group_audit_log (
                    route_family, operation, operator, resource_type, resource_id,
                    before_snapshot, after_snapshot, request_payload, validation_result,
                    rollback_payload, side_effect_safety, created_at
                )
                VALUES (
                    :route_family, :operation, :operator, 'task_group', :resource_id,
                    :before_snapshot, :after_snapshot, :request_payload, :validation_result,
                    :rollback_payload, :side_effect_safety, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "route_family": TASK_GROUP_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "resource_id": resource_id,
                "before_snapshot": _json_dumps(before),
                "after_snapshot": _json_dumps(after),
                "request_payload": _json_dumps(request_payload),
                "validation_result": _json_dumps({"ok": True}),
                "rollback_payload": _json_dumps(rollback_payload),
                "side_effect_safety": _json_dumps(task_group_side_effect_safety()),
            },
        )
        row = conn.execute(text("SELECT * FROM automation_task_group_audit_log WHERE id = (SELECT MAX(id) FROM automation_task_group_audit_log)")).fetchone()
        return self._audit_row_to_event(_as_mapping(row) or {})

    def _row_to_projection(self, row: dict[str, Any]) -> dict[str, Any]:
        return task_group_projection(
            {
                "id": row.get("id"),
                "program_id": row.get("program_id"),
                "group_code": row.get("group_code"),
                "group_name": row.get("group_name"),
                "sort_order": row.get("sort_order"),
                "metadata": _json_loads(row.get("metadata_json"), {}),
                "created_by": row.get("created_by"),
                "updated_by": row.get("updated_by"),
                "created_at": str(row.get("created_at") or utc_now_iso()),
                "updated_at": str(row.get("updated_at") or utc_now_iso()),
                "archived_at": str(row.get("archived_at") or ""),
            }
        )

    def _audit_row_to_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "route_family": row.get("route_family") or TASK_GROUP_ROUTE_FAMILY,
            "operation": row.get("operation") or "",
            "operator": row.get("operator") or "",
            "resource_type": row.get("resource_type") or "task_group",
            "resource_id": row.get("resource_id"),
            "before_snapshot": _json_loads(row.get("before_snapshot"), {}),
            "after_snapshot": _json_loads(row.get("after_snapshot"), {}),
            "request_payload": _json_loads(row.get("request_payload"), {}),
            "validation_result": _json_loads(row.get("validation_result"), {}),
            "rollback_payload": _json_loads(row.get("rollback_payload"), {}),
            "side_effect_safety": _json_loads(row.get("side_effect_safety"), task_group_side_effect_safety()),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "external_event_dispatched": False,
        }
