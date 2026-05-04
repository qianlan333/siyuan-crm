from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable

_DEFAULT_TTL = 60.0


class _TTLCache:
    """Tiny in-process TTL cache.

    Designed for low-cardinality dashboard queries. Keyed by
    ``(qualified_name, args, frozenset(kwargs))``; values evict on read after
    ``ttl`` seconds. Thread-safe via a single lock — fine for the existing
    Flask/gunicorn worker model.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[tuple, tuple[float, Any]] = {}

    def get(self, key: tuple) -> tuple[bool, Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._store.pop(key, None)
                return False, None
            return True, value

    def set(self, key: tuple, value: Any, ttl: float) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def invalidate(self, prefix: str | None = None) -> int:
        with self._lock:
            if prefix is None:
                count = len(self._store)
                self._store.clear()
                return count
            removed = [k for k in self._store if k and isinstance(k[0], str) and k[0].startswith(prefix)]
            for k in removed:
                self._store.pop(k, None)
            return len(removed)

    def size(self) -> int:
        with self._lock:
            return len(self._store)


_default_cache = _TTLCache()


def get_default_cache() -> _TTLCache:
    return _default_cache


def _cache_disabled() -> bool:
    """Bypass the cache when running under Flask test mode.

    Tests create fresh app + DB fixtures per case in the same process, so a
    process-wide TTL cache would otherwise leak counts/state across tests.
    Production paths (``app.testing`` is False) are unaffected.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context() and bool(current_app.config.get("TESTING")):
            return True
    except Exception:
        pass
    return False


def cached(ttl: float = _DEFAULT_TTL, key_prefix: str | None = None) -> Callable:
    """Memoize a function's return value for ``ttl`` seconds.

    The cache key includes the function's qualified name (or ``key_prefix``
    if provided), positional args, and a frozenset of keyword args. Args must
    be hashable; pass IDs not ORM rows.
    """

    def decorator(fn: Callable) -> Callable:
        prefix = key_prefix or f"{fn.__module__}.{fn.__qualname__}"

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _cache_disabled():
                return fn(*args, **kwargs)
            try:
                key = (prefix, args, frozenset(kwargs.items()))
            except TypeError:
                # unhashable arg — skip cache rather than crash
                return fn(*args, **kwargs)
            hit, value = _default_cache.get(key)
            if hit:
                return value
            value = fn(*args, **kwargs)
            _default_cache.set(key, value, ttl)
            return value

        wrapper.invalidate = lambda: _default_cache.invalidate(prefix)  # type: ignore[attr-defined]
        return wrapper

    return decorator


def invalidate_all() -> int:
    return _default_cache.invalidate(None)
