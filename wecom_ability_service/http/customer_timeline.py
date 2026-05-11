from __future__ import annotations

from flask import jsonify, request

from ..application.customer_read_model import CustomerTimelineQueryDTO, GetCustomerTimelineQuery
from ..customer_timeline.routes import parse_timeline_filters


def customer_timeline_detail(external_userid: str):
    try:
        filters = parse_timeline_filters(request.args)
        timeline = GetCustomerTimelineQuery()(
            CustomerTimelineQueryDTO(
                external_userid=external_userid,
                event_type=str(filters.get("event_type", "") or ""),
                limit=filters.get("limit", 50),
                offset=filters.get("offset", 0),
            )
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not timeline:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "timeline": timeline})



def register_routes(bp):
    bp.route('/api/customers/<external_userid>/timeline', methods=['GET'])(customer_timeline_detail)
