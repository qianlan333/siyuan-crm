from __future__ import annotations

from flask import jsonify, request

from ..domains.contacts.service import (
    list_contacts as list_contacts_from_store,
    sync_contact_from_wecom,
    sync_contacts_for_owner_from_wecom,
    update_contact_description_from_wecom,
)
from ..application.identity_contact._legacy_delegate import (
    _get_contact_by_external_userid as get_contact_by_external_userid,
)
from ..wecom_client import WeComClientError
from .common import _default_owner_userid, _wecom_error_response
from .sync_jobs import run_contacts_sync, run_external_contact_identity_sync
from .sync_support import _normalize_contact_descriptions as _normalize_contact_descriptions_sync


def list_contacts():
    owner_userid = request.args.get("owner_userid", "").strip() or _default_owner_userid()
    sync = request.args.get("sync", "1").strip().lower() not in {"0", "false", "no"}
    try:
        if sync:
            sync_contacts_for_owner_from_wecom(
                owner_userid,
                default_owner_userid=_default_owner_userid(),
            )
        contacts = list_contacts_from_store(owner_userid)
        return jsonify({"ok": True, "contacts": contacts})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def get_contact(external_userid: str):
    owner_userid = request.args.get("owner_userid", "").strip()
    sync = request.args.get("sync", "1").strip().lower() not in {"0", "false", "no"}
    try:
        if sync:
            local_contact = get_contact_by_external_userid(external_userid)
            resolved_owner = owner_userid or (local_contact.get("owner_userid") if local_contact else "") or _default_owner_userid()
            sync_contact_from_wecom(
                external_userid,
                owner_userid=resolved_owner,
                default_owner_userid=_default_owner_userid(),
            )
        contact = get_contact_by_external_userid(external_userid)
        if not contact:
            return jsonify({"ok": False, "error": "contact not found"}), 404
        return jsonify({"ok": True, "contact": contact})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def update_contact_description():
    payload = request.get_json(silent=True) or {}
    external_userid = (payload.get("external_userid") or "").strip()
    description = payload.get("description")
    userid = (payload.get("userid") or _default_owner_userid()).strip()
    if not external_userid or description is None:
        return jsonify({"ok": False, "error": "external_userid and description are required"}), 400
    try:
        result = update_contact_description_from_wecom(
            external_userid=external_userid,
            description=description,
            userid=userid,
        )
        contact = get_contact_by_external_userid(external_userid)
        return jsonify({"ok": True, "result": result, "contact": contact})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def full_sync_contacts():
    try:
        result = run_contacts_sync(only_new=False)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def sync_new_contacts():
    try:
        result = run_contacts_sync(only_new=True)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)



def normalize_contact_descriptions():
    try:
        result = _normalize_contact_descriptions_sync()
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def full_sync_external_contact_identity():
    try:
        result = run_external_contact_identity_sync(only_new=False)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)



def register_routes(bp):
    bp.route('/api/contacts', methods=['GET'])(list_contacts)
    bp.route('/api/contacts/<external_userid>', methods=['GET'])(get_contact)
    bp.route('/api/contacts/description', methods=['POST'])(update_contact_description)
    bp.route('/api/contacts/full-sync', methods=['POST'])(full_sync_contacts)
    bp.route('/api/contacts/sync-new', methods=['POST'])(sync_new_contacts)
    bp.route('/api/contacts/normalize-description', methods=['POST'])(normalize_contact_descriptions)
    bp.route('/internal/wecom/external-contact/full-sync', methods=['POST'])(full_sync_external_contact_identity)
