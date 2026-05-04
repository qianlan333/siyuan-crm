from __future__ import annotations

POOL_NEW_USER = "new_user"
POOL_INACTIVE_NORMAL = "inactive_normal"
POOL_INACTIVE_FOCUS = "inactive_focus"
POOL_ACTIVE_NORMAL = "active_normal"
POOL_ACTIVE_FOCUS = "active_focus"
POOL_SILENT = "silent"

FOLLOWUP_SEGMENT_UNKNOWN = "unknown"
FOLLOWUP_SEGMENT_NORMAL = "normal"
FOLLOWUP_SEGMENT_FOCUS = "focus"

FOCUS_POOL_KEYS = {
    POOL_INACTIVE_FOCUS,
    POOL_ACTIVE_FOCUS,
}

FOLLOWUP_SEGMENT_LABELS = {
    FOLLOWUP_SEGMENT_UNKNOWN: "未完成初判",
    FOLLOWUP_SEGMENT_NORMAL: "普通跟进",
    FOLLOWUP_SEGMENT_FOCUS: "重点跟进",
}

POOL_LABELS = {
    POOL_NEW_USER: "新用户池",
    POOL_INACTIVE_NORMAL: "未激活普通池",
    POOL_INACTIVE_FOCUS: "未激活重点跟进池",
    POOL_ACTIVE_NORMAL: "激活普通池",
    POOL_ACTIVE_FOCUS: "激活重点跟进池",
    POOL_SILENT: "沉默池",
}
