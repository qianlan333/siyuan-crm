from __future__ import annotations

from conftest import make_client


LIST_ITEM_KEYS = [
    "external_userid",
    "customer_name",
    "owner_userid",
    "owner_display_name",
    "mobile",
    "is_bound",
    "binding_status",
    "tags",
    "class_user_status",
    "last_message_at",
    "last_touch_at",
    "updated_at",
]

DETAIL_KEYS = [
    "external_userid",
    "customer_name",
    "owner_userid",
    "owner_display_name",
    "remark",
    "description",
    "mobile",
    "is_bound",
    "binding_status",
    "follow_user_userids",
    "tags",
    "class_user_status",
    "last_message_at",
    "last_touch_at",
    "updated_at",
    "binding",
    "identity",
    "follow_users",
    "marketing_summary",
    "marketing_profile",
    "contact",
    "sidebar_context",
]


def test_customers_returns_old_contract_compatible_shape() -> None:
    payload = make_client().get("/api/customers").json()
    assert payload["ok"] is True
    for key in ["customers", "items", "count", "total", "limit", "offset", "filters"]:
        assert key in payload
    assert payload["customers"] == payload["items"]
    assert payload["total"] >= 3
    customer = payload["items"][0]
    for key in LIST_ITEM_KEYS:
        assert key in customer


def test_customers_and_items_are_aligned() -> None:
    payload = make_client().get("/api/customers").json()
    assert payload["customers"] == payload["items"]
    assert payload["count"] == len(payload["items"])


def test_customers_limit_offset_works() -> None:
    client = make_client()
    first = client.get("/api/customers?limit=1&offset=0").json()
    second = client.get("/api/customers?limit=1&offset=1").json()
    assert first["count"] == second["count"] == 1
    assert first["items"][0]["external_userid"] != second["items"][0]["external_userid"]
    assert first["total"] == second["total"]


def test_customers_owner_userid_filter_works() -> None:
    payload = make_client().get("/api/customers?owner_userid=ZhaoYanFang").json()
    assert payload["total"] >= 2
    assert {item["owner_userid"] for item in payload["items"]} == {"ZhaoYanFang"}


def test_customers_tag_filter_works() -> None:
    payload = make_client().get("/api/customers?tag=复访").json()
    assert payload["total"] == 1
    assert payload["items"][0]["external_userid"] == "wx_ext_004"


def test_customers_status_filter_works() -> None:
    payload = make_client().get("/api/customers?status=followup").json()
    assert payload["total"] == 1
    assert payload["items"][0]["class_user_status"]["current_status"] == "followup"


def test_customers_is_bound_filter_works() -> None:
    client = make_client()
    bound = client.get("/api/customers?is_bound=true").json()
    unbound = client.get("/api/customers?is_bound=false").json()
    assert all(item["is_bound"] is True for item in bound["items"])
    assert all(item["is_bound"] is False for item in unbound["items"])
    assert unbound["items"][0]["external_userid"] == "wx_ext_002"


def test_customers_mobile_filter_works() -> None:
    payload = make_client().get("/api/customers?mobile=13700137").json()
    assert payload["total"] == 1
    assert payload["items"][0]["external_userid"] == "wx_ext_004"


def test_customers_keyword_filter_works() -> None:
    payload = make_client().get("/api/customers?keyword=赵艳芳").json()
    assert payload["total"] >= 2
    assert {item["owner_userid"] for item in payload["items"]} == {"ZhaoYanFang"}


def test_customers_filters_echo_works() -> None:
    payload = make_client().get("/api/customers?owner_userid=ZhaoYanFang&tag=黄小璨&limit=2&offset=1").json()
    assert payload["filters"]["owner_userid"] == "ZhaoYanFang"
    assert payload["filters"]["tag"] == "黄小璨"
    assert payload["filters"]["limit"] == "2"
    assert payload["filters"]["offset"] == "1"


def test_customer_detail_returns_detail_shape() -> None:
    payload = make_client().get("/api/customers/wx_ext_001").json()
    assert payload["ok"] is True
    customer = payload["customer"]
    for key in DETAIL_KEYS:
        assert key in customer


def test_customer_detail_unknown_customer_returns_404() -> None:
    response = make_client().get("/api/customers/wx_missing")
    assert response.status_code == 404


def test_customer_detail_does_not_fallback_to_mobile() -> None:
    response = make_client().get("/api/customers/13900139000")
    assert response.status_code == 404


def test_customer_detail_nested_shapes_exist() -> None:
    customer = make_client().get("/api/customers/wx_ext_001").json()["customer"]
    assert customer["binding"]["binding_status"] == "bound"
    assert customer["identity"]["person_id"] == "person_001"
    assert customer["follow_users"][0]["userid"] == "ZhaoYanFang"
    assert customer["sidebar_context"]["can_open_sidebar"] is True


def test_customer_detail_marketing_shapes_exist() -> None:
    customer = make_client().get("/api/customers/wx_ext_001").json()["customer"]
    assert customer["marketing_summary"]["main_stage"] == "trial"
    assert customer["marketing_profile"]["recommended_action"]


def test_customer_timeline_returns_timeline_shape() -> None:
    payload = make_client().get("/api/customers/wx_ext_001/timeline?limit=20").json()
    assert payload["ok"] is True
    timeline = payload["timeline"]
    for key in ["external_userid", "items", "count", "limit", "offset", "filters", "total"]:
        assert key in timeline
    item = timeline["items"][0]
    for key in ["event_id", "event_type", "event_time", "title", "summary", "source_table", "source_id", "metadata"]:
        assert key in item


def test_customer_timeline_limit_offset_works() -> None:
    client = make_client()
    first = client.get("/api/customers/wx_ext_001/timeline?limit=1&offset=0").json()["timeline"]
    second = client.get("/api/customers/wx_ext_001/timeline?limit=1&offset=1").json()["timeline"]
    assert first["count"] == second["count"] == 1
    assert first["items"][0]["event_id"] != second["items"][0]["event_id"]
    assert first["total"] == second["total"] == 2


def test_customer_timeline_event_type_filter_works() -> None:
    timeline = make_client().get("/api/customers/wx_ext_001/timeline?event_type=tag").json()["timeline"]
    assert timeline["total"] == 1
    assert timeline["items"][0]["event_type"] == "tag"


def test_customer_timeline_unknown_customer_returns_404() -> None:
    response = make_client().get("/api/customers/wx_missing/timeline")
    assert response.status_code == 404


def test_recent_messages_returns_messages() -> None:
    payload = make_client().get("/api/messages/wx_ext_001/recent").json()
    assert payload["ok"] is True
    assert payload["messages"]


def test_recent_message_required_fields_complete() -> None:
    message = make_client().get("/api/messages/wx_ext_001/recent").json()["messages"][0]
    for key in ["msgid", "msgtype", "content", "send_time", "external_userid"]:
        assert key in message


def test_recent_messages_limit_works() -> None:
    payload = make_client().get("/api/messages/wx_ext_001/recent?limit=1").json()
    assert len(payload["messages"]) == 1


def test_recent_messages_unknown_customer_returns_404() -> None:
    response = make_client().get("/api/messages/wx_missing/recent")
    assert response.status_code == 404
