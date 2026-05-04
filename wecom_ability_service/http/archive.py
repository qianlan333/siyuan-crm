from __future__ import annotations

from flask import current_app, jsonify, request

from ..domains.archive.service import (
    get_messages_by_user as _get_messages_by_user,
    get_recent_messages_by_user as _get_recent_messages_by_user,
    search_messages as _search_messages,
)
from ..domains.group_chats.repo import get_group_chat_map
from .sync_jobs import run_archive_health_check, run_manual_archive_sync


def archive_health():
    try:
        return jsonify({"ok": True, "adapter": run_archive_health_check()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


def archive_sync():
    payload = request.get_json(silent=True) or {}
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    owner_userid = payload.get("owner_userid") or current_app.config["WECOM_DEFAULT_OWNER_USERID"]
    cursor = payload.get("cursor", "")

    if not start_time or not end_time or not owner_userid:
        return jsonify({"ok": False, "error": "start_time, end_time and owner_userid are required"}), 400
    response_payload = run_manual_archive_sync(
        start_time=start_time,
        end_time=end_time,
        owner_userid=owner_userid,
        cursor=cursor,
    )
    status_code = 200 if response_payload.get("ok") else 502
    return jsonify(response_payload), status_code


def list_messages(external_userid: str):
    chat_type = request.args.get("chat_type", "").strip() or None
    try:
        messages = _get_messages_by_user(external_userid, chat_type, group_chat_map_loader=get_group_chat_map)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "messages": messages})


def list_recent_messages(external_userid: str):
    limit = request.args.get("limit", "20").strip() or "20"
    chat_type = request.args.get("chat_type", "").strip() or None
    try:
        messages = _get_recent_messages_by_user(external_userid, limit=int(limit), chat_type=chat_type, group_chat_map_loader=get_group_chat_map)
    except ValueError as exc:
        if "chat_type" in str(exc):
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    return jsonify({"ok": True, "messages": messages})


def query_messages():
    external_userid = request.args.get("external_userid", "").strip()
    keyword = request.args.get("keyword", "").strip()
    if not external_userid or not keyword:
        return jsonify({"ok": False, "error": "external_userid and keyword are required"}), 400
    return jsonify({"ok": True, "messages": _search_messages(external_userid, keyword, group_chat_map_loader=get_group_chat_map)})



def register_routes(bp):
    bp.route('/api/archive/health', methods=['GET'])(archive_health)
    bp.route('/api/archive/sync', methods=['POST'])(archive_sync)
    bp.route('/api/messages/<external_userid>', methods=['GET'])(list_messages)
    bp.route('/api/messages/<external_userid>/recent', methods=['GET'])(list_recent_messages)
    bp.route('/api/messages/search', methods=['GET'])(query_messages)
