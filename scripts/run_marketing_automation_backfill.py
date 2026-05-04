#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import recompute_signup_conversion_customers


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _collect_backfill_targets(*, include_mobile_only: bool) -> list[dict[str, Any]]:
    db = get_db()
    external_rows = db.execute(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid FROM class_user_status_current
            UNION
            SELECT external_userid FROM external_contact_bindings
            UNION
            SELECT external_userid FROM wecom_external_contact_identity_map
            UNION
            SELECT external_userid FROM wecom_external_contact_follow_users
            UNION
            SELECT external_userid FROM user_ops_lead_pool_current
            UNION
            SELECT external_userid FROM archived_messages
            UNION
            SELECT external_userid FROM questionnaire_submissions
        ) AS source_targets
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY external_userid ASC
        """
    ).fetchall()
    targets = [
        {"external_userid": _normalized_text(row["external_userid"]), "person_id": None}
        for row in external_rows
        if _normalized_text(row["external_userid"])
    ]
    if not include_mobile_only:
        return targets
    person_rows = db.execute(
        """
        SELECT p.id AS person_id
        FROM people p
        WHERE NOT EXISTS (
            SELECT 1
            FROM external_contact_bindings b
            WHERE b.person_id = p.id
        )
        ORDER BY p.id ASC
        """
    ).fetchall()
    targets.extend(
        {
            "external_userid": "",
            "person_id": int(row["person_id"]),
        }
        for row in person_rows
        if row["person_id"] is not None
    )
    return targets


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-off marketing automation recompute/backfill")
    parser.add_argument("--external-userid", default="")
    parser.add_argument("--person-id", type=int, default=None)
    parser.add_argument("--all", action="store_true", default=False)
    parser.add_argument("--skip-mobile-only", action="store_true", default=False)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--automation-key", default="signup_conversion_v1")
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args(argv)
    if not args.all and not _normalized_text(args.external_userid) and args.person_id is None:
        parser.error("provide --external-userid / --person-id, or use --all")
    if args.offset < 0:
        parser.error("--offset must be >= 0")
    if args.limit <= 0:
        parser.error("--limit must be >= 1")
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be >= 1")
    return args


def _segment_from_item(item: dict[str, Any]) -> str:
    value_segment = item.get("value_segment") or {}
    if isinstance(value_segment, dict):
        return _normalized_text(value_segment.get("segment")) or "unknown"
    summary = item.get("summary") or {}
    return _normalized_text(summary.get("current_segment")) or "unknown"


def _normalize_item_for_backfill_output(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    summary = dict(normalized.get("summary") or {})
    segment = _segment_from_item(normalized)
    if summary:
        summary["current_segment"] = segment
        normalized["summary"] = summary
    return normalized


def _build_summary(*, successes: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    segment_distribution = Counter(_segment_from_item(item) for item in successes)
    return {
        "processed_total": len(successes) + len(failures),
        "success_count": len(successes),
        "failure_count": len(failures),
        "segment_distribution": dict(sorted(segment_distribution.items())),
    }


def _run_single_target(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str,
    dry_run: bool,
) -> dict[str, Any]:
    payload = recompute_signup_conversion_customers(
        external_userid=external_userid,
        person_id=person_id,
        automation_key=automation_key,
        persist=not dry_run,
    )
    item = dict(payload.get("item") or {})
    item["dry_run"] = bool(dry_run)
    return _normalize_item_for_backfill_output(item)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app = create_app()
    try:
        with app.app_context():
            init_db()
            if args.all:
                enumerated_targets = _collect_backfill_targets(include_mobile_only=not args.skip_mobile_only)
                selected_targets = enumerated_targets[args.offset : args.offset + args.limit]
                result_items: list[dict[str, Any]] = []
                failures: list[dict[str, Any]] = []
                for chunk in _chunked(selected_targets, args.chunk_size):
                    for target in chunk:
                        try:
                            result_items.append(
                                _run_single_target(
                                    external_userid=_normalized_text(target.get("external_userid")),
                                    person_id=target.get("person_id"),
                                    automation_key=args.automation_key,
                                    dry_run=args.dry_run,
                                )
                            )
                        except Exception as exc:
                            failures.append(
                                {
                                    "target": {
                                        "external_userid": _normalized_text(target.get("external_userid")),
                                        "person_id": target.get("person_id"),
                                    },
                                    "error": str(exc),
                                }
                            )
                summary = _build_summary(successes=result_items, failures=failures)
                output = {
                    "ok": True,
                    "mode": "backfill",
                    "dry_run": bool(args.dry_run),
                    "automation_key": args.automation_key,
                    "enumerated_total": len(enumerated_targets),
                    "selected_count": len(selected_targets),
                    "processed_count": summary["processed_total"],
                    "success_count": summary["success_count"],
                    "failure_count": summary["failure_count"],
                    "segment_distribution": summary["segment_distribution"],
                    "offset": args.offset,
                    "limit": args.limit,
                    "chunk_size": args.chunk_size,
                    "include_mobile_only": not args.skip_mobile_only,
                    "items": result_items,
                    "failures": failures,
                }
            else:
                failures: list[dict[str, Any]] = []
                items: list[dict[str, Any]] = []
                try:
                    items.append(
                        _run_single_target(
                            external_userid=args.external_userid,
                            person_id=args.person_id,
                            automation_key=args.automation_key,
                            dry_run=args.dry_run,
                        )
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "target": {
                                "external_userid": _normalized_text(args.external_userid),
                                "person_id": args.person_id,
                            },
                            "error": str(exc),
                        }
                    )
                summary = _build_summary(successes=items, failures=failures)
                output = {
                    "ok": True,
                    "mode": "single",
                    "dry_run": bool(args.dry_run),
                    "automation_key": args.automation_key,
                    "processed_count": summary["processed_total"],
                    "success_count": summary["success_count"],
                    "failure_count": summary["failure_count"],
                    "segment_distribution": summary["segment_distribution"],
                    "items": items,
                    "failures": failures,
                }
                if items:
                    output["count"] = 1
                    output["item"] = items[0]
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
