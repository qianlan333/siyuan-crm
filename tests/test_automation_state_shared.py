from __future__ import annotations

from wecom_ability_service.domains.automation_conversion import service as automation_conversion_service
from wecom_ability_service.domains.automation_state import renderer, state_defs
from wecom_ability_service.domains.marketing_automation import presenter as marketing_presenter
from wecom_ability_service.domains.marketing_automation import service as marketing_service


def test_shared_state_defs_freeze_public_values():
    assert state_defs.POOL_NEW_USER == "new_user"
    assert state_defs.POOL_INACTIVE_NORMAL == "inactive_normal"
    assert state_defs.POOL_INACTIVE_FOCUS == "inactive_focus"
    assert state_defs.POOL_ACTIVE_NORMAL == "active_normal"
    assert state_defs.POOL_ACTIVE_FOCUS == "active_focus"
    assert state_defs.POOL_SILENT == "silent"
    assert state_defs.FOLLOWUP_SEGMENT_UNKNOWN == "unknown"
    assert state_defs.FOLLOWUP_SEGMENT_NORMAL == "normal"
    assert state_defs.FOLLOWUP_SEGMENT_FOCUS == "focus"
    assert state_defs.FOCUS_POOL_KEYS == {"inactive_focus", "active_focus"}
    assert state_defs.POOL_LABELS["new_user"] == "新用户池"
    assert state_defs.POOL_LABELS["active_focus"] == "激活重点跟进池"
    assert marketing_service.POOL_NEW_USER == "new_user"
    assert marketing_service.POOL_INACTIVE_NORMAL == "inactive_normal"
    assert marketing_service.POOL_INACTIVE_FOCUS == "inactive_focus"
    assert marketing_service.POOL_ACTIVE_NORMAL == "active_normal"
    assert marketing_service.POOL_ACTIVE_FOCUS == "active_focus"
    assert marketing_service.POOL_SILENT == "silent"
    assert marketing_service.FOLLOWUP_SEGMENT_UNKNOWN == "unknown"
    assert marketing_service.FOLLOWUP_SEGMENT_NORMAL == "normal"
    assert marketing_service.FOLLOWUP_SEGMENT_FOCUS == "focus"
    assert automation_conversion_service.POOL_NEW_USER == "new_user"
    assert automation_conversion_service.POOL_INACTIVE_NORMAL == "inactive_normal"
    assert automation_conversion_service.POOL_INACTIVE_FOCUS == "inactive_focus"
    assert automation_conversion_service.POOL_ACTIVE_NORMAL == "active_normal"
    assert automation_conversion_service.POOL_ACTIVE_FOCUS == "active_focus"
    assert automation_conversion_service.POOL_SILENT == "silent"
    assert marketing_service.POOL_NEW_USER == state_defs.POOL_NEW_USER
    assert marketing_service.POOL_INACTIVE_NORMAL == state_defs.POOL_INACTIVE_NORMAL
    assert marketing_service.POOL_INACTIVE_FOCUS == state_defs.POOL_INACTIVE_FOCUS
    assert marketing_service.POOL_ACTIVE_NORMAL == state_defs.POOL_ACTIVE_NORMAL
    assert marketing_service.POOL_ACTIVE_FOCUS == state_defs.POOL_ACTIVE_FOCUS
    assert marketing_service.POOL_SILENT == state_defs.POOL_SILENT
    assert marketing_service.FOLLOWUP_SEGMENT_UNKNOWN == state_defs.FOLLOWUP_SEGMENT_UNKNOWN
    assert marketing_service.FOLLOWUP_SEGMENT_NORMAL == state_defs.FOLLOWUP_SEGMENT_NORMAL
    assert marketing_service.FOLLOWUP_SEGMENT_FOCUS == state_defs.FOLLOWUP_SEGMENT_FOCUS
    assert automation_conversion_service.POOL_NEW_USER == state_defs.POOL_NEW_USER
    assert automation_conversion_service.POOL_INACTIVE_NORMAL == state_defs.POOL_INACTIVE_NORMAL
    assert automation_conversion_service.POOL_INACTIVE_FOCUS == state_defs.POOL_INACTIVE_FOCUS
    assert automation_conversion_service.POOL_ACTIVE_NORMAL == state_defs.POOL_ACTIVE_NORMAL
    assert automation_conversion_service.POOL_ACTIVE_FOCUS == state_defs.POOL_ACTIVE_FOCUS
    assert automation_conversion_service.POOL_SILENT == state_defs.POOL_SILENT
    assert marketing_service._FOCUS_POOL_KEYS == {"inactive_focus", "active_focus"}
    assert automation_conversion_service.FOCUS_SEND_ALLOWED_POOLS == {"inactive_focus", "active_focus"}
    assert marketing_service._FOLLOWUP_SEGMENT_LABELS is state_defs.FOLLOWUP_SEGMENT_LABELS
    assert marketing_service._POOL_LABELS is state_defs.POOL_LABELS
    assert marketing_service._POOL_LABELS["new_user"] == "新用户池"
    assert marketing_service._POOL_LABELS["active_focus"] == "激活重点跟进池"
    assert automation_conversion_service.POOL_LABELS["new_user"] == "新用户池"
    assert automation_conversion_service.POOL_LABELS["active_focus"] == "激活重点跟进池"


def test_shared_label_renderer_freezes_exact_cn_strings():
    assert renderer.business_pool_label("active_focus") == "激活重点跟进池"
    assert renderer.business_stage_label(stage_key="pool/active_focus") == "激活重点跟进池"
    assert renderer.business_stage_label(stage_key="converted/enrolled") == "已确认成交"
    assert renderer.business_segment_label("unknown") == "未完成初判"
    assert renderer.business_segment_label("core") == "重点跟进"
    assert renderer.business_eligibility_label(True) == "会"
    assert renderer.business_eligibility_label(False) == "不会"
    assert renderer.business_ineligible_reason(
        reason="trial_not_opened",
        main_stage="pool",
        sub_stage="new_user",
        eligible_for_conversion=False,
    ) == "问卷已提交，等待开通试用后再进入对应池子。"
    assert marketing_presenter.business_stage_label(stage_key="pool/active_focus") == "激活重点跟进池"
    assert marketing_presenter.business_stage_label(stage_key="converted/enrolled") == "已确认成交"
    assert marketing_presenter.business_segment_label("unknown") == "未完成初判"
    assert marketing_presenter.business_segment_label("core") == "重点跟进"
    assert marketing_presenter.business_eligibility_label(True) == "会"
    assert marketing_presenter.business_eligibility_label(False) == "不会"
    assert marketing_presenter.business_ineligible_reason(
        reason="trial_not_opened",
        main_stage="pool",
        sub_stage="new_user",
        eligible_for_conversion=False,
    ) == "问卷已提交，等待开通试用后再进入对应池子。"
