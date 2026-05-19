"""hxc_dashboard_v6_growth_columns — 激活漏斗看板 V6 成长能力字段.

Revision ID: 0012
Revises: 0011
"""
from __future__ import annotations

from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("hxc_member_level", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_member_expires_at", "TIMESTAMPTZ"),
    ("hxc_onboard_status", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_assessment_status", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_growth_onboard_status", "TEXT NOT NULL DEFAULT ''"),
    ("hxc_first_login_at", "TIMESTAMPTZ"),
    ("identity_stage", "TEXT NOT NULL DEFAULT ''"),
    ("monthly_income_range", "TEXT NOT NULL DEFAULT ''"),
    ("business_focus", "TEXT NOT NULL DEFAULT ''"),
    ("ai_usage_status", "TEXT NOT NULL DEFAULT ''"),
    ("main_pain_points", "TEXT NOT NULL DEFAULT ''"),
    ("ai_pain_points", "TEXT NOT NULL DEFAULT ''"),
    ("core_painful_scenario", "TEXT NOT NULL DEFAULT ''"),
    ("focus_topics", "TEXT NOT NULL DEFAULT ''"),
    ("persona_sketch", "TEXT NOT NULL DEFAULT ''"),
    ("interaction_style", "TEXT NOT NULL DEFAULT ''"),
    ("communication_style", "TEXT NOT NULL DEFAULT ''"),
    ("background_confidence", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_type", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_stage", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_tier", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_confirmed_at", "TIMESTAMPTZ"),
    ("main_line_desc", "TEXT NOT NULL DEFAULT ''"),
    ("main_line_issue", "TEXT NOT NULL DEFAULT ''"),
    ("assessment_count", "INTEGER NOT NULL DEFAULT 0"),
    ("latest_assessment_status", "TEXT NOT NULL DEFAULT ''"),
    ("latest_assessment_score", "INTEGER"),
    ("latest_assessment_phase", "TEXT NOT NULL DEFAULT ''"),
    ("latest_assessment_sub_type", "TEXT NOT NULL DEFAULT ''"),
    ("latest_assessment_completed_at", "TIMESTAMPTZ"),
    ("assessment_dimension_scores", "TEXT NOT NULL DEFAULT ''"),
    ("subscription_tier", "TEXT NOT NULL DEFAULT ''"),
    ("subscription_expires_at", "TIMESTAMPTZ"),
    ("subscription_quota", "INTEGER"),
    ("subscription_used", "INTEGER"),
    ("subscription_period_start", "DATE"),
    ("last_activation_sku_code", "TEXT NOT NULL DEFAULT ''"),
    ("last_activation_new_tier", "TEXT NOT NULL DEFAULT ''"),
    ("last_activation_source", "TEXT NOT NULL DEFAULT ''"),
    ("last_activation_at", "TIMESTAMPTZ"),
    ("active_goals_count", "INTEGER NOT NULL DEFAULT 0"),
    ("active_paths_count", "INTEGER NOT NULL DEFAULT 0"),
    ("current_milestone_max", "INTEGER"),
    ("active_tasks_count", "INTEGER NOT NULL DEFAULT 0"),
    ("completed_tasks_count", "INTEGER NOT NULL DEFAULT 0"),
    ("task_checkin_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_task_checkin_at", "TIMESTAMPTZ"),
    ("last_task_checkin_mood", "TEXT NOT NULL DEFAULT ''"),
    ("last_task_checkin_state_score", "INTEGER"),
    ("next_review_at", "TIMESTAMPTZ"),
    ("last_reviewed_at", "TIMESTAMPTZ"),
    ("review_schedule_status", "TEXT NOT NULL DEFAULT ''"),
    ("last_recent_event_at", "TIMESTAMPTZ"),
    ("last_recent_event_type", "TEXT NOT NULL DEFAULT ''"),
    ("recommended_topic_status", "TEXT NOT NULL DEFAULT ''"),
    ("recommended_topic_generated_at", "TIMESTAMPTZ"),
    ("topic_summary_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_topic_summary_at", "TIMESTAMPTZ"),
    ("last_topic_summary_title", "TEXT NOT NULL DEFAULT ''"),
    ("primary_role", "TEXT NOT NULL DEFAULT ''"),
    ("biz_score", "INTEGER"),
    ("inner_score", "INTEGER"),
    ("trust_score", "INTEGER"),
    ("trust_tier", "TEXT NOT NULL DEFAULT ''"),
    ("clarity_score", "INTEGER"),
    ("role_mode", "TEXT NOT NULL DEFAULT ''"),
    ("growth_credit_balance", "INTEGER"),
    ("growth_credit_period_granted", "INTEGER"),
    ("growth_credit_period_used", "INTEGER"),
    ("growth_credit_period_ends_at", "TIMESTAMPTZ"),
    ("webhook_questionnaire_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_webhook_questionnaire_at", "TIMESTAMPTZ"),
    ("last_webhook_questionnaire_status", "TEXT NOT NULL DEFAULT ''"),
    ("crm_chat_job_count", "INTEGER NOT NULL DEFAULT 0"),
    ("crm_chat_done_count", "INTEGER NOT NULL DEFAULT 0"),
    ("crm_chat_failed_count", "INTEGER NOT NULL DEFAULT 0"),
    ("last_crm_chat_job_status", "TEXT NOT NULL DEFAULT ''"),
    ("last_crm_chat_job_at", "TIMESTAMPTZ"),
    ("last_crm_chat_callback_status", "TEXT NOT NULL DEFAULT ''"),
)


def upgrade() -> None:
    for name, column_type in _COLUMNS:
        op.execute(
            f"ALTER TABLE user_ops_hxc_dashboard_snapshot "
            f"ADD COLUMN IF NOT EXISTS {name} {column_type}"
        )


def downgrade() -> None:
    for name, _column_type in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE user_ops_hxc_dashboard_snapshot DROP COLUMN IF EXISTS {name}")
