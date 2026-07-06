from __future__ import annotations

import logging
import os
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from aicrm_next.shared.db_session import get_engine

LOGGER = logging.getLogger(__name__)


def runtime_setting(key: str, default: str = "") -> str:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        return default
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT value FROM app_settings WHERE key = :key"),
                {"key": normalized_key},
            ).mappings().first()
    except (SQLAlchemyError, RuntimeError):
        LOGGER.debug("runtime app_settings read unavailable", exc_info=True)
        row = None
    if row is not None:
        return str(row.get("value") or "").strip()
    return str(os.getenv(normalized_key, default) or "").strip()


def runtime_bool(key: str, default: bool = False) -> bool:
    fallback = "true" if default else ""
    return runtime_setting(key, fallback).lower() in {"1", "true", "yes", "y", "on"}


def runtime_csv(key: str) -> set[str]:
    raw = runtime_setting(key, "")
    return {item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()}
