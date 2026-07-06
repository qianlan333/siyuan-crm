from __future__ import annotations

from aicrm_next.shared.runtime_settings import runtime_setting

WECOM_EXECUTION_MODE_KEY = "AICRM_WECOM_EXECUTION_MODE"
WECOM_EXECUTION_DISABLED_CODE = "wecom_execution_disabled"
_MISSING_SETTING = "__aicrm_wecom_execution_mode_missing__"


def is_wecom_effect_type(effect_type: str) -> bool:
    return str(effect_type or "").strip().startswith("wecom.")


def explicit_wecom_execution_disabled() -> bool:
    return runtime_setting(WECOM_EXECUTION_MODE_KEY, _MISSING_SETTING).strip().lower() == "disabled"


def wecom_execution_disabled_message() -> str:
    return f"{WECOM_EXECUTION_MODE_KEY}=disabled blocks WeCom external effects before adapter dispatch."
