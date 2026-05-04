from __future__ import annotations

import json

from openclaw_service.cli.customer_chat_context import main


def test_cli_prints_json_on_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "openclaw_service.cli.customer_chat_context.load_customer_chat_context",
        lambda external_userid, **kwargs: {
            "external_userid": external_userid,
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        },
    )

    exit_code = main(["--external-userid", "wm_ext_001"])

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert exit_code == 0
    assert payload["external_userid"] == "wm_ext_001"


def test_cli_returns_non_zero_and_error_json_on_failure(monkeypatch, capsys) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("crm unavailable")

    monkeypatch.setattr("openclaw_service.cli.customer_chat_context.load_customer_chat_context", fail)

    exit_code = main(["--external-userid", "wm_ext_002"])

    err = capsys.readouterr().err
    payload = json.loads(err)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["external_userid"] == "wm_ext_002"
