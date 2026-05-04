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
from . import _legacy_delegate
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


class QuestionnaireOauthExchangePayloadError(RuntimeError):
    def __init__(self, payload: dict[str, Any]):
        super().__init__("wechat_oauth_exchange_failed")
        self.payload = dict(payload or {})


class CreateQuestionnaireCommand:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.create_questionnaire`` for admin CRUD callers."""

    def __call__(self, dto: CreateQuestionnaireCommandDTO) -> CreateQuestionnaireCommandResultDTO:
        return _legacy_delegate.create_questionnaire_legacy(dto)

    execute = __call__


class UpdateQuestionnaireCommand:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.update_questionnaire`` for admin CRUD callers."""

    def __call__(self, dto: UpdateQuestionnaireCommandDTO) -> UpdateQuestionnaireCommandResultDTO:
        return _legacy_delegate.update_questionnaire_legacy(dto)

    execute = __call__


class CreateOrUpdateQuestionnaireCommand:
    """Wave 3 questionnaire compatibility command that delegates to ``domains.questionnaire.service.create_questionnaire`` or ``update_questionnaire`` via ``_legacy_delegate`` for admin CRUD callers while both legacy entrypoints still exist."""

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
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.disable_questionnaire`` for admin lifecycle callers."""

    def __call__(self, dto: DisableQuestionnaireCommandDTO) -> DisableQuestionnaireCommandResultDTO:
        return _legacy_delegate.disable_questionnaire_legacy(dto)

    execute = __call__


class DeleteQuestionnaireSubmissionsBySlugCommand:
    """Wave 3 questionnaire compatibility command that delegates to ``domains.questionnaire.service.delete_questionnaire_submissions_by_slug`` for historical maintenance callers."""

    def __call__(
        self,
        dto: DeleteQuestionnaireSubmissionsBySlugCommandDTO,
    ) -> DeleteQuestionnaireSubmissionsBySlugCommandResultDTO:
        return _legacy_delegate.delete_questionnaire_submissions_by_slug_legacy(dto)

    execute = __call__


class DeleteQuestionnaireCommand:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.delete_questionnaire`` for admin lifecycle callers."""

    def __call__(self, dto: DeleteQuestionnaireCommandDTO) -> DeleteQuestionnaireCommandResultDTO:
        return _legacy_delegate.delete_questionnaire_legacy(dto)

    execute = __call__


class SaveQuestionnaireSubmissionCommand:
    """Wave 3 questionnaire compatibility command that delegates to ``domains.questionnaire.service.save_questionnaire_submission`` for legacy submit orchestration until PR 2/3 move submit ownership into application."""

    def __call__(
        self,
        dto: SaveQuestionnaireSubmissionCommandDTO,
    ) -> SaveQuestionnaireSubmissionCommandResultDTO:
        return _legacy_delegate.save_questionnaire_submission_legacy(dto)

    execute = __call__


class ApplyQuestionnaireMobileBindingCommand:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.apply_questionnaire_mobile_binding`` for submit-side identity binding hooks."""

    def __call__(
        self,
        dto: ApplyQuestionnaireMobileBindingCommandDTO,
    ) -> ApplyQuestionnaireMobileBindingCommandResultDTO:
        return _legacy_delegate.apply_questionnaire_mobile_binding_legacy(dto)

    execute = __call__


class ApplyQuestionnaireSubmissionTagsCommand:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.apply_questionnaire_submission_tags_to_scrm`` for submit-side SCRM apply hooks."""

    def __call__(
        self,
        dto: ApplyQuestionnaireSubmissionTagsCommandDTO,
    ) -> ApplyQuestionnaireSubmissionTagsCommandResultDTO:
        return _legacy_delegate.apply_questionnaire_submission_tags_legacy(dto)

    execute = __call__


class ApplyQuestionnaireResultToScrmCommand:
    """Wave 3 questionnaire compatibility command that delegates to ``domains.questionnaire.service.apply_questionnaire_submission_tags_to_scrm`` via ``_legacy_delegate`` for submit-side SCRM apply hooks and future admin retry tooling."""

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
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.submit_questionnaire`` for public submit callers and future questionnaire submit service orchestration."""

    def __call__(
        self,
        dto: SubmitQuestionnaireCommandDTO,
    ) -> SubmitQuestionnaireCommandResultDTO:
        _bind_questionnaire_submit_runtime()
        return _legacy_delegate.submit_questionnaire_legacy(dto)

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
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.retry_questionnaire_external_push_log`` for future admin external-push console callers."""

    def __call__(
        self,
        dto: RetryQuestionnaireExternalPushLogCommandDTO,
    ) -> RetryQuestionnaireExternalPushLogCommandResultDTO:
        return _legacy_delegate.retry_questionnaire_external_push_log_legacy(dto)

    execute = __call__


class RetryQuestionnaireExternalPushLogsCommand:
    """Wave 3 questionnaire skeleton that delegates to ``domains.questionnaire.service.retry_questionnaire_external_push_logs`` for future admin external-push batch retry callers."""

    def __call__(
        self,
        dto: RetryQuestionnaireExternalPushLogsCommandDTO,
    ) -> RetryQuestionnaireExternalPushLogsCommandResultDTO:
        return _legacy_delegate.retry_questionnaire_external_push_logs_legacy(dto)

    execute = __call__


class RetryQuestionnaireExternalPushCommand:
    """Wave 3 questionnaire compatibility command that delegates to ``domains.questionnaire.service.retry_questionnaire_external_push_log`` or ``retry_questionnaire_external_push_logs`` via ``_legacy_delegate`` for future admin external-push console callers with a single formal command name."""

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
