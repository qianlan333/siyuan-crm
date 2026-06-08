from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from flask import current_app, has_app_context

from aicrm_next.commerce.domain import completion_redirect_projection, safe_completion_redirect_url

from ...db import get_db
from ...infra.json_utils import safe_json_loads
from ...infra.signed_context import append_ctx_query
from ...infra.settings import get_setting
from . import product_repo
from .exceptions import WeChatPayOrderError, WeChatPayProductError


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _positive_int_from_payload(payload: dict[str, Any], existing: dict[str, Any], key: str) -> int | None:
    value = payload.get(key) if key in payload else existing.get(key)
    try:
        normalized = int(value or 0)
    except (TypeError, ValueError):
        normalized = 0
    return normalized or None


def _setting(key: str, default: str = "") -> str:
    stored = get_setting(key)
    if stored is not None:
        return _normalized_text(stored)
    return _normalized_text(current_app.config.get(key, default))


PRODUCT_STATUS_DRAFT = "draft"
PRODUCT_STATUS_ACTIVE = "active"
PRODUCT_STATUS_DISABLED = "disabled"
PRODUCT_STATUSES = {PRODUCT_STATUS_DRAFT, PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_DISABLED}
PRODUCT_SLICE_LIMIT = 10


def _product_catalog() -> dict[str, dict[str, Any]]:
    raw = _setting("WECHAT_PAY_PRODUCT_CATALOG_JSON")
    payload = safe_json_loads(raw, default={}) if raw else {}
    catalog: dict[str, dict[str, Any]] = {}
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("products"), list):
            items = payload.get("products") or []
        else:
            items = [
                {"product_code": key, **(value if isinstance(value, dict) else {})}
                for key, value in payload.items()
            ]
    else:
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = _normalized_text(item.get("product_code") or item.get("code") or item.get("id"))
        if not code:
            continue
        amount_total = item.get("amount_total", item.get("amount_fen", item.get("price_fen", 0)))
        try:
            amount = int(amount_total)
        except (TypeError, ValueError):
            amount = 0
        catalog[code] = {
            "product_code": code,
            "name": _normalized_text(item.get("name") or item.get("title") or item.get("description") or code),
            "description": _normalized_text(item.get("description") or item.get("name") or item.get("title") or code),
            "amount_total": amount,
            "currency": _normalized_text(item.get("currency")) or "CNY",
            "success_url": _normalized_text(item.get("success_url")),
            "enabled": str(item.get("enabled", "true")).lower() not in {"0", "false", "no", "off"},
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "require_mobile": str(item.get("require_mobile", item.get("require_phone", "false"))).lower()
            in {"1", "true", "yes", "y", "on"},
            "cta_text": _normalized_text(item.get("cta_text")) or "确认支付",
            "lead_program_id": None,
            "lead_channel_id": None,
            "lead_plan_configured": False,
            "completion_redirect_enabled": _normalized_bool(item.get("completion_redirect_enabled")),
            "completion_redirect_url": safe_completion_redirect_url(item.get("completion_redirect_url")),
        }
    return catalog


def _money_amount_total(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> int:
    raw_amount = payload.get("amount_total")
    if raw_amount is not None and _normalized_text(raw_amount) != "":
        try:
            return int(raw_amount)
        except (TypeError, ValueError):
            raise WeChatPayProductError("价格格式不合法")
    for key in ("price_yuan", "price", "amount_yuan"):
        raw_yuan = payload.get(key)
        if raw_yuan is None or _normalized_text(raw_yuan) == "":
            continue
        try:
            return int(round(float(raw_yuan) * 100))
        except (TypeError, ValueError):
            raise WeChatPayProductError("价格格式不合法")
    if existing:
        return int(existing.get("amount_total") or 0)
    raise WeChatPayProductError("价格不能为空")


def _normalize_product_status(value: Any, *, default: str = PRODUCT_STATUS_DRAFT) -> str:
    normalized = _normalized_text(value) or default
    if normalized == "paused":
        normalized = PRODUCT_STATUS_DISABLED
    if normalized not in PRODUCT_STATUSES:
        raise WeChatPayProductError("商品状态不合法")
    return normalized


def _enabled_for_status(status: str) -> bool:
    return _normalized_text(status) == PRODUCT_STATUS_ACTIVE


def _generate_product_code() -> str:
    return "prd_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(3)


def _image_data_url(slice_row: dict[str, Any]) -> str:
    source_url = _normalized_text(slice_row.get("source_url"))
    if source_url:
        return source_url
    data_base64 = _normalized_text(slice_row.get("data_base64"))
    if not data_base64:
        return ""
    mime_type = _normalized_text(slice_row.get("mime_type")) or "image/png"
    return f"data:{mime_type};base64,{data_base64}"


def _present_slice(slice_row: dict[str, Any], *, include_image_url: bool = True) -> dict[str, Any]:
    item = {
        "id": int(slice_row.get("id") or 0),
        "product_id": int(slice_row.get("product_id") or 0),
        "image_library_id": int(slice_row.get("image_library_id") or 0),
        "sort_order": int(slice_row.get("sort_order") or 0),
        "name": _normalized_text(slice_row.get("image_name"))
        or _normalized_text(slice_row.get("file_name"))
        or f"切片 {int(slice_row.get('sort_order') or 0)}",
        "file_name": _normalized_text(slice_row.get("file_name")),
        "mime_type": _normalized_text(slice_row.get("mime_type")) or "image/png",
        "file_size": int(slice_row.get("file_size") or 0),
        "enabled": bool(slice_row.get("enabled")),
    }
    if include_image_url:
        item["image_url"] = _image_data_url(slice_row)
    return item


def _lead_qr_from_channel(channel: dict[str, Any] | None) -> dict[str, Any]:
    channel = dict(channel or {})
    qr_url = _normalized_text(channel.get("qr_url"))
    if not qr_url:
        return {}
    return {
        "channel_id": int(channel.get("id") or 0),
        "channel_name": _normalized_text(channel.get("channel_name")),
        "qr_url": qr_url,
        "status": _normalized_text(channel.get("status")),
        "owner_staff_id": _normalized_text(channel.get("owner_staff_id")),
    }


def resolve_lead_channel(program_id: int | None, *, channel_id: int | None = None) -> dict[str, Any] | None:
    from ..automation_conversion import service as automation_service

    return automation_service.resolve_lead_channel_for_program(program_id, channel_id=channel_id)


def _lead_qr_for_product(product: dict[str, Any]) -> dict[str, Any]:
    from ..automation_conversion import service as automation_service

    channel_id = int(product.get("lead_channel_id") or 0)
    program_id = int(product.get("lead_program_id") or 0)
    if channel_id <= 0 and program_id <= 0:
        return {}
    channel = automation_service.resolve_lead_channel_for_program(
        program_id,
        channel_id=channel_id,
    )
    return _lead_qr_from_channel(channel)


def _normalize_completion_redirect_payload(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    enabled = (
        _normalized_bool(payload.get("completion_redirect_enabled"))
        if "completion_redirect_enabled" in payload
        else bool(existing.get("completion_redirect_enabled"))
    )
    raw_url = (
        _normalized_text(payload.get("completion_redirect_url"))
        if "completion_redirect_url" in payload
        else _normalized_text(existing.get("completion_redirect_url"))
    )
    safe_url = safe_completion_redirect_url(raw_url)
    if enabled and raw_url and not safe_url:
        raise WeChatPayProductError("完成后跳转 URL 必须是 https 链接或安全站内路径")
    return {
        "completion_redirect_enabled": enabled,
        "completion_redirect_url": safe_url,
    }


def get_completion_redirect_for_product_code(product_code: str) -> dict[str, Any]:
    if not has_app_context():
        return completion_redirect_projection(False, "")
    product = product_repo.get_product_by_code(_normalized_text(product_code))
    if not product:
        return completion_redirect_projection(False, "")
    return completion_redirect_projection(
        product.get("completion_redirect_enabled"),
        product.get("completion_redirect_url"),
    )


def get_lead_qr_for_product_code(product_code: str) -> dict[str, Any]:
    product = product_repo.get_product_by_code(_normalized_text(product_code))
    if not product:
        return {}
    return _lead_qr_for_product(product)


def _present_db_product(product: dict[str, Any]) -> dict[str, Any]:
    metadata = product.get("metadata_json") if isinstance(product.get("metadata_json"), dict) else {}
    lead_qr = _lead_qr_for_product(product)
    completion_redirect = completion_redirect_projection(
        product.get("completion_redirect_enabled"),
        product.get("completion_redirect_url"),
    )
    return {
        "id": int(product.get("id") or 0),
        "product_code": _normalized_text(product.get("product_code")),
        "name": _normalized_text(product.get("name")),
        "description": _normalized_text(product.get("name")),
        "amount_total": int(product.get("amount_total") or 0),
        "currency": _normalized_text(product.get("currency")) or "CNY",
        "success_url": "",
        "enabled": bool(product.get("enabled")) and _normalized_text(product.get("status")) == PRODUCT_STATUS_ACTIVE,
        "status": _normalized_text(product.get("status")) or PRODUCT_STATUS_DRAFT,
        "metadata": metadata,
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("cta_text")) or "立即报名",
        "lead_program_id": int(product.get("lead_program_id") or 0) or None,
        "lead_channel_id": int(product.get("lead_channel_id") or lead_qr.get("channel_id") or 0) or None,
        "lead_plan_configured": bool(lead_qr.get("qr_url")),
        "lead_qr": lead_qr,
        **completion_redirect,
        "updated_at": _normalized_text(product.get("updated_at")),
        "created_at": _normalized_text(product.get("created_at")),
    }


def list_products() -> list[dict[str, Any]]:
    db_products = [_present_db_product(product) for product in product_repo.list_active_db_products()]
    db_codes = {_normalized_text(product.get("product_code")) for product in db_products}
    catalog_products = [
        product
        for product in _product_catalog().values()
        if product.get("enabled") and _normalized_text(product.get("product_code")) not in db_codes
    ]
    return db_products + catalog_products


def get_product(product_code: str) -> dict[str, Any] | None:
    code = _normalized_text(product_code)
    db_product = product_repo.get_product_by_code(code)
    if db_product:
        product = _present_db_product(db_product)
        return product if product.get("enabled") else None
    product = _product_catalog().get(code)
    if not product or not product.get("enabled"):
        return None
    return dict(product)


def get_product_slices(product_id: int, *, include_image_url: bool = True) -> list[dict[str, Any]]:
    if int(product_id or 0) <= 0:
        return []
    return [
        _present_slice(row, include_image_url=include_image_url)
        for row in product_repo.list_product_slices(int(product_id), include_image_data=include_image_url)
    ]


def get_public_product_page_state(product_code: str, *, context_token: str = "", context_status: str = "") -> dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    checkout_path = f"/pay/{product['product_code']}"
    return {
        "product": product,
        "slices": get_product_slices(int(product.get("id") or 0)),
        "checkout_url": append_ctx_query(checkout_path, context_token) if context_token else checkout_path,
        "context_token": context_token,
        "context_status": context_status or ("valid" if context_token else "missing"),
    }


def _normalize_slices_payload(slices: Any) -> list[dict[str, int]]:
    if not isinstance(slices, list):
        return []
    if len(slices) > PRODUCT_SLICE_LIMIT:
        raise WeChatPayProductError("全景贴图最多 10 张")
    normalized: list[dict[str, int]] = []
    seen: set[int] = set()
    for index, item in enumerate(slices):
        if isinstance(item, dict):
            image_id = int(item.get("image_library_id") or item.get("id") or 0)
            sort_order = int(item.get("sort_order") or index + 1)
        else:
            image_id = int(item or 0)
            sort_order = index + 1
        if image_id <= 0 or image_id in seen:
            continue
        seen.add(image_id)
        normalized.append({"image_library_id": image_id, "sort_order": sort_order})
    return normalized


def _normalize_product_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    name = _normalized_text(payload.get("name")) or _normalized_text(existing.get("name"))
    if not name:
        raise WeChatPayProductError("商品名称不能为空")
    amount_total = _money_amount_total(payload, existing=existing)
    if amount_total <= 0:
        raise WeChatPayProductError("价格必须大于 0")
    status = _normalize_product_status(payload.get("status") if "status" in payload else existing.get("status"))
    lead_channel_id = _positive_int_from_payload(payload, existing, "lead_channel_id")
    if "lead_channel_id" in payload and not lead_channel_id and "lead_program_id" not in payload:
        lead_program_id = None
    else:
        lead_program_id = _positive_int_from_payload(payload, existing, "lead_program_id")
    if lead_channel_id:
        channel = resolve_lead_channel(lead_program_id, channel_id=lead_channel_id)
        if not _normalized_text((channel or {}).get("qr_url")):
            raise WeChatPayProductError("所选引流渠道码未配置二维码")
        lead_program_id = int((channel or {}).get("program_id") or 0) or lead_program_id
    elif lead_program_id:
        channel = resolve_lead_channel(lead_program_id)
        if not _normalized_text((channel or {}).get("qr_url")):
            raise WeChatPayProductError("所选引流计划未配置二维码")
        lead_channel_id = int((channel or {}).get("id") or 0) or lead_channel_id
    else:
        lead_channel_id = None
    completion_redirect = _normalize_completion_redirect_payload(payload, existing)
    return {
        "name": name[:120],
        "amount_total": amount_total,
        "currency": _normalized_text(payload.get("currency") or existing.get("currency")) or "CNY",
        "status": status,
        "enabled": _enabled_for_status(status),
        "cta_text": (_normalized_text(payload.get("cta_text")) or _normalized_text(existing.get("cta_text")) or "立即报名")[:24],
        "require_mobile": _normalized_bool(payload.get("require_mobile")) if "require_mobile" in payload else bool(existing.get("require_mobile")),
        "lead_program_id": lead_program_id,
        "lead_channel_id": lead_channel_id,
        **completion_redirect,
        "metadata": existing.get("metadata_json") if isinstance(existing.get("metadata_json"), dict) else {},
    }


def _present_admin_product(product: dict[str, Any], *, include_slices: bool = False) -> dict[str, Any]:
    item = _present_db_product(product)
    item["price_yuan"] = f"{item['amount_total'] / 100:.2f}"
    item["slice_count"] = int(product.get("slice_count") or len(get_product_slices(item["id"], include_image_url=False)))
    item.pop("description", None)
    item.pop("success_url", None)
    item.pop("lead_qr", None)
    if include_slices:
        item["slices"] = get_product_slices(item["id"], include_image_url=False)
    return item


def list_admin_products() -> list[dict[str, Any]]:
    return [_present_admin_product(product) for product in product_repo.list_admin_products()]


def get_admin_product(product_id: int) -> dict[str, Any]:
    product = product_repo.get_product_by_id(int(product_id))
    if not product:
        raise WeChatPayProductError("商品不存在")
    return _present_admin_product(product, include_slices=True)


def _product_share_qr_data_url(product_url: str) -> str:
    from io import BytesIO

    import segno

    qr = segno.make(_normalized_text(product_url), error="m", micro=False)
    buffer = BytesIO()
    qr.save(buffer, kind="svg", scale=6, xmldecl=False, svgns=True, nl=False)
    svg = buffer.getvalue().decode("utf-8")
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def build_admin_product_share(product_id: int, *, product_url: str) -> dict[str, Any]:
    product = get_admin_product(int(product_id))
    url = _normalized_text(product_url)
    if not url:
        raise WeChatPayProductError("商品链接生成失败")
    return {
        "product_id": int(product["id"]),
        "product_code": product["product_code"],
        "product_name": product["name"],
        "url": url,
        "qr_data_url": _product_share_qr_data_url(url),
    }


def create_admin_product(payload: dict[str, Any], *, operator: str = "") -> dict[str, Any]:
    del operator
    normalized = _normalize_product_payload(payload)
    product = product_repo.insert_product({"product_code": _generate_product_code(), **normalized})
    product_repo.replace_product_slices(int(product["id"]), _normalize_slices_payload(payload.get("slices")))
    get_db().commit()
    return get_admin_product(int(product["id"]))


def update_admin_product(product_id: int, payload: dict[str, Any], *, operator: str = "") -> dict[str, Any]:
    del operator
    existing = product_repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    normalized = _normalize_product_payload(payload, existing=existing)
    product = product_repo.update_product(int(product_id), normalized)
    if "slices" in payload:
        product_repo.replace_product_slices(int(product_id), _normalize_slices_payload(payload.get("slices")))
    get_db().commit()
    return get_admin_product(int(product["id"]))


def set_admin_product_status(product_id: int, status: str, *, operator: str = "") -> dict[str, Any]:
    del operator
    existing = product_repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    normalized_status = _normalize_product_status(status)
    payload = _normalize_product_payload({"status": normalized_status}, existing=existing)
    product = product_repo.update_product(int(product_id), payload)
    get_db().commit()
    return _present_admin_product(product)


def copy_admin_product(product_id: int, *, operator: str = "") -> dict[str, Any]:
    del operator
    existing = product_repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    payload = _normalize_product_payload(
        {
            "name": f"{_normalized_text(existing.get('name'))} 副本",
            "amount_total": int(existing.get("amount_total") or 0),
            "status": PRODUCT_STATUS_DRAFT,
            "cta_text": existing.get("cta_text"),
            "require_mobile": bool(existing.get("require_mobile")),
            "lead_program_id": existing.get("lead_program_id"),
            "lead_channel_id": existing.get("lead_channel_id"),
            "completion_redirect_enabled": bool(existing.get("completion_redirect_enabled")),
            "completion_redirect_url": existing.get("completion_redirect_url"),
        },
        existing=existing,
    )
    product = product_repo.insert_product({"product_code": _generate_product_code(), **payload})
    source_slices = [
        {"image_library_id": item["image_library_id"], "sort_order": item["sort_order"]}
        for item in product_repo.list_product_slices(int(product_id), enabled_only=False, include_image_data=False)
    ]
    product_repo.replace_product_slices(int(product["id"]), source_slices)
    get_db().commit()
    return get_admin_product(int(product["id"]))


def delete_admin_product(product_id: int, *, operator: str = "") -> None:
    del operator
    existing = product_repo.get_product_by_id(int(product_id))
    if not existing:
        raise WeChatPayProductError("商品不存在")
    product_code = _normalized_text(existing.get("product_code"))
    product_status = _normalized_text(existing.get("status")) or PRODUCT_STATUS_DRAFT
    if (
        product_status == PRODUCT_STATUS_ACTIVE
        and product_code
        and product_repo.count_orders_for_product_code(product_code) > 0
    ):
        raise WeChatPayProductError("已有订单的商品不能删除，请先下架")
    product_repo.delete_product(int(product_id))
    get_db().commit()


def add_admin_product_slice(product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not product_repo.get_product_by_id(int(product_id)):
        raise WeChatPayProductError("商品不存在")
    current_count = len(product_repo.list_product_slices(int(product_id), enabled_only=False, include_image_data=False))
    if current_count >= PRODUCT_SLICE_LIMIT:
        raise WeChatPayProductError("全景贴图最多 10 张")
    image_library_id = int(payload.get("image_library_id") or 0)
    if image_library_id <= 0:
        raise WeChatPayProductError("请选择图片切片")
    product_repo.add_product_slice(int(product_id), image_library_id, sort_order=payload.get("sort_order"))
    get_db().commit()
    return get_admin_product(int(product_id))


def reorder_admin_product_slices(product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if not product_repo.get_product_by_id(int(product_id)):
        raise WeChatPayProductError("商品不存在")
    slice_ids = [int(item) for item in (payload.get("slice_ids") or payload.get("slices") or []) if int(item or 0) > 0]
    product_repo.reorder_product_slices(int(product_id), slice_ids)
    get_db().commit()
    return get_admin_product(int(product_id))


def delete_admin_product_slice(product_id: int, slice_id: int) -> dict[str, Any]:
    product_repo.delete_product_slice(int(product_id), int(slice_id))
    get_db().commit()
    return get_admin_product(int(product_id))


def list_lead_plan_options() -> list[dict[str, Any]]:
    from ..automation_conversion import service as automation_service

    return automation_service.list_product_lead_plan_options()


def list_lead_channel_options() -> list[dict[str, Any]]:
    from ..automation_conversion import service as automation_service

    return automation_service.list_product_lead_channel_options()
