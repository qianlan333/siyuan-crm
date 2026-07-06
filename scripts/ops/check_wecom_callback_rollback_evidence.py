#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is True


def evaluate_rollback_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    quick_ack = payload.get("quick_ack_after_restore") if isinstance(payload.get("quick_ack_after_restore"), dict) else {}
    web_health = payload.get("web_health_after_restore") if isinstance(payload.get("web_health_after_restore"), dict) else {}
    requirements = {
        "production_rollback_drill": True,
        "rollback_ready": True,
        "backup_path_present": True,
        "backup_exists": True,
        "nginx_test_after_restore_ok": True,
        "nginx_reload_after_restore_ok": True,
        "web_health_after_restore_ok": True,
        "quick_ack_after_restore_enabled": True,
        "cutover_reapplied_after_drill": True,
    }
    violations: list[str] = []
    if payload.get("ok") is not True:
        violations.append("ok is not true")
    if payload.get("production_rollback_drill") is not True:
        violations.append("production_rollback_drill is not true")
    if payload.get("rollback_ready") is not True:
        violations.append("rollback_ready is not true")
    if not _text(payload.get("backup_path")):
        violations.append("backup_path is empty")
    if payload.get("backup_exists") is not True:
        violations.append("backup_exists is not true")
    if payload.get("nginx_test_after_restore_ok") is not True:
        violations.append("nginx_test_after_restore_ok is not true")
    if payload.get("nginx_reload_after_restore_ok") is not True:
        violations.append("nginx_reload_after_restore_ok is not true")
    if web_health.get("ok") is not True:
        violations.append("web_health_after_restore.ok is not true")
    if quick_ack.get("emergency_quick_ack_enabled") is not True:
        violations.append("quick_ack_after_restore.emergency_quick_ack_enabled is not true")
    if payload.get("cutover_reapplied_after_drill") is not True:
        violations.append("cutover_reapplied_after_drill is not true")

    return {
        "checked": True,
        "ok": not violations,
        "requirements": requirements,
        "backup_path": _text(payload.get("backup_path")),
        "production_rollback_drill": _bool(payload, "production_rollback_drill"),
        "rollback_ready": _bool(payload, "rollback_ready"),
        "backup_exists": _bool(payload, "backup_exists"),
        "nginx_test_after_restore_ok": _bool(payload, "nginx_test_after_restore_ok"),
        "nginx_reload_after_restore_ok": _bool(payload, "nginx_reload_after_restore_ok"),
        "web_health_after_restore": web_health,
        "quick_ack_after_restore": quick_ack,
        "cutover_reapplied_after_drill": _bool(payload, "cutover_reapplied_after_drill"),
        "violations": violations,
        "error": "" if not violations else "; ".join(violations),
    }


def read_rollback_evidence(path: str) -> dict[str, Any]:
    evidence_path = _text(path)
    if not evidence_path:
        return {"checked": False, "ok": None, "path": "", "error": "rollback evidence not provided"}
    try:
        payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"checked": True, "ok": False, "path": evidence_path, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"checked": True, "ok": False, "path": evidence_path, "error": "rollback evidence shape is invalid"}
    result = evaluate_rollback_evidence(payload)
    result["path"] = evidence_path
    return result


def sample_template() -> dict[str, Any]:
    return {
        "ok": True,
        "production_rollback_drill": True,
        "rollback_ready": True,
        "backup_path": "/etc/nginx/sites-enabled/youcangogogo.conf.bak-codex-callback-cutover-YYYYmmddTHHMMSS",
        "backup_exists": True,
        "nginx_test_after_restore_ok": True,
        "nginx_reload_after_restore_ok": True,
        "web_health_after_restore": {"ok": True, "status_code": 200, "latency_ms": 100},
        "quick_ack_after_restore": {"ok": True, "emergency_quick_ack_enabled": True},
        "cutover_reapplied_after_drill": True,
        "notes": [
            "Capture this only after an approved production rollback drill.",
            "cutover_reapplied_after_drill means the permanent 5002 cutover was restored after the emergency rollback check.",
        ],
    }


def run(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parse_args(argv)
    if bool(args.print_template):
        return sample_template()
    return read_rollback_evidence(str(args.evidence_file))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate WeCom callback rollback-drill evidence for production completion.")
    parser.add_argument("--evidence-file", default="", help="JSON captured after an approved production rollback drill.")
    parser.add_argument("--print-template", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = run(argv)
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
