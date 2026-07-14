from __future__ import annotations

from typing import Any

from aicrm_next.message_archive.sync_service import execute_archive_sync as _execute_archive_sync


def execute_archive_sync(**kwargs: Any) -> dict[str, Any]:
    """Compose the Admin Jobs control plane with the Message Archive runner."""

    return _execute_archive_sync(**kwargs)
