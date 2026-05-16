from __future__ import annotations

DEFAULT_WECOM_CORP_TAG_LIMIT = 1000

SIGNUP_TAG_GROUP_NAME = "AI 产品报名情况"
SIGNUP_TAG_STATUS_DEFINITIONS = [
    {
        "signup_status": "lead",
        "tag_name": "报名引流品",
        "label": "报名引流品",
        "routing_alias": "pre_signup",
    },
    {
        "signup_status": "signed_999",
        "tag_name": "已报名999",
        "label": "已报名999",
        "routing_alias": "signed_999",
    },
    {
        "signup_status": "signed_3999",
        "tag_name": "已报名3999",
        "label": "已报名3999",
        "routing_alias": "signed_3999",
    },
]

CLASS_USER_ALLOWED_STATUSES = {
    item["signup_status"]: {
        "signup_status": item["signup_status"],
        "label": item["label"],
        "tag_name": item["tag_name"],
    }
    for item in SIGNUP_TAG_STATUS_DEFINITIONS
}

USER_OPS_ACTIVATION_STATUS_DEFINITIONS = [
    {"value": "not_activated", "label": "未激活"},
    {"value": "activated", "label": "已激活"},
]
USER_OPS_ACTIVATION_STATUS_LABELS = {
    item["value"]: item["label"] for item in USER_OPS_ACTIVATION_STATUS_DEFINITIONS
}

USER_OPS_LEAD_POOL_ACTIVATION_STATE_DEFINITIONS = [
    {"value": "unknown", "label": "待录入"},
    {"value": "activated", "label": "已激活"},
    {"value": "not_activated", "label": "未激活"},
]
USER_OPS_LEAD_POOL_ACTIVATION_STATE_LABELS = {
    item["value"]: item["label"] for item in USER_OPS_LEAD_POOL_ACTIVATION_STATE_DEFINITIONS
}
USER_OPS_LEAD_POOL_ACTIVATION_STATES = {"unknown", "activated", "not_activated"}
USER_OPS_HUANGXIAOCAN_ACTIVATION_SOURCE_STATES = {"activated", "not_activated"}

LEGACY_USER_OPS_POOL_STATUS_ORDER = {
    "lead_trial": 1,
    "signed_999": 2,
    "signed_3999": 3,
}

USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS = [
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAjb1Hviu4Clrhmbre8Vc4Rw",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "首期7天改变计划",
        "class_term_no": 1,
        "class_term_label": "1期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAvZbE6E-660FDq6fwiofdBw",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "0322改变计划-第3期",
        "class_term_no": 3,
        "class_term_label": "3期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAA32qvyxXLx7n0vDdo3AtClA",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "0330改变计划-第4期",
        "class_term_no": 4,
        "class_term_label": "4期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAdYV9B_p7yLaC1FDPIQisoA",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "第5期",
        "class_term_no": 5,
        "class_term_label": "5期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAmySC2aE709vd7A50Cr7rSQ",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "第6期",
        "class_term_no": 6,
        "class_term_label": "6期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAA-omjqaC_eFRSNEBgUNhzHg",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "第7期",
        "class_term_no": 7,
        "class_term_label": "7期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAzq20nLoHk1uiRDh1j_Rbwg",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "第8期",
        "class_term_no": 8,
        "class_term_label": "8期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAyfrVA7QvJ_CNtn8O4RFPnw",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "第9期",
        "class_term_no": 9,
        "class_term_label": "9期",
    },
    {
        "group_id": "etbNXyCwAA94UNiV4_iDrvFap9f-1i3w",
        "tag_id": "etbNXyCwAAu9yJXB4X_BeL9XpV0mirXw",
        "tag_group_name": "9.9元改变计划",
        "tag_name": "第10期",
        "class_term_no": 10,
        "class_term_label": "10期",
    },
]

USER_OPS_CLASS_TERM_TAG_GROUP_NAME = "9.9元改变计划"
USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL = (
    "verify_class_term_tag_and_upsert_lead_pool"
)
