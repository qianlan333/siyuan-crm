from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from aicrm_next.shared.errors import ContractError

from .state_machine import utc_now_iso


TASK_ROUTE_FAMILY = "/api/admin/automation-conversion/tasks*"
MAX_TASK_NAME_LENGTH = 160
MAX_JSON_LENGTH = 20000
ALLOWED_TASK_STATUSES = {"draft", "disabled", "inactive", "pending"}
ALLOWED_TASK_TYPES = {"manual", "followup", "metadata", "review", "tagging"}
DANGEROUS_TASK_FIELDS = {
    "run_due",
    "execute",
    "execution",
    "workflow_execution",
    "task_execution",
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


def task_side_effect_safety() -> dict[str, bool]:
    return {
        "real_external_call_executed": False,
        "real_task_execution_executed": False,
        "real_run_due_executed": False,
        "real_workflow_runtime_executed": False,
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
    return slug or "task"


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


def reject_dangerous_task_fields(payload: dict[str, Any]) -> None:
    for key_path in _walk_keys(payload):
        normalized = key_path.lower().replace("-", "_")
        for field in DANGEROUS_TASK_FIELDS:
            if field in normalized:
                raise ContractError(f"dangerous task field is not allowed: {key_path}")


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a JSON object")
    if _json_size(value) > MAX_JSON_LENGTH:
        raise ContractError(f"{field} payload is too large")
    reject_dangerous_task_fields(value)
    return deepcopy(value)


def normalize_task_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_task_fields(source)

    task_name = _text(source.get("task_name") or source.get("name"))
    if not task_name:
        raise ContractError("task_name is required")
    if len(task_name) > MAX_TASK_NAME_LENGTH:
        raise ContractError(f"task_name must be at most {MAX_TASK_NAME_LENGTH} characters")

    ints: dict[str, int] = {}
    for field in ("program_id", "workflow_id", "node_id", "group_id", "sort_order"):
        try:
            value = int(source.get(field) or 0)
        except (TypeError, ValueError) as exc:
            raise ContractError(f"{field} must be an integer") from exc
        if value < 0:
            raise ContractError(f"{field} must be non-negative")
        ints[field] = value

    task_type = _text(source.get("task_type") or "manual").lower()
    if task_type not in ALLOWED_TASK_TYPES:
        raise ContractError(f"task type must be one of: {', '.join(sorted(ALLOWED_TASK_TYPES))}")

    status = _text(source.get("status") or "draft").lower()
    if status not in ALLOWED_TASK_STATUSES:
        raise ContractError(f"task status must be one of: {', '.join(sorted(ALLOWED_TASK_STATUSES))}")

    task_code = _text(source.get("task_code") or source.get("code")) or _slugify(task_name)
    return {
        **ints,
        "task_code": task_code,
        "code": task_code,
        "task_name": task_name,
        "name": task_name,
        "task_type": task_type,
        "status": status,
        "metadata": _json_object(source.get("metadata"), field="metadata"),
        "config": _json_object(source.get("config"), field="config"),
        "enabled": False,
        "created_by": _text(source.get("operator") or source.get("created_by") or "system"),
        "updated_by": _text(source.get("operator") or source.get("updated_by") or "system"),
    }


def task_projection(task: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(task or {})
    task_id = int(item.get("id") or item.get("task_id") or 0)
    code = _text(item.get("task_code") or item.get("code")) or _slugify(_text(item.get("task_name") or item.get("name")))
    name = _text(item.get("task_name") or item.get("name"))
    now = utc_now_iso()
    return {
        "id": task_id,
        "task_id": task_id,
        "program_id": int(item.get("program_id") or 0),
        "workflow_id": int(item.get("workflow_id") or 0),
        "node_id": int(item.get("node_id") or 0),
        "group_id": int(item.get("group_id") or 0),
        "task_code": code,
        "code": code,
        "task_name": name,
        "name": name,
        "task_type": _text(item.get("task_type") or "manual"),
        "status": _text(item.get("status") or "draft"),
        "sort_order": int(item.get("sort_order") or 0),
        "metadata": deepcopy(item.get("metadata") or {}),
        "config": deepcopy(item.get("config") or {}),
        "enabled": bool(item.get("enabled", False)),
        "created_by": _text(item.get("created_by")),
        "updated_by": _text(item.get("updated_by")),
        "created_at": _text(item.get("created_at")) or now,
        "updated_at": _text(item.get("updated_at")) or now,
        "archived_at": _text(item.get("archived_at")),
    }
