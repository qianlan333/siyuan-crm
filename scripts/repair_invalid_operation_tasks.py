from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.automation_engine.operation_task_contract import publishable_diagnostics
from wecom_ability_service import create_app
from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import operation_task_repo as task_repo


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run/apply bounded repair for invalid active operation tasks.")
    parser.add_argument("--program-id", type=int, required=True)
    parser.add_argument("--task-id", type=int, action="append", required=True)
    parser.add_argument("--action", choices=["pause", "patch-agent-fallback", "patch-behavior-segments"], required=True)
    parser.add_argument("--fallback-content", default="")
    parser.add_argument(
        "--segment",
        action="append",
        default=[],
        help="Behavior segment content as key=text, e.g. --segment lt_2='...'.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--operator-id", default="invalid_operation_task_repair")
    return parser.parse_args(argv)


def _parse_segments(raw_items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in raw_items or []:
        key, sep, value = str(raw or "").partition("=")
        key = key.strip()
        value = value.strip()
        if not sep or not key:
            raise ValueError("segment must use key=text")
        if key not in {"lt_2", "between_2_9", "gte_10"}:
            raise ValueError(f"unsupported behavior segment: {key}")
        if not value:
            raise ValueError(f"segment content_text is required: {key}")
        parsed[key] = value
    return parsed


def _required_behavior_segments(task: dict[str, Any]) -> list[str]:
    behavior_filter = str(task.get("behavior_filter") or "none").strip() or "none"
    if behavior_filter == "none":
        return ["lt_2", "between_2_9", "gte_10"]
    if behavior_filter in {"lt_2", "between_2_9", "gte_10"}:
        return [behavior_filter]
    raise ValueError(f"unsupported behavior_filter for behavior_layered repair: {behavior_filter}")


def _patch_behavior_segments(task: dict[str, Any], raw_segments: list[str]) -> dict[str, Any]:
    if str(task.get("content_mode") or "").strip() != "behavior_layered":
        raise ValueError("patch-behavior-segments only supports behavior_layered tasks")
    segments = _parse_segments(raw_segments)
    required = _required_behavior_segments(task)
    missing = [key for key in required if key not in segments]
    if missing:
        raise ValueError(f"missing required behavior segments: {','.join(missing)}")
    existing_by_key = {
        str(item.get("segment_key") or "").strip(): dict(item)
        for item in list(task.get("segment_contents_json") or [])
        if str(item.get("segment_key") or "").strip()
    }
    for key, text in segments.items():
        existing_by_key[key] = {
            **existing_by_key.get(key, {}),
            "segment_key": key,
            "content_text": text,
        }
    patched = dict(task)
    patched["segment_contents_json"] = [existing_by_key[key] for key in ["lt_2", "between_2_9", "gte_10"] if key in existing_by_key]
    return patched


def repair(args: argparse.Namespace) -> dict[str, Any]:
    dry_run = not bool(args.apply) or bool(args.dry_run)
    results: list[dict[str, Any]] = []
    for task_id in sorted(dict.fromkeys(int(item) for item in args.task_id or [])):
        task = task_repo.get_task(task_id)
        if not task or int(task.get("program_id") or 0) != int(args.program_id):
            results.append({"task_id": task_id, "ok": False, "reason": "task_not_found"})
            continue
        after = dict(task)
        if args.action == "pause":
            after["status"] = "paused"
        elif args.action == "patch-agent-fallback":
            fallback = str(args.fallback_content or "").strip()
            if not fallback:
                results.append({"task_id": task_id, "ok": False, "reason": "fallback_content_required"})
                continue
            agent = dict(after.get("agent_config_json") or {})
            agent["fallback_content"] = fallback
            after["agent_config_json"] = agent
        elif args.action == "patch-behavior-segments":
            try:
                after = _patch_behavior_segments(after, list(args.segment or []))
            except ValueError as exc:
                results.append({"task_id": task_id, "ok": False, "reason": str(exc)})
                continue
        after["updated_by"] = args.operator_id
        before_diagnostics = publishable_diagnostics(task)
        after_diagnostics = publishable_diagnostics(after)
        if args.action != "pause" and not after_diagnostics.get("ok"):
            results.append(
                {
                    "task_id": task_id,
                    "ok": False,
                    "reason": "publishable_diagnostics_failed_after_patch",
                    "publishable_diagnostics": after_diagnostics,
                }
            )
            continue
        result = {
            "task_id": task_id,
            "task_name": task.get("task_name") or "",
            "action": args.action,
            "dry_run": dry_run,
            "before": {
                "status": task.get("status"),
                "content_mode": task.get("content_mode"),
                "agent_config_json": task.get("agent_config_json"),
                "segment_contents_json": task.get("segment_contents_json"),
                "publishable_diagnostics": before_diagnostics,
            },
            "after": {
                "status": after.get("status"),
                "content_mode": after.get("content_mode"),
                "agent_config_json": after.get("agent_config_json"),
                "segment_contents_json": after.get("segment_contents_json"),
                "publishable_diagnostics": after_diagnostics,
            },
            "ok": True,
        }
        if not dry_run:
            updated = task_repo.update_task(task_id, after)
            updated_diagnostics = publishable_diagnostics(updated)
            if args.action != "pause" and not updated_diagnostics.get("ok"):
                get_db().rollback()
                results.append(
                    {
                        "task_id": task_id,
                        "ok": False,
                        "reason": "publishable_diagnostics_failed_after_apply",
                        "publishable_diagnostics": updated_diagnostics,
                    }
                )
                continue
            result["applied_publishable_diagnostics"] = updated_diagnostics
        results.append(result)
    if not dry_run:
        get_db().commit()
    return {"ok": True, "dry_run": dry_run, "program_id": int(args.program_id), "results": results}


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    app = create_app()
    with app.app_context():
        result = repair(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
