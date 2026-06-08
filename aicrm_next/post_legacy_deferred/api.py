from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()

_COMMON_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
}
_JSON_HEADERS = {key: value for key, value in _COMMON_HEADERS.items() if value}
_CSV_HEADERS = dict(_JSON_HEADERS)
_CSV_HEADERS["X-AICRM-External-Storage-Executed"] = "false"

_WE_COM_LINKS: list[dict[str, Any]] = []
_NEXT_ID = 1


def reset_post_legacy_deferred_fixture_state() -> None:
    global _WE_COM_LINKS, _NEXT_ID
    _NEXT_ID = 1
    now = _now()
    _WE_COM_LINKS = [
        {
            "id": 1,
            "link_id": "post_legacy_fixture_link",
            "link_name": "Post Legacy Fixture",
            "name": "Post Legacy Fixture",
            "description": "safe-mode local fixture",
            "link_url": "https://work.weixin.qq.com/ca/post-legacy-fixture",
            "customer_channel": "wca_post_legacy_fixture",
            "final_url": "https://work.weixin.qq.com/ca/post-legacy-fixture?customer_channel=wca_post_legacy_fixture",
            "program_id": None,
            "workflow_id": None,
            "initial_audience_code": "pending_questionnaire",
            "status": "active",
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "real_external_call_executed": False,
            "created_at": now,
            "updated_at": now,
        }
    ]
    _NEXT_ID = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _common_payload(source_status: str) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": source_status,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_JSON_HEADERS)


def _options(source_status: str) -> JSONResponse:
    payload = _common_payload(source_status)
    payload.update({"allowed": True})
    return _json(payload)


def _customer_channel(*, link_id: str, name: str) -> str:
    seed = _text(link_id) or _text(name) or uuid.uuid4().hex
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in seed).strip("_")
    return f"wca_{normalized[:48] or uuid.uuid4().hex[:12]}"


def _final_url(link_url: str, customer_channel: str) -> str:
    base = _text(link_url) or "https://work.weixin.qq.com/ca/post-legacy-local"
    parsed = urlsplit(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["customer_channel"] = customer_channel
    return urlunsplit((parsed.scheme or "https", parsed.netloc or "work.weixin.qq.com", parsed.path or "/ca/post-legacy-local", urlencode(query), parsed.fragment))


async def _payload(request: Request) -> dict[str, Any]:
    if request.method.upper() == "GET":
        return dict(request.query_params)
    if "application/json" in _text(request.headers.get("content-type")).lower():
        body = await request.json()
        return dict(body or {}) if isinstance(body, dict) else {}
    form = await request.form()
    return dict(form)


def _link_view(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _find_link(link_id: str) -> dict[str, Any] | None:
    normalized = _text(link_id)
    for row in _WE_COM_LINKS:
        if str(row.get("id")) == normalized or _text(row.get("link_id")) == normalized:
            return row
    return None


@router.api_route("/api/admin/class-user-management/export", methods=["GET", "POST", "OPTIONS"])
async def class_user_management_export(request: Request) -> Response:
    if request.method.upper() == "OPTIONS":
        return _options("next_class_user_management_export")
    payload = await _payload(request)
    signup_status = _text(payload.get("signup_status"))
    rows = [
        {
            "customer_name": "Post Legacy Local",
            "mobile": "13800138000",
            "follow_user_display_name": "ai_crm_next",
            "current_tag_name": signup_status or "post_legacy_baseline",
            "external_userid": "wx_ext_001",
            "updated_at": _now(),
        }
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["route_owner", "fallback_used", "real_external_call_executed", "export_generated"])
    writer.writerow(["ai_crm_next", "false", "false", "local_only"])
    writer.writerow([])
    writer.writerow(["客户昵称", "手机号", "跟进人", "当前状态标签", "external_userid", "更新时间"])
    for row in rows:
        writer.writerow(
            [
                row["customer_name"],
                row["mobile"],
                row["follow_user_display_name"],
                row["current_tag_name"],
                row["external_userid"],
                row["updated_at"],
            ]
        )
    headers = dict(_CSV_HEADERS)
    headers["Content-Disposition"] = 'attachment; filename="class-user-management-post-legacy.csv"'
    return Response(buffer.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@router.api_route("/api/admin/cloud-orchestrator/audit", methods=["GET", "OPTIONS"])
async def cloud_orchestrator_audit(request: Request) -> JSONResponse:
    if request.method.upper() == "OPTIONS":
        return _options("next_cloud_orchestrator_audit")
    payload = _common_payload("next_cloud_orchestrator_audit")
    payload.update(
        {
            "items": [],
            "audit": [],
            "count": 0,
            "limit": int(request.query_params.get("limit") or 100),
            "cursor": _text(request.query_params.get("cursor")),
            "campaign_code": _text(request.query_params.get("campaign_code")),
            "trace_id": _text(request.query_params.get("trace_id")),
            "session_id": _text(request.query_params.get("session_id")),
            "degraded": False,
            "warnings": [],
        }
    )
    return _json(payload)


@router.api_route("/api/admin/cloud-orchestrator/observability", methods=["GET", "OPTIONS"])
async def cloud_orchestrator_observability(request: Request) -> JSONResponse:
    if request.method.upper() == "OPTIONS":
        return _options("next_cloud_orchestrator_observability")
    payload = _common_payload("next_cloud_orchestrator_observability")
    payload.update(
        {
            "health": {"status": "ok", "source": "local_contract"},
            "metrics": {},
            "recent_runs": [],
            "plan_funnel_7d": {},
            "audit_status_1d": {},
            "tool_stats_1d": [],
            "recent_errors": [],
            "degraded": False,
            "warnings": [],
        }
    )
    return _json(payload)


@router.api_route("/api/admin/wecom-customer-acquisition-links", methods=["GET", "POST", "OPTIONS"])
async def wecom_customer_acquisition_links(request: Request) -> JSONResponse:
    global _NEXT_ID
    source_status = "next_wecom_customer_acquisition_links" if request.method.upper() == "GET" else "next_command"
    if request.method.upper() == "OPTIONS":
        return _options(source_status)
    if request.method.upper() == "GET":
        status = _text(request.query_params.get("status"))
        links = [_link_view(row) for row in _WE_COM_LINKS if not status or _text(row.get("status")) == status]
        payload = _common_payload(source_status)
        payload.update(
            {
                "items": links,
                "links": links,
                "count": len(links),
                "adapter_mode": "real_blocked",
                "wecom_api_called": False,
                "degraded": False,
                "warnings": [],
            }
        )
        return _json(payload)

    body = await _payload(request)
    now = _now()
    link_id = _text(body.get("link_id")) or f"post_legacy_link_{_NEXT_ID}"
    link_name = _text(body.get("link_name")) or _text(body.get("name")) or link_id
    link_url = _text(body.get("link_url")) or "https://work.weixin.qq.com/ca/post-legacy-local"
    customer_channel = _customer_channel(link_id=link_id, name=link_name)
    row = {
        "id": _NEXT_ID,
        "link_id": link_id,
        "link_name": link_name,
        "name": link_name,
        "description": _text(body.get("description")),
        "link_url": link_url,
        "customer_channel": customer_channel,
        "final_url": _final_url(link_url, customer_channel),
        "program_id": int(body["program_id"]) if _text(body.get("program_id")).isdigit() else None,
        "workflow_id": int(body["workflow_id"]) if _text(body.get("workflow_id")).isdigit() else None,
        "initial_audience_code": _text(body.get("initial_audience_code")) or "pending_questionnaire",
        "status": "active",
        "adapter_mode": "real_blocked",
        "wecom_api_called": False,
        "real_external_call_executed": False,
        "created_at": now,
        "updated_at": now,
    }
    _WE_COM_LINKS.insert(0, row)
    _NEXT_ID += 1
    payload = _common_payload(source_status)
    payload.update(
        {
            "command_id": f"cmd_wecom_ca_{uuid.uuid4().hex}",
            "command_name": "wecom_customer_acquisition_link.create.plan",
            "idempotency_key": _text(request.headers.get("Idempotency-Key")),
            "link": _link_view(row),
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "side_effect_plan": {
                "kind": "wecom_customer_acquisition_link_create",
                "status": "blocked",
                "reason": "post_legacy_safe_mode",
            },
        }
    )
    return _json(payload)


@router.api_route(
    "/api/admin/wecom-customer-acquisition-links/{link_id}",
    methods=["GET", "PATCH", "DELETE", "OPTIONS"],
)
async def wecom_customer_acquisition_link_detail(request: Request, link_id: str) -> JSONResponse:
    if request.method.upper() == "OPTIONS":
        return _options("next_wecom_customer_acquisition_links")
    row = _find_link(link_id)
    if not row:
        payload = _common_payload("next_wecom_customer_acquisition_links")
        payload.update({"ok": False, "error_code": "wecom_customer_acquisition_link_not_found", "link": {}})
        return _json(payload, status_code=404)
    if request.method.upper() == "GET":
        payload = _common_payload("next_wecom_customer_acquisition_links")
        payload.update({"link": _link_view(row), "adapter_mode": "real_blocked", "wecom_api_called": False})
        return _json(payload)
    if request.method.upper() == "DELETE":
        row["status"] = "disabled"
    elif request.method.upper() == "PATCH":
        body = await _payload(request)
        for key in ("link_name", "name", "description", "initial_audience_code"):
            if key in body:
                row[key] = _text(body.get(key))
        row["updated_at"] = _now()
    payload = _common_payload("next_command")
    payload.update(
        {
            "command_id": f"cmd_wecom_ca_{uuid.uuid4().hex}",
            "link": _link_view(row),
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "side_effect_plan": {"kind": "wecom_customer_acquisition_link_mutation", "status": "blocked"},
        }
    )
    return _json(payload)


@router.api_route(
    "/api/admin/wecom-customer-acquisition-links/{link_id}/{action}",
    methods=["POST", "OPTIONS"],
)
async def wecom_customer_acquisition_link_action(request: Request, link_id: str, action: str) -> JSONResponse:
    if request.method.upper() == "OPTIONS":
        return _options("next_command")
    normalized_action = _text(action)
    row = _find_link(link_id)
    if not row:
        payload = _common_payload("next_command")
        payload.update({"ok": False, "error_code": "wecom_customer_acquisition_link_not_found"})
        return _json(payload, status_code=404)
    if normalized_action not in {"enable", "disable", "sync"}:
        payload = _common_payload("next_command")
        payload.update(
            {
                "ok": False,
                "error_code": "wecom_customer_acquisition_action_deprecated",
                "replacement": "/api/admin/wecom-customer-acquisition-links/{link_id}",
            }
        )
        return _json(payload, status_code=410)
    if normalized_action == "enable":
        row["status"] = "active"
    elif normalized_action == "disable":
        row["status"] = "disabled"
    row["updated_at"] = _now()
    payload = _common_payload("next_command")
    payload.update(
        {
            "command_id": f"cmd_wecom_ca_{uuid.uuid4().hex}",
            "command_name": f"wecom_customer_acquisition_link.{normalized_action}.plan",
            "link": _link_view(row),
            "adapter_mode": "real_blocked",
            "wecom_api_called": False,
            "sync_executed": False,
            "side_effect_plan": {
                "kind": f"wecom_customer_acquisition_link_{normalized_action}",
                "status": "blocked",
                "reason": "real_wecom_api_blocked_by_default",
            },
        }
    )
    return _json(payload)
