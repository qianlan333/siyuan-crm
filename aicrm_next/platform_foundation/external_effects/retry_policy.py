from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

RETRYABLE_ERROR_CODES = {"timeout", "network_error", "rate_limited", "http_408", "http_429", "http_5xx", "adapter_exception"}
TERMINAL_ERROR_CODES = {
    "http_400",
    "http_401",
    "http_403",
    "http_404",
    "payload_invalid",
    "target_not_found",
    "config_missing",
}
BLOCKED_ERROR_CODES = {
    "adapter_blocked",
    "execution_disabled",
    "shadow_only",
    "plan_only",
    "effect_type_not_allowed",
    "unsupported_effect_type",
    "payment_execution_disabled",
    "push_capability_disabled",
    "push_capability_readonly",
}

_RETRY_DELAYS_SECONDS = (60, 300, 900, 3600)


def classify_error_code(error_code: str, *, status_code: int | None = None) -> str:
    code = str(error_code or "").strip()
    if status_code:
        if status_code in {408, 429}:
            return "retryable"
        if status_code >= 500:
            return "retryable"
        if status_code in {400, 401, 403, 404}:
            return "terminal"
    if code in RETRYABLE_ERROR_CODES:
        return "retryable"
    if code in TERMINAL_ERROR_CODES:
        return "terminal"
    if code in BLOCKED_ERROR_CODES:
        return "blocked"
    return "terminal" if code else "blocked"


def retry_delay_seconds(attempt_count: int) -> int:
    index = max(0, min(int(attempt_count or 0), len(_RETRY_DELAYS_SECONDS) - 1))
    return _RETRY_DELAYS_SECONDS[index]


def next_retry_at(
    attempt_count: int,
    *,
    now: datetime | None = None,
    retry_after_seconds: int | float | None = None,
) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    policy_delay = retry_delay_seconds(attempt_count)
    try:
        provider_delay = max(0, min(float(retry_after_seconds or 0), 86400))
    except (TypeError, ValueError):
        provider_delay = 0
    return current + timedelta(seconds=max(policy_delay, provider_delay))


def status_for_failure(*, error_code: str, attempt_count: int, max_attempts: int, status_code: int | None = None) -> str:
    classification = classify_error_code(error_code, status_code=status_code)
    if classification == "retryable" and int(attempt_count or 0) < int(max_attempts or 0):
        return "failed_retryable"
    return "failed_terminal"


def http_error_code(status_code: int | None) -> str:
    if status_code is None:
        return "network_error"
    if status_code == 408:
        return "http_408"
    if status_code == 429:
        return "http_429"
    if status_code >= 500:
        return "http_5xx"
    return f"http_{status_code}"


def result_status_from_exception(exc: Exception) -> dict[str, Any]:
    name = exc.__class__.__name__.lower()
    if "timeout" in name:
        return {"status": "failed_retryable", "error_code": "timeout"}
    return {"status": "failed_retryable", "error_code": "network_error"}
