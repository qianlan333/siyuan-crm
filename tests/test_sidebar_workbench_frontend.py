from __future__ import annotations

from pathlib import Path


WORKBENCH_TEMPLATE = Path("wecom_ability_service/templates/sidebar_customer_workbench.html")
WORKBENCH_JS = Path("wecom_ability_service/static/sidebar_workbench/sidebar_workbench.js")
WORKBENCH_CSS = Path("wecom_ability_service/static/sidebar_workbench/sidebar_workbench.css")


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
    css = WORKBENCH_CSS.read_text(encoding="utf-8")
    combined = template + "\n" + script + "\n" + css

    assert '["profile", "核心画像"]' in script
    assert '["questionnaires", "问卷"]' in script
    assert '["products", "商品"]' in script
    assert '["orders", "订单"]' in script
    assert '["materials", "素材"]' in script
    assert '["other_staff_messages", "其他客服聊天"]' in script
    assert "data-tab" in script
    assert "badge" not in combined.lower()
    assert "phone-state loading" in template
    assert "加载中..." in template
    assert "20260523-top-card-no-avatar" in template
    assert "customer-avatar" not in combined
    assert "class=\"avatar\"" not in combined
    assert ".avatar" not in css
    assert "grid-template-columns: minmax(0, 1fr) auto" in css

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
    assert "复制商品链接" in script
    assert "data-product-copy" in script
    assert "product_url" in script
    assert "发送介绍" not in script
    assert "商品介绍发送能力待接入" not in script
    assert "data-product-send" not in script
    assert "data-product-detail" not in script
    assert "image-thumb" in script
    assert "material-thumb" in script
    assert "material--image" in script
    assert "material-main" in script
    assert "material-title" in script
    assert "material-tags" in script
    assert "thumbnail_url" in script
    assert 'alt=""' in script
    assert "data-material-thumb-img" in script
    assert "sendChatMessage" in script
    assert "delivery_mode" in script
    assert "chat_toolbar" in script
    assert ">发送</button>" in script
    assert "发给客户" not in combined
    assert "预览" not in combined
    assert "更新时间" not in combined
    assert "source_url" not in script
    assert "item.description" not in script
    assert "object-fit: cover" in css
    assert ".material-thumb img" in css
    assert ".thumb.image-thumb img" in css
    assert "grid-column: 1 / 3" not in css
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


def test_sidebar_legacy_binding_apis_remain_available(client):
    status_response = client.get("/api/sidebar/contact-binding-status")
    bind_response = client.post("/api/sidebar/bind-mobile", json={})
    jssdk_response = client.get("/api/sidebar/jssdk-config")

    assert status_response.status_code == 400
    assert bind_response.status_code == 400
    assert jssdk_response.status_code == 400


def test_sidebar_workbench_v2_can_fallback_to_legacy_by_query(client):
    response = client.get("/sidebar/bind-mobile?v=legacy")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "客户档案绑定" in html
    assert "自动化转化操作区" in html


def test_sidebar_workbench_v2_can_fallback_to_legacy_by_config(client, app):
    app.config["SIDEBAR_WORKBENCH_V2_ENABLED"] = "false"

    response = client.get("/sidebar/bind-mobile")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "客户档案绑定" in html
    assert "自动化转化操作区" in html
