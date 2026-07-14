#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any


def _database_url() -> str:
    url = str(os.getenv("DATABASE_URL") or "").strip()
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be PostgreSQL")
    return url


def redact_report(value: dict[str, Any]) -> str:
    """Serialize the fixed count-only reconciliation schema; discard unknown fields."""

    counts = value.get("counts") if isinstance(value.get("counts"), dict) else {}
    safe_counts = {
        str(key): int(item)
        for key, item in counts.items()
        if str(key).endswith("_count") and isinstance(item, int)
    }
    safe_payload = {
        "ok": bool(value.get("ok")),
        "phase": str(value.get("phase") or ""),
        "release_sha": str(value.get("release_sha") or ""),
        "unsafe_count": int(value.get("unsafe_count") or 0),
        "registered_conflict_count": int(value.get("registered_conflict_count") or 0),
        "counts": safe_counts,
        "count_digest": str(value.get("count_digest") or ""),
        "pii_included": False,
    }
    return json.dumps(safe_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scalar(conn: Any, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int((row or {}).get("count") or 0)


def _table_count(conn: Any, table_name: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table_name}",)).fetchone()
    if not bool((exists or {}).get("exists")):
        return 0
    return _scalar(conn, f'SELECT COUNT(*) AS count FROM "{table_name}"')


_ALIAS_RELATIONS_SQL = """
aliases AS (
    SELECT unionid, 'external_userid'::text AS alias_type, primary_external_userid AS alias_value
    FROM crm_user_identity
    WHERE primary_external_userid <> ''
    UNION ALL
    SELECT identity.unionid,
           'external_userid',
           CASE
               WHEN jsonb_typeof(alias.value) = 'object' THEN alias.value ->> 'external_userid'
               ELSE trim('"' from alias.value::text)
           END
    FROM crm_user_identity identity
    CROSS JOIN LATERAL jsonb_array_elements(identity.external_userids_json) alias(value)
    UNION ALL
    SELECT unionid, 'openid', primary_openid
    FROM crm_user_identity
    WHERE primary_openid <> ''
    UNION ALL
    SELECT identity.unionid,
           'openid',
           CASE
               WHEN jsonb_typeof(alias.value) = 'object' THEN alias.value ->> 'openid'
               ELSE trim('"' from alias.value::text)
           END
    FROM crm_user_identity identity
    CROSS JOIN LATERAL jsonb_array_elements(identity.openids_json) alias(value)
    UNION ALL
    SELECT unionid, 'mobile', mobile_normalized
    FROM crm_user_identity
    WHERE mobile_normalized <> ''
), duplicate_groups AS (
    SELECT alias_type,
           alias_value,
           array_agg(DISTINCT unionid ORDER BY unionid) AS candidate_unionids
    FROM aliases
    WHERE COALESCE(alias_value, '') <> ''
    GROUP BY alias_type, alias_value
    HAVING COUNT(DISTINCT unionid) > 1
)
"""

_OPEN_REGISTERED_CONFLICT_SQL = """
EXISTS (
    SELECT 1
    FROM crm_user_identity_conflicts conflict
    WHERE conflict.conflict_type = 'duplicate_alias_conflict'
      AND conflict.source_type = 'r03_identity_preflight'
      AND COALESCE(conflict.status, 'open') = 'open'
      AND COALESCE(conflict.resolution_status, 'open') = 'open'
      AND (
          (duplicate.alias_type = 'external_userid' AND conflict.external_userid = duplicate.alias_value)
          OR (duplicate.alias_type = 'openid' AND conflict.openid = duplicate.alias_value)
          OR (duplicate.alias_type = 'mobile' AND conflict.mobile = duplicate.alias_value)
      )
)
"""


def _duplicate_alias_counts(conn: Any) -> tuple[int, int]:
    row = conn.execute(
        f"""
        WITH {_ALIAS_RELATIONS_SQL}
        SELECT COUNT(*) AS duplicate_count,
               COUNT(*) FILTER (WHERE NOT {_OPEN_REGISTERED_CONFLICT_SQL}) AS unregistered_count
        FROM duplicate_groups duplicate
        """
    ).fetchone()
    return int((row or {}).get("duplicate_count") or 0), int((row or {}).get("unregistered_count") or 0)


def _register_duplicate_alias_conflicts(conn: Any) -> int:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('r03_identity_duplicate_alias_registration'))")
    rows = conn.execute(
        f"""
        WITH {_ALIAS_RELATIONS_SQL}
        INSERT INTO crm_user_identity_conflicts (
            conflict_type,
            unionid,
            candidate_unionid,
            external_userid,
            openid,
            mobile,
            source_type,
            source_key,
            payload_json,
            source_payload_json,
            status,
            resolution_status,
            created_at,
            updated_at
        )
        SELECT 'duplicate_alias_conflict',
               duplicate.candidate_unionids[1],
               duplicate.candidate_unionids[2],
               CASE WHEN duplicate.alias_type = 'external_userid' THEN duplicate.alias_value ELSE '' END,
               CASE WHEN duplicate.alias_type = 'openid' THEN duplicate.alias_value ELSE '' END,
               CASE WHEN duplicate.alias_type = 'mobile' THEN duplicate.alias_value ELSE '' END,
               'r03_identity_preflight',
               'duplicate_alias_conflict',
               jsonb_build_object(
                   'alias_type', duplicate.alias_type,
                   'candidate_count', cardinality(duplicate.candidate_unionids),
                   'automatic_merge_attempted', FALSE
               ),
               '{{}}'::jsonb,
               'open',
               'open',
               NOW(),
               NOW()
        FROM duplicate_groups duplicate
        WHERE NOT {_OPEN_REGISTERED_CONFLICT_SQL}
        RETURNING id
        """
    ).fetchall()
    return len(rows)


def collect(conn: Any, *, release_sha: str, phase: str, registered_conflict_count: int = 0) -> dict[str, Any]:
    duplicate_alias_group_count, unregistered_duplicate_alias_group_count = _duplicate_alias_counts(conn)
    counts = {
        "canonical_identity_count": _scalar(conn, "SELECT COUNT(*) AS count FROM crm_user_identity"),
        "active_identity_count": _scalar(
            conn,
            "SELECT COUNT(*) AS count FROM crm_user_identity WHERE identity_status = 'active'",
        ),
        "non_active_identity_count": _scalar(
            conn,
            "SELECT COUNT(*) AS count FROM crm_user_identity WHERE identity_status <> 'active'",
        ),
        "duplicate_alias_group_count": duplicate_alias_group_count,
        "blocked_duplicate_alias_group_count": (
            duplicate_alias_group_count - unregistered_duplicate_alias_group_count
        ),
        "unregistered_duplicate_alias_group_count": unregistered_duplicate_alias_group_count,
        "open_conflict_count": _scalar(
            conn,
            """
            SELECT COUNT(*) AS count
            FROM crm_user_identity_conflicts
            WHERE COALESCE(resolution_status, 'open') = 'open'
               OR COALESCE(status, 'open') = 'open'
            """,
        ),
        "pending_resolution_count": _scalar(
            conn,
            """
            SELECT COUNT(*) AS count
            FROM crm_user_identity_resolution_queue
            WHERE status IN ('pending', 'polling')
            """,
        ),
        "failed_resolution_count": _scalar(
            conn,
            "SELECT COUNT(*) AS count FROM crm_user_identity_resolution_queue WHERE status = 'failed'",
        ),
        "missing_unionid_succeeded_consumer_count": _scalar(
            conn,
            """
            SELECT COUNT(*) AS count
            FROM internal_event_consumer_attempt
            WHERE consumer_name = 'service_period_entitlement_consumer'
              AND status = 'succeeded'
              AND response_summary_json ->> 'reason' = 'missing_unionid'
            """,
        ),
        "legacy_people_row_count": _table_count(conn, "people"),
        "legacy_external_binding_row_count": _table_count(conn, "external_contact_bindings"),
        "resolver_parity_mismatch_count": unregistered_duplicate_alias_group_count,
    }
    unsafe_count = (
        counts["unregistered_duplicate_alias_group_count"]
        + counts["missing_unionid_succeeded_consumer_count"]
    )
    digest_payload = json.dumps(counts, sort_keys=True, separators=(",", ":"))
    return {
        "ok": unsafe_count == 0,
        "phase": phase,
        "release_sha": release_sha,
        "unsafe_count": unsafe_count,
        "registered_conflict_count": max(0, int(registered_conflict_count)),
        "counts": counts,
        "count_digest": hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
        "pii_included": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed unionid identity cutover reconciliation")
    parser.add_argument("--expected-release-sha", default="")
    parser.add_argument("--phase", choices=("preflight", "post-deploy"), default="preflight")
    parser.add_argument(
        "--register-existing-conflicts",
        action="store_true",
        help="Record duplicate aliases in the existing conflict boundary without changing canonical identities.",
    )
    args = parser.parse_args()

    if args.register_existing_conflicts and args.phase != "preflight":
        parser.error("--register-existing-conflicts is only valid during preflight")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        registered_conflict_count = _register_duplicate_alias_conflicts(conn) if args.register_existing_conflicts else 0
        payload = collect(
            conn,
            release_sha=str(args.expected_release_sha or "").strip(),
            phase=args.phase,
            registered_conflict_count=registered_conflict_count,
        )
    print(redact_report(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
