from __future__ import annotations

from ..application.automation_engine.commands import (
    MarkEnrolledCommand,
    SetManualFollowupSegmentCommand,
    UnmarkEnrolledCommand,
)
from ..application.automation_engine.dto import (
    CustomerMarketingProfileQueryDTO,
    ManualFollowupSegmentCommandDTO,
    MarkEnrolledCommandDTO,
    SignupConversionPreviewQueryDTO,
    UnmarkEnrolledCommandDTO,
)
from ..application.automation_engine.queries import (
    GetCustomerMarketingProfileQuery,
    PreviewSignupConversionCustomerQuery,
)
from ..application.class_user.dto import GetClassUserStatusCurrentQueryDTO
from ..application.class_user.queries import GetClassUserStatusCurrentQuery
from ..application.identity_contact._runtime import get_contact_by_external_userid
from ..application.identity_contact.dto import (
    GetContactBindingStatusQueryDTO,
    GetPrimaryFollowUserUseridQueryDTO,
    ResolvePersonIdentityQueryDTO,
)
from ..application.identity_contact.queries import (
    GetContactBindingStatusQuery,
    GetPrimaryFollowUserUseridQuery,
    ResolvePersonIdentityQuery,
)
from ..domains.marketing_automation.presenter import business_marketing_display, business_segment_label


_SIDEBAR_SWITCHABLE_POOL_STAGE_KEYS = {
    "pool/inactive_normal",
    "pool/inactive_focus",
    "pool/active_normal",
    "pool/active_focus",
    "pool/silent",
}


def get_customer_marketing_profile(external_userid: str, *, scenario_key: str = "") -> dict[str, object]:
    return GetCustomerMarketingProfileQuery()(
        CustomerMarketingProfileQueryDTO(
            external_userid=str(external_userid or "").strip(),
            scenario_key=str(scenario_key or "").strip(),
        )
    )


def _get_class_user_status_current(external_userid: str):
    return GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid=str(external_userid or "").strip())
    )


def _get_contact_binding_status_payload(external_userid: str, owner_userid: str = "") -> dict[str, object]:
    return GetContactBindingStatusQuery()(
        GetContactBindingStatusQueryDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
        )
    )


def _resolve_person_identity_payload(external_userid: str = "", mobile: str = "", unionid: str = "") -> dict[str, object]:
    return ResolvePersonIdentityQuery()(
        ResolvePersonIdentityQueryDTO(
            external_userid=str(external_userid or "").strip(),
            mobile=str(mobile or "").strip(),
            unionid=str(unionid or "").strip(),
        )
    )


def _get_primary_follow_user_userid_payload(external_userid: str) -> str:
    return GetPrimaryFollowUserUseridQuery()(
        GetPrimaryFollowUserUseridQueryDTO(external_userid=str(external_userid or "").strip())
    )


def preview_signup_conversion_customer(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = "",
    persist: bool = True,
) -> dict[str, object]:
    return PreviewSignupConversionCustomerQuery()(
        SignupConversionPreviewQueryDTO(
            external_userid=str(external_userid or "").strip(),
            person_id=person_id,
            automation_key=str(automation_key or "").strip(),
            persist=bool(persist),
        )
    )


def mark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    signup_status: str = "",
    automation_key: str = "",
) -> dict[str, object]:
    return MarkEnrolledCommand()(
        MarkEnrolledCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "manual",
            signup_status=str(signup_status or "").strip(),
            automation_key=str(automation_key or "").strip(),
        )
    )


def unmark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    restore_signup_status: str = "",
    automation_key: str = "",
) -> dict[str, object]:
    return UnmarkEnrolledCommand()(
        UnmarkEnrolledCommandDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "manual",
            restore_signup_status=str(restore_signup_status or "").strip(),
            automation_key=str(automation_key or "").strip(),
        )
    )


def set_manual_followup_segment(
    *,
    external_userid: str,
    followup_segment: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    automation_key: str = "",
) -> dict[str, object]:
    return SetManualFollowupSegmentCommand()(
        ManualFollowupSegmentCommandDTO(
            external_userid=str(external_userid or "").strip(),
            followup_segment=str(followup_segment or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "manual",
            automation_key=str(automation_key or "").strip(),
        )
    )


def _followup_source_label(source: str) -> str:
    normalized = str(source or "").strip().lower()
    return {
        "manual_override": "人工改判",
        "questionnaire": "问卷初判",
        "awaiting_questionnaire": "待问卷提交",
    }.get(normalized, "待问卷提交")


def _manual_override_source_label(source: str) -> str:
    normalized = str(source or "").strip().lower()
    if not normalized:
        return ""
    if normalized.startswith("sidebar"):
        return "侧边栏人工改判"
    if normalized == "manual":
        return "人工改判"
    return normalized


def marketing_status_payload(preview: dict[str, object]) -> dict[str, object]:
    marketing_state = dict(preview.get("marketing_state") or {})
    state_payload = dict(marketing_state.get("state_payload") or {})
    value_segment = dict(preview.get("value_segment") or {})
    summary = dict(preview.get("summary") or {})
    resolved_customer = dict(preview.get("resolved_customer") or {})
    current_segment = str(summary.get("current_segment") or "").strip() or str(value_segment.get("segment") or "").strip()
    questionnaire_segment = str(state_payload.get("questionnaire_segment") or "").strip() or "unknown"
    manual_override_segment = str(state_payload.get("manual_followup_segment") or "").strip()
    followup_segment_source = str(state_payload.get("followup_segment_source") or "").strip() or "awaiting_questionnaire"
    stage_key = str(marketing_state.get("stage_key") or "").strip()
    activated = bool(marketing_state.get("activated")) or bool(str(marketing_state.get("last_activation_at") or "").strip())
    display = business_marketing_display(
        main_stage=marketing_state.get("main_stage"),
        sub_stage=marketing_state.get("sub_stage"),
        segment=current_segment,
        eligible_for_conversion=marketing_state.get("eligible_for_conversion"),
        ineligible_reason=summary.get("ineligible_reason"),
    )
    return {
        "person_id": resolved_customer.get("person_id"),
        "external_userid": str(resolved_customer.get("external_userid") or "").strip(),
        "mobile": str(resolved_customer.get("mobile") or "").strip(),
        "main_stage": str(marketing_state.get("main_stage") or "").strip(),
        "sub_stage": str(marketing_state.get("sub_stage") or "").strip(),
        "stage_key": stage_key,
        "pool_key": str(marketing_state.get("pool_key") or "").strip(),
        "pool_display": display["stage_label"],
        "segment": current_segment,
        "segment_label": str(summary.get("current_segment_label") or "").strip() or str(value_segment.get("segment_label") or "").strip(),
        "stage_display": display["stage_label"],
        "segment_display": display["segment_label"],
        "eligibility_display": display["eligibility_label"],
        "ineligible_reason_display": display["ineligible_reason_label"],
        "hit_count": int(value_segment.get("hit_count") or summary.get("hit_count") or 0),
        "matched_question_ids": [
            int(question_id)
            for question_id in summary.get("matched_question_ids") or value_segment.get("matched_question_ids_json") or []
            if str(question_id).strip()
        ],
        "matched_questions": list(summary.get("matched_questions") or []),
        "eligible_for_conversion": bool(marketing_state.get("eligible_for_conversion")),
        "ineligible_reason": str(summary.get("ineligible_reason") or "").strip(),
        "activated": activated,
        "current_followup_type": current_segment,
        "current_followup_type_display": display["segment_label"],
        "followup_segment_source": followup_segment_source,
        "followup_segment_source_display": _followup_source_label(followup_segment_source),
        "questionnaire_segment": questionnaire_segment,
        "questionnaire_segment_display": business_segment_label(questionnaire_segment),
        "manual_override_active": bool(manual_override_segment),
        "manual_override_segment": manual_override_segment,
        "manual_override_segment_display": business_segment_label(manual_override_segment) if manual_override_segment else "",
        "manual_override_source": str(state_payload.get("manual_followup_segment_source") or "").strip(),
        "manual_override_source_display": _manual_override_source_label(
            str(state_payload.get("manual_followup_segment_source") or "").strip()
        ),
        "manual_override_operator": str(state_payload.get("manual_followup_segment_operator") or "").strip(),
        "manual_override_at": str(state_payload.get("manual_followup_segment_at") or "").strip(),
        "can_switch_followup_segment": stage_key in _SIDEBAR_SWITCHABLE_POOL_STAGE_KEYS,
        "last_activation_at": str(marketing_state.get("last_activation_at") or "").strip(),
        "last_conversion_marked_at": str(marketing_state.get("last_conversion_marked_at") or "").strip(),
        "updated_at": str(marketing_state.get("updated_at") or value_segment.get("updated_at") or "").strip(),
    }


def sidebar_marketing_target_exists(external_userid: str) -> bool:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return False
    if get_contact_by_external_userid(normalized_external_userid) is not None:
        return True
    if _get_class_user_status_current(normalized_external_userid):
        return True
    if _get_primary_follow_user_userid_payload(normalized_external_userid):
        return True
    binding_status = _get_contact_binding_status_payload(normalized_external_userid)
    if not binding_status.get("is_bound"):
        return False
    resolved_identity = _resolve_person_identity_payload(external_userid=normalized_external_userid)
    return bool(resolved_identity.get("is_bound"))
