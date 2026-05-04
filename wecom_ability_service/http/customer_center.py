from __future__ import annotations

from flask import jsonify, request

from ..application.customer_read_model import (
    CustomerDetailQueryDTO,
    CustomerListQueryDTO,
    GetCustomerDetailQuery,
    ListCustomersQuery,
)
from ..customer_center.routes import parse_customer_filters


def customer_center_list():
    try:
        filters = parse_customer_filters(request.args)
        payload = ListCustomersQuery()(
            CustomerListQueryDTO(
                owner_userid=filters.get("owner_userid", ""),
                tag=filters.get("tag", ""),
                status=filters.get("status", ""),
                is_bound=filters.get("is_bound", ""),
                marketing_segment=filters.get("marketing_segment", ""),
                marketing_main_stage=filters.get("marketing_main_stage", ""),
                marketing_sub_stage=filters.get("marketing_sub_stage", ""),
                eligible_for_conversion=filters.get("eligible_for_conversion", ""),
                mobile=filters.get("mobile", ""),
                keyword=filters.get("keyword", ""),
                limit=filters.get("limit", ""),
                offset=filters.get("offset", ""),
            )
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def customer_center_detail(external_userid: str):
    customer = GetCustomerDetailQuery()(CustomerDetailQueryDTO(external_userid=external_userid))
    if not customer:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "customer": customer})



def register_routes(bp):
    bp.route('/api/customers', methods=['GET'])(customer_center_list)
    bp.route('/api/customers/<external_userid>', methods=['GET'])(customer_center_detail)
