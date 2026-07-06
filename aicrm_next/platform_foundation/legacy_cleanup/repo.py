from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from aicrm_next.platform_foundation.external_calls import scrub_summary
from aicrm_next.platform_foundation.external_effects.models import public_datetime, utcnow
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.runtime import fixture_mode

from .models import LegacyCleanupAudit, LegacyDeprecationEntry


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


def _dt(value: Any) -> datetime | None:
    text_value = _text(value)
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _public_entry(row: dict[str, Any] | None) -> LegacyDeprecationEntry | None:
    if not row:
        return None
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["notes_json"] = scrub_summary(_json_obj(payload.get("notes_json")))
    for key in ("deprecated_at", "delete_scheduled_at", "created_at", "updated_at"):
        payload[key] = public_datetime(payload.get(key))
    return LegacyDeprecationEntry(**payload)


def _public_audit(row: dict[str, Any] | None) -> LegacyCleanupAudit | None:
    if not row:
        return None
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["before_json"] = scrub_summary(_json_obj(payload.get("before_json")))
    payload["after_json"] = scrub_summary(_json_obj(payload.get("after_json")))
    payload["created_at"] = public_datetime(payload.get("created_at"))
    return LegacyCleanupAudit(**payload)


class LegacyCleanupRepository:
    def upsert_deprecation(self, entry: dict[str, Any], *, deprecated_at: datetime, delete_scheduled_at: datetime) -> LegacyDeprecationEntry:
        raise NotImplementedError

    def list_deprecations(self, filters: dict[str, Any] | None = None, *, limit: int = 200, offset: int = 0) -> tuple[list[LegacyDeprecationEntry], int]:
        raise NotImplementedError

    def get_deprecation(self, legacy_key: str) -> LegacyDeprecationEntry | None:
        raise NotImplementedError

    def due_deprecations(self, *, now: datetime, limit: int = 50) -> list[LegacyDeprecationEntry]:
        raise NotImplementedError

    def mark_deleted(self, legacy_key: str, *, delete_job_id: str, notes: dict[str, Any]) -> LegacyDeprecationEntry | None:
        raise NotImplementedError

    def mark_failed(self, legacy_key: str, *, error: str, notes: dict[str, Any]) -> LegacyDeprecationEntry | None:
        raise NotImplementedError

    def record_audit(self, *, legacy_key: str, action: str, operator: str, before: dict[str, Any], after: dict[str, Any]) -> LegacyCleanupAudit:
        raise NotImplementedError

    def list_audits(self, *, legacy_key: str = "", limit: int = 50) -> list[LegacyCleanupAudit]:
        raise NotImplementedError

    def recent_legacy_execution_count(self, *, legacy_key: str, since: datetime) -> int:
        raise NotImplementedError

    def legacy_action_counts(self, *, since: datetime) -> dict[str, dict[str, int]]:
        raise NotImplementedError


class SQLAlchemyLegacyCleanupRepository(LegacyCleanupRepository):
    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or get_session_factory()

    def _one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            return dict(row) if row else None

    def _all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            return [dict(row) for row in rows]

    def _write_one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            session.commit()
            return dict(row) if row else None

    def upsert_deprecation(self, entry: dict[str, Any], *, deprecated_at: datetime, delete_scheduled_at: datetime) -> LegacyDeprecationEntry:
        notes = scrub_summary(dict(entry.get("notes_json") or {}))
        row = self._write_one(
            """
            INSERT INTO legacy_webhook_deprecation_registry (
                legacy_key, legacy_type, legacy_route, legacy_module, status,
                deprecated_at, deprecated_by, deprecation_reason, replacement_route,
                delete_scheduled_at, delete_status, delete_job_id, notes_json,
                created_at, updated_at
            )
            VALUES (
                :legacy_key, :legacy_type, :legacy_route, :legacy_module, :status,
                CAST(:deprecated_at AS timestamptz), :deprecated_by, :deprecation_reason,
                :replacement_route, CAST(:delete_scheduled_at AS timestamptz),
                :delete_status, '', CAST(:notes_json AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (legacy_key) DO UPDATE
            SET legacy_type = EXCLUDED.legacy_type,
                legacy_route = EXCLUDED.legacy_route,
                legacy_module = EXCLUDED.legacy_module,
                status = CASE
                    WHEN legacy_webhook_deprecation_registry.status = 'deleted' THEN legacy_webhook_deprecation_registry.status
                    ELSE EXCLUDED.status
                END,
                deprecated_at = COALESCE(legacy_webhook_deprecation_registry.deprecated_at, EXCLUDED.deprecated_at),
                deprecated_by = EXCLUDED.deprecated_by,
                deprecation_reason = EXCLUDED.deprecation_reason,
                replacement_route = EXCLUDED.replacement_route,
                delete_scheduled_at = COALESCE(legacy_webhook_deprecation_registry.delete_scheduled_at, EXCLUDED.delete_scheduled_at),
                delete_status = CASE
                    WHEN legacy_webhook_deprecation_registry.delete_status = 'deleted' THEN legacy_webhook_deprecation_registry.delete_status
                    ELSE EXCLUDED.delete_status
                END,
                notes_json = legacy_webhook_deprecation_registry.notes_json || EXCLUDED.notes_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            {
                "legacy_key": _text(entry.get("legacy_key")),
                "legacy_type": _text(entry.get("legacy_type")),
                "legacy_route": _text(entry.get("legacy_route")),
                "legacy_module": _text(entry.get("legacy_module")),
                "status": _text(entry.get("status")) or "deprecated",
                "deprecated_at": public_datetime(deprecated_at),
                "deprecated_by": _text(entry.get("deprecated_by")) or "p0_1_external_effect_queue_migration",
                "deprecation_reason": _text(entry.get("deprecation_reason")) or "All outbound effects now use External Effect Queue",
                "replacement_route": _text(entry.get("replacement_route")) or "/admin/push-center",
                "delete_scheduled_at": public_datetime(delete_scheduled_at),
                "delete_status": _text(entry.get("delete_status")) or "scheduled",
                "notes_json": _json_dumps(notes),
            },
        )
        item = _public_entry(row)
        if item is None:
            raise RuntimeError("legacy deprecation upsert failed")
        return item

    def list_deprecations(self, filters: dict[str, Any] | None = None, *, limit: int = 200, offset: int = 0) -> tuple[list[LegacyDeprecationEntry], int]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key in ("legacy_key", "legacy_type", "legacy_module", "status", "delete_status"):
            value = _text(filters.get(key))
            if value:
                clauses.append(f"{key} = :{key}")
                params[key] = value
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        count_row = self._one(f"SELECT COUNT(*) AS total FROM legacy_webhook_deprecation_registry {where}", params)
        rows = self._all(
            f"""
            SELECT *
            FROM legacy_webhook_deprecation_registry
            {where}
            ORDER BY delete_scheduled_at ASC NULLS LAST, id ASC
            LIMIT :limit OFFSET :offset
            """,
            {**params, "limit": max(1, min(int(limit or 200), 500)), "offset": max(0, int(offset or 0))},
        )
        return [entry for row in rows if (entry := _public_entry(row)) is not None], int((count_row or {}).get("total") or 0)

    def get_deprecation(self, legacy_key: str) -> LegacyDeprecationEntry | None:
        return _public_entry(self._one("SELECT * FROM legacy_webhook_deprecation_registry WHERE legacy_key = :legacy_key LIMIT 1", {"legacy_key": _text(legacy_key)}))

    def due_deprecations(self, *, now: datetime, limit: int = 50) -> list[LegacyDeprecationEntry]:
        rows = self._all(
            """
            SELECT *
            FROM legacy_webhook_deprecation_registry
            WHERE delete_status = 'scheduled'
              AND delete_scheduled_at <= CAST(:now AS timestamptz)
            ORDER BY delete_scheduled_at ASC, id ASC
            LIMIT :limit
            """,
            {"now": public_datetime(now), "limit": max(1, min(int(limit or 50), 200))},
        )
        return [entry for row in rows if (entry := _public_entry(row)) is not None]

    def mark_deleted(self, legacy_key: str, *, delete_job_id: str, notes: dict[str, Any]) -> LegacyDeprecationEntry | None:
        return _public_entry(
            self._write_one(
                """
                UPDATE legacy_webhook_deprecation_registry
                SET status = 'deleted',
                    delete_status = 'deleted',
                    delete_job_id = :delete_job_id,
                    notes_json = notes_json || CAST(:notes_json AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
                WHERE legacy_key = :legacy_key
                RETURNING *
                """,
                {"legacy_key": _text(legacy_key), "delete_job_id": _text(delete_job_id), "notes_json": _json_dumps(scrub_summary(notes or {}))},
            )
        )

    def mark_failed(self, legacy_key: str, *, error: str, notes: dict[str, Any]) -> LegacyDeprecationEntry | None:
        merged = {**dict(notes or {}), "error": _text(error)}
        return _public_entry(
            self._write_one(
                """
                UPDATE legacy_webhook_deprecation_registry
                SET delete_status = 'failed',
                    notes_json = notes_json || CAST(:notes_json AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
                WHERE legacy_key = :legacy_key
                RETURNING *
                """,
                {"legacy_key": _text(legacy_key), "notes_json": _json_dumps(scrub_summary(merged))},
            )
        )

    def record_audit(self, *, legacy_key: str, action: str, operator: str, before: dict[str, Any], after: dict[str, Any]) -> LegacyCleanupAudit:
        row = self._write_one(
            """
            INSERT INTO legacy_webhook_cleanup_audit (
                audit_id, legacy_key, action, operator, before_json, after_json, created_at
            )
            VALUES (
                :audit_id, :legacy_key, :action, :operator,
                CAST(:before_json AS jsonb), CAST(:after_json AS jsonb), CURRENT_TIMESTAMP
            )
            RETURNING *
            """,
            {
                "audit_id": "lwca_" + uuid4().hex,
                "legacy_key": _text(legacy_key),
                "action": _text(action),
                "operator": _text(operator) or "system",
                "before_json": _json_dumps(scrub_summary(before or {})),
                "after_json": _json_dumps(scrub_summary(after or {})),
            },
        )
        audit = _public_audit(row)
        if audit is None:
            raise RuntimeError("legacy cleanup audit insert failed")
        return audit

    def list_audits(self, *, legacy_key: str = "", limit: int = 50) -> list[LegacyCleanupAudit]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 50), 200))}
        if _text(legacy_key):
            clauses.append("legacy_key = :legacy_key")
            params["legacy_key"] = _text(legacy_key)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._all(
            f"""
            SELECT *
            FROM legacy_webhook_cleanup_audit
            {where}
            ORDER BY id DESC
            LIMIT :limit
            """,
            params,
        )
        return [audit for row in rows if (audit := _public_audit(row)) is not None]

    def recent_legacy_execution_count(self, *, legacy_key: str, since: datetime) -> int:
        row = self._one(
            """
            SELECT COUNT(*) AS total
            FROM legacy_webhook_cleanup_audit
            WHERE legacy_key = :legacy_key
              AND action = 'legacy_real_execution'
              AND created_at >= CAST(:since AS timestamptz)
            """,
            {"legacy_key": _text(legacy_key), "since": public_datetime(since)},
        )
        return int((row or {}).get("total") or 0)

    def legacy_action_counts(self, *, since: datetime) -> dict[str, dict[str, int]]:
        rows = self._all(
            """
            SELECT legacy_key, action, COUNT(*) AS total
            FROM legacy_webhook_cleanup_audit
            WHERE action IN ('legacy_path_invoked', 'legacy_real_execution')
              AND created_at >= CAST(:since AS timestamptz)
            GROUP BY legacy_key, action
            """,
            {"since": public_datetime(since)},
        )
        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            key = _text(row.get("legacy_key"))
            action = _text(row.get("action"))
            if not key or not action:
                continue
            counts.setdefault(key, {})[action] = int(row.get("total") or 0)
        return counts


class InMemoryLegacyCleanupRepository(LegacyCleanupRepository):
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._audits: list[dict[str, Any]] = []
        self._next_id = 1
        self._next_audit_id = 1

    def upsert_deprecation(self, entry: dict[str, Any], *, deprecated_at: datetime, delete_scheduled_at: datetime) -> LegacyDeprecationEntry:
        legacy_key = _text(entry.get("legacy_key"))
        existing = self._find(legacy_key)
        now_text = public_datetime(utcnow())
        if existing:
            existing.update(
                {
                    "legacy_type": _text(entry.get("legacy_type")),
                    "legacy_route": _text(entry.get("legacy_route")),
                    "legacy_module": _text(entry.get("legacy_module")),
                    "deprecated_by": _text(entry.get("deprecated_by")) or "p0_1_external_effect_queue_migration",
                    "deprecation_reason": _text(entry.get("deprecation_reason")) or "All outbound effects now use External Effect Queue",
                    "replacement_route": _text(entry.get("replacement_route")) or "/admin/push-center",
                    "notes_json": {**dict(existing.get("notes_json") or {}), **scrub_summary(dict(entry.get("notes_json") or {}))},
                    "updated_at": now_text,
                }
            )
            if existing.get("status") != "deleted":
                existing["status"] = _text(entry.get("status")) or "deprecated"
            if existing.get("delete_status") != "deleted":
                existing["delete_status"] = _text(entry.get("delete_status")) or "scheduled"
            if not existing.get("deprecated_at"):
                existing["deprecated_at"] = public_datetime(deprecated_at)
            if not existing.get("delete_scheduled_at"):
                existing["delete_scheduled_at"] = public_datetime(delete_scheduled_at)
            item = _public_entry(existing)
            assert item is not None
            return item
        row = {
            "id": self._next_id,
            "legacy_key": legacy_key,
            "legacy_type": _text(entry.get("legacy_type")),
            "legacy_route": _text(entry.get("legacy_route")),
            "legacy_module": _text(entry.get("legacy_module")),
            "status": _text(entry.get("status")) or "deprecated",
            "deprecated_at": public_datetime(deprecated_at),
            "deprecated_by": _text(entry.get("deprecated_by")) or "p0_1_external_effect_queue_migration",
            "deprecation_reason": _text(entry.get("deprecation_reason")) or "All outbound effects now use External Effect Queue",
            "replacement_route": _text(entry.get("replacement_route")) or "/admin/push-center",
            "delete_scheduled_at": public_datetime(delete_scheduled_at),
            "delete_status": _text(entry.get("delete_status")) or "scheduled",
            "delete_job_id": "",
            "notes_json": scrub_summary(dict(entry.get("notes_json") or {})),
            "created_at": now_text,
            "updated_at": now_text,
        }
        self._next_id += 1
        self._entries.append(row)
        item = _public_entry(row)
        assert item is not None
        return item

    def list_deprecations(self, filters: dict[str, Any] | None = None, *, limit: int = 200, offset: int = 0) -> tuple[list[LegacyDeprecationEntry], int]:
        filters = dict(filters or {})
        rows = list(self._entries)
        for key in ("legacy_key", "legacy_type", "legacy_module", "status", "delete_status"):
            expected = _text(filters.get(key))
            if expected:
                rows = [row for row in rows if _text(row.get(key)) == expected]
        rows.sort(key=lambda row: (row.get("delete_scheduled_at") or "9999", int(row.get("id") or 0)))
        total = len(rows)
        window = rows[max(0, int(offset or 0)) : max(0, int(offset or 0)) + max(1, min(int(limit or 200), 500))]
        return [entry for row in window if (entry := _public_entry(row)) is not None], total

    def get_deprecation(self, legacy_key: str) -> LegacyDeprecationEntry | None:
        return _public_entry(self._find(legacy_key))

    def due_deprecations(self, *, now: datetime, limit: int = 50) -> list[LegacyDeprecationEntry]:
        rows = [
            row
            for row in self._entries
            if row.get("delete_status") == "scheduled"
            and (scheduled := _dt(row.get("delete_scheduled_at"))) is not None
            and scheduled <= now
        ]
        rows.sort(key=lambda row: (row.get("delete_scheduled_at") or "", int(row.get("id") or 0)))
        return [entry for row in rows[: max(1, min(int(limit or 50), 200))] if (entry := _public_entry(row)) is not None]

    def mark_deleted(self, legacy_key: str, *, delete_job_id: str, notes: dict[str, Any]) -> LegacyDeprecationEntry | None:
        row = self._find(legacy_key)
        if not row:
            return None
        row.update(
            {
                "status": "deleted",
                "delete_status": "deleted",
                "delete_job_id": _text(delete_job_id),
                "notes_json": {**dict(row.get("notes_json") or {}), **scrub_summary(dict(notes or {}))},
                "updated_at": public_datetime(utcnow()),
            }
        )
        return _public_entry(row)

    def mark_failed(self, legacy_key: str, *, error: str, notes: dict[str, Any]) -> LegacyDeprecationEntry | None:
        row = self._find(legacy_key)
        if not row:
            return None
        row.update(
            {
                "delete_status": "failed",
                "notes_json": {**dict(row.get("notes_json") or {}), **scrub_summary({**dict(notes or {}), "error": _text(error)})},
                "updated_at": public_datetime(utcnow()),
            }
        )
        return _public_entry(row)

    def record_audit(self, *, legacy_key: str, action: str, operator: str, before: dict[str, Any], after: dict[str, Any]) -> LegacyCleanupAudit:
        row = {
            "id": self._next_audit_id,
            "audit_id": "lwca_" + uuid4().hex,
            "legacy_key": _text(legacy_key),
            "action": _text(action),
            "operator": _text(operator) or "system",
            "before_json": scrub_summary(before or {}),
            "after_json": scrub_summary(after or {}),
            "created_at": public_datetime(utcnow()),
        }
        self._next_audit_id += 1
        self._audits.append(row)
        audit = _public_audit(row)
        assert audit is not None
        return audit

    def list_audits(self, *, legacy_key: str = "", limit: int = 50) -> list[LegacyCleanupAudit]:
        rows = list(self._audits)
        if _text(legacy_key):
            rows = [row for row in rows if _text(row.get("legacy_key")) == _text(legacy_key)]
        rows.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
        return [audit for row in rows[: max(1, min(int(limit or 50), 200))] if (audit := _public_audit(row)) is not None]

    def recent_legacy_execution_count(self, *, legacy_key: str, since: datetime) -> int:
        return len(
            [
                row
                for row in self._audits
                if row.get("legacy_key") == _text(legacy_key)
                and row.get("action") == "legacy_real_execution"
                and (created := _dt(row.get("created_at"))) is not None
                and created >= since
            ]
        )

    def legacy_action_counts(self, *, since: datetime) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}
        for row in self._audits:
            action = _text(row.get("action"))
            if action not in {"legacy_path_invoked", "legacy_real_execution"}:
                continue
            created = _dt(row.get("created_at"))
            if created is None or created < since:
                continue
            key = _text(row.get("legacy_key"))
            if not key:
                continue
            bucket = counts.setdefault(key, {})
            bucket[action] = bucket.get(action, 0) + 1
        return counts

    def _find(self, legacy_key: str) -> dict[str, Any] | None:
        key = _text(legacy_key)
        for row in self._entries:
            if row.get("legacy_key") == key:
                return row
        return None


_fixture_repo = InMemoryLegacyCleanupRepository()


def reset_legacy_cleanup_fixture_state() -> None:
    global _fixture_repo
    _fixture_repo = InMemoryLegacyCleanupRepository()


def build_legacy_cleanup_repository() -> LegacyCleanupRepository:
    if fixture_mode():
        return _fixture_repo
    return SQLAlchemyLegacyCleanupRepository()
