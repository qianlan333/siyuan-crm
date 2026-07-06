from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from aicrm_next.shared.runtime_settings import runtime_bool, runtime_csv, runtime_setting

from .adapters import ExternalEffectAdapterRegistry
from .execution_gates import explicit_wecom_execution_disabled, is_wecom_effect_type
from .models import WECOM_CONTACT_TAG_MARK, WECOM_PROFILE_UPDATE, WECOM_WELCOME_MESSAGE_SEND
from .repo import ExternalEffectRepository
from .worker import ExternalEffectWorker

LOGGER = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="external-effect-realtime")
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_COUNT = 0
REALTIME_ENABLED_KEY = "AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED"
REALTIME_ALLOWED_TYPES_KEY = "AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES"
REALTIME_MAX_CONCURRENCY_KEY = "AICRM_EXTERNAL_EFFECT_REALTIME_MAX_CONCURRENCY"
WELCOME_MESSAGE_CAPABILITY_ENABLED_KEY = "AICRM_PUSH_CAPABILITY_WELCOME_MESSAGE_ENABLED"
CHANNEL_ENTRY_REALTIME_EFFECT_TYPES = (
    WECOM_WELCOME_MESSAGE_SEND,
    WECOM_CONTACT_TAG_MARK,
    WECOM_PROFILE_UPDATE,
)
_MISSING_SETTING = "__aicrm_runtime_setting_missing__"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _max_concurrency() -> int:
    try:
        value = int(runtime_setting(REALTIME_MAX_CONCURRENCY_KEY, "2") or "2")
    except Exception:
        value = 2
    return max(1, min(value, 16))


def _execution_gate_enabled_for_type(effect_type: str) -> bool:
    if is_wecom_effect_type(effect_type) and explicit_wecom_execution_disabled():
        return False
    allowed_types = runtime_csv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
    if effect_type not in allowed_types:
        return False
    if effect_type.startswith("wecom."):
        return runtime_bool("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE")
    if effect_type.startswith("webhook."):
        return runtime_bool("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE")
    return True


def _setting_is_defined(key: str) -> bool:
    return runtime_setting(key, _MISSING_SETTING) != _MISSING_SETTING


def _welcome_message_capability_enabled() -> bool:
    return runtime_bool(WELCOME_MESSAGE_CAPABILITY_ENABLED_KEY)


def _effective_realtime_enabled() -> tuple[bool, str]:
    if _setting_is_defined(REALTIME_ENABLED_KEY):
        return runtime_bool(REALTIME_ENABLED_KEY), "explicit"
    if _welcome_message_capability_enabled():
        return True, "welcome_message_capability"
    return False, "default"


def _effective_realtime_allowed_types() -> tuple[set[str], str]:
    if _setting_is_defined(REALTIME_ALLOWED_TYPES_KEY):
        return runtime_csv(REALTIME_ALLOWED_TYPES_KEY), "explicit"
    if not _welcome_message_capability_enabled():
        return set(), "default"
    return (
        {
            effect_type
            for effect_type in CHANNEL_ENTRY_REALTIME_EFFECT_TYPES
            if _execution_gate_enabled_for_type(effect_type)
        },
        "welcome_message_capability",
    )


def realtime_wakeup_allowed(effect_type: str) -> bool:
    normalized = _text(effect_type)
    if not normalized:
        return False
    enabled, _enabled_source = _effective_realtime_enabled()
    if not enabled:
        return False
    allowed_types, _allowed_types_source = _effective_realtime_allowed_types()
    if normalized not in allowed_types:
        return False
    return _execution_gate_enabled_for_type(normalized)


def realtime_wakeup_state() -> dict[str, Any]:
    enabled, enabled_source = _effective_realtime_enabled()
    allowed_type_set, allowed_types_source = _effective_realtime_allowed_types()
    allowed_types = sorted(allowed_type_set)
    channel_entry_required = list(CHANNEL_ENTRY_REALTIME_EFFECT_TYPES)
    missing_channel_entry_types = [effect_type for effect_type in channel_entry_required if effect_type not in allowed_types]
    return {
        "enabled": enabled,
        "status": "enabled" if enabled else "disabled",
        "enabled_source": enabled_source,
        "allowed_types": allowed_types,
        "allowed_types_source": allowed_types_source,
        "derived_from_welcome_message_capability": enabled_source == "welcome_message_capability" or allowed_types_source == "welcome_message_capability",
        "max_concurrency": _max_concurrency(),
        "channel_entry_required_types": channel_entry_required,
        "channel_entry_missing_types": missing_channel_entry_types,
        "channel_entry_ready": enabled and not missing_channel_entry_types,
        "description": "渠道码欢迎语必须命中 realtime，否则 welcome_code 可能超过 20 秒窗口。",
    }


def _try_acquire_slot() -> bool:
    global _ACTIVE_COUNT
    with _ACTIVE_LOCK:
        if _ACTIVE_COUNT >= _max_concurrency():
            return False
        _ACTIVE_COUNT += 1
        return True


def _release_slot() -> None:
    global _ACTIVE_COUNT
    with _ACTIVE_LOCK:
        _ACTIVE_COUNT = max(0, _ACTIVE_COUNT - 1)


def dispatch_external_effect_job_realtime(
    job_id: int,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None = None,
    adapter_registry: ExternalEffectAdapterRegistry | None = None,
) -> dict[str, Any]:
    try:
        return ExternalEffectWorker(
            repository,
            adapter_registry,
            locked_by=f"external-effect-realtime:{_text(reason) or 'unspecified'}",
        ).dispatch_one(int(job_id))
    except Exception as exc:
        LOGGER.exception(
            "external effect realtime dispatch failed",
            extra={"external_effect_job_id": int(job_id or 0), "effect_type": _text(effect_type), "reason": _text(reason)},
        )
        return {
            "ok": False,
            "error": "external_effect_realtime_dispatch_failed",
            "error_message": str(exc),
            "real_external_call_executed": False,
        }


def _dispatch_and_release(
    job_id: int,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None,
    adapter_registry: ExternalEffectAdapterRegistry | None,
) -> None:
    try:
        dispatch_external_effect_job_realtime(
            job_id,
            reason=reason,
            effect_type=effect_type,
            repository=repository,
            adapter_registry=adapter_registry,
        )
    finally:
        _release_slot()


def wake_external_effect_job(
    job_id: Any,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None = None,
    adapter_registry: ExternalEffectAdapterRegistry | None = None,
    run_inline: bool = False,
) -> bool:
    try:
        normalized_job_id = int(job_id or 0)
    except (TypeError, ValueError):
        normalized_job_id = 0
    normalized_effect_type = _text(effect_type)
    if normalized_job_id <= 0 or not realtime_wakeup_allowed(normalized_effect_type):
        return False
    if not _try_acquire_slot():
        LOGGER.warning(
            "external effect realtime wakeup skipped because concurrency limit is reached",
            extra={"external_effect_job_id": normalized_job_id, "effect_type": normalized_effect_type, "reason": _text(reason)},
        )
        return False
    if run_inline:
        _dispatch_and_release(
            normalized_job_id,
            reason=reason,
            effect_type=normalized_effect_type,
            repository=repository,
            adapter_registry=adapter_registry,
        )
        return True
    try:
        _EXECUTOR.submit(
            _dispatch_and_release,
            normalized_job_id,
            reason=reason,
            effect_type=normalized_effect_type,
            repository=repository,
            adapter_registry=adapter_registry,
        )
    except Exception:
        _release_slot()
        LOGGER.exception(
            "external effect realtime wakeup scheduling failed",
            extra={"external_effect_job_id": normalized_job_id, "effect_type": normalized_effect_type, "reason": _text(reason)},
        )
        return False
    return True
