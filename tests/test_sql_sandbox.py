"""Segment SQL 沙箱 — 静态校验单元测试 (不连库)."""
from __future__ import annotations

from wecom_ability_service.domains.segments.sql_sandbox import (
    ALLOWED_TABLES,
    validate_segment_sql,
)


def test_validate_accepts_pool_current():
    """pool_current 是默认主表, 历史就支持."""
    ok, reason = validate_segment_sql(
        "SELECT id AS member_id, external_userid AS external_contact_id "
        "FROM user_ops_pool_current WHERE external_userid <> ''"
    )
    assert ok, reason


def test_validate_accepts_lead_pool_current():
    """PR 新增: lead_pool 是 pool_current 的互补半边, 也必须在白名单.

    回归 2026-05-12 灰度记忆 campaign 实战: 82 个 ZhaoYanFang 好友里 3 个只在
    lead_pool 不在 pool_current, 不加进白名单 agent 用 pool_current 单表写 segment
    会漏掉这 3 人.
    """
    ok, reason = validate_segment_sql(
        "SELECT id AS member_id, external_userid AS external_contact_id "
        "FROM user_ops_lead_pool_current WHERE external_userid <> ''"
    )
    assert ok, reason


def test_validate_accepts_hxc_dashboard_snapshot():
    """PR 新增: 漏斗看板快照, 技能 md §3.4 承诺可以直接 SQL 喂 propose_segment."""
    ok, reason = validate_segment_sql(
        "SELECT 0 AS member_id, external_userid AS external_contact_id "
        "FROM user_ops_hxc_dashboard_snapshot "
        "WHERE funnel_state = 'only_member' AND membership_type = 'trial'"
    )
    assert ok, reason


def test_validate_accepts_union_lead_pool_and_pool_current():
    """两表 UNION 是反查 ext_userid 时的典型用法, 沙箱必须接受."""
    ok, reason = validate_segment_sql(
        "SELECT id AS member_id, external_userid AS external_contact_id "
        "FROM user_ops_pool_current WHERE external_userid <> '' "
        "UNION "
        "SELECT id AS member_id, external_userid AS external_contact_id "
        "FROM user_ops_lead_pool_current WHERE external_userid <> ''"
    )
    assert ok, reason


def test_validate_rejects_unknown_table():
    """白名单外的表必须拒绝 (防 agent 误用 contacts / archived_messages 这类大表)."""
    ok, reason = validate_segment_sql(
        "SELECT id AS member_id FROM contacts WHERE external_userid <> ''"
    )
    assert not ok
    assert "forbidden_tables:contacts" in reason


def test_validate_rejects_embedded_write_keyword():
    """SELECT 外壳里塞 DELETE 关键字必须被关键字黑名单拦下."""
    ok, reason = validate_segment_sql(
        "SELECT id AS member_id FROM user_ops_pool_current "
        "WHERE id IN (SELECT id FROM user_ops_pool_current "
        "WHERE customer_name = 'DELETE me')"
    )
    # 这条其实 OK (DELETE 在字符串里, 但黑名单是全词正则匹配, 所以会被拦)
    assert not ok
    assert "DELETE" in reason


def test_allowed_tables_contains_double_source_pair():
    """显式断言双源核心表都在白名单, 防有人误删."""
    for tbl in ("user_ops_pool_current", "user_ops_lead_pool_current",
                "user_ops_hxc_dashboard_snapshot"):
        assert tbl in ALLOWED_TABLES, f"missing: {tbl}"
