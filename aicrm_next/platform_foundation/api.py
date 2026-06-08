from __future__ import annotations

from fastapi import APIRouter

from .application import GetSystemHealthQuery
from .route_registry.router import router as route_registry_router
from aicrm_next.shared.runtime import runtime_route_map_state

router = APIRouter()
router.include_router(route_registry_router)


@router.get("/health")
def health() -> dict:
    return GetSystemHealthQuery()()


@router.get("/api/system/health")
def system_health() -> dict:
    return GetSystemHealthQuery()()


@router.get("/api/system/runtime-route-map")
def runtime_route_map() -> dict:
    return runtime_route_map_state()
