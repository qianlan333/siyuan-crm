from __future__ import annotations

import threading
import time


class CircuitBreaker:
    """Minimal circuit breaker: closed → open → half-open → closed.

    Not thread-safe by design for the simple Flask/gunicorn model,
    but uses a lock for atomic state transitions in threaded workers.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._lock = threading.Lock()
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open" and time.time() - self._last_failure_time >= self._recovery_timeout:
                self._state = "half_open"
                self._half_open_calls = 0
            return self._state

    def allow_request(self) -> bool:
        state = self.state
        if state == "closed":
            return True
        if state == "half_open":
            with self._lock:
                if self._half_open_calls < self._half_open_max_calls:
                    self._half_open_calls += 1
                    return True
            return False
        return False

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
