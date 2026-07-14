from __future__ import annotations

import logging
from typing import Any

from aicrm_next.shared.wecom_runtime import load_wecom_execution_config
from aicrm_next.shared.runtime_settings import runtime_bool, runtime_csv, runtime_setting
from aicrm_next.shared.safe_logging import safe_log_exception

from .adapters import ExternalEffectAdapterRegistry
from .execution_gates import is_wecom_effect_type, typed_wecom_execution_block_reason
from .models import WECOM_CONTACT_TAG_MARK, WECOM_PROFILE_UPDATE, WECOM_WELCOME_MESSAGE_SEND
from .repo import ExternalEffectRepository
from .worker import ExternalEffectWorker

LOGGER = logging.getLogger(__name__)
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


def _execution_gate_enabled_for_type(effect_type: str) -> bool:
    if is_wecom_effect_type(effect_type):
        return not typed_wecom_execution_block_reason(effect_type)
    if effect_type.startswith("webhook."):
        return runtime_bool("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE")
    return True


def _setting_is_defined(key: str) -> bool:
    return runtime_setting(key, _MISSING_SETTING) != _MISSING_SETTING


def _welcome_message_capability_enabled() -> bool:
    return runtime_bool(WELCOME_MESSAGE_CAPABILITY_ENABLED_KEY)


def _effective_realtime_enabled() -> tuple[bool, str]:
    if _setting_is_defined(REALTIME_ENABLED_KEY):
        return runtime_bool(REALTIME_ENABLED_KEY) and load_wecom_execution_config().execution_mode == "execute", "legacy_realtime_flag"
    config = load_wecom_execution_config()
    return config.execution_mode == "execute" and not config.conflict, "wecom_execution_config"


def _effective_realtime_allowed_types() -> tuple[set[str], str]:
    config = load_wecom_execution_config()
    if config.execution_mode != "execute" or config.conflict:
        return set(), "wecom_execution_config"
    configured = set(config.enabled_effect_types)
    if _setting_is_defined(REALTIME_ALLOWED_TYPES_KEY):
        return configured.intersection(runtime_csv(REALTIME_ALLOWED_TYPES_KEY)), "legacy_realtime_allowlist"
    return configured.intersection(CHANNEL_ENTRY_REALTIME_EFFECT_TYPES), "wecom_execution_config"


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
        "max_concurrency": 1,
        "channel_entry_required_types": channel_entry_required,
        "channel_entry_missing_types": missing_channel_entry_types,
        "channel_entry_ready": enabled and not missing_channel_entry_types,
        "dispatch_boundary": "shared_external_effect_lease_claim",
        "uses_process_local_executor": False,
        "deprecated_settings": [REALTIME_ENABLED_KEY, REALTIME_ALLOWED_TYPES_KEY, REALTIME_MAX_CONCURRENCY_KEY],
        "deprecated_settings_owner": "integration_gateway",
        "deprecated_settings_delete_after": "2026-10-01",
        "description": "渠道码 worker 与定时 worker 通过同一持久化 lease/CAS claim 执行 Effect job。",
    }


def dispatch_external_effect_job_now(
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
            locked_by=f"external-effect-callback-worker:{_text(reason) or 'unspecified'}",
        ).dispatch_one(int(job_id))
    except Exception as exc:
        safe_log_exception(
            LOGGER,
            "external effect immediate dispatch failed",
            exc,
            external_effect_job_id=int(job_id or 0),
            effect_type=_text(effect_type),
            reason=_text(reason),
        )
        return {
            "ok": False,
            "error": "external_effect_immediate_dispatch_failed",
            "error_message": str(exc),
            "real_external_call_executed": False,
        }


def wake_external_effect_job(
    job_id: Any,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None = None,
    adapter_registry: ExternalEffectAdapterRegistry | None = None,
    run_inline: bool = True,
) -> bool:
    try:
        normalized_job_id = int(job_id or 0)
    except (TypeError, ValueError):
        normalized_job_id = 0
    normalized_effect_type = _text(effect_type)
    if normalized_job_id <= 0 or not realtime_wakeup_allowed(normalized_effect_type):
        return False
    if not run_inline:
        LOGGER.warning(
            "non-inline external effect wakeup is retired; dispatching in the durable caller",
            extra={"external_effect_job_id": normalized_job_id, "effect_type": normalized_effect_type, "reason": _text(reason)},
        )
    dispatch_external_effect_job_now(
        normalized_job_id,
        reason=reason,
        effect_type=normalized_effect_type,
        repository=repository,
        adapter_registry=adapter_registry,
    )
    return True


dispatch_external_effect_job_realtime = dispatch_external_effect_job_now
