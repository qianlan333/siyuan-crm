from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import shell_context
from aicrm_next.public_product import h5_wechat_pay
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.share_qr import svg_qr_data_url
from aicrm_next.shared.sync_request import read_request_json

from .application import (
    CopyServicePeriodProductCommand,
    CreateServicePeriodProductCommand,
    DeleteServicePeriodProductCommand,
    GetPublicServicePeriodProductQuery,
    GetServicePeriodProductBySlugQuery,
    GetServicePeriodProductQuery,
    GetServicePeriodProductStatsQuery,
    GetServicePeriodPublicStateQuery,
    ListServicePeriodMembersQuery,
    ListServicePeriodProductsQuery,
    SetServicePeriodProductEnabledCommand,
    UpdateServicePeriodProductCommand,
)
from .dto import ServicePeriodProductCreateRequest, ServicePeriodProductUpdateRequest
from .public import render_service_period_public_page


router = APIRouter()
LOGGER = logging.getLogger(__name__)
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FRONTEND_COMPAT_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=[_TEMPLATES_DIR, _FRONTEND_COMPAT_TEMPLATES_DIR])


def route_headers() -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "false",
        "X-AICRM-Payment-Request-Executed": "false",
        "X-AICRM-Order-Create-Executed": "false",
    }


def product_not_found_payload(path: str) -> dict[str, object]:
    return {
        "ok": False,
        "error": "service_period_product_not_found",
        "error_code": "service_period_product_not_found",
        "message": "Service period product path is not configured.",
        "path": str(path or "").strip().strip("/"),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
        "payment_request_executed": False,
        "order_create_executed": False,
    }


def _inactive_public_state(product: dict) -> dict:
    return {
        "ok": True,
        "available": False,
        "product": {
            "title": product.get("title") or product.get("name"),
            "price_cents": int(product.get("price_cents") or product.get("amount_total") or 0),
            "currency": str(product.get("currency") or "CNY"),
            "duration_days": int(product.get("duration_days") or 0),
        },
        "service_product": product,
        "entitlement": {"status": "unavailable", "remaining_days": 0, "end_at": ""},
        "cta_text": "暂未开放",
        "create_order_url": "",
    }


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    LOGGER.exception("service period api unexpected error")
    raise HTTPException(status_code=500, detail={"error_code": "service_period_internal_error", "message": "internal service period error"}) from exc


def _payload(data: dict) -> dict:
    return {
        **data,
        "route_owner": "ai_crm_next",
        "source_status": "next_service_period",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


def _admin_context(request: Request, *, page_title: str, page_summary: str, page_mode: str, product: dict | None = None) -> dict:
    context = shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint="api.admin_service_period_products_page",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "周期商品管理", "href": request.url_for("api.admin_service_period_products_page")},
    ]
    if page_mode != "list":
        context["breadcrumbs"].append({"label": page_title})
    context.update(
        {
            "page_mode": page_mode,
            "service_product_id": str((product or {}).get("id") or ""),
            "initial_product": jsonable_encoder(product or {}),
            "initial_product_json": json.dumps(jsonable_encoder(product or {}), ensure_ascii=False),
            "page_error": "",
        }
    )
    return context


@router.get("/admin/service-period-products", response_class=HTMLResponse, name="api.admin_service_period_products_page")
def admin_service_period_products_page(request: Request):
    try:
        payload = ListServicePeriodProductsQuery()(limit=100, offset=0)
    except Exception as exc:
        payload = {"ok": False, "items": [], "total": 0, "page_error": str(exc)}
    context = _admin_context(
        request,
        page_title="周期商品管理",
        page_summary="创建、编辑和上下架周期商品。",
        page_mode="list",
    )
    context.update(
        {
            "products": payload.get("items") or [],
            "product_total": int(payload.get("total") or 0),
            "page_error": str(payload.get("page_error") or ""),
        }
    )
    return templates.TemplateResponse(request, "service_period_products.html", context, status_code=200 if payload.get("ok", True) else 503)


@router.get("/admin/service-period-products/new", response_class=HTMLResponse, name="api.admin_service_period_product_new_page")
def admin_service_period_product_new_page(request: Request):
    return templates.TemplateResponse(
        request,
        "service_period_products.html",
        _admin_context(
            request,
            page_title="创建周期商品",
            page_summary="配置商品名称、价格、有效期和绑定会员设置。",
            page_mode="new",
        ),
    )


@router.get("/admin/service-period-products/{service_product_id}/edit", response_class=HTMLResponse, name="api.admin_service_period_product_edit_page")
def admin_service_period_product_edit_page(request: Request, service_product_id: str):
    try:
        product = GetServicePeriodProductQuery()(service_product_id)["product"]
        status_code = 200
    except Exception as exc:
        product = {}
        status_code = 404
        page_error = str(exc)
    else:
        page_error = ""
    context = _admin_context(
        request,
        page_title=f"编辑周期商品 {product.get('product_code')}" if product.get("product_code") else "编辑周期商品",
        page_summary="维护周期商品名称、价格、有效期和上架状态。",
        page_mode="edit",
        product=product,
    )
    context["page_error"] = page_error
    return templates.TemplateResponse(request, "service_period_products.html", context, status_code=status_code)


@router.get("/admin/service-period-products/{service_product_id}/data", response_class=HTMLResponse, name="api.admin_service_period_product_data_page")
def admin_service_period_product_data_page(request: Request, service_product_id: str):
    try:
        product = GetServicePeriodProductQuery()(service_product_id)["product"]
        stats = GetServicePeriodProductStatsQuery()(service_product_id)
        members = ListServicePeriodMembersQuery()(service_product_id, limit=100, offset=0)
        status_code = 200
        page_error = ""
    except Exception as exc:
        product = {}
        stats = {}
        members = {"items": []}
        status_code = 404
        page_error = str(exc)
    context = _admin_context(
        request,
        page_title=f"{product.get('title') or product.get('name') or '周期商品'}数据",
        page_summary="查看有效用户、到期用户和续费订单。",
        page_mode="data",
        product=product,
    )
    context.update({"stats": stats, "members": members.get("items") or [], "page_error": page_error})
    return templates.TemplateResponse(request, "service_period_products.html", context, status_code=status_code)


@router.get("/api/admin/service-period-products")
def list_service_period_products(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict:
    try:
        return _payload(ListServicePeriodProductsQuery()(limit=limit, offset=offset))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/service-period-products")
def create_service_period_product(payload: ServicePeriodProductCreateRequest) -> JSONResponse:
    try:
        result = _payload(CreateServicePeriodProductCommand()(payload))
    except Exception as exc:
        _raise_http(exc)
    return JSONResponse(jsonable_encoder(result), status_code=201)


@router.get("/api/admin/service-period-products/membership-configs")
def list_service_period_membership_configs() -> dict:
    return _payload({"ok": True, "items": []})


@router.get("/api/admin/service-period-products/{service_product_id}")
def get_service_period_product(service_product_id: str) -> dict:
    try:
        return _payload(GetServicePeriodProductQuery()(service_product_id))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/service-period-products/{service_product_id}")
def update_service_period_product(service_product_id: str, payload: ServicePeriodProductUpdateRequest) -> dict:
    try:
        return _payload(UpdateServicePeriodProductCommand()(service_product_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/service-period-products/{service_product_id}/copy")
def copy_service_period_product(service_product_id: str) -> JSONResponse:
    try:
        result = _payload(CopyServicePeriodProductCommand()(service_product_id))
    except Exception as exc:
        _raise_http(exc)
    return JSONResponse(jsonable_encoder(result), status_code=201)


@router.post("/api/admin/service-period-products/{service_product_id}/enable")
def enable_service_period_product(service_product_id: str) -> dict:
    try:
        return _payload(SetServicePeriodProductEnabledCommand()(service_product_id, enabled=True))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/service-period-products/{service_product_id}/disable")
def disable_service_period_product(service_product_id: str) -> dict:
    try:
        return _payload(SetServicePeriodProductEnabledCommand()(service_product_id, enabled=False))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/service-period-products/{service_product_id}")
def delete_service_period_product(service_product_id: str) -> dict:
    try:
        return _payload(DeleteServicePeriodProductCommand()(service_product_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/service-period-products/{service_product_id}/share")
def share_service_period_product(service_product_id: str, request: Request) -> dict:
    try:
        product = GetServicePeriodProductQuery()(service_product_id)["product"]
    except Exception as exc:
        _raise_http(exc)
    url = str(request.base_url).rstrip("/") + f"/s/{quote(str(product.get('link_slug') or ''))}"
    return _payload(
        {
            "ok": True,
            "share": {
                "service_product_id": str(product.get("id") or ""),
                "trade_product_id": str(product.get("trade_product_id") or ""),
                "product_code": str(product.get("product_code") or ""),
                "product_name": str(product.get("title") or product.get("name") or ""),
                "url": url,
                "qr_data_url": svg_qr_data_url(url),
            },
        }
    )


@router.get("/api/admin/service-period-products/{service_product_id}/stats")
def service_period_product_stats(service_product_id: str) -> dict:
    try:
        return _payload(GetServicePeriodProductStatsQuery()(service_product_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/service-period-products/{service_product_id}/members")
def service_period_product_members(
    service_product_id: str,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    try:
        return _payload(ListServicePeriodMembersQuery()(service_product_id, status=status, limit=limit, offset=offset))
    except Exception as exc:
        _raise_http(exc)


@router.get("/s/{link_slug}", response_class=HTMLResponse, name="api.public_service_period_product_page")
def public_service_period_product_page(request: Request, link_slug: str):
    try:
        product = GetPublicServicePeriodProductQuery()(link_slug)["product"]
    except NotFoundError:
        try:
            product = GetServicePeriodProductBySlugQuery()(link_slug)["product"]
        except NotFoundError:
            from aicrm_next.questionnaire.api import public_questionnaire_h5_page

            try:
                return public_questionnaire_h5_page(request, link_slug)
            except HTTPException:
                raise
            except Exception:
                return HTMLResponse(
                    "<!doctype html><meta charset='utf-8'><main data-route-owner='ai_crm_next'>周期商品不存在</main>",
                    status_code=404,
                    headers=route_headers(),
                )
        state = _inactive_public_state(product)
        html = render_service_period_public_page(product, state)
        return templates.TemplateResponse(request, "service_period_public.html", {"request": request, "html": html}, headers=route_headers())
    except Exception as exc:
        _raise_http(exc)
    try:
        identity = h5_wechat_pay.h5_payment_identity_from_request(request)
        state = GetServicePeriodPublicStateQuery()(link_slug, unionid=str(identity.get("unionid") or ""))
    except NotFoundError:
        state = _inactive_public_state(product)
    except Exception as exc:
        _raise_http(exc)
    html = render_service_period_public_page(product, state)
    return templates.TemplateResponse(request, "service_period_public.html", {"request": request, "html": html}, headers=route_headers())


@router.get("/api/h5/service-period-products/{link_slug}")
def public_service_period_product_state(request: Request, link_slug: str) -> dict:
    try:
        identity = h5_wechat_pay.h5_payment_identity_from_request(request)
        return _payload(GetServicePeriodPublicStateQuery()(link_slug, unionid=str(identity.get("unionid") or "")))
    except Exception as exc:
        if isinstance(exc, NotFoundError):
            return JSONResponse(product_not_found_payload(link_slug), status_code=404, headers=route_headers())
        _raise_http(exc)


@router.post("/api/h5/service-period-products/{link_slug}/wechat-pay/jsapi/orders")
def create_service_period_jsapi_order(request: Request, link_slug: str):
    try:
        body = read_request_json(request)
        product = GetPublicServicePeriodProductQuery()(link_slug)["product"]
        trade_product = dict(product.get("trade_product") or {})
        payload = body if isinstance(body, dict) else {}
        payload["product_code"] = trade_product.get("product_code") or product.get("product_code")
        return h5_wechat_pay.create_jsapi_order_response(
            request,
            payload,
            product_override=trade_product,
            checkout_return_path=f"/s/{product.get('link_slug')}",
            allow_paid_reuse=False,
            order_source="service_period_checkout",
            request_meta_extra={
                "service_period_product": {
                    "service_product_id": str(product.get("id") or ""),
                    "trade_product_id": str(product.get("trade_product_id") or ""),
                    "duration_days": int(product.get("duration_days") or 0),
                }
            },
        )
    except Exception as exc:
        if isinstance(exc, NotFoundError):
            return JSONResponse(product_not_found_payload(link_slug), status_code=404, headers=route_headers())
        _raise_http(exc)
