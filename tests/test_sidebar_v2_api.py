from __future__ import annotations

import base64
import json

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.infra.signed_context import load_sidebar_product_context_token

_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAEAAAcAAekVCC0AAAAASUVORK5CYII="
)
_TINY_PNG_B64 = base64.b64encode(_TINY_PNG_BYTES).decode("ascii")


def _seed_contact(external_userid: str = "wm_sidebar_v2") -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (external_userid) DO UPDATE SET
            customer_name = EXCLUDED.customer_name,
            owner_userid = EXCLUDED.owner_userid,
            remark = EXCLUDED.remark,
            description = EXCLUDED.description
        """,
        (external_userid, "月朗", "owner_current", "月朗", ""),
    )
    db.commit()


def test_sidebar_v2_workbench_returns_text_profile_fields_without_enum_options(client, app):
    with app.app_context():
        _seed_contact("wx_ext_001")

    response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": "wx_ext_001"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["profile"] == {
        "source": "",
        "industry": "",
        "industry_description": "",
        "needs_blockers_followup": "",
    }
    assert "profile_options" not in payload
    assert payload["modules"] == ["profile", "questionnaires", "products", "orders", "materials", "other_staff_messages"]
    assert "counts" not in payload
    assert payload["diagnostics"]["display_name_source"]


def test_sidebar_v2_workbench_resolves_display_name_from_contacts_or_identity_map(client, app):
    external_userid = "wmbNXy_raw_should_not_title"
    identity_only_external_userid = "wm_identity_name_only"
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, '', 'sales_01', '真实备注名', '')
            """,
            (external_userid,),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, '', '', ?, ?)
            """,
            ("ww-test", external_userid, "sales_01", "身份表姓名"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, '', '', ?, ?)
            """,
            ("ww-test", identity_only_external_userid, "sales_02", "身份表唯一姓名"),
        )
        db.commit()

    response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": external_userid})
    identity_only_response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": identity_only_external_userid})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["customer"]["display_name"] == "真实备注名"
    assert payload["customer"]["external_userid"] == external_userid
    assert payload["diagnostics"]["display_name_source"] == "contacts.remark"
    assert payload["customer"]["display_name"] != external_userid
    assert identity_only_response.status_code == 200
    identity_only_payload = identity_only_response.get_json()
    assert identity_only_payload["customer"]["display_name"] == "身份表唯一姓名"
    assert identity_only_payload["diagnostics"]["display_name_source"] == "wecom_external_contact_identity_map.name"


def _seed_mobile_binding(external_userid: str, mobile: str = "18906252970", owner_userid: str = "owner_current") -> None:
    db = get_db()
    person_id = db.execute(
        """
        INSERT INTO people (mobile, third_party_user_id)
        VALUES (?, '')
        ON CONFLICT (mobile) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (mobile,),
    ).fetchone()["id"]
    db.execute(
        """
        INSERT INTO external_contact_bindings (
            external_userid, person_id, first_bound_by_userid,
            first_owner_userid, last_owner_userid
        ) VALUES (?, ?, 'questionnaire_submit', ?, ?)
        ON CONFLICT (external_userid) DO UPDATE SET
            person_id = EXCLUDED.person_id,
            last_owner_userid = EXCLUDED.last_owner_userid,
            updated_at = CURRENT_TIMESTAMP
        """,
        (external_userid, person_id, owner_userid, owner_userid),
    )
    db.commit()


def test_sidebar_v2_workbench_uses_fresh_binding_after_customer_context_failure(client, app, monkeypatch):
    from aicrm_next.customer_read_model import sidebar_v2 as sidebar_read_model

    external_userid = "wm_context_failed_but_bound"

    class FailingContextQuery:
        def __call__(self, request):
            raise RuntimeError("customer read model transaction aborted")

    monkeypatch.setattr(sidebar_read_model, "GetCustomerContextQuery", lambda: FailingContextQuery())
    monkeypatch.setattr(sidebar_read_model, "build_customer_live_source_repository", lambda: (_ for _ in ()).throw(RuntimeError("live source shares aborted transaction")))
    with app.app_context():
        _seed_contact(external_userid)
        _seed_mobile_binding(external_userid)

    response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": external_userid})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["customer"]["is_bound"] is True
    assert payload["customer"]["mobile"] == "18906252970"
    assert payload["diagnostics"]["context_source_status"] == "error"
    assert payload["diagnostics"]["binding_source"] == "fresh_binding_status"


def test_sidebar_v2_workbench_fresh_binding_overrides_stale_unbound_context(client, app, monkeypatch):
    from aicrm_next.customer_read_model import sidebar_v2 as sidebar_read_model

    external_userid = "wm_stale_context_but_bound"

    class StaleContextQuery:
        def __call__(self, request):
            return {
                "ok": True,
                "customer": {
                    "display_name": "陈旧上下文姓名",
                    "owner_userid": "owner_current",
                    "binding": {"is_bound": False, "mobile": "", "binding_status": "unbound"},
                },
                "binding": {"is_bound": False, "mobile": "", "binding_status": "unbound"},
                "timeline": {"items": []},
                "recent_messages": [],
            }

    monkeypatch.setattr(sidebar_read_model, "GetCustomerContextQuery", lambda: StaleContextQuery())
    with app.app_context():
        _seed_contact(external_userid)
        _seed_mobile_binding(external_userid, "18906252970")

    response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": external_userid})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["customer"]["display_name"] == "月朗"
    assert payload["customer"]["is_bound"] is True
    assert payload["customer"]["mobile"] == "18906252970"
    assert payload["diagnostics"]["context_source_status"] == "next_read_model"
    assert payload["diagnostics"]["binding_source"] == "fresh_binding_status"


def test_sidebar_v2_profile_put_accepts_free_text_source_and_industry(client):
    response = client.put(
        "/api/sidebar/v2/profile",
        json={
            "external_userid": "wm_sidebar_v2",
            "source": "  媛子咨询群，朋友介绍  ",
            "industry": "  大健康，线下门店  ",
            "industry_description": "  本地连锁健康管理门店  ",
            "needs_blockers_followup": "  想先看案例  ",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["profile"] == {
        "source": "媛子咨询群，朋友介绍",
        "industry": "大健康，线下门店",
        "industry_description": "本地连锁健康管理门店",
        "needs_blockers_followup": "想先看案例",
    }


def test_sidebar_v2_profile_put_persists_fixed_fields(client):
    response = client.put(
        "/api/sidebar/v2/profile",
        json={
            "external_userid": "wm_sidebar_profile_save",
            "source": "流量群",
            "industry": "教育培训",
            "industry_description": "  K12 阅读训练  ",
            "needs_blockers_followup": "  预算待确认  ",
            "updated_by": "sales_01",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["profile"] == {
        "source": "流量群",
        "industry": "教育培训",
        "industry_description": "K12 阅读训练",
        "needs_blockers_followup": "预算待确认",
    }

    workbench = client.get(
        "/api/sidebar/v2/workbench",
        query_string={"external_userid": "wm_sidebar_profile_save"},
    ).get_json()
    assert workbench["profile"] == {
        "source": "流量群",
        "industry": "教育培训",
        "industry_description": "K12 阅读训练",
        "needs_blockers_followup": "预算待确认",
    }


def test_sidebar_v2_questionnaires_groups_answers(client, app):
    with app.app_context():
        _seed_contact()
        db = get_db()
        questionnaire_id = db.execute(
            """
            INSERT INTO questionnaires (slug, name, title)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            ("reading-v2", "阅读能力测评问卷", "阅读能力测评问卷"),
        ).fetchone()["id"]
        submission_id = db.execute(
            """
            INSERT INTO questionnaire_submissions (questionnaire_id, external_userid, submitted_at)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            (questionnaire_id, "wm_sidebar_v2", "2026-05-18 20:41:00"),
        ).fetchone()["id"]
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_texts_snapshot, text_value
            ) VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                1,
                "single_choice",
                "客户来源",
                json.dumps(["流量群"], ensure_ascii=False),
                "",
                submission_id,
                2,
                "textarea",
                "主要需求",
                json.dumps([], ensure_ascii=False),
                "提升阅读兴趣",
            ),
        )
        db.commit()

    response = client.get("/api/sidebar/v2/questionnaires", query_string={"external_userid": "wm_sidebar_v2"})

    assert response.status_code == 200
    questionnaire = response.get_json()["questionnaires"][0]
    assert questionnaire["title"] == "阅读能力测评问卷"
    assert questionnaire["submitted_at"] == "2026-05-18 20:41"
    assert questionnaire["answer_count"] == 2
    assert questionnaire["total_count"] == 2
    assert questionnaire["answers"] == [
        {"question": "客户来源", "answer": "流量群"},
        {"question": "主要需求", "answer": "提升阅读兴趣"},
    ]


def test_sidebar_v2_materials_use_unified_schema(client, app):
    with app.app_context():
        db = get_db()
        image_id = db.execute(
            """
            INSERT INTO image_library (
                name, file_name, source, source_url, data_base64, mime_type, file_size,
                thumb_media_id, thumb_media_id_expires_at, enabled, description, tags, category, ai_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '', NULL, ?, '', ?::jsonb, '', '{}'::jsonb)
            RETURNING id
            """,
            ("", "poster.png", "url", "https://example.com/raw-big-image.png", "", "image/png", 0, True, json.dumps(["课程介绍", "朋友圈", "海报", "第四个标签"], ensure_ascii=False)),
        ).fetchone()["id"]
        mini_id = db.execute(
            """
            INSERT INTO miniprogram_library (
                name, appid, pagepath, title, thumb_image_url, thumb_image_base64,
                thumb_image_id, thumb_media_id, thumb_media_id_expires_at, enabled
            ) VALUES (?, ?, ?, ?, '', '', NULL, '', NULL, ?)
            RETURNING id
            """,
            ("mini", "wx-mini", "pages/index", "", True),
        ).fetchone()["id"]
        pdf_id = db.execute(
            """
            INSERT INTO attachment_library (
                name, file_name, mime_type, file_size, data_base64, media_id,
                media_id_expires_at, enabled, description, tags
            ) VALUES (?, ?, ?, ?, '', '', NULL, ?, '', ?::jsonb)
            RETURNING id
            """,
            ("", "阅读资料.pdf", "application/pdf", 0, True, json.dumps(["PDF"], ensure_ascii=False)),
        ).fetchone()["id"]
        db.commit()

    image = client.get("/api/sidebar/v2/materials", query_string={"type": "image"}).get_json()["materials"][0]
    mini = client.get("/api/sidebar/v2/materials", query_string={"type": "mini"}).get_json()["materials"][0]
    pdf = client.get("/api/sidebar/v2/materials", query_string={"type": "pdf"}).get_json()["materials"][0]

    assert image == {
        "id": image_id,
        "type": "image",
        "title": "poster.png",
        "thumbnail_label": "图",
        "thumbnail_url": f"/api/sidebar/v2/materials/image/{image_id}/thumbnail",
        "tags": ["课程介绍", "朋友圈", "海报"],
        "enabled": True,
    }
    assert mini == {"id": mini_id, "type": "mini", "title": "mini", "thumbnail_label": "小", "thumbnail_url": "", "tags": [], "enabled": True}
    assert pdf == {"id": pdf_id, "type": "pdf", "title": "阅读资料.pdf", "thumbnail_label": "PDF", "thumbnail_url": "", "tags": ["PDF"], "enabled": True}


def test_sidebar_v2_material_titles_have_safe_fallbacks(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO image_library (
                name, file_name, source, source_url, data_base64, mime_type, file_size,
                thumb_media_id, thumb_media_id_expires_at, enabled, description, tags, category, ai_metadata
            ) VALUES ('', '', 'upload', '', '', 'image/png', 0, '', NULL, TRUE, '', '[]'::jsonb, '', '{}'::jsonb)
            """
        )
        db.execute(
            """
            INSERT INTO miniprogram_library (
                name, appid, pagepath, title, thumb_image_url, thumb_image_base64,
                thumb_image_id, thumb_media_id, thumb_media_id_expires_at, enabled
            ) VALUES ('', 'wx-mini', 'pages/index', '', '', '', NULL, '', NULL, TRUE)
            """
        )
        db.execute(
            """
            INSERT INTO attachment_library (
                name, file_name, mime_type, file_size, data_base64, media_id,
                media_id_expires_at, enabled, description, tags
            ) VALUES ('', '', 'application/pdf', 0, '', '', NULL, TRUE, '', '[]'::jsonb)
            """
        )
        db.commit()

    image = client.get("/api/sidebar/v2/materials", query_string={"type": "image"}).get_json()["materials"][0]
    mini = client.get("/api/sidebar/v2/materials", query_string={"type": "mini"}).get_json()["materials"][0]
    pdf = client.get("/api/sidebar/v2/materials", query_string={"type": "pdf"}).get_json()["materials"][0]

    assert image["title"] == "未命名图片素材"
    assert mini["title"] == "未命名小程序素材"
    assert pdf["title"] == "未命名 PDF 素材"


def test_sidebar_v2_image_material_thumbnail_returns_real_image(client, app):
    from wecom_ability_service.domains import image_library

    with app.app_context():
        item = image_library.create_image_from_base64(
            data_base64=_TINY_PNG_B64,
            file_name="tiny.png",
            mime_type="image/png",
            name="真实图片",
        )

    response = client.get(f"/api/sidebar/v2/materials/image/{item['id']}/thumbnail")

    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.data == _TINY_PNG_BYTES
    assert response.headers["Cache-Control"] == "private, max-age=86400"


def test_sidebar_v2_image_material_thumbnail_errors_are_json(client, app):
    response = client.get("/api/sidebar/v2/materials/image/999999/thumbnail")

    assert response.status_code == 404
    assert response.content_type.startswith("application/json")
    assert response.get_json()["ok"] is False

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO image_library (
                name, file_name, source, source_url, data_base64, mime_type, file_size,
                thumb_media_id, thumb_media_id_expires_at, enabled, description, tags, category, ai_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '', NULL, ?, '', ?, '', ?)
            """,
            ("坏图", "bad.png", "base64", "", "not-valid-base64!", "image/png", 0, True, "[]", "{}"),
        )
        image_id = db.execute("SELECT id FROM image_library WHERE file_name = ?", ("bad.png",)).fetchone()["id"]
        db.commit()

    bad_response = client.get(f"/api/sidebar/v2/materials/image/{image_id}/thumbnail")

    assert bad_response.status_code == 400
    assert bad_response.content_type.startswith("application/json")
    assert bad_response.get_json()["error"] == "invalid image data"


def test_sidebar_v2_products_and_orders_use_existing_wechat_pay_records(client, app):
    with app.app_context():
        _seed_contact()
        db = get_db()
        person_id = db.execute(
            "INSERT INTO people (mobile) VALUES (?) RETURNING id",
            ("13800138000",),
        ).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (external_userid, person_id, first_owner_userid, last_owner_userid)
            VALUES (?, ?, ?, ?)
            """,
            ("wm_sidebar_v2", person_id, "owner_current", "owner_current"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("corp_sidebar", "wm_sidebar_v2", "union_sidebar_v2", "openid_sidebar_v2", "owner_current", "月朗"),
        )
        db.execute(
            """
            INSERT INTO wechat_pay_products (
                product_code, name, amount_total, currency, status, enabled, cta_text, require_mobile
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "prd_sidebar_active",
                "暑期阅读提升营 · 4 周",
                39900,
                "CNY",
                "active",
                True,
                "立即报名",
                False,
                "prd_sidebar_draft",
                "草稿商品",
                19900,
                "CNY",
                "draft",
                False,
                "立即报名",
                False,
            ),
        )
        db.execute(
            """
            INSERT INTO wechat_pay_orders (
                out_trade_no, product_code, product_name, amount_total, currency,
                payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                transaction_id, paid_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
            """,
            (
                "WXP_SIDE_001",
                "prd_sidebar_active",
                "暑期阅读提升营 · 4 周",
                39900,
                "CNY",
                "openid_sidebar_v2",
                "",
                "",
                "13800138001",
                "paid",
                "SUCCESS",
                "4200003132202605227627324115",
                "2026-05-20 06:22:00+00",
                "2026-05-20 06:20:00+00",
            ),
        )
        order_id = db.execute(
            "SELECT id FROM wechat_pay_orders WHERE out_trade_no = ?",
            ("WXP_SIDE_001",),
        ).fetchone()["id"]
        db.commit()

    products_response = client.get(
        "/api/sidebar/v2/products",
        query_string={"external_userid": "wm_sidebar_v2", "owner_userid": "owner_current", "bind_by_userid": "sales_01"},
    )
    orders_response = client.get(
        "/api/sidebar/v2/orders",
        query_string={"external_userid": "wm_sidebar_v2", "owner_userid": "owner_current"},
    )

    assert products_response.status_code == 200
    assert orders_response.status_code == 200
    products_payload = products_response.get_json()
    product = products_payload["products"][0]
    assert product["id"] == "prd_sidebar_active"
    assert product["title"] == "暑期阅读提升营 · 4 周"
    assert product["price_label"] == "¥399"
    assert product["product_url"].startswith("/p/prd_sidebar_active?ctx=")
    assert product["checkout_url"].startswith("/pay/prd_sidebar_active?ctx=")
    assert "wm_sidebar_v2" not in product["product_url"]
    token = product["product_url"].split("ctx=", 1)[1]
    token_payload = load_sidebar_product_context_token(token)
    assert token_payload["ok"] is True
    assert token_payload["context"]["external_userid"] == "wm_sidebar_v2"
    assert token_payload["context"]["owner_userid"] == "owner_current"
    assert token_payload["context"]["bind_by_userid"] == "sales_01"
    assert products_payload["diagnostics"]["context_status"] == "signed"

    orders_payload = orders_response.get_json()
    assert orders_payload["orders"] == [
        {
            "id": "WXP_SIDE_001",
            "order_id": str(order_id),
            "title": "暑期阅读提升营 · 4 周",
            "amount_label": "¥399",
            "status_label": "已支付",
            "paid_at": "2026-05-20 14:22",
            "detail_url": f"/admin/wechat-pay/transactions/{order_id}",
        }
    ]
    assert orders_payload["customer"]["external_userid"] == "wm_sidebar_v2"
    assert orders_payload["diagnostics"]["paid_order_mobile_binding"]["status"] in {"already_bound", "no_single_candidate"}


def test_sidebar_v2_workbench_binds_unbound_mobile_from_paid_wechat_pay_order(client, app):
    with app.app_context():
        _seed_contact("wm_pay_unbound")
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("corp_sidebar", "wm_pay_unbound", "union_pay_unbound", "openid_pay_unbound", "owner_current", "月朗"),
        )
        db.execute(
            """
            INSERT INTO wechat_pay_orders (
                out_trade_no, product_code, product_name, amount_total, currency,
                payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                transaction_id, paid_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
            """,
            (
                "WXP_BIND_FROM_ORDER",
                "prd_sidebar_active",
                "黄小璨首月体验",
                990,
                "CNY",
                "openid_pay_unbound",
                "",
                "",
                "13166662677",
                "paid",
                "SUCCESS",
                "4200003053202605243919108042",
                "2026-05-24 09:58:40+00",
                "2026-05-24 09:58:30+00",
            ),
        )
        db.commit()

    response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": "wm_pay_unbound"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["customer"]["is_bound"] is True
    assert payload["customer"]["mobile"] == "13166662677"
    assert payload["diagnostics"]["paid_order_mobile_binding"]["status"] == "read_overlay"

    status = client.get(
        "/api/sidebar/contact-binding-status",
        query_string={"external_userid": "wm_pay_unbound"},
    ).get_json()
    assert status["is_bound"] is False
    assert status["mobile"] == ""

    with app.app_context():
        binding_count = get_db().execute(
            "SELECT COUNT(*) AS total FROM external_contact_bindings WHERE external_userid = ?",
            ("wm_pay_unbound",),
        ).fetchone()["total"]
        assert binding_count == 0


def test_sidebar_v2_workbench_backfills_orphan_questionnaire_submissions_from_paid_order(client, app):
    with app.app_context():
        _seed_contact("wm_pay_questionnaire_orphan")
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "corp_sidebar",
                "wm_pay_questionnaire_orphan",
                "union_pay_questionnaire_orphan",
                "openid_pay_questionnaire_orphan",
                "owner_current",
                "月朗",
            ),
        )
        db.execute(
            """
            INSERT INTO wechat_pay_orders (
                out_trade_no, product_code, product_name, amount_total, currency,
                payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                transaction_id, paid_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
            """,
            (
                "WXP_BIND_ORPHAN_QUESTIONNAIRE",
                "prd_sidebar_active",
                "黄小璨首月体验",
                990,
                "CNY",
                "openid_pay_questionnaire_orphan",
                "",
                "",
                "13166662679",
                "paid",
                "SUCCESS",
                "4200003053202606043919108042",
                "2026-06-04 05:58:40+00",
                "2026-06-04 05:58:30+00",
            ),
        )
        questionnaire_id = db.execute(
            """
            INSERT INTO questionnaires (slug, name, title)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            ("orphan-binding-v1", "孤儿提交补偿问卷", "孤儿提交补偿问卷"),
        ).fetchone()["id"]
        submission_id = db.execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, external_userid, follow_user_userid, matched_by,
                mobile_snapshot, submitted_at
            ) VALUES (?, '', '', '', ?, ?::timestamptz)
            RETURNING id
            """,
            (questionnaire_id, "131 6666 2679", "2026-06-04 05:00:21+00"),
        ).fetchone()["id"]
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_texts_snapshot, text_value
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                1,
                "textarea",
                "主要需求",
                json.dumps([], ensure_ascii=False),
                "想了解首月体验",
            ),
        )
        db.commit()

    workbench = client.get(
        "/api/sidebar/v2/workbench",
        query_string={"external_userid": "wm_pay_questionnaire_orphan"},
    )
    assert workbench.status_code == 200
    assert workbench.get_json()["customer"]["is_bound"] is True
    assert workbench.get_json()["customer"]["mobile"] == "13166662679"

    questionnaires = client.get(
        "/api/sidebar/v2/questionnaires",
        query_string={"external_userid": "wm_pay_questionnaire_orphan"},
    )
    assert questionnaires.status_code == 200
    questionnaire = questionnaires.get_json()["questionnaires"][0]
    assert questionnaire["title"] == "孤儿提交补偿问卷"
    assert questionnaire["answers"] == [{"question": "主要需求", "answer": "想了解首月体验"}]

    with app.app_context():
        row = get_db().execute(
            """
            SELECT external_userid, follow_user_userid, matched_by
            FROM questionnaire_submissions
            WHERE id = ?
            """,
            (submission_id,),
        ).fetchone()
        assert dict(row) == {
            "external_userid": "",
            "follow_user_userid": "",
            "matched_by": "",
        }


def test_sidebar_v2_order_mobile_binding_skips_ambiguous_paid_order_mobiles(client, app):
    with app.app_context():
        _seed_contact("wm_pay_ambiguous")
        db = get_db()
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("corp_sidebar", "wm_pay_ambiguous", "union_pay_ambiguous", "openid_pay_ambiguous", "owner_current", "月朗"),
        )
        db.executemany(
            """
            INSERT INTO wechat_pay_orders (
                out_trade_no, product_code, product_name, amount_total, currency,
                payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                transaction_id, paid_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
            """,
            [
                (
                    "WXP_AMBIGUOUS_1",
                    "prd_sidebar_active",
                    "黄小璨首月体验",
                    990,
                    "CNY",
                    "openid_pay_ambiguous",
                    "",
                    "",
                    "13166662677",
                    "paid",
                    "SUCCESS",
                    "420000AMBIGUOUS1",
                    "2026-05-24 09:58:40+00",
                    "2026-05-24 09:58:30+00",
                ),
                (
                    "WXP_AMBIGUOUS_2",
                    "prd_sidebar_active",
                    "黄小璨首月体验",
                    990,
                    "CNY",
                    "openid_pay_ambiguous",
                    "",
                    "",
                    "13166662678",
                    "paid",
                    "SUCCESS",
                    "420000AMBIGUOUS2",
                    "2026-05-24 10:58:40+00",
                    "2026-05-24 10:58:30+00",
                ),
            ],
        )
        db.commit()

    response = client.get("/api/sidebar/v2/workbench", query_string={"external_userid": "wm_pay_ambiguous"})

    assert response.status_code == 200
    assert response.get_json()["customer"]["is_bound"] is False
    assert response.get_json()["customer"]["mobile"] == ""
    with app.app_context():
        binding_count = get_db().execute(
            "SELECT COUNT(*) AS total FROM external_contact_bindings WHERE external_userid = ?",
            ("wm_pay_ambiguous",),
        ).fetchone()["total"]
        assert binding_count == 0


def test_sidebar_v2_other_staff_messages_filters_current_user_and_keeps_recent_text_images(client, app):
    with app.app_context():
        _seed_contact()
        db = get_db()
        db.execute(
            "INSERT INTO owner_role_map (userid, display_name, role) VALUES (?, ?, ?), (?, ?, ?)",
            ("staff_other", "张老师", "staff", "owner_current", "当前客服", "staff"),
        )
        rows = []
        for index in range(25):
            rows.append(
                (
                    index + 1,
                    f"msg_other_{index:02d}",
                    "group" if index % 2 else "private",
                    "wm_sidebar_v2",
                    "owner_current",
                    "staff_other",
                    "wm_sidebar_v2",
                    "image" if index == 24 else "text",
                    "" if index == 24 else f"消息{index:02d}",
                    f"2026-05-18 10:{index:02d}:00",
                    json.dumps({"decrypted_message": {"roomid": "room_1" if index % 2 else "", "tolist": ["wm_sidebar_v2"]}}, ensure_ascii=False),
                )
            )
        rows.extend(
            [
                (100, "msg_current", "private", "wm_sidebar_v2", "owner_current", "owner_current", "wm_sidebar_v2", "text", "当前客服消息", "2026-05-18 11:00:00", "{}"),
                (101, "msg_voice", "private", "wm_sidebar_v2", "owner_current", "staff_other", "wm_sidebar_v2", "voice", "voice", "2026-05-18 11:01:00", "{}"),
            ]
        )
        db.executemany(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                msgtype, content, send_time, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        db.execute(
            """
            INSERT INTO group_chats (chat_id, group_name, owner_userid, raw_payload)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (chat_id) DO UPDATE SET group_name = EXCLUDED.group_name
            """,
            ("room_1", "三年级阅读训练营咨询群", "owner_current", "{}"),
        )
        db.commit()

    response = client.get(
        "/api/sidebar/v2/other-staff-messages",
        query_string={"external_userid": "wm_sidebar_v2", "current_userid": "owner_current", "limit": 20},
    )

    messages = response.get_json()["messages"]
    assert len(messages) == 20
    assert messages[0]["content"] == "消息05"
    assert messages[-1]["type"] == "image"
    assert messages[-1]["content"] == "发送了图片"
    assert {item["staff_userid"] for item in messages} == {"staff_other"}
    assert all(item["type"] in {"text", "image"} for item in messages)
    assert any(item["scene"] == "group" and item["scene_label"] == "三年级阅读训练营咨询群" for item in messages)
    assert any(item["scene"] == "private" and item["scene_label"] == "私聊" for item in messages)


def test_sidebar_v2_material_send_uses_private_message_dispatch(client, monkeypatch):
    from wecom_ability_service.domains.sidebar_v2 import service

    captured = {}
    monkeypatch.setattr(service.image_library, "resolve_image_media_id", lambda image_id: f"media_{image_id}")

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "status": "sent", "record_id": 77, "task_ids": [88], "sender_userid": kwargs["sender_userid"]}

    monkeypatch.setattr(service.private_message_dispatch, "_dispatch_private_message_batch", fake_dispatch)

    response = client.post(
        "/api/sidebar/v2/materials/send",
        json={
            "external_userid": "wm_sidebar_v2",
            "owner_userid": "HuangYouCan",
            "type": "image",
            "material_id": 123,
            "operator": "operator_1",
        },
    )

    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["record_id"] == 77
    assert payload["task_ids"] == [88]
    assert captured["target_items"] == [{"external_userid": "wm_sidebar_v2"}]
    assert captured["image_media_ids"] == ["media_123"]
    assert captured["sender_userid"] == "HuangYouCan"
    assert captured["operator_id"] == "operator_1"


def test_sidebar_v2_image_material_send_can_prepare_chat_toolbar_media(client, monkeypatch):
    from wecom_ability_service.domains.sidebar_v2 import service

    monkeypatch.setattr(service.image_library, "resolve_image_media_id", lambda image_id: f"media_{image_id}")

    def fail_dispatch(**_kwargs):
        raise AssertionError("chat toolbar mode should not create background dispatch")

    monkeypatch.setattr(service.private_message_dispatch, "_dispatch_private_message_batch", fail_dispatch)

    response = client.post(
        "/api/sidebar/v2/materials/send",
        json={
            "external_userid": "wm_sidebar_v2",
            "owner_userid": "HuangYouCan",
            "type": "image",
            "material_id": 123,
            "operator": "operator_1",
            "delivery_mode": "chat_toolbar",
        },
    )

    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["delivery_mode"] == "chat_toolbar"
    assert payload["media_id"] == "media_123"
    assert payload["record_id"] == 0
    assert payload["task_ids"] == []


@pytest.mark.parametrize(
    ("material_type", "expected_key"),
    [("mini", "miniprogram_library_ids"), ("pdf", "attachment_library_ids")],
)
def test_sidebar_v2_non_image_material_send_uses_dispatch(client, monkeypatch, material_type, expected_key):
    from wecom_ability_service.domains.sidebar_v2 import service

    captured = {}

    def fake_dispatch(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "status": "sent", "record_id": 91, "task_ids": [92], "sender_userid": kwargs["sender_userid"]}

    monkeypatch.setattr(service.private_message_dispatch, "_dispatch_private_message_batch", fake_dispatch)

    response = client.post(
        "/api/sidebar/v2/materials/send",
        json={
            "external_userid": "wm_sidebar_v2",
            "owner_userid": "HuangYouCan",
            "type": material_type,
            "material_id": 456,
            "operator": "operator_1",
        },
    )

    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["record_id"] == 91
    assert captured["target_items"] == [{"external_userid": "wm_sidebar_v2"}]
    assert captured[expected_key] == [456]
    assert "image_media_ids" not in captured


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"type": "image", "material_id": 1}, "external_userid is required"),
        ({"external_userid": "wm_sidebar_v2", "type": "image"}, "material_id is required"),
        ({"external_userid": "wm_sidebar_v2", "type": "unknown", "material_id": 1}, "type must be image, mini, or pdf"),
    ],
)
def test_sidebar_v2_material_send_validates_required_inputs(client, payload, error):
    response = client.post("/api/sidebar/v2/materials/send", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": error}
