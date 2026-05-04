from __future__ import annotations

import sys
import types
from pathlib import Path


def test_questionnaire_application_skeleton_is_importable():
    sys.modules.setdefault("imghdr", types.ModuleType("imghdr"))

    import wecom_ability_service.application as application_namespace
    from wecom_ability_service.application.questionnaire import (
        ApplyQuestionnaireMobileBindingCommand,
        ApplyQuestionnaireResultToScrmCommand,
        ApplyQuestionnaireSubmissionTagsCommand,
        BuildQuestionnairePreflightQuery,
        CheckQuestionnaireSubmissionStatusQuery,
        ComputeQuestionnaireSubmissionOutcomeQuery,
        CreateOrUpdateQuestionnaireCommand,
        CreateQuestionnaireCommand,
        DeleteQuestionnaireCommand,
        DeleteQuestionnaireSubmissionsBySlugCommand,
        DisableQuestionnaireCommand,
        ExportQuestionnaireSubmissionsQuery,
        GetLatestQuestionnaireSubmitDebugQuery,
        GetPublicQuestionnaireBySlugQuery,
        GetQuestionnaireDetailQuery,
        HasQuestionnaireSubmissionQuery,
        ListAvailableWeComTagsQuery,
        ListQuestionnairesQuery,
        ResolveQuestionnaireSubmitIdentityQuery,
        RetryQuestionnaireExternalPushCommand,
        RetryQuestionnaireExternalPushLogCommand,
        RetryQuestionnaireExternalPushLogsCommand,
        SaveQuestionnaireSubmissionCommand,
        SubmitQuestionnaireCommand,
        UpdateQuestionnaireCommand,
        ValidateQuestionnaireAnswersQuery,
    )

    assert "questionnaire" in application_namespace.__all__
    assert ListQuestionnairesQuery
    assert ListAvailableWeComTagsQuery
    assert BuildQuestionnairePreflightQuery
    assert GetLatestQuestionnaireSubmitDebugQuery
    assert GetQuestionnaireDetailQuery
    assert ExportQuestionnaireSubmissionsQuery
    assert GetPublicQuestionnaireBySlugQuery
    assert ResolveQuestionnaireSubmitIdentityQuery
    assert CheckQuestionnaireSubmissionStatusQuery
    assert HasQuestionnaireSubmissionQuery
    assert ValidateQuestionnaireAnswersQuery
    assert ComputeQuestionnaireSubmissionOutcomeQuery
    assert CreateQuestionnaireCommand
    assert CreateOrUpdateQuestionnaireCommand
    assert UpdateQuestionnaireCommand
    assert DisableQuestionnaireCommand
    assert DeleteQuestionnaireSubmissionsBySlugCommand
    assert DeleteQuestionnaireCommand
    assert SaveQuestionnaireSubmissionCommand
    assert ApplyQuestionnaireMobileBindingCommand
    assert ApplyQuestionnaireSubmissionTagsCommand
    assert ApplyQuestionnaireResultToScrmCommand
    assert SubmitQuestionnaireCommand
    assert RetryQuestionnaireExternalPushCommand
    assert RetryQuestionnaireExternalPushLogCommand
    assert RetryQuestionnaireExternalPushLogsCommand


def test_services_questionnaire_symbols_route_through_application_wrappers():
    services_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "services.py"
    source = services_path.read_text(encoding="utf-8")

    required_fragments = [
        "ListQuestionnairesQuery",
        "ListAvailableWeComTagsQuery",
        "GetLatestQuestionnaireSubmitDebugQuery",
        "CreateQuestionnaireCommand",
        "GetQuestionnaireDetailQuery",
        "UpdateQuestionnaireCommand",
        "DisableQuestionnaireCommand",
        "DeleteQuestionnaireSubmissionsBySlugCommand",
        "DeleteQuestionnaireCommand",
        "ExportQuestionnaireSubmissionsQuery",
        "GetPublicQuestionnaireBySlugQuery",
        "ValidateQuestionnaireAnswersQuery",
        "ComputeQuestionnaireSubmissionOutcomeQuery",
        "ResolveQuestionnaireSubmitIdentityQuery",
        "HasQuestionnaireSubmissionQuery",
        "SaveQuestionnaireSubmissionCommand",
        "ApplyQuestionnaireMobileBindingCommand",
        "ApplyQuestionnaireSubmissionTagsCommand",
        "ApplyQuestionnaireResultToScrmCommand",
        "SubmitQuestionnaireCommand",
        "RetryQuestionnaireExternalPushLogCommand",
        "RetryQuestionnaireExternalPushLogsCommand",
    ]
    for fragment in required_fragments:
        assert fragment in source, f"services.py must route questionnaire symbol through {fragment}"

    forbidden_fragments = [
        "list_questionnaires = questionnaire_domain_service.list_questionnaires",
        "list_available_wecom_tags = questionnaire_domain_service.list_available_wecom_tags",
        "get_latest_questionnaire_submit_debug = questionnaire_domain_service.get_latest_questionnaire_submit_debug",
        "create_questionnaire = questionnaire_domain_service.create_questionnaire",
        "get_questionnaire_detail = questionnaire_domain_service.get_questionnaire_detail",
        "update_questionnaire = questionnaire_domain_service.update_questionnaire",
        "disable_questionnaire = questionnaire_domain_service.disable_questionnaire",
        "delete_questionnaire_submissions_by_slug = questionnaire_domain_service.delete_questionnaire_submissions_by_slug",
        "delete_questionnaire = questionnaire_domain_service.delete_questionnaire",
        "export_questionnaire_submissions = questionnaire_domain_service.export_questionnaire_submissions",
        "get_public_questionnaire_by_slug = questionnaire_domain_service.get_public_questionnaire_by_slug",
        "validate_questionnaire_answers = questionnaire_domain_service.validate_questionnaire_answers",
        "compute_questionnaire_submission_outcome = questionnaire_domain_service.compute_questionnaire_submission_outcome",
        "return questionnaire_domain_service.resolve_questionnaire_submit_identity(",
        "return questionnaire_domain_service.has_questionnaire_submission(",
        "return questionnaire_domain_service.save_questionnaire_submission(",
        "return questionnaire_domain_service.apply_questionnaire_mobile_binding(",
        "return questionnaire_domain_service.apply_questionnaire_submission_tags_to_scrm(",
        "return questionnaire_domain_service.submit_questionnaire(",
        "return questionnaire_domain_service.retry_questionnaire_external_push_log(",
        "return questionnaire_domain_service.retry_questionnaire_external_push_logs(",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source, f"services.py must not regress to direct questionnaire legacy delegation: {fragment}"
