from __future__ import annotations

import inspect

import wecom_ability_service.domains.automation_conversion as automation_package
from wecom_ability_service.db import migrations as db_migrations_module
from wecom_ability_service.domains.automation_conversion import __all__ as automation_public_names
from wecom_ability_service.domains.automation_conversion import service as automation_service
from wecom_ability_service.domains.questionnaire import service as questionnaire_service
from wecom_ability_service.http import background_jobs, customer_automation


def test_automation_conversion_service_public_reexports_stable():
    required_names = {
        "ensure_sop_v1_defaults",
        "generate_default_channel_qr",
        "get_member_detail",
        "get_model_infra_payload",
        "get_overview_payload",
        "get_settings_payload",
        "get_stage_detail_payload",
        "handle_qrcode_enter_from_callback",
        "push_openclaw",
        "run_due_focus_send_batches",
        "run_due_reply_monitor",
        "run_due_sop",
        "run_message_activity_sync",
        "run_reply_monitor_capture",
        "save_model_infra_prompt",
        "save_model_infra_settings",
        "save_reply_monitor_enabled",
        "save_settings",
        "send_stage_manual_message",
        "sync_member_activation",
        "sync_member_from_questionnaire_submission",
        "test_model_infra_connection",
    }
    assert required_names.issubset(set(automation_public_names))
    for name in required_names:
        assert hasattr(automation_service, name)
        assert getattr(automation_package, name) is getattr(automation_service, name)


def test_automation_conversion_service_monkeypatch_seams_stable():
    for name in (
        "_iso_now",
        "_build_live_context",
        "dispatch_wecom_task",
        "push_openclaw",
        "query_message_activity_counts",
        "send_outbound_webhook",
    ):
        assert hasattr(automation_service, name)


def test_init_db_bootstrap_keeps_sop_and_prompt_seed_paths(monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(automation_service, "ensure_sop_v1_defaults", lambda: called.append("sop"))
    monkeypatch.setattr(automation_service, "ensure_agent_prompt_defaults", lambda: called.append("prompt"))
    db_migrations_module._ensure_automation_sop_v1_seed_data()
    db_migrations_module._ensure_automation_agent_prompt_defaults()
    assert called == ["sop", "prompt"]


def test_http_entrypoints_keep_binding_to_automation_conversion_service_symbols():
    assert customer_automation.sync_member_activation is automation_service.sync_member_activation
    assert background_jobs.handle_qrcode_enter_from_callback is automation_service.handle_qrcode_enter_from_callback


def test_questionnaire_service_lazy_import_path_keeps_sync_member_entrypoint():
    source = inspect.getsource(questionnaire_service.submit_questionnaire)
    assert "from ..automation_conversion.service import sync_member_from_questionnaire_submission" in source
