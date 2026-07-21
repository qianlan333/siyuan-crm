from __future__ import annotations

from functools import partial

from .commerce.external_push_admin import plan_order_paid_external_push_effect
from .commerce.repo import execute_commerce_transaction
from .commerce.payment_tagging import (
    product_paid_wecom_tag_consumer,
    resolve_payment_tag_identity,
)
from .identity_contact.payment_projection import project_payment_order_mobile
from .ai_audience_ops import register_ai_audience_event_consumers
from .ai_audience_ops.repository import build_audience_repository
from .cloud_orchestrator.repository import build_cloud_plan_repository
from .questionnaire.event_consumers import (
    automation_questionnaire_consumer,
    customer_summary_consumer,
    questionnaire_projection_consumer,
    questionnaire_tag_consumer,
    questionnaire_webhook_consumer,
)
from .questionnaire.continuation import (
    configure_questionnaire_continuation_audience_repository,
    questionnaire_identity_continuation_consumer,
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


def _project_payment_order_identity_from_db(*, order: dict, source_route: str) -> dict:
    if not production_data_ready():
        return {"ok": True, "projected": False, "reason": "production_database_required"}

    return execute_commerce_transaction(
        lambda conn: project_payment_order_mobile(conn, order, source_route=source_route)
    )


def _resolve_payment_tag_identity_from_db(order: dict, owner_userid: str) -> dict:
    if not production_data_ready():
        return {"ok": False, "reason": "production_database_required"}
    return execute_commerce_transaction(
        lambda conn: resolve_payment_tag_identity(conn, order, owner_userid)
    )
from .platform_foundation.internal_events import (
    InternalEventConsumerRegistry,
    current_internal_event_consumer_registry,
    register_payment_succeeded_consumers as _register_payment_succeeded_consumers,
    register_questionnaire_event_consumers as _register_questionnaire_event_consumers,
    register_customer_wecom_identity_ready_consumer as _register_customer_wecom_identity_ready_consumer,
    register_refund_succeeded_consumers as _register_refund_succeeded_consumers,
    register_shadow_event_consumers as _register_shadow_event_consumers,
)


def register_payment_succeeded_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or current_internal_event_consumer_registry()
    _register_payment_succeeded_consumers(
        registry,
        payment_identity_projector=_project_payment_order_identity_from_db,
        service_period_consumer=service_period_entitlement_consumer,
        product_paid_tag_consumer=partial(
            product_paid_wecom_tag_consumer,
            identity_resolver=_resolve_payment_tag_identity_from_db,
        ),
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


def register_questionnaire_identity_continuation_consumer(
    registry: InternalEventConsumerRegistry | None = None,
) -> None:
    registry = registry or current_internal_event_consumer_registry()
    _register_customer_wecom_identity_ready_consumer(
        questionnaire_identity_continuation_consumer,
        registry,
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
    configure_questionnaire_continuation_audience_repository(build_audience_repository)
    registry = InternalEventConsumerRegistry()
    register_payment_succeeded_consumers(registry)
    register_refund_succeeded_consumers(registry)
    register_questionnaire_event_consumers(registry)
    register_questionnaire_identity_continuation_consumer(registry)
    register_shadow_event_consumers(registry)
    register_ai_audience_event_consumers(registry)
    registry.seal_fanout_contract()
    return registry


__all__ = [
    "build_internal_event_consumer_registry",
    "register_payment_succeeded_consumers",
    "register_questionnaire_event_consumers",
    "register_questionnaire_identity_continuation_consumer",
    "register_refund_succeeded_consumers",
    "register_shadow_event_consumers",
]
