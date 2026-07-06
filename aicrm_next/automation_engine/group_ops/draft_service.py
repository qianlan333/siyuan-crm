from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any
from uuid import uuid4

from aicrm_next.shared.errors import ContractError, NotFoundError

from .draft_repository import GroupOpsWorkspaceDraftRepository, build_group_ops_workspace_draft_repository


FORBIDDEN_KEY_FRAGMENTS = (
    "raw_receiver",
    "receiver_plaintext",
    "raw_external_userid",
    "external_userid",
    "phone",
    "mobile",
    "raw_chat",
    "raw_member",
    "openid",
    "unionid",
    "token",
    "secret",
    "authorization",
    "raw_message_body",
    "raw_callback_body",
    "target_list",
    "raw_target",
)
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:", re.IGNORECASE),
)
ALLOWED_ITEM_TYPES = {"plan", "group", "node", "execution", "push_center", "evidence", "config"}
ALLOWED_DRAFT_STATUSES = {"draft", "ready_for_review", "archived", "rejected"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_clone(value: Any, default: Any) -> Any:
    if value is None:
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    return deepcopy(default)


def _canonical_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _actor_id(actor: dict[str, Any]) -> str:
    return _text(actor.get("username") or actor.get("wecom_userid") or actor.get("user_id") or actor.get("sub") or "admin")


def _actor_label(actor: dict[str, Any]) -> str:
    return _text(actor.get("display_name") or actor.get("name") or actor.get("username") or "admin")


def _actor_metadata(actor: dict[str, Any]) -> dict[str, Any]:
    roles = actor.get("roles") if isinstance(actor.get("roles"), list) else []
    return {
        "auth_source": _text(actor.get("auth_source")),
        "login_type": _text(actor.get("login_type")),
        "roles": [_text(role) for role in roles if _text(role)],
    }


def _audit_metadata(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_status": draft.get("draft_status"),
        "version": int(draft.get("version") or 0),
        "source_plan_id": draft.get("source_plan_id"),
        "snapshot_hash": draft.get("snapshot_hash"),
        "item_count": len(draft.get("items") or []),
    }


def _raise_if_sensitive(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = _text(raw_key).lower()
            if any(fragment in key for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise ContractError(f"sensitive field rejected: {path}.{raw_key}")
            _raise_if_sensitive(item, path=f"{path}.{raw_key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _raise_if_sensitive(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        lowered = value.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
            raise ContractError(f"sensitive value rejected: {path}")
        for pattern in FORBIDDEN_VALUE_PATTERNS:
            if pattern.search(value):
                raise ContractError(f"sensitive value rejected: {path}")


def _normalized_items(raw_items: Any) -> list[dict[str, Any]]:
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raise ContractError("items must be a list")
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ContractError("each item must be an object")
        item_type = _text(raw.get("item_type"))
        if item_type not in ALLOWED_ITEM_TYPES:
            raise ContractError("invalid item_type")
        item = {
            "item_type": item_type,
            "item_ref_id": _text(raw.get("item_ref_id")),
            "item_order": int(raw.get("item_order") if raw.get("item_order") is not None else index),
            "sanitized_item": _json_clone(raw.get("sanitized_item"), {}),
            "guardrail_summary": _json_clone(raw.get("guardrail_summary"), {}),
        }
        _raise_if_sensitive(item)
        items.append(item)
    return items


def _normalize_save_payload(payload: dict[str, Any], actor: dict[str, Any], *, draft_id: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    _raise_if_sensitive(payload)
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise ContractError("idempotency_key is required")
    source_plan_id = _text(payload.get("source_plan_id"))
    sanitized_payload = _json_clone(payload.get("sanitized_payload"), {})
    guardrail_summary = _json_clone(payload.get("guardrail_summary"), {})
    approval_requirements = _json_clone(payload.get("approval_requirements"), {})
    items = _normalized_items(payload.get("items"))
    hash_input = {
        "source_plan_id": source_plan_id,
        "sanitized_payload": sanitized_payload,
        "guardrail_summary": guardrail_summary,
        "approval_requirements": approval_requirements,
        "items": items,
    }
    return {
        "draft_id": draft_id or f"gowd_{uuid4().hex}",
        "tenant_id": _text(payload.get("tenant_id")) or "aicrm",
        "admin_scope": _text(payload.get("admin_scope")),
        "source_plan_id": source_plan_id,
        "idempotency_key": idempotency_key,
        "snapshot_hash": _snapshot_hash(hash_input),
        "sanitized_payload": sanitized_payload,
        "guardrail_summary": guardrail_summary,
        "approval_requirements": approval_requirements,
        "items": items,
        "actor_id": _actor_id(actor),
        "actor_label": _actor_label(actor),
        "actor_metadata": _actor_metadata(actor),
    }


def _normalize_request_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    _raise_if_sensitive(payload)
    expected_version = int(payload.get("version") or 0)
    if expected_version <= 0:
        raise ContractError("version is required")
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise ContractError("idempotency_key is required")
    review_note = _text(payload.get("review_note"))
    client_snapshot_hash = _text(payload.get("client_snapshot_hash"))
    normalized = {
        "version": expected_version,
        "idempotency_key": idempotency_key,
        "review_note": review_note,
        "client_snapshot_hash": client_snapshot_hash,
    }
    return {
        **normalized,
        "request_review_payload_hash": _snapshot_hash(normalized),
    }


def _envelope(
    draft: dict[str, Any],
    *,
    operation: str,
    production_write: bool,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "draft_id": draft.get("draft_id"),
        "draft_status": draft.get("draft_status"),
        "version": draft.get("version"),
        "source_plan_id": draft.get("source_plan_id"),
        "snapshot_hash": draft.get("snapshot_hash"),
        "sanitized_payload": draft.get("sanitized_payload") or {},
        "guardrail_summary": draft.get("guardrail_summary") or {},
        "approval_requirements": draft.get("approval_requirements") or {},
        "items": draft.get("items") or [],
        "created_at": draft.get("created_at"),
        "updated_at": draft.get("updated_at"),
        "archived_at": draft.get("archived_at"),
        "preview_only": True,
        "production_write": production_write,
        "production_write_scope": "draft_tables_only" if production_write else "none",
        "ready_for_review": draft.get("draft_status") == "ready_for_review",
        "approved": False,
        "real_external_call": False,
        "real_external_call_executed": False,
        "push_center_job_created": False,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
        "can_claim_pass_90_plus": False,
        "execution_status": "not_execution",
        "idempotent_replay": idempotent_replay,
        "route_owner": "ai_crm_next",
        "capability_owner": "automation_engine",
    }


class GroupOpsWorkspaceDraftService:
    def __init__(self, repo: GroupOpsWorkspaceDraftRepository | None = None) -> None:
        self.repo = repo or build_group_ops_workspace_draft_repository()

    def list_drafts(self, filters: dict[str, Any]) -> dict[str, Any]:
        status = _text(filters.get("status"))
        if status and status not in ALLOWED_DRAFT_STATUSES:
            raise ContractError("invalid draft status")
        items, total = self.repo.list_drafts(filters)
        return {
            "ok": True,
            "items": [_envelope(item, operation="list_item", production_write=False) for item in items],
            "total": total,
            "preview_only": True,
            "production_write": False,
            "real_external_call": False,
            "real_external_call_executed": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
            "can_claim_pass_90_plus": False,
            "execution_status": "not_execution",
            "route_owner": "ai_crm_next",
            "capability_owner": "automation_engine",
        }

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        draft = self.repo.get_draft(_text(draft_id))
        if not draft:
            raise NotFoundError("draft not found")
        return _envelope(draft, operation="get", production_write=False)

    def create_draft(self, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_save_payload(payload, actor)
        existing = self.repo.find_by_idempotency_key(
            tenant_id=normalized["tenant_id"],
            admin_scope=normalized["admin_scope"],
            idempotency_key=normalized["idempotency_key"],
        )
        if existing:
            if existing.get("snapshot_hash") != normalized["snapshot_hash"]:
                raise ContractError("idempotency key conflict")
            return _envelope(existing, operation="create", production_write=False, idempotent_replay=True)
        draft = self.repo.create_draft(normalized, audit_metadata=_audit_metadata({**normalized, "version": 1, "draft_status": "draft"}))
        return _envelope(draft, operation="create", production_write=True)

    def update_draft(self, draft_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        current = self.repo.get_draft(_text(draft_id))
        if not current:
            raise NotFoundError("draft not found")
        expected_version = int(payload.get("version") or 0) if isinstance(payload, dict) else 0
        if expected_version <= 0:
            raise ContractError("version is required")
        normalized = _normalize_save_payload(payload, actor, draft_id=_text(draft_id))
        updated = self.repo.update_draft(
            _text(draft_id),
            normalized,
            expected_version=expected_version,
            before_metadata=_audit_metadata(current),
            after_metadata=_audit_metadata({**normalized, "version": expected_version + 1, "draft_status": current.get("draft_status")}),
        )
        return _envelope(updated, operation="update", production_write=True)

    def archive_draft(self, draft_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ContractError("request body must be a JSON object")
        _raise_if_sensitive(payload)
        current = self.repo.get_draft(_text(draft_id))
        if not current:
            raise NotFoundError("draft not found")
        expected_version = int(payload.get("version") or 0)
        if expected_version <= 0:
            raise ContractError("version is required")
        after = {**_audit_metadata(current), "draft_status": "archived", "archive_reason": _text(payload.get("archive_reason"))}
        archived = self.repo.archive_draft(
            _text(draft_id),
            expected_version=expected_version,
            actor_id=_actor_id(actor),
            actor_label=_actor_label(actor),
            actor_metadata=_actor_metadata(actor),
            before_metadata=_audit_metadata(current),
            after_metadata=after,
        )
        return _envelope(archived, operation="archive", production_write=True)

    def request_review(self, draft_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_request_review_payload(payload)
        current = self.repo.get_draft(_text(draft_id))
        if not current:
            raise NotFoundError("draft not found")

        existing_review = self.repo.find_request_review_audit(
            draft_id=_text(draft_id),
            idempotency_key=normalized["idempotency_key"],
        )
        if existing_review:
            after_metadata = existing_review.get("after_metadata") or {}
            if after_metadata.get("request_review_payload_hash") != normalized["request_review_payload_hash"]:
                raise ContractError("request-review idempotency key conflict")
            return _envelope(current, operation="request_review", production_write=False, idempotent_replay=True)

        expected_version = int(normalized["version"])
        if int(current.get("version") or 0) != expected_version:
            raise ContractError("draft version conflict")
        if current.get("draft_status") == "archived":
            raise ContractError("archived draft cannot request review")
        if current.get("draft_status") == "rejected":
            raise ContractError("rejected draft cannot request review")
        if current.get("draft_status") == "ready_for_review":
            raise ContractError("draft already ready_for_review")
        if current.get("draft_status") != "draft":
            raise ContractError("draft status cannot request review")
        if normalized["client_snapshot_hash"] and normalized["client_snapshot_hash"] != _text(current.get("snapshot_hash")):
            raise ContractError("draft snapshot conflict")

        after_metadata = {
            **_audit_metadata(current),
            "draft_status": "ready_for_review",
            "request_review_idempotency_key": normalized["idempotency_key"],
            "request_review_payload_hash": normalized["request_review_payload_hash"],
            "review_note_present": bool(normalized["review_note"]),
            "client_snapshot_hash": normalized["client_snapshot_hash"],
            "approved": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
        }
        reviewed = self.repo.request_review_draft(
            _text(draft_id),
            expected_version=expected_version,
            actor_id=_actor_id(actor),
            actor_label=_actor_label(actor),
            actor_metadata=_actor_metadata(actor),
            before_metadata=_audit_metadata(current),
            after_metadata=after_metadata,
        )
        return _envelope(reviewed, operation="request_review", production_write=True)
