"""用户激活漏斗看板 — admin 路由 + 视图层测试."""
from __future__ import annotations

import pytest


@pytest.fixture()
def client(app):
    """覆盖顶层 client fixture: 注入 break_glass admin session 绕开 /login 重定向.

    与 tests/test_admin_console_phase4.py 同款做法 — 所有 /admin/* 路径都被
    register_admin_request_guards 守住, 没 admin session 会 302 到 /login,
    导致 page render 测试拿到 302 而不是 200.
    """
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "hxc-dashboard-test-admin"
        sess["admin_session_break_glass_username"] = "hxc-dashboard-test-admin"
    return client


def _seed_snapshot(db, rows):
    for row in rows:
        db.execute(
            """
            INSERT INTO user_ops_hxc_dashboard_snapshot (
                mobile, phone_match_key,
                in_lead_pool, in_people, in_questionnaire,
                customer_name, external_userid, owner_userid,
                funnel_state, hxc_member_hit, hxc_user_hit,
                membership_type, membership_days_left,
                msg_user, hxc_nickname
            ) VALUES (
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?
            )
            """,
            (
                row["mobile"], row.get("phone_match_key", ""),
                row.get("in_lead_pool", False),
                row.get("in_people", False),
                row.get("in_questionnaire", False),
                row.get("customer_name", ""),
                row.get("external_userid", ""),
                row.get("owner_userid", ""),
                row["funnel_state"],
                row.get("hxc_member_hit", False),
                row.get("hxc_user_hit", False),
                row.get("membership_type", ""),
                row.get("membership_days_left"),
                row.get("msg_user", 0),
                row.get("hxc_nickname", ""),
            ),
        )
    db.commit()


def test_view_service_lists_rows_and_masks_mobile(app):
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.user_ops.hxc_dashboard_view_service import (
        list_hxc_dashboard_rows,
    )

    with app.app_context():
        _seed_snapshot(get_db(), [
            {
                "mobile": "13912345678",
                "funnel_state": "member_and_user",
                "in_lead_pool": True,
                "hxc_member_hit": True,
                "hxc_user_hit": True,
                "customer_name": "张三",
                "msg_user": 30,
            },
            {
                "mobile": "13800001111",
                "funnel_state": "only_member",
                "in_people": True,
                "hxc_member_hit": True,
                "membership_type": "trial",
                "membership_days_left": 5,
                "msg_user": 0,
            },
        ])

        rows = list_hxc_dashboard_rows()
        assert len(rows) == 2
        # msg_user 降序 → 30 在前
        assert rows[0]["mobile_masked"] == "139****5678"
        assert rows[0]["funnel_label"] == "已激活并打开"
        assert rows[0]["customer_name"] == "张三"
        assert rows[1]["mobile_masked"] == "138****1111"
        assert rows[1]["funnel_label"] == "仅激活未打开"
        assert rows[1]["membership_type"] == "trial"
        assert rows[1]["membership_days_left"] == 5


def test_summary_returns_funnel_buckets(app):
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.user_ops.hxc_dashboard_view_service import (
        get_dashboard_summary,
    )

    with app.app_context():
        _seed_snapshot(get_db(), [
            {"mobile": "13900000001", "funnel_state": "member_and_user",
             "hxc_member_hit": True, "hxc_user_hit": True, "membership_type": "member"},
            {"mobile": "13900000002", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial"},
            {"mobile": "13900000003", "funnel_state": "only_member",
             "hxc_member_hit": True, "membership_type": "trial"},
            {"mobile": "13900000004", "funnel_state": "inactive"},
        ])
        summary = get_dashboard_summary()
        assert summary["total"] == 4
        assert summary["funnel"]["member_and_user"] == 1
        assert summary["funnel"]["only_member"] == 2
        assert summary["funnel"]["inactive"] == 1
        assert summary["member_hit"] == 3
        assert summary["user_hit"] == 1
        assert summary["member_count"] == 1
        assert summary["trial_count"] == 2


def test_admin_dashboard_page_renders(client, app):
    """GET /admin/hxc-dashboard 应该 200 + 含关键关键字 + 数据 JSON."""
    from wecom_ability_service.db import get_db

    with app.app_context():
        _seed_snapshot(get_db(), [
            {"mobile": "13912345678", "funnel_state": "member_and_user",
             "hxc_member_hit": True, "hxc_user_hit": True,
             "customer_name": "测试客户", "msg_user": 5},
        ])

    resp = client.get("/admin/hxc-dashboard")
    assert resp.status_code == 200, resp.data[:300]
    body = resp.data.decode("utf-8")
    # 页面壳
    assert "用户激活漏斗看板" in body
    assert "漏斗状态汇总" in body
    # nav 已注册
    assert "激活漏斗" in body
    # 数据 JSON 嵌入 (tojson ensure_ascii=True 会把中文转 \uXXXX, 只验 ASCII 字段)
    assert "139****5678" in body


def test_admin_dashboard_has_send_config_link(client, app):
    """漏斗看板工具栏应包含「发送人管理」链接."""
    with app.app_context():
        from wecom_ability_service.db import get_db
        _seed_snapshot(get_db(), [
            {"mobile": "13900000001", "funnel_state": "inactive"},
        ])

    resp = client.get("/admin/hxc-dashboard")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "/admin/hxc-send-config" in body


def test_send_config_page_renders(client, app):
    """GET /admin/hxc-send-config 应返回 200 + 含关键字."""
    resp = client.get("/admin/hxc-send-config")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "群发发送人管理" in body or "sc-members-data" in body


def test_admin_refresh_endpoint_fails_when_not_configured(client, app):
    """没配 MESSAGE_ACTIVITY_DB_* → /refresh 返回 500 + status=not_configured."""
    with app.app_context():
        app.config.update(
            MESSAGE_ACTIVITY_DB_HOST="",
            MESSAGE_ACTIVITY_DB_NAME="",
            MESSAGE_ACTIVITY_DB_USER="",
            MESSAGE_ACTIVITY_DB_PASS="",
        )
    resp = client.post(
        "/api/admin/hxc-dashboard/refresh",
        json={"trigger_source": "admin"},
    )
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["ok"] is False
    assert payload["status"] == "not_configured"


# ── 发送人白名单 CRUD ──


def test_send_config_upsert_and_list(client, app):
    resp = client.post(
        "/api/admin/hxc-dashboard/send-config",
        json={"sender_userid": "alice", "display_name": "Alice", "priority": 10},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    resp = client.get("/api/admin/hxc-dashboard/send-config")
    configs = resp.get_json()
    assert len(configs) == 1
    assert configs[0]["sender_userid"] == "alice"
    assert configs[0]["display_name"] == "Alice"
    assert configs[0]["priority"] == 10
    assert configs[0]["is_active"] is True


def test_send_config_upsert_updates_existing(client, app):
    client.post(
        "/api/admin/hxc-dashboard/send-config",
        json={"sender_userid": "bob", "display_name": "Bob", "priority": 50},
    )
    client.post(
        "/api/admin/hxc-dashboard/send-config",
        json={"sender_userid": "bob", "display_name": "Bob Updated", "priority": 20},
    )
    configs = client.get("/api/admin/hxc-dashboard/send-config").get_json()
    assert len(configs) == 1
    assert configs[0]["display_name"] == "Bob Updated"
    assert configs[0]["priority"] == 20


def test_send_config_upsert_rejects_empty_userid(client):
    resp = client.post(
        "/api/admin/hxc-dashboard/send-config",
        json={"sender_userid": "", "display_name": "X"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_send_config_delete(client, app):
    client.post(
        "/api/admin/hxc-dashboard/send-config",
        json={"sender_userid": "charlie", "display_name": "Charlie"},
    )
    resp = client.delete("/api/admin/hxc-dashboard/send-config/charlie")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    configs = client.get("/api/admin/hxc-dashboard/send-config").get_json()
    assert len(configs) == 0


def test_send_config_ordering_by_priority(client, app):
    for uid, prio in [("z_low", 99), ("a_high", 1), ("m_mid", 50)]:
        client.post(
            "/api/admin/hxc-dashboard/send-config",
            json={"sender_userid": uid, "priority": prio},
        )
    configs = client.get("/api/admin/hxc-dashboard/send-config").get_json()
    assert [c["sender_userid"] for c in configs] == ["a_high", "m_mid", "z_low"]


# ── 一键群发 ──


def _seed_send_config(db, sender_userid, display_name="", priority=100, is_active=True):
    db.execute(
        """
        INSERT INTO user_ops_hxc_send_config (sender_userid, display_name, priority, is_active)
        VALUES (?, ?, ?, ?)
        """,
        (sender_userid, display_name, priority, is_active),
    )
    db.commit()


def _seed_follow_users(db, pairs):
    """pairs: [(external_userid, user_id), ...]"""
    for euid, uid in pairs:
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users
                (corp_id, external_userid, user_id, relation_status, is_primary)
            VALUES ('corp1', ?, ?, 'active', FALSE)
            """,
            (euid, uid),
        )
    db.commit()


def test_broadcast_no_targets(client):
    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": [], "content": "hello"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "no targets"


def test_broadcast_empty_content(client):
    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": ["ext1"], "content": ""},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "empty content"


def test_broadcast_no_active_senders(client, app):
    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": ["ext1"], "content": "hello"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "no_active_senders"


def test_broadcast_skips_no_matching_sender(client, app):
    """ext1 的好友是 unknown_owner，不在白名单 → skipped."""
    with app.app_context():
        from wecom_ability_service.db import get_db
        db = get_db()
        _seed_send_config(db, "alice", "Alice", priority=1)
        _seed_follow_users(db, [("ext1", "unknown_owner")])

    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": ["ext1"], "content": "hello"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"] == "no_eligible_targets"
    assert data["skipped_no_match"] == 1


def test_broadcast_dispatches_grouped_by_sender(client, app, monkeypatch):
    with app.app_context():
        from wecom_ability_service.db import get_db
        db = get_db()
        _seed_send_config(db, "alice", "Alice", priority=1)
        _seed_send_config(db, "bob", "Bob", priority=2)
        _seed_follow_users(db, [
            ("ext1", "alice"),
            ("ext2", "alice"),
            ("ext3", "bob"),
        ])

    dispatched = []

    def mock_dispatch(task_type, action, payload):
        dispatched.append({"task_type": task_type, "action": action, "payload": payload})
        return {"task_id": f"mock_{len(dispatched)}"}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task",
        mock_dispatch,
    )

    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": ["ext1", "ext2", "ext3"], "content": "测试消息"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total_sent"] == 3
    assert data["total_failed"] == 0
    assert len(data["sender_results"]) == 2

    assert len(dispatched) == 2
    senders = {d["payload"]["sender"] for d in dispatched}
    assert senders == {"alice", "bob"}
    for d in dispatched:
        assert d["task_type"] == "private_message"
        assert d["payload"]["text"]["content"] == "测试消息"


def test_broadcast_priority_overrides_owner(client, app, monkeypatch):
    """ext1 同时加了 alice(优先级1) 和 bob(优先级2) 为好友，应由 alice 发送."""
    with app.app_context():
        from wecom_ability_service.db import get_db
        db = get_db()
        _seed_send_config(db, "alice", "Alice", priority=1)
        _seed_send_config(db, "bob", "Bob", priority=2)
        _seed_follow_users(db, [
            ("ext1", "bob"),
            ("ext1", "alice"),
        ])

    dispatched = []

    def mock_dispatch(task_type, action, payload):
        dispatched.append(payload)
        return {"task_id": "mock"}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task",
        mock_dispatch,
    )

    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": ["ext1"], "content": "hello"},
    )
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total_sent"] == 1
    assert len(dispatched) == 1
    assert dispatched[0]["sender"] == "alice"


def test_broadcast_inactive_sender_excluded(client, app, monkeypatch):
    """bob 是 ext2 的好友但已停用 → ext2 无匹配 sender → skipped."""
    with app.app_context():
        from wecom_ability_service.db import get_db
        db = get_db()
        _seed_send_config(db, "alice", "Alice", priority=1, is_active=True)
        _seed_send_config(db, "bob", "Bob", priority=2, is_active=False)
        _seed_follow_users(db, [
            ("ext1", "alice"),
            ("ext2", "bob"),
        ])

    dispatched = []

    def mock_dispatch(task_type, action, payload):
        dispatched.append(payload)
        return {"task_id": "mock"}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_task",
        mock_dispatch,
    )

    resp = client.post(
        "/api/admin/hxc-dashboard/broadcast",
        json={"external_userids": ["ext1", "ext2"], "content": "hello"},
    )
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total_sent"] == 1
    assert data["skipped_no_match"] == 1
    assert len(dispatched) == 1
    assert dispatched[0]["sender"] == "alice"
