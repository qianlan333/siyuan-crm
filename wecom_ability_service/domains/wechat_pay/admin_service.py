from __future__ import annotations

import base64
import csv
import html
import json
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flask import current_app

from ...infra.json_utils import safe_json_loads
from ..admin_audit import record_audit
from . import repo
from .service import _create_wechat_pay_client, list_products


ADMIN_ORDER_STATUSES = {
    "pending": "待支付",
    "paid": "已支付",
    "partial_refunded": "部分退款",
    "full_refunded": "全额退款",
}
ALLOWED_LIMITS = {20, 50, 100}
EXPORT_HEADERS = [
    "订单创建时间",
    "微信单号",
    "付款人/客户身份",
    "手机号",
    "userid",
    "external_userid",
    "商品名称",
    "商品编码",
    "金额",
    "状态",
]
EXPORT_MAX_DAYS = 90
EXPORT_MAX_ROWS = 5000


class WeChatPayAdminError(ValueError):
    pass


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return _normalized_text(value)


def _iso_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return _normalized_text(value)


def _money_text(amount_total: Any) -> str:
    cents = _normalized_int(amount_total)
    return f"{cents / 100:.2f}"


def _encode_cursor(row: dict[str, Any]) -> str:
    payload = {"created_at": _iso_text(row.get("created_at")), "id": int(row.get("id") or 0)}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


def _merge_order_status(order: dict[str, Any]) -> str:
    amount_total = _normalized_int(order.get("amount_total"))
    refunded = _normalized_int(order.get("refunded_amount_total"))
    refund_status = _normalized_text(order.get("refund_status"))
    if refund_status == "full_refunded" or (amount_total > 0 and refunded >= amount_total):
        return "full_refunded"
    if refund_status == "partial_refunded" or refunded > 0:
        return "partial_refunded"
    if _normalized_text(order.get("status")) == "paid" or _normalized_text(order.get("trade_state")) == "SUCCESS":
        return "paid"
    return "pending"


def _identity_text(order: dict[str, Any]) -> str:
    payer_name = _normalized_text(order.get("payer_name_snapshot")) or "未记录付款人"
    mobile = _normalized_text(order.get("mobile_snapshot")) or "未记录手机号"
    userid = _normalized_text(order.get("userid_snapshot"))
    external_userid = _normalized_text(order.get("external_userid"))
    identity = userid or external_userid or _normalized_text(order.get("respondent_key")) or "-"
    return f"{payer_name} / {mobile} / {identity}"


def _present_order(order: dict[str, Any], *, include_refund: bool = False) -> dict[str, Any]:
    status = _merge_order_status(order)
    amount_total = _normalized_int(order.get("amount_total"))
    refunded = max(0, _normalized_int(order.get("refunded_amount_total")))
    refundable = max(0, amount_total - refunded)
    product_code = _normalized_text(order.get("product_code"))
    product_name = _normalized_text(order.get("product_name")) or product_code
    presented = {
        "id": int(order.get("id") or 0),
        "created_at": _dt_text(order.get("created_at")),
        "transaction_id": _normalized_text(order.get("transaction_id")) or "待支付暂无微信单号",
        "has_transaction_id": bool(_normalized_text(order.get("transaction_id"))),
        "payer_name": _normalized_text(order.get("payer_name_snapshot")) or "未记录付款人",
        "mobile": _normalized_text(order.get("mobile_snapshot")),
        "userid": _normalized_text(order.get("userid_snapshot")),
        "external_userid": _normalized_text(order.get("external_userid")),
        "identity": _identity_text(order),
        "product_code": product_code,
        "product_name": product_name,
        "amount_total": amount_total,
        "amount_yuan": _money_text(amount_total),
        "currency": _normalized_text(order.get("currency")) or "CNY",
        "status": status,
        "status_label": ADMIN_ORDER_STATUSES[status],
        "detail_url": f"/admin/wechat-pay/transactions/{int(order.get('id') or 0)}",
    }
    if include_refund:
        presented.update(
            {
                "refunded_amount_total": refunded,
                "refunded_amount_yuan": _money_text(refunded),
                "refundable_amount_total": refundable,
                "refundable_amount_yuan": _money_text(refundable),
                "can_refund": status in {"paid", "partial_refunded"} and refundable > 0,
            }
        )
    return presented


def default_filters() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    return {
        "created_from": start.strftime("%Y-%m-%dT00:00"),
        "created_to": now.strftime("%Y-%m-%dT23:59"),
        "product_code": "",
        "status": "",
        "mobile": "",
        "identity": "",
        "transaction_id": "",
    }


def normalize_filters(payload: dict[str, Any] | None) -> dict[str, str]:
    source = dict(payload or {})
    filters = {
        "created_from": _normalized_text(source.get("created_from")),
        "created_to": _normalized_text(source.get("created_to")),
        "product_code": _normalized_text(source.get("product_code")),
        "status": _normalized_text(source.get("status")),
        "mobile": _normalized_text(source.get("mobile") or source.get("mobile_snapshot")),
        "identity": _normalized_text(source.get("identity")),
        "transaction_id": _normalized_text(source.get("transaction_id")),
    }
    if filters["status"] and filters["status"] not in ADMIN_ORDER_STATUSES:
        raise WeChatPayAdminError("订单状态筛选不合法")
    return filters


def normalize_limit(value: Any) -> int:
    limit = _normalized_int(value, default=20)
    return limit if limit in ALLOWED_LIMITS else 20


def list_product_options() -> list[dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for product in list_products():
        code = _normalized_text(product.get("product_code"))
        if not code:
            continue
        options[code] = {"product_code": code, "product_name": _normalized_text(product.get("name")) or code}
    for product in repo.list_products_from_orders():
        code = _normalized_text(product.get("product_code"))
        if not code or code in options:
            continue
        options[code] = {"product_code": code, "product_name": _normalized_text(product.get("product_name")) or code}
    return list(options.values())


def list_orders(*, filters: dict[str, Any] | None, limit: Any = 20, cursor: str = "") -> dict[str, Any]:
    normalized_filters = normalize_filters(filters)
    page_size = normalize_limit(limit)
    rows = repo.list_admin_orders(filters=normalized_filters, limit=page_size + 1, cursor=_normalized_text(cursor))
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor = _encode_cursor(page_rows[-1]) if has_more and page_rows else ""
    return {
        "items": [_present_order(row) for row in page_rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": page_size,
    }


def get_order_detail(order_id: Any) -> dict[str, Any]:
    order = repo.get_admin_order_by_id(_normalized_int(order_id))
    if not order:
        raise WeChatPayAdminError("订单不存在")
    events = [
        {
            "id": int(event.get("id") or 0),
            "event_type": _normalized_text(event.get("event_type")),
            "event_label": _event_label(event.get("event_type")),
            "transaction_id": _normalized_text(event.get("transaction_id")) or "-",
            "trade_state": _normalized_text(event.get("trade_state")) or "-",
            "created_at": _dt_text(event.get("created_at")),
        }
        for event in repo.list_order_events(order.get("out_trade_no"))
    ]
    return {"order": _present_order(order, include_refund=True), "events": events}


def _event_label(event_type: Any) -> str:
    mapping = {
        "notify": "微信支付通知",
        "query": "主动查询订单",
        "refund_requested": "后台申请退款",
        "refund_failed": "退款申请失败",
    }
    text = _normalized_text(event_type)
    return mapping.get(text, text or "订单事件")


def _generate_out_refund_no() -> str:
    return "WXR" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(6).upper()


def create_refund_request(
    *,
    order_id: Any,
    refund_amount_total: Any,
    reason: Any,
    transaction_id_confirmation: Any,
    checked: Any,
    operator: str,
) -> dict[str, Any]:
    order = repo.get_admin_order_by_id(_normalized_int(order_id))
    if not order:
        raise WeChatPayAdminError("订单不存在")
    status = _merge_order_status(order)
    if status not in {"paid", "partial_refunded"}:
        raise WeChatPayAdminError("只有已支付或部分退款订单可以申请退款")
    transaction_id = _normalized_text(order.get("transaction_id"))
    if not transaction_id or _normalized_text(transaction_id_confirmation) != transaction_id:
        raise WeChatPayAdminError("微信单号二次确认不匹配")
    if str(checked).lower() not in {"1", "true", "yes", "on"}:
        raise WeChatPayAdminError("请先勾选已核对付款人、商品、金额和微信单号")
    amount_total = _normalized_int(refund_amount_total)
    if amount_total <= 0:
        raise WeChatPayAdminError("退款金额必须大于 0")
    order_amount = _normalized_int(order.get("amount_total"))
    refunded = _normalized_int(order.get("refunded_amount_total"))
    active_refunding = repo.sum_active_refund_amount(int(order.get("id") or 0))
    if refunded + active_refunding + amount_total > order_amount:
        raise WeChatPayAdminError("累计退款金额不能超过订单金额")
    reason_text = _normalized_text(reason)
    if not reason_text:
        raise WeChatPayAdminError("请选择退款原因")

    out_refund_no = _generate_out_refund_no()
    currency = _normalized_text(order.get("currency")) or "CNY"
    request_payload = {
        "transaction_id": transaction_id,
        "out_refund_no": out_refund_no,
        "reason": reason_text[:80],
        "amount": {
            "refund": amount_total,
            "total": order_amount,
            "currency": currency,
        },
    }
    repo.insert_refund_request(
        {
            "order_id": int(order.get("id") or 0),
            "out_trade_no": order.get("out_trade_no"),
            "transaction_id": transaction_id,
            "out_refund_no": out_refund_no,
            "reason": reason_text,
            "refund_amount_total": amount_total,
            "order_amount_total": order_amount,
            "currency": currency,
            "requested_by": _normalized_text(operator) or "crm_console",
            "request_payload": request_payload,
        }
    )
    try:
        response_payload = _create_wechat_pay_client().create_refund(request_payload)
    except Exception as exc:
        repo.update_refund_response(
            out_refund_no,
            status="failed",
            response_payload={},
            error_message=str(exc),
        )
        repo.insert_event(
            out_trade_no=order.get("out_trade_no"),
            event_type="refund_failed",
            transaction_id=transaction_id,
            trade_state=_normalized_text(order.get("trade_state")),
            payload={"out_refund_no": out_refund_no, "amount_total": amount_total, "error": str(exc)},
            headers={},
        )
        raise WeChatPayAdminError(f"微信支付退款申请失败：{exc}") from exc

    refund_status = _normalized_text(response_payload.get("status")) or "PROCESSING"
    repo.update_refund_response(
        out_refund_no,
        refund_id=_normalized_text(response_payload.get("refund_id")),
        status=refund_status,
        response_payload=response_payload,
        error_message="",
    )
    updated_order = order
    if refund_status == "SUCCESS":
        updated_order = repo.apply_successful_refund(order_id=int(order.get("id") or 0), amount_total=amount_total)
    repo.insert_event(
        out_trade_no=order.get("out_trade_no"),
        event_type="refund_requested",
        transaction_id=transaction_id,
        trade_state=_normalized_text(order.get("trade_state")),
        payload={
            "out_refund_no": out_refund_no,
            "refund_id": _normalized_text(response_payload.get("refund_id")),
            "wechat_refund_status": refund_status,
            "amount_total": amount_total,
        },
        headers={},
    )
    record_audit(
        operator=_normalized_text(operator) or "crm_console",
        action_type="wechat_pay_refund_requested",
        target_type="wechat_pay_order",
        target_id=str(order.get("id") or ""),
        before={
            "status": status,
            "amount_total": order_amount,
            "refunded_amount_total": refunded,
        },
        after={
            "refund_amount_total": amount_total,
            "reason": reason_text,
            "transaction_id": transaction_id,
            "wechat_refund_status": refund_status,
        },
    )
    presented_order = _present_order(updated_order or order, include_refund=True)
    return {
        "order": presented_order,
        "refund": {
            "status": refund_status,
            "status_label": _refund_status_label(refund_status),
        },
    }


def _refund_status_label(status: str) -> str:
    mapping = {
        "SUCCESS": "退款成功",
        "CLOSED": "退款关闭",
        "PROCESSING": "退款处理中",
        "ABNORMAL": "退款异常",
        "failed": "退款申请失败",
    }
    return mapping.get(_normalized_text(status), _normalized_text(status) or "退款处理中")


def _parse_date(value: str) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _validate_export_filters(filters: dict[str, str]) -> None:
    created_from = _parse_date(filters.get("created_from", ""))
    created_to = _parse_date(filters.get("created_to", ""))
    if created_from and created_to and created_to - created_from > timedelta(days=EXPORT_MAX_DAYS):
        raise WeChatPayAdminError(f"导出时间范围最多 {EXPORT_MAX_DAYS} 天")


def create_export_job(
    *,
    filters: dict[str, Any] | None,
    scope: str,
    file_format: str,
    cursor: str = "",
    limit: Any = 20,
    requested_by: str = "",
) -> dict[str, Any]:
    normalized_filters = normalize_filters(filters)
    export_defaults = default_filters()
    normalized_filters["created_from"] = normalized_filters["created_from"] or export_defaults["created_from"]
    normalized_filters["created_to"] = normalized_filters["created_to"] or export_defaults["created_to"]
    _validate_export_filters(normalized_filters)
    normalized_scope = _normalized_text(scope) or "filtered"
    if normalized_scope not in {"filtered", "current_page"}:
        raise WeChatPayAdminError("导出范围不合法")
    normalized_format = _normalized_text(file_format).lower() or "xlsx"
    if normalized_format not in {"xlsx", "csv"}:
        raise WeChatPayAdminError("导出格式不合法")
    job_id = "WXP_EXP_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(3).upper()
    job = repo.insert_export_job(
        {
            "job_id": job_id,
            "requested_by": requested_by,
            "filters": normalized_filters,
            "scope": normalized_scope,
            "file_format": normalized_format,
        }
    )
    try:
        _run_export_job(job_id=job_id, filters=normalized_filters, scope=normalized_scope, file_format=normalized_format, cursor=cursor, limit=limit)
    except Exception as exc:  # pragma: no cover - defensive envelope
        repo.update_export_job(job_id, status="failed", error_message=str(exc)[:500], finished_at=_dt_text(datetime.now(timezone.utc)))
    return {"job_id": job_id, "status": "queued", "created_at": _dt_text(job.get("created_at"))}


def _run_export_job(*, job_id: str, filters: dict[str, str], scope: str, file_format: str, cursor: str, limit: Any) -> None:
    repo.update_export_job(job_id, status="running")
    export_limit = normalize_limit(limit) if scope == "current_page" else EXPORT_MAX_ROWS
    query_cursor = _normalized_text(cursor) if scope == "current_page" else ""
    payload = list_orders(filters=filters, limit=export_limit if export_limit in ALLOWED_LIMITS else 100, cursor=query_cursor)
    rows = payload["items"]
    if scope == "filtered":
        while payload["has_more"] and len(rows) < EXPORT_MAX_ROWS:
            payload = list_orders(filters=filters, limit=100, cursor=payload["next_cursor"])
            rows.extend(payload["items"])
    file_name = f"{job_id}.{file_format}"
    export_dir = Path(current_app.instance_path) / "wechat_pay_order_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / file_name
    if file_format == "csv":
        _write_csv(file_path, rows)
    else:
        _write_xlsx(file_path, rows)
    repo.update_export_job(
        job_id,
        status="succeeded",
        exported_count=len(rows),
        file_name=file_name,
        file_path=str(file_path),
        error_message="",
        finished_at=_dt_text(datetime.now(timezone.utc)),
    )


def _export_row(row: dict[str, Any]) -> list[str]:
    return [
        _normalized_text(row.get("created_at")),
        _normalized_text(row.get("transaction_id")),
        _normalized_text(row.get("identity")),
        _normalized_text(row.get("mobile")),
        _normalized_text(row.get("userid")),
        _normalized_text(row.get("external_userid")),
        _normalized_text(row.get("product_name")),
        _normalized_text(row.get("product_code")),
        _normalized_text(row.get("amount_yuan")),
        _normalized_text(row.get("status_label")),
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPORT_HEADERS)
        for row in rows:
            writer.writerow(_export_row(row))


def _xlsx_cell(value: Any) -> str:
    escaped = html.escape(_normalized_text(value), quote=False)
    return f'<c t="inlineStr"><is><t>{escaped}</t></is></c>'


def _write_xlsx(path: Path, rows: list[dict[str, Any]]) -> None:
    table_rows = [EXPORT_HEADERS] + [_export_row(row) for row in rows]
    sheet_xml_rows = []
    for row_index, row in enumerate(table_rows, start=1):
        cells = "".join(_xlsx_cell(cell) for cell in row)
        sheet_xml_rows.append(f'<row r="{row_index}">{cells}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(sheet_xml_rows)
        + "</sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _XLSX_CONTENT_TYPES)
        zf.writestr("_rels/.rels", _XLSX_RELS)
        zf.writestr("xl/workbook.xml", _XLSX_WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", _XLSX_WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def get_export_job(job_id: str) -> dict[str, Any]:
    job = repo.get_export_job(job_id)
    if not job:
        raise WeChatPayAdminError("导出任务不存在")
    filters_json = job.get("filters_json")
    filters = filters_json if isinstance(filters_json, dict) else safe_json_loads(filters_json, default={})
    return {
        "job_id": _normalized_text(job.get("job_id")),
        "status": _normalized_text(job.get("status")) or "queued",
        "scope": _normalized_text(job.get("scope")),
        "format": _normalized_text(job.get("file_format")),
        "filters": filters if isinstance(filters, dict) else {},
        "exported_count": _normalized_int(job.get("exported_count")),
        "file_name": _normalized_text(job.get("file_name")),
        "error_message": _normalized_text(job.get("error_message")),
        "created_at": _dt_text(job.get("created_at")),
        "finished_at": _normalized_text(job.get("finished_at")),
    }


def export_download_path(job_id: str) -> tuple[Path, str]:
    job = repo.get_export_job(job_id)
    if not job:
        raise WeChatPayAdminError("导出任务不存在")
    if _normalized_text(job.get("status")) != "succeeded":
        raise WeChatPayAdminError("导出任务尚未完成")
    path = Path(_normalized_text(job.get("file_path")))
    if not path.exists():
        raise WeChatPayAdminError("导出文件不存在")
    return path, _normalized_text(job.get("file_name")) or path.name


_XLSX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
_XLSX_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
_XLSX_WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="微信支付订单" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
_XLSX_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
