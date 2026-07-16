#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.script_runtime import print_json  # noqa: E402


DEFAULT_BASE_URL = "http://127.0.0.1:5001"
_MAX_RESPONSE_BYTES = 64 * 1024
_RELEASE_SHA = re.compile(r"[0-9a-f]{40}\Z")
_AUTH_PROBES = {
    "qr": {
        "host": "open.work.weixin.qq.com",
        "path": "/wwopen/sso/qrConnect",
    },
    "oauth": {
        "host": "open.weixin.qq.com",
        "path": "/connect/oauth2/authorize",
    },
}


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: str
    error_code: str = ""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # noqa: ANN001
        del request, file_pointer, code, message, headers, new_url
        return None


def _normalized_headers(headers: Any) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _read_body(response: Any) -> str:
    return response.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")


def _fetch(url: str, *, timeout: float) -> HttpResponse:
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/html;q=0.9",
            "User-Agent": "aicrm-runtime-secret-readiness/1.0",
        },
        method="GET",
    )
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResponse(
                status_code=int(response.status),
                headers=_normalized_headers(response.headers),
                body=_read_body(response),
            )
    except HTTPError as exc:
        return HttpResponse(
            status_code=int(exc.code),
            headers=_normalized_headers(exc.headers),
            body=_read_body(exc),
        )
    except (OSError, TimeoutError, URLError) as exc:
        return HttpResponse(
            status_code=0,
            headers={},
            body="",
            error_code=f"http_{exc.__class__.__name__.lower()}",
        )


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.hostname or parsed.username or parsed.password:
        return ""
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return ""
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        return ""
    try:
        parsed.port
    except ValueError:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _url(base_url: str, path: str, *, query: dict[str, str] | None = None) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(query or {}), ""))


def _safe_release_sha(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if _RELEASE_SHA.fullmatch(normalized) else ""


def _health_probe(base_url: str, *, expected_sha: str, timeout: float) -> dict[str, Any]:
    response = _fetch(_url(base_url, "/health"), timeout=timeout)
    release_sha = _safe_release_sha(response.headers.get("x-aicrm-release-sha"))
    payload: dict[str, Any] = {}
    json_valid = False
    if response.status_code == 200:
        try:
            decoded = json.loads(response.body)
            payload = decoded if isinstance(decoded, dict) else {}
            json_valid = isinstance(decoded, dict)
        except json.JSONDecodeError:
            json_valid = False

    secret_key_present = payload.get("secret_key_present") is True
    callback_token_present = payload.get("wechat_shop_callback_token_present") is True
    production_data_ready = payload.get("production_data_ready") is True
    release_sha_matches = bool(release_sha and release_sha == expected_sha)

    error_code = ""
    if response.error_code:
        error_code = "health_unreachable"
    elif response.status_code != 200:
        error_code = "health_status_not_200"
    elif not json_valid:
        error_code = "health_json_invalid"
    elif payload.get("ok") is not True:
        error_code = "health_payload_not_ok"
    elif not release_sha_matches:
        error_code = "health_release_sha_mismatch"
    elif not secret_key_present:
        error_code = "health_secret_key_not_ready"
    elif not callback_token_present:
        error_code = "health_wechat_shop_callback_token_not_ready"
    elif not production_data_ready:
        error_code = "health_production_data_not_ready"

    return {
        "ok": not error_code,
        "status_code": response.status_code,
        "release_sha": release_sha,
        "release_sha_matches": release_sha_matches,
        "secret_key_present": secret_key_present,
        "wechat_shop_callback_token_present": callback_token_present,
        "production_data_ready": production_data_ready,
        "error_code": error_code,
    }


def _validated_callback_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    try:
        port = parsed.port
    except ValueError:
        return ""
    hostname = str(parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or hostname in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.path != "/auth/wecom/callback"
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return urlunsplit(("https", hostname, parsed.path, "", ""))


def _auth_probe(
    base_url: str,
    *,
    mode: str,
    expected_callback_url: str,
    timeout: float,
) -> dict[str, Any]:
    contract = _AUTH_PROBES[mode]
    response = _fetch(
        _url(
            base_url,
            "/auth/wecom/start",
            query={"mode": mode, "next": "/admin"},
        ),
        timeout=timeout,
    )
    location = str(response.headers.get("location") or "")
    parsed = urlsplit(location)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    target_valid = bool(
        parsed.scheme == "https"
        and parsed.hostname == contract["host"]
        and parsed.path == contract["path"]
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
    )
    query = parse_qs(parsed.query, keep_blank_values=True)
    state_present = bool(query.get("state") and str(query["state"][-1] or "").strip())
    app_id_present = len(query.get("appid") or []) == 1 and bool(str(query["appid"][0] or "").strip())
    agent_id_present = mode != "qr" or (len(query.get("agentid") or []) == 1 and bool(str(query["agentid"][0] or "").strip()))
    identity_parameters_present = app_id_present and agent_id_present
    redirect_uris = query.get("redirect_uri") or []
    callback_url_matches = bool(len(redirect_uris) == 1 and _validated_callback_url(str(redirect_uris[0] or "")) == expected_callback_url)
    auth_error_present = "auth_error" in unquote(location).lower()
    external_header = str(response.headers.get("x-aicrm-real-external-call-executed") or "").strip().lower()
    external_call_blocked = external_header == "false"

    error_code = ""
    if response.error_code:
        error_code = f"{mode}_auth_start_unreachable"
    elif response.status_code != 302:
        error_code = f"{mode}_auth_start_status_not_302"
    elif auth_error_present:
        error_code = f"{mode}_auth_error_redirect"
    elif not target_valid:
        error_code = f"{mode}_redirect_target_invalid"
    elif not identity_parameters_present:
        error_code = f"{mode}_identity_parameters_missing"
    elif not callback_url_matches:
        error_code = f"{mode}_callback_url_mismatch"
    elif not state_present:
        error_code = f"{mode}_state_missing"
    elif not external_call_blocked:
        error_code = f"{mode}_real_external_call_executed"

    return {
        "ok": not error_code,
        "status_code": response.status_code,
        "redirect_scheme": parsed.scheme if target_valid else "",
        "redirect_host": parsed.hostname if target_valid else "",
        "redirect_path": parsed.path if target_valid else "",
        "identity_parameters_present": identity_parameters_present,
        "callback_url_matches": callback_url_matches,
        "state_present": state_present,
        "auth_error_present": auth_error_present,
        "real_external_call_executed": not external_call_blocked,
        "error_code": error_code,
    }


def _not_checked_payload(error_code: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": error_code,
        "health": {"ok": False, "error_code": "not_checked"},
        "auth": {
            "qr": {"ok": False, "error_code": "not_checked"},
            "oauth": {"ok": False, "error_code": "not_checked"},
        },
    }


def run(
    *,
    base_url: str,
    expected_sha: str,
    expected_callback_url: str,
    timeout: float,
) -> dict[str, Any]:
    normalized_sha = str(expected_sha or "").strip()
    if not _RELEASE_SHA.fullmatch(normalized_sha):
        return _not_checked_payload("expected_release_sha_invalid")
    normalized_base_url = _validated_base_url(base_url)
    if not normalized_base_url:
        return _not_checked_payload("base_url_invalid")
    normalized_callback_url = _validated_callback_url(expected_callback_url)
    if not normalized_callback_url:
        return _not_checked_payload("expected_callback_url_invalid")

    health = _health_probe(normalized_base_url, expected_sha=normalized_sha, timeout=timeout)
    auth = {
        mode: _auth_probe(
            normalized_base_url,
            mode=mode,
            expected_callback_url=normalized_callback_url,
            timeout=timeout,
        )
        for mode in ("qr", "oauth")
    }
    error_code = str(health.get("error_code") or "")
    if not error_code:
        for mode in ("qr", "oauth"):
            error_code = str(auth[mode].get("error_code") or "")
            if error_code:
                break
    return {
        "ok": not error_code,
        "error_code": error_code,
        "health": health,
        "auth": auth,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only process canary for release, secret, production-data, and WeCom auth readiness.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-callback-url", required=True)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args(argv)
    payload = run(
        base_url=str(args.base_url),
        expected_sha=str(args.expected_sha),
        expected_callback_url=str(args.expected_callback_url),
        timeout=max(0.1, float(args.timeout)),
    )
    print_json(payload, indent=2, sort_keys=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
