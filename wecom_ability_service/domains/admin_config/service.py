from __future__ import annotations

from datetime import datetime
import json
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app

from ...infra.settings import get_setting, mask_value
from ..admin_auth import count_admin_users
from . import repo

TARGET_APP_SETTING = "app_setting"
TARGET_MCP_TOOL_SETTING = "mcp_tool_setting"

AUTOMATION_CONVERSION_SEGMENT_DEFINITIONS = (
    {
        "segment": "unknown",
        "key": "awaiting_questionnaire",
        "label": "未完成初判",
        "description": "还没提交问卷，暂时留在新用户池。",
    },
    {
        "segment": "normal",
        "key": "normal_followup",
        "label": "普通跟进",
        "description": "当前在普通跟进池，走标准转化动作。",
    },
    {
        "segment": "focus",
        "key": "focus_followup",
        "label": "重点跟进",
        "description": "当前在重点跟进池，优先交给 OpenClaw。",
    },
)

AUTOMATION_CONVERSION_STAGE_DEFINITIONS = (
    {
        "main_stage": "pool",
        "sub_stage": "new_user",
        "key": "new_user_pool",
        "route_key": "new-user",
        "label": "新用户池",
        "description": "刚加好友、还没提交问卷的客户。",
    },
    {
        "main_stage": "pool",
        "sub_stage": "inactive_normal",
        "key": "inactive_normal_pool",
        "route_key": "inactive-normal",
        "label": "未激活普通池",
        "description": "问卷已提交、试用已开通、未激活、普通跟进。",
    },
    {
        "main_stage": "pool",
        "sub_stage": "inactive_focus",
        "key": "inactive_focus_pool",
        "route_key": "inactive-focus",
        "label": "未激活重点跟进池",
        "description": "问卷已提交、试用已开通、未激活、重点跟进。",
    },
    {
        "main_stage": "pool",
        "sub_stage": "active_normal",
        "key": "active_normal_pool",
        "route_key": "active-normal",
        "label": "激活普通池",
        "description": "已激活、普通跟进。",
    },
    {
        "main_stage": "pool",
        "sub_stage": "active_focus",
        "key": "active_focus_pool",
        "route_key": "active-focus",
        "label": "激活重点跟进池",
        "description": "已激活、重点跟进。",
    },
    {
        "main_stage": "pool",
        "sub_stage": "silent",
        "key": "silent_pool",
        "route_key": "silent",
        "label": "沉默池",
        "description": "停留超时后自动进入，当前只做留存记录。",
    },
    {
        "main_stage": "converted",
        "sub_stage": "enrolled",
        "key": "converted",
        "route_key": "converted",
        "label": "已确认成交",
        "description": "人工确认成交后退出全部营销。",
    },
)

AUTOMATION_CONVERSION_DISPATCH_FILTERS = (
    {"value": "", "label": "全部处理结果", "raw_status": ""},
    {"value": "waiting_ai", "label": "等待 AI 接手", "raw_status": "pending"},
    {"value": "night_pause", "label": "夜间暂停", "raw_status": "blocked_quiet_hours"},
    {"value": "ai_received", "label": "AI 已接收", "raw_status": "acked"},
    {"value": "already_converted", "label": "客户已确认成交", "raw_status": "converted_before_dispatch"},
)

APP_SETTING_DEFINITIONS = (
    {
        "key": "WECOM_CORP_ID",
        "label": "企业微信 Corp ID",
        "mode": "editable",
        "input_type": "text",
        "description": "企业微信的唯一标识。",
    },
    {
        "key": "WECOM_AGENT_ID",
        "label": "企业微信 Agent ID",
        "mode": "editable",
        "input_type": "text",
        "description": "企业微信应用的编号。",
    },
    {
        "key": "ADMIN_AUTH_MODE",
        "label": "后台认证模式",
        "mode": "editable",
        "input_type": "text",
        "description": "第一阶段默认 wecom_sso，表示后台主认证使用企业微信 SSO。",
    },
    {
        "key": "ADMIN_LOGIN_REDIRECT_URI",
        "label": "后台登录回调地址",
        "mode": "editable",
        "input_type": "url",
        "description": "企业微信登录完成后回跳的后台地址；为空时按当前域名或可信域名推导。",
    },
    {
        "key": "ADMIN_WECHAT_TRUSTED_DOMAIN",
        "label": "后台可信域名",
        "mode": "editable",
        "input_type": "text",
        "description": "用于拼装企业微信登录回调地址的可信域名，例如 crm.example.com。",
    },
    {
        "key": "WECOM_API_BASE",
        "label": "企业微信接口地址",
        "mode": "editable",
        "input_type": "url",
        "description": "企业微信接口访问地址。",
    },
    {
        "key": "WECOM_DEFAULT_OWNER_USERID",
        "label": "默认负责人账号",
        "mode": "editable",
        "input_type": "text",
        "description": "没有明确负责人时使用的默认负责人账号。",
    },
    {
        "key": "WECOM_PRIVATE_KEY_PATH",
        "label": "会话存档私钥路径",
        "mode": "editable",
        "input_type": "text",
        "description": "会话存档使用的私钥文件路径。",
    },
    {
        "key": "WECOM_SDK_LIB_PATH",
        "label": "会话存档 SDK 路径",
        "mode": "editable",
        "input_type": "text",
        "description": "会话存档 SDK 所在路径。",
    },
    {
        "key": "WECOM_ARCHIVE_TIMEOUT",
        "label": "会话存档超时时间",
        "mode": "editable",
        "input_type": "number",
        "description": "会话存档相关请求的超时时间（秒）。",
    },
    {
        "key": "WECOM_CORP_TAG_LIMIT",
        "label": "企微客户标签上限",
        "mode": "editable",
        "input_type": "number",
        "description": "企微标签管理页面使用的容量提示上限；未配置时默认 1000。",
    },
    {
        "key": "WECHAT_MP_APP_ID",
        "label": "微信公众号 App ID",
        "mode": "editable",
        "input_type": "text",
        "description": "微信授权所使用的公众号 App ID。",
    },
    {
        "key": "WECHAT_MP_OAUTH_SCOPE",
        "label": "微信授权范围",
        "mode": "editable",
        "input_type": "text",
        "description": "微信授权时使用的范围设置。",
    },
    {
        "key": "WECHAT_PAY_ENABLED",
        "label": "微信支付已启用",
        "mode": "editable",
        "input_type": "text",
        "description": "填写 true / false 或 1 / 0。开启后微信内 H5 JSAPI 支付接口才允许下单。",
    },
    {
        "key": "WECHAT_PAY_APP_ID",
        "label": "微信支付 AppID",
        "mode": "editable",
        "input_type": "text",
        "description": "JSAPI 支付使用的公众号 AppID；为空时复用 WECHAT_MP_APP_ID。",
    },
    {
        "key": "WECHAT_PAY_MCH_ID",
        "label": "微信支付商户号",
        "mode": "editable",
        "input_type": "text",
        "description": "微信支付商户平台分配的商户号 mchid。",
    },
    {
        "key": "WECHAT_PAY_PRIVATE_KEY_PATH",
        "label": "微信支付商户私钥路径",
        "mode": "editable",
        "input_type": "text",
        "description": "APIv3 请求签名使用的商户 API 证书私钥 PEM 文件路径。",
    },
    {
        "key": "WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH",
        "label": "微信支付平台证书/公钥路径",
        "mode": "editable",
        "input_type": "text",
        "description": "支付通知验签使用的微信支付平台证书 PEM 或平台公钥 PEM 文件路径。",
    },
    {
        "key": "WECHAT_PAY_PLATFORM_CERT_SERIAL_NO",
        "label": "微信支付平台证书序列号",
        "mode": "editable",
        "input_type": "text",
        "description": "支付通知请求头 Wechatpay-Serial 的期望序列号；为空时只用证书/公钥验签。",
    },
    {
        "key": "WECHAT_PAY_NOTIFY_URL",
        "label": "微信支付通知地址",
        "mode": "editable",
        "input_type": "url",
        "description": "微信支付异步通知 URL，例如 https://www.youcangogogo.com/api/h5/wechat-pay/notify。",
    },
    {
        "key": "WECHAT_PAY_API_BASE",
        "label": "微信支付 API Base",
        "mode": "editable",
        "input_type": "url",
        "description": "默认 https://api.mch.weixin.qq.com。",
    },
    {
        "key": "WECHAT_PAY_TIMEOUT_SECONDS",
        "label": "微信支付请求超时",
        "mode": "editable",
        "input_type": "number",
        "description": "调用微信支付 API 的超时时间（秒）。",
    },
    {
        "key": "WECHAT_PAY_PRODUCT_CATALOG_JSON",
        "label": "微信支付商品目录",
        "mode": "editable",
        "input_type": "textarea",
        "description": "服务端商品白名单 JSON；每个商品需配置 product_code、name、description、amount_total。",
    },
    {
        "key": "WECHAT_PAY_API_V3_KEY",
        "label": "微信支付 APIv3 密钥",
        "mode": "masked",
        "input_type": "password",
        "description": "32 字节 APIv3 密钥，用于回调报文解密。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECHAT_PAY_CERT_SERIAL_NO",
        "label": "微信支付商户证书序列号",
        "mode": "masked",
        "input_type": "password",
        "description": "商户 API 证书序列号，用于请求签名 Authorization。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECOM_SECRET",
        "label": "企业微信 Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "企业微信主应用密钥。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECOM_CONTACT_SECRET",
        "label": "企业微信联系人 Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "企业微信联系人接口密钥。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECOM_ARCHIVE_SECRET",
        "label": "会话存档 Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "会话存档接口密钥。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECOM_CALLBACK_TOKEN",
        "label": "回调 Token",
        "mode": "masked",
        "input_type": "password",
        "description": "回调验证令牌。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECOM_CALLBACK_AES_KEY",
        "label": "回调 AES Key",
        "mode": "masked",
        "input_type": "password",
        "description": "回调加密密钥。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "WECHAT_MP_APP_SECRET",
        "label": "微信公众号 App Secret",
        "mode": "masked",
        "input_type": "password",
        "description": "微信授权密钥。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "AUTOMATION_INTERNAL_API_TOKEN",
        "label": "自动化内部接口令牌",
        "mode": "masked",
        "input_type": "password",
        "description": "统一保护自动化内部动作接口的 Bearer Token。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "MCP_BEARER_TOKEN",
        "label": "MCP 协议访问令牌",
        "mode": "masked",
        "input_type": "password",
        "description": "MCP 协议访问令牌。当前仅保留 /mcp endpoint 兼容能力；页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "ADMIN_BREAK_GLASS_LOGIN_ENABLED",
        "label": "启用 break-glass 应急入口",
        "mode": "editable",
        "input_type": "text",
        "description": "填写 true / false 或 1 / 0。开启后，/login 才会展示本地兜底登录表单。",
    },
    {
        "key": "ADMIN_BREAK_GLASS_USERNAME",
        "label": "break-glass 用户名",
        "mode": "editable",
        "input_type": "text",
        "description": "本地兜底入口用户名，仅在 ADMIN_BREAK_GLASS_LOGIN_ENABLED=true 时生效。",
    },
    {
        "key": "ADMIN_BREAK_GLASS_PASSWORD_HASH",
        "label": "break-glass 密码哈希",
        "mode": "masked",
        "input_type": "password",
        "description": "使用 werkzeug 安全哈希后的兜底密码；页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "OPENCLAW_WEBHOOK_URL",
        "label": "OpenClaw Webhook 地址",
        "mode": "editable",
        "input_type": "url",
        "description": "一键自动化写话术推送到 OpenClaw 的 webhook 地址。",
    },
    {
        "key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "label": "重点跟进消息 Webhook 超时",
        "mode": "editable",
        "input_type": "number",
        "description": "重点跟进消息 webhook 请求超时时间（秒）。",
    },
    {
        "key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN",
        "label": "重点跟进消息 Webhook Token",
        "mode": "masked",
        "input_type": "password",
        "description": "重点跟进消息 webhook Bearer Token。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "LAOHUANG_CHAT_ENABLED",
        "label": "老黄 AI 异步接话已启用",
        "mode": "editable",
        "input_type": "text",
        "description": "填写 true / false 或 1 / 0。开启后 reply monitor 放行会请求老黄 AI 异步聊天接口。",
    },
    {
        "key": "LAOHUANG_CHAT_WEBHOOK_URL",
        "label": "老黄 AI 聊天接口地址",
        "mode": "editable",
        "input_type": "url",
        "description": "AI-CRM 请求老黄 AI 的异步聊天接口地址。",
    },
    {
        "key": "LAOHUANG_CHAT_WEBHOOK_TOKEN",
        "label": "老黄 AI 聊天接口 Token",
        "mode": "masked",
        "input_type": "password",
        "description": "以 URL query 的 token 参数传给老黄 AI 聊天 webhook；页面不会显示完整内容，留空表示保持原值。",
    },
    {
        "key": "LAOHUANG_CHAT_TIMEOUT_SECONDS",
        "label": "老黄 AI 请求超时",
        "mode": "editable",
        "input_type": "number",
        "description": "AI-CRM 请求老黄 AI accepted 接口的超时时间（秒）。",
    },
    {
        "key": "LAOHUANG_CHAT_SEND_CHANNEL",
        "label": "老黄 AI 回复发送通道",
        "mode": "editable",
        "input_type": "text",
        "description": "首版使用 private_message，复用现有企微私聊发送底座。",
    },
    {
        "key": "DEEPSEEK_ENABLED",
        "label": "DeepSeek 已启用",
        "mode": "editable",
        "input_type": "text",
        "description": "填写 true / false 或 1 / 0。控制 CRM 内部 DeepSeek 调用是否启用。",
    },
    {
        "key": "DEEPSEEK_API_KEY",
        "label": "DeepSeek API Key",
        "mode": "masked",
        "input_type": "password",
        "description": "DeepSeek API Key。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "DEEPSEEK_BASE_URL",
        "label": "DeepSeek Base URL",
        "mode": "editable",
        "input_type": "url",
        "description": "DeepSeek 接口基础地址。",
    },
    {
        "key": "DEEPSEEK_ROUTER_MODEL",
        "label": "DeepSeek Router Model",
        "mode": "editable",
        "input_type": "text",
        "description": "中央路由 Agent 默认使用的模型名。",
    },
    {
        "key": "DEEPSEEK_EXECUTION_MODEL",
        "label": "DeepSeek Execution Model",
        "mode": "editable",
        "input_type": "text",
        "description": "执行 Agent 默认使用的模型名。",
    },
    {
        "key": "DEEPSEEK_REASONER_MODEL",
        "label": "DeepSeek Reasoner Model",
        "mode": "editable",
        "input_type": "text",
        "description": "需要更强推理时显式切换使用的模型名，默认 deepseek-reasoner。",
    },
    {
        "key": "DEEPSEEK_TIMEOUT_SECONDS",
        "label": "DeepSeek 超时时间",
        "mode": "editable",
        "input_type": "number",
        "description": "DeepSeek 请求超时时间（秒）。",
    },
    {
        "key": "OUTBOUND_WEBHOOK_RETRY_ENABLED",
        "label": "启用出站 Webhook 自动重试",
        "mode": "editable",
        "input_type": "text",
        "description": "填写 true / false 或 1 / 0。只影响 OpenClaw 焦点消息 webhook 和问卷提交外发 webhook。",
    },
    {
        "key": "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS",
        "label": "出站 Webhook 最大重试次数",
        "mode": "editable",
        "input_type": "number",
        "description": "出站 webhook 首次失败后的最大尝试次数，默认 3。",
    },
    {
        "key": "OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS",
        "label": "出站 Webhook 重试间隔（秒）",
        "mode": "editable",
        "input_type": "number",
        "description": "出站 webhook 失败后进入 retry_scheduled 的间隔秒数，默认 60。",
    },
    {
        "key": "AUTOMATION_ACTIVATION_WEBHOOK_TOKEN",
        "label": "激活回写 Webhook Token",
        "mode": "masked",
        "input_type": "password",
        "description": "外部系统按手机号回写激活状态时使用的校验 Token。已兼容统一内部接口令牌；页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
        "label": "问卷提交外发 Webhook 地址",
        "mode": "editable",
        "input_type": "url",
        "description": "问卷提交成功后，按固定格式外发 mobile / userid / unionid 的 webhook 地址。",
    },
    {
        "key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "label": "问卷提交 Webhook 超时",
        "mode": "editable",
        "input_type": "number",
        "description": "问卷提交外发 webhook 请求超时时间（秒）。",
    },
    {
        "key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN",
        "label": "问卷提交 Webhook Token",
        "mode": "masked",
        "input_type": "password",
        "description": "问卷提交外发 webhook Bearer Token。页面不会显示完整内容；留空表示保持原值。",
    },
    {
        "key": "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED",
        "label": "问卷外推全局总开关",
        "mode": "editable",
        "input_type": "text",
        "description": "填写 true / false 或 1 / 0。关闭后，已开启问卷外推的问卷提交会直接记录“全局关闭跳过”，不再发起外推请求。",
    },
    {
        "key": "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS",
        "label": "问卷外推请求超时",
        "mode": "editable",
        "input_type": "number",
        "description": "问卷外推请求超时时间（秒），默认 3，最大按 10 秒截断。",
    },
)

_SETTING_KEY_ALIASES = {
    "OPENCLAW_WEBHOOK_URL": ("OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL",),
}


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, field_name: str, minimum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} 不能小于 {minimum}")
    return number


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _filter_text_match(row: dict[str, Any], fields: list[str], query: str) -> bool:
    normalized_query = _normalized_text(query).lower()
    if not normalized_query:
        return True
    haystack = " ".join(_normalized_text(row.get(field)).lower() for field in fields)
    return normalized_query in haystack


def _setting_metadata_map() -> dict[str, dict[str, Any]]:
    return {item["key"]: dict(item) for item in APP_SETTING_DEFINITIONS}


def _operator(value: str | None) -> str:
    return _normalized_text(value) or "crm_console"


def _audit_log(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    # Delegates to the unified entry in admin_audit so all three legacy
    # ``_audit_log`` shims share one row format + structured-log emission.
    from ..admin_audit import record_audit

    record_audit(
        operator=_operator(operator),
        action_type=action_type,
        target_type=target_type,
        target_id=_normalized_text(target_id),
        before=before or {},
        after=after or {},
    )


def _audit_meta_map(target_type: str, target_ids: list[str]) -> dict[str, dict[str, str]]:
    raw = repo.get_latest_audit_map(target_type=target_type, target_ids=target_ids)
    return {
        target_id: {
            "last_modified_at": _normalized_text(item.get("created_at")),
            "last_modified_by": _normalized_text(item.get("operator")),
            "last_action_type": _normalized_text(item.get("action_type")),
        }
        for target_id, item in raw.items()
    }


def _apply_audit_meta(rows: list[dict[str, Any]], *, target_type: str, id_field: str) -> list[dict[str, Any]]:
    audit_map = _audit_meta_map(target_type, [_normalized_text(row.get(id_field)) for row in rows])
    enriched: list[dict[str, Any]] = []
    for row in rows:
        row_id = _normalized_text(row.get(id_field))
        enriched.append({**row, **audit_map.get(row_id, {"last_modified_at": "", "last_modified_by": "", "last_action_type": ""})})
    return enriched


def _recent_audit_entries(target_type: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = repo.list_admin_operation_logs(target_type=target_type, limit=limit)
    return [
        {
            "operator": _normalized_text(row.get("operator")),
            "action_type": _normalized_text(row.get("action_type")),
            "target_id": _normalized_text(row.get("target_id")),
            "created_at": _normalized_text(row.get("created_at")),
        }
        for row in rows
    ]


def config_tabs(active_key: str) -> list[dict[str, Any]]:
    items = [
        {"key": "overview", "label": "概览", "href": "/admin/config"},
        {"key": "app_settings", "label": "系统设置", "href": "/admin/config/app-settings"},
        {"key": "login_access", "label": "登录与权限", "href": "/admin/config/login-access"},
        {"key": "checklist", "label": "配置检查清单", "href": "/admin/config/checklist"},
    ]
    return [{**item, "active": item["key"] == active_key} for item in items]


def build_config_home_payload() -> dict[str, Any]:
    app_rows = list_admin_app_settings(query="", scope="")
    return {
        "cards": [
            {
                "label": "系统设置",
                "value": len(app_rows["rows"]),
                "description": "维护渠道、Webhook 与其他系统级参数",
                "href": "/admin/config/app-settings",
            },
            {
                "label": "登录与权限",
                "value": count_admin_users(),
                "description": "维护企微成员授权、角色分配、启停状态与登录审计",
                "href": "/admin/config/login-access",
            },
        ]
    }


def _automation_stage_key(main_stage: str, sub_stage: str) -> str:
    normalized_main_stage = _normalized_text(main_stage)
    normalized_sub_stage = _normalized_text(sub_stage)
    if normalized_main_stage and normalized_sub_stage:
        return f"{normalized_main_stage}/{normalized_sub_stage}"
    return normalized_main_stage or normalized_sub_stage


def _automation_today_string() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def automation_conversion_segment_cards() -> dict[str, Any]:
    counts = repo.get_automation_conversion_segment_counts()
    cards: list[dict[str, Any]] = [
        {
            "key": item["key"],
            "label": item["label"],
            "value": int(counts.get(item["segment"], 0) or 0),
            "description": item["description"],
            "ratio": 0,
        }
        for item in AUTOMATION_CONVERSION_SEGMENT_DEFINITIONS
    ]
    visible_total = sum(int(item["value"]) for item in cards)
    for item in cards:
        item["ratio"] = int(round((int(item["value"]) / visible_total) * 100)) if visible_total else 0
    if cards and visible_total:
        remainder = 100 - sum(int(item["ratio"]) for item in cards)
        cards[-1]["ratio"] = max(0, int(cards[-1]["ratio"]) + remainder)
    unclassified_count = int(counts.get("unknown", 0) or 0)
    return {
        "cards": cards,
        "visible_total": visible_total,
        "unclassified_count": unclassified_count,
        "unclassified_hint": (
            f"另有 {unclassified_count} 位客户还没完成问卷初判。"
            if unclassified_count
            else ""
        ),
    }


def automation_conversion_dispatch_filter_options() -> list[dict[str, str]]:
    return [{"value": item["value"], "label": item["label"]} for item in AUTOMATION_CONVERSION_DISPATCH_FILTERS]


def normalize_automation_conversion_dispatch_filter(value: str) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    alias_map = {item["value"]: item["value"] for item in AUTOMATION_CONVERSION_DISPATCH_FILTERS if item["value"]}
    raw_map = {
        item["raw_status"]: item["value"]
        for item in AUTOMATION_CONVERSION_DISPATCH_FILTERS
        if item["value"] and item["raw_status"]
    }
    if normalized in alias_map:
        return alias_map[normalized]
    return raw_map.get(normalized, "")


def _automation_segment_label(segment: str) -> str:
    normalized_segment = _normalized_text(segment).lower()
    for item in AUTOMATION_CONVERSION_SEGMENT_DEFINITIONS:
        if item["segment"] == normalized_segment:
            return item["label"]
    return "未完成初判"


def _automation_stage_label(main_stage: str, sub_stage: str) -> str:
    stage_key = _automation_stage_key(main_stage, sub_stage)
    mapping = {
        "pool/new_user": "新用户池",
        "pool/inactive_normal": "未激活普通池",
        "pool/inactive_focus": "未激活重点跟进池",
        "pool/active_normal": "激活普通池",
        "pool/active_focus": "激活重点跟进池",
        "pool/silent": "沉默池",
        "converted/enrolled": "已确认成交",
    }
    if stage_key in mapping:
        return mapping[stage_key]
    for item in AUTOMATION_CONVERSION_STAGE_DEFINITIONS:
        if _automation_stage_key(item["main_stage"], item.get("sub_stage", "")) == stage_key:
            return item["label"]
    return "暂无阶段"


def _automation_dispatch_status_label(status: str) -> str:
    normalized_status = _normalized_text(status)
    mapping = {
        "pending": "等待 AI 接手",
        "blocked_quiet_hours": "夜间暂停",
        "acked": "AI 已接收",
        "converted_before_dispatch": "客户已确认成交",
        "dispatched": "已交给 AI",
        "cancelled": "已取消",
    }
    return mapping.get(normalized_status, normalized_status or "暂无结果")


def list_automation_conversion_dispatch_history(*, status: str = "", limit: int = 50) -> dict[str, Any]:
    normalized_status = _normalized_text(status)
    rows = repo.list_automation_conversion_dispatch_history(status=normalized_status, limit=limit)
    items: list[dict[str, Any]] = []
    for row in rows:
        main_stage = _normalized_text(row.get("main_stage"))
        sub_stage = _normalized_text(row.get("sub_stage"))
        stage = _automation_stage_key(main_stage, sub_stage)
        items.append(
            {
                "batch_id": int(row.get("batch_id") or 0),
                "external_userid": _normalized_text(row.get("external_userid")),
                "owner_userid": _normalized_text(row.get("owner_userid")),
                "segment": _normalized_text(row.get("segment")).lower() or "unknown",
                "main_stage": main_stage,
                "sub_stage": sub_stage,
                "stage": stage,
                "dispatch_status": _normalized_text(row.get("dispatch_status")),
                "created_at": _normalized_text(row.get("created_at")),
                "acked_at": _normalized_text(row.get("acked_at")),
            }
        )
    return {
        "status": normalized_status,
        "limit": int(limit),
        "count": len(items),
        "items": items,
    }


def automation_conversion_recent_activity(*, filter_value: str = "", limit: int = 50) -> dict[str, Any]:
    normalized_filter = normalize_automation_conversion_dispatch_filter(filter_value)
    raw_status = next(
        (
            item["raw_status"]
            for item in AUTOMATION_CONVERSION_DISPATCH_FILTERS
            if item["value"] == normalized_filter
        ),
        "",
    )
    history = list_automation_conversion_dispatch_history(status=raw_status, limit=limit)
    items: list[dict[str, Any]] = []
    for item in history["items"]:
        items.append(
            {
                **item,
                "segment_label": _automation_segment_label(item.get("segment", "")),
                "stage_label": _automation_stage_label(item.get("main_stage", ""), item.get("sub_stage", "")),
                "dispatch_status_label": _automation_dispatch_status_label(item.get("dispatch_status", "")),
            }
        )
    return {
        "filter_value": normalized_filter,
        "limit": history["limit"],
        "count": history["count"],
        "items": items,
    }


def _setting_value_source(key: str) -> tuple[str, str]:
    stored = get_setting(key)
    if stored is not None:
        return stored, "app_settings"
    for alias_key in _SETTING_KEY_ALIASES.get(key, ()):
        alias_stored = get_setting(alias_key)
        if alias_stored is not None:
            return alias_stored, "app_settings"
    configured = _normalized_text(current_app.config.get(key, ""))
    if configured:
        return configured, "config"
    for alias_key in _SETTING_KEY_ALIASES.get(key, ()):
        alias_configured = _normalized_text(current_app.config.get(alias_key, ""))
        if alias_configured:
            return alias_configured, "config"
    return "", "config"


def _validate_known_setting(key: str, value: str) -> str:
    normalized = _normalized_text(value)
    if key in {
        "WECOM_ARCHIVE_TIMEOUT",
        "DEEPSEEK_TIMEOUT_SECONDS",
        "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "LAOHUANG_CHAT_TIMEOUT_SECONDS",
        "WECHAT_PAY_TIMEOUT_SECONDS",
        "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS",
        "OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
    }:
        return str(_normalize_int(normalized or "0", field_name=key, minimum=1))
    if key in {
        "OUTBOUND_WEBHOOK_RETRY_ENABLED",
        "DEEPSEEK_ENABLED",
        "LAOHUANG_CHAT_ENABLED",
        "WECHAT_PAY_ENABLED",
    }:
        return "true" if normalized.lower() in {"1", "true", "yes", "y", "on"} else "false"
    if key == "LAOHUANG_CHAT_SEND_CHANNEL":
        if normalized and normalized != "private_message":
            raise ValueError("LAOHUANG_CHAT_SEND_CHANNEL 首版只允许 private_message")
        return normalized or "private_message"
    if key in {
        "WECOM_API_BASE",
        "DEEPSEEK_BASE_URL",
        "OPENCLAW_WEBHOOK_URL",
        "LAOHUANG_CHAT_WEBHOOK_URL",
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


def list_admin_app_settings(*, query: str, scope: str) -> dict[str, Any]:
    metadata_map = _setting_metadata_map()
    audit_map = _audit_meta_map(TARGET_APP_SETTING, list(metadata_map.keys()))
    rows: list[dict[str, Any]] = []
    for item in APP_SETTING_DEFINITIONS:
        value, source = _setting_value_source(item["key"])
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
        "metadata_map": metadata_map,
        "summary_cards": [
            {"label": "可直接编辑", "value": editable_count, "description": "可以直接修改的设置项"},
            {"label": "敏感信息", "value": masked_count, "description": "只显示掩码的设置项"},
            {"label": "已配置", "value": configured_count, "description": "当前已经配置完成的设置项"},
        ],
        "audit_entries": _recent_audit_entries(TARGET_APP_SETTING, limit=10),
    }


def save_admin_app_settings(payload: dict[str, Any], *, operator: str) -> list[dict[str, Any]]:
    metadata_map = _setting_metadata_map()
    changed_rows: list[dict[str, Any]] = []
    for key, raw_value in payload.items():
        normalized_key = _normalized_text(key)
        if not normalized_key:
            continue
        metadata = metadata_map.get(normalized_key)
        if metadata:
            if metadata["mode"] == "masked" and _normalized_text(raw_value) == "":
                continue
            validated = _validate_known_setting(normalized_key, _normalized_text(raw_value))
        else:
            validated = _normalized_text(raw_value)
        before_row = repo.get_app_setting_row(normalized_key)
        before_value = _normalized_text((before_row or {}).get("value"))
        if before_value == validated:
            continue
        repo.upsert_app_setting(key=normalized_key, value=validated)
        after_row = repo.get_app_setting_row(normalized_key) or {}
        _audit_log(
            operator=operator,
            action_type="update" if before_row else "create",
            target_type=TARGET_APP_SETTING,
            target_id=normalized_key,
            before=before_row,
            after=after_row,
        )
        changed_rows.append(after_row)
    return changed_rows


def list_settings_snapshot_compat() -> dict[str, str]:
    # Keep the historical /api/settings payload stable.
    from ...infra.settings import list_settings_snapshot

    return list_settings_snapshot(current_app.config)


def update_settings_compat(settings: dict[str, Any], *, operator: str) -> dict[str, str]:
    save_admin_app_settings(settings, operator=operator)
    return list_settings_snapshot_compat()


def _default_mcp_tool_defs() -> list[dict[str, Any]]:
    from ...mcp_adapter import TOOL_DEFS

    return [dict(item) for item in TOOL_DEFS]


def _default_tool_group(tool_name: str) -> str:
    if tool_name.startswith("create_") or tool_name.startswith("record_") or tool_name.startswith("send_"):
        return "tasks"
    if "message_batch" in tool_name:
        return "ops"
    if tool_name == "get_owner_role_map":
        return "config"
    if tool_name.startswith("get_") or tool_name.startswith("resolve_") or tool_name.startswith("search_"):
        return "crm"
    return "misc"


def _tool_group_label(value: str) -> str:
    mapping = {
        "crm": "客户查询",
        "tasks": "触达任务",
        "config": "配置规则",
        "ops": "同步任务",
        "misc": "其他",
    }
    normalized = _normalized_text(value)
    return mapping.get(normalized, normalized or "-")


def _legacy_default_display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def _default_display_name(tool_name: str) -> str:
    mapping = {
        "resolve_customer": "定位客户",
        "get_contact": "查看客户资料",
        "get_customer_context": "查看客户上下文",
        "get_messages": "查看聊天历史",
        "get_recent_messages": "查看最近聊天",
        "search_messages": "搜索聊天内容",
        "get_group_chat": "查看群聊资料",
        "mark_tags": "添加客户标签",
        "unmark_tags": "移除客户标签",
        "update_customer_tags": "更新客户标签",
        "create_private_message_task": "创建单聊任务",
        "create_group_message_task": "创建群发任务",
        "create_moment_task": "创建朋友圈任务",
        "record_conversion_feedback": "记录转化反馈",
        "get_owner_role_map": "查看负责人角色",
        "get_pending_message_batches": "查看待确认消息批次",
        "get_message_batch": "查看消息批次详情",
        "ack_message_batch": "确认消息批次",
        "get_customer_marketing_profile": "查看营销画像",
        "get_pending_conversion_batches": "查看待转化批次",
        "get_conversion_batch": "查看转化批次详情",
        "ack_conversion_batch": "确认转化批次",
        "get_signup_conversion_batches": "查看转化自动化批次",
        "get_signup_conversion_batch": "查看转化自动化详情",
        "get_owner_recent_chat_dump": "查看负责人最近聊天",
        "get_hourly_followup_candidates": "查看跟进候选",
        "send_pool_private_message": "按池子群发",
    }
    return mapping.get(tool_name, _legacy_default_display_name(tool_name))


def _default_tool_description(tool_name: str, fallback: str = "") -> str:
    mapping = {
        "resolve_customer": "根据手机号或客户编号定位客户。",
        "get_contact": "查看单个客户的基础资料。",
        "get_customer_context": "查看客户资料、互动记录和最近聊天。",
        "get_messages": "查看客户完整聊天历史。",
        "get_recent_messages": "查看客户最近聊天。",
        "search_messages": "按关键词搜索客户聊天内容。",
        "get_group_chat": "查看群聊资料。",
        "mark_tags": "给客户添加标签。",
        "unmark_tags": "移除客户标签。",
        "update_customer_tags": "统一处理客户标签更新。",
        "create_private_message_task": "创建单聊触达任务。",
        "create_group_message_task": "创建群发触达任务。",
        "create_moment_task": "创建朋友圈触达任务。",
        "record_conversion_feedback": "记录转化反馈；当 feedback_type 为 mark_enrolled/unmark_enrolled 时同步统一转化真相。",
        "get_owner_role_map": "查看负责人角色配置。",
        "get_pending_message_batches": "查看待确认的消息批次。",
        "get_message_batch": "查看单个消息批次详情。",
        "ack_message_batch": "确认消息批次已处理。",
        "get_customer_marketing_profile": "查看 CRM 整理好的营销画像。",
        "get_pending_conversion_batches": "查看已经通过 CRM 路由筛选的待转化批次。",
        "get_conversion_batch": "查看单个待转化批次及其营销画像。",
        "ack_conversion_batch": "确认 OpenClaw 已消费转化批次。",
        "get_signup_conversion_batches": "查看经过 CRM 转化规则筛选后的自动化批次。",
        "get_signup_conversion_batch": "查看单个自动化批次及其客户画像。",
        "get_owner_recent_chat_dump": "查看某位负责人的最近聊天记录。",
        "get_hourly_followup_candidates": "查看建议优先跟进的客户。",
        "send_pool_private_message": "按当前池子直接调用 CRM 群发能力，并记录发送记录。",
    }
    return mapping.get(tool_name, fallback)


def _audit_action_label(action_type: str) -> str:
    mapping = {
        "create": "新建",
        "update": "更新",
    }
    normalized = _normalized_text(action_type)
    return mapping.get(normalized, normalized or "-")


def ensure_mcp_tool_settings_seed() -> None:
    existing = {item["tool_name"]: item for item in repo.list_mcp_tool_settings()}
    for index, tool in enumerate(_default_mcp_tool_defs()):
        tool_name = _normalized_text(tool.get("name"))
        if not tool_name or tool_name in existing:
            continue
        repo.upsert_mcp_tool_setting(
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


def list_mcp_tool_settings(*, query: str, enabled_only: bool) -> dict[str, Any]:
    ensure_mcp_tool_settings_seed()
    defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _normalized_text(item.get("name"))}
    rows = []
    for item in repo.list_mcp_tool_settings():
        tool_name = _normalized_text(item.get("tool_name"))
        default = defaults.get(tool_name, {})
        raw_display_name = _normalized_text(item.get("display_name"))
        tool_group = _normalized_text(item.get("tool_group")) or _default_tool_group(tool_name)
        row = {
            "tool_name": tool_name,
            "tool_group": tool_group,
            "tool_group_label": _tool_group_label(tool_group),
            "display_name": _default_display_name(tool_name) if not raw_display_name or raw_display_name == _legacy_default_display_name(tool_name) else raw_display_name,
            "description_override": _normalized_text(item.get("description_override")),
            "description": _normalized_text(item.get("description_override")) or _default_tool_description(tool_name, _normalized_text(default.get("description"))),
            "enabled": bool(item.get("enabled")),
            "visible_in_console": bool(item.get("visible_in_console")),
            "show_sample_args": bool(item.get("show_sample_args")),
            "show_sample_output": bool(item.get("show_sample_output")),
            "sort_order": int(item.get("sort_order") or 0),
            "updated_at": _normalized_text(item.get("updated_at")),
        }
        if enabled_only and not row["enabled"]:
            continue
        if not _filter_text_match(row, ["tool_name", "tool_group", "display_name", "description"], query):
            continue
        rows.append(row)
    rows = _apply_audit_meta(rows, target_type=TARGET_MCP_TOOL_SETTING, id_field="tool_name")
    auth_value, auth_source = _setting_value_source("MCP_BEARER_TOKEN")
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
            {**item, "action_label": _audit_action_label(_normalized_text(item.get("action_type")))}
            for item in _recent_audit_entries(TARGET_MCP_TOOL_SETTING, limit=8)
        ],
    }


def save_mcp_tool_setting(payload: dict[str, Any], *, operator: str) -> dict[str, Any]:
    tool_name = _normalized_text(payload.get("tool_name"))
    defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _normalized_text(item.get("name"))}
    if tool_name not in defaults:
        raise ValueError("工具名称不合法")
    before = repo.get_mcp_tool_setting(tool_name)
    repo.upsert_mcp_tool_setting(
        tool_name=tool_name,
        tool_group=_normalized_text(payload.get("tool_group")) or _default_tool_group(tool_name),
        display_name=_normalized_text(payload.get("display_name")) or _default_display_name(tool_name),
        description_override=_normalized_text(payload.get("description_override")),
        enabled=_normalize_bool(payload.get("enabled")),
        visible_in_console=_normalize_bool(payload.get("visible_in_console")),
        show_sample_args=_normalize_bool(payload.get("show_sample_args")),
        show_sample_output=_normalize_bool(payload.get("show_sample_output")),
        sort_order=_normalize_int(payload.get("sort_order") or 0, field_name="sort_order", minimum=0),
    )
    saved = repo.get_mcp_tool_setting(tool_name) or {}
    _audit_log(
        operator=operator,
        action_type="update" if before else "create",
        target_type=TARGET_MCP_TOOL_SETTING,
        target_id=tool_name,
        before=before,
        after=saved,
    )
    return dict(saved)


def list_mcp_runtime_tools() -> list[dict[str, Any]]:
    payload = list_mcp_tool_settings(query="", enabled_only=True)
    defaults = {item["name"]: item for item in _default_mcp_tool_defs() if _normalized_text(item.get("name"))}
    result: list[dict[str, Any]] = []
    for row in sorted(payload["rows"], key=lambda item: (int(item.get("sort_order") or 0), item["tool_name"])):
        default = defaults.get(row["tool_name"], {})
        result.append(
            {
                **default,
                "name": row["tool_name"],
                "description": row["description"],
            }
        )
    return result


def mcp_tool_enabled(tool_name: str) -> bool:
    payload = list_mcp_tool_settings(query="", enabled_only=False)
    matched = next((item for item in payload["rows"] if item["tool_name"] == _normalized_text(tool_name)), None)
    return bool((matched or {}).get("enabled"))
