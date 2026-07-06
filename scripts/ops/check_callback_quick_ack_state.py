#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
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
PROBE_URL_ENV = "AICRM_CALLBACK_QUICK_ACK_PROBE_URL"
PROBE_URLS_ENV = "AICRM_CALLBACK_QUICK_ACK_PROBE_URLS"
CALLBACK_ROUTES = ("/wecom/external-contact/callback", "/api/wecom/events")
QUICK_ACK_RETURN_RE = re.compile(r"\breturn\s+200\s+[\"']?success[\"']?\s*;", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_env_file(path: str) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
    return True


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _strip_nginx_comments(content: str) -> str:
    lines: list[str] = []
    for line in content.splitlines():
        lines.append(line.split("#", 1)[0])
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


def _route_quick_ack_state(content: str, route: str) -> dict[str, Any]:
    block = _extract_nginx_block(content, f"location = {route}")
    return {
        "present": bool(block),
        "emergency_quick_ack_enabled": bool(block and QUICK_ACK_RETURN_RE.search(block)),
    }


def _detect_quick_ack(nginx_config: str) -> dict[str, Any]:
    path = Path(nginx_config)
    if not path.exists():
        return {
            "nginx_config": nginx_config,
            "nginx_config_found": False,
            "emergency_quick_ack_enabled": False,
            "matched_routes": [],
            "callback_route_details": {},
            "error": "nginx config not found",
        }
    content = _strip_nginx_comments(path.read_text(encoding="utf-8", errors="replace"))
    route_details = {route: _route_quick_ack_state(content, route) for route in CALLBACK_ROUTES}
    matched_routes = [route for route, detail in route_details.items() if detail["present"]]
    quick_ack_routes = [route for route, detail in route_details.items() if detail["emergency_quick_ack_enabled"]]
    return {
        "nginx_config": nginx_config,
        "nginx_config_found": True,
        "emergency_quick_ack_enabled": bool(quick_ack_routes),
        "matched_routes": matched_routes,
        "quick_ack_routes": quick_ack_routes,
        "callback_route_details": route_details,
        "error": "",
    }


def _recent_callback_events(minutes: int) -> dict[str, Any]:
    database_url = _psycopg_url(_text(os.getenv("DATABASE_URL")))
    if not database_url:
        return {"database_checked": False, "recent_app_callback_events": None, "error": "DATABASE_URL is empty"}
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(database_url, row_factory=dict_row) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM wecom_external_contact_event_logs
                WHERE created_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
                """,
                (max(1, int(minutes or 10)),),
            )
            row = dict(cur.fetchone() or {})
        return {"database_checked": True, "recent_app_callback_events": int(row.get("count") or 0), "error": ""}
    except Exception as exc:  # pragma: no cover - depends on production env
        return {"database_checked": False, "recent_app_callback_events": None, "error": str(exc)}


def _probe_callback_post(url: str, timeout_seconds: float) -> dict[str, Any]:
    if not url:
        return {"callback_post_checked": False, "callback_post_nginx_200": None, "status_code": None, "body": "", "error": "probe url is empty"}
    request = Request(
        url,
        data=b"codex-quick-ack-check",
        headers={"Content-Type": "text/plain", "User-Agent": "aicrm-callback-quick-ack-check/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(200).decode("utf-8", errors="replace")
            status_code = int(response.status)
        return {
            "callback_post_checked": True,
            "callback_post_nginx_200": status_code == 200 and body.strip() == "success",
            "status_code": status_code,
            "body": body,
            "error": "",
        }
    except HTTPError as exc:
        body = exc.read(200).decode("utf-8", errors="replace")
        return {
            "callback_post_checked": True,
            "callback_post_nginx_200": False,
            "status_code": int(exc.code),
            "body": body,
            "error": "",
        }
    except URLError as exc:  # pragma: no cover - depends on network
        return {"callback_post_checked": False, "callback_post_nginx_200": None, "status_code": None, "body": "", "error": str(exc)}


def _probe_callback_posts(urls: list[str], timeout_seconds: float) -> dict[str, Any]:
    probes = []
    for url in urls:
        probe = _probe_callback_post(url, timeout_seconds)
        probe["url"] = url
        probes.append(probe)
    checked = [item for item in probes if item.get("callback_post_checked") is True]
    nginx_200 = [item for item in checked if item.get("callback_post_nginx_200") is True]
    first = probes[0] if probes else {}
    return {
        "callback_post_checked": bool(checked) and len(checked) == len(probes),
        "callback_post_nginx_200": bool(probes) and len(nginx_200) == len(probes),
        "callback_post_nginx_200_all": bool(probes) and len(nginx_200) == len(probes),
        "callback_post_nginx_200_any": bool(nginx_200),
        "status_code": first.get("status_code"),
        "body": first.get("body") or "",
        "error": "; ".join(_text(item.get("error")) for item in probes if _text(item.get("error"))),
        "probes": probes,
    }


def _env_probe_urls() -> list[str]:
    raw_urls = _text(os.getenv(PROBE_URLS_ENV))
    if raw_urls:
        return [_text(item) for item in raw_urls.split(",") if _text(item)]
    single_url = _text(os.getenv(PROBE_URL_ENV))
    return [single_url] if single_url else []


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether emergency nginx quick ACK is still suppressing WeCom callback business processing.")
    parser.add_argument("--nginx-config", default=os.getenv("AICRM_NGINX_CONFIG", DEFAULT_NGINX_CONFIG))
    parser.add_argument("--env-file", default=os.getenv("AICRM_ENV_FILE", "/opt/openclaw/.env"))
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument(
        "--probe-url",
        action="append",
        default=None,
        help=f"Callback POST probe URL. Repeat to check both callback routes. If omitted, uses {PROBE_URLS_ENV} or {PROBE_URL_ENV}.",
    )
    parser.add_argument("--probe-timeout", type=float, default=3.0)
    parser.add_argument("--skip-probe", action="store_true", default=False)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parse_args(argv)
    env_file_loaded = _load_env_file(str(args.env_file))
    nginx_state = _detect_quick_ack(str(args.nginx_config))
    db_state = _recent_callback_events(int(args.minutes))
    probe_urls = [str(item) for item in (args.probe_url if args.probe_url is not None else _env_probe_urls()) if _text(item)]
    probe_state = (
        {
            "callback_post_checked": False,
            "callback_post_nginx_200": None,
            "callback_post_nginx_200_all": None,
            "callback_post_nginx_200_any": None,
            "status_code": None,
            "body": "",
            "error": "probe skipped",
            "probes": [],
        }
        if args.skip_probe
        else (
            _probe_callback_posts(probe_urls, float(args.probe_timeout))
            if probe_urls
            else {
                "callback_post_checked": False,
                "callback_post_nginx_200": None,
                "callback_post_nginx_200_all": None,
                "callback_post_nginx_200_any": None,
                "status_code": None,
                "body": "",
                "error": f"probe url required; pass --probe-url or set {PROBE_URLS_ENV}/{PROBE_URL_ENV}",
                "probes": [],
            }
        )
    )
    emergency_enabled = bool(nginx_state["emergency_quick_ack_enabled"])
    recent_events = db_state.get("recent_app_callback_events")
    business_processing_suppressed = bool(emergency_enabled and recent_events == 0)
    warnings = []
    if emergency_enabled:
        warnings.append("nginx emergency quick ACK is enabled; application callback business processing is bypassed until rollback")
    if emergency_enabled and recent_events not in (0, None):
        warnings.append("recent app callback events were found even though quick ACK appears enabled")
    if db_state.get("error"):
        warnings.append(f"database check unavailable: {db_state['error']}")
    if probe_state.get("error"):
        warnings.append(f"callback POST probe unavailable: {probe_state['error']}")
    ok = bool(nginx_state.get("nginx_config_found")) and not (emergency_enabled and recent_events not in (0, None))
    nginx_error = _text(nginx_state.get("error"))
    database_error = _text(db_state.get("error"))
    callback_post_error = _text(probe_state.get("error"))
    return {
        "ok": ok,
        "emergency_quick_ack_enabled": emergency_enabled,
        "business_processing_suppressed": business_processing_suppressed,
        "recent_window_minutes": int(args.minutes),
        "env_file": str(args.env_file),
        "env_file_loaded": env_file_loaded,
        "nginx_config": nginx_state.get("nginx_config"),
        "nginx_config_found": nginx_state.get("nginx_config_found"),
        "matched_routes": nginx_state.get("matched_routes") or [],
        "quick_ack_routes": nginx_state.get("quick_ack_routes") or [],
        "callback_route_details": nginx_state.get("callback_route_details") or {},
        "nginx_error": nginx_error,
        "database_checked": db_state.get("database_checked"),
        "recent_app_callback_events": recent_events,
        "database_error": database_error,
        "callback_post_checked": probe_state.get("callback_post_checked"),
        "callback_post_nginx_200": probe_state.get("callback_post_nginx_200"),
        "callback_post_nginx_200_all": probe_state.get("callback_post_nginx_200_all"),
        "callback_post_nginx_200_any": probe_state.get("callback_post_nginx_200_any"),
        "callback_post_probe_urls": probe_urls,
        "callback_post_probes": probe_state.get("probes") or [],
        "status_code": probe_state.get("status_code"),
        "body": probe_state.get("body"),
        "callback_post_error": callback_post_error,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    payload = run(argv)
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
