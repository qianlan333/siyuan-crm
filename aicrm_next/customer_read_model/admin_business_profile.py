from __future__ import annotations

from typing import Any

from aicrm_next.shared.typing import JsonDict

from .application import GetAdminCustomerProfileQuery, GetAdminCustomerProfileTagsQuery, GetCustomerContextQuery, ListRecentMessagesQuery
from .dto import RecentMessagesRequest
from .repo import CustomerReadRepository

ROUTE_OWNER = "ai_crm_next"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _questionnaire_answers(profile: dict[str, Any]) -> list[JsonDict]:
    groups = [
        profile.get("matched_questions"),
        dict(profile.get("sidebar_context") or {}).get("matched_questions"),
        dict(profile.get("marketing_summary") or {}).get("matched_questions"),
        dict(profile.get("marketing_profile") or {}).get("matched_questions"),
    ]
    latest_assessment = (
        dict(profile.get("latest_assessment_result") or {})
        or dict(dict(profile.get("marketing_profile") or {}).get("latest_assessment_result") or {})
        or dict(dict(profile.get("sidebar_context") or {}).get("latest_assessment_result") or {})
    )
    if latest_assessment:
        groups.append(latest_assessment.get("questions") or latest_assessment.get("answers"))
    answers: list[JsonDict] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            question = _text(item.get("question") or item.get("title") or item.get("question_text") or item.get("label"))
            answer = _text(item.get("answer") or item.get("answer_text") or item.get("value") or item.get("text"))
            if not question and not answer:
                continue
            normalized = {
                "questionnaire_id": _text(item.get("questionnaire_id") or item.get("form_id")),
                "questionnaire_title": _text(item.get("questionnaire_title") or item.get("form_title") or item.get("title")),
                "submission_id": _text(item.get("submission_id") or item.get("record_id")),
                "submitted_at": _text(item.get("submitted_at") or item.get("created_at")),
                "question_id": _text(item.get("question_id") or item.get("id")),
                "question": question or "未命名问题",
                "answer": answer or "未填写",
                "raw": item,
            }
            key = (normalized["submission_id"], normalized["question_id"], normalized["question"])
            if key in seen:
                continue
            seen.add(key)
            answers.append(normalized)
    return answers


def get_customer_business_profile(
    external_userid: str,
    *,
    limit: int = 20,
    customer_repo: CustomerReadRepository | None = None,
    live_source_repo: CustomerReadRepository | None = None,
) -> JsonDict:
    requested_limit = max(1, min(int(limit or 20), 20))
    context_query = GetCustomerContextQuery(customer_repo, live_source_repo=live_source_repo)
    profile_result = GetAdminCustomerProfileQuery(context_query)(external_userid=external_userid)
    if not profile_result.get("ok"):
        payload = dict(profile_result)
        payload.setdefault("route_owner", ROUTE_OWNER)
        payload.setdefault("fallback_used", False)
        return payload
    tags_result = GetAdminCustomerProfileTagsQuery(context_query)(external_userid=external_userid)
    messages_result = ListRecentMessagesQuery(customer_repo, live_source_repo=live_source_repo)(
        RecentMessagesRequest(external_userid=external_userid, limit=requested_limit)
    )
    profile = dict(profile_result.get("profile") or profile_result.get("customer") or {})
    tags = list(tags_result.get("tags") or [])
    recent_messages = list(messages_result.get("messages") or messages_result.get("items") or [])[:requested_limit]
    questionnaire_answers = _questionnaire_answers(profile)
    return {
        "ok": True,
        "external_userid": external_userid,
        "business_profile": {
            "tags": tags,
            "recent_messages": recent_messages,
            "questionnaire_answers": questionnaire_answers,
        },
        "counts": {
            "tags": len(tags),
            "recent_messages": len(recent_messages),
            "questionnaire_answers": len(questionnaire_answers),
        },
        "route_owner": ROUTE_OWNER,
        "source_status": "next_customer_business_profile",
        "fallback_used": bool(profile_result.get("fallback_used") or tags_result.get("fallback_used") or messages_result.get("fallback_used")),
        "degraded": bool(profile_result.get("degraded") or tags_result.get("degraded") or messages_result.get("degraded")),
        "status_code": int(profile_result.get("status_code", 200) or 200),
    }
