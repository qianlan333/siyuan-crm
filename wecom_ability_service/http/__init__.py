from __future__ import annotations

from flask import Blueprint

from .admin_jobs import register_routes as register_admin_jobs_console_routes
from .admin_broadcast_jobs import register_routes as register_admin_broadcast_jobs_routes
from .admin_customers import register_routes as register_admin_customer_console_routes
from .admin_audit import register_routes as register_admin_audit_console_routes
from .admin_api_docs import register_routes as register_admin_api_docs_routes
from .admin_mcp import register_routes as register_admin_mcp_console_routes
from .admin_operations import register_routes as register_admin_operations_console_routes
try:
    from .admin_questionnaire_console import register_routes as register_admin_questionnaire_console_routes
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for older file layout
    from .admin_questionnaires import register_routes as register_admin_questionnaire_console_routes
from .admin_config_api import register_routes as register_admin_config_api_routes
from .admin_config import register_routes as register_admin_config_routes
from .admin_config_login_access import register_routes as register_admin_config_login_access_routes
from .admin_config_marketing_automation import register_routes as register_admin_config_marketing_automation_routes
from .admin_console import register_routes as register_admin_console_routes
from .admin_dashboard import register_routes as register_admin_dashboard_routes
from .admin_class_user import register_routes as register_admin_class_user_routes
from .image_library_upload import register_routes as register_image_library_upload_routes
from .admin_questionnaires import register_routes as register_admin_questionnaires_routes
from .admin_alipay_pay import register_routes as register_admin_alipay_pay_routes
from .admin_wechat_pay import register_routes as register_admin_wechat_pay_routes
from .admin_wecom_tags import register_routes as register_admin_wecom_tags_routes
from .common_operation_members import register_routes as register_common_operation_members_routes
from .wecom_customer_acquisition import register_routes as register_wecom_customer_acquisition_routes
from .automation_conversion import register_routes as register_automation_conversion_routes
from .archive import register_routes as register_archive_routes
from .callbacks import register_routes as register_callback_routes
from .contacts import register_routes as register_contacts_routes
from .customer_automation import register_routes as register_customer_automation_routes
from .group_chats import register_routes as register_group_chat_routes
from .identity import register_routes as register_identity_routes
from .ops import register_routes as register_ops_routes
from .public_questionnaire_oauth import register_routes as register_public_questionnaire_oauth_routes
from .public_questionnaires import register_routes as register_public_questionnaire_routes
from .public_questionnaire_diagnostics import register_routes as register_public_questionnaire_diagnostics_routes
from .alipay_pay import register_routes as register_alipay_pay_routes
from .wechat_pay import register_routes as register_wechat_pay_routes
from .settings_ops import register_routes as register_settings_routes
from .sidebar import register_routes as register_sidebar_routes
from .sidebar_v2 import register_routes as register_sidebar_v2_routes
from .sidebar_marketing import register_routes as register_sidebar_marketing_routes
from .setup_wizard import register_routes as register_setup_wizard_routes
from .system_health import register_routes as register_system_health_routes
from .tags import register_routes as register_tag_routes
from .tasks import register_routes as register_task_routes
from .internal_auth import register_routes as register_internal_auth_routes

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
    "internal_auth": "wecom_ability_service.http.internal_auth",
    "sidebar_marketing": "wecom_ability_service.http.sidebar_marketing",
    "customer_automation": "wecom_ability_service.http.customer_automation",
    "automation_conversion": "wecom_ability_service.http.automation_conversion",
    "automation_conversion_delivery": "wecom_ability_service.http.automation_conversion_delivery",
    "automation_conversion_member_api": "wecom_ability_service.http.automation_conversion_member_api",
    "automation_conversion_task_runtime": "wecom_ability_service.http.automation_conversion_task_runtime",
    "automation_conversion_runtime_api": "wecom_ability_service.http.automation_conversion_runtime_api",
    "automation_conversion_execution_outbound": "wecom_ability_service.http.automation_conversion_execution_outbound",
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
    "admin_config": "wecom_ability_service.http.admin_config",
    "admin_config_api": "wecom_ability_service.http.admin_config_api",
    "admin_config_login_access": "wecom_ability_service.http.admin_config_login_access",
    "admin_config_marketing_automation": "wecom_ability_service.http.admin_config_marketing_automation",
    "admin_dashboard": "wecom_ability_service.http.admin_dashboard",
    "admin_alipay_pay": "wecom_ability_service.http.admin_alipay_pay",
    "admin_wechat_pay": "wecom_ability_service.http.admin_wechat_pay",
    "admin_class_user": "wecom_ability_service.http.admin_class_user",
    "admin_questionnaires": "wecom_ability_service.http.admin_questionnaires",
    "admin_wecom_tags": "wecom_ability_service.http.admin_wecom_tags",
    "common_operation_members": "wecom_ability_service.http.common_operation_members",
    "wecom_customer_acquisition": "wecom_ability_service.http.wecom_customer_acquisition",
    "public_questionnaire_oauth": "wecom_ability_service.http.public_questionnaire_oauth",
    "public_questionnaire_diagnostics": "wecom_ability_service.http.public_questionnaire_diagnostics",
    "image_library_upload": "wecom_ability_service.http.image_library_upload",
    "public_questionnaires": "wecom_ability_service.http.public_questionnaires",
    "alipay_pay": "wecom_ability_service.http.alipay_pay",
    "wechat_pay": "wecom_ability_service.http.wechat_pay",
    "setup_wizard": "wecom_ability_service.http.setup_wizard",
    "system_health": "wecom_ability_service.http.system_health",
}

HTTP_ROUTE_PLACEMENT = {
    "customer": (
        "sidebar.py for /sidebar/* contact binding, signup-tag, and JSSDK endpoints",
        "sidebar_v2.py for /api/sidebar/v2* workbench, profile fields, materials, and lightweight read/write facades",
        "sidebar_lead_pool.py for /api/sidebar/lead-pool* user-ops handlers registered by sidebar.py",
        "sidebar_marketing.py for /api/sidebar/marketing-status* automation-engine handlers",
        "customer_automation.py for /api/customers/automation/signup-conversion/batches*",
        "D3 retired legacy customer read-model owner; AI-CRM Next owns /api/customers* and /api/customers/<external_userid>/timeline",
        "contacts.py and identity.py for contact binding / identity resolution",
        "archive.py for archive health/sync and /api/messages* customer conversation history endpoints",
        "group_chats.py for /api/group-chats* sync controllers",
        "tasks.py for /api/tasks* outbound WeCom task dispatch controllers",
        "public_questionnaires.py for legacy POST /api/h5/questionnaires/<slug>/submit fallback only; D5 retired public questionnaire readonly GET ownership",
        "public_questionnaire_oauth.py for public questionnaire WeChat OAuth start/callback handlers",
        "public_questionnaire_diagnostics.py for public questionnaire client diagnostics and debug session endpoint",
    ),
    "admin": (
        "admin_console.py for /admin home, shell helpers, and legacy shell embeds",
        "internal_auth.py for session auth, RBAC guard, and old-page sunset interception",
        "admin_broadcast_jobs.py for broadcast job queue page and /api/admin/broadcast-jobs* controllers",
        "admin_jobs.py for /admin/jobs and confirmed sync/task actions",
        "admin_audit.py for /admin/audit governance page and /api/admin/audit/logs",
        "admin_customers.py for customer profile APIs and legacy customer detail actions; D3 retired /admin/customers page ownership",
        "admin_api_docs.py for /admin/api-docs human-readable API documentation",
        "admin_mcp.py for legacy /admin/mcp compatibility redirect only",
        "admin_operations.py for /admin/user-ops, /admin/class-users, and confirmed operations actions",
        "admin_questionnaire_console.py for legacy questionnaire console POST save/toggle fallback only; D5 retired admin questionnaire readonly page ownership",
        "admin_config.py for /admin/config* pages and form action controllers",
        "admin_config_api.py for /api/admin/config* JSON controllers",
        "admin_config_login_access.py for /admin/config/login-access* pages and account-management actions",
        "admin_config_marketing_automation.py for /admin/marketing-automation* and signup-conversion config compatibility APIs",
        "image_library_upload.py for multipart /api/admin/image-library/upload used by product slices and image pickers",
        "automation_conversion.py for legacy automation write/external/runtime fallback only; D6 retired core Automation readonly page/API/alias GET ownership",
        "automation_conversion_delivery.py for focus-send and SOP v1 delivery handlers registered by automation_conversion.py",
        "automation_conversion_member_api.py for member actions and manual-send JSON handlers registered by automation_conversion.py",
        "automation_conversion_task_runtime.py for operation-task due-runner handlers registered by automation_conversion.py",
        "automation_conversion_runtime_api.py for internal runtime triggers and callback endpoints registered by automation_conversion.py",
        "automation_conversion_execution_outbound.py for execution-item outbound send handlers registered by automation_conversion.py",
        "aicrm_next.channel_entry.api owns channel runtime diagnosis, dry-run, and repair routes",
        "admin_dashboard.py for /api/admin/dashboard/* shell status",
        "admin_class_user.py for /api/admin/class-user-management*",
        "admin_questionnaires.py for legacy questionnaire admin write fallback only; D5 retired admin questionnaire readonly GET ownership",
        "admin_wecom_tags.py for /api/admin/wecom/tags* enterprise customer tag management",
        "common_operation_members.py for /api/admin/common/operation-members unified operation-member selector API",
        "admin_alipay_pay.py for /admin/alipay/transactions* and /api/admin/alipay* transaction reads and exports",
        "admin_wechat_pay.py for /admin/wechat-pay/transactions* and /api/admin/wechat-pay* transaction management",
        "wecom_customer_acquisition.py for /api/admin/wecom-customer-acquisition-links* and /admin/wecom-customer-acquisition-links/ui",
        "retired Cloud Orchestrator legacy HTTP handlers; current owner is aicrm_next.cloud_orchestrator and retained domain tests do not use Flask HTTP handlers",
        "alipay_pay.py for Alipay WAP checkout, order status, return display, and notify callbacks",
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
    ("internal_auth", register_internal_auth_routes),
    ("admin_console", register_admin_console_routes),
    ("admin_api_docs", register_admin_api_docs_routes),
    ("admin_broadcast_jobs", register_admin_broadcast_jobs_routes),
    ("admin_jobs", register_admin_jobs_console_routes),
    ("admin_audit", register_admin_audit_console_routes),
    ("admin_customers", register_admin_customer_console_routes),
    ("admin_mcp", register_admin_mcp_console_routes),
    ("admin_operations", register_admin_operations_console_routes),
    ("admin_questionnaire_console", register_admin_questionnaire_console_routes),
    ("admin_config", register_admin_config_routes),
    ("admin_config_api", register_admin_config_api_routes),
    ("admin_config_login_access", register_admin_config_login_access_routes),
    ("admin_config_marketing_automation", register_admin_config_marketing_automation_routes),
    ("admin_dashboard", register_admin_dashboard_routes),
    ("image_library_upload", register_image_library_upload_routes),
    ("admin_class_user", register_admin_class_user_routes),
    ("admin_alipay_pay", register_admin_alipay_pay_routes),
    ("admin_wechat_pay", register_admin_wechat_pay_routes),
    ("admin_wecom_tags", register_admin_wecom_tags_routes),
    ("common_operation_members", register_common_operation_members_routes),
    ("wecom_customer_acquisition", register_wecom_customer_acquisition_routes),
    ("admin_questionnaires", register_admin_questionnaires_routes),
    ("automation_conversion", register_automation_conversion_routes),
    ("customer_automation", register_customer_automation_routes),
    ("public_questionnaires", register_public_questionnaire_routes),
    ("public_questionnaire_diagnostics", register_public_questionnaire_diagnostics_routes),
    ("public_questionnaire_oauth", register_public_questionnaire_oauth_routes),
    ("alipay_pay", register_alipay_pay_routes),
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
