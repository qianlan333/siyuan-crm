from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from aicrm_next.shared.errors import ContractError

from .state_machine import utc_now_iso


WORKFLOW_ROUTE_FAMILY = "/api/admin/automation-conversion/workflows*"
MAX_WORKFLOW_NAME_LENGTH = 160
MAX_JSON_LENGTH = 20000
ALLOWED_WORKFLOW_STATUSES = {"draft", "disabled", "inactive"}
DANGEROUS_WORKFLOW_FIELDS = {
    "activate",
    "activation",
    "node_runtime",
    "run_due",
    "execute",
    "execution",
    "send",
    "wecom",
    "openclaw",
    "mcp",
    "timer",
    "outbound",
    "production_owner",
    "fallback_removal",
    "external_call",
    "deepseek",
    "llm",
}


def workflow_side_effect_safety() -> dict[str, bool]:
    return {
        "real_external_call_executed": False,
        "real_workflow_activation_executed": False,
        "real_workflow_runtime_executed": False,
        "real_node_transition_executed": False,
        "real_timer_executed": False,
        "real_outbound_send_executed": False,
        "real_wecom_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_mcp_call_executed": False,
        "real_llm_call_executed": False,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return slug or "workflow"


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _walk_keys(value: Any, *, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            full = f"{prefix}.{key_text}" if prefix else key_text
            keys.append(full)
            keys.extend(_walk_keys(child, prefix=full))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            keys.extend(_walk_keys(child, prefix=f"{prefix}[{index}]"))
    return keys


def reject_dangerous_workflow_fields(payload: dict[str, Any]) -> None:
    for key_path in _walk_keys(payload):
        normalized = key_path.lower().replace("-", "_")
        for field in DANGEROUS_WORKFLOW_FIELDS:
            if field in normalized:
                raise ContractError(f"dangerous workflow field is not allowed: {key_path}")


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a JSON object")
    if _json_size(value) > MAX_JSON_LENGTH:
        raise ContractError(f"{field} payload is too large")
    reject_dangerous_workflow_fields(value)
    return deepcopy(value)


def normalize_workflow_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_workflow_fields(source)

    workflow_name = _text(source.get("workflow_name") or source.get("name"))
    if not workflow_name:
        raise ContractError("workflow_name is required")
    if len(workflow_name) > MAX_WORKFLOW_NAME_LENGTH:
        raise ContractError(f"workflow_name must be at most {MAX_WORKFLOW_NAME_LENGTH} characters")

    program_id_raw = source.get("program_id")
    try:
        program_id = int(program_id_raw or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("program_id must be an integer") from exc
    if program_id < 0:
        raise ContractError("program_id must be non-negative")

    status = _text(source.get("status") or "draft").lower()
    if status not in ALLOWED_WORKFLOW_STATUSES:
        raise ContractError(f"workflow status must be one of: {', '.join(sorted(ALLOWED_WORKFLOW_STATUSES))}")

    workflow_code = _text(source.get("workflow_code") or source.get("code")) or _slugify(workflow_name)
    return {
        "program_id": program_id,
        "workflow_code": workflow_code,
        "code": workflow_code,
        "workflow_name": workflow_name,
        "name": workflow_name,
        "description": _text(source.get("description")),
        "review_status": _text(source.get("review_status") or "fixture_reviewed"),
        "created_by_agent": False,
        "status": status,
        "segmentation_basis": _json_object(source.get("segmentation_basis"), field="segmentation_basis"),
        "generation_mode": _text(source.get("generation_mode") or "manual_fixture"),
        "profile_segment_template_id": int(source.get("profile_segment_template_id") or 0),
        "behavior_tier_scheme": _json_object(source.get("behavior_tier_scheme"), field="behavior_tier_scheme"),
        "fallback_to_standard_content": bool(source.get("fallback_to_standard_content", True)),
        "enabled": False,
        "created_by": _text(source.get("operator") or source.get("created_by") or "system"),
        "updated_by": _text(source.get("operator") or source.get("updated_by") or "system"),
    }


def workflow_projection(workflow: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(workflow or {})
    workflow_id = int(item.get("id") or item.get("workflow_id") or 0)
    code = _text(item.get("workflow_code") or item.get("code")) or _slugify(_text(item.get("workflow_name") or item.get("name")))
    name = _text(item.get("workflow_name") or item.get("name"))
    now = utc_now_iso()
    return {
        "id": workflow_id,
        "workflow_id": workflow_id,
        "program_id": int(item.get("program_id") or 0),
        "workflow_code": code,
        "code": code,
        "workflow_name": name,
        "name": name,
        "description": _text(item.get("description")),
        "review_status": _text(item.get("review_status") or "fixture_reviewed"),
        "created_by_agent": bool(item.get("created_by_agent", False)),
        "status": _text(item.get("status") or "draft"),
        "segmentation_basis": deepcopy(item.get("segmentation_basis") or {}),
        "generation_mode": _text(item.get("generation_mode") or "manual_fixture"),
        "profile_segment_template_id": int(item.get("profile_segment_template_id") or 0),
        "behavior_tier_scheme": deepcopy(item.get("behavior_tier_scheme") or {}),
        "fallback_to_standard_content": bool(item.get("fallback_to_standard_content", True)),
        "enabled": bool(item.get("enabled", False)),
        "created_by": _text(item.get("created_by")),
        "updated_by": _text(item.get("updated_by")),
        "created_at": _text(item.get("created_at")) or now,
        "updated_at": _text(item.get("updated_at")) or now,
        "archived_at": _text(item.get("archived_at")),
    }
