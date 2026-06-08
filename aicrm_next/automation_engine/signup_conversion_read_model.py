from __future__ import annotations

import json
from typing import Any

from aicrm_next.customer_read_model.application import GetCustomerChatContextQuery
from aicrm_next.customer_read_model.dto import CustomerChatContextRequest
from aicrm_next.shared.postgres_connection import get_db


DEFAULT_SCENARIO_KEY = "signup_conversion_v1"
PENDING_DISPATCH_STATUSES = {"pending", "blocked_quiet_hours"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _limit(value: Any, *, default: int = 20, maximum: int = 200) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_load(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row or {})


def _serialize_dispatch_log(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = row.get("dispatch_payload")
    if not isinstance(payload, dict):
        payload = _json_load(row.get("dispatch_payload_json"), {})
    result = dict(row)
    result["dispatch_payload"] = payload if isinstance(payload, dict) else {}
    return result


def _delivery_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = _json_load(row.get("payload_json"), {})
    return {
        "id": _int(row.get("id")),
        "event_type": _text(row.get("event_type")),
        "source_key": _text(row.get("source_key")),
        "source_id": _text(row.get("source_id")),
        "target_url": _text(row.get("target_url")),
        "payload": payload if isinstance(payload, dict) else {},
        "payload_summary": _text(row.get("payload_summary")),
        "token_configured": bool(row.get("token_configured")),
        "status": _text(row.get("status")),
        "attempt_count": _int(row.get("attempt_count")),
        "max_attempts": _int(row.get("max_attempts")),
        "response_status_code": row.get("response_status_code"),
        "response_body_summary": _text(row.get("response_body_summary")),
        "last_error": _text(row.get("last_error")),
        "last_attempted_at": _text(row.get("last_attempted_at")),
        "next_retry_at": _text(row.get("next_retry_at")),
        "created_at": _text(row.get("created_at")),
        "updated_at": _text(row.get("updated_at")),
    }


def _customer_context(external_userid: str) -> dict[str, Any]:
    payload = GetCustomerChatContextQuery()(
        CustomerContextRequest(
            external_userid=external_userid,
            recent_message_limit=20,
            timeline_limit=20,
        )
    )
    return {
        "external_userid": _text(payload.get("external_userid")) or external_userid,
        "customer": payload.get("customer"),
        "recent_messages": list(payload.get("recent_messages") or []),
        "timeline": dict(payload.get("timeline") or {}),
        "recent_timeline_events": list(payload.get("recent_timeline_events") or []),
        "source_status": _text(payload.get("source_status")) or "live",
        "degraded": bool(payload.get("degraded")),
        "warnings": list(payload.get("warnings") or []),
    }


class SignupConversionRepository:
    def list_message_batches(self, *, limit: int, cursor: str) -> dict[str, Any]:
        safe_limit = _limit(limit, maximum=50)
        cursor_id = _int(cursor)
        rows = get_db().execute(
            """
            SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
            FROM message_batches
            WHERE status = 'pending' AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (cursor_id, safe_limit + 1),
        ).fetchall()
        items = [_row_dict(row) for row in rows[:safe_limit]]
        next_cursor = str(items[-1]["id"]) if len(rows) > safe_limit and items else ""
        return {"items": items, "next_cursor": next_cursor}

    def get_message_batch(self, batch_id: int, *, limit: int = 500) -> dict[str, Any] | None:
        batch = get_db().execute(
            """
            SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
            FROM message_batches
            WHERE id = ?
            """,
            (int(batch_id),),
        ).fetchone()
        if not batch:
            return None
        rows = get_db().execute(
            """
            SELECT am.seq, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.sender, am.receiver,
                   am.msgtype, am.content, am.send_time, am.raw_payload, mbi.id AS batch_item_id
            FROM message_batch_items mbi
            JOIN archived_messages am ON am.id = mbi.message_id
            WHERE mbi.batch_id = ?
            ORDER BY mbi.id ASC
            LIMIT ?
            """,
            (int(batch_id), _limit(limit, default=500, maximum=500) + 1),
        ).fetchall()
        return {
            "batch": _row_dict(batch),
            "messages": [_format_message_row(_row_dict(row)) for row in rows[:limit]],
            "paging": {"limit": limit, "cursor": "", "next_cursor": str(rows[limit - 1]["batch_item_id"]) if len(rows) > limit else ""},
        }

    def dispatch_logs(self, batch_id: int) -> list[dict[str, Any]]:
        rows = get_db().execute(
            """
            SELECT *
            FROM conversion_dispatch_log
            WHERE batch_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (int(batch_id),),
        ).fetchall()
        return [_row_dict(row) for row in rows]

    def list_webhook_deliveries(self, *, event_type: str = "", status: str = "", limit: int = 50) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if _text(event_type):
            clauses.append("event_type = ?")
            params.append(_text(event_type))
        if _text(status):
            clauses.append("status = ?")
            params.append(_text(status))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = get_db().execute(
            f"""
            SELECT id, event_type, source_key, source_id, target_url, payload_json, payload_summary,
                   token_configured, status, attempt_count, max_attempts, response_status_code,
                   response_body_summary, last_error, last_attempted_at, next_retry_at, created_at, updated_at
            FROM outbound_webhook_deliveries
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params + [_limit(limit, default=50, maximum=200)]),
        ).fetchall()
        return [_delivery_snapshot(_row_dict(row)) for row in rows]


def _format_message_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = _json_load(row.get("raw_payload"), {})
    decrypted = raw_payload.get("decrypted_message") if isinstance(raw_payload, dict) else {}
    decrypted = decrypted if isinstance(decrypted, dict) else {}
    tolist = decrypted.get("tolist") or []
    if isinstance(tolist, str):
        tolist = [tolist]
    chat_id = _text(decrypted.get("roomid"))
    return {
        "seq": row.get("seq"),
        "msgid": _text(row.get("msgid")),
        "chat_type": _text(row.get("chat_type")) or ("group" if chat_id else ("private" if len(tolist) == 1 else "group")),
        "external_userid": _text(row.get("external_userid")),
        "owner_userid": _text(row.get("owner_userid")),
        "sender": _text(row.get("sender")),
        "from": _text(decrypted.get("from")) or _text(row.get("sender")),
        "tolist": tolist,
        "roomid": chat_id,
        "chat_id": chat_id,
        "group_name": "",
        "msgtype": _text(row.get("msgtype")),
        "content": _text(row.get("content")),
        "send_time": _text(row.get("send_time")),
    }


class SignupConversionReadModel:
    def __init__(self, repo: SignupConversionRepository | None = None) -> None:
        self.repo = repo or SignupConversionRepository()

    def list_batches(self, *, limit: int = 20, cursor: str = "") -> dict[str, Any]:
        safe_limit = _limit(limit, maximum=50)
        page = self.repo.list_message_batches(limit=safe_limit, cursor=cursor)
        items: list[dict[str, Any]] = []
        for batch in page.get("items") or []:
            detail = self.batch_detail(_int(batch.get("id")), include_customer_context=False)
            if not detail:
                continue
            candidate_count = _int(detail.get("candidate_count"))
            blocked_count = _int(detail.get("blocked_count"))
            if candidate_count <= 0 and blocked_count <= 0:
                continue
            items.append(
                {
                    "id": _int(batch.get("id")),
                    "status": _text(batch.get("status")),
                    "window_start": _text(batch.get("window_start")),
                    "window_end": _text(batch.get("window_end")),
                    "message_count": _int(batch.get("message_count")),
                    "candidate_count": candidate_count,
                    "blocked_count": blocked_count,
                    "skipped_count": _int(detail.get("skipped_count")),
                    "candidates_preview": [
                        {
                            "external_userid": _text(candidate.get("external_userid")),
                            "customer_name": _text(candidate.get("customer_name")),
                            "owner_userid": _text(candidate.get("owner_userid")),
                            "current_stage": _text(candidate.get("current_stage")),
                            "marketing_phase": _text(((candidate.get("marketing_profile") or {}).get("marketing_state") or {}).get("marketing_phase")),
                            "value_segment": _text(candidate.get("current_segment")),
                            "score": _int(((candidate.get("dispatch_log") or {}).get("dispatch_payload") or {}).get("hit_count")),
                            "dispatch_status": _text(candidate.get("dispatch_status")),
                        }
                        for candidate in detail.get("candidates") or []
                    ],
                }
            )
        return {
            "scenario_key": DEFAULT_SCENARIO_KEY,
            "items": items,
            "count": len(items),
            "filters": {"limit": str(safe_limit), "cursor": _text(cursor)},
            "source_cursor": _text(page.get("next_cursor")),
            "next_cursor": _text(page.get("next_cursor")),
        }

    def batch_detail(self, batch_id: int, *, include_customer_context: bool = True) -> dict[str, Any] | None:
        payload = self.repo.get_message_batch(batch_id)
        if not payload:
            return None
        logs = [_serialize_dispatch_log(row) for row in self.repo.dispatch_logs(batch_id)]
        candidates: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        blocked_count = 0
        for log in logs:
            external_userid = _text(log.get("external_userid"))
            status = _text(log.get("dispatch_status"))
            if not external_userid:
                continue
            if status not in PENDING_DISPATCH_STATUSES:
                reason = "already_dispatched"
                if status == "acked":
                    reason = "already_acked"
                elif status in {"cancelled", "converted_before_dispatch"}:
                    reason = status
                skipped.append({"external_userid": external_userid, "reason": reason, "dispatch_status": status})
                continue
            if status == "blocked_quiet_hours":
                blocked_count += 1
                skipped.append({"external_userid": external_userid, "reason": "blocked_quiet_hours", "dispatch_status": status})
                continue
            payload_json = log.get("dispatch_payload") if isinstance(log.get("dispatch_payload"), dict) else {}
            customer_context = _customer_context(external_userid) if include_customer_context else {}
            customer = dict((customer_context.get("customer") or {}) if isinstance(customer_context, dict) else {})
            candidate = {
                "external_userid": external_userid,
                "customer_name": _text(customer.get("display_name") or customer.get("customer_name")) or external_userid,
                "owner_userid": _text(customer.get("owner_userid")),
                "marketing_profile": {
                    "marketing_state": {
                        "stage_key": _text(payload_json.get("current_stage")),
                        "marketing_phase": _text(payload_json.get("main_stage")),
                    },
                    "value_segment": {
                        "value_segment": _text(payload_json.get("current_segment")),
                        "is_core": _text(payload_json.get("current_segment")) == "focus",
                    },
                },
                "current_stage": _text(payload_json.get("current_stage")),
                "current_segment": _text(payload_json.get("current_segment")),
                "eligible_for_conversion": bool(payload_json.get("eligible_for_conversion")),
                "dispatch_status": status,
                "dispatch_log": log,
                "trigger_reason": "pending_text_message_batch",
                "latest_customer_message_at": _text(payload_json.get("latest_customer_message_at")),
                "candidate_messages": [],
                "candidate_message_count": 0,
            }
            if include_customer_context:
                candidate["customer_context"] = customer_context
            candidates.append(candidate)
        return {
            "scenario_key": DEFAULT_SCENARIO_KEY,
            "batch": payload.get("batch") or {},
            "messages": payload.get("messages") or [],
            "paging": payload.get("paging") or {},
            "candidates": candidates,
            "candidate_count": len(candidates),
            "blocked_count": blocked_count,
            "quiet_hours_blocked": blocked_count > 0,
            "skipped_customers": skipped,
            "skipped_count": len(skipped),
        }

    def list_webhook_deliveries(self, *, event_type: str = "", status: str = "", limit: int = 50) -> dict[str, Any]:
        safe_limit = _limit(limit, default=50, maximum=200)
        items = self.repo.list_webhook_deliveries(event_type=event_type, status=status, limit=safe_limit)
        return {
            "items": items,
            "count": len(items),
            "filters": {"event_type": _text(event_type), "status": _text(status), "limit": safe_limit},
        }
