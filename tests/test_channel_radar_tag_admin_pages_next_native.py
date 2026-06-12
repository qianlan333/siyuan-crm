from __future__ import annotations

from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_TEMPLATES = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console"
FRONTEND_STATIC = ROOT / "aicrm_next" / "frontend_compat" / "static" / "admin_console"
AUTOMATION_TEMPLATES = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console"
AUTOMATION_STATIC = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console"
CUSTOMER_TAGS_TEMPLATES = ROOT / "aicrm_next" / "customer_tags" / "templates" / "admin_console"
CUSTOMER_TAGS_STATIC = ROOT / "aicrm_next" / "customer_tags" / "static" / "admin_console"
RADAR_TEMPLATES = ROOT / "aicrm_next" / "radar_links" / "templates" / "admin_console"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("SECRET_KEY", "channel-radar-tag-pages-native-test")
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_channel_radar_and_tag_pages_are_served_by_next_native_routers(monkeypatch) -> None:
    app = create_app()
    route_modules = {
        route.name: route.endpoint.__module__
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.name
        in {
            "api.admin_channels_page",
            "api.admin_channel_new_page",
            "api.admin_channel_edit_page",
            "api.admin_radar_links",
            "api.admin_radar_link_new",
            "api.admin_radar_link_edit",
            "api.admin_radar_link_detail",
            "api.admin_wecom_tags_page",
        }
    }

    assert route_modules == {
        "api.admin_channels_page": "aicrm_next.automation_engine.channel_admin_pages",
        "api.admin_channel_new_page": "aicrm_next.automation_engine.channel_admin_pages",
        "api.admin_channel_edit_page": "aicrm_next.automation_engine.channel_admin_pages",
        "api.admin_radar_links": "aicrm_next.radar_links.admin_pages",
        "api.admin_radar_link_new": "aicrm_next.radar_links.admin_pages",
        "api.admin_radar_link_edit": "aicrm_next.radar_links.admin_pages",
        "api.admin_radar_link_detail": "aicrm_next.radar_links.admin_pages",
        "api.admin_wecom_tags_page": "aicrm_next.customer_tags.admin_pages",
    }

    client = _client(monkeypatch)
    created = client.post(
        "/api/admin/channels",
        json={"channel_name": "Native ownership smoke", "channel_type": "qrcode", "owner_staff_id": "sales_01"},
    )
    channel_id = created.json()["channel"]["id"]

    for url in [
        "/admin/channels",
        "/admin/channels/new",
        f"/admin/channels/{channel_id}/edit",
        "/admin/radar-links",
        "/admin/radar-links/new",
        "/admin/radar-links/1/edit",
        "/admin/radar-links/1/detail",
        "/admin/wecom-tags",
    ]:
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.headers.get("X-AICRM-Compatibility-Facade") is None, url
        assert "客户管理后台" in response.text, url
        assert "Not Found" not in response.text, url


def test_channel_radar_and_tag_pages_keep_existing_static_and_api_contracts(monkeypatch) -> None:
    client = _client(monkeypatch)

    channels = client.get("/admin/channels")
    channel_new = client.get("/admin/channels/new")
    radar_list = client.get("/admin/radar-links")
    radar_new = client.get("/admin/radar-links/new")
    radar_detail = client.get("/admin/radar-links/1/detail")
    wecom_tags = client.get("/admin/wecom-tags")

    assert "/api/admin/channels?limit=300" in channels.text
    assert "/static/automation-engine/admin_console/channel_admission_pages.css" in channels.text
    assert "/static/automation-engine/admin_console/channel_code_center_next.js" in channels.text
    assert "新建渠道" in channels.text
    assert "自动化运营" in channels.text

    assert "/static/automation-engine/admin_console/channel_admission_pages.css" in channel_new.text
    assert "/static/automation-engine/admin_console/channel_admission_pages.js" in channel_new.text
    assert "/static/admin_console/material_picker.js" in channel_new.text
    assert "/static/admin_console/send_content_composer.js" in channel_new.text
    assert '"/api/admin/wecom/tags"' in channel_new.text

    assert "/api/admin/radar-links" in radar_list.text
    assert "/admin/radar-links/new" in radar_list.text
    assert "/api/admin/radar-links/new/options" in radar_new.text
    assert "/static/admin_console/material_picker.js" in radar_new.text
    assert "AICRMMaterialPicker.open" in radar_new.text
    assert "/api/admin/radar-links/${linkId}/events" in radar_detail.text

    assert "/static/customer-tags/admin_console/wecom_tag_management.js" in wecom_tags.text
    assert 'data-api-tags="/api/admin/wecom/tags"' in wecom_tags.text
    assert 'data-api-groups="/api/admin/wecom/tag-groups"' in wecom_tags.text
    assert 'data-api-sync="/api/admin/wecom/tags/sync"' in wecom_tags.text


def test_channel_radar_and_tag_pages_are_removed_from_frontend_compat_inventory() -> None:
    assert not (ROOT / "aicrm_next/frontend_compat/legacy_routes.py").exists()


def test_channel_radar_and_tag_templates_and_static_are_native_owned() -> None:
    native_files = [
        AUTOMATION_TEMPLATES / "channel_code_center.html",
        AUTOMATION_TEMPLATES / "channel_code_form.html",
        AUTOMATION_STATIC / "channel_admission_pages.css",
        AUTOMATION_STATIC / "channel_admission_pages.js",
        AUTOMATION_STATIC / "channel_code_center_next.js",
        CUSTOMER_TAGS_TEMPLATES / "config_wecom_tags.html",
        CUSTOMER_TAGS_STATIC / "wecom_tag_management.js",
        RADAR_TEMPLATES / "radar_links.html",
        RADAR_TEMPLATES / "radar_link_form.html",
        RADAR_TEMPLATES / "radar_link_detail.html",
    ]
    removed_frontend_compat_files = [
        FRONTEND_TEMPLATES / "channel_code_center.html",
        FRONTEND_TEMPLATES / "channel_code_form.html",
        FRONTEND_STATIC / "channel_admission_pages.css",
        FRONTEND_STATIC / "channel_admission_pages.js",
        FRONTEND_STATIC / "channel_code_center_next.js",
        FRONTEND_TEMPLATES / "config_wecom_tags.html",
        FRONTEND_STATIC / "wecom_tag_management.js",
        FRONTEND_TEMPLATES / "radar_links.html",
        FRONTEND_TEMPLATES / "radar_link_form.html",
        FRONTEND_TEMPLATES / "radar_link_detail.html",
    ]

    for path in native_files:
        assert path.exists(), path
    for path in removed_frontend_compat_files:
        assert not path.exists(), path


def test_native_static_mounts_serve_moved_page_assets(monkeypatch) -> None:
    client = _client(monkeypatch)

    channel_css = client.get("/static/automation-engine/admin_console/channel_admission_pages.css")
    channel_js = client.get("/static/automation-engine/admin_console/channel_admission_pages.js")
    tag_js = client.get("/static/customer-tags/admin_console/wecom_tag_management.js")

    assert channel_css.status_code == 200
    assert ".channel-action-cell" in channel_css.text
    assert channel_js.status_code == 200
    assert "AICRMChannelWelcomeAdapter" in channel_js.text
    assert tag_js.status_code == 200
    assert "/api/admin/wecom/tags" in tag_js.text
