from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import date, datetime, timezone
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import RepositoryProviderError
from aicrm_next.shared.runtime import production_data_ready, raw_database_url

from .time_helpers import DEFAULT_SEND_TIME as _DEFAULT_CAMPAIGN_SEND_TIME
from .time_helpers import DEFAULT_TIMEZONE as _DEFAULT_CAMPAIGN_TIMEZONE
from .time_helpers import campaign_step_due_iso


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _json_dump(value: Any) -> str:
    def _default(item: Any) -> str:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError(f"Object of type {item.__class__.__name__} is not JSON serializable")

    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=_default)


def _resolve_unionid_by_external_userid(conn: Any, external_userid: str) -> str:
    external = _text(external_userid)
    if not external:
        return ""
    try:
        row = conn.execute(
            """
            SELECT unionid
            FROM crm_user_identity
            WHERE primary_external_userid = %s
               OR jsonb_exists(external_userids_json, %s)
            ORDER BY CASE WHEN primary_external_userid = %s THEN 0 ELSE 1 END,
                     updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (external, external, external),
        ).fetchone()
    except Exception:
        return ""
    return _text((row or {}).get("unionid"))


def _unionid_targets_from_external_members(conn: Any, members: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    unionids: list[str] = []
    normalized_members: list[dict[str, Any]] = []
    for member in members:
        unionid = _text(member.get("unionid")) or _resolve_unionid_by_external_userid(conn, member.get("external_contact_id"))
        if not unionid:
            continue
        if unionid not in unionids:
            unionids.append(unionid)
        sanitized = {key: value for key, value in dict(member).items() if key not in {"external_contact_id", "external_userid"}}
        sanitized["unionid"] = unionid
        normalized_members.append(sanitized)
    return unionids, normalized_members


def _limit(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _offset(value: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def connect_cloud_campaign_read_db(database_url: str) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(_psycopg_url(database_url), row_factory=dict_row)
    except Exception as exc:
        raise RepositoryProviderError(f"cloud campaign read repository unavailable: {exc}") from exc


class CloudPlanRepository(Protocol):
    def list_plans(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_plan(self, plan_id: str) -> dict[str, Any] | None: ...
    def plan_stats(self, plan_id: str) -> dict[str, int]: ...
    def list_recipients(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_recipient(self, plan_id: str, recipient_id: int) -> dict[str, Any] | None: ...
    def list_recipient_messages(self, recipient_id: int) -> list[dict[str, Any]]: ...
    def approve_plan(self, plan_id: str, *, operator: str) -> dict[str, Any] | None: ...
    def reject_plan(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None: ...
    def create_or_reuse_plan_broadcast_job(
        self,
        plan_id: str,
        *,
        operator: str,
        source_event_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]: ...
    def create_or_reuse_recipient_broadcast_jobs(
        self,
        plan_id: str,
        *,
        operator: str,
        source_event_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]: ...
    def create_or_reuse_agent_send_plan(
        self,
        *,
        external_event_id: str,
        package_key: str,
        external_userid: str,
        owner_userid: str,
        content_package: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]: ...
    def approve_recipient(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]: ...
    def reject_recipient(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]: ...
    def update_recipient_message(
        self,
        plan_id: str,
        recipient_id: int,
        message_id: int,
        *,
        content_package: dict[str, Any],
        day_offset: Any = None,
        send_time: Any = None,
        operator: str,
    ) -> dict[str, Any]: ...


def _plan_view(row: dict[str, Any], stats: dict[str, int] | None = None) -> dict[str, Any]:
    selection = _json(row.get("selection_json"), default={})
    stats = stats or {}
    target_count = int(row.get("target_count") or row.get("candidate_count") or stats.get("target_count") or 0)
    return {
        "plan_id": _text(row.get("plan_id")),
        "display_name": _text(row.get("display_name")) or _text(row.get("intent")) or _text(row.get("plan_id")),
        "owner_userid": _text(row.get("owner_userid")) or _text(selection.get("owner_userid")),
        "target_count": target_count,
        "approved_count": int(stats.get("approved_count") or 0),
        "pending_count": int(stats.get("pending_count") or 0),
        "rejected_count": int(stats.get("rejected_count") or 0),
        "sent_count": int(stats.get("sent_count") or 0),
        "failed_count": int(stats.get("failed_count") or 0),
        "review_status": _text(row.get("review_status")) or ("rejected" if _text(row.get("status")) == "rejected" else "pending_review"),
        "run_status": _text(row.get("run_status")) or _text(row.get("status")) or "draft",
        "updated_at": row.get("updated_at") or "",
        "source_type": _text(row.get("source_type")) or "cloud_plan",
    }


def _recipient_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipient_id": int(row.get("id") or row.get("recipient_id") or 0),
        "external_userid": _text(row.get("external_userid")),
        "display_name": _text(row.get("display_name")) or _text(row.get("external_userid")),
        "owner_userid": _text(row.get("owner_userid")),
        "updated_at": row.get("updated_at") or "",
        "planned_message_count": int(row.get("planned_message_count") or 0),
        "approval_status": _text(row.get("approval_status")) or "pending",
        "send_status": _text(row.get("send_status")) or "pending",
        "approved_by": _text(row.get("approved_by")),
        "approved_at": row.get("approved_at"),
        "rejected_by": _text(row.get("rejected_by")),
        "rejected_at": row.get("rejected_at"),
        "reject_reason": _text(row.get("reject_reason")),
        "broadcast_job_id": row.get("broadcast_job_id"),
        "last_error": _text(row.get("last_error")),
        "source_type": _text(row.get("source_type")) or "cloud_plan",
        "supports_recipient_approval": bool(row.get("supports_recipient_approval", True)),
    }


def _message_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": int(row.get("id") or row.get("message_id") or 0),
        "sequence_index": int(row.get("sequence_index") or 0),
        "day_offset": int(row.get("day_offset") or 0),
        "send_time": _text(row.get("send_time")),
        "content_text": _text(row.get("content_text")),
        "content_payload": _json(row.get("content_payload_json"), default={}),
        "attachments": _json(row.get("attachments_json"), default=[]),
        "status": _text(row.get("status")) or "pending",
        "sent_at": row.get("sent_at"),
        "last_error": _text(row.get("last_error")),
        "source_type": _text(row.get("source_type")) or "cloud_plan",
    }


def _content_payload_for_package(content_package: dict[str, Any]) -> dict[str, Any]:
    package = {
        "content_text": _text(content_package.get("content_text")),
        "image_library_ids": list(content_package.get("image_library_ids") or []),
        "miniprogram_library_ids": list(content_package.get("miniprogram_library_ids") or []),
        "attachment_library_ids": list(content_package.get("attachment_library_ids") or []),
    }
    return {
        "content_package": package,
        "image_library_ids": package["image_library_ids"],
        "image_media_ids": [],
        "miniprogram_library_ids": package["miniprogram_library_ids"],
        "attachment_library_ids": package["attachment_library_ids"],
    }


def _legacy_recipient_status(member_status: str) -> tuple[str, str]:
    status = _text(member_status)
    if status in {"completed", "sent"}:
        return "approved", "sent"
    if status in {"failed"}:
        return "approved", "failed"
    if status in {"cancelled", "stopped"}:
        return "rejected", "cancelled"
    if status in {"running", "queued"}:
        return "approved", "queued"
    return "pending", "pending"


_LEGACY_GROUP_KEY_SQL = "COALESCE(NULLIF(c.metadata_json->>'group_code', ''), c.campaign_code)"
_LEGACY_GROUP_KEY_UPDATE_SQL = _LEGACY_GROUP_KEY_SQL.replace("c.", "")
_LEGACY_GROUP_LABEL_SQL = "COALESCE(MAX(NULLIF(c.metadata_json->>'group_label', '')), MAX(NULLIF(c.display_name, '')), " + _LEGACY_GROUP_KEY_SQL + ")"
_CAMPAIGN_QUEUE_SOURCE_TYPE = "campaign"
_CAMPAIGN_QUEUE_SOURCE_TABLE = "campaign_members"
_CAMPAIGN_QUEUE_CONTENT_TYPE = "private_message"
_CAMPAIGN_QUEUE_CHANNEL = "wecom_private"
_CAMPAIGN_QUEUE_TARGET_KIND = "unionid"
_CAMPAIGN_OPEN_JOB_STATUSES = ["waiting_approval", "queued", "claimed"]
_CLOUD_HAS_MATCHING_LEGACY_GROUP_SQL = f"""
EXISTS (
    SELECT 1
    FROM campaigns c
    WHERE {_LEGACY_GROUP_KEY_SQL} = cloud_broadcast_plans.plan_id
)
"""
_CLOUD_PLAN_HAS_TARGETS_SQL = "COALESCE(candidate_count, 0) > 0"
_LEGACY_HAS_TARGETED_CLOUD_PLAN_SQL = f"""
EXISTS (
    SELECT 1
    FROM cloud_broadcast_plans p
    WHERE p.plan_id = {_LEGACY_GROUP_KEY_SQL}
      AND COALESCE(p.candidate_count, 0) > 0
)
"""


def _campaign_job_source_id(*, campaign_id: int, campaign_segment_id: int, step_index: int) -> str:
    return f"{int(campaign_id)}:{int(campaign_segment_id)}:{int(step_index)}"


def _legacy_campaign_job_source_id(*, campaign_id: int, step_index: int) -> str:
    return f"{int(campaign_id)}:{int(step_index)}"


def _campaign_private_broadcast_payload(*, campaign: dict[str, Any], step: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "channel": _CAMPAIGN_QUEUE_CHANNEL,
        "target_kind": _CAMPAIGN_QUEUE_TARGET_KIND,
        "campaign": campaign,
        "step": step,
        "members": members,
    }


def _broadcast_job_columns(conn: Any) -> set[str]:
    try:
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = ANY(current_schemas(false))
              AND table_name = 'broadcast_jobs'
            """
        ).fetchall()
    except Exception:
        return set()
    return {_text(row.get("column_name")) for row in rows if _text(row.get("column_name"))}


def _campaign_private_broadcast_job_extra_fields(available_columns: set[str]) -> tuple[list[str], list[str], list[Any]]:
    fields: list[tuple[str, Any]] = []
    if "business_domain" in available_columns:
        fields.append(("business_domain", "automation_ops"))
    if "channel" in available_columns:
        fields.append(("channel", _CAMPAIGN_QUEUE_CHANNEL))
    if "target_kind" in available_columns:
        fields.append(("target_kind", _CAMPAIGN_QUEUE_TARGET_KIND))
    if not fields:
        return [], [], []
    return [field for field, _value in fields], ["%s"] * len(fields), [value for _field, value in fields]


def _plan_broadcast_idempotency_key(plan_id: str, *, source_event_id: str = "", idempotency_key: str = "") -> str:
    source = _text(idempotency_key) or _text(source_event_id) or _text(plan_id)
    return f"ops_plan_approved_broadcast:{source}"[:240]


def _plan_broadcast_content_payload(*, plan_id: str, owner_userid: str, target_count: int, source_event_id: str) -> dict[str, Any]:
    return {
        "plan_id": _text(plan_id),
        "message_mode": "ops_plan_approval_broadcast",
        "owner_userid": _text(owner_userid),
        "target_count": int(target_count or 0),
        "source_event_id": _text(source_event_id),
    }


def _plan_broadcast_summary(plan: dict[str, Any], *, target_count: int) -> str:
    label = _text(plan.get("display_name")) or _text(plan.get("intent")) or _text(plan.get("plan_id"))
    return f"{label} · {int(target_count or 0)} recipients"


def _agent_plan_id(external_event_id: str) -> str:
    normalized = _text(external_event_id)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", ":"} else "_" for ch in normalized)[:120]
    return f"agent_plan:{safe or digest}:{digest}"


class PostgresCloudPlanRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(_text(database_url or raw_database_url() or os.getenv("DATABASE_URL")))
        if not self._database_url:
            raise RepositoryProviderError("cloud_orchestrator production repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RepositoryProviderError(f"cloud_orchestrator production repository unavailable: {exc}") from exc

    def _audit(self, conn, *, operator: str, action_type: str, target_type: str, target_id: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO admin_operation_logs (operator, action_type, target_type, target_id, before_json, after_json, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, CURRENT_TIMESTAMP)
            """,
            (_text(operator) or "crm_console", action_type, target_type, target_id, _json_dump(before), _json_dump(after)),
        )

    def _approve_and_start_legacy_group(self, conn, plan_id: str, *, operator: str) -> dict[str, Any] | None:
        normalized_plan_id = _text(plan_id)
        campaigns = conn.execute(
            """
            SELECT c.*
            FROM campaigns c
            WHERE """
            + _LEGACY_GROUP_KEY_SQL
            + """
             = %s
            FOR UPDATE
            """,
            (normalized_plan_id,),
        ).fetchall()
        if not campaigns:
            return None
        before = [dict(row) for row in campaigns]
        if any(_text(row.get("review_status")) == "rejected" for row in campaigns):
            raise ValueError("plan is rejected")
        campaign_ids = [int(row["id"]) for row in campaigns]
        conn.execute(
            """
            UPDATE campaigns
            SET review_status = 'approved',
                run_status = CASE
                    WHEN run_status IN ('finished', 'completed', 'cancelled') THEN run_status
                    ELSE 'active'
                END,
                approved_by = %s,
                approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ANY(%s)
            """,
            (_text(operator) or "crm_console", campaign_ids),
        )
        conn.execute(
            """
            UPDATE campaign_members cm
            SET anchor_date = COALESCE(NULLIF(c.anchor_date, ''), TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD')),
                joined_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            FROM campaigns c
            WHERE cm.campaign_id = c.id
              AND c.id = ANY(%s)
              AND COALESCE(c.anchor_mode, 'campaign_start_date') = 'campaign_start_date'
              AND cm.status = 'pending'
            """,
            (campaign_ids,),
        )
        conn.execute(
            """
            UPDATE campaign_members cm
            SET anchor_date = TO_CHAR(COALESCE(cm.joined_at, CURRENT_TIMESTAMP) AT TIME ZONE 'UTC', 'YYYY-MM-DD'),
                updated_at = CURRENT_TIMESTAMP
            FROM campaigns c
            WHERE cm.campaign_id = c.id
              AND c.id = ANY(%s)
              AND COALESCE(c.anchor_mode, 'campaign_start_date') <> 'campaign_start_date'
              AND cm.status = 'pending'
            """,
            (campaign_ids,),
        )
        due_rows = conn.execute(
            """
            SELECT cm.id AS cm_id,
                   cm.member_id,
                   cm.unionid,
                   cm.campaign_id,
                   cm.campaign_segment_id,
                   cm.anchor_date,
                   cm.trace_id AS member_trace_id,
                   c.campaign_code,
                   c.owner_userid,
                   c.trace_id AS campaign_trace_id,
                   cs.id AS step_id,
                   cs.step_index,
                   cs.day_offset,
                   cs.send_time,
                   cs.timezone,
                   cs.content_text,
                   cs.content_payload_json,
                   cs.stop_on_reply,
                   cs.skip_if_recently_touched_days
            FROM campaign_members cm
            JOIN campaigns c ON c.id = cm.campaign_id
            JOIN LATERAL (
                SELECT *
                FROM campaign_steps cs
                WHERE cs.campaign_segment_id = cm.campaign_segment_id
                ORDER BY cs.step_index ASC, cs.id ASC
                LIMIT 1
            ) cs ON TRUE
            WHERE cm.campaign_id = ANY(%s)
              AND c.run_status = 'active'
              AND cm.status = 'pending'
            ORDER BY cm.id ASC
            """,
            (campaign_ids,),
        ).fetchall()
        groups: dict[str, dict[str, Any]] = {}
        for row in due_rows:
            due_iso = campaign_step_due_iso(
                anchor_date=_text(row.get("anchor_date")),
                day_offset=int(row.get("day_offset") or 0),
                send_time=_text(row.get("send_time")) or _DEFAULT_CAMPAIGN_SEND_TIME,
                step_timezone=_text(row.get("timezone")) or _DEFAULT_CAMPAIGN_TIMEZONE,
            )
            conn.execute(
                """
                UPDATE campaign_members
                SET next_due_at = %s::timestamptz,
                    current_step_index = -1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (due_iso, int(row["cm_id"])),
            )
            source_id = _campaign_job_source_id(
                campaign_id=int(row["campaign_id"]),
                campaign_segment_id=int(row["campaign_segment_id"]),
                step_index=int(row.get("step_index") or 0),
            )
            if source_id not in groups:
                groups[source_id] = {
                    "source_ids": (
                        source_id,
                        _legacy_campaign_job_source_id(
                            campaign_id=int(row["campaign_id"]),
                            step_index=int(row.get("step_index") or 0),
                        ),
                    ),
                    "scheduled_for": due_iso,
                    "campaign": {
                        "id": int(row["campaign_id"]),
                        "campaign_code": _text(row.get("campaign_code")),
                        "owner_userid": _text(row.get("owner_userid")),
                        "trace_id": _text(row.get("campaign_trace_id") or row.get("member_trace_id")),
                    },
                    "step": {
                        "id": int(row.get("step_id") or 0),
                        "step_index": int(row.get("step_index") or 0),
                        "day_offset": int(row.get("day_offset") or 0),
                        "send_time": _text(row.get("send_time")),
                        "content_text": _text(row.get("content_text")),
                        "timezone": _text(row.get("timezone")),
                        "content_payload_json": _json(row.get("content_payload_json"), default={}),
                        "stop_on_reply": bool(row.get("stop_on_reply")),
                        "skip_if_recently_touched_days": int(row.get("skip_if_recently_touched_days") or 0),
                    },
                    "members": [],
                }
            unionid = _text(row.get("unionid"))
            if unionid:
                groups[source_id]["members"].append(
                    {
                        "cm_id": int(row["cm_id"]),
                        "member_id": int(row.get("member_id") or 0),
                        "unionid": unionid,
                        "trace_id": _text(row.get("member_trace_id")),
                        "campaign_segment_id": int(row["campaign_segment_id"]),
                    }
                )
        broadcast_columns = _broadcast_job_columns(conn)
        extra_columns, extra_placeholders, extra_params = _campaign_private_broadcast_job_extra_fields(broadcast_columns)
        extra_columns_sql = (", " + ", ".join(extra_columns)) if extra_columns else ""
        extra_values_sql = (", " + ", ".join(extra_placeholders)) if extra_placeholders else ""
        enqueued = 0
        for source_id, group in groups.items():
            members = group["members"]
            if not members:
                continue
            existing = conn.execute(
                """
                SELECT id
                FROM broadcast_jobs
                WHERE source_type = %s
                  AND source_table = %s
                  AND source_id = ANY(%s)
                  AND status = ANY(%s)
                LIMIT 1
                """,
                (_CAMPAIGN_QUEUE_SOURCE_TYPE, _CAMPAIGN_QUEUE_SOURCE_TABLE, list(group["source_ids"]), _CAMPAIGN_OPEN_JOB_STATUSES),
            ).fetchone()
            if existing:
                continue
            campaign = group["campaign"]
            step = group["step"]
            target_unionids, normalized_members = _unionid_targets_from_external_members(conn, members)
            if not target_unionids:
                continue
            inserted = conn.execute(
                """
                INSERT INTO broadcast_jobs (
                    source_type, source_id, source_table, scheduled_for, priority, batch_key,
                    idempotency_key""" + extra_columns_sql + """, status, requires_approval,
                    target_unionids_json, target_count, target_summary,
                    content_type, content_payload, content_summary, trace_id, created_by
                ) VALUES (
                    %s, %s, %s, %s::timestamptz, 100, %s,
                    %s""" + extra_values_sql + """, 'queued', FALSE,
                    %s::jsonb, %s, %s,
                    %s, %s::jsonb, %s, %s, %s
                )
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
                DO NOTHING
                RETURNING id
                """,
                (
                    _CAMPAIGN_QUEUE_SOURCE_TYPE,
                    source_id,
                    _CAMPAIGN_QUEUE_SOURCE_TABLE,
                    group["scheduled_for"],
                    normalized_plan_id,
                    f"campaign_member_step:{source_id}",
                    *extra_params,
                    _json_dump(target_unionids),
                    len(target_unionids),
                    f"campaign={campaign.get('campaign_code')} step={step.get('step_index')}",
                    _CAMPAIGN_QUEUE_CONTENT_TYPE,
                    _json_dump(_campaign_private_broadcast_payload(campaign=campaign, step=step, members=normalized_members)),
                    _text(step.get("content_text"))[:200],
                    _text(campaign.get("trace_id")),
                    _text(operator) or "crm_console",
                ),
            ).fetchone()
            if inserted:
                enqueued += 1
        after = conn.execute(
            """
            SELECT c.*
            FROM campaigns c
            WHERE """
            + _LEGACY_GROUP_KEY_SQL
            + """
             = %s
            ORDER BY c.id ASC
            """,
            (normalized_plan_id,),
        ).fetchall()
        self._audit(
            conn,
            operator=operator,
            action_type="legacy_campaign_group_approve_and_start_from_cloud_plan",
            target_type="legacy_campaign_group",
            target_id=normalized_plan_id,
            before={"campaigns": before},
            after={"campaigns": [dict(row) for row in after], "queued_jobs": enqueued},
        )
        return self._legacy_group_plan_row(conn, normalized_plan_id)

    def _reject_legacy_group(self, conn, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None:
        normalized_plan_id = _text(plan_id)
        campaigns = conn.execute(
            """
            SELECT c.*
            FROM campaigns c
            WHERE """
            + _LEGACY_GROUP_KEY_SQL
            + """
             = %s
            FOR UPDATE
            """,
            (normalized_plan_id,),
        ).fetchall()
        if not campaigns:
            return None
        campaign_ids = [int(row["id"]) for row in campaigns]
        before = [dict(row) for row in campaigns]
        reason_text = _text(reason)[:200] or "cloud plan rejected"
        updated_campaigns = conn.execute(
            """
            UPDATE campaigns
            SET review_status = 'rejected',
                run_status = CASE
                    WHEN run_status IN ('finished', 'completed') THEN run_status
                    ELSE 'cancelled'
                END,
                paused_reason = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ANY(%s)
            RETURNING *
            """,
            (reason_text, campaign_ids),
        ).fetchall()
        cancelled_members = conn.execute(
            """
            UPDATE campaign_members
            SET status = 'cancelled',
                next_due_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE campaign_id = ANY(%s)
              AND status IN ('pending', 'running', 'queued', 'paused')
            RETURNING id
            """,
            (campaign_ids,),
        ).fetchall()
        cancelled_jobs = conn.execute(
            """
            UPDATE broadcast_jobs bj
            SET status = 'cancelled',
                cancelled_by = %s,
                cancelled_at = CURRENT_TIMESTAMP,
                cancel_reason = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE bj.source_type = %s
              AND COALESCE(bj.source_table, %s) = %s
              AND bj.status = ANY(%s)
              AND EXISTS (
                  SELECT 1
                  FROM unnest(%s::int[]) AS campaign_id
                  WHERE bj.source_id LIKE (campaign_id::text || ':%%')
              )
            RETURNING bj.id
            """,
            (
                _text(operator) or "crm_console",
                reason_text,
                _CAMPAIGN_QUEUE_SOURCE_TYPE,
                _CAMPAIGN_QUEUE_SOURCE_TABLE,
                _CAMPAIGN_QUEUE_SOURCE_TABLE,
                _CAMPAIGN_OPEN_JOB_STATUSES,
                campaign_ids,
            ),
        ).fetchall()
        self._audit(
            conn,
            operator=operator,
            action_type="legacy_campaign_group_reject_from_cloud_plan",
            target_type="legacy_campaign_group",
            target_id=normalized_plan_id,
            before={"campaigns": before},
            after={
                "campaigns": [dict(row) for row in updated_campaigns],
                "cancelled_members": len(cancelled_members),
                "cancelled_jobs": len(cancelled_jobs),
            },
        )
        return self._legacy_group_plan_row(conn, normalized_plan_id)

    def _stats_for_plan_ids(self, conn, plan_ids: list[str]) -> dict[str, dict[str, int]]:
        if not plan_ids:
            return {}
        try:
            rows = conn.execute(
                """
                SELECT plan_id,
                       COUNT(*) AS target_count,
                       COALESCE(SUM(CASE WHEN approval_status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_count,
                       COALESCE(SUM(CASE WHEN approval_status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
                       COALESCE(SUM(CASE WHEN approval_status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
                       COALESCE(SUM(CASE WHEN send_status = 'sent' THEN 1 ELSE 0 END), 0) AS sent_count,
                       COALESCE(SUM(CASE WHEN send_status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
                FROM cloud_broadcast_plan_recipients
                WHERE plan_id = ANY(%s)
                GROUP BY plan_id
                """,
                (plan_ids,),
            ).fetchall()
        except Exception as exc:
            if "cloud_broadcast_plan_recipients" in str(exc) and "permission denied" in str(exc).lower():
                conn.rollback()
                return {}
            raise
        return {str(row["plan_id"]): {key: int(row.get(key) or 0) for key in row.keys() if key != "plan_id"} for row in rows}

    def _legacy_stats_for_plan_ids(self, conn, plan_ids: list[str]) -> dict[str, dict[str, int]]:
        if not plan_ids:
            return {}
        rows = conn.execute(
            f"""
            SELECT {_LEGACY_GROUP_KEY_SQL} AS plan_id,
                   COUNT(cm.id) AS target_count,
                   COALESCE(SUM(CASE WHEN c.review_status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_count,
                   COALESCE(SUM(CASE WHEN c.review_status NOT IN ('approved', 'rejected') THEN 1 ELSE 0 END), 0) AS pending_count,
                   COALESCE(SUM(CASE WHEN c.review_status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
                   COALESCE(SUM(CASE WHEN cm.status IN ('completed', 'sent') THEN 1 ELSE 0 END), 0) AS sent_count,
                   COALESCE(SUM(CASE WHEN cm.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
            FROM campaigns c
            LEFT JOIN campaign_members cm ON cm.campaign_id = c.id
            WHERE {_LEGACY_GROUP_KEY_SQL} = ANY(%s)
            GROUP BY {_LEGACY_GROUP_KEY_SQL}
            """,
            (plan_ids,),
        ).fetchall()
        return {str(row["plan_id"]): {key: int(row.get(key) or 0) for key in row.keys() if key != "plan_id"} for row in rows}

    def list_plans(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("(COALESCE(review_status, '') = %s OR COALESCE(run_status, '') = %s OR status = %s)")
            params.extend([status, status, status])
        if keyword:
            like = f"%{keyword.lower()}%"
            clauses.append("(LOWER(plan_id) LIKE %s OR LOWER(COALESCE(display_name, intent, '')) LIKE %s OR LOWER(COALESCE(owner_userid, '')) LIKE %s)")
            params.extend([like, like, like])
        cloud_clauses = [
            *clauses,
            f"({_CLOUD_PLAN_HAS_TARGETS_SQL} OR NOT {_CLOUD_HAS_MATCHING_LEGACY_GROUP_SQL})",
        ]
        cloud_where = " WHERE " + " AND ".join(cloud_clauses)
        legacy_clauses: list[str] = []
        legacy_params: list[Any] = []
        if status:
            legacy_clauses.append("(COALESCE(c.review_status, '') = %s OR COALESCE(c.run_status, '') = %s)")
            legacy_params.extend([status, status])
        if keyword:
            like = f"%{keyword.lower()}%"
            legacy_clauses.append(
                f"(LOWER({_LEGACY_GROUP_KEY_SQL}) LIKE %s OR LOWER(COALESCE(c.metadata_json->>'group_label', c.display_name, c.intent, '')) LIKE %s OR LOWER(COALESCE(c.owner_userid, '')) LIKE %s)"
            )
            legacy_params.extend([like, like, like])
        legacy_where = " AND " + " AND ".join(legacy_clauses) if legacy_clauses else ""
        limit = _limit(limit, default=20, maximum=100)
        offset = _offset(offset)
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH merged AS (
                    SELECT id, plan_id, intent, display_name, owner_userid, candidate_count,
                           selection_json, review_status, run_status, status, updated_at,
                           'cloud_plan' AS source_type
                    FROM cloud_broadcast_plans
                    """
                + cloud_where
                + f"""
                    UNION ALL
                    SELECT MAX(c.id) AS id,
                           {_LEGACY_GROUP_KEY_SQL} AS plan_id,
                           MAX(c.intent) AS intent,
                           {_LEGACY_GROUP_LABEL_SQL} AS display_name,
                           STRING_AGG(DISTINCT NULLIF(c.owner_userid, ''), ' / ') AS owner_userid,
                           COUNT(cm.id) AS candidate_count,
                           jsonb_build_object('group_code', {_LEGACY_GROUP_KEY_SQL}, 'legacy_campaign_count', COUNT(DISTINCT c.id)) AS selection_json,
                           CASE
                               WHEN BOOL_AND(c.review_status = 'approved') THEN 'approved'
                               WHEN BOOL_OR(c.review_status = 'rejected') AND NOT BOOL_OR(c.review_status <> 'rejected') THEN 'rejected'
                               ELSE 'pending_review'
                           END AS review_status,
                           CASE
                               WHEN BOOL_OR(c.run_status = 'active') THEN 'active'
                               WHEN BOOL_OR(c.run_status = 'paused') THEN 'paused'
                               WHEN BOOL_AND(c.run_status IN ('finished', 'completed')) THEN 'finished'
                               WHEN BOOL_AND(c.run_status = 'cancelled') THEN 'cancelled'
                               ELSE 'draft'
                           END AS run_status,
                           CASE
                               WHEN BOOL_OR(c.run_status = 'active') THEN 'active'
                               WHEN BOOL_AND(c.run_status = 'cancelled') THEN 'cancelled'
                               ELSE 'draft'
                           END AS status,
                           MAX(c.updated_at) AS updated_at,
                           'legacy_campaign' AS source_type
                    FROM campaigns c
                    LEFT JOIN campaign_members cm ON cm.campaign_id = c.id
                    WHERE NOT {_LEGACY_HAS_TARGETED_CLOUD_PLAN_SQL}
                    """
                + legacy_where
                + f"""
                    GROUP BY {_LEGACY_GROUP_KEY_SQL}
                    """
                + """
                )
                SELECT *
                FROM merged
                ORDER BY updated_at DESC, id DESC
                LIMIT %s OFFSET %s
                """
                ,
                tuple([*params, *legacy_params, limit, offset]),
            ).fetchall()
            total = int(
                (
                    conn.execute(
                        """
                        WITH merged AS (
                            SELECT plan_id FROM cloud_broadcast_plans
                            """
                        + cloud_where
                + f"""
                            UNION ALL
                            SELECT {_LEGACY_GROUP_KEY_SQL} AS plan_id FROM campaigns c
                            LEFT JOIN campaign_members cm ON cm.campaign_id = c.id
                            WHERE NOT {_LEGACY_HAS_TARGETED_CLOUD_PLAN_SQL}
                            """
                        + legacy_where
                        + f"""
                            GROUP BY {_LEGACY_GROUP_KEY_SQL}
                            """
                        + """
                        )
                        SELECT COUNT(*) AS total FROM merged
                        """,
                        tuple([*params, *legacy_params]),
                    ).fetchone()
                    or {}
                ).get("total")
                or 0
            )
            cloud_ids = [str(row["plan_id"]) for row in rows if _text(row.get("source_type")) == "cloud_plan"]
            legacy_ids = [str(row["plan_id"]) for row in rows if _text(row.get("source_type")) == "legacy_campaign"]
            stats = {**self._stats_for_plan_ids(conn, cloud_ids), **self._legacy_stats_for_plan_ids(conn, legacy_ids)}
        return [_plan_view(dict(row), stats.get(str(row["plan_id"]), {})) for row in rows], total

    def _legacy_group_plan_row(self, conn, plan_id: str):
        return conn.execute(
            f"""
            SELECT MAX(c.id) AS id,
                   {_LEGACY_GROUP_KEY_SQL} AS plan_id,
                   MAX(c.intent) AS intent,
                   {_LEGACY_GROUP_LABEL_SQL} AS display_name,
                   STRING_AGG(DISTINCT NULLIF(c.owner_userid, ''), ' / ') AS owner_userid,
                   COUNT(cm.id) AS candidate_count,
                   jsonb_build_object('group_code', {_LEGACY_GROUP_KEY_SQL}, 'legacy_campaign_count', COUNT(DISTINCT c.id)) AS selection_json,
                   CASE
                       WHEN BOOL_AND(c.review_status = 'approved') THEN 'approved'
                       WHEN BOOL_OR(c.review_status = 'rejected') AND NOT BOOL_OR(c.review_status <> 'rejected') THEN 'rejected'
                       ELSE 'pending_review'
                   END AS review_status,
                   CASE
                       WHEN BOOL_OR(c.run_status = 'active') THEN 'active'
                       WHEN BOOL_OR(c.run_status = 'paused') THEN 'paused'
                       WHEN BOOL_AND(c.run_status IN ('finished', 'completed')) THEN 'finished'
                       WHEN BOOL_AND(c.run_status = 'cancelled') THEN 'cancelled'
                       ELSE 'draft'
                   END AS run_status,
                   CASE
                       WHEN BOOL_OR(c.run_status = 'active') THEN 'active'
                       WHEN BOOL_AND(c.run_status = 'cancelled') THEN 'cancelled'
                       ELSE 'draft'
                   END AS status,
                   MAX(c.updated_at) AS updated_at,
                   'legacy_campaign' AS source_type
            FROM campaigns c
            LEFT JOIN campaign_members cm ON cm.campaign_id = c.id
            WHERE {_LEGACY_GROUP_KEY_SQL} = %s
            GROUP BY {_LEGACY_GROUP_KEY_SQL}
            """,
            (_text(plan_id),),
        ).fetchone()

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, plan_id, intent, display_name, owner_userid, candidate_count, selection_json,
                       review_status, run_status, status, updated_at
                FROM cloud_broadcast_plans
                WHERE plan_id = %s
                """,
                (_text(plan_id),),
            ).fetchone()
            if row:
                if int(row.get("candidate_count") or 0) <= 0:
                    row = self._legacy_group_plan_row(conn, plan_id) or row
            else:
                row = self._legacy_group_plan_row(conn, plan_id)
                if not row:
                    return None
            if _text(row.get("source_type")) == "legacy_campaign":
                stats = self._legacy_stats_for_plan_ids(conn, [_text(plan_id)]).get(_text(plan_id), {})
            else:
                stats = self._stats_for_plan_ids(conn, [_text(plan_id)]).get(_text(plan_id), {})
        return _plan_view(dict(row), stats)

    def plan_stats(self, plan_id: str) -> dict[str, int]:
        with self._connect() as conn:
            cloud = conn.execute(
                "SELECT candidate_count FROM cloud_broadcast_plans WHERE plan_id = %s",
                (_text(plan_id),),
            ).fetchone()
            if cloud and int(cloud.get("candidate_count") or 0) > 0:
                stats = self._stats_for_plan_ids(conn, [_text(plan_id)]).get(_text(plan_id), {})
                if stats:
                    return stats
            return self._legacy_stats_for_plan_ids(conn, [_text(plan_id)]).get(_text(plan_id), {})

    def list_recipients(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        clauses = ["plan_id = %s"]
        params: list[Any] = [_text(plan_id)]
        if status:
            clauses.append("(approval_status = %s OR send_status = %s)")
            params.extend([status, status])
        where = " WHERE " + " AND ".join(clauses)
        limit = _limit(limit, default=50, maximum=200)
        offset = _offset(offset)
        with self._connect() as conn:
            cloud = conn.execute(
                "SELECT candidate_count FROM cloud_broadcast_plans WHERE plan_id = %s",
                (_text(plan_id),),
            ).fetchone()
            if not cloud or int(cloud.get("candidate_count") or 0) <= 0:
                return self._legacy_recipients(conn, _text(plan_id), status=status, limit=limit, offset=offset)
            total = int((conn.execute("SELECT COUNT(*) AS total FROM cloud_broadcast_plan_recipients" + where, tuple(params)).fetchone() or {}).get("total") or 0)
            if total:
                rows = conn.execute(
                    """
                    SELECT *, 'cloud_plan' AS source_type, TRUE AS supports_recipient_approval
                    FROM cloud_broadcast_plan_recipients
                    """
                    + where
                    + " ORDER BY id ASC LIMIT %s OFFSET %s",
                    tuple([*params, limit, offset]),
                ).fetchall()
                return [_recipient_view(dict(row)) for row in rows], total
            return self._legacy_recipients(conn, _text(plan_id), status=status, limit=limit, offset=offset)

    def _legacy_recipients(self, conn, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        status_clause = ""
        params: list[Any] = [plan_id]
        if status == "approved":
            status_clause = " AND cm.status IN ('running', 'queued', 'completed', 'sent', 'failed')"
        elif status == "sent":
            status_clause = " AND cm.status IN ('completed', 'sent')"
        elif status == "rejected":
            status_clause = " AND cm.status IN ('cancelled', 'stopped')"
        elif status == "pending":
            status_clause = " AND cm.status IN ('pending', 'paused')"
        elif status:
            status_clause = " AND cm.status = %s"
            params.append(status)
        total = int(
            (
                conn.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM campaign_members cm
                    JOIN campaigns c ON c.id = cm.campaign_id
                    WHERE """ + _LEGACY_GROUP_KEY_UPDATE_SQL + """ = %s
                    """
                    + status_clause,
                    tuple(params),
                ).fetchone()
                or {}
            ).get("total")
            or 0
        )
        rows = conn.execute(
            """
            SELECT cm.id, cm.unionid,
                   CASE
                       WHEN c.run_status = 'active' AND cm.status = 'pending' AND cm.next_due_at IS NOT NULL THEN 'queued'
                       ELSE cm.status
                   END AS status,
                   cm.updated_at,
                   c.owner_userid,
                   COALESCE(NULLIF(read_model.display_name, ''), cm.unionid) AS display_name,
                   (SELECT COUNT(*) FROM campaign_steps cs WHERE cs.campaign_segment_id = cm.campaign_segment_id) AS planned_message_count
            FROM campaign_members cm
            JOIN campaigns c ON c.id = cm.campaign_id
            LEFT JOIN customer_read_model_current read_model ON read_model.unionid = cm.unionid
            WHERE """ + _LEGACY_GROUP_KEY_SQL + """ = %s
            """
            + status_clause
            + " ORDER BY cm.id ASC LIMIT %s OFFSET %s",
            tuple([*params, limit, offset]),
        ).fetchall()
        recipients = []
        for row in rows:
            approval_status, send_status = _legacy_recipient_status(row.get("status"))
            recipients.append(
                _recipient_view(
                    {
                        "id": -int(row["id"]),
                        "unionid": row.get("unionid"),
                        "display_name": row.get("display_name"),
                        "owner_userid": row.get("owner_userid"),
                        "updated_at": row.get("updated_at"),
                        "planned_message_count": row.get("planned_message_count"),
                        "approval_status": approval_status,
                        "send_status": send_status,
                        "source_type": "legacy_campaign",
                        "supports_recipient_approval": False,
                    }
                )
            )
        return recipients, total

    def get_recipient(self, plan_id: str, recipient_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            if int(recipient_id) < 0:
                legacy_rows, _total = self._legacy_recipients(conn, _text(plan_id), limit=1, offset=0)
                row = None
                legacy_id = abs(int(recipient_id))
                for item in legacy_rows:
                    if abs(int(item["recipient_id"])) == legacy_id:
                        return item
                row = conn.execute(
                    """
                    SELECT cm.id, cm.unionid,
                           CASE
                               WHEN c.run_status = 'active' AND cm.status = 'pending' AND cm.next_due_at IS NOT NULL THEN 'queued'
                               ELSE cm.status
                           END AS status,
                           cm.updated_at,
                           c.owner_userid,
                           COALESCE(NULLIF(read_model.display_name, ''), cm.unionid) AS display_name,
                           (SELECT COUNT(*) FROM campaign_steps cs WHERE cs.campaign_segment_id = cm.campaign_segment_id) AS planned_message_count
                    FROM campaign_members cm
                    JOIN campaigns c ON c.id = cm.campaign_id
                    LEFT JOIN customer_read_model_current read_model ON read_model.unionid = cm.unionid
                    WHERE """ + _LEGACY_GROUP_KEY_SQL + """ = %s AND cm.id = %s
                    """,
                    (_text(plan_id), legacy_id),
                ).fetchone()
                if row:
                    approval_status, send_status = _legacy_recipient_status(row.get("status"))
                    return _recipient_view(
                        {
                            "id": -int(row["id"]),
                            "unionid": row.get("unionid"),
                            "display_name": row.get("display_name"),
                            "owner_userid": row.get("owner_userid"),
                            "updated_at": row.get("updated_at"),
                            "planned_message_count": row.get("planned_message_count"),
                            "approval_status": approval_status,
                            "send_status": send_status,
                            "source_type": "legacy_campaign",
                            "supports_recipient_approval": False,
                        }
                    )
            row = conn.execute(
                """
                SELECT *, 'cloud_plan' AS source_type, TRUE AS supports_recipient_approval
                FROM cloud_broadcast_plan_recipients
                WHERE plan_id = %s AND id = %s
                """,
                (_text(plan_id), int(recipient_id)),
            ).fetchone()
        return _recipient_view(dict(row)) if row else None

    def list_recipient_messages(self, recipient_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if int(recipient_id) < 0:
                rows = conn.execute(
                    """
                    SELECT cs.id, cs.step_index AS sequence_index, cs.day_offset, cs.send_time,
                           cs.content_text, cs.content_payload_json, '[]'::jsonb AS attachments_json,
                           CASE
                               WHEN cm.status IN ('completed', 'sent') OR cm.current_step_index >= cs.step_index THEN 'sent'
                               WHEN cm.status = 'failed' THEN 'failed'
                               ELSE 'pending'
                           END AS status,
                           NULL AS sent_at,
                           cm.last_error_text AS last_error,
                           'legacy_campaign' AS source_type
                    FROM campaign_members cm
                    JOIN campaign_steps cs ON cs.campaign_segment_id = cm.campaign_segment_id
                    WHERE cm.id = %s
                    ORDER BY cs.step_index ASC, cs.id ASC
                    """,
                    (abs(int(recipient_id)),),
                ).fetchall()
                return [_message_view(dict(row)) for row in rows]
            rows = conn.execute(
                """
                SELECT *, 'cloud_plan' AS source_type
                FROM cloud_broadcast_plan_recipient_messages
                WHERE recipient_id = %s
                ORDER BY sequence_index ASC, id ASC
                """,
                (int(recipient_id),),
            ).fetchall()
        return [_message_view(dict(row)) for row in rows]

    def approve_plan(self, plan_id: str, *, operator: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            before = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (_text(plan_id),)).fetchone()
            if not before:
                row = self._approve_and_start_legacy_group(conn, _text(plan_id), operator=operator)
                if not row:
                    return None
                conn.commit()
                return _plan_view(dict(row), self.plan_stats(plan_id))
            if _text(before.get("review_status") or before.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plans
                SET review_status = 'approved', run_status = COALESCE(NULLIF(run_status, ''), status, 'draft'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE plan_id = %s
                RETURNING *
                """,
                (_text(plan_id),),
            ).fetchone()
            self._audit(conn, operator=operator, action_type="cloud_plan_approve", target_type="cloud_broadcast_plan", target_id=_text(plan_id), before=dict(before), after=dict(row or {}))
            conn.commit()
        return self.get_plan(plan_id)

    def reject_plan(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None:
        with self._connect() as conn:
            before = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (_text(plan_id),)).fetchone()
            if not before:
                row = self._reject_legacy_group(conn, _text(plan_id), operator=operator, reason=reason)
                if not row:
                    return None
                conn.commit()
                return _plan_view(dict(row), self.plan_stats(plan_id))
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plans
                SET review_status = 'rejected', status = CASE WHEN status = 'committed' THEN status ELSE 'rejected' END,
                    error_message = %s, updated_at = CURRENT_TIMESTAMP
                WHERE plan_id = %s
                RETURNING *
                """,
                (_text(reason)[:200], _text(plan_id)),
            ).fetchone()
            self._audit(conn, operator=operator, action_type="cloud_plan_reject", target_type="cloud_broadcast_plan", target_id=_text(plan_id), before=dict(before), after=dict(row or {}))
            conn.commit()
        return self.get_plan(plan_id)

    def create_or_reuse_recipient_broadcast_jobs(
        self,
        plan_id: str,
        *,
        operator: str,
        source_event_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        normalized_plan_id = _text(plan_id)
        if not normalized_plan_id:
            return {"status": "skipped", "reason": "missing_plan_id"}
        job_ids: list[int] = []
        created_count = 0
        reused_count = 0
        target_count = 0
        planner_idempotency_key = _plan_broadcast_idempotency_key(
            normalized_plan_id,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key,
        )
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (normalized_plan_id,)).fetchone()
            if not plan:
                return {"status": "skipped", "reason": "missing_plan_id"}
            plan_dict = dict(plan)
            source_type = _text(plan_dict.get("source_type")) or "cloud_plan"
            if source_type and source_type != "cloud_plan":
                return {"status": "skipped", "reason": "unsupported_plan_type", "plan_type": source_type}
            review_status = _text(plan_dict.get("review_status") or plan_dict.get("status"))
            if review_status not in {"approved", "reviewing"}:
                return {"status": "skipped", "reason": "unsupported_plan_type", "review_status": review_status}
            recipients = conn.execute(
                """
                SELECT id, unionid, display_name, owner_userid
                FROM cloud_broadcast_plan_recipients
                WHERE plan_id = %s
                  AND COALESCE(approval_status, 'pending') <> 'rejected'
                  AND COALESCE(send_status, 'pending') NOT IN ('cancelled', 'sent')
                  AND COALESCE(unionid, '') <> ''
                  AND EXISTS (
                    SELECT 1
                    FROM cloud_broadcast_plan_recipient_messages m
                    WHERE m.plan_id = cloud_broadcast_plan_recipients.plan_id
                      AND m.recipient_id = cloud_broadcast_plan_recipients.id
                      AND COALESCE(m.status, 'pending') <> 'cancelled'
                  )
                ORDER BY id ASC
                """,
                (normalized_plan_id,),
            ).fetchall()
            if not recipients:
                return {"status": "skipped", "reason": "missing_audience"}
            target_count = len(recipients)
            for recipient_row in recipients:
                recipient = dict(recipient_row)
                recipient_id = int(recipient["id"])
                recipient_idempotency_key = f"cloud_plan_recipient:{normalized_plan_id}:{recipient_id}"
                existing = conn.execute(
                    "SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1",
                    (recipient_idempotency_key,),
                ).fetchone()
                job_id = int(existing["id"]) if existing else 0
                if job_id:
                    reused_count += 1
                else:
                    metadata = {
                        "planner_consumer": "broadcast_task_planner_consumer",
                        "source_event_id": _text(source_event_id),
                        "plan_idempotency_key": planner_idempotency_key,
                        "duplicate_policy": "reuse_recipient_idempotency_key",
                    }
                    inserted = conn.execute(
                        """
                        INSERT INTO broadcast_jobs (
                            source_type, source_id, source_table, scheduled_for, priority, batch_key,
                            business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
                            status, requires_approval, target_unionids_json, target_count, target_summary,
                            content_type, content_payload, content_summary, trace_id, created_by
                        ) VALUES (
                            'cloud_plan', %s, 'cloud_broadcast_plan_recipients', CURRENT_TIMESTAMP, 100, %s,
                            'ai_assistant', %s, 'wecom_private', 'unionid', '{}'::jsonb, %s::jsonb,
                            'queued', FALSE, %s::jsonb, 1, %s,
                            'cloud_plan', %s::jsonb, %s, %s, %s
                        )
                        ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
                        DO NOTHING
                        RETURNING id
                        """,
                        (
                            f"{normalized_plan_id}:{recipient_id}",
                            f"cloud_plan_recipient:{normalized_plan_id}",
                            recipient_idempotency_key,
                            _json_dump(metadata),
                            _json_dump([_text(recipient.get("unionid"))]),
                            _text(recipient.get("display_name")) or _text(recipient.get("unionid")),
                            _json_dump(
                                {
                                    "plan_id": normalized_plan_id,
                                    "recipient_id": recipient_id,
                                    "unionid": _text(recipient.get("unionid")),
                                    "message_mode": "recipient_messages",
                                }
                            ),
                            f"{_text(plan_dict.get('display_name')) or _text(plan_dict.get('intent')) or normalized_plan_id} · {_text(recipient.get('display_name')) or _text(recipient.get('unionid'))}",
                            _text(plan_dict.get("trace_id")) or normalized_plan_id,
                            _text(operator) or "internal_event_worker",
                        ),
                    ).fetchone()
                    if inserted:
                        job_id = int(inserted["id"])
                        created_count += 1
                    else:
                        existing = conn.execute(
                            "SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1",
                            (recipient_idempotency_key,),
                        ).fetchone()
                        job_id = int(existing["id"]) if existing else 0
                        if job_id:
                            reused_count += 1
                if job_id:
                    job_ids.append(job_id)
                    conn.execute(
                        """
                        UPDATE cloud_broadcast_plan_recipients
                        SET approval_status = 'approved',
                            send_status = CASE WHEN send_status = 'pending' THEN 'queued' ELSE send_status END,
                            approved_by = CASE WHEN COALESCE(approved_by, '') = '' THEN %s ELSE approved_by END,
                            approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
                            broadcast_job_id = COALESCE(broadcast_job_id, %s),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (_text(operator) or "internal_event_worker", job_id, recipient_id),
                    )
                    conn.execute(
                        """
                        UPDATE cloud_broadcast_plan_recipient_messages
                        SET status = CASE WHEN status = 'pending' THEN 'queued' ELSE status END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE plan_id = %s
                          AND recipient_id = %s
                        """,
                        (normalized_plan_id, recipient_id),
                    )
            if not job_ids:
                return {"status": "skipped", "reason": "missing_send_content"}
            self._audit(
                conn,
                operator=operator,
                action_type="ops_plan_recipient_broadcast_jobs_plan",
                target_type="cloud_broadcast_plan",
                target_id=normalized_plan_id,
                before={},
                after={
                    "plan_id": normalized_plan_id,
                    "broadcast_job_id": job_ids[0],
                    "broadcast_job_count": len(set(job_ids)),
                    "created_count": created_count,
                    "reused_count": reused_count,
                    "target_count": target_count,
                    "idempotency_key": planner_idempotency_key,
                },
            )
            conn.commit()
        job_status = "created" if created_count else "reused"
        first_job_id = job_ids[0] if job_ids else 0
        return {
            "status": job_status,
            "broadcast_job_id": first_job_id,
            "broadcast_job_count": len(set(job_ids)),
            "created_count": created_count,
            "reused_count": reused_count,
            "idempotency_key": planner_idempotency_key,
            "target_count": target_count,
            "source_id": normalized_plan_id,
            "trace_id": normalized_plan_id,
            "downstream_status": "broadcast_job_queued",
            "push_center_job_id": f"broadcast_job:{first_job_id}" if first_job_id else "",
        }

    def create_or_reuse_plan_broadcast_job(
        self,
        plan_id: str,
        *,
        operator: str,
        source_event_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        return self.create_or_reuse_recipient_broadcast_jobs(
            plan_id,
            operator=operator,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key,
        )

    def create_or_reuse_agent_send_plan(
        self,
        *,
        external_event_id: str,
        package_key: str,
        external_userid: str,
        owner_userid: str,
        content_package: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        normalized_event_id = _text(external_event_id)
        normalized_external_userid = _text(external_userid)
        normalized_owner = _text(owner_userid)
        if not normalized_event_id:
            return {"status": "skipped", "reason": "missing_external_event_id"}
        if not normalized_external_userid:
            return {"status": "skipped", "reason": "missing_external_userid"}
        if not normalized_owner:
            return {"status": "skipped", "reason": "missing_owner_userid"}
        plan_id = _agent_plan_id(normalized_event_id)
        content_payload = _content_payload_for_package(content_package)
        with self._connect() as conn:
            normalized_unionid = _resolve_unionid_by_external_userid(conn, normalized_external_userid)
            if not normalized_unionid:
                return {"status": "skipped", "reason": "identity_pending_unionid"}
            existing_plan = conn.execute(
                "SELECT plan_id FROM cloud_broadcast_plans WHERE plan_id = %s",
                (plan_id,),
            ).fetchone()
            if not existing_plan:
                conn.execute(
                    """
                    INSERT INTO cloud_broadcast_plans (
                        plan_id, trace_id, session_id, operator, intent, display_name, owner_userid,
                        selection_json, content_strategy, max_recipients, candidate_count,
                        explanation_json, status, review_status, run_status, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, 'agent_generated_single', 1, 1,
                        %s::jsonb, 'draft', 'approved', 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (plan_id) DO NOTHING
                    """,
                    (
                        plan_id,
                        normalized_event_id,
                        normalized_event_id,
                        _text(operator) or "automation_agent",
                        f"Agent generated send plan {normalized_external_userid}",
                        f"Agent 生成待发送计划 · {normalized_external_userid}",
                        normalized_owner,
                        _json_dump(
                            {
                                "source": "automation_agent",
                                "package_key": _text(package_key),
                                "external_event_id": normalized_event_id,
                                "unionid": normalized_unionid,
                            }
                        ),
                        _json_dump({"source": "automation_agent", "external_event_id": normalized_event_id}),
                    ),
                )
            recipient = conn.execute(
                """
                INSERT INTO cloud_broadcast_plan_recipients (
                    plan_id, unionid, owner_userid, display_name, planned_message_count,
                    approval_status, send_status, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, 1, 'approved', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (plan_id, unionid) WHERE unionid <> '' DO UPDATE SET
                    owner_userid = EXCLUDED.owner_userid,
                    planned_message_count = 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                (plan_id, normalized_unionid, normalized_owner, normalized_unionid),
            ).fetchone()
            recipient_id = int((recipient or {}).get("id") or 0)
            existing_message = conn.execute(
                """
                SELECT id
                FROM cloud_broadcast_plan_recipient_messages
                WHERE plan_id = %s AND recipient_id = %s AND sequence_index = 1
                ORDER BY id ASC
                LIMIT 1
                """,
                (plan_id, recipient_id),
            ).fetchone()
            if existing_message:
                message_id = int(existing_message["id"])
                conn.execute(
                    """
                    UPDATE cloud_broadcast_plan_recipient_messages
                    SET content_text = %s,
                        content_payload_json = %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (_text(content_package.get("content_text")), _json_dump(content_payload), message_id),
                )
            else:
                inserted_message = conn.execute(
                    """
                    INSERT INTO cloud_broadcast_plan_recipient_messages (
                        plan_id, recipient_id, unionid, sequence_index, day_offset, send_time,
                        content_text, content_payload_json, attachments_json, status, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, 1, 0, '', %s, %s::jsonb, '[]'::jsonb, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """,
                    (
                        plan_id,
                        recipient_id,
                        normalized_unionid,
                        _text(content_package.get("content_text")),
                        _json_dump(content_payload),
                    ),
                ).fetchone()
                message_id = int((inserted_message or {}).get("id") or 0)
            self._audit(
                conn,
                operator=_text(operator) or "automation_agent",
                action_type="automation_agent_enqueue_send_plan",
                target_type="cloud_broadcast_plan",
                target_id=plan_id,
                before={},
                after={
                    "plan_id": plan_id,
                    "recipient_id": recipient_id,
                    "message_id": message_id,
                    "external_event_id": normalized_event_id,
                    "duplicate_handling": "reused" if existing_plan else "created",
                },
            )
            conn.commit()
        return {
            "status": "reused" if existing_plan else "created",
            "plan_id": plan_id,
            "recipient_id": recipient_id,
            "message_id": message_id,
            "downstream_status": "send_plan_pending",
            "push_center_job_id": f"cloud_plan:{plan_id}",
        }

    def approve_recipient(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]:
        normalized_plan_id = _text(plan_id)
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (normalized_plan_id,)).fetchone()
            if not plan:
                raise LookupError("plan not found")
            if _text(plan.get("review_status") or plan.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            if _text(plan.get("review_status")) not in {"approved", "reviewing"}:
                raise ValueError("plan is not approved for recipient review")
            recipient = conn.execute(
                "SELECT * FROM cloud_broadcast_plan_recipients WHERE plan_id = %s AND id = %s FOR UPDATE",
                (normalized_plan_id, int(recipient_id)),
            ).fetchone()
            if not recipient:
                raise LookupError("recipient not found")
            before = dict(recipient)
            if _text(recipient.get("approval_status")) == "rejected":
                raise ValueError("recipient is rejected")
            if _text(recipient.get("send_status")) == "sent":
                return {"status": "already_sent", "recipient": _recipient_view(dict(recipient)), "job_id": recipient.get("broadcast_job_id")}
            idempotency_key = f"cloud_plan_recipient:{normalized_plan_id}:{int(recipient_id)}"
            existing = conn.execute("SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1", (idempotency_key,)).fetchone()
            job_id = int(existing["id"]) if existing else 0
            if not job_id:
                inserted = conn.execute(
                    """
                    INSERT INTO broadcast_jobs (
                        source_type, source_id, source_table, scheduled_for, priority, batch_key,
                        business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
                        status, requires_approval, target_unionids_json, target_count, target_summary,
                        content_type, content_payload, content_summary, trace_id, created_by
                    ) VALUES (
                        'cloud_plan', %s, 'cloud_broadcast_plan_recipients', CURRENT_TIMESTAMP, 100, %s,
                        'ai_assistant', %s, 'wecom_private', 'unionid', '{}'::jsonb, '{}'::jsonb,
                        'queued', FALSE, %s::jsonb, 1, %s,
                        'cloud_plan', %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
                    DO NOTHING
                    RETURNING id
                    """,
                    (
                        f"{normalized_plan_id}:{int(recipient_id)}",
                        f"cloud_plan_recipient:{normalized_plan_id}",
                        idempotency_key,
                        _json_dump([_text(recipient.get("unionid"))]),
                        _text(recipient.get("display_name")) or _text(recipient.get("unionid")),
                        _json_dump(
                            {
                                "plan_id": normalized_plan_id,
                                "recipient_id": int(recipient_id),
                                "unionid": _text(recipient.get("unionid")),
                                "message_mode": "recipient_messages",
                            }
                        ),
                        f"{_text(plan.get('display_name')) or _text(plan.get('intent')) or normalized_plan_id} · {_text(recipient.get('display_name')) or _text(recipient.get('unionid'))}",
                        _text(plan.get("trace_id")),
                        _text(operator) or "crm_console",
                    ),
                ).fetchone()
                if inserted:
                    job_id = int(inserted["id"])
                else:
                    existing = conn.execute("SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1", (idempotency_key,)).fetchone()
                    job_id = int(existing["id"]) if existing else 0
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipients
                SET approval_status = 'approved', send_status = CASE WHEN send_status = 'pending' THEN 'queued' ELSE send_status END,
                    approved_by = %s, approved_at = CURRENT_TIMESTAMP, broadcast_job_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (_text(operator) or "crm_console", job_id or None, int(recipient_id)),
            ).fetchone()
            conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipient_messages
                SET status = CASE WHEN status = 'pending' THEN 'queued' ELSE status END, updated_at = CURRENT_TIMESTAMP
                WHERE recipient_id = %s
                """,
                (int(recipient_id),),
            )
            self._audit(conn, operator=operator, action_type="cloud_plan_recipient_approve", target_type="cloud_broadcast_plan_recipient", target_id=f"{normalized_plan_id}:{int(recipient_id)}", before=before, after=dict(row or {}))
            conn.commit()
        return {"status": "already_approved" if existing else "approved", "recipient": _recipient_view(dict(row or {})), "job_id": job_id}

    def reject_recipient(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]:
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s", (_text(plan_id),)).fetchone()
            if not plan:
                raise LookupError("plan not found")
            if _text(plan.get("review_status") or plan.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            recipient = conn.execute(
                "SELECT * FROM cloud_broadcast_plan_recipients WHERE plan_id = %s AND id = %s FOR UPDATE",
                (_text(plan_id), int(recipient_id)),
            ).fetchone()
            if not recipient:
                raise LookupError("recipient not found")
            before = dict(recipient)
            if _text(recipient.get("send_status")) == "sent":
                raise ValueError("sent recipient cannot be rejected")
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipients
                SET approval_status = 'rejected', send_status = CASE WHEN send_status IN ('pending', 'queued') THEN 'cancelled' ELSE send_status END,
                    rejected_by = %s, rejected_at = CURRENT_TIMESTAMP, reject_reason = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (_text(operator) or "crm_console", _text(reason)[:500], int(recipient_id)),
            ).fetchone()
            self._audit(conn, operator=operator, action_type="cloud_plan_recipient_reject", target_type="cloud_broadcast_plan_recipient", target_id=f"{_text(plan_id)}:{int(recipient_id)}", before=before, after=dict(row or {}))
            conn.commit()
        return {"status": "rejected", "recipient": _recipient_view(dict(row or {}))}

    def update_recipient_message(
        self,
        plan_id: str,
        recipient_id: int,
        message_id: int,
        *,
        content_package: dict[str, Any],
        day_offset: Any = None,
        send_time: Any = None,
        operator: str,
    ) -> dict[str, Any]:
        normalized_plan_id = _text(plan_id)
        normalized_recipient_id = int(recipient_id)
        normalized_message_id = int(message_id)
        if normalized_recipient_id < 0:
            return self._update_legacy_recipient_message(
                normalized_plan_id,
                normalized_recipient_id,
                normalized_message_id,
                content_package=content_package,
                day_offset=day_offset,
                send_time=send_time,
                operator=operator,
            )
        content_payload = _content_payload_for_package(content_package)
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (normalized_plan_id,)).fetchone()
            if not plan:
                raise LookupError("plan not found")
            if _text(plan.get("review_status") or plan.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            recipient = conn.execute(
                "SELECT * FROM cloud_broadcast_plan_recipients WHERE plan_id = %s AND id = %s FOR UPDATE",
                (normalized_plan_id, normalized_recipient_id),
            ).fetchone()
            if not recipient:
                raise LookupError("recipient not found")
            if _text(recipient.get("approval_status")) != "pending" or _text(recipient.get("send_status")) != "pending":
                raise ValueError("recipient is not editable")
            message = conn.execute(
                """
                SELECT *
                FROM cloud_broadcast_plan_recipient_messages
                WHERE recipient_id = %s AND id = %s
                FOR UPDATE
                """,
                (normalized_recipient_id, normalized_message_id),
            ).fetchone()
            if not message:
                raise LookupError("message not found")
            if _text(message.get("status")) != "pending":
                raise ValueError("message is not editable")
            try:
                normalized_day_offset = max(0, int(day_offset if day_offset is not None else message.get("day_offset") or 0))
            except (TypeError, ValueError):
                normalized_day_offset = int(message.get("day_offset") or 0)
            normalized_send_time = (_text(send_time) or _text(message.get("send_time")))[:16]
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipient_messages
                SET content_text = %s,
                    content_payload_json = %s::jsonb,
                    attachments_json = '[]'::jsonb,
                    day_offset = %s,
                    send_time = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (
                    _text(content_package.get("content_text")),
                    _json_dump(content_payload),
                    normalized_day_offset,
                    normalized_send_time,
                    normalized_message_id,
                ),
            ).fetchone()
            recipient_row = conn.execute(
                "SELECT *, 'cloud_plan' AS source_type, TRUE AS supports_recipient_approval FROM cloud_broadcast_plan_recipients WHERE id = %s",
                (normalized_recipient_id,),
            ).fetchone()
            self._audit(
                conn,
                operator=operator,
                action_type="cloud_plan_recipient_message_update",
                target_type="cloud_broadcast_plan_recipient_message",
                target_id=f"{normalized_plan_id}:{normalized_recipient_id}:{normalized_message_id}",
                before=dict(message),
                after=dict(row or {}),
            )
            conn.commit()
        return {
            "status": "updated",
            "recipient": _recipient_view(dict(recipient_row or {})),
            "message": _message_view({**dict(row or {}), "source_type": "cloud_plan"}),
        }

    def _update_legacy_recipient_message(
        self,
        plan_id: str,
        recipient_id: int,
        message_id: int,
        *,
        content_package: dict[str, Any],
        day_offset: Any = None,
        send_time: Any = None,
        operator: str,
    ) -> dict[str, Any]:
        legacy_member_id = abs(int(recipient_id))
        content_payload = _content_payload_for_package(content_package)
        with self._connect() as conn:
            member = conn.execute(
                """
                SELECT cm.*, c.owner_userid, c.review_status AS campaign_review_status,
                       c.run_status AS campaign_run_status, c.status AS campaign_status
                FROM campaign_members cm
                JOIN campaigns c ON c.id = cm.campaign_id
                WHERE """
                + _LEGACY_GROUP_KEY_SQL
                + """
                  = %s
                  AND cm.id = %s
                FOR UPDATE OF cm, c
                """,
                (plan_id, legacy_member_id),
            ).fetchone()
            if not member:
                raise LookupError("recipient not found")
            if _text(member.get("campaign_review_status")) == "rejected":
                raise ValueError("plan is rejected")
            approval_status, send_status = _legacy_recipient_status(_text(member.get("status")))
            if approval_status != "pending" or send_status != "pending":
                raise ValueError("recipient is not editable")
            step = conn.execute(
                """
                SELECT *, 'legacy_campaign' AS source_type
                FROM campaign_steps
                WHERE campaign_segment_id = %s AND id = %s
                FOR UPDATE
                """,
                (int(member.get("campaign_segment_id") or 0), int(message_id)),
            ).fetchone()
            if not step:
                raise LookupError("message not found")
            if int(member.get("current_step_index") or -1) >= int(step.get("step_index") or 0):
                raise ValueError("message is not editable")
            try:
                normalized_day_offset = max(0, int(day_offset if day_offset is not None else step.get("day_offset") or 0))
            except (TypeError, ValueError):
                normalized_day_offset = int(step.get("day_offset") or 0)
            normalized_send_time = (_text(send_time) or _text(step.get("send_time")))[:16]
            row = conn.execute(
                """
                UPDATE campaign_steps
                SET content_text = %s,
                    content_payload_json = %s::jsonb,
                    day_offset = %s,
                    send_time = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *, 'legacy_campaign' AS source_type
                """,
                (
                    _text(content_package.get("content_text")),
                    _json_dump(content_payload),
                    normalized_day_offset,
                    normalized_send_time,
                    int(message_id),
                ),
            ).fetchone()
            self._audit(
                conn,
                operator=operator,
                action_type="legacy_campaign_step_update_from_cloud_plan",
                target_type="campaign_step",
                target_id=f"{plan_id}:{legacy_member_id}:{int(message_id)}",
                before=dict(step),
                after=dict(row or {}),
            )
            conn.commit()
        recipient = self.get_recipient(plan_id, recipient_id)
        return {
            "status": "updated",
            "recipient": recipient or {},
            "message": _message_view(dict(row or {})),
        }


class InMemoryCloudPlanRepository:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        now = _now()
        self.plans = [
            {
                "id": 1,
                "plan_id": "plan_probe",
                "display_name": "1.6.3 触达赵言方",
                "intent": "1.6.3 触达赵言方",
                "owner_userid": "HuangYouCan",
                "candidate_count": 2,
                "review_status": "pending_review",
                "run_status": "draft",
                "status": "draft",
                "selection_json": {"owner_userid": "HuangYouCan"},
                "updated_at": now,
            }
        ]
        self.recipients = [
            {"id": 1, "plan_id": "plan_probe", "unionid": "union_plan_a", "external_userid": "wm_a", "owner_userid": "HuangYouCan", "display_name": "赵言方", "planned_message_count": 1, "approval_status": "pending", "send_status": "pending", "updated_at": now},
            {"id": 2, "plan_id": "plan_probe", "unionid": "union_plan_b", "external_userid": "wm_b", "owner_userid": "HuangYouCan", "display_name": "黄永灿", "planned_message_count": 1, "approval_status": "pending", "send_status": "pending", "updated_at": now},
        ]
        self.messages = [
            {"id": 1, "plan_id": "plan_probe", "recipient_id": 1, "unionid": "union_plan_a", "external_userid": "wm_a", "sequence_index": 1, "day_offset": 0, "send_time": "10:00", "content_text": "你好", "content_payload_json": {}, "attachments_json": [], "status": "pending"},
            {"id": 2, "plan_id": "plan_probe", "recipient_id": 2, "unionid": "union_plan_b", "external_userid": "wm_b", "sequence_index": 1, "day_offset": 0, "send_time": "10:00", "content_text": "你好", "content_payload_json": {}, "attachments_json": [], "status": "pending"},
        ]
        self.legacy_plans = [
            {
                "id": 10,
                "plan_id": "standard_subscription_20260530_1000_zhaoyanfang_v1",
                "display_name": "Standard 订阅 v1.6.3 触达 · ZhaoYanFang · 2026-05-30 10:00",
                "intent": "Standard 订阅 v1.6.3 触达",
                "owner_userid": "ZhaoYanFang",
                "candidate_count": 3,
                "review_status": "approved",
                "run_status": "active",
                "status": "draft",
                "selection_json": {"group_code": "standard_subscription_20260530_1000_zhaoyanfang_v1"},
                "updated_at": now,
                "source_type": "legacy_campaign",
            }
        ]
        self.legacy_recipients = [
            {"id": -11, "plan_id": "standard_subscription_20260530_1000_zhaoyanfang_v1", "external_userid": "wm_legacy_a", "owner_userid": "ZhaoYanFang", "display_name": "老客户 A", "planned_message_count": 2, "approval_status": "approved", "send_status": "queued", "updated_at": now, "source_type": "legacy_campaign", "supports_recipient_approval": False},
            {"id": -12, "plan_id": "standard_subscription_20260530_1000_zhaoyanfang_v1", "external_userid": "wm_legacy_b", "owner_userid": "ZhaoYanFang", "display_name": "老客户 B", "planned_message_count": 2, "approval_status": "approved", "send_status": "queued", "updated_at": now, "source_type": "legacy_campaign", "supports_recipient_approval": False},
            {"id": -13, "plan_id": "standard_subscription_20260530_1000_zhaoyanfang_v1", "external_userid": "wm_legacy_c", "owner_userid": "ZhaoYanFang", "display_name": "老客户 C", "planned_message_count": 2, "approval_status": "approved", "send_status": "sent", "updated_at": now, "source_type": "legacy_campaign", "supports_recipient_approval": False},
        ]
        self.legacy_messages = [
            {"id": -101, "recipient_id": -11, "sequence_index": 1, "day_offset": 0, "send_time": "10:00", "content_text": "老话术 1", "content_payload_json": {}, "attachments_json": [], "status": "pending", "source_type": "legacy_campaign"},
            {"id": -102, "recipient_id": -11, "sequence_index": 2, "day_offset": 1, "send_time": "10:00", "content_text": "老话术 2", "content_payload_json": {}, "attachments_json": [], "status": "pending", "source_type": "legacy_campaign"},
        ]
        self.broadcast_jobs: list[dict[str, Any]] = []
        self.audits: list[dict[str, Any]] = []

    def _resolve_fixture_unionid_by_external_userid(self, external_userid: str) -> str:
        normalized_external_userid = _text(external_userid)
        if not normalized_external_userid:
            return ""
        for recipient in self.recipients:
            if _text(recipient.get("external_userid")) == normalized_external_userid:
                return _text(recipient.get("unionid"))
        suffix = normalized_external_userid
        for prefix in ("wm_", "external_"):
            if suffix.startswith(prefix):
                suffix = suffix[len(prefix) :]
                break
        return f"union_{suffix}" if suffix else ""

    def _stats(self, plan_id: str) -> dict[str, int]:
        rows = [item for item in [*self.recipients, *self.legacy_recipients] if item["plan_id"] == plan_id]
        return {
            "target_count": len(rows),
            "approved_count": sum(1 for item in rows if item.get("approval_status") == "approved"),
            "pending_count": sum(1 for item in rows if item.get("approval_status") == "pending"),
            "rejected_count": sum(1 for item in rows if item.get("approval_status") == "rejected"),
            "sent_count": sum(1 for item in rows if item.get("send_status") == "sent"),
            "failed_count": sum(1 for item in rows if item.get("send_status") == "failed"),
        }

    def list_plans(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        legacy_plan_ids = {item["plan_id"] for item in self.legacy_plans}
        materialized_cloud_plan_ids = {item["plan_id"] for item in self.recipients}
        cloud_rows = [
            item
            for item in self.plans
            if item["plan_id"] in materialized_cloud_plan_ids or item["plan_id"] not in legacy_plan_ids
        ]
        legacy_rows = [item for item in self.legacy_plans if item["plan_id"] not in materialized_cloud_plan_ids]
        rows = [item for item in [*cloud_rows, *legacy_rows] if (not status or item.get("review_status") == status or item.get("status") == status or item.get("run_status") == status)]
        if keyword:
            rows = [item for item in rows if keyword.lower() in (item.get("display_name", "") + item.get("plan_id", "")).lower()]
        total = len(rows)
        rows = rows[_offset(offset) : _offset(offset) + _limit(limit, default=20, maximum=100)]
        return [_plan_view(copy.deepcopy(item), self._stats(item["plan_id"])) for item in rows], total

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        materialized_cloud_plan_ids = {item["plan_id"] for item in self.recipients}
        if plan_id not in materialized_cloud_plan_ids:
            for item in self.legacy_plans:
                if item["plan_id"] == plan_id:
                    return _plan_view(copy.deepcopy(item), self._stats(plan_id))
        for item in self.plans:
            if item["plan_id"] == plan_id:
                return _plan_view(copy.deepcopy(item), self._stats(plan_id))
        for item in self.legacy_plans:
            if item["plan_id"] == plan_id:
                return _plan_view(copy.deepcopy(item), self._stats(plan_id))
        return None

    def plan_stats(self, plan_id: str) -> dict[str, int]:
        return self._stats(plan_id)

    def list_recipients(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = [item for item in [*self.recipients, *self.legacy_recipients] if item["plan_id"] == plan_id and (not status or item.get("approval_status") == status or item.get("send_status") == status)]
        total = len(rows)
        rows = rows[_offset(offset) : _offset(offset) + _limit(limit, default=50, maximum=200)]
        return [_recipient_view(copy.deepcopy(item)) for item in rows], total

    def get_recipient(self, plan_id: str, recipient_id: int) -> dict[str, Any] | None:
        for item in [*self.recipients, *self.legacy_recipients]:
            if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id):
                return _recipient_view(copy.deepcopy(item))
        return None

    def list_recipient_messages(self, recipient_id: int) -> list[dict[str, Any]]:
        return [_message_view(copy.deepcopy(item)) for item in [*self.messages, *self.legacy_messages] if int(item["recipient_id"]) == int(recipient_id)]

    def approve_plan(self, plan_id: str, *, operator: str) -> dict[str, Any] | None:
        for item in self.plans:
            if item["plan_id"] == plan_id:
                if item.get("review_status") == "rejected":
                    raise ValueError("plan is rejected")
                item["review_status"] = "approved"
                item["updated_at"] = _now()
                self.audits.append({"action_type": "cloud_plan_approve", "target_id": plan_id, "operator": operator})
                return self.get_plan(plan_id)
        for item in self.legacy_plans:
            if item["plan_id"] == plan_id:
                if item.get("review_status") == "rejected":
                    raise ValueError("plan is rejected")
                item["review_status"] = "approved"
                item["run_status"] = "active"
                item["status"] = "active"
                item["updated_at"] = _now()
                queued = 0
                for recipient in self.legacy_recipients:
                    if recipient["plan_id"] == plan_id and recipient.get("send_status") == "pending":
                        recipient["approval_status"] = "approved"
                        recipient["send_status"] = "queued"
                        recipient["updated_at"] = _now()
                        queued += 1
                if queued:
                    self.broadcast_jobs.append(
                        {
                            "id": len(self.broadcast_jobs) + 1,
                            "source_type": "campaign",
                            "source_table": "campaign_members",
                            "source_id": f"{plan_id}:legacy",
                            "status": "queued",
                            "scheduled_for": _now(),
                            "target_count": queued,
                        }
                    )
                self.audits.append({"action_type": "legacy_campaign_group_approve_and_start_from_cloud_plan", "target_id": plan_id, "operator": operator})
                return self.get_plan(plan_id)
        return None

    def reject_plan(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None:
        for item in self.plans:
            if item["plan_id"] == plan_id:
                item["review_status"] = "rejected"
                item["status"] = "rejected"
                item["updated_at"] = _now()
                self.audits.append({"action_type": "cloud_plan_reject", "target_id": plan_id, "operator": operator, "reason": reason})
                return self.get_plan(plan_id)
        for item in self.legacy_plans:
            if item["plan_id"] == plan_id:
                item["review_status"] = "rejected"
                item["run_status"] = "cancelled"
                item["status"] = "cancelled"
                item["updated_at"] = _now()
                cancelled_members = 0
                for recipient in self.legacy_recipients:
                    if recipient["plan_id"] == plan_id and recipient.get("send_status") != "sent":
                        recipient["approval_status"] = "rejected"
                        recipient["send_status"] = "cancelled"
                        recipient["updated_at"] = _now()
                        cancelled_members += 1
                cancelled_jobs = 0
                for job in self.broadcast_jobs:
                    if job.get("source_type") == "campaign" and job.get("source_id") == f"{plan_id}:legacy" and job.get("status") in _CAMPAIGN_OPEN_JOB_STATUSES:
                        job["status"] = "cancelled"
                        job["cancelled_by"] = operator
                        job["cancel_reason"] = reason or "cloud plan rejected"
                        job["cancelled_at"] = _now()
                        cancelled_jobs += 1
                self.audits.append(
                    {
                        "action_type": "legacy_campaign_group_reject_from_cloud_plan",
                        "target_id": plan_id,
                        "operator": operator,
                        "reason": reason,
                        "cancelled_members": cancelled_members,
                        "cancelled_jobs": cancelled_jobs,
                    }
                )
                return self.get_plan(plan_id)
        return None

    def create_or_reuse_recipient_broadcast_jobs(
        self,
        plan_id: str,
        *,
        operator: str,
        source_event_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        normalized_plan_id = _text(plan_id)
        if not normalized_plan_id:
            return {"status": "skipped", "reason": "missing_plan_id"}
        plan = self.get_plan(normalized_plan_id)
        if not plan:
            return {"status": "skipped", "reason": "missing_plan_id"}
        if _text(plan.get("source_type")) and _text(plan.get("source_type")) != "cloud_plan":
            return {"status": "skipped", "reason": "unsupported_plan_type", "plan_type": _text(plan.get("source_type"))}
        if _text(plan.get("review_status")) not in {"approved", "reviewing"}:
            return {"status": "skipped", "reason": "unsupported_plan_type", "review_status": _text(plan.get("review_status"))}
        recipients = [
            item
            for item in self.recipients
            if item["plan_id"] == normalized_plan_id
            and item.get("approval_status") != "rejected"
            and item.get("send_status") not in {"cancelled", "sent"}
            and _text(item.get("unionid"))
            and any(
                message.get("plan_id") == normalized_plan_id
                and int(message.get("recipient_id") or 0) == int(item.get("id") or 0)
                and message.get("status") != "cancelled"
                for message in self.messages
            )
        ]
        if not recipients:
            return {"status": "skipped", "reason": "missing_audience"}
        planner_idempotency_key = _plan_broadcast_idempotency_key(
            normalized_plan_id,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key,
        )
        job_ids: list[int] = []
        created_count = 0
        reused_count = 0
        for recipient in recipients:
            recipient_id = int(recipient["id"])
            existing = next(
                (
                    item
                    for item in self.broadcast_jobs
                    if item.get("idempotency_key") == f"cloud_plan_recipient:{normalized_plan_id}:{recipient_id}"
                ),
                None,
            )
            if existing:
                job_id = int(existing["id"])
                reused_count += 1
            else:
                job_id = len(self.broadcast_jobs) + 1
                self.broadcast_jobs.append(
                    {
                        "id": job_id,
                        "source_type": "cloud_plan",
                        "source_table": "cloud_broadcast_plan_recipients",
                        "source_id": f"{normalized_plan_id}:{recipient_id}",
                        "scheduled_for": _now(),
                        "priority": 100,
                        "batch_key": f"cloud_plan_recipient:{normalized_plan_id}",
                        "business_domain": "ai_assistant",
                        "idempotency_key": f"cloud_plan_recipient:{normalized_plan_id}:{recipient_id}",
                        "channel": "wecom_private",
                        "target_kind": "unionid",
                        "status": "queued",
                        "requires_approval": False,
                        "target_unionids_json": [_text(recipient["unionid"])],
                        "target_count": 1,
                        "target_summary": _text(recipient.get("display_name")) or _text(recipient["unionid"]),
                        "content_type": "cloud_plan",
                        "content_payload": {
                            "plan_id": normalized_plan_id,
                            "recipient_id": recipient_id,
                            "unionid": _text(recipient["unionid"]),
                            "message_mode": "recipient_messages",
                        },
                        "content_summary": f"{_text(plan.get('display_name')) or _text(plan.get('intent')) or normalized_plan_id} · {_text(recipient.get('display_name')) or _text(recipient['unionid'])}",
                        "trace_id": normalized_plan_id,
                        "created_by": _text(operator) or "internal_event_worker",
                        "created_at": _now(),
                        "updated_at": _now(),
                        "metadata_json": {
                            "planner_consumer": "broadcast_task_planner_consumer",
                            "source_event_id": _text(source_event_id),
                            "plan_idempotency_key": planner_idempotency_key,
                            "duplicate_policy": "reuse_recipient_idempotency_key",
                        },
                    }
                )
                created_count += 1
            job_ids.append(job_id)
            recipient.update(
                {
                    "approval_status": "approved",
                    "send_status": "queued" if recipient.get("send_status") == "pending" else recipient.get("send_status"),
                    "approved_by": recipient.get("approved_by") or operator,
                    "approved_at": recipient.get("approved_at") or _now(),
                    "broadcast_job_id": recipient.get("broadcast_job_id") or job_id,
                    "updated_at": _now(),
                }
            )
            for message in self.messages:
                if message.get("plan_id") == normalized_plan_id and int(message.get("recipient_id") or 0) == recipient_id and message.get("status") == "pending":
                    message["status"] = "queued"
        self.audits.append(
            {
                "action_type": "ops_plan_recipient_broadcast_jobs_plan",
                "target_id": normalized_plan_id,
                "operator": operator,
                "plan_id": normalized_plan_id,
                "broadcast_job_count": len(set(job_ids)),
                "created_count": created_count,
                "reused_count": reused_count,
            }
        )
        first_job_id = job_ids[0] if job_ids else 0
        return {
            "status": "created" if created_count else "reused",
            "broadcast_job_id": first_job_id,
            "broadcast_job_count": len(set(job_ids)),
            "created_count": created_count,
            "reused_count": reused_count,
            "idempotency_key": planner_idempotency_key,
            "target_count": len(recipients),
            "source_id": normalized_plan_id,
            "trace_id": normalized_plan_id,
            "downstream_status": "broadcast_job_queued",
            "push_center_job_id": f"broadcast_job:{first_job_id}" if first_job_id else "",
        }

    def create_or_reuse_plan_broadcast_job(
        self,
        plan_id: str,
        *,
        operator: str,
        source_event_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        return self.create_or_reuse_recipient_broadcast_jobs(
            plan_id,
            operator=operator,
            source_event_id=source_event_id,
            idempotency_key=idempotency_key,
        )

    def create_or_reuse_agent_send_plan(
        self,
        *,
        external_event_id: str,
        package_key: str,
        external_userid: str,
        owner_userid: str,
        content_package: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        normalized_event_id = _text(external_event_id)
        normalized_external_userid = _text(external_userid)
        normalized_owner = _text(owner_userid)
        if not normalized_event_id:
            return {"status": "skipped", "reason": "missing_external_event_id"}
        if not normalized_external_userid:
            return {"status": "skipped", "reason": "missing_external_userid"}
        if not normalized_owner:
            return {"status": "skipped", "reason": "missing_owner_userid"}
        normalized_unionid = self._resolve_fixture_unionid_by_external_userid(normalized_external_userid)
        if not normalized_unionid:
            return {"status": "skipped", "reason": "identity_pending_unionid"}
        plan_id = _agent_plan_id(normalized_event_id)
        existing = next((item for item in self.plans if item.get("plan_id") == plan_id), None)
        if not existing:
            self.plans.append(
                {
                    "id": len(self.plans) + len(self.legacy_plans) + 1,
                    "plan_id": plan_id,
                    "display_name": f"Agent 生成待发送计划 · {normalized_external_userid}",
                    "intent": f"Agent generated send plan {normalized_external_userid}",
                    "owner_userid": normalized_owner,
                    "candidate_count": 1,
                    "review_status": "approved",
                    "run_status": "draft",
                    "status": "draft",
                    "selection_json": {
                        "source": "automation_agent",
                        "package_key": _text(package_key),
                        "external_event_id": normalized_event_id,
                        "unionid": normalized_unionid,
                    },
                    "updated_at": _now(),
                    "source_type": "cloud_plan",
                }
            )
        recipient = next(
            (
                item
                for item in self.recipients
                if item.get("plan_id") == plan_id and item.get("unionid") == normalized_unionid
            ),
            None,
        )
        if recipient is None:
            recipient = {
                "id": len(self.recipients) + 1,
                "plan_id": plan_id,
                "unionid": normalized_unionid,
                "external_userid": normalized_external_userid,
                "owner_userid": normalized_owner,
                "display_name": normalized_unionid,
                "planned_message_count": 1,
                "approval_status": "approved",
                "send_status": "pending",
                "updated_at": _now(),
            }
            self.recipients.append(recipient)
        content_payload = _content_payload_for_package(content_package)
        message = next(
            (
                item
                for item in self.messages
                if item.get("plan_id") == plan_id and int(item.get("recipient_id") or 0) == int(recipient["id"]) and int(item.get("sequence_index") or 0) == 1
            ),
            None,
        )
        if message is None:
            message = {
                "id": len(self.messages) + 1,
                "plan_id": plan_id,
                "recipient_id": int(recipient["id"]),
                "unionid": normalized_unionid,
                "external_userid": normalized_external_userid,
                "sequence_index": 1,
                "day_offset": 0,
                "send_time": "",
                "content_text": _text(content_package.get("content_text")),
                "content_payload_json": content_payload,
                "attachments_json": [],
                "status": "pending",
            }
            self.messages.append(message)
        else:
            message["content_text"] = _text(content_package.get("content_text"))
            message["content_payload_json"] = content_payload
        self.audits.append(
            {
                "action_type": "automation_agent_enqueue_send_plan",
                "target_id": plan_id,
                "operator": operator,
                "external_event_id": normalized_event_id,
            }
        )
        return {
            "status": "reused" if existing else "created",
            "plan_id": plan_id,
            "recipient_id": int(recipient["id"]),
            "message_id": int(message["id"]),
            "downstream_status": "send_plan_pending",
            "push_center_job_id": f"cloud_plan:{plan_id}",
        }

    def approve_recipient(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise LookupError("plan not found")
        if plan["review_status"] == "rejected":
            raise ValueError("plan is rejected")
        if plan["review_status"] not in {"approved", "reviewing"}:
            raise ValueError("plan is not approved for recipient review")
        recipient = next((item for item in self.recipients if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id)), None)
        if not recipient:
            raise LookupError("recipient not found")
        if recipient.get("approval_status") == "rejected":
            raise ValueError("recipient is rejected")
        source_id = f"{plan_id}:{int(recipient_id)}"
        existing = next((item for item in self.broadcast_jobs if item["source_id"] == source_id), None)
        if existing:
            status = "already_approved"
            job_id = existing["id"]
        else:
            job_id = len(self.broadcast_jobs) + 1
            self.broadcast_jobs.append(
                {
                    "id": job_id,
                    "source_type": "cloud_plan",
                    "source_table": "cloud_broadcast_plan_recipients",
                    "source_id": source_id,
                    "target_unionids_json": [recipient["unionid"]],
                    "target_count": 1,
                    "content_payload": {"plan_id": plan_id, "recipient_id": int(recipient_id), "unionid": recipient["unionid"], "message_mode": "recipient_messages"},
                    "idempotency_key": f"cloud_plan_recipient:{plan_id}:{int(recipient_id)}",
                }
            )
            status = "approved"
        recipient.update({"approval_status": "approved", "send_status": "queued", "approved_by": operator, "approved_at": _now(), "broadcast_job_id": job_id, "updated_at": _now()})
        for message in self.messages:
            if int(message["recipient_id"]) == int(recipient_id) and message.get("status") == "pending":
                message["status"] = "queued"
        self.audits.append({"action_type": "cloud_plan_recipient_approve", "target_id": source_id, "operator": operator})
        return {"status": status, "recipient": _recipient_view(copy.deepcopy(recipient)), "job_id": job_id}

    def reject_recipient(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise LookupError("plan not found")
        if plan["review_status"] == "rejected":
            raise ValueError("plan is rejected")
        recipient = next((item for item in self.recipients if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id)), None)
        if not recipient:
            raise LookupError("recipient not found")
        if recipient.get("send_status") == "sent":
            raise ValueError("sent recipient cannot be rejected")
        recipient.update({"approval_status": "rejected", "send_status": "cancelled", "rejected_by": operator, "rejected_at": _now(), "reject_reason": reason, "updated_at": _now()})
        self.audits.append({"action_type": "cloud_plan_recipient_reject", "target_id": f"{plan_id}:{int(recipient_id)}", "operator": operator})
        return {"status": "rejected", "recipient": _recipient_view(copy.deepcopy(recipient))}

    def update_recipient_message(
        self,
        plan_id: str,
        recipient_id: int,
        message_id: int,
        *,
        content_package: dict[str, Any],
        day_offset: Any = None,
        send_time: Any = None,
        operator: str,
    ) -> dict[str, Any]:
        if int(recipient_id) < 0:
            plan = self.get_plan(plan_id)
            if not plan:
                raise LookupError("plan not found")
            if plan["review_status"] == "rejected":
                raise ValueError("plan is rejected")
            recipient = next((item for item in self.legacy_recipients if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id)), None)
            if not recipient:
                raise LookupError("recipient not found")
            if recipient.get("approval_status") != "pending" or recipient.get("send_status") != "pending":
                raise ValueError("recipient is not editable")
            message = next((item for item in self.legacy_messages if int(item["recipient_id"]) == int(recipient_id) and int(item["id"]) == int(message_id)), None)
            if not message:
                raise LookupError("message not found")
            if message.get("status") != "pending":
                raise ValueError("message is not editable")
            try:
                normalized_day_offset = max(0, int(day_offset if day_offset is not None else message.get("day_offset") or 0))
            except (TypeError, ValueError):
                normalized_day_offset = int(message.get("day_offset") or 0)
            content_payload = _content_payload_for_package(content_package)
            message.update(
                {
                    "content_text": _text(content_package.get("content_text")),
                    "content_payload_json": content_payload,
                    "attachments_json": [],
                    "day_offset": normalized_day_offset,
                    "send_time": _text(send_time) or _text(message.get("send_time")),
                    "updated_at": _now(),
                }
            )
            recipient["updated_at"] = _now()
            self.audits.append({"action_type": "legacy_campaign_step_update_from_cloud_plan", "target_id": f"{plan_id}:{int(recipient_id)}:{int(message_id)}", "operator": operator})
            return {
                "status": "updated",
                "recipient": _recipient_view(copy.deepcopy(recipient)),
                "message": _message_view(copy.deepcopy(message)),
            }
        plan = self.get_plan(plan_id)
        if not plan:
            raise LookupError("plan not found")
        if plan["review_status"] == "rejected":
            raise ValueError("plan is rejected")
        recipient = next((item for item in self.recipients if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id)), None)
        if not recipient:
            raise LookupError("recipient not found")
        if recipient.get("approval_status") != "pending" or recipient.get("send_status") != "pending":
            raise ValueError("recipient is not editable")
        message = next((item for item in self.messages if int(item["recipient_id"]) == int(recipient_id) and int(item["id"]) == int(message_id)), None)
        if not message:
            raise LookupError("message not found")
        if message.get("status") != "pending":
            raise ValueError("message is not editable")
        try:
            normalized_day_offset = max(0, int(day_offset if day_offset is not None else message.get("day_offset") or 0))
        except (TypeError, ValueError):
            normalized_day_offset = int(message.get("day_offset") or 0)
        content_payload = _content_payload_for_package(content_package)
        message.update(
            {
                "content_text": _text(content_package.get("content_text")),
                "content_payload_json": content_payload,
                "attachments_json": [],
                "day_offset": normalized_day_offset,
                "send_time": _text(send_time) or _text(message.get("send_time")),
                "updated_at": _now(),
            }
        )
        recipient["updated_at"] = _now()
        self.audits.append({"action_type": "cloud_plan_recipient_message_update", "target_id": f"{plan_id}:{int(recipient_id)}:{int(message_id)}", "operator": operator})
        return {
            "status": "updated",
            "recipient": _recipient_view(copy.deepcopy(recipient)),
            "message": _message_view(copy.deepcopy(message)),
        }


_FIXTURE_REPO = InMemoryCloudPlanRepository()


def reset_cloud_plan_fixture_state() -> None:
    _FIXTURE_REPO.reset()


def build_cloud_plan_repository() -> CloudPlanRepository:
    if production_data_ready():
        return PostgresCloudPlanRepository()
    return _FIXTURE_REPO
