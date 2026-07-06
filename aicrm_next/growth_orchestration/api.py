from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .application import list_growth_members, list_growth_programs, list_growth_tasks, list_growth_touchpoints


router = APIRouter()


@router.get("/api/admin/growth-orchestration/programs")
def api_growth_orchestration_programs(limit: int = 50, offset: int = 0) -> JSONResponse:
    return JSONResponse(list_growth_programs(limit=limit, offset=offset))


@router.get("/api/admin/growth-orchestration/members")
def api_growth_orchestration_members(limit: int = 50, offset: int = 0) -> JSONResponse:
    return JSONResponse(list_growth_members(limit=limit, offset=offset))


@router.get("/api/admin/growth-orchestration/tasks")
def api_growth_orchestration_tasks(limit: int = 50, offset: int = 0) -> JSONResponse:
    return JSONResponse(list_growth_tasks(limit=limit, offset=offset))


@router.get("/api/admin/growth-orchestration/touchpoints")
def api_growth_orchestration_touchpoints(limit: int = 50, offset: int = 0) -> JSONResponse:
    return JSONResponse(list_growth_touchpoints(limit=limit, offset=offset))
