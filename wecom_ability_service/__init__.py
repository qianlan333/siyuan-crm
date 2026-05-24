from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, Response

from .db import close_db, init_app as init_db_app
from .infra.settings import DEFAULT_LAOHUANG_CHAT_WEBHOOK_URL, DEFAULT_OPENCLAW_WEBHOOK_URL
from .infra.task_queue import init_task_queue
from .http.internal_auth import register_admin_request_guards
from .mcp_adapter import mcp_bp
from .observability import attach_logging_filter, register_request_observability
from .routes import bp

DEFAULT_SECRET_KEY = "dev-secret-key-change-me"


def _has_configured_secret_key(app: Flask) -> bool:
    value = str(app.config.get("SECRET_KEY", "") or "").strip()
    return bool(value and value != DEFAULT_SECRET_KEY)


def _configure_logging(app: Flask) -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s "
        "request_id=%(request_id)s release_sha=%(release_sha)s method=%(method)s path=%(path)s %(message)s"
    )
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        app.logger.addHandler(handler)
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)
        attach_logging_filter(handler)
    app.logger.setLevel(logging.INFO)

    for logger_name in ["callback", "archive_sync", "contacts_sync", "wecom_api", "mcp", "questionnaire", "owner_backfill"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = True
        if not logger.handlers:
            for handler in app.logger.handlers:
                logger.addHandler(handler)


def _log_startup_config(app: Flask) -> None:
    oauth_keys = ["WECHAT_MP_APP_ID", "WECHAT_MP_APP_SECRET", "WECHAT_MP_OAUTH_SCOPE", "SECRET_KEY"]
    snapshot_items = []
    for key in oauth_keys:
        if key == "SECRET_KEY":
            status = "set" if _has_configured_secret_key(app) else "missing"
        else:
            status = "set" if str(app.config.get(key, "") or "").strip() else "missing"
        snapshot_items.append(f"{key}={status}")
    snapshot = ", ".join(snapshot_items)
    app.logger.info("questionnaire oauth config: %s", snapshot)
    missing_required = [
        key
        for key in ["WECHAT_MP_APP_ID", "WECHAT_MP_APP_SECRET"]
        if not str(app.config.get(key, "") or "").strip()
    ]
    if not _has_configured_secret_key(app):
        missing_required.append("SECRET_KEY")
    if missing_required:
        app.logger.warning(
            "questionnaire oauth not fully configured, missing=%s; service will still start and non-oauth flows remain available",
            ",".join(missing_required),
        )
    app.logger.info(
        "questionnaire session debug api: %s",
        "enabled" if app.config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API") else "disabled",
    )


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    explicit_debug_session_api = os.getenv("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API", "").strip()
    openclaw_webhook_url = os.getenv("OPENCLAW_WEBHOOK_URL", DEFAULT_OPENCLAW_WEBHOOK_URL)

    app.config.from_mapping(
        DEBUG=os.getenv("FLASK_ENV", "").lower() == "development",
        SECRET_KEY=os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY),
        APP_HOST=os.getenv("APP_HOST", "127.0.0.1"),
        APP_PORT=os.getenv("APP_PORT", "5000"),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        RELEASE_SHA=os.getenv("RELEASE_SHA", ""),
        WECOM_CORP_ID=os.getenv("WECOM_CORP_ID", ""),
        WECOM_CONTACT_SECRET=os.getenv("WECOM_CONTACT_SECRET", ""),
        WECOM_SECRET=os.getenv("WECOM_SECRET", ""),
        WECOM_AGENT_ID=os.getenv("WECOM_AGENT_ID", ""),
        WECOM_API_BASE=os.getenv("WECOM_API_BASE", "https://qyapi.weixin.qq.com"),
        ADMIN_AUTH_MODE=os.getenv("ADMIN_AUTH_MODE", "wecom_sso"),
        ADMIN_LOGIN_REDIRECT_URI=os.getenv("ADMIN_LOGIN_REDIRECT_URI", ""),
        ADMIN_WECHAT_TRUSTED_DOMAIN=os.getenv("ADMIN_WECHAT_TRUSTED_DOMAIN", ""),
        ADMIN_BREAK_GLASS_LOGIN_ENABLED=os.getenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED", ""),
        ADMIN_BREAK_GLASS_USERNAME=os.getenv("ADMIN_BREAK_GLASS_USERNAME", ""),
        ADMIN_BREAK_GLASS_PASSWORD_HASH=os.getenv("ADMIN_BREAK_GLASS_PASSWORD_HASH", ""),
        WECOM_ARCHIVE_SECRET=os.getenv("WECOM_ARCHIVE_SECRET", ""),
        WECOM_PRIVATE_KEY_PATH=os.getenv("WECOM_PRIVATE_KEY_PATH", "/home/ubuntu/wecom_private_key.pem"),
        WECOM_SDK_LIB_PATH=os.getenv(
            "WECOM_SDK_LIB_PATH", "/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so"
        ),
        WECOM_DEFAULT_OWNER_USERID=os.getenv("WECOM_DEFAULT_OWNER_USERID", ""),
        WECOM_CALLBACK_TOKEN=os.getenv("WECOM_CALLBACK_TOKEN", ""),
        WECOM_CALLBACK_AES_KEY=os.getenv("WECOM_CALLBACK_AES_KEY", ""),
        WECHAT_MP_APP_ID=os.getenv("WECHAT_MP_APP_ID", ""),
        WECHAT_MP_APP_SECRET=os.getenv("WECHAT_MP_APP_SECRET", ""),
        WECHAT_MP_OAUTH_SCOPE=os.getenv("WECHAT_MP_OAUTH_SCOPE", "snsapi_base"),
        WECHAT_PAY_ENABLED=os.getenv("WECHAT_PAY_ENABLED", "false"),
        WECHAT_PAY_APP_ID=os.getenv("WECHAT_PAY_APP_ID", ""),
        WECHAT_PAY_MCH_ID=os.getenv("WECHAT_PAY_MCH_ID", ""),
        WECHAT_PAY_API_V3_KEY=os.getenv("WECHAT_PAY_API_V3_KEY", ""),
        WECHAT_PAY_PRIVATE_KEY_PATH=os.getenv("WECHAT_PAY_PRIVATE_KEY_PATH", ""),
        WECHAT_PAY_CERT_SERIAL_NO=os.getenv("WECHAT_PAY_CERT_SERIAL_NO", ""),
        WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH=os.getenv("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH", ""),
        WECHAT_PAY_PLATFORM_CERT_SERIAL_NO=os.getenv("WECHAT_PAY_PLATFORM_CERT_SERIAL_NO", ""),
        WECHAT_PAY_NOTIFY_URL=os.getenv("WECHAT_PAY_NOTIFY_URL", ""),
        WECHAT_PAY_API_BASE=os.getenv("WECHAT_PAY_API_BASE", "https://api.mch.weixin.qq.com"),
        WECHAT_PAY_TIMEOUT_SECONDS=int(os.getenv("WECHAT_PAY_TIMEOUT_SECONDS", "10")),
        WECHAT_PAY_PRODUCT_CATALOG_JSON=os.getenv("WECHAT_PAY_PRODUCT_CATALOG_JSON", ""),
        ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API=(
            explicit_debug_session_api.lower() in {"1", "true", "yes"} if explicit_debug_session_api else None
        ),
        WECOM_ARCHIVE_TIMEOUT=int(os.getenv("WECOM_ARCHIVE_TIMEOUT", "15")),
        WECOM_SYNC_BATCH_SIZE=int(os.getenv("WECOM_SYNC_BATCH_SIZE", "100")),
        WECOM_SYNC_RETRY_LIMIT=int(os.getenv("WECOM_SYNC_RETRY_LIMIT", "3")),
        WECOM_CORP_TAG_LIMIT=int(os.getenv("WECOM_CORP_TAG_LIMIT", "1000")),
        AUTOMATION_CONVERSION_CHANNEL_PROVIDER=os.getenv("AUTOMATION_CONVERSION_CHANNEL_PROVIDER", "wecom_contact_way"),
        MCP_BEARER_TOKEN=os.getenv("MCP_BEARER_TOKEN", ""),
        ACCESS_TOKEN_CACHE_SECONDS=int(os.getenv("ACCESS_TOKEN_CACHE_SECONDS", "7000")),
        SIDEBAR_THIRD_PARTY_API_URL=os.getenv("SIDEBAR_THIRD_PARTY_API_URL", ""),
        SIDEBAR_THIRD_PARTY_API_TOKEN=os.getenv("SIDEBAR_THIRD_PARTY_API_TOKEN", ""),
        SIDEBAR_THIRD_PARTY_TIMEOUT_SECONDS=int(os.getenv("SIDEBAR_THIRD_PARTY_TIMEOUT_SECONDS", "10")),
        SIDEBAR_WORKBENCH_V2_ENABLED=os.getenv("SIDEBAR_WORKBENCH_V2_ENABLED", "true"),
        SIDEBAR_PERSON_DETAIL_URL_TEMPLATE=os.getenv(
            "SIDEBAR_PERSON_DETAIL_URL_TEMPLATE",
            "https://www.youcangogogo.com/person/{person_id}",
        ),
        OPENCLAW_WEBHOOK_URL=openclaw_webhook_url,
        LAOHUANG_CHAT_ENABLED=os.getenv("LAOHUANG_CHAT_ENABLED", "false"),
        LAOHUANG_CHAT_WEBHOOK_URL=os.getenv("LAOHUANG_CHAT_WEBHOOK_URL", DEFAULT_LAOHUANG_CHAT_WEBHOOK_URL),
        LAOHUANG_CHAT_TIMEOUT_SECONDS=int(os.getenv("LAOHUANG_CHAT_TIMEOUT_SECONDS", "10")),
        LAOHUANG_CHAT_SEND_CHANNEL=os.getenv("LAOHUANG_CHAT_SEND_CHANNEL", "private_message"),
        MESSAGE_ACTIVITY_DB_HOST=os.getenv("MESSAGE_ACTIVITY_DB_HOST", ""),
        MESSAGE_ACTIVITY_DB_PORT=int(os.getenv("MESSAGE_ACTIVITY_DB_PORT", "3306")),
        MESSAGE_ACTIVITY_DB_NAME=os.getenv("MESSAGE_ACTIVITY_DB_NAME", ""),
        MESSAGE_ACTIVITY_DB_USER=os.getenv("MESSAGE_ACTIVITY_DB_USER", ""),
        MESSAGE_ACTIVITY_DB_PASS=os.getenv("MESSAGE_ACTIVITY_DB_PASS", ""),
        REDIS_URL=os.getenv("REDIS_URL", ""),
        ENV_FILE_PATH=os.getenv("ENV_FILE_PATH", "/home/ubuntu/.openclaw-wecom.env"),
        CRON_SCRIPT_PATH=os.getenv(
            "CRON_SCRIPT_PATH",
            str(Path(app.root_path).parent / "scripts" / "run_incremental_archive_sync.py"),
        ),
        MESSAGE_ACTIVITY_SYNC_CRON_SCRIPT_PATH=os.getenv(
            "MESSAGE_ACTIVITY_SYNC_CRON_SCRIPT_PATH",
            str(Path(app.root_path).parent / "scripts" / "run_message_activity_sync.py"),
        ),
    )

    if test_config:
        app.config.update(test_config)

    app.config.setdefault("CALLBACK_ASYNC_ENABLED", not app.testing)
    if app.config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API") is None:
        app.config["ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API"] = app.testing

    init_db_app(app)
    app.teardown_appcontext(close_db)
    init_task_queue(app)
    _configure_logging(app)
    _log_startup_config(app)
    register_request_observability(app)
    register_admin_request_guards(app)

    _schema_migrated = [False]

    @app.before_request
    def _auto_migrate_schema() -> None:
        if not _schema_migrated[0]:
            _schema_migrated[0] = True
            from .db import init_db as _do_init_db
            try:
                _do_init_db()
            except Exception:
                app.logger.warning("auto schema migration failed", exc_info=True)

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status=204)

    app.register_blueprint(bp)
    app.register_blueprint(mcp_bp)

    return app
