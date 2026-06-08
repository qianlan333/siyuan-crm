from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from aicrm_next.shared.errors import ContractError

from .state_machine import utc_now_iso


ACTION_TEMPLATE_ROUTE_FAMILY = "/api/admin/automation-conversion/action-templates*"
ALLOWED_ACTION_TEMPLATE_STATUS = {"active", "archived"}
DANGEROUS_ACTION_TEMPLATE_FIELDS = {
    "run_due",
    "execute",
    "execution",
    "send",
    "wecom",
    "openclaw",
    "mcp",
    "timer",
    "workflow_activation",
    "customer_pool_state_change",
    "outbound_task",
    "agent_runtime_execution",
    "deepseek",
    "llm",
}
MAX_NAME_LENGTH = 160
MAX_DESCRIPTION_LENGTH = 1200
MAX_JSON_LENGTH = 20000


def action_template_side_effect_safety() -> dict[str, bool]:
    return {
        "real_external_call_executed": False,
        "real_automation_execution_executed": False,
        "real_outbound_send_executed": False,
        "real_wecom_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_mcp_call_executed": False,
        "real_llm_call_executed": False,
        "real_timer_executed": False,
        "real_customer_pool_state_changed": False,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return slug or "action_template"


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


def reject_dangerous_action_template_fields(payload: dict[str, Any]) -> None:
    for key_path in _walk_keys(payload):
        normalized = key_path.lower().replace("-", "_")
        for field in DANGEROUS_ACTION_TEMPLATE_FIELDS:
            if field in normalized:
                raise ContractError(f"dangerous action template field is not allowed: {key_path}")


def _json_object(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be a JSON object")
    if _json_size(value) > MAX_JSON_LENGTH:
        raise ContractError(f"{field} payload is too large")
    reject_dangerous_action_template_fields(value)
    return deepcopy(value)


def _json_list(value: Any, *, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ContractError(f"{field} must be a JSON list")
    if _json_size(value) > MAX_JSON_LENGTH:
        raise ContractError(f"{field} payload is too large")
    for item in value:
        if isinstance(item, dict):
            reject_dangerous_action_template_fields(item)
    return deepcopy(value)


def normalize_action_template_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_action_template_fields(source)

    name = _text(source.get("name")) or _text(source.get("template_name"))
    if not name:
        raise ContractError("template_name is required")
    if len(name) > MAX_NAME_LENGTH:
        raise ContractError(f"template_name must be at most {MAX_NAME_LENGTH} characters")

    code = _text(source.get("code")) or _text(source.get("template_code"))
    if not code:
        code = _slugify(name)

    template_source = _text(source.get("template_source") or "crm_local")
    if template_source != "crm_local":
        raise ContractError("template_source must be crm_local for fixture/local create")

    description = _text(source.get("description"))
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ContractError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    status = _text(source.get("status") or "active").lower()
    if status not in ALLOWED_ACTION_TEMPLATE_STATUS:
        allowed = ", ".join(sorted(ALLOWED_ACTION_TEMPLATE_STATUS))
        raise ContractError(f"status must be one of: {allowed}")

    return {
        "template_code": code,
        "code": code,
        "template_name": name,
        "name": name,
        "template_source": template_source,
        "category": _text(source.get("category")),
        "description": description,
        "status": status,
        "default_config": _json_object(source.get("default_config"), field="default_config"),
        "ui_schema": _json_object(source.get("ui_schema"), field="ui_schema"),
        "workflow_blueprint": _json_object(source.get("workflow_blueprint"), field="workflow_blueprint"),
        "node_blueprints": _json_list(source.get("node_blueprints"), field="node_blueprints"),
        "created_by": _text(source.get("operator") or source.get("created_by") or "system"),
        "updated_by": _text(source.get("operator") or source.get("updated_by") or "system"),
    }


def action_template_projection(template: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(template)
    template_id = int(item.get("id") or item.get("template_id") or 0)
    code = _text(item.get("template_code") or item.get("code"))
    name = _text(item.get("template_name") or item.get("name"))
    source = _text(item.get("template_source") or "crm_local")
    status = _text(item.get("status") or "active")
    now = utc_now_iso()
    return {
        "id": template_id,
        "template_id": template_id,
        "template_code": code,
        "code": code,
        "template_name": name,
        "name": name,
        "template_source": source,
        "category": _text(item.get("category")),
        "description": _text(item.get("description")),
        "status": status if status in ALLOWED_ACTION_TEMPLATE_STATUS else "active",
        "default_config": deepcopy(item.get("default_config") or {}),
        "ui_schema": deepcopy(item.get("ui_schema") or {}),
        "workflow_blueprint": deepcopy(item.get("workflow_blueprint") or {}),
        "node_blueprints": deepcopy(item.get("node_blueprints") or []),
        "created_by": _text(item.get("created_by")),
        "updated_by": _text(item.get("updated_by")),
        "created_at": _text(item.get("created_at")) or now,
        "updated_at": _text(item.get("updated_at")) or now,
        "archived_at": _text(item.get("archived_at")),
        "is_builtin": source == "builtin",
    }
