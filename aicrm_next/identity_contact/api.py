from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .application import GetSidebarContactBindingStatusQuery, ResolvePersonIdentityQuery
from .dto import ResolvePersonIdentityRequest

router = APIRouter()


@router.get("/api/identity/resolve")
def resolve_identity(
    external_userid: str | None = None,
    mobile: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
) -> dict:
    result = ResolvePersonIdentityQuery()(
        ResolvePersonIdentityRequest(
            external_userid=external_userid,
            mobile=mobile,
            openid=openid,
            unionid=unionid,
        )
    )
    if result is None:
        raise HTTPException(status_code=404, detail="identity not found")
    return {"ok": True, "identity": result.model_dump()}


@router.get("/api/sidebar/contact-binding-status")
def sidebar_contact_binding_status(
    external_userid: str | None = None,
    owner_userid: str | None = None,
):
    result = GetSidebarContactBindingStatusQuery()(
        external_userid=external_userid,
        owner_userid=owner_userid,
    )
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


@router.get("/api/sidebar/binding-status")
def sidebar_binding_status(
    external_userid: str | None = None,
    owner_userid: str | None = None,
):
    result = GetSidebarContactBindingStatusQuery()(
        external_userid=external_userid,
        owner_userid=owner_userid,
    )
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)
