from __future__ import annotations

from datetime import datetime, timezone

from flask import current_app

from ..db import get_db_backend
from ..observability import get_request_id
from ..domains.archive.service import count_archived_messages, get_archive_last_seq, get_last_sync_run
from ..domains.contacts.repo import count_contacts, get_last_contacts_sync_time
from ..domains.group_chats.repo import count_group_chats
from ..domains.user_ops.service import get_user_ops_deferred_job_counts
from ..wecom_callback import get_callback_config
from .common import APP_STARTED_AT, APP_STARTED_AT_TEXT


def build_ops_status_payload() -> dict:
    last_sync = get_last_sync_run() or {}
    callback_enabled = bool(
        (get_callback_config().get("token") and get_callback_config().get("aes_key") and get_callback_config().get("corp_id"))
    )
    database_backend = get_db_backend()
    payload = {
        "ok": True,
        "service_ok": True,
        "request_id": get_request_id(),
        "release_sha": str(current_app.config.get("RELEASE_SHA", "") or "").strip(),
        "app_started_at": APP_STARTED_AT_TEXT,
        "uptime_seconds": max(int((datetime.now(timezone.utc).replace(tzinfo=None) - APP_STARTED_AT).total_seconds()), 0),
        "background_async_enabled": bool(current_app.config.get("CALLBACK_ASYNC_ENABLED", True)),
        "archived_messages_count": count_archived_messages(),
        "contacts_count": count_contacts(),
        "group_chats_count": count_group_chats(),
        "database_backend": database_backend,
        "last_seq": get_archive_last_seq(),
        "last_archive_sync_run_id": last_sync.get("id"),
        "last_archive_sync_status": last_sync.get("status", ""),
        "last_archive_sync_time": last_sync.get("finished_at") or last_sync.get("created_at") or "",
        "last_contacts_sync_time": get_last_contacts_sync_time(),
        "callback_enabled": callback_enabled,
        "user_ops_deferred_jobs": get_user_ops_deferred_job_counts(),
        "cron_script_path": current_app.config["CRON_SCRIPT_PATH"],
        "env_file_path": current_app.config["ENV_FILE_PATH"],
        "database_url_configured": bool(current_app.config.get("DATABASE_URL")),
    }
    return payload
