from __future__ import annotations

from ..customer_read_model.dto import InternalAuthQueryDTO, InternalAuthResultDTO


class AuthorizeInternalRequestQuery:
    """Wave 1 skeleton that delegates to ``infra.internal_auth_runtime.require_internal_api_token_compat``."""

    def __call__(self, dto: InternalAuthQueryDTO | None = None) -> InternalAuthResultDTO:
        # Wave 1 skeleton: preserve the current Flask request-context behavior
        # but delegate through infra instead of importing HTTP transport glue.
        from ...infra.internal_auth_runtime import require_internal_api_token_compat

        query = dto or InternalAuthQueryDTO()
        return require_internal_api_token_compat(
            token_keys=tuple(query.token_keys),
            legacy_header_names=tuple(query.legacy_header_names),
            require_configured=bool(query.require_configured),
        )

    execute = __call__


__all__ = ["AuthorizeInternalRequestQuery"]
