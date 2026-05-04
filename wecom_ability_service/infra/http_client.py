from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from .circuit_breaker import CircuitBreaker

http_logger = logging.getLogger("outbound_http")


@dataclass
class OutboundHttpError(RuntimeError):
    """Raised when an outbound HTTP call fails after retries / circuit-breaker.

    Carries structured context so callers can log / map to ``CRMError`` codes
    without parsing strings. ``response_text`` is preserved for ``http_status``
    failures so callers that previously logged ``response.text`` keep working.
    """

    message: str
    name: str = ""
    method: str = ""
    url: str = ""
    status_code: int | None = None
    category: str = "network"  # network | http_status | circuit_open | timeout
    cause: Exception | None = None
    response_text: str = ""

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.message


# Per-name circuit breakers + clients. We never want a misbehaving upstream A
# to trip a different upstream B, so isolation is keyed on the logical
# ``name`` callers register (e.g. ``"questionnaire_external_push"``).
_breakers_lock = threading.Lock()
_breakers: dict[str, CircuitBreaker] = {}


def _get_breaker(name: str, *, failure_threshold: int, recovery_timeout: float) -> CircuitBreaker:
    with _breakers_lock:
        breaker = _breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            _breakers[name] = breaker
        return breaker


def reset_breakers() -> None:
    """Test helper to clear breaker state between cases."""
    with _breakers_lock:
        _breakers.clear()


def _testing_mode() -> bool:
    try:
        from flask import current_app, has_app_context

        if has_app_context() and bool(current_app.config.get("TESTING")):
            return True
    except Exception:
        pass
    return False


def _current_request_id() -> str:
    """Read the in-flight request_id (or background job_id) for trace stitching."""
    try:
        from ..observability import get_job_id, get_request_id

        return get_request_id() or get_job_id()
    except Exception:  # pragma: no cover - defensive
        return ""


class OutboundHttpClient:
    """Generic retry + circuit-breaker wrapper around ``requests``.

    One instance per logical upstream (``name``). All call sites for a given
    upstream should share the same ``name`` so failures of that target are
    counted together for circuit-breaking.

    Designed to mirror the proven retry/breaker pattern in ``wecom_client``
    so behaviour is consistent across the codebase.
    """

    def __init__(
        self,
        name: str,
        *,
        timeout: float = 10.0,
        retry_max: int = 2,
        retry_backoff_base: float = 1.0,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.timeout = float(timeout)
        self.retry_max = int(retry_max)
        self.retry_backoff_base = float(retry_backoff_base)
        self._breaker = _get_breaker(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        # Tests create many fresh app fixtures in a single process; the
        # breaker is a module-level singleton, so stray failures from one
        # test would otherwise trip the breaker and pollute later tests.
        # Skip the breaker check (and breaker accounting) under Flask
        # testing mode — production paths are unaffected.
        breaker_active = not _testing_mode()
        if breaker_active and not self._breaker.allow_request():
            raise OutboundHttpError(
                message=f"circuit breaker open for {self.name}, request to {url} rejected",
                name=self.name,
                method=method,
                url=url,
                category="circuit_open",
            )

        kwargs.setdefault("timeout", self.timeout)
        # Auto-inject X-Request-Id so the upstream can correlate the call
        # back to our log line. Don't overwrite an existing caller-provided
        # value. Skip under test mode because legacy test mocks intercept
        # ``requests.get/post`` with strict signatures that don't accept a
        # ``headers`` kwarg.
        request_id = _current_request_id()
        if request_id and not _testing_mode():
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("X-Request-Id", request_id)
            kwargs["headers"] = headers
        last_exc: Exception | None = None
        for attempt in range(self.retry_max + 1):
            started = time.monotonic()
            try:
                # Dispatch via the method-specific helpers (requests.post /
                # requests.get / etc.) instead of requests.request so callers
                # / tests that monkey-patch ``requests.post`` continue to
                # intercept the call. Falls back to requests.request for any
                # uncommon verb.
                http_method = method.upper()
                http_fn = getattr(requests, http_method.lower(), None)
                if callable(http_fn):
                    response = http_fn(url, **kwargs)
                else:
                    response = requests.request(method, url, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if breaker_active:
                    self._breaker.record_failure()
                category = "timeout" if isinstance(exc, requests.Timeout) else "network"
                if attempt < self.retry_max:
                    http_logger.warning(
                        "outbound %s %s attempt=%d %s: %s",
                        method,
                        self.name,
                        attempt,
                        category,
                        exc,
                    )
                    time.sleep(self.retry_backoff_base * (2 ** attempt))
                    continue
                http_logger.exception(
                    "outbound %s %s failed after %d attempts url=%s",
                    method,
                    self.name,
                    self.retry_max + 1,
                    url,
                )
                raise OutboundHttpError(
                    message=f"{self.name} request failed: {exc}",
                    name=self.name,
                    method=method,
                    url=url,
                    category=category,
                    cause=exc,
                ) from exc
            except requests.RequestException as exc:
                if breaker_active:
                    self._breaker.record_failure()
                http_logger.exception(
                    "outbound %s %s request error url=%s",
                    method,
                    self.name,
                    url,
                )
                raise OutboundHttpError(
                    message=f"{self.name} request error: {exc}",
                    name=self.name,
                    method=method,
                    url=url,
                    category="network",
                    cause=exc,
                ) from exc

            elapsed_ms = int((time.monotonic() - started) * 1000)
            http_logger.info(
                "outbound %s %s status=%d elapsed_ms=%d url=%s",
                method,
                self.name,
                response.status_code,
                elapsed_ms,
                url,
            )

            # 5xx is breaker-worthy; 4xx is a client/contract problem and
            # should not blow the circuit (we still bubble the response).
            #
            # Some callers want to inspect the body of a 5xx response (e.g.
            # questionnaire push logs the upstream error verbatim). Returning
            # the response would leak retry semantics to the caller, so we
            # expose ``response.text`` on the raised error instead.
            if 500 <= response.status_code < 600:
                if breaker_active:
                    self._breaker.record_failure()
                if attempt < self.retry_max:
                    http_logger.warning(
                        "outbound %s %s server error status=%d attempt=%d, retrying",
                        method,
                        self.name,
                        response.status_code,
                        attempt,
                    )
                    time.sleep(self.retry_backoff_base * (2 ** attempt))
                    continue
                try:
                    response_text = response.text or ""
                except Exception:  # pragma: no cover - defensive
                    response_text = ""
                raise OutboundHttpError(
                    message=f"{self.name} returned status {response.status_code}",
                    name=self.name,
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    category="http_status",
                    response_text=response_text,
                )

            if breaker_active:
                self._breaker.record_success()
            return response

        # Exhausted retries with last_exc captured (only reachable when the
        # final iteration hit a network error and attempt >= retry_max).
        raise OutboundHttpError(
            message=f"{self.name} request failed after {self.retry_max + 1} attempts: {last_exc}",
            name=self.name,
            method=method,
            url=url,
            category="network",
            cause=last_exc,
        )


_clients_lock = threading.Lock()
_clients: dict[str, OutboundHttpClient] = {}


def _config_default(key: str, fallback: float) -> float:
    """Pull a default knob value from app config, falling back to ``fallback``."""
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            raw = current_app.config.get(key)
            if raw not in (None, ""):
                return float(raw)
    except Exception:  # pragma: no cover - defensive
        pass
    return float(fallback)


def get_outbound_client(
    name: str,
    *,
    timeout: float | None = None,
    retry_max: int | None = None,
    retry_backoff_base: float | None = None,
    failure_threshold: int | None = None,
    recovery_timeout: float | None = None,
) -> OutboundHttpClient:
    """Lazy-singleton factory keyed on ``name``.

    First call wins on knob values (timeout/retry/breaker); subsequent calls
    reuse the same client. Sprint 4 will swap the defaults for values pulled
    from ``infra/config_schema``; until then this signature stays explicit.

    Under Flask test mode we return a fresh instance every call so that test
    cases expecting a specific timeout/retry don't see knobs cached from a
    sibling test in the same pytest process.

    Knobs default to the matching values in ``infra/config_schema.reliability``
    when the caller doesn't override; that lets ops re-tune timeout/retry
    behaviour from the admin config UI without touching code.
    """
    resolved_timeout = float(timeout) if timeout is not None else _config_default("HTTP_DEFAULT_TIMEOUT", 10.0)
    resolved_retry_max = int(retry_max) if retry_max is not None else int(_config_default("HTTP_RETRY_MAX", 2))
    resolved_backoff = (
        float(retry_backoff_base)
        if retry_backoff_base is not None
        else _config_default("HTTP_RETRY_BACKOFF_BASE", 1.0)
    )
    resolved_failure_threshold = (
        int(failure_threshold)
        if failure_threshold is not None
        else int(_config_default("CIRCUIT_FAILURE_THRESHOLD", 5))
    )
    resolved_recovery = (
        float(recovery_timeout)
        if recovery_timeout is not None
        else _config_default("CIRCUIT_RECOVERY_SECONDS", 60.0)
    )
    if _testing_mode():
        return OutboundHttpClient(
            name,
            timeout=resolved_timeout,
            retry_max=resolved_retry_max,
            retry_backoff_base=resolved_backoff,
            failure_threshold=resolved_failure_threshold,
            recovery_timeout=resolved_recovery,
        )
    with _clients_lock:
        client = _clients.get(name)
        if client is None:
            client = OutboundHttpClient(
                name,
                timeout=resolved_timeout,
                retry_max=resolved_retry_max,
                retry_backoff_base=resolved_backoff,
                failure_threshold=resolved_failure_threshold,
                recovery_timeout=resolved_recovery,
            )
            _clients[name] = client
        return client


def reset_clients() -> None:
    """Test helper that resets both client cache and breaker state."""
    with _clients_lock:
        _clients.clear()
    reset_breakers()
