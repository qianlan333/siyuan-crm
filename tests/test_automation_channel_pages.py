from __future__ import annotations

import re

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.channel_binding_service import (
    bind_channels_to_program,
    save_channel_resource,
)

from automation_channel_admission_helpers import admin_action_token, create_program, login_admin


def _row_for(html: str, marker: str) -> str:
    match = re.search(rf"<tr[^>]*{re.escape(marker)}[^>]*>.*?</tr>", html, flags=re.S)
    assert match, marker
    return match.group(0)


def _seed_page_channels() -> dict[str, int]:
    program_id = create_program("page_p1")
    other_program_id = create_program("page_p2")
    qrcode = save_channel_resource(
        {
            "channel_code": "CH-PAGE-QR",
            "channel_name": "页面普通二维码",
            "channel_type": "qrcode",
            "carrier_type": "qrcode",
            "scene_value": "scene_page_qr",
            "qr_url": "https://example.test/qr.png",
            "welcome_message": "欢迎",
            "welcome_attachment_library_ids": [102],
            "entry_tag_id": "tag_qr",
            "entry_tag_name": "二维码标签",
            "status": "active",
        }
    )
    bound_link = save_channel_resource(
        {
            "channel_code": "CH-PAGE-LINK",
            "channel_name": "页面获客助手链接",
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "customer_channel": "wca_page_link",
            "link_url": "https://work.weixin.qq.com/ca/page",
            "welcome_miniprogram_library_ids": [201],
            "welcome_attachment_library_ids": [108],
            "status": "active",
        }
    )
    candidate_link = save_channel_resource(
        {
            "channel_code": "CH-PAGE-LINK-CANDIDATE",
            "channel_name": "可绑定获客助手链接",
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "customer_channel": "wca_page_candidate",
            "link_url": "https://work.weixin.qq.com/ca/candidate",
            "status": "active",
        }
    )
    other_bound_link = save_channel_resource(
        {
            "channel_code": "CH-PAGE-LINK-OTHER",
            "channel_name": "其他方案已绑定链接",
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "customer_channel": "wca_page_other",
            "link_url": "https://work.weixin.qq.com/ca/other",
            "status": "active",
        }
    )
    program_bindings = bind_channels_to_program(program_id, [int(qrcode["id"]), int(bound_link["id"])], {}, "pytest")[
        "bindings"
    ]
    other_bindings = bind_channels_to_program(other_program_id, [int(other_bound_link["id"])], {}, "pytest")["bindings"]
    return {
        "program_id": program_id,
        "other_program_id": other_program_id,
        "qrcode_id": int(qrcode["id"]),
        "bound_link_id": int(bound_link["id"]),
        "candidate_link_id": int(candidate_link["id"]),
        "other_bound_link_id": int(other_bound_link["id"]),
        "qrcode_binding_id": int(program_bindings[0]["id"]),
        "bound_link_binding_id": int(program_bindings[1]["id"]),
        "other_bound_link_binding_id": int(other_bindings[0]["id"]),
    }


def test_channel_center_page_splits_qrcode_and_wecom_link_actions(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    with app.app_context():
        ids = _seed_page_channels()

    response = client.get("/admin/channels")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "渠道码中心" in html
    assert "渠道码中心只管理渠道资产" in html
    assert "绑定到自动化运营" not in html
    assert "绑定冲突" not in html

    qrcode_row = _row_for(html, f'data-channel-id="{ids["qrcode_id"]}"')
    assert "普通二维码" in qrcode_row
    assert "下载二维码" in qrcode_row
    assert "查看" in qrcode_row
    assert "编辑" in qrcode_row
    assert "复制链接" not in qrcode_row
    assert "分享链接" not in qrcode_row

    link_row = _row_for(html, f'data-channel-id="{ids["bound_link_id"]}"')
    assert "企微获客助手链接" in link_row
    assert "复制链接" in link_row
    assert "分享链接" in link_row
    assert "查看" in link_row
    assert "编辑" in link_row
    assert "下载二维码" not in link_row


def test_channel_create_and_link_edit_pages_render_type_specific_controls(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    token = admin_action_token(client)
    create_response = client.post(
        "/api/admin/channels",
        json={
            "admin_action_token": token,
            "channel_type": "wecom_customer_acquisition",
            "carrier_type": "link",
            "channel_name": "保存获客链接",
            "channel_code": "CH-SAVE-LINK",
            "customer_channel": "wca_save_link",
            "link_url": "https://work.weixin.qq.com/ca/save",
            "welcome_miniprogram_library_ids": [201],
            "welcome_attachment_library_ids": [102, 108],
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    saved = create_response.get_json()["channel"]
    assert saved["channel_type"] == "wecom_customer_acquisition"
    assert saved["carrier_type"] == "link"
    assert saved["customer_channel"] == "wca_save_link"
    assert saved["final_url"].endswith("customer_channel=wca_save_link")
    assert saved["welcome_miniprogram_library_ids"] == [201]
    assert saved["welcome_attachment_library_ids"] == [102, 108]

    with app.app_context():
        get_db().execute(
            """
            INSERT INTO admin_users (wecom_userid, wecom_corpid, display_name, is_active)
            VALUES (?, ?, ?, TRUE)
            ON CONFLICT (wecom_corpid, wecom_userid)
            DO UPDATE SET display_name = EXCLUDED.display_name, is_active = TRUE
            """,
            ("sales_owner_channel_01", app.config["WECOM_CORP_ID"], "渠道负责人 01"),
        )
        get_db().execute(
            """
            INSERT INTO miniprogram_library (name, appid, pagepath, title, enabled)
            VALUES ('欢迎小程序', 'wx-material', 'pages/home', '欢迎小程序', TRUE)
            """
        )
        get_db().execute(
            """
            INSERT INTO attachment_library (name, file_name, mime_type, enabled)
            VALUES ('欢迎图片', 'welcome.png', 'image/png', TRUE),
                   ('欢迎PDF', 'welcome.pdf', 'application/pdf', TRUE)
            """
        )
        get_db().commit()

    new_page = client.get("/admin/channels/new")
    assert new_page.status_code == 200
    new_html = new_page.get_data(as_text=True)
    assert "普通二维码预览" not in new_html
    assert "保存后可下载二维码" not in new_html
    assert "状态" not in new_html
    assert "普通二维码场景值" not in new_html
    assert "二维码图片地址" not in new_html
    assert "小程序素材" in new_html
    assert "图片/PDF素材" in new_html
    assert "预览并选择小程序" in new_html
    assert "预览并选择图片/PDF" in new_html
    assert "预览并选择标签" in new_html
    assert "data-resource-picker-search" in new_html
    assert "小程序" in new_html
    assert "图片" in new_html
    assert "PDF" in new_html
    assert "负责人 owner_staff_id" not in new_html
    assert "<span>channel_code</span>" not in new_html
    assert "<span>scene_value</span>" not in new_html
    assert "<span>customer_channel</span>" not in new_html
    assert "<span>entry_tag_id</span>" not in new_html
    assert "<span>entry_tag_name</span>" not in new_html
    assert "入渠标签编号" not in new_html
    assert "入渠标签名称" not in new_html
    assert 'placeholder="sales_01"' not in new_html
    assert "选择负责人" in new_html
    assert "渠道负责人 01" in new_html
    assert "sales_owner_channel_01" in new_html
    assert "data-channel-owner-pick" in new_html
    assert "选择自动化运营计划" not in new_html
    materials = client.get("/api/admin/channel-welcome-materials?type=all&keyword=欢迎")
    assert materials.status_code == 200
    material_types = {item["type"] for item in materials.get_json()["materials"]}
    assert {"miniprogram", "image", "pdf"}.issubset(material_types)
    pdf_materials = client.get("/api/admin/channel-welcome-materials?type=pdf&keyword=欢迎").get_json()["materials"]
    assert pdf_materials
    assert {item["type"] for item in pdf_materials} == {"pdf"}

    edit_page = client.get(f"/admin/channels/{saved['id']}/edit")
    assert edit_page.status_code == 200
    edit_html = edit_page.get_data(as_text=True)
    assert "企微获客助手链接预览" in edit_html
    assert "该类型没有二维码下载动作，使用链接分享" in edit_html
    assert "复制链接" in edit_html
    assert "分享链接" in edit_html
    assert re.search(r'data-qrcode-section\s+hidden', edit_html)


def test_entry_channels_page_displays_two_types_and_filters_active_bound_links(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    with app.app_context():
        ids = _seed_page_channels()

    response = client.get(f"/admin/automation-conversion/programs/{ids['program_id']}/entry-channels")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "绑定已有渠道码" in html
    assert "入池清洗" in html
    assert "历史用户导入" in html
    assert "普通二维码" in html
    assert "企微获客助手链接" in html
    assert "入池策略" not in html
    assert "auto_enter_pool" not in html
    assert "initial_audience_code" not in html
    assert f'data-bind-candidate data-channel-id="{ids["candidate_link_id"]}"' in html
    assert f'data-bind-candidate data-channel-id="{ids["other_bound_link_id"]}"' not in html
    assert "导入模式：只做预估" in html
    assert "入池时间：使用导入时间" in html


def test_qrcode_download_is_png_attachment_and_link_channel_rejects(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    with app.app_context():
        ids = _seed_page_channels()

    qrcode_response = client.get(f"/api/admin/channels/{ids['qrcode_id']}/qrcode/download")
    assert qrcode_response.status_code == 200
    assert qrcode_response.content_type.startswith("image/png")
    disposition = qrcode_response.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert "CH-PAGE-QR" in disposition
    assert qrcode_response.data.startswith(b"\x89PNG")

    link_response = client.get(f"/api/admin/channels/{ids['bound_link_id']}/qrcode/download")
    assert link_response.status_code == 400
    assert link_response.get_json()["error"] == "link channel does not support qrcode download"


def _insert_program_member(
    *,
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    stage_code: str,
    audience_code: str,
    entered_at: str,
    in_program: bool = True,
) -> int:
    row = get_db().execute(
        """
        INSERT INTO automation_program_member (
            program_id, external_contact_id, source_channel_id, source_binding_id,
            first_source_channel_id, latest_source_channel_id, in_program,
            current_stage_code, current_audience_code, current_stage_entered_at,
            pool_entered_at, exited_at, exit_reason, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? THEN NULL ELSE CAST(? AS timestamptz) END, CASE WHEN ? THEN '' ELSE 'manual_exit' END, ?, ?)
        RETURNING id
        """,
        (
            program_id,
            external_contact_id,
            channel_id,
            binding_id,
            channel_id,
            channel_id,
            in_program,
            stage_code,
            audience_code,
            entered_at,
            entered_at,
            in_program,
            entered_at,
            in_program,
            entered_at,
            entered_at,
        ),
    ).fetchone()
    get_db().commit()
    return int(row["id"])


def test_member_stage_summary_counts_only_current_binding_members(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    with app.app_context():
        ids = _seed_page_channels()
        stages = [
            ("wm_order", "order_review", "pending_questionnaire"),
            ("wm_questionnaire", "questionnaire_review", "pending_questionnaire"),
            ("wm_operating", "operating", "operating"),
            ("wm_converted", "converted", "converted"),
        ]
        for external_contact_id, stage_code, audience_code in stages:
            _insert_program_member(
                program_id=ids["program_id"],
                channel_id=ids["qrcode_id"],
                binding_id=ids["qrcode_binding_id"],
                external_contact_id=external_contact_id,
                stage_code=stage_code,
                audience_code=audience_code,
                entered_at="2026-05-23 10:00:00+08",
            )
        _insert_program_member(
            program_id=ids["program_id"],
            channel_id=ids["bound_link_id"],
            binding_id=ids["bound_link_binding_id"],
            external_contact_id="wm_other_channel",
            stage_code="operating",
            audience_code="operating",
            entered_at="2026-05-23 10:00:00+08",
        )

    response = client.get(
        f"/api/admin/automation-conversion/programs/{ids['program_id']}/channel-bindings/{ids['qrcode_binding_id']}/member-stage-summary"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["summary"]["total"] == 4
    assert payload["summary"]["order_review"] == 1
    assert payload["summary"]["questionnaire_review"] == 1
    assert payload["summary"]["operating"] == 1
    assert payload["summary"]["converted"] == 1
    assert {item["external_contact_id"] for item in payload["members"]} == {
        "wm_order",
        "wm_questionnaire",
        "wm_operating",
        "wm_converted",
    }
    assert "wm_other_channel" not in {item["external_contact_id"] for item in payload["members"]}

    missing = client.get(
        f"/api/admin/automation-conversion/programs/{ids['program_id']}/channel-bindings/999999/member-stage-summary"
    )
    assert missing.status_code == 404


def test_entry_channel_binding_payload_is_channel_ids_only_and_old_setup_is_readonly(app, client, monkeypatch):
    login_admin(client, app, monkeypatch)
    with app.app_context():
        ids = _seed_page_channels()

    entry_html = client.get(f"/admin/automation-conversion/programs/{ids['program_id']}/entry-channels").get_data(as_text=True)
    assert "initial_audience_code" not in entry_html
    assert "auto_enter_pool" not in entry_html
    assert "entry_rule_json" not in entry_html
    js_source = (
        "/Users/qianlan/Documents/New project/AI-CRM-channel-admission/"
        "wecom_ability_service/static/admin_console/channel_admission_pages.js"
    )
    with open(js_source, encoding="utf-8") as handle:
        source = handle.read()
    bind_body = source[source.index("channel_ids: ids") - 120 : source.index("channel_ids: ids") + 60]
    assert "channel_ids: ids" in bind_body
    assert "auto_enter_pool" not in bind_body
    assert "initial_audience_code" not in bind_body
    assert "entry_rule_json" not in bind_body

    setup_response = client.get(f"/admin/automation-conversion/programs/{ids['program_id']}/setup?step=entry")
    assert setup_response.status_code == 200
    setup_html = setup_response.get_data(as_text=True)
    assert "入口渠道已迁移" in setup_html
    assert f"/admin/automation-conversion/programs/{ids['program_id']}/entry-channels" in setup_html
    assert "生成二维码" not in setup_html
    assert "重新生成二维码" not in setup_html
    assert "initial_audience_code" not in setup_html
