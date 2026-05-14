"""user_ops_hxc_dashboard_snapshot — 用户激活漏斗看板快照表

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-12

CRM 三表(`user_ops_lead_pool_current`+ `people` + `questionnaire_submissions`)的
手机号并集 × 黄小璨 MySQL 用户/会员/会话/消息聚合, 整表写入这张快照表;
定时 30 分钟刷一次, 供:

- ``/admin/user-ops/hxc-dashboard``  管理后台看板页
- ``/api/v1/hxc-dashboard/list``     外部 API 接口
- CSV 导出 / 漏斗分析 (已激活并打开 / 仅激活未打开 / 注册但无会员 / 未激活)

每行 = 1 个手机号 = 1 个客户; 每次刷新先 TRUNCATE 再批量 INSERT。
"""
from __future__ import annotations

from alembic import op


revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_ops_hxc_dashboard_snapshot (
            id                       BIGSERIAL PRIMARY KEY,
            mobile                   TEXT NOT NULL UNIQUE,
            phone_match_key          TEXT NOT NULL DEFAULT '',

            -- CRM 三表来源命中
            in_lead_pool             BOOLEAN NOT NULL DEFAULT FALSE,
            in_people                BOOLEAN NOT NULL DEFAULT FALSE,
            in_questionnaire         BOOLEAN NOT NULL DEFAULT FALSE,

            -- CRM lead_pool 字段
            customer_name            TEXT NOT NULL DEFAULT '',
            external_userid          TEXT NOT NULL DEFAULT '',
            owner_userid             TEXT NOT NULL DEFAULT '',
            is_wecom_added           BOOLEAN,
            is_mobile_bound          BOOLEAN,
            class_term_no            INTEGER,
            class_term_label         TEXT NOT NULL DEFAULT '',
            first_entry_source       TEXT NOT NULL DEFAULT '',
            last_entry_source        TEXT NOT NULL DEFAULT '',
            crm_hxc_state            TEXT NOT NULL DEFAULT '',
            crm_created_at           DATE,

            -- 问卷聚合
            questionnaires           TEXT NOT NULL DEFAULT '',
            questionnaire_count      INTEGER NOT NULL DEFAULT 0,
            last_questionnaire_at    DATE,

            -- 黄小璨命中 / 漏斗
            hxc_member_hit           BOOLEAN NOT NULL DEFAULT FALSE,
            hxc_user_hit             BOOLEAN NOT NULL DEFAULT FALSE,
            funnel_state             TEXT NOT NULL DEFAULT 'inactive',

            -- 黄小璨用户 (new_version_users)
            hxc_user_id              TEXT NOT NULL DEFAULT '',
            hxc_nickname             TEXT NOT NULL DEFAULT '',
            hxc_member_status        TEXT NOT NULL DEFAULT '',
            hxc_registered_at        TIMESTAMPTZ,
            hxc_last_login_at        TIMESTAMPTZ,
            hxc_silent_days          INTEGER,

            -- 黄小璨会员 (new_version_memberships)
            membership_type          TEXT NOT NULL DEFAULT '',
            membership_status        TEXT NOT NULL DEFAULT '',
            membership_end_at        TIMESTAMPTZ,
            membership_days_left     INTEGER,
            membership_source        TEXT NOT NULL DEFAULT '',
            consultation_used        INTEGER,
            consultation_limit       INTEGER,

            -- 黄小璨行为深度
            conv_chat                INTEGER NOT NULL DEFAULT 0,
            conv_consult             INTEGER NOT NULL DEFAULT 0,
            conv_lesson              INTEGER NOT NULL DEFAULT 0,
            msg_user                 INTEGER NOT NULL DEFAULT 0,
            msg_ai                   INTEGER NOT NULL DEFAULT 0,
            consult_completed        INTEGER NOT NULL DEFAULT 0,
            consult_avg_turn         NUMERIC(6, 2),
            last_msg_at              TIMESTAMPTZ,

            -- 元数据
            refreshed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # 看板高频筛选 → 索引
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_funnel "
        "ON user_ops_hxc_dashboard_snapshot (funnel_state)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_owner "
        "ON user_ops_hxc_dashboard_snapshot (owner_userid) WHERE owner_userid <> ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_class_term "
        "ON user_ops_hxc_dashboard_snapshot (class_term_label) WHERE class_term_label <> ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_membership_type "
        "ON user_ops_hxc_dashboard_snapshot (membership_type) WHERE membership_type <> ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_refreshed_at "
        "ON user_ops_hxc_dashboard_snapshot (refreshed_at DESC)"
    )

    # 刷新元信息单行表(用于看板顶部"上次刷新时间"+ 刷新历史)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_ops_hxc_dashboard_meta (
            id              BIGSERIAL PRIMARY KEY,
            started_at      TIMESTAMPTZ NOT NULL,
            finished_at     TIMESTAMPTZ,
            status          TEXT NOT NULL DEFAULT 'running',
            row_count       INTEGER NOT NULL DEFAULT 0,
            member_hit      INTEGER NOT NULL DEFAULT 0,
            user_hit        INTEGER NOT NULL DEFAULT 0,
            only_member     INTEGER NOT NULL DEFAULT 0,
            error_message   TEXT NOT NULL DEFAULT '',
            trigger_source  TEXT NOT NULL DEFAULT 'scheduled'
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hxc_snapshot_meta_started_at "
        "ON user_ops_hxc_dashboard_meta (started_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_meta_started_at")
    op.execute("DROP TABLE IF EXISTS user_ops_hxc_dashboard_meta")
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_refreshed_at")
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_membership_type")
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_class_term")
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_owner")
    op.execute("DROP INDEX IF EXISTS idx_hxc_snapshot_funnel")
    op.execute("DROP TABLE IF EXISTS user_ops_hxc_dashboard_snapshot")
