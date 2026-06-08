"""Campaign 硬删除（DELETE FROM campaigns）的测试。

跟 image_library 硬删除同思路：删 campaign 时把所有子表（campaign_segments /
campaign_steps / campaign_members）的关联行一起清掉，并把 broadcast_jobs 队列里
属于这个 campaign 的待发批次也一起删；cloud_broadcast_plans.campaign_id 留住
plan 自身只解关联（审计要）。

active 状态的 campaign 不能删 —— 队列里可能正在跑，删了 worker 拿到悬空 source_id。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app as create_next_app

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.campaigns import service as campaign_service


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        MCP_BEARER_TOKEN="mcp-token",
        AUTOMATION_INTERNAL_API_TOKEN="internal-token",
    ) as app:
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


def _seed_broadcast_job(campaign_id: int, campaign_segment_id: int = 99, step_index: int = 0) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO broadcast_jobs (source_type, source_id, source_table, status) "
        "VALUES ('campaign', ?, 'campaign_members', 'queued')",
        (f"{campaign_id}:{campaign_segment_id}:{step_index}",),
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
    """campaign_id=1 删除时不能误中 source_id='12:99:0' 的 job。"""
    with app.app_context():
        # 用 raw SQL 直接造两个不同 id 的 broadcast_job。
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO broadcast_jobs (source_type, source_id, source_table, status) "
            "VALUES ('campaign', '1:99:0', 'campaign_members', 'queued')"
        )
        cur.execute(
            "INSERT INTO broadcast_jobs (source_type, source_id, source_table, status) "
            "VALUES ('campaign', '12:99:0', 'campaign_members', 'queued')"
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
        # source_id='12:99:0' 必须保留
        assert _row_count("broadcast_jobs", "source_id = '12:99:0'") == 1


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


# ---------- step 编辑闸口 ----------

def test_campaign_step_mutations_reject_active_campaign(app):
    with app.app_context():
        camp = _create_draft("active-step-edit")
        cid = int(camp["id"])
        seg_id, step_index = _seed_segment_and_step(cid)
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE campaigns SET run_status = 'active' WHERE id = ?", (cid,))
        db.commit()

        with pytest.raises(PermissionError, match="run_status=active"):
            campaign_service.update_campaign_step(
                campaign_id=cid,
                step_index=step_index,
                content_text="new copy",
            )
        with pytest.raises(PermissionError, match="run_status=active"):
            campaign_service.delete_campaign_step(campaign_id=cid, step_index=step_index)
        with pytest.raises(PermissionError, match="run_status=active"):
            campaign_service.append_campaign_step(
                campaign_id=cid,
                campaign_segment_id=seg_id,
                content_text="next copy",
            )


def test_delete_campaign_step_rejects_last_step(app):
    with app.app_context():
        camp = _create_draft("last-step")
        cid = int(camp["id"])
        _seed_segment_and_step(cid)

        with pytest.raises(PermissionError, match="last campaign step"):
            campaign_service.delete_campaign_step(campaign_id=cid, step_index=0)
        assert _row_count("campaign_steps", "campaign_id = ?", (cid,)) == 1


def test_delete_campaign_step_requires_existing_step(app):
    with app.app_context():
        camp = _create_draft("missing-step")
        cid = int(camp["id"])
        _seed_segment_and_step(cid)

        with pytest.raises(LookupError, match="step 99 not found"):
            campaign_service.delete_campaign_step(campaign_id=cid, step_index=99)


def test_delete_campaign_step_removes_one_step_when_multiple_exist(app):
    with app.app_context():
        camp = _create_draft("multi-step")
        cid = int(camp["id"])
        seg_id, _ = _seed_segment_and_step(cid)
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO campaign_steps (campaign_id, campaign_segment_id, step_index, day_offset, "
            "send_time, content_text) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, seg_id, 1, 1, "11:00", "next"),
        )
        db.commit()

        result = campaign_service.delete_campaign_step(campaign_id=cid, step_index=0)

        assert result["deleted"] is True
        assert result["rowcount"] == 1
        assert _row_count("campaign_steps", "campaign_id = ?", (cid,)) == 1
        assert _row_count("campaign_steps", "campaign_id = ? AND step_index = 1", (cid,)) == 1


# ---------- Next command endpoint ----------

def _next_client() -> TestClient:
    return TestClient(create_next_app(), raise_server_exceptions=False)


def test_next_delete_campaign_endpoint_uses_next_command_boundary(app):
    with app.app_context():
        camp = _create_draft("via-http")
        code = camp["campaign_code"]

    client = _next_client()
    resp = client.delete(
        f"/api/admin/cloud-orchestrator/campaigns/{code}",
        headers={"Idempotency-Key": "campaign-delete-next-command"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert resp.headers["X-AICRM-Fallback-Used"] == "false"
    body = resp.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_command"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["command_name"] == "cloud_orchestrator.campaign.delete"
    assert body["write_model_status"] == "deleted"
    assert body["campaign"]["campaign_code"] == code

    with app.app_context():
        assert campaign_service.get_campaign(campaign_code=code) is not None


def test_next_delete_campaign_not_found_returns_404(app):
    client = _next_client()
    resp = client.delete(
        "/api/admin/cloud-orchestrator/campaigns/no-such-camp",
        headers={"Idempotency-Key": "campaign-delete-missing-next-command"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["source_status"] == "next_command"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False


def test_next_delete_active_campaign_is_plan_only_not_legacy_http_409(app):
    with app.app_context():
        camp = _create_draft("active-via-http")
        cid = int(camp["id"])
        code = camp["campaign_code"]
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE campaigns SET run_status = 'active' WHERE id = ?", (cid,))
        db.commit()

    client = _next_client()
    resp = client.delete(
        f"/api/admin/cloud-orchestrator/campaigns/{code}",
        headers={"Idempotency-Key": "campaign-delete-active-next-command"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_command"
    assert body["real_external_call_executed"] is False
    assert body["write_model_status"] == "deleted"
