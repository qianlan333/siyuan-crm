from __future__ import annotations

import json
from typing import Any

from aicrm_next.shared.database import get_database_url


class QuestionnaireTagProjectionError(RuntimeError):
    pass


def _psycopg_url() -> str:
    url = get_database_url()
    if not url:
        raise QuestionnaireTagProjectionError("DATABASE_URL is required")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in result:
            result.append(text)
    return result


def apply_questionnaire_tag_projection(
    *,
    external_userid: str,
    follow_user_userid: str,
    tag_ids: list[str],
    tag_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist successful questionnaire tag effects to local CRM read surfaces."""

    normalized_external_userid = _clean_text(external_userid)
    normalized_follow_user = _clean_text(follow_user_userid)
    normalized_tag_ids = _unique_text(tag_ids)
    if not normalized_external_userid or not normalized_follow_user or not normalized_tag_ids:
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing_external_userid_follow_user_or_tags",
            "external_userid": normalized_external_userid,
            "follow_user_userid": normalized_follow_user,
            "tag_ids": normalized_tag_ids,
            "contact_tags_upserted": 0,
            "customer_list_updated": 0,
            "customer_detail_updated": 0,
        }

    names = {str(key): _clean_text(value) for key, value in dict(tag_names or {}).items()}
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise QuestionnaireTagProjectionError("psycopg is required") from exc

    with psycopg.connect(_psycopg_url()) as conn:
        cur = conn.cursor(row_factory=psycopg.rows.dict_row)
        unresolved = [tag_id for tag_id in normalized_tag_ids if not names.get(tag_id)]
        if unresolved:
            cur.execute(
                """
                SELECT tag_id, tag_name
                FROM wecom_corp_tags
                WHERE tag_id = ANY(%s)
                """,
                (unresolved,),
            )
            for row in cur.fetchall():
                names[_clean_text(row.get("tag_id"))] = _clean_text(row.get("tag_name"))

        upserted = 0
        for tag_id in normalized_tag_ids:
            cur.execute(
                """
                INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (external_userid, userid, tag_id) DO UPDATE
                SET tag_name = EXCLUDED.tag_name
                """,
                (
                    normalized_external_userid,
                    normalized_follow_user,
                    tag_id,
                    names.get(tag_id) or tag_id,
                ),
            )
            upserted += 1

        cur.execute(
            """
            SELECT COALESCE(NULLIF(tag_name, ''), tag_id) AS tag
            FROM contact_tags
            WHERE external_userid = %s
            ORDER BY tag ASC
            """,
            (normalized_external_userid,),
        )
        all_tags = _unique_text([row.get("tag") for row in cur.fetchall()])
        cur.execute(
            """
            UPDATE customer_list_index_next
            SET tags_json = %s, updated_at = CURRENT_TIMESTAMP
            WHERE external_userid = %s
            """,
            (_jsonb(all_tags), normalized_external_userid),
        )
        list_updated = cur.rowcount
        cur.execute(
            """
            UPDATE customer_detail_snapshot_next
            SET customer_json = jsonb_set(
                    COALESCE(customer_json::jsonb, '{}'::jsonb),
                    '{tags}',
                    %s,
                    TRUE
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE external_userid = %s
            """,
            (_jsonb(all_tags), normalized_external_userid),
        )
        detail_updated = cur.rowcount
        conn.commit()

    return {
        "ok": True,
        "skipped": False,
        "external_userid": normalized_external_userid,
        "follow_user_userid": normalized_follow_user,
        "tag_ids": normalized_tag_ids,
        "tag_names": {tag_id: names.get(tag_id) or tag_id for tag_id in normalized_tag_ids},
        "contact_tags_upserted": upserted,
        "customer_list_updated": list_updated,
        "customer_detail_updated": detail_updated,
        "tags_after": all_tags,
    }
