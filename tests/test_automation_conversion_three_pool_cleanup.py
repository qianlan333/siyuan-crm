from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.db.helpers import _sqlite_table_columns, _sqlite_table_sql
from wecom_ability_service.domains.automation_conversion import (
    get_conversion_dashboard_payload,
    save_sop_v1_pool_config,
)


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "automation-conversion-cleanup.sqlite3"
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


def _seed_contact(app, *, external_userid: str, mobile: str = "", owner_userid: str = "sales_01") -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, external_userid, owner_userid),
        )
        if mobile:
            person_id = db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM people").fetchone()["next_id"]
            db.execute(
                """
                INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (person_id, mobile, external_userid),
            )
        db.commit()


def _seed_member(
    app,
    *,
    external_contact_id: str,
    phone: str,
    current_pool: str,
    questionnaire_status: str,
    follow_type: str = "normal",
) -> None:
    audience_code = "converted" if current_pool == "converted" else "operating" if questionnaire_status == "submitted" else "pending_questionnaire"
    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                questionnaire_status, decision_source, source_type, last_active_pool,
                current_audience_code, current_audience_entered_at, joined_at, created_at, updated_at
            )
            VALUES (?, ?, 'sales_01', 1, ?, ?, ?, 'system', 'manual', '', ?, '2026-04-08 08:00:00', '2026-04-08 08:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (external_contact_id, phone, current_pool, follow_type, questionnaire_status, audience_code),
        ).fetchone()
        db.execute(
            """
            INSERT INTO automation_member_audience_entry (
                member_id, audience_code, entered_at, exited_at, is_current,
                entry_source, entry_reason, source_snapshot_json, created_at, updated_at
            )
            VALUES (?, ?, '2026-04-08 08:00:00', '', 1, 'test', 'seed', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (row["id"], audience_code),
        )
        db.commit()


def test_automation_member_schema_drops_activation_status_and_normalizes_sop_pool_keys(app):
    with app.app_context():
        member_columns = _sqlite_table_columns(get_db(), "automation_member")
        assert "activation_status" not in member_columns

        sop_sql = _sqlite_table_sql(get_db(), "automation_sop_pool_config")
        assert "pending_questionnaire" in sop_sql
        assert "operating" in sop_sql
        assert "converted" in sop_sql
        assert "new_user" not in sop_sql


def test_dashboard_payload_uses_three_audiences_and_no_activation_fields(app):
    _seed_contact(app, external_userid="wm_cleanup_pending_001", mobile="13800003111")
    _seed_contact(app, external_userid="wm_cleanup_operating_001", mobile="13800003112")
    _seed_contact(app, external_userid="wm_cleanup_converted_001", mobile="13800003113")
    _seed_member(app, external_contact_id="wm_cleanup_pending_001", phone="13800003111", current_pool="pending_questionnaire", questionnaire_status="pending")
    _seed_member(app, external_contact_id="wm_cleanup_operating_001", phone="13800003112", current_pool="operating", questionnaire_status="submitted")
    _seed_member(app, external_contact_id="wm_cleanup_converted_001", phone="13800003113", current_pool="converted", questionnaire_status="submitted")

    with app.app_context():
        payload = get_conversion_dashboard_payload()

    audience = payload["audience_overview"]
    assert audience["pending_questionnaire_count"] == 1
    assert audience["operating_count"] == 1
    assert audience["converted_count"] == 1

    flattened_items = [
        item
        for group in payload["audience_member_details"]["groups"]
        for item in group.get("items") or []
    ]
    assert flattened_items
    assert all("activation_status" not in item for item in flattened_items)
    assert all("activation_status_label" not in item for item in flattened_items)


def test_save_sop_v1_pool_config_accepts_legacy_alias_but_persists_three_pool_model(app):
    with app.app_context():
        saved = save_sop_v1_pool_config(pool_key="new_user", enabled=True, send_time="09:00", timezone="Asia/Shanghai")
    assert saved["pool_key"] == "pending_questionnaire"
