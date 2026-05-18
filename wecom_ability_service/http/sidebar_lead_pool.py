from __future__ import annotations

from flask import jsonify, request

from ..application.user_ops.commands import (
    UpsertSidebarLeadPoolClassTermCommand,
    UpsertSidebarLeadPoolClassTermCommandDTO,
)
from ..application.user_ops.queries import (
    GetSidebarLeadPoolStatusQuery,
    GetSidebarLeadPoolStatusQueryDTO,
)
from ..wecom_client import WeComClientError
from .common import _wecom_error_response


def _get_sidebar_lead_pool_status_payload(external_userid: str, owner_userid: str = "") -> dict[str, object]:
    return GetSidebarLeadPoolStatusQuery()(
        GetSidebarLeadPoolStatusQueryDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
        )
    )


def _upsert_sidebar_lead_pool_class_term_payload(
    *,
    external_userid: str,
    owner_userid: str,
    class_term_no: int,
    operator: str,
) -> dict[str, object]:
    return UpsertSidebarLeadPoolClassTermCommand()(
        UpsertSidebarLeadPoolClassTermCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            class_term_no=int(class_term_no),
            operator=str(operator or "").strip(),
        )
    )


def sidebar_lead_pool_status():
    external_userid = request.args.get("external_userid", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    try:
        payload = _get_sidebar_lead_pool_status_payload(external_userid=external_userid, owner_userid=owner_userid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def sidebar_lead_pool_upsert_class_term():
    payload = request.get_json(silent=True) or {}
    try:
        result = _upsert_sidebar_lead_pool_class_term_payload(
            external_userid=str(payload.get("external_userid") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            class_term_no=int(payload.get("class_term_no")),
            operator=str(payload.get("operator") or "").strip(),
        )
        status_payload = _get_sidebar_lead_pool_status_payload(
            external_userid=str(payload.get("external_userid") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **status_payload, "upsert": result})
