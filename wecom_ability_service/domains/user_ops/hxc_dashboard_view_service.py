"""用户激活漏斗看板 — 读侧服务

从 ``user_ops_hxc_dashboard_snapshot`` PG 快照表读全量数据 + 汇总,
供 admin 看板页 + 外部 API 复用. 写侧 (聚合刷新) 在
``hxc_dashboard_snapshot_service`` 里, 这里只读不算.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ...db import get_db
from .hxc_dashboard_snapshot_service import (
    FUNNEL_INACTIVE,
    FUNNEL_LABELS,
    FUNNEL_MEMBER_AND_USER,
    FUNNEL_ONLY_MEMBER,
    FUNNEL_USER_NO_MEMBER,
    get_latest_snapshot_meta,
)


def _mask_mobile(phone: str | None) -> str:
    text = str(phone or "")
    if len(text) < 7:
        return text
    return f"{text[:3]}****{text[-4:]}"


def _to_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _bool_tick(value: Any) -> str:
    """三态: True → '✓', False → '✗', None → ''."""
    if value is None:
        return ""
    return "✓" if value else "✗"


def _bool_tick_required(value: Any) -> str:
    """二态: True → '✓', else '✗'."""
    return "✓" if value else "✗"


def list_hxc_dashboard_rows() -> list[dict[str, Any]]:
    """读快照表全量, 返回前端可直接渲染的 dict list (字段名走 snake_case)."""
    rows = get_db().execute(
        """
        SELECT
            mobile,
            phone_match_key,
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
        FROM user_ops_hxc_dashboard_snapshot
        ORDER BY msg_user DESC, mobile ASC
        """
    ).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        funnel = data.get("funnel_state") or FUNNEL_INACTIVE
        consult_used = data.get("consultation_used")
        consult_limit = data.get("consultation_limit")
        consult_usage = (
            f"{consult_used}/{consult_limit}"
            if consult_limit is not None
            else ""
        )
        out.append({
            # 身份 (脱敏)
            "mobile_masked":           _mask_mobile(data.get("mobile")),
            "customer_name":           _to_text(data.get("customer_name")),
            "funnel_state":            funnel,
            "funnel_label":            FUNNEL_LABELS.get(funnel, funnel),
            "external_userid":         _to_text(data.get("external_userid")),
            "owner_userid":            _to_text(data.get("owner_userid")),
            # 来源命中
            "in_lead_pool":            _bool_tick_required(data.get("in_lead_pool")),
            "in_people":               _bool_tick_required(data.get("in_people")),
            "in_questionnaire":        _bool_tick_required(data.get("in_questionnaire")),
            "questionnaires":          _to_text(data.get("questionnaires")),
            "questionnaire_count":     int(data.get("questionnaire_count") or 0),
            "last_questionnaire_at":   _to_iso(data.get("last_questionnaire_at")),
            # CRM
            "is_wecom_added":          _bool_tick(data.get("is_wecom_added")),
            "is_mobile_bound":         _bool_tick(data.get("is_mobile_bound")),
            "class_term_label":        _to_text(data.get("class_term_label")),
            "first_entry_source":      _to_text(data.get("first_entry_source")),
            "last_entry_source":       _to_text(data.get("last_entry_source")),
            "crm_hxc_state":           _to_text(data.get("crm_hxc_state")),
            "crm_created_at":          _to_iso(data.get("crm_created_at")),
            # 黄小璨命中
            "hxc_member_hit":          _bool_tick_required(data.get("hxc_member_hit")),
            "hxc_user_hit":            _bool_tick_required(data.get("hxc_user_hit")),
            "hxc_nickname":            _to_text(data.get("hxc_nickname")),
            "hxc_member_status":       _to_text(data.get("hxc_member_status")),
            "membership_type":         _to_text(data.get("membership_type")),
            "membership_days_left":    data.get("membership_days_left"),
            "membership_end_at":       _to_iso(data.get("membership_end_at")),
            "consult_usage":           consult_usage,
            "membership_source":       _to_text(data.get("membership_source")),
            "hxc_silent_days":         data.get("hxc_silent_days"),
            "hxc_registered_at":       _to_iso(data.get("hxc_registered_at")),
            "hxc_last_login_at":       _to_iso(data.get("hxc_last_login_at")),
            # 行为深度
            "conv_chat":               int(data.get("conv_chat") or 0),
            "conv_consult":            int(data.get("conv_consult") or 0),
            "conv_lesson":             int(data.get("conv_lesson") or 0),
            "msg_user":                int(data.get("msg_user") or 0),
            "msg_ai":                  int(data.get("msg_ai") or 0),
            "consult_completed":       int(data.get("consult_completed") or 0),
            "consult_avg_turn":        float(data["consult_avg_turn"]) if data.get("consult_avg_turn") is not None else None,
            "last_msg_at":             _to_iso(data.get("last_msg_at")),
        })
    return out


def get_dashboard_summary() -> dict[str, Any]:
    """看板顶部 stat card 用 — 总数 / 漏斗分布 / 最后刷新时间."""
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN funnel_state = 'member_and_user' THEN 1 ELSE 0 END) AS member_and_user,
            SUM(CASE WHEN funnel_state = 'only_member'    THEN 1 ELSE 0 END) AS only_member,
            SUM(CASE WHEN funnel_state = 'user_no_member' THEN 1 ELSE 0 END) AS user_no_member,
            SUM(CASE WHEN funnel_state = 'inactive'       THEN 1 ELSE 0 END) AS inactive,
            SUM(CASE WHEN hxc_member_hit THEN 1 ELSE 0 END) AS member_hit,
            SUM(CASE WHEN hxc_user_hit   THEN 1 ELSE 0 END) AS user_hit,
            SUM(CASE WHEN membership_type = 'member' THEN 1 ELSE 0 END) AS member_count,
            SUM(CASE WHEN membership_type = 'trial'  THEN 1 ELSE 0 END) AS trial_count
        FROM user_ops_hxc_dashboard_snapshot
        """
    ).fetchone()
    counts = dict(row) if row else {}
    total = int(counts.get("total") or 0)
    member_hit = int(counts.get("member_hit") or 0)
    user_hit = int(counts.get("user_hit") or 0)
    meta = get_latest_snapshot_meta()
    return {
        "total": total,
        "funnel": {
            FUNNEL_MEMBER_AND_USER: int(counts.get("member_and_user") or 0),
            FUNNEL_ONLY_MEMBER:     int(counts.get("only_member")     or 0),
            FUNNEL_USER_NO_MEMBER:  int(counts.get("user_no_member")  or 0),
            FUNNEL_INACTIVE:        int(counts.get("inactive")        or 0),
        },
        "member_hit": member_hit,
        "member_hit_pct": round(member_hit / total * 100, 1) if total else 0.0,
        "user_hit": user_hit,
        "user_hit_pct": round(user_hit / total * 100, 1) if total else 0.0,
        "member_count": int(counts.get("member_count") or 0),
        "trial_count": int(counts.get("trial_count") or 0),
        "latest_refresh": meta,
    }
