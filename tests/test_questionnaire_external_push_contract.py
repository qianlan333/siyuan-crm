from __future__ import annotations

import sys
import types
from pathlib import Path


def test_questionnaire_external_push_application_contract_is_importable():
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

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


def test_admin_questionnaire_console_uses_formal_application_external_push_owner():
    source = (
        Path(__file__).resolve().parents[1]
        / "wecom_ability_service"
        / "http"
        / "admin_questionnaire_push_logs.py"
    ).read_text(encoding="utf-8")

    required_fragments = [
        "GetQuestionnaireExternalPushLogsQuery",
        "GetGlobalQuestionnaireExternalPushLogsQuery",
        "RetryQuestionnaireExternalPushCommand",
    ]
    for fragment in required_fragments:
        assert fragment in source

    forbidden_fragments = [
        "build_questionnaire_external_push_logs_payload",
        "build_global_questionnaire_external_push_logs_payload",
        "retry_questionnaire_external_push_log_for_console",
        "retry_questionnaire_external_push_logs_for_console",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source
