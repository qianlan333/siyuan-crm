from __future__ import annotations

from io import BytesIO
import re

from flask import jsonify, request, send_file

from ..domains.automation_conversion.admission_service import (
    import_channel_contacts_to_program,
    list_admission_attempts,
    list_program_member_stage_history,
)
from ..domains.automation_conversion.channel_binding_service import (
    archive_program_channel_binding,
    bind_channels_to_program,
    ensure_legacy_program_channel_bindings,
    get_channel,
    get_program_channel_binding_member_stage_summary,
    list_channel_bindings,
    list_channel_contacts,
    list_channels,
    list_program_channel_bindings,
    save_channel_resource,
    update_program_channel_binding,
)
from ._routes_helpers import _operator_from_request
from .automation_conversion_compat import parent_patch
from .internal_auth import validate_admin_console_action_token as _validate_admin_console_action_token


def validate_admin_console_action_token():
    return parent_patch("validate_admin_console_action_token", _validate_admin_console_action_token)()


def _json_payload() -> dict:
    return dict(request.get_json(silent=True) or {})


def _token_error_response():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error, "reason": "admin_action_token_required"}), 400
    return None


def _download_filename(channel: dict) -> str:
    raw = str(channel.get("channel_code") or channel.get("id") or "channel").strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._") or "channel"
    return f"{safe}.png"


def _png_qrcode_bytes(value: str) -> bytes:
    import segno

    out = BytesIO()
    segno.make(str(value or ""), error="m").save(out, kind="png", scale=8, border=2)
    return out.getvalue()


def _welcome_material_type_filter(value: str) -> str:
    normalized = str(value or "all").strip().lower()
    return normalized if normalized in {"all", "miniprogram", "image", "pdf"} else "all"


def _list_channel_welcome_materials(*, material_type: str = "all", keyword: str = "") -> list[dict]:
    from ..domains import attachment_library, miniprogram_library

    material_type = _welcome_material_type_filter(material_type)
    keyword = str(keyword or "").strip().lower()
    items: list[dict] = []
    if material_type in {"all", "miniprogram"}:
        for item in miniprogram_library.list_miniprograms(enabled_only=True):
            title = str(item.get("title") or item.get("name") or "")
            haystack = " ".join(str(item.get(key) or "") for key in ("title", "name", "appid", "pagepath")).lower()
            if keyword and keyword not in haystack:
                continue
            items.append(
                {
                    "id": int(item.get("id") or 0),
                    "type": "miniprogram",
                    "name": title,
                    "title": title,
                    "description": str(item.get("pagepath") or item.get("appid") or ""),
                }
            )
    if material_type in {"all", "image", "pdf"}:
        attachments = attachment_library.list_attachments(enabled_only=True, limit=200, q=keyword or None)
        for item in attachments:
            mime = str(item.get("mime_type") or "").lower()
            is_pdf = mime == "application/pdf" or str(item.get("file_name") or "").lower().endswith(".pdf")
            is_image = mime.startswith("image/")
            if material_type == "pdf" and not is_pdf:
                continue
            if material_type == "image" and not is_image:
                continue
            if material_type == "all" and not (is_pdf or is_image):
                continue
            item_type = "image" if is_image else "pdf"
            name = str(item.get("name") or item.get("file_name") or "")
            items.append(
                {
                    "id": int(item.get("id") or 0),
                    "type": item_type,
                    "name": name,
                    "title": name,
                    "description": str(item.get("file_name") or item.get("mime_type") or ""),
                    "mime_type": str(item.get("mime_type") or ""),
                }
            )
    return items


def api_admin_channels():
    if request.method == "GET":
        ensure_legacy_program_channel_bindings()
        return jsonify(
            {
                "ok": True,
                "channels": list_channels(
                    status=str(request.args.get("status") or "").strip(),
                    limit=int(request.args.get("limit") or 100),
                    available_for_program_id=int(request.args.get("available_for_program_id") or 0) or None,
                ),
                "reason": "channels_listed",
            }
        )
    token_response = _token_error_response()
    if token_response:
        return token_response
    try:
        channel = save_channel_resource(_json_payload())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 400
    return jsonify({"ok": True, "channel": channel, "reason": "channel_created"}), 201


def api_admin_channel_detail(channel_id: int):
    if request.method == "GET":
        channel = get_channel(int(channel_id))
        if not channel:
            return jsonify({"ok": False, "error": "channel_not_found", "reason": "channel_not_found"}), 404
        return jsonify({"ok": True, "channel": channel, "reason": "channel_loaded"})
    token_response = _token_error_response()
    if token_response:
        return token_response
    try:
        channel = save_channel_resource(_json_payload(), channel_id=int(channel_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 400
    return jsonify({"ok": True, "channel": channel, "reason": "channel_updated"})


def api_admin_channel_contacts(channel_id: int):
    if not get_channel(int(channel_id)):
        return jsonify({"ok": False, "error": "channel_not_found", "reason": "channel_not_found"}), 404
    return jsonify(
        {
            "ok": True,
            "contacts": list_channel_contacts(int(channel_id), limit=int(request.args.get("limit") or 100)),
            "reason": "channel_contacts_listed",
        }
    )


def api_admin_channel_bindings(channel_id: int):
    if not get_channel(int(channel_id)):
        return jsonify({"ok": False, "error": "channel_not_found", "reason": "channel_not_found"}), 404
    ensure_legacy_program_channel_bindings(channel_id=int(channel_id))
    return jsonify({"ok": True, "bindings": list_channel_bindings(int(channel_id)), "reason": "channel_bindings_listed"})


def api_admin_channel_qrcode_download(channel_id: int):
    channel = get_channel(int(channel_id))
    if not channel:
        return jsonify({"ok": False, "error": "channel_not_found", "reason": "channel_not_found"}), 404
    if channel.get("carrier_type") == "link" or channel.get("channel_type") == "wecom_customer_acquisition":
        return jsonify(
            {
                "ok": False,
                "error": "link channel does not support qrcode download",
                "reason": "link_channel_does_not_support_qrcode_download",
            }
        ), 400
    qr_url = str(channel.get("qr_url") or "").strip()
    if not qr_url:
        return jsonify({"ok": False, "error": "qrcode_not_ready", "reason": "qrcode_not_ready"}), 404
    png = _png_qrcode_bytes(qr_url)
    return send_file(
        BytesIO(png),
        mimetype="image/png",
        as_attachment=True,
        download_name=_download_filename(channel),
        max_age=0,
    )


def api_admin_channel_share_link(channel_id: int):
    channel = get_channel(int(channel_id))
    if not channel:
        return jsonify({"ok": False, "error": "channel_not_found", "reason": "channel_not_found"}), 404
    if channel.get("carrier_type") != "link" and channel.get("channel_type") != "wecom_customer_acquisition":
        return jsonify({"ok": False, "error": "channel_is_not_link_carrier", "reason": "channel_is_not_link_carrier"}), 400
    share_url = str(channel.get("share_url") or channel.get("copy_text") or channel.get("final_url") or channel.get("link_url") or "").strip()
    return jsonify({"ok": True, "share_url": share_url, "copy_text": share_url, "reason": "share_link_loaded"})


def api_admin_channel_welcome_materials():
    return jsonify(
        {
            "ok": True,
            "materials": _list_channel_welcome_materials(
                material_type=str(request.args.get("type") or "all"),
                keyword=str(request.args.get("keyword") or request.args.get("q") or ""),
            ),
            "reason": "channel_welcome_materials_listed",
        }
    )


def api_admin_program_channel_bindings(program_id: int):
    if request.method == "GET":
        ensure_legacy_program_channel_bindings()
        return jsonify(
            {
                "ok": True,
                "bindings": list_program_channel_bindings(int(program_id)),
                "reason": "program_channel_bindings_listed",
            }
        )
    token_response = _token_error_response()
    if token_response:
        return token_response
    payload = _json_payload()
    channel_ids = payload.get("channel_ids") or payload.get("channel_id") or []
    if not isinstance(channel_ids, list):
        channel_ids = [channel_ids]
    try:
        result = bind_channels_to_program(
            int(program_id),
            [int(item) for item in channel_ids if str(item).strip()],
            payload,
            _operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_program_channel_binding_detail(program_id: int, binding_id: int):
    token_response = _token_error_response()
    if token_response:
        return token_response
    try:
        if request.method == "DELETE":
            result = archive_program_channel_binding(int(program_id), int(binding_id), _operator_from_request())
        else:
            result = update_program_channel_binding(
                int(program_id),
                int(binding_id),
                _json_payload(),
                _operator_from_request(),
            )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_program_channel_binding_member_stage_summary(program_id: int, binding_id: int):
    try:
        result = get_program_channel_binding_member_stage_summary(
            int(program_id),
            int(binding_id),
            limit=int(request.args.get("limit") or 200),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_program_channel_bindings_import(program_id: int):
    token_response = _token_error_response()
    if token_response:
        return token_response
    payload = _json_payload()
    try:
        result = import_channel_contacts_to_program(
            int(program_id),
            channel_id=int(payload.get("channel_id") or 0),
            operator_id=_operator_from_request(),
            use_historical_channel_entered_at=bool(payload.get("use_historical_channel_entered_at")),
            dry_run=bool(payload.get("dry_run")),
            limit=int(payload.get("limit") or 500),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc), "reason": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_program_admission_attempts(program_id: int):
    return jsonify(
        {
            "ok": True,
            "admission_attempts": list_admission_attempts(
                int(program_id),
                limit=int(request.args.get("limit") or 100),
            ),
            "reason": "admission_attempts_listed",
        }
    )


def api_admin_program_member_stage_history(program_id: int, program_member_id: int):
    return jsonify(
        {
            "ok": True,
            "stage_history": list_program_member_stage_history(
                int(program_member_id),
                program_id=int(program_id),
            ),
            "reason": "program_member_stage_history_listed",
        }
    )
