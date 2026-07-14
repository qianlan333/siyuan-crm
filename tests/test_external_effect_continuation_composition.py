from __future__ import annotations

from aicrm_next.external_effect_composition import (
    build_external_effect_adapter_registry,
    build_external_effect_continuation_registry,
)
from aicrm_next.main import create_app


def test_external_effect_continuation_composition_is_explicit_and_deterministic() -> None:
    first = build_external_effect_continuation_registry()
    second = build_external_effect_continuation_registry()

    assert first is not second
    assert first.names == (
        "questionnaire_contact_tags",
        "external_push_delivery",
        "automation_agent_audience_webhook",
    )
    assert second.names == first.names


def test_web_app_owns_its_external_effect_continuation_registry() -> None:
    first_app = create_app()
    second_app = create_app()

    assert first_app.state.external_effect_continuation_registry.names == (
        "questionnaire_contact_tags",
        "external_push_delivery",
        "automation_agent_audience_webhook",
    )
    assert first_app.state.external_effect_continuation_registry is not second_app.state.external_effect_continuation_registry


def test_web_apps_do_not_share_external_effect_adapter_instances() -> None:
    first = build_external_effect_adapter_registry()
    second = build_external_effect_adapter_registry()
    first_app = create_app()
    second_app = create_app()

    assert first is not second
    assert first._adapters.keys() == second._adapters.keys()  # type: ignore[attr-defined]
    assert all(
        first._adapters[name] is not second._adapters[name]  # type: ignore[attr-defined]
        for name in first._adapters  # type: ignore[attr-defined]
    )
    assert first_app.state.external_effect_adapter_registry is not second_app.state.external_effect_adapter_registry


def test_callback_workers_use_their_own_app_effect_registry() -> None:
    first_app = create_app()
    second_app = create_app()
    first_worker = first_app.state.wecom_callback_inbox_worker_factory()
    second_worker = second_app.state.wecom_callback_inbox_worker_factory()

    assert first_worker is not second_worker
    assert (
        first_worker._processor.keywords["external_effect_adapter_registry"]  # type: ignore[attr-defined]
        is first_app.state.external_effect_adapter_registry
    )
    assert (
        second_worker._processor.keywords["external_effect_adapter_registry"]  # type: ignore[attr-defined]
        is second_app.state.external_effect_adapter_registry
    )
