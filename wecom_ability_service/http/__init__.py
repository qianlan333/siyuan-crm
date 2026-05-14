from __future__ import annotations

from flask import Blueprint

from .admin_jobs import register_routes as register_admin_jobs_console_routes
from .admin_customers import register_routes as register_admin_customer_console_routes
from .admin_audit import register_routes as register_admin_audit_console_routes
from .admin_api_docs import register_routes as register_admin_api_docs_routes
from .internal_auth import register_routes as register_internal_auth_routes
from .admin_mcp import register_routes as register_admin_mcp_console_routes
from .admin_operations import register_routes as register_admin_operations_console_routes
try:
    from .admin_questionnaire_console import register_routes as register_admin_questionnaire_console_routes
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for older file layout
    from .admin_questionnaires import register_routes as register_admin_questionnaire_console_routes
from .admin_config import register_routes as register_admin_config_routes
from .admin_console import register_routes as register_admin_console_routes
from .admin_dashboard import register_routes as register_admin_dashboard_routes
from .admin_class_user import register_routes as register_admin_class_user_routes
from .admin_hxc_dashboard import register_routes as register_admin_hxc_dashboard_routes
from .admin_questionnaires import register_routes as register_admin_questionnaires_routes
from .admin_user_ops import register_routes as register_admin_user_ops_routes
from .automation_conversion import register_routes as register_automation_conversion_routes
from .cloud_orchestrator_endpoint import register_routes as register_cloud_orchestrator_routes
from .miniprogram_library_endpoint import register_routes as register_miniprogram_library_routes
from .image_library_endpoint import register_routes as register_image_library_routes
from .archive import register_routes as register_archive_routes
from .callbacks import register_routes as register_callback_routes
from .contacts import register_routes as register_contacts_routes
from .customer_center import register_routes as register_customer_center_routes
from .customer_automation import register_routes as register_customer_automation_routes
from .customer_timeline import register_routes as register_customer_timeline_routes
from .group_chats import register_routes as register_group_chat_routes
from .identity import register_routes as register_identity_routes
from .ops import register_routes as register_ops_routes
from .public_questionnaires import register_routes as register_public_questionnaire_routes
from .settings_ops import register_routes as register_settings_routes
from .sidebar import register_routes as register_sidebar_routes
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
    "identity": "wecom_ability_service.http.identity",
    "ops": "wecom_ability_service.http.ops",
    "settings": "wecom_ability_service.http.settings_ops",
    "internal_auth": "wecom_ability_service.http.internal_auth",
    "customer_center": "wecom_ability_service.http.customer_center",
    "customer_automation": "wecom_ability_service.http.customer_automation",
    "automation_conversion": "wecom_ability_service.http.automation_conversion",
    "customer_timeline": "wecom_ability_service.http.customer_timeline",
    "archive": "wecom_ability_service.http.archive",
    "contacts": "wecom_ability_service.http.contacts",
    "group_chats": "wecom_ability_service.http.group_chats",
    "callbacks": "wecom_ability_service.http.callbacks",
    "tasks": "wecom_ability_service.http.tasks",
    "tags": "wecom_ability_service.http.tags",
    "admin_console": "wecom_ability_service.http.admin_console",
    "admin_jobs": "wecom_ability_service.http.admin_jobs",
    "admin_audit": "wecom_ability_service.http.admin_audit",
    "admin_api_docs": "wecom_ability_service.http.admin_api_docs",
    "admin_customers": "wecom_ability_service.http.admin_customers",
    "admin_mcp": "wecom_ability_service.http.admin_mcp",
    "admin_operations": "wecom_ability_service.http.admin_operations",
    "admin_questionnaire_console": "wecom_ability_service.http.admin_questionnaire_console",
    "admin_config": "wecom_ability_service.http.admin_config",
    "admin_dashboard": "wecom_ability_service.http.admin_dashboard",
    "admin_user_ops": "wecom_ability_service.http.admin_user_ops",
    "admin_class_user": "wecom_ability_service.http.admin_class_user",
    "admin_questionnaires": "wecom_ability_service.http.admin_questionnaires",
    "public_questionnaires": "wecom_ability_service.http.public_questionnaires",
    "setup_wizard": "wecom_ability_service.http.setup_wizard",
    "system_health": "wecom_ability_service.http.system_health",
}

HTTP_ROUTE_PLACEMENT = {
    "customer": (
        "customer_center.py for /api/customers* list/detail",
        "customer_automation.py for /api/customers/automation/signup-conversion/batches*",
        "customer_timeline.py for /api/customers/<external_userid>/timeline",
        "contacts.py and identity.py for contact binding / identity resolution",
    ),
    "admin": (
        "admin_console.py for /admin home, shell helpers, and legacy shell embeds",
        "internal_auth.py for /login, /logout, /auth/wecom/*, session auth, RBAC guard, and old-page sunset interception",
        "admin_jobs.py for /admin/jobs and confirmed sync/task actions",
        "admin_audit.py for /admin/audit governance page and /api/admin/audit/logs",
        "admin_customers.py for /admin/customers* pages and customer detail actions",
        "admin_api_docs.py for /admin/api-docs human-readable API documentation",
        "admin_mcp.py for legacy /admin/mcp compatibility redirect only",
        "admin_operations.py for /admin/user-ops, /admin/class-users, and confirmed operations actions",
        "admin_questionnaire_console.py for /admin/questionnaires* shell pages",
        "admin_config.py for /admin/config* pages and /api/admin/config* controllers",
        "automation_conversion.py for /admin/automation-conversion* and /api/admin/automation-conversion*",
        "admin_dashboard.py for /api/admin/dashboard/* shell status",
        "admin_user_ops.py for /api/admin/user-ops* and /admin/user-ops/ui",
        "admin_class_user.py for /api/admin/class-user-management*",
        "admin_questionnaires.py for /api/admin/questionnaires* and /admin/questionnaires/ui",
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
    ("identity", register_identity_routes),
    ("ops", register_ops_routes),
    ("settings", register_settings_routes),
    ("internal_auth", register_internal_auth_routes),
    ("admin_console", register_admin_console_routes),
    ("admin_api_docs", register_admin_api_docs_routes),
    ("admin_jobs", register_admin_jobs_console_routes),
    ("admin_audit", register_admin_audit_console_routes),
    ("admin_customers", register_admin_customer_console_routes),
    ("admin_mcp", register_admin_mcp_console_routes),
    ("admin_operations", register_admin_operations_console_routes),
    ("admin_questionnaire_console", register_admin_questionnaire_console_routes),
    ("admin_config", register_admin_config_routes),
    ("admin_dashboard", register_admin_dashboard_routes),
    ("admin_user_ops", register_admin_user_ops_routes),
    ("admin_hxc_dashboard", register_admin_hxc_dashboard_routes),
    ("admin_class_user", register_admin_class_user_routes),
    ("admin_questionnaires", register_admin_questionnaires_routes),
    ("automation_conversion", register_automation_conversion_routes),
    ("cloud_orchestrator", register_cloud_orchestrator_routes),
    ("miniprogram_library", register_miniprogram_library_routes),
    ("image_library", register_image_library_routes),
    ("customer_center", register_customer_center_routes),
    ("customer_automation", register_customer_automation_routes),
    ("customer_timeline", register_customer_timeline_routes),
    ("public_questionnaires", register_public_questionnaire_routes),
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
