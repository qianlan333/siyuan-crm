from __future__ import annotations

from flask import current_app, jsonify, render_template, request

from ..application.identity_contact.commands import BindExternalContactIdentityCommand
from ..application.identity_contact.dto import BindExternalContactIdentityCommandDTO, GetContactBindingStatusQueryDTO
from ..application.identity_contact.queries import (
    GetContactBindingStatusQuery,
)
from ..infra.wecom_runtime import build_jsapi_payload
from ..application.class_user.dto import GetClassUserStatusCurrentQueryDTO
from ..application.class_user.queries import GetClassUserStatusCurrentQuery
from ..domains.identity import ContactBindingConflictError
from ..application.user_ops import ThirdPartyUserSyncError
from ..wecom_client import WeComClientError
from .admin_support import (
    _apply_signup_sidebar_tag,
    _configured_signup_tag_rules_payload,
    _normalize_jssdk_url,
    _sidebar_person_detail_url,
)
from .common import _corp_id, _wecom_error_response
from .sidebar_lead_pool import sidebar_lead_pool_status, sidebar_lead_pool_upsert_class_term
from .sidebar_marketing_support import get_customer_marketing_profile, sidebar_marketing_target_exists


def _get_class_user_status_current(external_userid: str):
    return GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid=str(external_userid or "").strip())
    )


def _get_contact_binding_status_payload(external_userid: str, owner_userid: str = "") -> dict[str, object]:
    return GetContactBindingStatusQuery()(
        GetContactBindingStatusQueryDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
        )
    )


def _bind_external_contact_identity_payload(
    *,
    external_userid: str,
    owner_userid: str,
    bind_by_userid: str,
    mobile: str,
    force_rebind: bool,
) -> dict[str, object]:
    return BindExternalContactIdentityCommand()(
        BindExternalContactIdentityCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            bind_by_userid=str(bind_by_userid or "").strip(),
            mobile=str(mobile or "").strip(),
            force_rebind=bool(force_rebind),
        )
    )


def sidebar_bind_mobile_page():
    return render_template(
        "sidebar_customer_workbench.html",
        debug_enabled=bool(current_app.config.get("DEBUG")),
    )


def sidebar_contact_binding_status():
    external_userid = request.args.get("external_userid", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    status = _get_contact_binding_status_payload(external_userid, owner_userid)
    status["ok"] = True
    status.setdefault("mobile", "")
    if sidebar_marketing_target_exists(external_userid):
        try:
            status["marketing_profile"] = get_customer_marketing_profile(external_userid)
        except Exception:
            status["marketing_profile"] = {}
    if status.get("is_bound"):
        status["detail_url"] = _sidebar_person_detail_url(status)
    return jsonify(status)


def sidebar_jssdk_config():
    raw_url = request.args.get("url", "")
    try:
        normalized_url = _normalize_jssdk_url(raw_url)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    try:
        payload = build_jsapi_payload(
            url=normalized_url,
            corp_id=_corp_id(),
            agent_id=str(current_app.config.get("WECOM_AGENT_ID", "") or ""),
        )
    except (ValueError, WeComClientError) as exc:
        if isinstance(exc, WeComClientError):
            return _wecom_error_response(exc)
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def sidebar_bind_mobile():
    payload = request.get_json(silent=True) or {}
    try:
        binding = _bind_external_contact_identity_payload(
            external_userid=str(payload.get("external_userid") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            bind_by_userid=str(payload.get("bind_by_userid") or "").strip(),
            mobile=str(payload.get("mobile") or "").strip(),
            force_rebind=bool(payload.get("force_rebind")),
        )
    except ContactBindingConflictError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except (ValueError, ThirdPartyUserSyncError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    binding["detail_url"] = _sidebar_person_detail_url(binding)
    return jsonify({"ok": True, "binding": binding})


def sidebar_signup_tag_status():
    external_userid = request.args.get("external_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    current_status = _get_class_user_status_current(external_userid) or {}
    configured = _configured_signup_tag_rules_payload()
    return jsonify(
        {
            "ok": True,
            "definitions": configured.get("definitions") or [],
            "initialized": bool(configured.get("initialized")),
            "missing_statuses": configured.get("missing_statuses") or [],
            "current_signup_status": str(current_status.get("signup_status") or "").strip(),
            "current_tag": str(current_status.get("signup_label_name") or "").strip(),
            "wecom_tag_sync_status": str(current_status.get("wecom_tag_sync_status") or "").strip(),
            "wecom_tag_sync_error": str(current_status.get("wecom_tag_sync_error") or "").strip(),
            "marketing_profile": get_customer_marketing_profile(external_userid),
        }
    )


def sidebar_signup_tag_mark():
    payload = request.get_json(silent=True) or {}
    try:
        result = _apply_signup_sidebar_tag(
            str(payload.get("external_userid") or "").strip(),
            str(payload.get("owner_userid") or "").strip(),
            str(payload.get("signup_status") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **result})


def register_routes(bp):
    bp.route('/sidebar/bind-mobile', methods=['GET'])(sidebar_bind_mobile_page)
    bp.route('/api/sidebar/contact-binding-status', methods=['GET'])(sidebar_contact_binding_status)
    bp.route('/api/sidebar/jssdk-config', methods=['GET'])(sidebar_jssdk_config)
    bp.route('/api/sidebar/bind-mobile', methods=['POST'])(sidebar_bind_mobile)
    bp.route('/api/sidebar/lead-pool/status', methods=['GET'])(sidebar_lead_pool_status)
    bp.route('/api/sidebar/lead-pool/upsert-class-term', methods=['POST'])(sidebar_lead_pool_upsert_class_term)
    bp.route('/api/sidebar/signup-tags/status', methods=['GET'])(sidebar_signup_tag_status)
    bp.route('/api/sidebar/signup-tags/mark', methods=['POST'])(sidebar_signup_tag_mark)
