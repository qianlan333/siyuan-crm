from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from aicrm_next.shared.errors import ContractError

from .state_machine import utc_now_iso


WORKFLOW_NODE_ROUTE_FAMILY = "/api/admin/automation-conversion/workflow-nodes*"
MAX_NODE_NAME_LENGTH = 160
MAX_JSON_LENGTH = 20000
ALLOWED_WORKFLOW_NODE_STATUSES = {"draft", "disabled", "inactive", "archived"}
ALLOWED_WORKFLOW_NODE_TYPES = {"manual", "condition", "wait", "message_template", "tagging", "metadata"}
DANGEROUS_WORKFLOW_NODE_FIELDS = {
    "activate",
    "activation",
    "run_due",
    "execute",
    "execution",
    "transition_runtime",
    "node_transition",
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


def workflow_node_side_effect_safety() -> dict[str, bool]:
    return {
        "real_external_call_executed": False,
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
    return slug or "workflow_node"


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


def reject_dangerous_workflow_node_fields(payload: dict[str, Any]) -> None:
    for key_path in _walk_keys(payload):
        normalized = key_path.lower().replace("-", "_")
        for field in DANGEROUS_WORKFLOW_NODE_FIELDS:
            if field in normalized:
                raise ContractError(f"dangerous workflow node field is not allowed: {key_path}")


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a JSON object")
    if _json_size(value) > MAX_JSON_LENGTH:
        raise ContractError(f"{field} payload is too large")
    reject_dangerous_workflow_node_fields(value)
    return deepcopy(value)


def normalize_workflow_node_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_workflow_node_fields(source)

    node_name = _text(source.get("node_name") or source.get("name"))
    if not node_name:
        raise ContractError("node_name is required")
    if len(node_name) > MAX_NODE_NAME_LENGTH:
        raise ContractError(f"node_name must be at most {MAX_NODE_NAME_LENGTH} characters")

    try:
        workflow_id = int(source.get("workflow_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("workflow_id must be an integer") from exc
    if workflow_id < 0:
        raise ContractError("workflow_id must be non-negative")

    try:
        program_id = int(source.get("program_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("program_id must be an integer") from exc
    if program_id < 0:
        raise ContractError("program_id must be non-negative")

    try:
        sort_order = int(source.get("sort_order") or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("sort_order must be an integer") from exc

    node_type = _text(source.get("node_type") or "manual").lower()
    if node_type not in ALLOWED_WORKFLOW_NODE_TYPES:
        raise ContractError(f"workflow node type must be one of: {', '.join(sorted(ALLOWED_WORKFLOW_NODE_TYPES))}")

    status = _text(source.get("status") or "draft").lower()
    if status not in ALLOWED_WORKFLOW_NODE_STATUSES:
        raise ContractError(f"workflow node status must be one of: {', '.join(sorted(ALLOWED_WORKFLOW_NODE_STATUSES))}")

    node_code = _text(source.get("node_code") or source.get("code")) or _slugify(node_name)
    return {
        "program_id": program_id,
        "workflow_id": workflow_id,
        "node_code": node_code,
        "code": node_code,
        "node_name": node_name,
        "name": node_name,
        "node_type": node_type,
        "status": status,
        "sort_order": sort_order,
        "position": _json_object(source.get("position"), field="position"),
        "metadata": _json_object(source.get("metadata"), field="metadata"),
        "config": _json_object(source.get("config"), field="config"),
        "enabled": False,
        "created_by": _text(source.get("operator") or source.get("created_by") or "system"),
        "updated_by": _text(source.get("operator") or source.get("updated_by") or "system"),
    }


def normalize_workflow_node_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_workflow_node_fields(source)
    patch: dict[str, Any] = {}

    if "node_name" in source or "name" in source:
        node_name = _text(source.get("node_name") or source.get("name"))
        if not node_name:
            raise ContractError("node_name is required")
        if len(node_name) > MAX_NODE_NAME_LENGTH:
            raise ContractError(f"node_name must be at most {MAX_NODE_NAME_LENGTH} characters")
        patch["node_name"] = node_name
        patch["name"] = node_name

    if "node_code" in source or "code" in source:
        node_code = _text(source.get("node_code") or source.get("code"))
        if not node_code:
            raise ContractError("node_code is required")
        patch["node_code"] = node_code
        patch["code"] = node_code

    if "node_type" in source:
        node_type = _text(source.get("node_type")).lower()
        if node_type not in ALLOWED_WORKFLOW_NODE_TYPES:
            raise ContractError(f"workflow node type must be one of: {', '.join(sorted(ALLOWED_WORKFLOW_NODE_TYPES))}")
        patch["node_type"] = node_type

    if "status" in source:
        status = _text(source.get("status")).lower()
        if status not in ALLOWED_WORKFLOW_NODE_STATUSES:
            raise ContractError(f"workflow node status must be one of: {', '.join(sorted(ALLOWED_WORKFLOW_NODE_STATUSES))}")
        patch["status"] = status

    if "sort_order" in source:
        try:
            patch["sort_order"] = int(source.get("sort_order") or 0)
        except (TypeError, ValueError) as exc:
            raise ContractError("sort_order must be an integer") from exc

    for field in ("position", "metadata", "config"):
        if field in source:
            patch[field] = _json_object(source.get(field), field=field)

    patch["updated_by"] = _text(source.get("operator") or source.get("updated_by") or "system")
    return patch


def workflow_node_projection(node: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(node or {})
    node_id = int(item.get("id") or item.get("node_id") or 0)
    code = _text(item.get("node_code") or item.get("code")) or _slugify(_text(item.get("node_name") or item.get("name")))
    name = _text(item.get("node_name") or item.get("name"))
    now = utc_now_iso()
    return {
        "id": node_id,
        "node_id": node_id,
        "program_id": int(item.get("program_id") or 0),
        "workflow_id": int(item.get("workflow_id") or 0),
        "node_code": code,
        "code": code,
        "node_name": name,
        "name": name,
        "node_type": _text(item.get("node_type") or "manual"),
        "status": _text(item.get("status") or "draft"),
        "sort_order": int(item.get("sort_order") or 0),
        "position": deepcopy(item.get("position") or {}),
        "metadata": deepcopy(item.get("metadata") or {}),
        "config": deepcopy(item.get("config") or {}),
        "enabled": bool(item.get("enabled", False)),
        "created_by": _text(item.get("created_by")),
        "updated_by": _text(item.get("updated_by")),
        "created_at": _text(item.get("created_at")) or now,
        "updated_at": _text(item.get("updated_at")) or now,
        "archived_at": _text(item.get("archived_at")),
    }
