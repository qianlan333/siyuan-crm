from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import shell_context
from aicrm_next.shared.errors import ContractError, NotFoundError

from .admin_transactions import (
    default_filters,
    create_wechat_refund_request,
    export_orders_csv,
    list_wechat_admin_orders,
    list_wechat_product_options,
)
from .admin_transaction_detail import (
    CommerceAdminTransactionDetailReadModel,
    CommerceAdminTransactionListReadModel,
    PaymentProviderStatusMapper,
    provider_config,
)
from .external_push_admin import (
    ExternalPushAdminError,
    list_order_external_push_state,
    retry_order_delivery,
    send_product_external_push_test,
)
from .application import (
    CheckoutCommand,
    DeleteProductCommand,
    GetOrderQuery,
    GetProductQuery,
    GetPublicProductQuery,
    ListProductsQuery,
    NotifyPaymentCommand,
    PaymentReturnCommand,
    SetProductEnabledCommand,
    UpsertProductCommand,
)
from .dto import CheckoutRequest, PaymentNotifyRequest, ProductUpsertRequest
from .external_orders import router as external_orders_router
from .repo import build_commerce_repository

router = APIRouter()
router.include_router(external_orders_router)
_COMMERCE_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FRONTEND_COMPAT_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=[_COMMERCE_TEMPLATES_DIR, _FRONTEND_COMPAT_TEMPLATES_DIR])
_EXTERNAL_PUSH_CALL_EXECUTED = bool(1)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _checkout_order_headers(*, order_create_executed: str = "false") -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "false",
        "X-AICRM-Payment-Request-Executed": "false",
        "X-AICRM-Order-Create-Executed": order_create_executed,
    }


def _checkout_order_side_effects(*, order_create_executed: str | bool = False) -> dict:
    return {
        "fallback_used": False,
        "real_external_call_executed": False,
        "payment_request_executed": False,
        "real_wechat_pay_executed": False,
        "real_alipay_executed": False,
        "order_create_executed": order_create_executed,
    }


def _checkout_order_options_payload(route: str, methods: list[str], *, adapter_mode: str = "fake/real_blocked") -> dict:
    return {
        "ok": True,
        "route": route,
        "methods": methods,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "adapter_mode": adapter_mode,
        "side_effect_safety": _checkout_order_side_effects(),
    }


def _checkout_order_error_payload(
    *,
    error_code: str,
    message: str,
    method: str,
    path: str,
    source_status: str,
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error_code": error_code,
            "message": message,
            "method": method.upper(),
            "path": path,
            "source_status": source_status,
            "route_owner": "ai_crm_next",
            **_checkout_order_side_effects(),
        },
        status_code=status_code,
        headers=_checkout_order_headers(),
    )


def _provider_payment_headers(*, notify_executed: str = "false", return_executed: str = "false") -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "false",
        "X-AICRM-Real-Payment-Notify-Executed": "false",
        "X-AICRM-Provider-Signature-Verified": "false",
        "X-AICRM-Payment-Notify-Executed": notify_executed,
        "X-AICRM-Payment-Return-Executed": return_executed,
    }


def _provider_payment_side_effects(*, notify_executed: str | bool = False, return_executed: str | bool = False) -> dict:
    return {
        "fallback_used": False,
        "real_external_call_executed": False,
        "real_payment_notify_executed": False,
        "real_wechat_pay_executed": False,
        "real_alipay_executed": False,
        "provider_signature_verified": False,
        "payment_notify_executed": notify_executed,
        "payment_return_executed": return_executed,
    }


def _provider_payment_options_payload(route: str, methods: list[str], *, source_status: str) -> dict:
    return {
        "ok": True,
        "route": route,
        "methods": methods,
        "source_status": source_status,
        "route_owner": "ai_crm_next",
        "adapter_mode": "fake/real_blocked",
        **_provider_payment_side_effects(),
    }


def _provider_payment_error_payload(
    *,
    error_code: str,
    message: str,
    method: str,
    path: str,
    source_status: str,
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error_code": error_code,
            "message": message,
            "method": method.upper(),
            "path": path,
            "source_status": source_status,
            "route_owner": "ai_crm_next",
            **_provider_payment_side_effects(),
        },
        status_code=status_code,
        headers=_provider_payment_headers(),
    )


def _bool_header(value: bool) -> str:
    return "true" if value else "false"


def _payment_final_headers(*, real_external_call_executed: bool = False, real_refund_executed: bool = False) -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": _bool_header(real_external_call_executed),
        "X-AICRM-Payment-Request-Executed": "false",
        "X-AICRM-Real-WeChat-Pay-Executed": "false",
        "X-AICRM-Real-Alipay-Executed": "false",
        "X-AICRM-Provider-Signature-Verified": "false",
        "X-AICRM-Real-Refund-Executed": _bool_header(real_refund_executed),
    }


def _payment_final_side_effects(
    *,
    source_status: str = "next_payment_admin",
    real_external_call_executed: bool = False,
    real_refund_executed: bool = False,
) -> dict:
    return {
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": real_external_call_executed,
        "payment_request_executed": False,
        "real_wechat_pay_executed": False,
        "real_alipay_executed": False,
        "provider_signature_verified": False,
        "real_refund_executed": real_refund_executed,
        "source_status": source_status,
    }


def _payment_final_payload(
    payload: dict,
    *,
    source_status: str = "next_payment_admin",
    real_external_call_executed: bool = False,
    real_refund_executed: bool = False,
) -> dict:
    result = dict(payload)
    result.update(
        _payment_final_side_effects(
            source_status=source_status,
            real_external_call_executed=real_external_call_executed,
            real_refund_executed=real_refund_executed,
        )
    )
    return result


def _payment_final_blocked_payload(
    *,
    error_code: str,
    message: str,
    method: str,
    path: str,
    source_status: str,
    status_code: int = 410,
    replacement: str = "",
) -> JSONResponse:
    body = {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "method": method.upper(),
        "path": path,
        "replacement": replacement,
        "adapter_mode": "real_blocked",
        **_payment_final_side_effects(source_status=source_status),
    }
    return JSONResponse(body, status_code=status_code, headers=_payment_final_headers())


def _payment_final_options_payload(route: str, methods: list[str], *, source_status: str) -> dict:
    return {
        "ok": True,
        "route": route,
        "methods": methods,
        "adapter_mode": "real_blocked",
        **_payment_final_side_effects(source_status=source_status),
    }


def _product_admin_context(
    request: Request,
    *,
    page_title: str,
    page_summary: str,
    mode: str,
    product: dict | None = None,
) -> dict:
    context = shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint="api.admin_wechat_pay_products_page",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "商品管理", "href": request.url_for("api.admin_wechat_pay_products_page")},
    ]
    if mode != "list":
        context["breadcrumbs"].append({"label": "创建商品" if mode == "new" else "编辑商品"})
    context.update(
        {
            "product_page_mode": mode,
            "initial_product": jsonable_encoder(product or {}),
            "initial_product_json": json.dumps(jsonable_encoder(product or {}), ensure_ascii=False),
        }
    )
    return context


def _share_payload(request: Request, product: dict) -> dict:
    product_code = str(product.get("product_code") or "")
    url = str(request.base_url).rstrip("/") + f"/p/{quote(product_code)}"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'>"
        "<rect width='256' height='256' fill='#ffffff'/>"
        "<rect x='24' y='24' width='208' height='208' fill='none' stroke='#111827' stroke-width='12'/>"
        "<text x='128' y='126' text-anchor='middle' font-size='20' font-family='monospace' fill='#111827'>"
        "PRODUCT"
        "</text>"
        "<text x='128' y='158' text-anchor='middle' font-size='14' font-family='monospace' fill='#475569'>"
        f"{product_code[:18]}"
        "</text>"
        "</svg>"
    )
    return {
        "product_id": str(product.get("id") or ""),
        "product_code": product_code,
        "product_name": str(product.get("title") or ""),
        "url": url,
        "qr_data_url": "data:image/svg+xml;utf8," + quote(svg),
    }


def _transaction_admin_context(request: Request, *, provider: str, detail_order: dict | None = None, detail_error: str = "") -> dict:
    config = provider_config(provider)
    page_title = f"{config.provider_label}交易管理" if not detail_order else f"{config.provider_label}订单详情"
    page_summary = (
        f"按订单创建时间检索{config.provider_label}订单，查看商户单号、平台单号、商品、客户、金额、状态与回调摘要。"
        if not detail_order
        else f"核对{config.provider_label}订单状态、客户身份、回调摘要与事件时间线。"
    )
    active_endpoint = "api.admin_alipay_transactions_page" if provider == "alipay" else "api.admin_wechat_pay_transactions_page"
    context = shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint=active_endpoint,
    )
    list_href = str(request.url_for(active_endpoint))
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": f"{config.provider_label}交易管理", "href": list_href if detail_order or detail_error else ""},
    ]
    if detail_order or detail_error:
        context["breadcrumbs"].append({"label": "订单详情"})
    context.update(
        {
            "payment_provider": provider,
            "payment_provider_label": config.provider_label,
            "provider_platform_no_label": config.platform_no_label,
            "list_api_url": config.api_path,
            "export_api_url": "/api/admin/wechat-pay/order-exports" if provider == "wechat" else "",
            "default_filters": default_filters(),
            "status_options": [{"value": key, "label": label} for key, label in PaymentProviderStatusMapper.LABELS.items()],
            "product_options": list_wechat_product_options() if provider == "wechat" else [],
            "detail_order": detail_order,
            "detail_error": detail_error,
        }
    )
    return context


@router.get("/admin/wechat-pay/products", response_class=HTMLResponse, name="api.admin_wechat_pay_products_page")
def admin_wechat_pay_products_page(request: Request):
    try:
        payload = ListProductsQuery()(limit=100, offset=0)
    except Exception as exc:
        payload = {"ok": False, "items": [], "total": 0, "page_error": str(exc)}
    context = _product_admin_context(
        request,
        page_title="微信支付商品管理",
        page_summary="创建、编辑和上下架微信支付商品。",
        mode="list",
    )
    products = payload.get("items") or []
    context.update(
        {
            "initial_products": jsonable_encoder(products),
            "initial_products_json": json.dumps(jsonable_encoder(products), ensure_ascii=False),
            "product_total": int(payload.get("total") or len(products)),
            "page_error": str(payload.get("page_error") or ""),
        }
    )
    return templates.TemplateResponse(request, "wechat_products.html", context, status_code=200 if payload.get("ok", True) else 503)


@router.get("/admin/wechat-pay/products/new", response_class=HTMLResponse, name="api.admin_wechat_pay_product_new_page")
def admin_wechat_pay_product_new_page(request: Request):
    context = _product_admin_context(
        request,
        page_title="创建微信支付商品",
        page_summary="配置商品编码、名称、价格与上架状态。",
        mode="new",
    )
    return templates.TemplateResponse(request, "wechat_products.html", context)


@router.get("/admin/wechat-pay/products/{product_id}/edit", response_class=HTMLResponse, name="api.admin_wechat_pay_product_edit_page")
def admin_wechat_pay_product_edit_page(request: Request, product_id: str):
    try:
        product = GetProductQuery()(product_id)["product"]
    except Exception as exc:
        context = _product_admin_context(
            request,
            page_title="商品不存在",
            page_summary="当前没有找到这个商品。",
            mode="edit",
        )
        context["page_error"] = str(exc)
        return templates.TemplateResponse(request, "wechat_products.html", context, status_code=404)
    context = _product_admin_context(
        request,
        page_title=f"编辑商品 {product.get('product_code')}",
        page_summary="维护商品名称、价格与上架状态。",
        mode="edit",
        product=product,
    )
    return templates.TemplateResponse(request, "wechat_products.html", context)


@router.get("/admin/wechat-pay/transactions", response_class=HTMLResponse, name="api.admin_wechat_pay_transactions_page")
def admin_wechat_transactions_page(request: Request):
    return templates.TemplateResponse(
        request,
        "wechat_transactions.html",
        _transaction_admin_context(request, provider="wechat"),
    )


@router.get("/admin/wechat-pay/transactions/{order_id}", response_class=HTMLResponse, name="api.admin_wechat_pay_transaction_detail_page")
def admin_wechat_transaction_detail_page(request: Request, order_id: str) -> Response:
    try:
        order = CommerceAdminTransactionDetailReadModel("wechat").execute(order_id)["transaction"]
        status_code = 200
        context = _transaction_admin_context(request, provider="wechat", detail_order=order)
    except NotFoundError:
        status_code = 404
        context = _transaction_admin_context(request, provider="wechat", detail_error="订单不存在")
    return templates.TemplateResponse(
        request,
        "wechat_transactions.html",
        context,
        status_code=status_code,
    )


@router.get("/admin/alipay/transactions", response_class=HTMLResponse, name="api.admin_alipay_transactions_page")
def admin_alipay_transactions_page(request: Request):
    return templates.TemplateResponse(
        request,
        "wechat_transactions.html",
        _transaction_admin_context(request, provider="alipay"),
    )


@router.get("/api/admin/wechat-pay/orders")
def list_wechat_admin_order_page(
    mobile: str | None = None,
    identity: str | None = None,
    transaction_id: str | None = None,
    product_code: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    return _payment_final_payload(
        list_wechat_admin_orders(
            {
                "mobile": mobile,
                "identity": identity,
                "transaction_id": transaction_id,
                "product_code": product_code,
                "created_from": created_from,
                "created_to": created_to,
                "status": status,
            },
            limit=limit,
            offset=offset,
        )
    )


@router.post("/api/admin/wechat-pay/order-exports")
async def export_wechat_admin_orders(request: Request) -> Response:
    payload = await request.json()
    csv_text = export_orders_csv(payload.get("filters") if isinstance(payload, dict) else {})
    return Response(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            **_payment_final_headers(),
            "Content-Disposition": 'attachment; filename="wechat-pay-orders.csv"',
        },
    )


@router.get("/api/admin/wechat-pay/order-exports/{job_id}")
@router.get("/api/admin/wechat-pay/order-exports/{job_id}/download")
def deprecated_wechat_admin_order_export_job(job_id: str, request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="admin_wechat_pay_export_job_removed",
        message="legacy export job download path is removed; use POST /api/admin/wechat-pay/order-exports for immediate CSV export",
        method=request.method,
        path=f"/api/admin/wechat-pay/order-exports/{job_id}" + ("/download" if request.url.path.endswith("/download") else ""),
        source_status="next_payment_admin_deprecated",
        replacement="/api/admin/wechat-pay/order-exports",
    )


@router.get("/api/admin/wechat-pay/orders/{order_id}/external-push-deliveries")
def list_wechat_order_external_push_deliveries(order_id: str) -> JSONResponse:
    try:
        payload = list_order_external_push_state(int(order_id))
    except ExternalPushAdminError as exc:
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=404, headers=_payment_final_headers())
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=400, headers=_payment_final_headers())
    return JSONResponse(jsonable_encoder(_payment_final_payload(payload)), headers=_payment_final_headers())


@router.post("/api/admin/wechat-pay/orders/{order_id}/external-push-deliveries/{delivery_id}/retry")
def retry_wechat_order_external_push_delivery(order_id: str, delivery_id: str) -> JSONResponse:
    try:
        result = retry_order_delivery(int(order_id), delivery_id)
    except ExternalPushAdminError as exc:
        status_code = 404 if "不存在" in str(exc) else 400
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=status_code, headers=_payment_final_headers())
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=400, headers=_payment_final_headers())
    return JSONResponse(
        jsonable_encoder(_payment_final_payload({"ok": True, "result": result}, real_external_call_executed=_EXTERNAL_PUSH_CALL_EXECUTED)),
        headers=_payment_final_headers(real_external_call_executed=_EXTERNAL_PUSH_CALL_EXECUTED),
    )


@router.post("/api/admin/wechat-pay/orders/{order_id}/refunds")
async def request_wechat_admin_refund(order_id: str, request: Request) -> JSONResponse:
    payload = await request.json()
    try:
        result = create_wechat_refund_request(order_id, payload if isinstance(payload, dict) else {})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=400, headers=_payment_final_headers())
    provider_refund_executed = bool((result.get("refund") or {}).get("provider_refund_executed"))
    return JSONResponse(
        _payment_final_payload(
            result,
            real_external_call_executed=provider_refund_executed,
            real_refund_executed=provider_refund_executed,
        ),
        headers=_payment_final_headers(
            real_external_call_executed=provider_refund_executed,
            real_refund_executed=provider_refund_executed,
        ),
    )


@router.get("/api/admin/wechat-pay/products")
def list_products(limit: int = 50, offset: int = 0) -> dict:
    try:
        return _payment_final_payload(ListProductsQuery()(limit=limit, offset=offset))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/wechat-pay/products/lead-channels")
def list_product_lead_channels() -> dict:
    try:
        return _payment_final_payload({"ok": True, "items": build_commerce_repository().list_lead_channels()})
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/wechat-pay/products/lead-plans")
def deprecated_product_lead_plans(request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="admin_wechat_pay_lead_plans_removed",
        message="legacy lead-plans path is removed; use lead-channels for commerce product binding",
        method=request.method,
        path="/api/admin/wechat-pay/products/lead-plans",
        source_status="next_payment_admin_deprecated",
        replacement="/api/admin/wechat-pay/products/lead-channels",
    )


@router.get("/api/admin/wechat-pay/products/{product_id}")
def get_product(product_id: str) -> dict:
    try:
        return _payment_final_payload(GetProductQuery()(product_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/wechat-pay/products/{product_id}/share")
def share_product(product_id: str, request: Request) -> dict:
    try:
        product = GetProductQuery()(product_id)["product"]
    except Exception as exc:
        _raise_http(exc)
    return _payment_final_payload({"ok": True, "share": _share_payload(request, product)})


@router.post("/api/admin/wechat-pay/products/{product_id}/copy")
def copy_product(product_id: str) -> JSONResponse:
    try:
        product = build_commerce_repository().copy_product(product_id)
    except Exception as exc:
        _raise_http(exc)
    return JSONResponse(_payment_final_payload({"ok": True, "product": product}), status_code=201, headers=_payment_final_headers())


@router.get("/api/admin/wechat-pay/products/{product_id}/external-push")
def get_product_external_push(product_id: str) -> dict:
    try:
        return _payment_final_payload({"ok": True, "config": build_commerce_repository().get_external_push_config(product_id)})
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/wechat-pay/products/{product_id}/external-push")
async def save_product_external_push(product_id: str, request: Request) -> dict:
    try:
        payload = await request.json()
        config = build_commerce_repository().save_external_push_config(product_id, payload if isinstance(payload, dict) else {})
    except Exception as exc:
        _raise_http(exc)
    return _payment_final_payload({"ok": True, "config": config})


@router.post("/api/admin/wechat-pay/products/{product_id}/external-push/test")
def test_product_external_push(product_id: str) -> JSONResponse:
    try:
        result = send_product_external_push_test(int(product_id))
    except ExternalPushAdminError as exc:
        status_code = 404 if str(exc) == "商品不存在" else 400
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=status_code, headers=_payment_final_headers())
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc), **_payment_final_side_effects()}, status_code=400, headers=_payment_final_headers())
    return JSONResponse(
        jsonable_encoder(_payment_final_payload({"ok": True, "result": result}, real_external_call_executed=_EXTERNAL_PUSH_CALL_EXECUTED)),
        headers=_payment_final_headers(real_external_call_executed=_EXTERNAL_PUSH_CALL_EXECUTED),
    )


@router.post("/api/admin/wechat-pay/products")
def create_product(payload: ProductUpsertRequest) -> dict:
    try:
        return _payment_final_payload(UpsertProductCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/wechat-pay/products/{product_id}")
def update_product(product_id: str, payload: ProductUpsertRequest) -> dict:
    try:
        return _payment_final_payload(UpsertProductCommand()(payload, product_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/wechat-pay/products/{product_id}/enable")
def enable_product(product_id: str) -> dict:
    try:
        return _payment_final_payload(SetProductEnabledCommand()(product_id, enabled=True))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/wechat-pay/products/{product_id}/disable")
def disable_product(product_id: str) -> dict:
    try:
        return _payment_final_payload(SetProductEnabledCommand()(product_id, enabled=False))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/wechat-pay/products/{product_id}")
def delete_product(product_id: str) -> dict:
    try:
        return _payment_final_payload(DeleteProductCommand()(product_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/products/{page_slug}")
def public_product(page_slug: str) -> dict:
    try:
        return GetPublicProductQuery()(page_slug)
    except Exception as exc:
        _raise_http(exc)


@router.get("/p/{page_slug}", response_class=HTMLResponse)
def product_page(request: Request, page_slug: str) -> str:
    try:
        payload = GetPublicProductQuery()(page_slug)
    except Exception as exc:
        _raise_http(exc)
    product = payload["product"]
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        + product["title"]
        + "</title></head><body><main><h1>"
        + product["title"]
        + "</h1><p>"
        + product.get("description", "")
        + "</p><button>"
        + product.get("buy_button_text", "立即购买")
        + "</button></main></body></html>"
    )


@router.post("/api/checkout/wechat")
def checkout_wechat(payload: CheckoutRequest) -> JSONResponse:
    try:
        result = CheckoutCommand("wechat")(payload)
        return JSONResponse(result, headers=_checkout_order_headers(order_create_executed="local_only"))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/checkout/alipay")
def checkout_alipay(payload: CheckoutRequest) -> JSONResponse:
    try:
        result = CheckoutCommand("alipay")(payload)
        return JSONResponse(result, headers=_checkout_order_headers(order_create_executed="local_only"))
    except Exception as exc:
        _raise_http(exc)


@router.options("/api/checkout/wechat")
def checkout_wechat_options() -> JSONResponse:
    payload = _checkout_order_options_payload("/api/checkout/wechat", ["POST", "OPTIONS"])
    return JSONResponse(payload, headers=_checkout_order_headers())


@router.options("/api/checkout/alipay")
def checkout_alipay_options() -> JSONResponse:
    payload = _checkout_order_options_payload("/api/checkout/alipay", ["POST", "OPTIONS"])
    return JSONResponse(payload, headers=_checkout_order_headers())


@router.api_route("/api/checkout/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def checkout_unknown(path: str, request: Request) -> JSONResponse:
    return _checkout_order_error_payload(
        error_code="checkout_path_removed",
        message="unknown checkout API path is closed in Next; legacy fallback is removed",
        method=request.method,
        path=f"/api/checkout/{path}",
        source_status="next_checkout_not_found",
        status_code=410,
    )


@router.get("/api/orders/{order_no}")
@router.get("/api/orders/{order_no}/status")
def get_order(order_no: str) -> JSONResponse:
    try:
        return JSONResponse(GetOrderQuery()(order_no), headers=_checkout_order_headers())
    except NotFoundError as exc:
        return _checkout_order_error_payload(
            error_code="order_not_found",
            message=str(exc),
            method="GET",
            path=f"/api/orders/{order_no}",
            source_status="next_order_read_not_found",
            status_code=404,
        )
    except Exception as exc:
        _raise_http(exc)


@router.options("/api/orders/{order_no}")
def get_order_options(order_no: str) -> JSONResponse:
    payload = _checkout_order_options_payload(f"/api/orders/{order_no}", ["GET", "OPTIONS"], adapter_mode="none")
    payload["source_status"] = "next_order_read"
    return JSONResponse(payload, headers=_checkout_order_headers())


@router.options("/api/orders/{order_no}/status")
def get_order_status_options(order_no: str) -> JSONResponse:
    payload = _checkout_order_options_payload(f"/api/orders/{order_no}/status", ["GET", "OPTIONS"], adapter_mode="none")
    payload["source_status"] = "next_order_read"
    return JSONResponse(payload, headers=_checkout_order_headers())


@router.api_route("/api/orders/{order_no}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def order_unknown_child(order_no: str, path: str, request: Request) -> JSONResponse:
    return _checkout_order_error_payload(
        error_code="order_child_path_removed",
        message="unknown order API child path is closed in Next; legacy fallback is removed",
        method=request.method,
        path=f"/api/orders/{order_no}/{path}",
        source_status="next_order_child_not_found",
        status_code=410,
    )


@router.post("/api/wechat-pay/notify")
def wechat_notify(payload: PaymentNotifyRequest) -> JSONResponse:
    try:
        result = NotifyPaymentCommand("wechat")(payload)
        return JSONResponse(result, headers=_provider_payment_headers(notify_executed="local_only"))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/alipay/notify")
def alipay_notify(payload: PaymentNotifyRequest) -> JSONResponse:
    try:
        result = NotifyPaymentCommand("alipay")(payload)
        return JSONResponse(result, headers=_provider_payment_headers(notify_executed="local_only"))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/alipay/return")
def alipay_return(order_no: str = "", status: str = "paid") -> JSONResponse:
    try:
        result = PaymentReturnCommand()(order_no=order_no, status=status)
        return JSONResponse(result, headers=_provider_payment_headers(return_executed="fake"))
    except Exception as exc:
        _raise_http(exc)


@router.options("/api/wechat-pay/notify")
def wechat_notify_options() -> JSONResponse:
    payload = _provider_payment_options_payload("/api/wechat-pay/notify", ["POST", "OPTIONS"], source_status="next_payment_notify")
    return JSONResponse(payload, headers=_provider_payment_headers())


@router.options("/api/alipay/notify")
def alipay_notify_options() -> JSONResponse:
    payload = _provider_payment_options_payload("/api/alipay/notify", ["POST", "OPTIONS"], source_status="next_payment_notify")
    return JSONResponse(payload, headers=_provider_payment_headers())


@router.options("/api/alipay/return")
def alipay_return_options() -> JSONResponse:
    payload = _provider_payment_options_payload("/api/alipay/return", ["GET", "OPTIONS"], source_status="next_payment_return")
    return JSONResponse(payload, headers=_provider_payment_headers())


@router.api_route("/api/wechat-pay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def wechat_pay_unknown(path: str, request: Request) -> JSONResponse:
    return _provider_payment_error_payload(
        error_code="provider_payment_path_removed",
        message="unknown WeChat Pay provider path is closed in Next; legacy fallback is removed",
        method=request.method,
        path=f"/api/wechat-pay/{path}",
        source_status="next_payment_provider_not_found",
        status_code=410,
    )


@router.api_route("/api/alipay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def alipay_unknown(path: str, request: Request) -> JSONResponse:
    return _provider_payment_error_payload(
        error_code="provider_payment_path_removed",
        message="unknown Alipay provider path is closed in Next; legacy fallback is removed",
        method=request.method,
        path=f"/api/alipay/{path}",
        source_status="next_payment_provider_not_found",
        status_code=410,
    )


def _transaction_filters(
    payment_status: str | None = None,
    product_code: str | None = None,
    mobile: str | None = None,
    external_userid: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    return {
        "payment_status": payment_status,
        "product_code": product_code,
        "mobile": mobile,
        "external_userid": external_userid,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get("/api/admin/wechat-pay/transactions")
def list_wechat_transactions(
    payment_status: str | None = None,
    product_code: str | None = None,
    mobile: str | None = None,
    external_userid: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return _payment_final_payload(
        CommerceAdminTransactionListReadModel("wechat").execute(
            _transaction_filters(payment_status, product_code, mobile, external_userid, date_from, date_to),
            limit=limit,
            offset=offset,
        )
    )


@router.get("/api/admin/wechat-pay/transactions/{order_no}")
def get_wechat_transaction(order_no: str) -> dict:
    try:
        return _payment_final_payload(CommerceAdminTransactionDetailReadModel("wechat").execute(order_no))
    except Exception as exc:
        _raise_http(exc)


@router.options("/api/admin/wechat-pay/{path:path}")
def admin_wechat_pay_options(path: str) -> JSONResponse:
    payload = _payment_final_options_payload(
        f"/api/admin/wechat-pay/{path}",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        source_status="next_payment_admin",
    )
    return JSONResponse(payload, headers=_payment_final_headers())


@router.api_route("/api/admin/wechat-pay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
def admin_wechat_pay_unknown(path: str, request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="admin_wechat_pay_path_removed",
        message="unknown admin WeChat Pay path is closed in Next; legacy fallback is removed",
        method=request.method,
        path=f"/api/admin/wechat-pay/{path}",
        source_status="next_payment_admin_not_found",
    )


@router.get("/api/admin/alipay/transactions")
def list_alipay_transactions(
    payment_status: str | None = None,
    product_code: str | None = None,
    mobile: str | None = None,
    external_userid: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return _payment_final_payload(
        CommerceAdminTransactionListReadModel("alipay").execute(
            _transaction_filters(payment_status, product_code, mobile, external_userid, date_from, date_to),
            limit=limit,
            offset=offset,
        )
    )


@router.get("/api/admin/alipay/transactions/{order_no}")
def get_alipay_transaction(order_no: str) -> dict:
    try:
        return _payment_final_payload(CommerceAdminTransactionDetailReadModel("alipay").execute(order_no))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/alipay/orders")
@router.get("/api/admin/alipay/order-export.csv")
def deprecated_admin_alipay_paths(request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="admin_alipay_path_removed",
        message="legacy Alipay admin order/export path is removed; use Next transaction APIs",
        method=request.method,
        path=request.url.path,
        source_status="next_payment_admin_deprecated",
        replacement="/api/admin/alipay/transactions",
    )


@router.options("/api/admin/alipay/{path:path}")
def admin_alipay_options(path: str) -> JSONResponse:
    payload = _payment_final_options_payload(
        f"/api/admin/alipay/{path}",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        source_status="next_payment_admin",
    )
    return JSONResponse(payload, headers=_payment_final_headers())


@router.api_route("/api/admin/alipay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
def admin_alipay_unknown(path: str, request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="admin_alipay_path_removed",
        message="unknown admin Alipay path is closed in Next; legacy fallback is removed",
        method=request.method,
        path=f"/api/admin/alipay/{path}",
        source_status="next_payment_admin_not_found",
    )


@router.options("/api/h5/wechat-pay/{path:path}")
def h5_wechat_pay_options(path: str) -> JSONResponse:
    payload = _payment_final_options_payload(
        f"/api/h5/wechat-pay/{path}",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        source_status="next_h5_payment_blocked",
    )
    return JSONResponse(payload, headers=_payment_final_headers())


@router.api_route("/api/h5/wechat-pay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
def h5_wechat_pay_unknown(path: str, request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="h5_wechat_pay_path_removed",
        message="legacy H5 WeChat Pay path is closed in Next; use public checkout/order/provider APIs",
        method=request.method,
        path=f"/api/h5/wechat-pay/{path}",
        source_status="next_h5_payment_blocked",
        replacement="/api/checkout/wechat",
    )


@router.options("/api/h5/alipay/{path:path}")
def h5_alipay_options(path: str) -> JSONResponse:
    payload = _payment_final_options_payload(
        f"/api/h5/alipay/{path}",
        ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        source_status="next_h5_payment_blocked",
    )
    return JSONResponse(payload, headers=_payment_final_headers())


@router.api_route("/api/h5/alipay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
def h5_alipay_unknown(path: str, request: Request) -> JSONResponse:
    return _payment_final_blocked_payload(
        error_code="h5_alipay_path_removed",
        message="legacy H5 Alipay path is closed in Next; use public checkout/order/provider APIs",
        method=request.method,
        path=f"/api/h5/alipay/{path}",
        source_status="next_h5_payment_blocked",
        replacement="/api/checkout/alipay",
    )
