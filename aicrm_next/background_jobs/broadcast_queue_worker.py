from __future__ import annotations

import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from aicrm_next.platform_foundation.external_effects.execution_gates import (
    WECOM_EXECUTION_DISABLED_CODE,
    explicit_wecom_execution_disabled,
    wecom_execution_disabled_message,
)
from aicrm_next.shared.runtime_settings import runtime_setting

from .db import connect, has_database_url, int_value, json_list, utcnow


class BroadcastDispatcher(Protocol):
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]: ...


class BroadcastQueueRepository(Protocol):
    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]: ...
    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0, claim_token: str = "") -> None: ...
    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error", claim_token: str = "") -> None: ...


class SafeSkippedBroadcastDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = _json_dict(job.get("content_payload"))
        if _is_wecom_private_job(job, payload):
            return _dispatch_wecom_private(job, payload)
        if _is_wecom_customer_group_job(job, payload):
            return _dispatch_wecom_customer_group(job, payload)
        return {
            "ok": False,
            "status": "skipped",
            "reason": "next_native_dispatcher_missing",
            "source_type": str(job.get("source_type") or ""),
            "source_table": str(job.get("source_table") or ""),
            "content_type": str(job.get("content_type") or ""),
            "channel": str(job.get("channel") or ""),
            "target_kind": str(job.get("target_kind") or ""),
            "payload_channel": str(payload.get("channel") or ""),
        }


class PostgresBroadcastQueueRepository:
    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                """
                WITH due AS (
                    SELECT id
                    FROM broadcast_jobs
                    WHERE scheduled_for <= %s
                      AND (
                        status = 'queued'
                        OR (
                            status = 'claimed'
                            AND lease_expires_at IS NOT NULL
                            AND lease_expires_at <= %s
                        )
                        OR (
                            status = 'failed_retryable'
                            AND (next_retry_at IS NULL OR next_retry_at <= %s)
                        )
                      )
                    ORDER BY priority ASC, scheduled_for ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE broadcast_jobs bj
                SET status = 'claimed',
                    claimed_at = %s,
                    claim_token = %s,
                    lease_expires_at = %s,
                    attempt_count = attempt_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                FROM due
                WHERE bj.id = due.id
                RETURNING bj.*
                """,
                (now, now, now, int(limit), now, claim_token, now + timedelta(seconds=int(lease_seconds))),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0, claim_token: str = "") -> None:
        token = str(claim_token or "")
        with connect() as conn:
            conn.execute(
                """
                UPDATE broadcast_jobs
                SET status = 'sent',
                    outbound_task_id = %s,
                    sent_count = %s,
                    failed_count = %s,
                    claim_token = '',
                    lease_expires_at = NULL,
                    next_retry_at = NULL,
                    sent_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND (%s = '' OR claim_token = %s)
                """,
                (outbound_task_id, int(sent_count), int(failed_count), int(job_id), token, token),
            )

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error", claim_token: str = "") -> None:
        error_text = str(error or "")[:1000]
        token = str(claim_token or "")
        terminal_failure = failure_type in {"identity_external_userid_missing", "invalid_payload", "cancelled"}
        retry_delay_seconds = int(os.getenv("BROADCAST_QUEUE_RETRY_DELAY_SECONDS", "300"))
        with connect() as conn:
            conn.execute(
                """
                UPDATE broadcast_jobs
                SET status = CASE
                        WHEN %s THEN 'blocked'
                        WHEN attempt_count >= COALESCE(max_attempts, 3) THEN 'failed_terminal'
                        ELSE 'failed_retryable'
                    END,
                    failure_type = %s,
                    last_error = %s,
                    claim_token = '',
                    lease_expires_at = NULL,
                    next_retry_at = CASE
                        WHEN %s OR attempt_count >= COALESCE(max_attempts, 3) THEN NULL
                        ELSE CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND (%s = '' OR claim_token = %s)
                """,
                (terminal_failure, failure_type, error_text, terminal_failure, retry_delay_seconds, int(job_id), token, token),
            )
            conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipients r
                SET send_status = 'failed',
                    last_error = %s,
                    updated_at = CURRENT_TIMESTAMP
                FROM broadcast_jobs j
                WHERE j.id = %s
                  AND j.source_type = 'cloud_plan'
                  AND j.source_table = 'cloud_broadcast_plan_recipients'
                  AND (%s = '' OR j.claim_token = %s)
                  AND r.broadcast_job_id = j.id
                  AND r.send_status IN ('pending', 'queued', 'sending')
                """,
                (error_text, int(job_id), token, token),
            )
            conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipient_messages m
                SET status = 'failed',
                    last_error = %s,
                    updated_at = CURRENT_TIMESTAMP
                FROM cloud_broadcast_plan_recipients r
                JOIN broadcast_jobs j ON j.id = r.broadcast_job_id
                WHERE j.id = %s
                  AND j.source_type = 'cloud_plan'
                  AND j.source_table = 'cloud_broadcast_plan_recipients'
                  AND (%s = '' OR j.claim_token = %s)
                  AND m.plan_id = r.plan_id
                  AND m.recipient_id = r.id
                  AND m.status IN ('pending', 'queued')
                """,
                (error_text, int(job_id), token, token),
            )
            conn.execute(
                """
                UPDATE broadcast_jobs
                SET claim_token = '',
                    lease_expires_at = NULL
                WHERE id = %s
                  AND (%s = '' OR claim_token = %s)
                """,
                (int(job_id), token, token),
            )


def _summary(*, limit: int, dry_run: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "job": "broadcast_queue_worker",
        "limit": int(limit),
        "dry_run": bool(dry_run),
        "scanned_at": utcnow().isoformat(),
        "claimed": 0,
        "sent_ok": 0,
        "sent_failed": 0,
        "skipped": 0,
        "results": [],
        "errors": [],
    }


def _count_targets(job: dict[str, Any]) -> int:
    return len(json_list(job.get("target_unionids_json"))) or int_value(job.get("target_count"))


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_wecom_customer_group_job(job: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("channel") or "").strip() == "wecom_customer_group"
        or str(job.get("content_type") or "").strip() == "wecom_customer_group"
        or str(job.get("channel") or "").strip() == "wecom_customer_group"
    )


def _is_wecom_private_job(job: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        _text(payload.get("channel")) == "wecom_private"
        or _text(job.get("channel")) == "wecom_private"
        or (
            _text(job.get("source_type")) == "campaign"
            and _text(job.get("source_table")) == "campaign_members"
            and _text(job.get("content_type")) == "private_message"
        )
    )


def _record_outbound_task(
    *,
    job: dict[str, Any],
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    status: str,
    task_type: str = "broadcast_job/group_ops",
) -> int | None:
    task_id = str(
        response_payload.get("wecom_msgid")
        or response_payload.get("msgid")
        or _json_dict(response_payload.get("result")).get("msgid")
        or _json_dict(response_payload.get("result")).get("task_id")
        or ""
    )
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                task_type,
                _json_dumps(request_payload),
                _json_dumps(response_payload),
                task_id,
                status,
                str(job.get("trace_id") or ""),
            ),
        ).fetchone()
    return int((row or {}).get("id") or 0) or None


def _extract_target_unionids(job: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    values = _json_list(job.get("target_unionids_json")) or _json_list(payload.get("target_unionids"))
    return [_text(item) for item in values if _text(item)]


def _resolve_private_targets_by_unionid(unionids: list[str]) -> tuple[list[str], list[str]]:
    unique_unionids = []
    for unionid in unionids:
        if unionid and unionid not in unique_unionids:
            unique_unionids.append(unionid)
    if not unique_unionids:
        return [], []
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT unionid, primary_external_userid
            FROM crm_user_identity
            WHERE unionid = ANY(%s)
              AND COALESCE(primary_external_userid, '') <> ''
            """,
            (unique_unionids,),
        ).fetchall()
    by_unionid = {_text(dict(row).get("unionid")): _text(dict(row).get("primary_external_userid")) for row in rows}
    targets = [by_unionid[unionid] for unionid in unique_unionids if by_unionid.get(unionid)]
    missing = [unionid for unionid in unique_unionids if not by_unionid.get(unionid)]
    return targets, missing


def _extract_private_text(payload: dict[str, Any]) -> str:
    rendered = payload.get("rendered_content") if isinstance(payload.get("rendered_content"), dict) else {}
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    return _text(
        rendered.get("content_text")
        or rendered.get("text")
        or payload.get("content_text")
        or payload.get("text")
        or step.get("content_text")
    )


def _configured_wecom_sender(fallback: str = "") -> str:
    raw = runtime_setting("AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS", "")
    candidates = [
        item.strip()
        for item in raw.replace("\n", ",").replace(" ", ",").split(",")
        if item.strip()
    ]
    return candidates[0] if candidates else _text(fallback)


def _extract_private_sender(payload: dict[str, Any]) -> str:
    campaign = payload.get("campaign") if isinstance(payload.get("campaign"), dict) else {}
    fallback = _text(payload.get("sender_userid") or payload.get("owner_userid") or campaign.get("owner_userid"))
    return _configured_wecom_sender(fallback)


def _load_cloud_plan_recipient_message(payload: dict[str, Any]) -> dict[str, Any]:
    if _text(payload.get("message_mode")) != "recipient_messages":
        return {}
    plan_id = _text(payload.get("plan_id"))
    recipient_id = int_value(payload.get("recipient_id"))
    if not plan_id or not recipient_id:
        return {}
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, recipient_id, content_text, content_payload_json, attachments_json
            FROM cloud_broadcast_plan_recipient_messages
            WHERE plan_id = %s
              AND recipient_id = %s
              AND status IN ('queued', 'pending')
            ORDER BY sequence_index ASC, id ASC
            LIMIT 1
            """,
            (plan_id, recipient_id),
        ).fetchone()
    if not row:
        return {}
    return {
        "cloud_plan_message_id": int_value(row.get("id")),
        "content_text": _text(row.get("content_text")),
        "content_payload_json": _json_dict(row.get("content_payload_json")),
        "attachments": _json_list(row.get("attachments_json")),
    }


def _with_cloud_plan_recipient_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = _load_cloud_plan_recipient_message(payload)
    if not message:
        return payload
    hydrated = dict(payload)
    if message.get("content_text"):
        hydrated["content_text"] = message.get("content_text")
    if message.get("content_payload_json"):
        hydrated["content_payload_json"] = message.get("content_payload_json")
    if message.get("attachments"):
        hydrated["attachments"] = message.get("attachments")
    if message.get("cloud_plan_message_id"):
        hydrated["cloud_plan_message_id"] = message.get("cloud_plan_message_id")
    return hydrated


def _mark_cloud_plan_recipient_message_sent(payload: dict[str, Any], *, outbound_task_id: int | None) -> None:
    message_id = int_value(payload.get("cloud_plan_message_id"))
    recipient_id = int_value(payload.get("recipient_id"))
    if not message_id or not recipient_id:
        return
    with connect() as conn:
        conn.execute(
            """
            UPDATE cloud_broadcast_plan_recipient_messages
            SET status = 'sent', sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (message_id,),
        )
        conn.execute(
            """
            UPDATE cloud_broadcast_plan_recipients
            SET send_status = 'sent', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (recipient_id,),
        )


def _merge_content_package(target: dict[str, Any], source: Any) -> None:
    source_dict = _json_dict(source)
    if not source_dict:
        return
    for nested_key in ("content_payload_json", "content_package_json", "content_package", "attachments"):
        nested = _json_dict(source_dict.get(nested_key))
        if nested:
            _merge_content_package(target, nested)
    for key in ("image_library_ids", "miniprogram_library_ids", "attachment_library_ids"):
        values = _json_list(source_dict.get(key))
        if values:
            existing = list(target.get(key) or [])
            for value in values:
                if value not in existing:
                    existing.append(value)
            target[key] = existing


def _extract_private_content_package(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = payload.get("rendered_content") if isinstance(payload.get("rendered_content"), dict) else {}
    step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
    content_package: dict[str, Any] = {}
    for source in (payload, rendered, step):
        _merge_content_package(content_package, source)
    return content_package


def _resolve_private_attachments(content_package: dict[str, Any]) -> list[dict[str, Any]]:
    if not any(_json_list(content_package.get(key)) for key in ("image_library_ids", "miniprogram_library_ids", "attachment_library_ids")):
        return []
    from aicrm_next.automation_engine.group_ops.integration_gateway import resolve_group_ops_content_package_materials

    attachments, image_media_ids = resolve_group_ops_content_package_materials(content_package)
    image_attachments = [{"msgtype": "image", "image": {"media_id": media_id}} for media_id in image_media_ids if _text(media_id)]
    return list(attachments or []) + image_attachments


def _normalize_private_attachments_for_wecom(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not attachments:
        return []
    from aicrm_next.automation_engine.group_ops.message_content import normalize_miniprogram_attachment_payload

    normalized: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        msgtype = _text(item.get("msgtype")).lower()
        if msgtype != "miniprogram":
            normalized.append(dict(item))
            continue
        payload = item.get("miniprogram") if isinstance(item.get("miniprogram"), dict) else {}
        normalized.append({"msgtype": "miniprogram", "miniprogram": normalize_miniprogram_attachment_payload(payload)})
    return normalized


def _dispatch_wecom_private(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from aicrm_next.integration_gateway.wecom_private_adapter import build_wecom_private_message_adapter

    if explicit_wecom_execution_disabled():
        return {
            "ok": False,
            "error": wecom_execution_disabled_message(),
            "failure_type": WECOM_EXECUTION_DISABLED_CODE,
            "side_effect_executed": False,
        }
    payload = _with_cloud_plan_recipient_message(payload)
    target_unionids = _extract_target_unionids(job, payload)
    targets, missing_unionids = _resolve_private_targets_by_unionid(target_unionids)
    target_count = int_value(job.get("target_count"))
    sender_userid = _extract_private_sender(payload)
    content_text = _extract_private_text(payload)
    if not target_unionids:
        return {"ok": False, "error": "target_unionids_missing", "failure_type": "validation_failed"}
    if missing_unionids:
        return {
            "ok": False,
            "error": "identity_external_userid_missing",
            "failure_type": "identity_external_userid_missing",
            "missing_unionids": missing_unionids,
        }
    if target_count != len(target_unionids):
        return {"ok": False, "error": "target_count_mismatch", "failure_type": "validation_failed"}
    if not sender_userid:
        return {"ok": False, "error": "sender_userid_missing", "failure_type": "validation_failed"}
    content_package = _extract_private_content_package(payload)
    try:
        attachments = _resolve_private_attachments(content_package)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "failure_type": "material_resolve_failed"}
    try:
        attachments = _normalize_private_attachments_for_wecom(attachments)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "failure_type": "material_resolve_failed"}
    direct_attachments = _json_list(payload.get("attachments")) or _json_list(payload.get("attachments_json"))
    if direct_attachments:
        attachments = direct_attachments + attachments
    if not content_text and not attachments:
        return {"ok": False, "error": "content_text_or_attachment_missing", "failure_type": "validation_failed"}
    request_payload = {
        "job_id": int_value(job.get("id")),
        "source_type": _text(job.get("source_type")),
        "source_id": _text(job.get("source_id")),
        "sender_userid": sender_userid,
        "target_unionids": target_unionids,
        "external_userids": targets,
        "content_hash": _json_dict(payload.get("rendered_content")).get("content_hash") or "",
        "content_preview": content_text[:120],
    }
    if content_text:
        request_payload["text"] = {"content": content_text}
    if attachments:
        request_payload["attachments"] = attachments
    adapter_payload = {"sender": sender_userid, "external_userids": targets}
    if content_text:
        adapter_payload["text"] = {"content": content_text}
    if attachments:
        adapter_payload["attachments"] = attachments
    result = build_wecom_private_message_adapter().create_private_message_task(
        adapter_payload,
        idempotency_key=_text(job.get("idempotency_key") or job.get("trace_id") or job.get("id")),
    )
    failure_type = _text(result.get("error_code")) or "handler_error"
    outbound_task_id = _record_outbound_task(
        job=job,
        request_payload=request_payload,
        response_payload=result,
        status="created" if result.get("ok") else "failed",
        task_type="broadcast_job/wecom_private",
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": _text(result.get("error_message") or result.get("error_code") or "wecom private message dispatch failed"),
            "failure_type": failure_type,
            "outbound_task_id": outbound_task_id,
        }
    if not outbound_task_id:
        return {"ok": False, "error": "outbound_task_record_missing", "failure_type": "handler_error"}
    _mark_cloud_plan_recipient_message_sent(payload, outbound_task_id=outbound_task_id)
    return {
        "ok": True,
        "sent_count": len(targets),
        "failed_count": 0,
        "outbound_task_id": outbound_task_id,
        "wecom_msgid": _text(result.get("wecom_msgid") or _json_dict(result.get("result")).get("msgid")),
    }


def _dispatch_wecom_customer_group(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from aicrm_next.integration_gateway.wecom_group_adapter import build_wecom_group_message_adapter

    if explicit_wecom_execution_disabled():
        return {
            "ok": False,
            "error": wecom_execution_disabled_message(),
            "failure_type": WECOM_EXECUTION_DISABLED_CODE,
            "side_effect_executed": False,
        }
    existing_outbound_task_id = int_value(job.get("outbound_task_id"))
    if existing_outbound_task_id:
        return {
            "ok": True,
            "sent_count": len(list(payload.get("chat_ids") or [])),
            "failed_count": 0,
            "outbound_task_id": existing_outbound_task_id,
        }
    result = build_wecom_group_message_adapter().create_group_message_task(
        payload,
        idempotency_key=str(job.get("idempotency_key") or job.get("trace_id") or job.get("id") or ""),
    )
    if result.get("ok") and result.get("exact_target_verified") is not True:
        chats = ",".join([str(item) for item in list(result.get("requested_chat_ids") or payload.get("chat_ids") or [])])
        return {"ok": False, "error": f"exact target not verified for requested chat ids: {chats}"}
    outbound_task_id = _record_outbound_task(
        job=job,
        request_payload=payload,
        response_payload=result,
        status="created" if result.get("ok") else "failed",
    )
    if not result.get("ok"):
        error = str(result.get("error_message") or result.get("error_code") or "wecom group message dispatch failed")
        return {"ok": False, "error": error, "outbound_task_id": outbound_task_id}
    return {
        "ok": True,
        "sent_count": len(list(payload.get("chat_ids") or [])),
        "failed_count": 0,
        "outbound_task_id": outbound_task_id,
    }


def run_broadcast_queue_worker(
    *,
    limit: int = 50,
    dry_run: bool = False,
    repo: BroadcastQueueRepository | None = None,
    dispatcher: BroadcastDispatcher | None = None,
    now: datetime | None = None,
    lease_seconds: int | None = None,
) -> dict[str, Any]:
    summary = _summary(limit=limit, dry_run=dry_run)
    if int(limit) <= 0:
        return {**summary, "ok": False, "errors": [{"code": "invalid_limit", "message": "limit must be >= 1"}]}
    if dry_run and repo is None:
        return {**summary, "status": "skipped", "skipped": 1, "skipped_components": [{"component": "postgres_repository", "status": "skipped", "reason": "dry_run"}]}
    if repo is None and not has_database_url():
        return {**summary, "ok": False, "errors": [{"code": "database_url_missing", "message": "DATABASE_URL is required"}]}

    repo = repo or PostgresBroadcastQueueRepository()
    dispatcher = dispatcher or SafeSkippedBroadcastDispatcher()
    current_time = now or utcnow()
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    lease = int(lease_seconds or int(os.getenv("BROADCAST_QUEUE_LEASE_SECONDS", "900")))
    try:
        claim_token = f"{os.getpid()}:{uuid.uuid4().hex}"
        jobs = repo.claim_due_jobs(limit=int(limit), now=current_time, claim_token=claim_token, lease_seconds=lease)
        summary["claimed"] = len(jobs)
        for job in jobs:
            job_id = int(job.get("id") or 0)
            try:
                outcome = dispatcher.dispatch(job)
                if outcome.get("ok"):
                    sent_count = int_value(outcome.get("sent_count")) or _count_targets(job)
                    repo.mark_sent(
                        job_id,
                        outbound_task_id=outcome.get("outbound_task_id") or outcome.get("task_id"),
                        sent_count=sent_count,
                        failed_count=int_value(outcome.get("failed_count")),
                        claim_token=claim_token,
                    )
                    summary["sent_ok"] += 1
                    summary["results"].append({"id": job_id, "status": "sent", "sent_count": sent_count})
                    continue
                reason = str(outcome.get("reason") or outcome.get("error") or "next_native_dispatch_failed")
                failure_type = str(outcome.get("failure_type") or ("next_native_dispatch_skipped" if outcome.get("status") == "skipped" else "handler_error"))
                repo.mark_failed(job_id, error=reason, failure_type=failure_type, claim_token=claim_token)
                summary["sent_failed"] += 1
                if outcome.get("status") == "skipped":
                    summary["skipped"] += 1
                summary["results"].append({"id": job_id, "status": outcome.get("status") or "failed_retryable", "reason": reason, "failure_type": failure_type})
            except Exception as exc:
                reason = str(exc)
                repo.mark_failed(job_id, error=reason, failure_type="handler_exception", claim_token=claim_token)
                summary["sent_failed"] += 1
                summary["results"].append({"id": job_id, "status": "failed_retryable", "reason": reason, "failure_type": "handler_exception"})
        return summary
    except Exception as exc:
        return {**summary, "ok": False, "errors": [{"code": "broadcast_queue_worker_failed", "message": str(exc)}]}
