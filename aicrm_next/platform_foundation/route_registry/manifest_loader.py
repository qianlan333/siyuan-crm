from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import LegacyDeletionLifecycleItem, RouteRegistry, RouteRegistryEntry

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNERSHIP_MANIFEST = REPO_ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
LEGACY_EXIT_MANIFEST = REPO_ROOT / "docs/architecture/legacy_exit_route_registry.yaml"


def _clean_methods(value: Any) -> tuple[str, ...]:
    methods = value if isinstance(value, list) else []
    normalized = sorted({str(method).upper().strip() for method in methods if str(method).strip() and str(method).upper() != "HEAD"})
    return tuple(normalized or ("GET",))


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip("/").replace("{path:path}", "wildcard"))
    return text.strip("_").lower() or "root"


def _runtime_owner(record: dict[str, Any]) -> str:
    owner = str(record.get("runtime_owner") or record.get("current_runtime_owner") or "").strip()
    behavior = str(record.get("production_behavior") or "").strip()
    if owner == "next_adapter" or behavior == "next_adapter":
        return "next_adapter"
    if owner == "next_command" or behavior == "next_command":
        return "next_command"
    if owner in {"next", "ai_crm_next", "next_native"} or owner.startswith("aicrm_next."):
        return "next_native"
    if owner == "frontend_compat":
        return "frontend_compat"
    if owner == "production_compat":
        return "production_compat"
    if owner == "legacy_facade" or behavior == "legacy_forward":
        return "legacy_forward"
    if behavior == "fake_adapter":
        return "fake_adapter"
    if behavior == "real_blocked" or str(record.get("external_side_effect_risk") or "") == "real_blocked":
        return "real_blocked"
    return owner if owner in {"next_command", "next_adapter", "sandbox_adapter", "unknown"} else "unknown"


def _risk(record: dict[str, Any]) -> str:
    risk = str(record.get("external_side_effect_risk") or "").strip()
    return {
        "guarded": "medium",
        "real_blocked": "critical",
        "": "none",
    }.get(risk, risk if risk in {"none", "low", "medium", "high", "critical"} else "medium")


def _adapter_mode(record: dict[str, Any]) -> str:
    explicit = str(record.get("adapter_mode") or "").strip()
    if explicit:
        return explicit
    behavior = str(record.get("production_behavior") or "").strip()
    owner = str(record.get("current_runtime_owner") or "").strip()
    risk = str(record.get("external_side_effect_risk") or "").strip()
    if behavior == "fake_adapter":
        return "fake"
    if risk == "real_blocked" or owner == "blocked":
        return "real_blocked"
    return "none"


def _entry_from_ownership(record: dict[str, Any]) -> RouteRegistryEntry:
    path = str(record.get("route_pattern") or "").strip()
    behavior = str(record.get("production_behavior") or "").strip()
    return RouteRegistryEntry(
        route_id=str(record.get("route_id") or f"ownership_{_slug(path)}"),
        path_pattern=path,
        methods=_clean_methods(record.get("methods")),
        capability_owner=str(record.get("capability_owner") or "unknown"),
        runtime_owner=_runtime_owner(record),  # type: ignore[arg-type]
        legacy_fallback_allowed=bool(record.get("legacy_fallback_allowed")),
        legacy_source="production_route_ownership_manifest" if bool(record.get("legacy_fallback_allowed")) or behavior == "legacy_forward" else "",
        external_side_effect_risk=_risk(record),  # type: ignore[arg-type]
        adapter_mode=_adapter_mode(record),  # type: ignore[arg-type]
        delete_status=str(record.get("delete_status") or "active"),  # type: ignore[arg-type]
        replacement_status=str(record.get("replacement_status") or "not_started"),  # type: ignore[arg-type]
        checker=str(record.get("checker") or ""),
        rollback_owner=str(record.get("rollback_owner") or record.get("capability_owner") or ""),
        notes=str(record.get("notes") or ""),
    )


def _entry_from_legacy_exit(record: dict[str, Any]) -> RouteRegistryEntry:
    path = str(record.get("path_pattern") or record.get("route_pattern") or "").strip()
    return RouteRegistryEntry(
        route_id=str(record.get("route_id") or f"legacy_exit_{_slug(path)}"),
        path_pattern=path,
        methods=_clean_methods(record.get("methods")),
        capability_owner=str(record.get("capability_owner") or "unknown"),
        runtime_owner=str(record.get("runtime_owner") or "unknown"),  # type: ignore[arg-type]
        legacy_fallback_allowed=bool(record.get("legacy_fallback_allowed", False)),
        legacy_source=str(record.get("legacy_source") or ""),
        external_side_effect_risk=str(record.get("external_side_effect_risk") or "none"),  # type: ignore[arg-type]
        adapter_mode=str(record.get("adapter_mode") or "none"),  # type: ignore[arg-type]
        delete_status=str(record.get("delete_status") or "active"),  # type: ignore[arg-type]
        replacement_status=str(record.get("replacement_status") or "not_started"),  # type: ignore[arg-type]
        checker=str(record.get("checker") or ""),
        rollback_owner=str(record.get("rollback_owner") or ""),
        notes=str(record.get("notes") or ""),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_route_registry(
    ownership_manifest: Path | None = None,
    legacy_exit_manifest: Path | None = None,
) -> RouteRegistry:
    ownership_path = ownership_manifest or OWNERSHIP_MANIFEST
    legacy_exit_path = legacy_exit_manifest or LEGACY_EXIT_MANIFEST
    sources: list[str] = []
    entries: list[RouteRegistryEntry] = []

    ownership = _load_yaml(ownership_path)
    if ownership:
        sources.append(str(ownership_path.relative_to(REPO_ROOT)))
        entries.extend(_entry_from_ownership(record) for record in ownership.get("routes") or [])

    legacy_exit = _load_yaml(legacy_exit_path)
    lifecycle: list[LegacyDeletionLifecycleItem] = []
    if legacy_exit:
        sources.append(str(legacy_exit_path.relative_to(REPO_ROOT)))
        by_id = {entry.route_id: entry for entry in entries}
        by_path = {(entry.path_pattern, entry.methods): entry for entry in entries}
        for raw in legacy_exit.get("routes") or []:
            entry = _entry_from_legacy_exit(raw)
            if entry.route_id in by_id:
                entries[entries.index(by_id[entry.route_id])] = entry
            elif (entry.path_pattern, entry.methods) in by_path:
                entries[entries.index(by_path[(entry.path_pattern, entry.methods)])] = entry
            else:
                entries.append(entry)
        lifecycle.extend(LegacyDeletionLifecycleItem(**item) for item in legacy_exit.get("lifecycle_items") or [])

    return RouteRegistry(routes=tuple(entries), lifecycle_items=tuple(lifecycle), sources=tuple(sources))
