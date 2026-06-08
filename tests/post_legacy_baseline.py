from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from starlette.routing import Match

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs/architecture/post_legacy_product_baseline_inventory.md"


@dataclass(frozen=True)
class PageCase:
    key: str
    path: str
    owner: str
    expected_statuses: tuple[int, ...] = (200,)


@dataclass(frozen=True)
class ApiCase:
    key: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    path: str
    owner: str
    expected_statuses: tuple[int, ...]
    json: dict[str, Any] | None = None
    content: bytes | None = None
    params: dict[str, Any] | None = None


ADMIN_PAGE_CASES: tuple[PageCase, ...] = (
    PageCase("login", "/login", "aicrm_next.admin_auth"),
    PageCase("admin_dashboard", "/admin", "aicrm_next.admin_shell"),
    PageCase("route_registry", "/admin/system/routes", "aicrm_next.platform_foundation"),
    PageCase("customers", "/admin/customers", "aicrm_next.frontend_compat"),
    PageCase("customer_detail", "/admin/customers/wx_ext_001", "aicrm_next.frontend_compat"),
    PageCase("user_ops", "/admin/user-ops", "aicrm_next.frontend_compat"),
    PageCase("questionnaires", "/admin/questionnaires", "aicrm_next.frontend_compat"),
    PageCase("questionnaire_new", "/admin/questionnaires/new", "aicrm_next.frontend_compat"),
    PageCase("questionnaire_detail", "/admin/questionnaires/1", "aicrm_next.frontend_compat"),
    PageCase("questionnaire_missing_detail", "/admin/questionnaires/21", "aicrm_next.frontend_compat", (404,)),
    PageCase("wecom_tags", "/admin/wecom-tags", "aicrm_next.frontend_compat"),
    PageCase("image_library", "/admin/image-library", "aicrm_next.frontend_compat"),
    PageCase("attachment_library", "/admin/attachment-library", "aicrm_next.frontend_compat"),
    PageCase("miniprogram_library", "/admin/miniprogram-library", "aicrm_next.frontend_compat"),
    PageCase("admin_config", "/admin/config", "aicrm_next.admin_config"),
    PageCase("admin_config_app_settings", "/admin/config/app-settings", "aicrm_next.admin_config"),
    PageCase("admin_config_login_access", "/admin/config/login-access", "aicrm_next.admin_config"),
    PageCase("admin_config_checklist", "/admin/config/checklist", "aicrm_next.admin_config"),
    PageCase("setup_wizard", "/setup/wizard", "aicrm_next.admin_config"),
    PageCase("cloud_campaigns", "/admin/cloud-orchestrator/campaigns", "aicrm_next.cloud_orchestrator"),
    PageCase("cloud_plans", "/admin/cloud-orchestrator/plans", "aicrm_next.cloud_orchestrator"),
    PageCase("hxc_dashboard", "/admin/hxc-dashboard", "aicrm_next.hxc_dashboard"),
    PageCase("hxc_send_config", "/admin/hxc-send-config", "aicrm_next.hxc_dashboard"),
    PageCase("group_ops", "/admin/automation-conversion/group-ops/ui", "aicrm_next.automation_engine.group_ops"),
    PageCase("group_ops_detail", "/admin/automation-conversion/group-ops/plans/1", "aicrm_next.automation_engine.group_ops"),
    PageCase("group_ops_groups", "/admin/automation-conversion/group-ops/groups/ui", "aicrm_next.automation_engine.group_ops"),
    PageCase("wechat_products", "/admin/wechat-pay/products", "aicrm_next.commerce"),
    PageCase("wechat_product_new", "/admin/wechat-pay/products/new", "aicrm_next.commerce"),
    PageCase("wechat_transactions", "/admin/wechat-pay/transactions", "aicrm_next.commerce"),
)

PUBLIC_H5_PAGE_CASES: tuple[PageCase, ...] = (
    PageCase("public_product", "/p/test-product", "aicrm_next.public_product"),
    PageCase("public_pay", "/pay/test-product", "aicrm_next.public_product"),
    PageCase("questionnaire_h5", "/s/hxc-activation-v1", "aicrm_next.questionnaire"),
    PageCase("questionnaire_submitted", "/s/hxc-activation-v1/submitted", "aicrm_next.questionnaire"),
    PageCase("auth_wecom_start", "/auth/wecom/start", "aicrm_next.auth_wecom", (503,)),
    PageCase("auth_wecom_callback", "/auth/wecom/callback", "aicrm_next.auth_wecom", (503,)),
)

API_CONTRACT_CASES: tuple[ApiCase, ...] = (
    ApiCase("customers_read", "GET", "/api/customers", "aicrm_next.customer_read_model", (200,)),
    ApiCase("route_registry_read", "GET", "/api/admin/system/routes", "aicrm_next.platform_foundation", (200,)),
    ApiCase("user_ops_overview", "GET", "/api/admin/user-ops/overview", "aicrm_next.ops_enrollment", (200,)),
    ApiCase("questionnaire_admin_list", "GET", "/api/admin/questionnaires", "aicrm_next.questionnaire", (200,)),
    ApiCase("questionnaire_admin_detail", "GET", "/api/admin/questionnaires/1", "aicrm_next.questionnaire", (200,)),
    ApiCase("questionnaire_h5_read", "GET", "/api/h5/questionnaires/hxc-activation-v1", "aicrm_next.questionnaire", (200,)),
    ApiCase(
        "questionnaire_h5_submit",
        "POST",
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        "aicrm_next.questionnaire",
        (200,),
        json={"answers": {"q_activation": "activated", "q_interest": ["ai_tools"]}, "source": "post_legacy_baseline"},
    ),
    ApiCase(
        "questionnaire_h5_diagnostics",
        "POST",
        "/api/h5/questionnaires/hxc-activation-v1/client-diagnostics",
        "aicrm_next.questionnaire",
        (200,),
        json={"event": "post_legacy_baseline", "payload": {}},
    ),
    ApiCase(
        "questionnaire_oauth_start",
        "GET",
        "/api/h5/wechat/oauth/start",
        "aicrm_next.questionnaire",
        (200, 503),
        params={"slug": "hxc-activation-v1", "redirect": "/s/hxc-activation-v1"},
    ),
    ApiCase("admin_wecom_auth_start", "GET", "/auth/wecom/start", "aicrm_next.auth_wecom", (503,)),
    ApiCase("admin_wecom_auth_callback", "GET", "/auth/wecom/callback", "aicrm_next.auth_wecom", (503,)),
    ApiCase("wecom_tags_read", "GET", "/api/admin/wecom/tags", "aicrm_next.customer_tags", (200,)),
    ApiCase(
        "wecom_tags_write",
        "POST",
        "/api/admin/wecom/tags",
        "aicrm_next.customer_tags",
        (200,),
        json={"group_id": "group_fixture_lifecycle", "tag_name": "Post Legacy Baseline"},
    ),
    ApiCase(
        "wecom_tags_live_mutation_blocked",
        "POST",
        "/api/admin/wecom/tags/live/mark",
        "aicrm_next.customer_tags",
        (200, 400),
        json={"external_userid": "wx_ext_001", "tag_ids": ["tag_fixture_active"], "dry_run": True},
    ),
    ApiCase("image_library_read", "GET", "/api/admin/image-library", "aicrm_next.media_library", (200,)),
    ApiCase("attachment_library_read", "GET", "/api/admin/attachment-library", "aicrm_next.media_library", (200,)),
    ApiCase("miniprogram_library_read", "GET", "/api/admin/miniprogram-library", "aicrm_next.media_library", (200,)),
    ApiCase("cloud_campaigns_read", "GET", "/api/admin/cloud-orchestrator/campaigns", "aicrm_next.cloud_orchestrator", (200,)),
    ApiCase("cloud_audit_read", "GET", "/api/admin/cloud-orchestrator/audit", "aicrm_next.post_legacy_deferred", (200,)),
    ApiCase("cloud_observability_read", "GET", "/api/admin/cloud-orchestrator/observability", "aicrm_next.post_legacy_deferred", (200,)),
    ApiCase(
        "cloud_campaigns_run_due_preview",
        "POST",
        "/api/admin/cloud-orchestrator/campaigns/run-due/preview",
        "aicrm_next.cloud_orchestrator",
        (200,),
        json={},
    ),
    ApiCase(
        "cloud_campaigns_run_due_plan",
        "POST",
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        "aicrm_next.cloud_orchestrator",
        (200,),
        json={"dry_run": True},
    ),
    ApiCase(
        "automation_jobs_run_due_preview",
        "POST",
        "/api/admin/automation-conversion/jobs/run-due/preview",
        "aicrm_next.automation_engine",
        (200,),
        json={},
    ),
    ApiCase(
        "automation_member_put_in_pool",
        "POST",
        "/api/admin/automation-conversion/member/put-in-pool",
        "aicrm_next.automation_engine",
        (200,),
        json={"external_contact_id": "wx_ext_001", "pool_id": "pool_fixture", "reason": "post legacy baseline"},
    ),
    ApiCase(
        "customer_activation_webhook",
        "POST",
        "/api/customers/automation/activation-webhook",
        "aicrm_next.automation_engine",
        (200, 400),
        json={"external_userid": "wx_ext_001", "event": "activation", "source": "post_legacy_baseline"},
    ),
    ApiCase("hxc_dashboard_read", "GET", "/api/admin/hxc-dashboard", "aicrm_next.hxc_dashboard", (200,)),
    ApiCase("hxc_dashboard_refresh", "POST", "/api/admin/hxc-dashboard/refresh", "aicrm_next.hxc_dashboard", (200,), json={}),
    ApiCase("class_user_management_export", "GET", "/api/admin/class-user-management/export", "aicrm_next.post_legacy_deferred", (200,)),
    ApiCase("wecom_customer_acquisition_links_read", "GET", "/api/admin/wecom-customer-acquisition-links", "aicrm_next.post_legacy_deferred", (200,)),
    ApiCase(
        "wecom_customer_acquisition_links_create",
        "POST",
        "/api/admin/wecom-customer-acquisition-links",
        "aicrm_next.post_legacy_deferred",
        (200,),
        json={"name": "Post Legacy Baseline", "description": "safe-mode only"},
    ),
    ApiCase("public_product_api", "GET", "/api/products/test-product", "aicrm_next.public_product", (200,)),
    ApiCase(
        "checkout_wechat_fake",
        "POST",
        "/api/checkout/wechat",
        "aicrm_next.commerce",
        (200,),
        json={
            "product_code": "test-product",
            "quantity": 1,
            "buyer_identity": {"mobile": "13800138000", "external_userid": "wx_ext_001"},
            "return_url": "/pay/test-product",
        },
    ),
    ApiCase("order_read_controlled_missing", "GET", "/api/orders/smoke", "aicrm_next.commerce", (404,)),
    ApiCase("provider_notify_controlled", "POST", "/api/wechat-pay/notify", "aicrm_next.commerce", (200, 400, 422), content=b""),
    ApiCase("admin_payment_unknown_closed", "GET", "/api/admin/wechat-pay/unknown-child", "aicrm_next.commerce", (410,)),
    ApiCase("h5_payment_unknown_closed", "GET", "/api/h5/wechat-pay/unknown-child", "aicrm_next.commerce", (410,)),
)

DEFERRED_FRONTEND_API_PATTERNS: tuple[str, ...] = ()


def baseline_env(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "post-legacy-product-baseline")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "post-legacy-product-baseline-token")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")


def first_matching_route(app, method: str, path: str):
    scope = {"type": "http", "method": method.upper(), "path": path, "root_path": "", "headers": []}
    for route in app.routes:
        match, _ = route.matches(scope) if hasattr(route, "matches") else (None, None)
        if match == Match.FULL:
            return route
    return None


def assert_no_compatibility_facade(response) -> None:
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert response.headers.get("X-AICRM-Route-Owner") == "ai_crm_next"


def assert_no_legacy_flags(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    assert payload.get("route_owner", "ai_crm_next") == "ai_crm_next"
    assert payload.get("fallback_used", False) is False
    assert payload.get("real_external_call_executed", False) is False
    assert payload.get("real_external_call", False) is False
    assert payload.get("external_call_executed", False) is False
