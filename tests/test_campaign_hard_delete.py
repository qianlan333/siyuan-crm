"""Campaign 硬删除（DELETE FROM campaigns）的测试。

跟 image_library 硬删除同思路：删 campaign 时把所有子表（campaign_segments /
campaign_steps / campaign_members）的关联行一起清掉，并把 broadcast_jobs 队列里
属于这个 campaign 的待发批次也一起删；cloud_broadcast_plans.campaign_id 留住
plan 自身只解关联（审计要）。

active 状态的 campaign 不能删 —— 队列里可能正在跑，删了 worker 拿到悬空 source_id。
"""
from __future__ import annotations

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.campaigns import service as campaign_service


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "campaign-delete.sqlite3"
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
            "MCP_BEARER_TOKEN": "mcp-token",
            "AUTOMATION_INTERNAL_API_TOKEN": "internal-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


def _create_draft(name: str = "test-camp") -> dict:
    return campaign_service.create_campaign_draft(
        display_name=name, intent="test intent", anchor_date="2026-05-10"
    )


def _seed_segment_and_step(campaign_id: int) -> tuple[int, int]:
    """造一个 segment + 一个 step，返回 (segment_id, step_index)。"""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority, label) "
        "VALUES (?, ?, ?, ?, ?)",
        (campaign_id, 999, "seg-test", 100, "test"),
    )
    seg_id = int(cur.lastrowid or 0)
    cur.execute(
        "INSERT INTO campaign_steps (campaign_id, campaign_segment_id, step_index, day_offset, "
        "send_time, content_text) VALUES (?, ?, ?, ?, ?, ?)",
        (campaign_id, seg_id, 0, 0, "10:00", "hi"),
    )
    db.commit()
    return seg_id, 0


def _seed_member(campaign_id: int, segment_id: int, member_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO campaign_members (campaign_id, campaign_segment_id, segment_id, member_id, "
        "external_contact_id, status) VALUES (?, ?, ?, ?, ?, 'pending')",
        (campaign_id, segment_id, 999, member_id, f"ec-{member_id}"),
    )
    db.commit()


def _seed_broadcast_job(campaign_id: int, step_index: int = 0) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO broadcast_jobs (source_type, source_id, source_table, status) "
        "VALUES ('campaign', ?, 'campaign_members', 'queued')",
        (f"{campaign_id}:{step_index}",),
    )
    db.commit()


def _row_count(table: str, where_sql: str = "1=1", args: tuple = ()) -> int:
    cur = get_db().cursor()
    cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {where_sql}", args)
    row = cur.fetchone()
    return int(dict(row)["c"]) if row else 0


# ---------- 基础：草稿 campaign 直接删 ----------

def test_delete_campaign_removes_main_row(app):
    with app.app_context():
        camp = _create_draft("solo-draft")
        result = campaign_service.delete_campaign(campaign_id=int(camp["id"]))
        assert result["ok"] is True
        assert result["deleted_id"] == int(camp["id"])
        assert result["deleted_campaign_code"] == camp["campaign_code"]
        assert _row_count("campaigns", "id = ?", (int(camp["id"]),)) == 0


def test_delete_campaign_not_found_raises(app):
    with app.app_context():
        with pytest.raises(LookupError, match="not found"):
            campaign_service.delete_campaign(campaign_id=999999)


# ---------- 子表全部清空 ----------

def test_delete_campaign_cascades_segments_steps_members(app):
    with app.app_context():
        camp = _create_draft("with-children")
        cid = int(camp["id"])
        seg_id, _ = _seed_segment_and_step(cid)
        _seed_member(cid, seg_id, member_id=1)
        _seed_member(cid, seg_id, member_id=2)
        # 另造一个不相干 campaign 验证不会被误删
        other = _create_draft("other-camp")
        other_id = int(other["id"])
        other_seg, _ = _seed_segment_and_step(other_id)
        _seed_member(other_id, other_seg, member_id=99)

        result = campaign_service.delete_campaign(campaign_id=cid)
        assert result["rows_cleared"]["campaign_segments"] == 1
        assert result["rows_cleared"]["campaign_steps"] == 1
        assert result["rows_cleared"]["campaign_members"] == 2

        # 本 campaign 全部消失
        assert _row_count("campaign_segments", "campaign_id = ?", (cid,)) == 0
        assert _row_count("campaign_steps", "campaign_id = ?", (cid,)) == 0
        assert _row_count("campaign_members", "campaign_id = ?", (cid,)) == 0
        # 别人的 campaign 不动
        assert _row_count("campaign_segments", "campaign_id = ?", (other_id,)) == 1
        assert _row_count("campaign_steps", "campaign_id = ?", (other_id,)) == 1
        assert _row_count("campaign_members", "campaign_id = ?", (other_id,)) == 1


def test_delete_campaign_clears_broadcast_jobs(app):
    with app.app_context():
        camp = _create_draft("with-jobs")
        cid = int(camp["id"])
        _seed_broadcast_job(cid, step_index=0)
        _seed_broadcast_job(cid, step_index=1)
        # 别的 campaign 的 job 不能误删
        other = _create_draft("other")
        _seed_broadcast_job(int(other["id"]), step_index=0)

        result = campaign_service.delete_campaign(campaign_id=cid)
        assert result["rows_cleared"]["broadcast_jobs"] == 2

        assert _row_count(
            "broadcast_jobs",
            "source_type = 'campaign' AND source_id LIKE ?",
            (f"{cid}:%",),
        ) == 0
        assert _row_count(
            "broadcast_jobs",
            "source_type = 'campaign' AND source_id LIKE ?",
            (f"{int(other['id'])}:%",),
        ) == 1


def test_delete_campaign_id_substring_safety(app):
    """campaign_id=1 删除时不能误中 source_id='12:0' 的 job（LIKE '1:%' 不会匹配 '12:0'）。"""
    with app.app_context():
        # 用 raw SQL 直接造两个不同 id 的 broadcast_job：source_id 分别是 '1:0' 和 '12:0'
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO broadcast_jobs (source_type, source_id, source_table, status) "
            "VALUES ('campaign', '1:0', 'campaign_members', 'queued')"
        )
        cur.execute(
            "INSERT INTO broadcast_jobs (source_type, source_id, source_table, status) "
            "VALUES ('campaign', '12:0', 'campaign_members', 'queued')"
        )
        db.commit()
        # 造一个真的 id=1 的 campaign 才能删
        cur.execute(
            "INSERT INTO campaigns (id, campaign_code, display_name, intent, anchor_mode, "
            "anchor_date, review_status, run_status) "
            "VALUES (1, 'one', 'one', '', 'campaign_start_date', '2026-05-10', 'draft', 'draft')"
        )
        db.commit()

        result = campaign_service.delete_campaign(campaign_id=1)
        assert result["rows_cleared"]["broadcast_jobs"] == 1
        # source_id='12:0' 必须保留
        assert _row_count("broadcast_jobs", "source_id = '12:0'") == 1


# ---------- active 不能删 ----------

def test_delete_active_campaign_raises_permission(app):
    with app.app_context():
        camp = _create_draft("running-camp")
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "UPDATE campaigns SET run_status = 'active' WHERE id = ?",
            (int(camp["id"]),),
        )
        db.commit()
        with pytest.raises(PermissionError, match="active"):
            campaign_service.delete_campaign(campaign_id=int(camp["id"]))
        # 数据没动
        assert _row_count("campaigns", "id = ?", (int(camp["id"]),)) == 1


def test_delete_paused_campaign_allowed(app):
    """paused / cancelled / finished 都允许删。"""
    with app.app_context():
        for run_status in ("paused", "cancelled", "finished"):
            camp = _create_draft(f"camp-{run_status}")
            cid = int(camp["id"])
            db = get_db()
            cur = db.cursor()
            cur.execute(
                "UPDATE campaigns SET run_status = ? WHERE id = ?",
                (run_status, cid),
            )
            db.commit()
            result = campaign_service.delete_campaign(campaign_id=cid)
            assert result["ok"] is True


# ---------- HTTP endpoint ----------

def test_http_delete_campaign_endpoint(app):
    with app.app_context():
        camp = _create_draft("via-http")
        code = camp["campaign_code"]

    client = app.test_client()
    resp = client.delete(f"/api/admin/cloud-orchestrator/campaigns/{code}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["deleted_campaign_code"] == code

    with app.app_context():
        assert campaign_service.get_campaign(campaign_code=code) is None


def test_http_delete_campaign_not_found_returns_404(app):
    client = app.test_client()
    resp = client.delete("/api/admin/cloud-orchestrator/campaigns/no-such-camp")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["ok"] is False


def test_http_delete_active_campaign_returns_409(app):
    with app.app_context():
        camp = _create_draft("active-via-http")
        cid = int(camp["id"])
        code = camp["campaign_code"]
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE campaigns SET run_status = 'active' WHERE id = ?", (cid,))
        db.commit()

    client = app.test_client()
    resp = client.delete(f"/api/admin/cloud-orchestrator/campaigns/{code}")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert "active" in body["error"]
