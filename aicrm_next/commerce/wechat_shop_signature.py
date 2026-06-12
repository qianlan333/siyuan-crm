from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from aicrm_next.shared.runtime import production_environment

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    return str(value or "").strip()


def verify_signature(token: str, timestamp: str, nonce: str, signature: str) -> bool:
    parts = [_text(token), _text(timestamp), _text(nonce)]
    if not all(parts) or not _text(signature):
        return False
    digest = hashlib.sha1("".join(sorted(parts)).encode("utf-8")).hexdigest()
    return digest == _text(signature).lower()


def callback_token() -> str:
    return _text(os.getenv("WECHAT_SHOP_CALLBACK_TOKEN"))


def should_skip_signature_without_token() -> bool:
    if _text(os.getenv("AICRM_NEXT_ENV")).lower() == "test" or not production_environment():
        return True
    logger.warning("WECHAT_SHOP_CALLBACK_TOKEN is not configured; skipping WeChat Shop callback signature verification")
    return True
