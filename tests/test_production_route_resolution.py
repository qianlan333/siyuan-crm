from __future__ import annotations

from tools import check_production_route_resolution as checker


def _owner_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["route_owner"])
    raise AssertionError(f"missing sample {method} {path}")


def _endpoint_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["endpoint_module"])
    raise AssertionError(f"missing sample {method} {path}")


def test_next_exact_routes_are_not_caught_by_production_compat_wildcards():
    result = checker.run_check()
    samples = result["resolution_samples"]

    for method, path in (
        ("GET", "/login"),
        ("POST", "/login"),
        ("OPTIONS", "/login"),
        ("GET", "/logout"),
        ("OPTIONS", "/logout"),
    ):
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.admin_auth.api"
    assert _owner_for(samples, "GET", "/auth/wecom/start") == "next"
    assert _endpoint_for(samples, "GET", "/auth/wecom/start") == "aicrm_next.auth_wecom.api"
    assert _owner_for(samples, "GET", "/api/customers") == "next"
    assert _endpoint_for(samples, "GET", "/api/customers") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/messages/wx_ext_001/recent") == "next"
    assert _endpoint_for(samples, "GET", "/api/messages/wx_ext_001/recent") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/media/upload") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/media/upload") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/admin/cloud-orchestrator/campaigns") == "next"
    assert _endpoint_for(samples, "GET", "/admin/cloud-orchestrator/campaigns") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library/from-url") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library/from-url") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library/from-base64") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library/from-base64") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/image-library/upload") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/image-library/upload") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library/image_masked_001") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library/image_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "PUT", "/api/admin/image-library/image_masked_001") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/image-library/image_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "DELETE", "/api/admin/image-library/image_masked_001") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/image-library/image_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library/image_masked_001/thumbnail") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library/image_masked_001/thumbnail") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/image-library/image_masked_001/variants/thumb_160") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/image-library/image_masked_001/variants/thumb_160") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/attachment-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/attachment-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/attachment-library") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/attachment-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/attachment-library/upload") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/attachment-library/upload") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/attachment-library/attachment_masked_001") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/attachment-library/attachment_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "PUT", "/api/admin/attachment-library/attachment_masked_001") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/attachment-library/attachment_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "DELETE", "/api/admin/attachment-library/attachment_masked_001") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/attachment-library/attachment_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/miniprogram-library") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/miniprogram-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "POST", "/api/admin/miniprogram-library") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/miniprogram-library") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/api/admin/miniprogram-library/miniprogram_masked_001") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/miniprogram-library/miniprogram_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "PUT", "/api/admin/miniprogram-library/miniprogram_masked_001") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/miniprogram-library/miniprogram_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "DELETE", "/api/admin/miniprogram-library/miniprogram_masked_001") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/miniprogram-library/miniprogram_masked_001") == "aicrm_next.media_library.api"
    assert _owner_for(samples, "GET", "/admin/image-library") == "next"
    assert _endpoint_for(samples, "GET", "/admin/image-library") == "aicrm_next.media_library.admin_pages"
    assert _owner_for(samples, "GET", "/admin/attachment-library") == "next"
    assert _endpoint_for(samples, "GET", "/admin/attachment-library") == "aicrm_next.media_library.admin_pages"
    assert _owner_for(samples, "GET", "/admin/miniprogram-library") == "next"
    assert _endpoint_for(samples, "GET", "/admin/miniprogram-library") == "aicrm_next.media_library.admin_pages"
    assert _owner_for(samples, "GET", "/admin/questionnaires") == "next"
    assert _endpoint_for(samples, "GET", "/admin/questionnaires") == "aicrm_next.questionnaire.admin_pages"
    assert _owner_for(samples, "GET", "/admin/questionnaires/new") == "next"
    assert _endpoint_for(samples, "GET", "/admin/questionnaires/new") == "aicrm_next.questionnaire.admin_pages"
    assert _owner_for(samples, "GET", "/admin/questionnaires/21") == "next"
    assert _endpoint_for(samples, "GET", "/admin/questionnaires/21") == "aicrm_next.questionnaire.admin_pages"
    assert _owner_for(samples, "GET", "/api/admin/questionnaires/21") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/questionnaires/21") == "aicrm_next.questionnaire.api"
    assert _owner_for(samples, "GET", "/sidebar/bind-mobile") == "next"
    assert _endpoint_for(samples, "GET", "/sidebar/bind-mobile") == "aicrm_next.frontend_compat.legacy_routes"
    assert _owner_for(samples, "GET", "/api/sidebar/contact-binding-status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/contact-binding-status") == "aicrm_next.identity_contact.api"
    assert _owner_for(samples, "GET", "/api/sidebar/customer-context") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/customer-context") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/admin/customers/profile") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/customers/profile") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/admin/customers/profile/tags") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/customers/profile/tags") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/lead-pool/status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/lead-pool/status") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/signup-tags/status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/signup-tags/status") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/marketing-status") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/marketing-status") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/v2/workbench") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/v2/workbench") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "GET", "/api/sidebar/v2/materials") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/v2/materials") == "aicrm_next.customer_read_model.api"
    assert _owner_for(samples, "POST", "/api/sidebar/bind-mobile") == "next"
    assert _endpoint_for(samples, "POST", "/api/sidebar/bind-mobile") == "aicrm_next.sidebar_write.api"
    assert _owner_for(samples, "POST", "/api/sidebar/v2/materials/send") == "next"
    assert _endpoint_for(samples, "POST", "/api/sidebar/v2/materials/send") == "aicrm_next.sidebar_write.api"
    assert _owner_for(samples, "GET", "/api/customers/automation/signup-conversion/batches") == "next"
    assert (
        _endpoint_for(samples, "GET", "/api/customers/automation/signup-conversion/batches")
        == "aicrm_next.automation_engine.api"
    )
    assert _owner_for(samples, "GET", "/api/customers/automation/signup-conversion/batches/1") == "next"
    assert _endpoint_for(samples, "GET", "/api/customers/automation/signup-conversion/batches/1") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "GET", "/api/customers/automation/webhook-deliveries") == "next"
    assert _endpoint_for(samples, "GET", "/api/customers/automation/webhook-deliveries") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/customers/automation/activation-webhook") == "next"
    assert _endpoint_for(samples, "POST", "/api/customers/automation/activation-webhook") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/customers/automation/webhook-deliveries/1/retry") == "next"
    assert _endpoint_for(samples, "POST", "/api/customers/automation/webhook-deliveries/1/retry") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/customers/automation/webhook-deliveries/retry-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/customers/automation/webhook-deliveries/retry-due") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "GET", "/api/admin/automation-conversion/agents/options") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/automation-conversion/agents/options") == "aicrm_next.automation_engine.api"
    for method, path in (
        ("GET", "/admin/hxc-dashboard"),
        ("GET", "/admin/hxc-send-config"),
        ("GET", "/api/admin/hxc-dashboard"),
        ("POST", "/api/admin/hxc-dashboard/refresh"),
        ("POST", "/api/admin/hxc-dashboard/refresh-directory"),
        ("GET", "/api/admin/hxc-dashboard/send-config"),
        ("POST", "/api/admin/hxc-dashboard/send-config"),
        ("DELETE", "/api/admin/hxc-dashboard/send-config/hxc_sender_fixture"),
        ("POST", "/api/admin/hxc-dashboard/broadcast"),
        ("GET", "/api/admin/hxc-dashboard/unknown"),
    ):
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.hxc_dashboard.api"
    assert _owner_for(samples, "GET", "/api/admin/automation-conversion/member") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/automation-conversion/member") == "aicrm_next.automation_engine.api"
    for member_action_path in (
        "/api/admin/automation-conversion/member/put-in-pool",
        "/api/admin/automation-conversion/member/remove-from-pool",
        "/api/admin/automation-conversion/member/set-focus",
        "/api/admin/automation-conversion/member/set-normal",
        "/api/admin/automation-conversion/member/mark-won",
        "/api/admin/automation-conversion/member/unmark-won",
        "/api/admin/automation-conversion/member/push-openclaw",
    ):
        assert _owner_for(samples, "POST", member_action_path) == "next"
        assert _endpoint_for(samples, "POST", member_action_path) == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "GET", "/api/admin/wecom/tags") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wecom/tags") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tags") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tags") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "PATCH", "/api/admin/wecom/tags/tag_fixture_active") == "next"
    assert _endpoint_for(samples, "PATCH", "/api/admin/wecom/tags/tag_fixture_active") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "DELETE", "/api/admin/wecom/tags/tag_fixture_active") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/wecom/tags/tag_fixture_active") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tags/sync") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tags/sync") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tags/sync-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tags/sync-due") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "GET", "/api/admin/wecom/tag-groups") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wecom/tag-groups") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "POST", "/api/admin/wecom/tag-groups") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wecom/tag-groups") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "PATCH", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "next"
    assert _endpoint_for(samples, "PATCH", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "aicrm_next.customer_tags.api"
    assert _owner_for(samples, "DELETE", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "next"
    assert _endpoint_for(samples, "DELETE", "/api/admin/wecom/tag-groups/group_fixture_lifecycle") == "aicrm_next.customer_tags.api"


def test_high_risk_legacy_facade_routes_remain_production_compat_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    assert _owner_for(samples, "POST", "/wecom/external-contact/callback") == "next"
    assert _endpoint_for(samples, "POST", "/wecom/external-contact/callback") == "aicrm_next.channel_entry.api"
    assert _owner_for(samples, "POST", "/api/wecom/events") == "next"
    assert _endpoint_for(samples, "POST", "/api/wecom/events") == "aicrm_next.channel_entry.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/reply-monitor/capture") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/reply-monitor/capture") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/reply-monitor/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/reply-monitor/run-due") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due/preview") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due/preview") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/tasks/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/tasks/run-due") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/execution-items/123/send-via-bazhuayu") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/execution-items/123/send-via-bazhuayu") == "aicrm_next.automation_engine.api"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "GET", "/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "GET", "/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/admin/wechat-pay/products/new") == "next"
    assert _endpoint_for(samples, "GET", "/admin/wechat-pay/products/new") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "POST", "/api/admin/wechat-pay/products") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wechat-pay/products") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/lead-channels") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/lead-channels") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1/share") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1/share") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "POST", "/api/admin/wechat-pay/products/1/copy") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wechat-pay/products/1/copy") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/admin/wechat-pay/products/1/external-push") == "next"
    assert _endpoint_for(samples, "GET", "/api/admin/wechat-pay/products/1/external-push") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "PUT", "/api/admin/wechat-pay/products/1/external-push") == "next"
    assert _endpoint_for(samples, "PUT", "/api/admin/wechat-pay/products/1/external-push") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "POST", "/api/admin/wechat-pay/products/1/external-push/test") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/wechat-pay/products/1/external-push/test") == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/p/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "GET", "/p/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    assert _owner_for(samples, "OPTIONS", "/p/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "OPTIONS", "/p/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    assert _owner_for(samples, "GET", "/pay/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "GET", "/pay/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    assert _owner_for(samples, "OPTIONS", "/pay/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "OPTIONS", "/pay/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    assert _owner_for(samples, "GET", "/api/products/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "GET", "/api/products/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    assert _owner_for(samples, "POST", "/api/products/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "POST", "/api/products/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    assert _owner_for(samples, "OPTIONS", "/api/products/prd_20260518095708_9f77db") == "next"
    assert _endpoint_for(samples, "OPTIONS", "/api/products/prd_20260518095708_9f77db") == "aicrm_next.public_product.api"
    for method, path in (
        ("POST", "/api/checkout/wechat"),
        ("POST", "/api/checkout/alipay"),
        ("OPTIONS", "/api/checkout/wechat"),
        ("OPTIONS", "/api/checkout/alipay"),
        ("GET", "/api/checkout/unknown-child"),
        ("GET", "/api/orders/smoke"),
        ("GET", "/api/orders/smoke/status"),
        ("OPTIONS", "/api/orders/smoke"),
        ("OPTIONS", "/api/orders/smoke/status"),
        ("GET", "/api/orders/smoke/legacy-child"),
    ):
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/orders/smoke") == "next"
    assert _endpoint_for(samples, "GET", "/api/orders/smoke") == "aicrm_next.commerce.api"
    for method, path in (
        ("POST", "/api/wechat-pay/notify"),
        ("OPTIONS", "/api/wechat-pay/notify"),
        ("GET", "/api/wechat-pay/unknown-child"),
        ("POST", "/api/alipay/notify"),
        ("GET", "/api/alipay/return"),
        ("OPTIONS", "/api/alipay/return"),
        ("GET", "/api/alipay/unknown-child"),
    ):
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.commerce.api"
    for method, path in (
        ("GET", "/api/admin/wechat-pay/unknown-child"),
        ("OPTIONS", "/api/admin/wechat-pay/products"),
        ("GET", "/api/admin/alipay/transactions"),
        ("GET", "/api/admin/alipay/unknown-child"),
        ("GET", "/api/h5/wechat-pay/legacy-probe"),
        ("GET", "/api/h5/alipay/legacy-probe"),
    ):
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.commerce.api"
    assert _owner_for(samples, "GET", "/api/sidebar/jssdk-config") == "next"
    assert _endpoint_for(samples, "GET", "/api/sidebar/jssdk-config") == "aicrm_next.identity_contact.sidebar_jssdk"
    assert _owner_for(samples, "POST", "/api/customers/automation/webhook-deliveries/1/retry") == "next"
    assert _endpoint_for(samples, "POST", "/api/customers/automation/webhook-deliveries/1/retry") == "aicrm_next.automation_engine.api"


def test_checker_reports_no_unexpected_shadowed_exact_routes_or_blockers():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["blockers"] == []
    unexpected_shadowed = [
        item
        for item in result["shadowed_exact_routes"]
        if item["manifest_route_pattern"]
            not in {
                "/api/admin/wecom/tags*",
                "/api/admin/wecom/tag-groups*",
                "/api/h5/questionnaires/{slug}/submit",
                "/api/h5/wechat/oauth*",
        }
    ]
    assert unexpected_shadowed == []
