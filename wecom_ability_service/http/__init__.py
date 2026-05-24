from __future__ import annotations

from flask import Blueprint

from .admin_jobs import register_routes as register_admin_jobs_console_routes
from .admin_broadcast_jobs import register_routes as register_admin_broadcast_jobs_routes
from .admin_customers import register_routes as register_admin_customer_console_routes
from .admin_audit import register_routes as register_admin_audit_console_routes
from .admin_api_docs import register_routes as register_admin_api_docs_routes
from .admin_auth_routes import register_routes as register_admin_auth_routes
from .admin_mcp import register_routes as register_admin_mcp_console_routes
from .admin_operations import register_routes as register_admin_operations_console_routes
try:
    from .admin_questionnaire_console import register_routes as register_admin_questionnaire_console_routes
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for older file layout
    from .admin_questionnaires import register_routes as register_admin_questionnaire_console_routes
from .admin_questionnaire_push_logs import register_routes as register_admin_questionnaire_push_logs_routes
from .admin_config_api import register_routes as register_admin_config_api_routes
from .admin_config import register_routes as register_admin_config_routes
from .admin_config_login_access import register_routes as register_admin_config_login_access_routes
from .admin_config_marketing_automation import register_routes as register_admin_config_marketing_automation_routes
from .admin_console import register_routes as register_admin_console_routes
from .admin_dashboard import register_routes as register_admin_dashboard_routes
from .admin_class_user import register_routes as register_admin_class_user_routes
from .admin_hxc_dashboard import register_routes as register_admin_hxc_dashboard_routes
from .admin_questionnaires import register_routes as register_admin_questionnaires_routes
from .admin_user_ops import register_routes as register_admin_user_ops_routes
from .admin_user_ops_delivery import register_routes as register_admin_user_ops_delivery_routes
from .admin_wechat_pay import register_routes as register_admin_wechat_pay_routes
from .admin_wechat_pay_products import register_routes as register_admin_wechat_pay_products_routes
from .admin_wecom_tags import register_routes as register_admin_wecom_tags_routes
from .wecom_customer_acquisition import register_routes as register_wecom_customer_acquisition_routes
from .automation_conversion import register_routes as register_automation_conversion_routes
from .cloud_orchestrator_endpoint import register_routes as register_cloud_orchestrator_routes
from .miniprogram_library_endpoint import register_routes as register_miniprogram_library_routes
from .image_library_endpoint import register_routes as register_image_library_routes
from .attachment_library_endpoint import register_routes as register_attachment_library_routes
from .archive import register_routes as register_archive_routes
from .callbacks import register_routes as register_callback_routes
from .contacts import register_routes as register_contacts_routes
from .customer_center import register_routes as register_customer_center_routes
from .customer_automation import register_routes as register_customer_automation_routes
from .customer_timeline import register_routes as register_customer_timeline_routes
from .group_chats import register_routes as register_group_chat_routes
from .identity import register_routes as register_identity_routes
from .ops import register_routes as register_ops_routes
from .public_questionnaire_oauth import register_routes as register_public_questionnaire_oauth_routes
from .public_questionnaires import register_routes as register_public_questionnaire_routes
from .public_questionnaire_diagnostics import register_routes as register_public_questionnaire_diagnostics_routes
from .wechat_pay import register_routes as register_wechat_pay_routes
from .settings_ops import register_routes as register_settings_routes
from .sidebar import register_routes as register_sidebar_routes
from .sidebar_v2 import register_routes as register_sidebar_v2_routes
from .sidebar_marketing import register_routes as register_sidebar_marketing_routes
from .setup_wizard import register_routes as register_setup_wizard_routes
from .system_health import register_routes as register_system_health_routes
from .tags import register_routes as register_tag_routes
from .tasks import register_routes as register_task_routes

HTTP_CONTROLLER_RULES = (
    "controller only parses request input, validates/coerces primitives, delegates to services/runtime helpers, and builds responses",
    "controller must not execute raw SQL directly",
    "controller must not call third-party HTTP APIs directly",
    "controller must not implement complex business rules or job orchestration inline",
)

HTTP_ROUTE_MODULES = {
    "sidebar": "wecom_ability_service.http.sidebar",
    "sidebar_v2": "wecom_ability_service.http.sidebar_v2",
    "sidebar_lead_pool": "wecom_ability_service.http.sidebar_lead_pool",
    "identity": "wecom_ability_service.http.identity",
    "ops": "wecom_ability_service.http.ops",
    "settings": "wecom_ability_service.http.settings_ops",
    "admin_auth_routes": "wecom_ability_service.http.admin_auth_routes",
    "internal_auth": "wecom_ability_service.http.internal_auth",
    "sidebar_marketing": "wecom_ability_service.http.sidebar_marketing",
    "customer_center": "wecom_ability_service.http.customer_center",
    "customer_automation": "wecom_ability_service.http.customer_automation",
    "automation_conversion": "wecom_ability_service.http.automation_conversion",
    "automation_conversion_channels": "wecom_ability_service.http.automation_conversion_channels",
    "automation_conversion_agent_page_actions": "wecom_ability_service.http.automation_conversion_agent_page_actions",
    "automation_conversion_auto_reply_actions": "wecom_ability_service.http.automation_conversion_auto_reply_actions",
    "automation_conversion_agent_api": "wecom_ability_service.http.automation_conversion_agent_api",
    "automation_conversion_delivery": "wecom_ability_service.http.automation_conversion_delivery",
    "automation_conversion_member_api": "wecom_ability_service.http.automation_conversion_member_api",
    "automation_conversion_operation_tasks": "wecom_ability_service.http.automation_conversion_operation_tasks",
    "automation_conversion_page_actions": "wecom_ability_service.http.automation_conversion_page_actions",
    "automation_conversion_pages": "wecom_ability_service.http.automation_conversion_pages",
    "automation_conversion_review": "wecom_ability_service.http.automation_conversion_review",
    "automation_conversion_runtime_api": "wecom_ability_service.http.automation_conversion_runtime_api",
    "automation_conversion_router_callback_api": "wecom_ability_service.http.automation_conversion_router_callback_api",
    "automation_conversion_segments": "wecom_ability_service.http.automation_conversion_segments",
    "automation_conversion_settings": "wecom_ability_service.http.automation_conversion_settings",
    "automation_conversion_setup": "wecom_ability_service.http.automation_conversion_setup",
    "automation_conversion_templates": "wecom_ability_service.http.automation_conversion_templates",
    "automation_conversion_workflows": "wecom_ability_service.http.automation_conversion_workflows",
    "customer_timeline": "wecom_ability_service.http.customer_timeline",
    "archive": "wecom_ability_service.http.archive",
    "contacts": "wecom_ability_service.http.contacts",
    "group_chats": "wecom_ability_service.http.group_chats",
    "callbacks": "wecom_ability_service.http.callbacks",
    "tasks": "wecom_ability_service.http.tasks",
    "tags": "wecom_ability_service.http.tags",
    "admin_console": "wecom_ability_service.http.admin_console",
    "admin_broadcast_jobs": "wecom_ability_service.http.admin_broadcast_jobs",
    "admin_jobs": "wecom_ability_service.http.admin_jobs",
    "admin_audit": "wecom_ability_service.http.admin_audit",
    "admin_api_docs": "wecom_ability_service.http.admin_api_docs",
    "admin_customers": "wecom_ability_service.http.admin_customers",
    "admin_mcp": "wecom_ability_service.http.admin_mcp",
    "admin_operations": "wecom_ability_service.http.admin_operations",
    "admin_questionnaire_console": "wecom_ability_service.http.admin_questionnaire_console",
    "admin_questionnaire_push_logs": "wecom_ability_service.http.admin_questionnaire_push_logs",
    "admin_config": "wecom_ability_service.http.admin_config",
    "admin_config_api": "wecom_ability_service.http.admin_config_api",
    "admin_config_login_access": "wecom_ability_service.http.admin_config_login_access",
    "admin_config_marketing_automation": "wecom_ability_service.http.admin_config_marketing_automation",
    "admin_dashboard": "wecom_ability_service.http.admin_dashboard",
    "admin_hxc_dashboard": "wecom_ability_service.http.admin_hxc_dashboard",
    "admin_user_ops": "wecom_ability_service.http.admin_user_ops",
    "admin_user_ops_delivery": "wecom_ability_service.http.admin_user_ops_delivery",
    "admin_wechat_pay": "wecom_ability_service.http.admin_wechat_pay",
    "admin_wechat_pay_products": "wecom_ability_service.http.admin_wechat_pay_products",
    "admin_class_user": "wecom_ability_service.http.admin_class_user",
    "admin_questionnaires": "wecom_ability_service.http.admin_questionnaires",
    "admin_wecom_tags": "wecom_ability_service.http.admin_wecom_tags",
    "wecom_customer_acquisition": "wecom_ability_service.http.wecom_customer_acquisition",
    "cloud_orchestrator": "wecom_ability_service.http.cloud_orchestrator_endpoint",
    "cloud_orchestrator_campaigns": "wecom_ability_service.http.cloud_orchestrator_campaigns",
    "cloud_orchestrator_campaign_details": "wecom_ability_service.http.cloud_orchestrator_campaign_details",
    "cloud_orchestrator_media": "wecom_ability_service.http.cloud_orchestrator_media",
    "cloud_orchestrator_pages": "wecom_ability_service.http.cloud_orchestrator_pages",
    "cloud_orchestrator_plans": "wecom_ability_service.http.cloud_orchestrator_plans",
    "cloud_orchestrator_segments": "wecom_ability_service.http.cloud_orchestrator_segments",
    "image_library_create": "wecom_ability_service.http.image_library_create",
    "image_library": "wecom_ability_service.http.image_library_endpoint",
    "attachment_library": "wecom_ability_service.http.attachment_library_endpoint",
    "miniprogram_library": "wecom_ability_service.http.miniprogram_library_endpoint",
    "public_questionnaire_oauth": "wecom_ability_service.http.public_questionnaire_oauth",
    "public_questionnaire_diagnostics": "wecom_ability_service.http.public_questionnaire_diagnostics",
    "public_questionnaires": "wecom_ability_service.http.public_questionnaires",
    "wechat_pay": "wecom_ability_service.http.wechat_pay",
    "setup_wizard": "wecom_ability_service.http.setup_wizard",
    "system_health": "wecom_ability_service.http.system_health",
}

HTTP_ROUTE_PLACEMENT = {
    "customer": (
        "sidebar.py for /sidebar/* contact binding, signup-tag, and JSSDK endpoints",
        "sidebar_v2.py for /api/sidebar/v2* customer workbench APIs",
        "sidebar_lead_pool.py for /api/sidebar/lead-pool* user-ops handlers registered by sidebar.py",
        "sidebar_marketing.py for /api/sidebar/marketing-status* automation-engine handlers",
        "customer_center.py for /api/customers* list/detail",
        "customer_automation.py for /api/customers/automation/signup-conversion/batches*",
        "customer_timeline.py for /api/customers/<external_userid>/timeline",
        "contacts.py and identity.py for contact binding / identity resolution",
        "archive.py for archive health/sync and /api/messages* customer conversation history endpoints",
        "group_chats.py for /api/group-chats* sync controllers",
        "tasks.py for /api/tasks* outbound WeCom task dispatch controllers",
        "public_questionnaires.py for /s/* questionnaire H5 pages, submit/result APIs, diagnostics, and debug session endpoint",
        "public_questionnaire_oauth.py for public questionnaire WeChat OAuth start/callback handlers",
        "public_questionnaire_diagnostics.py for public questionnaire client diagnostics and debug session endpoint",
    ),
    "admin": (
        "admin_console.py for /admin home, shell helpers, and legacy shell embeds",
        "admin_auth_routes.py for /login, /logout, and /auth/wecom/* login controllers",
        "internal_auth.py for session auth, RBAC guard, and old-page sunset interception",
        "admin_broadcast_jobs.py for broadcast job queue page and /api/admin/broadcast-jobs* controllers",
        "admin_jobs.py for /admin/jobs and confirmed sync/task actions",
        "admin_audit.py for /admin/audit governance page and /api/admin/audit/logs",
        "admin_customers.py for /admin/customers* pages and customer detail actions",
        "admin_api_docs.py for /admin/api-docs human-readable API documentation",
        "admin_mcp.py for legacy /admin/mcp compatibility redirect only",
        "admin_operations.py for /admin/user-ops, /admin/class-users, and confirmed operations actions",
        "admin_questionnaire_console.py for /admin/questionnaires* shell and editor pages",
        "admin_questionnaire_push_logs.py for /admin/questionnaires* external-push-log list and retry handlers",
        "admin_config.py for /admin/config* pages and form action controllers",
        "admin_config_api.py for /api/admin/config* JSON controllers",
        "admin_config_login_access.py for /admin/config/login-access* pages and account-management actions",
        "admin_config_marketing_automation.py for /admin/marketing-automation* and signup-conversion config compatibility APIs",
        "admin_hxc_dashboard.py for Huangxiaocan dashboard pages",
        "automation_conversion.py for /admin/automation-conversion* and /api/admin/automation-conversion*",
        "automation_conversion_channels.py for channel center, channel binding, admission logs, and entry-channel member summaries registered by automation_conversion.py",
        "automation_conversion_agent_page_actions.py for agent orchestration page form actions registered by automation_conversion.py",
        "automation_conversion_auto_reply_actions.py for auto-reply monitor page actions registered by automation_conversion.py",
        "automation_conversion_agent_api.py for agent outputs, agent config, and router callback JSON handlers registered by automation_conversion.py",
        "automation_conversion_delivery.py for focus-send and SOP v1 delivery handlers registered by automation_conversion.py",
        "automation_conversion_member_api.py for member actions and manual-send JSON handlers registered by automation_conversion.py",
        "automation_conversion_operation_tasks.py for operation-task group, task CRUD, preview, and due-runner handlers registered by automation_conversion.py",
        "automation_conversion_page_actions.py for automation program form actions registered by automation_conversion.py",
        "automation_conversion_pages.py for automation program pages, shared page entries, and program CRUD form handlers registered by automation_conversion.py",
        "automation_conversion_review.py for auto-reply review-output handlers registered by automation_conversion.py",
        "automation_conversion_runtime_api.py for internal runtime triggers and callback endpoints registered by automation_conversion.py",
        "automation_conversion_router_callback_api.py for router callback replay/check handlers registered by automation_conversion.py",
        "automation_conversion_segments.py for member segment search and filtered broadcast handlers registered by automation_conversion.py",
        "automation_conversion_settings.py for default channel, settings, and model-infra JSON handlers registered by automation_conversion.py",
        "automation_conversion_setup.py for program setup and publish JSON handlers registered by automation_conversion.py",
        "automation_conversion_templates.py for action templates and profile-segment template handlers registered by automation_conversion.py",
        "automation_conversion_workflows.py for workflow model, node, dashboard, and execution-record handlers registered by automation_conversion.py",
        "admin_dashboard.py for /api/admin/dashboard/* shell status",
        "admin_user_ops.py for /api/admin/user-ops* lead-pool list/import/maintenance APIs and /admin/user-ops/ui",
        "admin_user_ops_delivery.py for /api/admin/user-ops/do-not-disturb, batch-send, and send-record APIs",
        "admin_class_user.py for /api/admin/class-user-management*",
        "admin_questionnaires.py for /api/admin/questionnaires* and /admin/questionnaires/ui",
        "admin_wecom_tags.py for /api/admin/wecom/tags* enterprise customer tag management",
        "admin_wechat_pay.py for /admin/wechat-pay/transactions* and /api/admin/wechat-pay* transaction management",
        "admin_wechat_pay_products.py for /admin/wechat-pay/products* and /api/admin/wechat-pay/products* product management",
        "wecom_customer_acquisition.py for /api/admin/wecom-customer-acquisition-links* and /admin/wecom-customer-acquisition-links/ui",
        "cloud_orchestrator_endpoint.py for /admin/cloud-orchestrator* and /api/admin/cloud-orchestrator* route aggregation",
        "cloud_orchestrator_campaigns.py for Cloud Orchestrator campaign JSON handlers registered by cloud_orchestrator_endpoint.py",
        "cloud_orchestrator_campaign_details.py for Cloud Orchestrator campaign member and step handlers registered by cloud_orchestrator_endpoint.py",
        "cloud_orchestrator_pages.py for Cloud Orchestrator admin page render handlers registered by cloud_orchestrator_endpoint.py",
        "cloud_orchestrator_media.py for Cloud Orchestrator media upload handlers registered by cloud_orchestrator_endpoint.py",
        "cloud_orchestrator_plans.py for Cloud Orchestrator plan, audit, and observability handlers registered by cloud_orchestrator_endpoint.py",
        "cloud_orchestrator_segments.py for Cloud Orchestrator segment handlers registered by cloud_orchestrator_endpoint.py",
        "image_library_create.py for /api/admin/image-library upload/from-url/from-base64 handlers registered by image_library_endpoint.py",
        "image_library_endpoint.py for /admin/image-library and /api/admin/image-library* controllers",
        "attachment_library_endpoint.py for /admin/attachment-library and /api/admin/attachment-library*",
        "miniprogram_library_endpoint.py for /admin/miniprogram-library and /api/admin/miniprogram-library* controllers",
        "wechat_pay.py for WeChat-internal H5 JSAPI checkout, order status, OAuth, and notify callbacks",
    ),
    "callbacks": (
        "callbacks.py for callback controllers only",
        "callback_runtime.py for callback auth/decrypt/dispatch runtime",
        "background_jobs.py for async task dispatch and callback background handlers",
    ),
    "ops_settings": (
        "ops.py for /health, /archive/messages, /api/init-db, /api/ops/status",
        "settings_ops.py for /api/settings",
        "system_health.py for /api/system/health and /api/system/compensate",
        "setup_wizard.py for /setup/wizard and /admin/config/checklist",
    ),
}

HTTP_ROUTE_REGISTRARS = (
    ("sidebar", register_sidebar_routes),
    ("sidebar_v2", register_sidebar_v2_routes),
    ("sidebar_marketing", register_sidebar_marketing_routes),
    ("identity", register_identity_routes),
    ("ops", register_ops_routes),
    ("settings", register_settings_routes),
    ("admin_auth_routes", register_admin_auth_routes),
    ("admin_console", register_admin_console_routes),
    ("admin_api_docs", register_admin_api_docs_routes),
    ("admin_broadcast_jobs", register_admin_broadcast_jobs_routes),
    ("admin_jobs", register_admin_jobs_console_routes),
    ("admin_audit", register_admin_audit_console_routes),
    ("admin_customers", register_admin_customer_console_routes),
    ("admin_mcp", register_admin_mcp_console_routes),
    ("admin_operations", register_admin_operations_console_routes),
    ("admin_questionnaire_console", register_admin_questionnaire_console_routes),
    ("admin_questionnaire_push_logs", register_admin_questionnaire_push_logs_routes),
    ("admin_config", register_admin_config_routes),
    ("admin_config_api", register_admin_config_api_routes),
    ("admin_config_login_access", register_admin_config_login_access_routes),
    ("admin_config_marketing_automation", register_admin_config_marketing_automation_routes),
    ("admin_dashboard", register_admin_dashboard_routes),
    ("admin_user_ops", register_admin_user_ops_routes),
    ("admin_user_ops_delivery", register_admin_user_ops_delivery_routes),
    ("admin_hxc_dashboard", register_admin_hxc_dashboard_routes),
    ("admin_class_user", register_admin_class_user_routes),
    ("admin_wechat_pay", register_admin_wechat_pay_routes),
    ("admin_wechat_pay_products", register_admin_wechat_pay_products_routes),
    ("admin_wecom_tags", register_admin_wecom_tags_routes),
    ("wecom_customer_acquisition", register_wecom_customer_acquisition_routes),
    ("admin_questionnaires", register_admin_questionnaires_routes),
    ("automation_conversion", register_automation_conversion_routes),
    ("cloud_orchestrator", register_cloud_orchestrator_routes),
    ("miniprogram_library", register_miniprogram_library_routes),
    ("image_library", register_image_library_routes),
    ("attachment_library", register_attachment_library_routes),
    ("customer_center", register_customer_center_routes),
    ("customer_automation", register_customer_automation_routes),
    ("customer_timeline", register_customer_timeline_routes),
    ("public_questionnaires", register_public_questionnaire_routes),
    ("public_questionnaire_diagnostics", register_public_questionnaire_diagnostics_routes),
    ("public_questionnaire_oauth", register_public_questionnaire_oauth_routes),
    ("wechat_pay", register_wechat_pay_routes),
    ("archive", register_archive_routes),
    ("contacts", register_contacts_routes),
    ("group_chats", register_group_chat_routes),
    ("callbacks", register_callback_routes),
    ("tasks", register_task_routes),
    ("tags", register_tag_routes),
    ("system_health", register_system_health_routes),
    ("setup_wizard", register_setup_wizard_routes),
)


def register_http_routes(bp: Blueprint) -> Blueprint:
    for _, register_routes in HTTP_ROUTE_REGISTRARS:
        register_routes(bp)
    return bp


def create_http_blueprint() -> Blueprint:
    bp = Blueprint("api", __name__)
    return register_http_routes(bp)


bp = create_http_blueprint()

__all__ = [
    "HTTP_CONTROLLER_RULES",
    "HTTP_ROUTE_MODULES",
    "HTTP_ROUTE_PLACEMENT",
    "HTTP_ROUTE_REGISTRARS",
    "bp",
    "create_http_blueprint",
    "register_http_routes",
]
