from __future__ import annotations

from flask import Response, current_app, jsonify, request

from ..application.questionnaire.commands import (
    CreateOrUpdateQuestionnaireCommand,
    DeleteQuestionnaireCommand,
    DisableQuestionnaireCommand,
)
from ..application.questionnaire.dto import (
    BuildQuestionnairePreflightQueryDTO,
    CreateOrUpdateQuestionnaireCommandDTO,
    DeleteQuestionnaireCommandDTO,
    DisableQuestionnaireCommandDTO,
    ExportQuestionnaireSubmissionsQueryDTO,
    GetLatestQuestionnaireSubmitDebugQueryDTO,
    GetQuestionnaireDetailQueryDTO,
)
from ..application.questionnaire.queries import (
    BuildQuestionnairePreflightQuery,
    ExportQuestionnaireSubmissionsQuery,
    GetLatestQuestionnaireSubmitDebugQuery,
    GetQuestionnaireDetailQuery,
    ListQuestionnairesQuery,
)
from .common import _build_excel_xml, _deprecated_admin_redirect
from .questionnaire_support import _attach_questionnaire_links


def admin_list_questionnaires():
    questionnaires = ListQuestionnairesQuery()()
    return jsonify({"ok": True, "questionnaires": [_attach_questionnaire_links(item) for item in questionnaires]})


def admin_questionnaires_preflight():
    return jsonify(
        BuildQuestionnairePreflightQuery()(
            BuildQuestionnairePreflightQueryDTO(
                config_snapshot=current_app.config,
            )
        )
    )



def admin_questionnaires_ui():
    return _deprecated_admin_redirect("api.admin_console_questionnaires")


def admin_create_questionnaire():
    payload = request.get_json(silent=True) or {}
    try:
        questionnaire = CreateOrUpdateQuestionnaireCommand()(
            CreateOrUpdateQuestionnaireCommandDTO(
                payload=dict(payload or {}),
            )
        )
        return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_get_questionnaire(questionnaire_id: int):
    questionnaire = GetQuestionnaireDetailQuery()(
        GetQuestionnaireDetailQueryDTO(questionnaire_id=int(questionnaire_id))
    )
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})


def admin_questionnaire_latest_submit_debug(questionnaire_id: int):
    result = GetLatestQuestionnaireSubmitDebugQuery()(
        GetLatestQuestionnaireSubmitDebugQueryDTO(questionnaire_id=int(questionnaire_id))
    )
    if not result:
        return jsonify({"ok": False, "error": "no_submission_found"})
    payload = {"ok": True}
    payload.update(result)
    return jsonify(payload)


def admin_update_questionnaire(questionnaire_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        questionnaire = CreateOrUpdateQuestionnaireCommand()(
            CreateOrUpdateQuestionnaireCommandDTO(
                questionnaire_id=int(questionnaire_id),
                payload=dict(payload or {}),
            )
        )
        if not questionnaire:
            return jsonify({"ok": False, "error": "questionnaire not found"}), 404
        return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_disable_questionnaire(questionnaire_id: int):
    payload = request.get_json(silent=True) or {}
    questionnaire = DisableQuestionnaireCommand()(
        DisableQuestionnaireCommandDTO(
            questionnaire_id=int(questionnaire_id),
            is_disabled=bool(payload.get("is_disabled", True)),
        )
    )
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})


def admin_delete_questionnaire(questionnaire_id: int):
    questionnaire = GetQuestionnaireDetailQuery()(
        GetQuestionnaireDetailQueryDTO(questionnaire_id=int(questionnaire_id))
    )
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    if not questionnaire.get("is_disabled"):
        return jsonify({"ok": False, "error": "请先停用问卷后再删除"}), 400
    deleted = DeleteQuestionnaireCommand()(
        DeleteQuestionnaireCommandDTO(questionnaire_id=int(questionnaire_id))
    )
    if not deleted:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "deleted": True})


def admin_export_questionnaire(questionnaire_id: int):
    try:
        export_payload = ExportQuestionnaireSubmissionsQuery()(
            ExportQuestionnaireSubmissionsQueryDTO(questionnaire_id=int(questionnaire_id))
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    response = Response(content, mimetype="application/vnd.ms-excel")
    response.headers["Content-Disposition"] = f'attachment; filename="{export_payload["filename"]}"'
    return response



def register_routes(bp):
    bp.route('/api/admin/questionnaires', methods=['POST'])(admin_create_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>', methods=['PUT'])(admin_update_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>/disable', methods=['POST'])(admin_disable_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>', methods=['DELETE'])(admin_delete_questionnaire)
