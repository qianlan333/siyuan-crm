from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

from aicrm_next.shared.postgres_connection import get_db

JsonDict = dict[str, Any]


class ExternalCampaignRepositoryError(Exception):
    pass


class ExternalCampaignRepository(Protocol):
    def table_columns(self, table_name: str) -> set[str]: ...
    def fetch_user_ops_pool_current_row(self, external_userid: str) -> JsonDict: ...
    def fetch_automation_member_row(self, external_userid: str) -> JsonDict: ...
    def fetch_contact_row(self, external_userid: str) -> JsonDict: ...
    def get_sidebar_binding_candidate(self, external_userid: str) -> JsonDict: ...
    def ensure_automation_member_for_external_campaign(
        self,
        *,
        external_userid: str,
        owner_userid: str,
        operator: str,
        dry_run: bool,
        allow_owner_mismatch: bool,
    ) -> JsonDict: ...
    def get_campaign_by_code(self, campaign_code: str) -> JsonDict | None: ...
    def get_campaign_by_id(self, campaign_id: int) -> JsonDict | None: ...
    def count_open_campaign_jobs(self, campaign_id: int) -> int: ...
    def get_segment_by_code(self, segment_code: str) -> JsonDict | None: ...
    def create_or_update_external_segment(
        self,
        *,
        segment_code: str,
        display_name: str,
        external_userid: str,
        owner_userid: str,
        sql_query: str,
        sql_params: JsonDict,
        operator: str,
        session_id: str,
    ) -> JsonDict: ...
    def create_campaign_draft(
        self,
        *,
        campaign_code: str,
        display_name: str,
        intent: str,
        anchor_date: str,
        owner_userid: str,
        operator: str,
        session_id: str,
        trace_id: str,
        metadata: JsonDict,
    ) -> JsonDict: ...
    def add_segment_to_campaign(self, *, campaign_id: int, segment_code: str, priority: int, label: str) -> JsonDict: ...
    def add_step_to_campaign(
        self,
        *,
        campaign_id: int,
        campaign_segment_id: int,
        step_index: int,
        day_offset: int,
        content_text: str,
        content_payload: JsonDict,
        send_time: str,
        timezone_name: str,
        stop_on_reply: bool,
        skip_if_recently_touched_days: int,
        agent_run_id: str,
    ) -> JsonDict: ...
    def allocate_campaign_members(self, campaign_id: int) -> JsonDict: ...
    def submit_campaign_for_review(self, campaign_id: int, operator: str) -> JsonDict: ...
    def delete_campaign(self, campaign_id: int) -> JsonDict: ...
    def assemble_campaign_overview(self, campaign_id: int) -> JsonDict: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_text(value: Any, *, default: str = "{}") -> str:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str):
        return value or default
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_object(value: Any) -> JsonDict:
    if isinstance(value, dict):
        return dict(value)
    try:
        loaded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def _json_list(value: Any) -> list[JsonDict]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    try:
        loaded = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [dict(item) for item in loaded if isinstance(item, dict)] if isinstance(loaded, list) else []


def _row_to_dict(row: Any) -> JsonDict:
    return dict(row) if row else {}


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class PostgresExternalCampaignRepository:
    def __init__(self, db: Any | None = None) -> None:
        self.db = db or get_db()
        self._columns_cache: dict[str, set[str]] = {}

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def table_columns(self, table_name: str) -> set[str]:
        safe_name = _text(table_name)
        if not safe_name.replace("_", "").isalnum():
            raise ExternalCampaignRepositoryError(f"invalid_table_name:{safe_name}")
        if safe_name in self._columns_cache:
            return self._columns_cache[safe_name]
        cur = self.db.cursor()
        try:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ?
                """,
                (safe_name,),
            )
            columns = {_text(row.get("column_name")) for row in (cur.fetchall() or []) if _text(row.get("column_name"))}
            if columns:
                self._columns_cache[safe_name] = columns
                return columns
        except Exception:
            self.rollback()
        try:
            cur.execute(f"PRAGMA table_info({safe_name})")
            columns = {_text(row.get("name")) for row in (cur.fetchall() or []) if _text(row.get("name"))}
            self._columns_cache[safe_name] = columns
            return columns
        except Exception:
            self.rollback()
        self._columns_cache[safe_name] = set()
        return set()

    def fetch_user_ops_pool_current_row(self, external_userid: str) -> JsonDict:
        row = self.db.execute(
            """
            SELECT *
            FROM user_ops_pool_current
            WHERE external_userid = ?
            LIMIT 1
            """,
            (_text(external_userid),),
        ).fetchone()
        return _row_to_dict(row)

    def fetch_automation_member_row(self, external_userid: str) -> JsonDict:
        row = self.db.execute(
            """
            SELECT id, external_contact_id, owner_staff_id
            FROM automation_member
            WHERE external_contact_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (_text(external_userid),),
        ).fetchone()
        return _row_to_dict(row)

    def fetch_contact_row(self, external_userid: str) -> JsonDict:
        row = self.db.execute(
            """
            SELECT external_userid, owner_userid, customer_name, remark
            FROM contacts
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (_text(external_userid),),
        ).fetchone()
        return _row_to_dict(row)

    def get_sidebar_binding_candidate(self, external_userid: str) -> JsonDict:
        row = self.db.execute(
            """
            SELECT
                b.external_userid,
                p.id AS person_id,
                p.mobile AS phone,
                b.last_owner_userid,
                b.first_owner_userid,
                c.owner_userid AS contact_owner_userid,
                COALESCE(NULLIF(c.customer_name, ''), NULLIF(c.remark, '')) AS customer_name,
                (
                    SELECT wf.user_id
                    FROM wecom_external_contact_follow_users wf
                    WHERE wf.external_userid = b.external_userid
                      AND wf.relation_status = 'active'
                      AND wf.user_id <> ''
                    ORDER BY
                      CASE WHEN wf.is_primary THEN 0 ELSE 1 END ASC,
                      wf.updated_at DESC,
                      wf.id DESC
                    LIMIT 1
                ) AS active_follow_userid
            FROM external_contact_bindings b
            JOIN people p ON p.id = b.person_id
            LEFT JOIN contacts c ON c.external_userid = b.external_userid
            WHERE b.external_userid = ?
              AND b.external_userid <> ''
              AND p.mobile <> ''
            LIMIT 1
            """,
            (_text(external_userid),),
        ).fetchone()
        candidate = _row_to_dict(row)
        if not candidate:
            return {}
        owner = (
            _text(candidate.get("active_follow_userid"))
            or _text(candidate.get("last_owner_userid"))
            or _text(candidate.get("first_owner_userid"))
            or _text(candidate.get("contact_owner_userid"))
        )
        return {
            "external_userid": _text(candidate.get("external_userid")),
            "phone": _text(candidate.get("phone")),
            "person_id": _positive_int(candidate.get("person_id")),
            "owner_staff_id": owner,
            "customer_name": _text(candidate.get("customer_name")),
        }

    def _backfill_source(self, external_userid: str) -> JsonDict:
        contact = self.fetch_contact_row(external_userid)
        pool_current = self.fetch_user_ops_pool_current_row(external_userid)
        if contact or pool_current:
            source = contact or pool_current
            return {
                "source": "contacts" if contact else "user_ops_pool_current",
                "external_userid": external_userid,
                "owner_userid": _text(contact.get("owner_userid")) or _text(pool_current.get("owner_userid")),
                "customer_name": _text(contact.get("customer_name")) or _text(pool_current.get("customer_name")),
                "remark": _text(contact.get("remark")),
                "phone": _text(pool_current.get("mobile")) or _text(pool_current.get("phone")),
                "person_id": _positive_int(pool_current.get("person_id") or pool_current.get("master_customer_id")),
                "contact": contact,
                "pool_current": pool_current,
            }
        candidate = self.get_sidebar_binding_candidate(external_userid)
        if not candidate:
            return {}
        return {
            "source": "sidebar_binding",
            "external_userid": external_userid,
            "owner_userid": _text(candidate.get("owner_staff_id")),
            "customer_name": _text(candidate.get("customer_name")),
            "phone": _text(candidate.get("phone")),
            "person_id": _positive_int(candidate.get("person_id")),
            "contact": {},
            "pool_current": {},
        }

    def ensure_automation_member_for_external_campaign(
        self,
        *,
        external_userid: str,
        owner_userid: str,
        operator: str,
        dry_run: bool,
        allow_owner_mismatch: bool,
    ) -> JsonDict:
        external = _text(external_userid)
        requested_owner = _text(owner_userid)
        existing = self.fetch_automation_member_row(external)
        if existing:
            return {
                "external_userid": external,
                "status": "exists",
                "source": "automation_member",
                "automation_member_id": int(existing.get("id") or 0),
                "owner_userid": _text(existing.get("owner_staff_id")),
            }
        source = self._backfill_source(external)
        if not source:
            return {"external_userid": external, "status": "unresolved", "source": "", "owner_userid": ""}
        source_owner = _text(source.get("owner_userid"))
        if source_owner and requested_owner and source_owner != requested_owner and not allow_owner_mismatch:
            return {
                "external_userid": external,
                "status": "owner_mismatch",
                "source": _text(source.get("source")),
                "owner_userid": source_owner,
                "requested_owner_userid": requested_owner,
                "customer_name": _text(source.get("customer_name")),
            }
        result = {
            "external_userid": external,
            "status": "would_insert" if dry_run else "inserted",
            "source": _text(source.get("source")),
            "owner_userid": source_owner or requested_owner,
            "requested_owner_userid": requested_owner,
            "customer_name": _text(source.get("customer_name")),
            "operator": _text(operator),
            "target": source,
        }
        if dry_run:
            return result

        columns = self.table_columns("automation_member")
        if "external_contact_id" not in columns:
            raise ExternalCampaignRepositoryError("automation_member.external_contact_id column is required")
        sidebar = _text(source.get("source")) == "sidebar_binding"
        values: JsonDict = {
            "external_contact_id": external,
            "phone": _text(source.get("phone")),
            "master_customer_id": _positive_int(source.get("person_id")),
            "owner_staff_id": source_owner or requested_owner,
            "in_pool": True,
            "current_pool": "campaign_ready" if sidebar else "operating",
            "current_audience_code": "pending_questionnaire" if sidebar else "operating",
            "source_type": "sidebar_binding_campaign_backfill" if sidebar else "external_campaign_backfill",
            "joined_at": "CURRENT_TIMESTAMP",
            "created_at": "CURRENT_TIMESTAMP",
            "updated_at": "CURRENT_TIMESTAMP",
        }
        insert_columns = [column for column in values if column in columns and values[column] is not None]
        placeholders: list[str] = []
        params: list[Any] = []
        for column in insert_columns:
            value = values[column]
            if value == "CURRENT_TIMESTAMP":
                placeholders.append("CURRENT_TIMESTAMP")
            else:
                placeholders.append("?")
                params.append(value)
        cur = self.db.cursor()
        cur.execute(
            f"INSERT INTO automation_member ({', '.join(insert_columns)}) VALUES ({', '.join(placeholders)})",
            tuple(params),
        )
        result["automation_member_id"] = int(cur.lastrowid or 0)
        return result

    def _decode_campaign(self, row: Any) -> JsonDict | None:
        if not row:
            return None
        item = _row_to_dict(row)
        item["metadata"] = _json_object(item.get("metadata_json"))
        item["stats"] = _json_object(item.get("stats_json"))
        return item

    def get_campaign_by_code(self, campaign_code: str) -> JsonDict | None:
        row = self.db.execute("SELECT * FROM campaigns WHERE campaign_code = ? LIMIT 1", (_text(campaign_code),)).fetchone()
        return self._decode_campaign(row)

    def get_campaign_by_id(self, campaign_id: int) -> JsonDict | None:
        row = self.db.execute("SELECT * FROM campaigns WHERE id = ? LIMIT 1", (int(campaign_id),)).fetchone()
        return self._decode_campaign(row)

    def count_open_campaign_jobs(self, campaign_id: int) -> int:
        row = self.db.execute(
            """
            SELECT COUNT(*) AS job_count
            FROM broadcast_jobs
            WHERE source_type = 'campaign'
              AND source_id LIKE ?
              AND status IN ('waiting_approval', 'queued', 'claimed')
            """,
            (f"{int(campaign_id)}:%",),
        ).fetchone()
        return int((row or {}).get("job_count") or 0)

    def _decode_segment(self, row: Any) -> JsonDict | None:
        if not row:
            return None
        item = _row_to_dict(row)
        item["sql_params"] = _json_object(item.get("sql_params_json"))
        item["cached_sample"] = _json_list(item.get("cached_sample_json"))
        return item

    def get_segment_by_code(self, segment_code: str) -> JsonDict | None:
        row = self.db.execute("SELECT * FROM segments WHERE segment_code = ? LIMIT 1", (_text(segment_code),)).fetchone()
        return self._decode_segment(row)

    def _run_segment_query(self, sql_query: str, sql_params: JsonDict, *, max_rows: int = 10000) -> list[JsonDict]:
        safe_sql = f"SELECT * FROM ({sql_query.strip().rstrip(';')}) AS _external_campaign_segment LIMIT {int(max_rows)}"
        rows = self.db.execute(safe_sql, sql_params or {}).fetchall() or []
        cleaned: list[JsonDict] = []
        seen: set[int] = set()
        for row in rows:
            item = _row_to_dict(row)
            try:
                member_id = int(item.get("member_id") or 0)
            except (TypeError, ValueError):
                continue
            if member_id <= 0 or member_id in seen:
                continue
            seen.add(member_id)
            item["member_id"] = member_id
            item["external_contact_id"] = _text(item.get("external_contact_id"))
            cleaned.append(item)
        return cleaned

    def create_or_update_external_segment(
        self,
        *,
        segment_code: str,
        display_name: str,
        external_userid: str,
        owner_userid: str,
        sql_query: str,
        sql_params: JsonDict,
        operator: str,
        session_id: str,
    ) -> JsonDict:
        code = _text(segment_code)
        existing = self.get_segment_by_code(code)
        if existing and _text(existing.get("source_type")) != "external_campaign":
            raise ExternalCampaignRepositoryError(f"segment_code already exists with source_type={existing.get('source_type')}")
        rows = self._run_segment_query(sql_query, sql_params)
        headcount = len(rows)
        sample_json = json.dumps(rows[:20], ensure_ascii=False, default=str)[:8000]
        params_json = json.dumps(sql_params or {"external_userid": _text(external_userid)}, ensure_ascii=False)
        if existing:
            version = int(existing.get("version") or 1) + 1
            self.db.execute(
                """
                UPDATE segments SET
                    display_name = ?, sql_query = ?, sql_params_json = ?,
                    status = 'active', cached_headcount = ?, cached_sample_json = ?,
                    last_refreshed_at = ?, version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _text(display_name) or code,
                    sql_query,
                    params_json,
                    headcount,
                    sample_json,
                    _now_iso(),
                    version,
                    _now_iso(),
                    int(existing["id"]),
                ),
            )
            return self.get_segment_by_code(code) or {}
        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO segments
                (segment_code, display_name, description, source_type, sql_query,
                 sql_params_json, status, version, created_by_agent, created_by_session,
                 cached_headcount, cached_sample_json, last_refreshed_at, tags_json)
            VALUES (?, ?, ?, 'external_campaign', ?, ?, 'active', 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                _text(display_name) or code,
                "External token protected one-recipient campaign segment.",
                sql_query,
                params_json,
                _text(operator)[:100],
                _text(session_id)[:100],
                headcount,
                sample_json,
                _now_iso(),
                json.dumps(["external_campaign", _text(owner_userid)], ensure_ascii=False),
            ),
        )
        return self.get_segment_by_code(code) or {"id": int(cur.lastrowid or 0), "segment_code": code, "cached_headcount": headcount, "status": "active", "source_type": "external_campaign", "sql_params": sql_params}

    def create_campaign_draft(
        self,
        *,
        campaign_code: str,
        display_name: str,
        intent: str,
        anchor_date: str,
        owner_userid: str,
        operator: str,
        session_id: str,
        trace_id: str,
        metadata: JsonDict,
    ) -> JsonDict:
        code = _text(campaign_code)
        if self.get_campaign_by_code(code):
            raise ExternalCampaignRepositoryError(f"campaign_code already exists: {code}")
        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO campaigns
                (campaign_code, display_name, intent, anchor_mode, anchor_date,
                 review_status, run_status, created_by_agent, created_by_session,
                 trace_id, owner_userid, metadata_json)
            VALUES (?, ?, ?, 'campaign_start_date', ?, 'draft', 'draft', ?, ?, ?, ?, ?)
            """,
            (
                code,
                _text(display_name) or code,
                _text(intent),
                _text(anchor_date),
                _text(operator)[:100],
                _text(session_id)[:100],
                _text(trace_id)[:100],
                _text(owner_userid)[:100],
                json.dumps(metadata or {}, ensure_ascii=False, default=str),
            ),
        )
        campaign = self.get_campaign_by_code(code)
        if campaign:
            return campaign
        return {"id": int(cur.lastrowid or 0), "campaign_code": code, "review_status": "draft", "run_status": "draft"}

    def add_segment_to_campaign(self, *, campaign_id: int, segment_code: str, priority: int, label: str) -> JsonDict:
        segment = self.get_segment_by_code(segment_code)
        if not segment:
            raise ExternalCampaignRepositoryError("segment not found")
        if _text(segment.get("status")) != "active":
            raise ExternalCampaignRepositoryError(f"segment not active: {segment.get('segment_code')}")
        row = self.db.execute(
            "SELECT id FROM campaign_segments WHERE campaign_id = ? AND segment_id = ?",
            (int(campaign_id), int(segment["id"])),
        ).fetchone()
        if row:
            return {"id": int(row["id"]), "status": "exists", "segment_id": int(segment["id"])}
        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO campaign_segments (campaign_id, segment_id, segment_code, priority, label)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(campaign_id), int(segment["id"]), _text(segment["segment_code"]), int(priority), _text(label)[:200]),
        )
        self.db.execute("UPDATE segments SET usage_count = usage_count + 1, updated_at = ? WHERE id = ?", (_now_iso(), int(segment["id"])))
        return {"id": int(cur.lastrowid or 0), "segment_id": int(segment["id"])}

    def add_step_to_campaign(
        self,
        *,
        campaign_id: int,
        campaign_segment_id: int,
        step_index: int,
        day_offset: int,
        content_text: str,
        content_payload: JsonDict,
        send_time: str,
        timezone_name: str,
        stop_on_reply: bool,
        skip_if_recently_touched_days: int,
        agent_run_id: str,
    ) -> JsonDict:
        self.db.execute(
            """
            INSERT INTO campaign_steps
                (campaign_id, campaign_segment_id, step_index, day_offset, send_time,
                 timezone, content_text, content_payload_json, stop_on_reply,
                 skip_if_recently_touched_days, agent_run_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (campaign_segment_id, step_index) DO UPDATE SET
                campaign_id = excluded.campaign_id,
                day_offset = excluded.day_offset,
                send_time = excluded.send_time,
                timezone = excluded.timezone,
                content_text = excluded.content_text,
                content_payload_json = excluded.content_payload_json,
                stop_on_reply = excluded.stop_on_reply,
                skip_if_recently_touched_days = excluded.skip_if_recently_touched_days,
                agent_run_id = excluded.agent_run_id,
                updated_at = excluded.updated_at
            """,
            (
                int(campaign_id),
                int(campaign_segment_id),
                int(step_index),
                int(day_offset),
                _text(send_time) or "09:00",
                _text(timezone_name) or "Asia/Shanghai",
                _text(content_text)[:4000],
                json.dumps(content_payload or {}, ensure_ascii=False, default=str),
                bool(stop_on_reply),
                int(skip_if_recently_touched_days or 0),
                _text(agent_run_id)[:100],
                _now_iso(),
            ),
        )
        return {"campaign_segment_id": int(campaign_segment_id), "step_index": int(step_index)}

    def allocate_campaign_members(self, campaign_id: int) -> JsonDict:
        campaign = self.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ExternalCampaignRepositoryError("campaign not found")
        rows = self.db.execute(
            """
            SELECT cs.id AS campaign_segment_id, cs.segment_id, cs.priority,
                   s.segment_code, s.sql_query, s.sql_params_json, s.status, s.source_type
            FROM campaign_segments cs
            JOIN segments s ON s.id = cs.segment_id
            WHERE cs.campaign_id = ?
            ORDER BY cs.priority DESC, cs.id ASC
            """,
            (int(campaign_id),),
        ).fetchall() or []
        columns = self.table_columns("campaign_members")
        base_columns = ["campaign_id", "campaign_segment_id", "segment_id", "member_id", "external_contact_id", "status"]
        optional_columns = [column for column in ("current_step_index", "trace_id") if column in columns]
        allocated = 0
        skipped = 0
        per_segment: dict[int, JsonDict] = {}
        errors: list[JsonDict] = []
        seen: set[int] = set()
        for row in rows:
            segment = _row_to_dict(row)
            if _text(segment.get("status")) != "active" or _text(segment.get("source_type")) != "external_campaign":
                continue
            cs_id = int(segment["campaign_segment_id"])
            bucket = per_segment.setdefault(cs_id, {"matched": 0, "allocated": 0, "skipped": 0})
            member_rows = self._run_segment_query(_text(segment.get("sql_query")), _json_object(segment.get("sql_params_json")))
            bucket["matched"] += len(member_rows)
            for member in member_rows:
                member_id = int(member["member_id"])
                if member_id in seen:
                    skipped += 1
                    bucket["skipped"] += 1
                    continue
                insert_columns = base_columns + optional_columns
                values: list[Any] = [
                    int(campaign_id),
                    cs_id,
                    int(segment["segment_id"]),
                    member_id,
                    _text(member.get("external_contact_id")),
                    "pending",
                ]
                if "current_step_index" in optional_columns:
                    values.append(-1)
                if "trace_id" in optional_columns:
                    values.append(_text(campaign.get("trace_id")))
                try:
                    placeholders = ", ".join("?" for _ in values)
                    self.db.execute(
                        f"INSERT INTO campaign_members ({', '.join(insert_columns)}) VALUES ({placeholders})",
                        tuple(values),
                    )
                    seen.add(member_id)
                    allocated += 1
                    bucket["allocated"] += 1
                except Exception as exc:
                    skipped += 1
                    bucket["skipped"] += 1
                    if len(errors) < 10:
                        errors.append({"member_id": member_id, "campaign_segment_id": cs_id, "reason": str(exc)})
        return {
            "campaign_id": int(campaign_id),
            "allocated": allocated,
            "skipped_collisions": skipped,
            "per_segment": per_segment,
            "errors": errors,
            "trace_id": _text(campaign.get("trace_id")),
        }

    def submit_campaign_for_review(self, campaign_id: int, operator: str) -> JsonDict:
        cur = self.db.cursor()
        cur.execute(
            """
            UPDATE campaigns
            SET review_status = 'pending_review', updated_at = ?
            WHERE id = ? AND review_status IN ('draft','pending_review')
            """,
            (_now_iso(), int(campaign_id)),
        )
        if not cur.rowcount:
            raise ExternalCampaignRepositoryError("campaign not in submittable state")
        return self.get_campaign_by_id(campaign_id) or {}

    def delete_campaign(self, campaign_id: int) -> JsonDict:
        cid = int(campaign_id)
        deleted: dict[str, int] = {}
        for table in ("campaign_members", "campaign_steps", "campaign_segments"):
            cur = self.db.cursor()
            cur.execute(f"DELETE FROM {table} WHERE campaign_id = ?", (cid,))
            deleted[table] = int(cur.rowcount or 0)
        cur = self.db.cursor()
        cur.execute("DELETE FROM campaigns WHERE id = ?", (cid,))
        deleted["campaigns"] = int(cur.rowcount or 0)
        return {"ok": deleted["campaigns"] > 0, "deleted_id": cid, "rows_cleared": deleted}

    def assemble_campaign_overview(self, campaign_id: int) -> JsonDict:
        campaign = self.get_campaign_by_id(campaign_id)
        if not campaign:
            return {}
        segment_rows = self.db.execute(
            """
            SELECT cs.id AS campaign_segment_id, cs.segment_id, cs.segment_code,
                   cs.priority, cs.label,
                   s.display_name AS segment_name, s.cached_headcount,
                   (SELECT COUNT(*) FROM campaign_members cm
                      WHERE cm.campaign_segment_id = cs.id) AS allocated_count
            FROM campaign_segments cs
            JOIN segments s ON s.id = cs.segment_id
            WHERE cs.campaign_id = ?
            ORDER BY cs.priority DESC, cs.id ASC
            """,
            (int(campaign_id),),
        ).fetchall() or []
        segments: list[JsonDict] = []
        for row in segment_rows:
            item = _row_to_dict(row)
            step_rows = self.db.execute(
                """
                SELECT step_index, day_offset, send_time, content_text, stop_on_reply,
                       skip_if_recently_touched_days, content_payload_json
                FROM campaign_steps
                WHERE campaign_segment_id = ?
                ORDER BY step_index ASC
                """,
                (int(item["campaign_segment_id"]),),
            ).fetchall() or []
            steps = []
            for step_row in step_rows:
                step = _row_to_dict(step_row)
                step["content_payload_json"] = _json_object(step.get("content_payload_json"))
                steps.append(step)
            item["steps"] = steps
            segments.append(item)
        status_rows = self.db.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM campaign_members
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (int(campaign_id),),
        ).fetchall() or []
        member_status = {_text(row.get("status")) or "unknown": int(row.get("c") or 0) for row in status_rows}
        return {
            "campaign": campaign,
            "segments": segments,
            "member_status_counts": member_status,
            "total_members": sum(member_status.values()),
        }


def build_external_campaign_repository() -> ExternalCampaignRepository:
    return PostgresExternalCampaignRepository()

