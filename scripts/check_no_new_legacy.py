#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report
from aicrm_next.platform_foundation.route_registry.service import RouteRegistryService

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv310",
    "__pycache__",
    "docs",
    "migrations",
    "tests",
    "tools",
    "skills",
    "experiments",
    "wecom_ability_service",
    "scripts",
}
LEGACY_IMPORT_ALLOWLIST = {
    Path("aicrm_next/frontend_compat/legacy_routes.py"),
}
WECOM_IMPORT_ALLOWLIST = set()
API_SIDE_EFFECT_ALLOWLIST = set()
SIDE_EFFECT_MARKERS = {
    "dispatch_wecom_task",
    "create_contact_way",
    "requests.post(",
    "requests.put(",
    "requests.patch(",
    "requests.delete(",
    "httpx.post(",
    "httpx.put(",
    "httpx.patch(",
    "httpx.delete(",
}
CUSTOMER_READ_ROLLBACK_FLAG = "CUSTOMER_READ_MODEL" + "_LEGACY_ROLLBACK_ENABLED"
PROD_COMPAT_ROUTER_NAME = "production_compat" + "_router"
PROD_COMPAT_WILDCARD_ROUTER_NAME = "production_compat" + "_wildcard_router"
PROD_COMPAT_INCLUDE = f"include_router({PROD_COMPAT_ROUTER_NAME})"
PROD_COMPAT_WILDCARD_INCLUDE = f"include_router({PROD_COMPAT_WILDCARD_ROUTER_NAME})"
MESSAGES_BROAD_WILDCARD = "/api/messages*"
MESSAGES_BROAD_WILDCARD_RUNTIME = "/api/messages/{path:path}"
SIDEBAR_READONLY_ROUTES = (
    "/api/sidebar/customer-context",
    "/api/sidebar/profile",
    "/api/sidebar/tags",
    "/api/sidebar/binding-status",
    "/api/sidebar/contact-binding-status",
    "/api/sidebar/lead-pool/status",
    "/api/sidebar/signup-tags/status",
    "/api/sidebar/marketing-status",
    "/api/sidebar/v2/workbench",
    "/api/sidebar/v2/questionnaires",
    "/api/sidebar/v2/materials",
    "/api/sidebar/v2/materials/image/{image_id}/thumbnail",
    "/api/sidebar/v2/other-staff-messages",
    "/api/sidebar/v2/products",
    "/api/sidebar/v2/orders",
)
SIDEBAR_WRITE_ROUTES = (
    "/api/sidebar/bind-mobile",
    "/api/sidebar/lead-pool/upsert-class-term",
    "/api/sidebar/signup-tags/mark",
    "/api/sidebar/marketing-status/set-followup-segment",
    "/api/sidebar/marketing-status/mark-enrolled",
    "/api/sidebar/marketing-status/unmark-enrolled",
    "/api/sidebar/v2/profile",
    "/api/sidebar/v2/materials/send",
)
SIDEBAR_JSSDK_ROUTE = "/api/sidebar/jssdk-config"
SIDEBAR_JSSDK_METHODS = ("GET", "HEAD", "OPTIONS")
USER_OPS_READONLY_ROUTES = (
    "/api/admin/user-ops/overview",
    "/api/admin/user-ops/cards",
    "/api/admin/user-ops/customers",
    "/api/admin/user-ops/customers/{external_userid}",
    "/api/admin/user-ops/customers/{external_userid}/timeline",
    "/api/admin/user-ops/filters",
    "/api/admin/user-ops/send-records",
)
USER_OPS_PREVIEW_ROUTES = (
    "/api/admin/user-ops/broadcast/preview",
    "/api/admin/user-ops/export/preview",
)
QUESTIONNAIRE_ADMIN_READ_ROUTES = (
    "/admin/questionnaires",
    "/admin/questionnaires/new",
    "/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires",
    "/api/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires/{questionnaire_id}/questions",
    "/api/admin/questionnaires/{questionnaire_id}/results",
    "/api/admin/questionnaires/{questionnaire_id}/submissions",
)
QUESTIONNAIRE_ADMIN_WRITE_ROUTES = (
    "/api/admin/questionnaires",
    "/api/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires/{questionnaire_id}/duplicate",
    "/api/admin/questionnaires/{questionnaire_id}/publish",
    "/api/admin/questionnaires/{questionnaire_id}/enable",
    "/api/admin/questionnaires/{questionnaire_id}/disable",
    "/api/admin/questionnaires/{questionnaire_id}/export/preview",
    "/api/admin/questionnaires/{questionnaire_id}/export",
)
QUESTIONNAIRE_H5_COMMAND_ROUTES = (
    "/api/h5/questionnaires/{slug}/submit",
    "/api/h5/questionnaires/{slug}/client-diagnostics",
)
QUESTIONNAIRE_OAUTH_EXACT_ROUTES = (
    "/api/h5/wechat/oauth/start",
    "/api/h5/wechat/oauth/callback",
)
QUESTIONNAIRE_OUT_OF_SCOPE_ROUTES = (
    "/api/h5/wechat/oauth*",
)
AUTH_WECOM_EXACT_ROUTES = (
    "/auth/wecom/start",
    "/auth/wecom/callback",
    "/auth/wecom/unknown",
    "/api/h5/wechat/oauth/unknown",
)
AUTH_WECOM_WILDCARD_ROUTES = (
    "/api/h5/wechat/oauth/{path:path}",
    "/auth/wecom/{path:path}",
)
AUTH_WECOM_WILDCARD_REGISTRY_ROUTES = (
    "/api/h5/wechat/oauth*",
    "/auth/wecom*",
)
WECOM_TAG_READ_ROUTES = (
    "/api/admin/wecom/tags",
    "/api/admin/wecom/tags/{tag_id}",
    "/api/admin/wecom/tag-groups",
    "/api/admin/wecom/tag-groups/{group_id}",
)
WECOM_TAG_FAMILY_ROUTES = (
    "/api/admin/wecom/tags*",
    "/api/admin/wecom/tag-groups*",
)
WECOM_TAG_WRITE_ROUTES = (
    ("/api/admin/wecom/tags", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tags/{tag_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
    ("/api/admin/wecom/tag-groups", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tag-groups/{group_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
)
WECOM_TAG_SYNC_ROUTES = (
    ("/api/admin/wecom/tags/sync", ("POST", "OPTIONS")),
    ("/api/admin/wecom/tags/sync-due", ("POST", "OPTIONS")),
)
WECOM_TAG_LIVE_MUTATION_ROUTES = (
    ("/api/admin/wecom/tags/live/gate", ("GET",), "next_native", "next_exact"),
    ("/api/admin/wecom/tags/live/mark", ("POST", "OPTIONS"), "next_command", "next_command"),
    ("/api/admin/wecom/tags/live/unmark", ("POST", "OPTIONS"), "next_command", "next_command"),
)
WECOM_TAG_LIVE_MUTATION_EXACT_ROUTES = {route for route, _methods, _owner, _behavior in WECOM_TAG_LIVE_MUTATION_ROUTES}
GROUP_OPS_ADMIN_PAGE_ROUTES = (
    "/admin/automation-conversion/group-ops/ui",
    "/admin/automation-conversion/group-ops/plans/{plan_id}",
    "/admin/automation-conversion/group-ops/groups/ui",
)
MEDIA_LIBRARY_PAGE_ROUTES = (
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
)
MEDIA_LIBRARY_API_PREFIXES = (
    "/api/admin/image-library",
    "/api/admin/attachment-library",
    "/api/admin/miniprogram-library",
)
MEDIA_LIBRARY_REGISTRY_FAMILIES = (
    ("media_library_admin_pages_family", "/admin/*-library", ("GET",), "next_native_page_shell", "none"),
    ("media_library_image_read_family", "/api/admin/image-library*", ("GET",), "next_native", "local"),
    ("media_library_image_command_family", "/api/admin/image-library*", ("POST", "PUT", "DELETE", "OPTIONS"), "next_storage_adapter", "local / fake / real_blocked"),
    ("media_library_attachment_read_family", "/api/admin/attachment-library*", ("GET",), "next_native", "local"),
    ("media_library_attachment_command_family", "/api/admin/attachment-library*", ("POST", "PUT", "DELETE", "OPTIONS"), "next_storage_adapter", "local / fake / real_blocked"),
    ("media_library_miniprogram_read_family", "/api/admin/miniprogram-library*", ("GET",), "next_native", "local"),
    ("media_library_miniprogram_command_family", "/api/admin/miniprogram-library*", ("POST", "PUT", "DELETE", "OPTIONS"), "next_storage_adapter", "local / fake / real_blocked"),
)
MEDIA_LIBRARY_MANIFEST_ROUTES = (
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
    "/api/admin/image-library*",
    "/api/admin/image-library/upload",
    "/api/admin/attachment-library*",
    "/api/admin/miniprogram-library*",
)
MEDIA_LIBRARY_DIRECT_EXTERNAL_MARKERS = {
    "requests.get(": "media_library_direct_http_client",
    "requests.post(": "media_library_direct_http_client",
    "httpx.": "media_library_direct_http_client",
    "boto3": "media_library_direct_storage_client",
    "upload_media": "media_library_direct_wecom_media_upload",
    "/media/upload": "media_library_direct_wecom_media_upload",
    "access_token": "media_library_direct_wecom_media_upload",
    "real_external_call_executed=True": "media_library_real_external_call_true",
    "real_external_call_executed = True": "media_library_real_external_call_true",
    '"real_external_call_executed": True': "media_library_real_external_call_true",
    "'real_external_call_executed': True": "media_library_real_external_call_true",
    "real_enabled default": "media_library_real_enabled_default",
    "default real_enabled": "media_library_real_enabled_default",
}
HXC_DASHBOARD_PAGE_ROUTES = (
    "/admin/hxc-dashboard",
    "/admin/hxc-send-config",
)
HXC_DASHBOARD_API_ROUTES = (
    "/api/admin/hxc-dashboard",
    "/api/admin/hxc-dashboard/refresh",
    "/api/admin/hxc-dashboard/refresh-directory",
    "/api/admin/hxc-dashboard/send-config",
    "/api/admin/hxc-dashboard/send-config/{sender_userid}",
    "/api/admin/hxc-dashboard/broadcast",
    "/api/admin/hxc-dashboard/{unknown_path}",
)
HXC_DASHBOARD_PRODUCTION_COMPAT_ROUTES = (
    "/admin/hxc-dashboard",
    "/admin/hxc-send-config",
    "/api/admin/hxc-dashboard",
    "/api/admin/hxc-dashboard/{path:path}",
)
HXC_DASHBOARD_REGISTRY_RECORDS = (
    "hxc_dashboard_admin_api_family",
    "hxc_dashboard_admin_pages_family",
    "hxc_dashboard_refresh_next_command",
    "hxc_dashboard_directory_sync_next_command",
    "hxc_dashboard_send_config_next_read",
    "hxc_dashboard_send_config_next_command",
    "hxc_dashboard_broadcast_next_command",
)
HXC_DASHBOARD_DIRECT_MARKERS = {
    "forward_to_legacy_flask": "hxc_dashboard_legacy_facade",
    "wecom_ability_service": "hxc_dashboard_legacy_import",
    "refresh_hxc_dashboard_snapshot": "hxc_dashboard_legacy_refresh",
    "sync_admin_wecom_directory_members": "hxc_dashboard_legacy_directory_sync",
    "broadcast_to_filtered_users": "hxc_dashboard_legacy_broadcast",
    "requests.": "hxc_dashboard_direct_http_client",
    "httpx": "hxc_dashboard_direct_http_client",
    "OpenClaw": "hxc_dashboard_direct_openclaw_client",
    "WeComClient": "hxc_dashboard_direct_wecom_client",
    "access_token": "hxc_dashboard_direct_access_token",
}
HXC_DASHBOARD_TRUE_MARKERS = {
    '"fallback_used": True': "hxc_dashboard_fallback_true",
    "'fallback_used': True": "hxc_dashboard_fallback_true",
    '"real_external_call_executed": True': "hxc_dashboard_real_external_call_true",
    "'real_external_call_executed': True": "hxc_dashboard_real_external_call_true",
    '"hxc_refresh_executed": True': "hxc_dashboard_refresh_true",
    "'hxc_refresh_executed': True": "hxc_dashboard_refresh_true",
    '"directory_sync_executed": True': "hxc_dashboard_directory_sync_true",
    "'directory_sync_executed': True": "hxc_dashboard_directory_sync_true",
    '"hxc_broadcast_executed": True': "hxc_dashboard_broadcast_true",
    "'hxc_broadcast_executed': True": "hxc_dashboard_broadcast_true",
    '"wecom_send_executed": True': "hxc_dashboard_wecom_send_true",
    "'wecom_send_executed': True": "hxc_dashboard_wecom_send_true",
    '"wecom_api_called": True': "hxc_dashboard_wecom_api_true",
    "'wecom_api_called': True": "hxc_dashboard_wecom_api_true",
}
ADMIN_AUTH_LOGIN_ROUTES = ("/login", "/logout")
ADMIN_AUTH_LOGIN_REGISTRY_RECORDS = ("frontend_compat_auth_pages", "frontend_compat_logout_pages")
ADMIN_AUTH_LOGIN_DIRECT_MARKERS = {
    "forward_to_legacy_flask": "admin_auth_legacy_forward",
    "legacy_flask_facade": "admin_auth_legacy_facade",
    "admin_auth_routes": "admin_auth_legacy_handler",
    "requests.": "admin_auth_direct_http_client",
    "httpx": "admin_auth_direct_http_client",
    "access_token": "admin_auth_access_token_marker",
    "exchange_code_for_wecom_user": "admin_auth_direct_wecom_exchange",
    "build_wecom_qr_login_url": "admin_auth_direct_wecom_authorize",
    "build_wecom_oauth_login_url": "admin_auth_direct_wecom_authorize",
}
ADMIN_AUTH_LOGIN_TRUE_MARKERS = {
    '"fallback_used": True': "admin_auth_fallback_true",
    "'fallback_used': True": "admin_auth_fallback_true",
    '"real_external_call_executed": True': "admin_auth_real_external_call_true",
    "'real_external_call_executed': True": "admin_auth_real_external_call_true",
    "real_external_call_executed=True": "admin_auth_real_external_call_true",
    "real_external_call_executed = True": "admin_auth_real_external_call_true",
    "real_enabled default": "admin_auth_real_enabled_default",
    "default real_enabled": "admin_auth_real_enabled_default",
}
PUBLIC_PRODUCT_PAY_ROUTES = ("/p/{path:path}", "/pay/{path:path}", "/api/products/{path:path}")
PUBLIC_PRODUCT_PAY_REGISTRY_RECORDS = (
    "public_product_page_next_landing",
    "public_pay_landing_next_blocked",
    "public_product_api_next_contract",
)
PUBLIC_PRODUCT_PAY_MANIFEST_ROUTES = ("/p/{page_slug}", "/pay/{product_code}", "/api/products*")
PUBLIC_PRODUCT_PAY_DIRECT_MARKERS = {
    "forward_to_legacy_flask": "public_product_legacy_forward",
    "legacy_flask_facade": "public_product_legacy_facade",
    "WeChatPay": "public_product_direct_wechat_pay",
    "Alipay": "public_product_direct_alipay",
    "requests.": "public_product_direct_http_client",
    "httpx": "public_product_direct_http_client",
    "access_token": "public_product_access_token_marker",
    "create_jsapi_order": "public_product_payment_request",
    "create_h5_order": "public_product_payment_request",
    "create_wap_order": "public_product_payment_request",
    "create_order(": "public_product_order_create",
}
PUBLIC_PRODUCT_PAY_DIRECT_MARKER_ALLOWLIST = {
    Path("aicrm_next/public_product/api.py"): {"create_jsapi_order"},
    Path("aicrm_next/public_product") / "h5_wechat_pay.py": {"WeChatPay", "access_token", "create_jsapi_order"},
}
PUBLIC_PRODUCT_PAY_TRUE_MARKERS = {
    '"fallback_used": True': "public_product_fallback_true",
    "'fallback_used': True": "public_product_fallback_true",
    '"real_external_call_executed": True': "public_product_real_external_call_true",
    "'real_external_call_executed': True": "public_product_real_external_call_true",
    "real_external_call_executed=True": "public_product_real_external_call_true",
    "real_external_call_executed = True": "public_product_real_external_call_true",
    '"payment_request_executed": True': "public_product_payment_request_true",
    "'payment_request_executed': True": "public_product_payment_request_true",
    "payment_request_executed=True": "public_product_payment_request_true",
    "payment_request_executed = True": "public_product_payment_request_true",
    '"order_create_executed": True': "public_product_order_create_true",
    "'order_create_executed': True": "public_product_order_create_true",
    "order_create_executed=True": "public_product_order_create_true",
    "order_create_executed = True": "public_product_order_create_true",
    "real_enabled default": "public_product_real_enabled_default",
    "default real_enabled": "public_product_real_enabled_default",
}
CHECKOUT_ORDERS_COMPAT_ROUTES = ("/api/checkout/{path:path}", "/api/orders/{path:path}")
CHECKOUT_ORDERS_REGISTRY_RECORDS = (
    "checkout_wechat_next_checkout",
    "checkout_alipay_next_checkout",
    "orders_public_read_next_order_read",
    "orders_public_status_next_order_read",
    "checkout_unknown_next_blocked",
    "orders_unknown_child_next_not_found",
)
CHECKOUT_ORDERS_MANIFEST_ROUTES = ("/api/checkout*", "/api/orders*")
CHECKOUT_ORDERS_DIRECT_MARKERS = {
    "forward_to_legacy_flask": "checkout_orders_legacy_forward",
    "legacy_flask_facade": "checkout_orders_legacy_facade",
    "requests.": "checkout_orders_direct_http_client",
    "httpx.": "checkout_orders_direct_http_client",
    "access_token": "checkout_orders_access_token_marker",
    "raw WeChatPay": "checkout_orders_raw_wechatpay_client",
    "raw Alipay": "checkout_orders_raw_alipay_client",
}
CHECKOUT_ORDERS_TRUE_MARKERS = {
    '"fallback_used": True': "checkout_orders_fallback_true",
    "'fallback_used': True": "checkout_orders_fallback_true",
    '"real_external_call_executed": True': "checkout_orders_real_external_call_true",
    "'real_external_call_executed': True": "checkout_orders_real_external_call_true",
    "real_external_call_executed=True": "checkout_orders_real_external_call_true",
    "real_external_call_executed = True": "checkout_orders_real_external_call_true",
    '"payment_request_executed": True': "checkout_orders_payment_request_true",
    "'payment_request_executed': True": "checkout_orders_payment_request_true",
    "payment_request_executed=True": "checkout_orders_payment_request_true",
    "payment_request_executed = True": "checkout_orders_payment_request_true",
    '"real_wechat_pay_executed": True': "checkout_orders_real_wechat_pay_true",
    "'real_wechat_pay_executed': True": "checkout_orders_real_wechat_pay_true",
    "real_wechat_pay_executed=True": "checkout_orders_real_wechat_pay_true",
    "real_wechat_pay_executed = True": "checkout_orders_real_wechat_pay_true",
    '"real_alipay_executed": True': "checkout_orders_real_alipay_true",
    "'real_alipay_executed': True": "checkout_orders_real_alipay_true",
    "real_alipay_executed=True": "checkout_orders_real_alipay_true",
    "real_alipay_executed = True": "checkout_orders_real_alipay_true",
    "real_enabled default": "checkout_orders_real_enabled_default",
    "default real_enabled": "checkout_orders_real_enabled_default",
}
PROVIDER_PAYMENT_COMPAT_ROUTES = ("/api/wechat-pay/{path:path}", "/api/alipay/{path:path}")
PROVIDER_PAYMENT_REGISTRY_RECORDS = (
    "wechat_pay_notify_next_payment_notify",
    "alipay_notify_next_payment_notify",
    "alipay_return_next_payment_return",
    "wechat_pay_unknown_next_not_found",
    "alipay_unknown_next_not_found",
)
PROVIDER_PAYMENT_MANIFEST_ROUTES = ("/api/wechat-pay*", "/api/alipay*")
PROVIDER_PAYMENT_DIRECT_MARKERS = {
    "forward_to_legacy_flask": "provider_payment_legacy_forward",
    "legacy_flask_facade": "provider_payment_legacy_facade",
    "requests.": "provider_payment_direct_http_client",
    "httpx.": "provider_payment_direct_http_client",
    "access_token": "provider_payment_access_token_marker",
    "raw WeChatPay": "provider_payment_raw_wechatpay_client",
    "raw Alipay": "provider_payment_raw_alipay_client",
}
PROVIDER_PAYMENT_TRUE_MARKERS = {
    '"fallback_used": True': "provider_payment_fallback_true",
    "'fallback_used': True": "provider_payment_fallback_true",
    '"real_external_call_executed": True': "provider_payment_real_external_call_true",
    "'real_external_call_executed': True": "provider_payment_real_external_call_true",
    "real_external_call_executed=True": "provider_payment_real_external_call_true",
    "real_external_call_executed = True": "provider_payment_real_external_call_true",
    '"real_payment_notify_executed": True': "provider_payment_real_notify_true",
    "'real_payment_notify_executed': True": "provider_payment_real_notify_true",
    "real_payment_notify_executed=True": "provider_payment_real_notify_true",
    "real_payment_notify_executed = True": "provider_payment_real_notify_true",
    '"real_wechat_pay_executed": True': "provider_payment_real_wechat_pay_true",
    "'real_wechat_pay_executed': True": "provider_payment_real_wechat_pay_true",
    "real_wechat_pay_executed=True": "provider_payment_real_wechat_pay_true",
    "real_wechat_pay_executed = True": "provider_payment_real_wechat_pay_true",
    '"real_alipay_executed": True': "provider_payment_real_alipay_true",
    "'real_alipay_executed': True": "provider_payment_real_alipay_true",
    "real_alipay_executed=True": "provider_payment_real_alipay_true",
    "real_alipay_executed = True": "provider_payment_real_alipay_true",
    '"provider_signature_verified": True': "provider_payment_signature_verified_true",
    "'provider_signature_verified': True": "provider_payment_signature_verified_true",
    "provider_signature_verified=True": "provider_payment_signature_verified_true",
    "provider_signature_verified = True": "provider_payment_signature_verified_true",
    "real_enabled default": "provider_payment_real_enabled_default",
    "default real_enabled": "provider_payment_real_enabled_default",
}
PAYMENT_WILDCARD_FINAL_COMPAT_ROUTES = (
    "/api/admin/wechat-pay/{path:path}",
    "/api/admin/alipay/{path:path}",
    "/api/h5/wechat-pay/{path:path}",
    "/api/h5/alipay/{path:path}",
)
PAYMENT_WILDCARD_FINAL_REGISTRY_RECORDS = (
    "admin_wechat_pay_wildcard_final_closeout",
    "admin_alipay_wildcard_final_closeout",
    "h5_wechat_pay_wildcard_final_closeout",
    "h5_alipay_wildcard_final_closeout",
)
PAYMENT_WILDCARD_FINAL_MANIFEST_ROUTES = (
    "/api/admin/wechat-pay*",
    "/api/admin/alipay*",
    "/api/h5/wechat-pay*",
    "/api/h5/alipay*",
)
POST_LEGACY_DEFERRED_ROUTES = {
    "/api/admin/class-user-management/export": {
        "manifest_behavior": "next_export",
        "registry_owner": "next_native",
        "manifest_owner": "next",
    },
    "/api/admin/cloud-orchestrator/audit": {
        "manifest_behavior": "next_cloud_observability",
        "registry_owner": "next_native",
        "manifest_owner": "next",
    },
    "/api/admin/cloud-orchestrator/observability": {
        "manifest_behavior": "next_cloud_observability",
        "registry_owner": "next_native",
        "manifest_owner": "next",
    },
    "/api/admin/wecom-customer-acquisition-links": {
        "manifest_behavior": "next_wecom_customer_acquisition",
        "registry_owner": "next_command",
        "manifest_owner": "next_command",
    },
    "/api/admin/wecom-customer-acquisition-links/{link_id}": {
        "manifest_behavior": "next_wecom_customer_acquisition",
        "registry_owner": "next_command",
        "manifest_owner": "next_command",
    },
    "/api/admin/wecom-customer-acquisition-links/{link_id}/{action}": {
        "manifest_behavior": "next_wecom_customer_acquisition",
        "registry_owner": "next_command",
        "manifest_owner": "next_command",
    },
}
POST_LEGACY_DEVELOPMENT_DOCS = {
    Path("docs/architecture/post_legacy_next_development_rules.md"): (
        "所有新功能必须 Next-owned",
        "禁止新增 production_compat",
        "禁止新增 legacy Flask forward",
        "禁止新增 compatibility facade",
        "route registry",
        "production route ownership manifest",
        "aicrm_next.customer_read_model",
        "aicrm_next.cloud_orchestrator",
        "aicrm_next.commerce",
        "aicrm_next.media_library",
        "aicrm_next.customer_tags",
        "aicrm_next.questionnaire",
    ),
    Path("docs/development/codex_post_legacy_development_contract.md"): (
        "每次开发前必须读取",
        "existing module search",
        "不允许恢复 `production_compat`",
        "不允许新增 `forward_to_legacy_flask`",
        "不允许新建 legacy facade",
        "不允许默认真实外部调用",
        "不允许不登记 route owner",
        "不允许跳过 strict guard",
    ),
    Path("docs/architecture/post_legacy_legacy_module_prune_inventory.md"): (
        "legacy module / package",
        "替代 Next 模块",
        "删除决策",
        "keep_temporarily_historical",
        "wecom_ability_service/http/admin_hxc_dashboard.py",
        "wecom_ability_service/http/admin_auth_routes.py",
        "wecom_ability_service/http/cloud_orchestrator_campaigns.py",
        "wecom_ability_service/http/cloud_orchestrator_media.py",
        "wecom_ability_service/http/cloud_orchestrator_endpoint.py",
    ),
}
POST_LEGACY_DELETED_HTTP_MODULES = {
    "admin_hxc_dashboard": Path("wecom_ability_service/http/admin_hxc_dashboard.py"),
    "admin_auth_routes": Path("wecom_ability_service/http/admin_auth_routes.py"),
    "cloud_orchestrator_campaigns": Path("wecom_ability_service/http/cloud_orchestrator_campaigns.py"),
    "cloud_orchestrator_campaign_details": Path("wecom_ability_service/http/cloud_orchestrator_campaign_details.py"),
    "cloud_orchestrator_media": Path("wecom_ability_service/http/cloud_orchestrator_media.py"),
    "cloud_orchestrator_endpoint": Path("wecom_ability_service/http/cloud_orchestrator_endpoint.py"),
    "cloud_orchestrator_pages": Path("wecom_ability_service/http/cloud_orchestrator_pages.py"),
    "cloud_orchestrator_plans": Path("wecom_ability_service/http/cloud_orchestrator_plans.py"),
    "cloud_orchestrator_segments": Path("wecom_ability_service/http/cloud_orchestrator_segments.py"),
}
POST_LEGACY_TEMPORARY_HISTORICAL_HTTP_MODULES = {
    "automation_conversion": Path("wecom_ability_service/http/automation_conversion.py"),
    "automation_conversion_runtime_api": Path("wecom_ability_service/http/automation_conversion_runtime_api.py"),
    "automation_conversion_task_runtime": Path("wecom_ability_service/http/automation_conversion_task_runtime.py"),
    "automation_conversion_execution_outbound": Path("wecom_ability_service/http/automation_conversion_execution_outbound.py"),
    "automation_conversion_member_api": Path("wecom_ability_service/http/automation_conversion_member_api.py"),
    "customer_automation": Path("wecom_ability_service/http/customer_automation.py"),
}
POST_LEGACY_MAIN_FORBIDDEN_MARKERS = {
    "production_compat_router": "post_legacy_main_production_compat_router",
    "production_compat_wildcard_router": "post_legacy_main_production_compat_wildcard_router",
    "forward_to_legacy_flask": "post_legacy_main_legacy_forward",
    "legacy_flask_facade": "post_legacy_main_legacy_facade",
    "X-AICRM-Compatibility-Facade": "post_legacy_main_compatibility_facade_header",
}
POST_LEGACY_PARALLEL_MODULE_MARKERS = {
    "duplicate checkout": "post_legacy_duplicate_checkout_guard",
    "duplicate media upload": "post_legacy_duplicate_media_upload_guard",
    "duplicate customer selector": "post_legacy_duplicate_customer_selector_guard",
    "duplicate tag catalog": "post_legacy_duplicate_tag_catalog_guard",
    "duplicate broadcast sender": "post_legacy_duplicate_broadcast_sender_guard",
    "WeComClient.from_app": "post_legacy_wecom_client_from_app_guard",
    "real_external_call_executed=True": "post_legacy_real_external_true_guard",
    "real_enabled default": "post_legacy_real_enabled_default_guard",
}
PAYMENT_WILDCARD_FINAL_DIRECT_MARKERS = {
    "forward_to_legacy_flask": "payment_wildcard_final_legacy_forward",
    "legacy_flask_facade": "payment_wildcard_final_legacy_facade",
    "requests.": "payment_wildcard_final_direct_http_client",
    "httpx.": "payment_wildcard_final_direct_http_client",
    "access_token": "payment_wildcard_final_access_token_marker",
    "raw WeChatPay": "payment_wildcard_final_raw_wechatpay_client",
    "raw Alipay": "payment_wildcard_final_raw_alipay_client",
}
PAYMENT_WILDCARD_FINAL_TRUE_MARKERS = {
    '"fallback_used": True': "payment_wildcard_final_fallback_true",
    "'fallback_used': True": "payment_wildcard_final_fallback_true",
    '"real_external_call_executed": True': "payment_wildcard_final_real_external_call_true",
    "'real_external_call_executed': True": "payment_wildcard_final_real_external_call_true",
    "real_external_call_executed=True": "payment_wildcard_final_real_external_call_true",
    "real_external_call_executed = True": "payment_wildcard_final_real_external_call_true",
    '"payment_request_executed": True': "payment_wildcard_final_payment_request_true",
    "'payment_request_executed': True": "payment_wildcard_final_payment_request_true",
    "payment_request_executed=True": "payment_wildcard_final_payment_request_true",
    "payment_request_executed = True": "payment_wildcard_final_payment_request_true",
    '"real_wechat_pay_executed": True': "payment_wildcard_final_real_wechat_pay_true",
    "'real_wechat_pay_executed': True": "payment_wildcard_final_real_wechat_pay_true",
    "real_wechat_pay_executed=True": "payment_wildcard_final_real_wechat_pay_true",
    "real_wechat_pay_executed = True": "payment_wildcard_final_real_wechat_pay_true",
    '"real_alipay_executed": True': "payment_wildcard_final_real_alipay_true",
    "'real_alipay_executed': True": "payment_wildcard_final_real_alipay_true",
    "real_alipay_executed=True": "payment_wildcard_final_real_alipay_true",
    "real_alipay_executed = True": "payment_wildcard_final_real_alipay_true",
    '"provider_signature_verified": True': "payment_wildcard_final_signature_verified_true",
    "'provider_signature_verified': True": "payment_wildcard_final_signature_verified_true",
    "provider_signature_verified=True": "payment_wildcard_final_signature_verified_true",
    "provider_signature_verified = True": "payment_wildcard_final_signature_verified_true",
    '"real_refund_executed": True': "payment_wildcard_final_real_refund_true",
    "'real_refund_executed': True": "payment_wildcard_final_real_refund_true",
    "real_refund_executed=True": "payment_wildcard_final_real_refund_true",
    "real_refund_executed = True": "payment_wildcard_final_real_refund_true",
    "real_enabled default": "payment_wildcard_final_real_enabled_default",
    "default real_enabled": "payment_wildcard_final_real_enabled_default",
}
CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE = "/api/admin/cloud-orchestrator/media/upload"
CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE = "/admin/cloud-orchestrator/campaigns"
CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE = "/api/admin/cloud-orchestrator/campaigns*"
CLOUD_ORCHESTRATOR_CAMPAIGN_READ_SAMPLES = (
    "/api/admin/cloud-orchestrator/campaigns",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps",
)
CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE", "OPTIONS")
CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE = "/api/admin/cloud-orchestrator/campaigns*"
CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTES = (
    "/api/admin/cloud-orchestrator/campaigns/batch-start",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/start",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/pause",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/reject",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps",
    "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps/{step_index}",
)
CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE = "/api/admin/cloud-orchestrator/campaigns/run-due*"
CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_EXACT_ROUTES = {
    "/api/admin/cloud-orchestrator/campaigns/run-due",
    "/api/admin/cloud-orchestrator/campaigns/run-due/preview",
}
CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_DIRECT_EXTERNAL_MARKERS = {
    "process_due_campaign_members": "cloud_campaign_run_due_legacy_scheduler",
    "WeComClient.from_app": "cloud_campaign_run_due_wecom_client",
    "send_message": "cloud_campaign_run_due_direct_send_message",
    "dispatch_wecom_task": "cloud_campaign_run_due_dispatch_wecom_task",
    "requests.": "cloud_campaign_run_due_direct_http_client",
    "httpx": "cloud_campaign_run_due_direct_http_client",
    "access_token": "cloud_campaign_run_due_token_exchange",
    "real_external_call_executed=True": "cloud_campaign_run_due_real_external_true",
    "real_external_call_executed = True": "cloud_campaign_run_due_real_external_true",
    '"real_external_call_executed": True': "cloud_campaign_run_due_real_external_true",
    "'real_external_call_executed': True": "cloud_campaign_run_due_real_external_true",
    "campaign_runtime_executed=True": "cloud_campaign_run_due_runtime_true",
    "campaign_runtime_executed = True": "cloud_campaign_run_due_runtime_true",
    '"campaign_runtime_executed": True': "cloud_campaign_run_due_runtime_true",
    "'campaign_runtime_executed': True": "cloud_campaign_run_due_runtime_true",
    "automation_runtime_executed=True": "cloud_campaign_run_due_automation_runtime_true",
    "automation_runtime_executed = True": "cloud_campaign_run_due_automation_runtime_true",
    '"automation_runtime_executed": True': "cloud_campaign_run_due_automation_runtime_true",
    "'automation_runtime_executed': True": "cloud_campaign_run_due_automation_runtime_true",
    "wecom_send_executed=True": "cloud_campaign_run_due_send_true",
    "wecom_send_executed = True": "cloud_campaign_run_due_send_true",
    '"wecom_send_executed": True': "cloud_campaign_run_due_send_true",
    "'wecom_send_executed': True": "cloud_campaign_run_due_send_true",
    "real_enabled default": "cloud_campaign_run_due_real_enabled_default",
    "default real_enabled": "cloud_campaign_run_due_real_enabled_default",
}
AUTOMATION_CONVERSION_TIMER_ROUTES = {
    "/api/admin/automation-conversion/reply-monitor/run-due",
    "/api/admin/automation-conversion/reply-monitor/capture",
    "/api/admin/automation-conversion/jobs/run-due",
    "/api/admin/automation-conversion/jobs/run-due/preview",
}
AUTOMATION_CONVERSION_TIMER_REGISTRY_RECORDS = {
    "automation_conversion_reply_monitor_timer_next_safe_mode": "/api/admin/automation-conversion/reply-monitor*",
    "automation_conversion_jobs_run_due_timer_next_safe_mode": "/api/admin/automation-conversion/jobs/run-due*",
}
AUTOMATION_CONVERSION_TIMER_MANIFEST_ROUTES = (
    "/api/admin/automation-conversion/reply-monitor*",
    "/api/admin/automation-conversion/jobs/run-due*",
)
AUTOMATION_CONVERSION_TIMER_DIRECT_EXTERNAL_MARKERS = {
    "run_reply_monitor_capture": "automation_timer_legacy_capture_runtime",
    "run_due_reply_monitor": "automation_timer_legacy_reply_runtime",
    "run_registered_due_jobs": "automation_timer_legacy_jobs_runtime",
    "WeComClient.from_app": "automation_timer_wecom_client",
    "send_message": "automation_timer_direct_send_message",
    "OpenClaw": "automation_timer_openclaw_direct_invoke",
    "Bazhuayu": "automation_timer_bazhuayu_direct_invoke",
    "requests": "automation_timer_direct_http_client",
    "httpx": "automation_timer_direct_http_client",
    "access_token": "automation_timer_token_exchange",
}
AUTOMATION_CONVERSION_TIMER_TRUE_DEFAULT_MARKERS = {
    "real_external_call_executed=True": "automation_timer_real_external_true",
    "real_external_call_executed = True": "automation_timer_real_external_true",
    '"real_external_call_executed": True': "automation_timer_real_external_true",
    "'real_external_call_executed': True": "automation_timer_real_external_true",
    "automation_runtime_executed=True": "automation_timer_runtime_true",
    "automation_runtime_executed = True": "automation_timer_runtime_true",
    '"automation_runtime_executed": True': "automation_timer_runtime_true",
    "'automation_runtime_executed': True": "automation_timer_runtime_true",
    "reply_monitor_capture_executed=True": "automation_timer_capture_true",
    "reply_monitor_capture_executed = True": "automation_timer_capture_true",
    '"reply_monitor_capture_executed": True': "automation_timer_capture_true",
    "'reply_monitor_capture_executed': True": "automation_timer_capture_true",
    "reply_monitor_run_due_executed=True": "automation_timer_reply_true",
    "reply_monitor_run_due_executed = True": "automation_timer_reply_true",
    '"reply_monitor_run_due_executed": True': "automation_timer_reply_true",
    "'reply_monitor_run_due_executed': True": "automation_timer_reply_true",
    "jobs_run_due_executed=True": "automation_timer_jobs_true",
    "jobs_run_due_executed = True": "automation_timer_jobs_true",
    '"jobs_run_due_executed": True': "automation_timer_jobs_true",
    "'jobs_run_due_executed': True": "automation_timer_jobs_true",
    "wecom_send_executed=True": "automation_timer_send_true",
    "wecom_send_executed = True": "automation_timer_send_true",
    '"wecom_send_executed": True': "automation_timer_send_true",
    "'wecom_send_executed': True": "automation_timer_send_true",
    "real_enabled default": "automation_timer_real_enabled_default",
    "default real_enabled": "automation_timer_real_enabled_default",
}
AUTOMATION_WORKSPACE_RUNTIME_ROUTES = {
    "/api/admin/automation-conversion/tasks/run-due",
    "/api/admin/automation-conversion/execution-items/{execution_item_id:int}/send-via-bazhuayu",
}
AUTOMATION_WORKSPACE_RUNTIME_API_ROUTES = {
    "/api/admin/automation-conversion/tasks/run-due",
    "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
}
AUTOMATION_WORKSPACE_RUNTIME_REGISTRY_RECORDS = {
    "automation_workspace_tasks_run_due_next_safe_mode": "/api/admin/automation-conversion/tasks/run-due",
    "automation_workspace_execution_item_bazhuayu_next_safe_mode": "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
}
AUTOMATION_WORKSPACE_RUNTIME_MANIFEST_ROUTES = (
    "/api/admin/automation-conversion/tasks/run-due",
    "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
)
AUTOMATION_WORKSPACE_RUNTIME_DIRECT_EXTERNAL_MARKERS = {
    "run_due_operation_tasks": "automation_workspace_legacy_operation_task_runtime",
    "send_conversion_execution_item_via_bazhuayu": "automation_workspace_legacy_outbound_runtime",
    "AutomationConversionDispatchError": "automation_workspace_legacy_dispatch_error",
    "WeComClient.from_app": "automation_workspace_wecom_client",
    "OpenClaw": "automation_workspace_openclaw_direct_invoke",
    "Bazhuayu": "automation_workspace_bazhuayu_direct_invoke",
    "requests": "automation_workspace_direct_http_client",
    "httpx": "automation_workspace_direct_http_client",
    "access_token": "automation_workspace_token_exchange",
}
AUTOMATION_WORKSPACE_RUNTIME_TRUE_DEFAULT_MARKERS = {
    "real_external_call_executed=True": "automation_workspace_real_external_true",
    "real_external_call_executed = True": "automation_workspace_real_external_true",
    '"real_external_call_executed": True': "automation_workspace_real_external_true",
    "'real_external_call_executed': True": "automation_workspace_real_external_true",
    "automation_runtime_executed=True": "automation_workspace_runtime_true",
    "automation_runtime_executed = True": "automation_workspace_runtime_true",
    '"automation_runtime_executed": True': "automation_workspace_runtime_true",
    "'automation_runtime_executed': True": "automation_workspace_runtime_true",
    "operation_tasks_executed=True": "automation_workspace_operation_tasks_true",
    "operation_tasks_executed = True": "automation_workspace_operation_tasks_true",
    '"operation_tasks_executed": True': "automation_workspace_operation_tasks_true",
    "'operation_tasks_executed': True": "automation_workspace_operation_tasks_true",
    "bazhuayu_send_executed=True": "automation_workspace_bazhuayu_true",
    "bazhuayu_send_executed = True": "automation_workspace_bazhuayu_true",
    '"bazhuayu_send_executed": True': "automation_workspace_bazhuayu_true",
    "'bazhuayu_send_executed': True": "automation_workspace_bazhuayu_true",
    "wecom_send_executed=True": "automation_workspace_send_true",
    "wecom_send_executed = True": "automation_workspace_send_true",
    '"wecom_send_executed": True': "automation_workspace_send_true",
    "'wecom_send_executed': True": "automation_workspace_send_true",
    "real_enabled default": "automation_workspace_real_enabled_default",
    "default real_enabled": "automation_workspace_real_enabled_default",
}
AUTOMATION_MEMBER_DETAIL_ROUTE = "/api/admin/automation-conversion/member"
AUTOMATION_MEMBER_WILDCARD_ROUTE = "/api/admin/automation-conversion/member/{path:path}"
AUTOMATION_MEMBER_ACTION_ROUTES = {
    "automation_member_put_in_pool_next_command": "/api/admin/automation-conversion/member/put-in-pool",
    "automation_member_remove_from_pool_next_command": "/api/admin/automation-conversion/member/remove-from-pool",
    "automation_member_set_focus_next_command": "/api/admin/automation-conversion/member/set-focus",
    "automation_member_set_normal_next_command": "/api/admin/automation-conversion/member/set-normal",
    "automation_member_mark_won_next_command": "/api/admin/automation-conversion/member/mark-won",
    "automation_member_unmark_won_next_command": "/api/admin/automation-conversion/member/unmark-won",
    "automation_member_push_openclaw_next_command": "/api/admin/automation-conversion/member/push-openclaw",
}
AUTOMATION_OVERVIEW_POOL_ROUTES = (
    "/api/admin/automation-conversion/overview",
    "/api/admin/automation-conversion/pools",
)
AUTOMATION_OVERVIEW_POOL_ROUTE_IDS = {
    "automation_conversion_overview_next_read_model": "/api/admin/automation-conversion/overview",
    "automation_conversion_pools_next_read_model": "/api/admin/automation-conversion/pools",
}
AUTOMATION_OVERVIEW_POOL_DELETED_MARKERS = {
    "get_automation_overview_from_legacy",
    "list_automation_pools_from_legacy",
}
AUTOMATION_OVERVIEW_POOL_FORBIDDEN_API_MARKERS = {
    *AUTOMATION_OVERVIEW_POOL_DELETED_MARKERS,
    "legacy_automation_facade",
    "production_data_ready",
}
AUTOMATION_MEMBER_API_ROUTES = (
    AUTOMATION_MEMBER_DETAIL_ROUTE,
    *AUTOMATION_MEMBER_ACTION_ROUTES.values(),
)
AUTOMATION_MEMBER_DIRECT_MARKERS = {
    "wecom_ability_service": "automation_member_legacy_service_import",
    "legacy_automation_facade": "automation_member_legacy_facade",
    "get_automation_member_detail_from_legacy": "automation_member_legacy_detail",
    "send_outbound_webhook": "automation_member_openclaw_direct_invoke",
    "PushMemberContextToOpenClawCommand": "automation_member_openclaw_direct_invoke",
    "OpenClawWebhookAdapter": "automation_member_openclaw_direct_invoke",
    "requests": "automation_member_direct_http_client",
    "httpx": "automation_member_direct_http_client",
    "access_token": "automation_member_token_exchange",
}
AUTOMATION_MEMBER_TRUE_DEFAULT_MARKERS = {
    "real_external_call_executed=True": "automation_member_real_external_true",
    "real_external_call_executed = True": "automation_member_real_external_true",
    '"real_external_call_executed": True': "automation_member_real_external_true",
    "'real_external_call_executed': True": "automation_member_real_external_true",
    "openclaw_push_executed=True": "automation_member_openclaw_true",
    "openclaw_push_executed = True": "automation_member_openclaw_true",
    '"openclaw_push_executed": True': "automation_member_openclaw_true",
    "'openclaw_push_executed': True": "automation_member_openclaw_true",
    "automation_runtime_executed=True": "automation_member_runtime_true",
    "automation_runtime_executed = True": "automation_member_runtime_true",
    '"automation_runtime_executed": True': "automation_member_runtime_true",
    "'automation_runtime_executed': True": "automation_member_runtime_true",
    "real_enabled default": "automation_member_real_enabled_default",
    "default real_enabled": "automation_member_real_enabled_default",
}
CUSTOMER_AUTOMATION_WEBHOOK_COMPAT_ROUTES = {
    "/api/customers/automation/activation-webhook",
    "/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry",
    "/api/customers/automation/webhook-deliveries/retry-due",
}
CUSTOMER_AUTOMATION_WEBHOOK_API_ROUTES = {
    "/api/customers/automation/activation-webhook": "next_customer_activation_webhook",
    "/api/customers/automation/webhook-deliveries/{delivery_id}/retry": "next_customer_webhook_retry_plan",
    "/api/customers/automation/webhook-deliveries/retry-due": "next_customer_webhook_retry_due_plan",
}
CUSTOMER_AUTOMATION_WEBHOOK_REGISTRY_RECORDS = {
    "customer_automation_activation_webhook_next_command": (
        "/api/customers/automation/activation-webhook",
        "next_command",
        "medium",
        "local",
    ),
    "customer_automation_webhook_delivery_retry_next_safe_mode": (
        "/api/customers/automation/webhook-deliveries/{delivery_id}/retry",
        "next_runtime_plan",
        "high",
        "real_blocked",
    ),
    "customer_automation_webhook_delivery_retry_due_next_safe_mode": (
        "/api/customers/automation/webhook-deliveries/retry-due",
        "next_runtime_plan",
        "high",
        "real_blocked",
    ),
}
CUSTOMER_AUTOMATION_WEBHOOK_DIRECT_MARKERS = {
    "wecom_ability_service": "customer_automation_webhook_legacy_service_import",
    "legacy_customer_automation_compat_routes": "customer_automation_webhook_legacy_compat_route",
    "ApplyActivationWebhookCommand": "customer_automation_webhook_legacy_activation_command",
    "RetryOutboundWebhookDeliveryCommand": "customer_automation_webhook_legacy_retry_command",
    "RunDueOutboundWebhookRetriesCommand": "customer_automation_webhook_legacy_retry_due_command",
    "send_outbound_webhook": "customer_automation_webhook_direct_outbound_send",
    "requests.": "customer_automation_webhook_direct_http_client",
    "httpx.": "customer_automation_webhook_direct_http_client",
    "access_token": "customer_automation_webhook_token_exchange",
}
CUSTOMER_AUTOMATION_WEBHOOK_TRUE_DEFAULT_MARKERS = {
    "real_external_call_executed=True": "customer_automation_webhook_real_external_true",
    "real_external_call_executed = True": "customer_automation_webhook_real_external_true",
    '"real_external_call_executed": True': "customer_automation_webhook_real_external_true",
    "'real_external_call_executed': True": "customer_automation_webhook_real_external_true",
    "outbound_webhook_executed=True": "customer_automation_webhook_outbound_true",
    "outbound_webhook_executed = True": "customer_automation_webhook_outbound_true",
    '"outbound_webhook_executed": True': "customer_automation_webhook_outbound_true",
    "'outbound_webhook_executed': True": "customer_automation_webhook_outbound_true",
    "automation_runtime_executed=True": "customer_automation_webhook_runtime_true",
    "automation_runtime_executed = True": "customer_automation_webhook_runtime_true",
    '"automation_runtime_executed": True': "customer_automation_webhook_runtime_true",
    "'automation_runtime_executed': True": "customer_automation_webhook_runtime_true",
    "wecom_send_executed=True": "customer_automation_webhook_send_true",
    "wecom_send_executed = True": "customer_automation_webhook_send_true",
    '"wecom_send_executed": True': "customer_automation_webhook_send_true",
    "'wecom_send_executed': True": "customer_automation_webhook_send_true",
    "real_enabled default": "customer_automation_webhook_real_enabled_default",
    "default real_enabled": "customer_automation_webhook_real_enabled_default",
}
CLOUD_ORCHESTRATOR_CAMPAIGN_DIRECT_EXTERNAL_MARKERS = {
    "WeComClient.from_app": "cloud_campaign_read_wecom_client",
    "send_message": "cloud_campaign_read_send_message",
    "dispatch_wecom_task": "cloud_campaign_read_dispatch_wecom_task",
    "process_due_campaign_members": "cloud_campaign_read_runtime",
    "run_due": "cloud_campaign_read_runtime",
    "requests.": "cloud_campaign_read_direct_http_client",
    "httpx": "cloud_campaign_read_direct_http_client",
    "access_token": "cloud_campaign_read_access_token",
    "real_external_call_executed=True": "cloud_campaign_read_real_external_call_true",
    "real_external_call_executed = True": "cloud_campaign_read_real_external_call_true",
    '"real_external_call_executed": True': "cloud_campaign_read_real_external_call_true",
    "'real_external_call_executed': True": "cloud_campaign_read_real_external_call_true",
    "automation_runtime=True": "cloud_campaign_read_runtime_true",
    "automation_runtime = True": "cloud_campaign_read_runtime_true",
    "wecom_send=True": "cloud_campaign_read_wecom_send_true",
    "wecom_send = True": "cloud_campaign_read_wecom_send_true",
}
CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_DIRECT_EXTERNAL_MARKERS = {
    "WeComClient.from_app": "cloud_media_upload_wecom_client",
    "upload_cloud_orchestrator_image": "cloud_media_upload_legacy_helper",
    "access_token": "cloud_media_upload_access_token",
    "requests.": "cloud_media_upload_direct_http_client",
    "httpx": "cloud_media_upload_direct_http_client",
}


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    detail: str
    remediation: str = "Register the route in the route registry and update the deletion lifecycle; do not add new legacy fallback or direct side-effect paths."

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _iter_python_files(root: Path) -> Iterable[Path]:
    candidates: list[Path] = []
    for item in [root / "aicrm_next", root / "app.py", root / "legacy_flask_app.py"]:
        if item.is_file():
            candidates.append(item)
        elif item.is_dir():
            candidates.extend(item.rglob("*.py"))
    for path in candidates:
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_DIRS:
            continue
        yield path


def scan_source_tree(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_python_files(root):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if "legacy_flask_facade" in text and rel not in LEGACY_IMPORT_ALLOWLIST:
            violations.append(Violation("legacy_flask_facade_import", str(rel), "legacy Flask facade import is not allowlisted"))
        if "wecom_ability_service" in text and rel not in WECOM_IMPORT_ALLOWLIST:
            violations.append(Violation("wecom_ability_service_import", str(rel), "legacy wecom_ability_service import is not allowlisted"))
        if rel.name in {"api.py", "routes.py"} and rel not in API_SIDE_EFFECT_ALLOWLIST:
            for marker in SIDE_EFFECT_MARKERS:
                if marker in text:
                    violations.append(Violation("api_direct_external_side_effect", str(rel), marker))
    return violations


def check_startup_legacy_closeout(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    app_path = root / "app.py"
    legacy_runner = root / "legacy_flask_app.py"
    checker_path = root / "scripts/check_no_new_legacy.py"
    deploy_path = root / ".github/workflows/deploy.yml"

    if legacy_runner.exists():
        violations.append(
            Violation(
                "legacy_flask_app_file_remaining",
                str(legacy_runner.relative_to(root)),
                "legacy_flask_app.py must not exist after startup compatibility closeout",
            )
        )

    app_text = app_path.read_text(encoding="utf-8") if app_path.exists() else ""
    forbidden_app_markers = {
        "wecom_ability_service": "app_py_imports_legacy_startup",
        "run_legacy": "app_py_legacy_command_executes",
        "init_db_legacy": "app_py_legacy_command_executes",
        "delete_questionnaire_submissions_legacy": "app_py_legacy_command_executes",
        "create_app()": "app_py_legacy_command_executes",
        "init_db()": "app_py_legacy_command_executes",
        "delete_questionnaire_submissions_by_slug": "app_py_legacy_command_executes",
    }
    for marker, code in forbidden_app_markers.items():
        if marker in app_text:
            violations.append(Violation(code, "app.py", marker))

    required_app_markers = (
        'NEXT_APP_IMPORT = "aicrm_next.main:app"',
        "run_next",
        "print_next_health",
        "print_next_routes",
        "removed_legacy_command",
        "run-legacy",
        "init-db",
        "init-db-legacy",
    )
    for marker in required_app_markers:
        if marker not in app_text:
            violations.append(Violation("app_py_next_only_marker_missing", "app.py", marker))

    deploy_text = deploy_path.read_text(encoding="utf-8") if deploy_path.exists() else ""
    forbidden_deploy_markers = (
        "python3 app.py init-db",
        "python app.py init-db",
        "init-db-legacy",
        "legacy_flask_app",
        "alembic stamp head",
    )
    for marker in forbidden_deploy_markers:
        if marker in deploy_text:
            violations.append(Violation("deploy_workflow_uses_legacy_init_db", str(deploy_path.relative_to(root)), marker))

    required_deploy_markers = (
        "source /home/ubuntu/.openclaw-wecom-pg.env",
        'test -n "${DATABASE_URL:-}"',
        "python3 -m alembic upgrade head",
    )
    for marker in required_deploy_markers:
        if marker not in deploy_text:
            violations.append(Violation("deploy_workflow_missing_alembic_upgrade", str(deploy_path.relative_to(root)), marker))

    checker_text = checker_path.read_text(encoding="utf-8") if checker_path.exists() else ""
    stale_allowlist_markers = (
        'Path("' + 'app.py' + '")',
        'Path("' + 'legacy_flask_app.py' + '")',
    )
    for marker in stale_allowlist_markers:
        if marker in checker_text:
            violations.append(Violation("startup_wecom_allowlist_not_empty", str(checker_path.relative_to(root)), marker))

    return violations


def _file_contains_any(path: Path, markers: tuple[str, ...]) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [marker for marker in markers if marker in text]


def check_group_ops_message_content_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    domain_path = root / "aicrm_next/automation_engine/group_ops/domain.py"
    message_content_path = root / "aicrm_next/automation_engine/group_ops/message_content.py"
    legacy_facade_path = root / "aicrm_next/integration_gateway/legacy_flask_facade.py"

    for marker in _file_contains_any(
        domain_path,
        (
            "legacy_flask_facade",
            "build_legacy_private_message_request_payload",
            "wecom_ability_service.domains.tasks.private_message",
        ),
    ):
        violations.append(Violation("group_ops_domain_legacy_message_builder", str(domain_path.relative_to(root)), marker))

    for marker in _file_contains_any(
        message_content_path,
        (
            "legacy_flask_facade",
            "wecom_ability_service",
            "build_legacy_private_message_request_payload",
        ),
    ):
        violations.append(Violation("group_ops_message_content_legacy_import", str(message_content_path.relative_to(root)), marker))

    for marker in _file_contains_any(
        legacy_facade_path,
        (
            "def legacy_private_message_module",
            "def build_legacy_private_message_request_payload",
        ),
    ):
        violations.append(Violation("legacy_flask_facade_private_message_wrapper_remaining", str(legacy_facade_path.relative_to(root)), marker))

    return violations


def check_group_ops_material_resolver_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    gateway_path = root / "aicrm_next/automation_engine/group_ops/integration_gateway.py"
    resolver_path = root / "aicrm_next/automation_engine/group_ops/material_resolver.py"

    if gateway_path.exists():
        text = gateway_path.read_text(encoding="utf-8")
        rel = str(gateway_path.relative_to(root))
        for marker in (
            "wecom_ability_service",
            "image_library",
            "miniprogram_library",
            "attachment_library",
            "legacy_flask_facade",
            "WeComClient.from_app",
        ):
            if marker in text:
                violations.append(Violation("group_ops_material_gateway_legacy_import", rel, marker))
        for marker in ("requests.", "httpx"):
            if marker in text:
                violations.append(Violation("group_ops_material_gateway_direct_http", rel, marker))
        if "build_group_ops_material_resolver" not in text:
            violations.append(Violation("group_ops_material_gateway_not_native", rel, "build_group_ops_material_resolver"))
    else:
        violations.append(Violation("group_ops_material_gateway_not_native", str(gateway_path.relative_to(root)), "missing integration_gateway.py"))

    if resolver_path.exists():
        text = resolver_path.read_text(encoding="utf-8")
        rel = str(resolver_path.relative_to(root))
        for marker in (
            "wecom_ability_service",
            "legacy_flask_facade",
            "flask",
            "current_app",
            "WeComClient.from_app",
        ):
            if marker in text:
                violations.append(Violation("group_ops_material_resolver_legacy_import", rel, marker))
        for marker in ("requests.", "httpx"):
            if marker in text:
                violations.append(Violation("group_ops_material_resolver_direct_http", rel, marker))
        for marker in (
            "GroupOpsMaterialResolver",
            "resolve_content_package_materials",
            "build_group_ops_material_resolver",
        ):
            if marker not in text:
                violations.append(Violation("group_ops_material_resolver_contract_missing", rel, marker))
    else:
        violations.append(Violation("group_ops_material_resolver_contract_missing", str(resolver_path.relative_to(root)), "missing material_resolver.py"))

    return violations


def check_group_ops_scheduler_duplicate_checker_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    group_ops_root = root / "aicrm_next" / "automation_engine" / "group_ops"
    scheduler_path = group_ops_root / "scheduler.py"
    duplicate_checker_path = group_ops_root / "duplicate_checker.py"
    checker_path = root / "scripts/check_no_new_legacy.py"

    legacy_markers = (
        "wecom_ability_service",
        "legacy_flask_facade",
        "legacy_broadcast",
        "broadcast_jobs.service",
        "broadcast_jobs import repo",
        "from wecom_ability_service",
        "WeComClient.from_app",
        "current_app",
    )
    direct_http_markers = ("requests.", "httpx")

    if scheduler_path.exists():
        text = scheduler_path.read_text(encoding="utf-8")
        rel = str(scheduler_path.relative_to(root))
        for marker in legacy_markers:
            if marker in text:
                violations.append(Violation("group_ops_scheduler_legacy_duplicate_checker", rel, marker))
        for marker in direct_http_markers:
            if marker in text:
                violations.append(Violation("group_ops_scheduler_direct_http", rel, marker))
        if "duplicate_checker: Callable[[str], bool] | None = None" not in text or "self._duplicate_checker = duplicate_checker or" not in text:
            violations.append(
                Violation(
                    "group_ops_scheduler_duplicate_injection_missing",
                    rel,
                    "scheduler must keep injectable duplicate_checker parameter",
                )
            )
    else:
        violations.append(Violation("group_ops_scheduler_duplicate_injection_missing", str(scheduler_path.relative_to(root)), "missing scheduler.py"))

    if duplicate_checker_path.exists():
        text = duplicate_checker_path.read_text(encoding="utf-8")
        rel = str(duplicate_checker_path.relative_to(root))
        for marker in legacy_markers:
            if marker in text:
                violations.append(Violation("group_ops_duplicate_checker_legacy_import", rel, marker))
        for marker in direct_http_markers:
            if marker in text:
                violations.append(Violation("group_ops_scheduler_direct_http", rel, marker))

    if checker_path.exists():
        text = checker_path.read_text(encoding="utf-8")
        allowlist_marker = 'Path("aicrm_next/automation_engine/group_ops/' + 'scheduler.py")'
        if allowlist_marker in text:
            violations.append(Violation("group_ops_scheduler_stale_wecom_allowlist", str(checker_path.relative_to(root)), allowlist_marker))

    return violations


def check_channel_identity_bridge_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    channel_root = root / "aicrm_next" / "channel_entry"
    bridge_path = channel_root / "identity_bridge.py"
    repo_path = channel_root / "identity_bridge_repo.py"
    service_path = channel_root / "identity_bridge_service.py"
    checker_path = root / "scripts" / "check_no_new_legacy.py"
    test_path = root / "tests" / "test_next_channel_identity_bridge.py"

    if bridge_path.exists():
        text = bridge_path.read_text(encoding="utf-8")
        rel = str(bridge_path.relative_to(root))
        for marker in (
            "wecom_ability_service",
            "_legacy_app",
            "legacy_flask_facade",
            "create_app",
            "with _legacy_app",
            "current_app",
            "from flask",
            "BindExternalContactMobileFromIdentitySourcesCommand",
            "BuildExternalContactIdentityRecordCommand",
            "backfill_questionnaire_submissions_for_mobile_binding",
        ):
            if marker in text:
                violations.append(Violation("channel_identity_bridge_legacy_import", rel, marker))

    if repo_path.exists():
        text = repo_path.read_text(encoding="utf-8")
        rel = str(repo_path.relative_to(root))
        for marker in ("wecom_ability_service", "legacy_flask_facade", "flask", "current_app"):
            if marker in text:
                violations.append(Violation("channel_identity_repo_legacy_import", rel, marker))
    else:
        violations.append(Violation("channel_identity_repo_legacy_import", str(repo_path.relative_to(root)), "missing identity_bridge_repo.py"))

    if service_path.exists():
        text = service_path.read_text(encoding="utf-8")
        rel = str(service_path.relative_to(root))
        for marker in ("wecom_ability_service", "legacy_flask_facade", "_legacy_app", "flask", "current_app"):
            if marker in text:
                violations.append(Violation("channel_identity_service_legacy_import", rel, marker))
    else:
        violations.append(Violation("channel_identity_service_legacy_import", str(service_path.relative_to(root)), "missing identity_bridge_service.py"))

    if checker_path.exists():
        text = checker_path.read_text(encoding="utf-8")
        allowlist_marker = 'Path("aicrm_next/channel_entry/' + 'identity_bridge.py")'
        if allowlist_marker in text:
            violations.append(Violation("channel_identity_stale_wecom_allowlist", str(checker_path.relative_to(root)), allowlist_marker))

    if test_path.exists():
        text = test_path.read_text(encoding="utf-8")
        rel = str(test_path.relative_to(root))
        for marker in (
            "identity_bridge._legacy_app",
            "wecom_ability_service.db",
            "wecom_ability_service.application.identity_contact",
        ):
            if marker in text:
                violations.append(Violation("channel_identity_test_legacy_monkeypatch", rel, marker))

    return violations


def check_questionnaire_adapters_native_oauth(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    adapters_path = root / "aicrm_next" / "integration_gateway" / "questionnaire_adapters.py"
    client_path = root / "aicrm_next" / "integration_gateway" / "wechat_oauth_client.py"
    checker_path = root / "scripts" / "check_no_new_legacy.py"

    if adapters_path.exists():
        text = adapters_path.read_text(encoding="utf-8")
        rel = str(adapters_path.relative_to(root))
        for marker in (
            "wecom_ability_service",
            "from wecom_ability_service",
            "legacy_flask_facade",
            "wechat_oauth.exchange_wechat_oauth_code",
            "wechat_oauth.fetch_wechat_userinfo",
            "current_app",
            "from flask",
        ):
            if marker in text:
                violations.append(Violation("questionnaire_adapters_legacy_oauth_import", rel, marker))
        if not all(marker in text for marker in ("build_wechat_oauth_client", "WeChatOAuthClientError", "oauth_client_factory")):
            violations.append(Violation("questionnaire_adapters_oauth_injection_missing", rel, "native OAuth client injection markers missing"))
    else:
        violations.append(Violation("questionnaire_adapters_legacy_oauth_import", str(adapters_path.relative_to(root)), "missing questionnaire_adapters.py"))

    if client_path.exists():
        text = client_path.read_text(encoding="utf-8")
        rel = str(client_path.relative_to(root))
        for marker in ("wecom_ability_service", "legacy_flask_facade", "flask", "current_app"):
            if marker in text:
                violations.append(Violation("questionnaire_oauth_client_legacy_import", rel, marker))
    else:
        violations.append(Violation("questionnaire_oauth_client_legacy_import", str(client_path.relative_to(root)), "missing wechat_oauth_client.py"))

    if checker_path.exists():
        text = checker_path.read_text(encoding="utf-8")
        allowlist_marker = 'Path("aicrm_next/integration_gateway/' + 'questionnaire_adapters.py")'
        if allowlist_marker in text:
            violations.append(Violation("questionnaire_adapters_stale_wecom_allowlist", str(checker_path.relative_to(root)), allowlist_marker))

    return violations


def check_public_product_h5_pay_oauth_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    h5_pay_path = root / "aicrm_next" / "public_product" / "h5_wechat_pay.py"

    if not h5_pay_path.exists():
        violations.append(
            Violation(
                "public_product_h5_pay_oauth_native_client_missing",
                str(h5_pay_path.relative_to(root)),
                "missing h5_wechat_pay.py",
            )
        )
        return violations

    text = h5_pay_path.read_text(encoding="utf-8")
    rel = str(h5_pay_path.relative_to(root))
    for marker in (
        "wecom_ability_service.infra.wechat_oauth",
        "exchange_wechat_oauth_code",
        "fetch_wechat_userinfo",
        "WeChatOAuthRequestError",
    ):
        if marker in text:
            violations.append(Violation("public_product_h5_pay_legacy_oauth_import", rel, marker))
    if not all(marker in text for marker in ("build_wechat_oauth_client", "WeChatOAuthClientError")):
        violations.append(
            Violation(
                "public_product_h5_pay_oauth_native_client_missing",
                rel,
                "native WeChat OAuth client markers missing",
            )
        )
    if not any(marker in text for marker in ("set_h5_wechat_pay_oauth_client_factory", "_OAUTH_CLIENT_FACTORY")):
        violations.append(
            Violation(
                "public_product_h5_pay_oauth_injection_missing",
                rel,
                "native WeChat OAuth client injection seam missing",
            )
        )
    return violations


def check_public_product_h5_pay_sidebar_context_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    public_product_dir = root / "aicrm_next" / "public_product"
    h5_pay_path = public_product_dir / "h5_wechat_pay.py"
    signed_context_path = public_product_dir / "signed_context.py"
    sidebar_context_path = public_product_dir / "sidebar_order_context.py"

    if not h5_pay_path.exists():
        violations.append(
            Violation(
                "public_product_h5_pay_context_native_import_missing",
                str(h5_pay_path.relative_to(root)),
                "missing h5_wechat_pay.py",
            )
        )
        return violations

    h5_text = h5_pay_path.read_text(encoding="utf-8")
    h5_rel = str(h5_pay_path.relative_to(root))
    if "wecom_ability_service.infra.signed_context" in h5_text:
        violations.append(
            Violation(
                "public_product_h5_pay_legacy_signed_context_import",
                h5_rel,
                "wecom_ability_service.infra.signed_context",
            )
        )
    if "wecom_ability_service.domains.wechat_pay.sidebar_context" in h5_text:
        violations.append(
            Violation(
                "public_product_h5_pay_legacy_sidebar_context_import",
                h5_rel,
                "wecom_ability_service.domains.wechat_pay.sidebar_context",
            )
        )
    if "from .signed_context import" not in h5_text or "from .sidebar_order_context import" not in h5_text:
        violations.append(
            Violation(
                "public_product_h5_pay_context_native_import_missing",
                h5_rel,
                "native sidebar context imports missing",
            )
        )

    legacy_helper_markers = ("wecom_ability_service", "flask", "current_app", "legacy_flask_facade")
    for helper_path, code in (
        (signed_context_path, "public_product_signed_context_legacy_import"),
        (sidebar_context_path, "public_product_sidebar_order_context_legacy_import"),
    ):
        helper_rel = str(helper_path.relative_to(root))
        if not helper_path.exists():
            violations.append(Violation("public_product_h5_pay_context_native_import_missing", helper_rel, "native helper missing"))
            continue
        helper_text = helper_path.read_text(encoding="utf-8")
        for marker in legacy_helper_markers:
            if marker in helper_text:
                violations.append(Violation(code, helper_rel, marker))

    return violations


def check_public_product_h5_pay_legacy_closeout(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    public_product_dir = root / "aicrm_next" / "public_product"
    h5_pay_path = public_product_dir / "h5_wechat_pay.py"
    signed_context_path = public_product_dir / "signed_context.py"
    sidebar_context_path = public_product_dir / "sidebar_order_context.py"
    checker_path = root / "scripts" / "check_no_new_legacy.py"

    if not h5_pay_path.exists():
        violations.append(
            Violation(
                "public_product_h5_pay_native_import_missing",
                str(h5_pay_path.relative_to(root)),
                "missing h5_wechat_pay.py",
            )
        )
        return violations

    h5_text = h5_pay_path.read_text(encoding="utf-8")
    h5_rel = str(h5_pay_path.relative_to(root))
    for marker in (
        "wecom_ability_service",
        "legacy_flask_facade",
        "forward_to_legacy_flask",
        "production_compat",
        "from flask",
        "current_app",
        "exchange_wechat_oauth_code",
        "fetch_wechat_userinfo",
        "WeChatOAuthRequestError",
        "wecom_ability_service.infra.signed_context",
        "wecom_ability_service.domains.wechat_pay.sidebar_context",
    ):
        if marker in h5_text:
            violations.append(Violation("public_product_h5_pay_legacy_import", h5_rel, marker))

    for marker in (
        "build_wechat_oauth_client",
        "WeChatOAuthClientError",
        "from .signed_context import",
        "from .sidebar_order_context import",
    ):
        if marker not in h5_text:
            violations.append(Violation("public_product_h5_pay_native_import_missing", h5_rel, marker))

    helper_markers = ("wecom_ability_service", "flask", "current_app", "legacy_flask_facade")
    for helper_path, code in (
        (signed_context_path, "public_product_signed_context_legacy_import"),
        (sidebar_context_path, "public_product_sidebar_order_context_legacy_import"),
    ):
        helper_rel = str(helper_path.relative_to(root))
        if not helper_path.exists():
            violations.append(Violation("public_product_h5_pay_native_import_missing", helper_rel, "native helper missing"))
            continue
        helper_text = helper_path.read_text(encoding="utf-8")
        for marker in helper_markers:
            if marker in helper_text:
                violations.append(Violation(code, helper_rel, marker))

    if checker_path.exists():
        checker_text = checker_path.read_text(encoding="utf-8")
        stale_marker = 'Path("aicrm_next/public_product/' + 'h5_wechat_pay.py")'
        if stale_marker in checker_text:
            violations.append(Violation("public_product_h5_pay_stale_wecom_allowlist", str(checker_path.relative_to(root)), stale_marker))

    return violations


def check_wecom_group_adapter_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    adapter_path = root / "aicrm_next/integration_gateway/wecom_group_adapter.py"
    client_path = root / "aicrm_next/integration_gateway/wecom_customer_group_client.py"

    if adapter_path.exists():
        adapter_text = adapter_path.read_text(encoding="utf-8")
        rel = str(adapter_path.relative_to(root))
        for marker in ("legacy_flask_facade", "_legacy_app"):
            if marker in adapter_text:
                violations.append(Violation("wecom_group_adapter_legacy_facade_import", rel, marker))
        for marker in ("legacy_wecom_client_from_app", "wecom_ability_service"):
            if marker in adapter_text:
                violations.append(Violation("wecom_group_adapter_legacy_wecom_client", rel, marker))
        for marker in (
            "legacy_broadcast_enqueue_job",
            "legacy_broadcast_jobs_service",
            "LegacyBroadcastJobQueueGateway",
            "LegacyGroupOpsQueueStatsGateway",
        ):
            if marker in adapter_text:
                violations.append(Violation("wecom_group_adapter_legacy_broadcast_gateway", rel, marker))
        if "def build_group_ops_queue_gateway" in adapter_text and "return NextGroupOpsQueueGateway()" not in adapter_text:
            violations.append(Violation("wecom_group_queue_builder_not_next", rel, "build_group_ops_queue_gateway must return NextGroupOpsQueueGateway"))
        if "def build_group_ops_queue_stats_gateway" in adapter_text and "return NextGroupOpsQueueStatsGateway()" not in adapter_text:
            violations.append(Violation("wecom_group_queue_stats_builder_not_next", rel, "build_group_ops_queue_stats_gateway must return NextGroupOpsQueueStatsGateway"))

    if client_path.exists():
        client_text = client_path.read_text(encoding="utf-8")
        rel = str(client_path.relative_to(root))
        for marker in (
            "legacy_flask_facade",
            "wecom_ability_service",
            "flask",
            "current_app",
            "WeComClient.from_app",
        ):
            if marker in client_text:
                violations.append(Violation("wecom_group_client_legacy_import", rel, marker))

    return violations


def check_ai_assist_external_campaigns_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    service_path = root / "aicrm_next/ai_assist/external_campaigns.py"
    repo_path = root / "aicrm_next/ai_assist/external_campaigns_repo.py"

    if service_path.exists():
        service_text = service_path.read_text(encoding="utf-8")
        rel = str(service_path.relative_to(root))
        for marker in ("_legacy_app", "legacy_flask_facade", "forward_to_legacy_flask"):
            if marker in service_text:
                violations.append(Violation("ai_external_campaigns_legacy_import", rel, marker))
        for marker in (
            "wecom_ability_service",
            "campaign_service",
            "segment_service",
            "automation_member_backfill_service",
            "ensure_campaign_scheduled_jobs",
        ):
            if marker in service_text:
                violations.append(Violation("ai_external_campaigns_legacy_service_orchestration", rel, marker))

    if repo_path.exists():
        repo_text = repo_path.read_text(encoding="utf-8")
        rel = str(repo_path.relative_to(root))
        for marker in (
            "_legacy_app",
            "legacy_flask_facade",
            "wecom_ability_service",
            "flask",
            "current_app",
            "forward_to_legacy_flask",
        ):
            if marker in repo_text:
                violations.append(Violation("ai_external_campaigns_repo_legacy_import", rel, marker))

    expected_registry = {
        "/api/ai-assist/external/campaigns": ("POST",),
        "/api/ai-assist/external/campaigns/{campaign_code}": ("GET",),
    }
    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    for route_path, methods in expected_registry.items():
        record = _record_for_path_and_methods(registry_records, "path_pattern", route_path, methods)
        if record is None:
            violations.append(Violation("ai_external_campaigns_registry_not_locked", route_path, "missing registry record"))
            continue
        if (
            record.get("legacy_fallback_allowed") is not False
            or str(record.get("legacy_source") or "") != ""
            or record.get("delete_status") != "deletion_locked"
            or record.get("replacement_status") != "locked"
        ):
            violations.append(
                Violation(
                    "ai_external_campaigns_registry_not_locked",
                    route_path,
                    (
                        f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')} "
                        f"legacy_source={record.get('legacy_source')} "
                        f"delete_status={record.get('delete_status')} "
                        f"replacement_status={record.get('replacement_status')}"
                    ),
                )
            )

    forbidden_manifest_phrases = (
        "production_compat",
        "legacy_forward",
        "legacy facade",
        "legacy production facade",
    )
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    for route_path, methods in expected_registry.items():
        record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, methods)
        if record is None:
            violations.append(Violation("ai_external_campaigns_manifest_stale_legacy", route_path, "missing manifest record"))
            continue
        phrase = _contains_forbidden_phrase(record.get("notes"), forbidden_manifest_phrases)
        if phrase or record.get("legacy_fallback_allowed") is not False:
            violations.append(
                Violation(
                    "ai_external_campaigns_manifest_stale_legacy",
                    route_path,
                    phrase or f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}",
                )
            )

    return violations


def check_customer_read_model_legacy_deletion(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    customer_read_root = root / "aicrm_next/customer_read_model"
    for path in customer_read_root.rglob("*.py"):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if "legacy_customer_read_facade" in text:
            violations.append(Violation("customer_read_legacy_facade_import", str(rel), "customer_read_model must not import legacy_customer_read_facade"))
        if CUSTOMER_READ_ROLLBACK_FLAG in text:
            violations.append(Violation("customer_read_legacy_rollback_flag", str(rel), "customer read legacy rollback flag has been deleted"))
        if "LegacyShadowCustomerReadModelSource" in text:
            violations.append(Violation("customer_read_legacy_shadow_source", str(rel), "legacy shadow backfill source has been deleted"))

    backfill_script = root / "scripts/backfill_customer_read_model.py"
    if backfill_script.exists():
        text = backfill_script.read_text(encoding="utf-8")
        if "settings.database_url" in text or "get_settings().database_url" in text:
            violations.append(Violation("customer_read_backfill_execute_uses_default_database", str(backfill_script.relative_to(root)), "--execute must use explicit --database-url only"))
        if "legacy-shadow" in text or "LegacyShadowCustomerReadModelSource" in text:
            violations.append(Violation("customer_read_backfill_legacy_source", str(backfill_script.relative_to(root)), "backfill CLI must not expose legacy-shadow source"))

    service = RouteRegistryService()
    protected_paths = {
        "/api/customers",
        "/api/customers/{external_userid}",
        "/api/customers/{external_userid}/timeline",
        "/api/messages/{external_userid}/recent",
        "/admin/customers*",
    }
    for entry in service.list_routes():
        if entry.path_pattern in protected_paths and entry.legacy_fallback_allowed:
            violations.append(Violation("customer_read_route_legacy_fallback_allowed", entry.path_pattern, "customer read routes must not allow legacy fallback after deletion"))
    return violations


def _decorator_route_paths(path: Path) -> list[str]:
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    route_paths: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func
            if not isinstance(attr, ast.Attribute) or attr.attr != "api_route":
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                route_paths.append(first.value)
    return route_paths


def _module_list_constants(tree: ast.AST) -> dict[str, tuple[str, ...]]:
    constants: dict[str, tuple[str, ...]] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        values: list[str] = []
        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value.upper())
        if values:
            constants[node.targets[0].id] = tuple(values)
    return constants


def _decorator_route_methods(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = _module_list_constants(tree)
    route_methods: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func
            if not isinstance(attr, ast.Attribute) or attr.attr != "api_route":
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            methods: tuple[str, ...] = ("GET",)
            for keyword in decorator.keywords:
                if keyword.arg != "methods":
                    continue
                if isinstance(keyword.value, (ast.List, ast.Tuple)):
                    parsed = [
                        str(item.value).upper()
                        for item in keyword.value.elts
                        if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    ]
                    methods = tuple(parsed)
                elif isinstance(keyword.value, ast.Name):
                    methods = constants.get(keyword.value.id, methods)
            route_methods.append((first.value, methods))
    return route_methods


def _decorated_route_function_sources(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    route_sources: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_paths: list[str] = []
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func
            if not isinstance(attr, ast.Attribute) or attr.attr not in {"get", "post", "put", "patch", "delete", "options", "head", "api_route"}:
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                route_paths.append(first.value)
        if not route_paths:
            continue
        source = ast.get_source_segment(text, node) or ""
        for route_path in route_paths:
            route_sources.setdefault(route_path, []).append(source)
    return route_sources


def _function_sources(path: Path, names: set[str]) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    sources: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            sources[node.name] = ast.get_source_segment(text, node) or ""
    return sources


def check_production_compat_routes(root: Path = ROOT) -> list[Violation]:
    service = RouteRegistryService()
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    for route_path, methods in _decorator_route_methods(compat_path):
        registry_lookup_path = {
            "/api/admin/wecom/tags": "/api/admin/wecom/tags*",
            "/api/admin/wecom/tag-groups": "/api/admin/wecom/tag-groups*",
        }.get(route_path, route_path)
        entry = service.find_route(registry_lookup_path, set(methods))
        if not entry:
            violations.append(Violation("production_compat_route_not_registered", str(compat_path.relative_to(root)), route_path))
            continue
        if entry.runtime_owner != "production_compat" and not entry.legacy_fallback_allowed:
            violations.append(Violation("production_compat_route_owner_mismatch", str(compat_path.relative_to(root)), route_path))
        if "{path:path}" in route_path and not entry.legacy_fallback_allowed:
            violations.append(Violation("undocumented_wildcard_fallback", str(compat_path.relative_to(root)), route_path))
    return violations


def check_production_compat_removed(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    checker_path = root / "scripts/check_no_new_legacy.py"
    main_path = root / "aicrm_next/main.py"

    if compat_path.exists():
        violations.append(
            Violation(
                "production_compat_api_file_remaining",
                str(compat_path.relative_to(root)),
                "Remove the empty production_compat router file.",
            )
        )

    if checker_path.exists():
        checker_text = checker_path.read_text(encoding="utf-8")
        stale_allowlist_marker = 'Path("aicrm_next/production_compat/' + 'api.py")'
        if stale_allowlist_marker in checker_text:
            violations.append(
                Violation(
                    "production_compat_stale_allowlist",
                    str(checker_path.relative_to(root)),
                    stale_allowlist_marker,
                    "Remove production_compat/api.py from legacy and side-effect allowlists.",
                )
            )

    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        for marker in ("production_compat", PROD_COMPAT_ROUTER_NAME, PROD_COMPAT_WILDCARD_ROUTER_NAME):
            if marker in main_text:
                violations.append(
                    Violation(
                        "production_compat_main_include_remaining",
                        str(main_path.relative_to(root)),
                        marker,
                        "Do not import or include production_compat in the FastAPI app runtime.",
                    )
                )

    runtime_root = root / "aicrm_next"
    if runtime_root.exists():
        for path in runtime_root.rglob("*.py"):
            if "__pycache__" in path.parts or path == compat_path:
                continue
            text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            imports_removed_module = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports_removed_module = any(alias.name == "aicrm_next.production_compat.api" for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports_removed_module = node.module == "aicrm_next.production_compat.api" or (
                        node.module == "aicrm_next.production_compat" and any(alias.name == "api" for alias in node.names)
                    )
                if imports_removed_module:
                    break
            if imports_removed_module:
                violations.append(
                    Violation(
                        "production_compat_runtime_import_remaining",
                        str(path.relative_to(root)),
                        "aicrm_next.production_compat.api",
                        "Runtime code must not import the removed production_compat API module.",
                    )
                )
    return violations


def check_orphan_legacy_facades_removed(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    facade_paths = {
        "legacy_questionnaire_facade": (
            root / "aicrm_next/integration_gateway/legacy_questionnaire_facade.py",
            "orphan_legacy_questionnaire_facade_file_remaining",
        ),
        "legacy_automation_facade": (
            root / "aicrm_next/integration_gateway/legacy_automation_facade.py",
            "orphan_legacy_automation_facade_file_remaining",
        ),
    }

    for _name, (path, code) in facade_paths.items():
        if path.exists():
            violations.append(
                Violation(
                    code,
                    str(path.relative_to(root)),
                    "Remove orphan legacy facade file.",
                )
            )

    checker_path = root / "scripts/check_no_new_legacy.py"
    if checker_path.exists():
        checker_text = checker_path.read_text(encoding="utf-8")
        for stale_path in (
            'Path("aicrm_next/integration_gateway/legacy_' + 'questionnaire_facade.py")',
            'Path("aicrm_next/integration_gateway/legacy_' + 'automation_facade.py")',
        ):
            if stale_path in checker_text:
                violations.append(
                    Violation(
                        "orphan_legacy_facade_stale_allowlist",
                        str(checker_path.relative_to(root)),
                        stale_path,
                        "Remove orphan questionnaire/automation facades from LEGACY_IMPORT_ALLOWLIST.",
                    )
                )

    runtime_root = root / "aicrm_next"
    if runtime_root.exists():
        for path in runtime_root.rglob("*.py"):
            if "__pycache__" in path.parts or path in {item[0] for item in facade_paths.values()}:
                continue
            text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            imported_facade = ""
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.endswith(".legacy_questionnaire_facade") or alias.name.endswith(".legacy_automation_facade"):
                            imported_facade = alias.name
                            break
                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    if module_name.endswith(".legacy_questionnaire_facade") or module_name.endswith(".legacy_automation_facade"):
                        imported_facade = module_name
                    elif module_name == "aicrm_next.integration_gateway":
                        for alias in node.names:
                            if alias.name in {"legacy_questionnaire_facade", "legacy_automation_facade"}:
                                imported_facade = alias.name
                                break
                if imported_facade:
                    break
            if imported_facade:
                violations.append(
                    Violation(
                        "orphan_legacy_facade_runtime_import",
                        str(path.relative_to(root)),
                        imported_facade,
                        "Runtime code must not import removed orphan legacy facades.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    for record in registry_records:
        legacy_source = str(record.get("legacy_source") or "").strip()
        if legacy_source not in {"legacy_questionnaire_facade", "legacy_automation_facade"}:
            continue
        delete_status = str(record.get("delete_status") or "").strip()
        runtime_owner = str(record.get("runtime_owner") or "").strip()
        legacy_allowed = record.get("legacy_fallback_allowed")
        if delete_status not in {"legacy_deleted", "deletion_locked", "archived"} or legacy_allowed is True or runtime_owner in {
            "production_compat",
            "legacy_forward",
        }:
            violations.append(
                Violation(
                    "orphan_legacy_facade_registry_active_source",
                    str(record.get("route_id") or record.get("path_pattern") or "<unknown>"),
                    f"legacy_source={legacy_source} delete_status={delete_status}",
                    "Registry must not keep removed orphan facades as active legacy sources.",
                )
            )

    return violations


def check_legacy_flask_facade_removed(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    facade_path = root / "aicrm_next/integration_gateway/legacy_flask_facade.py"
    checker_path = root / "scripts/check_no_new_legacy.py"

    if facade_path.exists():
        violations.append(
            Violation(
                "legacy_flask_facade_file_remaining",
                str(facade_path.relative_to(root)),
                "Remove the legacy Flask forwarding facade file.",
            )
        )

    if checker_path.exists():
        checker_text = checker_path.read_text(encoding="utf-8")
        stale_allowlist_marker = 'Path("aicrm_next/integration_gateway/legacy_' + 'flask_facade.py")'
        if stale_allowlist_marker in checker_text:
            violations.append(
                Violation(
                    "legacy_flask_facade_stale_allowlist",
                    str(checker_path.relative_to(root)),
                    stale_allowlist_marker,
                    "Remove legacy_flask_facade.py from LEGACY_IMPORT_ALLOWLIST.",
                )
            )

    runtime_root = root / "aicrm_next"
    frontend_page_shell = root / "aicrm_next/frontend_compat/legacy_routes.py"
    if runtime_root.exists():
        for path in runtime_root.rglob("*.py"):
            if "__pycache__" in path.parts or path in {facade_path, frontend_page_shell}:
                continue
            text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue

            imported_facade = ""
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.endswith(".legacy_flask_facade"):
                            imported_facade = alias.name
                            break
                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module or ""
                    if module_name.endswith(".legacy_flask_facade"):
                        imported_facade = module_name
                    elif module_name == "aicrm_next.integration_gateway":
                        for alias in node.names:
                            if alias.name == "legacy_flask_facade":
                                imported_facade = alias.name
                                break
                if imported_facade:
                    break

            if imported_facade:
                violations.append(
                    Violation(
                        "legacy_flask_facade_runtime_import",
                        str(path.relative_to(root)),
                        imported_facade,
                        "Runtime code must not import removed legacy_flask_facade.",
                    )
                )

            for marker in ("forward_to_legacy_flask", "_legacy_app", "legacy_wecom_client_from_app"):
                if marker in text:
                    violations.append(
                        Violation(
                            "legacy_flask_facade_forwarder_remaining",
                            str(path.relative_to(root)),
                            marker,
                            "Runtime code must not retain legacy Flask facade forwarding symbols.",
                        )
                    )

    for rel_dir in (
        "aicrm_next/automation_engine",
        "aicrm_next/cloud_orchestrator",
        "aicrm_next/platform_foundation",
    ):
        base = root / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "X-AICRM-Compatibility-Facade" in text:
                violations.append(
                    Violation(
                        "legacy_compatibility_facade_header_remaining",
                        str(path.relative_to(root)),
                        "X-AICRM-Compatibility-Facade",
                        "Guarded Next-native route modules must not emit legacy compatibility facade headers.",
                    )
                )

    return violations


def _load_yaml_records(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = payload.get(key) or []
    return [record for record in records if isinstance(record, dict)]


def _load_yaml_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _contains_forbidden_phrase(value: object, phrases: tuple[str, ...]) -> str | None:
    text = str(value or "").lower()
    for phrase in phrases:
        if phrase.lower() in text:
            return phrase
    return None


def check_route_progress_docs_do_not_drift(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    registry_path = root / "docs/architecture/legacy_exit_route_registry.yaml"
    manifest_path = root / "docs/route_ownership/production_route_ownership_manifest.yaml"
    backlog_path = root / "docs/development/legacy_replacement_backlog.yaml"
    registry_records = _load_yaml_records(registry_path, "routes")
    manifest_records = _load_yaml_records(manifest_path, "routes")
    backlog_payload = _load_yaml_payload(backlog_path)
    backlog_entries = [entry for entry in backlog_payload.get("entries") or [] if isinstance(entry, dict)]

    stale_legacy_sources = {
        "legacy_questionnaire_facade",
        "legacy_automation_facade",
        "legacy_sidebar_read_facade",
        "legacy_flask_facade",
        "production_compat",
    }
    next_no_fallback_owners = {"next_native", "next_command", "next_adapter", "next_read_model", "next_runtime_plan"}
    stale_registry_note_phrases = (
        "remain legacy-forwarded",
        "through the legacy production facade",
        "production mode reads",
        "Keep legacy fallback until",
        "legacy production facade",
    )
    stale_manifest_archived_phrases = (
        "remain legacy-forwarded",
        "legacy-forwarded",
        "legacy production facade",
    )
    backlog_keep_legacy_fields = (
        "business_continuity_requirement",
        "replacement_strategy",
        "fallback_required_until",
        "delete_condition",
        "notes",
    )
    manifest_compare_fields = (
        "current_runtime_owner",
        "production_behavior",
        "legacy_fallback_allowed",
        "fixture_allowed_in_production",
        "external_side_effect_risk",
        "checker",
        "notes",
    )

    for record in registry_records:
        label = str(record.get("path_pattern") or record.get("route_id") or "<unknown>")
        if (
            record.get("legacy_fallback_allowed") is False
            and record.get("runtime_owner") in next_no_fallback_owners
            and record.get("legacy_source") in stale_legacy_sources
        ):
            violations.append(Violation("route_progress_stale_legacy_source", label, f"legacy_source={record.get('legacy_source')}"))
        if record.get("legacy_fallback_allowed") is False:
            phrase = _contains_forbidden_phrase(record.get("notes"), stale_registry_note_phrases)
            if phrase:
                violations.append(Violation("route_progress_stale_legacy_note", label, phrase))

    for record in manifest_records:
        label = str(record.get("route_pattern") or "<unknown>")
        if record.get("legacy_fallback_allowed") is False and record.get("production_behavior") == "archived_no_runtime":
            phrase = _contains_forbidden_phrase(record.get("notes"), stale_manifest_archived_phrases)
            if phrase:
                violations.append(Violation("route_progress_manifest_archived_legacy_note", label, phrase))

    if backlog_payload.get("status") != "current_progress_snapshot_no_runtime_change":
        violations.append(Violation("route_progress_backlog_status_stale", str(backlog_path.relative_to(root)), f"status={backlog_payload.get('status')}"))

    manifest_by_pattern: dict[str, list[dict]] = {}
    for record in manifest_records:
        manifest_by_pattern.setdefault(str(record.get("route_pattern") or ""), []).append(record)

    for entry in backlog_entries:
        label = str(entry.get("route_pattern") or entry.get("id") or "<unknown>")
        if entry.get("legacy_fallback_allowed") is False:
            for field in backlog_keep_legacy_fields:
                if "Keep legacy fallback until" in str(entry.get(field) or ""):
                    violations.append(Violation("route_progress_backlog_false_fallback_keeps_legacy", label, field))

        candidates = manifest_by_pattern.get(str(entry.get("route_pattern") or ""), [])
        if not candidates:
            continue
        matching_manifest = None
        entry_methods = tuple(entry.get("methods") or [])
        for candidate in candidates:
            if tuple(candidate.get("methods") or []) == entry_methods:
                matching_manifest = candidate
                break
        if matching_manifest is None and len(candidates) == 1:
            matching_manifest = candidates[0]
        if matching_manifest is None or any(entry.get(field) != matching_manifest.get(field) for field in manifest_compare_fields):
            drift_fields = [
                field
                for field in manifest_compare_fields
                if matching_manifest is None or entry.get(field) != matching_manifest.get(field)
            ]
            violations.append(Violation("route_progress_backlog_manifest_drift", label, ",".join(drift_fields)))

    return violations


def check_internal_run_due_guard_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    guard_path = root / "aicrm_next/platform_foundation/internal_run_due_guard.py"
    automation_api_path = root / "aicrm_next/automation_engine/api.py"
    cloud_api_path = root / "aicrm_next/cloud_orchestrator/api.py"

    if not guard_path.exists():
        violations.append(
            Violation(
                "internal_run_due_guard_missing",
                str(guard_path.relative_to(root)),
                "missing guard module",
                "Add the Next-native internal run-due guard module.",
            )
        )
    else:
        guard_source = guard_path.read_text(encoding="utf-8")
        for marker in ("legacy_flask_facade", "wecom_ability_service", "production_compat", "from flask", "current_app"):
            if marker in guard_source:
                violations.append(
                    Violation(
                        "internal_run_due_guard_legacy_import",
                        str(guard_path.relative_to(root)),
                        marker,
                        "Keep internal run-due guard Next-native with no legacy or Flask imports.",
                    )
                )
        if "X-AICRM-Compatibility-Facade" in guard_source:
            violations.append(
                Violation(
                    "internal_run_due_guard_compatibility_facade_header",
                    str(guard_path.relative_to(root)),
                    "X-AICRM-Compatibility-Facade",
                    "Next-native guard responses must not emit compatibility facade headers.",
                )
            )

    for api_path, code in (
        (automation_api_path, "automation_timer_guard_not_next_native"),
        (cloud_api_path, "cloud_run_due_guard_not_next_native"),
    ):
        if not api_path.exists():
            violations.append(Violation(code, str(api_path.relative_to(root)), "missing api module"))
            continue
        source = api_path.read_text(encoding="utf-8")
        if "maybe_guard_internal_run_due_request" not in source or "aicrm_next.platform_foundation.internal_run_due_guard" not in source:
            violations.append(
                Violation(
                    code,
                    str(api_path.relative_to(root)),
                    "maybe_guard_internal_run_due_request",
                    "Run-due POST routes must use the Next-native internal guard.",
                )
            )
        for marker in ("legacy_flask_facade", "forward_to_legacy_flask"):
            if marker in source:
                violations.append(
                    Violation(
                        "internal_run_due_guard_legacy_import",
                        str(api_path.relative_to(root)),
                        marker,
                        "Run-due route code must not import or call legacy_flask_facade.",
                    )
                )
        if "X-AICRM-Compatibility-Facade" in source:
            violations.append(
                Violation(
                    "internal_run_due_guard_compatibility_facade_header",
                    str(api_path.relative_to(root)),
                    "X-AICRM-Compatibility-Facade",
                    "Run-due route code must not emit compatibility facade headers.",
                )
            )

    return violations


def check_messages_broad_wildcard_deletion(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        text = compat_path.read_text(encoding="utf-8")
        forbidden_decorators = (
            '@wildcard_router.api_route("/api/messages/{path:path}"',
            "@wildcard_router.api_route('/api/messages/{path:path}'",
        )
        for marker in forbidden_decorators:
            if marker in text:
                violations.append(
                    Violation(
                        "messages_broad_wildcard_decorator",
                        str(compat_path.relative_to(root)),
                        marker,
                        "Remove the /api/messages/{path:path} production_compat wildcard; exact Next routes own messages surfaces.",
                    )
                )
        if MESSAGES_BROAD_WILDCARD_RUNTIME in text and "forward_to_legacy_flask" in text:
            violations.append(
                Violation(
                    "messages_broad_wildcard_legacy_forward",
                    str(compat_path.relative_to(root)),
                    MESSAGES_BROAD_WILDCARD_RUNTIME,
                    "Do not reintroduce /api/messages/{path:path} forwarding to the legacy Flask facade.",
                )
            )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_record = next((record for record in registry_records if record.get("path_pattern") == MESSAGES_BROAD_WILDCARD), None)
    if registry_record is None:
        violations.append(
            Violation(
                "messages_broad_wildcard_registry_record_missing",
                "docs/architecture/legacy_exit_route_registry.yaml",
                MESSAGES_BROAD_WILDCARD,
                "Keep a deletion record for /api/messages* and mark it legacy_deleted or deletion_locked.",
            )
        )
    else:
        if registry_record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("messages_broad_wildcard_registry_legacy_allowed", MESSAGES_BROAD_WILDCARD, "legacy_fallback_allowed=true"))
        if registry_record.get("runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("messages_broad_wildcard_registry_owner", MESSAGES_BROAD_WILDCARD, f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("delete_status") not in {"legacy_deleted", "deletion_locked"}:
            violations.append(Violation("messages_broad_wildcard_registry_delete_status", MESSAGES_BROAD_WILDCARD, f"delete_status={registry_record.get('delete_status')}"))
        if registry_record.get("replacement_status") not in {"deleted", "locked"}:
            violations.append(Violation("messages_broad_wildcard_registry_replacement_status", MESSAGES_BROAD_WILDCARD, f"replacement_status={registry_record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_record = next((record for record in manifest_records if record.get("route_pattern") == MESSAGES_BROAD_WILDCARD), None)
    if manifest_record is None:
        violations.append(
            Violation(
                "messages_broad_wildcard_manifest_record_missing",
                "docs/route_ownership/production_route_ownership_manifest.yaml",
                MESSAGES_BROAD_WILDCARD,
                "Keep a production manifest deletion record for /api/messages*.",
            )
        )
    else:
        if manifest_record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("messages_broad_wildcard_manifest_legacy_allowed", MESSAGES_BROAD_WILDCARD, "legacy_fallback_allowed=true"))
        if manifest_record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("messages_broad_wildcard_manifest_legacy_forward", MESSAGES_BROAD_WILDCARD, "production_behavior=legacy_forward"))
        if manifest_record.get("current_runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("messages_broad_wildcard_manifest_owner", MESSAGES_BROAD_WILDCARD, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("delete_ready") is not True:
            violations.append(Violation("messages_broad_wildcard_manifest_not_delete_ready", MESSAGES_BROAD_WILDCARD, f"delete_ready={manifest_record.get('delete_ready')}"))

    return violations


def check_sidebar_readonly_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path in _decorator_route_paths(compat_path):
            if route_path in SIDEBAR_READONLY_ROUTES:
                violations.append(
                    Violation(
                        "sidebar_readonly_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Sidebar readonly exact routes are locked to Next-native owners and must not reappear in production_compat.",
                    )
                )
            if route_path in SIDEBAR_WRITE_ROUTES:
                violations.append(
                    Violation(
                        "sidebar_write_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Sidebar write exact routes are deletion_locked to Next CommandBus and must not reappear in production_compat. JSSDK remains the only sidebar exact production_compat exception in this closeout.",
                    )
                )

    for api_path in [
        root / "aicrm_next/customer_read_model/api.py",
        root / "aicrm_next/identity_contact/api.py",
    ]:
        if not api_path.exists():
            continue
        for route_path, function_sources in _decorated_route_function_sources(api_path).items():
            if route_path not in SIDEBAR_READONLY_ROUTES:
                continue
            for source in function_sources:
                forbidden_markers = {
                    "legacy_sidebar_read_facade": "sidebar_readonly_legacy_facade",
                    "forward_to_legacy_flask": "sidebar_readonly_legacy_forward",
                    "production_compat": "sidebar_readonly_production_compat_reference",
                    "X-AICRM-Compatibility-Facade": "sidebar_readonly_compatibility_facade_header",
                    '"fallback_used": True': "sidebar_readonly_fallback_used_true",
                    "'fallback_used': True": "sidebar_readonly_fallback_used_true",
                }
                for marker, code in forbidden_markers.items():
                    if marker in source:
                        violations.append(
                            Violation(
                                code,
                                str(api_path.relative_to(root)),
                                f"{route_path}: {marker}",
                                "Sidebar readonly route handlers must stay Next-native, must not forward to legacy, and must not expose compatibility facade behavior.",
                            )
                        )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in SIDEBAR_READONLY_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_readonly_registry_record_missing",
                    "docs/architecture/legacy_exit_route_registry.yaml",
                    route_path,
                    "Keep sidebar readonly routes registered and locked as Next-native deletion_locked routes.",
                )
            )
            continue
        if record.get("runtime_owner") != "next_native":
            violations.append(Violation("sidebar_readonly_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_readonly_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("sidebar_readonly_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") not in {"locked", "validated"}:
            violations.append(Violation("sidebar_readonly_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in SIDEBAR_READONLY_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_readonly_manifest_record_missing",
                    "docs/route_ownership/production_route_ownership_manifest.yaml",
                    route_path,
                    "Keep sidebar readonly routes in the production manifest as Next-owned readonly routes.",
                )
            )
            continue
        if record.get("current_runtime_owner") not in {"next", "next_native"}:
            violations.append(Violation("sidebar_readonly_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("sidebar_readonly_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_readonly_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))

    for route_path in SIDEBAR_WRITE_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_write_manifest_record_missing",
                    "docs/route_ownership/production_route_ownership_manifest.yaml",
                    route_path,
                    "Keep sidebar write routes in the production manifest as Next CommandBus locked routes.",
                )
            )
            continue
        behavior = record.get("production_behavior")
        if record.get("current_runtime_owner") not in {"next", "next_native"}:
            violations.append(Violation("sidebar_write_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if behavior == "legacy_forward":
            violations.append(Violation("sidebar_write_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
        if behavior != "next_command":
            violations.append(Violation("sidebar_write_manifest_behavior", route_path, f"production_behavior={behavior}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_write_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True:
            violations.append(Violation("sidebar_write_manifest_not_delete_ready", route_path, f"delete_ready={record.get('delete_ready')}"))

    jssdk_record = manifest_by_path.get(SIDEBAR_JSSDK_ROUTE)
    if jssdk_record is not None:
        if (
            jssdk_record.get("production_behavior") != "next_adapter"
            or jssdk_record.get("delete_ready") is not True
            or jssdk_record.get("legacy_fallback_allowed") is not False
        ):
            violations.append(
                Violation(
                    "sidebar_jssdk_not_locked_by_group15_closeout",
                    SIDEBAR_JSSDK_ROUTE,
                    f"production_behavior={jssdk_record.get('production_behavior')} delete_ready={jssdk_record.get('delete_ready')} legacy_fallback_allowed={jssdk_record.get('legacy_fallback_allowed')}",
                    "Sidebar JSSDK group 15 is deletion_locked on the Next adapter; production_compat rollback must not be restored.",
                )
            )

    for route_path in SIDEBAR_WRITE_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(
                Violation(
                    "sidebar_write_registry_record_missing",
                    "docs/architecture/legacy_exit_route_registry.yaml",
                    route_path,
                    "Keep sidebar write routes registered as deletion_locked Next CommandBus routes.",
                )
            )
            continue
        if record.get("runtime_owner") != "next_native":
            violations.append(Violation("sidebar_write_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_write_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("sidebar_write_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") not in {"locked", "deleted"}:
            violations.append(Violation("sidebar_write_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("sidebar_write_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))

    sidebar_write_api = root / "aicrm_next/sidebar_write/api.py"
    sidebar_write_application = root / "aicrm_next/sidebar_write/application.py"
    for api_path in [sidebar_write_api, sidebar_write_application]:
        if not api_path.exists():
            continue
        text = api_path.read_text(encoding="utf-8")
        forbidden_markers = {
            "X-AICRM-Compatibility-Facade": "sidebar_write_compatibility_facade_header",
            '"fallback_used": True': "sidebar_write_fallback_used_true",
            "'fallback_used': True": "sidebar_write_fallback_used_true",
            '"real_external_call_executed": True': "sidebar_write_real_external_call_true",
            "'real_external_call_executed': True": "sidebar_write_real_external_call_true",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(api_path.relative_to(root)),
                        marker,
                        "Sidebar write routes must not expose compatibility facade behavior, fallback_used=true, or real external calls.",
                    )
                )

    return violations


def check_sidebar_jssdk_next_adapter(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path in _decorator_route_paths(compat_path):
            if route_path == SIDEBAR_JSSDK_ROUTE:
                violations.append(
                    Violation(
                        "sidebar_jssdk_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Remove /api/sidebar/jssdk-config from production_compat; the route is deletion_locked on the Next JSSDK adapter.",
                    )
                )

    inventory_path = root / "docs/architecture/sidebar_jssdk_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("sidebar_jssdk_inventory_missing", str(inventory_path.relative_to(root)), "missing inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend ↔ API ↔ Backend Contract Matrix",
            "/sidebar/bind-mobile",
            "sidebar_customer_workbench.html",
            "sidebar_workbench.js",
            "/api/sidebar/jssdk-config",
            "url",
            "debug",
            "agentid",
            "ok",
            "appId",
            "corpId",
            "timestamp",
            "nonceStr",
            "signature",
            "jsApiList",
            "source_status",
            "adapter_mode",
            "route_owner",
            "fallback_used",
            "real_external_call_executed",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("sidebar_jssdk_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/identity_contact/sidebar_jssdk.py"
    adapter_path = root / "aicrm_next/integration_gateway/wecom_jssdk_adapter.py"
    main_path = root / "aicrm_next/main.py"
    for path, markers in [
        (api_path, ("sidebar_jssdk_config", "build_sidebar_jssdk_config", "HEAD", "OPTIONS")),
        (adapter_path, ("build_sidebar_jssdk_config", "ExternalCallAttempt", "record_event", "real_external_call_executed")),
    ]:
        if not path.exists():
            violations.append(Violation("sidebar_jssdk_module_missing", str(path.relative_to(root)), ",".join(markers)))
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in source:
                violations.append(Violation("sidebar_jssdk_module_marker_missing", str(path.relative_to(root)), marker))
        for forbidden, code in {
            "forward_to_legacy_flask": "sidebar_jssdk_legacy_forward",
            "legacy_flask_facade": "sidebar_jssdk_legacy_facade",
            "production_compat": "sidebar_jssdk_production_compat_reference",
            "X-AICRM-Compatibility-Facade": "sidebar_jssdk_compatibility_facade",
            "requests.": "sidebar_jssdk_direct_http_client",
            "requests": "sidebar_jssdk_direct_http_client",
            "httpx.": "sidebar_jssdk_direct_http_client",
            "httpx": "sidebar_jssdk_direct_http_client",
            '"fallback_used": True': "sidebar_jssdk_fallback_used_true",
            "'fallback_used': True": "sidebar_jssdk_fallback_used_true",
        }.items():
            if forbidden in source:
                violations.append(Violation(code, str(path.relative_to(root)), forbidden))
        normalized = " ".join(source.lower().split())
        for marker in ("default real_enabled", "real_enabled default", "return 'real_enabled' # default", 'return "real_enabled" # default'):
            if marker in normalized:
                violations.append(
                    Violation(
                        "sidebar_jssdk_default_real_enabled",
                        str(path.relative_to(root)),
                        marker,
                        "Sidebar JSSDK production default must stay real_blocked; real signing requires the explicit real_enabled gate.",
                    )
                )

    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        if "sidebar_jssdk_router" not in main_text:
            violations.append(Violation("sidebar_jssdk_router_not_included", str(main_path.relative_to(root)), "sidebar_jssdk_router"))
        elif PROD_COMPAT_ROUTER_NAME in main_text and main_text.index("sidebar_jssdk_router") > main_text.index(PROD_COMPAT_ROUTER_NAME):
            violations.append(
                Violation(
                    "sidebar_jssdk_router_order",
                    str(main_path.relative_to(root)),
                    f"sidebar_jssdk_router must be included before {PROD_COMPAT_ROUTER_NAME}",
                )
            )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_route = {(record.get("path_pattern"), tuple(record.get("methods") or [])): record for record in registry_records}
    registry_record = registry_by_route.get((SIDEBAR_JSSDK_ROUTE, ("GET", "HEAD", "OPTIONS")))
    if registry_record is None:
        violations.append(Violation("sidebar_jssdk_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", SIDEBAR_JSSDK_ROUTE))
    else:
        if registry_record.get("runtime_owner") != "next_adapter":
            violations.append(Violation("sidebar_jssdk_registry_owner", SIDEBAR_JSSDK_ROUTE, f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_jssdk_registry_legacy_allowed", SIDEBAR_JSSDK_ROUTE, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
        if registry_record.get("legacy_source") == "production_compat":
            violations.append(Violation("sidebar_jssdk_registry_legacy_source", SIDEBAR_JSSDK_ROUTE, "legacy_source=production_compat"))
        if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
            violations.append(Violation("sidebar_jssdk_registry_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))
        if registry_record.get("delete_status") == "next_primary_with_legacy_rollback" or registry_record.get("replacement_status") == "validating":
            violations.append(Violation("sidebar_jssdk_registry_rollback_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))
        if registry_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("sidebar_jssdk_registry_adapter_mode", SIDEBAR_JSSDK_ROUTE, f"adapter_mode={registry_record.get('adapter_mode')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_route = {(record.get("route_pattern"), tuple(record.get("methods") or [])): record for record in manifest_records}
    manifest_record = manifest_by_route.get((SIDEBAR_JSSDK_ROUTE, ("GET", "HEAD", "OPTIONS")))
    if manifest_record is None:
        violations.append(Violation("sidebar_jssdk_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", SIDEBAR_JSSDK_ROUTE))
    else:
        if manifest_record.get("current_runtime_owner") != "next_adapter":
            violations.append(Violation("sidebar_jssdk_manifest_owner", SIDEBAR_JSSDK_ROUTE, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("production_behavior") != "next_adapter":
            violations.append(Violation("sidebar_jssdk_manifest_behavior", SIDEBAR_JSSDK_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("sidebar_jssdk_manifest_legacy_forward", SIDEBAR_JSSDK_ROUTE, "production_behavior=legacy_forward"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("sidebar_jssdk_manifest_legacy_allowed", SIDEBAR_JSSDK_ROUTE, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("delete_ready") is not True:
            violations.append(Violation("sidebar_jssdk_manifest_delete_ready", SIDEBAR_JSSDK_ROUTE, f"delete_ready={manifest_record.get('delete_ready')}"))
        if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
            violations.append(Violation("sidebar_jssdk_manifest_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
        if manifest_record.get("delete_status") == "next_primary_with_legacy_rollback" or manifest_record.get("replacement_status") == "validating":
            violations.append(Violation("sidebar_jssdk_manifest_rollback_lifecycle", SIDEBAR_JSSDK_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
        if manifest_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("sidebar_jssdk_manifest_adapter_mode", SIDEBAR_JSSDK_ROUTE, f"adapter_mode={manifest_record.get('adapter_mode')}"))

    return violations


def check_user_ops_next_native_preview(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path.startswith("/api/admin/user-ops") or route_path.startswith("/admin/user-ops"):
                violations.append(
                    Violation(
                        "user_ops_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "User Ops group 6 routes must stay in Next ops_enrollment/frontend_compat and must not be added to production_compat.",
                    )
                )

    ops_root = root / "aicrm_next/ops_enrollment"
    for path in ops_root.rglob("*.py") if ops_root.exists() else []:
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        forbidden_markers = {
            "forward_to_legacy_flask": "user_ops_legacy_forward",
            "legacy_flask_facade": "user_ops_legacy_facade",
            '"fallback_used": True': "user_ops_fallback_used_true",
            "'fallback_used': True": "user_ops_fallback_used_true",
            '"real_external_call_executed": True': "user_ops_real_external_call_true",
            "'real_external_call_executed': True": "user_ops_real_external_call_true",
            "real_enabled": "user_ops_real_enabled_marker",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(rel),
                        marker,
                        "User Ops read/preview routes must not use legacy forward, fallback_used=true, or real external-call enablement.",
                    )
                )
    application_path = ops_root / "application.py"
    if application_path.exists():
        preview_sources = _function_sources(application_path, {"_handle_broadcast_preview", "_handle_export_preview"})
        forbidden_preview_markers = {
            "real_external_call_executed=true": "user_ops_preview_real_external_call_true",
            "real_external_call_executed': true": "user_ops_preview_real_external_call_true",
            'real_external_call_executed": true': "user_ops_preview_real_external_call_true",
            "real_enabled default": "user_ops_preview_real_enabled_default",
            "default real_enabled": "user_ops_preview_real_enabled_default",
            "send_private_message(": "user_ops_preview_direct_wecom_send",
            "dispatch_wecom_task(": "user_ops_preview_direct_wecom_send",
            "requests.post(": "user_ops_preview_direct_wecom_send",
            "httpx.post(": "user_ops_preview_direct_wecom_send",
            "open(": "user_ops_preview_direct_storage_write",
            "write_text(": "user_ops_preview_direct_storage_write",
            "write_bytes(": "user_ops_preview_direct_storage_write",
            "upload_file(": "user_ops_preview_direct_storage_write",
        }
        for function_name, source in preview_sources.items():
            normalized = " ".join(source.lower().split())
            for marker, code in forbidden_preview_markers.items():
                if marker in normalized:
                    violations.append(
                        Violation(
                            code,
                            str(application_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "User Ops preview handlers must stay SideEffectPlan-only with real external calls and storage writes blocked.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    readonly_records = {"/admin/user-ops": "frontend_compat", **{route: "next_native" for route in USER_OPS_READONLY_ROUTES}}
    for route_path, expected_owner in readonly_records.items():
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_registry_readonly_record_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != expected_owner:
            violations.append(Violation("user_ops_registry_readonly_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_registry_readonly_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("user_ops_registry_readonly_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_registry_readonly_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    for record in registry_records:
        route_path = str(record.get("path_pattern") or "")
        if not (route_path.startswith("/api/admin/user-ops") or route_path.startswith("/admin/user-ops")):
            continue
        if route_path in {"/api/admin/user-ops*", "/admin/user-ops*"}:
            continue
        if record.get("runtime_owner") == "production_compat" or record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("user_ops_registry_legacy_rollback_reintroduced", route_path, f"runtime_owner={record.get('runtime_owner')} legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
    for route_path in USER_OPS_PREVIEW_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_preview_registry_record_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != "next_native":
            violations.append(Violation("user_ops_preview_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_preview_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("user_ops_preview_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("user_ops_preview_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_preview_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in readonly_records:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_manifest_readonly_record_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") == "production_compat" or record.get("production_behavior") == "legacy_forward" or record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_manifest_readonly_legacy_forward", route_path, f"current_runtime_owner={record.get('current_runtime_owner')} production_behavior={record.get('production_behavior')} legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_manifest_readonly_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    for record in manifest_records:
        route_path = str(record.get("route_pattern") or "")
        if not (route_path.startswith("/api/admin/user-ops") or route_path.startswith("/admin/user-ops")):
            continue
        if route_path in {"/api/admin/user-ops*", "/admin/user-ops*"}:
            continue
        if record.get("current_runtime_owner") == "production_compat" or record.get("production_behavior") == "legacy_forward" or record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("user_ops_manifest_legacy_rollback_reintroduced", route_path, f"current_runtime_owner={record.get('current_runtime_owner')} production_behavior={record.get('production_behavior')} legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
    for route_path in USER_OPS_PREVIEW_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("user_ops_preview_manifest_record_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("user_ops_preview_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("user_ops_preview_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("user_ops_preview_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("user_ops_preview_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
    return violations


def check_questionnaire_admin_read_next_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in QUESTIONNAIRE_ADMIN_READ_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_admin_read_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire admin read routes must stay in questionnaire Next read model code, not production_compat.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    if api_path.exists():
        sources = _function_sources(
            api_path,
            {
                "list_questionnaires",
                "get_questionnaire",
                "get_questionnaire_questions",
                "get_questionnaire_results",
                "get_questionnaire_submissions",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_admin_read_legacy_forward",
            "list_questionnaires_from_legacy": "questionnaire_admin_read_legacy_facade",
            "get_questionnaire_detail_from_legacy": "questionnaire_admin_read_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_admin_read_compatibility_facade",
            '"fallback_used": True': "questionnaire_admin_read_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_read_fallback_used_true",
            "create_questionnaire_in_legacy": "questionnaire_admin_read_write_facade",
            "update_questionnaire_in_legacy": "questionnaire_admin_read_write_facade",
            "delete_questionnaire_in_legacy": "questionnaire_admin_read_write_facade",
            "requests.post(": "questionnaire_admin_read_direct_external_call",
            "httpx.post(": "questionnaire_admin_read_direct_external_call",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire admin read handlers must stay Next-query/read-model only with no legacy forward or direct side effects.",
                        )
                    )

    admin_pages_path = root / "aicrm_next/questionnaire/admin_pages.py"
    if admin_pages_path.exists():
        sources = _function_sources(
            admin_pages_path,
            {
                "admin_questionnaires",
                "admin_questionnaires_legacy_ui_alias",
                "admin_questionnaire_new",
                "admin_questionnaire_detail",
                "_questionnaire_editor_response",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_admin_read_page_legacy_forward",
            "list_questionnaires_from_legacy": "questionnaire_admin_read_page_legacy_facade",
            "get_questionnaire_detail_from_legacy": "questionnaire_admin_read_page_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_admin_read_page_compatibility_facade",
            '"fallback_used": True': "questionnaire_admin_read_page_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_read_page_fallback_used_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(admin_pages_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire admin read pages must stay Next-query/read-model only with no legacy forward, compatibility facade, or fallback_used=true.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in QUESTIONNAIRE_ADMIN_READ_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_admin_read_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        expected_owner = "next_native"
        if record.get("runtime_owner") != expected_owner:
            violations.append(Violation("questionnaire_admin_read_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_read_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source"):
            violations.append(Violation("questionnaire_admin_read_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("questionnaire_admin_read_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_read_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))

    for route_path in QUESTIONNAIRE_OUT_OF_SCOPE_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            continue
        if record.get("delete_status") == "deletion_locked" or record.get("replacement_status") == "locked":
            violations.append(Violation("questionnaire_out_of_scope_route_locked", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in QUESTIONNAIRE_ADMIN_READ_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_admin_read_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") not in {"next", "next_native", "frontend_compat"}:
            violations.append(Violation("questionnaire_admin_read_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("questionnaire_admin_read_manifest_legacy_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("production_behavior") != "next_read_model_only":
            violations.append(Violation("questionnaire_admin_read_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_read_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_read_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_questionnaire_admin_write_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path.startswith("/api/admin/questionnaires") and route_path not in QUESTIONNAIRE_ADMIN_READ_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_admin_write_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire admin write routes are deletion_locked to Next CommandBus; do not add production_compat handlers.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    if api_path.exists():
        sources = _function_sources(
            api_path,
            {
                "create_questionnaire",
                "update_questionnaire",
                "duplicate_questionnaire",
                "publish_questionnaire",
                "disable_questionnaire",
                "enable_questionnaire",
                "delete_questionnaire",
                "export_questionnaire",
                "export_questionnaire_preview",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_admin_write_legacy_forward",
            "legacy_questionnaire_facade": "questionnaire_admin_write_legacy_facade",
            "create_questionnaire_in_legacy": "questionnaire_admin_write_legacy_facade",
            "update_questionnaire_in_legacy": "questionnaire_admin_write_legacy_facade",
            "delete_questionnaire_in_legacy": "questionnaire_admin_write_legacy_facade",
            "set_questionnaire_enabled_in_legacy": "questionnaire_admin_write_legacy_facade",
            "export_questionnaire_from_legacy": "questionnaire_admin_write_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_admin_write_compatibility_facade",
            '"fallback_used": True': "questionnaire_admin_write_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_write_fallback_used_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire admin write handlers must execute Next CommandBus commands without legacy forward or compatibility facade behavior.",
                        )
                    )

    write_root = root / "aicrm_next/questionnaire"
    for path in [write_root / "admin_write.py", api_path]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        forbidden_markers = {
            '"fallback_used": True': "questionnaire_admin_write_fallback_used_true",
            "'fallback_used': True": "questionnaire_admin_write_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_admin_write_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_admin_write_real_external_call_true",
            "real_enabled": "questionnaire_admin_write_real_enabled_marker",
            "requests.post(": "questionnaire_admin_write_direct_external_call",
            "httpx.post(": "questionnaire_admin_write_direct_external_call",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(path.relative_to(root)),
                        marker,
                        "Questionnaire admin write commands must not expose fallback_used=true, real external calls, or real-enabled adapter behavior.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    write_family = registry_by_path.get("/api/admin/questionnaires*")
    if write_family is None:
        violations.append(Violation("questionnaire_admin_write_registry_family_missing", "docs/architecture/legacy_exit_route_registry.yaml", "/api/admin/questionnaires*"))
    else:
        if write_family.get("runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_admin_write_registry_owner", "/api/admin/questionnaires*", f"runtime_owner={write_family.get('runtime_owner')}"))
        if write_family.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_admin_write_registry_legacy_allowed", "/api/admin/questionnaires*", f"legacy_fallback_allowed={write_family.get('legacy_fallback_allowed')}"))
        if write_family.get("legacy_source") != "":
            violations.append(Violation("questionnaire_admin_write_registry_legacy_source", "/api/admin/questionnaires*", f"legacy_source={write_family.get('legacy_source')}"))
        if write_family.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_admin_write_registry_adapter_mode", "/api/admin/questionnaires*", f"adapter_mode={write_family.get('adapter_mode')}"))
        if write_family.get("delete_status") != "deletion_locked":
            violations.append(Violation("questionnaire_admin_write_registry_delete_status", "/api/admin/questionnaires*", f"delete_status={write_family.get('delete_status')}"))
        if write_family.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_admin_write_registry_replacement_status", "/api/admin/questionnaires*", f"replacement_status={write_family.get('replacement_status')}"))
        notes = str(write_family.get("notes") or "")
        if "CommandBus" not in notes or "legacy rollback removed" not in notes:
            violations.append(Violation("questionnaire_admin_write_registry_notes", "/api/admin/questionnaires*", notes))

    export_record = registry_by_path.get("/api/admin/questionnaires/{questionnaire_id}/export")
    if export_record is None:
        violations.append(Violation("questionnaire_admin_export_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "/api/admin/questionnaires/{questionnaire_id}/export"))
    elif (
        export_record.get("runtime_owner") != "next_command"
        or export_record.get("legacy_fallback_allowed") is not False
        or export_record.get("adapter_mode") != "real_blocked"
        or export_record.get("delete_status") != "deletion_locked"
        or export_record.get("replacement_status") != "locked"
    ):
        violations.append(
            Violation(
                "questionnaire_admin_export_registry_lifecycle",
                "/api/admin/questionnaires/{questionnaire_id}/export",
                f"runtime_owner={export_record.get('runtime_owner')} legacy_fallback_allowed={export_record.get('legacy_fallback_allowed')} adapter_mode={export_record.get('adapter_mode')} delete_status={export_record.get('delete_status')} replacement_status={export_record.get('replacement_status')}",
            )
        )

    external_push_route = "/admin/questionnaires*external-push-logs*"
    external_push_record = registry_by_path.get(external_push_route)
    if external_push_record is None:
        violations.append(Violation("questionnaire_external_push_logs_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", external_push_route))
    elif (
        external_push_record.get("runtime_owner") != "next_native"
        or external_push_record.get("legacy_fallback_allowed") is not False
        or external_push_record.get("legacy_source") != ""
        or external_push_record.get("adapter_mode") != "real_blocked"
        or external_push_record.get("delete_status") != "deletion_locked"
        or external_push_record.get("replacement_status") != "locked"
    ):
        violations.append(
            Violation(
                "questionnaire_external_push_logs_registry_lifecycle",
                external_push_route,
                f"runtime_owner={external_push_record.get('runtime_owner')} legacy_fallback_allowed={external_push_record.get('legacy_fallback_allowed')} legacy_source={external_push_record.get('legacy_source')} adapter_mode={external_push_record.get('adapter_mode')} delete_status={external_push_record.get('delete_status')} replacement_status={external_push_record.get('replacement_status')}",
            )
        )
    admin_pages_path = root / "aicrm_next/questionnaire/admin_pages.py"
    if admin_pages_path.exists():
        admin_pages_source = admin_pages_path.read_text(encoding="utf-8")
        try:
            start = admin_pages_source.index('"/admin/questionnaires/external-push-logs"')
            route_block = admin_pages_source[start:]
        except ValueError:
            violations.append(Violation("questionnaire_external_push_logs_route_block_missing", str(admin_pages_path.relative_to(root)), external_push_route))
        else:
            if "forward_to_legacy_flask" in route_block:
                violations.append(Violation("questionnaire_external_push_logs_legacy_forward", str(admin_pages_path.relative_to(root)), "forward_to_legacy_flask"))
            for marker in [
                "QuestionnaireExternalPushLogReadService",
                "QuestionnaireExternalPushRetryService",
                "QuestionnaireExternalPushRetryCommand",
                "QuestionnaireExternalPushRetryBatchCommand",
            ]:
                if marker not in admin_pages_source:
                    violations.append(Violation("questionnaire_external_push_logs_next_service_missing", str(admin_pages_path.relative_to(root)), marker))
    else:
        violations.append(Violation("questionnaire_external_push_logs_native_page_missing", str(admin_pages_path.relative_to(root)), external_push_route))

    frontend_routes_path = root / "aicrm_next/frontend_compat/legacy_routes.py"
    if frontend_routes_path.exists():
        frontend_source = frontend_routes_path.read_text(encoding="utf-8")
        if "/admin/questionnaires/external-push-logs" in frontend_source:
            violations.append(
                Violation(
                    "questionnaire_external_push_logs_frontend_compat_route",
                    str(frontend_routes_path.relative_to(root)),
                    external_push_route,
                )
            )

    shell_endpoint_markers = [
        "api.admin_console_global_questionnaire_external_push_logs",
        "api.admin_console_questionnaire_external_push_logs",
    ]
    for shell_path in [
        root / "aicrm_next/frontend_compat/admin_shell.py",
        root / "aicrm_next/admin_jobs/shell.py",
    ]:
        if not shell_path.exists():
            continue
        shell_source = shell_path.read_text(encoding="utf-8")
        for marker in shell_endpoint_markers:
            if marker in shell_source:
                violations.append(
                    Violation(
                        "questionnaire_external_push_logs_admin_shell_mapping",
                        str(shell_path.relative_to(root)),
                        marker,
                    )
                )

    next_template_path = root / "aicrm_next/questionnaire/templates/admin_console/questionnaire_external_push_logs.html"
    if next_template_path.exists():
        next_template_source = next_template_path.read_text(encoding="utf-8")
        for marker in shell_endpoint_markers:
            if marker in next_template_source:
                violations.append(
                    Violation(
                        "questionnaire_external_push_logs_template_shell_endpoint",
                        str(next_template_path.relative_to(root)),
                        marker,
                    )
                )

    retired_legacy_paths = [
        root / "wecom_ability_service/http/admin_questionnaire_push_logs.py",
        root / "wecom_ability_service/templates/admin_console/questionnaire_external_push_logs.html",
    ]
    for retired_path in retired_legacy_paths:
        if retired_path.exists():
            violations.append(
                Violation(
                    "questionnaire_external_push_logs_legacy_file_retained",
                    str(retired_path.relative_to(root)),
                    "retired Flask external-push-log surface must stay deleted",
                )
            )
    legacy_http_init = root / "wecom_ability_service/http/__init__.py"
    if legacy_http_init.exists():
        http_init_source = legacy_http_init.read_text(encoding="utf-8")
        if "admin_questionnaire_push_logs" in http_init_source:
            violations.append(
                Violation(
                    "questionnaire_external_push_logs_legacy_registrar",
                    str(legacy_http_init.relative_to(root)),
                    "admin_questionnaire_push_logs",
                )
            )
    legacy_admin_console_service = root / "wecom_ability_service/domains/admin_console/service.py"
    if legacy_admin_console_service.exists():
        legacy_service_source = legacy_admin_console_service.read_text(encoding="utf-8")
        for marker in [
            "build_questionnaire_external_push_logs_payload",
            "build_global_questionnaire_external_push_logs_payload",
            "retry_questionnaire_external_push_log_for_console",
            "retry_questionnaire_external_push_logs_for_console",
        ]:
            if marker in legacy_service_source:
                violations.append(
                    Violation(
                        "questionnaire_external_push_logs_legacy_console_helper",
                        str(legacy_admin_console_service.relative_to(root)),
                        marker,
                    )
                )

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in ["/api/admin/questionnaires*", "/api/admin/questionnaires/{questionnaire_id}/export"]:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_admin_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_admin_write_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        expected_behavior = "next_command" if route_path == "/api/admin/questionnaires*" else "next_command"
        if record.get("production_behavior") != expected_behavior:
            violations.append(Violation("questionnaire_admin_write_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        expected_fallback = False
        if record.get("legacy_fallback_allowed") is not expected_fallback:
            violations.append(Violation("questionnaire_admin_write_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_admin_write_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        expected_delete_status = "deletion_locked"
        expected_replacement_status = "locked"
        if record.get("delete_status") != expected_delete_status or record.get("replacement_status") != expected_replacement_status:
            violations.append(Violation("questionnaire_admin_write_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    external_push_manifest = manifest_by_path.get(external_push_route)
    if external_push_manifest is None:
        violations.append(Violation("questionnaire_external_push_logs_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", external_push_route))
    elif (
        external_push_manifest.get("current_runtime_owner") != "next_native"
        or external_push_manifest.get("production_behavior") != "next_native"
        or external_push_manifest.get("legacy_fallback_allowed") is not False
        or external_push_manifest.get("adapter_mode") != "real_blocked"
        or external_push_manifest.get("delete_status") != "deletion_locked"
        or external_push_manifest.get("replacement_status") != "locked"
    ):
        violations.append(
            Violation(
                "questionnaire_external_push_logs_manifest_lifecycle",
                external_push_route,
                f"current_runtime_owner={external_push_manifest.get('current_runtime_owner')} production_behavior={external_push_manifest.get('production_behavior')} legacy_fallback_allowed={external_push_manifest.get('legacy_fallback_allowed')} adapter_mode={external_push_manifest.get('adapter_mode')} delete_status={external_push_manifest.get('delete_status')} replacement_status={external_push_manifest.get('replacement_status')}",
            )
        )
    return violations


def check_questionnaire_h5_submit_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in QUESTIONNAIRE_H5_COMMAND_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_h5_submit_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire H5 submit/diagnostics are deletion_locked to Next CommandBus; do not re-add production_compat exact handlers.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    if api_path.exists():
        sources = _function_sources(
            api_path,
            {
                "public_submit_questionnaire",
                "public_questionnaire_client_diagnostics",
                "_execute_h5_submit",
                "_execute_h5_diagnostics",
            },
        )
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_h5_submit_legacy_forward",
            "legacy_questionnaire_facade": "questionnaire_h5_submit_legacy_facade",
            "X-AICRM-Compatibility-Facade": "questionnaire_h5_submit_compatibility_facade",
            '"fallback_used": True': "questionnaire_h5_submit_fallback_used_true",
            "'fallback_used': True": "questionnaire_h5_submit_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_h5_submit_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_h5_submit_real_external_call_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "Questionnaire H5 submit/diagnostics handlers must execute Next CommandBus commands without legacy forward, compatibility facade, fallback_used=true, or real external calls.",
                        )
                    )

    for path in [root / "aicrm_next/questionnaire/h5_write.py", api_path]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        forbidden_markers = {
            '"fallback_used": True': "questionnaire_h5_submit_fallback_used_true",
            "'fallback_used': True": "questionnaire_h5_submit_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_h5_submit_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_h5_submit_real_external_call_true",
            "send_private_message(": "questionnaire_h5_submit_direct_wecom_mutation",
            "dispatch_wecom_task(": "questionnaire_h5_submit_direct_wecom_mutation",
            "mark_contact_tags(": "questionnaire_h5_submit_direct_wecom_mutation",
            "external_push_delivery": "questionnaire_h5_submit_external_push_execution",
            "execute_external_push": "questionnaire_h5_submit_external_push_execution",
            "requests.post(": "questionnaire_h5_submit_direct_external_call",
            "httpx.post(": "questionnaire_h5_submit_direct_external_call",
            "X-AICRM-Compatibility-Facade": "questionnaire_h5_submit_compatibility_facade",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(path.relative_to(root)),
                        marker,
                        "Questionnaire H5 submit/diagnostics must stay on the Next CommandBus with no compatibility facade or direct API-layer external calls.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in QUESTIONNAIRE_H5_COMMAND_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_h5_submit_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_h5_submit_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_h5_submit_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") in {"production_compat", "legacy_questionnaire_facade"}:
            violations.append(Violation("questionnaire_h5_submit_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
        expected_adapter_mode = "real_enabled" if route_path == "/api/h5/questionnaires/{slug}/submit" else "real_blocked"
        if record.get("adapter_mode") != expected_adapter_mode:
            violations.append(Violation("questionnaire_h5_submit_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_h5_submit_registry_rollback_lifecycle", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("delete_status") != "deletion_locked":
            violations.append(Violation("questionnaire_h5_submit_registry_delete_status", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_h5_submit_registry_replacement_status", route_path, f"replacement_status={record.get('replacement_status')}"))
        notes = str(record.get("notes") or "")
        if "CommandBus" not in notes or "legacy rollback removed" not in notes:
            violations.append(Violation("questionnaire_h5_submit_registry_notes", route_path, notes))
        elif route_path == "/api/h5/questionnaires/{slug}/submit" and "configured questionnaire external push executes" not in notes:
            violations.append(Violation("questionnaire_h5_submit_registry_notes", route_path, notes))
        elif route_path != "/api/h5/questionnaires/{slug}/submit" and "real_external_call_executed=false" not in notes:
            violations.append(Violation("questionnaire_h5_submit_registry_notes", route_path, notes))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in QUESTIONNAIRE_H5_COMMAND_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_h5_submit_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_command":
            violations.append(Violation("questionnaire_h5_submit_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("questionnaire_h5_submit_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_h5_submit_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True:
            violations.append(Violation("questionnaire_h5_submit_manifest_not_delete_ready", route_path, f"delete_ready={record.get('delete_ready')}"))
        expected_adapter_mode = "real_enabled" if route_path == "/api/h5/questionnaires/{slug}/submit" else "real_blocked"
        if record.get("adapter_mode") != expected_adapter_mode:
            violations.append(Violation("questionnaire_h5_submit_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_h5_submit_manifest_rollback_lifecycle", route_path, f"delete_status={record.get('delete_status')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_h5_submit_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_questionnaire_oauth_next_adapter(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
                violations.append(
                    Violation(
                        "questionnaire_oauth_production_compat_exact_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Questionnaire OAuth start/callback exact routes must stay Next adapter primary; keep only wildcard/out-of-scope legacy rollback.",
                    )
                )

    api_path = root / "aicrm_next/questionnaire/api.py"
    oauth_path = root / "aicrm_next/questionnaire/oauth.py"
    if api_path.exists():
        sources = _function_sources(api_path, {"wechat_oauth_start", "wechat_oauth_callback", "wechat_oauth_start_options", "wechat_oauth_callback_options"})
        forbidden_markers = {
            "forward_to_legacy_flask": "questionnaire_oauth_legacy_forward",
            "X-AICRM-Compatibility-Facade": "questionnaire_oauth_compatibility_facade",
            '"fallback_used": True': "questionnaire_oauth_fallback_used_true",
            "'fallback_used': True": "questionnaire_oauth_fallback_used_true",
            '"real_external_call_executed": True': "questionnaire_oauth_real_external_call_true",
            "'real_external_call_executed': True": "questionnaire_oauth_real_external_call_true",
        }
        for function_name, source in sources.items():
            for marker, code in forbidden_markers.items():
                if marker in source:
                    violations.append(Violation(code, str(api_path.relative_to(root)), f"{function_name}:{marker}"))

    if oauth_path.exists():
        text = oauth_path.read_text(encoding="utf-8")
        forbidden_markers = {
            "requests.post(": "questionnaire_oauth_direct_external_call",
            "httpx.post(": "questionnaire_oauth_direct_external_call",
            "access_token\":": "questionnaire_oauth_token_leak_marker",
            "app_secret\":": "questionnaire_oauth_token_leak_marker",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(Violation(code, str(oauth_path.relative_to(root)), marker))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    for route_path in QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_oauth_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
            continue
        if record.get("runtime_owner") != "next_adapter":
            violations.append(Violation("questionnaire_oauth_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_oauth_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") in {"production_compat", "legacy_questionnaire_facade"}:
            violations.append(Violation("questionnaire_oauth_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_oauth_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("questionnaire_oauth_registry_production_compat_owner", route_path, "runtime_owner=production_compat"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_oauth_registry_rollback_lifecycle", route_path, "delete_status=next_primary_with_legacy_rollback"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_oauth_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("questionnaire_oauth_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_adapter":
            violations.append(Violation("questionnaire_oauth_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "production_compat"}:
            violations.append(Violation("questionnaire_oauth_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("questionnaire_oauth_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("questionnaire_oauth_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("current_runtime_owner") == "production_compat":
            violations.append(Violation("questionnaire_oauth_manifest_production_compat_owner", route_path, "current_runtime_owner=production_compat"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("questionnaire_oauth_manifest_rollback_lifecycle", route_path, "delete_status=next_primary_with_legacy_rollback"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("questionnaire_oauth_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
    return violations


def check_auth_wecom_wildcard_inventory(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/auth_wecom_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "auth_wecom_inventory_missing",
                "docs/architecture/auth_wecom_route_inventory.md",
                "missing inventory document",
                "Add docs/architecture/auth_wecom_route_inventory.md before retaining or replacing auth/wecom wildcard routes.",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path in AUTH_WECOM_EXACT_ROUTES + AUTH_WECOM_WILDCARD_ROUTES + QUESTIONNAIRE_OAUTH_EXACT_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("auth_wecom_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths):
            if route_path in AUTH_WECOM_EXACT_ROUTES:
                violations.append(
                    Violation(
                        "auth_wecom_production_compat_exact_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Known auth/wecom and OAuth probe exact routes must stay Next-owned with no production_compat fallback.",
                    )
                )
            if route_path in AUTH_WECOM_WILDCARD_ROUTES:
                violations.append(
                    Violation(
                        "auth_wecom_deleted_wildcard_reintroduced",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Auth/wecom and OAuth wildcard fallbacks are deleted and locked; do not re-add production_compat wildcard decorators.",
                    )
                )
            if (
                (route_path.startswith("/auth/wecom") or route_path.startswith("/api/h5/wechat/oauth"))
                and "{path:path}" in route_path
            ):
                violations.append(
                    Violation(
                        "auth_wecom_unregistered_wildcard",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Do not add new auth/wecom or OAuth wildcard routes; inventory exact paths and register them explicitly.",
                    )
                )

    auth_api_path = root / "aicrm_next/auth_wecom/api.py"
    if auth_api_path.exists():
        text = auth_api_path.read_text(encoding="utf-8")
        forbidden_markers = {
            "forward_to_legacy_flask": "auth_wecom_legacy_forward",
            "legacy_flask_facade": "auth_wecom_legacy_facade",
            "X-AICRM-Compatibility-Facade": "auth_wecom_compatibility_facade",
            '"fallback_used": True': "auth_wecom_fallback_used_true",
            "'fallback_used': True": "auth_wecom_fallback_used_true",
            '"real_external_call_executed": True': "auth_wecom_real_external_call_true",
            "'real_external_call_executed': True": "auth_wecom_real_external_call_true",
            "requests.post(": "auth_wecom_direct_external_call",
            "httpx.post(": "auth_wecom_direct_external_call",
            "exchange_code_for_wecom_user": "auth_wecom_direct_wecom_exchange",
            "build_wecom_qr_login_url": "auth_wecom_direct_wecom_authorize",
            "build_wecom_oauth_login_url": "auth_wecom_direct_wecom_authorize",
            "access_token\":": "auth_wecom_token_leak_marker",
            "app_secret\":": "auth_wecom_token_leak_marker",
            "real_enabled default": "auth_wecom_real_enabled_default",
            "default real_enabled": "auth_wecom_real_enabled_default",
        }
        for marker, code in forbidden_markers.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        str(auth_api_path.relative_to(root)),
                        marker,
                        "Auth/wecom Next exact responses must not forward to legacy, leak tokens, or execute real OAuth/WeCom calls.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_path = {record.get("path_pattern"): record for record in registry_records}
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}

    for route_path in AUTH_WECOM_EXACT_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("auth_wecom_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if record.get("runtime_owner") != "next_native":
                violations.append(Violation("auth_wecom_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
            if record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
            if record.get("adapter_mode") not in {"real_blocked", "none"}:
                violations.append(Violation("auth_wecom_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
            if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
                violations.append(Violation("auth_wecom_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        manifest_record = manifest_by_path.get(route_path)
        if manifest_record is None:
            violations.append(Violation("auth_wecom_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("auth_wecom_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_exact":
                violations.append(Violation("auth_wecom_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("auth_wecom_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    for route_path in AUTH_WECOM_WILDCARD_REGISTRY_ROUTES:
        record = registry_by_path.get(route_path)
        if record is None:
            violations.append(Violation("auth_wecom_wildcard_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if record.get("runtime_owner") == "production_compat":
                violations.append(Violation("auth_wecom_wildcard_registry_production_compat", route_path, f"runtime_owner={record.get('runtime_owner')}"))
            if record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_wildcard_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
            if record.get("delete_status") == "active" or record.get("replacement_status") == "validating":
                violations.append(Violation("auth_wecom_wildcard_registry_retained_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
            if record.get("delete_status") not in {"legacy_deleted", "deletion_locked"} or record.get("replacement_status") not in {"deleted", "locked"}:
                violations.append(Violation("auth_wecom_wildcard_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        manifest_record = manifest_by_path.get(route_path)
        if manifest_record is None:
            violations.append(Violation("auth_wecom_wildcard_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") == "production_compat":
                violations.append(Violation("auth_wecom_wildcard_manifest_production_compat", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("auth_wecom_wildcard_manifest_legacy_forward", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("auth_wecom_wildcard_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("delete_status") == "active" or manifest_record.get("replacement_status") == "validating":
                violations.append(Violation("auth_wecom_wildcard_manifest_retained_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
            if manifest_record.get("delete_status") not in {"legacy_deleted", "deletion_locked"} or manifest_record.get("replacement_status") not in {"deleted", "locked"}:
                violations.append(Violation("auth_wecom_wildcard_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def check_wecom_tag_read_next_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/wecom_tag_read_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "wecom_tag_read_inventory_missing",
                "docs/architecture/wecom_tag_read_route_inventory.md",
                "missing inventory document",
                "Add the WeCom tag read route inventory before moving read routes or changing tag fallback lifecycle.",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path in WECOM_TAG_READ_ROUTES + WECOM_TAG_FAMILY_ROUTES + ("/api/sidebar/signup-tags/status",):
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_read_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for phrase in ("Write Out Of Scope", "External Side Effects Out Of Scope", "No separate sidebar tag catalog selector"):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_read_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/customer_tags/api.py"
    read_model_path = root / "aicrm_next/customer_tags/read_model.py"
    main_path = root / "aicrm_next/main.py"
    production_compat_path = root / "aicrm_next/production_compat/api.py"
    if not api_path.exists():
        violations.append(Violation("wecom_tag_read_api_missing", str(api_path.relative_to(root)), "missing customer_tags api"))
    else:
        api_text = api_path.read_text(encoding="utf-8")
        if "read_router = APIRouter()" not in api_text:
            violations.append(Violation("wecom_tag_read_router_missing", str(api_path.relative_to(root)), "read_router = APIRouter()"))
        for route_path in WECOM_TAG_READ_ROUTES:
            if f'@read_router.get("{route_path}")' not in api_text and f"@read_router.get('{route_path}')" not in api_text:
                violations.append(Violation("wecom_tag_read_exact_route_missing", str(api_path.relative_to(root)), route_path))
        sources = _function_sources(
            api_path,
            {
                "list_admin_wecom_tags_read_model",
                "get_admin_wecom_tag_read_model",
                "list_admin_wecom_tag_groups_read_model",
                "get_admin_wecom_tag_group_read_model",
                "_read_catalog_payload",
                "_production_unavailable",
            },
        )
        for function_name, source in sources.items():
            for marker, code in {
                "forward_to_legacy_flask": "wecom_tag_read_legacy_forward",
                "legacy_flask_facade": "wecom_tag_read_legacy_facade",
                "X-AICRM-Compatibility-Facade": "wecom_tag_read_compatibility_facade",
                '"fallback_used": True': "wecom_tag_read_fallback_used_true",
                "'fallback_used': True": "wecom_tag_read_fallback_used_true",
                '"real_external_call_executed": True': "wecom_tag_read_real_external_call_true",
                "'real_external_call_executed': True": "wecom_tag_read_real_external_call_true",
                '"sync_executed": True': "wecom_tag_read_sync_executed_true",
                "'sync_executed': True": "wecom_tag_read_sync_executed_true",
                "requests.": "wecom_tag_read_direct_http_client",
                "httpx.": "wecom_tag_read_direct_http_client",
                "list_wecom_tags_live": "wecom_tag_read_real_wecom_sync",
                "mark_tags_live": "wecom_tag_read_real_wecom_mutation",
            }.items():
                if marker in source:
                    violations.append(
                        Violation(
                            code,
                            str(api_path.relative_to(root)),
                            f"{function_name}:{marker}",
                            "WeCom tag read routes must use the Next read model with no legacy forward, compatibility facade, or real WeCom call.",
                        )
                    )
    if not read_model_path.exists():
        violations.append(Violation("wecom_tag_read_model_missing", str(read_model_path.relative_to(root)), "missing tag catalog read model"))
    if read_model_path.exists():
        source = read_model_path.read_text(encoding="utf-8")
        for marker, code in {
            "requests.": "wecom_tag_read_direct_http_client",
            "httpx.": "wecom_tag_read_direct_http_client",
            "WeComTagLiveGateway": "wecom_tag_read_real_wecom_gateway",
            "list_wecom_tags_live": "wecom_tag_read_real_wecom_sync",
            "mark_external_contact_tags": "wecom_tag_read_real_wecom_mutation",
            "production_success_claimed": "wecom_tag_read_production_success_claimed",
        }.items():
            if marker in source:
                violations.append(Violation(code, str(read_model_path.relative_to(root)), marker))
    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        read_include = main_text.find("include_router(customer_tags_read_router)")
        compat_include = main_text.find(PROD_COMPAT_INCLUDE)
        if read_include < 0 or (compat_include >= 0 and read_include > compat_include):
            violations.append(
                Violation(
                    "wecom_tag_read_router_order",
                    str(main_path.relative_to(root)),
                    f"customer_tags_read_router must be included before {PROD_COMPAT_ROUTER_NAME}",
                )
            )
    if production_compat_path.exists():
        compat_text = production_compat_path.read_text(encoding="utf-8")
        write_methods_line = next(
            (line for line in compat_text.splitlines() if line.strip().startswith("_WRITE_FALLBACK_METHODS")),
            "",
        )
        if "GET" in write_methods_line or "HEAD" in write_methods_line:
            violations.append(
                Violation(
                    "wecom_tag_read_production_compat_write_methods_include_read",
                    str(production_compat_path.relative_to(root)),
                    write_methods_line.strip(),
                    "Keep WeCom tag production_compat fallback limited to write/sync methods; read routes are locked to Next.",
                )
            )
        for line in compat_text.splitlines():
            if (
                "@router.api_route(" in line
                and (
                    '"/api/admin/wecom/tags' in line
                    or "'/api/admin/wecom/tags" in line
                    or '"/api/admin/wecom/tag-groups' in line
                    or "'/api/admin/wecom/tag-groups" in line
                )
                and ("_ALL_METHODS" in line or '"GET"' in line or "'GET'" in line or '"HEAD"' in line or "'HEAD'" in line)
            ):
                violations.append(
                    Violation(
                        "wecom_tag_read_production_compat_read_route",
                        str(production_compat_path.relative_to(root)),
                        line.strip(),
                        "Do not register WeCom tag read routes in production_compat; keep only write/sync fallback methods.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")

    for route_path in WECOM_TAG_READ_ROUTES:
        record = _record_for_path_and_methods(registry_records, "path_pattern", route_path, ("GET",))
        if record is None:
            violations.append(Violation("wecom_tag_read_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if record.get("runtime_owner") != "next_native":
                violations.append(Violation("wecom_tag_read_registry_owner", route_path, f"runtime_owner={record.get('runtime_owner')}"))
            if record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_read_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
            if record.get("legacy_source") not in {"", None}:
                violations.append(Violation("wecom_tag_read_registry_legacy_source", route_path, f"legacy_source={record.get('legacy_source')}"))
            if record.get("external_side_effect_risk") != "none":
                violations.append(Violation("wecom_tag_read_registry_side_effect_risk", route_path, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
            if record.get("adapter_mode") not in {"none", ""}:
                violations.append(Violation("wecom_tag_read_registry_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
            if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_read_registry_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        manifest_record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("GET",))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_read_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("wecom_tag_read_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_exact":
                violations.append(Violation("wecom_tag_read_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_read_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("external_side_effect_risk") != "none":
                violations.append(Violation("wecom_tag_read_manifest_side_effect_risk", route_path, f"external_side_effect_risk={manifest_record.get('external_side_effect_risk')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("wecom_tag_read_manifest_behavior", route_path, "production_behavior=legacy_forward"))
            if manifest_record.get("current_runtime_owner") == "production_compat":
                violations.append(Violation("wecom_tag_read_manifest_owner", route_path, "current_runtime_owner=production_compat"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_read_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    for route_path in WECOM_TAG_FAMILY_ROUTES:
        manifest_record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_family_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if manifest_record.get("current_runtime_owner") != "next":
            violations.append(Violation("wecom_tag_family_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("production_behavior") == "legacy_forward":
            violations.append(Violation("wecom_tag_family_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("wecom_tag_family_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("delete_status") == "deletion_locked" or manifest_record.get("replacement_status") == "locked":
            violations.append(Violation("wecom_tag_family_manifest_mislocked", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def _record_for_path_and_methods(records: list[dict], path_key: str, path: str, methods: tuple[str, ...]) -> dict | None:
    exact = [record for record in records if record.get(path_key) == path and tuple(record.get("methods") or []) == methods]
    if exact:
        return exact[0]
    methodless = [record for record in records if record.get(path_key) == path and not record.get("methods")]
    if methodless:
        return methodless[0]
    return None


def _is_media_library_route_path(route_path: str) -> bool:
    return route_path in MEDIA_LIBRARY_PAGE_ROUTES or any(route_path.startswith(prefix) for prefix in MEDIA_LIBRARY_API_PREFIXES)


def check_media_library_admin_pages_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    frontend_routes = root / "aicrm_next/frontend_compat/legacy_routes.py"
    if frontend_routes.exists():
        source = frontend_routes.read_text(encoding="utf-8")
        for marker in (
            "/admin/image-library",
            "/admin/miniprogram-library",
            "/admin/attachment-library",
            "admin_image_library",
            "admin_miniprogram_library",
            "admin_attachment_library",
        ):
            if marker in source:
                violations.append(
                    Violation(
                        "media_library_page_still_in_frontend_compat",
                        str(frontend_routes.relative_to(root)),
                        marker,
                    )
                )

    admin_pages = root / "aicrm_next/media_library/admin_pages.py"
    if not admin_pages.exists():
        violations.append(
            Violation(
                "media_library_admin_pages_missing",
                str(admin_pages.relative_to(root)),
                "missing native media library admin page module",
            )
        )
    else:
        source = admin_pages.read_text(encoding="utf-8")
        for route in MEDIA_LIBRARY_PAGE_ROUTES:
            if route not in source:
                violations.append(
                    Violation(
                        "media_library_admin_pages_route_missing",
                        str(admin_pages.relative_to(root)),
                        route,
                    )
                )

    main_path = root / "aicrm_next/main.py"
    if main_path.exists():
        source = main_path.read_text(encoding="utf-8")
        native_import = "from .media_library.admin_pages import router as media_library_admin_pages_router"
        native_include = "app.include_router(media_library_admin_pages_router)"
        frontend_include = "app.include_router(frontend_compat_router)"
        missing_registration = native_import not in source or native_include not in source
        if not missing_registration and frontend_include in source:
            missing_registration = source.index(native_include) > source.index(frontend_include)
        if missing_registration:
            violations.append(
                Violation(
                    "media_library_admin_pages_not_registered",
                    str(main_path.relative_to(root)),
                    "media_library_admin_pages_router must be registered before frontend_compat_router",
                )
            )

    return violations


def check_media_library_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/media_library_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("media_library_inventory_missing", str(inventory_path.relative_to(root)), "missing Media Library inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend ↔ API ↔ Backend Contract Matrix",
            "production_compat rollback is removed",
            "legacy_fallback_allowed",
            "deletion_locked",
            "real_external_call_executed=false",
            "Real external object storage enablement.",
            "Real WeCom media upload.",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("media_library_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path)) | set(_decorated_route_function_sources(compat_path))
        for route_path in sorted(route_paths):
            if _is_media_library_route_path(route_path):
                violations.append(
                    Violation(
                        "media_library_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Media Library group 16 is deletion_locked to Next/front-end-compat-over-Next APIs; do not register production_compat rollback routes.",
                    )
                )

    media_root = root / "aicrm_next/media_library"
    if media_root.exists():
        for path in media_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            for marker, code in MEDIA_LIBRARY_DIRECT_EXTERNAL_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Media Library closeout must keep real external storage, direct HTTP fetch, and real WeCom media upload blocked by default.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id, path_pattern, methods, owner, adapter_mode in MEDIA_LIBRARY_REGISTRY_FAMILIES:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("media_library_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("path_pattern") != path_pattern or tuple(record.get("methods") or []) != methods:
            violations.append(Violation("media_library_registry_route_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != owner:
            violations.append(Violation("media_library_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("media_library_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("media_library_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("media_library_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("adapter_mode") != adapter_mode:
            violations.append(Violation("media_library_registry_adapter_mode", route_id, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("media_library_registry_rollback_lifecycle", route_id, "delete_status=next_primary_with_legacy_rollback"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in MEDIA_LIBRARY_MANIFEST_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("media_library_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        expected_owner = "next"
        if record.get("current_runtime_owner") != expected_owner:
            violations.append(Violation("media_library_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("media_library_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True:
            violations.append(Violation("media_library_manifest_delete_ready", route_path, f"delete_ready={record.get('delete_ready')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("media_library_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("media_library_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        notes = str(record.get("notes") or "")
        if route_path.startswith("/api/admin/") and ("real external" not in notes and "cloud storage" not in notes):
            violations.append(Violation("media_library_manifest_no_real_storage_note", route_path, "notes must document no real external storage"))
        if route_path.startswith("/api/admin/") and "WeCom media" not in notes:
            violations.append(Violation("media_library_manifest_no_real_wecom_note", route_path, "notes must document no real WeCom media upload"))

    return violations


def check_hxc_dashboard_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/hxc_dashboard_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("hxc_dashboard_inventory_missing", str(inventory_path.relative_to(root)), "missing HXC dashboard inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend <-> API <-> Backend Contract Matrix",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "refresh_hxc_dashboard_snapshot",
            "sync_admin_wecom_directory_members",
            "broadcast_to_filtered_users",
            "real_external_call_executed=false",
            "No real HXC broadcast.",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("hxc_dashboard_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, _methods in _decorator_route_methods(compat_path):
            if route_path in HXC_DASHBOARD_PRODUCTION_COMPAT_ROUTES or route_path.startswith("/api/admin/hxc-dashboard"):
                violations.append(
                    Violation(
                        "hxc_dashboard_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "HXC dashboard production_compat fallback is deletion_locked; serve it from aicrm_next.hxc_dashboard only.",
                    )
                )

    hxc_root = root / "aicrm_next/hxc_dashboard"
    if hxc_root.exists():
        for path in hxc_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            for marker, code in HXC_DASHBOARD_DIRECT_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "HXC dashboard Next closeout must not import legacy Flask, call legacy HXC helpers, or execute real HTTP/WeCom/OpenClaw clients.",
                        )
                    )
            for marker, code in HXC_DASHBOARD_TRUE_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "HXC dashboard Next closeout must keep fallback and real side-effect execution flags false.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id in HXC_DASHBOARD_REGISTRY_RECORDS:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("hxc_dashboard_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("hxc_dashboard_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("hxc_dashboard_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("hxc_dashboard_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("hxc_dashboard_registry_owner", route_id, "runtime_owner=production_compat"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")

    def _manifest_record(route_path: str, method: str) -> dict | None:
        for record in manifest_records:
            if record.get("route_pattern") != route_path:
                continue
            methods = {str(item).upper() for item in record.get("methods") or []}
            if method.upper() in methods:
                return record
        return None

    for route_path in HXC_DASHBOARD_PAGE_ROUTES:
        record = _manifest_record(route_path, "GET")
        if record is None:
            violations.append(Violation("hxc_dashboard_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next" or record.get("production_behavior") != "next_exact":
            violations.append(Violation("hxc_dashboard_manifest_owner", route_path, f"owner={record.get('current_runtime_owner')} behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("hxc_dashboard_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("hxc_dashboard_manifest_lifecycle", route_path, str(record)))

    read_routes = {
        "/api/admin/hxc-dashboard",
        "/api/admin/hxc-dashboard/send-config",
        "/api/admin/hxc-dashboard/{unknown_path}",
    }
    for route_path in HXC_DASHBOARD_API_ROUTES:
        method = "DELETE" if route_path.endswith("{sender_userid}") else "GET" if route_path in read_routes else "POST"
        record = _manifest_record(route_path, method)
        if record is None:
            violations.append(Violation("hxc_dashboard_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", f"{method} {route_path}"))
            continue
        if record.get("current_runtime_owner") != "next":
            violations.append(Violation("hxc_dashboard_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("hxc_dashboard_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("hxc_dashboard_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("hxc_dashboard_manifest_lifecycle", route_path, str(record)))
    return violations


def check_admin_auth_login_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/admin_auth_login_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("admin_auth_login_inventory_missing", str(inventory_path.relative_to(root)), "missing admin auth login inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend <-> API <-> Backend Contract Matrix",
            "GET 200, non-empty",
            "Invalid credential controlled",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "/auth/wecom/start",
            "/auth/wecom/callback",
            "Do not change payment",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("admin_auth_login_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, _methods in _decorator_route_methods(compat_path):
            if route_path in ADMIN_AUTH_LOGIN_ROUTES:
                violations.append(
                    Violation(
                        "admin_auth_login_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Admin auth login/logout is deletion_locked to Next; do not register production_compat rollback routes.",
                    )
                )

    auth_root = root / "aicrm_next/admin_auth"
    if auth_root.exists():
        for path in auth_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            for marker, code in ADMIN_AUTH_LOGIN_DIRECT_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Admin auth login/logout Next closeout must not call legacy auth handlers or direct HTTP/WeCom token exchange paths.",
                        )
                    )
            for marker, code in ADMIN_AUTH_LOGIN_TRUE_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Admin auth login/logout Next closeout must keep fallback and real external execution flags false.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id in ADMIN_AUTH_LOGIN_REGISTRY_RECORDS:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("admin_auth_login_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("admin_auth_login_registry_owner", route_id, "runtime_owner=production_compat"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("admin_auth_login_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("admin_auth_login_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("admin_auth_login_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in ADMIN_AUTH_LOGIN_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("admin_auth_login_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next":
            violations.append(Violation("admin_auth_login_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("admin_auth_login_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("admin_auth_login_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("admin_auth_login_manifest_lifecycle", route_path, str(record)))
    return violations


def check_public_product_pay_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/public_product_pay_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("public_product_inventory_missing", str(inventory_path.relative_to(root)), "missing public product/pay inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend <-> API <-> Backend Contract Matrix",
            "/p/{product_or_slug}",
            "/pay/{product_or_slug}",
            "/api/products/{path}",
            "production_compat rollback removed",
            "wildcard_router rollback removed",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "Next-owned H5 WeChat Pay may create JSAPI orders",
            "Do not change admin/alipay/checkout/orders/provider ownership",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("public_product_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        compat_text = compat_path.read_text(encoding="utf-8")
        for route_path in PUBLIC_PRODUCT_PAY_ROUTES:
            if f'@router.api_route("{route_path}"' in compat_text or f"@router.api_route('{route_path}'" in compat_text:
                violations.append(
                    Violation(
                        "public_product_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Public product/pay routes are deletion_locked to Next; do not register production_compat router rollback routes.",
                    )
                )
            if f'@wildcard_router.api_route("{route_path}"' in compat_text or f"@wildcard_router.api_route('{route_path}'" in compat_text:
                violations.append(
                    Violation(
                        "public_product_wildcard_production_compat_route",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Public product/pay wildcard rollback is removed; keep payment/admin/h5/checkout/orders out-of-scope wildcards only.",
                    )
                )

    public_root = root / "aicrm_next/public_product"
    if public_root.exists():
        for path in public_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel_path = path.relative_to(root)
            rel = str(rel_path)
            allowed_markers = PUBLIC_PRODUCT_PAY_DIRECT_MARKER_ALLOWLIST.get(rel_path, set())
            for marker, code in PUBLIC_PRODUCT_PAY_DIRECT_MARKERS.items():
                if marker in allowed_markers:
                    continue
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Public product/pay closeout must not call legacy facade, direct payment clients, HTTP clients, token paths, or order creation.",
                        )
                    )
            for marker, code in PUBLIC_PRODUCT_PAY_TRUE_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Public product/pay closeout must keep fallback, payment request, order create, and real external execution flags false.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id in PUBLIC_PRODUCT_PAY_REGISTRY_RECORDS:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("public_product_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("public_product_registry_owner", route_id, "runtime_owner=production_compat"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("public_product_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("public_product_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("public_product_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in PUBLIC_PRODUCT_PAY_MANIFEST_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("public_product_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next":
            violations.append(Violation("public_product_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("public_product_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("public_product_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("public_product_manifest_lifecycle", route_path, str(record)))
    return violations


def check_checkout_orders_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/checkout_orders_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("checkout_orders_inventory_missing", str(inventory_path.relative_to(root)), "missing checkout/orders inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "API <-> Backend <-> Payment Adapter Contract Matrix",
            "/api/checkout/wechat",
            "/api/checkout/alipay",
            "/api/orders/{order_no}",
            "/api/orders/{order_no}/status",
            "/api/checkout/{unknown_path}",
            "/api/orders/{unknown_child_path}",
            "payment_request_executed=false",
            "real_external_call_executed=false",
            "production_compat wildcard removed",
            "provider notify/return",
            "admin payment",
            "H5 payment",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("checkout_orders_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, _methods in _decorator_route_methods(compat_path):
            if route_path in CHECKOUT_ORDERS_COMPAT_ROUTES:
                violations.append(
                    Violation(
                        "checkout_orders_production_compat_wildcard",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Checkout/orders public API wildcard rollback is deletion_locked to Next; keep provider/admin/h5 payment wildcards out of scope.",
                    )
                )

    commerce_paths = [
        root / "aicrm_next/commerce/api.py",
        root / "aicrm_next/commerce/application.py",
    ]
    for path in commerce_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))
        for marker, code in CHECKOUT_ORDERS_DIRECT_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Checkout/orders Next closeout must not call legacy facades, direct HTTP clients, raw payment clients, or access-token paths.",
                    )
                )
        for marker, code in CHECKOUT_ORDERS_TRUE_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Checkout/orders Next closeout must keep fallback, real external, and real payment execution flags false.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id in CHECKOUT_ORDERS_REGISTRY_RECORDS:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("checkout_orders_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("checkout_orders_registry_owner", route_id, "runtime_owner=production_compat"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("checkout_orders_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("checkout_orders_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("checkout_orders_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in CHECKOUT_ORDERS_MANIFEST_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("checkout_orders_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") not in {"next", "next_checkout", "next_order_read"}:
            violations.append(Violation("checkout_orders_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("checkout_orders_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("checkout_orders_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("checkout_orders_manifest_lifecycle", route_path, str(record)))

    return violations


def check_provider_payment_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/provider_payment_notify_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("provider_payment_inventory_missing", str(inventory_path.relative_to(root)), "missing provider payment notify/return inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Provider Callback <-> API <-> Backend <-> Payment Adapter Matrix",
            "/api/wechat-pay/notify",
            "/api/alipay/notify",
            "/api/alipay/return",
            "/api/wechat-pay/{unknown_path}",
            "/api/alipay/{unknown_path}",
            "provider_signature_verified=false",
            "real_payment_notify_executed=false",
            "real_external_call_executed=false",
            "production_compat wildcard removed",
            "Admin payment",
            "H5 payment",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("provider_payment_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, _methods in _decorator_route_methods(compat_path):
            if route_path in PROVIDER_PAYMENT_COMPAT_ROUTES:
                violations.append(
                    Violation(
                        "provider_payment_production_compat_wildcard",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Public provider payment wildcard rollback is deletion_locked to Next; keep admin/h5 payment wildcards out of scope.",
                    )
                )

    commerce_paths = [
        root / "aicrm_next/commerce/api.py",
        root / "aicrm_next/commerce/application.py",
    ]
    for path in commerce_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))
        for marker, code in PROVIDER_PAYMENT_DIRECT_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Provider payment Next closeout must not call legacy facades, direct HTTP clients, raw payment clients, or access-token paths.",
                    )
                )
        for marker, code in PROVIDER_PAYMENT_TRUE_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Provider payment Next closeout must keep fallback, real external, real provider, and signature verification flags false.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id in PROVIDER_PAYMENT_REGISTRY_RECORDS:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("provider_payment_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("runtime_owner") == "production_compat":
            violations.append(Violation("provider_payment_registry_owner", route_id, "runtime_owner=production_compat"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("provider_payment_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("provider_payment_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("provider_payment_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in PROVIDER_PAYMENT_MANIFEST_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("provider_payment_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") not in {"next", "next_payment_notify", "next_payment_return"}:
            violations.append(Violation("provider_payment_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("provider_payment_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("provider_payment_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("provider_payment_manifest_lifecycle", route_path, str(record)))

    return violations


def check_payment_wildcard_final_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/admin_h5_payment_wildcard_closeout_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("payment_wildcard_final_inventory_missing", str(inventory_path.relative_to(root)), "missing admin/h5 payment wildcard closeout inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Route <-> Caller <-> Backend <-> Decision Matrix",
            "/api/admin/wechat-pay/{path:path}",
            "/api/admin/alipay/{path:path}",
            "/api/h5/wechat-pay/{path:path}",
            "/api/h5/alipay/{path:path}",
            "unknown child path",
            "production_compat wildcard removed",
            "final no legacy fallback",
            "real_refund_executed=false",
            "real_external_call_executed=false",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("payment_wildcard_final_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        compat_text = compat_path.read_text(encoding="utf-8")
        if "forward_to_legacy_flask" in compat_text or "legacy_flask_facade" in compat_text:
            violations.append(Violation("payment_wildcard_final_production_compat_facade", str(compat_path.relative_to(root)), "legacy facade reference"))
        for route_path, _methods in _decorator_route_methods(compat_path):
            violations.append(
                Violation(
                    "payment_wildcard_final_production_compat_route",
                    str(compat_path.relative_to(root)),
                    route_path,
                    "Final payment wildcard closeout leaves production_compat with no API routes.",
                )
            )

    commerce_paths = [
        root / "aicrm_next/commerce/api.py",
        root / "aicrm_next/commerce/application.py",
    ]
    for path in commerce_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))
        for marker, code in PAYMENT_WILDCARD_FINAL_DIRECT_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Final payment wildcard closeout must not call legacy facades, direct HTTP clients, raw payment clients, or access-token paths.",
                    )
                )
        for marker, code in PAYMENT_WILDCARD_FINAL_TRUE_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Final payment wildcard closeout must keep fallback, real external, payment request, provider, signature, and refund execution flags false.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id in PAYMENT_WILDCARD_FINAL_REGISTRY_RECORDS:
        record = registry_by_id.get(route_id)
        if record is None:
            violations.append(Violation("payment_wildcard_final_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("payment_wildcard_final_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("payment_wildcard_final_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("payment_wildcard_final_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("payment_wildcard_final_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_path = {record.get("route_pattern"): record for record in manifest_records}
    for route_path in PAYMENT_WILDCARD_FINAL_MANIFEST_ROUTES:
        record = manifest_by_path.get(route_path)
        if record is None:
            violations.append(Violation("payment_wildcard_final_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("payment_wildcard_final_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("payment_wildcard_final_manifest_legacy_forward", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("payment_wildcard_final_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("delete_ready") is not True or record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("payment_wildcard_final_manifest_lifecycle", route_path, str(record)))

    return violations


def check_cloud_orchestrator_media_upload_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/cloud_orchestrator_media_upload_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "cloud_media_upload_inventory_missing",
                str(inventory_path.relative_to(root)),
                "missing Cloud Orchestrator media upload inventory document",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Deletion Closeout Status Matrix",
            "production_compat rollback removed",
            "Next adapter only",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "real_external_call_executed=true",
            "wecom_media_upload_executed=true",
        ):
            if phrase not in inventory_text:
                violations.append(
                    Violation(
                        "cloud_media_upload_inventory_boundary_missing",
                        str(inventory_path.relative_to(root)),
                        phrase,
                        "Document that Cloud Orchestrator media upload is locked to the Next adapter with production_compat rollback removed.",
                    )
                )

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        compat_text = compat_path.read_text(encoding="utf-8")
        if CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE in compat_text:
            violations.append(
                Violation(
                    "cloud_media_upload_production_compat_route",
                    str(compat_path.relative_to(root)),
                    CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE,
                    "Cloud Orchestrator media upload deletion closeout removed this exact production_compat rollback; campaigns/run-due routes remain out of scope.",
                )
            )
        for route_path in _decorator_route_paths(compat_path):
            if route_path == CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE:
                violations.append(
                    Violation(
                        "cloud_media_upload_production_compat_decorator",
                        str(compat_path.relative_to(root)),
                        route_path,
                        "Do not register POST/OPTIONS /api/admin/cloud-orchestrator/media/upload in production_compat.",
                    )
                )

    cloud_root = root / "aicrm_next/cloud_orchestrator"
    if cloud_root.exists():
        for path in cloud_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(root))
            for marker, code in CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_DIRECT_EXTERNAL_MARKERS.items():
                if marker in text:
                    violations.append(
                        Violation(
                            code,
                            rel,
                            marker,
                            "Cloud Orchestrator media upload must only use the approved WeCom media gateway boundary and must not use direct HTTP clients.",
                        )
                    )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_record = next(
        (record for record in registry_records if record.get("route_id") == "cloud_orchestrator_media_upload_adapter"),
        None,
    )
    if registry_record is None:
        violations.append(
            Violation(
                "cloud_media_upload_registry_missing",
                "docs/architecture/legacy_exit_route_registry.yaml",
                "cloud_orchestrator_media_upload_adapter",
                "Keep the Cloud Orchestrator media upload route registered and deletion_locked.",
            )
        )
    else:
        if registry_record.get("path_pattern") != CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE:
            violations.append(Violation("cloud_media_upload_registry_path", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"path_pattern={registry_record.get('path_pattern')}"))
        if tuple(registry_record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("cloud_media_upload_registry_methods", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"methods={registry_record.get('methods')}"))
        if registry_record.get("runtime_owner") not in {"next_adapter", "next_command"}:
            violations.append(Violation("cloud_media_upload_registry_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("runtime_owner") == "production_compat":
            violations.append(Violation("cloud_media_upload_registry_production_compat_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, "runtime_owner=production_compat"))
        if registry_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_media_upload_registry_legacy_allowed", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
        if registry_record.get("legacy_source") not in {"", None}:
            violations.append(Violation("cloud_media_upload_registry_legacy_source", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"legacy_source={registry_record.get('legacy_source')}"))
        if registry_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
            violations.append(Violation("cloud_media_upload_registry_rollback_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={registry_record.get('delete_status')}"))
        if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_media_upload_registry_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))
        if registry_record.get("adapter_mode") not in {"production", "real_enabled"}:
            violations.append(Violation("cloud_media_upload_registry_adapter_mode", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"adapter_mode={registry_record.get('adapter_mode')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_record = next((record for record in manifest_records if record.get("route_pattern") == CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE), None)
    if manifest_record is None:
        violations.append(
            Violation(
                "cloud_media_upload_manifest_missing",
                "docs/route_ownership/production_route_ownership_manifest.yaml",
                CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE,
                "Keep the Cloud Orchestrator media upload production manifest record deletion_locked.",
            )
        )
    else:
        if manifest_record.get("current_runtime_owner") not in {"next", "next_adapter", "next_command"}:
            violations.append(Violation("cloud_media_upload_manifest_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("current_runtime_owner") == "production_compat":
            violations.append(Violation("cloud_media_upload_manifest_production_compat_owner", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, "current_runtime_owner=production_compat"))
        if manifest_record.get("production_behavior") not in {"next_adapter", "next_adapter_real_upload"}:
            violations.append(Violation("cloud_media_upload_manifest_behavior", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("cloud_media_upload_manifest_legacy_behavior", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_media_upload_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("delete_ready") is not True:
            violations.append(Violation("cloud_media_upload_manifest_delete_ready", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_ready={manifest_record.get('delete_ready')}"))
        if manifest_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
            violations.append(Violation("cloud_media_upload_manifest_rollback_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={manifest_record.get('delete_status')}"))
        if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_media_upload_manifest_lifecycle", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))
        if manifest_record.get("adapter_mode") not in {"production", "real_enabled"}:
            violations.append(Violation("cloud_media_upload_manifest_adapter_mode", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, f"adapter_mode={manifest_record.get('adapter_mode')}"))

    return violations


def check_cloud_orchestrator_media_upload_native_client(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    media_upload_path = root / "aicrm_next/cloud_orchestrator/media_upload.py"
    native_client_path = root / "aicrm_next/integration_gateway/wecom_media_upload_client.py"
    adapter_test_path = root / "tests/test_cloud_orchestrator_media_upload_adapter.py"

    if media_upload_path.exists():
        text = media_upload_path.read_text(encoding="utf-8")
        rel = str(media_upload_path.relative_to(root))
        for marker in (
            "legacy_flask_facade",
            "_legacy_app",
            "legacy_wecom_client_from_app",
            "_upload_private_message_image",
            "wecom_ability_service",
            "WeComClient.from_app",
        ):
            if marker in text:
                violations.append(Violation("cloud_media_upload_legacy_client_import", rel, marker))
        for marker in ("requests.", "httpx", "access_token"):
            if marker in text:
                violations.append(Violation("cloud_media_upload_direct_http_client", rel, marker))

    if native_client_path.exists():
        text = native_client_path.read_text(encoding="utf-8")
        rel = str(native_client_path.relative_to(root))
        for marker in (
            "legacy_flask_facade",
            "_legacy_app",
            "legacy_wecom_client_from_app",
            "wecom_ability_service",
            "flask",
            "current_app",
            "WeComClient.from_app",
        ):
            if marker in text:
                violations.append(Violation("cloud_media_client_legacy_import", rel, marker))

    if adapter_test_path.exists():
        text = adapter_test_path.read_text(encoding="utf-8")
        rel = str(adapter_test_path.relative_to(root))
        for marker in (
            "aicrm_next.integration_gateway.legacy_flask_facade._legacy_app",
            "aicrm_next.integration_gateway.legacy_flask_facade.legacy_wecom_client_from_app",
        ):
            if marker in text:
                violations.append(Violation("cloud_media_tests_legacy_monkeypatch", rel, marker))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_record = next((record for record in registry_records if record.get("route_id") == "cloud_orchestrator_media_upload_adapter"), None)
    if registry_record is None:
        violations.append(Violation("cloud_media_registry_not_locked", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, "missing registry record"))
    elif (
        registry_record.get("runtime_owner") != "next_adapter"
        or registry_record.get("legacy_fallback_allowed") is not False
        or str(registry_record.get("legacy_source") or "") != ""
        or registry_record.get("delete_status") != "deletion_locked"
        or registry_record.get("replacement_status") != "locked"
    ):
        violations.append(
            Violation(
                "cloud_media_registry_not_locked",
                CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE,
                (
                    f"runtime_owner={registry_record.get('runtime_owner')} "
                    f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')} "
                    f"legacy_source={registry_record.get('legacy_source')} "
                    f"delete_status={registry_record.get('delete_status')} "
                    f"replacement_status={registry_record.get('replacement_status')}"
                ),
            )
        )

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_record = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, ("POST", "OPTIONS"))
    if manifest_record is None:
        violations.append(Violation("cloud_media_manifest_not_locked", CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE, "missing manifest record"))
    elif (
        manifest_record.get("current_runtime_owner") != "next"
        or manifest_record.get("production_behavior") != "next_adapter_real_upload"
        or manifest_record.get("legacy_fallback_allowed") is not False
        or manifest_record.get("delete_status") != "deletion_locked"
        or manifest_record.get("replacement_status") != "locked"
    ):
        violations.append(
            Violation(
                "cloud_media_manifest_not_locked",
                CLOUD_ORCHESTRATOR_MEDIA_UPLOAD_ROUTE,
                (
                    f"current_runtime_owner={manifest_record.get('current_runtime_owner')} "
                    f"production_behavior={manifest_record.get('production_behavior')} "
                    f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')} "
                    f"delete_status={manifest_record.get('delete_status')} "
                    f"replacement_status={manifest_record.get('replacement_status')}"
                ),
            )
        )

    return violations


def check_cloud_orchestrator_repository_time_helpers_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    repository_path = root / "aicrm_next/cloud_orchestrator/repository.py"
    time_helper_path = root / "aicrm_next/cloud_orchestrator/time_helpers.py"

    if repository_path.exists():
        text = repository_path.read_text(encoding="utf-8")
        rel = str(repository_path.relative_to(root))
        if "wecom_ability_service.domains.campaigns.time_helpers" in text:
            violations.append(
                Violation(
                    "cloud_repo_legacy_time_helper_import",
                    rel,
                    "wecom_ability_service.domains.campaigns.time_helpers",
                )
            )
        for marker in (
            "from wecom_ability_service",
            "wecom_ability_service",
            "legacy_flask_facade",
            "current_app",
        ):
            if marker in text:
                violations.append(Violation("cloud_repo_legacy_runtime_import", rel, marker))
        if "from .time_helpers import" not in text or "campaign_step_due_iso" not in text:
            violations.append(
                Violation(
                    "cloud_repo_time_helper_not_next",
                    rel,
                    "repository.py must import campaign_step_due_iso from .time_helpers",
                )
            )
    else:
        violations.append(Violation("cloud_repo_time_helper_not_next", str(repository_path.relative_to(root)), "missing repository.py"))

    if time_helper_path.exists():
        text = time_helper_path.read_text(encoding="utf-8")
        rel = str(time_helper_path.relative_to(root))
        for marker in (
            "wecom_ability_service",
            "legacy_flask_facade",
            "flask",
            "current_app",
        ):
            if marker in text:
                violations.append(Violation("cloud_time_helper_legacy_import", rel, marker))
        for marker in (
            'DEFAULT_SEND_TIME = "09:00"',
            'DEFAULT_TIMEZONE = "Asia/Shanghai"',
            "def campaign_step_due_iso",
        ):
            if marker not in text:
                violations.append(Violation("cloud_time_helper_contract_missing", rel, marker))
    else:
        violations.append(Violation("cloud_time_helper_contract_missing", str(time_helper_path.relative_to(root)), "missing time_helpers.py"))

    return violations


def check_cloud_orchestrator_campaign_read_closeout_lock(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/cloud_orchestrator_campaigns_route_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "cloud_campaign_read_inventory_missing",
                str(inventory_path.relative_to(root)),
                "missing Cloud Orchestrator campaigns route inventory document",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Deletion Closeout Status Matrix",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "legacy fallback removed",
            "write controls locked on Next CommandBus",
            "No real WeCom send",
            "No automation runtime",
        ):
            if phrase not in inventory_text:
                violations.append(
                    Violation(
                        "cloud_campaign_read_inventory_boundary_missing",
                        str(inventory_path.relative_to(root)),
                        phrase,
                        "Document that campaign read/workspace routes are locked to Next and write/run-due remain out of scope.",
                    )
                )
        for route_path in CLOUD_ORCHESTRATOR_CAMPAIGN_READ_SAMPLES:
            if route_path not in inventory_text:
                violations.append(
                    Violation(
                        "cloud_campaign_read_inventory_route_missing",
                        str(inventory_path.relative_to(root)),
                        route_path,
                    )
                )

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, methods in _decorator_route_methods(compat_path):
            if route_path in {
                "/api/admin/cloud-orchestrator/campaigns",
                "/api/admin/cloud-orchestrator/campaigns/{path:path}",
            } and "GET" in set(methods):
                violations.append(
                    Violation(
                        "cloud_campaign_read_production_compat_get_route",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={methods}",
                        "Campaign GET read rollback is deletion_locked; production_compat may retain only write/run-due methods.",
                    )
                )

    read_model_path = root / "aicrm_next/cloud_orchestrator/campaigns_read.py"
    if read_model_path.exists():
        text = read_model_path.read_text(encoding="utf-8")
        rel = str(read_model_path.relative_to(root))
        for marker, code in CLOUD_ORCHESTRATOR_CAMPAIGN_DIRECT_EXTERNAL_MARKERS.items():
            if marker in text:
                violations.append(
                    Violation(
                        code,
                        rel,
                        marker,
                        "Campaign read closeout must not trigger real WeCom send, automation runtime, token exchange, or direct HTTP calls.",
                    )
                )

    api_path = root / "aicrm_next/cloud_orchestrator/api.py"
    if api_path.exists():
        api_text = api_path.read_text(encoding="utf-8")
        rel = str(api_path.relative_to(root))
        for marker in (
            "X-AICRM-Compatibility-Facade",
            '"fallback_used": True',
            "'fallback_used': True",
            "fallback_used=True",
            "real_external_call_executed=True",
            "real_external_call_executed = True",
            '"real_external_call_executed": True',
            "'real_external_call_executed': True",
        ):
            if marker in api_text:
                violations.append(
                    Violation(
                        "cloud_campaign_read_response_contract_drift",
                        rel,
                        marker,
                        "Campaign read API must return fallback_used=false, no compatibility facade, and no real_external_call_executed=true.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    read_record = registry_by_id.get("cloud_orchestrator_campaigns_read_family")
    if read_record is None:
        violations.append(Violation("cloud_campaign_read_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_read_family"))
    else:
        if read_record.get("path_pattern") != CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE or tuple(read_record.get("methods") or []) != ("GET",):
            violations.append(Violation("cloud_campaign_read_registry_route_shape", "cloud_orchestrator_campaigns_read_family", f"path_pattern={read_record.get('path_pattern')} methods={read_record.get('methods')}"))
        if read_record.get("runtime_owner") != "next_read_model":
            violations.append(Violation("cloud_campaign_read_registry_owner", "cloud_orchestrator_campaigns_read_family", f"runtime_owner={read_record.get('runtime_owner')}"))
        if read_record.get("runtime_owner") == "production_compat":
            violations.append(Violation("cloud_campaign_read_registry_production_compat_owner", "cloud_orchestrator_campaigns_read_family", "runtime_owner=production_compat"))
        if read_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_read_registry_legacy_allowed", "cloud_orchestrator_campaigns_read_family", f"legacy_fallback_allowed={read_record.get('legacy_fallback_allowed')}"))
        if read_record.get("legacy_source") not in {"", None}:
            violations.append(Violation("cloud_campaign_read_registry_legacy_source", "cloud_orchestrator_campaigns_read_family", f"legacy_source={read_record.get('legacy_source')}"))
        if read_record.get("external_side_effect_risk") != "none":
            violations.append(Violation("cloud_campaign_read_registry_side_effect_risk", "cloud_orchestrator_campaigns_read_family", f"external_side_effect_risk={read_record.get('external_side_effect_risk')}"))
        if read_record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("cloud_campaign_read_registry_rollback_lifecycle", "cloud_orchestrator_campaigns_read_family", "delete_status=next_primary_with_legacy_rollback"))
        if read_record.get("delete_status") != "deletion_locked" or read_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_read_registry_lifecycle", "cloud_orchestrator_campaigns_read_family", f"delete_status={read_record.get('delete_status')} replacement_status={read_record.get('replacement_status')}"))

    page_record = registry_by_id.get("cloud_orchestrator_campaigns_page")
    if page_record is None:
        violations.append(Violation("cloud_campaign_page_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_page"))
    else:
        if page_record.get("path_pattern") != CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE or tuple(page_record.get("methods") or []) != ("GET",):
            violations.append(Violation("cloud_campaign_page_registry_route_shape", "cloud_orchestrator_campaigns_page", f"path_pattern={page_record.get('path_pattern')} methods={page_record.get('methods')}"))
        if page_record.get("runtime_owner") != "frontend_compat over Next read APIs":
            violations.append(Violation("cloud_campaign_page_registry_owner", "cloud_orchestrator_campaigns_page", f"runtime_owner={page_record.get('runtime_owner')}"))
        if page_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_page_registry_legacy_allowed", "cloud_orchestrator_campaigns_page", f"legacy_fallback_allowed={page_record.get('legacy_fallback_allowed')}"))
        if page_record.get("delete_status") != "deletion_locked" or page_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_page_registry_lifecycle", "cloud_orchestrator_campaigns_page", f"delete_status={page_record.get('delete_status')} replacement_status={page_record.get('replacement_status')}"))

    write_record = registry_by_id.get("cloud_orchestrator_campaigns_write_legacy_family")
    if write_record is None:
        violations.append(Violation("cloud_campaign_write_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_write_legacy_family"))
    else:
        if write_record.get("runtime_owner") != "next_command":
            violations.append(Violation("cloud_campaign_write_registry_owner", "cloud_orchestrator_campaigns_write_legacy_family", f"runtime_owner={write_record.get('runtime_owner')}"))
        if write_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_write_registry_legacy_allowed", "cloud_orchestrator_campaigns_write_legacy_family", f"legacy_fallback_allowed={write_record.get('legacy_fallback_allowed')}"))
        if write_record.get("delete_status") != "deletion_locked" or write_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_write_registry_lifecycle", "cloud_orchestrator_campaigns_write_legacy_family", f"delete_status={write_record.get('delete_status')} replacement_status={write_record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    read_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, ("GET",))
    if read_manifest is None:
        violations.append(Violation("cloud_campaign_read_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE))
    else:
        if read_manifest.get("current_runtime_owner") != "next":
            violations.append(Violation("cloud_campaign_read_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"current_runtime_owner={read_manifest.get('current_runtime_owner')}"))
        if read_manifest.get("production_behavior") != "next_exact":
            violations.append(Violation("cloud_campaign_read_manifest_behavior", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"production_behavior={read_manifest.get('production_behavior')}"))
        if read_manifest.get("production_behavior") == "legacy_forward":
            violations.append(Violation("cloud_campaign_read_manifest_legacy_forward", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, "production_behavior=legacy_forward"))
        if read_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_read_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"legacy_fallback_allowed={read_manifest.get('legacy_fallback_allowed')}"))
        if read_manifest.get("external_side_effect_risk") != "none":
            violations.append(Violation("cloud_campaign_read_manifest_side_effect_risk", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"external_side_effect_risk={read_manifest.get('external_side_effect_risk')}"))
        if read_manifest.get("delete_ready") is not True:
            violations.append(Violation("cloud_campaign_read_manifest_delete_ready", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"delete_ready={read_manifest.get('delete_ready')}"))
        if read_manifest.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("cloud_campaign_read_manifest_rollback_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, "delete_status=next_primary_with_legacy_rollback"))
        if read_manifest.get("delete_status") != "deletion_locked" or read_manifest.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_read_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"delete_status={read_manifest.get('delete_status')} replacement_status={read_manifest.get('replacement_status')}"))

    page_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, ("GET",))
    if page_manifest is None:
        violations.append(Violation("cloud_campaign_page_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE))
    else:
        if page_manifest.get("current_runtime_owner") != "next":
            violations.append(Violation("cloud_campaign_page_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, f"current_runtime_owner={page_manifest.get('current_runtime_owner')}"))
        if page_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_page_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, f"legacy_fallback_allowed={page_manifest.get('legacy_fallback_allowed')}"))
        if page_manifest.get("delete_status") != "deletion_locked" or page_manifest.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_page_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_PAGE_ROUTE, f"delete_status={page_manifest.get('delete_status')} replacement_status={page_manifest.get('replacement_status')}"))

    write_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_METHODS)
    if write_manifest is None:
        violations.append(Violation("cloud_campaign_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE))
    else:
        if write_manifest.get("current_runtime_owner") != "next_command":
            violations.append(Violation("cloud_campaign_write_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"current_runtime_owner={write_manifest.get('current_runtime_owner')}"))
        if write_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_write_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"legacy_fallback_allowed={write_manifest.get('legacy_fallback_allowed')}"))
        if write_manifest.get("delete_status") != "deletion_locked" or write_manifest.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_write_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_READ_ROUTE, f"delete_status={write_manifest.get('delete_status')} replacement_status={write_manifest.get('replacement_status')}"))

    return violations


def check_cloud_orchestrator_campaign_write_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/cloud_orchestrator_campaign_write_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("cloud_campaign_write_inventory_missing", str(inventory_path.relative_to(root)), "missing campaign write controls inventory"))
    else:
        text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend API CommandBus Contract Matrix",
            "ApproveCloudCampaignCommand",
            "RejectCloudCampaignCommand",
            "StartCloudCampaignCommand",
            "PauseCloudCampaignCommand",
            "DeleteCloudCampaignCommand",
            "BatchStartCloudCampaignsCommand",
            "AddCloudCampaignStepCommand",
            "UpdateCloudCampaignStepCommand",
            "DeleteCloudCampaignStepCommand",
            "SideEffectPlan",
            "Deletion Closeout Status Matrix",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "legacy fallback removed",
            "adapter_mode=real_blocked",
            "run-due",
            "separately deletion_locked",
            "real WeCom send",
            "automation runtime",
        ):
            if phrase not in text:
                violations.append(Violation("cloud_campaign_write_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for route_path in CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTES:
            if route_path not in text:
                violations.append(Violation("cloud_campaign_write_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    write_path = root / "aicrm_next/cloud_orchestrator/campaigns_write.py"
    if not write_path.exists():
        violations.append(Violation("cloud_campaign_write_module_missing", str(write_path.relative_to(root)), "missing campaigns_write.py"))
    else:
        source = write_path.read_text(encoding="utf-8")
        for marker in (
            "ApproveCloudCampaignCommand",
            "RejectCloudCampaignCommand",
            "StartCloudCampaignCommand",
            "PauseCloudCampaignCommand",
            "DeleteCloudCampaignCommand",
            "BatchStartCloudCampaignsCommand",
            "AddCloudCampaignStepCommand",
            "UpdateCloudCampaignStepCommand",
            "DeleteCloudCampaignStepCommand",
            "InMemoryAuditLedger",
            "InMemorySideEffectPlanRepository",
            "CommandBus",
            "campaign_execute_executed",
            "wecom_send_executed",
            "real_blocked",
        ):
            if marker not in source:
                violations.append(Violation("cloud_campaign_write_command_boundary_missing", str(write_path.relative_to(root)), marker))
        forbidden_markers = {
            "process_due_campaign_members": "cloud_campaign_write_runtime_call",
            "dispatch_wecom_task": "cloud_campaign_write_wecom_send_call",
            "upload_media": "cloud_campaign_write_media_upload_call",
            "media/upload": "cloud_campaign_write_media_upload_call",
            "requests.": "cloud_campaign_write_direct_http_client",
            "httpx": "cloud_campaign_write_direct_http_client",
            "real_external_call_executed=True": "cloud_campaign_write_real_external_true",
            '"real_external_call_executed": True': "cloud_campaign_write_real_external_true",
            "'real_external_call_executed': True": "cloud_campaign_write_real_external_true",
            "campaign_execute_executed=True": "cloud_campaign_write_execute_true",
            "wecom_send_executed=True": "cloud_campaign_write_send_true",
        }
        for marker, code in forbidden_markers.items():
            if marker in source:
                violations.append(Violation(code, str(write_path.relative_to(root)), marker))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, methods in _decorator_route_methods(compat_path):
            if route_path in {
                "/api/admin/cloud-orchestrator/campaigns",
                "/api/admin/cloud-orchestrator/campaigns/{path:path}",
            } and set(methods) & set(CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_METHODS):
                violations.append(
                    Violation(
                        "cloud_campaign_write_production_compat_rollback",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={methods}",
                        "Campaign write controls are deletion_locked on Next CommandBus; keep only run-due/preview production_compat timer routes.",
                    )
                )

    api_path = root / "aicrm_next/cloud_orchestrator/api.py"
    if api_path.exists():
        api_source = api_path.read_text(encoding="utf-8")
        for marker in (
            "api_batch_start_cloud_campaigns",
            "api_approve_cloud_campaign",
            "api_start_cloud_campaign",
            "api_pause_cloud_campaign",
            "api_reject_cloud_campaign",
            "api_delete_cloud_campaign",
            "api_add_cloud_campaign_step",
            "api_update_cloud_campaign_step",
            "api_delete_cloud_campaign_step",
            "execute_cloud_campaign_command",
        ):
            if marker not in api_source:
                violations.append(Violation("cloud_campaign_write_api_route_missing", str(api_path.relative_to(root)), marker))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    write_record = registry_by_id.get("cloud_orchestrator_campaigns_write_legacy_family")
    if not write_record:
        violations.append(Violation("cloud_campaign_write_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_write_legacy_family"))
    else:
        if write_record.get("runtime_owner") != "next_command":
            violations.append(Violation("cloud_campaign_write_registry_owner", "cloud_orchestrator_campaigns_write_legacy_family", f"runtime_owner={write_record.get('runtime_owner')}"))
        if write_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_write_registry_legacy_allowed", "cloud_orchestrator_campaigns_write_legacy_family", f"legacy_fallback_allowed={write_record.get('legacy_fallback_allowed')}"))
        if write_record.get("legacy_source") not in {"", None}:
            violations.append(Violation("cloud_campaign_write_registry_legacy_source", "cloud_orchestrator_campaigns_write_legacy_family", f"legacy_source={write_record.get('legacy_source')}"))
        if write_record.get("delete_status") != "deletion_locked" or write_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_write_registry_lifecycle", "cloud_orchestrator_campaigns_write_legacy_family", f"delete_status={write_record.get('delete_status')} replacement_status={write_record.get('replacement_status')}"))
        if write_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("cloud_campaign_write_registry_adapter_mode", "cloud_orchestrator_campaigns_write_legacy_family", f"adapter_mode={write_record.get('adapter_mode')}"))
        if "run-due is separately deletion_locked" not in str(write_record.get("notes") or ""):
            violations.append(Violation("cloud_campaign_write_registry_run_due_boundary", "cloud_orchestrator_campaigns_write_legacy_family", "run-due locked boundary missing"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    write_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_METHODS)
    if not write_manifest:
        violations.append(Violation("cloud_campaign_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE))
    else:
        if write_manifest.get("current_runtime_owner") != "next_command":
            violations.append(Violation("cloud_campaign_write_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, f"current_runtime_owner={write_manifest.get('current_runtime_owner')}"))
        if write_manifest.get("production_behavior") != "next_command":
            violations.append(Violation("cloud_campaign_write_manifest_behavior", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, f"production_behavior={write_manifest.get('production_behavior')}"))
        if write_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_write_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, f"legacy_fallback_allowed={write_manifest.get('legacy_fallback_allowed')}"))
        if write_manifest.get("delete_ready") is not True:
            violations.append(Violation("cloud_campaign_write_manifest_delete_ready", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, f"delete_ready={write_manifest.get('delete_ready')}"))
        if write_manifest.get("delete_status") != "deletion_locked" or write_manifest.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_write_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, f"delete_status={write_manifest.get('delete_status')} replacement_status={write_manifest.get('replacement_status')}"))
        if write_manifest.get("adapter_mode") != "real_blocked":
            violations.append(Violation("cloud_campaign_write_manifest_adapter_mode", CLOUD_ORCHESTRATOR_CAMPAIGN_WRITE_ROUTE, f"adapter_mode={write_manifest.get('adapter_mode')}"))

    run_due_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, ("POST", "OPTIONS"))
    if not run_due_manifest:
        violations.append(Violation("cloud_campaign_write_run_due_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE))
    elif run_due_manifest.get("current_runtime_owner") != "next_runtime_plan" or run_due_manifest.get("delete_status") != "deletion_locked":
        violations.append(Violation("cloud_campaign_write_run_due_not_locked", "docs/route_ownership/production_route_ownership_manifest.yaml", str(run_due_manifest)))

    return violations


def check_cloud_orchestrator_run_due_next_safe_mode(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/cloud_orchestrator_run_due_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("cloud_campaign_run_due_inventory_missing", str(inventory_path.relative_to(root)), "missing run-due route inventory"))
    else:
        text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
            "PreviewCloudCampaignRunDueCommand",
            "PlanCloudCampaignRunDueCommand",
            "SideEffectPlan",
            "AuditLedger",
            "ExternalCallAttempt",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "production_compat rollback removed",
            "adapter_mode=real_blocked",
            "real_external_call_executed=false",
            "campaign_runtime_executed=false",
            "automation_runtime_executed=false",
            "wecom_send_executed=false",
            "automation-conversion/jobs/run-due",
            "out-of-scope",
        ):
            if phrase not in text:
                violations.append(Violation("cloud_campaign_run_due_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for route_path in CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_EXACT_ROUTES:
            if route_path not in text:
                violations.append(Violation("cloud_campaign_run_due_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    run_due_path = root / "aicrm_next/cloud_orchestrator/run_due.py"
    if not run_due_path.exists():
        violations.append(Violation("cloud_campaign_run_due_module_missing", str(run_due_path.relative_to(root)), "missing run_due.py"))
    else:
        source = run_due_path.read_text(encoding="utf-8")
        for marker in (
            "PreviewCloudCampaignRunDueCommand",
            "PlanCloudCampaignRunDueCommand",
            "InMemoryAuditLedger",
            "InMemorySideEffectPlanRepository",
            "InMemoryExternalCallAttemptRepository",
            "CommandBus",
            "cloud_orchestrator.campaign.run_due",
            "next_run_due_preview",
            "next_run_due_plan",
            "real_blocked",
            "campaign_runtime_executed",
            "automation_runtime_executed",
            "wecom_send_executed",
        ):
            if marker not in source:
                violations.append(Violation("cloud_campaign_run_due_module_marker_missing", str(run_due_path.relative_to(root)), marker))
        for marker, code in CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_DIRECT_EXTERNAL_MARKERS.items():
            if marker in source:
                violations.append(Violation(code, str(run_due_path.relative_to(root)), marker))

    api_path = root / "aicrm_next/cloud_orchestrator/api.py"
    if not api_path.exists():
        violations.append(Violation("cloud_campaign_run_due_api_missing", str(api_path.relative_to(root)), "missing cloud_orchestrator api"))
    else:
        api_source = api_path.read_text(encoding="utf-8")
        for marker in (
            "api_plan_cloud_campaign_run_due",
            "api_preview_cloud_campaign_run_due",
            "api_cloud_campaign_run_due_options",
            "api_cloud_campaign_run_due_preview_options",
            "execute_cloud_campaign_run_due_command",
        ):
            if marker not in api_source:
                violations.append(Violation("cloud_campaign_run_due_api_route_missing", str(api_path.relative_to(root)), marker))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        for route_path, methods in _decorator_route_methods(compat_path):
            if route_path in CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_EXACT_ROUTES and set(methods) & {"POST", "OPTIONS"}:
                violations.append(
                    Violation(
                        "cloud_campaign_run_due_production_compat_rollback",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={methods}",
                        "Cloud campaign run-due/preview rollback is deletion_locked to Next safe-mode planner.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    registry_record = registry_by_id.get("cloud_orchestrator_campaigns_run_due_safe_timer")
    if not registry_record:
        violations.append(Violation("cloud_campaign_run_due_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", "cloud_orchestrator_campaigns_run_due_safe_timer"))
    else:
        if registry_record.get("path_pattern") != CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE or tuple(registry_record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("cloud_campaign_run_due_registry_shape", "cloud_orchestrator_campaigns_run_due_safe_timer", f"path_pattern={registry_record.get('path_pattern')} methods={registry_record.get('methods')}"))
        if registry_record.get("runtime_owner") != "next_runtime_plan":
            violations.append(Violation("cloud_campaign_run_due_registry_owner", "cloud_orchestrator_campaigns_run_due_safe_timer", f"runtime_owner={registry_record.get('runtime_owner')}"))
        if registry_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_run_due_registry_legacy_allowed", "cloud_orchestrator_campaigns_run_due_safe_timer", f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
        if registry_record.get("legacy_source") not in {"", None}:
            violations.append(Violation("cloud_campaign_run_due_registry_legacy_source", "cloud_orchestrator_campaigns_run_due_safe_timer", f"legacy_source={registry_record.get('legacy_source')}"))
        if registry_record.get("external_side_effect_risk") != "high":
            violations.append(Violation("cloud_campaign_run_due_registry_side_effect_risk", "cloud_orchestrator_campaigns_run_due_safe_timer", f"external_side_effect_risk={registry_record.get('external_side_effect_risk')}"))
        if registry_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("cloud_campaign_run_due_registry_adapter_mode", "cloud_orchestrator_campaigns_run_due_safe_timer", f"adapter_mode={registry_record.get('adapter_mode')}"))
        if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_run_due_registry_lifecycle", "cloud_orchestrator_campaigns_run_due_safe_timer", f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_record = _record_for_path_and_methods(manifest_records, "route_pattern", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, ("POST", "OPTIONS"))
    if not manifest_record:
        violations.append(Violation("cloud_campaign_run_due_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE))
    else:
        if manifest_record.get("current_runtime_owner") != "next_runtime_plan":
            violations.append(Violation("cloud_campaign_run_due_manifest_owner", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
        if manifest_record.get("production_behavior") != "next_command":
            violations.append(Violation("cloud_campaign_run_due_manifest_behavior", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("cloud_campaign_run_due_manifest_legacy_allowed", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
        if manifest_record.get("production_behavior") in {"legacy_forward", "scheduled_safe_mode", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("cloud_campaign_run_due_manifest_legacy_behavior", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, f"production_behavior={manifest_record.get('production_behavior')}"))
        if manifest_record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("cloud_campaign_run_due_manifest_adapter_mode", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, f"adapter_mode={manifest_record.get('adapter_mode')}"))
        if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
            violations.append(Violation("cloud_campaign_run_due_manifest_lifecycle", CLOUD_ORCHESTRATOR_CAMPAIGN_RUN_DUE_ROUTE, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def check_automation_conversion_timers_next_safe_mode(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/automation_conversion_timer_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("automation_timer_inventory_missing", str(inventory_path.relative_to(root)), "missing timer route inventory"))
    else:
        text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
            "PlanReplyMonitorCaptureCommand",
            "PlanReplyMonitorRunDueCommand",
            "PreviewAutomationJobsRunDueCommand",
            "PlanAutomationJobsRunDueCommand",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "adapter_mode=real_blocked",
            "real_external_call_executed=false",
            "automation_runtime_executed=false",
            "wecom_send_executed=false",
            "next_reply_monitor_capture_plan",
            "next_reply_monitor_run_due_plan",
            "next_jobs_run_due_preview",
            "next_jobs_run_due_plan",
            "/api/admin/automation-conversion/tasks/run-due",
            "send-via-bazhuayu",
        ):
            if phrase not in text:
                violations.append(Violation("automation_timer_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for route_path in AUTOMATION_CONVERSION_TIMER_ROUTES:
            if route_path not in text:
                violations.append(Violation("automation_timer_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    timer_path = root / "aicrm_next/automation_engine/timers.py"
    if not timer_path.exists():
        violations.append(Violation("automation_timer_module_missing", str(timer_path.relative_to(root)), "missing timers.py"))
    else:
        source = timer_path.read_text(encoding="utf-8")
        for marker in (
            "PlanReplyMonitorCaptureCommand",
            "PlanReplyMonitorRunDueCommand",
            "PreviewAutomationJobsRunDueCommand",
            "PlanAutomationJobsRunDueCommand",
            "InMemoryAuditLedger",
            "InMemorySideEffectPlanRepository",
            "InMemoryExternalCallAttemptRepository",
            "CommandBus",
            "next_reply_monitor_capture_plan",
            "next_reply_monitor_run_due_plan",
            "next_jobs_run_due_preview",
            "next_jobs_run_due_plan",
            "real_blocked",
            "automation_runtime_executed",
            "wecom_send_executed",
        ):
            if marker not in source:
                violations.append(Violation("automation_timer_module_marker_missing", str(timer_path.relative_to(root)), marker))
        for marker, code in {**AUTOMATION_CONVERSION_TIMER_DIRECT_EXTERNAL_MARKERS, **AUTOMATION_CONVERSION_TIMER_TRUE_DEFAULT_MARKERS}.items():
            if marker in source:
                violations.append(Violation(code, str(timer_path.relative_to(root)), marker))

    api_path = root / "aicrm_next/automation_engine/api.py"
    if not api_path.exists():
        violations.append(Violation("automation_timer_api_missing", str(api_path.relative_to(root)), "missing automation api"))
    else:
        api_source = api_path.read_text(encoding="utf-8")
        for marker in (
            "api_plan_automation_conversion_reply_monitor_capture",
            "api_plan_automation_conversion_reply_monitor_run_due",
            "api_preview_automation_conversion_jobs_run_due",
            "api_plan_automation_conversion_jobs_run_due",
            "execute_automation_timer_command",
        ):
            if marker not in api_source:
                violations.append(Violation("automation_timer_api_route_missing", str(api_path.relative_to(root)), marker))
        sources = _decorated_route_function_sources(api_path)
        for route_path in AUTOMATION_CONVERSION_TIMER_ROUTES:
            joined = "\n".join(sources.get(route_path, []))
            if not joined:
                violations.append(Violation("automation_timer_api_route_missing", str(api_path.relative_to(root)), route_path))
                continue
            for marker, code in {**AUTOMATION_CONVERSION_TIMER_DIRECT_EXTERNAL_MARKERS, **AUTOMATION_CONVERSION_TIMER_TRUE_DEFAULT_MARKERS}.items():
                if marker in joined:
                    violations.append(Violation(code, str(api_path.relative_to(root)), f"{route_path}: {marker}"))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_methods = dict(_decorator_route_methods(compat_path))
        for route_path in AUTOMATION_CONVERSION_TIMER_ROUTES:
            if route_path in route_methods:
                violations.append(
                    Violation(
                        "automation_timer_production_compat_rollback",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={route_methods[route_path]}",
                        "Automation conversion timer routes are deletion_locked to the Next safe-mode planner.",
                    )
                )
    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id, route_path in AUTOMATION_CONVERSION_TIMER_REGISTRY_RECORDS.items():
        record = registry_by_id.get(route_id)
        if not record:
            violations.append(Violation("automation_timer_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("path_pattern") != route_path or tuple(record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("automation_timer_registry_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != "next_runtime_plan":
            violations.append(Violation("automation_timer_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_timer_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("automation_timer_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("external_side_effect_risk") != "high":
            violations.append(Violation("automation_timer_registry_side_effect_risk", route_id, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("automation_timer_registry_adapter_mode", route_id, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_timer_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    for route_path in AUTOMATION_CONVERSION_TIMER_MANIFEST_ROUTES:
        record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("POST", "OPTIONS"))
        if not record:
            violations.append(Violation("automation_timer_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_runtime_plan":
            violations.append(Violation("automation_timer_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("automation_timer_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_timer_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("production_behavior") in {"legacy_forward", "scheduled_safe_mode", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("automation_timer_manifest_legacy_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("automation_timer_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_timer_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    return violations


def check_automation_workspace_runtime_next_safe_mode(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/automation_workspace_runtime_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("automation_workspace_inventory_missing", str(inventory_path.relative_to(root)), "missing workspace runtime route inventory"))
    else:
        text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
            "PlanAutomationOperationTasksRunDueCommand",
            "PlanAutomationExecutionItemBazhuayuDispatchCommand",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "adapter_mode=real_blocked",
            "real_external_call_executed=false",
            "automation_runtime_executed=false",
            "operation_tasks_executed=false",
            "bazhuayu_send_executed=false",
            "wecom_send_executed=false",
            "next_automation_tasks_run_due_plan",
            "next_bazhuayu_dispatch_plan",
            "member/manual/focus/SOP",
            "customer automation webhooks",
        ):
            if phrase not in text:
                violations.append(Violation("automation_workspace_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for route_path in AUTOMATION_WORKSPACE_RUNTIME_API_ROUTES:
            if route_path not in text:
                violations.append(Violation("automation_workspace_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    runtime_path = root / "aicrm_next/automation_engine/workspace_runtime.py"
    if not runtime_path.exists():
        violations.append(Violation("automation_workspace_module_missing", str(runtime_path.relative_to(root)), "missing workspace_runtime.py"))
    else:
        source = runtime_path.read_text(encoding="utf-8")
        for marker in (
            "PlanAutomationOperationTasksRunDueCommand",
            "PlanAutomationExecutionItemOutboundDispatchCommand",
            "InMemoryAuditLedger",
            "InMemorySideEffectPlanRepository",
            "InMemoryExternalCallAttemptRepository",
            "CommandBus",
            "next_automation_tasks_run_due_plan",
            "next_bazhuayu_dispatch_plan",
            "real_blocked",
            "operation_tasks_executed",
            "bazhuayu_send_executed",
            "wecom_send_executed",
        ):
            if marker not in source:
                violations.append(Violation("automation_workspace_module_marker_missing", str(runtime_path.relative_to(root)), marker))
        for marker, code in {**AUTOMATION_WORKSPACE_RUNTIME_DIRECT_EXTERNAL_MARKERS, **AUTOMATION_WORKSPACE_RUNTIME_TRUE_DEFAULT_MARKERS}.items():
            if marker in source:
                violations.append(Violation(code, str(runtime_path.relative_to(root)), marker))

    api_path = root / "aicrm_next/automation_engine/api.py"
    if not api_path.exists():
        violations.append(Violation("automation_workspace_api_missing", str(api_path.relative_to(root)), "missing automation api"))
    else:
        api_source = api_path.read_text(encoding="utf-8")
        for marker in (
            "api_plan_automation_workspace_tasks_run_due",
            "api_plan_automation_workspace_execution_item_outbound",
            "api_automation_workspace_tasks_run_due_options",
            "api_automation_workspace_execution_item_outbound_options",
            "execute_workspace_runtime_command",
        ):
            if marker not in api_source:
                violations.append(Violation("automation_workspace_api_route_missing", str(api_path.relative_to(root)), marker))
        sources = _decorated_route_function_sources(api_path)
        for route_path in AUTOMATION_WORKSPACE_RUNTIME_API_ROUTES:
            joined = "\n".join(sources.get(route_path, []))
            if not joined:
                violations.append(Violation("automation_workspace_api_route_missing", str(api_path.relative_to(root)), route_path))
                continue
            for marker, code in {**AUTOMATION_WORKSPACE_RUNTIME_DIRECT_EXTERNAL_MARKERS, **AUTOMATION_WORKSPACE_RUNTIME_TRUE_DEFAULT_MARKERS}.items():
                if marker in joined:
                    violations.append(Violation(code, str(api_path.relative_to(root)), f"{route_path}: {marker}"))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_methods = dict(_decorator_route_methods(compat_path))
        for route_path in AUTOMATION_WORKSPACE_RUNTIME_ROUTES:
            if route_path in route_methods:
                violations.append(
                    Violation(
                        "automation_workspace_production_compat_rollback",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={route_methods[route_path]}",
                        "Automation workspace runtime routes are deletion_locked to the Next safe-mode planner.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id, route_path in AUTOMATION_WORKSPACE_RUNTIME_REGISTRY_RECORDS.items():
        record = registry_by_id.get(route_id)
        if not record:
            violations.append(Violation("automation_workspace_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("path_pattern") != route_path or tuple(record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("automation_workspace_registry_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != "next_runtime_plan":
            violations.append(Violation("automation_workspace_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_workspace_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("automation_workspace_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("external_side_effect_risk") != "high":
            violations.append(Violation("automation_workspace_registry_side_effect_risk", route_id, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("automation_workspace_registry_adapter_mode", route_id, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_workspace_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    for route_path in AUTOMATION_WORKSPACE_RUNTIME_MANIFEST_ROUTES:
        record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("POST", "OPTIONS"))
        if not record:
            violations.append(Violation("automation_workspace_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
            continue
        if record.get("current_runtime_owner") != "next_runtime_plan":
            violations.append(Violation("automation_workspace_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("automation_workspace_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_workspace_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("production_behavior") in {"legacy_forward", "scheduled_safe_mode", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("automation_workspace_manifest_legacy_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("automation_workspace_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_workspace_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    return violations


def check_automation_member_actions_next_safe_mode(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/automation_member_actions_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("automation_member_inventory_missing", str(inventory_path.relative_to(root)), "missing member actions inventory"))
    else:
        text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Frontend ↔ API ↔ Backend Contract Matrix",
            "GetAutomationMemberDetailQuery",
            "PutAutomationMemberInPoolCommand",
            "RemoveAutomationMemberFromPoolCommand",
            "SetAutomationMemberFocusCommand",
            "SetAutomationMemberNormalCommand",
            "MarkAutomationMemberWonCommand",
            "UnmarkAutomationMemberWonCommand",
            "PlanAutomationMemberOpenClawPushCommand",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "adapter_mode=real_blocked",
            "real_external_call_executed=false",
            "automation_runtime_executed=false",
            "openclaw_push_executed=false",
            "stage manual-send",
            "focus-send-batches",
            "SOP",
            "customer automation webhook",
        ):
            if phrase not in text:
                violations.append(Violation("automation_member_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for route_path in AUTOMATION_MEMBER_API_ROUTES:
            if route_path not in text:
                violations.append(Violation("automation_member_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_methods = dict(_decorator_route_methods(compat_path))
        for route_path in (AUTOMATION_MEMBER_DETAIL_ROUTE, AUTOMATION_MEMBER_WILDCARD_ROUTE):
            if route_path in route_methods:
                violations.append(
                    Violation(
                        "automation_member_production_compat_rollback",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={route_methods[route_path]}",
                        "Automation member detail/actions are deletion_locked to Next read-model and commands.",
                    )
                )

    module_path = root / "aicrm_next/automation_engine/member_actions.py"
    if not module_path.exists():
        violations.append(Violation("automation_member_module_missing", str(module_path.relative_to(root)), "missing member_actions.py"))
    else:
        source = module_path.read_text(encoding="utf-8")
        for marker in (
            "GetAutomationMemberDetailQuery",
            "PutAutomationMemberInPoolCommand",
            "RemoveAutomationMemberFromPoolCommand",
            "SetAutomationMemberFocusCommand",
            "SetAutomationMemberNormalCommand",
            "MarkAutomationMemberWonCommand",
            "UnmarkAutomationMemberWonCommand",
            "PlanAutomationMemberOpenClawPushCommand",
            "InMemoryAuditLedger",
            "InMemorySideEffectPlanRepository",
            "InMemoryExternalCallAttemptRepository",
            "CommandBus",
            "next_automation_member_read",
            "next_command",
            "real_blocked",
            "openclaw_push_executed",
        ):
            if marker not in source:
                violations.append(Violation("automation_member_module_marker_missing", str(module_path.relative_to(root)), marker))
        for marker, code in {**AUTOMATION_MEMBER_DIRECT_MARKERS, **AUTOMATION_MEMBER_TRUE_DEFAULT_MARKERS}.items():
            if marker in source:
                violations.append(Violation(code, str(module_path.relative_to(root)), marker))

    api_path = root / "aicrm_next/automation_engine/api.py"
    if not api_path.exists():
        violations.append(Violation("automation_member_api_missing", str(api_path.relative_to(root)), "missing automation api"))
    else:
        api_source = api_path.read_text(encoding="utf-8")
        for marker in (
            "api_automation_member_detail",
            "api_plan_automation_member_put_in_pool",
            "api_plan_automation_member_remove_from_pool",
            "api_plan_automation_member_set_focus",
            "api_plan_automation_member_set_normal",
            "api_plan_automation_member_mark_won",
            "api_plan_automation_member_unmark_won",
            "api_plan_automation_member_push_openclaw",
            "execute_member_action_command",
            "read_automation_member_detail",
        ):
            if marker not in api_source:
                violations.append(Violation("automation_member_api_route_missing", str(api_path.relative_to(root)), marker))
        sources = _decorated_route_function_sources(api_path)
        for route_path in AUTOMATION_MEMBER_API_ROUTES:
            joined = "\n".join(sources.get(route_path, []))
            if not joined:
                violations.append(Violation("automation_member_api_route_missing", str(api_path.relative_to(root)), route_path))
                continue
            for marker, code in {**AUTOMATION_MEMBER_DIRECT_MARKERS, **AUTOMATION_MEMBER_TRUE_DEFAULT_MARKERS}.items():
                if marker in joined:
                    violations.append(Violation(code, str(api_path.relative_to(root)), f"{route_path}: {marker}"))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    detail_record = registry_by_id.get("automation_member_detail_next_read_model")
    if not detail_record:
        violations.append(Violation("automation_member_registry_missing", "automation_member_detail_next_read_model", AUTOMATION_MEMBER_DETAIL_ROUTE))
    else:
        if detail_record.get("path_pattern") != AUTOMATION_MEMBER_DETAIL_ROUTE or tuple(detail_record.get("methods") or []) != ("GET", "HEAD"):
            violations.append(Violation("automation_member_registry_shape", "automation_member_detail_next_read_model", f"path_pattern={detail_record.get('path_pattern')} methods={detail_record.get('methods')}"))
        if detail_record.get("runtime_owner") != "next_read_model":
            violations.append(Violation("automation_member_registry_owner", "automation_member_detail_next_read_model", f"runtime_owner={detail_record.get('runtime_owner')}"))
        if detail_record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_member_registry_legacy_allowed", "automation_member_detail_next_read_model", f"legacy_fallback_allowed={detail_record.get('legacy_fallback_allowed')}"))
        if detail_record.get("external_side_effect_risk") != "none":
            violations.append(Violation("automation_member_registry_side_effect_risk", "automation_member_detail_next_read_model", f"external_side_effect_risk={detail_record.get('external_side_effect_risk')}"))
        if detail_record.get("delete_status") != "deletion_locked" or detail_record.get("replacement_status") != "locked":
            violations.append(Violation("automation_member_registry_lifecycle", "automation_member_detail_next_read_model", f"delete_status={detail_record.get('delete_status')} replacement_status={detail_record.get('replacement_status')}"))
    for route_id, route_path in AUTOMATION_MEMBER_ACTION_ROUTES.items():
        record = registry_by_id.get(route_id)
        if not record:
            violations.append(Violation("automation_member_registry_missing", route_id, route_path))
            continue
        if record.get("path_pattern") != route_path or tuple(record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("automation_member_registry_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != "next_command":
            violations.append(Violation("automation_member_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_member_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        expected_risk = "high" if route_id == "automation_member_push_openclaw_next_command" else "medium"
        if record.get("external_side_effect_risk") != expected_risk:
            violations.append(Violation("automation_member_registry_side_effect_risk", route_id, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("automation_member_registry_adapter_mode", route_id, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_member_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    detail_manifest = _record_for_path_and_methods(manifest_records, "route_pattern", AUTOMATION_MEMBER_DETAIL_ROUTE, ("GET", "HEAD"))
    if not detail_manifest:
        violations.append(Violation("automation_member_manifest_missing", AUTOMATION_MEMBER_DETAIL_ROUTE, "GET/HEAD"))
    else:
        if detail_manifest.get("current_runtime_owner") != "next_read_model":
            violations.append(Violation("automation_member_manifest_owner", AUTOMATION_MEMBER_DETAIL_ROUTE, f"current_runtime_owner={detail_manifest.get('current_runtime_owner')}"))
        if detail_manifest.get("production_behavior") != "next_exact":
            violations.append(Violation("automation_member_manifest_behavior", AUTOMATION_MEMBER_DETAIL_ROUTE, f"production_behavior={detail_manifest.get('production_behavior')}"))
        if detail_manifest.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_member_manifest_legacy_allowed", AUTOMATION_MEMBER_DETAIL_ROUTE, f"legacy_fallback_allowed={detail_manifest.get('legacy_fallback_allowed')}"))
        if detail_manifest.get("delete_status") != "deletion_locked" or detail_manifest.get("replacement_status") != "locked":
            violations.append(Violation("automation_member_manifest_lifecycle", AUTOMATION_MEMBER_DETAIL_ROUTE, f"delete_status={detail_manifest.get('delete_status')} replacement_status={detail_manifest.get('replacement_status')}"))
    for route_path in AUTOMATION_MEMBER_ACTION_ROUTES.values():
        record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("POST", "OPTIONS"))
        if not record:
            violations.append(Violation("automation_member_manifest_missing", route_path, "POST/OPTIONS"))
            continue
        if record.get("current_runtime_owner") != "next_command":
            violations.append(Violation("automation_member_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("automation_member_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_member_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("automation_member_manifest_legacy_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("adapter_mode") != "real_blocked":
            violations.append(Violation("automation_member_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_member_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    return violations


def check_automation_overview_pools_next_read_model(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    module_path = root / "aicrm_next/automation_engine/overview_read_model.py"
    if not module_path.exists():
        violations.append(Violation("automation_overview_read_model_missing", str(module_path.relative_to(root)), "missing overview_read_model.py"))
    else:
        source = module_path.read_text(encoding="utf-8")
        for marker in (
            "AutomationOverviewReadModel",
            "AutomationPoolReadModel",
            "AutomationStageColumnProjection",
            "automation_member",
            "stage_columns",
            "focus_count",
            "normal_count",
            "today_new_count",
            "source_status",
            "next_read_model",
        ):
            if marker not in source:
                violations.append(Violation("automation_overview_read_model_marker_missing", str(module_path.relative_to(root)), marker))
        for marker in AUTOMATION_OVERVIEW_POOL_FORBIDDEN_API_MARKERS:
            if marker in source:
                violations.append(Violation("automation_overview_read_model_legacy_marker", str(module_path.relative_to(root)), marker))

    api_path = root / "aicrm_next/automation_engine/api.py"
    if not api_path.exists():
        violations.append(Violation("automation_overview_api_missing", str(api_path.relative_to(root)), "missing automation api"))
    else:
        api_source = api_path.read_text(encoding="utf-8")
        for marker in ("AutomationOverviewReadModel", "AutomationPoolReadModel", "X-AICRM-Fallback-Used"):
            if marker not in api_source:
                violations.append(Violation("automation_overview_api_marker_missing", str(api_path.relative_to(root)), marker))
        sources = _decorated_route_function_sources(api_path)
        for route_path in AUTOMATION_OVERVIEW_POOL_ROUTES:
            joined = "\n".join(sources.get(route_path, []))
            if not joined:
                violations.append(Violation("automation_overview_api_route_missing", str(api_path.relative_to(root)), route_path))
                continue
            for marker in AUTOMATION_OVERVIEW_POOL_FORBIDDEN_API_MARKERS:
                if marker in joined:
                    violations.append(Violation("automation_overview_api_legacy_marker", str(api_path.relative_to(root)), f"{route_path}: {marker}"))
            if "JSONResponse" not in joined or "Automation" not in joined:
                violations.append(Violation("automation_overview_api_not_next_read_model", str(api_path.relative_to(root)), route_path))

    facade_path = root / "aicrm_next/integration_gateway/legacy_automation_facade.py"
    if facade_path.exists():
        facade_source = facade_path.read_text(encoding="utf-8")
        for marker in AUTOMATION_OVERVIEW_POOL_DELETED_MARKERS:
            if marker in facade_source:
                violations.append(Violation("automation_overview_deleted_facade_function", str(facade_path.relative_to(root)), marker))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id, route_path in AUTOMATION_OVERVIEW_POOL_ROUTE_IDS.items():
        record = registry_by_id.get(route_id)
        if not record:
            violations.append(Violation("automation_overview_registry_missing", route_id, route_path))
            continue
        if record.get("path_pattern") != route_path or tuple(record.get("methods") or []) != ("GET",):
            violations.append(Violation("automation_overview_registry_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != "next_read_model":
            violations.append(Violation("automation_overview_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_overview_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("external_side_effect_risk") != "none":
            violations.append(Violation("automation_overview_registry_side_effect_risk", route_id, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_overview_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    for route_path in AUTOMATION_OVERVIEW_POOL_ROUTES:
        record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("GET",))
        if not record:
            violations.append(Violation("automation_overview_manifest_missing", route_path, "GET"))
            continue
        if record.get("current_runtime_owner") != "next_read_model":
            violations.append(Violation("automation_overview_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_exact":
            violations.append(Violation("automation_overview_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("automation_overview_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("external_side_effect_risk") != "none":
            violations.append(Violation("automation_overview_manifest_side_effect_risk", route_path, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("automation_overview_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    return violations


def check_group_ops_admin_pages_next_native(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    frontend_routes = root / "aicrm_next/frontend_compat/legacy_routes.py"
    native_pages = root / "aicrm_next/automation_engine/group_ops/admin_pages.py"
    native_template = root / "aicrm_next/automation_engine/group_ops/templates/admin_console/group_ops.html"
    native_static = root / "aicrm_next/automation_engine/group_ops/static/admin_console"
    main_path = root / "aicrm_next/main.py"

    if frontend_routes.exists():
        source = frontend_routes.read_text(encoding="utf-8")
        for route in GROUP_OPS_ADMIN_PAGE_ROUTES:
            if route in source:
                violations.append(Violation("group_ops_admin_page_legacy_route", str(frontend_routes.relative_to(root)), route))
        for marker in ("def _group_ops_page_context", "def admin_group_ops_ui", "def admin_group_ops_plan_detail", "def admin_group_ops_groups_ui"):
            if marker in source:
                violations.append(Violation("group_ops_admin_page_legacy_handler", str(frontend_routes.relative_to(root)), marker))

    retired_frontend_assets = (
        root / "aicrm_next/frontend_compat/templates/admin_console/group_ops.html",
        root / "aicrm_next/frontend_compat/static/admin_console/group_ops.css",
        root / "aicrm_next/frontend_compat/static/admin_console/group_ops.js",
    )
    for path in retired_frontend_assets:
        if path.exists():
            violations.append(Violation("group_ops_admin_page_frontend_asset", str(path.relative_to(root)), "retired asset still present"))

    required_native_paths = (
        native_pages,
        native_template,
        native_static / "group_ops.css",
        native_static / "group_ops.js",
    )
    for path in required_native_paths:
        if not path.exists():
            violations.append(Violation("group_ops_admin_page_native_asset_missing", str(path.relative_to(root)), "missing native group ops page bundle file"))

    if native_pages.exists():
        source = native_pages.read_text(encoding="utf-8")
        for route in GROUP_OPS_ADMIN_PAGE_ROUTES:
            if route.replace("{plan_id}", "{plan_id:int}") not in source and route not in source:
                violations.append(Violation("group_ops_admin_page_native_route_missing", str(native_pages.relative_to(root)), route))

    if native_template.exists():
        template = native_template.read_text(encoding="utf-8")
        if "/static/group-ops/admin_console/group_ops.css" not in template or "/static/group-ops/admin_console/group_ops.js" not in template:
            violations.append(Violation("group_ops_admin_page_native_static_path", str(native_template.relative_to(root)), "group ops page static path must use native bundle"))

    if main_path.exists():
        main_source = main_path.read_text(encoding="utf-8")
        if "group_ops_admin_pages_router" not in main_source:
            violations.append(Violation("group_ops_admin_page_router_not_mounted", str(main_path.relative_to(root)), "group_ops_admin_pages_router"))
        if '"/static/group-ops"' not in main_source:
            violations.append(Violation("group_ops_admin_page_static_not_mounted", str(main_path.relative_to(root)), "/static/group-ops"))

    return violations


def check_customer_automation_webhook_next_safe_mode(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    inventory_path = root / "docs/architecture/customer_automation_webhook_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("customer_automation_webhook_inventory_missing", str(inventory_path.relative_to(root)), "missing customer automation webhook inventory"))
    else:
        text = inventory_path.read_text(encoding="utf-8")
        for phrase in (
            "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
            "ApplyCustomerActivationWebhookCommand",
            "PlanCustomerWebhookDeliveryRetryCommand",
            "PlanCustomerWebhookDeliveryRetryDueCommand",
            "legacy_fallback_allowed=false",
            "deletion_locked",
            "adapter_mode=local",
            "adapter_mode=real_blocked",
            "real_external_call_executed=false",
            "outbound_webhook_executed=false",
            "next_customer_activation_webhook",
            "next_customer_webhook_retry_plan",
            "next_customer_webhook_retry_due_plan",
        ):
            if phrase not in text:
                violations.append(Violation("customer_automation_webhook_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for route_path in CUSTOMER_AUTOMATION_WEBHOOK_API_ROUTES:
            if route_path not in text:
                violations.append(Violation("customer_automation_webhook_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))

    compat_path = root / "aicrm_next/production_compat/api.py"
    if compat_path.exists():
        route_methods = dict(_decorator_route_methods(compat_path))
        for route_path in CUSTOMER_AUTOMATION_WEBHOOK_COMPAT_ROUTES:
            if route_path in route_methods:
                violations.append(
                    Violation(
                        "customer_automation_webhook_production_compat_rollback",
                        str(compat_path.relative_to(root)),
                        f"{route_path} methods={route_methods[route_path]}",
                        "Customer automation webhook writes are deletion_locked to Next safe-mode routes.",
                    )
                )

    module_path = root / "aicrm_next/automation_engine/customer_webhooks.py"
    if not module_path.exists():
        violations.append(Violation("customer_automation_webhook_module_missing", str(module_path.relative_to(root)), "missing customer_webhooks.py"))
    else:
        source = module_path.read_text(encoding="utf-8")
        for marker in (
            "ApplyCustomerActivationWebhookCommand",
            "PlanCustomerWebhookDeliveryRetryCommand",
            "PlanCustomerWebhookDeliveryRetryDueCommand",
            "InMemoryAuditLedger",
            "InMemorySideEffectPlanRepository",
            "InMemoryExternalCallAttemptRepository",
            "CommandBus",
            "next_customer_activation_webhook",
            "next_customer_webhook_retry_plan",
            "next_customer_webhook_retry_due_plan",
            "real_blocked",
            "outbound_webhook_executed",
        ):
            if marker not in source:
                violations.append(Violation("customer_automation_webhook_module_marker_missing", str(module_path.relative_to(root)), marker))
        for marker, code in {**CUSTOMER_AUTOMATION_WEBHOOK_DIRECT_MARKERS, **CUSTOMER_AUTOMATION_WEBHOOK_TRUE_DEFAULT_MARKERS}.items():
            if marker in source:
                violations.append(Violation(code, str(module_path.relative_to(root)), marker))

    api_path = root / "aicrm_next/automation_engine/api.py"
    if not api_path.exists():
        violations.append(Violation("customer_automation_webhook_api_missing", str(api_path.relative_to(root)), "missing automation api"))
    else:
        api_source = api_path.read_text(encoding="utf-8")
        for marker in (
            "api_customer_automation_activation_webhook",
            "api_plan_customer_automation_webhook_delivery_retry",
            "api_plan_customer_automation_webhook_delivery_retry_due",
            "execute_customer_webhook_command",
        ):
            if marker not in api_source:
                violations.append(Violation("customer_automation_webhook_api_route_missing", str(api_path.relative_to(root)), marker))
        sources = _decorated_route_function_sources(api_path)
        for route_path, source_status in CUSTOMER_AUTOMATION_WEBHOOK_API_ROUTES.items():
            api_route_path = route_path.replace("{delivery_id}", "{delivery_id:int}")
            joined = "\n".join(sources.get(api_route_path, sources.get(route_path, [])))
            if not joined:
                violations.append(Violation("customer_automation_webhook_api_route_missing", str(api_path.relative_to(root)), route_path))
                continue
            if source_status not in joined:
                violations.append(Violation("customer_automation_webhook_api_source_status_missing", str(api_path.relative_to(root)), f"{route_path}: {source_status}"))
            for marker, code in {**CUSTOMER_AUTOMATION_WEBHOOK_DIRECT_MARKERS, **CUSTOMER_AUTOMATION_WEBHOOK_TRUE_DEFAULT_MARKERS}.items():
                if marker in joined:
                    violations.append(Violation(code, str(api_path.relative_to(root)), f"{route_path}: {marker}"))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_id = {record.get("route_id"): record for record in registry_records}
    for route_id, (route_path, expected_owner, expected_risk, expected_adapter) in CUSTOMER_AUTOMATION_WEBHOOK_REGISTRY_RECORDS.items():
        record = registry_by_id.get(route_id)
        if not record:
            violations.append(Violation("customer_automation_webhook_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_id))
            continue
        if record.get("path_pattern") != route_path or tuple(record.get("methods") or []) != ("POST", "OPTIONS"):
            violations.append(Violation("customer_automation_webhook_registry_shape", route_id, f"path_pattern={record.get('path_pattern')} methods={record.get('methods')}"))
        if record.get("runtime_owner") != expected_owner:
            violations.append(Violation("customer_automation_webhook_registry_owner", route_id, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("customer_automation_webhook_registry_legacy_allowed", route_id, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("legacy_source") not in {"", None}:
            violations.append(Violation("customer_automation_webhook_registry_legacy_source", route_id, f"legacy_source={record.get('legacy_source')}"))
        if record.get("external_side_effect_risk") != expected_risk:
            violations.append(Violation("customer_automation_webhook_registry_side_effect_risk", route_id, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("adapter_mode") != expected_adapter:
            violations.append(Violation("customer_automation_webhook_registry_adapter_mode", route_id, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("customer_automation_webhook_registry_lifecycle", route_id, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    for route_path, (_source_status, expected_owner, expected_risk, expected_adapter) in {
        "/api/customers/automation/activation-webhook": ("next_customer_activation_webhook", "next_command", "medium", "local"),
        "/api/customers/automation/webhook-deliveries/{delivery_id}/retry": ("next_customer_webhook_retry_plan", "next_runtime_plan", "high", "real_blocked"),
        "/api/customers/automation/webhook-deliveries/retry-due": ("next_customer_webhook_retry_due_plan", "next_runtime_plan", "high", "real_blocked"),
    }.items():
        record = _record_for_path_and_methods(manifest_records, "route_pattern", route_path, ("POST", "OPTIONS"))
        if not record:
            violations.append(Violation("customer_automation_webhook_manifest_missing", route_path, "POST/OPTIONS"))
            continue
        if record.get("current_runtime_owner") != expected_owner:
            violations.append(Violation("customer_automation_webhook_manifest_owner", route_path, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") != "next_command":
            violations.append(Violation("customer_automation_webhook_manifest_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("legacy_fallback_allowed") is not False:
            violations.append(Violation("customer_automation_webhook_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={record.get('legacy_fallback_allowed')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("customer_automation_webhook_manifest_legacy_behavior", route_path, f"production_behavior={record.get('production_behavior')}"))
        if record.get("external_side_effect_risk") != expected_risk:
            violations.append(Violation("customer_automation_webhook_manifest_side_effect_risk", route_path, f"external_side_effect_risk={record.get('external_side_effect_risk')}"))
        if record.get("adapter_mode") != expected_adapter:
            violations.append(Violation("customer_automation_webhook_manifest_adapter_mode", route_path, f"adapter_mode={record.get('adapter_mode')}"))
        if record.get("delete_status") != "deletion_locked" or record.get("replacement_status") != "locked":
            violations.append(Violation("customer_automation_webhook_manifest_lifecycle", route_path, f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}"))

    return violations


def check_wecom_tag_write_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/wecom_tag_write_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("wecom_tag_write_inventory_missing", str(inventory_path.relative_to(root)), "missing inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path, _methods in WECOM_TAG_WRITE_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_write_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for route_path, _methods in WECOM_TAG_SYNC_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_sync_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for phrase in ("Frontend API Backend Contract Matrix", "SideEffectPlan", "production_compat rollback removed", "legacy_fallback_allowed=false", "deletion_locked", "real_external_call_executed=false"):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_write_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))
        for phrase in ("execute_wecom_tag_catalog_sync", "next_live_catalog_sync", "live_catalog_sync", "sync_executed=true"):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_sync_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/customer_tags/api.py"
    admin_write_path = root / "aicrm_next/customer_tags/admin_write.py"
    commands_path = root / "aicrm_next/customer_tags/commands.py"
    write_repo_path = root / "aicrm_next/customer_tags/write_repo.py"
    sync_service_path = root / "aicrm_next/customer_tags/sync_service.py"
    main_path = root / "aicrm_next/main.py"
    production_compat_path = root / "aicrm_next/production_compat/api.py"

    if not api_path.exists():
        violations.append(Violation("wecom_tag_write_api_missing", str(api_path.relative_to(root)), "missing customer_tags api"))
    else:
        api_text = api_path.read_text(encoding="utf-8")
        if "write_router = APIRouter()" not in api_text:
            violations.append(Violation("wecom_tag_write_router_missing", str(api_path.relative_to(root)), "write_router = APIRouter()"))
        for route_path, _methods in WECOM_TAG_WRITE_ROUTES:
            if route_path not in api_text:
                violations.append(Violation("wecom_tag_write_exact_route_missing", str(api_path.relative_to(root)), route_path))
        for route_path, _methods in WECOM_TAG_SYNC_ROUTES:
            if route_path not in api_text:
                violations.append(Violation("wecom_tag_sync_exact_route_missing", str(api_path.relative_to(root)), route_path))
        if "execute_wecom_tag_write" not in api_text:
            violations.append(Violation("wecom_tag_write_command_executor_missing", str(api_path.relative_to(root)), "execute_wecom_tag_write"))
        if "execute_wecom_tag_catalog_sync" not in api_text:
            violations.append(Violation("wecom_tag_sync_executor_missing", str(api_path.relative_to(root)), "execute_wecom_tag_catalog_sync"))

    for path, marker in [
        (admin_write_path, "execute_wecom_tag_write"),
        (commands_path, "WeComTagWriteCommand"),
        (write_repo_path, "WeComTagWriteRepository"),
    ]:
        if not path.exists():
            violations.append(Violation("wecom_tag_write_module_missing", str(path.relative_to(root)), marker))
            continue
        source = path.read_text(encoding="utf-8")
        if marker not in source:
            violations.append(Violation("wecom_tag_write_module_marker_missing", str(path.relative_to(root)), marker))
        for forbidden, code in {
            "forward_to_legacy_flask": "wecom_tag_write_legacy_forward",
            "legacy_flask_facade": "wecom_tag_write_legacy_facade",
            "X-AICRM-Compatibility-Facade": "wecom_tag_write_compatibility_facade",
            '"fallback_used": True': "wecom_tag_write_fallback_used_true",
            "'fallback_used': True": "wecom_tag_write_fallback_used_true",
            '"real_external_call_executed": True': "wecom_tag_write_real_external_call_true",
            "'real_external_call_executed': True": "wecom_tag_write_real_external_call_true",
            '"sync_executed": True': "wecom_tag_write_sync_executed_true",
            "'sync_executed': True": "wecom_tag_write_sync_executed_true",
            "requests.": "wecom_tag_write_direct_http_client",
            "httpx.": "wecom_tag_write_direct_http_client",
            "WeComTagLiveGateway": "wecom_tag_write_real_wecom_gateway",
            "mark_external_contact_tags": "wecom_tag_write_real_wecom_mutation",
        }.items():
            if forbidden in source:
                violations.append(Violation(code, str(path.relative_to(root)), forbidden))

    if not sync_service_path.exists():
        violations.append(Violation("wecom_tag_sync_service_missing", str(sync_service_path.relative_to(root)), "missing sync service"))
    else:
        sync_source = sync_service_path.read_text(encoding="utf-8")
        for marker in ("execute_wecom_tag_catalog_sync", "WeComTagSyncRepository", "build_wecom_tag_live_gateway"):
            if marker not in sync_source:
                violations.append(Violation("wecom_tag_sync_service_marker_missing", str(sync_service_path.relative_to(root)), marker))
        for forbidden, code in {
            "forward_to_legacy_flask": "wecom_tag_sync_legacy_forward",
            "legacy_flask_facade": "wecom_tag_sync_legacy_facade",
            "X-AICRM-Compatibility-Facade": "wecom_tag_sync_compatibility_facade",
            '"fallback_used": True': "wecom_tag_sync_fallback_used_true",
            "'fallback_used': True": "wecom_tag_sync_fallback_used_true",
            "mark_external_contact_tags": "wecom_tag_sync_real_wecom_mutation",
            "externalcontact/add_corp_tag": "wecom_tag_sync_real_wecom_mutation",
            "externalcontact/edit_corp_tag": "wecom_tag_sync_real_wecom_mutation",
            "externalcontact/del_corp_tag": "wecom_tag_sync_real_wecom_mutation",
        }.items():
            if forbidden in sync_source:
                violations.append(Violation(code, str(sync_service_path.relative_to(root)), forbidden))

    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        write_include = main_text.find("include_router(customer_tags_write_router)")
        compat_include = main_text.find(PROD_COMPAT_INCLUDE)
        if write_include < 0:
            violations.append(Violation("wecom_tag_write_router_order", str(main_path.relative_to(root)), "customer_tags_write_router missing"))
        elif compat_include >= 0 and write_include > compat_include:
            violations.append(Violation("wecom_tag_write_router_order", str(main_path.relative_to(root)), f"customer_tags_write_router must be included before {PROD_COMPAT_ROUTER_NAME}"))

    if production_compat_path.exists():
        compat_sources = _decorated_route_function_sources(production_compat_path)
        for route_path in compat_sources:
            if route_path.startswith("/api/admin/wecom/tags") or route_path.startswith("/api/admin/wecom/tag-groups"):
                violations.append(
                    Violation(
                        "wecom_tag_write_production_compat_route",
                        str(production_compat_path.relative_to(root)),
                        route_path,
                        "WeCom tag read/write/sync production_compat rollback is deleted; keep live/fake routes in aicrm_next.customer_tags only.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_route = {(record.get("path_pattern"), tuple(record.get("methods") or [])): record for record in registry_records}
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_route = {(record.get("route_pattern"), tuple(record.get("methods") or [])): record for record in manifest_records}

    for route_path, methods in WECOM_TAG_WRITE_ROUTES:
        registry_record = registry_by_route.get((route_path, methods))
        if registry_record is None:
            violations.append(Violation("wecom_tag_write_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if registry_record.get("runtime_owner") != "next_command":
                violations.append(Violation("wecom_tag_write_registry_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_write_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
            if registry_record.get("legacy_source") not in {"", None}:
                violations.append(Violation("wecom_tag_write_registry_legacy_source", route_path, f"legacy_source={registry_record.get('legacy_source')}"))
            if registry_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_write_registry_adapter_mode", route_path, f"adapter_mode={registry_record.get('adapter_mode')}"))
            if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_write_registry_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))

        manifest_record = manifest_by_route.get((route_path, methods))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_write_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("wecom_tag_write_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_command":
                violations.append(Violation("wecom_tag_write_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_write_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("wecom_tag_write_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
            if manifest_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_write_manifest_adapter_mode", route_path, f"adapter_mode={manifest_record.get('adapter_mode')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_write_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    for route_path, methods in WECOM_TAG_SYNC_ROUTES:
        registry_record = registry_by_route.get((route_path, methods))
        if registry_record is None:
            violations.append(Violation("wecom_tag_sync_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if registry_record.get("runtime_owner") != "next_native_sync":
                violations.append(Violation("wecom_tag_sync_registry_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_sync_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
            if registry_record.get("legacy_source") not in {"", None}:
                violations.append(Violation("wecom_tag_sync_registry_legacy_source", route_path, f"legacy_source={registry_record.get('legacy_source')}"))
            if registry_record.get("external_side_effect_risk") != "medium":
                violations.append(Violation("wecom_tag_sync_registry_risk", route_path, f"external_side_effect_risk={registry_record.get('external_side_effect_risk')}"))
            if registry_record.get("adapter_mode") != "live_catalog_sync":
                violations.append(Violation("wecom_tag_sync_registry_adapter_mode", route_path, f"adapter_mode={registry_record.get('adapter_mode')}"))
            if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_sync_registry_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))

        manifest_record = manifest_by_route.get((route_path, methods))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_sync_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next_native_sync":
                violations.append(Violation("wecom_tag_sync_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != "next_live_catalog_sync":
                violations.append(Violation("wecom_tag_sync_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_sync_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("production_behavior") == "legacy_forward":
                violations.append(Violation("wecom_tag_sync_manifest_legacy_forward", route_path, "production_behavior=legacy_forward"))
            if manifest_record.get("external_side_effect_risk") != "medium":
                violations.append(Violation("wecom_tag_sync_manifest_risk", route_path, f"external_side_effect_risk={manifest_record.get('external_side_effect_risk')}"))
            if manifest_record.get("adapter_mode") != "live_catalog_sync":
                violations.append(Violation("wecom_tag_sync_manifest_adapter_mode", route_path, f"adapter_mode={manifest_record.get('adapter_mode')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_sync_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def check_wecom_tag_live_mutation_next_commandbus(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    inventory_path = root / "docs/architecture/wecom_tag_live_mutation_route_inventory.md"
    if not inventory_path.exists():
        violations.append(Violation("wecom_tag_live_mutation_inventory_missing", str(inventory_path.relative_to(root)), "missing inventory document"))
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path, _methods, _owner, _behavior in WECOM_TAG_LIVE_MUTATION_ROUTES:
            if route_path not in inventory_text:
                violations.append(Violation("wecom_tag_live_mutation_inventory_route_missing", str(inventory_path.relative_to(root)), route_path))
        for phrase in (
            "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
            "PlanWeComTagMarkCommand",
            "PlanWeComTagUnmarkCommand",
            "PlanCustomerTagAssignmentCommand",
            "PlanQuestionnaireTagSideEffectCommand",
            "real_external_call_executed=false",
            "wecom_api_called=false",
            "real_blocked",
        ):
            if phrase not in inventory_text:
                violations.append(Violation("wecom_tag_live_mutation_inventory_boundary_missing", str(inventory_path.relative_to(root)), phrase))

    api_path = root / "aicrm_next/customer_tags/api.py"
    live_mutation_path = root / "aicrm_next/customer_tags/live_mutation.py"
    commands_path = root / "aicrm_next/customer_tags/mutation_commands.py"
    questionnaire_path = root / "aicrm_next" / "integration_gateway" / "questionnaire_adapters.py"
    compat_path = root / "aicrm_next/production_compat/api.py"

    if compat_path.exists():
        route_paths = set(_decorator_route_paths(compat_path))
        route_paths.update(_decorated_route_function_sources(compat_path).keys())
        for route_path in sorted(route_paths & WECOM_TAG_LIVE_MUTATION_EXACT_ROUTES):
            violations.append(
                Violation(
                    "wecom_tag_live_mutation_production_compat_route",
                    str(compat_path.relative_to(root)),
                    route_path,
                    "WeCom live mutation routes are deletion_locked to Next and must not be reintroduced in production_compat.",
                )
            )

    for path, markers in [
        (api_path, ("mark_tags_live", "unmark_tags_live", "execute_wecom_tag_mutation", "live_gate_status")),
        (live_mutation_path, ("execute_wecom_tag_mutation", "InMemoryAuditLedger", "InMemorySideEffectPlanRepository", "wecom_api_called")),
        (commands_path, ("PlanWeComTagMarkCommand", "PlanWeComTagUnmarkCommand", "PlanCustomerTagAssignmentCommand", "PlanQuestionnaireTagSideEffectCommand")),
        (questionnaire_path, ("PlanQuestionnaireTagSideEffectCommand", "execute_wecom_tag_mutation")),
    ]:
        if not path.exists():
            violations.append(Violation("wecom_tag_live_mutation_module_missing", str(path.relative_to(root)), ",".join(markers)))
            continue
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in source:
                violations.append(Violation("wecom_tag_live_mutation_module_marker_missing", str(path.relative_to(root)), marker))

    for path in (api_path, live_mutation_path, commands_path):
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden, code in {
            "forward_to_legacy_flask": "wecom_tag_live_mutation_legacy_forward",
            "legacy_flask_facade": "wecom_tag_live_mutation_legacy_facade",
            "X-AICRM-Compatibility-Facade": "wecom_tag_live_mutation_compatibility_facade",
            '"fallback_used": True': "wecom_tag_live_mutation_fallback_used_true",
            "'fallback_used': True": "wecom_tag_live_mutation_fallback_used_true",
            '"real_external_call_executed": True': "wecom_tag_live_mutation_real_external_call_true",
            "'real_external_call_executed': True": "wecom_tag_live_mutation_real_external_call_true",
            '"wecom_api_called": True': "wecom_tag_live_mutation_wecom_api_called_true",
            "'wecom_api_called': True": "wecom_tag_live_mutation_wecom_api_called_true",
            "requests.": "wecom_tag_live_mutation_direct_http_client",
            "httpx.": "wecom_tag_live_mutation_direct_http_client",
            "WeComTagLiveGateway": "wecom_tag_live_mutation_real_wecom_gateway",
            "build_wecom_tag_live_gateway": "wecom_tag_live_mutation_real_wecom_gateway",
            "access_token": "wecom_tag_live_mutation_real_wecom_token",
            "externalcontact": "wecom_tag_live_mutation_real_wecom_api",
            "mark_external_contact_tags": "wecom_tag_live_mutation_real_wecom_mutation",
            "real_enabled=True": "wecom_tag_live_mutation_real_enabled_default",
            "real_enabled = True": "wecom_tag_live_mutation_real_enabled_default",
        }.items():
            if forbidden in source:
                violations.append(Violation(code, str(path.relative_to(root)), forbidden))

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    registry_by_route = {(record.get("path_pattern"), tuple(record.get("methods") or [])): record for record in registry_records}
    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    manifest_by_route = {(record.get("route_pattern"), tuple(record.get("methods") or [])): record for record in manifest_records}

    for route_path, methods, owner, behavior in WECOM_TAG_LIVE_MUTATION_ROUTES:
        registry_record = registry_by_route.get((route_path, methods))
        if registry_record is None:
            violations.append(Violation("wecom_tag_live_mutation_registry_missing", "docs/architecture/legacy_exit_route_registry.yaml", route_path))
        else:
            if registry_record.get("runtime_owner") != owner:
                violations.append(Violation("wecom_tag_live_mutation_registry_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_live_mutation_registry_rollback_allowed", route_path, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
            if registry_record.get("runtime_owner") in {"production_compat", "legacy_forward"}:
                violations.append(Violation("wecom_tag_live_mutation_registry_legacy_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("external_side_effect_risk") != "high":
                violations.append(Violation("wecom_tag_live_mutation_registry_side_effect_risk", route_path, f"external_side_effect_risk={registry_record.get('external_side_effect_risk')}"))
            if registry_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_live_mutation_registry_adapter_mode", route_path, f"adapter_mode={registry_record.get('adapter_mode')}"))
            if registry_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
                violations.append(Violation("wecom_tag_live_mutation_registry_rollback_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')}"))
            if registry_record.get("delete_status") != "deletion_locked" or registry_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_live_mutation_registry_lifecycle", route_path, f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}"))

        manifest_record = manifest_by_route.get((route_path, methods))
        if manifest_record is None:
            violations.append(Violation("wecom_tag_live_mutation_manifest_missing", "docs/route_ownership/production_route_ownership_manifest.yaml", route_path))
        else:
            if manifest_record.get("current_runtime_owner") != "next":
                violations.append(Violation("wecom_tag_live_mutation_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != behavior:
                violations.append(Violation("wecom_tag_live_mutation_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
                violations.append(Violation("wecom_tag_live_mutation_manifest_legacy_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("wecom_tag_live_mutation_manifest_rollback_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("adapter_mode") != "real_blocked":
                violations.append(Violation("wecom_tag_live_mutation_manifest_adapter_mode", route_path, f"adapter_mode={manifest_record.get('adapter_mode')}"))
            if manifest_record.get("delete_status") in {"next_primary_with_legacy_rollback", "active"}:
                violations.append(Violation("wecom_tag_live_mutation_manifest_rollback_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')}"))
            if manifest_record.get("delete_status") != "deletion_locked" or manifest_record.get("replacement_status") != "locked":
                violations.append(Violation("wecom_tag_live_mutation_manifest_lifecycle", route_path, f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}"))

    return violations


def check_final_legacy_exit_cleanup(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []
    compat_path = root / "aicrm_next/production_compat/api.py"
    main_path = root / "aicrm_next/main.py"

    if compat_path.exists():
        source = compat_path.read_text(encoding="utf-8")
        for marker, code in {
            "@router.api_route": "final_cleanup_prod_compat_route_decorator",
            "@wildcard_router.api_route": "final_cleanup_production_compat_wildcard_route",
            "forward_to_legacy_flask": "final_cleanup_production_compat_legacy_forward",
            "legacy_flask_facade": "final_cleanup_production_compat_legacy_facade",
        }.items():
            if marker in source:
                violations.append(
                    Violation(
                        code,
                        str(compat_path.relative_to(root)),
                        marker,
                        "Final Legacy Exit requires production_compat to stay route-free and detached from the app runtime.",
                    )
                )

    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        for marker in (PROD_COMPAT_ROUTER_NAME, PROD_COMPAT_WILDCARD_ROUTER_NAME, PROD_COMPAT_INCLUDE, PROD_COMPAT_WILDCARD_INCLUDE):
            if marker in main_text:
                violations.append(
                    Violation(
                        "final_cleanup_production_compat_included",
                        str(main_path.relative_to(root)),
                        marker,
                        "Remove production compatibility router imports and include_router calls from app startup.",
                    )
                )

    registry_records = _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")
    for record in registry_records:
        route = str(record.get("path_pattern") or record.get("route_id") or "<unknown>")
        if record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("final_cleanup_registry_legacy_fallback_allowed", route, "legacy_fallback_allowed=true"))
        if record.get("legacy_source") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("final_cleanup_registry_legacy_source", route, f"legacy_source={record.get('legacy_source')}"))
        if record.get("runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("final_cleanup_registry_legacy_owner", route, f"runtime_owner={record.get('runtime_owner')}"))
        if record.get("delete_status") == "next_primary_with_legacy_rollback":
            violations.append(Violation("final_cleanup_registry_rollback_lifecycle", route, f"delete_status={record.get('delete_status')}"))
        if record.get("legacy_source") in {"production_compat", "legacy_forward"} and (
            record.get("delete_status") == "active" or record.get("replacement_status") == "not_started"
        ):
            violations.append(
                Violation(
                    "final_cleanup_registry_unlocked_legacy_source",
                    route,
                    f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}",
                )
            )

    manifest_records = _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")
    for record in manifest_records:
        route = str(record.get("route_pattern") or "<unknown>")
        if record.get("legacy_fallback_allowed") is True:
            violations.append(Violation("final_cleanup_manifest_legacy_fallback_allowed", route, "legacy_fallback_allowed=true"))
        if record.get("current_runtime_owner") in {"production_compat", "legacy_forward"}:
            violations.append(Violation("final_cleanup_manifest_legacy_owner", route, f"current_runtime_owner={record.get('current_runtime_owner')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"}:
            violations.append(Violation("final_cleanup_manifest_legacy_behavior", route, f"production_behavior={record.get('production_behavior')}"))
        if record.get("production_behavior") in {"legacy_forward", "next_primary_with_legacy_rollback"} and (
            record.get("delete_status") == "active" or record.get("replacement_status") == "not_started"
        ):
            violations.append(
                Violation(
                    "final_cleanup_manifest_unlocked_legacy_behavior",
                    route,
                    f"delete_status={record.get('delete_status')} replacement_status={record.get('replacement_status')}",
                )
            )

    route_report = build_route_check_report(strict=True)
    final_counts = {
        "undocumented_routes_count": route_report["undocumented_routes_count"],
        "unknown_owner_count": route_report["unknown_owner_count"],
        "deleted_but_still_registered_count": route_report["deleted_but_still_registered_count"],
        "production_compat_route_count": route_report["production_compat_route_count"],
        "production_compat_catch_all_count": route_report["production_compat_catch_all_count"],
        "legacy_fallback_routes_count": route_report["legacy_fallback_routes_count"],
        "wildcard_legacy_forward_count": route_report["wildcard_legacy_forward_count"],
    }
    for count_name, count in final_counts.items():
        if count != 0:
            violations.append(
                Violation(
                    "final_cleanup_route_registry_count",
                    "runtime",
                    f"{count_name}={count}",
                    "Final Legacy Exit strict runtime counters must stay at zero.",
                )
            )

    return violations


def check_post_legacy_deferred_api_cleanup(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    baseline_path = root / "tests/post_legacy_baseline.py"
    if not baseline_path.exists():
        violations.append(
            Violation(
                "post_legacy_deferred_baseline_missing",
                str(baseline_path.relative_to(root)),
                "missing baseline file",
            )
        )
    else:
        baseline_text = baseline_path.read_text(encoding="utf-8")
        if "DEFERRED_FRONTEND_API_PATTERNS: tuple[str, ...] = ()" not in baseline_text:
            violations.append(
                Violation(
                    "post_legacy_deferred_patterns_not_empty",
                    str(baseline_path.relative_to(root)),
                    "DEFERRED_FRONTEND_API_PATTERNS must stay empty",
                    "Post-Legacy deferred API cleanup forbids reintroducing a frontend/API gray-area whitelist.",
                )
            )

    inventory_path = root / "docs/architecture/post_legacy_deferred_api_cleanup_inventory.md"
    if not inventory_path.exists():
        violations.append(
            Violation(
                "post_legacy_deferred_inventory_missing",
                str(inventory_path.relative_to(root)),
                "missing deferred API cleanup inventory",
            )
        )
    else:
        inventory_text = inventory_path.read_text(encoding="utf-8")
        for route_path in POST_LEGACY_DEFERRED_ROUTES:
            if route_path not in inventory_text:
                violations.append(
                    Violation(
                        "post_legacy_deferred_inventory_route_missing",
                        str(inventory_path.relative_to(root)),
                        route_path,
                    )
                )
        for phrase in (
            "DEFERRED_FRONTEND_API_PATTERNS` is empty",
            "real WeCom blocked",
            "external_storage_executed=false",
            "wecom_api_called=false",
        ):
            if phrase not in inventory_text:
                violations.append(
                    Violation(
                        "post_legacy_deferred_inventory_guardrail_missing",
                        str(inventory_path.relative_to(root)),
                        phrase,
                    )
                )

    api_path = root / "aicrm_next/post_legacy_deferred/api.py"
    if not api_path.exists():
        violations.append(
            Violation(
                "post_legacy_deferred_api_missing",
                str(api_path.relative_to(root)),
                "missing Next-owned deferred closeout API module",
            )
        )
    else:
        api_text = api_path.read_text(encoding="utf-8")
        for marker, code in {
            "requests.": "post_legacy_deferred_direct_requests_client",
            "httpx.": "post_legacy_deferred_direct_httpx_client",
            "urlopen(": "post_legacy_deferred_direct_urlopen_client",
            "create_contact_way": "post_legacy_deferred_wecom_contact_way",
            "dispatch_wecom_task": "post_legacy_deferred_wecom_dispatch",
            "external_storage_executed = True": "post_legacy_deferred_external_storage_true",
            "wecom_api_called = True": "post_legacy_deferred_wecom_api_true",
            "real_external_call_executed = True": "post_legacy_deferred_real_external_true",
            '"external_storage_executed": True': "post_legacy_deferred_external_storage_true",
            '"wecom_api_called": True': "post_legacy_deferred_wecom_api_true",
            '"real_external_call_executed": True': "post_legacy_deferred_real_external_true",
        }.items():
            if marker in api_text:
                violations.append(
                    Violation(
                        code,
                        str(api_path.relative_to(root)),
                        marker,
                        "Deferred API closeout routes must remain local, safe-mode, and no-real-external by default.",
                    )
                )
        for route_path in POST_LEGACY_DEFERRED_ROUTES:
            if route_path not in api_text:
                violations.append(
                    Violation(
                        "post_legacy_deferred_api_route_missing",
                        str(api_path.relative_to(root)),
                        route_path,
                    )
                )

    registry_records = {record.get("path_pattern"): record for record in _load_yaml_records(root / "docs/architecture/legacy_exit_route_registry.yaml", "routes")}
    manifest_records = {record.get("route_pattern"): record for record in _load_yaml_records(root / "docs/route_ownership/production_route_ownership_manifest.yaml", "routes")}
    for route_path, expected in POST_LEGACY_DEFERRED_ROUTES.items():
        registry_record = registry_records.get(route_path)
        manifest_record = manifest_records.get(route_path)
        if not registry_record:
            violations.append(Violation("post_legacy_deferred_registry_missing", route_path, "missing registry record"))
        else:
            if registry_record.get("runtime_owner") != expected["registry_owner"]:
                violations.append(Violation("post_legacy_deferred_registry_owner", route_path, f"runtime_owner={registry_record.get('runtime_owner')}"))
            if registry_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("post_legacy_deferred_registry_legacy_allowed", route_path, f"legacy_fallback_allowed={registry_record.get('legacy_fallback_allowed')}"))
            if registry_record.get("delete_status") not in {"deletion_locked", "post_legacy_locked"} or registry_record.get("replacement_status") != "locked":
                violations.append(
                    Violation(
                        "post_legacy_deferred_registry_lifecycle",
                        route_path,
                        f"delete_status={registry_record.get('delete_status')} replacement_status={registry_record.get('replacement_status')}",
                    )
                )
        if not manifest_record:
            violations.append(Violation("post_legacy_deferred_manifest_missing", route_path, "missing production manifest record"))
        else:
            if manifest_record.get("current_runtime_owner") != expected["manifest_owner"]:
                violations.append(Violation("post_legacy_deferred_manifest_owner", route_path, f"current_runtime_owner={manifest_record.get('current_runtime_owner')}"))
            if manifest_record.get("production_behavior") != expected["manifest_behavior"]:
                violations.append(Violation("post_legacy_deferred_manifest_behavior", route_path, f"production_behavior={manifest_record.get('production_behavior')}"))
            if manifest_record.get("legacy_fallback_allowed") is not False:
                violations.append(Violation("post_legacy_deferred_manifest_legacy_allowed", route_path, f"legacy_fallback_allowed={manifest_record.get('legacy_fallback_allowed')}"))
            if manifest_record.get("delete_status") not in {"deletion_locked", "post_legacy_locked"} or manifest_record.get("replacement_status") != "locked":
                violations.append(
                    Violation(
                        "post_legacy_deferred_manifest_lifecycle",
                        route_path,
                        f"delete_status={manifest_record.get('delete_status')} replacement_status={manifest_record.get('replacement_status')}",
                    )
                )

    route_report = build_route_check_report(strict=True)
    if route_report["production_compat_route_count"] != 0:
        violations.append(
            Violation(
                "post_legacy_deferred_production_compat_runtime_count",
                "runtime",
                f"production_compat_route_count={route_report['production_compat_route_count']}",
            )
        )

    return violations


def check_post_legacy_architecture_freeze(root: Path = ROOT) -> list[Violation]:
    violations: list[Violation] = []

    for rel_path, required_phrases in POST_LEGACY_DEVELOPMENT_DOCS.items():
        path = root / rel_path
        if not path.exists():
            violations.append(Violation("post_legacy_development_doc_missing", str(rel_path), "required post-legacy freeze document is missing"))
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in required_phrases:
            if phrase not in text:
                violations.append(Violation("post_legacy_development_doc_phrase_missing", str(rel_path), phrase))

    inventory_path = root / "docs/architecture/post_legacy_legacy_module_prune_inventory.md"
    inventory_text = inventory_path.read_text(encoding="utf-8") if inventory_path.exists() else ""
    for module_name, rel_path in POST_LEGACY_DELETED_HTTP_MODULES.items():
        module_path = root / rel_path
        if module_path.exists():
            violations.append(Violation("post_legacy_deleted_handler_still_exists", str(rel_path), "deleted legacy handler file is still present"))
        if f"`{rel_path.as_posix()}`" not in inventory_text or "`deleted`" not in inventory_text:
            violations.append(Violation("post_legacy_deleted_handler_inventory_missing", str(inventory_path.relative_to(root)), module_name))

    for module_name, rel_path in POST_LEGACY_TEMPORARY_HISTORICAL_HTTP_MODULES.items():
        if f"`{rel_path.as_posix()}`" not in inventory_text or "keep_temporarily_historical" not in inventory_text:
            violations.append(Violation("post_legacy_kept_handler_inventory_missing", str(inventory_path.relative_to(root)), module_name))

    http_init = root / "wecom_ability_service/http/__init__.py"
    if http_init.exists():
        http_init_text = http_init.read_text(encoding="utf-8")
        for module_name in POST_LEGACY_DELETED_HTTP_MODULES:
            if module_name in http_init_text:
                violations.append(Violation("post_legacy_deleted_handler_still_registered", str(http_init.relative_to(root)), module_name))

    main_path = root / "aicrm_next/main.py"
    if main_path.exists():
        main_text = main_path.read_text(encoding="utf-8")
        for marker, code in POST_LEGACY_MAIN_FORBIDDEN_MARKERS.items():
            if marker in main_text:
                violations.append(Violation(code, str(main_path.relative_to(root)), marker))

    for rel_root in ("aicrm_next", "scripts", "tools"):
        search_root = root / rel_root
        if not search_root.exists():
            continue
        for path in search_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root)
            for module_name in POST_LEGACY_DELETED_HTTP_MODULES:
                dotted = f"wecom_ability_service.http.{module_name}"
                if dotted in text or f"from wecom_ability_service.http import {module_name}" in text:
                    violations.append(Violation("post_legacy_deleted_handler_import", str(rel), dotted))

    combined_docs = "\n".join(
        (root / rel_path).read_text(encoding="utf-8")
        for rel_path in POST_LEGACY_DEVELOPMENT_DOCS
        if (root / rel_path).exists()
    )
    for marker, code in POST_LEGACY_PARALLEL_MODULE_MARKERS.items():
        if marker not in combined_docs:
            violations.append(Violation(code, "post_legacy_development_docs", marker))

    if root == ROOT:
        route_report = build_route_check_report(strict=True)
        zero_counter_keys = (
            "deleted_but_still_registered_count",
            "production_compat_route_count",
            "production_compat_catch_all_count",
            "legacy_fallback_routes_count",
            "wildcard_legacy_forward_count",
            "undocumented_routes_count",
            "unknown_owner_routes_count",
        )
        for key in zero_counter_keys:
            if route_report[key] != 0:
                violations.append(Violation("post_legacy_route_resolution_counter_nonzero", "runtime", f"{key}={route_report[key]}"))

    return violations


def run_checks(*, strict: bool) -> dict:
    violations = (
        scan_source_tree(ROOT)
        + check_startup_legacy_closeout(ROOT)
        + check_group_ops_message_content_native(ROOT)
        + check_group_ops_material_resolver_native(ROOT)
        + check_group_ops_scheduler_duplicate_checker_native(ROOT)
        + check_channel_identity_bridge_native(ROOT)
        + check_questionnaire_adapters_native_oauth(ROOT)
        + check_public_product_h5_pay_oauth_native(ROOT)
        + check_public_product_h5_pay_sidebar_context_native(ROOT)
        + check_public_product_h5_pay_legacy_closeout(ROOT)
        + check_wecom_group_adapter_native(ROOT)
        + check_ai_assist_external_campaigns_native(ROOT)
        + check_customer_read_model_legacy_deletion(ROOT)
        + check_production_compat_removed(ROOT)
        + check_production_compat_routes(ROOT)
        + check_orphan_legacy_facades_removed(ROOT)
        + check_legacy_flask_facade_removed(ROOT)
        + check_internal_run_due_guard_native(ROOT)
        + check_messages_broad_wildcard_deletion(ROOT)
        + check_sidebar_readonly_closeout_lock(ROOT)
        + check_sidebar_jssdk_next_adapter(ROOT)
        + check_user_ops_next_native_preview(ROOT)
        + check_questionnaire_admin_read_next_native(ROOT)
        + check_questionnaire_admin_write_next_commandbus(ROOT)
        + check_questionnaire_h5_submit_next_commandbus(ROOT)
        + check_questionnaire_oauth_next_adapter(ROOT)
        + check_auth_wecom_wildcard_inventory(ROOT)
        + check_wecom_tag_read_next_native(ROOT)
        + check_wecom_tag_write_next_commandbus(ROOT)
        + check_wecom_tag_live_mutation_next_commandbus(ROOT)
        + check_media_library_admin_pages_native(ROOT)
        + check_media_library_closeout_lock(ROOT)
        + check_hxc_dashboard_closeout_lock(ROOT)
        + check_admin_auth_login_closeout_lock(ROOT)
        + check_public_product_pay_closeout_lock(ROOT)
        + check_checkout_orders_closeout_lock(ROOT)
        + check_provider_payment_closeout_lock(ROOT)
        + check_payment_wildcard_final_closeout_lock(ROOT)
        + check_cloud_orchestrator_media_upload_closeout_lock(ROOT)
        + check_cloud_orchestrator_media_upload_native_client(ROOT)
        + check_cloud_orchestrator_repository_time_helpers_native(ROOT)
        + check_cloud_orchestrator_campaign_read_closeout_lock(ROOT)
        + check_cloud_orchestrator_campaign_write_next_commandbus(ROOT)
        + check_cloud_orchestrator_run_due_next_safe_mode(ROOT)
        + check_automation_conversion_timers_next_safe_mode(ROOT)
        + check_automation_workspace_runtime_next_safe_mode(ROOT)
        + check_automation_member_actions_next_safe_mode(ROOT)
        + check_automation_overview_pools_next_read_model(ROOT)
        + check_group_ops_admin_pages_next_native(ROOT)
        + check_customer_automation_webhook_next_safe_mode(ROOT)
        + check_final_legacy_exit_cleanup(ROOT)
        + check_post_legacy_deferred_api_cleanup(ROOT)
        + check_post_legacy_architecture_freeze(ROOT)
        + check_route_progress_docs_do_not_drift(ROOT)
    )
    route_report = build_route_check_report(strict=strict)
    for item in route_report["blockers"]:
        violations.append(
            Violation(
                "route_registry_strict",
                "runtime",
                str(item),
                "Resolve the route diff through route registry ownership and lifecycle updates instead of adding undocumented fallback.",
            )
        )
    return {
        "ok": not violations,
        "strict": strict,
        "violations": [violation.to_dict() for violation in violations],
        "route_registry": {
            "ok": route_report["ok"],
            "mode": route_report["mode"],
            "registered_routes_count": route_report["registered_routes_count"],
            "manifest_routes_count": route_report["manifest_routes_count"],
            "undocumented_routes_count": len(route_report["undocumented_routes"]),
            "legacy_fallback_routes_count": len(route_report["legacy_fallback_routes"]),
            "wildcard_routes_count": len(route_report["wildcard_routes"]),
            "unknown_owner_routes_count": len(route_report["unknown_owner_routes"]),
            "deleted_but_still_registered_routes_count": len(route_report["deleted_but_still_registered_routes"]),
            "blockers": route_report["blockers"],
            "warnings": route_report["warnings"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Block new legacy imports, fallbacks, wildcard routes, and undocumented Next routes.")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = run_checks(strict=bool(args.strict))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
