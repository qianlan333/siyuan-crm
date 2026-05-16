"""用户激活漏斗看板 — 快照刷新单元测试.

纯函数路径不依赖 DB; 完整刷新路径 mock 黄小璨 MySQL 拉取后跑真 PG.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from wecom_ability_service.domains.user_ops import hxc_dashboard_snapshot_service as svc
from wecom_ability_service.domains.user_ops.phone_helpers import mask_mobile, phone_match_key


# ── 纯函数 (无 DB 依赖) ──

def test_funnel_state_4_buckets():
    assert svc._funnel_state(user_hit=True, member_hit=True) == svc.FUNNEL_MEMBER_AND_USER
    assert svc._funnel_state(user_hit=False, member_hit=True) == svc.FUNNEL_ONLY_MEMBER
    assert svc._funnel_state(user_hit=True, member_hit=False) == svc.FUNNEL_USER_NO_MEMBER
    assert svc._funnel_state(user_hit=False, member_hit=False) == svc.FUNNEL_INACTIVE


def test_funnel_labels_complete():
    # 4 个枚举值必须都有中文 label, 看板渲染会用
    for state in (
        svc.FUNNEL_MEMBER_AND_USER,
        svc.FUNNEL_ONLY_MEMBER,
        svc.FUNNEL_USER_NO_MEMBER,
        svc.FUNNEL_INACTIVE,
    ):
        assert state in svc.FUNNEL_LABELS
        assert svc.FUNNEL_LABELS[state]


def test_phone_match_key_valid_11_digit():
    assert svc._phone_match_key("13912345678") == "139_5678"


def test_phone_match_key_too_short():
    assert svc._phone_match_key("123") == ""
    assert svc._phone_match_key("") == ""
    assert svc._phone_match_key(None) == ""  # type: ignore[arg-type]


def test_user_ops_phone_helpers_normalize_digits():
    assert phone_match_key("+86 139-1234-5678") == "861_5678"
    assert mask_mobile("139 1234 5678") == "139****5678"
    assert mask_mobile("123") == "123"


def test_to_float_handles_decimal():
    assert svc._to_float(Decimal("3.14")) == 3.14
    assert svc._to_float(2) == 2.0
    assert svc._to_float(None) is None


def test_select_hxc_user_rows_keeps_latest_active_user_for_duplicate_phone():
    rows = [
        {
            "phone": "13912345678",
            "hxc_user_id": "old",
            "last_login_at": dt.datetime(2026, 5, 1, 10, 0),
            "last_msg_at": dt.datetime(2026, 5, 10, 10, 0),
            "hxc_registered_at": dt.datetime(2026, 4, 1, 10, 0),
        },
        {
            "phone": "13912345678",
            "hxc_user_id": "latest-login",
            "last_login_at": dt.datetime(2026, 5, 12, 10, 0),
            "last_msg_at": dt.datetime(2026, 5, 2, 10, 0),
            "hxc_registered_at": dt.datetime(2026, 3, 1, 10, 0),
        },
        {
            "phone": "13800138000",
            "hxc_user_id": "other",
            "last_login_at": None,
            "last_msg_at": dt.datetime(2026, 5, 9, 10, 0),
            "hxc_registered_at": dt.datetime(2026, 3, 1, 10, 0),
        },
    ]

    selected = svc._select_hxc_user_rows(rows)

    assert selected["13912345678"]["hxc_user_id"] == "latest-login"
    assert selected["13800138000"]["hxc_user_id"] == "other"


def test_qids_sql_list_inlines_constants():
    """白名单常量必须 inline 进 SQL, 不能依赖 placeholder."""
    sql = svc._qids_sql_list()
    for qid in svc.HXC_ACTIVATION_QUESTIONNAIRE_IDS:
        assert str(qid) in sql
    assert sql.startswith("(") and sql.endswith(")")


def test_build_crm_sql_no_placeholders():
    """CRM SQL 不能含 placeholder (?/%s/%(name)s) — 全部常量 inline."""
    sql = svc._build_crm_sql()
    assert "?" not in sql
    assert "%s" not in sql
    assert "%(" not in sql
    # 白名单问卷 ID 已 inline
    for qid in svc.HXC_ACTIVATION_QUESTIONNAIRE_IDS:
        assert str(qid) in sql


def test_build_snapshot_row_funnel_only_member():
    """memberships 命中但 users 未命中 → 仅激活未打开."""
    crm = _crm_row(mobile="13912345678", customer_name="张三")
    hxc = {
        "phone": "13912345678",
        "hxc_user_hit": False,
        "hxc_member_hit": True,
        "membership_type": "trial",
        "membership_days_left": 5,
    }
    row = svc._build_snapshot_row(crm, hxc)
    funnel_index = 21  # 见 _INSERT_SQL 字段顺序
    assert row[0] == "13912345678"
    assert row[funnel_index] == svc.FUNNEL_ONLY_MEMBER


def test_build_snapshot_row_funnel_member_and_user():
    crm = _crm_row(mobile="13912345678")
    hxc = {
        "phone": "13912345678",
        "hxc_user_hit": True,
        "hxc_member_hit": True,
        "membership_type": "member",
        "hxc_user_id": "uuid-1",
    }
    row = svc._build_snapshot_row(crm, hxc)
    assert row[21] == svc.FUNNEL_MEMBER_AND_USER


def test_build_snapshot_row_funnel_inactive():
    crm = _crm_row(mobile="13912345678")
    row = svc._build_snapshot_row(crm, {})
    assert row[21] == svc.FUNNEL_INACTIVE


def _crm_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "mobile": "13912345678",
        "external_userid": "",
        "customer_name": "",
        "owner_userid": "",
        "is_wecom_added": None,
        "is_mobile_bound": None,
        "class_term_no": None,
        "class_term_label": "",
        "first_entry_source": "",
        "last_entry_source": "",
        "crm_hxc_state": "",
        "crm_created_at": None,
        "in_lead_pool": True,
        "in_people": False,
        "in_questionnaire": False,
        "questionnaires": "",
        "questionnaire_count": 0,
        "last_questionnaire_at": None,
    }
    base.update(overrides)
    return base


# ── 集成: app fixture (真 PG) + mock 黄小璨 MySQL ──

def test_refresh_writes_snapshot_with_mocked_hxc(app, monkeypatch):
    """seed CRM 三表 → mock 黄小璨 → 跑 refresh → 查 snapshot 命中.

    没有真 MySQL 依赖, 但需要真 PG (app fixture 提供).
    """
    from wecom_ability_service.db import get_db

    with app.app_context():
        # 把 MESSAGE_ACTIVITY_DB_* 配齐, 让 get_message_activity_db_status 返回 configured
        app.config.update(
            MESSAGE_ACTIVITY_DB_HOST="x",
            MESSAGE_ACTIVITY_DB_PORT=3306,
            MESSAGE_ACTIVITY_DB_NAME="x",
            MESSAGE_ACTIVITY_DB_USER="x",
            MESSAGE_ACTIVITY_DB_PASS="x",
        )

        db = get_db()
        # seed CRM lead_pool 1 行 + people 1 行 + 问卷 0 行
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid,
                is_wecom_added, is_mobile_bound,
                huangxiaocan_activation_state,
                class_term_no, class_term_label,
                first_entry_source, last_entry_source
            ) VALUES (
                ?, ?, ?, ?, true, true, 'unknown', NULL, '', 'mobile_bind', 'mobile_bind'
            )
            """,
            ("13912345678", "wm_test_1", "张三", "owner_a"),
        )
        db.execute(
            "INSERT INTO people (mobile, third_party_user_id) VALUES (?, ?)",
            ("13912345678", ""),
        )
        # 第二个手机号只在 people 里 (lead_pool 没收到, 测试并集逻辑)
        db.execute(
            "INSERT INTO people (mobile, third_party_user_id) VALUES (?, ?)",
            ("13800001111", ""),
        )
        db.commit()

        # mock 黄小璨拉取: 13912345678 已激活并打开; 13800001111 仅激活未打开
        def _mock_fetch_hxc_index() -> dict[str, dict[str, Any]]:
            return {
                "13912345678": {
                    "phone": "13912345678",
                    "hxc_user_hit": True,
                    "hxc_member_hit": True,
                    "hxc_user_id": "uuid-1",
                    "hxc_nickname": "张三",
                    "hxc_member_status": "active",
                    "membership_type": "member",
                    "membership_status": "active",
                    "membership_days_left": 21,
                    "conv_chat": 5,
                    "msg_user": 30,
                    "hxc_silent_days": 3,
                    "consult_avg_turn": Decimal("4.5"),
                    "last_login_at": dt.datetime(2026, 5, 10, 12, 0, tzinfo=dt.timezone.utc),
                },
                "13800001111": {
                    "phone": "13800001111",
                    "hxc_user_hit": False,
                    "hxc_member_hit": True,
                    "membership_type": "trial",
                    "membership_status": "active",
                    "membership_days_left": 5,
                },
            }

        monkeypatch.setattr(svc, "_fetch_hxc_index", _mock_fetch_hxc_index)

        result = svc.refresh_hxc_dashboard_snapshot(trigger_source="test")
        assert result["ok"] is True, result
        assert result["row_count"] == 2
        assert result["member_hit"] == 2
        assert result["user_hit"] == 1
        assert result["only_member"] == 1

        # 查 snapshot 表
        rows = db.execute(
            """
            SELECT mobile, funnel_state, membership_type, membership_days_left,
                   msg_user, in_lead_pool, in_people, customer_name
            FROM user_ops_hxc_dashboard_snapshot
            ORDER BY mobile
            """
        ).fetchall()
        snapshot = {row["mobile"]: dict(row) for row in rows}

        assert snapshot["13800001111"]["funnel_state"] == svc.FUNNEL_ONLY_MEMBER
        assert snapshot["13800001111"]["in_lead_pool"] is False
        assert snapshot["13800001111"]["in_people"] is True
        assert snapshot["13800001111"]["membership_type"] == "trial"
        assert snapshot["13800001111"]["membership_days_left"] == 5
        assert snapshot["13800001111"]["msg_user"] == 0

        assert snapshot["13912345678"]["funnel_state"] == svc.FUNNEL_MEMBER_AND_USER
        assert snapshot["13912345678"]["in_lead_pool"] is True
        assert snapshot["13912345678"]["in_people"] is True
        assert snapshot["13912345678"]["customer_name"] == "张三"
        assert snapshot["13912345678"]["msg_user"] == 30

        # meta 表也应该有一行
        meta = svc.get_latest_snapshot_meta()
        assert meta["status"] == "success"
        assert meta["row_count"] == 2
        assert meta["trigger_source"] == "test"


def test_refresh_merges_pool_current_for_external_userid(app, monkeypatch):
    """pool_current 是客户档案主表; 当 lead_pool 没收到某 mobile 时,
    看板必须从 pool_current 拿 external_userid / customer_name / owner_userid.

    回归: 历史版本只查 lead_pool, 导致 100+ 个"已加企微但首次入口不在线索池"
    的客户在看板里 customer_name / external_userid 空白 (issue 2026-05-12).
    """
    from wecom_ability_service.db import get_db

    with app.app_context():
        app.config.update(
            MESSAGE_ACTIVITY_DB_HOST="x",
            MESSAGE_ACTIVITY_DB_PORT=3306,
            MESSAGE_ACTIVITY_DB_NAME="x",
            MESSAGE_ACTIVITY_DB_USER="x",
            MESSAGE_ACTIVITY_DB_PASS="x",
        )

        db = get_db()
        # mobile 只在 pool_current, lead_pool 没收到; 看板必须仍能反查到客户身份
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid,
                current_status, is_wecom_bound, activation_status,
                class_term_no, class_term_label, source_type
            ) VALUES (
                ?, ?, ?, ?, 'active_focus', true, 'activated',
                NULL, '', 'manual'
            )
            """,
            ("13570554128", "wm_only_in_pool_current", "Lucky", "MengYu"),
        )
        # mobile 同时在 pool_current 和 lead_pool, 但 lead_pool 的 customer_name 是空
        # 看板应该取 pool_current 的非空值, 而不是 lead_pool 的空串
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid,
                current_status, is_wecom_bound, activation_status,
                class_term_no, class_term_label, source_type
            ) VALUES (
                ?, ?, ?, ?, 'active_focus', true, 'activated',
                NULL, '', 'manual'
            )
            """,
            ("13800002222", "wm_pool_new", "新名字", "owner_pool"),
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid,
                is_wecom_added, is_mobile_bound,
                huangxiaocan_activation_state,
                class_term_no, class_term_label,
                first_entry_source, last_entry_source
            ) VALUES (?, '', '', '', true, true, 'unknown', NULL, '', 'mobile_bind', 'mobile_bind')
            """,
            ("13800002222",),
        )
        db.commit()

        def _mock_fetch_hxc_index() -> dict[str, dict[str, Any]]:
            return {
                "13570554128": {
                    "phone": "13570554128",
                    "hxc_user_hit": True,
                    "hxc_member_hit": True,
                    "membership_type": "member",
                    "membership_days_left": 30,
                },
                "13800002222": {
                    "phone": "13800002222",
                    "hxc_user_hit": True,
                    "hxc_member_hit": True,
                    "membership_type": "member",
                    "membership_days_left": 10,
                },
            }

        monkeypatch.setattr(svc, "_fetch_hxc_index", _mock_fetch_hxc_index)

        result = svc.refresh_hxc_dashboard_snapshot(trigger_source="test_pool_current")
        assert result["ok"] is True, result
        assert result["row_count"] == 2

        rows = db.execute(
            """
            SELECT mobile, external_userid, customer_name, owner_userid,
                   in_lead_pool, in_people
            FROM user_ops_hxc_dashboard_snapshot
            ORDER BY mobile
            """
        ).fetchall()
        snap = {row["mobile"]: dict(row) for row in rows}

        # Lucky: 只在 pool_current → 客户身份必须从 pool_current 反查到
        assert snap["13570554128"]["external_userid"] == "wm_only_in_pool_current"
        assert snap["13570554128"]["customer_name"] == "Lucky"
        assert snap["13570554128"]["owner_userid"] == "MengYu"
        assert snap["13570554128"]["in_lead_pool"] is False

        # 同 mobile 两表都有: pool_current 优先 (覆盖 lead_pool 的空值)
        assert snap["13800002222"]["external_userid"] == "wm_pool_new"
        assert snap["13800002222"]["customer_name"] == "新名字"
        assert snap["13800002222"]["owner_userid"] == "owner_pool"
        assert snap["13800002222"]["in_lead_pool"] is True


def test_refresh_fails_when_mysql_not_configured(app, monkeypatch):
    with app.app_context():
        # 清空 message_activity 配置
        app.config.update(
            MESSAGE_ACTIVITY_DB_HOST="",
            MESSAGE_ACTIVITY_DB_NAME="",
            MESSAGE_ACTIVITY_DB_USER="",
            MESSAGE_ACTIVITY_DB_PASS="",
        )
        result = svc.refresh_hxc_dashboard_snapshot()
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert "missing_keys" in result
