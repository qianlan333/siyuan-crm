from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import shell_context

from .checker import build_route_check_report
from .service import get_route_registry_service

router = APIRouter()
templates = Jinja2Templates(directory="aicrm_next/frontend_compat/templates")


def _filters(request: Request) -> dict[str, str]:
    allowed = {
        "runtime_owner",
        "legacy_fallback_allowed",
        "delete_status",
        "capability_owner",
        "external_side_effect_risk",
    }
    return {key: str(request.query_params.get(key) or "").strip() for key in allowed}


def _stats(routes: list[dict], report: dict) -> dict[str, int]:
    return {
        "total_routes": len(routes),
        "next_native_routes": len([route for route in routes if route["runtime_owner"] == "next_native"]),
        "legacy_fallback_routes": len([route for route in routes if route["legacy_fallback_allowed"]]),
        "wildcard_routes": len(report["wildcard_routes"]),
        "delete_" + "ready_routes": len([route for route in routes if route["delete_status"] in {"next_primary_no_legacy_rollback", "deletion_locked"} or route["replacement_status"] == "validated"]),
        "deleted_locked_routes": len([route for route in routes if route["delete_status"] in {"legacy_deleted", "deletion_locked"}]),
        "unknown_owner_routes": len([route for route in routes if route["runtime_owner"] == "unknown"]),
    }


@router.get("/api/admin/system/routes")
def api_admin_system_routes(request: Request) -> dict:
    service = get_route_registry_service()
    filters = _filters(request)
    routes = []
    for route in service.filtered_routes(filters):
        payload = route.to_dict()
        payload["lifecycle_items"] = [item.to_dict() for item in service.lifecycle_for_route(route.path_pattern)]
        routes.append(payload)
    report = build_route_check_report(service=service, strict=False)
    return {
        "ok": True,
        "filters": filters,
        "sources": list(service._registry.sources),
        "stats": _stats(routes, report),
        "checker": report,
        "routes": routes,
    }


@router.get("/admin/system/routes", response_class=HTMLResponse)
def admin_system_routes(request: Request):
    payload = api_admin_system_routes(request)
    context = shell_context(
        request=request,
        page_title="Route Registry",
        page_summary="生产 route owner、legacy fallback 与删除生命周期状态。",
        active_endpoint="api.admin_system_routes",
    )
    context.update(payload)
    return templates.TemplateResponse(request, "admin_console/route_registry.html", context)
