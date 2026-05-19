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
- ``app``：每个 test 一个干净 Flask app + truncate 关键表
- ``client``：``app.test_client()``

老测试以前自己用 ``tmp_path / "test.sqlite3"`` + ``DATABASE_PATH`` 起 SQLite，
迁移到这个顶层 fixture 后只需 ``def test_xxx(app, client):`` 即可。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse, urlunparse

import pytest

# 让 import 能找到项目包
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


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
    base_url = os.environ.get("DATABASE_URL", "").strip()
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
        return base_url
    new_url = urlunparse(parsed._replace(path=f"/{worker_db}"))
    os.environ["DATABASE_URL"] = new_url
    return new_url


# 测试间需要清理的关键表（FK 反向顺序：子表先清，autouse 用 CASCADE 兜底剩余 FK）
_TABLES_TO_TRUNCATE = [
    # — automation / campaign domain
    "automation_touch_delivery_log",
    "automation_frequency_consumption",
    "automation_frequency_budget",
    "automation_workflow_execution_item",
    "automation_workflow_execution",
    "automation_member_audience_entry",
    "automation_workflow_node_content_variant",
    "automation_workflow_node_content",
    "automation_workflow_node_transition",
    "automation_workflow_node",
    "automation_workflow_goal",
    "automation_operation_templates",
    "automation_workflow",
    "automation_event",
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
    "automation_focus_send_batch_item",
    "automation_focus_send_batch",
    "automation_agent_skill_call_audit",
    "automation_agent_skill_registry",
    "automation_agent_prompt_registry",
    "automation_workflow_agent_binding",
    "automation_agent_config",
    "automation_agent_output_export_job",
    "automation_agent_llm_call_log",
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
    "questionnaire_submission_answers",
    "questionnaire_submissions",
    "questionnaire_options",
    "questionnaire_questions",
    "questionnaire_score_rules",
    "questionnaires",
    "wechat_pay_product_page_slices",
    "wechat_pay_products",
    "wechat_pay_order_export_jobs",
    "wechat_pay_refunds",
    "wechat_pay_order_events",
    "wechat_pay_orders",
    # — admin / auth
    "admin_users",
    # admin_wecom_directory_member 不在 PG schema 中（WeCom 目录走 admin_users）
    "owner_role_map",
    "routing_rule_config",
    "wechat_pay_order_events",
    "wechat_pay_orders",
    "app_settings",
    "mcp_tool_settings",
    # — contacts / identity
    "contacts",
    "external_contact_bindings",
    "wecom_external_contact_identity_map",
    "wecom_external_contact_follow_users",
    "wecom_external_contact_event_logs",
    "contact_tags",
    "group_chats",
    # group_chat_members 不在 PG schema 中（成员信息嵌入 group_chats.raw_payload）
    "people",
    "class_user_status_current",
    "class_user_status_history",
    # — user_ops
    "user_ops_lead_pool_history",
    "user_ops_lead_pool_current",
    "user_ops_pool_history",
    "user_ops_pool_current",
    "user_ops_huangxiaocan_activation_source",
    "user_ops_activation_status_source",
    "signup_tag_rules",
    "marketing_automation_question_rules",
    "marketing_automation_configs",
    "class_term_tag_mapping",
    "user_ops_send_records",
    "user_ops_deferred_jobs",
    # — 激活漏斗看板 (alembic 0010-0011)
    "user_ops_hxc_send_config",
    "user_ops_hxc_dashboard_snapshot",
    "user_ops_hxc_dashboard_meta",
    # — message batches
    "message_batch_items",
    "message_batches",
    # — broadcast_jobs
    "broadcast_jobs",
    # — archive / system
    "archived_messages",
    "archive_sync_state",
    "sync_runs",
    "outbound_tasks",
    "outbound_webhook_deliveries",
    "outbound_event_outbox",
    "admin_operation_logs",
    "user_ops_import_batches",
    # customer_pulse_* / followup_orchestrator_* 表已经被 PR #232 删除——不再列入
    # truncate 清单（之前每个 test 跑 8 次注定失败的 SQL，刷 PG error log 还耗时）。
]


def _ensure_pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "PG required. Run: "
            "docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test "
            "-e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16; "
            "then DATABASE_URL=postgresql://test:test@localhost:5432/test pytest"
        )
    return url


def build_pg_test_app(tmp_path, **extra_config: Any):
    """老测试兼容 helper：起 PG 模式 app，允许传 extra_config 覆盖默认。

    用法（替换老 SQLite fixture）：

        @pytest.fixture
        def app(tmp_path):
            from tests.conftest import build_pg_test_app
            with build_pg_test_app(tmp_path, MCP_BEARER_TOKEN="mcp-token") as app:
                yield app
    """
    return _build_app_context(tmp_path, extra_config)


class _AppContextManager:
    """支持 with-statement，自动 truncate 隔离。"""

    def __init__(self, tmp_path, extra_config):
        self.tmp_path = tmp_path
        self.extra_config = extra_config
        self._app = None
        self._ctx = None

    def __enter__(self):
        database_url = _ensure_pg_url()
        private_key = self.tmp_path / "wecom_private_key.pem"
        sdk_lib = self.tmp_path / "libWeWorkFinanceSdk_C.so"
        private_key.write_text("fake-key", encoding="utf-8")
        sdk_lib.write_text("fake-so", encoding="utf-8")

        from wecom_ability_service import create_app
        from wecom_ability_service.db import close_db, init_db

        config = {
            "TESTING": True,
            "DATABASE_URL": database_url,
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key),
            "WECOM_SDK_LIB_PATH": str(sdk_lib),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
        config.update(self.extra_config)

        self._app = create_app(test_config=config)
        self._ctx = self._app.app_context()
        self._ctx.push()

        # session 级 ``_ensure_schema_once`` 已经建好 schema；这里只跑 init_db 做
        # ALTER 补丁 + seed。autouse ``_truncate_before_each_test`` 已经清完表。
        init_db()
        close_db()
        _truncate_cached_tables_once()
        return self._app

    def __exit__(self, *args):
        if self._ctx is not None:
            self._ctx.pop()


def _build_app_context(tmp_path, extra_config):
    return _AppContextManager(tmp_path, extra_config)


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


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema_once():
    """Session 起点（每个 xdist worker 各跑一次）：

    1. 路由到 per-worker DB（``test_<worker_id>``，主进程仍用 base ``test``）
    2. 跑 ``schema_postgres.sql`` 建表（带前向 FK 重试）
    3. 缓存 ``_TABLES_TO_TRUNCATE`` 里**真正存在**的表名 → 后续 per-test
       truncate 一次性 ``TRUNCATE t1, t2, ...`` 单 SQL 跑完
    """
    url = _resolve_worker_database_url()
    if not url:
        yield
        return
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        yield
        return
    schema_path = _ROOT / "wecom_ability_service" / "schema_postgres.sql"
    if schema_path.exists():
        from wecom_ability_service.db.migrations.schema_runner import (
            run_schema_with_forward_fk_retries,
        )

        conn = psycopg.connect(url)
        try:
            def _execute_schema_statement(stmt: str) -> None:
                cursor = conn.cursor()
                try:
                    cursor.execute(stmt)
                finally:
                    cursor.close()

            run_schema_with_forward_fk_retries(
                schema_path.read_text(encoding="utf-8"),
                execute=_execute_schema_statement,
                commit=conn.commit,
                rollback=conn.rollback,
            )
        finally:
            conn.close()

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
def app(tmp_path) -> Iterator[Any]:
    """干净 Flask app + 真 PG，每个 test 隔离。"""
    database_url = _ensure_pg_url()

    # WeCom SDK / private key 等运行时依赖文件（test 用 fake 占位）
    private_key = tmp_path / "wecom_private_key.pem"
    sdk_lib = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key.write_text("fake-key", encoding="utf-8")
    sdk_lib.write_text("fake-so", encoding="utf-8")

    from wecom_ability_service import create_app
    from wecom_ability_service.db import close_db, init_db

    app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE_URL": database_url,
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key),
            "WECOM_SDK_LIB_PATH": str(sdk_lib),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        # session 级 ``_ensure_schema_once`` 已经把 schema_postgres.sql 跑过了，
        # 这里不再重建（每 test 50-100ms × 1004 tests = 50-100s 浪费）。
        # init_db 仍要 per-test：内含 seed_default_segments / ensure_default_budgets，
        # 它们写入的 ``segments`` / ``automation_frequency_budget`` 表会被 truncate
        # fixture 清掉，必须每 test 重 seed。_init_postgres 的 ALTER 是 IF NOT EXISTS
        # 幂等，再跑一次也只是成本（暂未优化掉）。
        init_db()
        close_db()
        _truncate_cached_tables_once()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()
