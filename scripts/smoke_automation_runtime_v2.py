#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCENARIOS = {
    "channel-binding",
    "large-channel-protection",
    "future-scan",
    "questionnaire-agent",
    "payment",
    "webhook",
    "scheduled",
}
SMOKE_PREFIX = "smoke_runtime_v2"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_database_url(value: str) -> str:
    if not value:
        return ""
    if "@" not in value or "://" not in value:
        return "<set>"
    scheme, rest = value.split("://", 1)
    return f"{scheme}://***@{rest.split('@', 1)[1]}"


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    counts: dict[str, int] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    real_wecom_send_executed: bool = False


class SmokeFailure(RuntimeError):
    pass


class SmokeDatabase:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn: Any = None

    def connect(self) -> None:
        if self.conn is not None:
            return
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - depends on environment
            raise SmokeFailure(f"psycopg is required for write smoke: {exc}") from exc
        self.conn = psycopg.connect(self.database_url, row_factory=dict_row)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        self.connect()
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(sql, params)

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        self.connect()
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return dict(row) if row else None

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.connect()
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall() or []]

    def scalar(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        row = self.one(sql, params) or {}
        return int(next(iter(row.values()), 0) or 0)

    def commit(self) -> None:
        self.connect()
        assert self.conn is not None
        self.conn.commit()

    def rollback(self) -> None:
        if self.conn is not None:
            self.conn.rollback()


class SmokeHttpClient:
    def __init__(self, app_url: str, *, admin_cookie: str = "", admin_token: str = ""):
        self.app_url = app_url.rstrip("/")
        self.admin_cookie = admin_cookie
        self.admin_token = admin_token
        self._client: Any = None
        if not self.app_url:
            from fastapi.testclient import TestClient

            from aicrm_next.main import app

            self._client = TestClient(app)

    @property
    def mode(self) -> str:
        return "remote-app" if self.app_url else "local-app"

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.admin_cookie:
            headers["Cookie"] = self.admin_cookie
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        if self._client is not None:
            response = self._client.post(path, json=payload, headers=headers)
            if response.status_code >= 400:
                raise SmokeFailure(f"POST {path} failed: {response.status_code} {response.text[:500]}")
            return dict(response.json() or {})
        request = Request(
            f"{self.app_url}{path}",
            data=_json(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SmokeFailure(f"POST {path} failed: {exc.code} {body[:500]}") from exc


class SmokeRunner:
    def __init__(
        self,
        *,
        database_url: str,
        app_url: str = "",
        admin_cookie: str = "",
        admin_token: str = "",
        smoke_run_id: str = "",
        dry_run: bool = True,
        allow_write: bool = False,
        skip_frontend: bool = False,
        db: SmokeDatabase | None = None,
        http: SmokeHttpClient | None = None,
    ):
        self.database_url = database_url
        self.app_url = app_url
        self.admin_cookie = admin_cookie
        self.admin_token = admin_token
        self.smoke_run_id = smoke_run_id or f"{SMOKE_PREFIX}_{uuid.uuid4().hex[:10]}"
        self.dry_run = bool(dry_run)
        self.allow_write = bool(allow_write)
        self.skip_frontend = bool(skip_frontend)
        self.db = db or SmokeDatabase(database_url)
        self.http = http
        self._queue_safety_warnings: list[dict[str, Any]] = []

    def environment(self) -> dict[str, Any]:
        return {
            "database_url_set": bool(self.database_url),
            "database_url": _mask_database_url(self.database_url),
            "app_url": self.app_url,
            "mode": "remote-app" if self.app_url else "local-app",
            "smoke_run_id": self.smoke_run_id,
            "dry_run": self.dry_run,
            "allow_write": self.allow_write,
            "skip_frontend": self.skip_frontend,
            "queue_safety_warnings": self._queue_safety_warnings,
        }

    def run(self, scenario_names: list[str]) -> dict[str, Any]:
        if self.dry_run:
            scenarios = [
                ScenarioResult(
                    name=name,
                    ok=True,
                    diagnostics={"dry_run": True, "would_write": False, "smoke_run_id": self.smoke_run_id},
                )
                for name in scenario_names
            ]
            return self._result(scenarios, [])
        self._assert_write_allowed()
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.database_url
        self.db.connect()
        self._preflight_queue_safety()
        self.http = self.http or SmokeHttpClient(self.app_url, admin_cookie=self.admin_cookie, admin_token=self.admin_token)
        results: list[ScenarioResult] = []
        failures: list[dict[str, Any]] = []
        try:
            for name in scenario_names:
                try:
                    results.append(getattr(self, f"scenario_{name.replace('-', '_')}")())
                except Exception as exc:
                    self.db.rollback()
                    failures.append({"scenario": name, "error": str(exc)})
                    results.append(ScenarioResult(name=name, ok=False, diagnostics={"error": str(exc)}))
            self._apply_worker_claimed_result(results, failures)
            return self._result(results, failures)
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url
            self.db.close()

    def cleanup(self) -> dict[str, Any]:
        self._assert_database_url()
        if not self.smoke_run_id:
            raise SmokeFailure("--smoke-run-id is required for cleanup")
        self.db.connect()
        try:
            pattern = f"{SMOKE_PREFIX}_{self.smoke_run_id}%" if not self.smoke_run_id.startswith(SMOKE_PREFIX) else f"{self.smoke_run_id}%"
            job_ids = self.db.scalar(
                """
                WITH smoke_programs AS (
                    SELECT id FROM automation_program WHERE program_code LIKE %s
                ), smoke_plans AS (
                    SELECT id FROM automation_task_plan_v2 WHERE program_id IN (SELECT id FROM smoke_programs)
                ), updated_jobs AS (
                    UPDATE broadcast_jobs
                    SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                    WHERE source_type = 'automation_runtime_v2'
                      AND (
                        status IN ('queued', 'pending', 'planned')
                        OR (
                            status = 'claimed'
                            AND outbound_task_id IS NULL
                            AND sent_at IS NULL
                        )
                      )
                      AND (content_payload->>'task_plan_id') IN (SELECT id::text FROM smoke_plans)
                    RETURNING id
                )
                SELECT COUNT(*) AS count FROM updated_jobs
                """,
                (pattern,),
            )
            plan_ids = self.db.scalar(
                """
                WITH smoke_programs AS (
                    SELECT id FROM automation_program WHERE program_code LIKE %s
                ), updated_plans AS (
                    UPDATE automation_task_plan_v2
                    SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                    WHERE program_id IN (SELECT id FROM smoke_programs)
                      AND status IN ('planned', 'rendered', 'enqueued', 'skipped', 'failed', 'cancelled')
                    RETURNING id
                )
                SELECT COUNT(*) AS count FROM updated_plans
                """,
                (pattern,),
            )
            self.db.commit()
            return {
                "ok": True,
                "cleanup": True,
                "smoke_run_id": self.smoke_run_id,
                "cancelled_broadcast_jobs": job_ids,
                "cancelled_task_plans": plan_ids,
                "deleted_memberships": 0,
            }
        except Exception:
            self.db.rollback()
            raise
        finally:
            self.db.close()

    def _assert_database_url(self) -> None:
        if not self.database_url:
            raise SmokeFailure("DATABASE_URL or --database-url is required; refusing to fake staging evidence")

    def _assert_write_allowed(self) -> None:
        self._assert_database_url()
        if not self.allow_write:
            raise SmokeFailure("--allow-write is required for non-dry-run smoke")

    def _preflight_queue_safety(self) -> None:
        row = self.db.one(
            """
            SELECT COUNT(*) AS count
            FROM broadcast_jobs
            WHERE source_type = 'automation_runtime_v2'
              AND created_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
              AND (
                status IN ('claimed', 'sending', 'sent', 'failed')
                OR claimed_at IS NOT NULL
                OR sent_at IS NOT NULL
                OR outbound_task_id IS NOT NULL
              )
            """,
        ) or {}
        count = int(row.get("count") or 0)
        if count > 0:
            self._queue_safety_warnings.append(
                {
                    "reason": "recent_runtime_v2_worker_activity_detected",
                    "recent_claimed_or_sent_jobs": count,
                    "action": "pause staging broadcast worker timer before acceptance smoke",
                }
            )

    def _smoke_worker_claimed_count(self) -> int:
        pattern = f"{self.smoke_run_id}%"
        return self.db.scalar(
            """
            WITH smoke_programs AS (
                SELECT id FROM automation_program WHERE program_code LIKE %s
            ), smoke_plans AS (
                SELECT id FROM automation_task_plan_v2 WHERE program_id IN (SELECT id FROM smoke_programs)
            )
            SELECT COUNT(*) AS count
            FROM broadcast_jobs bj
            WHERE bj.source_type = 'automation_runtime_v2'
              AND (bj.content_payload->>'task_plan_id') IN (SELECT id::text FROM smoke_plans)
              AND (
                bj.status IN ('claimed', 'sending', 'sent', 'failed')
                OR bj.claimed_at IS NOT NULL
                OR bj.sent_at IS NOT NULL
                OR bj.outbound_task_id IS NOT NULL
              )
            """,
            (pattern,),
        )

    def _apply_worker_claimed_result(self, results: list[ScenarioResult], failures: list[dict[str, Any]]) -> None:
        claimed = self._smoke_worker_claimed_count()
        if claimed <= 0:
            return
        failure = {
            "scenario": "queue-safety",
            "error": "worker_claimed_smoke_jobs",
            "claimed_smoke_jobs": claimed,
        }
        failures.append(failure)
        for item in results:
            item.ok = False
            item.diagnostics["worker_claimed"] = True
            item.diagnostics["claimed_smoke_jobs"] = claimed

    def _result(self, scenarios: list[ScenarioResult], failures: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "ok": not failures and all(item.ok for item in scenarios),
            "environment": self.environment(),
            "scenarios": [
                {
                    "name": item.name,
                    "ok": item.ok,
                    "counts": item.counts,
                    "diagnostics": item.diagnostics,
                    "real_wecom_send_executed": item.real_wecom_send_executed,
                }
                for item in scenarios
            ],
            "failures": failures,
        }

    def _code(self, suffix: str) -> str:
        return f"{self.smoke_run_id}_{suffix}"

    def _program(self, suffix: str, *, requires_questionnaire: bool = False) -> int:
        code = self._code(f"program_{suffix}")
        row = self.db.one(
            """
            INSERT INTO automation_program (program_code, program_name, status, config_json, created_by, updated_by)
            VALUES (%s, %s, 'active', %s::jsonb, 'runtime_v2_smoke', 'runtime_v2_smoke')
            ON CONFLICT (program_code) DO UPDATE
            SET status = 'active', updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (code, code, _json({"smoke_run_id": self.smoke_run_id})),
        )
        program_id = int((row or {})["id"])
        if requires_questionnaire:
            self.db.one(
                """
                INSERT INTO automation_program_config_block (program_id, block_key, payload_json, status)
                VALUES (%s, 'entry_questionnaire', %s::jsonb, 'published')
                ON CONFLICT (program_id, block_key) DO UPDATE
                SET payload_json = EXCLUDED.payload_json, status = 'published', updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (program_id, _json({"requires_questionnaire": True, "smoke_run_id": self.smoke_run_id})),
            )
        self.db.commit()
        return program_id

    def _channel(self, suffix: str) -> int:
        code = self._code(f"channel_{suffix}")
        row = self.db.one(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, status, scene_value, owner_staff_id
            )
            VALUES (%s, %s, 'active', %s, 'runtime_v2_smoke_owner')
            ON CONFLICT (channel_code) DO UPDATE
            SET status = 'active', scene_value = EXCLUDED.scene_value, updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (code, code, code),
        )
        self.db.commit()
        return int((row or {})["id"])

    def _contact(self, channel_id: int, suffix: str) -> str:
        external = self._code(f"external_{suffix}")
        self.db.one(
            """
            INSERT INTO automation_channel_contact (
                channel_id, external_contact_id, first_channel_entered_at, last_channel_entered_at, source_payload_json
            )
            VALUES (%s, %s, CURRENT_TIMESTAMP - INTERVAL '1 day', CURRENT_TIMESTAMP - INTERVAL '1 day', %s::jsonb)
            ON CONFLICT (channel_id, external_contact_id) WHERE external_contact_id <> '' DO UPDATE
            SET source_payload_json = EXCLUDED.source_payload_json, updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (int(channel_id), external, _json({"smoke_run_id": self.smoke_run_id})),
        )
        self.db.commit()
        return external

    def _task(
        self,
        program_id: int,
        suffix: str,
        *,
        trigger_type: str = "audience_entered",
        target_stage: str = "operating",
        content_mode: str = "unified",
        content_text: str = "runtime v2 smoke",
        agent_config: dict[str, Any] | None = None,
        segment_contents: list[dict[str, Any]] | None = None,
        audience_day_offset: int = 1,
        send_time: str = "",
    ) -> int:
        row = self.db.one(
            """
            INSERT INTO automation_operation_task (
                program_id, task_name, status, trigger_type, send_time, timezone,
                target_audience_code, target_stage_code, audience_day_offset, behavior_filter, content_mode,
                unified_content_json, segment_contents_json, agent_config_json, created_by, updated_by, published_at
            )
            VALUES (%s, %s, 'active', %s, %s, 'Asia/Shanghai', %s, %s, %s, 'none', %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, 'runtime_v2_smoke', 'runtime_v2_smoke', CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                int(program_id),
                self._code(f"task_{suffix}"),
                trigger_type,
                send_time or datetime.now(timezone.utc).strftime("%H:%M"),
                target_stage,
                target_stage,
                int(audience_day_offset),
                content_mode,
                _json({"content_text": content_text, "smoke_run_id": self.smoke_run_id}),
                _json(segment_contents or []),
                _json({"smoke_run_id": self.smoke_run_id, **dict(agent_config or {})}),
            ),
        )
        self.db.commit()
        return int((row or {})["id"])

    def _agent(self, suffix: str) -> str:
        code = self._code(f"agent_{suffix}")
        self.db.one(
            """
            INSERT INTO automation_agent_config (
                agent_code, display_name, enabled, published_role_prompt, published_task_prompt,
                published_variables_json, published_output_schema_json, published_version, published_by
            )
            VALUES (%s, %s, TRUE, 'runtime v2 smoke role', '请根据问卷答案生成测试话术', %s::jsonb, '[]'::jsonb, 1, 'runtime_v2_smoke')
            ON CONFLICT (agent_code) DO UPDATE
            SET published_role_prompt = EXCLUDED.published_role_prompt,
                published_task_prompt = EXCLUDED.published_task_prompt,
                published_version = 1,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (code, code, _json([{"key": "questionnaire.answers", "smoke_run_id": self.smoke_run_id}])),
        )
        self.db.commit()
        return code

    def _questionnaire_submission(self, external: str, suffix: str) -> int:
        slug = self._code(f"questionnaire_{suffix}")
        q = self.db.one(
            """
            INSERT INTO questionnaires (slug, name, title, description)
            VALUES (%s, %s, %s, 'runtime v2 smoke')
            ON CONFLICT (slug) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (slug, slug, slug),
        )
        submission = self.db.one(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score,
                final_tags, assessment_result_snapshot, result_token
            )
            VALUES (%s, %s, %s, '', 10, %s::jsonb, %s::jsonb, %s)
            RETURNING id
            """,
            (
                int((q or {})["id"]),
                external,
                external,
                _json(["smoke"]),
                _json({"answers": {"need": "英语", "layer_key": "default"}, "smoke_run_id": self.smoke_run_id}),
                self._code(f"result_{suffix}"),
            ),
        )
        self.db.commit()
        return int((submission or {})["id"])

    def _bind_channel(self, program_id: int, channel_id: int, *, max_import_count: int = 1000) -> dict[str, Any]:
        assert self.http is not None
        return self.http.post_json(
            f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
            {
                "channel_ids": [channel_id],
                "binding_status": "active",
                "auto_enter_pool": True,
                "initial_audience_code": "pending_questionnaire",
                "batch_size": 50,
                "max_import_count": max_import_count,
                "smoke_run_id": self.smoke_run_id,
            },
        )

    def _counts_for_program(self, program_id: int) -> dict[str, int]:
        return {
            "events": self.db.scalar("SELECT COUNT(*) AS count FROM automation_event_v2 WHERE program_id = %s", (int(program_id),)),
            "memberships": self.db.scalar("SELECT COUNT(*) AS count FROM automation_membership_v2 WHERE program_id = %s", (int(program_id),)),
            "stage_entries": self.db.scalar("SELECT COUNT(*) AS count FROM automation_stage_entry_v2 WHERE program_id = %s", (int(program_id),)),
            "task_plans": self.db.scalar("SELECT COUNT(*) AS count FROM automation_task_plan_v2 WHERE program_id = %s", (int(program_id),)),
            "broadcast_jobs": self.db.scalar(
                """
                SELECT COUNT(*) AS count
                FROM broadcast_jobs bj
                INNER JOIN automation_task_plan_v2 tp ON (bj.content_payload->>'task_plan_id') = tp.id::text
                WHERE bj.source_type = 'automation_runtime_v2' AND tp.program_id = %s
                """,
                (int(program_id),),
            ),
        }

    def _assert_no_real_wecom_send(self, program_id: int) -> None:
        sent = self.db.scalar(
            """
            SELECT COUNT(*) AS count
            FROM broadcast_jobs bj
            INNER JOIN automation_task_plan_v2 tp ON (bj.content_payload->>'task_plan_id') = tp.id::text
            WHERE bj.source_type = 'automation_runtime_v2'
              AND tp.program_id = %s
              AND bj.status IN ('sent', 'sending', 'delivered')
            """,
            (int(program_id),),
        )
        if sent:
            raise SmokeFailure(f"real send status detected in broadcast_jobs: {sent}")

    def scenario_channel_binding(self) -> ScenarioResult:
        program_id = self._program("binding")
        channel_id = self._channel("binding")
        self._task(program_id, "binding_stage", trigger_type="audience_entered", target_stage="operating")
        for i in range(3):
            self._contact(channel_id, f"binding_{i}")
        result = self._bind_channel(program_id, channel_id)
        if result.get("history_imported") is not True or int(result.get("generated_event_count") or 0) <= 0:
            raise SmokeFailure(f"channel binding import failed: {result}")
        counts = self._counts_for_program(program_id)
        again = self._bind_channel(program_id, channel_id)
        counts_again = self._counts_for_program(program_id)
        if counts_again != counts:
            raise SmokeFailure(f"repeat binding changed counts: before={counts}, after={counts_again}, response={again}")
        self._assert_no_real_wecom_send(program_id)
        return ScenarioResult("channel-binding", True, counts, {"program_id": program_id, "channel_id": channel_id, "bind_response": result})

    def scenario_large_channel_protection(self) -> ScenarioResult:
        program_id = self._program("large_guard")
        channel_id = self._channel("large_guard")
        self._task(program_id, "large_guard", trigger_type="audience_entered", target_stage="operating")
        for i in range(3):
            self._contact(channel_id, f"large_guard_{i}")
        result = self._bind_channel(program_id, channel_id, max_import_count=2)
        counts = self._counts_for_program(program_id)
        if result.get("requires_batch_import") is not True or result.get("history_imported") is True:
            raise SmokeFailure(f"large-channel protection did not block import: {result}")
        if any(counts[key] for key in ("events", "memberships", "task_plans", "broadcast_jobs")):
            raise SmokeFailure(f"large-channel protection wrote partial runtime rows: {counts}")
        return ScenarioResult("large-channel-protection", True, counts, {"program_id": program_id, "channel_id": channel_id, "bind_response": result})

    def scenario_future_scan(self) -> ScenarioResult:
        from aicrm_next.automation_runtime_v2.bridge import process_channel_entry_event
        from aicrm_next.shared.postgres_connection import db_session

        program_id = self._program("future_scan")
        channel_id = self._channel("future_scan")
        self._task(program_id, "future_scan", trigger_type="audience_entered", target_stage="operating")
        self._bind_channel(program_id, channel_id)
        external = self._code("external_future_scan")
        with db_session():
            result = process_channel_entry_event(
                channel_id=channel_id,
                external_userid=external,
                event_log_id=None,
                occurred_at=_now(),
                payload_json={"smoke_run_id": self.smoke_run_id, "source": "smoke_future_scan"},
            )
        counts = self._counts_for_program(program_id)
        if not result.get("processed") or counts["events"] < 1 or counts["memberships"] < 1:
            raise SmokeFailure(f"future scan did not process v2 chain: result={result}, counts={counts}")
        self._assert_no_real_wecom_send(program_id)
        return ScenarioResult("future-scan", True, counts, {"program_id": program_id, "channel_id": channel_id, "runtime_result": result})

    def scenario_questionnaire_agent(self) -> ScenarioResult:
        from aicrm_next.automation_runtime_v2 import process_event_payload
        from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

        program_id = self._program("questionnaire_agent", requires_questionnaire=True)
        agent_code = self._agent("questionnaire")
        external = self._code("external_questionnaire")
        self._task(
            program_id,
            "questionnaire_agent",
            trigger_type="audience_entered",
            target_stage="operating",
            content_mode="agent",
            agent_config={"agent_code": agent_code, "mock_output": "runtime v2 smoke agent output"},
        )
        process_event_payload(
            AutomationEventInput(
                event_type="channel_entered",
                source_type="smoke",
                source_id=self._code("questionnaire_channel_entered"),
                idempotency_key=self._code("questionnaire_channel_entered"),
                program_id=program_id,
                external_userid=external,
                payload_json={"requires_questionnaire": True, "smoke_run_id": self.smoke_run_id},
            )
        )
        submission_id = self._questionnaire_submission(external, "questionnaire")
        result = process_event_payload(
            AutomationEventInput(
                event_type="questionnaire_submitted",
                source_type="questionnaire",
                source_id=self._code(f"submission_{submission_id}"),
                idempotency_key=self._code(f"submission_{submission_id}"),
                program_id=program_id,
                external_userid=external,
                payload_json={
                    "questionnaire_id": submission_id,
                    "submission_id": submission_id,
                    "answers": {"need": "英语", "layer_key": "default"},
                    "tags": ["smoke"],
                    "smoke_run_id": self.smoke_run_id,
                },
            )
        )
        counts = self._counts_for_program(program_id)
        bad = self.db.scalar("SELECT COUNT(*) AS count FROM automation_task_plan_v2 WHERE program_id = %s AND skip_reason = 'agent_runtime_content_missing'", (program_id,))
        rendered = self.db.scalar(
            "SELECT COUNT(*) AS count FROM automation_task_plan_v2 WHERE program_id = %s AND rendered_content_json::text LIKE %s",
            (program_id, "%questionnaire%"),
        )
        if bad or counts["task_plans"] < 1 or rendered < 1:
            raise SmokeFailure(f"questionnaire agent render failed: bad={bad}, rendered={rendered}, result={result}")
        self._assert_no_real_wecom_send(program_id)
        return ScenarioResult("questionnaire-agent", True, counts, {"program_id": program_id, "runtime_result": result})

    def scenario_payment(self) -> ScenarioResult:
        from aicrm_next.automation_runtime_v2 import process_event_payload
        from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

        program_id = self._program("payment")
        external = self._code("external_payment")
        self._task(program_id, "payment_event", trigger_type="on_event", content_text="payment event", agent_config={"trigger_event_type": "payment_succeeded"})
        self._task(program_id, "payment_stage", trigger_type="on_enter_stage", target_stage="converted", content_text="converted")
        result = process_event_payload(
            AutomationEventInput(
                event_type="payment_succeeded",
                source_type="payment",
                source_id=self._code("payment_order"),
                idempotency_key=self._code("payment_order"),
                program_id=program_id,
                external_userid=external,
                payload_json={"product_id": "smoke", "amount": 1, "paid_at": _now(), "smoke_run_id": self.smoke_run_id},
            )
        )
        counts = self._counts_for_program(program_id)
        repeat = process_event_payload(
            AutomationEventInput(
                event_type="payment_succeeded",
                source_type="payment",
                source_id=self._code("payment_order"),
                idempotency_key=self._code("payment_order"),
                program_id=program_id,
                external_userid=external,
            )
        )
        repeat_counts = self._counts_for_program(program_id)
        if repeat_counts != counts or counts["task_plans"] < 2:
            raise SmokeFailure(f"payment idempotency/task trigger failed: counts={counts}, repeat={repeat_counts}, repeat_result={repeat}")
        self._assert_no_real_wecom_send(program_id)
        return ScenarioResult("payment", True, counts, {"program_id": program_id, "runtime_result": result})

    def scenario_webhook(self) -> ScenarioResult:
        program_id = self._program("webhook")
        external = self._code("external_webhook")
        webhook_key = self._code("webhook_key")
        self._task(
            program_id,
            "webhook",
            trigger_type="webhook_push",
            content_mode="agent",
            agent_config={"agent_code": "missing", "fallback_content": "webhook fallback", "webhook_key": webhook_key},
        )
        assert self.http is not None
        result = self.http.post_json(
            f"/api/automation-runtime/v2/webhooks/{webhook_key}",
            {
                "external_userid": external,
                "program_id": program_id,
                "external_event_id": self._code("webhook_event"),
                "variables": {"from": "smoke"},
                "smoke_run_id": self.smoke_run_id,
            },
        )
        counts = self._counts_for_program(program_id)
        rendered = self.db.scalar(
            "SELECT COUNT(*) AS count FROM automation_task_plan_v2 WHERE program_id = %s AND rendered_content_json::text LIKE %s",
            (program_id, "%webhook%"),
        )
        if counts["events"] < 1 or counts["task_plans"] < 1 or rendered < 1:
            raise SmokeFailure(f"webhook smoke failed: response={result}, counts={counts}")
        self._assert_no_real_wecom_send(program_id)
        return ScenarioResult("webhook", True, counts, {"program_id": program_id, "webhook_key": webhook_key, "response": result})

    def scenario_scheduled(self) -> ScenarioResult:
        program_id = self._program("scheduled")
        external = self._code("external_scheduled")
        self._task(program_id, "scheduled_daily", trigger_type="scheduled_daily", target_stage="operating", content_text="daily")
        self._task(program_id, "scheduled_offset", trigger_type="scheduled", target_stage="operating", content_text="offset", agent_config={"schedule_type": "stage_day_offset"})
        from aicrm_next.automation_runtime_v2 import process_event_payload
        from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

        process_event_payload(
            AutomationEventInput(
                event_type="channel_entered",
                source_type="smoke",
                source_id=self._code("scheduled_channel"),
                idempotency_key=self._code("scheduled_channel"),
                program_id=program_id,
                external_userid=external,
                payload_json={"smoke_run_id": self.smoke_run_id},
            )
        )
        assert self.http is not None
        first = self.http.post_json("/api/automation-runtime/v2/scheduled/run-due", {"program_id": program_id, "smoke_run_id": self.smoke_run_id})
        counts = self._counts_for_program(program_id)
        second = self.http.post_json("/api/automation-runtime/v2/scheduled/run-due", {"program_id": program_id, "smoke_run_id": self.smoke_run_id})
        repeat_counts = self._counts_for_program(program_id)
        schedule_keys = [
            _text(item.get("schedule_key"))
            for item in self.db.rows(
                "SELECT schedule_key FROM automation_task_plan_v2 WHERE program_id = %s ORDER BY id ASC",
                (program_id,),
            )
        ]
        if (
            counts["task_plans"] < 2
            or counts["broadcast_jobs"] < 2
            or not any(key.startswith("daily_time:") for key in schedule_keys)
            or not any(key.startswith("stage_day_offset:") for key in schedule_keys)
            or repeat_counts != counts
            or int((second.get("counts") or {}).get("planned") or 0) != 0
        ):
            raise SmokeFailure(f"scheduled idempotency failed: first={first}, second={second}, counts={counts}, repeat={repeat_counts}")
        self._assert_no_real_wecom_send(program_id)
        return ScenarioResult("scheduled", True, counts, {"program_id": program_id, "first": first, "second": second})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automation Runtime v2 staging-like smoke harness")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL") or os.getenv("STAGING_DATABASE_URL") or os.getenv("AI_CRM_STAGING_DATABASE_URL") or "")
    parser.add_argument("--app-url", default=os.getenv("STAGING_APP_URL") or os.getenv("AI_CRM_STAGING_APP_URL") or "")
    parser.add_argument("--admin-cookie", default=os.getenv("AICRM_ADMIN_COOKIE") or "")
    parser.add_argument("--admin-token", default=os.getenv("AICRM_ADMIN_TOKEN") or "")
    parser.add_argument("--program-id", type=int, default=0, help="Reserved for future use; smoke creates isolated programs by default.")
    parser.add_argument("--dry-run", action="store_true", help="Plan scenarios without DB writes. This is the default unless --allow-write is set.")
    parser.add_argument("--allow-write", action="store_true", help="Allow smoke test data writes.")
    parser.add_argument("--skip-frontend", action="store_true", help="Do not attempt frontend page checks.")
    parser.add_argument("--scenario", action="append", choices=sorted(SCENARIOS | {"all"}), default=[])
    parser.add_argument("--cleanup", action="store_true", help="Cancel queued jobs and task plans created for a smoke run.")
    parser.add_argument("--smoke-run-id", default="")
    return parser.parse_args(argv)


def scenario_list(values: list[str]) -> list[str]:
    selected = values or ["all"]
    if "all" in selected:
        return [
            "channel-binding",
            "large-channel-protection",
            "future-scan",
            "questionnaire-agent",
            "payment",
            "webhook",
            "scheduled",
        ]
    return selected


def run_cli(argv: list[str] | None = None) -> tuple[int, dict[str, Any]]:
    args = parse_args(argv)
    effective_dry_run = bool(args.dry_run or not args.allow_write)
    runner = SmokeRunner(
        database_url=args.database_url,
        app_url=args.app_url,
        admin_cookie=args.admin_cookie,
        admin_token=args.admin_token,
        smoke_run_id=args.smoke_run_id,
        dry_run=effective_dry_run,
        allow_write=args.allow_write,
        skip_frontend=args.skip_frontend,
    )
    try:
        if args.cleanup:
            if not args.smoke_run_id:
                raise SmokeFailure("--smoke-run-id is required with --cleanup")
            payload = runner.cleanup()
            return (0 if payload.get("ok") else 1), payload
        if not args.database_url:
            raise SmokeFailure("DATABASE_URL or --database-url is required; refusing to fake staging evidence")
        payload = runner.run(scenario_list(args.scenario))
        return (0 if payload.get("ok") else 1), payload
    except Exception as exc:
        return 2, {
            "ok": False,
            "environment": runner.environment(),
            "scenarios": [],
            "failures": [{"error": str(exc)}],
        }


def main(argv: list[str] | None = None) -> int:
    code, payload = run_cli(argv)
    print(_json(payload))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
