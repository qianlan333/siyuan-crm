from __future__ import annotations

import os
from dataclasses import dataclass, field

from .auth import build_bearer_auth_headers


@dataclass(slots=True)
class CrmApiConfig:
    base_url: str
    api_token: str = ""
    mcp_bearer_token: str = ""
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.2
    retry_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)
    retry_methods: tuple[str, ...] = ("GET",)
    request_source: str = "openclaw-cloud"
    prefer_customer_endpoints: bool = True
    prefer_timeline_endpoint: bool = True
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "CrmApiConfig":
        base_url = os.getenv("CRM_API_BASE_URL", "").rstrip("/")
        return cls(
            base_url=base_url,
            api_token=os.getenv("CRM_API_TOKEN", ""),
            mcp_bearer_token=os.getenv("CRM_MCP_BEARER_TOKEN", ""),
            timeout_seconds=float(os.getenv("CRM_API_TIMEOUT_MS", "10000")) / 1000.0,
            max_retries=int(os.getenv("CRM_API_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("CRM_API_RETRY_BACKOFF_SECONDS", "0.2")),
            prefer_customer_endpoints=os.getenv("CRM_PREFER_CUSTOMER_ENDPOINTS", "true").lower() in {"1", "true", "yes"},
            prefer_timeline_endpoint=os.getenv("CRM_PREFER_TIMELINE_ENDPOINT", "true").lower() in {"1", "true", "yes"},
        )

    def default_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-OpenClaw-Source": self.request_source,
        }
        headers.update(self.headers)
        headers.update(build_bearer_auth_headers(self.api_token))
        return headers

    def mcp_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-OpenClaw-Source": self.request_source,
        }
        headers.update(build_bearer_auth_headers(self.mcp_bearer_token))
        return headers
