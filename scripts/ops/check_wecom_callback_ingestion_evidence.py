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
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


DEFAULT_ENV_FILE = "/home/ubuntu/.openclaw-wecom-pg.env"
DEFAULT_MAX_AGE_SECONDS = 600
EXPECTED_PROVIDER = "wecom"
EXPECTED_EVENT_FAMILY = "external_contact"
ALLOWED_STATUSES = {
    "received",
    "processing",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "dead_letter",
    "ignored",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _load_env_file(path: str) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
    return True


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def extract_idempotency_key_from_pressure_evidence(payload: dict[str, Any]) -> str:
    sample_validation = payload.get("sample_validation") if isinstance(payload.get("sample_validation"), dict) else {}
    return _text(sample_validation.get("idempotency_key"))


def read_pressure_evidence(path: str) -> dict[str, Any]:
    evidence_path = _text(path)
    if not evidence_path:
        return {"checked": False, "ok": None, "path": "", "error": "pressure evidence not provided"}
    try:
        payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"checked": True, "ok": False, "path": evidence_path, "error": str(exc)}
    if not isinstance(payload, dict):
        return {"checked": True, "ok": False, "path": evidence_path, "error": "pressure evidence shape is invalid"}
    idempotency_key = extract_idempotency_key_from_pressure_evidence(payload)
    if not idempotency_key:
        return {"checked": True, "ok": False, "path": evidence_path, "error": "sample_validation.idempotency_key is missing"}
    return {
        "checked": True,
        "ok": True,
        "path": evidence_path,
        "idempotency_key": idempotency_key,
        "sample_validation": payload.get("sample_validation") if isinstance(payload.get("sample_validation"), dict) else {},
        "error": "",
    }


def query_webhook_inbox_row(database_url: str, idempotency_key: str) -> dict[str, Any] | None:
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
                corp_id,
                event_type,
                change_type,
                external_event_id,
                idempotency_key,
                status,
                attempt_count,
                duplicate_count,
                received_at,
                last_seen_at,
                finished_at,
                COALESCE(
                    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - COALESCE(last_seen_at, received_at)),
                    999999999
                ) AS age_seconds
            FROM webhook_inbox
            WHERE tenant_id = 'aicrm'
              AND provider = %s
              AND event_family = %s
              AND idempotency_key = %s
            ORDER BY COALESCE(last_seen_at, received_at) DESC, id DESC
            LIMIT 1
            """,
            (EXPECTED_PROVIDER, EXPECTED_EVENT_FAMILY, idempotency_key),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def evaluate_ingestion_row(
    row: dict[str, Any] | None,
    *,
    idempotency_key: str,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    requirements = {
        "provider": EXPECTED_PROVIDER,
        "event_family": EXPECTED_EVENT_FAMILY,
        "max_age_seconds": int(max_age_seconds),
        "allowed_statuses": sorted(ALLOWED_STATUSES),
    }
    if not row:
        return {
            "checked": True,
            "ok": False,
            "idempotency_key": idempotency_key,
            "requirements": requirements,
            "webhook_inbox_row": {"found": False},
            "violations": ["webhook_inbox row not found"],
            "error": "webhook_inbox row not found for idempotency_key",
        }

    status = _text(row.get("status"))
    age_seconds = _int(row.get("age_seconds"))
    violations: list[str] = []
    if _text(row.get("provider")) != EXPECTED_PROVIDER:
        violations.append("provider mismatch")
    if _text(row.get("event_family")) != EXPECTED_EVENT_FAMILY:
        violations.append("event_family mismatch")
    if _text(row.get("idempotency_key")) != idempotency_key:
        violations.append("idempotency_key mismatch")
    if status not in ALLOWED_STATUSES:
        violations.append("status is not a known webhook_inbox status")
    if age_seconds > int(max_age_seconds):
        violations.append(f"row age {age_seconds} exceeds {int(max_age_seconds)} seconds")

    row_summary = {
        "found": True,
        "id": _int(row.get("id")),
        "tenant_id": _text(row.get("tenant_id")),
        "provider": _text(row.get("provider")),
        "event_family": _text(row.get("event_family")),
        "corp_id": _text(row.get("corp_id")),
        "event_type": _text(row.get("event_type")),
        "change_type": _text(row.get("change_type")),
        "external_event_id": _text(row.get("external_event_id")),
        "idempotency_key": _text(row.get("idempotency_key")),
        "status": status,
        "attempt_count": _int(row.get("attempt_count")),
        "duplicate_count": _int(row.get("duplicate_count")),
        "received_at": _iso(row.get("received_at")),
        "last_seen_at": _iso(row.get("last_seen_at")),
        "finished_at": _iso(row.get("finished_at")),
        "age_seconds": age_seconds,
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
            "requirements": {
                "provider": EXPECTED_PROVIDER,
                "event_family": EXPECTED_EVENT_FAMILY,
                "max_age_seconds": int(args.max_age_seconds),
            },
            "webhook_inbox_row": {"found": False},
            "warnings": ["idempotency_key is required to prove webhook_inbox ingestion"],
            "error": "idempotency_key is missing",
        }

    database_url = _psycopg_url(_text(args.database_url) or _text(os.getenv("DATABASE_URL")))
    try:
        row = query_webhook_inbox_row(database_url, idempotency_key)
        evaluation = evaluate_ingestion_row(row, idempotency_key=idempotency_key, max_age_seconds=int(args.max_age_seconds))
    except Exception as exc:
        evaluation = {
            "checked": False,
            "ok": False,
            "idempotency_key": idempotency_key,
            "requirements": {
                "provider": EXPECTED_PROVIDER,
                "event_family": EXPECTED_EVENT_FAMILY,
                "max_age_seconds": int(args.max_age_seconds),
            },
            "webhook_inbox_row": {"found": False},
            "violations": [],
            "error": str(exc),
        }

    warnings: list[str] = []
    if evidence.get("ok") is False:
        warnings.append(f"pressure evidence cannot provide idempotency_key: {evidence.get('error')}")
    if evaluation.get("ok") is not True:
        warnings.append(f"webhook_inbox ingestion evidence failed: {evaluation.get('error')}")
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
    parser = argparse.ArgumentParser(description="Prove that a valid WeCom callback pressure sample landed in webhook_inbox.")
    parser.add_argument("--pressure-evidence-file", default="", help="JSON output from probe_wecom_callback_pressure.py")
    parser.add_argument("--idempotency-key", default="", help="Override the key from pressure evidence sample_validation.idempotency_key")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--database-url", default="")
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = run(argv)
    print_json(payload, indent=2)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
