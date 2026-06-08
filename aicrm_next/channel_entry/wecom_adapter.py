from __future__ import annotations

import os
import time
from typing import Any

import requests

from .domain import text


class WeComAdapterBlocked(RuntimeError):
    def __init__(self, reason: str, *, missing_config: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.missing_config = list(missing_config or [])


class WeComApiError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__("wecom_api_error")
        self.message = message
        self.payload = dict(payload or {})


class GuardedWeComAdapter:
    """Adapter boundary for WeCom side effects.

    Real calls are intentionally not enabled here. Tests and staging wiring can
    inject an object with the same methods.
    """

    def __init__(
        self,
        *,
        welcome_reason: str = "wecom_welcome_external_call_blocked",
        tag_reason: str = "wecom_tag_external_call_blocked",
        contact_way_reason: str = "wecom_contact_way_external_call_blocked",
        detail_reason: str = "wecom_contact_detail_external_call_blocked",
        transfer_reason: str = "wecom_transfer_external_call_blocked",
        missing_config: list[str] | None = None,
    ) -> None:
        self.welcome_reason = welcome_reason
        self.tag_reason = tag_reason
        self.contact_way_reason = contact_way_reason
        self.detail_reason = detail_reason
        self.transfer_reason = transfer_reason
        self.missing_config = list(missing_config or [])

    def send_welcome_msg(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise WeComAdapterBlocked(self.welcome_reason, missing_config=self.missing_config)

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        raise WeComAdapterBlocked(self.tag_reason, missing_config=self.missing_config)

    def create_contact_way(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise WeComAdapterBlocked(self.contact_way_reason, missing_config=self.missing_config)

    def get_external_contact_detail(self, external_userid: str) -> dict[str, Any]:
        raise WeComAdapterBlocked(self.detail_reason, missing_config=self.missing_config)

    def transfer_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise WeComAdapterBlocked(self.transfer_reason, missing_config=self.missing_config)

    def transfer_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise WeComAdapterBlocked(self.transfer_reason, missing_config=self.missing_config)


class ProductionWeComAdapter:
    def __init__(
        self,
        *,
        corp_id: str | None = None,
        secret: str | None = None,
        api_base: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.corp_id = text(corp_id or os.getenv("WECOM_CORP_ID"))
        self.secret = text(secret or os.getenv("WECOM_CONTACT_SECRET") or os.getenv("WECOM_SECRET"))
        self.api_base = text(api_base or os.getenv("WECOM_API_BASE") or "https://qyapi.weixin.qq.com").rstrip("/")
        self.timeout = float(timeout or os.getenv("WECOM_TIMEOUT_SECONDS") or 15)
        self._access_token = ""
        self._token_expires_at = 0.0

    def get_access_token(self) -> str:
        if self._access_token and self._token_expires_at > time.time():
            return self._access_token
        payload = self._request_without_token(
            "GET",
            "/cgi-bin/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.secret},
        )
        if int(payload.get("errcode") or 0) != 0:
            raise WeComApiError("gettoken failed", payload=payload)
        token = text(payload.get("access_token"))
        if not token:
            raise WeComApiError("gettoken missing access_token", payload=payload)
        expires_in = int(payload.get("expires_in") or 7200)
        self._access_token = token
        self._token_expires_at = time.time() + max(60, expires_in - 60)
        return token

    def _request_without_token(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                f"{self.api_base}{path}",
                params=params or {},
                json=json_payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise WeComApiError(str(exc)) from exc
        return dict(payload or {})

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        request_params = {"access_token": access_token}
        request_params.update(params or {})
        payload = self._request_without_token(method, path, params=request_params, json_payload=json_payload)
        if int(payload.get("errcode") or 0) != 0:
            raise WeComApiError(f"WeCom API failed for {path}", payload=payload)
        return payload

    def send_welcome_msg(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/cgi-bin/externalcontact/send_welcome_msg", json_payload=payload)

    def mark_external_contact_tags(
        self,
        *,
        external_userid: str,
        follow_user_userid: str,
        add_tags: list[str],
        remove_tags: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "userid": text(follow_user_userid),
            "external_userid": text(external_userid),
            "add_tag": [text(tag) for tag in add_tags if text(tag)],
        }
        normalized_remove_tags = [text(tag) for tag in (remove_tags or []) if text(tag)]
        if normalized_remove_tags:
            payload["remove_tag"] = normalized_remove_tags
        return self._request("POST", "/cgi-bin/externalcontact/mark_tag", json_payload=payload)

    def create_contact_way(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/cgi-bin/externalcontact/add_contact_way", json_payload=payload)

    def get_external_contact_detail(self, external_userid: str) -> dict[str, Any]:
        return self._request("GET", "/cgi-bin/externalcontact/get", params={"external_userid": text(external_userid)})

    def transfer_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/cgi-bin/externalcontact/transfer_customer", json_payload=payload)

    def transfer_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/cgi-bin/externalcontact/transfer_result", json_payload=payload)


_adapter: Any | None = None


def _real_calls_enabled() -> bool:
    return text(os.getenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED")).lower() in {"1", "true", "yes", "on"}


def missing_wecom_config() -> list[str]:
    missing: list[str] = []
    if not text(os.getenv("WECOM_CORP_ID")):
        missing.append("WECOM_CORP_ID")
    if not (text(os.getenv("WECOM_CONTACT_SECRET")) or text(os.getenv("WECOM_SECRET"))):
        missing.append("WECOM_CONTACT_SECRET")
    return missing


def wecom_adapter_diagnostics() -> dict[str, Any]:
    missing = missing_wecom_config()
    enabled = _real_calls_enabled() and not missing
    if enabled:
        reason = "enabled"
    elif missing:
        reason = "missing_wecom_config"
    else:
        reason = "wecom_real_calls_disabled"
    return {
        "real_wecom_adapter_enabled": enabled,
        "real_wecom_adapter_reason": reason,
        "missing_config": missing,
        "can_send_welcome": enabled,
        "can_mark_tag": enabled,
        "can_create_contact_way": enabled,
        "can_transfer_customer": enabled,
    }


def _build_default_adapter() -> Any:
    diagnostics = wecom_adapter_diagnostics()
    reason = text(diagnostics["real_wecom_adapter_reason"])
    if reason == "enabled":
        return ProductionWeComAdapter()
    if reason == "missing_wecom_config":
        return GuardedWeComAdapter(
            welcome_reason="missing_wecom_config",
            tag_reason="missing_wecom_config",
            contact_way_reason="missing_wecom_config",
            detail_reason="missing_wecom_config",
            transfer_reason="missing_wecom_config",
            missing_config=list(diagnostics["missing_config"]),
        )
    return GuardedWeComAdapter(
        welcome_reason="wecom_real_calls_disabled",
        tag_reason="wecom_real_calls_disabled",
        contact_way_reason="wecom_real_calls_disabled",
        detail_reason="wecom_real_calls_disabled",
        transfer_reason="wecom_real_calls_disabled",
    )


def set_wecom_adapter(adapter: Any) -> None:
    global _adapter
    _adapter = adapter


def get_wecom_adapter() -> Any:
    return _adapter if _adapter is not None else _build_default_adapter()
