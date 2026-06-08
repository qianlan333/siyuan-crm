from wecom_ability_service.application.integration_gateway import mcp_dispatch


def test_sender_argument_prefers_userid_and_normalizes_lists():
    assert mcp_dispatch._sender_argument({"userid": [" sales_01 ", "", "sales_02"], "sender": "ignored"}) == [
        "sales_01",
        "sales_02",
    ]


def test_sender_argument_accepts_sender_alias():
    assert mcp_dispatch._sender_argument({"sender": (" sales_01 ", "sales_01", "sales_02")}) == [
        "sales_01",
        "sales_02",
    ]


def test_resolve_sender_userids_uses_explicit_sender_list_before_owner_fallback():
    customers = [{"customer": {"owner_userid": "owner_01"}}]

    assert mcp_dispatch._resolve_sender_userids(customers, [" sales_a ", "sales_b"]) == ["sales_a", "sales_b"]


def test_masked_mobile_customer_ref_helpers():
    assert mcp_dispatch._normalize_customer_ref("176xxxx5555") == "176xxxx5555"
    assert mcp_dispatch._normalize_customer_ref("176****5555") == "176****5555"
    assert mcp_dispatch._normalize_customer_ref("+86 176****5555") == "176****5555"
    assert mcp_dispatch._masked_mobile_parts("176xxxx5555") == ("176", "5555")
    assert mcp_dispatch._masked_mobile_parts("176****5555") == ("176", "5555")
    assert mcp_dispatch._masked_mobile_parts("17612345555") is None
