from __future__ import annotations

import hmac
from dataclasses import dataclass

from .runtime_settings import runtime_bool, runtime_setting


LEGACY_FALLBACK_ENABLED_KEY = "AICRM_LEGACY_INTERNAL_TOKEN_FALLBACK_ENABLED"
LEGACY_FALLBACK_OWNER = "platform_ops"
LEGACY_FALLBACK_DELETE_AFTER = "2026-08-10"
LEGACY_SHARED_TOKEN_KEY = "AUTOMATION_INTERNAL_API_TOKEN"


@dataclass(frozen=True)
class InternalTokenCredential:
    purpose: str
    setting_key: str
    service_account: str


@dataclass(frozen=True)
class InternalTokenValidation:
    ok: bool
    error: str
    purpose: str
    setting_key: str
    service_account: str
    used_legacy_fallback: bool = False


TOKEN_PURPOSES = {
    "mcp": InternalTokenCredential("mcp", "MCP_BEARER_TOKEN", "mcp_integration"),
    "identity": InternalTokenCredential("identity", "IDENTITY_INTERNAL_API_TOKEN", "identity_integration"),
    "archive": InternalTokenCredential("archive", "ARCHIVE_INTERNAL_API_TOKEN", "archive_worker"),
    "group_broadcast": InternalTokenCredential(
        "group_broadcast",
        "GROUP_BROADCAST_INTERNAL_API_TOKEN",
        "group_broadcast_worker",
    ),
    "callback": InternalTokenCredential("callback", "CALLBACK_INTERNAL_API_TOKEN", "callback_worker"),
    "automation_worker": InternalTokenCredential(
        "automation_worker",
        LEGACY_SHARED_TOKEN_KEY,
        "automation_worker",
    ),
}
RUNTIME_ENVIRONMENT_KEYS = frozenset(
    {
        "AICRM_LEGACY_INTERNAL_TOKEN_FALLBACK_ENABLED",
        "ARCHIVE_INTERNAL_API_TOKEN",
        "AUTOMATION_INTERNAL_API_TOKEN",
        "CALLBACK_INTERNAL_API_TOKEN",
        "GROUP_BROADCAST_INTERNAL_API_TOKEN",
        "IDENTITY_INTERNAL_API_TOKEN",
        "MCP_BEARER_TOKEN",
    }
)


def credential_for_purpose(purpose: str) -> InternalTokenCredential:
    normalized = str(purpose or "").strip()
    try:
        return TOKEN_PURPOSES[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown internal token purpose: {normalized or '<empty>'}") from exc


def legacy_fallback_enabled() -> bool:
    return runtime_bool(LEGACY_FALLBACK_ENABLED_KEY, default=False)


def internal_service_token_for_purpose(purpose: str) -> str:
    credential = credential_for_purpose(purpose)
    primary = str(runtime_setting(credential.setting_key) or "").strip()
    if primary:
        return primary
    if credential.purpose != "automation_worker" and legacy_fallback_enabled():
        return str(runtime_setting(LEGACY_SHARED_TOKEN_KEY) or "").strip()
    return ""


def validate_internal_service_token(purpose: str, provided: str) -> InternalTokenValidation:
    credential = credential_for_purpose(purpose)
    primary = str(runtime_setting(credential.setting_key) or "").strip()
    legacy = ""
    if credential.purpose != "automation_worker" and legacy_fallback_enabled():
        legacy = str(runtime_setting(LEGACY_SHARED_TOKEN_KEY) or "").strip()
    configured = [(primary, False)] if primary else []
    if legacy and (not primary or not hmac.compare_digest(legacy, primary)):
        configured.append((legacy, True))
    if not configured:
        return InternalTokenValidation(
            ok=False,
            error="internal_token_not_configured",
            purpose=credential.purpose,
            setting_key=credential.setting_key,
            service_account=credential.service_account,
        )
    candidate = str(provided or "").strip()
    for expected, used_legacy in configured:
        if candidate and hmac.compare_digest(candidate, expected):
            return InternalTokenValidation(
                ok=True,
                error="",
                purpose=credential.purpose,
                setting_key=credential.setting_key,
                service_account=credential.service_account,
                used_legacy_fallback=used_legacy,
            )
    return InternalTokenValidation(
        ok=False,
        error="internal_token_required",
        purpose=credential.purpose,
        setting_key=credential.setting_key,
        service_account=credential.service_account,
    )
