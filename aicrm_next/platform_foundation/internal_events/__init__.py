from __future__ import annotations

from .consumer_registry import DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY, InternalEventConsumerRegistry
from .models import (
    InternalEvent,
    InternalEventConsumerAttempt,
    InternalEventConsumerResult,
    InternalEventConsumerRun,
)
from .repository import InMemoryInternalEventRepository, reset_internal_event_fixture_state
from .service import InternalEventService
from .legacy_path_markers import (
    legacy_path_marker_diagnostics,
    mark_legacy_path_invoked,
    reset_legacy_path_marker_state,
)
from .customer_identity import CUSTOMER_PHONE_BOUND_EVENT_TYPE, register_customer_identity_event_consumers
from .payment import PAYMENT_SUCCEEDED_EVENT_TYPE, PAYMENT_SUCCEEDED_EVENT_TYPES, register_payment_succeeded_consumers
from .questionnaire import QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, register_questionnaire_event_consumers
from .shadow import register_shadow_event_consumers

__all__ = [
    "DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY",
    "InMemoryInternalEventRepository",
    "InternalEvent",
    "InternalEventConsumerAttempt",
    "InternalEventConsumerRegistry",
    "InternalEventConsumerResult",
    "InternalEventConsumerRun",
    "InternalEventService",
    "legacy_path_marker_diagnostics",
    "mark_legacy_path_invoked",
    "PAYMENT_SUCCEEDED_EVENT_TYPE",
    "PAYMENT_SUCCEEDED_EVENT_TYPES",
    "QUESTIONNAIRE_SUBMITTED_EVENT_TYPE",
    "CUSTOMER_PHONE_BOUND_EVENT_TYPE",
    "register_customer_identity_event_consumers",
    "register_payment_succeeded_consumers",
    "register_questionnaire_event_consumers",
    "register_shadow_event_consumers",
    "reset_legacy_path_marker_state",
    "reset_internal_event_fixture_state",
]
