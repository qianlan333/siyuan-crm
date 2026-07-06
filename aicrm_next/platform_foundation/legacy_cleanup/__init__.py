from __future__ import annotations

ROUTE_OWNER = "ai_crm_next"
CAPABILITY_OWNER = "ai_crm_next/platform_foundation/legacy_cleanup"

from .repo import reset_legacy_cleanup_fixture_state
from .service import LegacyWebhookCleanupService, legacy_disabled_payload

__all__ = [
    "CAPABILITY_OWNER",
    "ROUTE_OWNER",
    "LegacyWebhookCleanupService",
    "legacy_disabled_payload",
    "reset_legacy_cleanup_fixture_state",
]
