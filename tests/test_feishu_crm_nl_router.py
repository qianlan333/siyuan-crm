from __future__ import annotations

from openclaw_service.feishu.crm_nl_router import extract_external_userid, route_crm_text


def test_extract_external_userid_from_message() -> None:
    assert extract_external_userid("看看这个用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 什么情况") == "wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw"


def test_route_context_intent_calls_get_customer_context() -> None:
    captured: dict = {}

    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        captured["external_userid"] = external_userid
        captured["kwargs"] = kwargs
        return {
            "external_userid": external_userid,
            "customer": {
                "external_userid": external_userid,
                "name": "玄青",
                "status": "active",
                "tags": ["已报名3999"],
            },
            "recent_messages": [{"send_time": "2026-03-24 14:59:44", "content": "你好"}],
            "recent_timeline_events": [],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    text = route_crm_text(
        "查一下用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw",
        context_loader=fake_context_loader,
        tag_reader=lambda: [],
    )

    assert captured["external_userid"] == "wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw"
    assert captured["kwargs"] == {"recent_message_limit": 10, "timeline_limit": 10}
    assert "客户：玄青" in text
    assert "标签：已报名3999" in text


def test_route_add_tag_intent_resolves_tag_name_and_calls_update_customer_tags() -> None:
    captured: dict = {}

    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        return {
            "external_userid": external_userid,
            "customer": {
                "external_userid": external_userid,
                "name": "玄青",
                "owner_userid": "QianLan",
                "status": "active",
                "tags": [],
            },
            "recent_messages": [],
            "recent_timeline_events": [],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    def fake_tag_updater(external_userid: str, *, userid: str, add_tags=None, remove_tags=None) -> dict:
        captured["external_userid"] = external_userid
        captured["userid"] = userid
        captured["add_tags"] = add_tags
        captured["remove_tags"] = remove_tags
        return {"ok": True, "results": {"mark": {"ok": True, "response": {"ok": True}}}}

    text = route_crm_text(
        "给用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 打标签 高意向",
        context_loader=fake_context_loader,
        tag_updater=fake_tag_updater,
        tag_reader=lambda: [{"tag_id": "tag-001", "tag_name": "高意向", "group_id": "g1", "group_name": "业务标签"}],
    )

    assert captured == {
        "external_userid": "wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw",
        "userid": "QianLan",
        "add_tags": ["tag-001"],
        "remove_tags": [],
    }
    assert text == "已给用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 打上标签：高意向"


def test_route_remove_tag_intent_calls_update_customer_tags() -> None:
    captured: dict = {}

    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        return {
            "external_userid": external_userid,
            "customer": {
                "external_userid": external_userid,
                "name": "玄青",
                "owner_userid": "QianLan",
                "status": "active",
                "tags": ["高意向"],
            },
            "recent_messages": [],
            "recent_timeline_events": [],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    def fake_tag_updater(external_userid: str, *, userid: str, add_tags=None, remove_tags=None) -> dict:
        captured["external_userid"] = external_userid
        captured["userid"] = userid
        captured["add_tags"] = add_tags
        captured["remove_tags"] = remove_tags
        return {"ok": True, "results": {"unmark": {"ok": True, "response": {"ok": True}}}}

    text = route_crm_text(
        "把用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 的标签 高意向 去掉",
        context_loader=fake_context_loader,
        tag_updater=fake_tag_updater,
        tag_reader=lambda: [{"tag_id": "tag-001", "tag_name": "高意向", "group_id": "g1", "group_name": "业务标签"}],
    )

    assert captured == {
        "external_userid": "wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw",
        "userid": "QianLan",
        "add_tags": [],
        "remove_tags": ["tag-001"],
    }
    assert text == "已给用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 去掉标签：高意向"


def test_route_returns_clear_message_when_external_userid_missing() -> None:
    text = route_crm_text("帮我看看这个用户怎么跟进", tag_reader=lambda: [])

    assert text == "请提供客户 external_userid，例如：wmb..."


def test_route_returns_clear_message_when_tag_not_found() -> None:
    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        return {
            "external_userid": external_userid,
            "customer": {"external_userid": external_userid, "owner_userid": "QianLan"},
            "recent_messages": [],
            "recent_timeline_events": [],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    text = route_crm_text(
        "给用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 打标签 不存在标签",
        context_loader=fake_context_loader,
        tag_reader=lambda: [{"tag_id": "tag-001", "tag_name": "高意向", "group_id": "g1", "group_name": "业务标签"}],
    )

    assert text == "未找到标签：不存在标签"


def test_route_returns_clear_message_when_tag_name_conflicts() -> None:
    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        return {
            "external_userid": external_userid,
            "customer": {"external_userid": external_userid, "owner_userid": "QianLan"},
            "recent_messages": [],
            "recent_timeline_events": [],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    text = route_crm_text(
        "给用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 打标签 高意向",
        context_loader=fake_context_loader,
        tag_reader=lambda: [
            {"tag_id": "tag-001", "tag_name": "高意向", "group_id": "g1", "group_name": "业务标签"},
            {"tag_id": "tag-002", "tag_name": "高意向", "group_id": "g2", "group_name": "测试标签"},
        ],
    )

    assert text == "找到多个同名标签，请明确标签名/标签ID：高意向（业务标签） | 高意向（测试标签）"


def test_route_how_to_chat_returns_context_only() -> None:
    def fake_context_loader(external_userid: str, **kwargs) -> dict:
        return {
            "external_userid": external_userid,
            "customer": {
                "external_userid": external_userid,
                "name": "玄青",
                "status": "active",
                "tags": ["已报名3999"],
            },
            "recent_messages": [{"send_time": "2026-03-24 14:59:44", "content": "你好"}],
            "recent_timeline_events": [],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    text = route_crm_text(
        "这个用户 wmbNXyCwAAAGyWIpNr8E9X989gpT_RXw 我该怎么聊",
        context_loader=fake_context_loader,
        tag_reader=lambda: [],
    )

    assert "客户：玄青" in text
    assert "最近消息：" in text
    assert "当前版本只返回上下文，话术生成能力后续接入。" in text
