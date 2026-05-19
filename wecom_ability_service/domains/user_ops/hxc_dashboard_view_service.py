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
from .phone_helpers import mask_mobile


def _mask_mobile(phone: str | None) -> str:
    return mask_mobile(phone)


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
            hxc_member_level, hxc_member_expires_at,
            hxc_onboard_status, hxc_assessment_status,
            hxc_growth_onboard_status, hxc_first_login_at,
            membership_type, membership_status,
            membership_end_at, membership_days_left, membership_source,
            consultation_used, consultation_limit,
            conv_chat, conv_consult, conv_lesson,
            msg_user, msg_ai,
            consult_completed, consult_avg_turn, last_msg_at,
            identity_stage, monthly_income_range, business_focus, ai_usage_status,
            main_pain_points, ai_pain_points, core_painful_scenario, focus_topics,
            persona_sketch, interaction_style, communication_style, background_confidence,
            main_line_type, main_line_stage, main_line_tier,
            main_line_confirmed_at, main_line_desc, main_line_issue,
            assessment_count, latest_assessment_status, latest_assessment_score,
            latest_assessment_phase, latest_assessment_sub_type,
            latest_assessment_completed_at, assessment_dimension_scores,
            subscription_tier, subscription_expires_at, subscription_quota,
            subscription_used, subscription_period_start,
            last_activation_sku_code, last_activation_new_tier,
            last_activation_source, last_activation_at,
            active_goals_count, active_paths_count, current_milestone_max,
            active_tasks_count, completed_tasks_count,
            task_checkin_count, last_task_checkin_at,
            last_task_checkin_mood, last_task_checkin_state_score,
            next_review_at, last_reviewed_at, review_schedule_status,
            last_recent_event_at, last_recent_event_type,
            recommended_topic_status, recommended_topic_generated_at,
            topic_summary_count, last_topic_summary_at, last_topic_summary_title,
            primary_role, biz_score, inner_score, trust_score,
            trust_tier, clarity_score, role_mode,
            growth_credit_balance, growth_credit_period_granted,
            growth_credit_period_used, growth_credit_period_ends_at,
            webhook_questionnaire_count, last_webhook_questionnaire_at,
            last_webhook_questionnaire_status,
            crm_chat_job_count, crm_chat_done_count, crm_chat_failed_count,
            last_crm_chat_job_status, last_crm_chat_job_at,
            last_crm_chat_callback_status
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
            "hxc_member_level":        _to_text(data.get("hxc_member_level")),
            "hxc_member_expires_at":   _to_iso(data.get("hxc_member_expires_at")),
            "hxc_onboard_status":      _to_text(data.get("hxc_onboard_status")),
            "hxc_assessment_status":   _to_text(data.get("hxc_assessment_status")),
            "hxc_growth_onboard_status": _to_text(data.get("hxc_growth_onboard_status")),
            "hxc_first_login_at":      _to_iso(data.get("hxc_first_login_at")),
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
            # V6 画像 / 诊断 / 测评
            "identity_stage":          _to_text(data.get("identity_stage")),
            "monthly_income_range":    _to_text(data.get("monthly_income_range")),
            "business_focus":          _to_text(data.get("business_focus")),
            "ai_usage_status":         _to_text(data.get("ai_usage_status")),
            "main_pain_points":        _to_text(data.get("main_pain_points")),
            "ai_pain_points":          _to_text(data.get("ai_pain_points")),
            "core_painful_scenario":   _to_text(data.get("core_painful_scenario")),
            "focus_topics":            _to_text(data.get("focus_topics")),
            "persona_sketch":          _to_text(data.get("persona_sketch")),
            "interaction_style":       _to_text(data.get("interaction_style")),
            "communication_style":     _to_text(data.get("communication_style")),
            "background_confidence":   _to_text(data.get("background_confidence")),
            "main_line_type":          _to_text(data.get("main_line_type")),
            "main_line_stage":         _to_text(data.get("main_line_stage")),
            "main_line_tier":          _to_text(data.get("main_line_tier")),
            "main_line_confirmed_at":  _to_iso(data.get("main_line_confirmed_at")),
            "main_line_desc":          _to_text(data.get("main_line_desc")),
            "main_line_issue":         _to_text(data.get("main_line_issue")),
            "assessment_count":        int(data.get("assessment_count") or 0),
            "latest_assessment_status": _to_text(data.get("latest_assessment_status")),
            "latest_assessment_score": data.get("latest_assessment_score"),
            "latest_assessment_phase": _to_text(data.get("latest_assessment_phase")),
            "latest_assessment_sub_type": _to_text(data.get("latest_assessment_sub_type")),
            "latest_assessment_completed_at": _to_iso(data.get("latest_assessment_completed_at")),
            "assessment_dimension_scores": _to_text(data.get("assessment_dimension_scores")),
            # V6 订阅 / 成长主线 / 复盘
            "subscription_tier":       _to_text(data.get("subscription_tier")),
            "subscription_expires_at": _to_iso(data.get("subscription_expires_at")),
            "subscription_quota":      data.get("subscription_quota"),
            "subscription_used":       data.get("subscription_used"),
            "subscription_period_start": _to_iso(data.get("subscription_period_start")),
            "last_activation_sku_code": _to_text(data.get("last_activation_sku_code")),
            "last_activation_new_tier": _to_text(data.get("last_activation_new_tier")),
            "last_activation_source":  _to_text(data.get("last_activation_source")),
            "last_activation_at":      _to_iso(data.get("last_activation_at")),
            "active_goals_count":      int(data.get("active_goals_count") or 0),
            "active_paths_count":      int(data.get("active_paths_count") or 0),
            "current_milestone_max":   data.get("current_milestone_max"),
            "active_tasks_count":      int(data.get("active_tasks_count") or 0),
            "completed_tasks_count":   int(data.get("completed_tasks_count") or 0),
            "task_checkin_count":      int(data.get("task_checkin_count") or 0),
            "last_task_checkin_at":    _to_iso(data.get("last_task_checkin_at")),
            "last_task_checkin_mood":  _to_text(data.get("last_task_checkin_mood")),
            "last_task_checkin_state_score": data.get("last_task_checkin_state_score"),
            "next_review_at":          _to_iso(data.get("next_review_at")),
            "last_reviewed_at":        _to_iso(data.get("last_reviewed_at")),
            "review_schedule_status":  _to_text(data.get("review_schedule_status")),
            "last_recent_event_at":    _to_iso(data.get("last_recent_event_at")),
            "last_recent_event_type":  _to_text(data.get("last_recent_event_type")),
            "recommended_topic_status": _to_text(data.get("recommended_topic_status")),
            "recommended_topic_generated_at": _to_iso(data.get("recommended_topic_generated_at")),
            "topic_summary_count":     int(data.get("topic_summary_count") or 0),
            "last_topic_summary_at":   _to_iso(data.get("last_topic_summary_at")),
            "last_topic_summary_title": _to_text(data.get("last_topic_summary_title")),
            "primary_role":            _to_text(data.get("primary_role")),
            "biz_score":               data.get("biz_score"),
            "inner_score":             data.get("inner_score"),
            "trust_score":             data.get("trust_score"),
            "trust_tier":              _to_text(data.get("trust_tier")),
            "clarity_score":           data.get("clarity_score"),
            "role_mode":               _to_text(data.get("role_mode")),
            "growth_credit_balance":   data.get("growth_credit_balance"),
            "growth_credit_period_granted": data.get("growth_credit_period_granted"),
            "growth_credit_period_used": data.get("growth_credit_period_used"),
            "growth_credit_period_ends_at": _to_iso(data.get("growth_credit_period_ends_at")),
            # H5 / 外部桥接辅助列
            "webhook_questionnaire_count": int(data.get("webhook_questionnaire_count") or 0),
            "last_webhook_questionnaire_at": _to_iso(data.get("last_webhook_questionnaire_at")),
            "last_webhook_questionnaire_status": _to_text(data.get("last_webhook_questionnaire_status")),
            "crm_chat_job_count":      int(data.get("crm_chat_job_count") or 0),
            "crm_chat_done_count":     int(data.get("crm_chat_done_count") or 0),
            "crm_chat_failed_count":   int(data.get("crm_chat_failed_count") or 0),
            "last_crm_chat_job_status": _to_text(data.get("last_crm_chat_job_status")),
            "last_crm_chat_job_at":    _to_iso(data.get("last_crm_chat_job_at")),
            "last_crm_chat_callback_status": _to_text(data.get("last_crm_chat_callback_status")),
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
            SUM(CASE WHEN membership_type = 'trial'  THEN 1 ELSE 0 END) AS trial_count,
            SUM(CASE WHEN latest_assessment_status = 'completed' THEN 1 ELSE 0 END) AS assessment_completed_count,
            SUM(CASE WHEN active_goals_count > 0 THEN 1 ELSE 0 END) AS users_with_active_goals,
            SUM(CASE WHEN active_paths_count > 0 THEN 1 ELSE 0 END) AS users_with_active_paths,
            SUM(CASE WHEN subscription_tier IN ('standard', 'premium') THEN 1 ELSE 0 END) AS paid_subscription_count
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
        "assessment_completed_count": int(counts.get("assessment_completed_count") or 0),
        "users_with_active_goals": int(counts.get("users_with_active_goals") or 0),
        "users_with_active_paths": int(counts.get("users_with_active_paths") or 0),
        "paid_subscription_count": int(counts.get("paid_subscription_count") or 0),
        "latest_refresh": meta,
    }
