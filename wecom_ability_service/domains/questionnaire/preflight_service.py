from __future__ import annotations

from typing import Any, Callable, Mapping


def runtime_config_value(config: Mapping[str, Any], key: str) -> str:
    try:
        from ...infra.settings import get_setting

        setting = get_setting(key)
        if setting is not None:
            return str(setting or "").strip()
    except Exception:
        pass
    return str(config.get(key, "") or "").strip()


def _runtime_config_bool(config: Mapping[str, Any], key: str) -> bool:
    value = runtime_config_value(config, key).lower()
    return value in {"1", "true", "yes", "on"}


def _wechat_oauth_is_configured(config: Mapping[str, Any]) -> bool:
    secret_key = runtime_config_value(config, "SECRET_KEY")
    return bool(
        runtime_config_value(config, "WECHAT_MP_APP_ID")
        and runtime_config_value(config, "WECHAT_MP_APP_SECRET")
        and secret_key
        and secret_key != "dev-secret-key-change-me"
    )


def build_questionnaire_preflight_payload(
    *,
    config: Mapping[str, Any],
    list_available_wecom_tags_fn: Callable[[], list[dict[str, Any]]],
    count_external_contact_identity_maps_fn: Callable[[], int],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "wechat_oauth_configured": _wechat_oauth_is_configured(config),
        "wecom_contact_configured": all(
            runtime_config_value(config, key)
            for key in ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET"]
        ),
        "debug_session_api_enabled": _runtime_config_bool(config, "ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API"),
        "questionnaire_admin_ui_enabled": True,
        "wecom_tags_api_available": False,
        "identity_map_available": False,
    }

    try:
        list_available_wecom_tags_fn()
        payload["wecom_tags_api_available"] = True
    except Exception as exc:
        payload["wecom_tags_api_available"] = False
        payload["wecom_tags_api_error"] = str(exc)

    try:
        count_external_contact_identity_maps_fn()
        payload["identity_map_available"] = True
    except Exception as exc:
        payload["identity_map_available"] = False
        payload["identity_map_error"] = str(exc)

    try:
        from ..automation_conversion.customer_acquisition_service import build_customer_acquisition_preflight_payload

        payload.update(build_customer_acquisition_preflight_payload(config))
    except Exception as exc:
        payload.update(
            {
                "wecom_customer_acquisition_enabled": False,
                "wecom_customer_acquisition_configured": False,
                "wecom_customer_acquisition_secret_present": False,
                "wecom_customer_acquisition_mapping_table_ok": False,
                "wecom_customer_acquisition_callback_handler_ok": False,
                "wecom_customer_acquisition_mapping_table_error": str(exc),
            }
        )

    return payload
