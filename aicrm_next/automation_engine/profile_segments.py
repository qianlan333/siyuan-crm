from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from aicrm_next.shared.errors import ContractError

from .state_machine import utc_now_iso


ALLOWED_PROFILE_SEGMENT_TEMPLATE_STATUS = {"draft", "active", "inactive"}
DANGEROUS_PROFILE_SEGMENT_FIELDS = {
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
    "outbound_send",
    "task_dispatch",
    "agent_orchestration",
    "external_call",
    "webhook_url",
}
MAX_NAME_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 1000
MAX_RULES_JSON_LENGTH = 12000


def profile_segment_side_effect_safety() -> dict[str, bool]:
    return {
        "real_automation_write_executed": False,
        "real_external_call_executed": False,
        "real_workflow_runtime_executed": False,
        "real_wecom_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_mcp_call_executed": False,
        "real_timer_executed": False,
        "real_outbound_send_executed": False,
        "real_customer_pool_state_changed": False,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return slug or "profile_segment_template"


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


def reject_dangerous_profile_segment_fields(payload: dict[str, Any]) -> None:
    for key_path in _walk_keys(payload):
        normalized = key_path.lower().replace("-", "_")
        for field in DANGEROUS_PROFILE_SEGMENT_FIELDS:
            if field in normalized:
                raise ContractError(f"dangerous profile segment field is not allowed: {key_path}")


def normalize_profile_segment_template_payload(
    payload: dict[str, Any],
    *,
    partial: bool = False,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = deepcopy(payload or {})
    reject_dangerous_profile_segment_fields(source)
    existing = existing or {}

    has_name = "name" in source or "template_name" in source
    name = _text(source.get("name") if "name" in source else source.get("template_name"))
    if not name and existing and not has_name:
        name = _text(existing.get("name"))

    raw_code = (
        source.get("segment_key")
        if "segment_key" in source
        else source.get("code")
        if "code" in source
        else source.get("template_code")
    )
    code = _text(raw_code)
    if not code and existing and not any(key in source for key in ("segment_key", "code", "template_code")):
        code = _text(existing.get("code") or existing.get("segment_key"))
    if not code and name:
        code = _slugify(name)

    description = _text(source.get("description") if "description" in source else existing.get("description"))
    status = _text(source.get("status") if "status" in source else existing.get("status") or "draft").lower()
    if "enabled" in source and "status" not in source:
        status = "active" if bool(source.get("enabled")) else "inactive"
    sort_order = source.get("sort_order") if "sort_order" in source else existing.get("sort_order", 0)
    try:
        sort_order_int = int(sort_order or 0)
    except (TypeError, ValueError) as exc:
        raise ContractError("sort_order must be an integer") from exc

    rules = source.get("rules") if "rules" in source else existing.get("rules", {})
    conditions = source.get("conditions") if "conditions" in source else existing.get("conditions", {})
    if "categories" in source:
        rules = {"categories": deepcopy(source.get("categories") or [])}
    if rules is None:
        rules = {}
    if conditions is None:
        conditions = {}

    normalized = {
        "name": name,
        "description": description,
        "segment_key": code,
        "code": code,
        "rules": deepcopy(rules),
        "conditions": deepcopy(conditions),
        "status": status or "draft",
        "sort_order": sort_order_int,
    }
    validate_profile_segment_template_payload(normalized, partial=partial)
    return normalized


def validate_profile_segment_template_payload(payload: dict[str, Any], *, partial: bool = False) -> None:
    name = _text(payload.get("name"))
    if not partial and not name:
        raise ContractError("name is required")
    if name and len(name) > MAX_NAME_LENGTH:
        raise ContractError(f"name must be at most {MAX_NAME_LENGTH} characters")

    description = _text(payload.get("description"))
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ContractError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    status = _text(payload.get("status") or "draft").lower()
    if status not in ALLOWED_PROFILE_SEGMENT_TEMPLATE_STATUS:
        allowed = ", ".join(sorted(ALLOWED_PROFILE_SEGMENT_TEMPLATE_STATUS))
        raise ContractError(f"status must be one of: {allowed}")

    for key in ("rules", "conditions"):
        value = payload.get(key)
        if not isinstance(value, (dict, list)):
            raise ContractError(f"{key} must be a JSON object or list")
        if _json_size(value) > MAX_RULES_JSON_LENGTH:
            raise ContractError(f"{key} payload is too large")
        if isinstance(value, dict):
            reject_dangerous_profile_segment_fields(value)


def profile_segment_template_projection(template: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(template)
    template_id = int(item.get("id") or item.get("template_id") or 0)
    name = _text(item.get("name") or item.get("template_name"))
    code = _text(item.get("code") or item.get("segment_key") or item.get("template_code"))
    status = _text(item.get("status") or "draft").lower()
    now = utc_now_iso()
    projected = {
        "id": template_id,
        "template_id": template_id,
        "name": name,
        "template_name": name,
        "description": _text(item.get("description")),
        "segment_key": code,
        "code": code,
        "template_code": code,
        "conditions": deepcopy(item.get("conditions") if item.get("conditions") is not None else {}),
        "rules": deepcopy(item.get("rules") if item.get("rules") is not None else {}),
        "status": status if status in ALLOWED_PROFILE_SEGMENT_TEMPLATE_STATUS else "draft",
        "enabled": status == "active",
        "sort_order": int(item.get("sort_order") or 0),
        "created_at": _text(item.get("created_at")) or now,
        "updated_at": _text(item.get("updated_at")) or now,
    }
    return projected
