from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ...infra.http_client import OutboundHttpClient, OutboundHttpError


class WeChatPayClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class WeChatPayClientConfig:
    app_id: str
    mch_id: str
    api_v3_key: str
    private_key_path: str
    merchant_serial_no: str
    platform_public_key_path: str = ""
    platform_serial_no: str = ""
    api_base: str = "https://api.mch.weixin.qq.com"
    timeout_seconds: int = 10


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path or "/"
    return f"{path}?{parsed.query}" if parsed.query else path


def _json_body(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _load_private_key(path: str):
    if not _normalized_text(path):
        raise WeChatPayClientError("WECHAT_PAY_PRIVATE_KEY_PATH is required")
    try:
        key_bytes = Path(path).read_bytes()
        return serialization.load_pem_private_key(key_bytes, password=None)
    except Exception as exc:  # pragma: no cover - file/env defensive path
        raise WeChatPayClientError(f"failed to load WeChat Pay merchant private key: {exc}") from exc


def _load_public_key(path: str):
    if not _normalized_text(path):
        raise WeChatPayClientError("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH is required for notify signature verify")
    try:
        key_bytes = Path(path).read_bytes()
        try:
            return serialization.load_pem_public_key(key_bytes)
        except ValueError:
            return x509.load_pem_x509_certificate(key_bytes).public_key()
    except Exception as exc:  # pragma: no cover - file/env defensive path
        raise WeChatPayClientError(f"failed to load WeChat Pay platform public key/certificate: {exc}") from exc


class WeChatPayClient:
    """Thin WeChat Pay API v3 client for JSAPI payment.

    It intentionally keeps a narrow surface: create JSAPI order, query by
    out_trade_no, submit refunds, sign frontend pay params, and verify/decrypt
    payment notifications. Product and business order rules stay in service.py.
    """

    def __init__(self, config: WeChatPayClientConfig, *, http_client: OutboundHttpClient | None = None) -> None:
        self.config = config
        self.http = http_client or OutboundHttpClient(
            "wechat_pay",
            timeout=max(1, int(config.timeout_seconds or 10)),
            retry_max=1,
            retry_backoff_base=0.5,
        )

    def _merchant_signature(self, message: str) -> str:
        private_key = _load_private_key(self.config.private_key_path)
        signature = private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def _authorization_header(self, *, method: str, canonical_url: str, body: str) -> str:
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f"{method.upper()}\n{canonical_url}\n{timestamp}\n{nonce}\n{body}\n"
        signature = self._merchant_signature(message)
        return (
            "WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{self.config.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{self.config.merchant_serial_no}",'
            f'signature="{signature}"'
        )

    def _request_json(self, method: str, api_path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = _json_body(payload or {}) if method.upper() != "GET" else ""
        canonical = _canonical_url(api_path)
        url = f"{self.config.api_base.rstrip('/')}{canonical}"
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization_header(method=method, canonical_url=canonical, body=body),
            "Content-Type": "application/json",
        }
        platform_serial_no = _normalized_text(self.config.platform_serial_no)
        if platform_serial_no.startswith("PUB_KEY_ID_"):
            headers["Wechatpay-Serial"] = platform_serial_no
        try:
            response = self.http.request(method, url, data=body.encode("utf-8"), headers=headers)
        except OutboundHttpError as exc:
            raise WeChatPayClientError(str(exc)) from exc
        try:
            response_payload = response.json() if response.text else {}
        except ValueError:
            response_payload = {"raw": response.text}
        if response.status_code >= 300:
            message = str(response_payload.get("message") or response_payload.get("code") or response.text or "wechat_pay_http_error")
            raise WeChatPayClientError(message, status_code=response.status_code, payload=response_payload)
        return response_payload

    def create_jsapi_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/v3/pay/transactions/jsapi", payload=payload)

    def query_order_by_out_trade_no(self, out_trade_no: str) -> dict[str, Any]:
        trade_no = _normalized_text(out_trade_no)
        if not trade_no:
            raise WeChatPayClientError("out_trade_no is required")
        return self._request_json("GET", f"/v3/pay/transactions/out-trade-no/{trade_no}?mchid={self.config.mch_id}")

    def create_refund(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/v3/refund/domestic/refunds", payload=payload)

    def build_jsapi_pay_params(self, prepay_id: str) -> dict[str, str]:
        package_value = f"prepay_id={_normalized_text(prepay_id)}"
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f"{self.config.app_id}\n{timestamp}\n{nonce}\n{package_value}\n"
        return {
            "appId": self.config.app_id,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package_value,
            "signType": "RSA",
            "paySign": self._merchant_signature(message),
        }

    def verify_notification_signature(self, *, body: str, headers: dict[str, Any]) -> None:
        timestamp = _normalized_text(headers.get("Wechatpay-Timestamp") or headers.get("wechatpay-timestamp"))
        nonce = _normalized_text(headers.get("Wechatpay-Nonce") or headers.get("wechatpay-nonce"))
        signature = _normalized_text(headers.get("Wechatpay-Signature") or headers.get("wechatpay-signature"))
        serial_no = _normalized_text(headers.get("Wechatpay-Serial") or headers.get("wechatpay-serial"))
        if not timestamp or not nonce or not signature:
            raise WeChatPayClientError("missing WeChat Pay notify signature headers")
        expected_serial = _normalized_text(self.config.platform_serial_no)
        if expected_serial and serial_no and serial_no != expected_serial:
            raise WeChatPayClientError("unexpected WeChat Pay platform certificate serial")
        message = f"{timestamp}\n{nonce}\n{body}\n".encode("utf-8")
        public_key = _load_public_key(self.config.platform_public_key_path)
        try:
            public_key.verify(
                base64.b64decode(signature),
                message,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (InvalidSignature, ValueError) as exc:
            raise WeChatPayClientError("invalid WeChat Pay notify signature") from exc

    def decrypt_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        key = _normalized_text(self.config.api_v3_key).encode("utf-8")
        if len(key) != 32:
            raise WeChatPayClientError("WECHAT_PAY_API_V3_KEY must be 32 bytes")
        try:
            nonce = _normalized_text(resource.get("nonce")).encode("utf-8")
            associated_data = _normalized_text(resource.get("associated_data")).encode("utf-8")
            ciphertext = base64.b64decode(_normalized_text(resource.get("ciphertext")))
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data)
            payload = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise WeChatPayClientError("failed to decrypt WeChat Pay notify resource") from exc
        if not isinstance(payload, dict):
            raise WeChatPayClientError("invalid WeChat Pay notify resource payload")
        return payload

    def verify_and_decrypt_notification(self, *, body: str, headers: dict[str, Any]) -> dict[str, Any]:
        self.verify_notification_signature(body=body, headers=headers)
        try:
            payload = json.loads(body or "{}")
        except ValueError as exc:
            raise WeChatPayClientError("invalid WeChat Pay notify JSON") from exc
        resource = payload.get("resource")
        if not isinstance(resource, dict):
            raise WeChatPayClientError("missing WeChat Pay notify resource")
        return self.decrypt_resource(resource)
