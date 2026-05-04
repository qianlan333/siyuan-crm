from __future__ import annotations

from typing import Any, Callable, Mapping


def _wechat_oauth_is_configured(config: Mapping[str, Any]) -> bool:
    secret_key = str(config.get("SECRET_KEY", "") or "").strip()
    return bool(
        config.get("WECHAT_MP_APP_ID")
        and config.get("WECHAT_MP_APP_SECRET")
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
            str(config.get(key, "") or "").strip()
            for key in ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET"]
        ),
        "debug_session_api_enabled": bool(config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API")),
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

    return payload
