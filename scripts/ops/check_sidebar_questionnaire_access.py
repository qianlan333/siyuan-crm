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


def _scalar(conn: Any, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int((row or {}).get("count") or 0)


def collect(conn: Any, *, release_sha: str, phase: str) -> dict[str, Any]:
    relation_counts = conn.execute(
        """
        WITH current_owner_relations AS (
            SELECT external_userid, user_id AS owner_userid
            FROM wecom_external_contact_follow_users
            WHERE COALESCE(relation_status, 'active') = 'active'
              AND COALESCE(external_userid, '') <> ''
              AND COALESCE(user_id, '') <> ''
            UNION
            SELECT external_userid, follow_user_userid
            FROM wecom_external_contact_identity_map
            WHERE COALESCE(status, 'active') = 'active'
              AND COALESCE(external_userid, '') <> ''
              AND COALESCE(follow_user_userid, '') <> ''
            UNION
            SELECT alias.external_userid, identity.primary_owner_userid
            FROM crm_user_identity identity
            CROSS JOIN LATERAL (
                SELECT identity.primary_external_userid AS external_userid
                UNION
                SELECT CASE
                    WHEN jsonb_typeof(item.value) = 'object'
                    THEN item.value ->> 'external_userid'
                    ELSE trim('"' FROM item.value::text)
                END
                FROM jsonb_array_elements(identity.external_userids_json) item(value)
            ) alias
            WHERE COALESCE(identity.identity_status, 'active') = 'active'
              AND COALESCE(alias.external_userid, '') <> ''
              AND COALESCE(identity.primary_owner_userid, '') <> ''
        )
        SELECT
            (SELECT COUNT(*) FROM wecom_external_contact_follow_users
             WHERE COALESCE(relation_status, 'active') = 'active') AS active_follow_relation_count,
            (SELECT COUNT(*) FROM wecom_external_contact_identity_map
             WHERE COALESCE(status, 'active') = 'active'
               AND COALESCE(follow_user_userid, '') <> '') AS active_identity_map_relation_count,
            (SELECT COUNT(*) FROM crm_user_identity
             WHERE COALESCE(identity_status, 'active') = 'active'
               AND COALESCE(primary_owner_userid, '') <> '') AS active_canonical_owner_relation_count,
            (SELECT COUNT(DISTINCT external_userid) FROM current_owner_relations) AS current_owner_external_count,
            (SELECT COUNT(*) FROM external_contact_bindings) AS legacy_binding_external_count,
            (SELECT COUNT(*)
             FROM external_contact_bindings legacy
             WHERE NOT EXISTS (
                 SELECT 1
                 FROM current_owner_relations current
                 WHERE current.external_userid = legacy.external_userid
             )) AS blocked_legacy_only_external_count,
            (SELECT COUNT(*) FROM wecom_external_contact_follow_users
             WHERE COALESCE(relation_status, 'active') <> 'active') AS inactive_follow_relation_count
        """
    ).fetchone()
    counts = {str(key): int(value or 0) for key, value in dict(relation_counts or {}).items()}
    counts.update(
        {
            "questionnaire_result_token_missing_count": _scalar(
                conn,
                """
                SELECT COUNT(*) AS count
                FROM questionnaire_submissions
                WHERE COALESCE(result_token, '') = ''
                """,
            ),
            "questionnaire_result_token_duplicate_group_count": _scalar(
                conn,
                """
                SELECT COUNT(*) AS count
                FROM (
                    SELECT result_token
                    FROM questionnaire_submissions
                    WHERE COALESCE(result_token, '') <> ''
                    GROUP BY result_token
                    HAVING COUNT(*) > 1
                ) duplicate_tokens
                """,
            ),
        }
    )
    unsafe_count = counts["questionnaire_result_token_duplicate_group_count"]
    digest = hashlib.sha256(
        json.dumps(counts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "ok": unsafe_count == 0,
        "phase": phase,
        "release_sha": str(release_sha or "").strip(),
        "unsafe_count": unsafe_count,
        "counts": counts,
        "count_digest": digest,
        "pii_included": False,
    }


def redact_report(value: dict[str, Any]) -> str:
    counts = value.get("counts") if isinstance(value.get("counts"), dict) else {}
    safe_counts = {
        str(key): int(item)
        for key, item in counts.items()
        if str(key).endswith("_count") and isinstance(item, int)
    }
    payload = {
        "ok": bool(value.get("ok")),
        "phase": str(value.get("phase") or ""),
        "release_sha": str(value.get("release_sha") or ""),
        "unsafe_count": int(value.get("unsafe_count") or 0),
        "counts": safe_counts,
        "count_digest": str(value.get("count_digest") or ""),
        "pii_included": False,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count-only sidebar owner and questionnaire result access reconciliation"
    )
    parser.add_argument("--expected-release-sha", default="")
    parser.add_argument("--phase", choices=("preflight", "post-deploy"), default="preflight")
    args = parser.parse_args()

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        conn.execute("SET LOCAL statement_timeout = '15s'")
        payload = collect(
            conn,
            release_sha=args.expected_release_sha,
            phase=args.phase,
        )
    print(redact_report(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
