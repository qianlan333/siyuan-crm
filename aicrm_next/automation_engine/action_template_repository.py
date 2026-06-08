from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.errors import ContractError
from aicrm_next.shared.repository_provider import RepositoryProviderError, assert_repository_allowed

from .action_templates import (
    ACTION_TEMPLATE_ROUTE_FAMILY,
    action_template_projection,
    action_template_side_effect_safety,
    normalize_action_template_create_payload,
)
from .state_machine import utc_now_iso


class ActionTemplateIdempotencyConflict(ContractError):
    status_code = 409


ACTION_TEMPLATE_BACKEND_ENV = "AICRM_ACTION_TEMPLATES_REPO_BACKEND"
ACTION_TEMPLATE_DATABASE_URL_ENV = "AICRM_ACTION_TEMPLATES_DATABASE_URL"
ACTION_TEMPLATE_SQL_BACKENDS = {"sql", "sqlalchemy", "postgres", "postgresql"}


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _fixture_action_templates() -> list[dict[str, Any]]:
    return [
        action_template_projection(
            {
                "id": 1,
                "template_code": "fixture_crm_followup_note",
                "template_name": "Fixture CRM 跟进记录",
                "template_source": "crm_local",
                "category": "crm_metadata",
                "description": "Fixture/local action-template metadata only.",
                "status": "active",
                "default_config": {"channel": "fixture"},
                "ui_schema": {"fields": ["note"]},
                "workflow_blueprint": {},
                "node_blueprints": [],
                "created_by": "fixture",
                "updated_by": "fixture",
                "created_at": "2026-05-20T09:00:00Z",
                "updated_at": "2026-05-20T09:00:00Z",
            }
        ),
        action_template_projection(
            {
                "id": 2,
                "template_code": "fixture_builtin_readonly",
                "template_name": "Fixture Builtin Readonly",
                "template_source": "builtin",
                "category": "readonly",
                "description": "Readonly builtin fixture for list parity shape.",
                "status": "active",
                "default_config": {},
                "ui_schema": {},
                "workflow_blueprint": {},
                "node_blueprints": [],
                "created_by": "fixture",
                "updated_by": "fixture",
                "created_at": "2026-05-20T09:05:00Z",
                "updated_at": "2026-05-20T09:05:00Z",
            }
        ),
    ]


class InMemoryActionTemplateRepository:
    source_status = "fixture_local_contract"

    def __init__(self, templates: list[dict[str, Any]] | None = None) -> None:
        self._templates = {int(item["id"]): action_template_projection(item) for item in (templates or _fixture_action_templates())}
        self._idempotency: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._audit_events: list[dict[str, Any]] = []

    def list_action_templates(self, filters: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        template_source = str(filters.get("template_source") or "").strip()
        category = str(filters.get("category") or "").strip()
        keyword = str(filters.get("keyword") or "").strip().lower()
        include_archived = bool(filters.get("include_archived"))
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("offset") or 0)

        rows = [action_template_projection(item) for item in self._templates.values()]
        if template_source:
            rows = [item for item in rows if item.get("template_source") == template_source]
        if category:
            rows = [item for item in rows if item.get("category") == category]
        if not include_archived:
            rows = [item for item in rows if item.get("status") != "archived"]
        if keyword:
            rows = [
                item
                for item in rows
                if keyword
                in f"{item.get('template_name', '')} {item.get('description', '')} {item.get('category', '')}".lower()
            ]
        rows.sort(key=lambda item: (str(item.get("template_source") or ""), int(item.get("id") or 0)))
        total = len(rows)
        return deepcopy(rows[offset : offset + limit]), total

    def create_action_template(self, payload: dict[str, Any], *, idempotency_key: str, operator: str) -> dict[str, Any]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ContractError("idempotency_key is required")
        operator_id = str(operator or "system").strip() or "system"
        normalized = normalize_action_template_create_payload({**payload, "operator": operator_id})
        request_hash = _request_hash(normalized)
        idempotency_scope = (ACTION_TEMPLATE_ROUTE_FAMILY, "create", operator_id, key)
        replay = self._idempotency.get(idempotency_scope)
        if replay:
            if replay.get("request_hash") != request_hash:
                raise ActionTemplateIdempotencyConflict("idempotency key conflicts with a different request payload")
            response = deepcopy(replay.get("response_snapshot") or {})
            response["idempotent_replay"] = True
            return response

        self._assert_unique_template_code(normalized["template_code"])
        now = utc_now_iso()
        template_id = max(self._templates) + 1 if self._templates else 1
        saved = action_template_projection(
            {
                **normalized,
                "id": template_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        self._templates[template_id] = deepcopy(saved)
        rollback_payload = {
            "strategy": "archive_created_template_in_later_approved_phase",
            "created_template_id": template_id,
            "template_code": saved["template_code"],
            "delete_approved": False,
        }
        audit_event = self._append_audit_event(
            operation="create",
            operator=operator_id,
            resource_id=template_id,
            before={},
            after=saved,
            request_payload=normalized,
            rollback_payload=rollback_payload,
        )
        result = {
            "template": deepcopy(saved),
            "items": [deepcopy(saved)],
            "audit_event": audit_event,
            "rollback_payload": rollback_payload,
            "idempotent_replay": False,
        }
        self._idempotency[idempotency_scope] = {
            "request_hash": request_hash,
            "response_snapshot": deepcopy(result),
            "resource_id": template_id,
            "status": "succeeded",
        }
        return result

    def list_action_template_audit_events(self) -> list[dict[str, Any]]:
        return deepcopy(self._audit_events)

    def _assert_unique_template_code(self, template_code: str) -> None:
        normalized_code = str(template_code or "").strip().lower()
        for item in self._templates.values():
            if str(item.get("template_code") or "").strip().lower() == normalized_code:
                raise ContractError("action template code already exists")

    def _append_audit_event(
        self,
        *,
        operation: str,
        operator: str,
        resource_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        request_payload: dict[str, Any],
        rollback_payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "route_family": ACTION_TEMPLATE_ROUTE_FAMILY,
            "operation": operation,
            "operator": str(operator or "system"),
            "resource_type": "action_template",
            "resource_id": int(resource_id),
            "before_snapshot": deepcopy(before),
            "after_snapshot": deepcopy(after),
            "request_payload": deepcopy(request_payload),
            "validation_result": {"ok": True},
            "rollback_payload": deepcopy(rollback_payload),
            "side_effect_safety": action_template_side_effect_safety(),
            "created_at": utc_now_iso(),
        }
        self._audit_events.insert(0, event)
        return deepcopy(event)


_fixture_action_template_repo = InMemoryActionTemplateRepository()


def action_template_repository_backend() -> str:
    return str(os.getenv(ACTION_TEMPLATE_BACKEND_ENV) or "fixture").strip().lower()


def action_template_sqlalchemy_enabled() -> bool:
    return action_template_repository_backend() in ACTION_TEMPLATE_SQL_BACKENDS


def build_action_template_repository(*, backend: str | None = None, engine: Any | None = None) -> Any:
    selected_backend = str(backend or action_template_repository_backend()).strip().lower()
    if selected_backend in ACTION_TEMPLATE_SQL_BACKENDS:
        if engine is None:
            database_url = str(os.getenv(ACTION_TEMPLATE_DATABASE_URL_ENV) or "").strip()
            if not database_url:
                raise RepositoryProviderError(
                    f"{ACTION_TEMPLATE_DATABASE_URL_ENV} is required when {ACTION_TEMPLATE_BACKEND_ENV}=sqlalchemy"
                )
            engine = get_engine(database_url)
        from .action_template_sqlalchemy_repository import SqlAlchemyActionTemplateRepository

        return assert_repository_allowed(
            SqlAlchemyActionTemplateRepository(engine),
            capability_owner="aicrm_next.automation_engine.action_templates",
        )

    return assert_repository_allowed(
        _fixture_action_template_repo,
        capability_owner="aicrm_next.automation_engine",
    )


def reset_action_template_fixture_state() -> None:
    global _fixture_action_template_repo
    _fixture_action_template_repo = InMemoryActionTemplateRepository()
