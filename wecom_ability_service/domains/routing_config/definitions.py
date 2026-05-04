from __future__ import annotations

DEFAULT_SALES_ROUTE_OWNER_USERID = "ZhaoYanFang"
DEFAULT_DELIVERY_ROUTE_OWNER_USERID = "QianLan"

ROUTING_REASON_OWNER_ROLE_MISSING = "owner_role_missing"
ROUTING_REASON_OWNER_ROLE_UNKNOWN = "owner_role_unknown"
ROUTING_REASON_SIGNUP_STATUS_UNKNOWN = "signup_status_unknown"

ROUTING_RULES = {
    "pre_signup": {
        "route_owner_userid": DEFAULT_SALES_ROUTE_OWNER_USERID,
        "route_owner_role": "sales",
        "routing_target": "sales_handle",
    },
    "signed_999": {
        "route_owner_userid": DEFAULT_SALES_ROUTE_OWNER_USERID,
        "route_owner_role": "sales",
        "routing_target": "sales_handle",
    },
    "signed_3999": {
        "route_owner_userid": DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
        "when_owner_role_sales": "delivery_redirect",
        "when_owner_role_delivery": "delivery_handle",
        "fallback": "manual_review",
    },
    "unknown": {"routing_target": "manual_review"},
    "owner_role_missing": {"routing_target": "manual_review"},
}

OWNER_CLASS_TERM_BACKFILL_ENTRY_SOURCE_OVERRIDES = {
    DEFAULT_SALES_ROUTE_OWNER_USERID: "zhaoyanfang_owner_backfill_20260329",
}
