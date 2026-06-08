from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


def _insert_campaign_member(*, db, campaign_code: str, owner_userid: str, member_id: int) -> int:
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO campaigns (campaign_code, display_name, review_status, run_status, owner_userid)
        VALUES (?, ?, 'approved', 'active', ?)
        RETURNING id
        """,
        (campaign_code, campaign_code, owner_userid),
    )
    campaign_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO campaign_segments (campaign_id, segment_id, segment_code) VALUES (?, ?, ?) RETURNING id",
        (campaign_id, member_id, f"seg-{member_id}"),
    )
    segment_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaign_members (
            campaign_id, campaign_segment_id, segment_id, member_id,
            external_contact_id, status, next_due_at, anchor_date, last_step_sent_at
        )
        VALUES (?, ?, ?, ?, 'wm_reply_scope', 'pending', ?, '2026-05-20', ?)
        RETURNING id
        """,
        (
            campaign_id,
            segment_id,
            member_id,
            member_id,
            datetime.now(timezone.utc).isoformat(),
            (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        ),
    )
    member_row_id = int(cur.fetchone()["id"])
    db.commit()
    return member_row_id


def test_register_member_reply_only_stops_matching_campaign_owner(app):
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import scheduler

    with app.app_context():
        db = get_db()
        zhao_member_id = _insert_campaign_member(
            db=db,
            campaign_code="camp-zhao-reply-scope",
            owner_userid="ZhaoYanFang",
            member_id=101,
        )
        huang_member_id = _insert_campaign_member(
            db=db,
            campaign_code="camp-huang-reply-scope",
            owner_userid="HuangYouCan",
            member_id=102,
        )

        affected = scheduler.register_member_reply(
            external_contact_id="wm_reply_scope",
            owner_userid="HuangYouCan",
        )

        assert affected == 1
        rows = db.execute(
            "SELECT id, status FROM campaign_members WHERE id IN (?, ?) ORDER BY id",
            (zhao_member_id, huang_member_id),
        ).fetchall()
        assert [dict(row) for row in rows] == [
            {"id": zhao_member_id, "status": "pending"},
            {"id": huang_member_id, "status": "replied"},
        ]


def test_has_inbound_since_requires_matching_owner_when_supplied(app):
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns.scheduler import _has_inbound_since

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid,
                sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES (1, 'msg-owner-scope-1', 'private', 'wm_reply_scope',
                    'HuangYouCan', 'wm_reply_scope', 'HuangYouCan', 'text',
                    '我回复了', '2026-05-20 11:00:00', '{}')
            """
        )
        db.commit()

        assert _has_inbound_since(
            external_userid="wm_reply_scope",
            since_iso="2026-05-20 10:30:00",
            owner_userid="HuangYouCan",
        )
        assert not _has_inbound_since(
            external_userid="wm_reply_scope",
            since_iso="2026-05-20 10:30:00",
            owner_userid="ZhaoYanFang",
        )
