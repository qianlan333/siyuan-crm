from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Json = dict[str, Any]

OVERVIEW_TOP_LEVEL_KEYS = ["ok", "cards", "total", "filters", "generated_at"]
POOL_TOP_LEVEL_KEYS = ["ok", "pools", "total", "generated_at"]
POOL_ITEM_KEYS = ["pool_key", "label", "count", "description", "active_action_count", "allow_broadcast"]
MEMBERS_TOP_LEVEL_KEYS = ["ok", "items", "total", "limit", "offset", "filters"]
MEMBER_ITEM_KEYS = [
    "member_id",
    "person_id",
    "external_userid",
    "mobile",
    "customer_name",
    "owner_userid",
    "current_pool",
    "current_pool_label",
    "followup_type",
    "questionnaire_followup_type",
    "manual_followup_type",
    "trial_opened",
    "activated",
    "converted",
    "exited",
    "silent",
    "latest_event_at",
    "next_action",
    "can_manual_override",
    "can_confirm_conversion",
    "can_enter_silent",
    "can_exit_marketing",
]
MEMBER_DETAIL_TOP_LEVEL_KEYS = ["ok", "member", "history", "customer_context", "recent_timeline_events", "warnings"]
ACTIVATION_TOP_LEVEL_KEYS = ["ok", "member", "previous_pool", "current_pool", "warnings"]
EXECUTION_TOP_LEVEL_KEYS = ["ok", "items", "total", "limit", "offset"]
EXECUTION_ITEM_KEYS = ["id", "record_type", "member_id", "trigger", "status", "status_label", "delivery_status", "payload_preview", "created_at"]


@dataclass(frozen=True)
class EndpointSpec:
    method: str
    path: str
    expected_status: int = 200
    body: Json | None = None


ENDPOINT_SPECS: dict[str, EndpointSpec] = {
    "overview.default": EndpointSpec("GET", "/api/admin/automation-conversion/overview"),
    "pools.default": EndpointSpec("GET", "/api/admin/automation-conversion/pools"),
    "members.default": EndpointSpec("GET", "/api/admin/automation-conversion/members"),
    "member_detail.default": EndpointSpec("GET", "/api/admin/automation-conversion/members/member_002"),
    "activation_webhook.default": EndpointSpec(
        "POST",
        "/api/customer-automation/activation-webhook",
        body={"mobile": "13800138001", "activated_at": "2026-05-20T12:00:00Z", "source": "fixture_audit"},
    ),
    "execution_records.default": EndpointSpec("GET", "/api/admin/automation-conversion/execution-records"),
}

DEFAULT_SAFE_ENDPOINTS = [
    "overview.default",
    "pools.default",
    "members.default",
    "member_detail.default",
    "activation_webhook.default",
    "execution_records.default",
]


def compare_required_keys(payload: Json, required_keys: list[str], *, location: str = "$") -> list[Json]:
    return [
        {"rule": "required_key", "location": location, "key": key, "severity": "fail"}
        for key in required_keys
        if key not in payload
    ]


def compare_item_required_keys(items: Any, required_keys: list[str], *, location: str) -> list[Json]:
    if not isinstance(items, list):
        return [{"rule": "type_family", "location": location, "expected": "list", "actual": type(items).__name__, "severity": "fail"}]
    if not items:
        return []
    if not isinstance(items[0], dict):
        return [{"rule": "type_family", "location": f"{location}[0]", "expected": "object", "actual": type(items[0]).__name__, "severity": "fail"}]
    return compare_required_keys(items[0], required_keys, location=f"{location}[0]")


def validate_payload(endpoint_name: str, payload: Json) -> list[Json]:
    if endpoint_name == "overview.default":
        return compare_required_keys(payload, OVERVIEW_TOP_LEVEL_KEYS) + compare_item_required_keys(payload.get("cards"), ["key", "label", "value"], location="$.cards")
    if endpoint_name == "pools.default":
        return compare_required_keys(payload, POOL_TOP_LEVEL_KEYS) + compare_item_required_keys(payload.get("pools"), POOL_ITEM_KEYS, location="$.pools")
    if endpoint_name == "members.default":
        return compare_required_keys(payload, MEMBERS_TOP_LEVEL_KEYS) + compare_item_required_keys(payload.get("items"), MEMBER_ITEM_KEYS, location="$.items")
    if endpoint_name == "member_detail.default":
        issues = compare_required_keys(payload, MEMBER_DETAIL_TOP_LEVEL_KEYS)
        if isinstance(payload.get("member"), dict):
            issues.extend(compare_required_keys(payload["member"], MEMBER_ITEM_KEYS, location="$.member"))
        return issues
    if endpoint_name == "activation_webhook.default":
        issues = compare_required_keys(payload, ACTIVATION_TOP_LEVEL_KEYS)
        if isinstance(payload.get("member"), dict):
            issues.extend(compare_required_keys(payload["member"], MEMBER_ITEM_KEYS, location="$.member"))
        return issues
    if endpoint_name == "execution_records.default":
        return compare_required_keys(payload, EXECUTION_TOP_LEVEL_KEYS) + compare_item_required_keys(payload.get("items"), EXECUTION_ITEM_KEYS, location="$.items")
    return [{"rule": "unknown_endpoint_spec", "endpoint": endpoint_name, "severity": "fail"}]


def compare_type_family(old_payload: Any, next_payload: Any, *, location: str = "$") -> list[Json]:
    old_family = _type_family(old_payload)
    next_family = _type_family(next_payload)
    if old_family != next_family:
        return [{"rule": "type_family", "location": location, "expected": old_family, "actual": next_family, "severity": "fail"}]
    issues: list[Json] = []
    if isinstance(old_payload, dict) and isinstance(next_payload, dict):
        for key in old_payload.keys() & next_payload.keys():
            issues.extend(compare_type_family(old_payload[key], next_payload[key], location=f"{location}.{key}"))
    elif isinstance(old_payload, list) and old_payload and next_payload:
        issues.extend(compare_type_family(old_payload[0], next_payload[0], location=f"{location}[0]"))
    return issues


def compare_endpoint_payloads(endpoint_name: str, old_payload: Json, next_payload: Json) -> list[Json]:
    issues = validate_payload(endpoint_name, old_payload)
    issues.extend(validate_payload(endpoint_name, next_payload))
    issues.extend(compare_type_family(old_payload, next_payload))
    return issues


def compare_status_code(old_status: int, next_status: int, *, expected_status: int = 200) -> list[Json]:
    issues: list[Json] = []
    if old_status != expected_status:
        issues.append({"rule": "old_status_code", "expected": expected_status, "actual": old_status, "severity": "fail"})
    if next_status != expected_status:
        issues.append({"rule": "next_status_code", "expected": expected_status, "actual": next_status, "severity": "fail"})
    return issues


def _type_family(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str) or value is None:
        return "string_or_null"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
