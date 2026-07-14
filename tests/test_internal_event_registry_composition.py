from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.internal_event_composition import build_internal_event_consumer_registry
from aicrm_next.main import create_app
from aicrm_next.platform_foundation.internal_events import (
    DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY,
    InternalEventConsumerRegistry,
    InternalEventService,
    current_internal_event_consumer_registry,
    internal_event_consumer_registry_scope,
)


def _consumer_names(registry: InternalEventConsumerRegistry, event_type: str) -> set[str]:
    return {consumer.consumer_name for consumer in registry.list_for_event_type(event_type)}


def _unused_handler(event, run):  # pragma: no cover - registration probe only
    raise AssertionError("registry isolation probe must not execute")


def test_composition_builds_complete_isolated_registries() -> None:
    first = build_internal_event_consumer_registry()
    second = build_internal_event_consumer_registry()

    assert first is not second
    assert _consumer_names(first, "payment.succeeded") == _consumer_names(second, "payment.succeeded")
    assert "service_period_entitlement_consumer" in _consumer_names(first, "payment.succeeded")

    first.register("registry.probe", "first_only", _unused_handler)

    assert _consumer_names(first, "registry.probe") == {"first_only"}
    assert _consumer_names(second, "registry.probe") == set()


def test_create_app_owns_registry_without_mutating_process_default() -> None:
    before = DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY.to_dict()

    first_app = create_app()
    second_app = create_app()

    assert first_app.state.internal_event_consumer_registry is not second_app.state.internal_event_consumer_registry
    assert DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY.to_dict() == before


def test_registry_scope_binds_default_services_and_restores_cli_fallback() -> None:
    registry = build_internal_event_consumer_registry()

    assert current_internal_event_consumer_registry() is DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
    with internal_event_consumer_registry_scope(registry):
        assert current_internal_event_consumer_registry() is registry
        assert InternalEventService()._registry is registry
    assert current_internal_event_consumer_registry() is DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY


def test_web_request_uses_only_its_own_app_registry() -> None:
    first_app = create_app()
    second_app = create_app()
    first_app.state.internal_event_consumer_registry.register("registry.probe", "first_only", _unused_handler)

    first_payload = TestClient(first_app).get("/api/admin/internal-events/diagnostics").json()
    second_payload = TestClient(second_app).get("/api/admin/internal-events/diagnostics").json()

    assert first_payload["registered_consumers"]["registry.probe"][0]["consumer_name"] == "first_only"
    assert "registry.probe" not in second_payload["registered_consumers"]
