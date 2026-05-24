from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

from ...application.customer_read_model import CustomerChatContextQueryDTO, GetCustomerChatContextQuery
from ...application.identity_contact.dto import GetContactBindingStatusQueryDTO
from ...application.identity_contact.queries import GetContactBindingStatusQuery
from ...customer_center.repo import fetch_owner_role_map
from ...domains import attachment_library, image_library, miniprogram_library
from ...domains.admin_console.customer_profile_service import (
    get_customer_messages_payload,
    get_customer_questionnaire_answers_payload,
)
from ...domains.automation_conversion import private_message_dispatch
from ...domains.wechat_pay import product_service as wechat_pay_product_service
from . import repo

MODULES = ["profile", "questionnaires", "products", "orders", "materials", "other_staff_messages"]
MAX_PROFILE_TEXT_LENGTH = 4000
DEFAULT_MATERIAL_CONTENT = "给你发一份资料，你可以看下。"
ORDER_STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "refund_processing": "退款处理中",
    "partial_refunded": "部分退款",
    "full_refunded": "全额退款",
    "closed": "已关闭",
    "failed": "支付失败",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _limit(value: Any, *, default: int = 50, maximum: int = 200) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _format_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return (value + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    text = _text(value).replace("T", " ")
    if not text:
        return ""
    try:
        return (datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S") + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    return text[:16]


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _money_label(amount_total: Any) -> str:
    cents = _int(amount_total)
    yuan = cents / 100
    if cents % 100 == 0:
        return f"¥{int(yuan)}"
    return f"¥{yuan:.2f}"


def _context(external_userid: str) -> dict[str, Any]:
    try:
        payload = GetCustomerChatContextQuery()(
            CustomerChatContextQueryDTO(external_userid=external_userid, recent_message_limit=20, timeline_limit=20)
        )
    except Exception:
        return {}
    return dict(payload or {}) if (payload or {}).get("ok", True) else {}


def _binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    try:
        return GetContactBindingStatusQuery()(
            GetContactBindingStatusQueryDTO(external_userid=external_userid, owner_userid=owner_userid)
        )
    except Exception:
        return {}


def _avatar_text(display_name: str) -> str:
    return display_name[:1] if display_name else ""


def _customer_payload(context: dict[str, Any], binding: dict[str, Any], external_userid: str, owner_userid: str) -> dict[str, Any]:
    customer = dict(context.get("customer") or {})
    customer_binding = dict(customer.get("binding") or {})
    contact = dict(customer.get("contact") or {})
    display_name = (
        _text(customer.get("display_name"))
        or _text(customer.get("customer_name"))
        or _text(customer.get("remark"))
        or _text(contact.get("name"))
        or _text(binding.get("display_name"))
        or _text(binding.get("customer_name"))
        or external_userid
    )
    resolved_owner = owner_userid or _text(customer.get("owner_userid")) or _text(binding.get("owner_userid"))
    mobile = _text(customer.get("mobile")) or _text(customer_binding.get("mobile")) or _text(binding.get("mobile"))
    is_bound = bool(customer_binding.get("is_bound")) or bool(binding.get("is_bound")) or bool(mobile)
    return {
        "display_name": display_name,
        "avatar_text": _avatar_text(display_name),
        "mobile": mobile,
        "is_bound": is_bound,
        "external_userid": external_userid,
        "owner_userid": resolved_owner,
    }


def _answer_profile_fallback(questionnaires: list[dict[str, Any]]) -> dict[str, str]:
    fields = {"source": "", "industry": "", "industry_description": "", "needs_blockers_followup": ""}
    for questionnaire in questionnaires:
        for answer in questionnaire.get("answers") or []:
            question = _text(answer.get("question"))
            value = _text(answer.get("answer"))
            if not value:
                continue
            if not fields["source"] and ("来源" in question or "渠道" in question):
                fields["source"] = value
            elif not fields["industry"] and "行业" in question:
                fields["industry"] = value
            elif not fields["industry_description"] and ("行业" in question or "业务" in question):
                fields["industry_description"] = value
            elif not fields["needs_blockers_followup"] and any(key in question for key in ("需求", "痛点", "阻碍", "跟进")):
                fields["needs_blockers_followup"] = value
    return fields


def _profile_from_context(sidebar_context: dict[str, Any]) -> dict[str, str]:
    return {
        "source": _text(sidebar_context.get("source")),
        "industry": _text(sidebar_context.get("industry")),
        "industry_description": _text(sidebar_context.get("industry_description")),
        "needs_blockers_followup": _text(sidebar_context.get("needs_blockers_followup")),
    }


def _profile_payload(external_userid: str, context: dict[str, Any], questionnaires: list[dict[str, Any]]) -> dict[str, str]:
    persisted = repo.get_profile_fields(external_userid) or {}
    if persisted:
        return {
            "source": _text(persisted.get("source")),
            "industry": _text(persisted.get("industry")),
            "industry_description": _text(persisted.get("industry_description")),
            "needs_blockers_followup": _text(persisted.get("needs_blockers_followup")),
        }
    sidebar_context = dict((context.get("customer") or {}).get("sidebar_context") or {})
    fallback = _profile_from_context(sidebar_context)
    answer_fallback = _answer_profile_fallback(questionnaires)
    return {key: fallback.get(key) or answer_fallback.get(key) or "" for key in fallback}


def get_sidebar_workbench(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    normalized_external_userid = _text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_owner = _text(owner_userid)
    context = _context(normalized_external_userid)
    binding = dict(context.get("binding") or {}) or _binding_status(normalized_external_userid, normalized_owner)
    customer = _customer_payload(context, binding, normalized_external_userid, normalized_owner)
    questionnaires = get_questionnaires(external_userid=normalized_external_userid)["questionnaires"]
    sidebar_context = dict((context.get("customer") or {}).get("sidebar_context") or {})
    workflow_title = (
        _text(sidebar_context.get("workflow_title"))
        or _text(sidebar_context.get("sop_title"))
        or _text(sidebar_context.get("program_name"))
        or repo.get_workflow_title_for_customer(normalized_external_userid)
    )
    return {
        "ok": True,
        "customer": customer,
        "workflow": {"title": workflow_title},
        "profile": _profile_payload(normalized_external_userid, context, questionnaires),
        "modules": list(MODULES),
    }


def update_profile(
    *,
    external_userid: str,
    source: str,
    industry: str,
    industry_description: str = "",
    needs_blockers_followup: str = "",
    updated_by: str = "",
) -> dict[str, Any]:
    normalized_external_userid = _text(external_userid)
    normalized_source = _text(source)
    normalized_industry = _text(industry)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_source = normalized_source[:MAX_PROFILE_TEXT_LENGTH]
    normalized_industry = normalized_industry[:MAX_PROFILE_TEXT_LENGTH]
    description = _text(industry_description)[:MAX_PROFILE_TEXT_LENGTH]
    blockers = _text(needs_blockers_followup)[:MAX_PROFILE_TEXT_LENGTH]
    row = repo.upsert_profile_fields(
        external_userid=normalized_external_userid,
        source=normalized_source,
        industry=normalized_industry,
        industry_description=description,
        needs_blockers_followup=blockers,
        updated_by=_text(updated_by),
    )
    return {
        "ok": True,
        "profile": {
            "source": _text(row.get("source")),
            "industry": _text(row.get("industry")),
            "industry_description": _text(row.get("industry_description")),
            "needs_blockers_followup": _text(row.get("needs_blockers_followup")),
        },
        "updated_by": _text(row.get("updated_by")),
        "updated_at": _format_time(row.get("updated_at")),
    }


def _group_questionnaire_answers(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for answer in answers:
        submission_id = _text(answer.get("submission_id"))
        questionnaire_id = _text(answer.get("questionnaire_id"))
        submitted_at = _format_time(answer.get("submitted_at"))
        key = (submission_id or questionnaire_id, _text(answer.get("questionnaire_title")) or "未命名问卷", submitted_at)
        if key not in grouped:
            order.append(key)
            grouped[key] = {
                "id": submission_id or questionnaire_id or f"q_{len(order)}",
                "title": key[1],
                "submitted_at": submitted_at,
                "answer_count": 0,
                "total_count": 0,
                "answers": [],
            }
        grouped[key]["answers"].append({"question": _text(answer.get("question")), "answer": _text(answer.get("answer"))})
        grouped[key]["answer_count"] += 1
        grouped[key]["total_count"] += 1
    return [grouped[key] for key in order]


def get_questionnaires(*, external_userid: str) -> dict[str, Any]:
    normalized_external_userid = _text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    try:
        payload = get_customer_questionnaire_answers_payload(external_userid=normalized_external_userid)
    except LookupError:
        return {"ok": True, "questionnaires": []}
    answers = list((payload or {}).get("answers") or [])
    return {"ok": True, "questionnaires": _group_questionnaire_answers(answers)}


def _material_item(item: dict[str, Any], material_type: str) -> dict[str, Any]:
    item_id = int(item.get("id") or 0)
    thumbnail_url = ""
    if material_type == "image":
        title = _text(item.get("name")) or _text(item.get("file_name")) or "未命名图片素材"
        label = "图"
        if item_id:
            thumbnail_url = f"/api/sidebar/v2/materials/image/{item_id}/thumbnail"
    elif material_type == "mini":
        title = _text(item.get("title")) or _text(item.get("name")) or "未命名小程序素材"
        label = "小"
    else:
        title = _text(item.get("name")) or _text(item.get("file_name")) or "未命名 PDF 素材"
        label = "PDF"
    tags = [_text(tag) for tag in list(item.get("tags") or []) if _text(tag)][:3]
    return {
        "id": item_id,
        "type": material_type,
        "title": title,
        "thumbnail_label": label,
        "thumbnail_url": thumbnail_url,
        "tags": tags,
        "enabled": bool(item.get("enabled")),
    }


def list_materials(*, material_type: str, limit: int = 50) -> dict[str, Any]:
    normalized_type = _text(material_type)
    safe_limit = _limit(limit, default=50, maximum=200)
    if normalized_type == "image":
        rows = image_library.list_images(enabled_only=True, limit=safe_limit)
    elif normalized_type == "mini":
        rows = miniprogram_library.list_miniprograms(enabled_only=True)[:safe_limit]
    elif normalized_type == "pdf":
        rows = attachment_library.list_attachments(enabled_only=True, limit=safe_limit)
    else:
        raise ValueError("type must be image, mini, or pdf")
    return {"ok": True, "materials": [_material_item(dict(item), normalized_type) for item in rows]}


def get_image_thumbnail(image_id: int) -> dict[str, Any]:
    item = image_library.get_image(int(image_id or 0), include_data=True)
    if not item:
        raise LookupError("image not found")
    source_url = _text(item.get("source_url"))
    if _text(item.get("source")) == "url" and source_url:
        return {"redirect_url": source_url}
    data_base64 = _text(item.get("data_base64"))
    if not data_base64:
        raise LookupError("image data not found")
    if "," in data_base64 and data_base64.lower().startswith("data:"):
        data_base64 = data_base64.split(",", 1)[1]
    try:
        body = base64.b64decode(data_base64, validate=True)
    except Exception as exc:
        raise ValueError("invalid image data") from exc
    return {"body": body, "mime_type": _text(item.get("mime_type")) or "image/png"}


def send_material(
    *,
    external_userid: str,
    owner_userid: str = "",
    material_type: str,
    material_id: Any,
    operator: str = "",
    delivery_mode: str = "",
) -> dict[str, Any]:
    normalized_external_userid = _text(external_userid)
    normalized_type = _text(material_type)
    normalized_delivery_mode = _text(delivery_mode)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    try:
        library_id = int(material_id)
    except (TypeError, ValueError):
        raise ValueError("material_id is required") from None
    kwargs: dict[str, Any] = {}
    media_id = ""
    if normalized_type == "image":
        media_id = image_library.resolve_image_media_id(library_id)
        if normalized_delivery_mode == "chat_toolbar":
            return {
                "ok": True,
                "status": "ready",
                "delivery_mode": "chat_toolbar",
                "media_id": media_id,
                "record_id": 0,
                "task_ids": [],
                "sender_userid": _text(owner_userid),
                "error": "",
            }
        kwargs["image_media_ids"] = [media_id]
    elif normalized_type == "mini":
        kwargs["miniprogram_library_ids"] = [library_id]
    elif normalized_type == "pdf":
        kwargs["attachment_library_ids"] = [library_id]
    else:
        raise ValueError("type must be image, mini, or pdf")
    result = private_message_dispatch._dispatch_private_message_batch(
        target_items=[{"external_userid": normalized_external_userid}],
        content=DEFAULT_MATERIAL_CONTENT,
        operator_id=_text(operator) or _text(owner_userid) or "sidebar_v2",
        filter_snapshot={"source": "sidebar_v2_material_send", "material_type": normalized_type, "material_id": library_id},
        sender_userid=_text(owner_userid) or None,
        **kwargs,
    )
    return {
        "ok": bool(result.get("ok")),
        "status": _text(result.get("status")),
        "record_id": int(result.get("record_id") or 0),
        "task_ids": list(result.get("task_ids") or []),
        "sender_userid": _text(result.get("sender_userid")),
        "error": _text(result.get("error") or result.get("error_message")),
    }


def _staff_names(userids: set[str]) -> dict[str, str]:
    if not userids:
        return {}
    return {
        userid: _text(item.get("display_name")) or userid
        for userid, item in fetch_owner_role_map(sorted(userids)).items()
    }


def _message_scene(message: dict[str, Any]) -> tuple[str, str]:
    chat_type = _text(message.get("chat_type"))
    if chat_type == "group" or _text(message.get("chat_id")) or _text(message.get("roomid")):
        return "group", _text(message.get("group_name")) or "群聊"
    return "private", "私聊"


def get_other_staff_messages(*, external_userid: str, current_userid: str = "", limit: int = 20) -> dict[str, Any]:
    normalized_external_userid = _text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    safe_limit = _limit(limit, default=20, maximum=100)
    try:
        payload = get_customer_messages_payload(external_userid=normalized_external_userid, limit=200)
        messages = list((payload or {}).get("messages") or [])
    except LookupError:
        messages = []
    binding = _binding_status(normalized_external_userid, "")
    current_staff = {
        _text(current_userid),
        _text(binding.get("owner_userid")),
        _text(binding.get("first_owner_userid")),
        _text(binding.get("last_owner_userid")),
        _text(binding.get("first_bound_by_userid")),
    }
    current_staff.discard("")
    filtered: list[dict[str, Any]] = []
    for message in messages:
        sender = _text(message.get("sender"))
        msgtype = _text(message.get("msgtype"))
        if not sender or sender == normalized_external_userid or sender in current_staff or msgtype not in {"text", "image"}:
            continue
        filtered.append(message)
    selected = filtered[-safe_limit:]
    staff_name_map = _staff_names({_text(item.get("sender")) for item in selected if _text(item.get("sender"))})
    items: list[dict[str, Any]] = []
    for message in selected:
        sender = _text(message.get("sender"))
        msgtype = _text(message.get("msgtype"))
        scene, scene_label = _message_scene(message)
        content = _text(message.get("content")) if msgtype == "text" else "发送了图片"
        staff_name = staff_name_map.get(sender) or sender
        items.append(
            {
                "id": _text(message.get("id")) or _text(message.get("msgid")),
                "type": msgtype,
                "content": content,
                "send_time": _format_time(message.get("send_time")),
                "scene": scene,
                "scene_label": scene_label,
                "staff_name": staff_name,
                "staff_userid": sender,
                "sender_label": staff_name,
            }
        )
    return {"ok": True, "messages": items}


def _product_item(item: dict[str, Any]) -> dict[str, Any]:
    product_code = _text(item.get("product_code"))
    product_id = _text(item.get("id"))
    public_path = f"/p/{product_code}" if product_code else ""
    return {
        "id": product_code or product_id,
        "title": _text(item.get("name")) or product_code or "未命名商品",
        "price_label": _money_label(item.get("amount_total")),
        "product_url": public_path,
    }


def get_products(*, external_userid: str) -> dict[str, Any]:
    if not _text(external_userid):
        raise ValueError("external_userid is required")
    rows = wechat_pay_product_service.list_products()
    return {"ok": True, "products": [_product_item(dict(item)) for item in rows]}


def _order_status(order: dict[str, Any]) -> str:
    amount_total = _int(order.get("amount_total"))
    refunded = _int(order.get("refunded_amount_total"))
    refund_status = _text(order.get("refund_status"))
    status = _text(order.get("status"))
    trade_state = _text(order.get("trade_state"))
    if refund_status == "full_refunded" or (amount_total > 0 and refunded >= amount_total):
        return "full_refunded"
    if refund_status == "partial_refunded" or refunded > 0:
        return "partial_refunded"
    if status == "paid" or trade_state == "SUCCESS":
        return "paid"
    if status in {"closed", "cancelled"} or trade_state in {"CLOSED", "REVOKED"}:
        return "closed"
    if status in {"failed", "error"} or trade_state == "PAYERROR":
        return "failed"
    return "pending"


def _order_item(order: dict[str, Any]) -> dict[str, Any]:
    order_id = _text(order.get("id"))
    product_code = _text(order.get("product_code"))
    product_name = _text(order.get("product_name")) or product_code or "未命名商品"
    status = _order_status(order)
    return {
        "id": _text(order.get("out_trade_no")) or order_id,
        "order_id": order_id,
        "title": product_name,
        "amount_label": _money_label(order.get("amount_total")),
        "status_label": ORDER_STATUS_LABELS.get(status, status),
        "paid_at": _format_time(order.get("paid_at") or order.get("created_at")),
        "detail_url": f"/admin/wechat-pay/transactions/{order_id}" if order_id else "",
    }


def get_orders(*, external_userid: str) -> dict[str, Any]:
    normalized_external_userid = _text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    context = _context(normalized_external_userid)
    binding = dict(context.get("binding") or {}) or _binding_status(normalized_external_userid, "")
    customer = _customer_payload(context, binding, normalized_external_userid, "")
    rows = repo.list_customer_wechat_pay_orders(
        external_userid=normalized_external_userid,
        mobile=_text(customer.get("mobile")),
        limit=20,
    )
    return {"ok": True, "orders": [_order_item(dict(item)) for item in rows]}
