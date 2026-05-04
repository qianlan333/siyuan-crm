from __future__ import annotations

import json

from openclaw_service.cli.customer_chat_context_preflight import main
from openclaw_service.services.customer_chat_context_preflight import (
    run_customer_chat_context_preflight,
    validate_customer_chat_context_env,
)


def test_validate_env_detects_missing_required(monkeypatch) -> None:
    monkeypatch.delenv("CRM_API_BASE_URL", raising=False)
    monkeypatch.delenv("CRM_API_TOKEN", raising=False)

    result = validate_customer_chat_context_env()

    assert result["ok"] is False
    assert result["missing_required"] == ["CRM_API_BASE_URL", "CRM_API_TOKEN"]


def test_preflight_calls_registry_tool_path(monkeypatch) -> None:
    monkeypatch.setenv("CRM_API_BASE_URL", "https://crm.example.com")
    monkeypatch.setenv("CRM_API_TOKEN", "crm-token")
    captured: dict = {}

    def fake_dispatch(name: str, arguments: dict | None = None) -> dict:
        captured["name"] = name
        captured["arguments"] = arguments
        return {
            "external_userid": arguments["external_userid"],
            "customer": {
                "external_userid": arguments["external_userid"],
                "name": "Alice",
                "owner_userid": "sales_01",
            },
            "recent_messages": [{"id": "m-1"}],
            "recent_timeline_events": [{"event_id": "e-1"}],
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    monkeypatch.setattr(
        "openclaw_service.services.customer_chat_context_preflight.call_tool_by_name",
        fake_dispatch,
    )

    result = run_customer_chat_context_preflight("wm_ext_001", recent_message_limit=3, timeline_limit=4)

    assert result["ok"] is True
    assert result["source_status"] == "live"
    assert captured["name"] == "get_customer_chat_context"
    assert captured["arguments"] == {
        "external_userid": "wm_ext_001",
        "recent_message_limit": 3,
        "timeline_limit": 4,
    }


def test_preflight_returns_ok_true_for_fallback(monkeypatch) -> None:
    monkeypatch.setenv("CRM_API_BASE_URL", "https://crm.example.com")
    monkeypatch.setenv("CRM_API_TOKEN", "crm-token")
    monkeypatch.setattr(
        "openclaw_service.services.customer_chat_context_preflight.call_tool_by_name",
        lambda name, arguments=None: {
            "external_userid": arguments["external_userid"],
            "customer": {"external_userid": arguments["external_userid"]},
            "recent_messages": [{"id": "m-1"}],
            "recent_timeline_events": [{"event_id": "e-1"}],
            "source_status": "fallback",
            "degraded": True,
            "warnings": ["timeline fallback in use"],
        },
    )

    result = run_customer_chat_context_preflight("wm_ext_002")

    assert result["ok"] is True
    assert result["source_status"] == "fallback"
    assert result["degraded"] is True


def test_preflight_returns_ok_false_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("CRM_API_BASE_URL", raising=False)
    monkeypatch.delenv("CRM_API_TOKEN", raising=False)

    result = run_customer_chat_context_preflight("wm_ext_003")

    assert result["ok"] is False
    assert result["source_status"] == "error"
    assert result["env"]["missing_required"]


def test_preflight_cli_exit_code_live(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context_preflight.run_customer_chat_context_preflight",
        lambda external_userid, **kwargs: {
            "ok": True,
            "external_userid": external_userid,
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        },
    )

    exit_code = main(["--external-userid", "wm_ext_004"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["source_status"] == "live"


def test_preflight_cli_exit_code_fallback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context_preflight.run_customer_chat_context_preflight",
        lambda external_userid, **kwargs: {
            "ok": True,
            "external_userid": external_userid,
            "source_status": "fallback",
            "degraded": True,
            "warnings": ["timeline fallback in use"],
        },
    )

    exit_code = main(["--external-userid", "wm_ext_005"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["source_status"] == "fallback"


def test_preflight_cli_exit_code_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context_preflight.run_customer_chat_context_preflight",
        lambda external_userid, **kwargs: {
            "ok": False,
            "external_userid": external_userid,
            "source_status": "error",
            "degraded": False,
            "warnings": [],
            "error": "missing required env: CRM_API_TOKEN",
        },
    )

    exit_code = main(["--external-userid", "wm_ext_006"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["source_status"] == "error"
