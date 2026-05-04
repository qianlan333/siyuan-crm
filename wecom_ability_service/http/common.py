from __future__ import annotations

import logging
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape

from flask import current_app, jsonify, redirect, request, url_for

from ..infra.error_codes import CRMError, ERROR_REGISTRY
from ..infra.wecom_runtime import ContactWeComRuntimeClient, get_contact_runtime_client
from ..wecom_client import WeComClientError
callback_logger = logging.getLogger("callback")
archive_logger = logging.getLogger("archive_sync")
contacts_logger = logging.getLogger("contacts_sync")
wecom_logger = logging.getLogger("wecom_api")
APP_STARTED_AT = datetime.utcnow()
APP_STARTED_AT_TEXT = APP_STARTED_AT.replace(microsecond=0).isoformat() + "Z"


def _log_wecom_client_error(
    exc: WeComClientError,
    *,
    owner_userid: str = "",
    external_userid: str = "",
    chat_id: str = "",
    stage: str = "",
) -> None:
    errcode = (exc.payload or {}).get("errcode")
    errmsg = (exc.payload or {}).get("errmsg")
    wecom_logger.error(
        "stage=%s errcode=%s errmsg=%s owner_userid=%s external_userid=%s chat_id=%s",
        stage or exc.stage or "",
        errcode,
        errmsg or str(exc),
        owner_userid,
        external_userid,
        chat_id,
    )


def error_response(
    code: str,
    *,
    message: str = "",
    detail: str = "",
    http_status: int = 500,
    extra: dict | None = None,
):
    """Standardized JSON error envelope for HTTP controllers.

    Replaces the long tail of ``except Exception: return jsonify({...}), 500``
    blocks scattered across the http/ layer. Format is stable so the admin
    UI / sidebar can render error codes + ``troubleshoot`` text consistently:

        {
            "ok": false,
            "error": {
                "code": "E1003",
                "message": "...",
                "category": "...",
                "retryable": true,
                "detail": "...",     # optional
                "troubleshoot": "..."  # optional, from ERROR_REGISTRY
            }
        }
    """
    info = ERROR_REGISTRY.get(code, {})
    body = {
        "ok": False,
        "error": {
            "code": code,
            "message": message or info.get("message", code),
            "category": info.get("category", "unknown"),
            "retryable": bool(info.get("retryable", False)),
        },
    }
    if detail:
        body["error"]["detail"] = detail
    if info.get("troubleshoot"):
        body["error"]["troubleshoot"] = info["troubleshoot"]
    if extra:
        body["error"].update(extra)
    return jsonify(body), int(http_status)


def crm_error_response(exc: CRMError, *, http_status: int = 500):
    """Render a ``CRMError`` raised by the domain layer into ``error_response``."""
    return error_response(
        exc.code,
        message=exc.message,
        detail=exc.detail or "",
        http_status=http_status,
    )


def _wecom_error_response(exc: WeComClientError):
    payload_json = request.get_json(silent=True) or {}
    owner_userid = payload_json.get("owner_userid") or payload_json.get("userid") or request.args.get("owner_userid", "")
    external_userid = payload_json.get("external_userid") or request.args.get("external_userid", "")
    chat_id = payload_json.get("chat_id") or payload_json.get("ChatId") or request.args.get("chat_id", "")
    _log_wecom_client_error(
        exc,
        owner_userid=owner_userid,
        external_userid=external_userid,
        chat_id=chat_id,
    )
    payload = {"ok": False, "error": str(exc)}
    if exc.error_code:
        payload["error_code"] = exc.error_code
    if exc.category:
        payload["error_category"] = exc.category
    if exc.stage:
        payload["error_stage"] = exc.stage
    if exc.payload:
        payload["wecom_payload"] = exc.payload
    return jsonify(payload), 502


def _default_owner_userid() -> str:
    return current_app.config["WECOM_DEFAULT_OWNER_USERID"]


def _corp_id() -> str:
    return current_app.config["WECOM_CORP_ID"]


def _contact_sync_batch_size() -> int:
    return int(current_app.config.get("WECOM_SYNC_BATCH_SIZE", 100))


def _contact_sync_retry_limit() -> int:
    return int(current_app.config.get("WECOM_SYNC_RETRY_LIMIT", 3))


def _contact_client() -> ContactWeComRuntimeClient:
    return get_contact_runtime_client()


def _coerce_request_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _build_excel_xml(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:o="urn:schemas-microsoft-com:office:office"',
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
        '<Worksheet ss:Name="Questionnaire">',
        "<Table>",
    ]

    def _render_row(values: list[str]) -> str:
        cells = "".join(
            f'<Cell><Data ss:Type="String">{xml_escape(str(value or ""))}</Data></Cell>'
            for value in values
        )
        return f"<Row>{cells}</Row>"

    lines.append(_render_row(headers))
    lines.extend(_render_row(row) for row in rows)
    lines.extend(["</Table>", "</Worksheet>", "</Workbook>"])
    return "\n".join(lines).encode("utf-8")


def _deprecated_admin_redirect(endpoint: str, *, replacement: str = "", **values):
    location = replacement or url_for(endpoint, **values)
    response = redirect(location, code=302)
    response.headers["X-Admin-Deprecated"] = "true"
    response.headers["X-Admin-Replacement"] = location
    response.headers["Cache-Control"] = "no-store"
    return response
