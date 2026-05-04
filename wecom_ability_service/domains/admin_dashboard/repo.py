from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from ...customer_center.repo import list_scope_external_userids
from ...db import get_db, get_db_backend
from ...infra.cache import cached
from ...infra.settings import get_setting
from ...wecom_callback import get_callback_config
from ..archive.service import count_archived_messages, get_last_sync_run, list_message_batches
from ..callbacks.service import get_recent_external_contact_event_logs
from ..contacts.repo import count_contacts, get_last_contacts_sync_time
from ..group_chats.repo import count_group_chats
from ..identity.service import count_external_contact_identity_maps
from ..questionnaire import build_questionnaire_preflight_payload, list_questionnaires
from ..user_ops.service import get_user_ops_deferred_job_counts, get_user_ops_overview


def detect_environment(config: Mapping[str, Any]) -> dict[str, str]:
    raw_candidates = [
        config.get("APP_ENV"),
        config.get("DEPLOY_ENV"),
        config.get("ENV"),
        os.getenv("APP_ENV", ""),
        os.getenv("DEPLOY_ENV", ""),
        os.getenv("FLASK_ENV", ""),
    ]
    normalized = next((str(item or "").strip().lower() for item in raw_candidates if str(item or "").strip()), "")

    if normalized in {"", "unknown"}:
        if bool(config.get("TESTING")) or bool(config.get("DEBUG")):
            normalized = "dev"
        else:
            normalized = "prod"

    if any(token in normalized for token in ("dev", "local", "test")):
        return {"value": "dev", "label": "DEV", "tone": "dev"}
    if any(token in normalized for token in ("stage", "staging", "pre")):
        return {"value": "staging", "label": "STAGING", "tone": "staging"}
    return {"value": "prod", "label": "PROD", "tone": "prod"}


def get_release_sha(config: Mapping[str, Any]) -> str:
    release_sha = str(config.get("RELEASE_SHA", "") or "").strip()
    return release_sha[:12] if release_sha else "local"


def get_callback_enabled() -> bool:
    callback_config = get_callback_config()
    return bool(callback_config.get("token") and callback_config.get("aes_key") and callback_config.get("corp_id"))


def get_background_async_enabled(config: Mapping[str, Any]) -> bool:
    return bool(config.get("CALLBACK_ASYNC_ENABLED", True))


def get_admin_health_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        last_sync = get_last_sync_run() or {}
        callback_enabled = get_callback_enabled()
        last_archive_sync_status = str(last_sync.get("status") or "").strip()
        state = "healthy"
        label = "HEALTHY"
        detail = "service ok"
        if last_archive_sync_status == "failed":
            state = "degraded"
            label = "DEGRADED"
            detail = "archive sync failed"
        elif not callback_enabled:
            state = "degraded"
            label = "DEGRADED"
            detail = "callback not configured"
        elif not get_background_async_enabled(config):
            detail = "background async disabled"
        return {
            "state": state,
            "label": label,
            "detail": detail,
            "database_backend": get_db_backend(),
            "callback_enabled": callback_enabled,
            "last_archive_sync_status": last_archive_sync_status or "unknown",
            "last_archive_sync_time": str(last_sync.get("finished_at") or last_sync.get("created_at") or "").strip(),
        }
    except Exception:
        return {
            "state": "unknown",
            "label": "UNKNOWN",
            "detail": "status unavailable",
            "database_backend": get_db_backend(),
            "callback_enabled": False,
            "last_archive_sync_status": "unknown",
            "last_archive_sync_time": "",
        }


def get_system_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    last_sync = get_last_sync_run() or {}
    health = get_admin_health_snapshot(config)
    return {
        "health": health,
        "release_sha": get_release_sha(config),
        "database_backend": get_db_backend(),
        "callback_enabled": get_callback_enabled(),
        "background_async_enabled": get_background_async_enabled(config),
        "last_archive_sync": {
            "run_id": last_sync.get("id"),
            "status": str(last_sync.get("status") or "").strip() or "never",
            "time": str(last_sync.get("finished_at") or last_sync.get("created_at") or "").strip(),
            "error_message": str(last_sync.get("error_message") or "").strip(),
        },
        "last_contacts_sync_time": str(get_last_contacts_sync_time() or "").strip(),
    }


@cached(ttl=60)
def count_customers() -> int:
    # The scope CTE walks 7 tables; cache for a minute since dashboard COUNT
    # is not a transactional consistency surface.
    return len(list_scope_external_userids())


@cached(ttl=60)
def count_class_users_current() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM class_user_status_current").fetchone()
    return int(row["total"] or 0) if row else 0


@cached(ttl=60)
def get_questionnaire_overview() -> dict[str, Any]:
    questionnaires = list_questionnaires()
    latest_submission = max(
        (str(item.get("last_submitted_at") or "").strip() for item in questionnaires),
        default="",
    )
    total_submissions = sum(int(item.get("submission_count") or 0) for item in questionnaires)
    return {
        "questionnaire_total": len(questionnaires),
        "total_submissions": total_submissions,
        "latest_submission": latest_submission,
    }


def get_business_summary_counts() -> dict[str, Any]:
    user_ops_overview = get_user_ops_overview()
    questionnaire_overview = get_questionnaire_overview()
    return {
        "archived_messages_total": count_archived_messages(),
        "contacts_total": count_contacts(),
        "group_chats_total": count_group_chats(),
        "customers_total": count_customers(),
        "questionnaire_total": questionnaire_overview["questionnaire_total"],
        "questionnaire_total_submissions": questionnaire_overview["total_submissions"],
        "questionnaire_latest_submission": questionnaire_overview["latest_submission"],
        "user_ops_lead_pool_total": int(user_ops_overview.get("lead_pool_total_count") or 0),
        "class_user_current_total": count_class_users_current(),
    }


def count_pending_message_batches() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS total FROM message_batches WHERE status = 'pending'"
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def list_pending_message_batches(limit: int = 5) -> list[dict[str, Any]]:
    return [dict(item) for item in list_message_batches(status="pending", limit=limit).get("items") or []]


def list_recent_failed_sync_runs(limit: int = 5) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT id, status, owner_userid, fetched_count, inserted_count, error_message, created_at, finished_at
        FROM sync_runs
        WHERE status = 'failed'
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 20)),),
    ).fetchall()
    return [dict(row) for row in rows]


def list_recent_failed_questionnaire_apply_logs(limit: int = 5) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT id, submission_id, external_userid, follow_user_userid, status, error_message, created_at
        FROM questionnaire_scrm_apply_logs
        WHERE status = 'failed'
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit), 20)),),
    ).fetchall()
    return [dict(row) for row in rows]


def list_recent_failed_callbacks(limit: int = 5) -> list[dict[str, Any]]:
    failed_items: list[dict[str, Any]] = []
    for item in get_recent_external_contact_event_logs(limit=max(10, limit * 4)):
        if str(item.get("process_status") or "").strip() != "failed":
            continue
        failed_items.append(item)
        if len(failed_items) >= limit:
            break
    return failed_items


def get_questionnaire_preflight_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    # Dashboard only needs a lightweight readiness summary. The detailed remote
    # WeCom tag fetch remains on the questionnaire center preflight endpoint.
    def _lightweight_tag_probe() -> list[dict[str, Any]]:
        required_keys = ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET", "WECOM_API_BASE"]
        missing = [key for key in required_keys if not str(config.get(key, "") or "").strip()]
        if missing:
            raise RuntimeError(f"missing config: {', '.join(missing)}")
        return [{"tag_id": "config-ok", "tag_name": "config-ok"}]

    return build_questionnaire_preflight_payload(
        config=config,
        list_available_wecom_tags_fn=_lightweight_tag_probe,
        count_external_contact_identity_maps_fn=count_external_contact_identity_maps,
    )


def get_mcp_runtime_snapshot(config: Mapping[str, Any]) -> dict[str, Any]:
    bearer_token = str(get_setting("MCP_BEARER_TOKEN") or config.get("MCP_BEARER_TOKEN", "") or "").strip()
    return {
        "bearer_token_configured": bool(bearer_token),
    }
