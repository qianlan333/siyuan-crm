from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .application import GetAiAssistContractQuery
from .external_campaigns import create_external_campaigns_response
from .external_campaigns import get_external_campaign_status_response

router = APIRouter()


@router.get("/api/admin/ai-assist/contract")
def ai_assist_contract() -> dict:
    return GetAiAssistContractQuery()()


@router.post("/api/ai-assist/external/campaigns")
async def create_external_campaigns(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "invalid_json", "route_owner": "ai_crm_next"},
            status_code=400,
        )
    return create_external_campaigns_response(payload, request.headers)


@router.get("/api/ai-assist/external/campaigns/{campaign_code}")
async def get_external_campaign(campaign_code: str, request: Request):
    return get_external_campaign_status_response(campaign_code, request.headers)
