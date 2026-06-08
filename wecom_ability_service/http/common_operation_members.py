from __future__ import annotations

from flask import jsonify, request

from ..domains.common_operation_members import search_operation_members_from_request_args


def api_operation_members():
    return jsonify(search_operation_members_from_request_args(request.args))


def register_routes(bp):
    bp.route("/api/admin/common/operation-members", methods=["GET"])(api_operation_members)
