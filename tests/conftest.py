"""顶层 pytest fixtures — PG-only。

2026-05 砍掉 SQLite 后，所有测试**必须**连 PG。本地跑：

    docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16
    DATABASE_URL=postgresql://test:test@localhost:5432/test pytest

CI 上 service container 自动起 PG 并设 DATABASE_URL。

并行执行（pytest-xdist）：``pytest -n auto``。每个 worker 拿一个独立的
``test_<worker_id>`` 数据库——避免并发 truncate / 写竞争。需要 ``DATABASE_URL``
对应的 user 有 ``CREATEDB`` 权限（postgres 官方镜像里 POSTGRES_USER 是
superuser，开箱即用）。

提供的 fixture：
- ``next_app`` / ``next_client``：Next FastAPI 默认测试入口
- ``next_pg_schema``：显式 opt-in 的 Next/Alembic PG schema 测试入口
- ``app`` / ``client``：默认指向 Next FastAPI，测试层不再提供 legacy Flask bridge
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import pytest

# 让 import 能找到项目包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Most production-mode tests exercise data-source behavior, not admin login state.
# Auth-specific tests opt in with AICRM_ADMIN_AUTH_ENFORCED=true.
os.environ.setdefault("AICRM_ADMIN_AUTH_ENFORCED", "false")
os.environ.setdefault("SECRET_KEY", "pytest-secret-key")
os.environ.setdefault("WECHAT_SHOP_CALLBACK_TOKEN", "pytest-wechat-shop-callback-token")


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _fixture_default_runtime_enabled() -> bool:
    return _env_flag("AICRM_PYTEST_FIXTURE_DEFAULT")


def _xdist_worker_id() -> str:
    """xdist 子 worker 是 "gw0" / "gw1" / ...；非并行运行 / 主进程返回 "master"。"""
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


def _resolve_worker_database_url() -> str:
    """把 base ``DATABASE_URL`` 改成 per-worker DB ``test_<worker_id>``。

    主进程（serial 或 xdist master）继续用 base DB。子 worker 各自挂自己的 DB
    避免 truncate / DDL 互相打架。如果 worker DB 还不存在，连 base DB 用 raw
    psycopg 发一次 ``CREATE DATABASE``（postgres 官方镜像里 POSTGRES_USER 是
    superuser，有 CREATEDB 权限）。
    """
    base_url = os.environ.get("DATABASE_URL", "").strip() or os.environ.get("AICRM_TEST_DATABASE_URL", "").strip()
    if not base_url:
        return ""
    worker_id = _xdist_worker_id()
    if worker_id == "master":
        return base_url
    parsed = urlparse(base_url)
    base_db = parsed.path.lstrip("/") or "test"
    worker_db = f"{base_db}_{worker_id}"
    try:
        import psycopg

        bootstrap = psycopg.connect(base_url, autocommit=True)
        cur = bootstrap.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (worker_db,))
        if not cur.fetchone():
            # PG identifiers can't be parameterised; worker_id is "gw\d+" so safe to inline
            cur.execute(f'CREATE DATABASE "{worker_db}"')
        cur.close()
        bootstrap.close()
    except Exception:
        # 起 worker DB 失败时降级回 base DB（serial 模式）
        os.environ["AICRM_TEST_DATABASE_URL"] = base_url
        return base_url
    new_url = urlunparse(parsed._replace(path=f"/{worker_db}"))
    os.environ["AICRM_TEST_DATABASE_URL"] = new_url
    if not _fixture_default_runtime_enabled():
        os.environ["DATABASE_URL"] = new_url
    return new_url


# 测试间需要清理的关键表（FK 反向顺序：子表先清，autouse 用 CASCADE 兜底剩余 FK）
_TABLES_TO_TRUNCATE = [
    # — ai audience ops
    "ai_audience_inbound_webhook_event",
    "ai_audience_package_sender",
    "ai_audience_outbound_subscription",
    "ai_audience_member_event",
    "ai_audience_member_current",
    "ai_audience_package_run",
    "ai_audience_package_dependency",
    "ai_audience_package_version",
    "ai_audience_package",
    # — automation / campaign domain
    "automation_touch_delivery_log",
    "automation_frequency_consumption",
    "automation_frequency_budget",
    "automation_task_plan_v2",
    "automation_stage_entry_v2",
    "automation_membership_v2",
    "automation_event_v2",
    "automation_member_audience_entry",
    "automation_program_member_stage_history",
    "automation_program_admission_attempt",
    "automation_program_member",
    "automation_channel_contact",
    "automation_channel_assignment_event",
    "automation_channel_assignee",
    "automation_program_channel_binding",
    "automation_workflow_node_content_variant",
    "automation_workflow_node_content",
    "automation_workflow_node_transition",
    "automation_workflow_node",
    "automation_workflow_goal",
    "automation_operation_templates",
    "automation_workflow",
    "automation_member",
    "wecom_customer_acquisition_links",
    "automation_program_config_block",
    "automation_program",
    "automation_channel",
    "automation_sop_progress",
    "automation_sop_pool_config",
    "automation_sop_batch_item",
    "automation_sop_batch",
    "automation_sop_template",
    "automation_agent_run",
    "automation_agent_output",
    "automation_agent_llm_call_log",
    "automation_agent_webhook_item",
    "automation_agent_webhook_batch",
    "automation_agent_runtime_config",
    "automation_focus_send_batch_item",
    "automation_focus_send_batch",
    "automation_agent_skill_call_audit",
    "automation_agent_skill_registry",
    "automation_agent_prompt_registry",
    "automation_workflow_agent_binding",
    "automation_agent_config",
    "automation_agent_output_export_job",
    "automation_agent_router_config",
    "automation_laohuang_chat_job",
    "automation_reply_monitor_queue",
    "automation_reply_monitor_config",
    "automation_message_activity_sync_item",
    "automation_message_activity_sync_run",
    # — campaigns
    "campaign_members",
    "campaign_steps",
    "campaign_segments",
    "campaigns",
    # — cloud orchestrator
    "cloud_approval_tokens",
    "cloud_broadcast_plans",
    "cloud_agent_audit_log",
    # — segments + value
    "segments",
    "customer_value_segment_history",
    "customer_value_segment_current",
    "customer_marketing_state_history",
    "customer_marketing_state_current",
    # signup_conversion_question_rules / signup_conversion_config 已合入
    # marketing_automation_question_rules / marketing_automation_configs（下面列出），
    # PG schema 里不再有这两张表。
    # — libraries
    "image_library",
    "miniprogram_library",
    # — questionnaire
    "questionnaire_external_push_logs",
    "questionnaire_scrm_apply_logs",
    "legacy_webhook_cleanup_audit",
    "legacy_webhook_deprecation_registry",
    "questionnaire_submission_answers",
    "questionnaire_submissions",
    "questionnaire_options",
    "questionnaire_questions",
    "questionnaire_score_rules",
    "questionnaires",
    "external_push_delivery",
    "internal_event_consumer_attempt",
    "internal_event_consumer_run",
    "internal_event",
    "external_effect_attempt",
    "external_effect_test_receipt",
    "external_effect_job",
    "external_push_config",
    "domain_event_outbox",
    "wechat_pay_product_page_slices",
    "wechat_pay_products",
    "wechat_pay_order_export_jobs",
    "wechat_pay_refunds",
    "wechat_pay_order_events",
    "wechat_pay_orders",
    "alipay_pay_order_events",
    "alipay_pay_orders",
    # — admin / auth
    "admin_users",
    # admin_wecom_directory_member 不在 PG schema 中（WeCom 目录走 admin_users）
    "owner_role_map",
    "routing_rule_config",
    "wechat_pay_order_events",
    "wechat_pay_orders",
    "alipay_pay_order_events",
    "alipay_pay_orders",
    "app_settings",
    "mcp_tool_settings",
    # — contacts / identity
    "contacts",
    "external_contact_bindings",
    "sidebar_customer_profile_fields",
    "wecom_external_contact_identity_map",
    "wecom_external_contact_follow_users",
    "wecom_external_contact_event_logs",
    "contact_tags",
    "wecom_corp_tags",
    "wecom_corp_tag_groups",
    "group_chats",
    # group_chat_members 不在 PG schema 中（成员信息嵌入 group_chats.raw_payload）
    "people",
    "class_user_status_current",
    "class_user_status_history",
    # — user_ops
    "user_ops_huangxiaocan_activation_source",
    "user_ops_activation_status_source",
    "signup_tag_rules",
    "marketing_automation_question_rules",
    "marketing_automation_configs",
    "class_term_tag_mapping",
    # — 激活漏斗看板 (alembic 0010-0011)
    "user_ops_hxc_send_config",
    "user_ops_hxc_dashboard_snapshot",
    "user_ops_hxc_dashboard_meta",
    # — P1 group ops workspace drafts
    "group_ops_workspace_gray_window_approvals",
    "group_ops_workspace_allowlist_snapshots",
    "group_ops_workspace_governance_review_steps",
    "group_ops_workspace_governance_reviews",
    "group_ops_workspace_draft_audit_logs",
    "group_ops_workspace_draft_items",
    "group_ops_workspace_drafts",
    # — broadcast_jobs
    "broadcast_job_events",
    "broadcast_jobs",
    # — archive / system
    "archived_messages",
    "archive_sync_state",
    "sync_runs",
    "outbound_tasks",
    "outbound_webhook_deliveries",
    "outbound_event_outbox",
    "admin_operation_logs",
    "owner_migration_results",
    "owner_migration_previews",
    "owner_migration_import_sessions",
    "user_ops_import_batches",
    # customer_pulse_* / followup_orchestrator_* 表已经被 PR #232 删除——不再列入
    # truncate 清单（之前每个 test 跑 8 次注定失败的 SQL，刷 PG error log 还耗时）。
]


def _ensure_pg_url() -> str:
    url = os.environ.get("AICRM_TEST_DATABASE_URL", "").strip() or os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "PG required. Run: "
            "docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test "
            "-e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16; "
            "then DATABASE_URL=postgresql://test:test@localhost:5432/test pytest"
        )
    return url


# 缓存：session 起点 query 出 _TABLES_TO_TRUNCATE 中**真正存在**于当前 worker DB
# 的表名（按原顺序）。每个 test 起点拼成单条 ``TRUNCATE t1, t2, ... CASCADE`` 一次
# round-trip 全部清掉——之前是 N 张表 N 次 round-trip + 不存在表抛 ERROR + 单连接每
# test 重新建。从 ~250ms/test 降到 ~30ms/test。
_truncate_state: dict[str, Any] = {
    "url": "",
    "tables_sql": "",
    "conn": None,  # session-cached autocommit psycopg conn
}


def _close_truncate_conn() -> None:
    conn = _truncate_state.pop("conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def _terminate_idle_test_transactions(url: str) -> None:
    parsed = urlparse(url)
    database_name = parsed.path.lstrip("/")
    if not database_name:
        return
    maintenance_url = urlunparse(parsed._replace(path="/postgres"))
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        return
    conn = psycopg.connect(maintenance_url, autocommit=True)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid()
                  AND state = 'idle in transaction'
                """,
                (database_name,),
            )
        finally:
            cur.close()
    finally:
        conn.close()


def _truncate_cached_tables_once() -> None:
    url = _truncate_state.get("url") or os.environ.get("DATABASE_URL", "").strip()
    sql = _truncate_state.get("tables_sql", "")
    if not url or not sql:
        return
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        return
    for attempt in range(2):
        conn = psycopg.connect(url, autocommit=True)
        try:
            cur = conn.cursor()
            try:
                cur.execute("SET lock_timeout = '5s'")
                cur.execute(sql)
                return
            except Exception:
                if attempt == 0:
                    _terminate_idle_test_transactions(url)
                    continue
                raise
            finally:
                cur.close()
        finally:
            conn.close()


def _run_next_alembic_upgrade(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    _bootstrap_next_test_baseline_schema(url)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        config = Config(str(_ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


def _bootstrap_next_test_baseline_schema(url: str) -> None:
    """Create the minimal post-legacy baseline that Alembic 0001 assumes exists.

    The production migration chain starts with a no-op 0001 baseline because
    production databases already had these tables when Alembic was introduced.
    CI test databases are empty, so tests need a tiny Next-owned bootstrap
    before running later Alembic revisions. Keep this local to tests and do not
    read or import the retired legacy schema runner.
    """
    import psycopg

    statements = [
        """
        CREATE TABLE IF NOT EXISTS conversion_dispatch_log (
            id BIGSERIAL PRIMARY KEY,
            external_userid TEXT NOT NULL DEFAULT '',
            dispatched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_member (
            id BIGSERIAL PRIMARY KEY,
            external_contact_id TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            owner_staff_id TEXT NOT NULL DEFAULT '',
            in_pool BOOLEAN NOT NULL DEFAULT FALSE,
            current_pool TEXT NOT NULL DEFAULT 'removed',
            follow_type TEXT NOT NULL DEFAULT '',
            current_audience_code TEXT NOT NULL DEFAULT 'pending_questionnaire',
            questionnaire_status TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL DEFAULT '',
            last_ai_push_at TEXT NOT NULL DEFAULT '',
            ai_cooldown_until TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_channel (
            id BIGSERIAL PRIMARY KEY,
            channel_type TEXT NOT NULL DEFAULT 'qrcode',
            carrier_type TEXT NOT NULL DEFAULT 'qrcode',
            channel_name TEXT NOT NULL DEFAULT '',
            channel_code TEXT NOT NULL DEFAULT '',
            scene_value TEXT NOT NULL DEFAULT '',
            qr_url TEXT NOT NULL DEFAULT '',
            qr_ticket TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            owner_staff_id TEXT NOT NULL DEFAULT '',
            customer_channel TEXT NOT NULL DEFAULT '',
            link_url TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            welcome_message TEXT NOT NULL DEFAULT '',
            welcome_image_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            welcome_miniprogram_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            welcome_attachment_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            auto_accept_friend BOOLEAN NOT NULL DEFAULT FALSE,
            entry_tag_id TEXT NOT NULL DEFAULT '',
            entry_tag_name TEXT NOT NULL DEFAULT '',
            entry_tag_group_name TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_channel_contact (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL DEFAULT 0,
            external_contact_id TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            owner_staff_id TEXT NOT NULL DEFAULT '',
            enter_count INTEGER NOT NULL DEFAULT 1,
            first_channel_entered_at TIMESTAMPTZ,
            last_channel_entered_at TIMESTAMPTZ,
            source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'automation_channel_contact'
                  AND column_name = 'external_contact_id'
            ) THEN
                CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_channel_contact_external
                ON automation_channel_contact(channel_id, external_contact_id)
                WHERE external_contact_id <> '';
            END IF;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_ai_push_log (
            id BIGSERIAL PRIMARY KEY,
            member_id BIGINT NOT NULL DEFAULT 0,
            pushed_at TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_touch_delivery_log (
            id BIGSERIAL PRIMARY KEY,
            member_id BIGINT NOT NULL DEFAULT 0,
            trace_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            sent_at TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS outbound_tasks (
            id BIGSERIAL PRIMARY KEY,
            trace_id TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_agent_run (
            id BIGSERIAL PRIMARY KEY,
            trace_id TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_agent_config (
            id BIGSERIAL PRIMARY KEY,
            agent_code TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            scenario_code TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_workflow (
            id BIGSERIAL PRIMARY KEY,
            review_status TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_sop_template (
            id BIGSERIAL PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS radar_links (
            id BIGSERIAL PRIMARY KEY,
            code TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            target_type TEXT NOT NULL DEFAULT 'link',
            media_item_id TEXT NOT NULL DEFAULT '',
            deleted_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_chats (
            chat_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            notice TEXT NOT NULL DEFAULT '',
            member_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            create_time TEXT NOT NULL DEFAULT '',
            dismissed_at TEXT NOT NULL DEFAULT '',
            raw_payload TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS people (
            id BIGSERIAL PRIMARY KEY,
            mobile TEXT NOT NULL DEFAULT '',
            third_party_user_id TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS external_contact_bindings (
            external_userid TEXT PRIMARY KEY,
            person_id TEXT,
            first_owner_userid TEXT NOT NULL DEFAULT '',
            last_owner_userid TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wecom_external_contact_identity_map (
            id BIGSERIAL PRIMARY KEY,
            external_userid TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            openid TEXT NOT NULL DEFAULT '',
            follow_user_userid TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wecom_external_contact_follow_users (
            id BIGSERIAL PRIMARY KEY,
            external_userid TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            relation_status TEXT NOT NULL DEFAULT 'active',
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            remark TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crm_user_identity (
            unionid TEXT PRIMARY KEY,
            primary_external_userid TEXT NOT NULL DEFAULT '',
            external_userids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            primary_openid TEXT NOT NULL DEFAULT '',
            openids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            mobile TEXT NOT NULL DEFAULT '',
            mobile_normalized TEXT NOT NULL DEFAULT '',
            mobile_verified BOOLEAN NOT NULL DEFAULT FALSE,
            mobile_source TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            remark TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            avatar TEXT NOT NULL DEFAULT '',
            gender INTEGER,
            profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            primary_owner_userid TEXT NOT NULL DEFAULT '',
            follow_users_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            legacy_person_id TEXT NOT NULL DEFAULT '',
            legacy_identity_map_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            legacy_sources_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            identity_status TEXT NOT NULL DEFAULT 'active',
            unionid_resolved_at TIMESTAMPTZ,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_polled_at TIMESTAMPTZ,
            next_poll_at TIMESTAMPTZ,
            poll_attempt_count INTEGER NOT NULL DEFAULT 0,
            last_poll_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crm_user_identity_resolution_queue (
            id BIGSERIAL PRIMARY KEY,
            source_type TEXT NOT NULL DEFAULT '',
            source_key TEXT NOT NULL DEFAULT '',
            source_table TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            corp_id TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            openid TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            resolved_unionid TEXT NOT NULL DEFAULT '',
            conflict_reason TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            next_attempt_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_user_identity_resolution_queue_pending_source
        ON crm_user_identity_resolution_queue (source_type, source_key)
        WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
        """,
        """
        CREATE TABLE IF NOT EXISTS questionnaires (
            id BIGSERIAL PRIMARY KEY,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questionnaire_submissions (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            respondent_key TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            follow_user_userid TEXT NOT NULL DEFAULT '',
            mobile_snapshot TEXT NOT NULL DEFAULT '',
            source_channel TEXT NOT NULL DEFAULT '',
            campaign_id TEXT NOT NULL DEFAULT '',
            staff_id TEXT NOT NULL DEFAULT '',
            total_score INTEGER NOT NULL DEFAULT 0,
            final_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            assessment_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_token TEXT NOT NULL DEFAULT '',
            submitted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questionnaire_questions (
            id BIGSERIAL PRIMARY KEY,
            questionnaire_id BIGINT NOT NULL DEFAULT 0,
            type TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            required BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            placeholder_text TEXT NOT NULL DEFAULT '',
            assessment_dimension_key TEXT NOT NULL DEFAULT '',
            sidebar_profile_field TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questionnaire_submission_answers (
            id BIGSERIAL PRIMARY KEY,
            submission_id BIGINT NOT NULL DEFAULT 0,
            question_id BIGINT NOT NULL DEFAULT 0,
            question_type TEXT NOT NULL DEFAULT '',
            question_title_snapshot TEXT NOT NULL DEFAULT '',
            selected_option_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_option_texts_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_option_scores_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_option_tags_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            text_value TEXT NOT NULL DEFAULT '',
            score_contribution DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_products (
            id BIGSERIAL PRIMARY KEY,
            product_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'draft',
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            cta_text TEXT NOT NULL DEFAULT '立即报名',
            require_mobile BOOLEAN NOT NULL DEFAULT FALSE,
            lead_program_id BIGINT,
            lead_channel_id BIGINT,
            completion_redirect_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            completion_redirect_url TEXT NOT NULL DEFAULT '',
            completion_target_json JSONB,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        ALTER TABLE wechat_pay_products
        ADD COLUMN IF NOT EXISTS completion_redirect_enabled BOOLEAN NOT NULL DEFAULT FALSE
        """,
        """
        ALTER TABLE wechat_pay_products
        ADD COLUMN IF NOT EXISTS completion_redirect_url TEXT NOT NULL DEFAULT ''
        """,
        """
        ALTER TABLE wechat_pay_products
        ADD COLUMN IF NOT EXISTS completion_target_json JSONB
        """,
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_orders (
            id BIGSERIAL PRIMARY KEY,
            out_trade_no TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            order_source TEXT NOT NULL DEFAULT '',
            client_order_ref TEXT NOT NULL DEFAULT '',
            product_code TEXT NOT NULL DEFAULT '',
            product_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            unionid TEXT NOT NULL DEFAULT '',
            payer_name_snapshot TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'created',
            trade_state TEXT NOT NULL DEFAULT '',
            prepay_id TEXT NOT NULL DEFAULT '',
            bank_type TEXT NOT NULL DEFAULT '',
            payer_total INTEGER NOT NULL DEFAULT 0,
            success_url TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            notify_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_error TEXT NOT NULL DEFAULT '',
            expires_at TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            refunded_amount_total INTEGER NOT NULL DEFAULT 0,
            refund_status TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_refunds (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL DEFAULT 0,
            out_trade_no TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            out_refund_no TEXT NOT NULL DEFAULT '',
            refund_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            refund_amount_total INTEGER NOT NULL DEFAULT 0,
            order_amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT '',
            requested_by TEXT NOT NULL DEFAULT '',
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_order_events (
            id BIGSERIAL PRIMARY KEY,
            out_trade_no TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            trade_state TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    conn = psycopg.connect(url, autocommit=True)
    try:
        cur = conn.cursor()
        try:
            for statement in statements:
                cur.execute(statement)
        finally:
            cur.close()
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema_once():
    """Next/Alembic schema setup（每个 xdist worker 各跑一次）：

    1. 路由到 per-worker DB（``test_<worker_id>``，主进程仍用 base ``test``）
    2. 跑 Alembic migrations 到 head
    3. 缓存 ``_TABLES_TO_TRUNCATE`` 里**真正存在**的表名 → 后续 per-test
       truncate 一次性 ``TRUNCATE t1, t2, ...`` 单 SQL 跑完
    """
    url = _resolve_worker_database_url()
    if not url:
        yield
        return
    os.environ["AICRM_TEST_DATABASE_URL"] = url
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        yield
        return
    _run_next_alembic_upgrade(url)

    # 过滤出真存在的表，拼成单条 TRUNCATE。原顺序保留没意义（CASCADE 会自动处理 FK），
    # 但 information_schema 查一次省得每 test 抛 N 个 "relation does not exist"。
    probe = psycopg.connect(url, autocommit=True)
    pcur = probe.cursor()
    placeholders = ", ".join(["%s"] * len(_TABLES_TO_TRUNCATE))
    pcur.execute(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = 'public' AND table_name IN ({placeholders})",
        tuple(_TABLES_TO_TRUNCATE),
    )
    existing = {row[0] for row in pcur.fetchall()}
    pcur.close()
    probe.close()
    ordered = [t for t in _TABLES_TO_TRUNCATE if t in existing]
    _truncate_state["url"] = url
    _truncate_state["tables_sql"] = (
        f"TRUNCATE TABLE {', '.join(ordered)} RESTART IDENTITY CASCADE"
        if ordered
        else ""
    )
    if _fixture_default_runtime_enabled():
        os.environ.pop("DATABASE_URL", None)
    yield
    _close_truncate_conn()


@pytest.fixture(autouse=True)
def _truncate_before_each_test():
    """每个 test 起点单条 TRUNCATE 清完所有缓存的表。

    覆盖**所有** test，不管它用顶层 ``app`` fixture 还是自己的 ``app`` fixture。
    复用 session 级别 autocommit 连接（建一次用一辈子）；只在断连后重建。
    """
    url = _truncate_state.get("url") or os.environ.get("DATABASE_URL", "").strip()
    sql = _truncate_state.get("tables_sql", "")
    if not url or not sql:
        yield
        return
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        yield
        return
    conn = _truncate_state.get("conn")
    if conn is None or getattr(conn, "closed", True):
        conn = psycopg.connect(url, autocommit=True)
        cur = conn.cursor()
        try:
            cur.execute("SET lock_timeout = '5s'")
        except Exception:
            pass
        cur.close()
        _truncate_state["conn"] = conn
    cur = conn.cursor()
    try:
        cur.execute(sql)
    except Exception:
        # 断连 / 死锁 / 上个 test 遗留 idle transaction：弃旧连接，清 blocker 后重试。
        try:
            conn.close()
        except Exception:
            pass
        _truncate_state["conn"] = None
        _terminate_idle_test_transactions(url)
        retry_conn = psycopg.connect(url, autocommit=True)
        retry_cur = retry_conn.cursor()
        try:
            retry_cur.execute("SET lock_timeout = '5s'")
            retry_cur.execute(sql)
            _truncate_state["conn"] = retry_conn
        except Exception:
            try:
                retry_conn.close()
            except Exception:
                pass
            raise
        finally:
            try:
                retry_cur.close()
            except Exception:
                pass
    finally:
        try:
            cur.close()
        except Exception:
            pass
    yield


@pytest.fixture
def next_pg_schema(monkeypatch):
    """Explicit opt-in for tests that require the Next/Alembic PG schema."""
    monkeypatch.setenv("DATABASE_URL", _ensure_pg_url())
    return None


@pytest.fixture
def next_app(monkeypatch, request):
    if _fixture_default_runtime_enabled():
        if "next_pg_schema" in request.fixturenames:
            monkeypatch.setenv("DATABASE_URL", _ensure_pg_url())
        else:
            monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    from aicrm_next.main import create_app

    return create_app()


@pytest.fixture
def next_client(next_app):
    from fastapi.testclient import TestClient

    return TestClient(next_app)


@pytest.fixture
def app(next_app):
    """Default app fixture is Next-native; legacy Flask tests must opt in."""
    return next_app


@pytest.fixture
def client(next_client):
    """Default client fixture is Next-native; legacy Flask tests must opt in."""
    return next_client
