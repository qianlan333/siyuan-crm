"""PG 兼容性回归测试 —— 覆盖 6 个真生产 bug 涉及的代码路径。

每个 test 命名为 ``test_pg_bug_<编号>_<描述>``，注释里关联到原 PR。
任何引入 SQLite-only 写法（``= 1`` 比 BOOLEAN、``substr(TIMESTAMPTZ)``、
``WHERE ts <> ''`` 等）的 PR 会让对应 test 在 CI 的 PG job 上挂掉。

本地跑：
- PG：``DATABASE_URL=postgresql://test:test@localhost:5432/test pytest tests/integration/``
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch


def _insert_segment_with_known_member(app, *, segment_code: str, member_id: int, external_id: str) -> int:
    """造一个最小可用的 segment + automation_member，返回 segment_id。

    为了让 ``allocate_campaign_members`` 能跑通，segment 的 sql_query 直接 SELECT 这个 member.id。
    """
    from wecom_ability_service.db import get_db

    db = get_db()
    cur = db.cursor()
    # 造一个 automation_member（campaign_members.member_id 必须能对上）
    # in_pool 在 PG 是 BOOLEAN，传 True 跨库都吃；不能传 1
    cur.execute(
        """
        INSERT INTO automation_member (id, external_contact_id, phone, current_audience_code, in_pool)
        VALUES (?, ?, '', 'operating', ?)
        ON CONFLICT (id) DO UPDATE SET external_contact_id = excluded.external_contact_id
        """,
        (member_id, external_id, True),
    )
    cur.execute(
        """
        INSERT INTO segments
            (segment_code, display_name, source_type, sql_query, sql_params_json,
             cached_headcount, status)
        VALUES (?, ?, 'sql', ?, '{}', 0, 'active')
        ON CONFLICT (segment_code) DO UPDATE SET status = 'active'
        """,
        (
            segment_code,
            f"test segment {segment_code}",
            f"SELECT id AS member_id, external_contact_id, '' AS phone FROM automation_member WHERE id = {int(member_id)}",
        ),
    )
    db.commit()
    cur.execute("SELECT id FROM segments WHERE segment_code = ?", (segment_code,))
    return int(cur.fetchone()["id"])


# ----------------------------------------------------------------------------
# Bug 1 + 2 + 3 (PR #184/#185/#187): approval_token issue / consume / TIMESTAMPTZ
# ----------------------------------------------------------------------------

def test_pg_bug_184_185_187_approval_token_issue_consume(app):
    """token 全流程：issue → consume → race already_consumed → expired。

    覆盖 3 个旧 bug：
    - PR #184 ``utcnow() > exp`` TypeError
    - PR #185 ``utcnow().isoformat()`` naive 字符串被 PG 倒推
    - PR #187 ``WHERE consumed_at = ''`` PG 抛 InvalidDatetimeFormat
    """
    from wecom_ability_service.domains.cloud_orchestrator import approval_token

    # 签发
    issued = approval_token.issue_token(plan_id="test-plan-1", operator="alice", scope="start_campaign")
    assert issued["token"]
    assert issued["plan_id"] == "test-plan-1"

    # 第一次消费成功
    res = approval_token.consume_token(token=issued["token"], plan_id="test-plan-1", consumer="bob", scope="start_campaign")
    assert res["ok"], f"consume failed: {res}"
    assert res["reason"] == "consumed"

    # 第二次消费同 token 应失败（已消费）
    res2 = approval_token.consume_token(token=issued["token"], plan_id="test-plan-1", consumer="bob", scope="start_campaign")
    assert not res2["ok"]
    assert res2["reason"] == "already_consumed"

    # plan 不匹配应失败
    issued3 = approval_token.issue_token(plan_id="test-plan-2", operator="alice")
    res3 = approval_token.consume_token(token=issued3["token"], plan_id="WRONG", consumer="x")
    assert not res3["ok"]
    assert res3["reason"] == "plan_mismatch"


def test_pg_bug_184_185_token_timezone_aware_storage(app):
    """``expires_at`` 必须按 UTC 存，不能被 PG 按 server timezone 倒推。

    回归 PR #185：``datetime.utcnow().isoformat()`` 写 naive 字符串会被 PG (Asia/Shanghai)
    按本地时区解读后转 UTC，导致 token 一签发就过期。
    """
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.cloud_orchestrator import approval_token

    approval_token.issue_token(plan_id="test-tz", operator="alice", ttl_seconds=300)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT expires_at FROM cloud_approval_tokens WHERE plan_id = 'test-tz'")
    row = cur.fetchone()
    raw = row["expires_at"]

    # PG 返回 datetime；SQLite 返回字符串。无论哪种，过期时刻应在未来
    if isinstance(raw, datetime):
        exp = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    else:
        text = str(raw).rstrip("Z")
        if "+" not in text and text.count("-") <= 2:
            text = text + "+00:00"
        exp = datetime.fromisoformat(text)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (exp - now).total_seconds()
    assert 60 < delta < 600, f"expires_at not in future window: delta={delta}s exp={exp} now={now}"


# ----------------------------------------------------------------------------
# Bug 6 (PR #202): WHERE enabled = 1 boolean = integer
# ----------------------------------------------------------------------------

def test_pg_bug_202_frequency_budget_select_with_bool(app):
    """``frequency_budget_service`` 的 ``WHERE enabled = 1`` 在 PG 抛 ``boolean = integer``。

    PR #202 把 6 处 ``= 1`` 改成 ``WHERE enabled``。空表查也不能炸。
    """
    from wecom_ability_service.domains.marketing_automation import frequency_budget_service

    # 空表查（无 active campaign）应返回 allowed=True
    verdict = frequency_budget_service.check_member_budget(
        member_id=1,
        external_contact_id="ext-test",
        channels=("wecom_private", "ai_initiated"),
        program_codes=("campaign",),
    )
    assert verdict.allowed is True


def test_retired_budget_codes_are_disabled_on_init(app):
    """``_RETIRED_BUDGET_CODES`` 里的旧预算在启动期被自动 disable。

    回归三条已退役预算（ai_initiated_per_member_weekly /
    global_per_member_weekly / global_per_member_daily）的迁移路径——
    生产 DB 老行必须无需运营手工 UPDATE 也能立刻失效。
    """
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.marketing_automation import frequency_budget_service

    legacy_specs = (
        ("ai_initiated_per_member_weekly", "channel", "ai_initiated", 7 * 24 * 3600, 2),
        ("global_per_member_weekly", "global", "", 7 * 24 * 3600, 3),
        ("global_per_member_daily", "global", "", 24 * 3600, 1),
    )

    db = get_db()
    cursor = db.cursor()
    # 模拟老 DB：手动 INSERT 三条 enabled=true 的旧预算
    for code, scope, scope_key, window, cap in legacy_specs:
        cursor.execute(
            """
            INSERT INTO automation_frequency_budget
                (budget_code, scope, scope_key, window_seconds, max_count,
                 description, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (code, scope, scope_key, window, cap, "legacy row", True),
        )
    db.commit()

    # 模拟下次应用启动
    frequency_budget_service.ensure_default_budgets()

    for code, *_ in legacy_specs:
        cursor.execute(
            "SELECT enabled FROM automation_frequency_budget WHERE budget_code = ?",
            (code,),
        )
        row = cursor.fetchone()
        assert row is not None, f"{code} 保留行（仅 disable 不删除，维持 consumption 引用完整性）"
        assert not row["enabled"], f"{code} expected enabled=false, got {row['enabled']!r}"

    # 退役预算不再出现在 list_active_budgets 结果里
    active = frequency_budget_service.list_active_budgets(
        channels=("wecom_private", "ai_initiated"),
        program_codes=("campaign",),
    )
    codes = {b["budget_code"] for b in active}
    for code, *_ in legacy_specs:
        assert code not in codes, f"{code} should be filtered out of active budgets"


# ----------------------------------------------------------------------------
# Bug 4 + 5 (PR #192/#200): scheduler 的 substr / next_due_at 处理
# ----------------------------------------------------------------------------

def test_pg_bug_192_200_206_scheduler_full_cycle_batch(app):
    """启动 campaign + 调度链路全流程 —— 覆盖 4/5/6 + 验证 PR #206 batch dispatch。

    包括：
    - PR #192 ``substr(joined_at, ...)`` PG UndefinedFunction
    - PR #200 ``next_due_at <> ''`` + ``SET ts = ''`` InvalidDatetimeFormat
    - PR #202 ``WHERE enabled = 1`` boolean=integer
    - PR #206 batch dispatch（同 step 的 N 人聚合成 1 个 dispatch_wecom_task）
    """
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service
    from wecom_ability_service.domains.campaigns import scheduler

    # 造数据：3 个 member 同 segment
    _insert_segment_with_known_member(app, segment_code="seg-batch", member_id=901, external_id="ext-901")
    _insert_segment_with_known_member(app, segment_code="seg-batch", member_id=902, external_id="ext-902")
    _insert_segment_with_known_member(app, segment_code="seg-batch", member_id=903, external_id="ext-903")
    db = get_db()
    cur = db.cursor()
    # segments 表用 segment_code，3 个 member 但同一 segment，segment.sql_query 改成包含 3 人
    cur.execute(
        "UPDATE segments SET sql_query = ? WHERE segment_code = 'seg-batch'",
        ("SELECT id AS member_id, external_contact_id, '' AS phone FROM automation_member WHERE id IN (901, 902, 903)",),
    )
    db.commit()

    # propose campaign
    overview = campaign_service.propose_campaign(
        display_name="PG smoke",
        intent="测试 batch dispatch + PG 兼容",
        segments=[{
            "segment_code": "seg-batch",
            "priority": 100,
            "steps": [
                {"step_index": 0, "day_offset": 0, "send_time": "10:00", "content_text": "D+0 hello", "stop_on_reply": True},
            ],
        }],
        anchor_mode="campaign_start_date",
    )
    camp_id = int(overview["campaign"]["id"])
    assert overview["allocation"]["allocated"] == 3, f"allocate failed: {overview['allocation']}"

    # 启动 — 需要 token
    from wecom_ability_service.domains.cloud_orchestrator import approval_token
    issued = approval_token.issue_token(
        plan_id=overview["campaign"]["campaign_code"],
        operator="alice",
        scope="start_campaign",
    )
    started = campaign_service.start_campaign(
        campaign_id=camp_id,
        human_approver="bob",
        approval_token_value=issued["token"],
    )
    assert started["run_status"] == "active"

    # start_campaign 已同步一条 broadcast_jobs 排期；把 member/job 都拉到过去，
    # 让 worker 立即消费，同时验证 run_due 不会抢 claim。
    cur.execute(
        "UPDATE campaign_members SET next_due_at = ? WHERE campaign_id = ?",
        ("2020-01-01 00:00:00+00:00", int(camp_id)),
    )
    cur.execute(
        "UPDATE broadcast_jobs SET scheduled_for = ? WHERE source_type = 'campaign' AND status = 'queued'",
        ("2020-01-01 00:00:00+00:00",),
    )
    db.commit()

    # mock 企微 dispatch — 不真发；记录每次调用的 external_userid 数量
    dispatched_calls: list[dict[str, Any]] = []

    def _fake_dispatch(task_type: str, fn_name: str, payload: dict) -> dict:
        dispatched_calls.append(payload)
        return {"task_id": 42}

    import sys
    from pathlib import Path
    _scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    import run_broadcast_queue_worker as worker

    with patch(
        "wecom_ability_service.domains.marketing_automation.service.dispatch_wecom_task",
        side_effect=_fake_dispatch,
    ):
        scan_result = scheduler.process_due_campaign_members(batch_size=10)
        assert scan_result["batches_enqueued"] == 0, f"run_due should not duplicate queued job: {scan_result}"
        worker_result = worker.run(batch_size=10)

    # 关键断言：3 个 member，1 次 dispatch，1 个 task 含 3 人
    assert worker_result["sent_ok"] == 1, f"sent_ok={worker_result['sent_ok']} result={worker_result}"
    assert len(dispatched_calls) == 1, f"dispatch called {len(dispatched_calls)} times, should be 1"
    assert len(dispatched_calls[0]["external_userid"]) == 3
    assert set(dispatched_calls[0]["external_userid"]) == {"ext-901", "ext-902", "ext-903"}

    # member 状态推进了
    cur.execute("SELECT status, current_step_index FROM campaign_members WHERE campaign_id = ?", (int(camp_id),))
    rows = cur.fetchall() or []
    assert len(rows) == 3
    for r in rows:
        assert r["status"] == "completed", f"member status not completed: {dict(r)}"
        assert int(r["current_step_index"]) == 0


def test_propose_campaign_segment_sql_carries_external_contact_id(app):
    """Segment SQL 自带 external_contact_id 时, propose_campaign 必须直接用, 不再走
    automation_member.id 反查.

    回归: 历史 service.py 硬编码 ``SELECT ext FROM automation_member WHERE id=?``,
    导致用 user_ops_pool_current 等非 automation_member 表写 segment 时,
    campaign_members.external_contact_id 被填空, 启动后 dispatch 直接 skip
    no_external_userid (issue 2026-05-12 灰度记忆 campaign 实战暴露).
    """
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service

    db = get_db()
    cur = db.cursor()
    # 在 user_ops_pool_current 造 2 个真实客户 (sandbox 白名单允许)
    # 注意: 不在 automation_member 表里 → 老逻辑会拿不到 ext_id
    cur.execute(
        """
        INSERT INTO user_ops_pool_current
            (id, mobile, external_userid, customer_name, owner_userid,
             current_status, is_wecom_bound, activation_status,
             class_term_no, class_term_label, source_type)
        VALUES
            (888001, '13800000001', 'wm-pc-001', 'A',  'Sender1',
             'active_focus', true, 'activated', NULL, '', 'manual'),
            (888002, '13800000002', 'wm-pc-002', 'B',  'Sender1',
             'active_focus', true, 'activated', NULL, '', 'manual')
        ON CONFLICT (id) DO UPDATE SET external_userid = excluded.external_userid
        """
    )
    cur.execute(
        """
        INSERT INTO segments
            (segment_code, display_name, source_type, sql_query, sql_params_json,
             cached_headcount, status)
        VALUES (?, ?, 'sql', ?, '{}', 0, 'active')
        ON CONFLICT (segment_code) DO UPDATE SET status = 'active', sql_query = excluded.sql_query
        """,
        (
            "seg-pool-current-pilot",
            "test pool_current segment",
            "SELECT id AS member_id, external_userid AS external_contact_id "
            "FROM user_ops_pool_current WHERE id IN (888001, 888002)",
        ),
    )
    db.commit()

    overview = campaign_service.propose_campaign(
        display_name="pool_current pilot",
        intent="验证 segment SQL 自带 ext 时 propose 不丢",
        segments=[{
            "segment_code": "seg-pool-current-pilot",
            "priority": 100,
            "steps": [
                {"step_index": 0, "day_offset": 0, "send_time": "10:00",
                 "content_text": "hi", "stop_on_reply": True},
            ],
        }],
        anchor_mode="campaign_start_date",
    )
    assert overview["allocation"]["allocated"] == 2

    cur.execute(
        "SELECT member_id, external_contact_id FROM campaign_members "
        "WHERE campaign_id = ? ORDER BY member_id",
        (int(overview["campaign"]["id"]),),
    )
    rows = [dict(r) for r in cur.fetchall()]
    assert len(rows) == 2
    # 关键: external_contact_id 必须从 SQL 输出直接取, 不能为空
    assert rows[0]["member_id"] == 888001
    assert rows[0]["external_contact_id"] == "wm-pc-001"
    assert rows[1]["member_id"] == 888002
    assert rows[1]["external_contact_id"] == "wm-pc-002"


def test_campaign_dispatch_resolves_source_member_id_before_fk_touch_log(app):
    """Campaign member_id may be a source-pool row id, not automation_member.id.

    The dispatch path must resolve by external_contact_id before writing FK-backed
    touch logs, otherwise the worker can fail after WeCom dispatch and leave members
    stuck in running.
    """
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import scheduler

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO automation_member (id, external_contact_id, phone, current_audience_code, in_pool)
        VALUES (990, 'wm-source-pool-001', '', 'operating', ?)
        """,
        (True,),
    )
    cur.execute(
        """
        INSERT INTO automation_frequency_budget
            (budget_code, scope, scope_key, window_seconds, max_count, description, enabled)
        VALUES ('test_campaign_resolve_member', 'global', '', 604800, 3, 'test', ?)
        """,
        (True,),
    )
    cur.execute(
        """
        INSERT INTO segments
            (segment_code, display_name, source_type, sql_query, sql_params_json, cached_headcount, status)
        VALUES ('seg-source-pool-id', 'source pool id', 'sql',
                'SELECT id AS member_id, external_userid AS external_contact_id FROM user_ops_pool_current',
                '{}', 0, 'active')
        RETURNING id
        """
    )
    seg_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaigns (campaign_code, display_name, intent, anchor_mode, anchor_date,
                               review_status, run_status, owner_userid, metadata_json)
        VALUES ('camp-source-pool-id', 'source pool id campaign', '', 'campaign_start_date',
                '2026-05-13', 'approved', 'active', 'ZhaoYanFang', '{}')
        RETURNING id
        """
    )
    camp_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority)
        VALUES (?, ?, 'seg-source-pool-id', 100)
        RETURNING id
        """,
        (camp_id, seg_id),
    )
    cs_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaign_steps
            (campaign_id, campaign_segment_id, step_index, day_offset, send_time,
             timezone, content_text, stop_on_reply)
        VALUES (?, ?, 0, 0, '10:00', 'Asia/Shanghai', 'step 0', ?)
        RETURNING id
        """,
        (camp_id, cs_id, False),
    )
    step0_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaign_steps
            (campaign_id, campaign_segment_id, step_index, day_offset, send_time,
             timezone, content_text, stop_on_reply)
        VALUES (?, ?, 1, 1, '10:00', 'Asia/Shanghai', 'step 1', ?)
        """,
        (camp_id, cs_id, False),
    )
    cur.execute(
        """
        INSERT INTO campaign_members
            (campaign_id, campaign_segment_id, segment_id, member_id, external_contact_id,
             status, current_step_index, next_due_at, anchor_date, trace_id)
        VALUES (?, ?, ?, 888001, 'wm-source-pool-001',
                'running', -1, '2026-05-13 10:00:00+08', '2026-05-13', 'trace-source-pool')
        RETURNING id
        """,
        (camp_id, cs_id, seg_id),
    )
    cm_id = int(cur.fetchone()["id"])
    db.commit()

    with patch(
        "wecom_ability_service.domains.marketing_automation.service.dispatch_wecom_task",
        return_value={"task_id": 9900},
    ):
        result = scheduler.run_campaign_batch(
            batch_data={
                "campaign": {
                    "id": camp_id,
                    "campaign_code": "camp-source-pool-id",
                    "owner_userid": "ZhaoYanFang",
                    "trace_id": "trace-source-pool",
                },
                "step": {"id": step0_id, "step_index": 0, "content_text": "step 0"},
                "members": [{
                    "cm_id": cm_id,
                    "member_id": 888001,
                    "external_contact_id": "wm-source-pool-001",
                    "campaign_segment_id": cs_id,
                    "trace_id": "trace-source-pool",
                }],
                "request_payload": {
                    "external_userid": ["wm-source-pool-001"],
                    "text": {"content": "step 0"},
                },
            }
        )

    assert result["ok"] is True
    assert result["sent_count"] == 1
    cur.execute(
        "SELECT member_id, external_contact_id FROM automation_touch_delivery_log "
        "WHERE external_contact_id = 'wm-source-pool-001'",
    )
    delivery = cur.fetchone()
    assert delivery is not None
    assert int(delivery["member_id"]) == 990
    cur.execute(
        "SELECT member_id FROM automation_frequency_consumption "
        "WHERE external_contact_id = 'wm-source-pool-001'",
    )
    consumption = cur.fetchone()
    assert consumption is not None
    assert int(consumption["member_id"]) == 990
    cur.execute("SELECT status, current_step_index FROM campaign_members WHERE id = ?", (cm_id,))
    member = cur.fetchone()
    assert member["status"] == "pending"
    assert int(member["current_step_index"]) == 0


def test_propose_campaign_group_code_round_trip(app):
    """propose_campaign 传 group_code/group_label 后:
    1. 落进 campaigns.metadata_json
    2. list_campaigns 返回顶层 group_code/group_label, 让 admin 前端按 group 折叠

    回归: 同一份名单按 owner_userid 拆 N 个 campaign 时, 用 group 把这 N 个
    在 admin 列表合并成 1 张折叠卡 (2026-05-12 observation_invite 97 人拆 12 个
    campaign 实战引入).
    """
    import json as _json

    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO user_ops_pool_current
            (id, mobile, external_userid, customer_name, owner_userid,
             current_status, is_wecom_bound, activation_status,
             class_term_no, class_term_label, source_type)
        VALUES
            (999001, '13900000001', 'wm-grp-001', 'A', 'Sender1',
             'active_focus', true, 'activated', NULL, '', 'manual'),
            (999002, '13900000002', 'wm-grp-002', 'B', 'Sender2',
             'active_focus', true, 'activated', NULL, '', 'manual')
        ON CONFLICT (id) DO UPDATE SET external_userid = excluded.external_userid
        """
    )
    cur.execute(
        """
        INSERT INTO segments
            (segment_code, display_name, source_type, sql_query, sql_params_json,
             cached_headcount, status)
        VALUES (?, ?, 'sql', ?, '{}', 0, 'active'),
               (?, ?, 'sql', ?, '{}', 0, 'active')
        ON CONFLICT (segment_code) DO UPDATE SET status = 'active', sql_query = excluded.sql_query
        """,
        (
            "seg-grp-sender1", "grp seg sender1",
            "SELECT id AS member_id, external_userid AS external_contact_id "
            "FROM user_ops_pool_current WHERE id = 999001",
            "seg-grp-sender2", "grp seg sender2",
            "SELECT id AS member_id, external_userid AS external_contact_id "
            "FROM user_ops_pool_current WHERE id = 999002",
        ),
    )
    db.commit()

    overview_a = campaign_service.propose_campaign(
        display_name="GRP test A · Sender1",
        intent="集合卡测试 A",
        owner_userid="Sender1",
        group_code="grp_test_2026_05_12",
        group_label="集合卡测试组",
        segments=[{
            "segment_code": "seg-grp-sender1", "priority": 100,
            "steps": [{"step_index": 0, "day_offset": 0, "send_time": "10:00",
                       "content_text": "hi A", "stop_on_reply": True}],
        }],
    )
    overview_b = campaign_service.propose_campaign(
        display_name="GRP test B · Sender2",
        intent="集合卡测试 B",
        owner_userid="Sender2",
        group_code="grp_test_2026_05_12",
        group_label="集合卡测试组",
        segments=[{
            "segment_code": "seg-grp-sender2", "priority": 100,
            "steps": [{"step_index": 0, "day_offset": 0, "send_time": "10:00",
                       "content_text": "hi B", "stop_on_reply": True}],
        }],
    )

    # 1) metadata_json 落库正确
    cur.execute(
        "SELECT metadata_json FROM campaigns WHERE id IN (?, ?) ORDER BY id",
        (int(overview_a["campaign"]["id"]), int(overview_b["campaign"]["id"])),
    )
    rows = cur.fetchall() or []
    assert len(rows) == 2
    for r in rows:
        raw = r["metadata_json"]
        meta = raw if isinstance(raw, dict) else _json.loads(raw or "{}")
        assert meta.get("group_code") == "grp_test_2026_05_12"
        assert meta.get("group_label") == "集合卡测试组"

    # 2) list_campaigns 顶层暴露 group_code/group_label
    campaigns = campaign_service.list_campaigns(limit=20)
    grp_rows = [c for c in campaigns if c.get("group_code") == "grp_test_2026_05_12"]
    assert len(grp_rows) == 2
    for c in grp_rows:
        assert c["group_label"] == "集合卡测试组"
        assert c["owner_userid"] in ("Sender1", "Sender2")

    # 3) 不传 group_code 的 campaign 不被错误归组 (空字符串)
    overview_c = campaign_service.propose_campaign(
        display_name="GRP test C · standalone",
        intent="独立 campaign",
        owner_userid="Sender1",
        segments=[{
            "segment_code": "seg-grp-sender1", "priority": 50,
            "steps": [{"step_index": 0, "day_offset": 0, "send_time": "10:00",
                       "content_text": "hi C", "stop_on_reply": True}],
        }],
    )
    campaigns2 = campaign_service.list_campaigns(limit=20)
    standalone = next((c for c in campaigns2
                       if c["campaign_code"] == overview_c["campaign"]["campaign_code"]), None)
    assert standalone is not None
    assert standalone["group_code"] == ""
    assert standalone["group_label"] == ""


def test_pg_bug_200_register_member_reply_clears_next_due(app):
    """``register_member_reply`` 把 next_due_at 清空 —— PR #200 修了 SET = '' 写入。"""
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import scheduler

    # 造一条 campaign + 1 个 pending member
    seg_id = _insert_segment_with_known_member(app, segment_code="seg-reply", member_id=911, external_id="ext-911")
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO campaigns (campaign_code, display_name, intent, anchor_mode, anchor_date,
                               review_status, run_status, metadata_json)
        VALUES ('camp-reply', 'reply test', '', 'campaign_start_date', '2026-05-09', 'approved', 'active', '{}')
        """
    )
    db.commit()
    cur.execute("SELECT id FROM campaigns WHERE campaign_code = 'camp-reply'")
    camp_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority) VALUES (?, ?, 'seg-reply', 100)",
        (camp_id, seg_id),
    )
    cur.execute("SELECT id FROM campaign_segments WHERE campaign_id = ?", (camp_id,))
    cs_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaign_members (campaign_id, campaign_segment_id, segment_id, member_id,
                                       external_contact_id, status, next_due_at, anchor_date)
        VALUES (?, ?, ?, 911, 'ext-911', 'pending', '2026-05-09 10:00:00+08', '2026-05-09')
        """,
        (camp_id, cs_id, seg_id),
    )
    db.commit()

    # 触发回复
    affected = scheduler.register_member_reply(external_contact_id="ext-911")
    assert affected == 1

    # 验证 status / next_due_at 清空（不论 PG NULL 还是 SQLite ''）
    cur.execute("SELECT status, next_due_at FROM campaign_members WHERE external_contact_id = 'ext-911'")
    row = cur.fetchone()
    assert row["status"] == "replied"
    nda = row["next_due_at"]
    assert (nda is None) or (str(nda).strip() == ""), f"next_due_at not cleared: {nda!r}"


def test_campaign_multi_step_not_blocked_by_own_daily_budget(app):
    """同 campaign 续推不被 global_per_member_daily 挡住。

    场景：campaign 有 2 个 step（day_offset=0, 1），step 0 发完记了 consumption，
    step 1 调度时应该排除同 campaign 的消耗记录，不触发 budget_exceeded。
    """
    import sys
    from pathlib import Path
    _scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    import run_broadcast_queue_worker as worker

    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service
    from wecom_ability_service.domains.campaigns import scheduler

    # 框架默认预算已全部退役（见 _RETIRED_BUDGET_CODES）；本测试仍需要 daily budget
    # 存在才能验证 PR #224 修复（同 campaign 续推不被自己的 daily 消耗挡），
    # 因此手动 seed 一条 test-only 的 daily budget。
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO automation_frequency_budget
            (budget_code, scope, scope_key, window_seconds, max_count,
             description, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "test_daily_budget_for_pr224",
            "global",
            "",
            24 * 3600,
            1,
            "test-only daily budget for PR #224 regression",
            True,
        ),
    )
    db.commit()

    _insert_segment_with_known_member(
        app, segment_code="seg-multi-step", member_id=950, external_id="ext-950",
    )

    overview = campaign_service.propose_campaign(
        display_name="multi-step budget test",
        intent="验证续推不被 daily 挡",
        segments=[{
            "segment_code": "seg-multi-step",
            "priority": 100,
            "steps": [
                {"step_index": 0, "day_offset": 0, "send_time": "10:00", "content_text": "step 0", "stop_on_reply": False},
                {"step_index": 1, "day_offset": 1, "send_time": "10:00", "content_text": "step 1", "stop_on_reply": False},
            ],
        }],
        anchor_mode="campaign_start_date",
    )
    camp_id = int(overview["campaign"]["id"])

    from wecom_ability_service.domains.cloud_orchestrator import approval_token
    issued = approval_token.issue_token(
        plan_id=overview["campaign"]["campaign_code"],
        operator="alice",
        scope="start_campaign",
    )
    campaign_service.start_campaign(
        campaign_id=camp_id,
        human_approver="bob",
        approval_token_value=issued["token"],
    )

    # step 0 已经 due
    cur.execute(
        "UPDATE campaign_members SET next_due_at = ? WHERE campaign_id = ?",
        ("2020-01-01 00:00:00+00:00", int(camp_id)),
    )
    cur.execute(
        "UPDATE broadcast_jobs SET scheduled_for = ? WHERE source_type = 'campaign' AND status = 'queued'",
        ("2020-01-01 00:00:00+00:00",),
    )
    db.commit()

    dispatched: list[dict[str, Any]] = []

    def _fake_dispatch(task_type, fn_name, payload):
        dispatched.append(payload)
        return {"task_id": 100}

    with patch(
        "wecom_ability_service.domains.marketing_automation.service.dispatch_wecom_task",
        side_effect=_fake_dispatch,
    ):
        r1 = scheduler.process_due_campaign_members(batch_size=10)
        assert r1["batches_enqueued"] == 0, f"run_due should not duplicate queued step 0: {r1}"
        worker.run(batch_size=10)

    # step 0 写了 consumption → daily budget 已扣 1 次
    cur.execute(
        "SELECT COUNT(*) AS c FROM automation_frequency_consumption "
        "WHERE external_contact_id = 'ext-950' AND source_kind = 'campaign_step'",
    )
    assert int(cur.fetchone()["c"]) > 0, "consumption not recorded after step 0"

    # step 0 发完后 _pre_enqueue_next_step 已为 step 1 预排期
    # 把预排期 job 和 member 的 next_due_at 都拉到过去，模拟"明天已到"
    cur.execute(
        "UPDATE campaign_members SET next_due_at = ? WHERE campaign_id = ? AND status = 'pending'",
        ("2020-01-01 00:00:00+00:00", int(camp_id)),
    )
    cur.execute(
        "UPDATE broadcast_jobs SET scheduled_for = ? WHERE source_type = 'campaign' AND status = 'queued'",
        ("2020-01-01 00:00:00+00:00",),
    )
    db.commit()

    dispatched.clear()
    with patch(
        "wecom_ability_service.domains.marketing_automation.service.dispatch_wecom_task",
        side_effect=_fake_dispatch,
    ):
        # 预排期 job 已存在，直接由 worker 消费（不需要再 process_due_campaign_members）
        worker.run(batch_size=10)

    assert dispatched[0]["text"]["content"] == "step 1", f"wrong step dispatched: {dispatched}"

    cur.execute(
        "SELECT status, current_step_index FROM campaign_members WHERE campaign_id = ?",
        (int(camp_id),),
    )
    row = cur.fetchone()
    assert row["status"] == "completed", f"member not completed: {dict(row)}"


def test_campaign_scheduler_does_not_claim_member_when_open_job_exists(app):
    """预排期 job 已存在时, run-due 不能先把 member 抢成 running。

    否则 queue worker 到点后会因为 member 已不是 pending 而不发送, 形成生产上
    看到的 "queued job 存在但不推送"。
    """
    import sys
    from pathlib import Path

    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service
    from wecom_ability_service.domains.campaigns import scheduler
    from wecom_ability_service.domains.cloud_orchestrator import approval_token

    _insert_segment_with_known_member(app, segment_code="seg-open-job", member_id=960, external_id="ext-960")
    overview = campaign_service.propose_campaign(
        display_name="open job guard",
        intent="预排期 job 已存在时避免 run-due 抢占",
        segments=[{
            "segment_code": "seg-open-job",
            "priority": 100,
            "steps": [{"step_index": 0, "day_offset": 0, "send_time": "10:00", "content_text": "hello"}],
        }],
        anchor_mode="campaign_start_date",
    )
    camp_id = int(overview["campaign"]["id"])
    token = approval_token.issue_token(
        plan_id=overview["campaign"]["campaign_code"],
        operator="alice",
        scope="start_campaign",
    )
    campaign_service.start_campaign(
        campaign_id=camp_id,
        human_approver="alice",
        approval_token_value=token["token"],
    )

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE campaign_members SET next_due_at = ? WHERE campaign_id = ?",
        ("2020-01-01 00:00:00+00:00", camp_id),
    )
    cur.execute(
        "UPDATE broadcast_jobs SET scheduled_for = ? WHERE source_type = 'campaign' AND status = 'queued'",
        ("2020-01-01 00:00:00+00:00",),
    )
    cur.execute(
        """
        SELECT cm.id AS cm_id, cm.member_id, cm.external_contact_id,
               cm.campaign_segment_id, cm.trace_id, c.campaign_code, c.owner_userid
        FROM campaign_members cm
        JOIN campaigns c ON c.id = cm.campaign_id
        WHERE cm.campaign_id = ?
        """,
        (camp_id,),
    )
    member_row = dict(cur.fetchone())
    db.commit()

    scan = scheduler.process_due_campaign_members(batch_size=10)
    assert scan["batches_enqueued"] == 0
    cur.execute("SELECT status FROM campaign_members WHERE id = ?", (int(member_row["cm_id"]),))
    assert cur.fetchone()["status"] == "pending"

    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_broadcast_queue_worker as worker

    dispatched: list[dict[str, Any]] = []

    def _fake_dispatch(task_type: str, fn_name: str, payload: dict) -> dict:
        dispatched.append(payload)
        return {"task_id": 960}

    with patch(
        "wecom_ability_service.domains.marketing_automation.service.dispatch_wecom_task",
        side_effect=_fake_dispatch,
    ):
        worker_result = worker.run(batch_size=10)

    assert worker_result["sent_ok"] == 1
    assert dispatched and dispatched[0]["external_userid"] == ["ext-960"]
    cur.execute("SELECT status, current_step_index FROM campaign_members WHERE id = ?", (int(member_row["cm_id"]),))
    progressed = cur.fetchone()
    assert progressed["status"] == "completed"
    assert int(progressed["current_step_index"]) == 0


def test_start_campaign_prequeues_first_step_at_step_timezone(app):
    """start 时直接同步第一步排期, 并按 step.timezone 写入精确发送时间。"""
    from zoneinfo import ZoneInfo

    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service
    from wecom_ability_service.domains.cloud_orchestrator import approval_token

    _insert_segment_with_known_member(app, segment_code="seg-prequeue-tz", member_id=965, external_id="ext-965")
    overview = campaign_service.propose_campaign(
        display_name="prequeue timezone",
        intent="启动即排期并保持本地发送时间",
        segments=[{
            "segment_code": "seg-prequeue-tz",
            "priority": 100,
            "steps": [{
                "step_index": 0,
                "day_offset": 0,
                "send_time": "19:30",
                "timezone": "Asia/Shanghai",
                "content_text": "hello",
            }],
        }],
        anchor_mode="campaign_start_date",
        anchor_date="2026-05-12",
    )
    camp_id = int(overview["campaign"]["id"])
    token = approval_token.issue_token(
        plan_id=overview["campaign"]["campaign_code"],
        operator="alice",
        scope="start_campaign",
    )
    campaign_service.start_campaign(
        campaign_id=camp_id,
        human_approver="alice",
        approval_token_value=token["token"],
    )

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT source_id, scheduled_for, target_count
        FROM broadcast_jobs
        WHERE source_type = 'campaign'
          AND source_table = 'campaign_members'
          AND status = 'queued'
          AND source_id LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (f"{camp_id}:%",),
    )
    job = cur.fetchone()
    assert job is not None
    assert str(job["source_id"]).count(":") == 2
    assert int(job["target_count"]) == 1

    raw = job["scheduled_for"]
    if isinstance(raw, datetime):
        scheduled = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    else:
        text = str(raw).replace("Z", "+00:00")
        scheduled = datetime.fromisoformat(text)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
    local_time = scheduled.astimezone(ZoneInfo("Asia/Shanghai"))
    assert local_time.strftime("%Y-%m-%d %H:%M") == "2026-05-12 19:30"

    cur.execute("SELECT status FROM campaign_members WHERE campaign_id = ?", (camp_id,))
    assert cur.fetchone()["status"] == "pending"


def test_start_campaign_rejects_active_external_conflict(app):
    """同一个 external_userid 已有 active pending/running campaign 时, 新 campaign 不应启动。"""
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.campaigns import service as campaign_service
    from wecom_ability_service.domains.cloud_orchestrator import approval_token

    old_seg_id = _insert_segment_with_known_member(app, segment_code="seg-dupe-old", member_id=970, external_id="ext-dupe")
    new_seg_id = _insert_segment_with_known_member(app, segment_code="seg-dupe-new", member_id=970, external_id="ext-dupe")

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO campaigns (campaign_code, display_name, intent, anchor_mode, anchor_date,
                               review_status, run_status, metadata_json)
        VALUES ('camp-dupe-old', 'old active', '', 'campaign_start_date', '2026-05-12',
                'approved', 'active', '{}')
        RETURNING id
        """
    )
    old_campaign_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority) VALUES (?, ?, 'seg-dupe-old', 100) RETURNING id",
        (old_campaign_id, old_seg_id),
    )
    old_campaign_segment_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO campaign_members (campaign_id, campaign_segment_id, segment_id, member_id,
                                      external_contact_id, status, current_step_index)
        VALUES (?, ?, ?, 970, 'ext-dupe', 'pending', -1)
        """,
        (old_campaign_id, old_campaign_segment_id, old_seg_id),
    )
    db.commit()

    overview = campaign_service.propose_campaign(
        display_name="new duplicate",
        intent="重复 external 应被拦截",
        segments=[{
            "segment_code": "seg-dupe-new",
            "priority": 100,
            "steps": [{"step_index": 0, "day_offset": 0, "send_time": "10:00", "content_text": "hello"}],
        }],
        anchor_mode="campaign_start_date",
    )
    assert new_seg_id
    camp_id = int(overview["campaign"]["id"])
    token = approval_token.issue_token(
        plan_id=overview["campaign"]["campaign_code"],
        operator="alice",
        scope="start_campaign",
    )
    try:
        campaign_service.start_campaign(
            campaign_id=camp_id,
            human_approver="alice",
            approval_token_value=token["token"],
        )
    except PermissionError as exc:
        assert "already pending/running" in str(exc)
    else:
        raise AssertionError("start_campaign should reject active external conflict")


# ----------------------------------------------------------------------------
# image_library / miniprogram_library — PG-only library smoke
# ----------------------------------------------------------------------------

def test_pg_image_library_crud_smoke(app):
    """image_library 基本 CRUD 不依赖企微 API。"""
    from wecom_ability_service.domains import image_library

    item = image_library.create_image_from_url(url="https://example.com/a.png", name="test")
    assert item["id"] > 0
    assert item["source"] == "url"
    assert item["enabled"] is True

    items = image_library.list_images()
    assert any(it["id"] == item["id"] for it in items)

    image_library.update_image(item["id"], enabled=False)
    items_active = image_library.list_images(enabled_only=True)
    assert not any(it["id"] == item["id"] for it in items_active)
