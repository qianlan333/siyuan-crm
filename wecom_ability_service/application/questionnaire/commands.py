from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from ...domains.identity import service as identity_domain_service
from ...domains.questionnaire import service as questionnaire_domain_service
from ...infra.wechat_oauth import (
    WeChatOAuthRequestError,
    exchange_wechat_oauth_code,
    fetch_wechat_userinfo,
)
from .dto import (
    ApplyQuestionnaireMobileBindingCommandDTO,
    ApplyQuestionnaireMobileBindingCommandResultDTO,
    ApplyQuestionnaireResultToScrmCommandDTO,
    ApplyQuestionnaireResultToScrmCommandResultDTO,
    ApplyQuestionnaireSubmissionTagsCommandDTO,
    ApplyQuestionnaireSubmissionTagsCommandResultDTO,
    CreateOrUpdateQuestionnaireCommandDTO,
    CreateOrUpdateQuestionnaireCommandResultDTO,
    CreateQuestionnaireCommandDTO,
    CreateQuestionnaireCommandResultDTO,
    DeleteQuestionnaireCommandDTO,
    DeleteQuestionnaireCommandResultDTO,
    DeleteQuestionnaireSubmissionsBySlugCommandDTO,
    DeleteQuestionnaireSubmissionsBySlugCommandResultDTO,
    DisableQuestionnaireCommandDTO,
    DisableQuestionnaireCommandResultDTO,
    RetryQuestionnaireExternalPushCommandDTO,
    RetryQuestionnaireExternalPushCommandResultDTO,
    RetryQuestionnaireExternalPushLogCommandDTO,
    RetryQuestionnaireExternalPushLogCommandResultDTO,
    RetryQuestionnaireExternalPushLogsCommandDTO,
    RetryQuestionnaireExternalPushLogsCommandResultDTO,
    SaveQuestionnaireSubmissionCommandDTO,
    SaveQuestionnaireSubmissionCommandResultDTO,
    SubmitQuestionnaireCommandDTO,
    SubmitQuestionnaireCommandResultDTO,
    UpdateQuestionnaireCommandDTO,
    UpdateQuestionnaireCommandResultDTO,
)
from .queries import ResolveQuestionnaireRespondentIdentityQuery


def _bind_questionnaire_submit_runtime() -> None:
    questionnaire_domain_service._normalize_mobile = identity_domain_service.normalize_mobile


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


class QuestionnaireOauthExchangePayloadError(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        super().__init__("wechat_oauth_exchange_failed")
        self.payload = dict(payload or {})


class CreateQuestionnaireCommand:
    def __call__(self, dto: CreateQuestionnaireCommandDTO) -> CreateQuestionnaireCommandResultDTO:
        return questionnaire_domain_service.create_questionnaire(dict(dto.payload or {}))

    execute = __call__


class UpdateQuestionnaireCommand:
    def __call__(self, dto: UpdateQuestionnaireCommandDTO) -> UpdateQuestionnaireCommandResultDTO:
        return questionnaire_domain_service.update_questionnaire(
            int(dto.questionnaire_id),
            dict(dto.payload or {}),
        )

    execute = __call__


class CreateOrUpdateQuestionnaireCommand:
    def __call__(
        self,
        dto: CreateOrUpdateQuestionnaireCommandDTO,
    ) -> CreateOrUpdateQuestionnaireCommandResultDTO:
        if dto.questionnaire_id is None:
            return CreateQuestionnaireCommand()(
                CreateQuestionnaireCommandDTO(
                    payload=dict(dto.payload or {}),
                    operator=str(dto.operator or "").strip(),
                )
            )
        return UpdateQuestionnaireCommand()(
            UpdateQuestionnaireCommandDTO(
                questionnaire_id=int(dto.questionnaire_id),
                payload=dict(dto.payload or {}),
                operator=str(dto.operator or "").strip(),
            )
        )

    execute = __call__


class DisableQuestionnaireCommand:
    def __call__(self, dto: DisableQuestionnaireCommandDTO) -> DisableQuestionnaireCommandResultDTO:
        return questionnaire_domain_service.disable_questionnaire(
            int(dto.questionnaire_id),
            bool(dto.is_disabled),
        )

    execute = __call__


class DeleteQuestionnaireSubmissionsBySlugCommand:
    def __call__(
        self,
        dto: DeleteQuestionnaireSubmissionsBySlugCommandDTO,
    ) -> DeleteQuestionnaireSubmissionsBySlugCommandResultDTO:
        return questionnaire_domain_service.delete_questionnaire_submissions_by_slug(
            str(dto.slug or "").strip()
        )

    execute = __call__


class DeleteQuestionnaireCommand:
    def __call__(self, dto: DeleteQuestionnaireCommandDTO) -> DeleteQuestionnaireCommandResultDTO:
        return questionnaire_domain_service.delete_questionnaire(int(dto.questionnaire_id))

    execute = __call__


class SaveQuestionnaireSubmissionCommand:
    def __call__(
        self,
        dto: SaveQuestionnaireSubmissionCommandDTO,
    ) -> SaveQuestionnaireSubmissionCommandResultDTO:
        return questionnaire_domain_service.save_questionnaire_submission(
            dict(dto.questionnaire or {}),
            dict(dto.identity or {}) if dto.identity else None,
            dict(dto.computed_result or {}),
            dto.answers,
            request_meta=dict(dto.request_meta or {}) if dto.request_meta else None,
        )

    execute = __call__


class ApplyQuestionnaireMobileBindingCommand:
    def __call__(
        self,
        dto: ApplyQuestionnaireMobileBindingCommandDTO,
    ) -> ApplyQuestionnaireMobileBindingCommandResultDTO:
        submission_snapshot = dict(dto.submission_snapshot or {})
        if dto.submission_id and "id" not in submission_snapshot:
            submission_snapshot["id"] = int(dto.submission_id)
        return questionnaire_domain_service.apply_questionnaire_mobile_binding(submission_snapshot)

    execute = __call__


class ApplyQuestionnaireSubmissionTagsCommand:
    def __call__(
        self,
        dto: ApplyQuestionnaireSubmissionTagsCommandDTO,
    ) -> ApplyQuestionnaireSubmissionTagsCommandResultDTO:
        return questionnaire_domain_service.apply_questionnaire_submission_tags_to_scrm(
            int(dto.submission_id)
        )

    execute = __call__


class ApplyQuestionnaireResultToScrmCommand:
    def __call__(
        self,
        dto: ApplyQuestionnaireResultToScrmCommandDTO,
    ) -> ApplyQuestionnaireResultToScrmCommandResultDTO:
        return ApplyQuestionnaireSubmissionTagsCommand()(
            ApplyQuestionnaireSubmissionTagsCommandDTO(
                submission_id=int(dto.submission_id),
                operator=str(dto.operator or "").strip(),
            )
        )

    execute = __call__


class SubmitQuestionnaireCommand:
    def __call__(
        self,
        dto: SubmitQuestionnaireCommandDTO,
    ) -> SubmitQuestionnaireCommandResultDTO:
        _bind_questionnaire_submit_runtime()
        return questionnaire_domain_service.submit_questionnaire(
            str(dto.slug or "").strip(),
            _build_submit_payload(dto),
            request_meta=dict(dto.request_meta or {}) if dto.request_meta else None,
        )

    execute = __call__


class CompleteQuestionnaireOauthCallbackCommand:
    """Wave 3 questionnaire bridge command that performs OAuth code exchange and respondent session payload shaping for public questionnaire OAuth callback callers while transport keeps session write and redirect glue."""

    def __call__(
        self,
        *,
        code: str,
        state_payload: dict[str, Any] | None,
        app_id: str,
        app_secret: str,
        oauth_scope: str = "snsapi_base",
        exchange_oauth_code: Callable[..., dict[str, Any]] | None = None,
        fetch_wechat_userinfo_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_code = str(code or "").strip()
        normalized_state = {
            str(key): str(value)
            for key, value in (state_payload or {}).items()
            if value not in (None, "")
        }
        slug = str(normalized_state.get("slug") or "").strip()
        if not normalized_code:
            raise ValueError("code is required")
        if not slug:
            raise ValueError("invalid_state")

        exchange_fn = exchange_oauth_code or exchange_wechat_oauth_code
        userinfo_fn = fetch_wechat_userinfo_fn or fetch_wechat_userinfo
        oauth_payload = exchange_fn(
            app_id=str(app_id or "").strip(),
            app_secret=str(app_secret or "").strip(),
            code=normalized_code,
        )
        if oauth_payload.get("errcode") not in (None, 0):
            raise QuestionnaireOauthExchangePayloadError(oauth_payload)

        openid = str(oauth_payload.get("openid") or "").strip()
        unionid = str(oauth_payload.get("unionid") or "").strip()
        access_token = str(oauth_payload.get("access_token") or "").strip()
        if not unionid and str(oauth_scope or "").strip() == "snsapi_userinfo" and access_token and openid:
            try:
                userinfo_payload = userinfo_fn(access_token=access_token, openid=openid)
            except WeChatOAuthRequestError:
                userinfo_payload = {}
            if userinfo_payload.get("errcode") in (None, 0):
                unionid = str(userinfo_payload.get("unionid") or "").strip()

        session_identity = ResolveQuestionnaireRespondentIdentityQuery()(
            request_identity={"openid": openid, "unionid": unionid}
        )
        redirect_query = urlencode({key: value for key, value in normalized_state.items() if key != "slug"})
        redirect_target = f"/s/{slug}"
        if redirect_query:
            redirect_target = f"{redirect_target}?{redirect_query}"

        return {
            "slug": slug,
            "openid": openid,
            "unionid": unionid,
            "session_identity": {
                "openid": openid,
                "unionid": unionid,
                "respondent_key": str(session_identity.get("respondent_key") or "").strip(),
                "oauth_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "slug": slug,
            },
            "redirect_target": redirect_target,
        }

    execute = __call__


class RetryQuestionnaireExternalPushLogCommand:
    def __call__(
        self,
        dto: RetryQuestionnaireExternalPushLogCommandDTO,
    ) -> RetryQuestionnaireExternalPushLogCommandResultDTO:
        return questionnaire_domain_service.retry_questionnaire_external_push_log(
            int(dto.push_log_id)
        )

    execute = __call__


class RetryQuestionnaireExternalPushLogsCommand:
    def __call__(
        self,
        dto: RetryQuestionnaireExternalPushLogsCommandDTO,
    ) -> RetryQuestionnaireExternalPushLogsCommandResultDTO:
        return questionnaire_domain_service.retry_questionnaire_external_push_logs(
            list(dto.push_log_ids or [])
        )

    execute = __call__


class RetryQuestionnaireExternalPushCommand:
    def __call__(
        self,
        dto: RetryQuestionnaireExternalPushCommandDTO,
    ) -> RetryQuestionnaireExternalPushCommandResultDTO:
        if dto.push_log_ids:
            return RetryQuestionnaireExternalPushLogsCommand()(
                RetryQuestionnaireExternalPushLogsCommandDTO(
                    push_log_ids=list(dto.push_log_ids or []),
                    operator=str(dto.operator or "").strip(),
                )
            )
        return RetryQuestionnaireExternalPushLogCommand()(
            RetryQuestionnaireExternalPushLogCommandDTO(
                push_log_id=int(dto.push_log_id),
                operator=str(dto.operator or "").strip(),
            )
        )

    execute = __call__


__all__ = [
    "ApplyQuestionnaireMobileBindingCommand",
    "ApplyQuestionnaireResultToScrmCommand",
    "ApplyQuestionnaireSubmissionTagsCommand",
    "CompleteQuestionnaireOauthCallbackCommand",
    "CreateOrUpdateQuestionnaireCommand",
    "CreateQuestionnaireCommand",
    "DeleteQuestionnaireCommand",
    "DeleteQuestionnaireSubmissionsBySlugCommand",
    "DisableQuestionnaireCommand",
    "RetryQuestionnaireExternalPushCommand",
    "RetryQuestionnaireExternalPushLogCommand",
    "RetryQuestionnaireExternalPushLogsCommand",
    "SaveQuestionnaireSubmissionCommand",
    "SubmitQuestionnaireCommand",
    "UpdateQuestionnaireCommand",
]
