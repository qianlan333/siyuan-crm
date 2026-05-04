from __future__ import annotations

from ..domains.user_ops.service import (
    _resolve_third_party_user_id_by_mobile as _legacy_resolve_third_party_user_id_by_mobile,
)
from .wecom_runtime import get_contact_runtime_client


def get_user_ops_contact_client():
    """Stable Wave 2 adapter anchor for the user-ops contact runtime client."""

    return get_contact_runtime_client()


def resolve_third_party_user_id_by_mobile(mobile: str) -> str:
    """Stable Wave 2 adapter anchor for user-ops third-party-user lookup.

    Keep a direct reference to the legacy primitive so rebinding the domain hook
    does not recurse back into this adapter.
    """

    return _legacy_resolve_third_party_user_id_by_mobile(str(mobile or "").strip())


__all__ = [
    "get_user_ops_contact_client",
    "resolve_third_party_user_id_by_mobile",
]
