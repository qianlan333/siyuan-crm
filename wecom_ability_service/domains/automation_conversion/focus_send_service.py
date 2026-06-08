from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from . import local_projection
from . import repo
from . import service as automation_service
from .service import (
    FOCUS_SEND_INTERVAL_SECONDS,
    TOUCH_PROGRAM_SIGNUP_CONVERSION,
    TOUCH_SURFACE_FOCUS_SEND,
    _has_existing_touch_delivery,
    _normalized_text,
    _parse_timestamp,
    _serialize_member,
)

FOCUS_SEND_QUEUE_SOURCE_TYPE = "focus_send"
FOCUS_SEND_QUEUE_SOURCE_TABLE = "automation_focus_send_batch"
FOCUS_SEND_QUEUE_HANDLER = "focus_send"
FOCUS_SEND_OPEN_QUEUE_STATUSES = ("waiting_approval", "queued", "claimed")


def _iso_now() -> str:
    """Lazy proxy to service._iso_now so monkeypatch on service._iso_now propagates here."""
    from . import service as _svc
    return _svc._iso_now()


def _focus_send_queue_payload(batch_id: int) -> dict[str, int | str]:
    return {"handler": FOCUS_SEND_QUEUE_HANDLER, "batch_id": int(batch_id)}


def _fetch_open_focus_send_queue_job(batch_id: int) -> dict[str, Any] | None:
    from ..broadcast_jobs import repo as queue_repo

    return queue_repo.fetch_job_by_source(
        source_type=FOCUS_SEND_QUEUE_SOURCE_TYPE,
        source_id=str(int(batch_id)),
        source_table=FOCUS_SEND_QUEUE_SOURCE_TABLE,
        statuses=list(FOCUS_SEND_OPEN_QUEUE_STATUSES),
    )


def get_focus_send_batches_payload(*, limit: int = 20) -> dict[str, Any]:
    batches = [_serialize_focus_send_batch(row) for row in repo.list_recent_focus_send_batches(limit=max(1, int(limit)))]
    return {
        "batches": batches,
    }




def _focus_batch_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "pending": "待执行",
        "running": "执行中",
        "finished": "已完成",
        "cancelled": "已取消",
        "conflict": "冲突",
    }.get(normalized, normalized or "未知")


def _focus_batch_item_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "pending": "待执行",
        "running": "执行中",
        "sent": "已发送",
        "failed": "发送失败",
        "skipped": "已跳过",
        "cancelled": "已取消",
    }.get(normalized, normalized or "未知")

def _serialize_focus_send_batch_item(row: dict[str, Any]) -> dict[str, Any]:
    deserialized = repo.deserialize_focus_send_batch_item_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "batch_id": int(deserialized.get("batch_id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else 0,
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")),
        "phone": _normalized_text(deserialized.get("phone")),
        "position_index": int(deserialized.get("position_index") or 0),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _focus_batch_item_status_label(deserialized.get("status")),
        "detail": _normalized_text(deserialized.get("detail")),
        "result_payload": deserialized.get("result_payload") or {},
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "started_at": _normalized_text(deserialized.get("started_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
    }


def _serialize_focus_send_batch(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_focus_send_batch_row(row)
    total_count = int(deserialized.get("total_count") or 0)
    sent_count = int(deserialized.get("sent_count") or 0)
    failed_count = int(deserialized.get("failed_count") or 0)
    skipped_count = int(deserialized.get("skipped_count") or 0)
    cancelled_count = int(deserialized.get("cancelled_count") or 0)
    remaining_count = max(0, total_count - sent_count - failed_count - skipped_count - cancelled_count)
    return {
        "id": int(deserialized.get("id") or 0),
        "stage_key": _normalized_text(deserialized.get("stage_key")),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "operator_type": _normalized_text(deserialized.get("operator_type")),
        "operator_id": _normalized_text(deserialized.get("operator_id")),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _focus_batch_status_label(deserialized.get("status")),
        "total_count": total_count,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "cancelled_count": cancelled_count,
        "remaining_count": remaining_count,
        "next_run_at": _normalized_text(deserialized.get("next_run_at")),
        "last_run_at": _normalized_text(deserialized.get("last_run_at")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
    }


def _focus_batch_detail_payload(batch_row: dict[str, Any] | None, *, item_limit: int = 12) -> dict[str, Any]:
    serialized_batch = _serialize_focus_send_batch(batch_row)
    if not serialized_batch:
        return {}
    items = [
        _serialize_focus_send_batch_item(row)
        for row in repo.list_focus_send_batch_items(batch_id=int(serialized_batch["id"]), limit=max(1, int(item_limit)), descending=False)
    ]
    return {
        "batch": serialized_batch,
        "items": items[-max(1, int(item_limit)) :],
    }


def create_focus_send_batch(
    *,
    route_key: str,
    operator_id: str = "",
    operator_type: str = "user",
) -> dict[str, Any]:
    definition = local_projection.focus_send_stage_definition(route_key)
    normalized_route_key = _normalized_text(definition.get("route_key")) or _normalized_text(route_key)
    existing = repo.find_active_focus_send_batch_by_stage(_normalized_text(route_key))
    if existing:
        detail = _focus_batch_detail_payload(existing)
        return {
            "ok": True,
            "status": "existing",
            **detail,
        }
    now_text = _iso_now()
    pool_key = _normalized_text(definition.get("pool"))
    members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
    batch = _serialize_focus_send_batch(
        repo.insert_focus_send_batch(
            {
                "stage_key": _normalized_text(route_key),
                "pool_key": pool_key,
                "operator_type": _normalized_text(operator_type) or "user",
                "operator_id": _normalized_text(operator_id) or "crm_console",
                "status": "pending",
                "total_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "cancelled_count": 0,
                "next_run_at": "",
                "last_run_at": "",
                "created_at": now_text,
                "updated_at": now_text,
                "finished_at": "",
            }
        )
    )
    items: list[dict[str, Any]] = []
    skipped_reasons: dict[str, int] = {}
    for member in members:
        external_contact_id = _normalized_text(member.get("external_contact_id"))
        if not external_contact_id:
            skipped_reasons["missing_external_userid"] = int(skipped_reasons.get("missing_external_userid") or 0) + 1
            continue
        if _has_existing_touch_delivery(
            touch_surface=TOUCH_SURFACE_FOCUS_SEND,
            rule_key=normalized_route_key,
            external_contact_id=external_contact_id,
        ):
            skipped_reasons["already_touched"] = int(skipped_reasons.get("already_touched") or 0) + 1
            continue
        delivery = repo.claim_touch_delivery_once(
            {
                "program_code": TOUCH_PROGRAM_SIGNUP_CONVERSION,
                "touch_surface": TOUCH_SURFACE_FOCUS_SEND,
                "rule_key": normalized_route_key,
                "member_id": int(member.get("id") or 0) or None,
                "external_contact_id": external_contact_id,
                "source_batch_id": int(batch.get("id") or 0) or None,
                "detail": "",
                "metadata": {
                    "stage_key": normalized_route_key,
                    "requested_stage_key": _normalized_text(route_key),
                    "pool_key": pool_key,
                    "operator_id": _normalized_text(operator_id),
                },
                "claimed_at": now_text,
                "created_at": now_text,
                "updated_at": now_text,
            }
        )
        if not bool(delivery.get("_did_claim")):
            skipped_reasons["already_touched"] = int(skipped_reasons.get("already_touched") or 0) + 1
            continue
        item = _serialize_focus_send_batch_item(
            repo.insert_focus_send_batch_item(
                {
                    "batch_id": int(batch.get("id") or 0),
                    "member_id": int(member.get("id") or 0) or None,
                    "external_contact_id": external_contact_id,
                    "phone": _normalized_text(member.get("phone")),
                    "position_index": len(items) + 1,
                    "status": "pending",
                    "detail": "",
                    "result_payload": {},
                    "created_at": now_text,
                    "updated_at": now_text,
                    "started_at": "",
                    "finished_at": "",
                }
            )
        )
        repo.update_touch_delivery_log_status(
            int(delivery.get("id") or 0),
            status="claimed",
            source_batch_id=int(batch.get("id") or 0) or None,
            source_item_id=int(item.get("id") or 0) or None,
            detail="",
            metadata={
                "stage_key": normalized_route_key,
                "requested_stage_key": _normalized_text(route_key),
                "pool_key": pool_key,
                "operator_id": _normalized_text(operator_id),
            },
            updated_at=now_text,
        )
        items.append(item)
    skipped_count = sum(int(value or 0) for value in skipped_reasons.values())
    batch = _serialize_focus_send_batch(
        repo.update_focus_send_batch(
            int(batch.get("id") or 0),
            {
                **batch,
                "status": "pending" if items else "finished",
                "total_count": len(items) + skipped_count,
                "skipped_count": skipped_count,
                "next_run_at": now_text if items else "",
                "updated_at": now_text,
                "finished_at": "" if items else now_text,
            },
        )
    )
    get_db().commit()
    if items:
        from ..broadcast_jobs import service as queue_service
        queue_service.enqueue_job(
            source_type=FOCUS_SEND_QUEUE_SOURCE_TYPE,
            source_id=str(batch.get("id") or ""),
            source_table=FOCUS_SEND_QUEUE_SOURCE_TABLE,
            scheduled_for=now_text,
            target_external_userids=[
                _normalized_text(it.get("external_contact_id"))
                for it in items if _normalized_text(it.get("external_contact_id"))
            ],
            target_summary=f"{pool_key} 池 {len(items)} 人",
            content_type="openclaw_push",
            content_payload=_focus_send_queue_payload(int(batch.get("id") or 0)),
            content_summary=f"focus_send/{_normalized_text(route_key)}",
            created_by=_normalized_text(operator_id) or "crm_console",
        )
    return {
        "ok": True,
        "status": "created",
        "batch": batch,
        "items": items,
        "skipped_reasons": skipped_reasons,
    }


def _update_focus_batch_counters(
    batch: dict[str, Any],
    *,
    sent_delta: int = 0,
    failed_delta: int = 0,
    skipped_delta: int = 0,
    status: str = "",
    next_run_at: str = "",
    finished_at: str = "",
    last_run_at: str = "",
) -> dict[str, Any]:
    sent_count = int(batch.get("sent_count") or 0) + int(sent_delta)
    failed_count = int(batch.get("failed_count") or 0) + int(failed_delta)
    skipped_count = int(batch.get("skipped_count") or 0) + int(skipped_delta)
    total_count = int(batch.get("total_count") or 0)
    remaining_count = max(0, total_count - sent_count - failed_count - skipped_count - int(batch.get("cancelled_count") or 0))
    next_status = _normalized_text(status) or ("finished" if remaining_count <= 0 else "running")
    saved = repo.update_focus_send_batch(
        int(batch.get("id") or 0),
        {
            "stage_key": _normalized_text(batch.get("stage_key")),
            "pool_key": _normalized_text(batch.get("pool_key")),
            "operator_type": _normalized_text(batch.get("operator_type")),
            "operator_id": _normalized_text(batch.get("operator_id")),
            "status": next_status,
            "total_count": total_count,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "cancelled_count": int(batch.get("cancelled_count") or 0),
            "next_run_at": _normalized_text(next_run_at),
            "last_run_at": _normalized_text(last_run_at),
            "updated_at": _normalized_text(last_run_at) or _iso_now(),
            "finished_at": _normalized_text(finished_at),
        },
    )
    return _serialize_focus_send_batch(saved)


def _dispatch_focus_send_batch_item(
    *,
    batch_id: int,
    item: dict[str, Any],
    operator_id: str,
    now_text: str,
) -> dict[str, Any]:
    serialized_item = _serialize_focus_send_batch_item(item)
    external_contact_id = _normalized_text(serialized_item.get("external_contact_id"))
    push_result = automation_service.push_openclaw(
        external_contact_id=external_contact_id,
        operator_id=_normalized_text(operator_id),
    )
    accepted = bool(push_result.get("accepted"))
    item_status = "sent" if accepted else "failed"
    failure_detail = "" if accepted else (_normalized_text(push_result.get("error")) or _normalized_text(push_result.get("status")))
    repo.update_focus_send_batch_item(
        int(serialized_item.get("id") or 0),
        {
            **serialized_item,
            "status": item_status,
            "detail": failure_detail,
            "result_payload": dict(push_result or {}),
            "updated_at": now_text,
            "started_at": _normalized_text(serialized_item.get("started_at")) or now_text,
            "finished_at": now_text,
        },
    )
    repo.update_touch_delivery_log_status_by_source(
        touch_surface=TOUCH_SURFACE_FOCUS_SEND,
        source_batch_id=int(batch_id),
        source_item_id=int(serialized_item.get("id") or 0),
        external_contact_id=external_contact_id,
        status=item_status,
        detail=failure_detail,
        metadata=dict(push_result or {}),
        sent_at=now_text if accepted else "",
        updated_at=now_text,
    )
    return {
        "accepted": accepted,
        "item_status": item_status,
        "external_contact_id": external_contact_id,
        "push_result": push_result,
        "item": serialized_item,
    }


def run_due_focus_send_batches(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    limit: int = 20,
) -> dict[str, Any]:
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    processed_count = 0
    batches_payload: list[dict[str, Any]] = []

    for row in repo.list_due_focus_send_batches(due_at=now_text, limit=max(1, int(limit))):
        batch = _serialize_focus_send_batch(row)
        batch_id = int(batch.get("id") or 0)
        existing_job = _fetch_open_focus_send_queue_job(batch_id)
        if existing_job:
            batches_payload.append(
                {
                    **_focus_batch_detail_payload(batch, item_limit=12),
                    "queue_status": "already_queued",
                    "queue_job": {
                        "id": int(existing_job.get("id") or 0),
                        "status": _normalized_text(existing_job.get("status")),
                    },
                }
            )
            continue
        item = repo.claim_next_focus_send_batch_item(batch_id=batch_id, started_at=now_text)
        if not item:
            finalized = _update_focus_batch_counters(
                batch,
                status="finished",
                next_run_at="",
                finished_at=now_text,
                last_run_at=now_text,
            )
            batches_payload.append(_focus_batch_detail_payload(finalized, item_limit=12))
            continue
        item_result = _dispatch_focus_send_batch_item(
            batch_id=batch_id,
            item=item,
            operator_id=_normalized_text(operator_id) or "focus_send_runner",
            now_text=now_text,
        )
        accepted = bool(item_result.get("accepted"))
        processed_count += 1
        refreshed_batch = _update_focus_batch_counters(
            batch,
            sent_delta=1 if accepted else 0,
            failed_delta=0 if accepted else 1,
            next_run_at=(
                ""
                if (int(batch.get("remaining_count") or 0) - 1) <= 0
                else (now_dt + timedelta(seconds=FOCUS_SEND_INTERVAL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
            ),
            finished_at=now_text if (int(batch.get("remaining_count") or 0) - 1) <= 0 else "",
            last_run_at=now_text,
        )
        batches_payload.append(_focus_batch_detail_payload(refreshed_batch, item_limit=12))
    get_db().commit()
    return {
        "ok": True,
        "processed_count": processed_count,
        "batches": batches_payload,
    }


def get_focus_send_batch_detail(*, batch_id: int, item_limit: int = 12) -> dict[str, Any]:
    batch_row = repo.get_focus_send_batch(int(batch_id))
    if not batch_row:
        raise LookupError("focus send batch not found")
    return _focus_batch_detail_payload(batch_row, item_limit=item_limit)


def run_focus_send_job(*, batch_id: int) -> dict[str, Any]:
    """broadcast_jobs handler 调这个：一次性执行整个 focus_send batch（逐 item push_openclaw）。"""
    batch_row = repo.get_focus_send_batch(int(batch_id))
    if not batch_row:
        return {"ok": False, "error": "batch not found", "sent_count": 0, "failed_count": 0}
    batch = _serialize_focus_send_batch(batch_row)
    now_text = _iso_now()
    sent_count = 0
    failed_count = 0
    while True:
        item = repo.claim_next_focus_send_batch_item(batch_id=int(batch_id), started_at=now_text)
        if not item:
            break
        item_result = _dispatch_focus_send_batch_item(
            batch_id=int(batch_id),
            item=item,
            operator_id="broadcast_worker",
            now_text=now_text,
        )
        if bool(item_result.get("accepted")):
            sent_count += 1
        else:
            failed_count += 1
    _update_focus_batch_counters(
        batch,
        sent_delta=sent_count,
        failed_delta=failed_count,
        status="finished",
        next_run_at="",
        finished_at=now_text,
        last_run_at=now_text,
    )
    get_db().commit()
    return {"ok": True, "sent_count": sent_count, "failed_count": failed_count}
