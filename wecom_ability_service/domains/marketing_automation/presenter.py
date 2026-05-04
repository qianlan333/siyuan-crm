from __future__ import annotations

from typing import Any

from ..automation_state.renderer import (
    business_eligibility_label,
    business_ineligible_reason,
    business_marketing_display,
    business_segment_label,
    business_stage_label,
    marketing_stage_key,
)

def _text(value: Any) -> str:
    return str(value or "").strip()

def marketing_state_change_summary(*, previous_stage: Any = "", current_stage: Any = "") -> str:
    previous_label = business_stage_label(stage_key=previous_stage)
    current_label = business_stage_label(stage_key=current_stage)
    if previous_stage and previous_stage != current_stage:
        return f"客户池子从{previous_label}变为{current_label}"
    if current_stage:
        return f"客户池子更新为{current_label}"
    return "客户池子已更新"


def value_segment_change_summary(*, previous_segment: Any = "", current_segment: Any = "") -> str:
    previous_label = business_segment_label(previous_segment)
    current_label = business_segment_label(current_segment)
    if previous_segment and previous_segment != current_segment:
        return f"客户初判从{previous_label}变为{current_label}"
    if current_segment:
        return f"客户初判更新为{current_label}"
    return "客户初判已更新"


def conversion_marked_summary(action: Any, source: Any) -> str:
    normalized_action = _text(action)
    normalized_source = _text(source)
    source_prefix = "人工" if normalized_source.startswith("sidebar") or normalized_source == "manual" or not normalized_source else "系统"
    if normalized_action == "mark_enrolled":
        return f"{source_prefix}确认客户已成交，系统已退出全部营销。"
    if normalized_action == "unmark_enrolled":
        return f"{source_prefix}撤销成交标记，系统已重新判断当前池子。"
    return "成交状态已更新。"
