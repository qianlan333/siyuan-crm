from __future__ import annotations

import os


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = str(os.getenv(name, "") or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def raw_database_url() -> str:
    return str(os.getenv("DATABASE_URL", "") or "").strip()


def database_mode() -> str:
    url = raw_database_url()
    if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        return "postgres"
    return "fixture"


def fixture_mode() -> bool:
    return database_mode() != "postgres"


def production_environment() -> bool:
    values = {
        str(os.getenv("AICRM_NEXT_ENV", "") or "").strip().lower(),
        str(os.getenv("ENVIRONMENT", "") or "").strip().lower(),
        str(os.getenv("APP_ENV", "") or "").strip().lower(),
        str(os.getenv("FLASK_ENV", "") or "").strip().lower(),
    }
    return bool(values & {"prod", "production"})


def production_repository_required() -> bool:
    return database_mode() == "postgres" or production_environment()


def production_data_mode_enabled() -> bool:
    return database_mode() == "postgres"


def production_data_ready() -> bool:
    return production_data_mode_enabled()


def runtime_health_state() -> dict:
    mode = database_mode()
    fixture = fixture_mode()
    data_ready = production_data_ready()
    degraded = fixture and production_environment()
    warning = ""
    if degraded:
        warning = "production runtime is using fixture data; production data is not ready"
    elif fixture:
        warning = "fixture data mode"
    return {
        "ok": not degraded,
        "status": "degraded" if degraded else "ok",
        "service": "aicrm-next",
        "database": mode,
        "database_mode": mode,
        "fixture_mode": fixture,
        "production_data_ready": data_ready,
        "production_data_mode": production_data_mode_enabled(),
        "repository_policy": (
            "production_repositories_required"
            if production_repository_required()
            else "fixture_repositories_allowed"
        ),
        "runtime_owner": "ai_crm_next",
        "legacy_runtime_enabled": False,
        "warning": warning,
    }


def runtime_route_map_state() -> dict:
    return {
        "web_release_sha": str(os.getenv("RELEASE_SHA") or os.getenv("GIT_SHA") or "unknown").strip() or "unknown",
        "worker_release_sha": str(os.getenv("WORKER_RELEASE_SHA") or "unknown").strip() or "unknown",
        "route_owner": "ai_crm_next",
        "app_name": "aicrm-next",
        "task_queue_backend": "next_task_queue",
        "task_queue_pending": None,
        "callback_async_enabled": "next_task_queue",
        "redis_url_active": bool(str(os.getenv("REDIS_URL") or "").strip()),
        "wecom_callback_routes": {
            "/wecom/external-contact/callback": "aicrm_next.channel_entry.api",
            "/api/wecom/events": "aicrm_next.channel_entry.api",
            "/api/admin/channels/{channel_id}/qrcode/generate": "aicrm_next.channel_entry.api",
        },
        "next_live_callback_gateway_enabled": True,
        "legacy_callback_fallback_enabled": False,
    }
