"""PG 兼容性回归测试 —— 覆盖 6 个真生产 bug 涉及的代码路径。

每个 test 命名为 ``test_pg_bug_<编号>_<描述>``，注释里关联到原 PR。
任何引入 SQLite-only 写法（``= 1`` 比 BOOLEAN、``substr(TIMESTAMPTZ)``、
``WHERE ts <> ''`` 等）的 PR 会让对应 test 在 CI 的 PG job 上挂掉。

本地跑：
- SQLite（默认，秒级）：``pytest tests/integration/``
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

    # 改 next_due_at 到过去（默认是当天 10:00，可能未来），让 process_due 立即扫到
    cur.execute(
        "UPDATE campaign_members SET next_due_at = ? WHERE campaign_id = ?",
        ("2020-01-01 00:00:00+00:00", int(camp_id)),
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
        assert scan_result["batches_enqueued"] == 1, f"enqueue failed: {scan_result}"
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
        assert r1["batches_enqueued"] == 1, f"step 0 enqueue failed: {r1}"
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
        r2 = worker.run(batch_size=10)

    assert dispatched[0]["text"]["content"] == "step 1", f"wrong step dispatched: {dispatched}"

    cur.execute(
        "SELECT status, current_step_index FROM campaign_members WHERE campaign_id = ?",
        (int(camp_id),),
    )
    row = cur.fetchone()
    assert row["status"] == "completed", f"member not completed: {dict(row)}"


# ----------------------------------------------------------------------------
# image_library / miniprogram_library — PG/SQLite 跨库
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
