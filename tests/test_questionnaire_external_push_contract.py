from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


def test_questionnaire_external_push_application_contract_is_importable():
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

    from aicrm_next.questionnaire.external_push_logs import (
        ExternalPushDeliveryAdapter,
        QuestionnaireExternalPushLogReadService,
        QuestionnaireExternalPushRetryBatchCommand,
        QuestionnaireExternalPushRetryCommand,
    )
    from wecom_ability_service.application.questionnaire.commands import (
        RetryQuestionnaireExternalPushCommand,
    )
    from wecom_ability_service.application.questionnaire.queries import (
        GetGlobalQuestionnaireExternalPushLogsQuery,
        GetQuestionnaireExternalPushLogsQuery,
    )

    assert GetQuestionnaireExternalPushLogsQuery
    assert GetGlobalQuestionnaireExternalPushLogsQuery
    assert RetryQuestionnaireExternalPushCommand
    assert QuestionnaireExternalPushLogReadService
    assert QuestionnaireExternalPushRetryCommand
    assert QuestionnaireExternalPushRetryBatchCommand
    assert ExternalPushDeliveryAdapter


def test_next_external_push_log_routes_do_not_forward_to_legacy_flask():
    root = Path(__file__).resolve().parents[1]
    native_source = (
        root
        / "aicrm_next"
        / "questionnaire"
        / "admin_pages.py"
    ).read_text(encoding="utf-8")
    legacy_source = (
        root
        / "aicrm_next"
        / "frontend_compat"
        / "legacy_routes.py"
    ).read_text(encoding="utf-8")
    start = native_source.index('"/admin/questionnaires/external-push-logs"')
    route_block = native_source[start:]

    assert "forward_to_legacy_flask" not in route_block
    assert '"/admin/questionnaires/external-push-logs"' in native_source
    assert "QuestionnaireExternalPushLogReadService" in native_source
    assert "QuestionnaireExternalPushRetryService" in native_source
    assert "/admin/questionnaires/external-push-logs" not in legacy_source


def test_next_external_push_log_pages_do_not_use_admin_shell_legacy_endpoint_mapping():
    root = Path(__file__).resolve().parents[1]
    retired_endpoint_markers = [
        "api.admin_console_global_questionnaire_external_push_logs",
        "api.admin_console_questionnaire_external_push_logs",
    ]
    shell_sources = [
        root / "aicrm_next" / "frontend_compat" / "admin_shell.py",
        root / "aicrm_next" / "admin_jobs" / "shell.py",
    ]
    for path in shell_sources:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for marker in retired_endpoint_markers:
            assert marker not in source

    template_source = (
        root
        / "aicrm_next"
        / "questionnaire"
        / "templates"
        / "admin_console"
        / "questionnaire_external_push_logs.html"
    ).read_text(encoding="utf-8")
    for marker in retired_endpoint_markers:
        assert marker not in template_source
    assert "logs_payload.paths.index" in template_source
    assert "logs_payload.paths.retry_batch" in template_source


def test_legacy_flask_external_push_log_routes_are_deleted():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "wecom_ability_service" / "http" / "admin_questionnaire_push_logs.py").exists()
    assert not (
        root
        / "wecom_ability_service"
        / "templates"
        / "admin_console"
        / "questionnaire_external_push_logs.html"
    ).exists()

    http_init = (root / "wecom_ability_service" / "http" / "__init__.py").read_text(encoding="utf-8")
    assert "admin_questionnaire_push_logs" not in http_init

    admin_console_service = (
        root / "wecom_ability_service" / "domains" / "admin_console" / "service.py"
    ).read_text(encoding="utf-8")
    for fragment in [
        "build_questionnaire_external_push_logs_payload",
        "build_global_questionnaire_external_push_logs_payload",
        "retry_questionnaire_external_push_log_for_console",
        "retry_questionnaire_external_push_logs_for_console",
    ]:
        assert fragment not in admin_console_service


def test_external_push_actions_do_not_link_via_retired_flask_endpoint_helpers():
    root = Path(__file__).resolve().parents[1]
    query_source = (root / "wecom_ability_service" / "application" / "questionnaire" / "queries.py").read_text(
        encoding="utf-8"
    )
    next_template_source = (
        root
        / "aicrm_next"
        / "questionnaire"
        / "templates"
        / "admin_console"
        / "questionnaire_external_push_logs.html"
    ).read_text(encoding="utf-8")

    assert 'url_for("api.admin_console_global_questionnaire_external_push_logs' not in query_source
    assert "url_for('api.admin_console_global_questionnaire_external_push_logs" not in query_source
    assert 'url_for("api.admin_console_questionnaire_external_push_logs' not in query_source
    assert "url_for('api.admin_console_questionnaire_external_push_logs" not in query_source
    assert "logs_payload.paths.index" in next_template_source
    assert "logs_payload.paths.retry_batch" in next_template_source


def test_next_admin_detail_projection_preserves_legacy_external_push_fields():
    from aicrm_next.questionnaire.domain import admin_detail_projection

    payload = admin_detail_projection(
        {
            "id": 21,
            "slug": "q-legacy",
            "title": "生产问卷",
            "name": "生产问卷",
            "description": "",
            "is_disabled": False,
            "redirect_url": "",
            "created_at": "2026-05-23T00:00:00Z",
            "updated_at": "2026-05-23T00:00:00Z",
            "questions": [],
            "external_push_enabled": True,
            "external_push_url": "https://hooks.example.com/questionnaire",
            "external_push_type": "premium",
            "external_push_expires_at_ts": 1809100800,
            "external_push_day": 30,
            "external_push_frequency": 7,
            "external_push_remark": "深度思考群用户",
            "external_push_custom_params": [{"name": "source", "value": "questionnaire"}],
            "submission_count": 0,
            "assessment_enabled": False,
        }
    )

    questionnaire = payload["questionnaire"]
    assert questionnaire["external_push_enabled"] is True
    assert questionnaire["external_push_url"] == "https://hooks.example.com/questionnaire"
    assert questionnaire["external_push_type"] == "premium"
    assert questionnaire["external_push_expires_at_ts"] == 1809100800
    assert questionnaire["external_push_day"] == 30
    assert questionnaire["external_push_frequency"] == 7
    assert questionnaire["external_push_remark"] == "深度思考群用户"
    assert questionnaire["external_push_custom_params"] == [{"name": "source", "value": "questionnaire"}]


def test_next_admin_detail_projection_keeps_blank_external_push_values_blank():
    from aicrm_next.questionnaire.domain import admin_detail_projection

    payload = admin_detail_projection(
        {
            "id": 22,
            "slug": "q-blank",
            "title": "空外推配置问卷",
            "name": "空外推配置问卷",
            "description": "",
            "is_disabled": False,
            "redirect_url": "",
            "created_at": "2026-05-23T00:00:00Z",
            "updated_at": "2026-05-23T00:00:00Z",
            "questions": [],
            "external_push_enabled": False,
            "external_push_url": "",
            "external_push_type": "",
            "external_push_expires_at_ts": "",
            "external_push_day": "",
            "external_push_frequency": "",
            "external_push_remark": "",
            "external_push_custom_params": [],
            "submission_count": 0,
            "assessment_enabled": False,
        }
    )

    questionnaire = payload["questionnaire"]
    assert questionnaire["external_push_enabled"] is False
    assert questionnaire["external_push_url"] == ""
    assert questionnaire["external_push_type"] == ""
    assert questionnaire["external_push_expires_at_ts"] == ""
    assert questionnaire["external_push_day"] == ""
    assert questionnaire["external_push_frequency"] == ""
    assert questionnaire["external_push_remark"] == ""
    assert questionnaire["external_push_custom_params"] == []


def test_next_questionnaire_editor_does_not_prefill_external_push_defaults():
    root = Path(__file__).resolve().parents[1]
    sources = [
        root / "aicrm_next" / "questionnaire" / "templates" / "admin_questionnaires.html",
        root / "wecom_ability_service" / "templates" / "admin_questionnaires.html",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    assert "external_push_type: 'subscription'" not in combined
    assert "external_push_expires_at_ts: 1809100800" not in combined
    assert "placeholder=\"1809100800\"" not in combined
    assert "placeholder=\"20\"" not in combined


def test_questionnaire_editor_exposes_trial_external_push_type():
    root = Path(__file__).resolve().parents[1]
    sources = [
        root / "aicrm_next" / "questionnaire" / "templates" / "admin_questionnaires.html",
        root / "wecom_ability_service" / "templates" / "admin_questionnaires.html",
    ]
    for source in sources:
        content = source.read_text(encoding="utf-8")
        assert 'value="trial"' in content
        assert "首月权益" in content


def test_questionnaire_external_push_accepts_trial_type_without_pg(monkeypatch):
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

    from wecom_ability_service.domains.questionnaire import _service_helpers as helpers

    monkeypatch.setattr(helpers, "_questionnaire_exists_by_slug", lambda *args, **kwargs: False)

    payload = {
        "name": "trial external push",
        "title": "首月权益问卷",
        "external_push_enabled": True,
        "external_push_url": "https://hooks.example.com/q",
        "external_push_type": "trial",
        "questions": [],
    }

    normalized = helpers._normalize_questionnaire_payload(payload)
    assert normalized["external_push_type"] == "trial"

    with pytest.raises(ValueError, match="external_push_type must be subscription, premium or trial"):
        helpers._normalize_questionnaire_payload({**payload, "external_push_type": "unknown"})


def test_postgres_questionnaire_external_push_type_default_is_blank():
    root = Path(__file__).resolve().parents[1]
    schema = (root / "wecom_ability_service" / "schema_postgres.sql").read_text(encoding="utf-8")
    migration = (
        root / "wecom_ability_service" / "db" / "migrations" / "postgres_migrations.py"
    ).read_text(encoding="utf-8")

    assert "external_push_type TEXT NOT NULL DEFAULT ''" in schema
    assert "ADD COLUMN IF NOT EXISTS external_push_type TEXT NOT NULL DEFAULT ''" in migration
    assert "ALTER COLUMN external_push_type SET DEFAULT ''" in migration
    assert "DEFAULT 'subscription'" not in schema
    assert "SET external_push_type = 'subscription'" not in migration


def test_global_external_push_payload_builds_next_questionnaire_paths_without_flask_url_for(monkeypatch):
    from wecom_ability_service.application.questionnaire import queries

    row = {
        "id": 1,
        "questionnaire_id": 21,
        "questionnaire_title_snapshot": "真实生产问卷",
        "submission_record_id": 101,
        "retry_from_log_id": None,
        "retry_attempt": 0,
        "user_id": "user-1",
        "target_url": "https://hooks.example.com/apply",
        "request_payload": {},
        "response_status_code": 500,
        "response_body": "HTTP 500",
        "status": "failed",
        "failure_reason": "HTTP 500",
        "created_at": "2026-05-23 11:49:47",
        "updated_at": "2026-05-23 11:49:47",
        "is_retry": False,
        "retry_count": 0,
        "retries": [],
        "latest_log": {"id": 1, "status": "failed"},
        "latest_status": "failed",
        "latest_updated_at": "2026-05-23 11:49:47",
        "has_retry": False,
        "can_retry": True,
    }

    monkeypatch.setattr(
        queries.admin_console_repo,
        "list_questionnaire_external_push_log_threads",
        lambda *args, **kwargs: [dict(row)],
    )
    monkeypatch.setattr(
        queries.admin_console_repo,
        "count_questionnaire_external_push_logs",
        lambda **kwargs: 1,
    )
    monkeypatch.setattr(
        queries.questionnaire_domain_service,
        "is_questionnaire_external_push_global_enabled",
        lambda: True,
    )

    class FakeListQuestionnairesQuery:
        def __call__(self):
            return [{"external_push_enabled": True}]

    monkeypatch.setattr(queries, "ListQuestionnairesQuery", FakeListQuestionnairesQuery)

    payload = queries.GetGlobalQuestionnaireExternalPushLogsQuery()()

    assert payload["logs"][0]["questionnaire_path"] == "/admin/questionnaires/21"
    assert payload["logs"][0]["questionnaire_logs_path"] == "/admin/questionnaires/21/external-push-logs"
