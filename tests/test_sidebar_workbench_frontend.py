from __future__ import annotations

from pathlib import Path


WORKBENCH_TEMPLATE = Path("wecom_ability_service/templates/sidebar_customer_workbench.html")
WORKBENCH_JS = Path("wecom_ability_service/static/sidebar_workbench/sidebar_workbench.js")
WORKBENCH_CSS = Path("wecom_ability_service/static/sidebar_workbench/sidebar_workbench.css")
WORKBENCH_PRODUCT_CARD_COVER = Path("wecom_ability_service/static/sidebar_workbench/product-card-cover.png")
NEXT_WORKBENCH_TEMPLATE = Path("aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html")
NEXT_WORKBENCH_JS = Path("aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js")
NEXT_WORKBENCH_CSS = Path("aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.css")
NEXT_WORKBENCH_PRODUCT_CARD_COVER = Path("aicrm_next/frontend_compat/static/sidebar_workbench/product-card-cover.png")


def test_sidebar_workbench_v2_default_page_is_not_legacy_long_page(client):
    response = client.get("/sidebar/bind-mobile?external_userid=wm_frontend&owner_userid=sales_01")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "客户侧边栏 V2 工作台" in html
    assert "data-workbench-url=\"/api/sidebar/v2/workbench\"" in html
    assert "data-material-send-url=\"/api/sidebar/v2/materials/send\"" in html
    assert "sidebar_workbench/sidebar_workbench.js" in html
    assert "customer-avatar" not in html
    assert "class=\"avatar\"" not in html
    assert "加载中..." in html
    assert "自动化转化操作区" not in html
    assert "实时标签" not in html
    assert "一键自动化写话术" not in html
    assert "客户分层" not in html
    assert "第 3 天" not in html
    assert "重点跟进节点" not in html


def test_sidebar_workbench_static_contract_has_demo_approved_surface_only():
    template = WORKBENCH_TEMPLATE.read_text(encoding="utf-8")
    script = WORKBENCH_JS.read_text(encoding="utf-8")
    next_template = NEXT_WORKBENCH_TEMPLATE.read_text(encoding="utf-8")
    next_script = NEXT_WORKBENCH_JS.read_text(encoding="utf-8")
    css = WORKBENCH_CSS.read_text(encoding="utf-8")
    next_css = NEXT_WORKBENCH_CSS.read_text(encoding="utf-8")
    combined = template + "\n" + script + "\n" + next_template + "\n" + next_script + "\n" + css + "\n" + next_css

    assert '["profile", "核心画像"]' in script
    assert '["questionnaires", "问卷"]' in script
    assert '["products", "商品"]' in script
    assert '["orders", "订单"]' in script
    assert '["materials", "素材"]' in script
    assert '["other_staff_messages", "其他客服聊天"]' in script
    assert "data-tab" in script
    assert "identifying_customer" in script
    assert "sdk_unavailable" in script
    assert "context_missing" in script
    assert "loading_workbench" in script
    assert "degraded_ready" in script
    assert "AbortController" in script
    assert "timeoutMs" in script
    assert 'const error = new Error(method + " timeout");' in script
    assert 'invokeWeCom("getCurExternalContact"' in script
    assert "data-retry-boot" in script
    assert "bindingState.classList.toggle(\"loading\", isLoading)" in script
    assert "query context" in script
    assert "workbench response" in script
    assert "badge" not in combined.lower()
    assert "phone-state loading" in template
    assert "加载中..." in template
    assert "20260610-wecom-sdk" in template
    assert "20260610-wecom-sdk" in next_template
    assert "https://res.wx.qq.com/wwopen/js/jsapi/jweixin-1.0.0.js" in template
    assert "https://res.wx.qq.com/wwopen/js/jsapi/jweixin-1.0.0.js" in next_template
    assert "https://res.wx.qq.com/open/js/jweixin-1.6.0.js" not in combined
    assert "function getWeComSdk()" in script
    assert "window.jWeixin || window.wx || null" in script
    assert "window.wx = sdk;" in script
    assert "customer-avatar" not in combined
    assert "class=\"avatar\"" not in combined
    assert ".avatar" not in css
    assert ".avatar" not in next_css
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert "grid-template-columns: minmax(0, 1fr) auto" in next_css

    assert "用户来源" in script
    assert "行业信息" in script
    assert "行业具体描述" in script
    assert "需求、卡点、跟进状态" in script
    assert "textarea" in script
    assert "textAreaField(\"source\", \"用户来源\"" in script
    assert "textAreaField(\"industry\", \"行业信息\"" in script
    assert "<select" not in combined
    assert "selectField" not in combined
    assert "请选择" not in combined
    assert "发送商品" in script
    assert "data-product-send" in script
    assert "PRODUCT_CARD_IMAGE_PATH" in script
    assert "product-card-cover.png" in script
    assert 'msgtype: "news"' in script
    assert "news: {" in script
    assert "link: String(payload.url" in script
    assert 'desc: ""' in script
    assert "imgUrl" in script
    assert "sendLinkToCurrentChat" in script
    assert "复制商品链接" not in combined
    assert "data-product-copy" not in combined
    assert "copyText" not in combined
    assert "product_url" in script
    assert "customerContextQuery()" in script
    assert "product_url_has_context" in script
    assert "payload.customer" in script
    assert "renderTop();" in script
    assert "context_token" not in script
    assert "发送介绍" not in script
    assert "商品介绍发送能力待接入" not in script
    assert "data-product-detail" not in script
    assert "image-thumb" in script
    assert "material-thumb" in script
    assert "material-thumb" in next_script
    assert "material--image" in script
    assert "material--image" in next_script
    assert "material-main" in script
    assert "material-title" in script
    assert "material-tags" in script
    assert "thumbnail_url" in script
    assert 'alt=""' in script
    assert 'alt=""' in next_script
    assert "data-material-thumb-img" in script
    assert "data-material-thumb-img" in next_script
    assert "sendChatMessage" in script
    assert "delivery_mode" in script
    assert "chat_toolbar" in script
    assert ">发送</button>" in script
    assert "发给客户" not in combined
    assert "预览" not in combined
    assert WORKBENCH_PRODUCT_CARD_COVER.exists()
    assert NEXT_WORKBENCH_PRODUCT_CARD_COVER.exists()
    assert "更新时间" not in combined
    assert "source_url" not in script
    assert "source_url" not in next_script
    assert "item.description" not in script
    assert "item.description" not in next_script
    assert "object-fit: cover" in css
    assert "object-fit: cover" in next_css
    assert ".material-thumb img" in css
    assert ".material-thumb img" in next_css
    assert ".thumb.image-thumb img" in css
    assert ".thumb.image-thumb img" in next_css
    assert "grid-column: 1 / 3" not in css
    assert "grid-column: 1 / 3" not in next_css
    assert "data-order-detail-url" in script
    assert "window.open(link, \"_blank\", \"noopener\")" in script
    assert "window.location.href = link" not in combined
    assert "详情能力待接入" not in script

    forbidden = [
        "第 3 天",
        "重点跟进节点",
        "当前阶段",
        "负责人",
        "问卷数量",
        "最近订单",
        "AI 写话术",
        "入池",
        "换池",
        "用途说明",
        "状态角标",
        "原始记录",
        "推荐理由",
        "适配说明",
        "字段依据",
        "客户分层",
        "demo",
        "18210198814",
    ]
    for text in forbidden:
        assert text not in combined


def test_sidebar_workbench_static_copies_stay_in_sync():
    assert WORKBENCH_JS.read_text(encoding="utf-8") == NEXT_WORKBENCH_JS.read_text(encoding="utf-8")


def test_sidebar_workbench_query_context_skips_wecom_sdk_path():
    script = WORKBENCH_JS.read_text(encoding="utf-8")

    assert "const hasQuery = await resolveContextFromQuery();" in script
    assert 'const contextResult = hasQuery ? { ok: true, status: WORKBENCH_STATES.identifying_customer, source: "query" } : await resolveContextFromWeCom();' in script


def test_sidebar_legacy_binding_apis_remain_available(client):
    status_response = client.get("/api/sidebar/contact-binding-status")
    bind_response = client.post("/api/sidebar/bind-mobile", json={})
    jssdk_response = client.get("/api/sidebar/jssdk-config")

    assert status_response.status_code == 400
    assert bind_response.status_code == 400
    assert jssdk_response.status_code == 400
    assert "X-AICRM-Compatibility-Facade" not in jssdk_response.headers


def test_sidebar_workbench_v2_ignores_legacy_query_fallback(client):
    response = client.get("/sidebar/bind-mobile?v=legacy")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="sidebar-workbench-root"' in html
    assert 'data-workbench-url="/api/sidebar/v2/workbench"' in html
    assert "自动化转化操作区" not in html


def test_sidebar_workbench_v2_ignores_disabled_legacy_flag(client, app):
    app.config["SIDEBAR_WORKBENCH_V2_ENABLED"] = "false"

    response = client.get("/sidebar/bind-mobile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="sidebar-workbench-root"' in html
    assert 'data-workbench-url="/api/sidebar/v2/workbench"' in html
    assert "自动化转化操作区" not in html
