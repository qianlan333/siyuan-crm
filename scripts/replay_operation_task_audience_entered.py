from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.domains.automation_conversion.operation_task_replay_service import (
    replay_audience_entered_operation_task,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run/apply a bounded operation_task audience_entered replay.")
    parser.add_argument("--program-id", type=int, required=True)
    parser.add_argument("--external-userid", action="append", default=[])
    parser.add_argument("--member-id", type=int, default=0)
    parser.add_argument("--audience-entry-id", type=int, action="append", default=[])
    parser.add_argument("--task-id", type=int, action="append", required=True)
    parser.add_argument("--apply", action="store_true", help="Write retry execution/job. Omitted means dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run; default when --apply is omitted.")
    parser.add_argument("--allow-failed-empty-execution-retry", action="store_true")
    parser.add_argument("--operator-id", default="operation_task_replay")
    return parser.parse_args(argv)


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _scopes(args: argparse.Namespace) -> list[dict[str, Any]]:
    external_userids = [str(item or "").strip() for item in list(args.external_userid or []) if str(item or "").strip()]
    entry_ids = [int(item or 0) for item in list(args.audience_entry_id or []) if int(item or 0) > 0]
    member_id = int(args.member_id or 0)
    if not external_userids and not entry_ids and member_id <= 0:
        return [{"external_userid": "", "member_id": 0, "audience_entry_id": 0}]
    if member_id > 0 and not external_userids and not entry_ids:
        return [{"external_userid": "", "member_id": member_id, "audience_entry_id": 0}]
    if external_userids and entry_ids:
        if len(external_userids) == len(entry_ids):
            return [
                {"external_userid": external_userid, "member_id": member_id if len(external_userids) == 1 else 0, "audience_entry_id": entry_id}
                for external_userid, entry_id in zip(external_userids, entry_ids, strict=False)
            ]
        if len(external_userids) == 1:
            return [
                {"external_userid": external_userids[0], "member_id": member_id if len(entry_ids) == 1 else 0, "audience_entry_id": entry_id}
                for entry_id in entry_ids
            ]
        if len(entry_ids) == 1:
            return [
                {"external_userid": external_userid, "member_id": 0, "audience_entry_id": entry_ids[0]}
                for external_userid in external_userids
            ]
        raise ValueError("--external-userid and --audience-entry-id counts must match, unless one side has exactly one value")
    if external_userids:
        return [
            {"external_userid": external_userid, "member_id": member_id if len(external_userids) == 1 else 0, "audience_entry_id": 0}
            for external_userid in external_userids
        ]
    return [{"external_userid": "", "member_id": member_id if len(entry_ids) == 1 else 0, "audience_entry_id": entry_id} for entry_id in entry_ids]


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    dry_run = not bool(args.apply)
    if args.dry_run:
        dry_run = True
    app = create_app()
    with app.app_context():
        scopes = _scopes(args)
        results = [
            replay_audience_entered_operation_task(
                program_id=int(args.program_id),
                external_userid=str(scope.get("external_userid") or ""),
                member_id=int(scope.get("member_id") or 0),
                audience_entry_id=int(scope.get("audience_entry_id") or 0),
                task_ids=[int(item) for item in args.task_id or []],
                dry_run=dry_run,
                allow_failed_empty_execution_retry=bool(args.allow_failed_empty_execution_retry),
                operator_id=args.operator_id,
            )
            for scope in scopes
        ]
    result = results[0] if len(results) == 1 else {"ok": all(item.get("ok") for item in results), "dry_run": dry_run, "program_id": int(args.program_id), "batch_count": len(results), "results": results}
    _emit(result)


if __name__ == "__main__":
    main()
