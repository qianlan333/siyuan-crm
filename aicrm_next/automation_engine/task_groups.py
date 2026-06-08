from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from aicrm_next.shared.errors import ContractError

from .state_machine import utc_now_iso


TASK_GROUP_ROUTE_FAMILY = "/api/admin/automation-conversion/task-groups*"
MAX_GROUP_NAME_LENGTH = 120
MAX_JSON_LENGTH = 20000
DANGEROUS_TASK_GROUP_FIELDS = {
    "run_due",
    "execute",
    "execution",
    "send",
    "wecom",
    "openclaw",
    "mcp",
    "timer",
    "workflow_activation",
    "outbound",
    "agent_runtime_execution",
    "deepseek",
    "llm",
}


def task_group_side_effect_safety() -> dict[str, bool]:
    return {
        "real_external_call_executed": False,
        "real_automation_execution_executed": False,
        "real_task_execution_executed": False,
        "real_run_due_executed": False,
        "real_outbound_send_executed": False,
        "real_wecom_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_mcp_call_executed": False,
        "real_llm_call_executed": False,
        "real_timer_executed": False,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return slug or "task_group"


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


def reject_dangerous_task_group_fields(payload: dict[str, Any]) -> None:
    for key_path in _walk_keys(payload):
        normalized = key_path.lower().replace("-", "_")
        for field in DANGEROUS_TASK_GROUP_FIELDS:
            if field in normalized:
                raise ContractError(f"dangerous task group field is not allowed: {key_path}")


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a JSON object")
    if _json_size(value) > MAX_JSON_LENGTH:
        raise ContractError(f"{field} payload is too large")
    reject_dangerous_task_group_fields(value)
    return deepcopy(value)


def normalize_task_group_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_task_group_fields(source)

    group_name = _text(source.get("group_name") or source.get("name"))
    if not group_name:
        raise ContractError("group_name is required")
    if len(group_name) > MAX_GROUP_NAME_LENGTH:
        raise ContractError(f"group_name must be at most {MAX_GROUP_NAME_LENGTH} characters")

    program_id_raw = source.get("program_id")
    try:
        program_id = int(program_id_raw or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("program_id must be an integer") from exc
    if program_id < 0:
        raise ContractError("program_id must be non-negative")

    sort_order_raw = source.get("sort_order")
    try:
        sort_order = int(sort_order_raw or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("sort_order must be an integer") from exc

    group_code = _text(source.get("group_code") or source.get("code")) or _slugify(group_name)
    return {
        "program_id": program_id,
        "group_code": group_code,
        "code": group_code,
        "group_name": group_name,
        "name": group_name,
        "sort_order": sort_order,
        "metadata": _json_object(source.get("metadata"), field="metadata"),
        "created_by": _text(source.get("operator") or source.get("created_by") or "system"),
        "updated_by": _text(source.get("operator") or source.get("updated_by") or "system"),
    }


def task_group_projection(group: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(group or {})
    group_id = int(item.get("id") or item.get("group_id") or 0)
    program_id = int(item.get("program_id") or 0)
    code = _text(item.get("group_code") or item.get("code")) or _slugify(_text(item.get("group_name") or item.get("name")))
    name = _text(item.get("group_name") or item.get("name"))
    now = utc_now_iso()
    return {
        "id": group_id,
        "group_id": group_id,
        "program_id": program_id,
        "group_code": code,
        "code": code,
        "group_name": name,
        "name": name,
        "sort_order": int(item.get("sort_order") or 0),
        "metadata": deepcopy(item.get("metadata") or {}),
        "created_by": _text(item.get("created_by")),
        "updated_by": _text(item.get("updated_by")),
        "created_at": _text(item.get("created_at")) or now,
        "updated_at": _text(item.get("updated_at")) or now,
        "archived_at": _text(item.get("archived_at")),
    }
