from __future__ import annotations

from typing import Any, Iterable


ALL_CAPABILITIES = frozenset(
    {
        "admin_read",
        "manage_admin",
        "manage_automation",
        "manage_commerce",
        "manage_config",
        "manage_content",
        "manage_customer",
        "manage_group_ops",
        "manage_operations",
        "manage_questionnaire",
        "read_customer",
        "refund",
        "send_message",
    }
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "super_admin": ALL_CAPABILITIES,
    "config_admin": frozenset({"admin_read", "manage_admin", "manage_config"}),
    "automation_admin": frozenset(
        {
            "admin_read",
            "manage_automation",
            "manage_content",
            "manage_customer",
            "manage_group_ops",
            "read_customer",
            "send_message",
        }
    ),
    "questionnaire_admin": frozenset(
        {"admin_read", "manage_customer", "manage_questionnaire", "read_customer"}
    ),
    "viewer": frozenset({"admin_read", "read_customer"}),
}


def normalize_roles(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip()))


def capabilities_for_roles(values: Iterable[Any]) -> frozenset[str]:
    capabilities: set[str] = set()
    for role in normalize_roles(values):
        capabilities.update(ROLE_CAPABILITIES.get(role, ()))
    return frozenset(capabilities)


def session_roles(session: dict[str, Any] | None) -> tuple[str, ...]:
    return normalize_roles((session or {}).get("roles") or ())


def session_can(session: dict[str, Any] | None, capability: str) -> bool:
    return str(capability or "").strip() in capabilities_for_roles(session_roles(session))


def viewer_only(session: dict[str, Any] | None) -> bool:
    return session_roles(session) == ("viewer",)
