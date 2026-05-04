from __future__ import annotations

from typing import Mapping


def build_bearer_auth_headers(token: str | None, *, extra_headers: Mapping[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def redact_secret(value: str | None, *, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"
