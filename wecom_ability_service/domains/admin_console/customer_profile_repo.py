from __future__ import annotations

from typing import Any

from ...customer_center.repo import (
    fetch_binding_map,
    fetch_class_status_map,
    fetch_contact_map,
    fetch_follow_users_map,
    fetch_identity_map,
    fetch_owner_role_map,
    list_scope_external_userids,
)
from ...db import get_db
from ...db.helpers import fetchall_dicts, fetchone_dict
from ...infra.json_utils import safe_json_loads as _json_loads


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return fetchall_dicts(get_db(), sql, params)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    return fetchone_dict(get_db(), sql, params)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        normalized = _normalized_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _resolve_owner_userid(
    *,
    contact: dict[str, Any],
    binding: dict[str, Any],
    identity: dict[str, Any],
    class_status: dict[str, Any],
    follow_users: list[dict[str, Any]],
) -> str:
    primary_follow_user = next((item for item in follow_users if item.get("is_primary")), follow_users[0] if follow_users else {})
    return (
        _normalized_text(class_status.get("owner_userid_snapshot"))
        or _normalized_text(contact.get("owner_userid"))
        or _normalized_text(binding.get("last_owner_userid"))
        or _normalized_text(binding.get("first_owner_userid"))
        or _normalized_text(identity.get("follow_user_userid"))
        or _normalized_text(primary_follow_user.get("userid"))
    )


def _resolve_customer_name(
    *,
    external_userid: str,
    contact: dict[str, Any],
    identity: dict[str, Any],
    class_status: dict[str, Any],
) -> str:
    return (
        _normalized_text(class_status.get("customer_name_snapshot"))
        or _normalized_text(contact.get("customer_name"))
        or _normalized_text(identity.get("name"))
        or ""
    )


def _resolve_mobile(*, lookup_mobile: str, binding: dict[str, Any], class_status: dict[str, Any]) -> str:
    return (
        _normalized_text(binding.get("mobile"))
        or _normalized_text(class_status.get("mobile_snapshot"))
        or _normalized_text(lookup_mobile)
    )


def _find_external_userid_by_mobile(mobile: str) -> str:
    normalized_mobile = _normalized_text(mobile)
    if not normalized_mobile:
        return ""
    sql = """
    SELECT external_userid
    FROM (
        SELECT b.external_userid, COALESCE(b.updated_at::text, b.created_at::text, '') AS ordering_value
        FROM external_contact_bindings b
        INNER JOIN people p ON p.id = b.person_id
        WHERE p.mobile = ?

        UNION ALL

        SELECT external_userid, COALESCE(updated_at::text, created_at::text, '') AS ordering_value
        FROM class_user_status_current
        WHERE mobile_snapshot = ?

        UNION ALL

        SELECT external_userid, COALESCE(submitted_at::text, '') AS ordering_value
        FROM questionnaire_submissions
        WHERE mobile_snapshot = ? AND external_userid IS NOT NULL AND external_userid <> ''
    ) candidates
    WHERE external_userid IS NOT NULL AND external_userid <> ''
    ORDER BY ordering_value DESC, external_userid ASC
    LIMIT 1
    """
    row = _fetchone_dict(
        sql,
        (normalized_mobile, normalized_mobile, normalized_mobile),
    )
    return _normalized_text((row or {}).get("external_userid"))


def resolve_profile_lookup(
    *,
    external_userid: str = "",
    mobile: str = "",
    user_id: str = "",
) -> dict[str, Any] | None:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_mobile = _normalized_text(mobile)
    normalized_user_id = _normalized_text(user_id)

    if normalized_external_userid:
        if normalized_external_userid not in set(list_scope_external_userids()):
            return None
        return {
            "external_userid": normalized_external_userid,
            "mobile": normalized_mobile,
            "user_id": normalized_user_id,
            "resolved_by": "external_userid",
            "user_id_supported": False,
        }

    if normalized_mobile:
        resolved_external_userid = _find_external_userid_by_mobile(normalized_mobile)
        if not resolved_external_userid:
            return None
        return {
            "external_userid": resolved_external_userid,
            "mobile": normalized_mobile,
            "user_id": normalized_user_id,
            "resolved_by": "mobile",
            "user_id_supported": False,
        }

    if normalized_user_id:
        if normalized_user_id not in set(list_scope_external_userids()):
            return None
        return {
            "external_userid": normalized_user_id,
            "mobile": normalized_mobile,
            "user_id": normalized_user_id,
            "resolved_by": "user_id_fallback_external_userid",
            "user_id_supported": False,
        }

    raise ValueError("external_userid、mobile 或 user_id 至少提供一个")


def load_customer_base_profile(
    *,
    external_userid: str = "",
    mobile: str = "",
    user_id: str = "",
) -> dict[str, Any] | None:
    lookup = resolve_profile_lookup(
        external_userid=external_userid,
        mobile=mobile,
        user_id=user_id,
    )
    if not lookup:
        return None

    resolved_external_userid = _normalized_text(lookup.get("external_userid"))
    contact = fetch_contact_map([resolved_external_userid]).get(resolved_external_userid, {})
    binding = fetch_binding_map([resolved_external_userid]).get(resolved_external_userid, {})
    identity = fetch_identity_map([resolved_external_userid]).get(resolved_external_userid, {})
    class_status = fetch_class_status_map([resolved_external_userid]).get(resolved_external_userid, {})
    follow_users = fetch_follow_users_map([resolved_external_userid]).get(resolved_external_userid, [])
    owner_userid = _resolve_owner_userid(
        contact=contact,
        binding=binding,
        identity=identity,
        class_status=class_status,
        follow_users=follow_users,
    )
    owner_role = fetch_owner_role_map([owner_userid]).get(owner_userid, {})
    customer_name = _resolve_customer_name(
        external_userid=resolved_external_userid,
        contact=contact,
        identity=identity,
        class_status=class_status,
    )
    resolved_mobile = _resolve_mobile(
        lookup_mobile=_normalized_text(lookup.get("mobile")),
        binding=binding,
        class_status=class_status,
    )
    return {
        "external_userid": resolved_external_userid,
        "customer_name": customer_name,
        "owner_userid": owner_userid,
        "owner_display_name": _normalized_text(owner_role.get("display_name")) or owner_userid,
        "mobile": resolved_mobile,
        "unionid": _normalized_text(identity.get("unionid")),
        "lookup": lookup,
    }


def list_customer_questionnaire_answers(
    *,
    external_userid: str = "",
    mobile: str = "",
) -> list[dict[str, Any]]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_mobile = _normalized_text(mobile)
    if not normalized_external_userid and not normalized_mobile:
        return []

    clauses: list[str] = []
    params: list[Any] = []
    if normalized_external_userid:
        clauses.append("qs.external_userid = ?")
        params.append(normalized_external_userid)
    if normalized_mobile:
        clauses.append("qs.mobile_snapshot = ?")
        params.append(normalized_mobile)

    rows = _fetchall_dict(
        f"""
        SELECT
            qsa.id,
            qsa.submission_id,
            qsa.question_id,
            qsa.question_type,
            qsa.question_title_snapshot,
            qsa.selected_option_texts_snapshot,
            qsa.text_value,
            qs.questionnaire_id,
            qs.external_userid,
            qs.mobile_snapshot,
            qs.submitted_at,
            COALESCE(q.name, '') AS questionnaire_title
        FROM questionnaire_submission_answers qsa
        INNER JOIN questionnaire_submissions qs
          ON qs.id = qsa.submission_id
        LEFT JOIN questionnaires q
          ON q.id = qs.questionnaire_id
        WHERE {' OR '.join(clauses)}
        ORDER BY qs.submitted_at DESC, qsa.submission_id DESC, qsa.id ASC
        """,
        tuple(params),
    )
    answers: list[dict[str, Any]] = []
    for row in rows:
        question_type = _normalized_text(row.get("question_type"))
        if question_type in {"textarea", "mobile"}:
            answer = _normalized_text(row.get("text_value"))
        else:
            answer = "/".join(_dedupe_strings(_json_loads(row.get("selected_option_texts_snapshot"), default=[])))
        answers.append(
            {
                "submission_id": int(row["submission_id"]),
                "questionnaire_id": int(row["questionnaire_id"]),
                "questionnaire_title": _normalized_text(row.get("questionnaire_title")),
                "submitted_at": _normalized_text(row.get("submitted_at")),
                "external_userid": _normalized_text(row.get("external_userid")),
                "mobile": _normalized_text(row.get("mobile_snapshot")),
                "question": _normalized_text(row.get("question_title_snapshot")),
                "answer": answer,
            }
        )
    return answers


def list_customer_questionnaire_assessment_results(
    *,
    external_userid: str = "",
    mobile: str = "",
    limit: int = 3,
) -> list[dict[str, Any]]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_mobile = _normalized_text(mobile)
    if not normalized_external_userid and not normalized_mobile:
        return []

    clauses: list[str] = []
    params: list[Any] = []
    if normalized_external_userid:
        clauses.append("qs.external_userid = ?")
        params.append(normalized_external_userid)
    if normalized_mobile:
        clauses.append("qs.mobile_snapshot = ?")
        params.append(normalized_mobile)
    params.append(max(1, min(int(limit or 3), 20)))

    rows = _fetchall_dict(
        f"""
        SELECT
            qs.id AS submission_id,
            qs.questionnaire_id,
            qs.external_userid,
            qs.mobile_snapshot,
            qs.submitted_at,
            qs.total_score,
            qs.assessment_result_snapshot,
            qs.result_token,
            COALESCE(q.slug, '') AS questionnaire_slug,
            COALESCE(q.name, '') AS questionnaire_title
        FROM questionnaire_submissions qs
        LEFT JOIN questionnaires q
          ON q.id = qs.questionnaire_id
        WHERE ({' OR '.join(clauses)})
          AND qs.result_token <> ''
        ORDER BY qs.submitted_at DESC, qs.id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        snapshot = _json_loads(row.get("assessment_result_snapshot"), default={})
        if not isinstance(snapshot, dict) or not snapshot:
            continue
        overall_level = snapshot.get("overall_level") if isinstance(snapshot.get("overall_level"), dict) else {}
        dimensions = snapshot.get("dimensions") if isinstance(snapshot.get("dimensions"), list) else []
        dimension_summary = [
            {
                "key": _normalized_text(item.get("key")),
                "name": _normalized_text(item.get("name")),
                "score": float(item.get("score") or 0),
                "dominant_type_name": _normalized_text((item.get("dominant_type") or {}).get("name"))
                if isinstance(item.get("dominant_type"), dict)
                else "",
            }
            for item in dimensions
            if isinstance(item, dict)
        ]
        results.append(
            {
                "submission_id": int(row["submission_id"]),
                "questionnaire_id": int(row["questionnaire_id"]),
                "questionnaire_title": _normalized_text(row.get("questionnaire_title")),
                "questionnaire_slug": _normalized_text(row.get("questionnaire_slug")),
                "submitted_at": _normalized_text(row.get("submitted_at")),
                "external_userid": _normalized_text(row.get("external_userid")),
                "mobile": _normalized_text(row.get("mobile_snapshot")),
                "total_score": float(row.get("total_score") or snapshot.get("total_score") or 0),
                "overall_level_title": _normalized_text(overall_level.get("title") or overall_level.get("name")),
                "strengths": [
                    _normalized_text(item.get("name"))
                    for item in (snapshot.get("strengths") or [])
                    if isinstance(item, dict) and _normalized_text(item.get("name"))
                ],
                "weaknesses": [
                    _normalized_text(item.get("name"))
                    for item in (snapshot.get("weaknesses") or [])
                    if isinstance(item, dict) and _normalized_text(item.get("name"))
                ],
                "dimensions": dimension_summary,
                "result_url": f"/s/{_normalized_text(row.get('questionnaire_slug'))}/result/{_normalized_text(row.get('result_token'))}",
            }
        )
    return results


def list_customer_message_rows(
    external_userid: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return []
    return _fetchall_dict(
        """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
               msgtype, content, send_time, raw_payload, created_at
        FROM archived_messages
        WHERE external_userid = ?
        ORDER BY send_time DESC, id DESC
        LIMIT ?
        """,
        (normalized_external_userid, int(limit)),
    )
