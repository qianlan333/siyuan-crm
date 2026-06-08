#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _read_optional(path: str) -> str:
    file_path = ROOT / path
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def _decorated_routes(path: str) -> set[str]:
    text = _read_optional(path)
    if not text:
        return set()
    tree = ast.parse(text)
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"route", "api_route", "get", "post"}:
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    routes.add(arg.value)
    return routes


def _manifest_record(route_pattern: str) -> dict:
    manifest = yaml.safe_load(_read("docs/route_ownership/production_route_ownership_manifest.yaml"))
    for record in manifest.get("routes") or []:
        if record.get("route_pattern") == route_pattern:
            return dict(record)
    return {}


def main() -> int:
    blockers: list[str] = []
    callback_routes = _decorated_routes("wecom_ability_service/http/callbacks.py")
    for route in {"/wecom/external-contact/callback", "/api/wecom/events"} & callback_routes:
        blockers.append(f"legacy callbacks.py still registers {route}")

    automation_conversion = _read("wecom_ability_service/http/automation_conversion.py")
    for route in (
        "/api/admin/channels/runtime-diagnosis",
        "/api/admin/channels/<int:channel_id>/runtime-diagnosis",
        "/api/admin/channels/runtime-diagnosis/dry-run",
        "/api/admin/channels/repair-entry",
    ):
        if route in automation_conversion:
            blockers.append(f"legacy automation_conversion.py still registers {route}")

    if (ROOT / "wecom_ability_service/http/channel_runtime_diagnosis.py").exists():
        blockers.append("legacy channel_runtime_diagnosis.py still exists")
    if (ROOT / "wecom_ability_service/domains/automation_conversion/channel_entry_orchestrator.py").exists():
        blockers.append("legacy channel_entry_orchestrator.py still exists")

    background_jobs = _read("wecom_ability_service/http/background_jobs.py")
    if "HandleQrcodeEnterFromCallbackCommand" in background_jobs:
        blockers.append("legacy background_jobs still imports HandleQrcodeEnterFromCallbackCommand")
    if "qrcode_result = handle_qrcode_enter_from_callback" in background_jobs:
        blockers.append("legacy background_jobs still consumes channel entry callback")

    production_compat = _read_optional("aicrm_next/production_compat/api.py")
    for route in ("/wecom/external-contact/callback", "/api/wecom/events"):
        if route in production_compat:
            blockers.append(f"production_compat still declares {route}")
    if "handle_wecom_callback_via_legacy" in production_compat:
        blockers.append("production_compat still calls handle_wecom_callback_via_legacy")

    callback_facade = _read("aicrm_next/integration_gateway/wecom_callback_facade.py")
    if "async def handle_wecom_callback_via_legacy" in callback_facade or "forward_to_legacy_flask" in callback_facade:
        blockers.append("wecom_callback_facade still exposes legacy callback fallback")

    runtime_sources = [
        "aicrm_next/shared/runtime.py",
        "aicrm_next/channel_entry/application.py",
    ]
    for path in runtime_sources:
        text = _read(path)
        if "AICRM_ALLOW_LEGACY_WECOM_CALLBACK_FALLBACK" in text:
            blockers.append(f"{path} still reads legacy callback fallback env")
        if '"legacy_callback_fallback_enabled": False' not in text:
            blockers.append(f"{path} does not hard-disable legacy_callback_fallback_enabled")

    for path in sorted((ROOT / "aicrm_next/channel_entry").glob("*.py")):
        if "wecom_ability_service" in path.read_text(encoding="utf-8"):
            blockers.append(f"{path.relative_to(ROOT)} imports wecom_ability_service")

    for route in (
        "/wecom/external-contact/callback",
        "/api/wecom/events",
        "/api/admin/channels/runtime-diagnosis",
        "/api/admin/channels/repair-entry",
    ):
        record = _manifest_record(route)
        if record.get("capability_owner") != "aicrm_next.channel_entry":
            blockers.append(f"manifest {route} owner is not aicrm_next.channel_entry")
        if record.get("current_runtime_owner") != "next":
            blockers.append(f"manifest {route} runtime owner is not next")
        if record.get("legacy_fallback_allowed") is not False:
            blockers.append(f"manifest {route} still allows legacy fallback")

    if blockers:
        print("legacy_channel_entry_retired: failed")
        for blocker in blockers:
            print(f"- {blocker}")
        return 1
    print("legacy_channel_entry_retired: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
