from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import requests

from .config import CrmApiConfig
from .errors import CrmBusinessError, CrmHttpError, CrmTransportError

crm_logger = logging.getLogger("openclaw.crm")


class CrmApiClient:
    def __init__(self, config: CrmApiConfig, *, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self.request("GET", path, params=params, headers=headers, timeout=timeout)

    def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        return self.request("POST", path, params=params, json=json, headers=headers, timeout=timeout)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        request_id = str(uuid.uuid4())
        url = self._build_url(path)
        merged_headers = self.config.default_headers()
        if headers:
            merged_headers.update(headers)
        merged_headers["X-Request-Id"] = request_id
        request_timeout = timeout if timeout is not None else self.config.timeout_seconds

        attempts = self.config.max_retries + 1 if method.upper() in self.config.retry_methods else 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            started_at = time.monotonic()
            try:
                response = self.session.request(
                    method.upper(),
                    url,
                    params=params,
                    json=json,
                    headers=merged_headers,
                    timeout=request_timeout,
                )
            except requests.RequestException as exc:
                last_error = CrmTransportError(
                    "CRM transport request failed",
                    path=path,
                    request_id=request_id,
                    details={"attempt": attempt, "error": str(exc)},
                )
                crm_logger.warning(
                    "crm request transport failure method=%s path=%s request_id=%s attempt=%s error=%s",
                    method.upper(),
                    path,
                    request_id,
                    attempt,
                    exc,
                )
                if attempt >= attempts:
                    raise last_error
                time.sleep(self.config.retry_backoff_seconds * attempt)
                continue

            duration_ms = int((time.monotonic() - started_at) * 1000)
            crm_logger.info(
                "crm request method=%s path=%s status=%s duration_ms=%s request_id=%s",
                method.upper(),
                path,
                response.status_code,
                duration_ms,
                request_id,
            )

            if response.status_code >= 400:
                error = CrmHttpError(
                    "CRM returned HTTP error",
                    path=path,
                    request_id=request_id,
                    status_code=response.status_code,
                    response_text=response.text[:1000],
                    details={"attempt": attempt},
                )
                if response.status_code in self.config.retry_status_codes and attempt < attempts:
                    time.sleep(self.config.retry_backoff_seconds * attempt)
                    continue
                raise error

            payload = self._decode_payload(response, path=path, request_id=request_id)
            self._raise_business_error_if_needed(payload, path=path, request_id=request_id)
            return payload

        if last_error:
            raise last_error
        raise CrmTransportError("CRM request failed without a response", path=path, request_id=request_id)

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        base_url = self.config.base_url.rstrip("/")
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{base_url}{clean_path}"

    @staticmethod
    def _decode_payload(response: requests.Response, *, path: str, request_id: str) -> Any:
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        body = response.text.strip()
        if not body:
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw_text": body}

    @staticmethod
    def _raise_business_error_if_needed(payload: Any, *, path: str, request_id: str) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("ok") is False:
            raise CrmBusinessError(
                message=str(payload.get("error") or payload.get("message") or "CRM business error"),
                path=path,
                request_id=request_id,
                error_code=str(payload.get("code") or ""),
                response_payload=payload,
            )
