#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.customer_tags.live_mutation import execute_wecom_tag_mutation  # noqa: E402
from aicrm_next.customer_tags.mutation_commands import PlanQuestionnaireTagSideEffectCommand  # noqa: E402
from aicrm_next.integration_gateway.idempotency import make_idempotency_key  # noqa: E402


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _tag_list(value: Any) -> list[str]:
    tags: list[str] = []
    for item in _json_list(value):
        tag = str(item or "").strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _connect(database_url: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_psycopg_url(database_url), row_factory=dict_row)


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False))


def _score_rule_matches(rule: dict[str, Any], score: float) -> bool:
    min_score = rule.get("min_score")
    max_score = rule.get("max_score")
    if min_score is not None and score < float(min_score):
        return False
    if max_score is not None and score > float(max_score):
        return False
    return True


def _score_rule_tags(rules: list[dict[str, Any]], score: float) -> list[str]:
    tags: list[str] = []
    for rule in rules:
        if not _score_rule_matches(rule, score):
            continue
        for tag in _tag_list(rule.get("tag_codes")):
            if tag not in tags:
                tags.append(tag)
    return tags


def _merged_tags(*tag_groups: list[str]) -> list[str]:
    tags: list[str] = []
    for group in tag_groups:
        for tag in group:
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def _load_questionnaires(conn: Any, *, questionnaire_id: int | None, slug: str) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if questionnaire_id is not None:
        where = "WHERE id = %s"
        params.append(int(questionnaire_id))
    elif slug:
        where = "WHERE slug = %s"
        params.append(slug)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT id, slug, title, name
            FROM questionnaires
            {where}
            ORDER BY id ASC
            """,
            tuple(params),
        ).fetchall()
    ]


def _load_rules(conn: Any, questionnaire_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT min_score, max_score, tag_codes
            FROM questionnaire_score_rules
            WHERE questionnaire_id = %s
            ORDER BY sort_order ASC, id ASC
            """,
            (int(questionnaire_id),),
        ).fetchall()
    ]


def _load_submission_answer_tags(conn: Any, submission_ids: list[int]) -> dict[int, list[str]]:
    if not submission_ids:
        return {}
    rows = conn.execute(
        """
        SELECT submission_id, selected_option_tags_snapshot
        FROM questionnaire_submission_answers
        WHERE submission_id = ANY(%s)
        ORDER BY id ASC
        """,
        (submission_ids,),
    ).fetchall()
    tags_by_submission: dict[int, list[str]] = {}
    for row in rows:
        submission_id = int(row["submission_id"])
        tags_by_submission[submission_id] = _merged_tags(
            tags_by_submission.get(submission_id, []),
            _tag_list(row.get("selected_option_tags_snapshot")),
        )
    return tags_by_submission


def _plan_questionnaire_tag_apply(
    *,
    questionnaire_id: int,
    submission_id: int,
    external_userid: str,
    tag_ids: list[str],
) -> dict[str, Any]:
    return execute_wecom_tag_mutation(
        PlanQuestionnaireTagSideEffectCommand(
            idempotency_key=make_idempotency_key(
                operation="questionnaire.tag.backfill",
                payload={
                    "questionnaire_id": questionnaire_id,
                    "submission_id": submission_id,
                    "external_userid": external_userid,
                    "tag_ids": sorted(tag_ids),
                },
            ),
            actor_id="questionnaire_tag_backfill",
            actor_type="system",
            external_userid=external_userid,
            tag_ids=tag_ids,
            source_route="scripts/backfill_questionnaire_missing_tags.py",
            source_context={
                "source": "questionnaire_tag_backfill",
                "questionnaire_id": questionnaire_id,
                "submission_id": str(submission_id),
            },
        )
    )


def _append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def backfill(args: argparse.Namespace) -> dict[str, Any]:
    database_url = args.database_url or os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")

    summary = {
        "ok": True,
        "dry_run": not args.apply,
        "questionnaires": 0,
        "submissions_scanned": 0,
        "submissions_with_missing_tags": 0,
        "submissions_updated": 0,
        "tag_plan_created": 0,
        "tag_plan_skipped_missing_external_userid": 0,
        "real_external_call_executed": False,
        "wecom_api_called": False,
    }
    plan_output = Path(args.plan_output) if args.plan_output else None
    with _connect(database_url) as conn:
        questionnaires = _load_questionnaires(conn, questionnaire_id=args.questionnaire_id, slug=args.slug)
        summary["questionnaires"] = len(questionnaires)
        for questionnaire in questionnaires:
            questionnaire_id = int(questionnaire["id"])
            rules = _load_rules(conn, questionnaire_id)
            if not rules:
                continue
            last_id = 0
            while True:
                submissions = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT id, external_userid, total_score, final_tags
                        FROM questionnaire_submissions
                        WHERE questionnaire_id = %s AND id > %s
                        ORDER BY id ASC
                        LIMIT %s
                        """,
                        (questionnaire_id, last_id, int(args.batch_size)),
                    ).fetchall()
                ]
                if not submissions:
                    break
                submission_ids = [int(item["id"]) for item in submissions]
                answer_tags = _load_submission_answer_tags(conn, submission_ids)
                for submission in submissions:
                    submission_id = int(submission["id"])
                    last_id = max(last_id, submission_id)
                    summary["submissions_scanned"] += 1
                    existing_tags = _tag_list(submission.get("final_tags"))
                    computed_tags = _merged_tags(
                        answer_tags.get(submission_id, []),
                        _score_rule_tags(rules, float(submission.get("total_score") or 0)),
                    )
                    missing_tags = [tag for tag in computed_tags if tag not in existing_tags]
                    if not missing_tags:
                        continue
                    summary["submissions_with_missing_tags"] += 1
                    final_tags = _merged_tags(existing_tags, computed_tags)
                    if args.apply:
                        conn.execute(
                            "UPDATE questionnaire_submissions SET final_tags = %s WHERE id = %s",
                            (_jsonb(final_tags), submission_id),
                        )
                        summary["submissions_updated"] += 1
                    external_userid = str(submission.get("external_userid") or "").strip()
                    if args.plan_tags:
                        if not external_userid:
                            summary["tag_plan_skipped_missing_external_userid"] += 1
                        else:
                            plan = _plan_questionnaire_tag_apply(
                                questionnaire_id=questionnaire_id,
                                submission_id=submission_id,
                                external_userid=external_userid,
                                tag_ids=missing_tags,
                            )
                            summary["tag_plan_created"] += 1
                            if plan_output:
                                _append_jsonl(
                                    plan_output,
                                    {
                                        "questionnaire_id": questionnaire_id,
                                        "submission_id": submission_id,
                                        "external_userid": external_userid,
                                        "missing_tags": missing_tags,
                                        "final_tags": final_tags,
                                        "plan": plan,
                                    },
                                )
                    if args.verbose:
                        print(
                            json.dumps(
                                {
                                    "questionnaire_id": questionnaire_id,
                                    "submission_id": submission_id,
                                    "existing_tags": existing_tags,
                                    "missing_tags": missing_tags,
                                    "final_tags": final_tags,
                                    "external_userid_present": bool(external_userid),
                                },
                                ensure_ascii=False,
                            )
                        )
                if args.apply:
                    conn.commit()
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill questionnaire final_tags from answer snapshots and score rules.")
    parser.add_argument("--database-url", default="")
    parser.add_argument("--questionnaire-id", type=int)
    parser.add_argument("--slug", default="")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--apply", action="store_true", help="Update questionnaire_submissions.final_tags.")
    parser.add_argument("--plan-tags", action="store_true", help="Create plan-only questionnaire.tag.apply results for missing tags.")
    parser.add_argument("--plan-output", default="", help="Optional JSONL file for generated tag plans.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(backfill(parse_args()), ensure_ascii=False, sort_keys=True))
