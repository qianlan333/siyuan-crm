from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aicrm_next.channel_entry.wecom_adapter import get_wecom_adapter, wecom_adapter_diagnostics
from aicrm_next.customer_tags.questionnaire_projection import apply_questionnaire_tag_projection
from aicrm_next.shared.database import get_database_url


def _psycopg_url() -> str:
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _fetch_targets(conn, *, questionnaire_id: int | None = None) -> list[dict[str, Any]]:
    where = ["COALESCE(qs.external_userid, '') <> ''", "jsonb_array_length(COALESCE(qs.final_tags, '[]'::jsonb)) > 0"]
    params: list[Any] = []
    if questionnaire_id is not None:
        where.append("qs.questionnaire_id = %s")
        params.append(questionnaire_id)
    sql = f"""
        SELECT
            qs.id AS submission_id,
            qs.questionnaire_id,
            qs.external_userid,
            qs.final_tags,
            COALESCE(
                NULLIF(qs.follow_user_userid, ''),
                NULLIF(qs.staff_id, ''),
                (
                    SELECT NULLIF(ct.userid, '')
                    FROM contact_tags ct
                    WHERE ct.external_userid = qs.external_userid
                    ORDER BY ct.created_at DESC NULLS LAST, ct.id DESC
                    LIMIT 1
                ),
                (
                    SELECT NULLIF(fu.user_id, '')
                    FROM wecom_external_contact_follow_users fu
                    WHERE fu.external_userid = qs.external_userid
                    ORDER BY fu.is_primary DESC NULLS LAST, fu.updated_at DESC NULLS LAST
                    LIMIT 1
                )
            ) AS follow_user_userid
        FROM questionnaire_submissions qs
        WHERE {' AND '.join(where)}
        ORDER BY qs.external_userid ASC, qs.id ASC
    """
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    by_contact: dict[tuple[str, str], dict[str, Any]] = {}
    missing_follow: list[dict[str, Any]] = []
    for row in cur.fetchall():
        external_userid = _text(row["external_userid"])
        follow_user = _text(row["follow_user_userid"])
        final_tags = _unique(_list(row["final_tags"]))
        if not external_userid or not final_tags:
            continue
        if not follow_user:
            missing_follow.append(
                {
                    "external_userid": external_userid,
                    "submission_id": row["submission_id"],
                    "questionnaire_id": row["questionnaire_id"],
                    "tag_ids": final_tags,
                    "reason": "missing_follow_user_userid",
                }
            )
            continue
        key = (external_userid, follow_user)
        item = by_contact.setdefault(
            key,
            {
                "external_userid": external_userid,
                "follow_user_userid": follow_user,
                "tag_ids": [],
                "submission_ids": [],
                "questionnaire_ids": [],
            },
        )
        item["tag_ids"] = _unique([*item["tag_ids"], *final_tags])
        item["submission_ids"].append(row["submission_id"])
        item["questionnaire_ids"] = _unique([*item["questionnaire_ids"], row["questionnaire_id"]])
    return [*by_contact.values(), *missing_follow]


def _fetch_tag_names(conn, tag_ids: list[str]) -> dict[str, str]:
    if not tag_ids:
        return {}
    cur = conn.cursor()
    cur.execute(
        "SELECT tag_id, tag_name FROM wecom_corp_tags WHERE tag_id = ANY(%s)",
        (tag_ids,),
    )
    return {_text(row["tag_id"]): _text(row["tag_name"]) for row in cur.fetchall()}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def run(args: argparse.Namespace) -> dict[str, Any]:
    import psycopg

    diagnostics = wecom_adapter_diagnostics()
    apply = bool(args.apply)
    if apply and not args.confirm_real_wecom_call:
        raise RuntimeError("--apply requires --confirm-real-wecom-call")
    if apply and not diagnostics.get("can_mark_tag"):
        raise RuntimeError(f"real WeCom mark_tag is not available: {diagnostics}")

    with psycopg.connect(_psycopg_url(), row_factory=psycopg.rows.dict_row) as conn:
        targets = _fetch_targets(conn, questionnaire_id=args.questionnaire_id)
        all_tag_ids = _unique([tag for item in targets for tag in item.get("tag_ids", [])])
        tag_names = _fetch_tag_names(conn, all_tag_ids)

    adapter = get_wecom_adapter() if apply else None
    rows: list[dict[str, Any]] = []
    for item in targets:
        row = {
            **item,
            "tag_names": {tag_id: tag_names.get(tag_id) or tag_id for tag_id in item.get("tag_ids", [])},
            "apply": apply,
        }
        if item.get("reason") == "missing_follow_user_userid":
            row.update({"ok": False, "skipped": True, "wecom_result": {}, "projection": {}})
            rows.append(row)
            continue
        if apply:
            payload = adapter.mark_external_contact_tags(
                external_userid=item["external_userid"],
                follow_user_userid=item["follow_user_userid"],
                add_tags=item["tag_ids"],
                remove_tags=[],
            )
            success = int(payload.get("errcode") or 0) == 0
            projection = (
                apply_questionnaire_tag_projection(
                    external_userid=item["external_userid"],
                    follow_user_userid=item["follow_user_userid"],
                    tag_ids=item["tag_ids"],
                    tag_names=tag_names,
                )
                if success
                else {}
            )
            row.update(
                {
                    "ok": success and bool(projection.get("ok")),
                    "skipped": False,
                    "wecom_result": {"errcode": payload.get("errcode"), "errmsg": payload.get("errmsg", "")},
                    "projection": projection,
                }
            )
        else:
            row.update({"ok": True, "skipped": True, "wecom_result": {}, "projection": {}})
        rows.append(row)

    failed = [row for row in rows if not row.get("ok")]
    output_path = Path(args.output or f"/home/ubuntu/artifacts/questionnaire-real-wecom-tags-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl")
    _write_jsonl(output_path, rows)
    return {
        "ok": not failed,
        "apply": apply,
        "questionnaire_id": args.questionnaire_id,
        "target_count": len(targets),
        "success_count": len(rows) - len(failed),
        "failed_count": len(failed),
        "output_path": str(output_path),
        "diagnostics": diagnostics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill real WeCom tags from questionnaire final_tags.")
    parser.add_argument("--questionnaire-id", type=int, default=None, help="Limit to one questionnaire. Omit for all questionnaires.")
    parser.add_argument("--apply", action="store_true", help="Execute real WeCom mark_tag calls and update local projections.")
    parser.add_argument("--confirm-real-wecom-call", action="store_true", help="Required with --apply to acknowledge real WeCom writes.")
    parser.add_argument("--output", default="", help="JSONL report path.")
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
