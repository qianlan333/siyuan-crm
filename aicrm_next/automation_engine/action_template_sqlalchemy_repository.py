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

from .action_templates import (
    ACTION_TEMPLATE_ROUTE_FAMILY,
    action_template_projection,
    action_template_side_effect_safety,
    normalize_action_template_create_payload,
)
from .action_template_repository import ActionTemplateIdempotencyConflict
from .state_machine import utc_now_iso


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


class SqlAlchemyActionTemplateRepository:
    """Explicit-flag repository adapter for action-template metadata only."""

    source_status = "sql_alchemy_action_template_repository"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_action_templates(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        template_source = str(filters.get("template_source") or "").strip()
        category = str(filters.get("category") or "").strip()
        keyword = str(filters.get("keyword") or "").strip().lower()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)
        try:
            with self._engine.connect() as conn:
                clauses = []
                params: dict[str, Any] = {"limit": limit, "offset": offset}
                if template_source:
                    clauses.append("template_source = :template_source")
                    params["template_source"] = template_source
                if category:
                    clauses.append("category = :category")
                    params["category"] = category
                if not include_archived:
                    clauses.append("status != 'archived'")
                if keyword:
                    clauses.append("(LOWER(template_name) LIKE :keyword OR LOWER(description) LIKE :keyword OR LOWER(category) LIKE :keyword)")
                    params["keyword"] = f"%{keyword}%"
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                rows = conn.execute(
                    text(
                        f"""
                        SELECT *
                        FROM automation_operation_templates
                        {where}
                        ORDER BY template_source ASC, id ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                ).fetchall()
                total = conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*) AS total
                        FROM automation_operation_templates
                        {where}
                        """
                    ),
                    {key: value for key, value in params.items() if key not in {"limit", "offset"}},
                ).scalar_one()
            return [self._template_row_to_projection(_as_mapping(row) or {}) for row in rows], int(total or 0)
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"action template repository unavailable: {exc}") from exc

    def create_action_template(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_action_template_create_payload({**payload, "operator": operator_id})
        request_hash = _request_hash(normalized)
        try:
            with self._engine.begin() as conn:
                replay = self._load_idempotency(conn, operator=operator_id, idempotency_key=key)
                if replay:
                    if replay.get("request_hash") != request_hash:
                        raise ActionTemplateIdempotencyConflict("idempotency key conflicts with a different request payload")
                    response = _json_loads(replay.get("response_snapshot"), {})
                    if isinstance(response, dict):
                        response["idempotent_replay"] = True
                        response["source_status"] = self.source_status
                        return response
                self._insert_idempotency_pending(conn, operator=operator_id, idempotency_key=key, request_hash=request_hash)
                saved = self._insert_template(conn, normalized)
                rollback_payload = {
                    "strategy": "archive_created_template_in_later_approved_phase",
                    "created_template_id": saved["id"],
                    "template_code": saved["template_code"],
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
                    validation_result={"ok": True},
                    rollback_payload=rollback_payload,
                )
                result = {
                    "source_status": self.source_status,
                    "template": saved,
                    "items": [deepcopy(saved)],
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
        except (ContractError, ActionTemplateIdempotencyConflict):
            raise
        except IntegrityError as exc:
            raise ContractError("action template code already exists") from exc
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"action template repository unavailable: {exc}") from exc

    def list_action_template_audit_events(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        resource_id = filters.get("resource_id")
        limit = int(filters.get("limit") or 50)
        clauses = ["route_family = :route_family"]
        params: dict[str, Any] = {"route_family": ACTION_TEMPLATE_ROUTE_FAMILY, "limit": limit}
        if resource_id not in (None, ""):
            clauses.append("resource_id = :resource_id")
            params["resource_id"] = int(resource_id)
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        f"""
                        SELECT *
                        FROM automation_operation_template_audit_log
                        WHERE {' AND '.join(clauses)}
                        ORDER BY created_at DESC, id DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                ).fetchall()
            return [self._audit_row_to_event(_as_mapping(row) or {}) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"action template repository unavailable: {exc}") from exc

    def _load_idempotency(self, conn: Any, *, operator: str, idempotency_key: str) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM automation_operation_template_idempotency
                WHERE route_family = :route_family
                  AND operation = 'create'
                  AND operator = :operator
                  AND idempotency_key = :idempotency_key
                """
            ),
            {
                "route_family": ACTION_TEMPLATE_ROUTE_FAMILY,
                "operator": operator,
                "idempotency_key": idempotency_key,
            },
        ).fetchone()
        return _as_mapping(row)

    def _insert_idempotency_pending(self, conn: Any, *, operator: str, idempotency_key: str, request_hash: str) -> None:
        conn.execute(
            text(
                """
                INSERT INTO automation_operation_template_idempotency (
                    route_family, operation, operator, idempotency_key, request_hash,
                    response_snapshot, resource_type, resource_id, status, created_at, updated_at
                )
                VALUES (
                    :route_family, 'create', :operator, :idempotency_key, :request_hash,
                    :response_snapshot, 'action_template', NULL, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "route_family": ACTION_TEMPLATE_ROUTE_FAMILY,
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
                UPDATE automation_operation_template_idempotency
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
                "route_family": ACTION_TEMPLATE_ROUTE_FAMILY,
                "operator": operator,
                "idempotency_key": idempotency_key,
                "resource_id": resource_id,
                "response_snapshot": _json_dumps(response_snapshot),
            },
        )

    def _insert_template(self, conn: Any, normalized: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            text(
                """
                INSERT INTO automation_operation_templates (
                    template_code, template_name, template_source, category, description, status,
                    default_config_json, ui_schema_json, workflow_blueprint_json, node_blueprints_json,
                    created_by, updated_by, created_at, updated_at, archived_at
                )
                VALUES (
                    :template_code, :template_name, :template_source, :category, :description, :status,
                    :default_config_json, :ui_schema_json, :workflow_blueprint_json, :node_blueprints_json,
                    :created_by, :updated_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
                )
                RETURNING *
                """
            ),
            {
                "template_code": normalized["template_code"],
                "template_name": normalized["template_name"],
                "template_source": normalized["template_source"],
                "category": normalized["category"],
                "description": normalized["description"],
                "status": normalized["status"],
                "default_config_json": _json_dumps(normalized["default_config"]),
                "ui_schema_json": _json_dumps(normalized["ui_schema"]),
                "workflow_blueprint_json": _json_dumps(normalized["workflow_blueprint"]),
                "node_blueprints_json": _json_dumps(normalized["node_blueprints"]),
                "created_by": normalized["created_by"],
                "updated_by": normalized["updated_by"],
            },
        ).fetchone()
        return self._template_row_to_projection(_as_mapping(row) or {})

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
        validation_result: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = conn.execute(
            text(
                """
                INSERT INTO automation_operation_template_audit_log (
                    route_family, operation, operator, resource_type, resource_id,
                    before_snapshot, after_snapshot, request_payload, validation_result,
                    rollback_payload, side_effect_safety, created_at
                )
                VALUES (
                    :route_family, :operation, :operator, 'action_template', :resource_id,
                    :before_snapshot, :after_snapshot, :request_payload, :validation_result,
                    :rollback_payload, :side_effect_safety, CURRENT_TIMESTAMP
                )
                RETURNING *
                """
            ),
            {
                "route_family": ACTION_TEMPLATE_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "resource_id": resource_id,
                "before_snapshot": _json_dumps(before),
                "after_snapshot": _json_dumps(after),
                "request_payload": _json_dumps(request_payload),
                "validation_result": _json_dumps(validation_result),
                "rollback_payload": _json_dumps(rollback_payload),
                "side_effect_safety": _json_dumps(action_template_side_effect_safety()),
            },
        ).fetchone()
        return self._audit_row_to_event(_as_mapping(row) or {})

    def _template_row_to_projection(self, row: dict[str, Any]) -> dict[str, Any]:
        return action_template_projection(
            {
                "id": row.get("id"),
                "template_code": row.get("template_code"),
                "template_name": row.get("template_name"),
                "template_source": row.get("template_source"),
                "category": row.get("category"),
                "description": row.get("description"),
                "status": row.get("status"),
                "default_config": _json_loads(row.get("default_config_json"), {}),
                "ui_schema": _json_loads(row.get("ui_schema_json"), {}),
                "workflow_blueprint": _json_loads(row.get("workflow_blueprint_json"), {}),
                "node_blueprints": _json_loads(row.get("node_blueprints_json"), []),
                "created_by": row.get("created_by"),
                "updated_by": row.get("updated_by"),
                "created_at": str(row.get("created_at") or utc_now_iso()),
                "updated_at": str(row.get("updated_at") or utc_now_iso()),
                "archived_at": str(row.get("archived_at") or ""),
            }
        )

    def _audit_row_to_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row.get("id") or 0),
            "route_family": row.get("route_family") or ACTION_TEMPLATE_ROUTE_FAMILY,
            "operation": row.get("operation") or "",
            "operator": row.get("operator") or "",
            "resource_type": row.get("resource_type") or "action_template",
            "resource_id": row.get("resource_id"),
            "before_snapshot": _json_loads(row.get("before_snapshot"), {}),
            "after_snapshot": _json_loads(row.get("after_snapshot"), {}),
            "request_payload": _json_loads(row.get("request_payload"), {}),
            "validation_result": _json_loads(row.get("validation_result"), {}),
            "rollback_payload": _json_loads(row.get("rollback_payload"), {}),
            "side_effect_safety": _json_loads(row.get("side_effect_safety"), action_template_side_effect_safety()),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "external_event_dispatched": False,
        }
