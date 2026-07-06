from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .application import (
    data_health_check_detail,
    data_health_checks,
    data_health_summary,
    data_quality_check_detail,
    data_quality_checks,
    data_quality_groups,
    data_quality_summary,
)


router = APIRouter()


@router.get("/api/admin/data-health/summary")
def api_data_health_summary() -> JSONResponse:
    return _json(data_health_summary())


@router.get("/api/admin/data-health/checks")
def api_data_health_checks() -> JSONResponse:
    return _json(data_health_checks())


@router.get("/api/admin/data-health/checks/{check_id}")
def api_data_health_check_detail(check_id: str) -> JSONResponse:
    return _json(data_health_check_detail(check_id))


@router.get("/api/admin/data-quality/summary")
def api_data_quality_summary() -> JSONResponse:
    return _json(data_quality_summary())


@router.get("/api/admin/data-quality/groups")
def api_data_quality_groups() -> JSONResponse:
    return _json(data_quality_groups())


@router.get("/api/admin/data-quality/checks")
def api_data_quality_checks() -> JSONResponse:
    return _json(data_quality_checks())


@router.get("/api/admin/data-quality/checks/{check_id}")
def api_data_quality_check_detail(check_id: str) -> JSONResponse:
    return _json(data_quality_check_detail(check_id))


def _json(payload: dict) -> JSONResponse:
    return JSONResponse(payload, status_code=int(payload.get("status_code") or 200))
