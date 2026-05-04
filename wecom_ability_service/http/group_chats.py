from __future__ import annotations

from flask import jsonify
from ..wecom_client import WeComClientError
from .common import _wecom_error_response
from .sync_jobs import run_group_chat_sync


def full_sync_group_chats():
    try:
        result = run_group_chat_sync(only_new=False)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def sync_new_group_chats():
    try:
        result = run_group_chat_sync(only_new=True)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)



def register_routes(bp):
    bp.route('/api/group-chats/full-sync', methods=['POST'])(full_sync_group_chats)
    bp.route('/api/group-chats/sync-new', methods=['POST'])(sync_new_group_chats)
