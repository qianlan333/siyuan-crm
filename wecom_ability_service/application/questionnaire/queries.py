from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import url_for

from ...domains.admin_console import repo as admin_console_repo
from ...domains.questionnaire import service as questionnaire_domain_service
from ..identity_contact.dto import CountExternalContactIdentityMapsQueryDTO
from ..identity_contact.queries import CountExternalContactIdentityMapsQuery
from . import _legacy_delegate
from .dto import (
    BuildQuestionnairePreflightQueryDTO,
    BuildQuestionnairePreflightResultDTO,
    CheckQuestionnaireSubmissionStatusQueryDTO,
    CheckQuestionnaireSubmissionStatusResultDTO,
    ComputeQuestionnaireSubmissionOutcomeQueryDTO,
    ComputeQuestionnaireSubmissionOutcomeResultDTO,
    ExportQuestionnaireSubmissionsQueryDTO,
    ExportQuestionnaireSubmissionsResultDTO,
    GetLatestQuestionnaireSubmitDebugQueryDTO,
    GetLatestQuestionnaireSubmitDebugResultDTO,
    GetPublicQuestionnaireBySlugQueryDTO,
    GetPublicQuestionnaireBySlugResultDTO,
    GetQuestionnaireDetailQueryDTO,
    GetQuestionnaireDetailResultDTO,
    HasQuestionnaireSubmissionQueryDTO,
    ListAvailableWeComTagsQueryDTO,
    ListAvailableWeComTagsResultDTO,
    ListQuestionnairesQueryDTO,
    ListQuestionnairesResultDTO,
    ResolveQuestionnaireSubmitIdentityQueryDTO,
    ResolveQuestionnaireSubmitIdentityResultDTO,
    ValidateQuestionnaireAnswersQueryDTO,
    ValidateQuestionnaireAnswersResultDTO,
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _questionnaire_console_paths(slug: str) -> dict[str, str]:
    normalized_slug = _normalized_text(slug)
    return {
        "public_path": f"/s/{normalized_slug}" if normalized_slug else "",
        "submitted_path": f"/s/{normalized_slug}/submitted" if normalized_slug else "",
    }


def _questionnaire_external_push_status_tone(value: str) -> str:
    if value == "success":
        return "ok"
    if value == "skipped":
        return "warn"
    return "danger"


def _questionnaire_external_push_status_label(value: str) -> str:
    if value == "success":
        return "成功"
    if value == "skipped":
        return "跳过"
    return "失败"


def _questionnaire_external_push_effective_state_label(row: dict[str, Any]) -> str:
    latest_status = _normalized_text(row.get("latest_status"))
    if row.get("has_retry"):
        if latest_status == "success":
            return "补发成功"
        if latest_status == "skipped":
            return "补发已跳过"
        return "补发仍失败（待补发）"
    if latest_status == "success":
        return "首发成功"
    if latest_status == "skipped":
        return "首发已跳过"
    return "首发失败（待补发）"


def _normalize_questionnaire_external_push_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        latest_log = dict(row.get("latest_log") or {})
        normalized_rows.append(
            {
                **row,
                "first_status_label": _questionnaire_external_push_status_label(_normalized_text(row.get("status"))),
                "first_status_tone": _questionnaire_external_push_status_tone(_normalized_text(row.get("status"))),
                "effective_status_label": _questionnaire_external_push_effective_state_label(row),
                "effective_status_tone": _questionnaire_external_push_status_tone(
                    _normalized_text(row.get("latest_status"))
                ),
                "retries": [
                    {
                        **retry,
                        "status_label": _questionnaire_external_push_status_label(
                            _normalized_text(retry.get("status"))
                        ),
                        "status_tone": _questionnaire_external_push_status_tone(
                            _normalized_text(retry.get("status"))
                        ),
                    }
                    for retry in row.get("retries") or []
                ],
                "latest_log": {
                    **latest_log,
                    "status_label": _questionnaire_external_push_status_label(
                        _normalized_text(latest_log.get("status"))
                    ),
                    "status_tone": _questionnaire_external_push_status_tone(
                        _normalized_text(latest_log.get("status"))
                    ),
                },
            }
        )
    return normalized_rows


class ListQuestionnairesQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.list_questionnaires`` via ``_legacy_delegate`` for admin questionnaire readers and future admin console consumers."""

    def __call__(self, dto: ListQuestionnairesQueryDTO | None = None) -> ListQuestionnairesResultDTO:
        del dto
        return _legacy_delegate.list_questionnaires_legacy()

    execute = __call__


class ListAvailableWeComTagsQuery:
    """Wave 3 questionnaire compatibility query that delegates to ``domains.questionnaire.service.list_available_wecom_tags`` for admin questionnaire tag pickers and preflight checks."""

    def __call__(
        self,
        dto: ListAvailableWeComTagsQueryDTO | None = None,
    ) -> ListAvailableWeComTagsResultDTO:
        del dto
        return _legacy_delegate.list_available_wecom_tags_legacy()

    execute = __call__


class BuildQuestionnairePreflightQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.preflight_service.build_questionnaire_preflight_payload`` while composing stable questionnaire and identity application queries for future admin preflight callers."""

    def __call__(
        self,
        dto: BuildQuestionnairePreflightQueryDTO,
    ) -> BuildQuestionnairePreflightResultDTO:
        return _legacy_delegate.build_questionnaire_preflight_legacy(
            dto.config_snapshot,
            list_available_wecom_tags_fn=ListAvailableWeComTagsQuery(),
            count_external_contact_identity_maps_fn=lambda: CountExternalContactIdentityMapsQuery()(
                CountExternalContactIdentityMapsQueryDTO()
            ),
        )

    execute = __call__


class GetLatestQuestionnaireSubmitDebugQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.get_latest_questionnaire_submit_debug`` for admin debug readers."""

    def __call__(
        self,
        dto: GetLatestQuestionnaireSubmitDebugQueryDTO,
    ) -> GetLatestQuestionnaireSubmitDebugResultDTO:
        return _legacy_delegate.get_latest_questionnaire_submit_debug_legacy(dto)

    execute = __call__


class GetQuestionnaireDetailQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.get_questionnaire_detail`` for admin readers and future automation-adjacent readers."""

    def __call__(self, dto: GetQuestionnaireDetailQueryDTO) -> GetQuestionnaireDetailResultDTO:
        return _legacy_delegate.get_questionnaire_detail_legacy(dto)

    execute = __call__


class ExportQuestionnaireSubmissionsQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.export_questionnaire_submissions`` for admin export callers."""

    def __call__(
        self,
        dto: ExportQuestionnaireSubmissionsQueryDTO,
    ) -> ExportQuestionnaireSubmissionsResultDTO:
        return _legacy_delegate.export_questionnaire_submissions_legacy(dto)

    execute = __call__


class GetQuestionnaireExternalPushLogsQuery:
    """Wave 3 questionnaire console query that reads questionnaire-scoped external-push log threads via stable application queries plus ``domains.admin_console.repo`` while admin external-push pages stop touching legacy questionnaire services directly."""

    def __call__(
        self,
        *,
        questionnaire_id: int,
        status: str = "",
        limit: int | str = 50,
    ) -> dict[str, Any] | None:
        questionnaire = GetQuestionnaireDetailQuery()(
            GetQuestionnaireDetailQueryDTO(questionnaire_id=int(questionnaire_id))
        )
        if not questionnaire:
            return None
        normalized_status = _normalized_text(status)
        effective_status_filter = ""
        if normalized_status in {"failed", "failed_current"}:
            normalized_status = "failed_current"
            effective_status_filter = "failed"
        elif normalized_status in {"success", "success_current"}:
            normalized_status = "success_current"
            effective_status_filter = "success"
        normalized_limit = _normalized_int(limit, default=50, minimum=1, maximum=200)
        rows = admin_console_repo.list_questionnaire_external_push_log_threads(
            int(questionnaire_id),
            status=effective_status_filter,
            limit=normalized_limit,
        )
        normalized_rows = _normalize_questionnaire_external_push_rows(rows)
        return {
            "is_global": False,
            "questionnaire": {
                **questionnaire,
                **_questionnaire_console_paths(_normalized_text(questionnaire.get("slug"))),
            },
            "filters": {
                "status": normalized_status,
                "limit": normalized_limit,
            },
            "status_options": [
                {"value": "", "label": "全部"},
                {"value": "failed_current", "label": "仅待补发"},
                {"value": "success_current", "label": "仅当前成功"},
            ],
            "summary": admin_console_repo.summarize_questionnaire_external_push_logs(int(questionnaire_id)),
            "logs": normalized_rows,
            "retryable_count": sum(1 for row in normalized_rows if row.get("can_retry")),
        }

    execute = __call__


class GetGlobalQuestionnaireExternalPushLogsQuery:
    """Wave 3 questionnaire console query that reads global external-push log threads and summary via stable application questionnaire readers instead of admin console callers reaching questionnaire repo or legacy retry services directly."""

    def __call__(
        self,
        *,
        questionnaire_id: str = "",
        questionnaire_title: str = "",
        status: str = "",
        user_id: str = "",
        target_url: str = "",
        limit: int | str = 50,
    ) -> dict[str, Any]:
        normalized_questionnaire_id = _normalized_int(
            questionnaire_id,
            default=0,
            minimum=0,
            maximum=10**9,
        )
        questionnaire_id_filter = normalized_questionnaire_id or None
        normalized_questionnaire_title = _normalized_text(questionnaire_title)
        normalized_status = _normalized_text(status)
        normalized_user_id = _normalized_text(user_id)
        normalized_target_url = _normalized_text(target_url)
        effective_status_filter = ""
        if normalized_status in {"failed", "failed_current"}:
            normalized_status = "failed_current"
            effective_status_filter = "failed"
        elif normalized_status in {"success", "success_current"}:
            normalized_status = "success_current"
            effective_status_filter = "success"
        normalized_limit = _normalized_int(limit, default=50, minimum=1, maximum=200)
        filtered_rows = admin_console_repo.list_questionnaire_external_push_log_threads(
            questionnaire_id_filter,
            questionnaire_title=normalized_questionnaire_title,
            user_id=normalized_user_id,
            target_url=normalized_target_url,
            status=effective_status_filter,
            limit=None,
        )
        all_rows = admin_console_repo.list_questionnaire_external_push_log_threads(None, limit=None)
        recent_since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        normalized_rows = _normalize_questionnaire_external_push_rows(filtered_rows[:normalized_limit])
        all_questionnaires = ListQuestionnairesQuery()()
        total_questionnaires = len(all_questionnaires)
        enabled_questionnaire_count = sum(1 for item in all_questionnaires if item.get("external_push_enabled"))
        current_failed_count = sum(1 for row in all_rows if row.get("can_retry"))
        current_success_count = sum(1 for row in all_rows if _normalized_text(row.get("latest_status")) == "success")
        current_skipped_count = sum(1 for row in all_rows if _normalized_text(row.get("latest_status")) == "skipped")
        global_switch_enabled = questionnaire_domain_service.is_questionnaire_external_push_global_enabled()

        for row in normalized_rows:
            row["questionnaire_path"] = url_for(
                "api.admin_console_questionnaire_detail",
                questionnaire_id=int(row.get("questionnaire_id") or 0),
            )
            row["questionnaire_logs_path"] = url_for(
                "api.admin_console_questionnaire_external_push_logs",
                questionnaire_id=int(row.get("questionnaire_id") or 0),
            )

        return {
            "is_global": True,
            "questionnaire": None,
            "filters": {
                "questionnaire_id": normalized_questionnaire_id,
                "questionnaire_title": normalized_questionnaire_title,
                "status": normalized_status,
                "user_id": normalized_user_id,
                "target_url": normalized_target_url,
                "limit": normalized_limit,
            },
            "status_options": [
                {"value": "", "label": "全部"},
                {"value": "failed_current", "label": "仅待补发"},
                {"value": "success_current", "label": "仅当前成功"},
            ],
            "summary": {
                "questionnaire_total_count": total_questionnaires,
                "enabled_questionnaire_count": enabled_questionnaire_count,
                "matched_questionnaire_count": len({int(row.get("questionnaire_id") or 0) for row in filtered_rows}),
                "total_log_count": admin_console_repo.count_questionnaire_external_push_logs(),
                "current_failed_count": current_failed_count,
                "current_success_count": current_success_count,
                "current_skipped_count": current_skipped_count,
                "recent_success_count": admin_console_repo.count_questionnaire_external_push_logs(
                    status="success",
                    created_at_gte=recent_since,
                ),
                "recent_failed_count": admin_console_repo.count_questionnaire_external_push_logs(
                    status="failed",
                    created_at_gte=recent_since,
                ),
                "global_switch_enabled": global_switch_enabled,
                "global_switch_label": "已开启" if global_switch_enabled else "已关闭（止损中）",
                "global_switch_tone": "ok" if global_switch_enabled else "danger",
            },
            "logs": normalized_rows,
            "retryable_count": sum(1 for row in normalized_rows if row.get("can_retry")),
        }

    execute = __call__


class GetPublicQuestionnaireBySlugQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.get_public_questionnaire_by_slug`` for public read and submit callers."""

    def __call__(
        self,
        dto: GetPublicQuestionnaireBySlugQueryDTO,
    ) -> GetPublicQuestionnaireBySlugResultDTO:
        return _legacy_delegate.get_public_questionnaire_by_slug_legacy(dto)

    execute = __call__


class ResolveQuestionnaireSubmitIdentityQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.resolve_questionnaire_submit_identity`` for public submit identity lookup before the dedicated questionnaire identity service lands."""

    def __call__(
        self,
        dto: ResolveQuestionnaireSubmitIdentityQueryDTO | None = None,
    ) -> ResolveQuestionnaireSubmitIdentityResultDTO:
        return _legacy_delegate.resolve_questionnaire_submit_identity_legacy(
            dto or ResolveQuestionnaireSubmitIdentityQueryDTO()
        )

    execute = __call__


class ResolveQuestionnaireRespondentIdentityQuery:
    """Wave 3 questionnaire bridge query that composes session and request identity hints for public questionnaire read/submit callers while legacy identity-map lookup still delegates through ``ResolveQuestionnaireSubmitIdentityQuery``."""

    def __call__(
        self,
        *,
        session_identity: dict[str, Any] | None = None,
        request_identity: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        session_payload = {
            "respondent_key": str((session_identity or {}).get("respondent_key") or "").strip(),
            "openid": str((session_identity or {}).get("openid") or "").strip(),
            "unionid": str((session_identity or {}).get("unionid") or "").strip(),
            "external_userid": str((session_identity or {}).get("external_userid") or "").strip(),
        }
        request_payload = {
            "respondent_key": str((request_identity or {}).get("respondent_key") or "").strip(),
            "openid": str((request_identity or {}).get("openid") or "").strip(),
            "unionid": str((request_identity or {}).get("unionid") or "").strip(),
            "external_userid": str((request_identity or {}).get("external_userid") or "").strip(),
        }
        merged = {
            "respondent_key": session_payload["respondent_key"] or request_payload["respondent_key"],
            "openid": session_payload["openid"] or request_payload["openid"],
            "unionid": session_payload["unionid"] or request_payload["unionid"],
            "external_userid": request_payload["external_userid"] or session_payload["external_userid"],
        }
        if not merged["respondent_key"]:
            merged["respondent_key"] = (
                merged["unionid"] or merged["openid"] or merged["external_userid"]
            )
        return {key: value for key, value in merged.items() if value}

    execute = __call__


class CheckQuestionnaireSubmissionStatusQuery:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.has_questionnaire_submission`` for public read/submit duplicate checks."""

    def __call__(
        self,
        dto: CheckQuestionnaireSubmissionStatusQueryDTO,
    ) -> CheckQuestionnaireSubmissionStatusResultDTO:
        return _legacy_delegate.check_questionnaire_submission_status_legacy(dto)

    execute = __call__


class HasQuestionnaireSubmissionQuery:
    """Wave 3 questionnaire compatibility query that delegates to ``domains.questionnaire.service.has_questionnaire_submission`` for public submit duplicate checks and legacy caller naming."""

    def __call__(
        self,
        dto: HasQuestionnaireSubmissionQueryDTO,
    ) -> CheckQuestionnaireSubmissionStatusResultDTO:
        return _legacy_delegate.check_questionnaire_submission_status_legacy(
            CheckQuestionnaireSubmissionStatusQueryDTO(
                questionnaire_id=int(dto.questionnaire_id),
                identity=dict(dto.identity or {}) if dto.identity else None,
            )
        )

    execute = __call__


class ValidateQuestionnaireAnswersQuery:
    """Wave 3 questionnaire compatibility query that delegates to ``domains.questionnaire.service.validate_questionnaire_answers`` for legacy submit helpers while public submit wiring is still on the old path."""

    def __call__(
        self,
        dto: ValidateQuestionnaireAnswersQueryDTO,
    ) -> ValidateQuestionnaireAnswersResultDTO:
        return _legacy_delegate.validate_questionnaire_answers_legacy(dto)

    execute = __call__


class ComputeQuestionnaireSubmissionOutcomeQuery:
    """Wave 3 questionnaire compatibility query that delegates to ``domains.questionnaire.service.compute_questionnaire_submission_outcome`` for legacy submit helpers until PR 2/3 move orchestration into application."""

    def __call__(
        self,
        dto: ComputeQuestionnaireSubmissionOutcomeQueryDTO,
    ) -> ComputeQuestionnaireSubmissionOutcomeResultDTO:
        return _legacy_delegate.compute_questionnaire_submission_outcome_legacy(dto)

    execute = __call__


__all__ = [
    "BuildQuestionnairePreflightQuery",
    "CheckQuestionnaireSubmissionStatusQuery",
    "ComputeQuestionnaireSubmissionOutcomeQuery",
    "ExportQuestionnaireSubmissionsQuery",
    "GetGlobalQuestionnaireExternalPushLogsQuery",
    "GetLatestQuestionnaireSubmitDebugQuery",
    "GetPublicQuestionnaireBySlugQuery",
    "GetQuestionnaireExternalPushLogsQuery",
    "GetQuestionnaireDetailQuery",
    "HasQuestionnaireSubmissionQuery",
    "ListAvailableWeComTagsQuery",
    "ListQuestionnairesQuery",
    "ResolveQuestionnaireRespondentIdentityQuery",
    "ResolveQuestionnaireSubmitIdentityQuery",
    "ValidateQuestionnaireAnswersQuery",
]
