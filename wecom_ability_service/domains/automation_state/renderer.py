from __future__ import annotations

from typing import Any

from .state_defs import FOLLOWUP_SEGMENT_LABELS, POOL_LABELS


def _text(value: Any) -> str:
    return str(value or "").strip()


def marketing_stage_key(*, main_stage: Any = "", sub_stage: Any = "", stage_key: Any = "") -> str:
    normalized_stage_key = _text(stage_key)
    if normalized_stage_key:
        return normalized_stage_key
    normalized_main_stage = _text(main_stage)
    normalized_sub_stage = _text(sub_stage)
    if normalized_main_stage and normalized_sub_stage:
        return f"{normalized_main_stage}/{normalized_sub_stage}"
    return normalized_main_stage or normalized_sub_stage


def business_pool_label(pool_key: Any) -> str:
    return POOL_LABELS.get(_text(pool_key), "")


def business_stage_label(*, main_stage: Any = "", sub_stage: Any = "", stage_key: Any = "") -> str:
    normalized_stage_key = marketing_stage_key(main_stage=main_stage, sub_stage=sub_stage, stage_key=stage_key)
    stage_labels = {
        **{f"pool/{pool_key}": label for pool_key, label in POOL_LABELS.items()},
        "converted/enrolled": "已确认成交",
    }
    return stage_labels.get(normalized_stage_key, "暂无阶段")


def business_segment_label(segment: Any) -> str:
    normalized_segment = _text(segment).lower()
    if normalized_segment in {"core", "top"}:
        normalized_segment = "focus"
    return FOLLOWUP_SEGMENT_LABELS.get(normalized_segment, FOLLOWUP_SEGMENT_LABELS["unknown"])


def business_eligibility_label(eligible_for_conversion: Any) -> str:
    return "会" if bool(eligible_for_conversion) else "不会"


def business_ineligible_reason(
    *,
    reason: Any = "",
    main_stage: Any = "",
    sub_stage: Any = "",
    eligible_for_conversion: Any = False,
) -> str:
    if bool(eligible_for_conversion):
        return ""
    normalized_reason = _text(reason)
    stage = marketing_stage_key(main_stage=main_stage, sub_stage=sub_stage)
    mapping = {
        "enrolled": "客户已确认成交，已退出全部营销。",
        "signup_success": "客户已确认成交，已退出全部营销。",
        "awaiting_questionnaire": "客户还在新用户池，等待提交问卷后再首次分流。",
        "trial_not_opened": "问卷已提交，等待开通试用后再进入对应池子。",
        "pool_not_openclaw_target": "客户当前池子不需要交给 OpenClaw。",
        "pool_not_focus_followup": "客户当前属于普通跟进池，暂不交给 OpenClaw。",
        "silent_pool": "客户已进入沉默池，当前只做留存记录。",
        "silent_timeout": "客户停留超时后已进入沉默池。",
        "not_eligible": "客户当前暂不参与自动化转化。",
    }
    if normalized_reason in mapping:
        return mapping[normalized_reason]
    if stage == "converted/enrolled":
        return mapping["enrolled"]
    if stage == "pool/silent":
        return mapping["silent_pool"]
    return normalized_reason or mapping["not_eligible"]


def business_marketing_display(
    *,
    main_stage: Any = "",
    sub_stage: Any = "",
    segment: Any = "",
    eligible_for_conversion: Any = False,
    ineligible_reason: Any = "",
) -> dict[str, str]:
    return {
        "stage_label": business_stage_label(main_stage=main_stage, sub_stage=sub_stage),
        "segment_label": business_segment_label(segment),
        "eligibility_label": business_eligibility_label(eligible_for_conversion),
        "ineligible_reason_label": business_ineligible_reason(
            reason=ineligible_reason,
            main_stage=main_stage,
            sub_stage=sub_stage,
            eligible_for_conversion=eligible_for_conversion,
        ),
    }
