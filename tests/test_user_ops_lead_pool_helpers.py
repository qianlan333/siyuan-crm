from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import (
    upsert_user_ops_huangxiaocan_activation_source,
    upsert_user_ops_lead_pool_member,
)


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "user-ops-lead-pool.sqlite3"
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
        }
    )
    with app.app_context():
        init_db()
    yield app


def test_user_ops_lead_pool_current_allows_mobile_only_member(app):
    with app.app_context():
        payload = upsert_user_ops_lead_pool_member(
            mobile="17640055576",
            entry_source="student_import",
            operator="tester",
        )
        row = get_db().execute(
            """
            SELECT mobile, external_userid, is_wecom_added, is_mobile_bound, first_entry_source, last_entry_source
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("17640055576",),
        ).fetchone()

    assert payload["action_type"] == "lead_pool_insert"
    assert payload["member"]["mobile"] == "17640055576"
    assert payload["member"]["external_userid"] == ""
    assert row["mobile"] == "17640055576"
    assert row["external_userid"] == ""
    assert bool(row["is_wecom_added"]) is False
    assert bool(row["is_mobile_bound"]) is False
    assert row["first_entry_source"] == "student_import"
    assert row["last_entry_source"] == "student_import"


def test_user_ops_lead_pool_current_allows_external_only_member(app):
    with app.app_context():
        payload = upsert_user_ops_lead_pool_member(
            external_userid="wm_external_only_001",
            customer_name="外部联系人",
            entry_source="sidebar_manual_set_class_term",
            operator="tester",
        )
        row = get_db().execute(
            """
            SELECT mobile, external_userid, customer_name, is_mobile_bound
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
            """,
            ("wm_external_only_001",),
        ).fetchone()

    assert payload["action_type"] == "lead_pool_insert"
    assert payload["member"]["mobile"] == ""
    assert payload["member"]["external_userid"] == "wm_external_only_001"
    assert row["mobile"] == ""
    assert row["external_userid"] == "wm_external_only_001"
    assert row["customer_name"] == "外部联系人"
    assert bool(row["is_mobile_bound"]) is False


def test_user_ops_lead_pool_upsert_writes_history(app):
    with app.app_context():
        upsert_user_ops_lead_pool_member(
            mobile="17640055577",
            class_term_no=5,
            class_term_label="5期",
            entry_source="student_import",
            operator="tester",
        )
        row = get_db().execute(
            """
            SELECT action_type, source_type, operator, before_json, after_json
            FROM user_ops_lead_pool_history
            WHERE mobile = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("17640055577",),
        ).fetchone()

    assert row["action_type"] == "lead_pool_insert"
    assert row["source_type"] == "student_import"
    assert row["operator"] == "tester"
    assert row["before_json"] == "{}"
    assert '"class_term_label": "5期"' in row["after_json"]


def test_huangxiaocan_activation_source_patches_existing_member_only(app):
    with app.app_context():
        upsert_user_ops_lead_pool_member(
            mobile="17640055578",
            entry_source="student_import",
            operator="tester",
        )
        matched = upsert_user_ops_huangxiaocan_activation_source(
            mobile="17640055578",
            activation_state="activated",
            import_batch_id="batch-001",
            created_by="tester",
        )
        unmatched = upsert_user_ops_huangxiaocan_activation_source(
            mobile="17640055579",
            activation_state="not_activated",
            import_batch_id="batch-002",
            created_by="tester",
        )
        patched_row = get_db().execute(
            """
            SELECT mobile, huangxiaocan_activation_state
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("17640055578",),
        ).fetchone()
        missing_row = get_db().execute(
            """
            SELECT mobile
            FROM user_ops_lead_pool_current
            WHERE mobile = ?
            """,
            ("17640055579",),
        ).fetchone()
        source_row = get_db().execute(
            """
            SELECT mobile, activation_state
            FROM user_ops_huangxiaocan_activation_source
            WHERE mobile = ?
            """,
            ("17640055579",),
        ).fetchone()

    assert matched["matched_member"] is True
    assert matched["created_member"] is False
    assert patched_row["huangxiaocan_activation_state"] == "activated"
    assert unmatched["matched_member"] is False
    assert unmatched["created_member"] is False
    assert missing_row is None
    assert source_row["mobile"] == "17640055579"
    assert source_row["activation_state"] == "not_activated"
