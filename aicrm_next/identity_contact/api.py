from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse

from aicrm_next.shared.signed_context import load_sidebar_owner_context_token

from .application import GetSidebarContactBindingStatusQuery, ResolvePersonIdentityQuery
from .dto import ResolvePersonIdentityRequest

router = APIRouter()
SIDEBAR_OWNER_TOKEN_HEADER = "x-aicrm-sidebar-owner-token"


def _identity_error(*, error_code: str, message: str, source_status: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error_code": error_code,
            "message": message,
            "route_owner": "ai_crm_next",
            "source_status": source_status,
            "fallback_used": False,
        },
        status_code=status_code,
    )


def _identity_links(identity) -> dict:
    data = identity.model_dump() if hasattr(identity, "model_dump") else dict(identity or {})
    return {
        "person_id": data.get("person_id") or "",
        "external_userid": data.get("external_userid") or "",
        "mobile": data.get("mobile") or "",
        "openid": data.get("openid") or "",
        "unionid": data.get("unionid") or "",
        "user_id": data.get("external_userid") or "",
        "buyer_id": data.get("openid") or "",
    }


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


@router.get(
    "/api/admin/identity/resolve",
    summary="后台身份解析",
    description=(
        "Session Cookie 后台身份解析 wrapper，复用 ResolvePersonIdentityQuery。"
        "支持 external_userid/mobile/openid/unionid；user_id 会安全映射到 external_userid，buyer_id 会映射到 openid，transaction_id 仅进入 warnings。"
    ),
)
def admin_resolve_identity(
    external_userid: str | None = Query(None, description="企业微信外部联系人 external_userid"),
    mobile: str | None = Query(None, description="手机号"),
    openid: str | None = Query(None, description="公众号或支付侧 openid"),
    unionid: str | None = Query(None, description="微信 unionid"),
    user_id: str | None = Query(None, description="后台兼容 user_id；本阶段按 external_userid 尝试解析"),
    buyer_id: str | None = Query(None, description="支付宝 buyer_id；本阶段按 openid 尝试解析"),
    transaction_id: str | None = Query(None, description="支付平台交易号；当前 ResolvePersonIdentityRequest 不支持，返回 warnings"),
) -> JSONResponse:
    warnings: list[str] = []
    mapped_external_userid = external_userid or user_id
    mapped_openid = openid or buyer_id
    if user_id and not external_userid:
        warnings.append("user_id was mapped to external_userid for this slice")
    if buyer_id and not openid:
        warnings.append("buyer_id was mapped to openid for this slice")
    if transaction_id:
        warnings.append("transaction_id cannot be mapped by ResolvePersonIdentityRequest in this slice")
    result = ResolvePersonIdentityQuery()(
        ResolvePersonIdentityRequest(
            external_userid=mapped_external_userid,
            mobile=mobile,
            openid=mapped_openid,
            unionid=unionid,
        )
    )
    if result is None:
        return _identity_error(
            error_code="not_found",
            message="identity not found",
            source_status="next_admin_identity_resolve",
            status_code=404,
        )
    return JSONResponse(
        {
            "ok": True,
            "identity": result.model_dump(),
            "warnings": warnings,
            "route_owner": "ai_crm_next",
            "source_status": "next_admin_identity_resolve",
            "fallback_used": False,
        }
    )


@router.get(
    "/api/admin/identity/links/{identity_key}",
    summary="后台统一身份链路",
    description="按 external_userid、mobile、unionid、openid 等任意 identity_key 解析统一身份链路。找不到时返回结构化 not_found。",
)
def admin_identity_links(
    identity_key: str = Path(..., description="external_userid、mobile、openid、unionid、user_id 或 buyer_id"),
) -> JSONResponse:
    query = ResolvePersonIdentityQuery()
    key = str(identity_key or "").strip()
    attempts = [
        ResolvePersonIdentityRequest(external_userid=key),
        ResolvePersonIdentityRequest(mobile=key),
        ResolvePersonIdentityRequest(unionid=key),
        ResolvePersonIdentityRequest(openid=key),
    ]
    for request in attempts:
        result = query(request)
        if result is not None:
            return JSONResponse(
                {
                    "ok": True,
                    "identity_key": key,
                    "links": _identity_links(result),
                    "identity": result.model_dump(),
                    "route_owner": "ai_crm_next",
                    "source_status": "next_admin_identity_links",
                    "fallback_used": False,
                }
            )
    return _identity_error(
        error_code="not_found",
        message="identity links not found",
        source_status="next_admin_identity_links",
        status_code=404,
    )


@router.get("/api/sidebar/contact-binding-status")
def sidebar_contact_binding_status(
    request: Request,
    external_userid: str | None = None,
    owner_userid: str | None = None,
):
    resolved_owner_userid = _sidebar_owner_userid_from_request(request, owner_userid=owner_userid)
    result = GetSidebarContactBindingStatusQuery()(
        external_userid=external_userid,
        owner_userid=resolved_owner_userid,
        require_owner_scope=True,
    )
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


@router.get("/api/sidebar/binding-status")
def sidebar_binding_status(
    request: Request,
    external_userid: str | None = None,
    owner_userid: str | None = None,
):
    resolved_owner_userid = _sidebar_owner_userid_from_request(request, owner_userid=owner_userid)
    result = GetSidebarContactBindingStatusQuery()(
        external_userid=external_userid,
        owner_userid=resolved_owner_userid,
        require_owner_scope=True,
    )
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


def _sidebar_owner_userid_from_request(request: Request, *, owner_userid: str | None = None) -> str:
    token = (
        str(request.headers.get(SIDEBAR_OWNER_TOKEN_HEADER) or "").strip()
        or str(request.query_params.get("sidebar_owner_token") or "").strip()
        or str(request.query_params.get("owner_token") or "").strip()
    )
    token_result = load_sidebar_owner_context_token(token)
    if token_result.get("ok"):
        context = dict(token_result.get("context") or {})
        return str(context.get("owner_userid") or context.get("viewer_userid") or "").strip()
    return str(owner_userid or "").strip()
