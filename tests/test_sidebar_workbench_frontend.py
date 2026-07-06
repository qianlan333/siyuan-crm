from __future__ import annotations

from pathlib import Path


WORKBENCH_TEMPLATE = Path("aicrm_next/frontend_compat/templates/sidebar_customer_workbench.html")
WORKBENCH_JS = Path("aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.js")
WORKBENCH_CSS = Path("aicrm_next/frontend_compat/static/sidebar_workbench/sidebar_workbench.css")
WORKBENCH_PRODUCT_CARD_COVER = Path("aicrm_next/frontend_compat/static/sidebar_workbench/product-card-cover.png")


def test_sidebar_workbench_v2_page_is_next_owned(client):
    response = client.get("/sidebar/bind-mobile?external_userid=wm_frontend&owner_userid=sales_01")
    html = response.text

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "客户侧边栏 V2 工作台" in html
    assert 'data-workbench-url="/api/sidebar/v2/workbench"' in html
    assert 'data-material-send-url="/api/sidebar/v2/materials/send"' in html
    assert "sidebar_workbench/sidebar_workbench.js" in html
    assert "自动化转化操作区" not in html


def test_sidebar_workbench_static_contract_has_next_surface_only():
    template = WORKBENCH_TEMPLATE.read_text(encoding="utf-8")
    script = WORKBENCH_JS.read_text(encoding="utf-8")
    css = WORKBENCH_CSS.read_text(encoding="utf-8")
    combined = template + "\n" + script + "\n" + css

    assert '["profile", "核心画像"]' in script
    assert '["questionnaires", "问卷"]' in script
    assert '["products", "商品"]' in script
    assert '["orders", "订单"]' in script
    assert 'invokeWeCom("getCurExternalContact"' in script
    assert "sendChatMessage" in script
    assert "PRODUCT_CARD_IMAGE_PATH" in script
    assert "product-card-cover.png" in script
    assert "material-thumb" in script
    assert "skeleton-list" in script
    assert "requestPanelJson" in script
    assert "PANEL_TIMEOUT_MS" in script
    assert "PANEL_CACHE_TTL_MS" in script
    assert 'cache: "no-store"' in script
    assert "sidebar_owner_token" in script
    assert "data-material-thumb-img" in script
    assert "data-order-detail-url" in script
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert "@keyframes sidebar-skeleton" in css
    assert WORKBENCH_PRODUCT_CARD_COVER.exists()
    assert "context_token" not in script
    assert "customer-avatar" not in combined
    assert "复制商品链接" not in combined
    assert "待确认员工身份" not in combined
    assert "demo" not in combined.lower()


def test_sidebar_workbench_query_context_skips_wecom_sdk_path():
    script = WORKBENCH_JS.read_text(encoding="utf-8")

    assert "const hasQuery = await resolveContextFromQuery();" in script
    assert "await resolveContextFromWeCom();" in script


def test_sidebar_workbench_questionnaire_requests_reuse_owner_scoped_context_query():
    script = WORKBENCH_JS.read_text(encoding="utf-8")

    assert 'queryUrl(endpoint("questionnairesUrl"), customerContextQuery())' in script
    assert 'queryUrl(endpoint("questionnairesUrl"), { external_userid: state.external_userid })' not in script
