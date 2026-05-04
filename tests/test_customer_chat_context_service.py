from __future__ import annotations

from openclaw_service.integrations.crm.config import CrmApiConfig
from openclaw_service.services.customer_chat_context_service import get_customer_chat_context


def test_service_returns_context_without_manual_adapter_wiring(monkeypatch) -> None:
    monkeypatch.setattr(CrmApiConfig, "from_env", classmethod(lambda cls: CrmApiConfig(base_url="https://crm.example.com")))

    captured: dict = {}

    def fake_builder(external_userid: str, **kwargs):
        captured["external_userid"] = external_userid
        captured.update(kwargs)
        return {"external_userid": external_userid, "source_status": "live", "degraded": False, "warnings": []}

    monkeypatch.setattr(
        "openclaw_service.services.customer_chat_context_service.build_customer_chat_context",
        fake_builder,
    )

    result = get_customer_chat_context("wm_ext_001")

    assert result["external_userid"] == "wm_ext_001"
    assert captured["external_userid"] == "wm_ext_001"
    assert captured["customers"].__class__.__name__ == "CustomersAdapter"
    assert captured["messages"].__class__.__name__ == "MessagesAdapter"
    assert captured["timeline"].__class__.__name__ == "TimelineAdapter"


def test_service_passes_limit_arguments(monkeypatch) -> None:
    monkeypatch.setattr(CrmApiConfig, "from_env", classmethod(lambda cls: CrmApiConfig(base_url="https://crm.example.com")))

    captured: dict = {}

    def fake_builder(external_userid: str, **kwargs):
        captured.update(kwargs)
        return {"external_userid": external_userid, "source_status": "live", "degraded": False, "warnings": []}

    monkeypatch.setattr(
        "openclaw_service.services.customer_chat_context_service.build_customer_chat_context",
        fake_builder,
    )

    get_customer_chat_context("wm_ext_002", recent_message_limit=7, timeline_limit=9)

    assert captured["recent_message_limit"] == 7
    assert captured["timeline_limit"] == 9


def test_service_preserves_degraded_result(monkeypatch) -> None:
    monkeypatch.setattr(CrmApiConfig, "from_env", classmethod(lambda cls: CrmApiConfig(base_url="https://crm.example.com")))

    monkeypatch.setattr(
        "openclaw_service.services.customer_chat_context_service.build_customer_chat_context",
        lambda external_userid, **kwargs: {
            "external_userid": external_userid,
            "source_status": "fallback",
            "degraded": True,
            "warnings": ["timeline fallback in use"],
        },
    )

    result = get_customer_chat_context("wm_ext_003")

    assert result["degraded"] is True
    assert result["source_status"] == "fallback"
