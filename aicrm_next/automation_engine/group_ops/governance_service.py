from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aicrm_next.shared.errors import ContractError, NotFoundError

from .draft_service import _actor_id, _actor_label, _actor_metadata, _raise_if_sensitive, _text
from .governance_repository import (
    GroupOpsWorkspaceGovernanceRepository,
    build_group_ops_workspace_governance_repository,
)


REQUIRED_STEP_TYPES = ("operator_approval", "receiver_allowlist", "gray_window")


def _json_clone(value: Any, default: Any) -> Any:
    if value is None:
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    return deepcopy(default)


def _canonical_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_datetime(value: Any, *, field: str) -> datetime:
    raw = _text(value)
    if not raw:
        raise ContractError(f"{field} is required")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO datetime") from exc


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_allowlist_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("allowlist_summary is required")
    _raise_if_sensitive(value)
    allowlist_hash = _text(value.get("allowlist_hash"))
    if not allowlist_hash:
        raise ContractError("allowlist_hash is required")
    try:
        allowlist_count = int(value.get("allowlist_count"))
    except (TypeError, ValueError) as exc:
        raise ContractError("allowlist_count is required") from exc
    if allowlist_count < 0:
        raise ContractError("allowlist_count must be non-negative")
    allowlist_summary = _json_clone(value.get("allowlist_summary"), {})
    source_reference = _json_clone(value.get("source_reference"), {})
    normalized = {
        "allowlist_hash": allowlist_hash,
        "allowlist_count": allowlist_count,
        "allowlist_summary": allowlist_summary,
        "source_reference": source_reference,
        "expires_at": _text(value.get("expires_at")) or None,
    }
    _raise_if_sensitive(normalized)
    return normalized


def _normalize_gray_window(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("gray_window is required")
    _raise_if_sensitive(value)
    start_at = _parse_datetime(value.get("start_at"), field="gray_window.start_at")
    end_at = _parse_datetime(value.get("end_at"), field="gray_window.end_at")
    if end_at <= start_at:
        raise ContractError("gray_window end_at must be after start_at")
    timezone = _text(value.get("timezone")) or "UTC"
    metadata = _json_clone(value.get("metadata"), {})
    normalized = {
        "start_at": start_at,
        "end_at": end_at,
        "timezone": timezone,
        "metadata": metadata,
    }
    _raise_if_sensitive(normalized)
    return normalized


def _normalize_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    _raise_if_sensitive(payload)
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise ContractError("idempotency_key is required")
    client_snapshot_hash = _text(payload.get("client_snapshot_hash"))
    if not client_snapshot_hash:
        raise ContractError("client_snapshot_hash is required")
    request_note = _text(payload.get("request_note"))
    allowlist = _normalize_allowlist_summary(payload.get("allowlist_summary"))
    gray_window = _normalize_gray_window(payload.get("gray_window"))
    normalized = {
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": client_snapshot_hash,
        "allowlist_summary": allowlist,
        "gray_window": {
            **gray_window,
            "start_at": gray_window["start_at"].isoformat(),
            "end_at": gray_window["end_at"].isoformat(),
        },
        "request_note_present": bool(request_note),
        "request_note_hash": _hash({"request_note": request_note}) if request_note else "",
    }
    return {
        **normalized,
        "request_payload_hash": _hash(normalized),
        "gray_window_parsed": gray_window,
    }


def _review_envelope(
    review: dict[str, Any],
    *,
    operation: str,
    production_write: bool,
    idempotent_replay: bool = False,
    step: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "review_id": review.get("review_id"),
        "draft_id": review.get("draft_id"),
        "review_status": review.get("review_status"),
        "snapshot_hash": review.get("snapshot_hash", ""),
        "sanitized_payload_hash": review.get("sanitized_payload_hash", ""),
        "step_id": (step or {}).get("step_id", ""),
        "step_type": (step or {}).get("step_type", ""),
        "step_status": (step or {}).get("step_status", ""),
        "steps": [
            {
                "step_id": step.get("step_id"),
                "step_type": step.get("step_type"),
                "step_status": step.get("step_status"),
                "actor_metadata": {
                    "actor_label_present": bool(step.get("actor_label")),
                    "actor_id_present": bool(step.get("actor_id")),
                },
                "created_at": step.get("created_at"),
                "updated_at": step.get("updated_at"),
            }
            for step in review.get("steps") or []
        ],
        "allowlist_summary": {
            "hash": (review.get("allowlist_summary") or {}).get("allowlist_hash", ""),
            "count": (review.get("allowlist_summary") or {}).get("allowlist_count", 0),
            "source_reference_summary": (review.get("allowlist_summary") or {}).get("source_reference", {}),
            "expires_at": (review.get("allowlist_summary") or {}).get("expires_at", ""),
        },
        "gray_window": {
            "start_at": (review.get("gray_window") or {}).get("start_at", ""),
            "end_at": (review.get("gray_window") or {}).get("end_at", ""),
            "timezone": (review.get("gray_window") or {}).get("timezone", ""),
            "window_status": (review.get("gray_window") or {}).get("window_status", ""),
        },
        "created_at": review.get("created_at"),
        "updated_at": review.get("updated_at"),
        "expires_at": review.get("expires_at"),
        "preview_only": True,
        "production_write": production_write,
        "production_write_scope": "governance_tables_only" if production_write else "none",
        "approved": False,
        "governance_approved": review.get("review_status") == "governance_approved",
        "ready_for_review": True,
        "push_center_job_created": False,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
        "real_external_call": False,
        "real_external_call_executed": False,
        "can_claim_pass_90_plus": False,
        "execution_status": "not_execution",
        "idempotent_replay": idempotent_replay,
        "route_owner": "ai_crm_next",
        "capability_owner": "automation_engine",
    }


def _find_step(review: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in review.get("steps") or []:
        if _text(step.get("step_id")) == step_id:
            return step
    raise NotFoundError("governance step not found")


def _step_by_type(review: dict[str, Any], step_type: str) -> dict[str, Any] | None:
    for step in review.get("steps") or []:
        if _text(step.get("step_type")) == step_type:
            return step
    return None


def _normalize_step_payload(payload: dict[str, Any], *, action: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    _raise_if_sensitive(payload)
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise ContractError("idempotency_key is required")
    note = _text(payload.get("approval_note") or payload.get("reject_reason") or payload.get("expire_reason") or payload.get("note"))
    normalized: dict[str, Any] = {
        "action": action,
        "idempotency_key": idempotency_key,
        "note_present": bool(note),
        "note_hash": _hash({"note": note}) if note else "",
    }
    if "allowlist_hash" in payload:
        normalized["allowlist_hash"] = _text(payload.get("allowlist_hash"))
    if "allowlist_count" in payload:
        try:
            normalized["allowlist_count"] = int(payload.get("allowlist_count"))
        except (TypeError, ValueError) as exc:
            raise ContractError("allowlist_count must be an integer") from exc
    normalized["payload_hash"] = _hash(normalized)
    _raise_if_sensitive(normalized)
    return normalized


def _normalize_bridge_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("request body must be a JSON object")
    _raise_if_sensitive(payload)
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise ContractError("idempotency_key is required")
    client_snapshot_hash = _text(payload.get("client_snapshot_hash"))
    if not client_snapshot_hash:
        raise ContractError("client_snapshot_hash is required")
    allowlist_hash = _text(payload.get("allowlist_hash"))
    if not allowlist_hash:
        raise ContractError("allowlist_hash is required")
    try:
        allowlist_count = int(payload.get("allowlist_count"))
    except (TypeError, ValueError) as exc:
        raise ContractError("allowlist_count is required") from exc
    if allowlist_count < 0:
        raise ContractError("allowlist_count must be non-negative")
    bridge_note = _text(payload.get("bridge_note") or payload.get("note"))
    normalized = {
        "idempotency_key": idempotency_key,
        "client_snapshot_hash": client_snapshot_hash,
        "allowlist_hash": allowlist_hash,
        "allowlist_count": allowlist_count,
        "bridge_note_present": bool(bridge_note),
        "bridge_note_hash": _hash({"bridge_note": bridge_note}) if bridge_note else "",
    }
    normalized["bridge_payload_hash"] = _hash(normalized)
    _raise_if_sensitive(normalized)
    return normalized


def _transition_metadata(
    *,
    review: dict[str, Any],
    step: dict[str, Any] | None,
    normalized: dict[str, Any],
    actor: dict[str, Any],
) -> dict[str, Any]:
    return {
        **((step or {}).get("metadata") or {}),
        "transition": {
            "action": normalized["action"],
            "idempotency_key": normalized["idempotency_key"],
            "payload_hash": normalized["payload_hash"],
            "actor": {
                "actor_id": _actor_id(actor),
                "actor_label": _actor_label(actor),
                "actor_metadata": _actor_metadata(actor),
            },
            "review_id": review.get("review_id"),
            "step_id": (step or {}).get("step_id", ""),
            "step_type": (step or {}).get("step_type", ""),
            "real_external_call": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
        },
    }


def _audit_metadata(
    review: dict[str, Any],
    *,
    normalized: dict[str, Any],
    actor: dict[str, Any],
    action_key: str,
) -> dict[str, Any]:
    existing = _json_clone(review.get("audit_metadata"), {})
    actions = _json_clone(existing.get("governance_step_actions"), {})
    actions[action_key] = {
        "action": normalized["action"],
        "idempotency_key": normalized["idempotency_key"],
        "payload_hash": normalized["payload_hash"],
        "actor": {
            "actor_id": _actor_id(actor),
            "actor_label": _actor_label(actor),
            "actor_metadata": _actor_metadata(actor),
        },
        "real_external_call": False,
        "push_center_job_created": False,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
    }
    return {
        **existing,
        "governance_step_actions": actions,
    }


def _existing_transition(step: dict[str, Any]) -> dict[str, Any]:
    metadata = step.get("metadata") or {}
    transition = metadata.get("transition") if isinstance(metadata, dict) else None
    return transition if isinstance(transition, dict) else {}


def _assert_idempotent_or_pending(step: dict[str, Any], normalized: dict[str, Any], action: str) -> bool:
    existing = _existing_transition(step)
    if _text(step.get("step_status")) == "pending":
        if _text(step.get("idempotency_key")) and _text(step.get("idempotency_key")) == normalized["idempotency_key"]:
            if existing.get("payload_hash") != normalized["payload_hash"]:
                raise ContractError("governance step idempotency key conflict")
        return False
    if existing.get("action") == action and existing.get("idempotency_key") == normalized["idempotency_key"]:
        if existing.get("payload_hash") != normalized["payload_hash"]:
            raise ContractError("governance step idempotency key conflict")
        return True
    raise ContractError("governance step already transitioned")


def _review_action_metadata(review: dict[str, Any], action_key: str) -> dict[str, Any]:
    metadata = review.get("audit_metadata") or {}
    actions = metadata.get("governance_step_actions") if isinstance(metadata, dict) else None
    action = actions.get(action_key) if isinstance(actions, dict) else None
    return action if isinstance(action, dict) else {}


def _assert_review_can_transition(review: dict[str, Any]) -> None:
    if _text(review.get("review_status")) in {"governance_rejected", "governance_expired"}:
        raise ContractError("governance review is terminal")


def _review_status_for_steps(steps: list[dict[str, Any]]) -> str:
    if any(_text(step.get("step_status")) == "rejected" for step in steps):
        return "governance_rejected"
    if any(_text(step.get("step_status")) == "expired" for step in steps):
        return "governance_expired"
    if all(_text(step.get("step_status")) == "approved" for step in steps):
        return "governance_approved"
    if _text((_step_by_type({"steps": steps}, "operator_approval") or {}).get("step_status")) == "pending":
        return "approval_pending"
    if _text((_step_by_type({"steps": steps}, "receiver_allowlist") or {}).get("step_status")) == "pending":
        return "allowlist_pending"
    return "gray_window_pending"


def _bridge_job_id(review_id: str) -> str:
    return f"p1-gow-push-center:{review_id}"


def _existing_bridge_metadata(review: dict[str, Any]) -> dict[str, Any]:
    metadata = review.get("audit_metadata") or {}
    bridge = metadata.get("push_center_bridge") if isinstance(metadata, dict) else None
    return bridge if isinstance(bridge, dict) else {}


def _bridge_envelope(
    review: dict[str, Any],
    *,
    operation: str,
    production_write: bool,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    bridge = _existing_bridge_metadata(review)
    created = bool(bridge)
    return {
        "ok": True,
        "operation": operation,
        "review_id": review.get("review_id"),
        "draft_id": review.get("draft_id"),
        "review_status": review.get("review_status"),
        "push_center_job_created": created,
        "push_center_job_id": bridge.get("push_center_job_id", "") if created else "",
        "push_center_projection_id": bridge.get("push_center_projection_id", "") if created else "",
        "push_center_status": bridge.get("push_center_status", "not_bridged") if created else "not_bridged",
        "push_center_metadata": {
            "source": "p1_group_ops_workspace" if created else "",
            "draft_id": review.get("draft_id") if created else "",
            "review_id": review.get("review_id") if created else "",
            "governance_status": review.get("review_status") if created else "",
            "snapshot_hash": bridge.get("snapshot_hash", "") if created else "",
            "allowlist_hash": bridge.get("allowlist_hash", "") if created else "",
            "allowlist_count": bridge.get("allowlist_count", 0) if created else 0,
            "gray_window": bridge.get("gray_window", {}) if created else {},
            "no_external_call": True,
        },
        "preview_only": True,
        "production_write": production_write,
        "production_write_scope": "governance_bridge_metadata_only" if production_write else "none",
        "approved": False,
        "governance_approved": review.get("review_status") == "governance_approved",
        "ready_for_review": True,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
        "real_external_call": False,
        "real_external_call_executed": False,
        "execution_status": "push_center_pending_not_sent" if created else "not_execution",
        "can_claim_pass_90_plus": False,
        "idempotent_replay": idempotent_replay,
        "route_owner": "ai_crm_next",
        "capability_owner": "automation_engine",
    }


def _assert_required_steps_approved(review: dict[str, Any]) -> None:
    for step_type in REQUIRED_STEP_TYPES:
        step = _step_by_type(review, step_type)
        if not step or _text(step.get("step_status")) != "approved":
            raise ContractError(f"{step_type} step must be approved before Push Center bridge")


def _assert_bridge_window_and_allowlist(review: dict[str, Any], normalized: dict[str, Any]) -> None:
    allowlist = review.get("allowlist_summary") or {}
    if normalized["allowlist_hash"] != _text(allowlist.get("allowlist_hash")):
        raise ContractError("allowlist hash mismatch")
    if int(normalized["allowlist_count"]) != int(allowlist.get("allowlist_count") or 0):
        raise ContractError("allowlist count mismatch")
    expires_at = _text(allowlist.get("expires_at"))
    if expires_at and _ensure_aware(_parse_datetime(expires_at, field="allowlist.expires_at")) <= datetime.now(timezone.utc):
        raise ContractError("allowlist snapshot expired")

    gray_window = review.get("gray_window") or {}
    if _text(gray_window.get("window_status")) != "approved":
        raise ContractError("gray window step must be approved before Push Center bridge")
    start_at = _ensure_aware(_parse_datetime(gray_window.get("start_at"), field="gray_window.start_at"))
    end_at = _ensure_aware(_parse_datetime(gray_window.get("end_at"), field="gray_window.end_at"))
    if end_at <= start_at:
        raise ContractError("gray_window end_at must be after start_at")
    try:
        ZoneInfo(_text(gray_window.get("timezone")) or "UTC")
    except ZoneInfoNotFoundError as exc:
        raise ContractError("gray_window timezone is invalid") from exc
    if datetime.now(timezone.utc) > end_at:
        raise ContractError("gray window expired")


def _bridge_audit_metadata(
    review: dict[str, Any],
    *,
    draft: dict[str, Any],
    normalized: dict[str, Any],
    actor: dict[str, Any],
) -> dict[str, Any]:
    existing = _json_clone(review.get("audit_metadata"), {})
    gray_window = review.get("gray_window") or {}
    allowlist = review.get("allowlist_summary") or {}
    push_center_job_id = _bridge_job_id(_text(review.get("review_id")))
    bridge = {
        "action": "bridge_push_center",
        "idempotency_key": normalized["idempotency_key"],
        "bridge_payload_hash": normalized["bridge_payload_hash"],
        "source": "p1_group_ops_workspace",
        "draft_id": draft.get("draft_id"),
        "review_id": review.get("review_id"),
        "governance_status": review.get("review_status"),
        "push_center_job_id": push_center_job_id,
        "push_center_projection_id": push_center_job_id,
        "push_center_status": "pending",
        "snapshot_hash": review.get("snapshot_hash"),
        "allowlist_hash": allowlist.get("allowlist_hash", ""),
        "allowlist_count": allowlist.get("allowlist_count", 0),
        "gray_window": {
            "start_at": gray_window.get("start_at", ""),
            "end_at": gray_window.get("end_at", ""),
            "timezone": gray_window.get("timezone", ""),
            "window_status": gray_window.get("window_status", ""),
        },
        "created_by": _actor_id(actor),
        "actor": {
            "actor_id": _actor_id(actor),
            "actor_label": _actor_label(actor),
            "actor_metadata": _actor_metadata(actor),
        },
        "no_external_call": True,
        "push_center_job_created": True,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
        "real_external_call": False,
        "execution_status": "push_center_pending_not_sent",
        "can_claim_pass_90_plus": False,
    }
    _raise_if_sensitive(bridge)
    return {
        **existing,
        "push_center_bridge": bridge,
    }


class GroupOpsWorkspaceGovernanceService:
    def __init__(self, repo: GroupOpsWorkspaceGovernanceRepository | None = None) -> None:
        self.repo = repo or build_group_ops_workspace_governance_repository()

    def request_governance(self, draft_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_request_payload(payload)
        current = self.repo.get_draft(_text(draft_id))
        if not current:
            raise NotFoundError("draft not found")
        if current.get("draft_status") == "archived":
            raise ContractError("archived draft cannot request governance")
        if current.get("draft_status") == "rejected":
            raise ContractError("rejected draft cannot request governance")
        if current.get("draft_status") != "ready_for_review":
            raise ContractError("draft must be ready_for_review before governance request")
        if not _text(current.get("snapshot_hash")):
            raise ContractError("draft snapshot_hash is required")
        if not isinstance(current.get("sanitized_payload"), dict):
            raise ContractError("draft sanitized payload is required")
        if normalized["client_snapshot_hash"] != _text(current.get("snapshot_hash")):
            raise ContractError("draft snapshot conflict")

        existing = self.repo.find_by_idempotency_key(
            draft_id=_text(draft_id),
            idempotency_key=normalized["idempotency_key"],
        )
        if existing:
            metadata = existing.get("audit_metadata") or {}
            if metadata.get("request_payload_hash") != normalized["request_payload_hash"]:
                raise ContractError("governance request idempotency key conflict")
            return _review_envelope(existing, operation="request_governance", production_write=False, idempotent_replay=True)

        active_review = self.repo.find_active_review_for_draft(_text(draft_id))
        if active_review:
            raise ContractError("active governance review exists")

        review_id = f"gowg_{uuid4().hex}"
        actor_id = _actor_id(actor)
        actor_label = _actor_label(actor)
        audit_metadata = {
            "actor": {
                "actor_id": actor_id,
                "actor_label": actor_label,
                "actor_metadata": _actor_metadata(actor),
            },
            "action": "governance_request",
            "draft_id": _text(draft_id),
            "review_id": review_id,
            "snapshot_hash": current["snapshot_hash"],
            "sanitized_payload_hash": _hash(current.get("sanitized_payload") or {}),
            "allowlist_hash": normalized["allowlist_summary"]["allowlist_hash"],
            "allowlist_count": normalized["allowlist_summary"]["allowlist_count"],
            "gray_window": {
                "start_at": normalized["gray_window"]["start_at"],
                "end_at": normalized["gray_window"]["end_at"],
                "timezone": normalized["gray_window"]["timezone"],
            },
            "request_payload_hash": normalized["request_payload_hash"],
            "approved": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
        }
        created = self.repo.create_governance_review(
            {
                "review_id": review_id,
                "draft_id": _text(draft_id),
                "requested_by": actor_id,
                "actor_label": actor_label,
                "idempotency_key": normalized["idempotency_key"],
                "snapshot_hash": current["snapshot_hash"],
                "sanitized_payload_hash": _hash(current.get("sanitized_payload") or {}),
                "audit_metadata": audit_metadata,
                "expires_at": normalized["allowlist_summary"].get("expires_at"),
                "steps": [
                    {
                        "step_id": f"gowgs_{uuid4().hex}",
                        "step_type": step_type,
                        "metadata": {
                            "action": "governance_request",
                            "draft_id": _text(draft_id),
                            "review_id": review_id,
                            "step_type": step_type,
                        },
                    }
                    for step_type in REQUIRED_STEP_TYPES
                ],
                "allowlist_snapshot": {
                    "snapshot_id": f"gowas_{uuid4().hex}",
                    **normalized["allowlist_summary"],
                },
                "gray_window": {
                    "approval_id": f"gowgw_{uuid4().hex}",
                    **normalized["gray_window_parsed"],
                    "metadata": {
                        "action": "governance_request",
                        "draft_id": _text(draft_id),
                        "review_id": review_id,
                        "window_status": "pending",
                    },
                },
            }
        )
        return _review_envelope(created, operation="request_governance", production_write=True)

    def approve_step(self, review_id: str, step_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_step_payload(payload, action="approve")
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        _assert_review_can_transition(review)
        draft = self.repo.get_draft(_text(review.get("draft_id")))
        if not draft:
            raise NotFoundError("draft not found")
        if draft.get("draft_status") in {"archived", "rejected"}:
            raise ContractError("archived or rejected draft governance cannot be approved")
        step = _find_step(review, _text(step_id))
        idempotent_replay = _assert_idempotent_or_pending(step, normalized, "approve")
        if idempotent_replay:
            return _review_envelope(review, operation="approve_governance_step", production_write=False, idempotent_replay=True, step=step)

        step_type = _text(step.get("step_type"))
        gray_window_status = ""
        if step_type == "receiver_allowlist":
            allowlist = review.get("allowlist_summary") or {}
            if "allowlist_hash" not in normalized or "allowlist_count" not in normalized:
                raise ContractError("allowlist_hash and allowlist_count are required")
            if normalized["allowlist_hash"] != _text(allowlist.get("allowlist_hash")):
                raise ContractError("allowlist hash mismatch")
            if int(normalized["allowlist_count"]) != int(allowlist.get("allowlist_count") or 0):
                raise ContractError("allowlist count mismatch")
            expires_at = _text(allowlist.get("expires_at"))
            if expires_at and _ensure_aware(_parse_datetime(expires_at, field="allowlist.expires_at")) <= datetime.now(timezone.utc):
                raise ContractError("allowlist snapshot expired")
        elif step_type == "gray_window":
            gray_window = review.get("gray_window") or {}
            if not gray_window:
                raise ContractError("gray window record is required")
            start_at = _ensure_aware(_parse_datetime(gray_window.get("start_at"), field="gray_window.start_at"))
            end_at = _ensure_aware(_parse_datetime(gray_window.get("end_at"), field="gray_window.end_at"))
            if end_at <= start_at:
                raise ContractError("gray_window end_at must be after start_at")
            try:
                ZoneInfo(_text(gray_window.get("timezone")) or "UTC")
            except ZoneInfoNotFoundError as exc:
                raise ContractError("gray_window timezone is invalid") from exc
            if datetime.now(timezone.utc) > end_at:
                raise ContractError("gray window expired")
            gray_window_status = "approved"
        elif step_type != "operator_approval":
            raise ContractError("unsupported governance step type")

        next_steps = [
            {**candidate, "step_status": "approved"} if candidate.get("step_id") == step.get("step_id") else candidate
            for candidate in review.get("steps") or []
        ]
        review_status = _review_status_for_steps(next_steps)
        metadata = _transition_metadata(review=review, step=step, normalized=normalized, actor=actor)
        updated = self.repo.transition_governance_step(
            {
                "review_id": review["review_id"],
                "step_id": step["step_id"],
                "step_status": "approved",
                "review_status": review_status,
                "actor_id": _actor_id(actor),
                "actor_label": _actor_label(actor),
                "idempotency_key": normalized["idempotency_key"],
                "metadata": metadata,
                "audit_metadata": _audit_metadata(review, normalized=normalized, actor=actor, action_key=f"{step['step_id']}:approve"),
                "gray_window_status": gray_window_status,
            }
        )
        updated_step = _find_step(updated, _text(step_id))
        return _review_envelope(updated, operation="approve_governance_step", production_write=True, step=updated_step)

    def reject_step(self, review_id: str, step_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_step_payload(payload, action="reject")
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        _assert_review_can_transition(review)
        step = _find_step(review, _text(step_id))
        idempotent_replay = _assert_idempotent_or_pending(step, normalized, "reject")
        if idempotent_replay:
            return _review_envelope(review, operation="reject_governance_step", production_write=False, idempotent_replay=True, step=step)
        metadata = _transition_metadata(review=review, step=step, normalized=normalized, actor=actor)
        updated = self.repo.transition_governance_step(
            {
                "review_id": review["review_id"],
                "step_id": step["step_id"],
                "step_status": "rejected",
                "review_status": "governance_rejected",
                "actor_id": _actor_id(actor),
                "actor_label": _actor_label(actor),
                "idempotency_key": normalized["idempotency_key"],
                "metadata": metadata,
                "audit_metadata": _audit_metadata(review, normalized=normalized, actor=actor, action_key=f"{step['step_id']}:reject"),
                "gray_window_status": "rejected" if step.get("step_type") == "gray_window" else "",
            }
        )
        updated_step = _find_step(updated, _text(step_id))
        return _review_envelope(updated, operation="reject_governance_step", production_write=True, step=updated_step)

    def expire_review(self, review_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_step_payload(payload, action="expire")
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        existing = _review_action_metadata(review, "review:expire")
        if review.get("review_status") == "governance_expired":
            if existing.get("idempotency_key") == normalized["idempotency_key"]:
                if existing.get("payload_hash") != normalized["payload_hash"]:
                    raise ContractError("governance review expire idempotency key conflict")
                return _review_envelope(review, operation="expire_governance_review", production_write=False, idempotent_replay=True, step={"step_id": "", "step_type": "review", "step_status": "expired"})
            raise ContractError("governance review already expired")
        if review.get("review_status") == "governance_rejected":
            raise ContractError("governance review is rejected")
        metadata = {
            "transition": {
                "action": "expire",
                "idempotency_key": normalized["idempotency_key"],
                "payload_hash": normalized["payload_hash"],
                "actor": {
                    "actor_id": _actor_id(actor),
                    "actor_label": _actor_label(actor),
                    "actor_metadata": _actor_metadata(actor),
                },
                "review_id": review["review_id"],
                "real_external_call": False,
                "push_center_job_created": False,
                "external_effect_job_created": False,
                "broadcast_job_created": False,
                "internal_event_created": False,
            }
        }
        updated = self.repo.expire_governance_review(
            {
                "review_id": review["review_id"],
                "actor_id": _actor_id(actor),
                "actor_label": _actor_label(actor),
                "idempotency_key": normalized["idempotency_key"],
                "metadata": metadata,
                "audit_metadata": _audit_metadata(review, normalized=normalized, actor=actor, action_key="review:expire"),
            }
        )
        return _review_envelope(updated, operation="expire_governance_review", production_write=True, step={"step_id": "", "step_type": "review", "step_status": "expired"})

    def get_review(self, review_id: str) -> dict[str, Any]:
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        return _review_envelope(review, operation="get_governance", production_write=False)

    def list_reviews_for_draft(self, draft_id: str) -> dict[str, Any]:
        reviews = self.repo.list_reviews_for_draft(_text(draft_id))
        return {
            "ok": True,
            "items": [_review_envelope(review, operation="list_item", production_write=False) for review in reviews],
            "total": len(reviews),
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

    def bridge_push_center(self, review_id: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_bridge_payload(payload)
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        existing_bridge = _existing_bridge_metadata(review)
        if existing_bridge:
            if existing_bridge.get("idempotency_key") == normalized["idempotency_key"]:
                if existing_bridge.get("bridge_payload_hash") != normalized["bridge_payload_hash"]:
                    raise ContractError("Push Center bridge idempotency key conflict")
                return _bridge_envelope(review, operation="bridge_push_center", production_write=False, idempotent_replay=True)
            raise ContractError("governance review already bridged")

        if _text(review.get("review_status")) != "governance_approved":
            raise ContractError("governance review must be governance_approved before Push Center bridge")
        draft = self.repo.get_draft(_text(review.get("draft_id")))
        if not draft:
            raise NotFoundError("draft not found")
        if _text(draft.get("draft_status")) != "ready_for_review":
            raise ContractError("draft must be ready_for_review before Push Center bridge")
        draft_snapshot_hash = _text(draft.get("snapshot_hash"))
        review_snapshot_hash = _text(review.get("snapshot_hash"))
        if not draft_snapshot_hash or not review_snapshot_hash:
            raise ContractError("snapshot_hash is required before Push Center bridge")
        if draft_snapshot_hash != review_snapshot_hash:
            raise ContractError("draft snapshot mismatch")
        if normalized["client_snapshot_hash"] != review_snapshot_hash:
            raise ContractError("client snapshot mismatch")
        _assert_required_steps_approved(review)
        _assert_bridge_window_and_allowlist(review, normalized)

        updated = self.repo.record_push_center_bridge(
            review_id=review["review_id"],
            audit_metadata=_bridge_audit_metadata(review, draft=draft, normalized=normalized, actor=actor),
        )
        return _bridge_envelope(updated, operation="bridge_push_center", production_write=True)

    def get_push_center_bridge(self, review_id: str) -> dict[str, Any]:
        review = self.repo.get_review(_text(review_id))
        if not review:
            raise NotFoundError("governance review not found")
        return _bridge_envelope(review, operation="get_push_center_bridge", production_write=False)
