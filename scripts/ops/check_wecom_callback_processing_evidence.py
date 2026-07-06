#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.ops.check_wecom_callback_ingestion_evidence import (
        DEFAULT_ENV_FILE,
        DEFAULT_MAX_AGE_SECONDS,
        EXPECTED_EVENT_FAMILY,
        EXPECTED_PROVIDER,
        _load_env_file,
        _psycopg_url,
        _text,
        read_pressure_evidence,
    )
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from check_wecom_callback_ingestion_evidence import (
        DEFAULT_ENV_FILE,
        DEFAULT_MAX_AGE_SECONDS,
        EXPECTED_EVENT_FAMILY,
        EXPECTED_PROVIDER,
        _load_env_file,
        _psycopg_url,
        _text,
        read_pressure_evidence,
    )
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def query_processed_webhook_row(database_url: str, idempotency_key: str) -> dict[str, Any] | None:
    url = _psycopg_url(_text(database_url))
    if not url:
        raise ValueError("DATABASE_URL is empty")
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.webhook_inbox') AS table_name")
        table_name = _text((cur.fetchone() or {}).get("table_name"))
        if not table_name:
            raise ValueError("webhook_inbox table missing")
        cur.execute(
            """
            SELECT
                id,
                tenant_id,
                provider,
                event_family,
                event_type,
                change_type,
                idempotency_key,
                status,
                attempt_count,
                processing_summary_json,
                received_at,
                started_at,
                finished_at,
                COALESCE(
                    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - COALESCE(finished_at, updated_at, last_seen_at, received_at)),
                    999999999
                ) AS age_seconds
            FROM webhook_inbox
            WHERE tenant_id = 'aicrm'
              AND provider = %s
              AND event_family = %s
              AND idempotency_key = %s
            ORDER BY COALESCE(finished_at, updated_at, last_seen_at, received_at) DESC, id DESC
            LIMIT 1
            """,
            (EXPECTED_PROVIDER, EXPECTED_EVENT_FAMILY, idempotency_key),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def evaluate_processing_row(
    row: dict[str, Any] | None,
    *,
    idempotency_key: str,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    require_canary_noop: bool = True,
) -> dict[str, Any]:
    requirements = {
        "provider": EXPECTED_PROVIDER,
        "event_family": EXPECTED_EVENT_FAMILY,
        "status": "succeeded",
        "max_age_seconds": int(max_age_seconds),
        "require_canary_noop": bool(require_canary_noop),
        "requires_started_at": True,
        "requires_finished_at": True,
    }
    if not row:
        return {
            "checked": True,
            "ok": False,
            "idempotency_key": idempotency_key,
            "requirements": requirements,
            "webhook_inbox_row": {"found": False},
            "violations": ["processed webhook_inbox row not found"],
            "error": "processed webhook_inbox row not found for idempotency_key",
        }

    summary = row.get("processing_summary_json") if isinstance(row.get("processing_summary_json"), dict) else {}
    age_seconds = _int(row.get("age_seconds"))
    violations: list[str] = []
    if _text(row.get("provider")) != EXPECTED_PROVIDER:
        violations.append("provider mismatch")
    if _text(row.get("event_family")) != EXPECTED_EVENT_FAMILY:
        violations.append("event_family mismatch")
    if _text(row.get("idempotency_key")) != idempotency_key:
        violations.append("idempotency_key mismatch")
    if _text(row.get("status")) != "succeeded":
        violations.append("status is not succeeded")
    if not _text(row.get("started_at")):
        violations.append("started_at is empty")
    if not _text(row.get("finished_at")):
        violations.append("finished_at is empty")
    if age_seconds > int(max_age_seconds):
        violations.append(f"processed row age {age_seconds} exceeds {int(max_age_seconds)} seconds")
    if require_canary_noop:
        if _text(row.get("change_type")) != "del_external_contact":
            violations.append("change_type is not the default non-entry canary type")
        if summary.get("handled") is not False:
            violations.append("processing_summary_json.handled is not false")
        if _text(summary.get("identity_sync_status")) != "skipped":
            violations.append("processing_summary_json.identity_sync_status is not skipped")
        if summary.get("external_effect_job_ids") not in ([], None):
            violations.append("external_effect_job_ids is not empty")

    row_summary = {
        "found": True,
        "id": _int(row.get("id")),
        "tenant_id": _text(row.get("tenant_id")),
        "provider": _text(row.get("provider")),
        "event_family": _text(row.get("event_family")),
        "event_type": _text(row.get("event_type")),
        "change_type": _text(row.get("change_type")),
        "idempotency_key": _text(row.get("idempotency_key")),
        "status": _text(row.get("status")),
        "attempt_count": _int(row.get("attempt_count")),
        "received_at": _iso(row.get("received_at")),
        "started_at": _iso(row.get("started_at")),
        "finished_at": _iso(row.get("finished_at")),
        "age_seconds": age_seconds,
        "processing_summary_json": summary,
    }
    return {
        "checked": True,
        "ok": not violations,
        "idempotency_key": idempotency_key,
        "requirements": requirements,
        "webhook_inbox_row": row_summary,
        "violations": violations,
        "error": "" if not violations else "; ".join(violations),
    }


def run(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parse_args(argv)
    env_loaded = _load_env_file(str(args.env_file))
    evidence = read_pressure_evidence(str(args.pressure_evidence_file))
    idempotency_key = _text(args.idempotency_key) or _text(evidence.get("idempotency_key"))
    if not idempotency_key:
        return {
            "ok": False,
            "env_file": str(args.env_file),
            "env_file_loaded": env_loaded,
            "pressure_evidence": evidence,
            "idempotency_key": "",
            "webhook_inbox_row": {"found": False},
            "warnings": ["idempotency_key is required to prove webhook_inbox processing"],
            "error": "idempotency_key is missing",
        }
    database_url = _psycopg_url(_text(args.database_url) or _text(os.getenv("DATABASE_URL")))
    try:
        row = query_processed_webhook_row(database_url, idempotency_key)
        evaluation = evaluate_processing_row(
            row,
            idempotency_key=idempotency_key,
            max_age_seconds=int(args.max_age_seconds),
            require_canary_noop=not bool(args.allow_business_processing),
        )
    except Exception as exc:
        evaluation = {
            "checked": False,
            "ok": False,
            "idempotency_key": idempotency_key,
            "requirements": {"provider": EXPECTED_PROVIDER, "event_family": EXPECTED_EVENT_FAMILY},
            "webhook_inbox_row": {"found": False},
            "violations": [],
            "error": str(exc),
        }

    warnings: list[str] = []
    if evaluation.get("ok") is not True:
        warnings.append(f"webhook_inbox processing evidence failed: {evaluation.get('error')}")
    return {
        "ok": evaluation.get("ok") is True,
        "env_file": str(args.env_file),
        "env_file_loaded": env_loaded,
        "pressure_evidence": evidence,
        "idempotency_key": idempotency_key,
        "requirements": evaluation.get("requirements"),
        "webhook_inbox_row": evaluation.get("webhook_inbox_row"),
        "violations": evaluation.get("violations") or [],
        "warnings": warnings,
        "error": "" if evaluation.get("ok") is True else evaluation.get("error"),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove that the WeCom callback inbox worker processed the canary webhook_inbox row.")
    parser.add_argument("--pressure-evidence-file", default="", help="JSON output from probe_wecom_callback_pressure.py")
    parser.add_argument("--idempotency-key", default="", help="Override the key from pressure evidence sample_validation.idempotency_key")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--database-url", default="")
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    parser.add_argument("--allow-business-processing", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = run(argv)
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
