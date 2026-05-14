"""用户激活漏斗看板 — CRM × 黄小璨 数据聚合 → PG 快照表

每次调用 :func:`refresh_hxc_dashboard_snapshot` 都会:

1. 从 CRM (PG) 拉 ``user_ops_lead_pool_current`` ∪ ``user_ops_pool_current`` ∪
   ``people`` ∪ 激活/开通问卷的 ``questionnaire_submissions`` 四表手机号并集,
   带上 lead_pool / pool_current 字段和问卷聚合字段.
   - ``external_userid`` / ``customer_name`` / ``owner_userid`` 三个客户身份字段
     用 ``COALESCE(pool_current, lead_pool)`` 双源合并: pool_current 是客户档案
     主表 (覆盖更全, ~6300 个 external_userid), lead_pool 是线索池 (~1200 个).
     早期版本只查 lead_pool 会让"已加企微但首次入口不在线索池"的 100+ 个客户在
     看板里 customer_name / external_userid 空白.
2. 从黄小璨 (MySQL) 拉 ``new_version_users`` / ``new_version_memberships`` /
   ``new_version_consultation_states`` / ``new_version_conversations`` /
   ``new_version_messages`` 按手机号聚合的指标.
3. 在 Python 侧按 mobile merge, 推算 ``funnel_state`` (4 个互斥分类).
4. ``TRUNCATE`` + 批量 ``INSERT`` 写入 ``user_ops_hxc_dashboard_snapshot``,
   并把本次刷新汇总写入 ``user_ops_hxc_dashboard_meta``.

复用 ``message_activity_client`` 的 ``MESSAGE_ACTIVITY_DB_*`` 配置连黄小璨 MySQL,
不引入新的连接源.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from ...db import get_db
from ..automation_conversion.message_activity_client import (
    _db_config,
    get_message_activity_db_status,
)


# ── 漏斗状态枚举 (DB 用英文; UI 层翻译成中文) ──

FUNNEL_MEMBER_AND_USER = "member_and_user"   # 已激活并打开
FUNNEL_ONLY_MEMBER = "only_member"           # 仅激活未打开 (重点拉回人群)
FUNNEL_USER_NO_MEMBER = "user_no_member"     # 注册但无会员
FUNNEL_INACTIVE = "inactive"                  # 未激活

FUNNEL_LABELS = {
    FUNNEL_MEMBER_AND_USER: "已激活并打开",
    FUNNEL_ONLY_MEMBER: "仅激活未打开",
    FUNNEL_USER_NO_MEMBER: "注册但无会员",
    FUNNEL_INACTIVE: "未激活",
}

# 激活/开通类问卷; 当前固定 4 个, 后续要新增直接改这里
HXC_ACTIVATION_QUESTIONNAIRE_IDS: tuple[int, ...] = (14, 19, 20, 21)


# ── CRM 三表并集 + 问卷聚合 (PG) ──

def _qids_sql_list() -> str:
    """白名单常量直接转成 SQL ``IN (...)`` 列表, 避免 SQL placeholder 兼容性."""
    return "(" + ",".join(str(int(qid)) for qid in HXC_ACTIVATION_QUESTIONNAIRE_IDS) + ")"


def _build_crm_sql() -> str:
    qids = _qids_sql_list()
    return rf"""
WITH all_mobiles AS (
    SELECT mobile FROM user_ops_lead_pool_current
        WHERE mobile ~ '^1[3-9][0-9]{{9}}$'
    UNION
    SELECT mobile FROM user_ops_pool_current
        WHERE mobile ~ '^1[3-9][0-9]{{9}}$'
    UNION
    SELECT mobile FROM people
        WHERE mobile ~ '^1[3-9][0-9]{{9}}$'
    UNION
    SELECT mobile_snapshot FROM questionnaire_submissions
        WHERE questionnaire_id IN {qids}
          AND mobile_snapshot ~ '^1[3-9][0-9]{{9}}$'
),
q AS (
    SELECT
        s.mobile_snapshot AS mobile,
        string_agg(DISTINCT qn.name, ' / ' ORDER BY qn.name) AS questionnaires,
        COUNT(*) AS questionnaire_count,
        MAX(s.submitted_at)::date AS last_questionnaire_at
    FROM questionnaire_submissions s
    JOIN questionnaires qn ON qn.id = s.questionnaire_id
    WHERE s.questionnaire_id IN {qids}
    GROUP BY s.mobile_snapshot
)
SELECT
    am.mobile,
    -- 客户身份三字段双源合并: pool_current 是客户档案主表(更全), lead_pool 兜底
    COALESCE(NULLIF(pc.external_userid, ''), lp.external_userid)         AS external_userid,
    COALESCE(NULLIF(pc.customer_name, ''),  lp.customer_name, '')        AS customer_name,
    COALESCE(NULLIF(pc.owner_userid, ''),   lp.owner_userid, '')         AS owner_userid,
    lp.is_wecom_added,
    lp.is_mobile_bound,
    COALESCE(lp.class_term_no, pc.class_term_no)                         AS class_term_no,
    COALESCE(NULLIF(lp.class_term_label, ''), pc.class_term_label, '')   AS class_term_label,
    COALESCE(lp.first_entry_source, '')                                  AS first_entry_source,
    COALESCE(lp.last_entry_source, '')                                   AS last_entry_source,
    COALESCE(NULLIF(lp.huangxiaocan_activation_state, ''),
             pc.activation_status, '')                                   AS crm_hxc_state,
    COALESCE(lp.created_at, pc.created_at)::date                         AS crm_created_at,
    (lp.mobile IS NOT NULL)                                              AS in_lead_pool,
    (ppl.mobile IS NOT NULL)                                             AS in_people,
    (q.mobile IS NOT NULL)                                               AS in_questionnaire,
    COALESCE(q.questionnaires, '')                                       AS questionnaires,
    COALESCE(q.questionnaire_count, 0)                                   AS questionnaire_count,
    q.last_questionnaire_at
FROM all_mobiles am
LEFT JOIN user_ops_lead_pool_current lp ON lp.mobile = am.mobile
LEFT JOIN user_ops_pool_current pc      ON pc.mobile = am.mobile
LEFT JOIN people ppl                    ON ppl.mobile = am.mobile
LEFT JOIN q                             ON q.mobile  = am.mobile
"""


# ── 黄小璨聚合 SQL (MySQL) ──

_HXC_USERS_SQL = """
SELECT
  u.phone,
  u.id AS hxc_user_id,
  u.nickname AS hxc_nickname,
  u.member_status AS hxc_member_status,
  u.last_login_at,
  u.created_at AS hxc_registered_at,
  CASE WHEN u.last_login_at IS NULL THEN NULL
       ELSE DATEDIFF(NOW(), u.last_login_at) END AS hxc_silent_days,
  COUNT(DISTINCT CASE WHEN c.mode='chat'    THEN c.id END) AS conv_chat,
  COUNT(DISTINCT CASE WHEN c.mode='consult' THEN c.id END) AS conv_consult,
  COUNT(DISTINCT CASE WHEN c.mode='lesson'  THEN c.id END) AS conv_lesson,
  COUNT(CASE WHEN m.role='user'      THEN m.id END) AS msg_user,
  COUNT(CASE WHEN m.role='assistant' THEN m.id END) AS msg_ai,
  MAX(m.created_at) AS last_msg_at
FROM new_version_users u
LEFT JOIN new_version_conversations c ON u.id=c.user_id AND c.is_deleted=0
LEFT JOIN new_version_messages m ON c.id=m.session_id AND m.is_deleted=0
WHERE u.is_deleted=0
  AND u.phone IS NOT NULL
  AND TRIM(u.phone) <> ''
  AND (u.nickname IS NULL OR (u.nickname NOT LIKE '%neo%' AND u.nickname NOT LIKE '%Neo%'))
GROUP BY u.id, u.phone, u.nickname, u.member_status, u.last_login_at, u.created_at
"""

_HXC_MB_SQL = """
SELECT
  mb.phone,
  mb.member_type   AS membership_type,
  mb.status        AS membership_status,
  mb.end_date      AS membership_end_at,
  DATEDIFF(mb.end_date, NOW()) AS membership_days_left,
  mb.consultation_used,
  mb.consultation_limit,
  mb.created_by    AS membership_source
FROM new_version_memberships mb
WHERE mb.phone IS NOT NULL AND mb.phone <> ''
ORDER BY mb.phone, (mb.status='active') DESC, mb.end_date DESC
"""

_HXC_CONSULT_SQL = """
SELECT
  c.user_id,
  SUM(CASE WHEN cs.consultation_status='completed' THEN 1 ELSE 0 END) AS consult_completed,
  ROUND(AVG(cs.turn_count), 2) AS consult_avg_turn
FROM new_version_conversations c
JOIN new_version_consultation_states cs ON c.id=cs.session_id
WHERE c.is_deleted=0
GROUP BY c.user_id
"""


def _funnel_state(user_hit: bool, member_hit: bool) -> str:
    if member_hit and user_hit:
        return FUNNEL_MEMBER_AND_USER
    if member_hit:
        return FUNNEL_ONLY_MEMBER
    if user_hit:
        return FUNNEL_USER_NO_MEMBER
    return FUNNEL_INACTIVE


def _phone_match_key(phone: str) -> str:
    if not phone or len(phone) < 7:
        return ""
    return f"{phone[:3]}_{phone[-4:]}"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _connect_hxc():
    """复用 message_activity_client 的 MESSAGE_ACTIVITY_DB_* 配置."""
    import pymysql
    from pymysql.cursors import DictCursor

    cfg = _db_config()
    return pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"] or 3306),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        connect_timeout=10,
        read_timeout=60,
        autocommit=True,
    )


def _fetch_hxc_index() -> dict[str, dict[str, Any]]:
    """拉黄小璨三段聚合, 按 phone 合并为 dict[phone] = merged row."""
    connection = _connect_hxc()
    try:
        with connection.cursor() as cursor:
            cursor.execute(_HXC_USERS_SQL)
            users_by_phone: dict[str, dict[str, Any]] = {
                row["phone"]: row for row in cursor.fetchall() if row.get("phone")
            }
            cursor.execute(_HXC_MB_SQL)
            mb_by_phone: dict[str, dict[str, Any]] = {}
            for row in cursor.fetchall():
                phone = row.get("phone")
                # ORDER BY 后第一条 = active + 最新到期
                if phone and phone not in mb_by_phone:
                    mb_by_phone[phone] = row
            cursor.execute(_HXC_CONSULT_SQL)
            consult_by_uid: dict[str, dict[str, Any]] = {
                row["user_id"]: row for row in cursor.fetchall() if row.get("user_id")
            }
    finally:
        connection.close()

    merged: dict[str, dict[str, Any]] = {}
    for phone in set(users_by_phone) | set(mb_by_phone):
        row: dict[str, Any] = {"phone": phone}
        user_row = users_by_phone.get(phone) or {}
        mb_row = mb_by_phone.get(phone) or {}
        row["hxc_user_hit"] = bool(user_row)
        row["hxc_member_hit"] = bool(mb_row)
        row.update(user_row)
        row.update(mb_row)
        hxc_user_id = user_row.get("hxc_user_id")
        if hxc_user_id:
            row.update(consult_by_uid.get(hxc_user_id) or {})
        merged[phone] = row
    return merged


def _build_snapshot_row(crm_row: dict[str, Any], hxc_row: dict[str, Any]) -> tuple[Any, ...]:
    phone = crm_row["mobile"]
    user_hit = bool(hxc_row.get("hxc_user_hit"))
    member_hit = bool(hxc_row.get("hxc_member_hit"))
    return (
        phone,
        _phone_match_key(phone),
        bool(crm_row["in_lead_pool"]),
        bool(crm_row["in_people"]),
        bool(crm_row["in_questionnaire"]),
        crm_row["customer_name"] or "",
        crm_row["external_userid"] or "",
        crm_row["owner_userid"] or "",
        crm_row["is_wecom_added"],
        crm_row["is_mobile_bound"],
        crm_row["class_term_no"],
        crm_row["class_term_label"] or "",
        crm_row["first_entry_source"] or "",
        crm_row["last_entry_source"] or "",
        crm_row["crm_hxc_state"] or "",
        crm_row["crm_created_at"],
        crm_row["questionnaires"] or "",
        int(crm_row["questionnaire_count"] or 0),
        crm_row["last_questionnaire_at"],
        member_hit,
        user_hit,
        _funnel_state(user_hit, member_hit),
        hxc_row.get("hxc_user_id") or "",
        hxc_row.get("hxc_nickname") or "",
        hxc_row.get("hxc_member_status") or "",
        hxc_row.get("hxc_registered_at"),
        hxc_row.get("last_login_at"),
        hxc_row.get("hxc_silent_days"),
        hxc_row.get("membership_type") or "",
        hxc_row.get("membership_status") or "",
        hxc_row.get("membership_end_at"),
        hxc_row.get("membership_days_left"),
        hxc_row.get("membership_source") or "",
        hxc_row.get("consultation_used"),
        hxc_row.get("consultation_limit"),
        int(hxc_row.get("conv_chat") or 0),
        int(hxc_row.get("conv_consult") or 0),
        int(hxc_row.get("conv_lesson") or 0),
        int(hxc_row.get("msg_user") or 0),
        int(hxc_row.get("msg_ai") or 0),
        int(hxc_row.get("consult_completed") or 0),
        _to_float(hxc_row.get("consult_avg_turn")),
        hxc_row.get("last_msg_at"),
    )


_INSERT_SQL = """
INSERT INTO user_ops_hxc_dashboard_snapshot (
    mobile, phone_match_key,
    in_lead_pool, in_people, in_questionnaire,
    customer_name, external_userid, owner_userid,
    is_wecom_added, is_mobile_bound,
    class_term_no, class_term_label,
    first_entry_source, last_entry_source,
    crm_hxc_state, crm_created_at,
    questionnaires, questionnaire_count, last_questionnaire_at,
    hxc_member_hit, hxc_user_hit, funnel_state,
    hxc_user_id, hxc_nickname, hxc_member_status,
    hxc_registered_at, hxc_last_login_at, hxc_silent_days,
    membership_type, membership_status,
    membership_end_at, membership_days_left, membership_source,
    consultation_used, consultation_limit,
    conv_chat, conv_consult, conv_lesson,
    msg_user, msg_ai,
    consult_completed, consult_avg_turn, last_msg_at
) VALUES (
    ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?, ?
)
"""


def refresh_hxc_dashboard_snapshot(
    *,
    trigger_source: str = "scheduled",
) -> dict[str, Any]:
    """聚合 CRM × 黄小璨 数据写入快照表. 整表 TRUNCATE + 批量 INSERT."""
    db_status = get_message_activity_db_status()
    if not db_status["configured"]:
        return {
            "ok": False,
            "status": "not_configured",
            "error": "message activity db is not configured",
            "missing_keys": list(db_status.get("missing_keys") or []),
        }

    started_at = dt.datetime.now(dt.timezone.utc)
    db = get_db()

    meta_row = db.execute(
        """
        INSERT INTO user_ops_hxc_dashboard_meta (started_at, status, trigger_source)
        VALUES (?, 'running', ?)
        RETURNING id
        """,
        (started_at, trigger_source),
    ).fetchone()
    meta_id = int(meta_row["id"]) if meta_row else 0
    db.commit()

    try:
        crm_rows = db.execute(_build_crm_sql()).fetchall()

        hxc_index = _fetch_hxc_index()

        snapshot_tuples: list[tuple[Any, ...]] = []
        member_hit = 0
        user_hit = 0
        only_member = 0
        for crm_row in crm_rows:
            phone = crm_row["mobile"]
            hxc_row = hxc_index.get(phone) or {}
            snapshot_tuples.append(_build_snapshot_row(crm_row, hxc_row))
            mh = bool(hxc_row.get("hxc_member_hit"))
            uh = bool(hxc_row.get("hxc_user_hit"))
            member_hit += int(mh)
            user_hit += int(uh)
            if mh and not uh:
                only_member += 1

        db.execute("TRUNCATE TABLE user_ops_hxc_dashboard_snapshot")
        if snapshot_tuples:
            db.executemany(_INSERT_SQL, snapshot_tuples)

        finished_at = dt.datetime.now(dt.timezone.utc)
        db.execute(
            """
            UPDATE user_ops_hxc_dashboard_meta
            SET status='success', finished_at=?,
                row_count=?, member_hit=?, user_hit=?, only_member=?
            WHERE id=?
            """,
            (finished_at, len(snapshot_tuples), member_hit, user_hit, only_member, meta_id),
        )
        db.commit()

        return {
            "ok": True,
            "row_count": len(snapshot_tuples),
            "member_hit": member_hit,
            "user_hit": user_hit,
            "only_member": only_member,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        }
    except Exception as exc:  # pragma: no cover - 真异常路径在集成层处理
        db.rollback()
        finished_at = dt.datetime.now(dt.timezone.utc)
        try:
            db.execute(
                """
                UPDATE user_ops_hxc_dashboard_meta
                SET status='failed', finished_at=?, error_message=?
                WHERE id=?
                """,
                (finished_at, str(exc)[:500], meta_id),
            )
            db.commit()
        except Exception:
            db.rollback()
        return {"ok": False, "status": "failed", "error": str(exc)}


def get_latest_snapshot_meta() -> dict[str, Any]:
    """看板顶部展示用 — 最近一次刷新汇总."""
    row = get_db().execute(
        """
        SELECT
            started_at, finished_at, status,
            row_count, member_hit, user_hit, only_member,
            error_message, trigger_source
        FROM user_ops_hxc_dashboard_meta
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return {"status": "never", "row_count": 0}
    return dict(row)
