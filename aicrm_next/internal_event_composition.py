from __future__ import annotations

from functools import partial

from .commerce.external_push_admin import plan_order_paid_external_push_effect
from .commerce.repo import execute_commerce_transaction
from .ai_audience_ops import register_ai_audience_event_consumers
from .cloud_orchestrator.repository import build_cloud_plan_repository
from .questionnaire.event_consumers import (
    automation_questionnaire_consumer,
    customer_summary_consumer,
    questionnaire_projection_consumer,
    questionnaire_tag_consumer,
    questionnaire_webhook_consumer,
)
from .service_period.payment_consumer import service_period_entitlement_consumer
from .service_period.refund_consumer import service_period_refund_consumer
from .platform_foundation.internal_events.shadow import broadcast_task_planner_consumer
from .platform_foundation.internal_events.payment import webhook_order_paid_consumer
from .shared.runtime import production_data_ready


def _plan_order_paid_external_push_effect_from_db(
    *,
    order: dict,
    transaction: dict,
    domain_event_outbox_id: object,
) -> dict | None:
    if not production_data_ready():
        raise RuntimeError("production database is required for order-paid external push planning")
    def _plan(conn):
        return plan_order_paid_external_push_effect(
            conn,
            order=order,
            transaction=transaction,
            outbox={"id": domain_event_outbox_id},
            source_module="platform_foundation.internal_events.payment",
            source_route="/internal-events/payment.succeeded/webhook_order_paid_consumer",
        )
    return execute_commerce_transaction(_plan)
from .platform_foundation.internal_events import (
    InternalEventConsumerRegistry,
    current_internal_event_consumer_registry,
    register_payment_succeeded_consumers as _register_payment_succeeded_consumers,
    register_questionnaire_event_consumers as _register_questionnaire_event_consumers,
    register_refund_succeeded_consumers as _register_refund_succeeded_consumers,
    register_shadow_event_consumers as _register_shadow_event_consumers,
)


def register_payment_succeeded_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or current_internal_event_consumer_registry()
    _register_payment_succeeded_consumers(
        registry,
        service_period_consumer=service_period_entitlement_consumer,
        webhook_order_paid_handler=partial(
            webhook_order_paid_consumer,
            external_push_planner=_plan_order_paid_external_push_effect_from_db,
        ),
    )


def register_refund_succeeded_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or current_internal_event_consumer_registry()
    _register_refund_succeeded_consumers(
        registry,
        service_period_consumer=service_period_refund_consumer,
    )


def register_questionnaire_event_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or current_internal_event_consumer_registry()
    _register_questionnaire_event_consumers(
        registry,
        handlers={
            "questionnaire_projection_consumer": questionnaire_projection_consumer,
            "questionnaire_webhook_consumer": questionnaire_webhook_consumer,
            "questionnaire_tag_consumer": questionnaire_tag_consumer,
            "automation_questionnaire_consumer": automation_questionnaire_consumer,
            "customer_summary_consumer": customer_summary_consumer,
        },
    )


def register_shadow_event_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or current_internal_event_consumer_registry()
    _register_shadow_event_consumers(
        registry,
        broadcast_task_planner_handler=partial(
            broadcast_task_planner_consumer,
            repository_factory=build_cloud_plan_repository,
        ),
    )


def build_internal_event_consumer_registry() -> InternalEventConsumerRegistry:
    registry = InternalEventConsumerRegistry()
    register_payment_succeeded_consumers(registry)
    register_refund_succeeded_consumers(registry)
    register_questionnaire_event_consumers(registry)
    register_shadow_event_consumers(registry)
    register_ai_audience_event_consumers(registry)
    return registry


__all__ = [
    "build_internal_event_consumer_registry",
    "register_payment_succeeded_consumers",
    "register_questionnaire_event_consumers",
    "register_refund_succeeded_consumers",
    "register_shadow_event_consumers",
]
