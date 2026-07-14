#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Mapping
from typing import Any, Protocol

import requests


FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_TOKEN_ENV = "AICRM_RUNTIME_ROUTE_READ_TOKEN"


class HttpSession(Protocol):
    def get(self, url: str, *, headers: dict[str, str], timeout: float): ...


def _result(
    *,
    expected_sha: str,
    blocking_reasons: list[str],
    evidence: dict[str, Any] | None = None,
    probes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ok = not blocking_reasons
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "expected_release_sha": expected_sha,
        "blocking_reasons": list(blocking_reasons),
        "evidence": dict(evidence or {}),
        "probes": dict(probes or {}),
        "real_external_call_executed": False,
        "production_write_executed": False,
        "secrets_in_output": False,
        "pii_in_output": False,
    }


def _json_payload(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _release_header(response: Any) -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("x-aicrm-release-sha") or headers.get("X-AICRM-Release-SHA") or "").strip().lower()


def _probe_get(
    session: HttpSession,
    *,
    url: str,
    headers: dict[str, str],
    timeout: float,
    probe_name: str,
) -> tuple[Any | None, dict[str, Any], str]:
    try:
        response = session.get(url, headers=headers, timeout=timeout)
    except Exception as exc:
        return None, {}, f"{probe_name}_request_failed:{exc.__class__.__name__}"
    payload = _json_payload(response)
    return response, payload, ""


def run_check(
    *,
    base_url: str,
    expected_sha: str,
    token_env: str = DEFAULT_TOKEN_ENV,
    env: Mapping[str, str] | None = None,
    session: HttpSession | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    normalized_sha = str(expected_sha or "").strip().lower()
    environment = os.environ if env is None else env
    token = str(environment.get(token_env, "") or "").strip()

    if not normalized_base_url:
        return _result(expected_sha=normalized_sha, blocking_reasons=["base_url_required"])
    if not FULL_SHA_PATTERN.fullmatch(normalized_sha):
        return _result(expected_sha=normalized_sha, blocking_reasons=["expected_exact_sha_required"])
    if not token:
        return _result(expected_sha=normalized_sha, blocking_reasons=["runtime_route_read_token_required"])

    client = session or requests.Session()
    probes: dict[str, Any] = {}
    evidence: dict[str, Any] = {}

    health_response, health, error = _probe_get(
        client,
        url=f"{normalized_base_url}/health",
        headers={},
        timeout=timeout,
        probe_name="liveness",
    )
    if error:
        return _result(expected_sha=normalized_sha, blocking_reasons=[error], probes=probes)
    health_status = int(getattr(health_response, "status_code", 0) or 0)
    health_header = _release_header(health_response)
    probes["liveness"] = {"status_code": health_status, "release_sha": health_header, "payload": health}
    liveness_reasons: list[str] = []
    if health_status != 200:
        liveness_reasons.append(f"liveness_http_status:{health_status}")
    if health_header != normalized_sha:
        liveness_reasons.append("liveness_release_header_mismatch")
    if health.get("ok") is not True:
        liveness_reasons.append("liveness_not_ok")
    if health.get("legacy_runtime_enabled") is not False:
        liveness_reasons.append("legacy_runtime_state_invalid")
    if liveness_reasons:
        return _result(expected_sha=normalized_sha, blocking_reasons=liveness_reasons, probes=probes)

    readiness_response, readiness, error = _probe_get(
        client,
        url=f"{normalized_base_url}/api/system/health",
        headers={},
        timeout=timeout,
        probe_name="readiness",
    )
    if error:
        return _result(expected_sha=normalized_sha, blocking_reasons=[error], probes=probes)
    readiness_status = int(getattr(readiness_response, "status_code", 0) or 0)
    readiness_header = _release_header(readiness_response)
    probes["readiness"] = {"status_code": readiness_status, "release_sha": readiness_header, "payload": readiness}
    release_component = dict((readiness.get("components") or {}).get("release") or {})
    readiness_reasons: list[str] = []
    if readiness_status != 200:
        readiness_reasons.append(f"readiness_http_status:{readiness_status}")
    if readiness_header != normalized_sha:
        readiness_reasons.append("readiness_release_header_mismatch")
    if readiness.get("ok") is not True or readiness.get("status") != "ready":
        readiness_reasons.append("runtime_not_ready")
    if readiness.get("failed_components"):
        readiness_reasons.append("readiness_failed_components_present")
    if release_component.get("release_sha") != normalized_sha or release_component.get("exact_sha") is not True:
        readiness_reasons.append("readiness_release_sha_mismatch")
    if readiness_reasons:
        return _result(expected_sha=normalized_sha, blocking_reasons=readiness_reasons, probes=probes)

    route_response, route_map, error = _probe_get(
        client,
        url=f"{normalized_base_url}/api/system/runtime-route-map",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        probe_name="runtime_route_map",
    )
    if error:
        return _result(expected_sha=normalized_sha, blocking_reasons=[error], probes=probes)
    route_status = int(getattr(route_response, "status_code", 0) or 0)
    route_header = _release_header(route_response)
    probes["runtime_route_map"] = {
        "status_code": route_status,
        "release_sha": route_header,
        "payload": route_map,
        "authentication": "service_bearer",
    }
    route_reasons: list[str] = []
    if route_status != 200:
        route_reasons.append(f"runtime_route_map_http_status:{route_status}")
    if route_header != normalized_sha:
        route_reasons.append("runtime_route_map_release_header_mismatch")
    web_sha = str(route_map.get("web_release_sha") or "").strip().lower()
    worker_sha = str(route_map.get("worker_release_sha") or "").strip().lower()
    if web_sha != normalized_sha:
        route_reasons.append("web_release_sha_mismatch")
    if worker_sha != normalized_sha:
        route_reasons.append("worker_release_sha_mismatch")
    if route_map.get("route_owner") != "ai_crm_next":
        route_reasons.append("runtime_route_owner_mismatch")
    if route_map.get("legacy_callback_fallback_enabled") is not False:
        route_reasons.append("legacy_callback_fallback_enabled")
    if route_reasons:
        return _result(expected_sha=normalized_sha, blocking_reasons=route_reasons, probes=probes)

    evidence.update(
        {
            "web_release_sha": web_sha,
            "worker_release_sha": worker_sha,
            "database_status": str((readiness.get("components") or {}).get("database", {}).get("status") or ""),
            "migration_status": str((readiness.get("components") or {}).get("migration", {}).get("status") or ""),
            "queue_status": str((readiness.get("components") or {}).get("queues", {}).get("status") or ""),
            "wecom_status": str((readiness.get("components") or {}).get("wecom", {}).get("status") or ""),
            "runtime_route_auth": "service_bearer_verified",
            "legacy_callback_fallback_enabled": False,
        }
    )
    return _result(expected_sha=normalized_sha, blocking_reasons=[], evidence=evidence, probes=probes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the exact live AI-CRM web and worker runtime readiness.")
    parser.add_argument("--base-url", default=os.getenv("AICRM_BASE_URL", ""))
    parser.add_argument("--expected-sha", default=os.getenv("AICRM_EXPECTED_RELEASE_SHA", ""))
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_check(
        base_url=args.base_url,
        expected_sha=args.expected_sha,
        token_env=args.token_env,
        timeout=max(0.1, float(args.timeout)),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        from pathlib import Path

        Path(args.output_json).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
