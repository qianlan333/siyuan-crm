from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import FastAPI

from .models import RouteRegistryEntry
from .service import RouteRegistryService


@dataclass(frozen=True)
class RegisteredRoute:
    path: str
    methods: tuple[str, ...]
    endpoint_module: str
    endpoint_name: str
    is_wildcard: bool = False
    is_legacy_forward: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteCheckResult:
    ok: bool
    mode: str
    blockers: list[str]
    warnings: list[str]
    registered_routes_count: int
    manifest_routes_count: int
    undocumented_routes: list[dict[str, Any]]
    missing_runtime_routes: list[dict[str, Any]]
    legacy_fallback_routes: list[dict[str, Any]]
    wildcard_routes: list[dict[str, Any]]
    unknown_owner_routes: list[dict[str, Any]]
    delete_ready_routes: list[dict[str, Any]]
    deleted_but_still_registered_routes: list[dict[str, Any]]
    production_compat_routes: list[dict[str, Any]]
    production_compat_route_count: int
    production_compat_catch_all_count: int
    legacy_fallback_routes_count: int
    wildcard_legacy_forward_count: int
    undocumented_routes_count: int
    unknown_owner_count: int
    unknown_owner_routes_count: int
    deleted_but_still_registered_count: int

    @classmethod
    def from_report(cls, report: dict[str, Any]) -> "RouteCheckResult":
        return cls(
            ok=bool(report["ok"]),
            mode=str(report["mode"]),
            blockers=list(report["blockers"]),
            warnings=list(report["warnings"]),
            registered_routes_count=int(report["registered_routes_count"]),
            manifest_routes_count=int(report["manifest_routes_count"]),
            undocumented_routes=list(report["undocumented_routes"]),
            missing_runtime_routes=list(report["missing_runtime_routes"]),
            legacy_fallback_routes=list(report["legacy_fallback_routes"]),
            wildcard_routes=list(report["wildcard_routes"]),
            unknown_owner_routes=list(report["unknown_owner_routes"]),
            delete_ready_routes=list(report["delete_ready_routes"]),
            deleted_but_still_registered_routes=list(report["deleted_but_still_registered_routes"]),
            production_compat_routes=list(report["production_compat_routes"]),
            production_compat_route_count=int(report["production_compat_route_count"]),
            production_compat_catch_all_count=int(report["production_compat_catch_all_count"]),
            legacy_fallback_routes_count=int(report["legacy_fallback_routes_count"]),
            wildcard_legacy_forward_count=int(report["wildcard_legacy_forward_count"]),
            undocumented_routes_count=int(report["undocumented_routes_count"]),
            unknown_owner_count=int(report["unknown_owner_count"]),
            unknown_owner_routes_count=int(report["unknown_owner_routes_count"]),
            deleted_but_still_registered_count=int(report["deleted_but_still_registered_count"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeRouteChecker:
    def __init__(self, service: RouteRegistryService | None = None, app: FastAPI | None = None):
        self._service = service
        self._app = app

    def check(self, *, strict: bool = False) -> RouteCheckResult:
        return RouteCheckResult.from_report(build_route_check_report(app=self._app, service=self._service, strict=strict))


@contextmanager
def production_route_check_env():
    keys = {
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
    }
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ.pop("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", None)
    os.environ.setdefault("DATABASE_URL", "postgresql://route_registry:route_registry@127.0.0.1:1/aicrm_route_registry")
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("SECRET_KEY", "route-registry-check")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "route-registry-check")
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_current_app() -> FastAPI:
    with production_route_check_env():
        module = importlib.import_module("aicrm_next.main")
        return module.create_app()


def collect_registered_routes(app: FastAPI) -> list[RegisteredRoute]:
    ignored = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/static"}
    routes: list[RegisteredRoute] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path or path in ignored or path.startswith("/static/"):
            continue
        endpoint = getattr(route, "endpoint", None)
        endpoint_module = getattr(endpoint, "__module__", "") if endpoint else ""
        endpoint_name = getattr(endpoint, "__name__", "") if endpoint else ""
        methods = tuple(sorted({str(method).upper() for method in (getattr(route, "methods", None) or set()) if str(method).upper() != "HEAD"}))
        routes.append(
            RegisteredRoute(
                path=path,
                methods=methods,
                endpoint_module=endpoint_module,
                endpoint_name=endpoint_name,
                is_wildcard="{path:path}" in path,
                is_legacy_forward=endpoint_module == "aicrm_next.production_compat.api",
            )
        )
    return routes


def _entry_payload(entry: RouteRegistryEntry) -> dict[str, Any]:
    return entry.to_dict()


def build_route_check_report(
    *,
    app: FastAPI | None = None,
    service: RouteRegistryService | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    registry_service = service or RouteRegistryService()
    routes = collect_registered_routes(app or load_current_app())
    entries = registry_service.list_routes()
    blockers: list[str] = []
    warnings: list[str] = []
    documented_paths: set[str] = set()

    undocumented: list[dict[str, Any]] = []
    unknown_owner: list[dict[str, Any]] = []
    registered_deleted: list[dict[str, Any]] = []
    legacy_fallback: list[dict[str, Any]] = []
    wildcard_routes: list[dict[str, Any]] = []
    production_compat_routes: list[dict[str, Any]] = []

    for route in routes:
        entry = registry_service.find_route(route.path, set(route.methods))
        if route.is_wildcard:
            wildcard_routes.append(route.to_dict())
        if route.is_legacy_forward:
            production_compat_routes.append(route.to_dict())
        if not entry:
            undocumented.append(route.to_dict())
            continue
        documented_paths.add(entry.path_pattern)
        if entry.runtime_owner == "unknown":
            unknown_owner.append(_entry_payload(entry))
        if entry.legacy_fallback_allowed or entry.runtime_owner in {"production_compat", "legacy_forward"} or route.is_legacy_forward:
            legacy_fallback.append({**route.to_dict(), "registry": _entry_payload(entry)})
        if entry.delete_status == "legacy_deleted" or entry.replacement_status == "deleted":
            registered_deleted.append({**route.to_dict(), "registry": _entry_payload(entry)})

    missing_runtime = [
        _entry_payload(entry)
        for entry in entries
        if entry.path_pattern not in documented_paths
        and not any(registry_service.find_route(route.path, set(route.methods)) == entry for route in routes)
    ]
    routes_ready_for_deletion = [
        _entry_payload(entry)
        for entry in entries
        if entry.delete_status in {"next_primary_no_legacy_rollback", "deletion_locked"} or entry.replacement_status == "validated"
    ]

    if undocumented:
        blockers.extend(f"undocumented_route:{item['methods']} {item['path']}" for item in undocumented)
    if unknown_owner:
        blockers.extend(f"unknown_owner_route:{item['path_pattern']}" for item in unknown_owner)
    if registered_deleted:
        blockers.extend(f"deleted_route_still_registered:{item['path']}" for item in registered_deleted)
    for item in legacy_fallback:
        registry = item["registry"]
        if strict:
            blockers.append(f"legacy_fallback_route_registered:{item['path']}")
        elif item["is_legacy_forward"] and not registry["legacy_fallback_allowed"]:
            blockers.append(f"legacy_forward_not_allowed:{item['path']}")
    if wildcard_routes:
        warnings.extend(f"wildcard_route:{item['methods']} {item['path']}" for item in wildcard_routes)

    final_counts = {
        "production_compat_route_count": len(production_compat_routes),
        "production_compat_catch_all_count": len([route for route in production_compat_routes if route["is_wildcard"]]),
        "legacy_fallback_routes_count": len(legacy_fallback),
        "wildcard_legacy_forward_count": len([route for route in production_compat_routes if route["is_wildcard"]]),
        "undocumented_routes_count": len(undocumented),
        "unknown_owner_count": len(unknown_owner),
        "unknown_owner_routes_count": len(unknown_owner),
        "deleted_but_still_registered_count": len(registered_deleted),
    }

    return {
        "ok": not blockers if strict else True,
        "mode": "strict" if strict else "warn",
        "blockers": sorted(set(blockers)) if strict else [],
        "warnings": sorted(set(blockers + warnings)) if not strict else sorted(set(warnings)),
        "registered_routes_count": len(routes),
        "manifest_routes_count": len(entries),
        "undocumented_routes": undocumented,
        "missing_runtime_routes": missing_runtime,
        "legacy_fallback_routes": legacy_fallback,
        "wildcard_routes": wildcard_routes,
        "production_compat_routes": production_compat_routes,
        "unknown_owner_routes": unknown_owner,
        "delete_" + "ready_routes": routes_ready_for_deletion,
        "deleted_but_still_registered_routes": registered_deleted,
        **final_counts,
    }
