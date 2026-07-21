#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from aicrm_next.shared.db_session import connect_raw_postgres
from aicrm_next.shared.runtime import raw_database_url
from aicrm_next.shared.runtime_settings import runtime_setting


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: Any) -> str:
    normalized = _text(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16] if normalized else ""


def check_questionnaire_unionid_cutover(*, proof_hours: int = 24) -> dict[str, Any]:
    scope = _text(os.getenv("WECHAT_MP_OAUTH_SCOPE") or "snsapi_userinfo")
    oauth_mode = _text(os.getenv("AICRM_QUESTIONNAIRE_OAUTH_ADAPTER_MODE"))
    internal_event_types = {
        item.strip()
        for item in _text(os.getenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES")).split(",")
        if item.strip()
    }
    checks = {
        "wechat_app_id_configured": bool(_text(os.getenv("WECHAT_MP_APP_ID"))),
        "wechat_app_secret_configured": bool(runtime_setting("WECHAT_MP_APP_SECRET")),
        "oauth_scope_is_snsapi_userinfo": scope == "snsapi_userinfo",
        "oauth_adapter_real_enabled": (
            oauth_mode == "real_enabled"
            and _text(os.getenv("AICRM_QUESTIONNAIRE_OAUTH_ENABLE_REAL")).lower() in {"1", "true", "yes", "on"}
        ),
        "database_configured": bool(raw_database_url()),
        "identity_ready_event_allowed": (
            not internal_event_types or "customer.wecom_identity_ready" in internal_event_types
        ),
    }
    current_cutover_state = {
        "identity_gate_enabled": _text(os.getenv("AICRM_QUESTIONNAIRE_UNIONID_REQUIRED")).lower()
        in {"1", "true", "yes", "on"},
        "continuation_enabled": _text(os.getenv("AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED")).lower()
        in {"1", "true", "yes", "on"},
        "internal_events_enabled": _text(os.getenv("AICRM_INTERNAL_EVENTS_ENABLED")).lower()
        in {"1", "true", "yes", "on"},
    }
    proof: dict[str, Any] = {
        "available": False,
        "checked_window_hours": max(1, min(int(proof_hours or 24), 168)),
        "unionid_hash": "",
        "openid_hash": "",
        "projected_at": "",
    }
    if checks["database_configured"]:
        from psycopg.rows import dict_row

        with connect_raw_postgres(raw_database_url()) as conn:
            conn.row_factory = dict_row
            row = conn.execute(
                """
                SELECT unionid, primary_openid, updated_at
                FROM crm_user_identity
                WHERE identity_status = 'active'
                  AND BTRIM(unionid) <> ''
                  AND BTRIM(COALESCE(primary_openid, '')) <> ''
                  AND updated_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour')
                  AND profile_json -> 'wechat_payment_oauth' ->> 'source_route'
                      = '/api/h5/wechat/oauth/callback'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (proof["checked_window_hours"],),
            ).fetchone()
        if row:
            proof.update(
                {
                    "available": True,
                    "unionid_hash": _hash(row.get("unionid")),
                    "openid_hash": _hash(row.get("primary_openid")),
                    "projected_at": _text(row.get("updated_at")),
                }
            )
    ready = all(checks.values()) and bool(proof["available"])
    return {
        "ok": True,
        "ready_to_enable_identity_gate": ready,
        "checks": checks,
        "current_cutover_state": current_cutover_state,
        "real_oauth_identity_proof": proof,
        "required_cutover_settings": [
            "AICRM_QUESTIONNAIRE_UNIONID_REQUIRED=1",
            "AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED=1",
            "AICRM_INTERNAL_EVENTS_ENABLED=1",
            "append customer.wecom_identity_ready to AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES when non-empty",
        ],
        "database_mutation_performed": False,
        "provider_call_executed": False,
        "pii_in_output": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only preflight for the questionnaire UnionID/WeCom continuation cutover."
    )
    parser.add_argument("--proof-hours", type=int, default=24)
    parser.add_argument(
        "--require-real-proof",
        action="store_true",
        help="Exit non-zero unless a recent real questionnaire OAuth projection produced both UnionID and OpenID.",
    )
    args = parser.parse_args()
    payload = check_questionnaire_unionid_cutover(proof_hours=args.proof_hours)
    print_json(payload, indent=2)
    if args.require_real_proof and not payload["ready_to_enable_identity_gate"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
