from __future__ import annotations

import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.exc import SQLAlchemyError

from scripts.ops.bootstrap_database import (
    BASELINE_PATH,
    DatabaseBootstrapRefused,
    _psycopg_url,
    _safe_target,
    install_or_upgrade_database,
    redact_sensitive_text,
)


ROOT = Path(__file__).resolve().parents[1]
CREATE_TABLE_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def test_test_suite_uses_the_versioned_database_baseline() -> None:
    conftest_source = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    baseline_source = BASELINE_PATH.read_text(encoding="utf-8")

    assert "install_or_upgrade_database(url)" in conftest_source
    assert "CREATE TABLE" not in conftest_source
    assert len(CREATE_TABLE_PATTERN.findall(baseline_source)) >= 35


def test_every_active_manifest_table_has_a_versioned_create_source() -> None:
    manifest = yaml.safe_load((ROOT / "docs" / "architecture" / "data_table_lifecycle_manifest.yml").read_text(encoding="utf-8"))["tables"]
    created_tables = set(CREATE_TABLE_PATTERN.findall(BASELINE_PATH.read_text(encoding="utf-8")))
    for migration in sorted((ROOT / "migrations" / "versions").glob("*.py")):
        created_tables.update(CREATE_TABLE_PATTERN.findall(migration.read_text(encoding="utf-8")))

    active_tables = {table for table, entry in manifest.items() if entry.get("lifecycle") not in {"retired", "legacy"}}
    assert active_tables - created_tables == {"alembic_version"}
    assert not [
        table
        for table, entry in manifest.items()
        if entry.get("lifecycle") not in {"retired", "legacy"} and str(entry.get("migration_source") or "").startswith("pre-Alembic baseline")
    ]


def test_database_url_helpers_are_postgres_only_and_redact_passwords() -> None:
    url = "postgresql+psycopg://alice:secret@db.internal:5433/aicrm"

    assert _psycopg_url(url) == "postgresql://alice:secret@db.internal:5433/aicrm"
    assert _safe_target(_psycopg_url(url)) == "postgresql://db.internal:5433/aicrm"
    assert "secret" not in redact_sensitive_text(f"failed for {url}: secret", url)
    with pytest.raises(ValueError, match="PostgreSQL"):
        _psycopg_url("sqlite:///tmp/aicrm.db")


def test_empty_postgres_database_installs_and_reuses_alembic_head() -> None:
    with _isolated_database("install") as database_url:
        first = install_or_upgrade_database(database_url)
        second = install_or_upgrade_database(database_url)

        assert first.baseline_applied is True
        assert first.revision_before is None
        assert first.revision_after == "0120_service_period_member_views"
        assert second.baseline_applied is False
        assert second.revision_before == first.revision_after
        assert second.revision_after == first.revision_after
        with psycopg.connect(database_url) as connection:
            rows = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
        table_names = {str(row[0]) for row in rows}
        assert {
            "alembic_version",
            "auth_api_clients",
            "automation_channel_qrcode_asset",
            "automation_channel_scene_alias",
            "service_period_huangyoucan_usage_snapshot",
            "service_period_huangyoucan_usage_sync_runs",
            "sync_runs",
            "wecom_external_contact_event_logs",
            "wecom_media_leases",
        } <= table_names


def test_production_shape_alembic_database_upgrades_without_reapplying_baseline() -> None:
    with _isolated_database("production_shape") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0098_admin_session_revocation")
        with psycopg.connect(database_url) as connection:
            admin_user_id = int(
                connection.execute(
                    """
                    INSERT INTO admin_users (
                        wecom_userid, wecom_corpid, display_name, is_active,
                        login_enabled, admin_level, session_version
                    ) VALUES (
                        'production-shape-upgrade', 'corp-production-shape',
                        'Production shape upgrade', TRUE, TRUE, 'super_admin', 7
                    )
                    RETURNING id
                    """
                ).fetchone()[0]
            )
            connection.commit()

        result = install_or_upgrade_database(database_url)

        assert result.baseline_applied is False
        assert result.revision_before == "0098_admin_session_revocation"
        assert result.revision_after == "0120_service_period_member_views"
        with psycopg.connect(database_url) as connection:
            preserved = connection.execute(
                "SELECT wecom_userid, session_version FROM admin_users WHERE id = %s",
                (admin_user_id,),
            ).fetchone()
            auth_table = connection.execute("SELECT to_regclass('public.auth_sessions')").fetchone()
        assert preserved == ("production-shape-upgrade", 7)
        assert auth_table == ("auth_sessions",)


def test_questionnaire_auto_execute_upgrade_skips_only_pre_cutover_runs() -> None:
    with _isolated_database("questionnaire_auto_execute") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0108_customer_read_model_refresh")

        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                INSERT INTO internal_event (
                    event_id, event_type, aggregate_type, aggregate_id,
                    idempotency_key, occurred_at, created_at
                ) VALUES
                    (
                        'evt-questionnaire-pre-cutover', 'questionnaire.submitted',
                        'questionnaire_submission', 'pre-cutover', 'questionnaire-pre-cutover',
                        '2026-07-13 16:19:59+00', '2026-07-13 16:19:59+00'
                    ),
                    (
                        'evt-questionnaire-post-cutover', 'questionnaire.submitted',
                        'questionnaire_submission', 'post-cutover', 'questionnaire-post-cutover',
                        '2026-07-13 16:20:01+00', '2026-07-13 16:20:01+00'
                    )
                """
            )
            connection.execute(
                """
                INSERT INTO internal_event_consumer_run (
                    event_id, consumer_name, consumer_type, status
                )
                SELECT event_id, consumer_name, 'projection', 'pending'
                FROM (
                    VALUES
                        ('evt-questionnaire-pre-cutover'),
                        ('evt-questionnaire-post-cutover')
                ) AS event(event_id)
                CROSS JOIN (
                    VALUES
                        ('questionnaire_projection_consumer'),
                        ('questionnaire_webhook_consumer'),
                        ('questionnaire_tag_consumer'),
                        ('automation_questionnaire_consumer'),
                        ('customer_summary_consumer')
                ) AS consumer(consumer_name)
                """
            )
            connection.commit()

        _upgrade_database_to(database_url, "head")

        with psycopg.connect(database_url) as connection:
            statuses = connection.execute(
                """
                SELECT event_id, status, COUNT(*)
                FROM internal_event_consumer_run
                GROUP BY event_id, status
                ORDER BY event_id, status
                """
            ).fetchall()
            attempts = connection.execute(
                """
                SELECT status, error_code, COUNT(*)
                FROM internal_event_consumer_attempt
                GROUP BY status, error_code
                """
            ).fetchall()

        assert statuses == [
            ("evt-questionnaire-post-cutover", "pending", 5),
            ("evt-questionnaire-pre-cutover", "skipped", 5),
        ]
        assert attempts == [
            (
                "skipped",
                "questionnaire_shadow_before_auto_execute_cutover",
                5,
            )
        ]


def test_retired_workspace_drop_fails_closed_when_any_table_contains_data() -> None:
    with _isolated_database("retired_workspace_nonempty") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(BASELINE_PATH.read_text(encoding="utf-8"))
        _upgrade_database_to(database_url, "0107_hyc_usage_snapshot")
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                INSERT INTO group_ops_workspace_drafts (draft_id, idempotency_key)
                VALUES ('preserve_nonempty_draft', 'preserve_nonempty_draft')
                """
            )
            connection.commit()

        with pytest.raises(SQLAlchemyError, match="retired workspace table group_ops_workspace_drafts is not empty"):
            _upgrade_database_to(database_url, "head")

        with psycopg.connect(database_url) as connection:
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            preserved = connection.execute("SELECT COUNT(*) FROM group_ops_workspace_drafts").fetchone()
            refresh_state = connection.execute("SELECT to_regclass('public.customer_read_model_refresh_state')").fetchone()
        assert revision == ("0107_hyc_usage_snapshot",)
        assert preserved == (1,)
        assert refresh_state == (None,)


def test_nonempty_database_without_alembic_state_is_rejected() -> None:
    with _isolated_database("ambiguous") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("CREATE TABLE unmanaged_table (id BIGINT PRIMARY KEY)")

        with pytest.raises(DatabaseBootstrapRefused, match="user relations"):
            install_or_upgrade_database(database_url)

        with psycopg.connect(database_url) as connection:
            row = connection.execute("SELECT to_regclass('public.alembic_version')").fetchone()
        assert row == (None,)


def test_sequence_only_database_without_alembic_state_is_rejected() -> None:
    with _isolated_database("sequence_only") as database_url:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute("CREATE SEQUENCE unmanaged_sequence")

        with pytest.raises(DatabaseBootstrapRefused, match="public.unmanaged_sequence"):
            install_or_upgrade_database(database_url)

        with psycopg.connect(database_url) as connection:
            row = connection.execute("SELECT to_regclass('public.alembic_version')").fetchone()
        assert row == (None,)


def test_failed_baseline_is_atomic_and_does_not_fake_alembic_head(tmp_path: Path) -> None:
    bad_baseline = tmp_path / "bad-baseline.sql"
    bad_baseline.write_text(
        "CREATE TABLE should_roll_back (id BIGINT PRIMARY KEY);\nTHIS IS INVALID SQL;\n",
        encoding="utf-8",
    )
    with _isolated_database("rollback") as database_url:
        with pytest.raises(psycopg.Error):
            install_or_upgrade_database(database_url, baseline_path=bad_baseline)

        with psycopg.connect(database_url) as connection:
            row = connection.execute(
                """
                SELECT to_regclass('public.should_roll_back'),
                       to_regclass('public.alembic_version')
                """
            ).fetchone()
        assert row == (None, None)


def _upgrade_database_to(database_url: str, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(config, revision)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


@contextmanager
def _isolated_database(label: str):
    source_url = os.getenv("AICRM_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not source_url:
        pytest.skip("PostgreSQL integration URL is unavailable")
    source_url = _psycopg_url(source_url)
    parsed = urlsplit(source_url)
    maintenance_url = urlunsplit(parsed._replace(path="/postgres"))
    database_name = f"aicrm_bootstrap_test_{label}_{uuid.uuid4().hex[:8]}"
    database_url = urlunsplit(parsed._replace(path=f"/{database_name}"))

    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        yield database_url
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
