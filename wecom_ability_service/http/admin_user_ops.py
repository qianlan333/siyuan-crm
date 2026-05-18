from __future__ import annotations

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
from ..wecom_client import WeComClientError
from .admin_console import render_admin_user_ops_shell
from .common import _build_excel_xml, _coerce_request_bool, _wecom_error_response

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


def _run_user_ops_text_or_file_import(command_cls, dto_cls):
    uploaded_file = request.files.get("file")
    if uploaded_file and uploaded_file.filename:
        return command_cls()(
            dto_cls(
                file_name=uploaded_file.filename,
                file_bytes=uploaded_file.read(),
            )
        )

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        raise ValueError("file or pasted_text is required")
    return command_cls()(dto_cls(pasted_text=pasted_text))


def admin_user_ops_import_mobile_class_terms():
    try:
        payload = _run_user_ops_text_or_file_import(
            ImportMobileClassTermCommand,
            ImportMobileClassTermCommandDTO,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def admin_user_ops_import_activation_status():
    try:
        payload = _run_user_ops_text_or_file_import(
            ImportActivationStatusCommand,
            ImportActivationStatusCommandDTO,
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
    bp.route('/admin/user-ops/ui', methods=['GET'])(admin_user_ops_ui)
