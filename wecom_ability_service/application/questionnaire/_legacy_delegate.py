from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ...domains.questionnaire import preflight_service
from ...domains.questionnaire import service as questionnaire_domain_service
from .dto import (
    ApplyQuestionnaireMobileBindingCommandDTO,
    ApplyQuestionnaireSubmissionTagsCommandDTO,
    CheckQuestionnaireSubmissionStatusQueryDTO,
    ComputeQuestionnaireSubmissionOutcomeQueryDTO,
    CreateQuestionnaireCommandDTO,
    DeleteQuestionnaireCommandDTO,
    DeleteQuestionnaireSubmissionsBySlugCommandDTO,
    DisableQuestionnaireCommandDTO,
    ExportQuestionnaireSubmissionsQueryDTO,
    GetLatestQuestionnaireSubmitDebugQueryDTO,
    GetPublicQuestionnaireBySlugQueryDTO,
    GetQuestionnaireDetailQueryDTO,
    ResolveQuestionnaireSubmitIdentityQueryDTO,
    RetryQuestionnaireExternalPushLogCommandDTO,
    RetryQuestionnaireExternalPushLogsCommandDTO,
    SaveQuestionnaireSubmissionCommandDTO,
    SubmitQuestionnaireCommandDTO,
    UpdateQuestionnaireCommandDTO,
    ValidateQuestionnaireAnswersQueryDTO,
)


def list_questionnaires_legacy() -> list[dict[str, Any]]:
    return questionnaire_domain_service.list_questionnaires()


def list_available_wecom_tags_legacy() -> list[dict[str, Any]]:
    return questionnaire_domain_service.list_available_wecom_tags()


def build_questionnaire_preflight_legacy(
    config_snapshot: Mapping[str, Any],
    *,
    list_available_wecom_tags_fn: Callable[[], list[dict[str, Any]]],
    count_external_contact_identity_maps_fn: Callable[[], int],
) -> dict[str, Any]:
    return preflight_service.build_questionnaire_preflight_payload(
        config=config_snapshot,
        list_available_wecom_tags_fn=list_available_wecom_tags_fn,
        count_external_contact_identity_maps_fn=count_external_contact_identity_maps_fn,
    )


def get_latest_questionnaire_submit_debug_legacy(
    dto: GetLatestQuestionnaireSubmitDebugQueryDTO,
) -> dict[str, Any] | None:
    return questionnaire_domain_service.get_latest_questionnaire_submit_debug(int(dto.questionnaire_id))


def create_questionnaire_legacy(dto: CreateQuestionnaireCommandDTO) -> dict[str, Any]:
    return questionnaire_domain_service.create_questionnaire(dict(dto.payload or {}))


def get_questionnaire_detail_legacy(dto: GetQuestionnaireDetailQueryDTO) -> dict[str, Any] | None:
    return questionnaire_domain_service.get_questionnaire_detail(int(dto.questionnaire_id))


def update_questionnaire_legacy(dto: UpdateQuestionnaireCommandDTO) -> dict[str, Any] | None:
    return questionnaire_domain_service.update_questionnaire(
        int(dto.questionnaire_id),
        dict(dto.payload or {}),
    )


def disable_questionnaire_legacy(dto: DisableQuestionnaireCommandDTO) -> dict[str, Any] | None:
    return questionnaire_domain_service.disable_questionnaire(
        int(dto.questionnaire_id),
        bool(dto.is_disabled),
    )


def delete_questionnaire_submissions_by_slug_legacy(
    dto: DeleteQuestionnaireSubmissionsBySlugCommandDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.delete_questionnaire_submissions_by_slug(str(dto.slug or "").strip())


def delete_questionnaire_legacy(dto: DeleteQuestionnaireCommandDTO) -> bool:
    return questionnaire_domain_service.delete_questionnaire(int(dto.questionnaire_id))


def export_questionnaire_submissions_legacy(
    dto: ExportQuestionnaireSubmissionsQueryDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.export_questionnaire_submissions(int(dto.questionnaire_id))


def get_public_questionnaire_by_slug_legacy(
    dto: GetPublicQuestionnaireBySlugQueryDTO,
) -> dict[str, Any] | None:
    return questionnaire_domain_service.get_public_questionnaire_by_slug(str(dto.slug or "").strip())


def resolve_questionnaire_submit_identity_legacy(
    dto: ResolveQuestionnaireSubmitIdentityQueryDTO,
) -> dict[str, Any] | None:
    return questionnaire_domain_service.resolve_questionnaire_submit_identity(
        openid=str(dto.openid or "").strip(),
        unionid=str(dto.unionid or "").strip(),
        external_userid=str(dto.external_userid or "").strip(),
    )


def check_questionnaire_submission_status_legacy(
    dto: CheckQuestionnaireSubmissionStatusQueryDTO,
) -> bool:
    return questionnaire_domain_service.has_questionnaire_submission(
        int(dto.questionnaire_id),
        dict(dto.identity or {}) if dto.identity else None,
    )


def validate_questionnaire_answers_legacy(
    dto: ValidateQuestionnaireAnswersQueryDTO,
) -> list[dict[str, Any]]:
    return questionnaire_domain_service.validate_questionnaire_answers(
        dict(dto.questionnaire or {}),
        dto.answers,
    )


def compute_questionnaire_submission_outcome_legacy(
    dto: ComputeQuestionnaireSubmissionOutcomeQueryDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.compute_questionnaire_submission_outcome(
        dict(dto.questionnaire or {}),
        dto.answers,
    )


def save_questionnaire_submission_legacy(
    dto: SaveQuestionnaireSubmissionCommandDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.save_questionnaire_submission(
        dict(dto.questionnaire or {}),
        dict(dto.identity or {}) if dto.identity else None,
        dict(dto.computed_result or {}),
        dto.answers,
        request_meta=dict(dto.request_meta or {}) if dto.request_meta else None,
    )


def apply_questionnaire_mobile_binding_legacy(
    dto: ApplyQuestionnaireMobileBindingCommandDTO,
) -> dict[str, Any]:
    submission_snapshot = dict(dto.submission_snapshot or {})
    if dto.submission_id and "id" not in submission_snapshot:
        submission_snapshot["id"] = int(dto.submission_id)
    return questionnaire_domain_service.apply_questionnaire_mobile_binding(submission_snapshot)


def apply_questionnaire_submission_tags_legacy(
    dto: ApplyQuestionnaireSubmissionTagsCommandDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.apply_questionnaire_submission_tags_to_scrm(int(dto.submission_id))


def _build_submit_payload(dto: SubmitQuestionnaireCommandDTO) -> dict[str, Any]:
    payload = dict(dto.payload or {})
    if dto.answers is not None:
        payload["answers"] = dto.answers
    for key, value in (dto.hidden_identity or {}).items():
        if value not in (None, "") and key not in payload:
            payload[key] = value
    for key, value in (dto.source_params or {}).items():
        if value not in (None, "") and key not in payload:
            payload[key] = value
    return payload


def submit_questionnaire_legacy(dto: SubmitQuestionnaireCommandDTO) -> dict[str, Any]:
    return questionnaire_domain_service.submit_questionnaire(
        str(dto.slug or "").strip(),
        _build_submit_payload(dto),
        request_meta=dict(dto.request_meta or {}) if dto.request_meta else None,
    )


def retry_questionnaire_external_push_log_legacy(
    dto: RetryQuestionnaireExternalPushLogCommandDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.retry_questionnaire_external_push_log(int(dto.push_log_id))


def retry_questionnaire_external_push_logs_legacy(
    dto: RetryQuestionnaireExternalPushLogsCommandDTO,
) -> dict[str, Any]:
    return questionnaire_domain_service.retry_questionnaire_external_push_logs(list(dto.push_log_ids or []))


__all__ = [
    "apply_questionnaire_mobile_binding_legacy",
    "apply_questionnaire_submission_tags_legacy",
    "build_questionnaire_preflight_legacy",
    "check_questionnaire_submission_status_legacy",
    "compute_questionnaire_submission_outcome_legacy",
    "create_questionnaire_legacy",
    "delete_questionnaire_legacy",
    "delete_questionnaire_submissions_by_slug_legacy",
    "disable_questionnaire_legacy",
    "export_questionnaire_submissions_legacy",
    "get_latest_questionnaire_submit_debug_legacy",
    "get_public_questionnaire_by_slug_legacy",
    "get_questionnaire_detail_legacy",
    "list_available_wecom_tags_legacy",
    "list_questionnaires_legacy",
    "resolve_questionnaire_submit_identity_legacy",
    "retry_questionnaire_external_push_log_legacy",
    "retry_questionnaire_external_push_logs_legacy",
    "save_questionnaire_submission_legacy",
    "submit_questionnaire_legacy",
    "update_questionnaire_legacy",
    "validate_questionnaire_answers_legacy",
]
