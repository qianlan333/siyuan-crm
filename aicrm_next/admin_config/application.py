from __future__ import annotations

import json
import os
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aicrm_next.admin_jobs.routes import ensure_admin_action_token
from aicrm_next.platform_foundation.external_effects.jobs import (
    SCHEDULER_BATCH_SIZE_KEY,
    SCHEDULER_ENABLED_KEY,
    SCHEDULER_INTERVAL_SECONDS_KEY,
)
from aicrm_next.platform_foundation.external_effects.models import WECOM_MESSAGE_PRIVATE_SEND
from aicrm_next.platform_foundation.external_effects.realtime import (
    CHANNEL_ENTRY_REALTIME_EFFECT_TYPES,
    REALTIME_ALLOWED_TYPES_KEY,
    REALTIME_ENABLED_KEY,
    REALTIME_MAX_CONCURRENCY_KEY,
)
from aicrm_next.platform_foundation.push_center.capability_registry import (
    PushCapability,
    get_push_capability,
    visible_push_capabilities,
)
from aicrm_next.platform_foundation.push_center.repository import PushCenterRepository

from .category_registry import CONFIG_CATEGORIES, ConfigCategory, ConfigCategoryField, get_config_category
from .definitions import APP_SETTING_DEFINITIONS
from .repository import AdminConfigRepository
from .schema import CONFIG_SCHEMA, build_config_checklist, validate_config
from .settings import SENSITIVE_KEYS, mask_value


TARGET_APP_SETTING = "app_setting"
TARGET_CONFIG_CATEGORY_ENABLED = "config_category_enabled"
TARGET_ADMIN_USER = "admin_user"
TARGET_MCP_TOOL_SETTING = "mcp_tool_setting"
TARGET_MARKETING_AUTOMATION_CONFIG = "marketing_automation_config"
TARGET_PUSH_CAPABILITY = "push_capability"
DEFAULT_SIGNUP_CONVERSION_KEY = "signup_conversion_v1"
DEFAULT_MARKETING_AUTOMATION_NAME = "自动化转化问卷初判"
DEFAULT_MARKETING_TARGET_EVENT = "signup_success"
DEFAULT_MARKETING_CHANNEL_TYPE = "text_message"
DEFAULT_MARKETING_CORE_THRESHOLD = 3
DEFAULT_MARKETING_TOP_THRESHOLD = 4
DEFAULT_MARKETING_DAY_START_HOUR = 9
DEFAULT_MARKETING_QUIET_HOUR_START = 23
DEFAULT_MARKETING_TIMEZONE = "Asia/Shanghai"
DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL = {
    "new_user": 7,
    "inactive_normal": 7,
    "inactive_focus": 7,
    "active_normal": 7,
    "active_focus": 7,
}

ROLE_LABELS = {
    "super_admin": "超级管理员",
    "config_admin": "配置管理员",
    "automation_admin": "自动化管理员",
    "questionnaire_admin": "问卷管理员",
    "viewer": "只读成员",
}
ADMIN_ASSIGNABLE_ROLE_OPTIONS = [{"value": key, "label": value} for key, value in ROLE_LABELS.items() if key != "super_admin"]
ADMIN_LEVEL_LABELS = {"super_admin": "超级管理员", "admin": "管理员"}
MCP_TOOL_GROUP_LABELS = {
    "crm": "客户查询",
    "tasks": "触达任务",
    "config": "配置规则",
    "ops": "同步任务",
    "misc": "其他",
}
HTTP_URL_SETTING_KEYS = {
    "ADMIN_LOGIN_REDIRECT_URI",
    "WECOM_API_BASE",
    "DEEPSEEK_BASE_URL",
    "OPENCLAW_WEBHOOK_URL",
    "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
    "WECHAT_PAY_NOTIFY_URL",
    "WECHAT_PAY_API_BASE",
    "ALIPAY_SERVER_URL",
    "ALIPAY_NOTIFY_URL",
    "ALIPAY_RETURN_URL",
    "WECHAT_SHOP_API_BASE",
}
JSON_SETTING_KEYS = {"WECHAT_PAY_PRODUCT_CATALOG_JSON"}
PUSH_CAPABILITY_ADVANCED_KEYS = (
    ("OPENCLAW_WEBHOOK_URL", "OPENCLAW_WEBHOOK_URL", "OpenClaw Webhook 地址"),
    ("openclaw_focus_message_credential", "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN", "OpenClaw Focus Message 凭据"),
    ("QUESTIONNAIRE_SUBMIT_WEBHOOK_URL", "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL", "问卷提交 Webhook 地址"),
    ("questionnaire_submit_credential", "QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN", "问卷提交凭据"),
    ("external_effect_webhook_signing_config", "AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET", "External Effect Webhook 签名配置"),
)
EXTRA_SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "SIDEBAR_PRODUCT_CONTEXT_TOKEN_TTL_SECONDS": {
        "key": "SIDEBAR_PRODUCT_CONTEXT_TOKEN_TTL_SECONDS",
        "label": "侧边栏商品上下文有效期",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "侧边栏商品签名上下文 token 有效期（秒）。",
        "min": 1,
    },
    "SIDEBAR_CONTEXT_TOKEN_TTL_SECONDS": {
        "key": "SIDEBAR_CONTEXT_TOKEN_TTL_SECONDS",
        "label": "侧边栏上下文兼容有效期",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "旧侧边栏上下文 token 有效期兼容配置（秒）。",
        "min": 1,
    },
    "AICRM_SIDEBAR_JSSDK_ADAPTER_MODE": {
        "key": "AICRM_SIDEBAR_JSSDK_ADAPTER_MODE",
        "label": "侧边栏 JSSDK Adapter 模式",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "默认安全模式；仅显式 real_enabled 且真实开关打开时才允许真实 JSSDK 调用。",
    },
    "AICRM_SIDEBAR_JSSDK_REAL_ENABLED": {
        "key": "AICRM_SIDEBAR_JSSDK_REAL_ENABLED",
        "label": "侧边栏 JSSDK 真实调用开关",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "填写 true / false 或 1 / 0。",
    },
    "AICRM_SIDEBAR_JSSDK_SECRET": {
        "key": "AICRM_SIDEBAR_JSSDK_SECRET",
        "label": "侧边栏 JSSDK Secret",
        "mode": "masked",
        "input_type": "password",
        "type": "secret",
        "description": "侧边栏 JSSDK 专用密钥；留空表示保持原值。",
    },
    "AICRM_SIDEBAR_JSSDK_TIMEOUT_SECONDS": {
        "key": "AICRM_SIDEBAR_JSSDK_TIMEOUT_SECONDS",
        "label": "侧边栏 JSSDK 超时时间",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "侧边栏 JSSDK 请求超时时间（秒）。",
        "min": 1,
    },
    "AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE": {
        "key": "AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE",
        "label": "问卷外推模式",
        "mode": "readonly",
        "input_type": "text",
        "type": "string",
        "description": "已废弃：问卷外推固定只进入统一外部动作队列，legacy/shadow 不再恢复同步外呼。",
    },
    "AICRM_WECOM_EXECUTION_MODE": {
        "key": "AICRM_WECOM_EXECUTION_MODE",
        "label": "企微执行模式",
        "mode": "editable",
        "input_type": "select",
        "type": "string",
        "options": ["disabled", "dry_run", "execute"],
        "description": "统一企微执行主开关：disabled 不执行，dry_run 只验收配置，execute 才允许真实企微外呼。",
    },
    "AICRM_WECOM_ENABLED_EFFECT_TYPES": {
        "key": "AICRM_WECOM_ENABLED_EFFECT_TYPES",
        "label": "企微允许执行 effect types",
        "mode": "editable",
        "input_type": "textarea",
        "type": "string",
        "description": "逗号或换行分隔，仅允许企微 effect type；留空表示没有企微真实执行白名单。",
    },
    "AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE": {
        "key": "AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE",
        "label": "Webhook 队列真实执行",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后仍只执行允许列表中的 webhook effect_type；run-due 默认仍为 dry-run。",
    },
    "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE": {
        "key": "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
        "label": "企微消息队列真实执行",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后仍必须命中 effect_type、owner、target、群 webhook/chat 白名单；不包含标签、欢迎语或批量放大能力。",
    },
    "AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED": {
        "key": "AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED",
        "label": "测试接收端启用",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "仅用于本域名 loopback 验收；生产常态应关闭。",
    },
    "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY": {
        "key": "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY",
        "label": "仅允许测试任务真实执行",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后非 test_loopback / is_test 任务即使命中 allowlist 也会被阻断。",
    },
    "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES": {
        "key": "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
        "label": "允许执行的外部动作类型",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "逗号分隔；禁止 *。问卷外推填写 webhook.questionnaire_submission.push。",
    },
    REALTIME_ENABLED_KEY: {
        "key": REALTIME_ENABLED_KEY,
        "label": "统一队列实时唤醒",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后命中实时 allowlist 的 external_effect_job 会在入队后立即异步执行；渠道码欢迎语必须开启。",
    },
    REALTIME_ALLOWED_TYPES_KEY: {
        "key": REALTIME_ALLOWED_TYPES_KEY,
        "label": "实时唤醒外部动作类型",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "逗号分隔；建议渠道码开启 wecom.welcome_message.send,wecom.contact.tag.mark,wecom.profile.update。",
    },
    REALTIME_MAX_CONCURRENCY_KEY: {
        "key": REALTIME_MAX_CONCURRENCY_KEY,
        "label": "实时唤醒并发上限",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "单进程实时唤醒最多同时执行多少个外部动作；建议 2。",
        "min": 1,
    },
    "AICRM_EXTERNAL_EFFECT_ALLOWED_BASE_HOSTS": {
        "key": "AICRM_EXTERNAL_EFFECT_ALLOWED_BASE_HOSTS",
        "label": "允许生成 loopback URL 的域名",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "逗号分隔；生产应为 www.youcangogogo.com,youcangogogo.com，禁止 localhost / 127.0.0.1 / *。",
    },
    "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS": {
        "key": "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS",
        "label": "企微默认发送账号",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "兼容旧 key；当前执行层取第一个值作为默认 sender，不是完整 allowlist。",
    },
    "AICRM_WECOM_DEFAULT_SENDER_USERID": {
        "key": "AICRM_WECOM_DEFAULT_SENDER_USERID",
        "label": "企微默认 sender_userid",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "真实企微私信/群发在 payload 未指定 sender 时使用的默认发送账号；优先级高于旧 key。",
    },
    "AICRM_EXTERNAL_EFFECT_ALLOWED_TARGET_EXTERNAL_USERIDS": {
        "key": "AICRM_EXTERNAL_EFFECT_ALLOWED_TARGET_EXTERNAL_USERIDS",
        "label": "允许执行的私信客户 external_userid",
        "mode": "editable",
        "input_type": "textarea",
        "type": "string",
        "description": "逗号或换行分隔；真实私信执行必须单目标且命中。",
    },
    "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS": {
        "key": "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS",
        "label": "允许执行的群运营 webhook key",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "逗号分隔；真实群运营消息执行必须命中。",
    },
    "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_CHAT_IDS": {
        "key": "AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_CHAT_IDS",
        "label": "允许执行的群 chat_id",
        "mode": "editable",
        "input_type": "textarea",
        "type": "string",
        "description": "逗号或换行分隔；为空时由 adapter 的单群和 webhook key 约束兜底。",
    },
    "AICRM_WECOM_PRIVATE_ADAPTER_MODE": {
        "key": "AICRM_WECOM_PRIVATE_ADAPTER_MODE",
        "label": "企微私信群发 Adapter 模式",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "disabled / fake / staging / production；渠道码欢迎语兜底使用该 adapter。",
    },
    "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE": {
        "key": "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE",
        "label": "允许真实企微私信群发",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后 wecom.message.private.send 可调用企微 add_msg_template 单客户目标。",
    },
    "AICRM_WECOM_GROUP_ADAPTER_MODE": {
        "key": "AICRM_WECOM_GROUP_ADAPTER_MODE",
        "label": "企微客户群 Adapter 模式",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "disabled / fake / staging / production；群运营群消息使用。",
    },
    "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE": {
        "key": "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE",
        "label": "允许真实企微客户群群发",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后 wecom.message.group.send 可调用企微 add_msg_template 群目标。",
    },
    "AICRM_EXTERNAL_EFFECT_WEBHOOK_TIMEOUT_SECONDS": {
        "key": "AICRM_EXTERNAL_EFFECT_WEBHOOK_TIMEOUT_SECONDS",
        "label": "Webhook 队列请求超时",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "External Effect Queue 调用 webhook 的超时时间（秒）。",
        "min": 1,
    },
    "AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET": {
        "key": "AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET",
        "label": "Webhook 队列签名密钥",
        "mode": "masked",
        "input_type": "password",
        "type": "secret",
        "description": "用于 External Effect Queue webhook HMAC 签名；留空表示保持原值。",
    },
    SCHEDULER_ENABLED_KEY: {
        "key": SCHEDULER_ENABLED_KEY,
        "label": "统一队列自动调度",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "开启后由统一调度器定时捞所有到期 external_effect_job；能力开关只表示允许执行。",
    },
    SCHEDULER_INTERVAL_SECONDS_KEY: {
        "key": SCHEDULER_INTERVAL_SECONDS_KEY,
        "label": "统一队列调度间隔",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "建议 60 秒，即每 1 分钟统一扫描全部到期外部动作队列。",
        "min": 60,
    },
    SCHEDULER_BATCH_SIZE_KEY: {
        "key": SCHEDULER_BATCH_SIZE_KEY,
        "label": "统一队列每轮处理上限",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "调度器每轮最多处理多少条到期任务；实际仍逐条经过安全门禁和 adapter。",
        "min": 1,
    },
    "AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE": {
        "key": "AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE",
        "label": "支付查询队列真实执行（预留）",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "预留配置位；当前 External Effect Queue 未注册真实支付查询 adapter，开启不会产生真实支付查询。",
    },
    "AICRM_EXTERNAL_EFFECT_FEISHU_EXECUTE": {
        "key": "AICRM_EXTERNAL_EFFECT_FEISHU_EXECUTE",
        "label": "Feishu 通知队列真实执行（预留）",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "预留配置位；当前 External Effect Queue 未注册真实 Feishu adapter。",
    },
    "AICRM_EXTERNAL_EFFECT_OPENCLAW_EXECUTE": {
        "key": "AICRM_EXTERNAL_EFFECT_OPENCLAW_EXECUTE",
        "label": "OpenClaw 推送队列真实执行（预留）",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "预留配置位；当前 OpenClaw 真实执行仍由 integration_gateway 安全边界控制。",
    },
    "AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE": {
        "key": "AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE",
        "label": "素材上传队列真实执行（预留）",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "预留配置位；当前 External Effect Queue 未注册真实素材上传 adapter。",
    },
    "WECHAT_SHOP_ENABLED": {
        "key": "WECHAT_SHOP_ENABLED",
        "label": "微信小店已启用",
        "mode": "editable",
        "input_type": "text",
        "type": "boolean",
        "description": "配置中心中的微信小店开关；不会在本次改造中新增业务拦截。",
    },
    "WECHAT_SHOP_APPID": {
        "key": "WECHAT_SHOP_APPID",
        "label": "微信小店 AppID",
        "mode": "editable",
        "input_type": "text",
        "type": "string",
        "description": "微信小店接口使用的 AppID。",
    },
    "WECHAT_SHOP_APPSECRET": {
        "key": "WECHAT_SHOP_APPSECRET",
        "label": "微信小店 AppSecret",
        "mode": "masked",
        "input_type": "password",
        "type": "secret",
        "description": "微信小店接口密钥；留空表示保持原值。",
    },
    "WECHAT_SHOP_API_BASE": {
        "key": "WECHAT_SHOP_API_BASE",
        "label": "微信小店 API Base",
        "mode": "editable",
        "input_type": "url",
        "type": "string",
        "description": "默认 https://api.weixin.qq.com。",
    },
    "WECHAT_SHOP_CALLBACK_TOKEN": {
        "key": "WECHAT_SHOP_CALLBACK_TOKEN",
        "label": "微信小店 Callback Token",
        "mode": "masked",
        "input_type": "password",
        "type": "secret",
        "description": "微信小店回调签名 token；留空表示保持原值。",
    },
    "WECHAT_SHOP_HTTP_TIMEOUT_SECONDS": {
        "key": "WECHAT_SHOP_HTTP_TIMEOUT_SECONDS",
        "label": "微信小店请求超时",
        "mode": "editable",
        "input_type": "number",
        "type": "integer",
        "description": "微信小店接口请求超时时间（秒）。",
        "min": 1,
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _filter_text_match(row: dict[str, Any], fields: list[str], query: str) -> bool:
    normalized = _text(query).lower()
    if not normalized:
        return True
    haystack = " ".join(_text(row.get(field)).lower() for field in fields)
    return normalized in haystack


def _normalize_int(value: Any, *, field_name: str, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} 不能小于 {minimum}")
    return number


def _validate_known_setting(key: str, value: str) -> str:
    normalized = _text(value)
    if key in {
        "WECOM_CORP_TAG_LIMIT",
        "WECOM_ARCHIVE_TIMEOUT",
        "DEEPSEEK_TIMEOUT_SECONDS",
        "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "WECHAT_PAY_TIMEOUT_SECONDS",
        "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS",
        "OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS",
        "AICRM_EXTERNAL_EFFECT_WEBHOOK_TIMEOUT_SECONDS",
    }:
        return str(_normalize_int(normalized or "0", field_name=key, minimum=1))
    if key in {
        "OUTBOUND_WEBHOOK_RETRY_ENABLED",
        "DEEPSEEK_ENABLED",
        "WECHAT_PAY_ENABLED",
        "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED",
        "AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE",
        "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
        REALTIME_ENABLED_KEY,
        "AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED",
        "AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY",
        "AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE",
        "AICRM_EXTERNAL_EFFECT_FEISHU_EXECUTE",
        "AICRM_EXTERNAL_EFFECT_OPENCLAW_EXECUTE",
        "AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE",
        "AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE",
        "AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE",
        "ADMIN_BREAK_GLASS_LOGIN_ENABLED",
    }:
        return "true" if normalized.lower() in {"1", "true", "yes", "y", "on"} else "false"
    if key == "AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE":
        return "queue"
    if key == "AICRM_WECOM_EXECUTION_MODE":
        if not normalized:
            return "disabled"
        if normalized not in {"disabled", "dry_run", "execute"}:
            raise ValueError(f"{key} 只允许 disabled / dry_run / execute")
        return normalized
    if key in {"AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", REALTIME_ALLOWED_TYPES_KEY}:
        if "*" in {item.strip() for item in normalized.replace("\n", " ").replace(",", " ").split() if item.strip()}:
            raise ValueError(f"{key} 不允许使用 *")
        return normalized
    if key == "AICRM_WECOM_ENABLED_EFFECT_TYPES":
        allowed = {
            "wecom.contact.tag.mark",
            "wecom.contact.tag.unmark",
            "wecom.welcome_message.send",
            "wecom.message.private.send",
            "wecom.message.group.send",
            "wecom.profile.update",
        }
        values = [item.strip() for item in normalized.replace("\n", ",").split(",") if item.strip()]
        invalid = sorted({item for item in values if item not in allowed})
        if invalid:
            raise ValueError(f"{key} 包含不支持的企微 effect type: {', '.join(invalid)}")
        return ",".join(values)
    if key in {"AICRM_WECOM_PRIVATE_ADAPTER_MODE", "AICRM_WECOM_GROUP_ADAPTER_MODE"}:
        allowed_modes = {"disabled", "fake", "staging", "production"}
        if normalized and normalized not in allowed_modes:
            raise ValueError(f"{key} 只允许 disabled / fake / staging / production")
        return normalized or "disabled"
    if key == "AICRM_EXTERNAL_EFFECT_ALLOWED_BASE_HOSTS":
        blocked = {"*", "localhost", "127.0.0.1", "::1", "testserver"}
        hosts = {item.strip().lower().split(":", 1)[0] for item in normalized.replace("\n", ",").split(",") if item.strip()}
        if hosts & blocked:
            raise ValueError("AICRM_EXTERNAL_EFFECT_ALLOWED_BASE_HOSTS 不允许使用本地、测试或通配域名")
        return normalized
    if key in {
        "WECOM_API_BASE",
        "DEEPSEEK_BASE_URL",
        "OPENCLAW_WEBHOOK_URL",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
        "WECHAT_PAY_NOTIFY_URL",
        "WECHAT_PAY_API_BASE",
    } and normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{key} 必须以 http:// 或 https:// 开头")
    if key == "WECHAT_PAY_PRODUCT_CATALOG_JSON" and normalized:
        try:
            json.loads(normalized)
        except ValueError as exc:
            raise ValueError("WECHAT_PAY_PRODUCT_CATALOG_JSON 必须是合法 JSON") from exc
    return normalized


def _input_type_for_schema_type(field_type: str) -> str:
    if field_type == "integer":
        return "number"
    if field_type == "secret":
        return "password"
    return "text"


def _schema_setting_metadata() -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for group in CONFIG_SCHEMA.values():
        for key, field in group["fields"].items():
            field_type = _text(field.get("type")) or "string"
            metadata[key] = {
                "key": key,
                "label": _text(field.get("label")) or key,
                "mode": "masked" if field_type == "secret" or key in SENSITIVE_KEYS else "editable",
                "input_type": _input_type_for_schema_type(field_type),
                "type": field_type,
                "description": _text(field.get("help")),
                "required": bool(field.get("required")),
                "default": _text(field.get("default")),
                "min": field.get("min"),
                "max": field.get("max"),
            }
    return metadata


def _setting_metadata_map() -> dict[str, dict[str, Any]]:
    metadata = _schema_setting_metadata()
    for item in APP_SETTING_DEFINITIONS:
        key = _text(item.get("key"))
        if not key:
            continue
        merged = {**metadata.get(key, {}), **dict(item)}
        merged.setdefault("type", "secret" if merged.get("mode") == "masked" else "string")
        merged.setdefault("required", False)
        merged.setdefault("description", "")
        metadata[key] = merged
    for key, item in EXTRA_SETTING_DEFINITIONS.items():
        metadata[key] = {**metadata.get(key, {}), **dict(item)}
    for category in CONFIG_CATEGORIES:
        if category.enabled_key.startswith("CONFIG_CATEGORY_"):
            metadata.setdefault(
                category.enabled_key,
                {
                    "key": category.enabled_key,
                    "label": f"{category.label}生效开关",
                    "mode": "editable",
                    "input_type": "text",
                    "type": "boolean",
                    "description": "仅控制配置中心类目展示状态，不接入业务拦截。",
                    "required": False,
                },
            )
    return metadata


def _metadata_for_setting(key: str) -> dict[str, Any]:
    normalized_key = _text(key)
    metadata = _setting_metadata_map().get(normalized_key, {})
    if metadata:
        return dict(metadata)
    return {
        "key": normalized_key,
        "label": normalized_key,
        "mode": "masked" if normalized_key in SENSITIVE_KEYS else "editable",
        "input_type": "password" if normalized_key in SENSITIVE_KEYS else "text",
        "type": "secret" if normalized_key in SENSITIVE_KEYS else "string",
        "description": "",
        "required": False,
    }


def _is_boolean_setting(key: str, metadata: dict[str, Any]) -> bool:
    return _text(metadata.get("type")) == "boolean" or _text(key).endswith("_ENABLED")


def _is_integer_setting(metadata: dict[str, Any]) -> bool:
    return _text(metadata.get("type")) == "integer" or _text(metadata.get("input_type")) == "number"


def _normalize_boolean_text(value: Any) -> str:
    return "true" if _bool(value) else "false"


def _validate_category_setting(key: str, value: Any, metadata: dict[str, Any]) -> str:
    normalized_key = _text(key)
    normalized = _text(value)
    if _is_boolean_setting(normalized_key, metadata):
        return _normalize_boolean_text(normalized)
    if _is_integer_setting(metadata):
        minimum = metadata.get("min")
        maximum = metadata.get("max")
        minimum_int = int(minimum) if minimum is not None else 1
        number = _normalize_int(normalized or "0", field_name=normalized_key, minimum=minimum_int)
        if maximum is not None and number > int(maximum):
            raise ValueError(f"{normalized_key} 不能大于 {maximum}")
        return str(number)
    if normalized_key in HTTP_URL_SETTING_KEYS and normalized and not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{normalized_key} 必须以 http:// 或 https:// 开头")
    if normalized_key in JSON_SETTING_KEYS and normalized:
        try:
            json.loads(normalized)
        except ValueError as exc:
            raise ValueError(f"{normalized_key} 必须是合法 JSON") from exc
    return _validate_known_setting(normalized_key, normalized)


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _positive_int(value: Any, *, field_name: str, allow_none: bool = False) -> int | None:
    text = _text(value)
    if not text and allow_none:
        return None
    return _normalize_int(text if text else value, field_name=field_name, minimum=1)


def _bounded_int(value: Any, *, field_name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    text = _text(value)
    number = _normalize_int(text if text else default, field_name=field_name, minimum=minimum)
    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} 不能大于 {maximum}")
    return number


def _normalize_timezone(value: Any) -> str:
    timezone = _text(value) or DEFAULT_MARKETING_TIMEZONE
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone is invalid") from exc
    return timezone


def _normalize_silent_thresholds(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, int] = {}
    for pool_key, default_value in DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL.items():
        result[pool_key] = _bounded_int(
            raw.get(pool_key),
            field_name=f"silent_threshold_days_by_pool.{pool_key}",
            default=default_value,
            minimum=1,
        )
    return result


def _default_mcp_tool_defs() -> list[dict[str, Any]]:
    from aicrm_next.integration_gateway.mcp import MCP_TOOLS

    return [dict(item) for item in MCP_TOOLS]


def _default_tool_group(tool_name: str) -> str:
    if tool_name.startswith(("create_", "record_", "send_")):
        return "tasks"
    if "message_batch" in tool_name:
        return "ops"
    if tool_name.startswith(("get_", "resolve_", "search_")):
        return "crm"
    return "misc"


def _default_display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def _tool_group_label(value: str) -> str:
    normalized = _text(value)
    return MCP_TOOL_GROUP_LABELS.get(normalized, normalized or "-")


def _default_tool_description(tool_name: str, fallback: str = "") -> str:
    mapping = {
        "resolve_customer": "根据手机号、客户编号或 external_userid 定位客户。",
        "get_customer_context": "查看客户资料、互动记录和最近聊天。",
        "get_recent_messages": "查看客户最近聊天。",
    }
    return mapping.get(tool_name, fallback)


def _audit_action_label(action_type: str) -> str:
    mapping = {"create": "新建", "update": "更新"}
    normalized = _text(action_type)
    return mapping.get(normalized, normalized or "-")


def _capability_enabled_from_value(value: str, *, default: bool = False) -> bool:
    if not _text(value):
        return bool(default)
    return _bool(value)


def _capability_queue_counts(counts: dict[str, Any]) -> dict[str, int]:
    return {
        "total": int(counts.get("total") or 0),
        "queued": int(counts.get("queued") or 0),
        "planned": int(counts.get("planned") or 0),
        "succeeded": int(counts.get("succeeded") or 0),
        "blocked": int(counts.get("blocked") or 0),
        "failed": int(counts.get("failed") or 0),
        "cancelled": int(counts.get("cancelled") or 0),
    }


def _health_for_capability(*, capability: PushCapability, enabled: bool, counts: dict[str, int], last_error_code: str) -> tuple[str, str]:
    abnormal_count = counts["blocked"] + counts["failed"]
    if capability.readonly_reason:
        return "只读", "neutral"
    if not capability.supports_real_execution:
        return "暂未接入", "neutral"
    if not enabled:
        return "未开启", "warn"
    if abnormal_count or last_error_code:
        return "有异常", "danger"
    return "正常", "ok"


def _effect_type_union_for_enabled_capabilities(read_service: "AdminConfigReadService") -> list[str]:
    effect_types: list[str] = []
    seen: set[str] = set()
    for capability in visible_push_capabilities(main_only=False):
        if not capability.toggleable or not capability.supports_real_execution:
            continue
        value, _source = read_service._setting_value_source(capability.setting_key)
        if not _capability_enabled_from_value(value, default=False):
            continue
        for effect_type in capability.effect_types:
            if effect_type not in seen:
                seen.add(effect_type)
                effect_types.append(effect_type)
        if capability.key == "welcome_message" and WECOM_MESSAGE_PRIVATE_SEND not in seen:
            seen.add(WECOM_MESSAGE_PRIVATE_SEND)
            effect_types.append(WECOM_MESSAGE_PRIVATE_SEND)
    return effect_types


def _derived_gate_payload(effect_types: list[str], capabilities: list[PushCapability]) -> dict[str, Any]:
    enabled_keys = {capability.key for capability in capabilities}
    effect_type_set = set(effect_types)
    channel_entry_realtime_types = [
        effect_type
        for effect_type in CHANNEL_ENTRY_REALTIME_EFFECT_TYPES
        if effect_type in effect_type_set
    ]
    webhook_execute = any(
        capability.key in enabled_keys
        and capability.supports_real_execution
        and capability.adapter_family in {"webhook", "legacy_webhook", "mixed"}
        for capability in visible_push_capabilities(main_only=False)
    )
    wecom_execute = any(effect_type.startswith("wecom.") for effect_type in effect_types)
    payment_execute = any(capability.key in enabled_keys and capability.adapter_family == "payment" for capability in capabilities)
    feishu_execute = "feishu.webhook.notify" in effect_type_set
    openclaw_execute = "openclaw.context.push" in effect_type_set
    media_upload_execute = bool({"media.storage.upload", "wecom.media.upload"} & effect_type_set)
    test_receiver_enabled = "test_receiver" in enabled_keys
    return {
        "allowed_effect_types": effect_types,
        "webhook_execute": webhook_execute,
        "wecom_execute": wecom_execute,
        "payment_execute": payment_execute,
        "feishu_execute": feishu_execute,
        "openclaw_execute": openclaw_execute,
        "media_upload_execute": media_upload_execute,
        "test_receiver_enabled": test_receiver_enabled,
        "realtime_enabled": bool(channel_entry_realtime_types),
        "realtime_allowed_types": channel_entry_realtime_types,
    }


def _capability_requires_webhook_gate(capability: PushCapability) -> bool:
    return capability.adapter_family in {"webhook", "legacy_webhook"} or any(
        effect_type.startswith("webhook.")
        or effect_type in {
            "ai_assist.campaign.message.loopback",
            "group_ops.message.loopback",
            "group_ops.webhook.action.loopback",
        }
        for effect_type in capability.effect_types
    )


def _scheduler_state_for_read_service(read_service: "AdminConfigReadService") -> dict[str, Any]:
    enabled = read_service._capability_enabled_from_setting(SCHEDULER_ENABLED_KEY)
    interval_value, interval_source = read_service._setting_value_source(SCHEDULER_INTERVAL_SECONDS_KEY)
    batch_value, batch_source = read_service._setting_value_source(SCHEDULER_BATCH_SIZE_KEY)
    try:
        interval_seconds = _bounded_int(interval_value, field_name=SCHEDULER_INTERVAL_SECONDS_KEY, default=60, minimum=60, maximum=86400)
    except ValueError:
        interval_seconds = 60
    try:
        batch_size = _bounded_int(batch_value, field_name=SCHEDULER_BATCH_SIZE_KEY, default=20, minimum=1, maximum=500)
    except ValueError:
        batch_size = 20
    return {
        "enabled": enabled,
        "status": "enabled" if enabled else "disabled",
        "status_label": "自动调度已开启" if enabled else "自动调度未开启",
        "interval_seconds": interval_seconds,
        "interval_minutes": max(1, round(interval_seconds / 60)),
        "batch_size": batch_size,
        "interval_source": interval_source,
        "batch_size_source": batch_source,
        "setting_key": SCHEDULER_ENABLED_KEY,
        "description": "统一调度器按固定间隔扫描全部到期任务；业务能力开关只表示允许执行。",
    }


class AdminConfigReadService:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def config_tabs(self, active_key: str) -> list[dict[str, Any]]:
        items = [
            {"key": "overview", "label": "概览", "href": "/admin/config"},
            {"key": "app_settings", "label": "系统设置", "href": "/admin/config/app-settings"},
            {"key": "login_access", "label": "后台访问", "href": "/admin/config/detail/admin_access"},
            {"key": "checklist", "label": "配置检查清单", "href": "/admin/config/checklist"},
        ]
        return [{**item, "active": item["key"] == active_key} for item in items]

    def _setting_value_source(self, key: str) -> tuple[str, str]:
        row = self.repo.get_app_setting(key)
        if row is not None:
            return _text(row.get("value")), "app_settings"
        env_value = _text(os.getenv(key))
        return env_value, "config"

    def _current_setting_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for group in CONFIG_SCHEMA.values():
            for field_key in group["fields"]:
                value, _source = self._setting_value_source(field_key)
                if value:
                    values[field_key] = value
        return values

    def _audit_meta_map(self, target_ids: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for target_id, row in self.repo.latest_audit_map(target_type=TARGET_APP_SETTING, target_ids=target_ids).items():
            result[target_id] = {
                "last_modified_at": _text(row.get("created_at")),
                "last_modified_by": _text(row.get("operator")),
                "last_action_type": _text(row.get("action_type")),
            }
        return result

    def _recent_audit_entries(self, target_type: str, limit: int = 8) -> list[dict[str, str]]:
        return [
            {
                "id": _text(row.get("id")),
                "operator": _text(row.get("operator")),
                "action_type": _text(row.get("action_type")),
                "target_id": _text(row.get("target_id")),
                "created_at": _text(row.get("created_at")),
            }
            for row in self.repo.list_audit_logs(target_type=target_type, limit=limit)
        ]

    def ensure_mcp_tool_settings_seed(self) -> None:
        existing = {item["tool_name"]: item for item in self.repo.list_mcp_tool_settings()}
        for index, tool in enumerate(_default_mcp_tool_defs()):
            tool_name = _text(tool.get("name"))
            if not tool_name or tool_name in existing:
                continue
            self.repo.upsert_mcp_tool_setting(
                tool_name=tool_name,
                tool_group=_default_tool_group(tool_name),
                display_name=_default_display_name(tool_name),
                description_override="",
                enabled=True,
                visible_in_console=True,
                show_sample_args=False,
                show_sample_output=False,
                sort_order=index,
            )

    def build_home_payload(self) -> dict[str, Any]:
        categories = self.list_config_categories()["rows"]
        return {
            "cards": [
                {
                    "label": row["label"],
                    "value": row["status_label"],
                    "description": row["group_label"],
                    "href": row["detail_href"],
                    "key": row["key"],
                    "enabled": row["enabled"],
                }
                for row in categories
            ],
            "categories": categories,
        }

    def list_app_settings(self, *, query: str, scope: str) -> dict[str, Any]:
        definitions = [dict(item) for item in APP_SETTING_DEFINITIONS]
        metadata = {item["key"]: dict(item) for item in definitions}
        audit_map = self._audit_meta_map(list(metadata.keys()))
        rows: list[dict[str, Any]] = []
        for item in definitions:
            value, source = self._setting_value_source(item["key"])
            display_value = mask_value(item["key"], value) if item["mode"] == "masked" else value
            row = {
                **item,
                "value": value if item["mode"] == "editable" else "",
                "display_value": display_value,
                "configured": bool(value),
                "source": source,
            }
            row.update(audit_map.get(item["key"], {"last_modified_at": "", "last_modified_by": "", "last_action_type": ""}))
            if scope and row["mode"] != scope:
                continue
            if not _filter_text_match(row, ["key", "label", "description"], query):
                continue
            rows.append(row)
        editable_count = sum(1 for row in rows if row["mode"] == "editable")
        masked_count = sum(1 for row in rows if row["mode"] == "masked")
        configured_count = sum(1 for row in rows if row["configured"])
        return {
            "rows": rows,
            "metadata_map": metadata,
            "summary_cards": [
                {"label": "可直接编辑", "value": editable_count, "description": "可以直接修改的设置项"},
                {"label": "敏感信息", "value": masked_count, "description": "只显示掩码的设置项"},
                {"label": "已配置", "value": configured_count, "description": "当前已经配置完成的设置项"},
            ],
            "audit_entries": self._recent_audit_entries(TARGET_APP_SETTING, limit=10),
        }

    def _category_enabled(self, category: ConfigCategory) -> bool:
        value, _source = self._setting_value_source(category.enabled_key)
        if not value and category.enabled_key.startswith("CONFIG_CATEGORY_"):
            return True
        return _bool(value)

    def _serialize_category_summary(self, category: ConfigCategory) -> dict[str, Any]:
        enabled = self._category_enabled(category)
        return {
            "key": category.key,
            "label": category.label,
            "group_label": category.group_label,
            "enabled": enabled,
            "status_label": "已生效" if enabled else "未生效",
            "detail_href": category.detail_href,
            "check_supported": category.check_supported,
            "sort_order": category.sort_order,
        }

    def list_config_categories(self) -> dict[str, Any]:
        rows = [self._serialize_category_summary(category) for category in sorted(CONFIG_CATEGORIES, key=lambda item: item.sort_order)]
        return {"rows": rows}

    def _serialize_category_field(self, ref: ConfigCategoryField) -> dict[str, Any]:
        metadata = _metadata_for_setting(ref.key)
        value, source = self._setting_value_source(ref.key)
        sensitive = ref.key in SENSITIVE_KEYS or metadata.get("mode") == "masked" or metadata.get("type") == "secret"
        display_value = mask_value(ref.key, value) if sensitive else value
        return {
            **metadata,
            "key": ref.key,
            "value": "" if sensitive else value,
            "display_value": display_value,
            "configured": bool(value),
            "source": source,
            "sensitive": sensitive,
            "readonly": bool(ref.readonly),
            "block_title": ref.block_title,
        }

    def get_config_category_detail(self, category_key: str) -> dict[str, Any]:
        category = get_config_category(category_key)
        if not category:
            raise KeyError("config category not found")
        if category.key == "webhooks_push":
            return {
                "category": {
                    **self._serialize_category_summary(category),
                    "enabled_key": category.enabled_key,
                    "special_view": "push_capabilities",
                    "capabilities_api": "/api/admin/config/push-capabilities",
                    "push_center_stats_api": "/api/admin/push-center/stats",
                    "push_center_sections_api": "/api/admin/push-center/sections",
                    "push_center_jobs_api": "/api/admin/push-center/jobs",
                },
                "blocks": [],
                "special_view": "push_capabilities",
            }
        blocks_by_title: dict[str, list[dict[str, Any]]] = {}
        for ref in category.fields:
            field_row = self._serialize_category_field(ref)
            blocks_by_title.setdefault(ref.block_title, []).append(field_row)
        return {
            "category": {
                **self._serialize_category_summary(category),
                "enabled_key": category.enabled_key,
            },
            "blocks": [
                {"title": title, "fields": fields}
                for title, fields in blocks_by_title.items()
            ],
        }

    def _capability_enabled(self, capability: PushCapability, *, default: bool = False) -> bool:
        value, _source = self._setting_value_source(capability.setting_key)
        return _capability_enabled_from_value(value, default=default)

    def _capability_gate_consistent(self, capability: PushCapability, *, configured_enabled: bool) -> tuple[bool, str]:
        if not configured_enabled:
            return True, ""
        allowed_types = {
            item.strip()
            for item in _text(self._setting_value_source("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")[0]).replace("\n", ",").split(",")
            if item.strip()
        }
        missing_types = [effect_type for effect_type in capability.effect_types if effect_type not in allowed_types]
        if missing_types:
            return False, "effect_type_allowlist_missing"
        if _capability_requires_webhook_gate(capability) and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE"):
            return False, "webhook_execute_disabled"
        if any(effect_type.startswith("wecom.") for effect_type in capability.effect_types) and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE"):
            return False, "wecom_execute_disabled"
        if capability.adapter_family == "payment" and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE"):
            return False, "payment_execute_disabled"
        if "feishu.webhook.notify" in set(capability.effect_types) and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_FEISHU_EXECUTE"):
            return False, "feishu_execute_disabled"
        if "openclaw.context.push" in set(capability.effect_types) and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_OPENCLAW_EXECUTE"):
            return False, "openclaw_execute_disabled"
        if {"media.storage.upload", "wecom.media.upload"} & set(capability.effect_types) and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE"):
            return False, "media_upload_execute_disabled"
        if capability.key == "test_receiver" and not self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED"):
            return False, "test_receiver_disabled"
        return True, ""

    def _last_problem_for_section(self, section: str, repository: PushCenterRepository) -> dict[str, str]:
        jobs, _total = repository.list_jobs({"section": section}, limit=50, offset=0)
        for job in jobs:
            if _text(job.last_error_code) or job.status in {"blocked", "failed_retryable", "failed_terminal"}:
                return {
                    "last_error_code": _text(job.last_error_code),
                    "last_error_message": _text(job.last_error_message),
                }
        return {"last_error_code": "", "last_error_message": ""}

    def _serialize_push_capability(self, capability: PushCapability, *, repository: PushCenterRepository) -> dict[str, Any]:
        configured_enabled = self._capability_enabled(capability, default=False)
        gate_consistent, gate_problem = self._capability_gate_consistent(capability, configured_enabled=configured_enabled)
        enabled = configured_enabled and gate_consistent
        counts = _capability_queue_counts(repository.counts({"section": capability.section}))
        problem = self._last_problem_for_section(capability.section, repository)
        health_label, health_tone = _health_for_capability(
            capability=capability,
            enabled=enabled,
            counts=counts,
            last_error_code=gate_problem or problem["last_error_code"],
        )
        if configured_enabled and not gate_consistent:
            health_label, health_tone = "门禁未同步", "danger"
        return {
            **capability.to_dict(),
            "enabled": enabled if capability.toggleable else False,
            "configured_enabled": configured_enabled if capability.toggleable else False,
            "gate_consistent": gate_consistent,
            "gate_problem": gate_problem,
            "readonly_reason": capability.readonly_reason,
            "queue_counts": counts,
            "abnormal_count": counts["blocked"] + counts["failed"],
            "last_error_code": problem["last_error_code"],
            "last_error_message": problem["last_error_message"],
            "health_label": health_label,
            "health_tone": health_tone,
        }

    def _advanced_push_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for public_key, setting_key, label in PUSH_CAPABILITY_ADVANCED_KEYS:
            metadata = _metadata_for_setting(setting_key)
            value, _source = self._setting_value_source(setting_key)
            sensitive = setting_key in SENSITIVE_KEYS or metadata.get("mode") == "masked" or metadata.get("type") == "secret"
            items.append(
                {
                    "key": public_key,
                    "label": label,
                    "configured": bool(value),
                    "sensitive": sensitive,
                    "display_value": mask_value(setting_key, value) if sensitive else value,
                }
            )
        return items

    def get_push_capabilities(self, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
        repository = repository or PushCenterRepository()
        capabilities = [self._serialize_push_capability(item, repository=repository) for item in visible_push_capabilities(main_only=True)]
        enabled_count = sum(1 for item in capabilities if item["toggleable"] and item["enabled"])
        toggleable_count = sum(1 for item in capabilities if item["toggleable"])
        abnormal_count = sum(int(item["abnormal_count"]) for item in capabilities)
        test_only = self._capability_enabled_from_setting("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY")
        scheduler = _scheduler_state_for_read_service(self)
        if test_only:
            global_status = "test_only"
        elif enabled_count == 0:
            global_status = "disabled"
        elif enabled_count == toggleable_count:
            global_status = "enabled"
        else:
            global_status = "partial"
        return {
            "ok": True,
            "summary": {
                "total": len(capabilities),
                "enabled_count": enabled_count,
                "toggleable_count": toggleable_count,
                "abnormal_count": abnormal_count,
                "global_status": global_status,
            },
            "capabilities": capabilities,
            "scheduler": scheduler,
            "advanced": {"visible": False, "items": self._advanced_push_items()},
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        }

    def _capability_enabled_from_setting(self, key: str) -> bool:
        value, _source = self._setting_value_source(key)
        return _bool(value)

    def list_mcp_tool_settings(self, *, query: str, enabled_only: bool) -> dict[str, Any]:
        self.ensure_mcp_tool_settings_seed()
        defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _text(item.get("name"))}
        audit_map = self._audit_meta_map_for_type(
            TARGET_MCP_TOOL_SETTING,
            [item["tool_name"] for item in self.repo.list_mcp_tool_settings()],
        )
        rows: list[dict[str, Any]] = []
        for item in self.repo.list_mcp_tool_settings():
            tool_name = _text(item.get("tool_name"))
            default = defaults.get(tool_name, {})
            tool_group = _text(item.get("tool_group")) or _default_tool_group(tool_name)
            raw_display_name = _text(item.get("display_name"))
            description_override = _text(item.get("description_override"))
            row = {
                "tool_name": tool_name,
                "tool_group": tool_group,
                "tool_group_label": _tool_group_label(tool_group),
                "display_name": raw_display_name or _default_display_name(tool_name),
                "description_override": description_override,
                "description": description_override or _default_tool_description(tool_name, _text(default.get("description"))),
                "enabled": _bool(item.get("enabled")),
                "visible_in_console": _bool(item.get("visible_in_console")),
                "show_sample_args": _bool(item.get("show_sample_args")),
                "show_sample_output": _bool(item.get("show_sample_output")),
                "sort_order": int(item.get("sort_order") or 0),
                "updated_at": _text(item.get("updated_at")),
            }
            row.update(audit_map.get(tool_name, {"last_modified_at": "", "last_modified_by": "", "last_action_type": ""}))
            if enabled_only and not row["enabled"]:
                continue
            if not _filter_text_match(row, ["tool_name", "tool_group", "display_name", "description"], query):
                continue
            rows.append(row)
        auth_value, auth_source = self._setting_value_source("MCP_BEARER_TOKEN")
        return {
            "rows": rows,
            "auth_configured": bool(auth_value),
            "auth_source": auth_source,
            "summary_cards": [
                {"label": "工具数量", "value": len(rows), "description": "当前可管理的 AI 工具数量"},
                {"label": "已启用", "value": sum(1 for row in rows if row["enabled"]), "description": "当前允许调用的工具数量"},
                {"label": "后台展示", "value": sum(1 for row in rows if row["visible_in_console"]), "description": "当前在后台显示的工具数量"},
                {"label": "访问令牌", "value": "已配置" if auth_value else "未配置", "description": "AI 工具访问令牌状态"},
            ],
            "audit_entries": [
                {**item, "action_label": _audit_action_label(item["action_type"])}
                for item in self._recent_audit_entries(TARGET_MCP_TOOL_SETTING, limit=8)
            ],
        }

    def _marketing_default_config(self, automation_key: str = DEFAULT_SIGNUP_CONVERSION_KEY) -> dict[str, Any]:
        return {
            "automation_key": _text(automation_key) or DEFAULT_SIGNUP_CONVERSION_KEY,
            "automation_name": DEFAULT_MARKETING_AUTOMATION_NAME,
            "target_event": DEFAULT_MARKETING_TARGET_EVENT,
            "channel_type": DEFAULT_MARKETING_CHANNEL_TYPE,
            "enabled": True,
            "questionnaire_id": None,
            "questionnaire_missing": False,
            "missing_questionnaire_id": None,
            "core_threshold": DEFAULT_MARKETING_CORE_THRESHOLD,
            "top_threshold": DEFAULT_MARKETING_TOP_THRESHOLD,
            "day_start_hour": DEFAULT_MARKETING_DAY_START_HOUR,
            "quiet_hour_start": DEFAULT_MARKETING_QUIET_HOUR_START,
            "timezone": DEFAULT_MARKETING_TIMEZONE,
            "silent_threshold_days_by_pool": dict(DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL),
            "question_rules": [],
            "configured": False,
            "created_at": "",
            "updated_at": "",
        }

    def _questionnaire_rule_context(self, questionnaire_id: int | None) -> tuple[dict[int, dict[str, Any]], dict[int, dict[int, dict[str, Any]]]]:
        if not questionnaire_id:
            return {}, {}
        questions = self.repo.list_questionnaire_questions(int(questionnaire_id))
        question_map = {int(item.get("id") or 0): dict(item) for item in questions}
        option_map: dict[int, dict[int, dict[str, Any]]] = {}
        for option in self.repo.list_questionnaire_options(list(question_map.keys())):
            question_id = int(option.get("question_id") or 0)
            option_id = int(option.get("id") or 0)
            if question_id and option_id:
                option_map.setdefault(question_id, {})[option_id] = dict(option)
        return question_map, option_map

    def _serialize_marketing_rule(
        self,
        row: dict[str, Any],
        *,
        question_map: dict[int, dict[str, Any]],
        option_map: dict[int, dict[int, dict[str, Any]]],
    ) -> dict[str, Any]:
        question_id = int(row.get("question_id") or row.get("questionnaire_question_id") or 0)
        hit_option_ids = [
            int(item)
            for item in _json_loads(row.get("answer_match_value_json") or row.get("hit_option_ids_json"), default=[])
            if _text(item)
        ]
        question = question_map.get(question_id, {})
        available_options = option_map.get(question_id, {})
        return {
            "id": int(row.get("id") or 0),
            "questionnaire_id": int(row.get("questionnaire_id") or 0) or None,
            "questionnaire_question_id": question_id,
            "question_title": _text(question.get("title")) or _text(row.get("rule_name")),
            "question_type": _text(question.get("type")),
            "hit_option_ids_json": hit_option_ids,
            "hit_options": [
                {"id": option_id, "option_text": _text(available_options.get(option_id, {}).get("option_text"))}
                for option_id in hit_option_ids
            ],
            "sort_order": int(row.get("sort_order") or 0),
        }

    def get_signup_conversion_config(self, *, automation_key: str = DEFAULT_SIGNUP_CONVERSION_KEY) -> dict[str, Any]:
        key = _text(automation_key) or DEFAULT_SIGNUP_CONVERSION_KEY
        defaults = self._marketing_default_config(key)
        row = self.repo.get_marketing_automation_config(key)
        if not row:
            return defaults
        payload = dict(_json_loads(row.get("config_payload_json"), default={}) or {})
        questionnaire_id = _positive_int(payload.get("questionnaire_id"), field_name="questionnaire_id", allow_none=True)
        questionnaire_missing = bool(questionnaire_id and not self.repo.get_questionnaire(int(questionnaire_id)))
        question_map, option_map = self._questionnaire_rule_context(None if questionnaire_missing else questionnaire_id)
        return {
            **defaults,
            "automation_key": _text(row.get("automation_key")) or key,
            "automation_name": _text(row.get("automation_name")) or DEFAULT_MARKETING_AUTOMATION_NAME,
            "target_event": _text(row.get("target_event")) or DEFAULT_MARKETING_TARGET_EVENT,
            "channel_type": _text(row.get("channel_type")) or DEFAULT_MARKETING_CHANNEL_TYPE,
            "enabled": _text(row.get("status")).lower() == "active",
            "questionnaire_id": None if questionnaire_missing else questionnaire_id,
            "questionnaire_missing": questionnaire_missing,
            "missing_questionnaire_id": questionnaire_id if questionnaire_missing else None,
            "core_threshold": _bounded_int(payload.get("core_threshold"), field_name="core_threshold", default=DEFAULT_MARKETING_CORE_THRESHOLD, minimum=0),
            "top_threshold": _bounded_int(payload.get("top_threshold"), field_name="top_threshold", default=DEFAULT_MARKETING_TOP_THRESHOLD, minimum=0),
            "day_start_hour": _bounded_int(
                payload.get("day_start_hour"),
                field_name="day_start_hour",
                default=DEFAULT_MARKETING_DAY_START_HOUR,
                minimum=0,
                maximum=23,
            ),
            "quiet_hour_start": _bounded_int(
                row.get("do_not_start_after_hour"),
                field_name="quiet_hour_start",
                default=DEFAULT_MARKETING_QUIET_HOUR_START,
                minimum=0,
                maximum=23,
            ),
            "timezone": _normalize_timezone(payload.get("timezone")),
            "silent_threshold_days_by_pool": _normalize_silent_thresholds(payload.get("silent_threshold_days_by_pool")),
            "question_rules": [
                self._serialize_marketing_rule(item, question_map=question_map, option_map=option_map)
                for item in self.repo.list_marketing_automation_question_rules(int(row.get("id") or 0))
            ],
            "configured": True,
            "created_at": _text(row.get("created_at")),
            "updated_at": _text(row.get("updated_at")),
        }

    def _audit_meta_map_for_type(self, target_type: str, target_ids: list[str]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for target_id, row in self.repo.latest_audit_map(target_type=target_type, target_ids=target_ids).items():
            result[target_id] = {
                "last_modified_at": _text(row.get("created_at")),
                "last_modified_by": _text(row.get("operator")),
                "last_action_type": _text(row.get("action_type")),
            }
        return result

    def schema_groups(self) -> list[dict[str, Any]]:
        return [
            {"label": group["label"], "required": group.get("required", False), "fields": group["fields"]}
            for group in CONFIG_SCHEMA.values()
        ]

    def masked_setting_values(self) -> dict[str, str]:
        return {key: mask_value(key, value) for key, value in self._current_setting_values().items()}

    def build_checklist(self) -> list[dict[str, Any]]:
        return build_config_checklist(self._current_setting_values())

    def build_login_access_payload(self) -> dict[str, Any]:
        rows = self._admin_user_rows()
        login_audit_rows = [
            {
                "created_at": _text(row.get("created_at")),
                "display_name": _text(row.get("display_name")),
                "wecom_userid": _text(row.get("wecom_userid")),
                "login_type": _text(row.get("login_type")),
                "login_result": _text(row.get("login_result")),
                "ip": _text(row.get("ip")),
                "user_agent": _text(row.get("user_agent")),
            }
            for row in self.repo.list_admin_login_audit(limit=20)
        ]
        corp_id = self._setting_value_source("WECOM_CORP_ID")[0]
        directory_members = self._directory_members_from_admin_users(rows, corp_id=corp_id)
        return {
            "rows": rows,
            "super_admin_rows": [row for row in rows if row.get("admin_level") == "super_admin"],
            "admin_rows": [row for row in rows if row.get("admin_level") != "super_admin"],
            "directory_members": directory_members,
            "directory_summary": {
                "count": len(directory_members),
                "authorized_count": sum(1 for row in directory_members if row.get("is_authorized")),
                "last_synced_at": "",
            },
            "role_options": [{"value": key, "label": value} for key, value in ROLE_LABELS.items()],
            "assignable_role_options": list(ADMIN_ASSIGNABLE_ROLE_OPTIONS),
            "role_labels": dict(ROLE_LABELS),
            "admin_level_labels": dict(ADMIN_LEVEL_LABELS),
            "login_audit_rows": login_audit_rows,
            "break_glass_enabled": self._setting_value_source("ADMIN_BREAK_GLASS_LOGIN_ENABLED")[0].lower() in {"1", "true", "yes", "on"},
            "auth_mode": self._setting_value_source("ADMIN_AUTH_MODE")[0] or "wecom_sso",
            "corp_id": corp_id,
        }

    def _admin_user_rows(self) -> list[dict[str, Any]]:
        raw_rows = self.repo.list_admin_users()
        role_rows = self.repo.list_admin_user_roles([int(row.get("id") or 0) for row in raw_rows])
        role_map: dict[int, list[str]] = {}
        for row in role_rows:
            role_map.setdefault(int(row.get("admin_user_id") or 0), []).append(_text(row.get("role_code")))
        rows: list[dict[str, Any]] = []
        for row in raw_rows:
            user_id = int(row.get("id") or 0)
            roles = [role for role in role_map.get(user_id, []) if role]
            admin_level = _text(row.get("admin_level")) or ("super_admin" if "super_admin" in roles else "admin")
            rows.append(
                {
                    **row,
                    "id": user_id,
                    "roles": roles,
                    "role_labels": [ROLE_LABELS.get(role, role) for role in roles],
                    "roles_display": " / ".join(ROLE_LABELS.get(role, role) for role in roles) or "-",
                    "is_active": _bool(row.get("is_active")),
                    "login_enabled": _bool(row.get("login_enabled")),
                    "admin_level": admin_level,
                    "admin_level_label": ADMIN_LEVEL_LABELS.get(admin_level, admin_level),
                }
            )
        return rows

    def _directory_members_from_admin_users(self, rows: list[dict[str, Any]], *, corp_id: str) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            result.append(
                {
                    "wecom_userid": _text(row.get("wecom_userid")),
                    "display_name": _text(row.get("display_name")) or _text(row.get("wecom_userid")),
                    "wecom_corpid": _text(row.get("wecom_corpid")) or corp_id,
                    "department_ids_display": "",
                    "position": "",
                    "status_label": "已授权",
                    "is_authorized": True,
                    "admin_user_id": row.get("id"),
                    "admin_login_enabled": row.get("login_enabled"),
                    "admin_level": row.get("admin_level"),
                    "admin_level_label": row.get("admin_level_label"),
                }
            )
        return result


class AdminConfigWriteCommand:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def execute(self, settings: dict[str, Any], *, operator: str) -> list[dict[str, Any]]:
        metadata = {item["key"]: dict(item) for item in APP_SETTING_DEFINITIONS}
        changed: list[dict[str, Any]] = []
        for key, raw_value in settings.items():
            normalized_key = _text(key)
            if not normalized_key:
                continue
            metadata_row = metadata.get(normalized_key)
            if metadata_row:
                if metadata_row["mode"] == "masked" and _text(raw_value) == "":
                    continue
                validated = _validate_known_setting(normalized_key, _text(raw_value))
            else:
                validated = _text(raw_value)
            before = self.repo.get_app_setting(normalized_key)
            if _text((before or {}).get("value")) == validated:
                continue
            after = self.repo.upsert_app_setting(key=normalized_key, value=validated)
            self.repo.insert_audit_log(
                operator=operator,
                action_type="update" if before else "create",
                target_type=TARGET_APP_SETTING,
                target_id=normalized_key,
                before=before or {},
                after=after,
            )
            changed.append(after)
        return changed

    def _category_or_error(self, category_key: str) -> ConfigCategory:
        category = get_config_category(category_key)
        if not category:
            raise KeyError("config category not found")
        return category

    def set_category_enabled(self, category_key: str, enabled: bool, *, operator: str) -> dict[str, Any]:
        category = self._category_or_error(category_key)
        normalized_value = _normalize_boolean_text(enabled)
        before = self.repo.get_app_setting(category.enabled_key)
        if _text((before or {}).get("value")) == normalized_value:
            return {
                "key": category.key,
                "enabled_key": category.enabled_key,
                "enabled": _bool(normalized_value),
                "changed": False,
            }
        after = self.repo.upsert_app_setting(key=category.enabled_key, value=normalized_value)
        self.repo.insert_audit_log(
            operator=operator,
            action_type="update" if before else "create",
            target_type=TARGET_CONFIG_CATEGORY_ENABLED,
            target_id=category.key,
            before=before or {},
            after=after,
        )
        return {
            "key": category.key,
            "enabled_key": category.enabled_key,
            "enabled": _bool(after.get("value")),
            "changed": True,
        }

    def save_category_settings(self, category_key: str, settings: dict[str, Any], *, operator: str) -> list[dict[str, Any]]:
        category = self._category_or_error(category_key)
        if category.key == "webhooks_push":
            raise ValueError("webhooks_push settings are managed by push capabilities API")
        allowed_refs = {ref.key: ref for ref in category.fields}
        submitted_keys = {_text(key) for key in settings if _text(key)}
        unknown_keys = sorted(key for key in submitted_keys if key not in allowed_refs)
        if unknown_keys:
            raise ValueError(f"setting key is not in category: {', '.join(unknown_keys)}")
        changed: list[dict[str, Any]] = []
        for raw_key, raw_value in settings.items():
            key = _text(raw_key)
            if not key:
                continue
            ref = allowed_refs[key]
            if ref.readonly:
                raise ValueError(f"{key} is readonly")
            metadata = _metadata_for_setting(key)
            if (key in SENSITIVE_KEYS or metadata.get("mode") == "masked") and _text(raw_value) == "":
                continue
            validated = _validate_category_setting(key, raw_value, metadata)
            before = self.repo.get_app_setting(key)
            if _text((before or {}).get("value")) == validated:
                continue
            after = self.repo.upsert_app_setting(key=key, value=validated)
            self.repo.insert_audit_log(
                operator=operator,
                action_type="update" if before else "create",
                target_type=TARGET_APP_SETTING,
                target_id=key,
                before=before or {},
                after=after,
            )
            changed.append(after)
        return changed

    def _upsert_setting_with_audit(self, *, key: str, value: str, operator: str, target_type: str = TARGET_APP_SETTING) -> dict[str, Any]:
        before = self.repo.get_app_setting(key)
        after = self.repo.upsert_app_setting(key=key, value=value)
        if _text((before or {}).get("value")) != _text(after.get("value")):
            self.repo.insert_audit_log(
                operator=operator,
                action_type="update" if before else "create",
                target_type=target_type,
                target_id=key,
                before=before or {},
                after=after,
            )
        return after

    def _enabled_capabilities_for_derivation(self, read_service: AdminConfigReadService) -> list[PushCapability]:
        enabled: list[PushCapability] = []
        for capability in visible_push_capabilities(main_only=False):
            if not capability.toggleable or not capability.supports_real_execution:
                continue
            value, _source = read_service._setting_value_source(capability.setting_key)
            if _capability_enabled_from_value(value, default=False):
                enabled.append(capability)
        return enabled

    def _write_derived_push_gates(self, *, operator: str) -> dict[str, Any]:
        read_service = AdminConfigReadService(self.repo)
        enabled_capabilities = self._enabled_capabilities_for_derivation(read_service)
        effect_types = _effect_type_union_for_enabled_capabilities(read_service)
        gates = _derived_gate_payload(effect_types, enabled_capabilities)
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
            value=",".join(effect_types),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE",
            value=_normalize_boolean_text(gates["webhook_execute"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
            value=_normalize_boolean_text(gates["wecom_execute"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key=REALTIME_ENABLED_KEY,
            value=_normalize_boolean_text(gates["realtime_enabled"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key=REALTIME_ALLOWED_TYPES_KEY,
            value=",".join(gates["realtime_allowed_types"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE",
            value=_normalize_boolean_text(gates["payment_execute"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_FEISHU_EXECUTE",
            value=_normalize_boolean_text(gates["feishu_execute"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_OPENCLAW_EXECUTE",
            value=_normalize_boolean_text(gates["openclaw_execute"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_MEDIA_UPLOAD_EXECUTE",
            value=_normalize_boolean_text(gates["media_upload_execute"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        self._upsert_setting_with_audit(
            key="AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED",
            value=_normalize_boolean_text(gates["test_receiver_enabled"]),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        return gates

    def set_push_capability_enabled(self, capability_key: str, enabled: bool, *, operator: str) -> dict[str, Any]:
        capability = get_push_capability(capability_key)
        if not capability:
            raise KeyError("push capability not found")
        if not capability.toggleable:
            raise PermissionError("push_capability_not_toggleable")
        self._upsert_setting_with_audit(
            key=capability.setting_key,
            value=_normalize_boolean_text(enabled),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        derived = self._write_derived_push_gates(operator=operator)
        capability_payload = AdminConfigReadService(self.repo).get_push_capabilities()["capabilities"]
        current = next(item for item in capability_payload if item["key"] == capability.key)
        return {"capability": current, "derived_gates": derived}

    def set_external_effect_scheduler_enabled(self, enabled: bool, *, operator: str) -> dict[str, Any]:
        self._upsert_setting_with_audit(
            key=SCHEDULER_ENABLED_KEY,
            value=_normalize_boolean_text(enabled),
            operator=operator,
            target_type=TARGET_PUSH_CAPABILITY,
        )
        interval_value, _source = AdminConfigReadService(self.repo)._setting_value_source(SCHEDULER_INTERVAL_SECONDS_KEY)
        if not _text(interval_value):
            self._upsert_setting_with_audit(
                key=SCHEDULER_INTERVAL_SECONDS_KEY,
                value="60",
                operator=operator,
                target_type=TARGET_PUSH_CAPABILITY,
            )
        batch_value, _source = AdminConfigReadService(self.repo)._setting_value_source(SCHEDULER_BATCH_SIZE_KEY)
        if not _text(batch_value):
            self._upsert_setting_with_audit(
                key=SCHEDULER_BATCH_SIZE_KEY,
                value="20",
                operator=operator,
                target_type=TARGET_PUSH_CAPABILITY,
            )
        return {"scheduler": _scheduler_state_for_read_service(AdminConfigReadService(self.repo))}

    def check_category(self, category_key: str, *, operator: str) -> dict[str, Any]:
        del operator
        read_service = AdminConfigReadService(self.repo)
        detail = read_service.get_config_category_detail(category_key)
        category = self._category_or_error(category_key)
        checks: list[dict[str, Any]] = []
        for block in detail["blocks"]:
            for field in block["fields"]:
                key = _text(field.get("key"))
                label = _text(field.get("label")) or key
                value, source = read_service._setting_value_source(key)
                configured = bool(value)
                severity = "error" if field.get("required") else "warning"
                if field.get("required") and not configured:
                    checks.append(
                        {
                            "key": key,
                            "label": label,
                            "check": "required",
                            "status": "failed",
                            "severity": severity,
                            "message": "必填项未配置",
                        }
                    )
                if field.get("sensitive") and not configured:
                    checks.append(
                        {
                            "key": key,
                            "label": label,
                            "check": "sensitive_configured",
                            "status": "warning",
                            "severity": "warning",
                            "message": "敏感字段尚未配置",
                        }
                    )
                if configured:
                    try:
                        _validate_category_setting(key, value, field)
                    except ValueError as exc:
                        checks.append(
                            {
                                "key": key,
                                "label": label,
                                "check": "format",
                                "status": "failed",
                                "severity": "error",
                                "message": str(exc),
                            }
                        )
                    else:
                        checks.append(
                            {
                                "key": key,
                                "label": label,
                                "check": "format",
                                "status": "passed",
                                "severity": "info",
                                "message": f"配置值格式有效（source={source}）",
                            }
                        )
        adapter_preview: dict[str, Any] | None = None
        if category.key == "wechat_pay":
            adapter_preview = {
                "adapter": "wechat_pay",
                "mode": _text(os.getenv("AICRM_NEXT_WECHAT_PAY_MODE")) or "fake",
                "real_external_call_executed": False,
            }
        elif category.key == "alipay":
            adapter_preview = {
                "adapter": "alipay",
                "mode": _text(os.getenv("AICRM_NEXT_ALIPAY_MODE")) or "fake",
                "real_external_call_executed": False,
            }
        elif category.key == "wechat_shop":
            token_value, _source = read_service._setting_value_source("WECHAT_SHOP_CALLBACK_TOKEN")
            adapter_preview = {
                "adapter": "wechat_shop",
                "callback_token_configured": bool(token_value),
                "real_external_call_executed": False,
                "test_order_id_required_for_order_sync": True,
            }
        failed_count = sum(1 for item in checks if item["status"] == "failed")
        warning_count = sum(1 for item in checks if item["status"] == "warning")
        return {
            "ok": failed_count == 0,
            "category": detail["category"],
            "checks": checks,
            "summary": {
                "total": len(checks),
                "failed": failed_count,
                "warnings": warning_count,
            },
            "adapter_preview": adapter_preview,
            "real_external_call_executed": False,
        }


class SetupWizardStateService:
    def __init__(self, read_service: AdminConfigReadService | None = None) -> None:
        self.read_service = read_service or AdminConfigReadService()

    def build_state(self, *, validation_errors: list[dict[str, str]] | None = None, save_success: bool = False) -> dict[str, Any]:
        return {
            "schema_groups": self.read_service.schema_groups(),
            "current_values": self.read_service.masked_setting_values(),
            "validation_errors": validation_errors or [],
            "save_success": save_success,
            "admin_action_token": ensure_admin_action_token(),
        }


class SetupWizardSaveCommand:
    def __init__(
        self,
        read_service: AdminConfigReadService | None = None,
        write_command: AdminConfigWriteCommand | None = None,
    ) -> None:
        self.read_service = read_service or AdminConfigReadService()
        self.write_command = write_command or AdminConfigWriteCommand()

    def execute(self, form_payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        settings_to_save: dict[str, str] = {}
        for raw_key, raw_value in form_payload.items():
            key = _text(raw_key)
            if not key.startswith("setting__"):
                continue
            field_key = key[len("setting__") :]
            value = _text(raw_value)
            if field_key in SENSITIVE_KEYS and not value:
                continue
            settings_to_save[field_key] = value
        merged = self.read_service._current_setting_values()
        merged.update(settings_to_save)
        errors = validate_config(merged)
        if errors:
            return {"ok": False, "validation_errors": errors, "changed": []}
        changed = self.write_command.execute(settings_to_save, operator=operator) if settings_to_save else []
        return {
            "ok": True,
            "validation_errors": [],
            "changed": changed,
            "source_status": "next_command",
            "fallback_used": False,
            "real_external_call_executed": False,
        }


class LoginAccessSaveCommand:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def execute(self, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        wecom_userid = _text(payload.get("wecom_userid"))
        if not wecom_userid:
            raise ValueError("wecom_userid is required")
        admin_level = _text(payload.get("admin_level")) or "admin"
        if admin_level not in {"admin", "super_admin"}:
            raise ValueError("admin_level must be admin or super_admin")
        raw_roles = payload.get("role_codes") or []
        if isinstance(raw_roles, str):
            raw_roles = [raw_roles]
        roles = [_text(role) for role in raw_roles if _text(role) in ROLE_LABELS and _text(role) != "super_admin"]
        if admin_level == "super_admin":
            roles = ["super_admin"]
        elif not roles:
            roles = ["viewer"]
        before = self.repo.get_admin_user(int(payload.get("id") or 0)) if _text(payload.get("id")) else self.repo.get_admin_user_by_wecom_userid(wecom_userid)
        user_payload = {
            "id": int(payload.get("id") or 0),
            "wecom_userid": wecom_userid,
            "wecom_corpid": _text(payload.get("wecom_corpid")),
            "display_name": _text(payload.get("display_name")) or wecom_userid,
            "is_active": _bool(payload.get("is_active", True)),
            "auth_source": _text(payload.get("auth_source")) or "wecom_sso",
            "updated_by": operator,
            "login_enabled": _bool(payload.get("login_enabled", True)),
            "admin_level": admin_level,
        }
        saved = self.repo.upsert_admin_user(user_payload)
        self.repo.replace_admin_user_roles(admin_user_id=int(saved.get("id") or 0), role_codes=roles)
        after = self.repo.get_admin_user(int(saved.get("id") or 0)) or saved
        self.repo.insert_audit_log(
            operator=operator,
            action_type="update" if before else "create",
            target_type=TARGET_ADMIN_USER,
            target_id=_text(after.get("id")),
            before=before or {},
            after={**after, "roles": roles},
        )
        return {**after, "roles": roles}


class McpToolSettingSaveCommand:
    def __init__(self, repo: AdminConfigRepository | None = None, read_service: AdminConfigReadService | None = None) -> None:
        self.repo = repo or AdminConfigRepository()
        self.read_service = read_service or AdminConfigReadService(self.repo)

    def execute(self, payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
        self.read_service.ensure_mcp_tool_settings_seed()
        tool_name = _text(payload.get("tool_name") or payload.get("tool_key"))
        defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _text(item.get("name"))}
        if tool_name not in defaults:
            raise ValueError("工具名称不合法")
        before = self.repo.get_mcp_tool_setting(tool_name)
        saved = self.repo.upsert_mcp_tool_setting(
            tool_name=tool_name,
            tool_group=_text(payload.get("tool_group")) or _default_tool_group(tool_name),
            display_name=_text(payload.get("display_name")) or _default_display_name(tool_name),
            description_override=_text(payload.get("description_override")),
            enabled=_bool(payload.get("enabled")),
            visible_in_console=_bool(payload.get("visible_in_console", True)),
            show_sample_args=_bool(payload.get("show_sample_args")),
            show_sample_output=_bool(payload.get("show_sample_output")),
            sort_order=_normalize_int(payload.get("sort_order") or 0, field_name="sort_order", minimum=0),
        )
        self.repo.insert_audit_log(
            operator=operator,
            action_type="update" if before else "create",
            target_type=TARGET_MCP_TOOL_SETTING,
            target_id=tool_name,
            before=before or {},
            after=saved,
        )
        return {
            **saved,
            "enabled": _bool(saved.get("enabled")),
            "visible_in_console": _bool(saved.get("visible_in_console")),
            "show_sample_args": _bool(saved.get("show_sample_args")),
            "show_sample_output": _bool(saved.get("show_sample_output")),
        }


class SignupConversionConfigSaveCommand:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def _normalize_rules(
        self,
        rules: Any,
        *,
        questionnaire_id: int,
        question_map: dict[int, dict[str, Any]],
        option_map: dict[int, dict[int, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        if not isinstance(rules, list):
            raise ValueError("question_rules must be an array")
        if not rules:
            raise ValueError("question_rules must contain at least one item")
        normalized: list[dict[str, Any]] = []
        seen_question_ids: set[int] = set()
        for index, item in enumerate(rules, start=1):
            if not isinstance(item, dict):
                raise ValueError("question rule must be an object")
            question_id = _positive_int(item.get("questionnaire_question_id"), field_name="questionnaire_question_id")
            assert question_id is not None
            if question_id in seen_question_ids:
                raise ValueError("question_rules cannot contain duplicate questionnaire_question_id")
            seen_question_ids.add(question_id)
            question = question_map.get(question_id)
            if not question:
                raise ValueError(f"question {question_id} does not belong to questionnaire {questionnaire_id}")
            if _text(question.get("type")) not in {"single_choice", "multi_choice"}:
                raise ValueError(f"question {question_id} does not support option matching")
            available_options = option_map.get(question_id, {})
            hit_option_ids = [int(option_id) for option_id in item.get("hit_option_ids_json") or [] if _text(option_id)]
            invalid_option_ids = [option_id for option_id in hit_option_ids if option_id not in available_options]
            if invalid_option_ids:
                raise ValueError(f"option {invalid_option_ids[0]} does not belong to question {question_id}")
            normalized.append(
                {
                    "questionnaire_question_id": int(question_id),
                    "hit_option_ids_json": hit_option_ids,
                    "sort_order": _bounded_int(item.get("sort_order"), field_name="sort_order", default=index, minimum=1),
                    "rule_code": f"question-{question_id}",
                    "rule_name": _text(question.get("title")) or f"question-{question_id}",
                    "rule_payload": {"questionnaire_id": int(questionnaire_id)},
                }
            )
        normalized.sort(key=lambda item: (item["sort_order"], item["questionnaire_question_id"]))
        return normalized

    def execute(self, payload: dict[str, Any], *, operator: str = "crm_console", automation_key: str = DEFAULT_SIGNUP_CONVERSION_KEY) -> dict[str, Any]:
        raw_payload = dict(payload or {})
        key = _text(automation_key) or DEFAULT_SIGNUP_CONVERSION_KEY
        read_service = AdminConfigReadService(self.repo)
        before = read_service.get_signup_conversion_config(automation_key=key)
        questionnaire_id = _positive_int(raw_payload.get("questionnaire_id", before.get("questionnaire_id")), field_name="questionnaire_id")
        assert questionnaire_id is not None
        if not self.repo.get_questionnaire(int(questionnaire_id)):
            raise ValueError("questionnaire not found")
        question_map, option_map = read_service._questionnaire_rule_context(int(questionnaire_id))
        core_threshold = _bounded_int(
            raw_payload.get("core_threshold", before.get("core_threshold")),
            field_name="core_threshold",
            default=DEFAULT_MARKETING_CORE_THRESHOLD,
            minimum=0,
        )
        top_threshold = _bounded_int(
            raw_payload.get("top_threshold", before.get("top_threshold")),
            field_name="top_threshold",
            default=DEFAULT_MARKETING_TOP_THRESHOLD,
            minimum=0,
        )
        if top_threshold < core_threshold:
            raise ValueError("top_threshold must be >= core_threshold")
        day_start_hour = _bounded_int(
            raw_payload.get("day_start_hour", before.get("day_start_hour")),
            field_name="day_start_hour",
            default=DEFAULT_MARKETING_DAY_START_HOUR,
            minimum=0,
            maximum=23,
        )
        quiet_hour_start = _bounded_int(
            raw_payload.get("quiet_hour_start", before.get("quiet_hour_start")),
            field_name="quiet_hour_start",
            default=DEFAULT_MARKETING_QUIET_HOUR_START,
            minimum=0,
            maximum=23,
        )
        if day_start_hour >= quiet_hour_start:
            raise ValueError("day_start_hour must be < quiet_hour_start")
        timezone = _normalize_timezone(raw_payload.get("timezone", before.get("timezone")))
        silent_thresholds = _normalize_silent_thresholds(raw_payload.get("silent_threshold_days_by_pool", before.get("silent_threshold_days_by_pool")))
        rules = self._normalize_rules(
            raw_payload.get("question_rules", before.get("question_rules")),
            questionnaire_id=int(questionnaire_id),
            question_map=question_map,
            option_map=option_map,
        )
        enabled = _bool(raw_payload.get("enabled", before.get("enabled")))
        saved_row = self.repo.upsert_marketing_automation_config(
            automation_key=key,
            automation_name=DEFAULT_MARKETING_AUTOMATION_NAME,
            target_event=DEFAULT_MARKETING_TARGET_EVENT,
            channel_type=DEFAULT_MARKETING_CHANNEL_TYPE,
            status="active" if enabled else "disabled",
            do_not_start_after_hour=quiet_hour_start,
            config_payload={
                "questionnaire_id": int(questionnaire_id),
                "core_threshold": core_threshold,
                "top_threshold": top_threshold,
                "day_start_hour": day_start_hour,
                "timezone": timezone,
                "silent_threshold_days_by_pool": silent_thresholds,
            },
        )
        self.repo.replace_marketing_automation_question_rules(
            automation_config_id=int(saved_row.get("id") or 0),
            questionnaire_id=int(questionnaire_id),
            rules=rules,
        )
        after = read_service.get_signup_conversion_config(automation_key=key)
        if before != after:
            self.repo.insert_audit_log(
                operator=_text(operator) or "crm_console",
                action_type="update" if before.get("configured") else "create",
                target_type=TARGET_MARKETING_AUTOMATION_CONFIG,
                target_id=key,
                before=before,
                after=after,
            )
        return after
