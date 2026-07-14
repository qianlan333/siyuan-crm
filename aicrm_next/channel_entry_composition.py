from __future__ import annotations

from functools import partial

from .channel_entry.application import process_wecom_external_contact_event
from .channel_entry.inbox import WeComCallbackInboxWorker
from .platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry


def build_wecom_callback_inbox_worker_factory(
    *,
    external_effect_adapter_registry: ExternalEffectAdapterRegistry,
):
    processor = partial(
        process_wecom_external_contact_event,
        external_effect_adapter_registry=external_effect_adapter_registry,
    )
    return partial(WeComCallbackInboxWorker, processor=processor)


__all__ = ["build_wecom_callback_inbox_worker_factory"]
