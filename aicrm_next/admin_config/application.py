from __future__ import annotations

import json
import os
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aicrm_next.admin_jobs.routes import ensure_admin_action_token

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
    "LAOHUANG_CHAT_WEBHOOK_URL",
    "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
    "WECHAT_PAY_NOTIFY_URL",
    "WECHAT_PAY_API_BASE",
    "ALIPAY_SERVER_URL",
    "ALIPAY_NOTIFY_URL",
    "ALIPAY_RETURN_URL",
    "WECHAT_SHOP_API_BASE",
}
JSON_SETTING_KEYS = {"WECHAT_PAY_PRODUCT_CATALOG_JSON"}
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
        "LAOHUANG_CHAT_TIMEOUT_SECONDS",
        "WECHAT_PAY_TIMEOUT_SECONDS",
        "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS",
        "OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS",
        "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS",
    }:
        return str(_normalize_int(normalized or "0", field_name=key, minimum=1))
    if key in {
        "OUTBOUND_WEBHOOK_RETRY_ENABLED",
        "DEEPSEEK_ENABLED",
        "LAOHUANG_CHAT_ENABLED",
        "WECHAT_PAY_ENABLED",
        "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED",
        "ADMIN_BREAK_GLASS_LOGIN_ENABLED",
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
        "get_automation_context": "查看自动化成员上下文。",
    }
    return mapping.get(tool_name, fallback)


def _audit_action_label(action_type: str) -> str:
    mapping = {"create": "新建", "update": "更新"}
    normalized = _text(action_type)
    return mapping.get(normalized, normalized or "-")


class AdminConfigReadService:
    def __init__(self, repo: AdminConfigRepository | None = None) -> None:
        self.repo = repo or AdminConfigRepository()

    def config_tabs(self, active_key: str) -> list[dict[str, Any]]:
        items = [
            {"key": "overview", "label": "概览", "href": "/admin/config"},
            {"key": "app_settings", "label": "系统设置", "href": "/admin/config/app-settings"},
            {"key": "login_access", "label": "登录与权限", "href": "/admin/config/login-access"},
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
