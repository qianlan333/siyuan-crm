#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _read_optional(path: str) -> str:
    file_path = ROOT / path
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8")


def main() -> int:
    blockers: list[str] = []
    production_compat = _read_optional("aicrm_next/production_compat/api.py")
    if "/wecom/external-contact/callback" in production_compat and "handle_wecom_callback_via_legacy" in production_compat:
        blockers.append("callback route still defaults to handle_wecom_callback_via_legacy")
    if "/api/wecom/events" in production_compat and "handle_wecom_callback_via_legacy" in production_compat:
        blockers.append("events route still defaults to handle_wecom_callback_via_legacy")
    if "handle_wecom_callback_via_legacy" in production_compat:
        blockers.append("production_compat still imports or calls handle_wecom_callback_via_legacy")

    channel_entry_dir = ROOT / "aicrm_next" / "channel_entry"
    if not channel_entry_dir.exists():
        blockers.append("aicrm_next/channel_entry is missing")
    else:
        for path in sorted(channel_entry_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "wecom_ability_service" in text:
                blockers.append(f"{path.relative_to(ROOT)} imports or references wecom_ability_service")

    runtime = _read("aicrm_next/shared/runtime.py")
    if '"next_live_callback_gateway_enabled": False' in runtime:
        blockers.append("runtime_route_map_state still fixes next_live_callback_gateway_enabled=false")
    if "aicrm_next.channel_entry.api" not in runtime:
        blockers.append("runtime_route_map_state does not name aicrm_next.channel_entry.api")

    main_py = _read("aicrm_next/main.py")
    if "channel_entry_router" not in main_py:
        blockers.append("aicrm_next.main does not include channel_entry_router")

    channels_api = _read("aicrm_next/automation_engine/channels_api.py")
    if "historical_scene_values" in channels_api and "wecom_external_contact_event_logs e" in channels_api and "automation_member m" in channels_api:
        blockers.append("channels_api still uses event_logs + automation_member as historical_scene_values primary source")
    if "upsert_channel_scene_alias" in channels_api:
        blockers.append("channel save/update still mutates automation_channel_scene_alias")
    channel_entry_app = _read("aicrm_next/channel_entry/application.py")
    channel_entry_repo = _read("aicrm_next/channel_entry/repo.py")
    if "insert_qrcode_asset" not in channel_entry_app or "automation_channel_qrcode_asset" not in channel_entry_repo:
        blockers.append("qrcode generate path does not maintain automation_channel_qrcode_asset")

    manifest = _read("docs/route_ownership/production_route_ownership_manifest.yaml")
    for route in (
        "/wecom/external-contact/callback",
        "/api/wecom/events",
        "/api/admin/channels/runtime-diagnosis",
        "/api/admin/channels/{channel_id}/qrcode/generate",
        "/api/admin/channels/repair-entry",
    ):
        if route not in manifest:
            blockers.append(f"route ownership manifest missing {route}")
    if "capability_owner: aicrm_next.channel_entry" not in manifest:
        blockers.append("route ownership manifest does not name aicrm_next.channel_entry")

    legacy_files = [
        "wecom_ability_service/http/channel_runtime_diagnosis.py",
        "wecom_ability_service/domains/automation_conversion/channel_entry_orchestrator.py",
    ]
    for file_name in legacy_files:
        if "aicrm_next.channel_entry" in _read_optional(file_name):
            blockers.append(f"new channel_entry capability leaked into legacy side: {file_name}")

    if blockers:
        print("channel_entry_next_owner: failed")
        for blocker in blockers:
            print(f"- {blocker}")
        return 1
    print("channel_entry_next_owner: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
