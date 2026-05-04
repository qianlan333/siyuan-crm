from __future__ import annotations

from flask import jsonify, request

from ..domains.tags.service import create_wecom_tag, list_wecom_tags, mark_customer_tags, unmark_customer_tags
from ..wecom_client import WeComClientError
from .common import _wecom_error_response


def list_tags():
    payload = {
        "tag_id": request.args.getlist("tag_id"),
        "group_id": request.args.getlist("group_id"),
    }
    payload = {key: value for key, value in payload.items() if value}
    try:
        result = list_wecom_tags(payload)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def create_tag():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_wecom_tag(payload)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def mark_tag():
    payload = request.get_json(silent=True) or {}
    userid = payload.get("userid")
    external_userid = payload.get("external_userid")
    add_tag = payload.get("add_tag") or []

    if not userid or not external_userid or not add_tag:
        return jsonify({"ok": False, "error": "userid, external_userid and add_tag are required"}), 400

    try:
        result = mark_customer_tags(payload)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def unmark_tag():
    payload = request.get_json(silent=True) or {}
    userid = payload.get("userid")
    external_userid = payload.get("external_userid")
    remove_tag = payload.get("remove_tag") or []

    if not userid or not external_userid or not remove_tag:
        return jsonify({"ok": False, "error": "userid, external_userid and remove_tag are required"}), 400

    try:
        result = unmark_customer_tags(payload)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)



def register_routes(bp):
    bp.route('/api/tags', methods=['GET'])(list_tags)
    bp.route('/api/tags', methods=['POST'])(create_tag)
    bp.route('/api/tags/mark', methods=['POST'])(mark_tag)
    bp.route('/api/tags/unmark', methods=['POST'])(unmark_tag)
