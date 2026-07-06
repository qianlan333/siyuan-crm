#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from uuid import uuid4


Json = dict[str, Any]

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_ANSWERS_JSON = "{}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    return value is True


def _load_json_arg(raw: str, *, arg_name: str) -> Json:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{arg_name} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{arg_name} must decode to a JSON object")
    return value


def _load_answers(args: argparse.Namespace) -> Json:
    if args.answers_file:
        try:
            with open(args.answers_file, "r", encoding="utf-8") as handle:
                return _load_json_arg(handle.read(), arg_name="--answers-file")
        except OSError as exc:
            raise SystemExit(f"failed to read --answers-file: {exc}") from exc
    return _load_json_arg(args.answers_json or DEFAULT_ANSWERS_JSON, arg_name="--answers-json")


def _submit_url(base_url: str, questionnaire_slug: str) -> str:
    base = base_url.rstrip("/")
    slug = urllib.parse.quote(questionnaire_slug.strip(), safe="")
    return f"{base}/api/h5/questionnaires/{slug}/submit"


def build_submission_payload(
    *,
    answers: Json,
    unionid: str,
    external_userid: str,
    follow_user_userid: str,
    source_scene: str,
) -> Json:
    identity = {
        "unionid": unionid,
        "external_userid": external_userid,
        "follow_user_userid": follow_user_userid,
    }
    return {
        "answers": answers,
        "identity": {key: value for key, value in identity.items() if _text(value)},
        "source": {"scene": source_scene},
    }


def post_submission(
    *,
    base_url: str,
    questionnaire_slug: str,
    payload: Json,
    idempotency_key: str,
    timeout_seconds: float,
) -> tuple[int, Json, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _submit_url(base_url, questionnaire_slug),
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": idempotency_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8", errors="replace")
            return int(response.status), _parse_json_body(body_text), body_text
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), _parse_json_body(body_text), body_text


def _parse_json_body(body_text: str) -> Json:
    try:
        value = json.loads(body_text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _list_of_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _expected_tag_seen(body: Json, tag_apply: Json, expected_tag_id: str) -> bool:
    expected = _text(expected_tag_id)
    if not expected:
        return False
    candidate_lists = [
        _list_of_text(tag_apply.get("tag_ids")),
        _list_of_text((tag_apply.get("request_payload") or {}).get("add_tag") if isinstance(tag_apply.get("request_payload"), dict) else []),
        _list_of_text((body.get("result") or {}).get("final_tags") if isinstance(body.get("result"), dict) else []),
    ]
    return any(expected in candidates for candidates in candidate_lists)


def summarize_response(
    *,
    http_status: int,
    body: Json,
    raw_body: str,
    expected_tag_id: str,
    contact_tags_db_rows: list[Json] | None,
    contact_tags_db_error: str,
    require_db_mirror: bool,
) -> Json:
    tag_apply = body.get("tag_apply") if isinstance(body.get("tag_apply"), dict) else {}
    expected_seen = _expected_tag_seen(body, tag_apply, expected_tag_id)
    mirror_from_response = (
        _bool(tag_apply.get("local_projection_updated"))
        or _text(tag_apply.get("contact_tags_mirror_status")) == "updated"
        or _text(tag_apply.get("local_projection_status")) == "updated"
    )
    db_checked = contact_tags_db_rows is not None
    db_found = bool(contact_tags_db_rows)
    mirror_written: bool | None
    if db_checked:
        mirror_written = db_found
    elif mirror_from_response:
        mirror_written = True
    else:
        mirror_written = None

    checks = {
        "http_2xx": 200 <= http_status < 300,
        "tag_apply_succeeded": _text(tag_apply.get("status")) == "succeeded",
        "wecom_api_called": _bool(tag_apply.get("wecom_api_called")),
        "real_external_call_executed": _bool(tag_apply.get("real_external_call_executed")),
        "mark_tag_executed": _bool(tag_apply.get("mark_tag_executed")),
        "expected_tag_id_seen": expected_seen,
        "contact_tags_mirror_written": bool(mirror_written),
    }
    if require_db_mirror:
        checks["contact_tags_db_mirror_found"] = db_found
    ok = all(checks.values())

    return {
        "ok": ok,
        "http_status": http_status,
        "submission_id": body.get("submission_id") or "",
        "questionnaire_id": body.get("questionnaire_id"),
        "questionnaire_slug": body.get("slug") or "",
        "expected_tag_id": expected_tag_id,
        "final_tags": _list_of_text((body.get("result") or {}).get("final_tags") if isinstance(body.get("result"), dict) else []),
        "tag_apply": {
            "status": _text(tag_apply.get("status")),
            "error_code": _text(tag_apply.get("error_code")),
            "reason": _text(tag_apply.get("reason")),
            "wecom_api_called": _bool(tag_apply.get("wecom_api_called")),
            "real_external_call_executed": _bool(tag_apply.get("real_external_call_executed")),
            "mark_tag_executed": _bool(tag_apply.get("mark_tag_executed")),
            "requires_approval": _bool(tag_apply.get("requires_approval")),
            "execution_mode": _text(tag_apply.get("execution_mode")),
            "adapter_mode": _text(tag_apply.get("adapter_mode")),
            "contact_tags_mirror_status": _text(tag_apply.get("contact_tags_mirror_status")),
            "local_projection_updated": _bool(tag_apply.get("local_projection_updated")),
            "request_payload": tag_apply.get("request_payload") if isinstance(tag_apply.get("request_payload"), dict) else {},
            "response_summary": tag_apply.get("response_summary") if isinstance(tag_apply.get("response_summary"), dict) else {},
        },
        "checks": checks,
        "contact_tags_mirror_written": mirror_written,
        "contact_tags_db_checked": db_checked,
        "contact_tags_db_found": db_found,
        "contact_tags_db_rows": contact_tags_db_rows or [],
        "contact_tags_db_error": contact_tags_db_error,
        "manual_wecom_confirmation_required": True,
        "raw_body_preview": raw_body[:1200],
    }


def query_contact_tags_mirror(*, database_url: str, unionid: str, expected_tag_id: str, follow_user_userid: str) -> tuple[list[Json] | None, str]:
    if not _text(database_url):
        return None, ""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:
        return None, f"psycopg_not_installed:{exc}"

    sql = """
        SELECT unionid, userid, tag_id, tag_name, created_at
        FROM contact_tags
        WHERE unionid = %s
          AND tag_id = %s
          AND (%s = '' OR userid = %s)
        ORDER BY created_at DESC
        LIMIT 10
    """
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (unionid, expected_tag_id, follow_user_userid, follow_user_userid))
                rows = [dict(row) for row in cursor.fetchall()]
                for row in rows:
                    row["created_at"] = _text(row.get("created_at"))
                return rows, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a questionnaire and verify final_tags caused a real WeCom mark_tag result.",
    )
    parser.add_argument("--base-url", default=os.getenv("AICRM_SMOKE_BASE_URL") or os.getenv("AICRM_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--questionnaire-slug", required=True)
    parser.add_argument("--unionid", required=True)
    parser.add_argument("--external-userid", required=True)
    parser.add_argument("--follow-user-userid", required=True)
    parser.add_argument("--expected-tag-id", required=True)
    parser.add_argument("--answers-json", default=os.getenv("AICRM_SMOKE_ANSWERS_JSON") or DEFAULT_ANSWERS_JSON)
    parser.add_argument("--answers-file", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--source-scene", default="smoke_questionnaire_real_wecom_tag")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--require-db-mirror", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    answers = _load_answers(args)
    idempotency_key = args.idempotency_key or f"smoke-questionnaire-real-wecom-tag-{int(time.time())}-{uuid4().hex[:8]}"
    payload = build_submission_payload(
        answers=answers,
        unionid=args.unionid,
        external_userid=args.external_userid,
        follow_user_userid=args.follow_user_userid,
        source_scene=args.source_scene,
    )

    http_status, body, raw_body = post_submission(
        base_url=args.base_url,
        questionnaire_slug=args.questionnaire_slug,
        payload=payload,
        idempotency_key=idempotency_key,
        timeout_seconds=args.timeout_seconds,
    )
    contact_rows, contact_error = query_contact_tags_mirror(
        database_url=args.database_url,
        unionid=args.unionid,
        expected_tag_id=args.expected_tag_id,
        follow_user_userid=args.follow_user_userid,
    )
    summary = summarize_response(
        http_status=http_status,
        body=body,
        raw_body=raw_body,
        expected_tag_id=args.expected_tag_id,
        contact_tags_db_rows=contact_rows,
        contact_tags_db_error=contact_error,
        require_db_mirror=args.require_db_mirror,
    )
    summary["request"] = {
        "base_url": args.base_url.rstrip("/"),
        "questionnaire_slug": args.questionnaire_slug,
        "unionid": args.unionid,
        "external_userid": args.external_userid,
        "follow_user_userid": args.follow_user_userid,
        "expected_tag_id": args.expected_tag_id,
        "idempotency_key": idempotency_key,
        "answers_keys": sorted(answers.keys()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
