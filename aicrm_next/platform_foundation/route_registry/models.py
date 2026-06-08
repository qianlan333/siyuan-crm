from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RuntimeOwner = Literal[
    "next_native",
    "next_command",
    "next_adapter",
    "frontend_compat",
    "production_compat",
    "legacy_forward",
    "fake_adapter",
    "sandbox_adapter",
    "real_blocked",
    "unknown",
]
DeleteStatus = Literal[
    "active",
    "replacement_planned",
    "next_shadow",
    "next_primary_with_legacy_rollback",
    "next_primary_no_legacy_rollback",
    "legacy_deleted",
    "deletion_locked",
]
ReplacementStatus = Literal["not_started", "in_progress", "validating", "validated", "deleted", "locked"]
ExternalSideEffectRisk = Literal["none", "low", "medium", "high", "critical"]
AdapterMode = Literal["none", "fake", "sandbox", "real_blocked", "real_enabled"]
LifecycleStatus = Literal["planned", "replacing", "validating", "validated", "deleting", "deleted", "locked", "blocked"]


@dataclass(frozen=True)
class RouteRegistryEntry:
    route_id: str
    path_pattern: str
    methods: tuple[str, ...]
    capability_owner: str
    runtime_owner: RuntimeOwner = "unknown"
    legacy_fallback_allowed: bool = False
    legacy_source: str = ""
    external_side_effect_risk: ExternalSideEffectRisk = "none"
    adapter_mode: AdapterMode = "none"
    delete_status: DeleteStatus = "active"
    replacement_status: ReplacementStatus = "not_started"
    checker: str = ""
    rollback_owner: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["methods"] = list(self.methods)
        return payload


@dataclass(frozen=True)
class LegacyDeletionLifecycleItem:
    legacy_item_id: str
    capability_owner: str
    legacy_path: str
    replacement_path: str = ""
    replacement_pr: str = ""
    validation_pr: str = ""
    deletion_pr: str = ""
    legacy_replaced_at: str = ""
    validated_at: str = ""
    deleted_at: str = ""
    locked_at: str = ""
    delete_checker: str = ""
    rollback_plan: str = ""
    status: LifecycleStatus = "planned"
    notes: str = ""
    sample: bool = False
    production_decision: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteRegistry:
    routes: tuple[RouteRegistryEntry, ...] = field(default_factory=tuple)
    lifecycle_items: tuple[LegacyDeletionLifecycleItem, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": list(self.sources),
            "routes": [route.to_dict() for route in self.routes],
            "lifecycle_items": [item.to_dict() for item in self.lifecycle_items],
        }
