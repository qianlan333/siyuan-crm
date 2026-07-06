from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session

from aicrm_next.shared.db_session import get_session_factory


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(data) if isinstance(data, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value:
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return []
        return list(data) if isinstance(data, list) else []
    return []


def _public_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text_value = _text(value)
        if not text_value:
            return ""
        try:
            dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        except ValueError:
            return text_value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = dict(row)
    for key, value in list(payload.items()):
        if key.endswith("_jsons") or key in {"dependencies_json", "sample_rows_json", "validation_errors_json"}:
            payload[key] = _json_list(value)
        elif key.endswith("_json") or key.endswith("_jsonb") or key in {
            "payload_json",
            "message_json",
            "action_json",
            "headers_json",
            "payload_template_json",
            "explain_json",
        }:
            payload[key] = _json_obj(value)
        elif isinstance(value, datetime):
            payload[key] = _public_datetime(value)
    return payload


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


class AudienceRepository:
    def list_packages(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_package_summaries(self, *, limit: int = 200) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_package_detail(self, package_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def update_package_config(self, package_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    def copy_package(self, package_id: int, *, package_key: str, name: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def activate_package(self, package_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_admin_members(self, package_id: int, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        raise NotImplementedError

    def rotate_inbound_secret(self, package_id: int, secret: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_senders(self, package_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def replace_senders(self, package_id: int, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_ai_audience_batch_rows(self, package_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def resolve_member_unionid(self, normalized: dict[str, Any]) -> str:
        raise NotImplementedError

    def enqueue_identity_resolution(self, normalized: dict[str, Any], *, reason: str) -> None:
        raise NotImplementedError

    def create_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def get_package(self, package_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_package_by_key(self, package_key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def create_version(self, package_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_current_version(self, package_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_latest_version(self, package_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def publish_version(self, package_id: int, version_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def publish_version_without_activation(self, package_id: int, version_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def insert_external_spec_audit(self, *, operator: str, action_type: str, package_key: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        raise NotImplementedError

    def get_active_subscription_by_target(
        self,
        package_id: int,
        trigger_event_type: str,
        target_type: str,
        webhook_url: str,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    def update_package_status(self, package_id: int, status: str, *, reason: str = "") -> dict[str, Any] | None:
        raise NotImplementedError

    def replace_dependencies(self, package_id: int, version_id: int, dependencies: list[str]) -> None:
        raise NotImplementedError

    def execute_readonly_query(self, sql: str, params: dict[str, Any], *, limit: int, timeout_seconds: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def explain_readonly_query(self, sql: str, params: dict[str, Any], *, timeout_seconds: int) -> Any:
        raise NotImplementedError

    def get_agent_prompt(self, agent_code: str) -> dict[str, Any]:
        raise NotImplementedError

    def create_agent_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def complete_agent_run(self, row_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def log_agent_llm_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def record_agent_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class SQLAlchemyAudienceRepository(AudienceRepository):
    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or get_session_factory()

    def _one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            return _public_row(dict(row)) if row else None

    def _all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            return [_public_row(dict(row)) or {} for row in rows]

    def _write_one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            session.commit()
            return _public_row(dict(row)) if row else None

    def _write_all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            session.commit()
            return [_public_row(dict(row)) or {} for row in rows]

    def _table_columns(self, table: str) -> set[str]:
        rows = self._all(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """,
            {"table": table},
        )
        return {_text(row.get("column_name")) for row in rows}

    def _table_exists(self, table: str, *, schema: str = "public") -> bool:
        row = self._one(
            """
            SELECT 1 AS exists_flag
            FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
            LIMIT 1
            """,
            {"schema": schema, "table": table},
        )
        return bool(row)

    def _insert_available(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        columns = [key for key in values if key in self._table_columns(table)]
        if not columns:
            return {}
        params = {f"p{i}": values[column] for i, column in enumerate(columns)}
        placeholders = ", ".join(f":p{i}" for i, _column in enumerate(columns))
        column_sql = ", ".join(columns)
        return self._write_one(
            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) RETURNING *",
            params,
        ) or {}

    def _update_available(self, table: str, row_id: int, values: dict[str, Any]) -> dict[str, Any]:
        available_columns = self._table_columns(table)
        columns = [key for key in values if key in available_columns]
        if not columns or int(row_id or 0) <= 0:
            return {}
        params = {f"p{i}": values[column] for i, column in enumerate(columns)}
        params["row_id"] = int(row_id)
        assignments = ", ".join(f"{column} = :p{i}" for i, column in enumerate(columns))
        if "updated_at" in available_columns:
            assignments = f"{assignments}, updated_at = CURRENT_TIMESTAMP"
        return self._write_one(
            f"UPDATE {table} SET {assignments} WHERE id = :row_id RETURNING *",
            params,
        ) or {}

    def list_packages(self) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT p.*, v.version_number AS current_version_number
            FROM ai_audience_package p
            LEFT JOIN ai_audience_package_version v ON v.id = p.current_version_id
            ORDER BY p.id DESC
            """
        )

    def list_package_summaries(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._all(
            """
            WITH member_counts AS (
                SELECT
                    package_id,
                    COUNT(*) FILTER (WHERE status = 'active') AS member_count
                FROM ai_audience_member_current
                GROUP BY package_id
            ),
            latest_runs AS (
                SELECT DISTINCT ON (package_id)
                    package_id,
                    refresh_finished_at,
                    refresh_started_at,
                    status AS run_status
                FROM ai_audience_package_run
                ORDER BY package_id, refresh_finished_at DESC NULLS LAST, id DESC
            )
            SELECT
                p.id,
                p.package_key,
                p.name,
                p.status,
                COALESCE(mc.member_count, 0) AS member_count,
                lr.refresh_finished_at AS last_refreshed_at,
                p.incremental_enabled,
                p.incremental_interval_seconds,
                p.daily_enabled,
                p.daily_refresh_time,
                p.updated_at,
                COUNT(*) OVER () AS total_count
            FROM ai_audience_package p
            LEFT JOIN member_counts mc ON mc.package_id = p.id
            LEFT JOIN latest_runs lr ON lr.package_id = p.id
            WHERE p.status <> 'archived'
            ORDER BY p.updated_at DESC, p.id DESC
            LIMIT :limit
            """,
            {"limit": max(1, min(int(limit or 200), 200))},
        )

    def get_package_detail(self, package_id: int) -> dict[str, Any] | None:
        return self._one(
            """
            WITH member_counts AS (
                SELECT package_id, COUNT(*) FILTER (WHERE status = 'active') AS member_count
                FROM ai_audience_member_current
                WHERE package_id = :package_id
                GROUP BY package_id
            ),
            latest_runs AS (
                SELECT DISTINCT ON (package_id)
                    package_id,
                    refresh_finished_at,
                    refresh_started_at
                FROM ai_audience_package_run
                WHERE package_id = :package_id
                ORDER BY package_id, refresh_finished_at DESC NULLS LAST, id DESC
            )
            SELECT
                p.id,
                p.package_key,
                p.name,
                p.status,
                COALESCE(mc.member_count, 0) AS member_count,
                lr.refresh_finished_at AS last_refreshed_at,
                p.incremental_enabled,
                p.incremental_interval_seconds,
                p.daily_enabled,
                p.daily_refresh_time,
                p.natural_language_definition,
                p.timezone
            FROM ai_audience_package p
            LEFT JOIN member_counts mc ON mc.package_id = p.id
            LEFT JOIN latest_runs lr ON lr.package_id = p.id
            WHERE p.id = :package_id
            LIMIT 1
            """,
            {"package_id": int(package_id)},
        )

    def update_package_config(self, package_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_package
            SET name = :name,
                natural_language_definition = :natural_language_definition,
                incremental_enabled = :incremental_enabled,
                incremental_interval_seconds = :incremental_interval_seconds,
                daily_enabled = :daily_enabled,
                daily_refresh_time = :daily_refresh_time,
                next_incremental_refresh_at = CASE
                    WHEN :incremental_enabled THEN COALESCE(next_incremental_refresh_at, CURRENT_TIMESTAMP)
                    ELSE NULL
                END,
                next_daily_refresh_at = CASE
                    WHEN :daily_enabled THEN COALESCE(next_daily_refresh_at, :next_daily_refresh_at)
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :package_id
            RETURNING *
            """,
            {
                "package_id": int(package_id),
                "name": _text(payload.get("name")),
                "natural_language_definition": _text(payload.get("natural_language_definition")),
                "incremental_enabled": bool(payload.get("incremental_enabled")),
                "incremental_interval_seconds": int(payload.get("incremental_interval_seconds") or 180),
                "daily_enabled": bool(payload.get("daily_enabled")),
                "daily_refresh_time": _text(payload.get("daily_refresh_time")) or "02:00",
                "next_daily_refresh_at": next_daily_refresh_at(
                    _text(payload.get("daily_refresh_time")) or "02:00",
                    _text(payload.get("timezone")) or "Asia/Shanghai",
                ),
            },
        )

    def copy_package(self, package_id: int, *, package_key: str, name: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            source = session.execute(text("SELECT * FROM ai_audience_package WHERE id = :package_id LIMIT 1"), {"package_id": int(package_id)}).mappings().fetchone()
            if not source:
                return None
            row = session.execute(
                text(
                    """
                    INSERT INTO ai_audience_package (
                        package_key, name, natural_language_definition, status, query_mode, identity_policy,
                        incremental_enabled, daily_enabled, incremental_interval_seconds, daily_refresh_time,
                        timezone, lookback_seconds, inbound_webhook_secret,
                        next_incremental_refresh_at, next_daily_refresh_at, created_at, updated_at
                    )
                    VALUES (
                        :package_key, :name, :natural_language_definition, 'draft', :query_mode, :identity_policy,
                        :incremental_enabled, :daily_enabled, :incremental_interval_seconds, :daily_refresh_time,
                        :timezone, :lookback_seconds, :inbound_webhook_secret,
                        NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING *
                    """
                ),
                {
                    "package_key": _text(package_key),
                    "name": _text(name),
                    "natural_language_definition": _text(source.get("natural_language_definition")),
                    "query_mode": _text(source.get("query_mode")) or "hybrid",
                    "identity_policy": _text(source.get("identity_policy")) or "external_userid",
                    "incremental_enabled": bool(source.get("incremental_enabled")),
                    "daily_enabled": bool(source.get("daily_enabled")),
                    "incremental_interval_seconds": int(source.get("incremental_interval_seconds") or 180),
                    "daily_refresh_time": _text(source.get("daily_refresh_time")) or "02:00",
                    "timezone": _text(source.get("timezone")) or "Asia/Shanghai",
                    "lookback_seconds": int(source.get("lookback_seconds") or 600),
                    "inbound_webhook_secret": _text(source.get("inbound_webhook_secret")),
                },
            ).mappings().one()
            new_package_id = int(row["id"])
            version = session.execute(
                text(
                    """
                    SELECT *
                    FROM ai_audience_package_version
                    WHERE id = :version_id
                    LIMIT 1
                    """
                ),
                {"version_id": int(source.get("current_version_id") or 0)},
            ).mappings().fetchone()
            if version:
                new_version = session.execute(
                    text(
                        """
                        INSERT INTO ai_audience_package_version (
                            package_id, version_number, status, incremental_sql_text, snapshot_sql_text,
                            simple_sql_text, simple_compiled_sql_text,
                            ai_prompt, ai_rationale, natural_language_explanation, parameters_json, dependencies_json,
                            explain_json, sample_rows_json, validation_errors_json, created_at
                        )
                        VALUES (
                            :package_id, 1, 'draft', :incremental_sql_text, :snapshot_sql_text,
                            :simple_sql_text, :simple_compiled_sql_text,
                            :ai_prompt, :ai_rationale, :natural_language_explanation, CAST(:parameters_json AS jsonb), CAST(:dependencies_json AS jsonb),
                            CAST(:explain_json AS jsonb), CAST(:sample_rows_json AS jsonb), CAST(:validation_errors_json AS jsonb),
                            CURRENT_TIMESTAMP
                        )
                        RETURNING *
                        """
                    ),
                    {
                        "package_id": new_package_id,
                        "incremental_sql_text": _text(version.get("incremental_sql_text")),
                        "snapshot_sql_text": _text(version.get("snapshot_sql_text")),
                        "simple_sql_text": _text(version.get("simple_sql_text")),
                        "simple_compiled_sql_text": _text(version.get("simple_compiled_sql_text")),
                        "ai_prompt": _text(version.get("ai_prompt")),
                        "ai_rationale": _text(version.get("ai_rationale")),
                        "natural_language_explanation": _text(version.get("natural_language_explanation")),
                        "parameters_json": _json_dumps(version.get("parameters_json") or {}),
                        "dependencies_json": _json_dumps(version.get("dependencies_json") or []),
                        "explain_json": _json_dumps(version.get("explain_json") or {}),
                        "sample_rows_json": _json_dumps(version.get("sample_rows_json") or []),
                        "validation_errors_json": _json_dumps(version.get("validation_errors_json") or []),
                    },
                ).mappings().one()
                session.execute(
                    text("UPDATE ai_audience_package SET current_version_id = :version_id WHERE id = :package_id"),
                    {"version_id": int(new_version["id"]), "package_id": new_package_id},
                )
                session.execute(
                    text(
                        """
                        INSERT INTO ai_audience_package_dependency (
                            package_id, version_id, source_type, source_key, view_name, created_at
                        )
                        SELECT
                            :new_package_id, :new_version_id, source_type, source_key, view_name, CURRENT_TIMESTAMP
                        FROM ai_audience_package_dependency
                        WHERE package_id = :package_id
                          AND version_id = :source_version_id
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "new_package_id": new_package_id,
                        "new_version_id": int(new_version["id"]),
                        "package_id": int(package_id),
                        "source_version_id": int(version["id"]),
                    },
                )
            session.execute(
                text(
                    """
                    INSERT INTO ai_audience_outbound_subscription (
                        package_id, status, trigger_event_type, dispatch_mode, target_type, webhook_url,
                        signing_secret, headers_json, payload_template_json, execution_mode,
                        requires_approval, max_attempts, created_at, updated_at
                    )
                    SELECT
                        :new_package_id, status, trigger_event_type, dispatch_mode, target_type, webhook_url,
                        signing_secret, headers_json, payload_template_json, execution_mode,
                        requires_approval, max_attempts, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    FROM ai_audience_outbound_subscription
                    WHERE package_id = :package_id
                    """
                ),
                {"new_package_id": new_package_id, "package_id": int(package_id)},
            )
            if self._table_exists("ai_audience_package_sender"):
                session.execute(
                    text(
                        """
                        INSERT INTO ai_audience_package_sender (
                            package_id, sender_userid, display_name, priority, status, created_at, updated_at
                        )
                        SELECT
                            :new_package_id, sender_userid, display_name, priority, status,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        FROM ai_audience_package_sender
                        WHERE package_id = :package_id
                        """
                    ),
                    {"new_package_id": new_package_id, "package_id": int(package_id)},
                )
            session.commit()
            copied = session.execute(text("SELECT * FROM ai_audience_package WHERE id = :package_id"), {"package_id": new_package_id}).mappings().one()
            return _public_row(dict(copied))

    def activate_package(self, package_id: int) -> dict[str, Any] | None:
        current = self.get_package(package_id)
        if not current:
            return None
        next_daily = None
        if bool(current.get("daily_enabled")):
            next_daily = next_daily_refresh_at(_text(current.get("daily_refresh_time")) or "02:00", _text(current.get("timezone")) or "Asia/Shanghai")
        return self._write_one(
            """
            UPDATE ai_audience_package
            SET status = 'active',
                next_incremental_refresh_at = CASE WHEN incremental_enabled THEN CURRENT_TIMESTAMP ELSE NULL END,
                next_daily_refresh_at = CASE
                    WHEN daily_enabled THEN CAST(:next_daily_refresh_at AS TIMESTAMPTZ)
                    ELSE NULL
                END,
                paused_reason = '',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :package_id
            RETURNING *
            """,
            {"package_id": int(package_id), "next_daily_refresh_at": next_daily},
        )

    def create_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        daily_enabled = bool(payload.get("daily_enabled", False))
        daily_refresh_time = _text(payload.get("daily_refresh_time")) or "02:00"
        timezone_name = _text(payload.get("timezone")) or "Asia/Shanghai"
        status = _text(payload.get("status")) or "draft"
        if status not in {"draft", "paused", "active"}:
            status = "draft"
        row = self._write_one(
            """
            INSERT INTO ai_audience_package (
                package_key, name, natural_language_definition, status, query_mode, identity_policy,
                incremental_enabled, daily_enabled, incremental_interval_seconds, daily_refresh_time,
                timezone, lookback_seconds, inbound_webhook_secret,
                next_incremental_refresh_at, next_daily_refresh_at, created_at, updated_at
            )
            VALUES (
                :package_key, :name, :natural_language_definition, :status, :query_mode, :identity_policy,
                :incremental_enabled, :daily_enabled, :incremental_interval_seconds, :daily_refresh_time,
                :timezone, :lookback_seconds, :inbound_webhook_secret,
                :next_incremental_refresh_at, :next_daily_refresh_at,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING *
            """,
            {
                "package_key": _text(payload.get("package_key")),
                "name": _text(payload.get("name")),
                "status": status,
                "natural_language_definition": _text(payload.get("natural_language_definition")),
                "query_mode": _text(payload.get("query_mode")) or "hybrid",
                "identity_policy": _text(payload.get("identity_policy")) or "external_userid",
                "incremental_enabled": bool(payload.get("incremental_enabled", True)),
                "daily_enabled": daily_enabled,
                "incremental_interval_seconds": max(60, int(payload.get("incremental_interval_seconds") or 180)),
                "daily_refresh_time": daily_refresh_time,
                "timezone": timezone_name,
                "lookback_seconds": max(0, int(payload.get("lookback_seconds") or 600)),
                "inbound_webhook_secret": _text(payload.get("inbound_webhook_secret")),
                "next_incremental_refresh_at": default_refresh_started_at() if status == "active" and bool(payload.get("incremental_enabled", True)) else None,
                "next_daily_refresh_at": next_daily_refresh_at(daily_refresh_time, timezone_name) if status == "active" and daily_enabled else None,
            },
        )
        if row is None:
            raise RuntimeError("ai audience package create failed")
        return row

    def get_package(self, package_id: int) -> dict[str, Any] | None:
        return self._one("SELECT * FROM ai_audience_package WHERE id = :id LIMIT 1", {"id": int(package_id)})

    def get_package_by_key(self, package_key: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM ai_audience_package WHERE package_key = :package_key LIMIT 1", {"package_key": _text(package_key)})

    def create_version(self, package_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._write_one(
            """
            INSERT INTO ai_audience_package_version (
                package_id, version_number, status, incremental_sql_text, snapshot_sql_text,
                simple_sql_text, simple_compiled_sql_text,
                ai_prompt, ai_rationale, natural_language_explanation, parameters_json, dependencies_json,
                explain_json, sample_rows_json, validation_errors_json, created_at
            )
            SELECT
                :package_id,
                COALESCE(MAX(version_number), 0) + 1,
                'draft',
                :incremental_sql_text,
                :snapshot_sql_text,
                :simple_sql_text,
                :simple_compiled_sql_text,
                :ai_prompt,
                :ai_rationale,
                :natural_language_explanation,
                CAST(:parameters_json AS jsonb),
                CAST(:dependencies_json AS jsonb),
                CAST(:explain_json AS jsonb),
                CAST(:sample_rows_json AS jsonb),
                CAST(:validation_errors_json AS jsonb),
                CURRENT_TIMESTAMP
            FROM ai_audience_package_version
            WHERE package_id = :package_id
            RETURNING *
            """,
            {
                "package_id": int(package_id),
                "incremental_sql_text": _text(payload.get("incremental_sql_text")),
                "snapshot_sql_text": _text(payload.get("snapshot_sql_text")),
                "simple_sql_text": _text(payload.get("simple_sql_text")),
                "simple_compiled_sql_text": _text(payload.get("simple_compiled_sql_text")),
                "ai_prompt": _text(payload.get("ai_prompt")),
                "ai_rationale": _text(payload.get("ai_rationale")),
                "natural_language_explanation": _text(payload.get("natural_language_explanation")),
                "parameters_json": _json_dumps(payload.get("parameters") or payload.get("parameters_json") or {}),
                "dependencies_json": _json_dumps(payload.get("dependencies") or []),
                "explain_json": _json_dumps(payload.get("explain") or {}),
                "sample_rows_json": _json_dumps(payload.get("sample_rows") or []),
                "validation_errors_json": _json_dumps(payload.get("validation_errors") or []),
            },
        )
        if row is None:
            raise RuntimeError("ai audience package version create failed")
        return row

    def update_version_validation(self, version_id: int, *, dependencies: list[str], validation_errors: list[str], sample_rows: list[dict[str, Any]] | None = None, explain: Any | None = None) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_package_version
            SET dependencies_json = CAST(:dependencies_json AS jsonb),
                validation_errors_json = CAST(:validation_errors_json AS jsonb),
                sample_rows_json = COALESCE(CAST(:sample_rows_json AS jsonb), sample_rows_json),
                explain_json = COALESCE(CAST(:explain_json AS jsonb), explain_json)
            WHERE id = :version_id
            RETURNING *
            """,
            {
                "version_id": int(version_id),
                "dependencies_json": _json_dumps(dependencies),
                "validation_errors_json": _json_dumps(validation_errors),
                "sample_rows_json": _json_dumps(sample_rows) if sample_rows is not None else None,
                "explain_json": _json_dumps(explain) if explain is not None else None,
            },
        )

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        return self._one("SELECT * FROM ai_audience_package_version WHERE id = :id LIMIT 1", {"id": int(version_id)})

    def get_current_version(self, package_id: int) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT v.*
            FROM ai_audience_package p
            JOIN ai_audience_package_version v ON v.id = p.current_version_id
            WHERE p.id = :package_id
            LIMIT 1
            """,
            {"package_id": int(package_id)},
        )

    def get_latest_version(self, package_id: int) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT *
            FROM ai_audience_package_version
            WHERE package_id = :package_id
            ORDER BY version_number DESC, id DESC
            LIMIT 1
            """,
            {"package_id": int(package_id)},
        )

    def publish_version(self, package_id: int, version_id: int) -> dict[str, Any] | None:
        with self._session_factory() as session:
            package_row = session.execute(
                text(
                    """
                    SELECT daily_enabled, daily_refresh_time, timezone
                    FROM ai_audience_package
                    WHERE id = :package_id
                    LIMIT 1
                    """
                ),
                {"package_id": int(package_id)},
            ).mappings().fetchone()
            next_daily = None
            if package_row and bool(package_row.get("daily_enabled")):
                next_daily = next_daily_refresh_at(
                    _text(package_row.get("daily_refresh_time")) or "02:00",
                    _text(package_row.get("timezone")) or "Asia/Shanghai",
                )
            session.execute(
                text("UPDATE ai_audience_package_version SET status = 'archived' WHERE package_id = :package_id AND id <> :version_id"),
                {"package_id": int(package_id), "version_id": int(version_id)},
            )
            row = session.execute(
                text(
                    """
                    UPDATE ai_audience_package_version
                    SET status = 'published', published_at = CURRENT_TIMESTAMP
                    WHERE id = :version_id AND package_id = :package_id
                    RETURNING *
                    """
                ),
                {"package_id": int(package_id), "version_id": int(version_id)},
            ).mappings().fetchone()
            if not row:
                session.rollback()
                return None
            session.execute(
                text(
                    """
                    UPDATE ai_audience_package
                    SET current_version_id = :version_id,
                        status = 'active',
                        next_incremental_refresh_at = COALESCE(next_incremental_refresh_at, CURRENT_TIMESTAMP),
                        next_daily_refresh_at = CASE WHEN daily_enabled THEN COALESCE(next_daily_refresh_at, :next_daily_refresh_at) ELSE next_daily_refresh_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :package_id
                    """
                ),
                {"package_id": int(package_id), "version_id": int(version_id), "next_daily_refresh_at": next_daily},
            )
            session.commit()
            return _public_row(dict(row))

    def publish_version_without_activation(self, package_id: int, version_id: int) -> dict[str, Any] | None:
        with self._session_factory() as session:
            existing_package = session.execute(
                text(
                    """
                    SELECT status, next_incremental_refresh_at, next_daily_refresh_at
                    FROM ai_audience_package
                    WHERE id = :package_id
                    LIMIT 1
                    """
                ),
                {"package_id": int(package_id)},
            ).mappings().fetchone()
            if not existing_package:
                return None
            session.execute(
                text("UPDATE ai_audience_package_version SET status = 'archived' WHERE package_id = :package_id AND id <> :version_id"),
                {"package_id": int(package_id), "version_id": int(version_id)},
            )
            row = session.execute(
                text(
                    """
                    UPDATE ai_audience_package_version
                    SET status = 'published', published_at = CURRENT_TIMESTAMP
                    WHERE id = :version_id AND package_id = :package_id
                    RETURNING *
                    """
                ),
                {"package_id": int(package_id), "version_id": int(version_id)},
            ).mappings().fetchone()
            if not row:
                session.rollback()
                return None
            session.execute(
                text(
                    """
                    UPDATE ai_audience_package
                    SET current_version_id = :version_id,
                        status = :status,
                        next_incremental_refresh_at = :next_incremental_refresh_at,
                        next_daily_refresh_at = :next_daily_refresh_at,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :package_id
                    """
                ),
                {
                    "package_id": int(package_id),
                    "version_id": int(version_id),
                    "status": _text(existing_package.get("status")) or "paused",
                    "next_incremental_refresh_at": existing_package.get("next_incremental_refresh_at"),
                    "next_daily_refresh_at": existing_package.get("next_daily_refresh_at"),
                },
            )
            session.commit()
            return _public_row(dict(row))

    def update_package_status(self, package_id: int, status: str, *, reason: str = "") -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_package
            SET status = :status,
                paused_reason = :paused_reason,
                next_incremental_refresh_at = CASE
                    WHEN :status = 'active' AND incremental_enabled THEN COALESCE(next_incremental_refresh_at, CURRENT_TIMESTAMP)
                    WHEN :status = 'active' THEN NULL
                    ELSE NULL
                END,
                next_daily_refresh_at = CASE
                    WHEN :status = 'active' AND daily_enabled THEN COALESCE(next_daily_refresh_at, CURRENT_TIMESTAMP)
                    WHEN :status = 'active' THEN NULL
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :package_id
            RETURNING *
            """,
            {"package_id": int(package_id), "status": _text(status), "paused_reason": _text(reason)},
        )

    def replace_dependencies(self, package_id: int, version_id: int, dependencies: list[str]) -> None:
        with self._session_factory() as session:
            session.execute(
                text("DELETE FROM ai_audience_package_dependency WHERE package_id = :package_id AND version_id = :version_id"),
                {"package_id": int(package_id), "version_id": int(version_id)},
            )
            for dependency in dependencies:
                source_type = _dependency_source_type(dependency)
                session.execute(
                    text(
                        """
                        INSERT INTO ai_audience_package_dependency (package_id, version_id, source_type, source_key, view_name, created_at)
                        VALUES (:package_id, :version_id, :source_type, '', :view_name, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "package_id": int(package_id),
                        "version_id": int(version_id),
                        "source_type": source_type,
                        "view_name": _text(dependency),
                    },
                )
            session.commit()

    def insert_external_spec_audit(self, *, operator: str, action_type: str, package_key: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        self._write_one(
            """
            INSERT INTO admin_operation_logs (
                operator, action_type, target_type, target_id,
                before_json, after_json, created_at
            )
            VALUES (
                :operator, :action_type, 'ai_audience_external_spec', :target_id,
                CAST(:before_json AS jsonb), CAST(:after_json AS jsonb), CURRENT_TIMESTAMP
            )
            RETURNING id
            """,
            {
                "operator": _text(operator) or "external",
                "action_type": _text(action_type),
                "target_id": _text(package_key) or "-",
                "before_json": _json_dumps(before or {}),
                "after_json": _json_dumps(after or {}),
            },
        )

    def execute_readonly_query(self, sql: str, params: dict[str, Any], *, limit: int, timeout_seconds: int) -> list[dict[str, Any]]:
        readonly_url = _text(os.getenv("AICRM_AUDIENCE_READONLY_DATABASE_URL"))
        if not readonly_url:
            raise RuntimeError("audience_readonly_database_url_not_configured")
        session_factory = get_session_factory(database_url=readonly_url)
        timeout_ms = max(1, min(int(timeout_seconds or 10), 120)) * 1000
        bounded_limit = max(1, min(int(limit or 100), 100000))
        statement = f"SELECT * FROM ({sql}) AS ai_audience_query LIMIT :__ai_audience_limit"
        with session_factory() as session:
            session.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
            rows = session.execute(text(statement), {**dict(params or {}), "__ai_audience_limit": bounded_limit}).mappings().fetchall()
            session.rollback()
            return [_public_row(dict(row)) or {} for row in rows]

    def explain_readonly_query(self, sql: str, params: dict[str, Any], *, timeout_seconds: int) -> Any:
        readonly_url = _text(os.getenv("AICRM_AUDIENCE_READONLY_DATABASE_URL"))
        if not readonly_url:
            raise RuntimeError("audience_readonly_database_url_not_configured")
        session_factory = get_session_factory(database_url=readonly_url)
        timeout_ms = max(1, min(int(timeout_seconds or 10), 120)) * 1000
        with session_factory() as session:
            session.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
            rows = session.execute(text("EXPLAIN (FORMAT JSON) " + sql), dict(params or {})).fetchall()
            session.rollback()
            return rows[0][0] if rows else []

    def create_run(self, package_id: int, version_id: int, *, run_type: str, started_at: datetime, last_watermark_at: datetime | None = None) -> dict[str, Any]:
        row = self._write_one(
            """
            INSERT INTO ai_audience_package_run (
                package_id, version_id, run_type, status, refresh_started_at, last_watermark_at, created_at
            )
            VALUES (:package_id, :version_id, :run_type, 'running', :started_at, :last_watermark_at, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            {
                "package_id": int(package_id),
                "version_id": int(version_id or 0) or None,
                "run_type": _text(run_type),
                "started_at": started_at,
                "last_watermark_at": last_watermark_at,
            },
        )
        if row is None:
            raise RuntimeError("ai audience run create failed")
        return row

    def complete_run(self, run_id: int, *, status: str, returned_count: int = 0, entered_count: int = 0, updated_count: int = 0, exited_count: int = 0, member_event_count: int = 0, error_message: str = "", next_watermark_at: datetime | None = None) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_package_run
            SET status = :status,
                refresh_finished_at = CURRENT_TIMESTAMP,
                returned_count = :returned_count,
                entered_count = :entered_count,
                updated_count = :updated_count,
                exited_count = :exited_count,
                member_event_count = :member_event_count,
                error_message = :error_message,
                next_watermark_at = :next_watermark_at,
                duration_ms = GREATEST(0, (EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - refresh_started_at)) * 1000)::integer)
            WHERE id = :run_id
            RETURNING *
            """,
            {
                "run_id": int(run_id),
                "status": _text(status),
                "returned_count": int(returned_count or 0),
                "entered_count": int(entered_count or 0),
                "updated_count": int(updated_count or 0),
                "exited_count": int(exited_count or 0),
                "member_event_count": int(member_event_count or 0),
                "error_message": _text(error_message),
                "next_watermark_at": next_watermark_at,
            },
        )

    def list_current_members(self, package_id: int) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT *
            FROM ai_audience_member_current
            WHERE package_id = :package_id
            ORDER BY id ASC
            """,
            {"package_id": int(package_id)},
        )

    def resolve_member_unionid(self, normalized: dict[str, Any]) -> str:
        unionid = _text(normalized.get("unionid"))
        if unionid:
            return unionid
        external_userid = _text(normalized.get("external_userid"))
        if not external_userid or not self._table_exists("crm_user_identity"):
            return ""
        row = self._one(
            """
            SELECT unionid
            FROM crm_user_identity
            WHERE primary_external_userid = :external_userid
               OR jsonb_exists(external_userids_json, :external_userid)
            ORDER BY CASE WHEN primary_external_userid = :external_userid THEN 0 ELSE 1 END,
                     updated_at DESC NULLS LAST
            LIMIT 1
            """,
            {"external_userid": external_userid},
        )
        return _text((row or {}).get("unionid"))

    def enqueue_identity_resolution(self, normalized: dict[str, Any], *, reason: str) -> None:
        if not self._table_exists("crm_user_identity_resolution_queue"):
            return
        self._write_one(
            """
            INSERT INTO crm_user_identity_resolution_queue (
                source_type, source_key, reason, external_userid, mobile, payload_json, status,
                created_at, updated_at
            )
            VALUES (
                'ai_audience_ops', :source_key, :reason, :external_userid, :mobile, CAST(:payload_json AS jsonb),
                'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (source_type, source_key)
            WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
            DO UPDATE SET reason = EXCLUDED.reason,
                external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                mobile = COALESCE(NULLIF(EXCLUDED.mobile, ''), crm_user_identity_resolution_queue.mobile),
                payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            {
                "source_key": _text(normalized.get("event_source_key")) or f"{normalized.get('identity_type')}:{normalized.get('identity_value')}",
                "reason": _text(reason) or "missing_unionid",
                "external_userid": _text(normalized.get("external_userid")),
                "mobile": _text(normalized.get("mobile")),
                "payload_json": _json_dumps(
                    {
                        "identity_type": normalized.get("identity_type"),
                        "identity_value": normalized.get("identity_value"),
                        "event_source_key": normalized.get("event_source_key"),
                        "payload_json": normalized.get("payload_json") or {},
                    }
                ),
            },
        )

    def upsert_active_member(self, package_id: int, normalized: dict[str, Any], *, occurred_at: datetime) -> dict[str, Any]:
        row = self._write_one(
            """
            INSERT INTO ai_audience_member_current (
                package_id, identity_type, identity_value, unionid, status,
                mobile_hash, owner_userid, event_source_key, payload_hash, payload_json,
                first_entered_at, last_seen_at, last_updated_at, created_at, updated_at
            )
            VALUES (
                :package_id, :identity_type, :identity_value, :unionid, 'active',
                :mobile_hash, :owner_userid, :event_source_key, :payload_hash, CAST(:payload_json AS jsonb),
                :occurred_at, :occurred_at, :occurred_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (package_id, identity_type, identity_value)
            DO UPDATE SET status = 'active',
                unionid = EXCLUDED.unionid,
                mobile_hash = EXCLUDED.mobile_hash,
                owner_userid = EXCLUDED.owner_userid,
                event_source_key = EXCLUDED.event_source_key,
                payload_hash = EXCLUDED.payload_hash,
                payload_json = EXCLUDED.payload_json,
                last_seen_at = EXCLUDED.last_seen_at,
                last_updated_at = CASE
                    WHEN ai_audience_member_current.payload_hash <> EXCLUDED.payload_hash THEN EXCLUDED.last_updated_at
                    ELSE ai_audience_member_current.last_updated_at
                END,
                exited_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            {
                "package_id": int(package_id),
                "identity_type": _text(normalized.get("identity_type")),
                "identity_value": _text(normalized.get("identity_value")),
                "unionid": _text(normalized.get("unionid")),
                "mobile_hash": _text(normalized.get("mobile_hash")),
                "owner_userid": _text(normalized.get("owner_userid")),
                "event_source_key": _text(normalized.get("event_source_key")),
                "payload_hash": _text(normalized.get("payload_hash")),
                "payload_json": _json_dumps(normalized.get("payload_json") or {}),
                "occurred_at": occurred_at,
            },
        )
        if row is None:
            raise RuntimeError("ai audience member upsert failed")
        return row

    def mark_member_exited(self, member_id: int, *, occurred_at: datetime) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_member_current
            SET status = 'exited',
                exited_at = :occurred_at,
                last_seen_at = :occurred_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :member_id
            RETURNING *
            """,
            {"member_id": int(member_id), "occurred_at": occurred_at},
        )

    def insert_member_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        row = self._write_one(
            """
            INSERT INTO ai_audience_member_event (
                package_id, run_id, member_current_id, event_type, identity_type, identity_value,
                unionid, mobile_hash, owner_userid, event_source_key,
                payload_hash, payload_json, idempotency_key, occurred_at, created_at
            )
            VALUES (
                :package_id, :run_id, :member_current_id, :event_type, :identity_type, :identity_value,
                :unionid, :mobile_hash, :owner_userid, :event_source_key,
                :payload_hash, CAST(:payload_json AS jsonb), :idempotency_key, :occurred_at, CURRENT_TIMESTAMP
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING *
            """,
            {
                "package_id": int(event.get("package_id") or 0),
                "run_id": int(event.get("run_id") or 0) or None,
                "member_current_id": int(event.get("member_current_id") or 0) or None,
                "event_type": _text(event.get("event_type")),
                "identity_type": _text(event.get("identity_type")),
                "identity_value": _text(event.get("identity_value")),
                "unionid": _text(event.get("unionid")),
                "mobile_hash": _text(event.get("mobile_hash")),
                "owner_userid": _text(event.get("owner_userid")),
                "event_source_key": _text(event.get("event_source_key")),
                "payload_hash": _text(event.get("payload_hash")),
                "payload_json": _json_dumps(event.get("payload_json") or {}),
                "idempotency_key": _text(event.get("idempotency_key")),
                "occurred_at": event.get("occurred_at"),
            },
        )
        return row

    def update_member_event_internal_event_id(self, member_event_id: int, internal_event_id: str) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_member_event
            SET internal_event_id = :internal_event_id
            WHERE id = :member_event_id
            RETURNING *
            """,
            {"member_event_id": int(member_event_id), "internal_event_id": _text(internal_event_id)},
        )

    def acquire_due_packages(
        self,
        refresh_kind: str,
        *,
        limit: int = 20,
        lease_seconds: int = 300,
        due_window_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        if refresh_kind == "daily":
            due_column = "next_daily_refresh_at"
            enabled_column = "daily_enabled"
            watermark_column = "last_daily_refreshed_at"
        else:
            due_column = "next_incremental_refresh_at"
            enabled_column = "incremental_enabled"
            watermark_column = "last_incremental_watermark_at"
        lease_token = "aud_" + uuid4().hex
        return self._write_all(
            f"""
            WITH target AS (
                SELECT id
                FROM ai_audience_package
                WHERE status = 'active'
                  AND {enabled_column} = TRUE
                  AND current_version_id IS NOT NULL
                  AND (
                    {watermark_column} IS NULL
                    OR (
                        {due_column} IS NOT NULL
                        AND {due_column} <= CURRENT_TIMESTAMP + (:due_window_seconds || ' seconds')::interval
                    )
                  )
                  AND (lease_expires_at IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP)
                ORDER BY COALESCE({watermark_column}, TIMESTAMPTZ '1970-01-01') ASC,
                         COALESCE({due_column}, CURRENT_TIMESTAMP) ASC,
                         id ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE ai_audience_package p
            SET lease_token = :lease_token,
                lease_expires_at = CURRENT_TIMESTAMP + (:lease_seconds || ' seconds')::interval,
                updated_at = CURRENT_TIMESTAMP
            FROM target
            WHERE p.id = target.id
            RETURNING p.*
            """,
            {
                "limit": max(1, min(int(limit or 20), 200)),
                "lease_token": lease_token,
                "lease_seconds": int(lease_seconds or 300),
                "due_window_seconds": max(0, min(int(due_window_seconds or 0), 300)),
            },
        )

    def has_launch_refresh_due(self, refresh_kind: str) -> bool:
        if refresh_kind == "daily":
            enabled_column = "daily_enabled"
            watermark_column = "last_daily_refreshed_at"
        else:
            enabled_column = "incremental_enabled"
            watermark_column = "last_incremental_watermark_at"
        row = self._one(
            f"""
            SELECT 1 AS due
            FROM ai_audience_package
            WHERE status = 'active'
              AND {enabled_column} = TRUE
              AND current_version_id IS NOT NULL
              AND {watermark_column} IS NULL
              AND (lease_expires_at IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP)
            LIMIT 1
            """,
            {},
        )
        return bool(row)

    def update_refresh_success(
        self,
        package_id: int,
        *,
        refresh_kind: str,
        started_at: datetime,
        interval_seconds: int,
        daily_refresh_time: str = "02:00",
        timezone_name: str = "Asia/Shanghai",
    ) -> dict[str, Any] | None:
        if refresh_kind == "daily":
            next_daily = next_daily_refresh_at(daily_refresh_time, timezone_name, after=started_at)
            return self._write_one(
                """
                UPDATE ai_audience_package
                SET last_daily_refreshed_at = :started_at,
                    last_incremental_watermark_at = :started_at,
                    next_daily_refresh_at = :next_daily_refresh_at,
                    lease_token = '',
                    lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :package_id
                RETURNING *
                """,
                {"package_id": int(package_id), "started_at": started_at, "next_daily_refresh_at": next_daily},
            )
        return self._write_one(
            """
            UPDATE ai_audience_package
            SET last_incremental_watermark_at = :started_at,
                next_incremental_refresh_at = :started_at + (:interval_seconds || ' seconds')::interval,
                lease_token = '',
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :package_id
            RETURNING *
            """,
            {"package_id": int(package_id), "started_at": started_at, "interval_seconds": max(60, int(interval_seconds or 180))},
        )

    def update_refresh_failure(self, package_id: int, *, refresh_kind: str, backoff_seconds: int = 300, reason: str = "") -> dict[str, Any] | None:
        due_column = "next_daily_refresh_at" if refresh_kind == "daily" else "next_incremental_refresh_at"
        return self._write_one(
            f"""
            UPDATE ai_audience_package
            SET {due_column} = CURRENT_TIMESTAMP + (:backoff_seconds || ' seconds')::interval,
                lease_token = '',
                lease_expires_at = NULL,
                paused_reason = :reason,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :package_id
            RETURNING *
            """,
            {"package_id": int(package_id), "backoff_seconds": max(60, int(backoff_seconds or 300)), "reason": _text(reason)[:500]},
        )

    def poke_dependencies(self, *, source_type: str, source_key: str = "") -> int:
        row = self._write_one(
            """
            WITH matched AS (
                SELECT DISTINCT p.id
                FROM ai_audience_package p
                JOIN ai_audience_package_dependency d ON d.package_id = p.id
                WHERE p.status = 'active'
                  AND p.incremental_enabled = TRUE
                  AND d.source_type = :source_type
                  AND (:source_key = '' OR d.source_key = '' OR d.source_key = :source_key)
            ),
            updated AS (
                UPDATE ai_audience_package p
                SET next_incremental_refresh_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                FROM matched
                WHERE p.id = matched.id
                RETURNING p.id
            )
            SELECT COUNT(*) AS updated_count FROM updated
            """,
            {"source_type": _text(source_type), "source_key": _text(source_key)},
        )
        return int((row or {}).get("updated_count") or 0)

    def list_runs(self, package_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT *
            FROM ai_audience_package_run
            WHERE package_id = :package_id
            ORDER BY id DESC
            LIMIT :limit
            """,
            {"package_id": int(package_id), "limit": max(1, min(int(limit or 50), 200))},
        )

    def list_members(self, package_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT *
            FROM ai_audience_member_current
            WHERE package_id = :package_id
            ORDER BY status ASC, first_entered_at DESC, id DESC
            LIMIT :limit
            """,
            {"package_id": int(package_id), "limit": max(1, min(int(limit or 100), 500))},
        )

    def list_events(self, package_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT *
            FROM ai_audience_member_event
            WHERE package_id = :package_id
            ORDER BY occurred_at DESC, id DESC
            LIMIT :limit
            """,
            {"package_id": int(package_id), "limit": max(1, min(int(limit or 100), 500))},
        )

    def list_member_events_for_run(self, run_id: int, *, event_type: str = "entered") -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT
                event.*,
                COALESCE(identity.primary_external_userid, '') AS external_userid
            FROM ai_audience_member_event event
            LEFT JOIN crm_user_identity identity ON identity.unionid = event.unionid
            WHERE event.run_id = :run_id
              AND event.event_type = :event_type
              AND COALESCE(event.unionid, '') <> ''
            ORDER BY id ASC
            """,
            {"run_id": int(run_id), "event_type": _text(event_type) or "entered"},
        )

    def list_admin_members(self, package_id: int, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        bounded_limit = max(1, min(int(limit or 50), 200))
        bounded_offset = max(0, int(offset or 0))
        rows = self._all(
            """
            WITH active_members AS (
                SELECT *
                FROM ai_audience_member_current
                WHERE package_id = :package_id
                  AND status = 'active'
            ),
            identity_rows AS (
                SELECT
                    unionid,
                    primary_external_userid,
                    profile_json
                FROM crm_user_identity
                WHERE COALESCE(unionid, '') <> ''
            ),
            contact_names AS (
                SELECT DISTINCT ON (external_userid)
                    external_userid,
                    customer_name
                FROM audience_read.wecom_contacts_v1
                WHERE COALESCE(external_userid, '') <> ''
                ORDER BY external_userid, updated_at DESC NULLS LAST
            )
            SELECT
                m.id,
                COALESCE(NULLIF(c.customer_name, ''), NULLIF(i.profile_json->>'name', ''), '未命名客户') AS nickname,
                m.unionid,
                COALESCE(i.primary_external_userid, '') AS external_userid,
                m.first_entered_at AS entered_at,
                COUNT(*) OVER () AS total_count
            FROM active_members m
            LEFT JOIN identity_rows i ON i.unionid = m.unionid
            LEFT JOIN contact_names c ON c.external_userid = i.primary_external_userid
            ORDER BY m.first_entered_at DESC, m.id DESC
            LIMIT :limit OFFSET :offset
            """,
            {"package_id": int(package_id), "limit": bounded_limit, "offset": bounded_offset},
        )
        total = int(rows[0].get("total_count") or 0) if rows else 0
        return rows, total

    def rotate_inbound_secret(self, package_id: int, secret: str) -> dict[str, Any] | None:
        return self._write_one(
            """
            UPDATE ai_audience_package
            SET inbound_webhook_secret = :secret,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :package_id
            RETURNING *
            """,
            {"package_id": int(package_id), "secret": _text(secret)},
        )

    def list_senders(self, package_id: int) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT id, package_id, sender_userid, display_name, priority, status, created_at, updated_at
            FROM ai_audience_package_sender
            WHERE package_id = :package_id
            ORDER BY priority ASC, id ASC
            """,
            {"package_id": int(package_id)},
        )

    def replace_senders(self, package_id: int, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            session.execute(text("DELETE FROM ai_audience_package_sender WHERE package_id = :package_id"), {"package_id": int(package_id)})
            for item in items:
                session.execute(
                    text(
                        """
                        INSERT INTO ai_audience_package_sender (
                            package_id, sender_userid, display_name, priority, status, created_at, updated_at
                        )
                        VALUES (
                            :package_id, :sender_userid, :display_name, :priority, :status,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (package_id, sender_userid) DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            priority = EXCLUDED.priority,
                            status = EXCLUDED.status,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "package_id": int(package_id),
                        "sender_userid": _text(item.get("sender_userid")),
                        "display_name": _text(item.get("display_name")),
                        "priority": int(item.get("priority") or 100),
                        "status": _text(item.get("status")) or "active",
                    },
                )
            session.commit()
        return self.list_senders(package_id)

    def list_ai_audience_batch_rows(self, package_id: int) -> list[dict[str, Any]]:
        relation_parts: list[str] = []
        if self._table_exists("wecom_external_contact_follow_users"):
            relation_parts.append(
                """
                SELECT
                    external_userid,
                    user_id AS owner_userid,
                    COALESCE(NULLIF(remark, ''), '') AS customer_name
                FROM wecom_external_contact_follow_users
                WHERE COALESCE(external_userid, '') <> ''
                  AND COALESCE(user_id, '') <> ''
                  AND COALESCE(relation_status, 'active') = 'active'
                """
            )
        if self._table_exists("wecom_external_contact_identity_map"):
            relation_parts.append(
                """
                SELECT
                    external_userid,
                    follow_user_userid AS owner_userid,
                    COALESCE(NULLIF(name, ''), '') AS customer_name
                FROM wecom_external_contact_identity_map
                WHERE COALESCE(external_userid, '') <> ''
                  AND COALESCE(follow_user_userid, '') <> ''
                  AND COALESCE(status, 'active') = 'active'
                """
            )
        if not relation_parts:
            relation_parts.append("SELECT ''::text AS external_userid, ''::text AS owner_userid, ''::text AS customer_name WHERE FALSE")
        relation_sql = "\nUNION ALL\n".join(relation_parts)
        return self._all(
            f"""
            WITH active_members AS (
                SELECT
                    id,
                    COALESCE(NULLIF(unionid, ''), CASE WHEN identity_type = 'unionid' THEN identity_value ELSE '' END) AS unionid,
                    first_entered_at
                FROM ai_audience_member_current
                WHERE package_id = :package_id
                  AND status = 'active'
            ),
            identity_rows AS (
                SELECT
                    unionid,
                    primary_external_userid
                FROM crm_user_identity
                WHERE COALESCE(unionid, '') <> ''
            ),
            relations AS (
                {relation_sql}
            ),
            whitelist AS (
                SELECT id, sender_userid, display_name, priority
                FROM ai_audience_package_sender
                WHERE package_id = :package_id
                  AND status = 'active'
            ),
            resolved AS (
                SELECT DISTINCT ON (m.id)
                    m.id,
                    m.unionid,
                    COALESCE(i.primary_external_userid, '') AS external_userid,
                    COALESCE(NULLIF(r.customer_name, ''), '未命名客户') AS customer_name,
                    w.sender_userid AS owner_userid,
                    COALESCE(NULLIF(w.display_name, ''), w.sender_userid) AS owner_display_name,
                    ''::text AS skip_reason,
                    w.priority,
                    w.id AS sender_row_id
                FROM active_members m
                JOIN identity_rows i ON i.unionid = m.unionid
                JOIN relations r ON r.external_userid = i.primary_external_userid
                JOIN whitelist w ON w.sender_userid = r.owner_userid
                ORDER BY m.id, w.priority ASC, w.id ASC
            )
            SELECT
                m.id,
                m.unionid,
                COALESCE(r.external_userid, '') AS external_userid,
                COALESCE(r.customer_name, '未命名客户') AS customer_name,
                COALESCE(r.owner_userid, '') AS owner_userid,
                COALESCE(r.owner_display_name, '') AS owner_display_name,
                CASE WHEN r.owner_userid IS NULL THEN 'no_allowed_sender' ELSE '' END AS skip_reason,
                ''::text AS mobile,
                FALSE AS do_not_disturb,
                TRUE AS is_added_wecom,
                FALSE AS is_mobile_bound,
                ''::text AS activation_bucket,
                ''::text AS class_term_no,
                '[]'::jsonb AS tags
            FROM active_members m
            LEFT JOIN resolved r ON r.id = m.id
            ORDER BY m.id ASC
            """,
            {"package_id": int(package_id)},
        )

    def get_member_event(self, member_event_id: int) -> dict[str, Any] | None:
        return self._one("SELECT * FROM ai_audience_member_event WHERE id = :id LIMIT 1", {"id": int(member_event_id)})

    def get_active_subscription_by_target(
        self,
        package_id: int,
        trigger_event_type: str,
        target_type: str,
        webhook_url: str,
    ) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT *
            FROM ai_audience_outbound_subscription
            WHERE package_id = :package_id
              AND status = 'active'
              AND trigger_event_type = :trigger_event_type
              AND target_type = :target_type
              AND webhook_url = :webhook_url
            ORDER BY id ASC
            LIMIT 1
            """,
            {
                "package_id": int(package_id),
                "trigger_event_type": _text(trigger_event_type),
                "target_type": _text(target_type),
                "webhook_url": _text(webhook_url),
            },
        )

    def create_subscription(self, package_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        trigger_event_type = _text(payload.get("trigger_event_type")) or "entered"
        dispatch_mode = _text(payload.get("dispatch_mode")) or "per_member"
        target_type = _text(payload.get("target_type")) or "webhook"
        webhook_url = _text(payload.get("webhook_url"))
        params = {
            "package_id": int(package_id),
            "trigger_event_type": trigger_event_type,
            "dispatch_mode": dispatch_mode,
            "target_type": target_type,
            "webhook_url": webhook_url,
            "signing_secret": _text(payload.get("signing_secret")),
            "headers_json": _json_dumps(payload.get("headers") or {}),
            "payload_template_json": _json_dumps(payload.get("payload_template") or {}),
            "execution_mode": _text(payload.get("execution_mode")) or "execute",
            "requires_approval": bool(payload.get("requires_approval", False)),
            "max_attempts": max(1, int(payload.get("max_attempts") or 5)),
        }
        existing = self.get_active_subscription_by_target(
            int(package_id),
            trigger_event_type,
            target_type,
            webhook_url,
        )
        if existing:
            row = self._write_one(
                """
                UPDATE ai_audience_outbound_subscription
                SET dispatch_mode = :dispatch_mode,
                    signing_secret = :signing_secret,
                    headers_json = CAST(:headers_json AS jsonb),
                    payload_template_json = CAST(:payload_template_json AS jsonb),
                    execution_mode = :execution_mode,
                    requires_approval = :requires_approval,
                    max_attempts = :max_attempts,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :subscription_id
                RETURNING *, TRUE AS deduplicated
                """,
                {**params, "subscription_id": int(existing["id"])},
            )
            if row is None:
                raise RuntimeError("ai audience outbound subscription update failed")
            return row

        row = self._write_one(
            """
            INSERT INTO ai_audience_outbound_subscription (
                package_id, status, trigger_event_type, dispatch_mode, target_type, webhook_url,
                signing_secret, headers_json, payload_template_json, execution_mode,
                requires_approval, max_attempts, created_at, updated_at
            )
            VALUES (
                :package_id, 'active', :trigger_event_type, :dispatch_mode, :target_type, :webhook_url,
                :signing_secret, CAST(:headers_json AS jsonb), CAST(:payload_template_json AS jsonb),
                :execution_mode, :requires_approval, :max_attempts, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING *, FALSE AS deduplicated
            """,
            params,
        )
        if row is None:
            raise RuntimeError("ai audience outbound subscription create failed")
        return row

    def list_subscriptions(self, package_id: int, *, active_only: bool = False, trigger_event_type: str = "") -> list[dict[str, Any]]:
        clauses = ["package_id = :package_id"]
        params: dict[str, Any] = {"package_id": int(package_id)}
        if active_only:
            clauses.append("status = 'active'")
        if _text(trigger_event_type):
            clauses.append("trigger_event_type = :trigger_event_type")
            params["trigger_event_type"] = _text(trigger_event_type)
        return self._all(
            f"""
            SELECT *
            FROM ai_audience_outbound_subscription
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            """,
            params,
        )

    def update_subscription(self, subscription_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        current = self._one("SELECT * FROM ai_audience_outbound_subscription WHERE id = :id LIMIT 1", {"id": int(subscription_id)})
        if current is None:
            return None
        merged = {
            "status": payload.get("status", current.get("status")),
            "webhook_url": payload.get("webhook_url", current.get("webhook_url")),
            "signing_secret": payload.get("signing_secret", current.get("signing_secret")),
            "headers_json": payload.get("headers", current.get("headers_json") or {}),
            "payload_template_json": payload.get("payload_template", current.get("payload_template_json") or {}),
            "execution_mode": payload.get("execution_mode", current.get("execution_mode")),
            "requires_approval": payload.get("requires_approval", current.get("requires_approval")),
            "max_attempts": payload.get("max_attempts", current.get("max_attempts")),
        }
        return self._write_one(
            """
            UPDATE ai_audience_outbound_subscription
            SET status = :status,
                webhook_url = :webhook_url,
                signing_secret = :signing_secret,
                headers_json = CAST(:headers_json AS jsonb),
                payload_template_json = CAST(:payload_template_json AS jsonb),
                execution_mode = :execution_mode,
                requires_approval = :requires_approval,
                max_attempts = :max_attempts,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :subscription_id
            RETURNING *
            """,
            {
                "subscription_id": int(subscription_id),
                "status": _text(merged["status"]) or "active",
                "webhook_url": _text(merged["webhook_url"]),
                "signing_secret": _text(merged["signing_secret"]),
                "headers_json": _json_dumps(merged["headers_json"]),
                "payload_template_json": _json_dumps(merged["payload_template_json"]),
                "execution_mode": _text(merged["execution_mode"]) or "execute",
                "requires_approval": bool(merged["requires_approval"]),
                "max_attempts": max(1, int(merged["max_attempts"] or 5)),
            },
        )

    def record_inbound_webhook(self, package_id: int, payload: dict[str, Any], *, signature_valid: bool, external_effect_job_id: int | None = None) -> dict[str, Any]:
        row = self._write_one(
            """
            INSERT INTO ai_audience_inbound_webhook_event (
                package_id, external_event_id, member_event_id, status, message_json, action_json,
                payload_json, signature_valid, idempotency_key, external_effect_job_id, created_at
            )
            VALUES (
                :package_id, :external_event_id, :member_event_id, :status, CAST(:message_json AS jsonb),
                CAST(:action_json AS jsonb), CAST(:payload_json AS jsonb), :signature_valid,
                :idempotency_key, :external_effect_job_id, CURRENT_TIMESTAMP
            )
            ON CONFLICT (idempotency_key) DO UPDATE SET
                status = EXCLUDED.status
            RETURNING *
            """,
            {
                "package_id": int(package_id),
                "external_event_id": _text(payload.get("external_event_id")),
                "member_event_id": int(payload.get("member_event_id") or 0) or None,
                "status": _text(payload.get("status")),
                "message_json": _json_dumps(payload.get("message") or {}),
                "action_json": _json_dumps(payload.get("action") or {}),
                "payload_json": _json_dumps(payload),
                "signature_valid": bool(signature_valid),
                "idempotency_key": _text(payload.get("idempotency_key")),
                "external_effect_job_id": external_effect_job_id,
            },
        )
        if row is None:
            raise RuntimeError("ai audience inbound webhook record failed")
        return row

    def health(self) -> dict[str, Any]:
        row = self._one(
            """
            SELECT
                (SELECT COUNT(*) FROM ai_audience_package WHERE status = 'active') AS active_package_count,
                (SELECT COUNT(*) FROM ai_audience_package_run WHERE status = 'failed') AS failed_run_count,
                (SELECT MAX(refresh_finished_at) FROM ai_audience_package_run WHERE status = 'succeeded') AS last_success_at
            """
        )
        return row or {}

    def get_agent_prompt(self, agent_code: str) -> dict[str, Any]:
        row = self._one(
            """
            SELECT *
            FROM automation_agent_config
            WHERE agent_code = :agent_code
            LIMIT 1
            """,
            {"agent_code": _text(agent_code)},
        )
        item = dict(row or {})
        return {
            "role_prompt": _text(item.get("published_role_prompt") or item.get("role_prompt")),
            "task_prompt": _text(item.get("published_task_prompt") or item.get("task_prompt")),
            "published_version": int(item.get("published_version") or 0),
            "raw": item,
        }

    def create_agent_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert_available("automation_agent_run", payload)

    def complete_agent_run(self, row_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._update_available("automation_agent_run", row_id, payload)

    def log_agent_llm_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert_available("automation_agent_llm_call_log", payload)

    def record_agent_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._insert_available("automation_agent_output", payload)


def _dependency_source_type(view_name: str) -> str:
    if view_name.endswith("questionnaire_submissions_v1"):
        return "questionnaire_submission"
    if view_name.endswith("orders_v1"):
        return "payment"
    if view_name.endswith("channel_entries_v1"):
        return "channel_entry"
    if view_name.endswith("wecom_contacts_v1"):
        return "wecom_contact"
    if view_name.endswith("identity_universe_v1"):
        return "identity"
    return view_name.replace("audience_read.", "")


def default_refresh_started_at() -> datetime:
    return datetime.now(timezone.utc)


def previous_watermark(package: dict[str, Any], refresh_kind: str, *, started_at: datetime) -> datetime:
    raw = package.get("last_daily_refreshed_at") if refresh_kind == "daily" else package.get("last_incremental_watermark_at")
    text_value = _text(raw)
    if text_value:
        try:
            dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    lookback_seconds = max(0, int(package.get("lookback_seconds") or 600))
    return started_at - timedelta(seconds=lookback_seconds)


def next_daily_refresh_at(daily_refresh_time: str = "02:00", timezone_name: str = "Asia/Shanghai", *, after: datetime | None = None) -> datetime:
    hour, minute = _parse_daily_refresh_time(daily_refresh_time)
    try:
        local_tz = ZoneInfo(_text(timezone_name) or "Asia/Shanghai")
    except ZoneInfoNotFoundError:
        local_tz = timezone.utc
    base = after or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    local_base = base.astimezone(local_tz)
    target = local_base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local_base:
        target = target + timedelta(days=1)
    return target.astimezone(timezone.utc)


def _parse_daily_refresh_time(value: str) -> tuple[int, int]:
    text_value = _text(value) or "02:00"
    parts = text_value.split(":", 1)
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return 3, 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return 3, 0
    return hour, minute


def build_audience_repository() -> SQLAlchemyAudienceRepository:
    return SQLAlchemyAudienceRepository()
