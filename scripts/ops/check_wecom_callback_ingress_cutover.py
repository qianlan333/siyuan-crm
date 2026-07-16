#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


DEFAULT_NGINX_CONFIG = "/etc/nginx/sites-enabled/youcangogogo.conf"
DEFAULT_INGRESS_HEALTH_URL = "http://127.0.0.1:5002/health"
DEFAULT_INVALID_CALLBACK_URL = "http://127.0.0.1:5002/wecom/external-contact/callback?timestamp=1&nonce=codex-cutover&msg_signature=invalid"
CALLBACK_ROUTES = ("/wecom/external-contact/callback", "/api/wecom/events")
CALLBACK_UPSTREAM_NAME = "aicrm_wecom_ingress"
GLOBAL_BACKPRESSURE_SNIPPETS = (
    "limit_req_zone",
    "zone=aicrm_wecom_callback_req",
    "limit_conn_zone",
    "zone=aicrm_wecom_callback_conn",
)
ROUTE_BACKPRESSURE_SNIPPETS = (
    "limit_req zone=aicrm_wecom_callback_req",
    "limit_conn aicrm_wecom_callback_conn",
    "limit_req_status 429",
    "limit_conn_status 429",
)
ROUTE_TIMEOUT_SNIPPETS = ("proxy_connect_timeout 1s", "proxy_send_timeout 3s", "proxy_read_timeout 3s")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_config(path: str) -> tuple[str, str]:
    config_path = Path(path)
    if not config_path.exists():
        return "", "nginx config not found"
    try:
        return config_path.read_text(encoding="utf-8", errors="replace"), ""
    except OSError as exc:
        return "", str(exc)


def _read_global_nginx_config(path: str) -> str:
    config_path = Path(path)
    if not str(config_path).startswith("/etc/nginx/"):
        return ""
    try:
        effective = subprocess.run(
            ["/usr/sbin/nginx", "-T"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        effective = None
    if effective is not None and effective.returncode == 0:
        return effective.stdout + "\n" + effective.stderr
    global_config = Path("/etc/nginx/nginx.conf")
    if not global_config.exists() or global_config == config_path:
        return ""
    try:
        return global_config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _strip_nginx_comments(content: str) -> str:
    lines: list[str] = []
    for line in content.splitlines():
        before_comment = line.split("#", 1)[0]
        lines.append(before_comment)
    return "\n".join(lines)


def _extract_nginx_block(content: str, prefix: str) -> str:
    start = content.find(prefix)
    if start < 0:
        return ""
    brace_start = content.find("{", start)
    if brace_start < 0:
        return ""
    depth = 0
    for index in range(brace_start, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[brace_start + 1 : index]
    return ""


def _route_block(content: str, route: str) -> str:
    return _extract_nginx_block(content, f"location = {route}")


def _upstream_points_to_5002(content: str) -> bool:
    upstream_block = _extract_nginx_block(content, f"upstream {CALLBACK_UPSTREAM_NAME}")
    return "127.0.0.1:5002" in upstream_block


def _route_state(content: str, route: str, *, named_upstream_points_to_5002: bool) -> dict[str, Any]:
    block = _route_block(content, route)
    present = bool(block)
    uses_named_upstream = f"proxy_pass http://{CALLBACK_UPSTREAM_NAME}" in block
    proxy_to_5002 = present and ("proxy_pass http://127.0.0.1:5002" in block or (uses_named_upstream and named_upstream_points_to_5002))
    short_timeouts = present and all(snippet in block for snippet in ROUTE_TIMEOUT_SNIPPETS)
    backpressure = present and all(snippet in block for snippet in ROUTE_BACKPRESSURE_SNIPPETS)
    quick_ack = present and ('return 200 "success"' in block or "return 200 'success'" in block)
    return {
        "present": present,
        "proxy_to_5002": proxy_to_5002,
        "uses_named_upstream": uses_named_upstream,
        "short_timeouts_configured": short_timeouts,
        "backpressure_configured": backpressure,
        "emergency_quick_ack_enabled": quick_ack,
    }


def analyze_nginx_config(path: str) -> dict[str, Any]:
    content, error = _read_config(path)
    if error:
        return {
            "nginx_config": path,
            "nginx_config_found": False,
            "callback_routes_present": False,
            "emergency_quick_ack_enabled": False,
            "callback_routes_proxy_to_5002": False,
            "short_callback_timeouts_configured": False,
            "callback_backpressure_configured": False,
            "callback_route_details": {},
            "error": error,
        }
    effective_content = _strip_nginx_comments(content)
    effective_global_content = _strip_nginx_comments(_read_global_nginx_config(path))
    effective_combined_content = effective_content + "\n" + effective_global_content
    named_upstream_points_to_5002 = _upstream_points_to_5002(effective_content)
    route_details = {
        route: _route_state(effective_content, route, named_upstream_points_to_5002=named_upstream_points_to_5002)
        for route in CALLBACK_ROUTES
    }
    callback_routes_present = all(detail["present"] for detail in route_details.values())
    emergency_quick_ack_enabled = any(detail["emergency_quick_ack_enabled"] for detail in route_details.values())
    callback_routes_proxy_to_5002 = callback_routes_present and all(detail["proxy_to_5002"] for detail in route_details.values())
    short_timeouts = callback_routes_present and all(detail["short_timeouts_configured"] for detail in route_details.values())
    global_backpressure = all(snippet in effective_combined_content for snippet in GLOBAL_BACKPRESSURE_SNIPPETS)
    route_backpressure = callback_routes_present and all(detail["backpressure_configured"] for detail in route_details.values())
    backpressure = global_backpressure and route_backpressure
    return {
        "nginx_config": path,
        "nginx_config_found": True,
        "callback_routes_present": callback_routes_present,
        "emergency_quick_ack_enabled": emergency_quick_ack_enabled,
        "callback_routes_proxy_to_5002": callback_routes_proxy_to_5002,
        "short_callback_timeouts_configured": short_timeouts,
        "callback_backpressure_configured": backpressure,
        "callback_route_details": route_details,
        "error": "",
    }


def probe_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "aicrm-wecom-callback-ingress-cutover-check/1.0"}, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(2048).decode("utf-8", errors="replace")
            return {"checked": True, "ok": 200 <= int(response.status) < 300, "status_code": int(response.status), "body": body, "error": ""}
    except HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace")
        return {"checked": True, "ok": False, "status_code": int(exc.code), "body": body, "error": ""}
    except (OSError, URLError) as exc:
        return {"checked": False, "ok": False, "status_code": None, "body": "", "error": str(exc)}


def probe_invalid_callback(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        url,
        data=b"<xml>invalid</xml>",
        headers={"Content-Type": "text/xml; charset=utf-8", "User-Agent": "aicrm-wecom-callback-ingress-cutover-check/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(512).decode("utf-8", errors="replace")
            status_code = int(response.status)
    except HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except (OSError, URLError) as exc:
        return {"checked": False, "ok": False, "status_code": None, "body": "", "plain_success": None, "error": str(exc)}
    plain_success = status_code == 200 and body.strip() == "success"
    return {
        "checked": True,
        "ok": not plain_success and status_code in {400, 401, 403, 422, 500, 503},
        "status_code": status_code,
        "body": body,
        "plain_success": plain_success,
        "error": "",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check readiness for routing WeCom callbacks to isolated ingress on 127.0.0.1:5002.")
    parser.add_argument("--nginx-config", default=DEFAULT_NGINX_CONFIG)
    parser.add_argument("--ingress-health-url", default=DEFAULT_INGRESS_HEALTH_URL)
    parser.add_argument("--invalid-callback-url", default=DEFAULT_INVALID_CALLBACK_URL)
    parser.add_argument("--probe-timeout", type=float, default=2.0)
    parser.add_argument("--skip-health-probe", action="store_true", default=False)
    parser.add_argument("--skip-invalid-callback-probe", action="store_true", default=False)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parse_args(argv)
    nginx_state = analyze_nginx_config(str(args.nginx_config))
    health_state = (
        {"checked": False, "ok": None, "status_code": None, "body": "", "error": "probe skipped"}
        if args.skip_health_probe
        else probe_json(str(args.ingress_health_url), float(args.probe_timeout))
    )
    invalid_callback_state = (
        {"checked": False, "ok": None, "status_code": None, "body": "", "plain_success": None, "error": "probe skipped"}
        if args.skip_invalid_callback_probe
        else probe_invalid_callback(str(args.invalid_callback_url), float(args.probe_timeout))
    )
    ready = bool(
        nginx_state.get("nginx_config_found")
        and nginx_state.get("callback_routes_proxy_to_5002")
        and nginx_state.get("short_callback_timeouts_configured")
        and nginx_state.get("callback_backpressure_configured")
        and not nginx_state.get("emergency_quick_ack_enabled")
        and (health_state.get("ok") is True or health_state.get("checked") is False)
        and (invalid_callback_state.get("ok") is True or invalid_callback_state.get("checked") is False)
    )
    warnings: list[str] = []
    if nginx_state.get("emergency_quick_ack_enabled"):
        warnings.append("emergency quick ACK is still enabled; valid callbacks will not reach webhook_inbox")
    if not nginx_state.get("callback_routes_proxy_to_5002"):
        warnings.append("callback routes are not configured for 127.0.0.1:5002 ingress")
    if not nginx_state.get("short_callback_timeouts_configured"):
        warnings.append("callback route short proxy timeouts are missing")
    if not nginx_state.get("callback_backpressure_configured"):
        warnings.append("callback route backpressure limits are missing")
    if health_state.get("error") and health_state.get("checked") is False and health_state.get("error") != "probe skipped":
        warnings.append(f"ingress health probe unavailable: {health_state['error']}")
    if invalid_callback_state.get("plain_success") is True:
        warnings.append("invalid callback POST still returns plain success; callback route appears to be nginx quick ACK")
    if invalid_callback_state.get("error") and invalid_callback_state.get("checked") is False and invalid_callback_state.get("error") != "probe skipped":
        warnings.append(f"invalid callback probe unavailable: {invalid_callback_state['error']}")
    return {
        "ok": ready,
        "ready_for_cutover": ready,
        "nginx": nginx_state,
        "ingress_health": health_state,
        "invalid_callback": invalid_callback_state,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    payload = run(argv)
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
