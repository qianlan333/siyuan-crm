from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.automation_engine.operation_task_contract import agent_runtime_diagnostics, publishable_diagnostics
from wecom_ability_service import create_app
from wecom_ability_service.domains.automation_conversion import operation_task_repo as task_repo


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit active operation_task runtime contract for one program.")
    parser.add_argument("--program-id", type=int, required=True)
    return parser.parse_args(argv)


def _recommend(diagnostics: dict[str, Any]) -> str:
    errors = set(diagnostics.get("errors") or [])
    if not errors:
        return "none"
    if "agent_runtime_content_missing" in errors or "content_missing" in errors or "behavior_segment_content_missing" in errors:
        return "configure_content"
    return "pause_task"


def audit(program_id: int) -> dict[str, Any]:
    tasks = task_repo.list_tasks(int(program_id), status="active")
    items: list[dict[str, Any]] = []
    for task in tasks:
        diagnostics = publishable_diagnostics(task)
        items.append(
            {
                "task_id": int(task.get("id") or 0),
                "task_name": task.get("task_name") or "",
                "status": task.get("status") or "",
                "trigger_type": task.get("trigger_type") or "",
                "content_mode": task.get("content_mode") or "",
                "publishable_diagnostics": diagnostics,
                "agent_runtime_diagnostics": agent_runtime_diagnostics(task) if task.get("content_mode") == "agent" else {},
                "recommended_action": _recommend(diagnostics),
            }
        )
    invalid = [item for item in items if not item["publishable_diagnostics"].get("ok")]
    return {
        "ok": True,
        "program_id": int(program_id),
        "active_task_count": len(items),
        "invalid_task_count": len(invalid),
        "tasks": items,
    }


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    app = create_app()
    with app.app_context():
        result = audit(int(args.program_id))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
