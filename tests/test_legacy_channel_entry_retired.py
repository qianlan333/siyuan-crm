from __future__ import annotations

import importlib

import pytest

from aicrm_next.main import create_app
from aicrm_next.shared.runtime import runtime_route_map_state


RETIREMENT_MESSAGE = "Legacy channel entry is retired. Use aicrm_next.channel_entry."


def test_legacy_callback_routes_are_not_registered_in_flask_blueprint(app):
    legacy_routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/wecom/external-contact/callback" not in legacy_routes
    assert "/api/wecom/events" not in legacy_routes


def test_legacy_channel_diagnosis_routes_are_not_registered_in_flask_blueprint(app):
    legacy_routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/api/admin/channels/runtime-diagnosis" not in legacy_routes
    assert "/api/admin/channels/<int:channel_id>/runtime-diagnosis" not in legacy_routes
    assert "/api/admin/channels/runtime-diagnosis/dry-run" not in legacy_routes
    assert "/api/admin/channels/repair-entry" not in legacy_routes


def test_legacy_channel_entry_orchestrator_module_is_deleted():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("wecom_ability_service.domains.automation_conversion.channel_entry_orchestrator")


def test_legacy_channel_entry_service_entrypoints_raise():
    from wecom_ability_service.domains.automation_conversion import member_state_service
    from wecom_ability_service.http import background_jobs

    with pytest.raises(RuntimeError, match=RETIREMENT_MESSAGE):
        member_state_service.handle_channel_enter_from_callback(external_contact_id="wm", payload_json={"State": "s1"})
    with pytest.raises(RuntimeError, match=RETIREMENT_MESSAGE):
        member_state_service.handle_qrcode_enter_from_callback(external_contact_id="wm", payload_json={"State": "s1"})
    with pytest.raises(RuntimeError, match=RETIREMENT_MESSAGE):
        background_jobs.handle_qrcode_enter_from_callback(external_contact_id="wm", payload_json={"State": "s1"})


def test_production_compat_cannot_forward_wecom_callback_to_legacy(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://route:route@127.0.0.1:1/aicrm_route")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_ALLOW_LEGACY_WECOM_CALLBACK_FALLBACK", "1")
    app = create_app()
    paths = {
        route.path: route.endpoint.__module__
        for route in app.routes
        if getattr(route, "path", "") in {"/wecom/external-contact/callback", "/api/wecom/events"}
    }

    assert paths["/wecom/external-contact/callback"] == "aicrm_next.channel_entry.api"
    assert paths["/api/wecom/events"] == "aicrm_next.channel_entry.api"
    assert runtime_route_map_state()["legacy_callback_fallback_enabled"] is False


def test_wecom_callback_legacy_facade_no_longer_exports_runtime_handler():
    from aicrm_next.integration_gateway import wecom_callback_facade

    assert not hasattr(wecom_callback_facade, "handle_wecom_callback_via_legacy")
