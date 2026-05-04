from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.customer_center import repo as customer_repo
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "SIDEBAR_PERSON_DETAIL_URL_TEMPLATE": "https://www.youcangogogo.com/person/{person_id}",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def seed_customer_fixture(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            ("sales_01", "顾问一号", "sales", 1, "sales_02", "顾问二号", "sales", 1),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_customer_001",
                "客户甲",
                "sales_01",
                "重点客户",
                "客户甲描述",
                "2026-03-24 10:00:00",
                "wm_customer_002",
                "客户乙",
                "sales_02",
                "未绑定客户",
                "客户乙描述",
                "2026-03-24 09:00:00",
            ),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("13900000001", "tp_001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13900000001",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_customer_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_customer_001",
                "union-001",
                "openid-001",
                "sales_01",
                "客户甲",
                "active",
                "{}",
                "ww-test",
                "wm_customer_002",
                "union-002",
                "openid-002",
                "sales_02",
                "客户乙",
                "active",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-test",
                "wm_customer_001",
                "sales_01",
                "active",
                1,
                "备注甲",
                "描述甲",
                "{}",
                "ww-test",
                "wm_customer_002",
                "sales_02",
                "active",
                1,
                "备注乙",
                "描述乙",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
            VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)
            """,
            (
                "wm_customer_001",
                "sales_01",
                "tag-vip",
                "高意向",
                "2026-03-24 10:00:00",
                "wm_customer_002",
                "sales_02",
                "tag-cold",
                "待跟进",
                "2026-03-24 09:30:00",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            ("wm_customer_001", "signed_999", "已报名999", "客户甲", "sales_01", "13900000001", "sales_01", "success", "", "{}"),
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "msg-001",
                "wm_customer_001",
                "sales_01",
                "sales_01",
                "wm_customer_001",
                "text",
                "你好",
                "2026-03-24 11:00:00",
                "{}",
                2,
                "msg-002",
                "wm_customer_002",
                "sales_02",
                "sales_02",
                "wm_customer_002",
                "text",
                "稍后联系",
                "2026-03-24 12:00:00",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT INTO customer_marketing_state_current (
                person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
                eligible_for_conversion, lifecycle_status, last_activation_at, last_conversion_marked_at,
                last_message_at, last_batch_id, last_batch_status, last_batch_window_start, last_batch_window_end,
                last_trigger_message_at, entered_at, exited_at, exit_reason, state_payload_json, created_at, updated_at
            )
            VALUES (?, ?, 'signup_conversion_v1', 'active', 'activated', 1, 0, 1, 'active', ?, '', ?, NULL, '', '', '', ?, ?, '', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                person_id,
                "wm_customer_001",
                "2026-03-24 09:30:00",
                "2026-03-24 11:00:00",
                "2026-03-24 11:00:00",
                "2026-03-24 09:30:00",
            ),
        )
        db.execute(
            """
            INSERT INTO customer_value_segment_current (
                external_userid, segment, segment_rank, score, scoring_version, computed_reason, submission_id,
                matched_question_ids_json, source_payload_json, evaluated_at, computed_at, created_at, updated_at
            )
            VALUES (?, 'core', 2, 3, 'signup_conversion_question_hits_v1', 'seed', NULL, '[]', '{}', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "wm_customer_001",
                "2026-03-24 10:30:00",
                "2026-03-24 10:30:00",
            ),
        )
        db.execute(
            """
            INSERT INTO message_batches (
                id, batch_key, window_start, window_end, status, message_count, created_at
            )
            VALUES (9001, 'seed-batch-9001', '2026-03-24 10:35:00', '2026-03-24 10:45:00', 'acked', 1, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO conversion_dispatch_log (
                automation_key, batch_id, external_userid, dispatch_status, dispatch_channel,
                dispatch_payload_json, dispatch_note, dispatched_at, acked_at, created_at, updated_at
            )
            VALUES ('signup_conversion_v1', 9001, ?, 'sent', 'text_message', '{}', 'seed dispatch', ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_customer_001", "2026-03-24 10:40:00"),
        )
        db.commit()


def test_customers_list_returns_aggregated_results(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"limit": 10, "offset": 0})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["count"] == 2
    assert len(payload["customers"]) == 2
    assert payload["filters"] == {
        "owner_userid": "",
        "tag": "",
        "status": "",
        "is_bound": "",
        "marketing_segment": "",
        "marketing_main_stage": "",
        "marketing_sub_stage": "",
        "eligible_for_conversion": "",
        "mobile": "",
        "keyword": "",
        "limit": "10",
        "offset": "0",
    }
    assert {item["external_userid"] for item in payload["customers"]} == {"wm_customer_001", "wm_customer_002"}


def test_customers_list_filters_by_owner_userid(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"owner_userid": "sales_01"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["owner_userid"] == "sales_01"


def test_customers_list_filters_by_tag(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"tag": "高意向"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["external_userid"] == "wm_customer_001"
    assert payload["filters"]["tag"] == "高意向"


def test_customers_list_filters_by_is_bound(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"is_bound": "false"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["external_userid"] == "wm_customer_002"
    assert payload["customers"][0]["is_bound"] is False


def test_customers_list_filters_by_marketing_segment_stage_and_eligibility(client, app):
    seed_customer_fixture(app)

    response = client.get(
        "/api/customers",
        query_string={
            "marketing_segment": "unknown",
            "marketing_main_stage": "converted",
            "marketing_sub_stage": "enrolled",
            "eligible_for_conversion": "false",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["external_userid"] == "wm_customer_001"
    assert payload["filters"]["marketing_segment"] == "unknown"
    assert payload["filters"]["marketing_main_stage"] == "converted"
    assert payload["filters"]["marketing_sub_stage"] == "enrolled"
    assert payload["filters"]["eligible_for_conversion"] == "false"


def test_customers_list_filters_by_marketing_unknown_and_ineligible(client, app):
    seed_customer_fixture(app)

    response = client.get(
        "/api/customers",
        query_string={
            "marketing_segment": "unknown",
            "marketing_main_stage": "pool",
            "marketing_sub_stage": "silent",
            "eligible_for_conversion": "false",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["customers"][0]["external_userid"] == "wm_customer_002"


def test_customers_list_rejects_invalid_eligible_for_conversion_filter(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers", query_string={"eligible_for_conversion": "maybe"})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "eligible_for_conversion must be one of true/false/1/0"


def test_customers_list_uses_database_pagination_for_common_filters(client, app, monkeypatch):
    seed_customer_fixture(app)
    with app.app_context():
        db = get_db()
        for index in range(3, 28):
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
                VALUES (?, ?, ?, '', '', ?)
                """,
                (
                    f"wm_customer_{index:03d}",
                    f"客户{index:03d}",
                    "sales_01" if index % 2 else "sales_02",
                    f"2026-03-24 08:{index:02d}:00",
                ),
            )
        db.commit()

    def _fail_marketing_profile(_external_userid):
        raise AssertionError("common customer list filters must not build marketing profile for every customer")

    monkeypatch.setattr(
        "wecom_ability_service.customer_center.service.get_customer_marketing_profile",
        _fail_marketing_profile,
    )

    response = client.get("/api/customers", query_string={"keyword": "客户", "limit": 5, "offset": 0})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 27
    assert len(payload["customers"]) == 5


def test_customer_list_scope_sql_casts_timestamp_sort_columns_for_postgres(monkeypatch):
    # _customer_list_scope_sql now routes its dialect choice through the
    # shared db.dialect helper, so the patch needs to land on the helper's
    # backend probe rather than the repo's local re-export only.
    from wecom_ability_service.db import dialect as db_dialect

    monkeypatch.setattr(customer_repo, "get_db_backend", lambda: "postgres")
    monkeypatch.setattr(db_dialect, "get_db_backend", lambda: "postgres")

    sql = customer_repo._customer_list_scope_sql()

    assert "NULLIF(class_status.updated_at::text, '')" in sql
    assert "NULLIF(contact.updated_at::text, '')" in sql
    assert "NULLIF(binding.updated_at::text, '')" in sql
    assert "NULLIF(class_status.updated_at, '')" not in sql
    assert "NULLIF(contact.updated_at, '')" not in sql
    assert "NULLIF(binding.updated_at, '')" not in sql


def test_customer_detail_returns_unified_dto(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers/wm_customer_001")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    customer = payload["customer"]
    assert customer["external_userid"] == "wm_customer_001"
    assert customer["customer_name"] == "客户甲"
    assert customer["owner_userid"] == "sales_01"
    assert customer["mobile"] == "13900000001"
    assert customer["binding_status"] == "bound"
    assert customer["follow_user_userids"] == ["sales_01"]
    assert customer["class_user_status"]["signup_status"] == "signed_999"
    assert customer["marketing_profile"]["marketing_state"]["marketing_phase"] == "exited_signup_success"
    assert customer["marketing_summary"] == {
        "main_stage": "converted",
        "sub_stage": "enrolled",
        "segment": "unknown",
        "hit_count": 3,
        "eligible_for_conversion": False,
        "last_activation_at": "2026-03-24 09:30:00",
        "last_conversion_marked_at": "",
        "last_dispatch_at": "2026-03-24 10:40:00",
    }
    assert customer["last_message_at"] == "2026-03-24 11:00:00"
    assert customer["last_touch_at"] == "2026-03-24 11:00:00"


def test_customer_detail_returns_stable_empty_marketing_summary_when_current_rows_missing(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/customers/wm_customer_002")

    assert response.status_code == 200
    customer = response.get_json()["customer"]
    assert customer["external_userid"] == "wm_customer_002"
    assert customer["marketing_summary"] == {
        "main_stage": "pool",
        "sub_stage": "silent",
        "segment": "unknown",
        "hit_count": 0,
        "eligible_for_conversion": False,
        "last_activation_at": "",
        "last_conversion_marked_at": "",
        "last_dispatch_at": "",
    }


def test_legacy_contacts_api_smoke_still_works(client, app):
    seed_customer_fixture(app)

    response = client.get("/api/contacts", query_string={"sync": "0", "owner_userid": "sales_01"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "contacts" in payload
