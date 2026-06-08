from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AlipayPayClientError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class AlipayPayClientConfig:
    app_id: str
    app_private_key_path: str
    alipay_public_key_path: str
    server_url: str = "https://openapi.alipay.com/gateway.do"
    sign_type: str = "RSA2"
    timeout_seconds: int = 10


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _load_key_text(path: str, *, label: str) -> str:
    normalized = _normalized_text(path)
    if not normalized:
        raise AlipayPayClientError(f"{label} path is required")
    try:
        return Path(normalized).read_text(encoding="utf-8").strip()
    except Exception as exc:  # pragma: no cover - file/env defensive path
        raise AlipayPayClientError(f"failed to load {label}: {exc}") from exc


class AlipayPayClient:
    """Thin Alipay OpenAPI client.

    The SDK imports are lazy so the CRM can import and test the domain without
    live Alipay dependencies until an enabled payment path actually calls it.
    """

    def __init__(self, config: AlipayPayClientConfig) -> None:
        self.config = config
        self._client = None

    def _sdk_client(self):
        if self._client is not None:
            return self._client
        try:
            from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
            from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
        except Exception as exc:  # pragma: no cover - depends on deployment env
            raise AlipayPayClientError("alipay-sdk-python package is required") from exc

        sdk_config = AlipayClientConfig()
        sdk_config.server_url = _normalized_text(self.config.server_url) or "https://openapi.alipay.com/gateway.do"
        sdk_config.app_id = _normalized_text(self.config.app_id)
        sdk_config.app_private_key = _load_key_text(self.config.app_private_key_path, label="Alipay app private key")
        sdk_config.alipay_public_key = _load_key_text(self.config.alipay_public_key_path, label="Alipay public key")
        sdk_config.sign_type = _normalized_text(self.config.sign_type) or "RSA2"
        sdk_config.timeout = max(1, int(self.config.timeout_seconds or 10))
        self._client = DefaultAlipayClient(alipay_client_config=sdk_config)
        return self._client

    def create_wap_pay_url(
        self,
        *,
        biz_payload: dict[str, Any],
        notify_url: str,
        return_url: str,
    ) -> str:
        try:
            from alipay.aop.api.domain.AlipayTradeWapPayModel import AlipayTradeWapPayModel
            from alipay.aop.api.request.AlipayTradeWapPayRequest import AlipayTradeWapPayRequest
        except Exception as exc:  # pragma: no cover - depends on deployment env
            raise AlipayPayClientError("alipay-sdk-python package is required") from exc

        model = AlipayTradeWapPayModel()
        for key, value in biz_payload.items():
            if hasattr(model, key):
                setattr(model, key, value)
        request = AlipayTradeWapPayRequest(biz_model=model)
        request.notify_url = _normalized_text(notify_url)
        request.return_url = _normalized_text(return_url)
        payment_url = self._sdk_client().page_execute(request, http_method="GET")
        if not _normalized_text(payment_url):
            raise AlipayPayClientError("missing Alipay WAP payment URL")
        return payment_url

    def query_order(self, out_trade_no: str) -> dict[str, Any]:
        trade_no = _normalized_text(out_trade_no)
        if not trade_no:
            raise AlipayPayClientError("out_trade_no is required")
        try:
            from alipay.aop.api.domain.AlipayTradeQueryModel import AlipayTradeQueryModel
            from alipay.aop.api.request.AlipayTradeQueryRequest import AlipayTradeQueryRequest
        except Exception as exc:  # pragma: no cover - depends on deployment env
            raise AlipayPayClientError("alipay-sdk-python package is required") from exc

        model = AlipayTradeQueryModel()
        model.out_trade_no = trade_no
        request = AlipayTradeQueryRequest(biz_model=model)
        response_content = self._sdk_client().execute(request)
        if isinstance(response_content, bytes):
            response_content = response_content.decode("utf-8")
        if isinstance(response_content, str):
            try:
                payload = json.loads(response_content)
            except ValueError as exc:
                raise AlipayPayClientError("invalid Alipay query response", payload={"raw": response_content}) from exc
        elif isinstance(response_content, dict):
            payload = response_content
        else:
            payload = {"raw": response_content}
        response = payload.get("alipay_trade_query_response") if isinstance(payload.get("alipay_trade_query_response"), dict) else payload
        if _normalized_text(response.get("code")) and _normalized_text(response.get("code")) != "10000":
            message = _normalized_text(response.get("sub_msg")) or _normalized_text(response.get("msg")) or "alipay_trade_query_failed"
            raise AlipayPayClientError(message, payload=response)
        return dict(response)

    def verify_notification(self, params: dict[str, Any]) -> bool:
        signature = _normalized_text(params.get("sign"))
        if not signature:
            raise AlipayPayClientError("missing Alipay notify sign")
        try:
            from alipay.aop.api.util.SignatureUtils import get_sign_content, verify_with_rsa
        except Exception as exc:  # pragma: no cover - depends on deployment env
            raise AlipayPayClientError("alipay-sdk-python package is required") from exc

        sign_params = {
            key: value
            for key, value in params.items()
            if key not in {"sign", "sign_type"} and _normalized_text(value)
        }
        sign_content = get_sign_content(sign_params)
        public_key = _load_key_text(self.config.alipay_public_key_path, label="Alipay public key")
        try:
            return bool(verify_with_rsa(public_key, sign_content.encode("utf-8"), signature))
        except Exception as exc:
            raise AlipayPayClientError("invalid Alipay notify signature") from exc
