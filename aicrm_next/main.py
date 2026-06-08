from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai_assist.api import router as ai_assist_router
from .admin_auth.api import router as admin_auth_router
from .admin_config.api import router as admin_config_router
from .admin_shell.routes import router as admin_shell_router
from .admin_auth import reset_admin_auth_fixture_state
from .admin_jobs.repository import reset_admin_jobs_fixture_state
from .admin_jobs.routes import router as admin_jobs_router
from .automation_engine.admin_pages import router as automation_admin_pages_router
from .automation_engine.api import router as automation_router
from .automation_engine.channel_admin_pages import router as channel_admin_pages_router
from .automation_engine.channels_api import router as automation_channels_router
from .channel_entry.api import router as channel_entry_router
from .automation_engine.group_ops.admin_pages import router as group_ops_admin_pages_router
from .automation_engine.group_ops.repo import reset_group_ops_fixture_state
from .automation_engine.customer_webhooks import reset_customer_webhook_fixture_state
from .automation_engine.member_actions import reset_member_actions_fixture_state
from .automation_engine.repo import reset_automation_fixture_state
from .auth_wecom.api import router as auth_wecom_router
from .commerce.api import router as commerce_router
from .commerce.repo import reset_commerce_fixture_state
from .common_operation_members import router as common_operation_members_router
from .cloud_orchestrator.api import router as cloud_orchestrator_router
from .cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from .cloud_orchestrator.campaigns_write import reset_campaign_write_fixture_state
from .cloud_orchestrator.repository import reset_cloud_plan_fixture_state
from .customer_tags.api import read_router as customer_tags_read_router
from .customer_tags.api import router as customer_tags_router
from .customer_tags.api import write_router as customer_tags_write_router
from .customer_tags.admin_pages import router as customer_tags_admin_pages_router
from .customer_tags.admin_write import reset_wecom_tag_write_fixture_state
from .customer_tags.live_mutation import reset_wecom_tag_live_mutation_fixture_state
from .customer_read_model.api import router as customer_router
from .frontend_compat.legacy_routes import router as frontend_compat_router
from .hxc_dashboard.api import router as hxc_dashboard_router
from .hxc_dashboard.repo import reset_hxc_dashboard_fixture_state
from .hxc_dashboard.safe_mode import reset_hxc_safe_mode_fixture_state
from .identity_contact.api import router as identity_router
from .identity_contact.sidebar_jssdk import router as sidebar_jssdk_router
from .integration_gateway.wecom_jssdk_adapter import reset_sidebar_jssdk_attempts
from .integration_gateway.api import router as mcp_router
from .media_library.admin_pages import router as media_library_admin_pages_router
from .media_library.api import router as media_library_router
from .media_library.repo import reset_media_library_fixture_state
from .message_archive.api import router as message_archive_router
from .ops_enrollment.application import reset_user_ops_fixture_state
from .ops_enrollment.api import router as user_ops_router
from .owner_migration.api import router as owner_migration_router
from .platform_foundation.api import router as platform_router
from .post_legacy_deferred.api import router as post_legacy_deferred_router
from .post_legacy_deferred import reset_post_legacy_deferred_fixture_state
from .public_product.api import router as public_product_router
from .questionnaire.admin_pages import router as questionnaire_admin_pages_router
from .questionnaire.api import router as questionnaire_router
from .send_content.api import router as send_content_router
from .radar_links.api import router as radar_links_router
from .radar_links.admin_pages import router as radar_links_admin_pages_router
from .radar_links.repo import reset_radar_links_fixture_state
from .sidebar_write.api import router as sidebar_write_router
from .sidebar_write import reset_sidebar_write_fixture_state
from .shared.repository_provider import RepositoryProviderError
from .shared.runtime import fixture_mode
from .questionnaire.repo import reset_questionnaire_fixture_state
from .questionnaire.admin_write import reset_questionnaire_admin_write_fixture_state
from .questionnaire.h5_write import reset_questionnaire_h5_write_fixture_state

_FRONTEND_COMPAT_DIR = Path(__file__).resolve().parent / "frontend_compat"
_GROUP_OPS_DIR = Path(__file__).resolve().parent / "automation_engine" / "group_ops"
_AUTOMATION_ENGINE_DIR = Path(__file__).resolve().parent / "automation_engine"
_CUSTOMER_TAGS_DIR = Path(__file__).resolve().parent / "customer_tags"


def create_app() -> FastAPI:
    app = FastAPI(title="AI-CRM Next", version="0.1.0")

    if fixture_mode():
        reset_user_ops_fixture_state()
        reset_questionnaire_fixture_state()
        reset_questionnaire_h5_write_fixture_state()
        reset_automation_fixture_state()
        reset_customer_webhook_fixture_state()
        reset_member_actions_fixture_state()
        reset_group_ops_fixture_state()
        reset_commerce_fixture_state()
        reset_media_library_fixture_state()
        reset_admin_jobs_fixture_state()
        reset_hxc_dashboard_fixture_state()
        reset_hxc_safe_mode_fixture_state()
        reset_radar_links_fixture_state()
        reset_cloud_plan_fixture_state()
        reset_campaign_read_fixture_state()
        reset_campaign_write_fixture_state()
        reset_sidebar_write_fixture_state()
        reset_post_legacy_deferred_fixture_state()
        reset_admin_auth_fixture_state()
        reset_questionnaire_admin_write_fixture_state()
        reset_wecom_tag_write_fixture_state()
        reset_wecom_tag_live_mutation_fixture_state()
        reset_sidebar_jssdk_attempts()

    @app.exception_handler(RepositoryProviderError)
    async def repository_provider_error_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "fixture_repository_blocked_in_production",
                "detail": str(exc),
            },
        )

    @app.middleware("http")
    async def write_route_owner_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        response.headers.setdefault("X-AICRM-App", "ai_crm_next")
        response.headers.setdefault("X-AICRM-Release-SHA", os.getenv("AICRM_NEXT_RELEASE_SHA") or os.getenv("RELEASE_SHA") or "unknown")
        return response

    app.mount(
        "/static/group-ops",
        StaticFiles(directory=_GROUP_OPS_DIR / "static"),
        name="group_ops_static",
    )
    app.mount(
        "/static/automation-engine",
        StaticFiles(directory=_AUTOMATION_ENGINE_DIR / "static"),
        name="automation_engine_static",
    )
    app.mount(
        "/static/customer-tags",
        StaticFiles(directory=_CUSTOMER_TAGS_DIR / "static"),
        name="customer_tags_static",
    )
    app.mount(
        "/static",
        StaticFiles(directory=_FRONTEND_COMPAT_DIR / "static"),
        name="static",
    )
    app.include_router(platform_router)
    app.include_router(admin_auth_router)
    app.include_router(admin_shell_router)
    app.include_router(admin_config_router)
    app.include_router(post_legacy_deferred_router)
    app.include_router(common_operation_members_router)
    app.include_router(channel_entry_router)
    app.include_router(automation_channels_router)
    app.include_router(hxc_dashboard_router)
    app.include_router(public_product_router)
    app.include_router(sidebar_write_router)
    app.include_router(sidebar_jssdk_router)
    app.include_router(customer_tags_read_router)
    app.include_router(customer_tags_write_router)
    app.include_router(cloud_orchestrator_router)
    app.include_router(customer_router)
    app.include_router(customer_tags_router)
    app.include_router(user_ops_router)
    app.include_router(mcp_router)
    app.include_router(identity_router)
    app.include_router(message_archive_router)
    app.include_router(questionnaire_admin_pages_router)
    app.include_router(questionnaire_router)
    app.include_router(radar_links_admin_pages_router)
    app.include_router(radar_links_router)
    app.include_router(auth_wecom_router)
    app.include_router(group_ops_admin_pages_router)
    app.include_router(automation_admin_pages_router)
    app.include_router(channel_admin_pages_router)
    app.include_router(customer_tags_admin_pages_router)
    app.include_router(automation_router)
    app.include_router(commerce_router)
    app.include_router(media_library_router)
    app.include_router(media_library_admin_pages_router)
    app.include_router(ai_assist_router)
    app.include_router(send_content_router)
    app.include_router(admin_jobs_router)
    app.include_router(owner_migration_router)
    app.include_router(frontend_compat_router)
    return app


app = create_app()
