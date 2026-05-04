from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...db import get_db
from . import repo
from .message_activity_client import get_message_activity_db_status, query_message_activity_counts
from .service import (
    ACTIVE_FOCUS_MESSAGE_THRESHOLD,
    ACTIVE_MESSAGE_MIN_THRESHOLD,
    DECISION_SOURCE_SYSTEM,
    FOLLOWUP_FOCUS,
    FOLLOWUP_NORMAL,
    MESSAGE_ACTIVITY_SYNC_POOLS,
    MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED,
    POOL_OPERATING,
    POOL_PENDING_QUESTIONNAIRE,
    QUESTIONNAIRE_PENDING,
    QUESTIONNAIRE_SUBMITTED,
    _channel_status_is_generated,
    _default_channel_field_statuses,
    _dispatch_reply_monitor_queue_item,
    _effective_channel_entry_tag_payload,
    _inactive_follow_type_from_member,
    _member_snapshot,
    _normalized_text,
    _persist_member,
    _phone_last4,
    _phone_match_key,
    _phone_prefix3,
    _pool_label,
    _reply_monitor_status_payload,
    _resolve_channel_entry_tag_payload,
    _serialize_member,
    _serialize_reply_monitor_queue_item,
    _substantive_member_changed,
)



def _iso_now() -> str:
    """Lazy proxy to service._iso_now so monkeypatch on service._iso_now propagates here."""
    from . import service as _svc
    return _svc._iso_now()


def _message_activity_pool(*, questionnaire_status: str) -> str:
    return POOL_OPERATING if _normalized_text(questionnaire_status) == QUESTIONNAIRE_SUBMITTED else POOL_PENDING_QUESTIONNAIRE

def _message_activity_item_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "updated": "已更新",
        "unchanged": "无变化",
        "skipped_ambiguous": "匹配键冲突跳过",
        "skipped_unmatched": "未匹配跳过",
        "skipped_missing_phone": "手机号缺失跳过",
    }.get(normalized, normalized or "未知")


def _message_activity_sync_run_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "success": "成功",
        "failed": "失败",
        "running": "执行中",
    }.get(normalized, normalized or "暂无记录")


def _serialize_message_activity_sync_item(row: dict[str, Any]) -> dict[str, Any]:
    deserialized = repo.deserialize_message_activity_sync_item_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "run_id": int(deserialized.get("run_id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else 0,
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")),
        "phone": _normalized_text(deserialized.get("phone")),
        "phone_prefix3": _normalized_text(deserialized.get("phone_prefix3")),
        "phone_last4": _normalized_text(deserialized.get("phone_last4")),
        "phone_match_key": _normalized_text(deserialized.get("phone_match_key")),
        "message_count": int(deserialized.get("message_count") or 0),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _message_activity_item_status_label(deserialized.get("status")),
        "detail": _normalized_text(deserialized.get("detail")),
        "before_snapshot": deserialized.get("before_snapshot") or {},
        "after_snapshot": deserialized.get("after_snapshot") or {},
        "created_at": _normalized_text(deserialized.get("created_at")),
    }


def _serialize_message_activity_sync_run(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_message_activity_sync_run_row(row)
    summary = dict(deserialized.get("summary_json") or {})
    skipped_ambiguous_count = int(deserialized.get("skipped_ambiguous_count") or 0)
    skipped_unmatched_count = int(deserialized.get("skipped_unmatched_count") or 0)
    skipped_missing_phone_count = int(deserialized.get("skipped_missing_phone_count") or 0)
    return {
        "id": int(deserialized.get("id") or 0),
        "trigger_source": _normalized_text(deserialized.get("trigger_source")),
        "operator_type": _normalized_text(deserialized.get("operator_type")),
        "operator_id": _normalized_text(deserialized.get("operator_id")),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _message_activity_sync_run_status_label(deserialized.get("status")),
        "candidate_count": int(deserialized.get("candidate_count") or 0),
        "matched_count": int(deserialized.get("matched_count") or 0),
        "updated_count": int(deserialized.get("updated_count") or 0),
        "skipped_ambiguous_count": skipped_ambiguous_count,
        "skipped_unmatched_count": skipped_unmatched_count,
        "skipped_missing_phone_count": skipped_missing_phone_count,
        "skipped_count": skipped_ambiguous_count + skipped_unmatched_count + skipped_missing_phone_count,
        "focus_count": int(deserialized.get("focus_count") or 0),
        "normal_count": int(deserialized.get("normal_count") or 0),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "started_at": _normalized_text(deserialized.get("started_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
        "summary": summary,
    }



def _message_activity_sync_status_payload() -> dict[str, Any]:
    db_status = get_message_activity_db_status()
    last_run_row = repo.get_latest_message_activity_sync_run()
    last_run = _serialize_message_activity_sync_run(last_run_row)
    if (
        not db_status["configured"]
        and _normalized_text(last_run.get("error_message")) == "message activity db is not configured"
    ):
        last_run = {
            **last_run,
            "status": "not_configured",
            "status_label": _message_activity_sync_run_status_label("not_configured"),
            "finished_at": "",
            "error_message": "",
        }
    recent_items = (
        [_serialize_message_activity_sync_item(item) for item in repo.list_message_activity_sync_items(run_id=int(last_run["id"]), limit=12)]
        if last_run
        else []
    )
    return {
        "db_status": db_status,
        "scope_pools": [
            {"pool": pool, "label": _pool_label(pool)}
            for pool in MESSAGE_ACTIVITY_SYNC_POOLS
        ],
        "cron_script_path": _normalized_text(current_app.config.get("MESSAGE_ACTIVITY_SYNC_CRON_SCRIPT_PATH")),
        "last_run": last_run,
        "recent_items": recent_items,
    }



# --- Reply monitor functions moved to reply_monitor_service.py ---
from .reply_monitor_service import (  # noqa: E402
    _dispatch_reply_monitor_queue_item,
    _reply_monitor_status_payload,
    _serialize_reply_monitor_queue_item,
    run_due_reply_monitor,
    run_reply_monitor_capture,
    run_router_test_dispatch,
    save_reply_monitor_enabled,
)





# --- Channel functions moved to channel_service.py ---
from .channel_service import (  # noqa: E402
    _channel_status_is_generated,
    _default_channel_field_statuses,
    _effective_channel_entry_tag_payload,
    _resolve_channel_entry_tag_payload,
    generate_default_channel_qr,
    get_default_channel_settings_payload,
    save_default_channel_settings,
)

def run_message_activity_sync(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    trigger_source: str = MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED,
    current_pools: tuple[str, ...] = MESSAGE_ACTIVITY_SYNC_POOLS,
) -> dict[str, Any]:
    db = get_db()
    db_status = get_message_activity_db_status()
    if not db_status["configured"]:
        return {
            "ok": False,
            "status": "not_configured",
            "error": "message activity db is not configured",
            "missing_keys": list(db_status.get("missing_keys") or []),
            "run": {},
        }
    started_at = _iso_now()
    normalized_trigger_source = _normalized_text(trigger_source) or MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED
    normalized_operator_type = _normalized_text(operator_type) or "system"
    normalized_operator_id = _normalized_text(operator_id) or ("cron" if normalized_operator_type == "system" else "crm_console")
    base_run_payload = {
        "trigger_source": normalized_trigger_source,
        "operator_type": normalized_operator_type,
        "operator_id": normalized_operator_id,
        "status": "running",
        "candidate_count": 0,
        "matched_count": 0,
        "updated_count": 0,
        "skipped_ambiguous_count": 0,
        "skipped_unmatched_count": 0,
        "skipped_missing_phone_count": 0,
        "focus_count": 0,
        "normal_count": 0,
        "error_message": "",
        "summary_json": {},
        "started_at": started_at,
        "finished_at": started_at,
    }
    run_row = repo.insert_message_activity_sync_run(base_run_payload)
    db.commit()
    run_id = int(run_row.get("id") or 0)
    counters = {
        "candidate_count": 0,
        "matched_count": 0,
        "updated_count": 0,
        "skipped_ambiguous_count": 0,
        "skipped_unmatched_count": 0,
        "skipped_missing_phone_count": 0,
        "focus_count": 0,
        "normal_count": 0,
    }
    summary: dict[str, Any] = {
        "candidate_pools": list(current_pools),
        "message_source_rows": 0,
        "active_focus_message_threshold": ACTIVE_FOCUS_MESSAGE_THRESHOLD,
        "active_message_min_threshold": ACTIVE_MESSAGE_MIN_THRESHOLD,
        "ambiguous_phone_match_keys": [],
        "ambiguous_phone_last4": [],
    }
    try:
        eligible_members = sorted(
            [_serialize_member(row) for row in repo.list_members_for_message_activity_sync(current_pools=list(current_pools))],
            key=lambda item: (_normalized_text(item.get("external_contact_id")), int(item.get("id") or 0)),
        )
        counters["candidate_count"] = len(eligible_members)
        message_counts = {
            _normalized_text(row.get("phone_match_key")): {
                "phone_prefix3": _normalized_text(row.get("phone_prefix3")),
                "phone_last4": _normalized_text(row.get("phone_last4")),
                "phone_match_key": _normalized_text(row.get("phone_match_key")),
                "message_count": int(row.get("message_count") or 0),
            }
            for row in query_message_activity_counts()
            if _normalized_text(row.get("phone_match_key"))
        }
        summary["message_source_rows"] = len(message_counts)
        members_by_match_key: dict[str, list[dict[str, Any]]] = {}
        for member in eligible_members:
            match_key = _phone_match_key(member.get("phone"))
            if not match_key:
                continue
            members_by_match_key.setdefault(match_key, []).append(member)
        ambiguous_groups = {key: rows for key, rows in members_by_match_key.items() if len(rows) > 1}
        summary["ambiguous_phone_match_keys"] = sorted(ambiguous_groups.keys())
        summary["ambiguous_phone_last4"] = [_normalized_text(item).split("_", 1)[-1] for item in summary["ambiguous_phone_match_keys"]]

        matched_members: list[dict[str, Any]] = []
        for member in eligible_members:
            match_key = _phone_match_key(member.get("phone"))
            member_id = int(member.get("id") or 0)
            phone_prefix3 = _phone_prefix3(member.get("phone"))
            phone_last4 = _phone_last4(member.get("phone"))
            if not match_key:
                counters["skipped_missing_phone_count"] += 1
                repo.insert_message_activity_sync_item(
                    {
                        "run_id": run_id,
                        "member_id": member_id,
                        "external_contact_id": member.get("external_contact_id"),
                        "phone": member.get("phone"),
                        "phone_prefix3": phone_prefix3,
                        "phone_last4": phone_last4,
                        "phone_match_key": "",
                        "message_count": 0,
                        "status": "skipped_missing_phone",
                        "detail": "member phone is empty or shorter than 7 digits, cannot build phone_match_key",
                        "before_snapshot": _member_snapshot(member),
                        "after_snapshot": _member_snapshot(member),
                        "created_at": _iso_now(),
                    }
                )
                continue
            if match_key in ambiguous_groups:
                counters["skipped_ambiguous_count"] += 1
                conflict_members = ",".join(
                    _normalized_text(item.get("external_contact_id")) or f"id:{int(item.get('id') or 0)}"
                    for item in sorted(
                        ambiguous_groups[match_key],
                        key=lambda item: (_normalized_text(item.get("external_contact_id")), int(item.get("id") or 0)),
                    )
                )
                repo.insert_message_activity_sync_item(
                    {
                        "run_id": run_id,
                        "member_id": member_id,
                        "external_contact_id": member.get("external_contact_id"),
                        "phone": member.get("phone"),
                        "phone_prefix3": phone_prefix3,
                        "phone_last4": phone_last4,
                        "phone_match_key": match_key,
                        "message_count": 0,
                        "status": "skipped_ambiguous",
                        "detail": f"phone_match_key={match_key} matched multiple automation members: {conflict_members}",
                        "before_snapshot": _member_snapshot(member),
                        "after_snapshot": _member_snapshot(member),
                        "created_at": _iso_now(),
                    }
                )
                continue
            if match_key not in message_counts:
                counters["skipped_unmatched_count"] += 1
                repo.insert_message_activity_sync_item(
                    {
                        "run_id": run_id,
                        "member_id": member_id,
                        "external_contact_id": member.get("external_contact_id"),
                        "phone": member.get("phone"),
                        "phone_prefix3": phone_prefix3,
                        "phone_last4": phone_last4,
                        "phone_match_key": match_key,
                        "message_count": 0,
                        "status": "skipped_unmatched",
                        "detail": f"phone_match_key={match_key} not found in message activity source",
                        "before_snapshot": _member_snapshot(member),
                        "after_snapshot": _member_snapshot(member),
                        "created_at": _iso_now(),
                    }
                )
                continue
            matched_members.append(
                {
                    "member": member,
                    "phone_prefix3": phone_prefix3,
                    "phone_last4": phone_last4,
                    "phone_match_key": match_key,
                    "message_count": int((message_counts.get(match_key) or {}).get("message_count") or 0),
                }
            )

        counters["matched_count"] = len(matched_members)
        ranked_members = sorted(
            matched_members,
            key=lambda item: (-int(item["message_count"]), int((item["member"].get("id") or 0))),
        )

        for index, item in enumerate(ranked_members):
            before = item["member"]
            message_count = int(item["message_count"])
            if message_count >= ACTIVE_FOCUS_MESSAGE_THRESHOLD:
                next_follow_type = FOLLOWUP_FOCUS
                next_decision_source = DECISION_SOURCE_SYSTEM
                bucket_label = "active_focus_threshold"
                manual_preserved = False
            elif message_count >= ACTIVE_MESSAGE_MIN_THRESHOLD:
                next_follow_type = FOLLOWUP_NORMAL
                next_decision_source = DECISION_SOURCE_SYSTEM
                bucket_label = "active_normal_threshold"
                manual_preserved = False
            else:
                next_follow_type, next_decision_source, manual_preserved = _inactive_follow_type_from_member(before)
                bucket_label = "inactive_questionnaire_or_manual"
            if next_follow_type == FOLLOWUP_FOCUS:
                counters["focus_count"] += 1
            else:
                counters["normal_count"] += 1
            questionnaire_status = _normalized_text(before.get("questionnaire_status")) or QUESTIONNAIRE_PENDING
            next_payload = {
                **before,
                "follow_type": next_follow_type,
                "decision_source": next_decision_source,
                "current_pool": _message_activity_pool(questionnaire_status=questionnaire_status),
            }
            changed = _substantive_member_changed(before, next_payload)
            if changed:
                saved = _persist_member(before, next_payload)
                after = _serialize_member(saved)
                repo.insert_event(
                    member_id=int(after["id"]),
                    action="message_activity_sync",
                    operator_type=normalized_operator_type,
                    operator_id=normalized_operator_id,
                    before_snapshot=_member_snapshot(before),
                    after_snapshot=_member_snapshot(after),
                    remark=(
                        f"message_count={message_count}; phone_match_key={item['phone_match_key']}; "
                        f"rank={index + 1}/{len(ranked_members)}; "
                        f"bucket={bucket_label}; "
                        f"follow_type={'manual_preserved' if manual_preserved else next_follow_type}"
                    ),
                )
                counters["updated_count"] += 1
            else:
                after = before
            repo.insert_message_activity_sync_item(
                {
                    "run_id": run_id,
                    "member_id": int(before["id"]),
                    "external_contact_id": before.get("external_contact_id"),
                    "phone": before.get("phone"),
                    "phone_prefix3": item["phone_prefix3"],
                    "phone_last4": item["phone_last4"],
                    "phone_match_key": item["phone_match_key"],
                    "message_count": message_count,
                    "status": "updated" if changed else "unchanged",
                    "detail": (
                        f"rank={index + 1}/{len(ranked_members)}; "
                        f"bucket={bucket_label}; "
                        f"effective_follow_type={next_follow_type}; "
                        f"manual_preserved={'yes' if manual_preserved else 'no'}"
                    ),
                    "before_snapshot": _member_snapshot(before),
                    "after_snapshot": _member_snapshot(after),
                    "created_at": _iso_now(),
                }
            )

        finished_at = _iso_now()
        summary["processed_at"] = finished_at
        final_run_row = repo.update_message_activity_sync_run(
            run_id,
            {
                **base_run_payload,
                **counters,
                "status": "success",
                "summary_json": summary,
                "finished_at": finished_at,
            },
        )
        db.commit()
        return {
            "ok": True,
            "run": _serialize_message_activity_sync_run(final_run_row),
            "items": [
                _serialize_message_activity_sync_item(item)
                for item in repo.list_message_activity_sync_items(run_id=run_id, limit=50)
            ],
        }
    except Exception as exc:
        db.rollback()
        failed_at = _iso_now()
        failed_run_row = repo.update_message_activity_sync_run(
            run_id,
            {
                **base_run_payload,
                **counters,
                "status": "failed",
                "error_message": str(exc),
                "summary_json": {**summary, "processed_at": failed_at},
                "finished_at": failed_at,
            },
        )
        db.commit()
        return {
            "ok": False,
            "error": str(exc),
            "run": _serialize_message_activity_sync_run(failed_run_row),
        }



