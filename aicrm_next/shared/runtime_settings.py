from __future__ import annotations

import logging
import os
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.secret_store import (
    SECRET_REFERENCE_CUTOVER_KEY,
    SENSITIVE_SETTING_KEYS,
    FileSecretStore,
    SecretStoreError,
    parse_secret_reference,
)
from aicrm_next.shared.safe_logging import safe_log_exception

LOGGER = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _cutover_enabled(conn=None) -> bool:
    if str(os.getenv(SECRET_REFERENCE_CUTOVER_KEY, "") or "").strip().lower() in _TRUE_VALUES:
        return True
    if conn is None:
        return False
    try:
        row = conn.execute(
            text("SELECT value FROM app_settings WHERE key = :key"),
            {"key": SECRET_REFERENCE_CUTOVER_KEY},
        ).mappings().first()
    except SQLAlchemyError:
        return False
    return str((row or {}).get("value") or "").strip().lower() in _TRUE_VALUES


def _resolve_candidate(key: str, candidate: str, *, default: str, cutover_enabled: bool) -> str:
    normalized = str(candidate or "").strip()
    if normalized.startswith("secretref:"):
        try:
            reference = parse_secret_reference(normalized)
            if reference.key != key:
                raise SecretStoreError("secret reference does not match requested key")
            return FileSecretStore.from_environment().read(normalized).strip()
        except SecretStoreError:
            LOGGER.warning("runtime secret reference resolution failed for key=%s", key)
            return default
    if key in SENSITIVE_SETTING_KEYS and cutover_enabled and normalized:
        LOGGER.warning("runtime raw sensitive setting rejected after cutover for key=%s", key)
        return default
    return normalized


def runtime_setting(key: str, default: str = "") -> str:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return default
    fallback = str(default or "").strip()
    cutover_enabled = str(os.getenv(SECRET_REFERENCE_CUTOVER_KEY, "") or "").strip().lower() in _TRUE_VALUES
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT value FROM app_settings WHERE key = :key"),
                {"key": normalized_key},
            ).mappings().first()
            stored_value = str((row or {}).get("value") or "").strip()
            if normalized_key in SENSITIVE_SETTING_KEYS and not stored_value.startswith("secretref:"):
                cutover_enabled = _cutover_enabled(conn)
    except (AttributeError, SQLAlchemyError, RuntimeError) as exc:
        safe_log_exception(LOGGER, "runtime app_settings read unavailable", exc, level=logging.DEBUG)
        row = None
    if row is not None:
        return _resolve_candidate(
            normalized_key,
            str(row.get("value") or ""),
            default=fallback,
            cutover_enabled=cutover_enabled,
        )
    return _resolve_candidate(
        normalized_key,
        str(os.getenv(normalized_key, fallback) or ""),
        default=fallback,
        cutover_enabled=cutover_enabled,
    )


def runtime_bool(key: str, default: bool = False) -> bool:
    fallback = "true" if default else ""
    return runtime_setting(key, fallback).lower() in _TRUE_VALUES


def runtime_csv(key: str) -> set[str]:
    raw = runtime_setting(key, "")
    return {item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()}
