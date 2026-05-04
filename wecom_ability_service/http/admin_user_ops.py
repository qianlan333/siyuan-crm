from __future__ import annotations

import base64
import json

from flask import Response, jsonify, request

from ..application.user_ops import (
    BackfillOwnerClassTermsCommand,
    BackfillOwnerClassTermsCommandDTO,
    ExportUserOpsPoolQuery,
    ExportUserOpsPoolQueryDTO,
    GetUserOpsOverviewQuery,
    GetUserOpsOverviewQueryDTO,
    ImportActivationStatusCommand,
    ImportActivationStatusCommandDTO,
    ImportMobileClassTermCommand,
    ImportMobileClassTermCommandDTO,
    LeadPoolFiltersDTO,
    ListLeadPoolQuery,
    ListLeadPoolQueryDTO,
    ListUserOpsHistoryQuery,
    ListUserOpsHistoryQueryDTO,
    RunDueUserOpsDeferredJobsCommand,
    RunDueUserOpsDeferredJobsCommandDTO,
)
from ..domains.routing_config import DEFAULT_SALES_ROUTE_OWNER_USERID
from ..domains.tasks.private_message import MAX_PRIVATE_MESSAGE_IMAGES
from ..domains.user_ops.page_service import (
    execute_user_ops_batch_send,
    get_user_ops_send_record_detail,
    list_user_ops_send_records,
    preview_user_ops_batch_send,
    refresh_user_ops_send_record_status,
    set_user_ops_do_not_disturb,
)
from ..wecom_client import WeComClientError
from .admin_console import render_admin_user_ops_shell
from .common import _build_excel_xml, _coerce_request_bool, _wecom_error_response

MAX_ONE_TIME_BATCH_SEND_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_ONE_TIME_BATCH_SEND_IMAGE_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _detect_one_time_batch_send_image_type(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if file_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "webp"
    return ""


def _page_filters_from_request_args() -> dict[str, str]:
    return {
        "wecom_status": request.args.get("wecom_status", "").strip(),
        "mobile_binding_status": request.args.get("mobile_binding_status", "").strip(),
        "activation_bucket": request.args.get("activation_bucket", "").strip(),
        "class_term_no": request.args.get("class_term_no", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
        "mobile": request.args.get("mobile", "").strip(),
        "owner_userid": request.args.get("owner_userid", "").strip(),
        "is_wecom_added": request.args.get("is_wecom_added", "").strip(),
        "is_mobile_bound": request.args.get("is_mobile_bound", "").strip(),
        "huangxiaocan_activation_state": request.args.get("huangxiaocan_activation_state", "").strip(),
        "query": request.args.get("query", "").strip(),
    }


def _lead_pool_filters_dto_from_request_args() -> LeadPoolFiltersDTO:
    return LeadPoolFiltersDTO(**_page_filters_from_request_args())


def _parse_json_form_field(field_name: str, default):
    raw = str(request.form.get(field_name) or "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be valid json") from exc


def _normalize_one_time_batch_send_images():
    files = [item for item in list(request.files.getlist("images") or []) if getattr(item, "filename", "")]
    if len(files) > MAX_PRIVATE_MESSAGE_IMAGES:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")

    images = []
    for index, file_storage in enumerate(files, start=1):
        file_name = str(getattr(file_storage, "filename", "") or f"image-{index}.png").strip() or f"image-{index}.png"
        mime_type = str(getattr(file_storage, "mimetype", "") or "").strip().lower()
        if not mime_type.startswith("image/"):
            raise ValueError("only image files are allowed")
        file_bytes = file_storage.read()
        if len(file_bytes) > MAX_ONE_TIME_BATCH_SEND_IMAGE_SIZE_BYTES:
            raise ValueError("image file is too large (max 5MB)")
        detected_image_type = _detect_one_time_batch_send_image_type(file_bytes)
        detected_type = ALLOWED_ONE_TIME_BATCH_SEND_IMAGE_TYPES.get(detected_image_type, "")
        if not detected_type:
            raise ValueError("only image files are allowed")
        images.append(
            {
                "file_name": file_name,
                "content_type": detected_type,
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )
    return images


def _batch_send_payload_from_request() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}

    payload = {
        "selection_mode": str(request.form.get("selection_mode") or "").strip(),
        "content": str(request.form.get("content") or "").strip(),
        "include_do_not_disturb": _coerce_request_bool(request.form.get("include_do_not_disturb"), default=False),
        "confirm": _coerce_request_bool(request.form.get("confirm"), default=False),
        "operator": str(request.form.get("operator") or "").strip(),
        "filters": _parse_json_form_field("filters_json", {}),
        "selected_ids": _parse_json_form_field("selected_ids_json", []),
        "excluded_ids": _parse_json_form_field("excluded_ids_json", []),
    }
    images = _normalize_one_time_batch_send_images()
    if images:
        payload["images"] = images
    return payload


def admin_user_ops_overview():
    payload = GetUserOpsOverviewQuery()(
        GetUserOpsOverviewQueryDTO(filters=_lead_pool_filters_dto_from_request_args())
    )
    return jsonify({"ok": True, **payload})


def admin_user_ops_list():
    payload = ListLeadPoolQuery()(
        ListLeadPoolQueryDTO(filters=_lead_pool_filters_dto_from_request_args())
    )
    return jsonify({"ok": True, **payload})


def admin_user_ops_history():
    try:
        limit = int(request.args.get("limit", "100").strip() or "100")
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = ListUserOpsHistoryQuery()(ListUserOpsHistoryQueryDTO(limit=limit))
    return jsonify({"ok": True, **payload})


def admin_user_ops_reload():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy user-ops reload is no longer part of admin V2; use internal maintenance helpers only",
            }
        ),
        410,
    )


def admin_user_ops_import_experience_leads():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy experience-leads import is no longer exposed by admin V2",
            }
        ),
        410,
    )


def admin_user_ops_import_mobile_class_terms():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = ImportMobileClassTermCommand()(
                ImportMobileClassTermCommandDTO(
                    file_name=uploaded_file.filename,
                    file_bytes=uploaded_file.read(),
                )
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload)

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        return jsonify({"ok": False, "error": "file or pasted_text is required"}), 400
    try:
        payload = ImportMobileClassTermCommand()(
            ImportMobileClassTermCommandDTO(pasted_text=pasted_text)
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def admin_user_ops_import_activation_status():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = ImportActivationStatusCommand()(
                ImportActivationStatusCommandDTO(
                    file_name=uploaded_file.filename,
                    file_bytes=uploaded_file.read(),
                )
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload)

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        return jsonify({"ok": False, "error": "file or pasted_text is required"}), 400
    try:
        payload = ImportActivationStatusCommand()(
            ImportActivationStatusCommandDTO(pasted_text=pasted_text)
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def admin_user_ops_backfill_class_term():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy class-term backfill is no longer exposed by admin V2",
            }
        ),
        410,
    )


def internal_user_ops_backfill_owner_class_terms():
    payload_json = request.get_json(silent=True) or {}
    owner_userid = str(payload_json.get("owner_userid") or DEFAULT_SALES_ROUTE_OWNER_USERID).strip()
    class_term_min_value = payload_json.get("class_term_min", 1)
    class_term_max_value = payload_json.get("class_term_max", 5)
    dry_run = _coerce_request_bool(payload_json.get("dry_run", True), default=True)
    try:
        class_term_min = int(class_term_min_value)
        class_term_max = int(class_term_max_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "class_term_min and class_term_max must be integers"}), 400
    try:
        payload = BackfillOwnerClassTermsCommand()(
            BackfillOwnerClassTermsCommandDTO(
                owner_userid=owner_userid,
                class_term_min=class_term_min,
                class_term_max=class_term_max,
                dry_run=dry_run,
                operator=str(payload_json.get("operator") or "").strip(),
                entry_source=str(payload_json.get("entry_source") or "").strip(),
            )
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify(payload)


def admin_user_ops_run_deferred_jobs():
    payload_json = request.get_json(silent=True) or {}
    limit_value = payload_json.get("limit", 20)
    try:
        limit = int(limit_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = RunDueUserOpsDeferredJobsCommand()(RunDueUserOpsDeferredJobsCommandDTO(limit=limit))
    return jsonify(payload)


def admin_user_ops_export():
    export_payload = ExportUserOpsPoolQuery()(
        ExportUserOpsPoolQueryDTO(filters=_lead_pool_filters_dto_from_request_args())
    )
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename={export_payload['filename']}"},
    )


def admin_user_ops_do_not_disturb():
    payload_json = request.get_json(silent=True) or {}
    try:
        payload = set_user_ops_do_not_disturb(payload_json)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def admin_user_ops_batch_send_preview():
    try:
        payload_json = _batch_send_payload_from_request()
        payload = preview_user_ops_batch_send(payload_json)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def admin_user_ops_batch_send_execute():
    try:
        payload_json = _batch_send_payload_from_request()
        payload = execute_user_ops_batch_send(payload_json)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_records():
    try:
        limit = int(request.args.get("limit", "20").strip() or "20")
        offset = int(request.args.get("offset", "0").strip() or "0")
    except ValueError:
        return jsonify({"ok": False, "error": "limit and offset must be integers"}), 400
    payload = list_user_ops_send_records(limit=limit, offset=offset)
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_record_detail(record_id: int):
    try:
        payload = get_user_ops_send_record_detail(record_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_record_refresh(record_id: int):
    try:
        payload = refresh_user_ops_send_record_status(record_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def admin_user_ops_ui():
    return render_admin_user_ops_shell()



def register_routes(bp):
    bp.route('/api/admin/user-ops/overview', methods=['GET'])(admin_user_ops_overview)
    bp.route('/api/admin/user-ops/list', methods=['GET'])(admin_user_ops_list)
    bp.route('/api/admin/user-ops/history', methods=['GET'])(admin_user_ops_history)
    bp.route('/api/admin/user-ops/reload', methods=['POST'])(admin_user_ops_reload)
    bp.route('/api/admin/user-ops/import-experience-leads', methods=['POST'])(admin_user_ops_import_experience_leads)
    bp.route('/api/admin/user-ops/import-mobile-class-terms', methods=['POST'])(admin_user_ops_import_mobile_class_terms)
    bp.route('/api/admin/user-ops/import-activation-status', methods=['POST'])(admin_user_ops_import_activation_status)
    bp.route('/api/admin/user-ops/backfill-class-term', methods=['POST'])(admin_user_ops_backfill_class_term)
    bp.route('/api/internal/user-ops/lead-pool/backfill-owner-class-terms', methods=['POST'])(internal_user_ops_backfill_owner_class_terms)
    bp.route('/api/admin/user-ops/run-deferred-jobs', methods=['POST'])(admin_user_ops_run_deferred_jobs)
    bp.route('/api/admin/user-ops/export', methods=['GET'])(admin_user_ops_export)
    bp.route('/api/admin/user-ops/do-not-disturb', methods=['POST'])(admin_user_ops_do_not_disturb)
    bp.route('/api/admin/user-ops/batch-send/preview', methods=['POST'])(admin_user_ops_batch_send_preview)
    bp.route('/api/admin/user-ops/batch-send/execute', methods=['POST'])(admin_user_ops_batch_send_execute)
    bp.route('/api/admin/user-ops/send-records', methods=['GET'])(admin_user_ops_send_records)
    bp.route('/api/admin/user-ops/send-records/<int:record_id>', methods=['GET'])(admin_user_ops_send_record_detail)
    bp.route('/api/admin/user-ops/send-records/<int:record_id>/refresh', methods=['POST'])(admin_user_ops_send_record_refresh)
    bp.route('/admin/user-ops/ui', methods=['GET'])(admin_user_ops_ui)
