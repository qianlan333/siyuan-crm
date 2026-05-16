from __future__ import annotations

from typing import Any

from flask import has_app_context

from . import repo
from .definitions import (
    DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
    OWNER_CLASS_TERM_BACKFILL_ENTRY_SOURCE_OVERRIDES,
    ROUTING_REASON_OWNER_ROLE_MISSING,
    ROUTING_REASON_OWNER_ROLE_UNKNOWN,
    ROUTING_REASON_SIGNUP_STATUS_UNKNOWN,
    ROUTING_RULES,
)

OWNER_ROLE_OPTIONS = ("sales", "delivery", "ops", "admin")
ROUTING_TARGET_OPTIONS = (
    "sales_handle",
    "delivery_redirect",
    "delivery_handle",
    "manual_review",
)


def _normalize_owner_role_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userid": str(row.get("userid") or "").strip(),
        "display_name": str(row.get("display_name") or "").strip(),
        "role": str(row.get("role") or "").strip(),
        "active": bool(row.get("active")),
        "updated_at": str(row.get("updated_at") or "").strip(),
    }


def _normalize_routing_rule_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_key": str(row.get("rule_key") or "").strip(),
        "routing_alias": str(row.get("routing_alias") or "").strip(),
        "route_owner_userid": str(row.get("route_owner_userid") or "").strip(),
        "route_owner_role": str(row.get("route_owner_role") or "").strip(),
        "routing_target": str(row.get("routing_target") or "").strip(),
        "fallback_target": str(row.get("fallback_target") or "").strip(),
        "when_owner_role_sales": str(row.get("when_owner_role_sales") or "").strip(),
        "when_owner_role_delivery": str(row.get("when_owner_role_delivery") or "").strip(),
        "active": bool(row.get("active")),
        "updated_at": str(row.get("updated_at") or "").strip(),
    }


def _seed_rule_payload(rule_key: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_key": rule_key,
        "routing_alias": rule_key if rule_key not in {"unknown", "owner_role_missing"} else "",
        "route_owner_userid": str(value.get("route_owner_userid") or "").strip(),
        "route_owner_role": str(value.get("route_owner_role") or "").strip(),
        "routing_target": str(value.get("routing_target") or "").strip(),
        "fallback_target": str(value.get("fallback") or "").strip(),
        "when_owner_role_sales": str(value.get("when_owner_role_sales") or "").strip(),
        "when_owner_role_delivery": str(value.get("when_owner_role_delivery") or "").strip(),
        "active": True,
    }


def ensure_routing_rule_config_seed() -> None:
    if not has_app_context():
        return
    existing_rows = [_normalize_routing_rule_item(dict(row)) for row in repo.list_routing_rules(active_only=False)]
    existing_keys = {row["rule_key"] for row in existing_rows}
    for rule_key, value in ROUTING_RULES.items():
        if rule_key in existing_keys:
            continue
        seeded = _seed_rule_payload(rule_key, value)
        repo.upsert_routing_rule(
            rule_key=seeded["rule_key"],
            routing_alias=seeded["routing_alias"],
            route_owner_userid=seeded["route_owner_userid"],
            route_owner_role=seeded["route_owner_role"],
            routing_target=seeded["routing_target"],
            fallback_target=seeded["fallback_target"],
            when_owner_role_sales=seeded["when_owner_role_sales"],
            when_owner_role_delivery=seeded["when_owner_role_delivery"],
            active=seeded["active"],
        )


def get_owner_role(userid: str) -> dict[str, Any] | None:
    row = repo.get_owner_role(str(userid or "").strip())
    return _normalize_owner_role_item(dict(row)) if row else None


def list_owner_role_map(active_only: bool = False) -> list[dict[str, Any]]:
    return [_normalize_owner_role_item(dict(row)) for row in repo.list_owner_role_map(active_only=active_only)]


def list_routing_rules(active_only: bool = False) -> list[dict[str, Any]]:
    if not has_app_context():
        return [_seed_rule_payload(rule_key, value) for rule_key, value in ROUTING_RULES.items()]
    ensure_routing_rule_config_seed()
    return [_normalize_routing_rule_item(dict(row)) for row in repo.list_routing_rules(active_only=active_only)]


def get_routing_rule(rule_key: str) -> dict[str, Any] | None:
    if not has_app_context():
        seeded = ROUTING_RULES.get(str(rule_key or "").strip())
        return _seed_rule_payload(str(rule_key or "").strip(), seeded) if seeded else None
    ensure_routing_rule_config_seed()
    row = repo.get_routing_rule(str(rule_key or "").strip())
    return _normalize_routing_rule_item(dict(row)) if row else None


def build_routing_config(
    *,
    owner_role_map: list[dict[str, Any]] | None = None,
    signup_tag_rules: dict[str, Any],
) -> dict[str, Any]:
    owner_role_items = owner_role_map if owner_role_map is not None else list_owner_role_map()
    return {
        "owner_role_map": [dict(item) for item in owner_role_items],
        "signup_tag_rules": dict(signup_tag_rules),
        "routing_rules": {item["rule_key"]: dict(item) for item in list_routing_rules(active_only=False)},
    }


def _routing_rules_by_key() -> dict[str, dict[str, Any]]:
    rules = {item["rule_key"]: item for item in list_routing_rules(active_only=False)}
    for rule_key, value in ROUTING_RULES.items():
        rules.setdefault(rule_key, _seed_rule_payload(rule_key, value))
    return rules


def resolve_contact_routing_context(
    *,
    owner_userid: str,
    owner_role: str,
    signup_status: str,
    routing_alias: str = "",
) -> dict[str, Any]:
    del owner_userid

    rules = _routing_rules_by_key()
    normalized_owner_role = str(owner_role or "").strip()
    routing_status = str(routing_alias or signup_status or "").strip()

    owner_missing_rule = rules.get("owner_role_missing") or {}
    unknown_rule = rules.get("unknown") or {}

    if not normalized_owner_role:
        return {
            "routing_target": str(owner_missing_rule.get("routing_target") or "manual_review"),
            "route_owner_userid": str(owner_missing_rule.get("route_owner_userid") or "").strip(),
            "reason": ROUTING_REASON_OWNER_ROLE_MISSING,
        }

    target_rule = rules.get(routing_status)
    if target_rule and str(target_rule.get("routing_target") or "").strip():
        return {
            "routing_target": str(target_rule.get("routing_target") or "").strip(),
            "route_owner_userid": str(target_rule.get("route_owner_userid") or "").strip(),
        }

    if routing_status == "signed_3999" and target_rule:
        if normalized_owner_role == "sales":
            return {
                "routing_target": (
                    str(target_rule.get("when_owner_role_sales") or "").strip()
                    or str(target_rule.get("fallback_target") or "").strip()
                    or str(unknown_rule.get("routing_target") or "manual_review")
                ),
                "route_owner_userid": (
                    str(target_rule.get("route_owner_userid") or "").strip() or DEFAULT_DELIVERY_ROUTE_OWNER_USERID
                ),
            }
        if normalized_owner_role == "delivery":
            return {
                "routing_target": (
                    str(target_rule.get("when_owner_role_delivery") or "").strip()
                    or str(target_rule.get("fallback_target") or "").strip()
                    or str(unknown_rule.get("routing_target") or "manual_review")
                ),
                "route_owner_userid": (
                    str(target_rule.get("route_owner_userid") or "").strip() or DEFAULT_DELIVERY_ROUTE_OWNER_USERID
                ),
            }
        return {
            "routing_target": str(target_rule.get("fallback_target") or unknown_rule.get("routing_target") or "manual_review"),
            "route_owner_userid": str(target_rule.get("route_owner_userid") or "").strip(),
            "reason": ROUTING_REASON_OWNER_ROLE_UNKNOWN,
        }

    if routing_status in rules:
        return {
            "routing_target": str(unknown_rule.get("routing_target") or "manual_review"),
            "route_owner_userid": str(unknown_rule.get("route_owner_userid") or "").strip(),
            "reason": ROUTING_REASON_OWNER_ROLE_UNKNOWN,
        }
    return {
        "routing_target": str(unknown_rule.get("routing_target") or "manual_review"),
        "route_owner_userid": str(unknown_rule.get("route_owner_userid") or "").strip(),
        "reason": ROUTING_REASON_SIGNUP_STATUS_UNKNOWN,
    }


def get_owner_class_term_backfill_entry_source_override(owner_userid: str) -> str:
    normalized_owner_userid = str(owner_userid or "").strip()
    return OWNER_CLASS_TERM_BACKFILL_ENTRY_SOURCE_OVERRIDES.get(normalized_owner_userid, "")
