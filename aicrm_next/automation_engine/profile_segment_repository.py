from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from aicrm_next.shared.config import get_settings
from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError, assert_repository_allowed

from .profile_segments import (
    normalize_profile_segment_template_payload,
    profile_segment_side_effect_safety,
    profile_segment_template_projection,
)
from .state_machine import utc_now_iso


PROFILE_SEGMENT_ROUTE_FAMILY = "/api/admin/automation-conversion/profile-segment-templates*"
PROFILE_SEGMENT_BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
PROFILE_SEGMENT_BACKEND_ENV_FALLBACK = "PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
PROFILE_SEGMENT_DATABASE_URL_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_DATABASE_URL"
PROFILE_SEGMENT_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}


class ProfileSegmentTemplateIdempotencyConflict(ContractError):
    status_code = 409


def profile_segment_template_repository_backend() -> str:
    return str(
        os.getenv(PROFILE_SEGMENT_BACKEND_ENV)
        or os.getenv(PROFILE_SEGMENT_BACKEND_ENV_FALLBACK)
        or "memory"
    ).strip().lower()


def profile_segment_template_sqlalchemy_enabled() -> bool:
    return profile_segment_template_repository_backend() in PROFILE_SEGMENT_SQL_BACKENDS


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


def _enabled_from_status(status: str) -> bool:
    return str(status or "").strip().lower() == "active"


def _status_from_enabled(value: Any) -> str:
    return "active" if bool(value) else "inactive"


def _source_status() -> str:
    return "sql_alchemy_profile_segment_repository"


class SqlAlchemyProfileSegmentTemplateRepository:
    """Opt-in production repository adapter for profile segment template metadata only."""

    source_status = _source_status()

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def profile_segment_template_catalog(self) -> dict[str, Any]:
        try:
            with self._engine.connect() as conn:
                rows, total = self._list_templates(conn, enabled_only=False, program_id=None, limit=500, offset=0)
            return {
                "source_status": self.source_status,
                "items": rows,
                "total": total,
                "warnings": ["catalog_uses_profile_segment_template_table_projection"],
            }
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"profile segment template repository unavailable: {exc}") from exc

    def list_profile_segment_templates(
        self,
        *,
        enabled_only: bool = False,
        program_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            with self._engine.connect() as conn:
                return self._list_templates(
                    conn,
                    enabled_only=enabled_only,
                    program_id=program_id,
                    limit=limit,
                    offset=offset,
                )
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"profile segment template repository unavailable: {exc}") from exc

    def get_profile_segment_template(self, template_id: int) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                return self._load_template(conn, int(template_id))
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"profile segment template repository unavailable: {exc}") from exc

    def create_profile_segment_template(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_profile_segment_template_payload(payload)
        request_hash = _request_hash(normalized)
        try:
            with self._engine.begin() as conn:
                replay = self._load_idempotency(conn, operation="create", operator=operator_id, idempotency_key=key)
                if replay:
                    if replay.get("request_hash") != request_hash:
                        raise ProfileSegmentTemplateIdempotencyConflict("idempotency key conflicts with a different request payload")
                    response = _json_loads(replay.get("response_snapshot"), {})
                    if isinstance(response, dict):
                        response["idempotent_replay"] = True
                        response["source_status"] = self.source_status
                        return response
                self._assert_unique(conn, normalized["name"], normalized["code"])
                self._insert_idempotency_pending(conn, operation="create", operator=operator_id, idempotency_key=key, request_hash=request_hash)
                template_id = self._insert_parent(conn, normalized, operator=operator_id)
                self._replace_categories(conn, template_id, normalized)
                after = self._load_template(conn, template_id) or {}
                rollback = {
                    "strategy": "compensating_update_or_status_revert",
                    "created_template_id": template_id,
                    "delete_approved": False,
                    "disable_payload": {"status": "inactive", "enabled": False},
                }
                audit_event = self._insert_audit_event(
                    conn,
                    operation="create",
                    operator=operator_id,
                    resource_id=template_id,
                    before={},
                    after=after,
                    request_payload=normalized,
                    validation_result={"ok": True},
                    rollback_payload=rollback,
                )
                result = {
                    "source_status": self.source_status,
                    "template": after,
                    "template_bundle": {"template": after},
                    "audit_event": audit_event,
                    "rollback": rollback,
                    "idempotent_replay": False,
                }
                self._mark_idempotency_succeeded(
                    conn,
                    operation="create",
                    operator=operator_id,
                    idempotency_key=key,
                    resource_id=template_id,
                    response_snapshot=result,
                )
                return deepcopy(result)
        except (ContractError, NotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"profile segment template repository unavailable: {exc}") from exc

    def update_profile_segment_template(self, template_id: int, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        operator_id = str(operator or "system").strip() or "system"
        try:
            with self._engine.begin() as conn:
                before = self._load_template(conn, int(template_id))
                if not before:
                    raise NotFoundError("profile segment template not found")
                normalized = normalize_profile_segment_template_payload(payload, partial=True, existing=before)
                self._assert_unique(conn, normalized["name"], normalized["code"], exclude_id=int(template_id))
                conn.execute(
                    text(
                        """
                        UPDATE automation_profile_segment_template
                        SET template_code = :template_code,
                            template_name = :template_name,
                            description = :description,
                            enabled = :enabled,
                            version = COALESCE(version, 1) + 1,
                            updated_by = :updated_by,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :template_id
                        """
                    ),
                    {
                        "template_code": normalized["code"],
                        "template_name": normalized["name"],
                        "description": normalized["description"],
                        "enabled": _enabled_from_status(normalized["status"]),
                        "updated_by": operator_id,
                        "template_id": int(template_id),
                    },
                )
                self._replace_categories(conn, int(template_id), normalized)
                after = self._load_template(conn, int(template_id)) or {}
                rollback = {
                    "strategy": "restore_before_snapshot",
                    "template_id": int(template_id),
                    "before": before,
                    "after": after,
                    "optimistic_locking": "future_phase_required",
                }
                audit_event = self._insert_audit_event(
                    conn,
                    operation="update",
                    operator=operator_id,
                    resource_id=int(template_id),
                    before=before,
                    after=after,
                    request_payload=normalized,
                    validation_result={"ok": True, "warnings": ["optimistic_locking_not_enforced_in_phase_4i"]},
                    rollback_payload=rollback,
                )
                return {
                    "source_status": self.source_status,
                    "template": after,
                    "template_bundle": {"template": after},
                    "audit_event": audit_event,
                    "rollback": rollback,
                    "warnings": ["optimistic_locking_not_enforced_in_phase_4i"],
                }
        except (ContractError, NotFoundError):
            raise
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"profile segment template repository unavailable: {exc}") from exc

    def list_profile_segment_template_audit_events(self) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM automation_profile_segment_template_audit_log
                        ORDER BY id DESC
                        """
                    )
                ).fetchall()
            return [self._audit_row_to_event(_as_mapping(row) or {}) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryProviderError(f"profile segment template repository unavailable: {exc}") from exc

    def _list_templates(
        self,
        conn: Connection,
        *,
        enabled_only: bool,
        program_id: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        if enabled_only:
            conditions.append("enabled = :enabled")
            params["enabled"] = True
        if program_id is not None:
            conditions.append("program_id = :program_id")
            params["program_id"] = int(program_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(
            conn.execute(
                text(f"SELECT COUNT(*) AS count FROM automation_profile_segment_template {where}"),
                params,
            ).scalar()
            or 0
        )
        rows = conn.execute(
            text(
                f"""
                SELECT *
                FROM automation_profile_segment_template
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).fetchall()
        items = [self._template_from_parent(conn, _as_mapping(row) or {}) for row in rows]
        return items, total

    def _load_template(self, conn: Connection, template_id: int) -> dict[str, Any] | None:
        row = conn.execute(
            text("SELECT * FROM automation_profile_segment_template WHERE id = :template_id LIMIT 1"),
            {"template_id": int(template_id)},
        ).fetchone()
        mapping = _as_mapping(row)
        if not mapping:
            return None
        return self._template_from_parent(conn, mapping)

    def _template_from_parent(self, conn: Connection, parent: dict[str, Any]) -> dict[str, Any]:
        template_id = int(parent.get("id") or 0)
        categories = self._load_categories(conn, template_id)
        sort_order = categories[0].get("sort_order", 0) if categories else 0
        projected = profile_segment_template_projection(
            {
                "id": template_id,
                "template_name": parent.get("template_name"),
                "template_code": parent.get("template_code"),
                "description": parent.get("description"),
                "status": _status_from_enabled(parent.get("enabled")),
                "sort_order": sort_order,
                "rules": {"categories": categories},
                "conditions": {},
                "created_at": parent.get("created_at"),
                "updated_at": parent.get("updated_at"),
            }
        )
        projected.update(
            {
                "program_id": parent.get("program_id"),
                "questionnaire_id": parent.get("questionnaire_id"),
                "segmentation_question_id": parent.get("segmentation_question_id"),
                "version": parent.get("version"),
                "created_by": parent.get("created_by") or "",
                "updated_by": parent.get("updated_by") or "",
                "warnings": ["draft_status_maps_to_enabled_false_until_owner_approval"]
                if not parent.get("enabled")
                else [],
            }
        )
        return projected

    def _load_categories(self, conn: Connection, template_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM automation_profile_segment_category
                WHERE template_id = :template_id
                ORDER BY sort_order ASC, id ASC
                """
            ),
            {"template_id": int(template_id)},
        ).fetchall()
        categories: list[dict[str, Any]] = []
        for row in rows:
            category = _as_mapping(row) or {}
            category_id = int(category.get("id") or 0)
            categories.append(
                {
                    "id": category_id,
                    "category_id": category_id,
                    "category_key": category.get("category_key") or "",
                    "category_name": category.get("category_name") or "",
                    "description": category.get("description") or "",
                    "sort_order": int(category.get("sort_order") or 0),
                    "enabled": bool(category.get("enabled")),
                    "option_mappings": self._load_option_mappings(conn, template_id, category_id),
                }
            )
        return categories

    def _load_option_mappings(self, conn: Connection, template_id: int, category_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM automation_profile_segment_option_mapping
                WHERE template_id = :template_id AND category_id = :category_id
                ORDER BY id ASC
                """
            ),
            {"template_id": int(template_id), "category_id": int(category_id)},
        ).fetchall()
        return [
            {
                "id": int((_as_mapping(row) or {}).get("id") or 0),
                "question_id": int((_as_mapping(row) or {}).get("question_id") or 0),
                "option_id": int((_as_mapping(row) or {}).get("option_id") or 0),
            }
            for row in rows
        ]

    def _load_idempotency(self, conn: Connection, *, operation: str, operator: str, idempotency_key: str) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM automation_profile_segment_template_idempotency
                WHERE route_family = :route_family
                  AND operation = :operation
                  AND operator = :operator
                  AND idempotency_key = :idempotency_key
                LIMIT 1
                """
            ),
            {
                "route_family": PROFILE_SEGMENT_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "idempotency_key": idempotency_key,
            },
        ).fetchone()
        return _as_mapping(row)

    def _insert_idempotency_pending(
        self,
        conn: Connection,
        *,
        operation: str,
        operator: str,
        idempotency_key: str,
        request_hash: str,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO automation_profile_segment_template_idempotency (
                    route_family,
                    operation,
                    operator,
                    idempotency_key,
                    request_hash,
                    response_snapshot,
                    resource_type,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    :route_family,
                    :operation,
                    :operator,
                    :idempotency_key,
                    :request_hash,
                    :response_snapshot,
                    'profile_segment_template',
                    'pending',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "route_family": PROFILE_SEGMENT_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "response_snapshot": _json_dumps({}),
            },
        )

    def _mark_idempotency_succeeded(
        self,
        conn: Connection,
        *,
        operation: str,
        operator: str,
        idempotency_key: str,
        resource_id: int,
        response_snapshot: dict[str, Any],
    ) -> None:
        conn.execute(
            text(
                """
                UPDATE automation_profile_segment_template_idempotency
                SET resource_id = :resource_id,
                    response_snapshot = :response_snapshot,
                    status = 'succeeded',
                    updated_at = CURRENT_TIMESTAMP
                WHERE route_family = :route_family
                  AND operation = :operation
                  AND operator = :operator
                  AND idempotency_key = :idempotency_key
                """
            ),
            {
                "resource_id": int(resource_id),
                "response_snapshot": _json_dumps(response_snapshot),
                "route_family": PROFILE_SEGMENT_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "idempotency_key": idempotency_key,
            },
        )

    def _insert_parent(self, conn: Connection, normalized: dict[str, Any], *, operator: str) -> int:
        row = conn.execute(
            text(
                """
                INSERT INTO automation_profile_segment_template (
                    template_code,
                    template_name,
                    description,
                    enabled,
                    version,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at
                )
                VALUES (
                    :template_code,
                    :template_name,
                    :description,
                    :enabled,
                    1,
                    :created_by,
                    :updated_by,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                RETURNING id
                """
            ),
            {
                "template_code": normalized["code"],
                "template_name": normalized["name"],
                "description": normalized["description"],
                "enabled": _enabled_from_status(normalized["status"]),
                "created_by": operator,
                "updated_by": operator,
            },
        ).fetchone()
        mapping = _as_mapping(row) or {}
        return int(mapping.get("id") or 0)

    def _replace_categories(self, conn: Connection, template_id: int, normalized: dict[str, Any]) -> None:
        conn.execute(
            text("DELETE FROM automation_profile_segment_option_mapping WHERE template_id = :template_id"),
            {"template_id": int(template_id)},
        )
        conn.execute(
            text("DELETE FROM automation_profile_segment_category WHERE template_id = :template_id"),
            {"template_id": int(template_id)},
        )
        for category in self._categories_from_payload(normalized):
            row = conn.execute(
                text(
                    """
                    INSERT INTO automation_profile_segment_category (
                        template_id,
                        category_key,
                        category_name,
                        description,
                        sort_order,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :template_id,
                        :category_key,
                        :category_name,
                        :description,
                        :sort_order,
                        :enabled,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """
                ),
                {
                    "template_id": int(template_id),
                    "category_key": category["category_key"],
                    "category_name": category["category_name"],
                    "description": category["description"],
                    "sort_order": int(category["sort_order"]),
                    "enabled": bool(category["enabled"]),
                },
            ).fetchone()
            category_id = int((_as_mapping(row) or {}).get("id") or 0)
            for mapping in category.get("option_mappings") or []:
                conn.execute(
                    text(
                        """
                        INSERT INTO automation_profile_segment_option_mapping (
                            template_id,
                            category_id,
                            question_id,
                            option_id,
                            created_at
                        )
                        VALUES (
                            :template_id,
                            :category_id,
                            :question_id,
                            :option_id,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "template_id": int(template_id),
                        "category_id": int(category_id),
                        "question_id": int(mapping["question_id"]),
                        "option_id": int(mapping["option_id"]),
                    },
                )

    def _categories_from_payload(self, normalized: dict[str, Any]) -> list[dict[str, Any]]:
        rules = normalized.get("rules")
        raw_categories = rules.get("categories") if isinstance(rules, dict) else []
        categories: list[dict[str, Any]] = []
        if isinstance(raw_categories, list):
            for index, item in enumerate(raw_categories, start=1):
                if not isinstance(item, dict):
                    continue
                option_mappings = []
                for mapping in item.get("option_mappings") or item.get("mappings") or []:
                    if not isinstance(mapping, dict):
                        continue
                    if mapping.get("question_id") is None or mapping.get("option_id") is None:
                        continue
                    option_mappings.append(
                        {
                            "question_id": int(mapping.get("question_id") or 0),
                            "option_id": int(mapping.get("option_id") or 0),
                        }
                    )
                categories.append(
                    {
                        "category_key": str(item.get("category_key") or item.get("key") or f"{normalized['code']}_{index}"),
                        "category_name": str(item.get("category_name") or item.get("name") or normalized["name"]),
                        "description": str(item.get("description") or ""),
                        "sort_order": int(item.get("sort_order") or normalized.get("sort_order") or 0),
                        "enabled": bool(item.get("enabled", True)),
                        "option_mappings": option_mappings,
                    }
                )
        if categories:
            return categories
        return [
            {
                "category_key": normalized["code"],
                "category_name": normalized["name"],
                "description": normalized.get("description") or "",
                "sort_order": int(normalized.get("sort_order") or 0),
                "enabled": True,
                "option_mappings": [],
            }
        ]

    def _assert_unique(self, conn: Connection, name: str, code: str, *, exclude_id: int | None = None) -> None:
        params: dict[str, Any] = {
            "name": str(name or "").strip().lower(),
            "code": str(code or "").strip().lower(),
        }
        exclude = ""
        if exclude_id is not None:
            exclude = "AND id <> :exclude_id"
            params["exclude_id"] = int(exclude_id)
        row = conn.execute(
            text(
                f"""
                SELECT id
                FROM automation_profile_segment_template
                WHERE (LOWER(template_name) = :name OR LOWER(template_code) = :code)
                {exclude}
                LIMIT 1
                """
            ),
            params,
        ).fetchone()
        if row:
            raise ContractError("profile segment template name or code already exists")

    def _insert_audit_event(
        self,
        conn: Connection,
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
        safety = profile_segment_side_effect_safety()
        row = conn.execute(
            text(
                """
                INSERT INTO automation_profile_segment_template_audit_log (
                    route_family,
                    operation,
                    operator,
                    resource_type,
                    resource_id,
                    before_snapshot,
                    after_snapshot,
                    request_payload,
                    validation_result,
                    rollback_payload,
                    side_effect_safety,
                    created_at
                )
                VALUES (
                    :route_family,
                    :operation,
                    :operator,
                    'profile_segment_template',
                    :resource_id,
                    :before_snapshot,
                    :after_snapshot,
                    :request_payload,
                    :validation_result,
                    :rollback_payload,
                    :side_effect_safety,
                    CURRENT_TIMESTAMP
                )
                RETURNING *
                """
            ),
            {
                "route_family": PROFILE_SEGMENT_ROUTE_FAMILY,
                "operation": operation,
                "operator": operator,
                "resource_id": int(resource_id),
                "before_snapshot": _json_dumps(before),
                "after_snapshot": _json_dumps(after),
                "request_payload": _json_dumps(request_payload),
                "validation_result": _json_dumps(validation_result),
                "rollback_payload": _json_dumps(rollback_payload),
                "side_effect_safety": _json_dumps(safety),
            },
        ).fetchone()
        return self._audit_row_to_event(_as_mapping(row) or {})

    def _audit_row_to_event(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row.get("id") or 0),
            "action": row.get("operation") or "",
            "operation": row.get("operation") or "",
            "route_family": row.get("route_family") or PROFILE_SEGMENT_ROUTE_FAMILY,
            "template_id": row.get("resource_id"),
            "resource_id": row.get("resource_id"),
            "operator_id": row.get("operator") or "",
            "before": _json_loads(row.get("before_snapshot"), {}),
            "after": _json_loads(row.get("after_snapshot"), {}),
            "request_payload": _json_loads(row.get("request_payload"), {}),
            "validation_result": _json_loads(row.get("validation_result"), {}),
            "rollback_payload": _json_loads(row.get("rollback_payload"), {}),
            "side_effect_safety": _json_loads(row.get("side_effect_safety"), profile_segment_side_effect_safety()),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "external_event_dispatched": False,
        }


def build_profile_segment_template_repository(
    *,
    backend: str | None = None,
    engine: Engine | None = None,
) -> Any:
    selected_backend = str(backend or profile_segment_template_repository_backend()).strip().lower()
    if selected_backend in PROFILE_SEGMENT_SQL_BACKENDS:
        if engine is None:
            settings = get_settings()
            database_url = (
                os.getenv(PROFILE_SEGMENT_DATABASE_URL_ENV)
                or os.getenv("AICRM_NEXT_TEST_DATABASE_URL")
                or settings.database_url
            )
            engine = get_engine(database_url)
        return assert_repository_allowed(
            SqlAlchemyProfileSegmentTemplateRepository(engine),
            capability_owner="automation_engine.profile_segment_template",
        )

    from .repo import _fixture_repo

    return assert_repository_allowed(
        _fixture_repo,
        capability_owner="automation_engine.profile_segment_template",
    )
