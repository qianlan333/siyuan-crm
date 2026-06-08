from __future__ import annotations

from aicrm_next.ai_assist.external_campaigns import create_external_campaigns
from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import automation_member_backfill_service


def _seed_sidebar_binding(
    *,
    external_userid: str = "wm-campaign-ready",
    mobile: str = "13800138000",
    person_id: int = 1001,
    owner_userid: str = "HuangYouCan",
) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
        VALUES (?, ?, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE SET mobile = excluded.mobile
        """,
        (person_id, mobile),
    )
    db.execute(
        """
        INSERT INTO external_contact_bindings (
            external_userid, person_id, first_owner_userid, last_owner_userid, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (external_userid) DO UPDATE
        SET person_id = excluded.person_id,
            last_owner_userid = excluded.last_owner_userid,
            updated_at = CURRENT_TIMESTAMP
        """,
        (external_userid, person_id, owner_userid, owner_userid),
    )
    db.execute(
        """
        INSERT INTO contacts (external_userid, owner_userid, customer_name, remark)
        VALUES (?, ?, '测试客户', '')
        ON CONFLICT (external_userid) DO UPDATE SET owner_userid = excluded.owner_userid
        """,
        (external_userid, owner_userid),
    )
    db.execute(
        """
        INSERT INTO wecom_external_contact_follow_users (
            corp_id, external_userid, user_id, relation_status, is_primary, raw_follow_user
        )
        VALUES ('ww-test', ?, ?, 'active', true, '{}')
        ON CONFLICT (corp_id, external_userid, user_id) DO UPDATE
        SET relation_status = 'active', is_primary = true
        """,
        (external_userid, owner_userid),
    )
    db.commit()


def test_campaign_member_backfill_inserts_sidebar_bound_user_as_passive_campaign_ready(app) -> None:
    _seed_sidebar_binding()

    result = automation_member_backfill_service.ensure_campaign_member_from_sidebar_binding("wm-campaign-ready")

    assert result["ok"] is True
    assert result["status"] == "insert"
    assert result["phone"] == "13800138000"
    assert result["owner_staff_id"] == "HuangYouCan"

    row = get_db().execute(
        """
        SELECT external_contact_id, phone, master_customer_id, owner_staff_id,
               in_pool, current_pool, current_audience_code, source_type
        FROM automation_member
        WHERE external_contact_id = ?
        """,
        ("wm-campaign-ready",),
    ).fetchone()
    assert dict(row) == {
        "external_contact_id": "wm-campaign-ready",
        "phone": "13800138000",
        "master_customer_id": 1001,
        "owner_staff_id": "HuangYouCan",
        "in_pool": False,
        "current_pool": "campaign_ready",
        "current_audience_code": "pending_questionnaire",
        "source_type": "sidebar_binding_campaign_backfill",
    }


def test_campaign_member_refresh_fills_missing_fields_without_overwriting_pool_state(app) -> None:
    _seed_sidebar_binding(external_userid="wm-existing", mobile="13900139000", person_id=1002)
    db = get_db()
    db.execute(
        """
        INSERT INTO automation_member (
            external_contact_id, phone, master_customer_id, owner_staff_id,
            in_pool, current_pool, questionnaire_status, decision_source,
            source_type, current_audience_code
        )
        VALUES (?, '', NULL, '', true, 'operating', 'pending', 'manual', 'manual', 'operating')
        """,
        ("wm-existing",),
    )
    db.commit()

    result = automation_member_backfill_service.refresh_campaign_members_from_sidebar_bindings(limit=10)

    assert result["ok"] is True
    assert result["status_counts"]["update"] == 1
    row = db.execute(
        """
        SELECT phone, master_customer_id, owner_staff_id, in_pool, current_pool, current_audience_code, source_type
        FROM automation_member
        WHERE external_contact_id = ?
        """,
        ("wm-existing",),
    ).fetchone()
    assert dict(row) == {
        "phone": "13900139000",
        "master_customer_id": 1002,
        "owner_staff_id": "HuangYouCan",
        "in_pool": True,
        "current_pool": "operating",
        "current_audience_code": "operating",
        "source_type": "manual",
    }


def test_external_campaign_preview_can_dry_run_auto_backfill_without_writing_member(app) -> None:
    _seed_sidebar_binding(external_userid="wm-preview-backfill", mobile="13700137000", person_id=1003)

    result = create_external_campaigns(
        {
            "dry_run": True,
            "auto_backfill_automation_member": True,
            "owner_userid": "HuangYouCan",
            "external_userid": "wm-preview-backfill",
            "scheduled_for": "2099-01-01 10:00",
            "timezone": "Asia/Shanghai",
            "message": "hello",
            "group_code": "preview-auto-backfill",
            "group_label": "preview auto backfill",
            "intent": "preview auto backfill",
        }
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    backfill = result["campaigns"][0]["automation_member_backfill"]
    assert backfill["ok"] is True
    assert backfill["status"] == "insert"
    count = get_db().execute(
        "SELECT COUNT(*) AS total FROM automation_member WHERE external_contact_id = ?",
        ("wm-preview-backfill",),
    ).fetchone()["total"]
    assert count == 0
