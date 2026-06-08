from __future__ import annotations

from typing import Any

from ..db import get_db


DEFAULT_OPENCLAW_WEBHOOK_URL = "http://claw.youcangogogo.com/webhook"
DEFAULT_LAOHUANG_CHAT_WEBHOOK_URL = "https://www.youcangogogo.com/api/webhook/crm/chat"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_ROUTER_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_EXECUTION_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"
DEFAULT_DEEPSEEK_TIMEOUT_SECONDS = 30

SENSITIVE_KEYS = {
    "AUTOMATION_INTERNAL_API_TOKEN",
    "AUTOMATION_ACTIVATION_WEBHOOK_TOKEN",
    "DEEPSEEK_API_KEY",
    "MCP_BEARER_TOKEN",
    "LAOHUANG_CHAT_WEBHOOK_TOKEN",
    "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN",
    "QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN",
    "SIDEBAR_THIRD_PARTY_API_TOKEN",
    "WECOM_CONTACT_SECRET",
    "WECOM_SECRET",
    "WECOM_ARCHIVE_SECRET",
    "WECOM_CALLBACK_TOKEN",
    "WECOM_CALLBACK_AES_KEY",
    "WECHAT_MP_APP_SECRET",
    "WECHAT_PAY_API_V3_KEY",
    "WECHAT_PAY_CERT_SERIAL_NO",
    "ADMIN_BREAK_GLASS_PASSWORD_HASH",
}

_SETTING_KEY_ALIASES = {
    "OPENCLAW_WEBHOOK_URL": ("OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL",),
}


def mask_value(key: str, value: str) -> str:
    if key not in SENSITIVE_KEYS:
        return value
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-2:]}"


def get_setting(key: str) -> str | None:
    row = get_db().execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _setting_with_alias(config: dict[str, Any], key: str) -> str:
    value = get_setting(key)
    if value is not None:
        return value
    for alias_key in _SETTING_KEY_ALIASES.get(key, ()):
        alias_value = get_setting(alias_key)
        if alias_value is not None:
            return alias_value
    configured = str(config.get(key, ""))
    if configured:
        return configured
    for alias_key in _SETTING_KEY_ALIASES.get(key, ()):
        alias_configured = str(config.get(alias_key, ""))
        if alias_configured:
            return alias_configured
    return ""


def set_settings(settings: dict[str, Any]) -> None:
    db = get_db()
    for key, value in settings.items():
        db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, str(value)),
        )
    db.commit()


def list_settings_snapshot(config: dict[str, Any]) -> dict[str, str]:
    keys = [
        "WECOM_CORP_ID",
        "WECOM_SECRET",
        "WECOM_CONTACT_SECRET",
        "WECOM_AGENT_ID",
        "WECOM_API_BASE",
        "WECOM_ARCHIVE_SECRET",
        "WECOM_PRIVATE_KEY_PATH",
        "WECOM_SDK_LIB_PATH",
        "WECOM_DEFAULT_OWNER_USERID",
        "WECOM_CALLBACK_TOKEN",
        "WECOM_CALLBACK_AES_KEY",
        "WECOM_CORP_TAG_LIMIT",
        "WECOM_ARCHIVE_TIMEOUT",
        "ADMIN_AUTH_MODE",
        "ADMIN_LOGIN_REDIRECT_URI",
        "ADMIN_WECHAT_TRUSTED_DOMAIN",
        "ADMIN_BREAK_GLASS_LOGIN_ENABLED",
        "ADMIN_BREAK_GLASS_USERNAME",
        "ADMIN_BREAK_GLASS_PASSWORD_HASH",
        "WECHAT_MP_APP_ID",
        "WECHAT_MP_APP_SECRET",
        "WECHAT_MP_OAUTH_SCOPE",
        "WECHAT_PAY_ENABLED",
        "WECHAT_PAY_APP_ID",
        "WECHAT_PAY_MCH_ID",
        "WECHAT_PAY_API_V3_KEY",
        "WECHAT_PAY_PRIVATE_KEY_PATH",
        "WECHAT_PAY_CERT_SERIAL_NO",
        "WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH",
        "WECHAT_PAY_PLATFORM_CERT_SERIAL_NO",
        "WECHAT_PAY_NOTIFY_URL",
        "WECHAT_PAY_API_BASE",
        "WECHAT_PAY_TIMEOUT_SECONDS",
        "WECHAT_PAY_PRODUCT_CATALOG_JSON",
        "ALIPAY_ENABLED",
        "ALIPAY_APP_ID",
        "ALIPAY_APP_PRIVATE_KEY_PATH",
        "ALIPAY_PUBLIC_KEY_PATH",
        "ALIPAY_SERVER_URL",
        "ALIPAY_SIGN_TYPE",
        "ALIPAY_NOTIFY_URL",
        "ALIPAY_RETURN_URL",
        "ALIPAY_TIMEOUT_EXPRESS",
        "ALIPAY_TIMEOUT_SECONDS",
        "ALIPAY_SELLER_ID",
        "AUTOMATION_INTERNAL_API_TOKEN",
        "LAOHUANG_CHAT_ENABLED",
        "LAOHUANG_CHAT_WEBHOOK_URL",
        "LAOHUANG_CHAT_WEBHOOK_TOKEN",
        "LAOHUANG_CHAT_TIMEOUT_SECONDS",
        "LAOHUANG_CHAT_SEND_CHANNEL",
        "DEEPSEEK_ENABLED",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_ROUTER_MODEL",
        "DEEPSEEK_EXECUTION_MODEL",
        "DEEPSEEK_REASONER_MODEL",
        "DEEPSEEK_TIMEOUT_SECONDS",
        "OPENCLAW_WEBHOOK_URL",
        "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN",
        "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "OUTBOUND_WEBHOOK_RETRY_ENABLED",
        "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS",
        "OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS",
        "AUTOMATION_ACTIVATION_WEBHOOK_TOKEN",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED",
        "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS",
    ]
    snapshot: dict[str, str] = {}
    for key in keys:
        value = _setting_with_alias(config, key)
        snapshot[key] = mask_value(key, value)
    return snapshot
