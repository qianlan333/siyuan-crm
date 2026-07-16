from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts.ops import check_runtime_secret_readiness as readiness


EXPECTED_SHA = "1" * 40
EXPECTED_CALLBACK_URL = "https://crm.example.test/auth/wecom/callback"
QR_LOCATION = (
    "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
    "?appid=ww-test&agentid=1000023&redirect_uri=https%3A%2F%2Fcrm.example.test%2Fauth%2Fwecom%2Fcallback"
    "&state=private-qr-state"
)
OAUTH_LOCATION = (
    "https://open.weixin.qq.com/connect/oauth2/authorize"
    "?appid=ww-test&redirect_uri=https%3A%2F%2Fcrm.example.test%2Fauth%2Fwecom%2Fcallback"
    "&response_type=code&scope=snsapi_base&state=private-oauth-state#wechat_redirect"
)


def _response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    body: str = "",
) -> readiness.HttpResponse:
    return readiness.HttpResponse(
        status_code=status_code,
        headers={str(key).lower(): str(value) for key, value in (headers or {}).items()},
        body=body,
        error_code="",
    )


def _healthy_fetch(
    url: str,
    *,
    timeout: float,
    qr_location: str = QR_LOCATION,
    oauth_location: str = OAUTH_LOCATION,
    real_external_call_executed: str = "false",
) -> readiness.HttpResponse:
    del timeout
    parsed = urlsplit(url)
    if parsed.path == "/health":
        return _response(
            200,
            headers={"X-AICRM-Release-SHA": EXPECTED_SHA},
            body=json.dumps(
                {
                    "ok": True,
                    "secret_key_present": True,
                    "wechat_shop_callback_token_present": True,
                    "production_data_ready": True,
                }
            ),
        )
    if parsed.path == "/auth/wecom/start":
        mode = parse_qs(parsed.query).get("mode", [""])[0]
        location = qr_location if mode == "qr" else oauth_location
        return _response(
            302,
            headers={
                "Location": location,
                "X-AICRM-Real-External-Call-Executed": real_external_call_executed,
            },
        )
    raise AssertionError(f"unexpected canary URL path: {parsed.path}")


def test_fetch_does_not_follow_redirects() -> None:
    requested_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            requested_paths.append(self.path)
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/must-not-be-followed?state=private-state")
                self.end_headers()
                return
            self.send_response(500)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = readiness._fetch(
            f"http://127.0.0.1:{server.server_port}/start",
            timeout=1.0,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert response.status_code == 302
    assert requested_paths == ["/start"]


def test_run_accepts_exact_healthy_contract_and_redacts_redirect_details(monkeypatch) -> None:
    monkeypatch.setattr(readiness, "_fetch", _healthy_fetch)

    payload = readiness.run(
        base_url="http://127.0.0.1:5001",
        expected_sha=EXPECTED_SHA,
        expected_callback_url=EXPECTED_CALLBACK_URL,
        timeout=1.0,
    )

    assert payload["ok"] is True
    assert payload["error_code"] == ""
    assert payload["health"] == {
        "ok": True,
        "status_code": 200,
        "release_sha": EXPECTED_SHA,
        "release_sha_matches": True,
        "secret_key_present": True,
        "wechat_shop_callback_token_present": True,
        "production_data_ready": True,
        "error_code": "",
    }
    assert payload["auth"]["qr"]["redirect_host"] == "open.work.weixin.qq.com"
    assert payload["auth"]["qr"]["redirect_path"] == "/wwopen/sso/qrConnect"
    assert payload["auth"]["oauth"]["redirect_host"] == "open.weixin.qq.com"
    assert payload["auth"]["oauth"]["redirect_path"] == "/connect/oauth2/authorize"
    assert payload["auth"]["qr"]["state_present"] is True
    assert payload["auth"]["oauth"]["state_present"] is True
    assert payload["auth"]["qr"]["identity_parameters_present"] is True
    assert payload["auth"]["oauth"]["identity_parameters_present"] is True
    assert payload["auth"]["qr"]["callback_url_matches"] is True
    assert payload["auth"]["oauth"]["callback_url_matches"] is True
    assert payload["auth"]["qr"]["real_external_call_executed"] is False
    assert payload["auth"]["oauth"]["real_external_call_executed"] is False

    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        QR_LOCATION,
        OAUTH_LOCATION,
        "private-qr-state",
        "private-oauth-state",
        "redirect_uri",
        "appid",
        "agentid",
        "location",
    ):
        assert forbidden not in rendered.lower()


@pytest.mark.parametrize(
    ("health_override", "expected_error"),
    [
        ({"release_sha": "2" * 40}, "health_release_sha_mismatch"),
        ({"secret_key_present": False}, "health_secret_key_not_ready"),
        (
            {"wechat_shop_callback_token_present": False},
            "health_wechat_shop_callback_token_not_ready",
        ),
        ({"production_data_ready": False}, "health_production_data_not_ready"),
    ],
)
def test_run_fails_closed_when_health_contract_is_not_ready(
    monkeypatch,
    health_override: dict[str, object],
    expected_error: str,
) -> None:
    def fetch(url: str, *, timeout: float) -> readiness.HttpResponse:
        response = _healthy_fetch(url, timeout=timeout)
        if urlsplit(url).path != "/health":
            return response
        payload = json.loads(response.body)
        headers = dict(response.headers)
        if "release_sha" in health_override:
            headers["x-aicrm-release-sha"] = str(health_override["release_sha"])
        else:
            payload.update(health_override)
        return _response(200, headers=headers, body=json.dumps(payload))

    monkeypatch.setattr(readiness, "_fetch", fetch)

    payload = readiness.run(
        base_url="http://127.0.0.1:5001",
        expected_sha=EXPECTED_SHA,
        expected_callback_url=EXPECTED_CALLBACK_URL,
        timeout=1.0,
    )

    assert payload["ok"] is False
    assert payload["health"]["ok"] is False
    assert payload["health"]["error_code"] == expected_error
    assert payload["error_code"] == expected_error


def test_run_allows_missing_wechat_shop_callback_token_only_when_explicit(monkeypatch) -> None:
    def fetch(url: str, *, timeout: float) -> readiness.HttpResponse:
        response = _healthy_fetch(url, timeout=timeout)
        if urlsplit(url).path != "/health":
            return response
        payload = json.loads(response.body)
        payload["wechat_shop_callback_token_present"] = False
        return _response(200, headers=dict(response.headers), body=json.dumps(payload))

    monkeypatch.setattr(readiness, "_fetch", fetch)

    payload = readiness.run(
        base_url="http://127.0.0.1:5001",
        expected_sha=EXPECTED_SHA,
        expected_callback_url=EXPECTED_CALLBACK_URL,
        timeout=1.0,
        allow_missing_wechat_shop_callback_token=True,
    )

    assert payload["ok"] is True
    assert payload["error_code"] == ""
    assert payload["health"]["ok"] is True
    assert payload["health"]["wechat_shop_callback_token_present"] is False


def test_main_accepts_allow_missing_wechat_shop_callback_token_flag(monkeypatch, capsys) -> None:
    def fetch(url: str, *, timeout: float) -> readiness.HttpResponse:
        response = _healthy_fetch(url, timeout=timeout)
        if urlsplit(url).path != "/health":
            return response
        payload = json.loads(response.body)
        payload["wechat_shop_callback_token_present"] = False
        return _response(200, headers=dict(response.headers), body=json.dumps(payload))

    monkeypatch.setattr(readiness, "_fetch", fetch)

    exit_code = readiness.main(
        [
            "--base-url",
            "http://127.0.0.1:5001",
            "--expected-sha",
            EXPECTED_SHA,
            "--expected-callback-url",
            EXPECTED_CALLBACK_URL,
            "--allow-missing-wechat-shop-callback-token",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


@pytest.mark.parametrize(
    ("qr_location", "oauth_location", "external_header", "expected_error"),
    [
        (
            "/login?next=%2Fadmin&auth_error=wecom_admin_auth_config_missing",
            OAUTH_LOCATION,
            "false",
            "qr_auth_error_redirect",
        ),
        (
            QR_LOCATION,
            "https://example.invalid/connect/oauth2/authorize?state=private-state",
            "false",
            "oauth_redirect_target_invalid",
        ),
        (
            QR_LOCATION,
            OAUTH_LOCATION,
            "true",
            "qr_real_external_call_executed",
        ),
        (
            QR_LOCATION.replace(
                "https%3A%2F%2Fcrm.example.test%2Fauth%2Fwecom%2Fcallback",
                "http%3A%2F%2F127.0.0.1%3A5001%2Fauth%2Fwecom%2Fcallback",
            ),
            OAUTH_LOCATION,
            "false",
            "qr_callback_url_mismatch",
        ),
    ],
)
def test_run_rejects_unsafe_auth_start_contracts(
    monkeypatch,
    qr_location: str,
    oauth_location: str,
    external_header: str,
    expected_error: str,
) -> None:
    def fetch(url: str, *, timeout: float) -> readiness.HttpResponse:
        return _healthy_fetch(
            url,
            timeout=timeout,
            qr_location=qr_location,
            oauth_location=oauth_location,
            real_external_call_executed=external_header,
        )

    monkeypatch.setattr(readiness, "_fetch", fetch)

    payload = readiness.run(
        base_url="http://127.0.0.1:5001",
        expected_sha=EXPECTED_SHA,
        expected_callback_url=EXPECTED_CALLBACK_URL,
        timeout=1.0,
    )

    assert payload["ok"] is False
    assert payload["error_code"] == expected_error
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "private-state" not in rendered
    assert "auth_error=" not in rendered


@pytest.mark.parametrize(
    "expected_sha",
    ["", "abc", "G" * 40, "1" * 39],
)
def test_run_rejects_invalid_expected_release_sha_without_probing(monkeypatch, expected_sha: str) -> None:
    monkeypatch.setattr(
        readiness,
        "_fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("invalid SHA must not probe")),
    )

    payload = readiness.run(
        base_url="http://127.0.0.1:5001",
        expected_sha=expected_sha,
        expected_callback_url=EXPECTED_CALLBACK_URL,
        timeout=1.0,
    )

    assert payload == {
        "ok": False,
        "error_code": "expected_release_sha_invalid",
        "health": {"ok": False, "error_code": "not_checked"},
        "auth": {
            "qr": {"ok": False, "error_code": "not_checked"},
            "oauth": {"ok": False, "error_code": "not_checked"},
        },
    }


def test_run_rejects_non_loopback_base_url_without_probing(monkeypatch) -> None:
    monkeypatch.setattr(
        readiness,
        "_fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("external base URL must not be probed")),
    )

    payload = readiness.run(
        base_url="https://example.invalid",
        expected_sha=EXPECTED_SHA,
        expected_callback_url=EXPECTED_CALLBACK_URL,
        timeout=1.0,
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "base_url_invalid"
    assert payload["health"]["error_code"] == "not_checked"


@pytest.mark.parametrize(
    "expected_callback_url",
    [
        "",
        "http://crm.example.test/auth/wecom/callback",
        "https://localhost/auth/wecom/callback",
        "https://crm.example.test/wrong-callback",
    ],
)
def test_run_rejects_invalid_expected_callback_url_without_probing(
    monkeypatch,
    expected_callback_url: str,
) -> None:
    monkeypatch.setattr(
        readiness,
        "_fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("invalid callback URL must not probe")),
    )

    payload = readiness.run(
        base_url="http://127.0.0.1:5001",
        expected_sha=EXPECTED_SHA,
        expected_callback_url=expected_callback_url,
        timeout=1.0,
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "expected_callback_url_invalid"
    assert payload["health"]["error_code"] == "not_checked"
