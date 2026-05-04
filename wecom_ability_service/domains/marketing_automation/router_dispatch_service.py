from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app

from ...db import get_db
from . import repo
from .service import (
    DEFAULT_CHANNEL_TYPE,
    DEFAULT_DAY_START_HOUR,
    DEFAULT_QUIET_HOUR_START,
    DEFAULT_SCENARIO_KEY,
    FOLLOWUP_SEGMENT_FOCUS,
    _ROUTER_ALLOWED_STAGE_KEYS,
    _ROUTER_BLOCKED_DISPATCH_STATUS,
    _ROUTER_PENDING_DISPATCH_STATUS,
    _ROUTER_TERMINAL_DISPATCH_STATUSES,
    _blocked_phase_label,
    _build_batch_context,
    _is_within_auto_start_window,
    _json_loads,
    _load_formatted_batch,
    _normalize_followup_segment,
    _normalize_int,
    _normalized_text,
    _pool_stage_key,
    _router_now,
    _router_quiet_hours_blocked,
    _routing_reason_from_preview,
    _serialize_dispatch_log,
    get_customer_marketing_profile,
    get_signup_conversion_config,
    preview_signup_conversion_customer,
)


def _iso_now() -> str:
    from . import service as _svc
    return _svc._iso_now()


logger = logging.getLogger(__name__)


def _ensure_router_dispatch_log(
    *,
    scenario_key: str,
    batch_context: dict[str, Any],
    external_userid: str,
    dispatch_status: str,
    preview: dict[str, Any],
    existing_log: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    serialized_existing = _serialize_dispatch_log(existing_log)
    existing_status = _normalized_text(serialized_existing.get("dispatch_status"))
    if existing_status == dispatch_status:
        return serialized_existing, False
    summary = dict(preview.get("summary") or {})
    marketing_state = dict(preview.get("marketing_state") or {})
    payload = {
        "source": "marketing_candidate_router",
        "route_status": dispatch_status,
        "current_stage": _normalized_text(summary.get("current_stage")),
        "current_segment": _normalized_text(summary.get("current_segment")),
        "hit_count": int(summary.get("hit_count") or 0),
        "eligible_for_conversion": bool(summary.get("eligible_for_conversion")),
        "main_stage": _normalized_text(marketing_state.get("main_stage")),
        "sub_stage": _normalized_text(marketing_state.get("sub_stage")),
        "batch_window_start": _normalized_text(batch_context.get("window_start")),
        "batch_window_end": _normalized_text(batch_context.get("window_end")),
        "latest_customer_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
    }
    note = "candidate eligible for openclaw" if dispatch_status == _ROUTER_PENDING_DISPATCH_STATUS else "blocked by quiet hours"
    row = repo.upsert_conversion_dispatch_log(
        automation_key=scenario_key,
        batch_id=int(batch_context.get("batch_id") or 0),
        external_userid=external_userid,
        dispatch_status=dispatch_status,
        dispatch_channel=DEFAULT_CHANNEL_TYPE,
        dispatch_payload=payload,
        dispatch_note=note,
    )
    return _serialize_dispatch_log(row), True


def _candidate_skip_entry(
    external_userid: str,
    reason: str,
    *,
    dispatch_status: str = "",
) -> dict[str, Any]:
    payload = {"external_userid": external_userid, "reason": reason}
    if dispatch_status:
        payload["dispatch_status"] = dispatch_status
    return payload


def _candidate_preview_stage(preview: dict[str, Any]) -> str:
    return _normalized_text(((preview.get("summary") or {}).get("current_stage")))


def _candidate_preview_segment(preview: dict[str, Any]) -> str:
    return _normalize_followup_segment(((preview.get("summary") or {}).get("current_segment")))


def _build_disabled_batch_result(
    batch_payload: dict[str, Any],
    *,
    scenario_key: str,
) -> dict[str, Any]:
    batch = dict(batch_payload.get("batch") or {})
    messages = [dict(item) for item in batch_payload.get("messages") or [] if isinstance(item, dict)]
    external_userids = sorted(
        {
            _normalized_text(item.get("external_userid"))
            for item in messages
            if _normalized_text(item.get("external_userid"))
        }
    )
    skipped_customers = [
        {"external_userid": external_userid, "reason": "automation_disabled"} for external_userid in external_userids
    ]
    return {
        "scenario_key": scenario_key,
        "batch": batch,
        "messages": messages,
        "paging": batch_payload.get("paging") or {},
        "candidates": [],
        "candidate_count": 0,
        "blocked_count": 0,
        "skipped_customers": skipped_customers,
        "skipped_count": len(skipped_customers),
    }


def route_signup_conversion_batch_candidates(
    batch_id: int,
    *,
    scenario_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    from ..archive.service import materialize_message_batches

    materialize_message_batches(window_minutes=3)
    batch_payload = _load_formatted_batch(int(batch_id))
    if not batch_payload:
        return None
    config = get_signup_conversion_config(automation_key=scenario_key)
    if not bool(config.get("enabled")):
        return _build_disabled_batch_result(batch_payload, scenario_key=scenario_key)
    batch = dict(batch_payload.get("batch") or {})
    messages = [dict(item) for item in batch_payload.get("messages") or [] if isinstance(item, dict)]
    base_cache: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    skipped_customers: list[dict[str, Any]] = []
    blocked_count = 0
    seen_external_userids: set[str] = set()
    wrote_dispatch_logs = False
    quiet_hours_blocked = _router_quiet_hours_blocked(config=config)
    batch_status = _normalized_text(batch.get("status"))

    for message in messages:
        external_userid = _normalized_text(message.get("external_userid"))
        if not external_userid or external_userid in seen_external_userids:
            continue
        seen_external_userids.add(external_userid)
        batch_context = _build_batch_context(
            batch,
            messages,
            external_userid,
            day_start_hour=int(config.get("day_start_hour") or DEFAULT_DAY_START_HOUR),
            quiet_hour_start=int(config.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START),
        )
        if int(batch_context.get("customer_text_count") or 0) <= 0:
            skipped_customers.append(_candidate_skip_entry(external_userid, "no_customer_text_trigger"))
            continue
        if batch_status != "pending":
            skipped_customers.append(_candidate_skip_entry(external_userid, "batch_not_pending"))
            continue
        base = base_cache.setdefault(external_userid, repo.load_customer_marketing_base(external_userid))
        preview = preview_signup_conversion_customer(
            external_userid=external_userid,
            automation_key=scenario_key,
        )
        current_stage = _candidate_preview_stage(preview)
        current_segment = _candidate_preview_segment(preview)
        ineligible_reason = _normalized_text(((preview.get("summary") or {}).get("ineligible_reason")))
        routing_reason = _routing_reason_from_preview(preview)
        if current_stage not in _ROUTER_ALLOWED_STAGE_KEYS:
            skipped_customers.append(_candidate_skip_entry(external_userid, ineligible_reason or routing_reason))
            continue
        if current_segment != FOLLOWUP_SEGMENT_FOCUS:
            skipped_customers.append(_candidate_skip_entry(external_userid, routing_reason))
            continue
        if not bool(((preview.get("summary") or {}).get("eligible_for_conversion"))):
            skipped_customers.append(_candidate_skip_entry(external_userid, ineligible_reason or "not_eligible"))
            continue

        existing_dispatch_log = _serialize_dispatch_log(repo.get_conversion_dispatch_log(int(batch_id), external_userid))
        existing_status = _normalized_text(existing_dispatch_log.get("dispatch_status"))
        if existing_status in _ROUTER_TERMINAL_DISPATCH_STATUSES:
            terminal_reason = "already_acked" if existing_status == "acked" else "already_dispatched"
            if existing_status in {"cancelled", "converted_before_dispatch"}:
                terminal_reason = existing_status
            skipped_customers.append(_candidate_skip_entry(external_userid, terminal_reason, dispatch_status=existing_status))
            continue
        if quiet_hours_blocked:
            dispatch_log, did_write = _ensure_router_dispatch_log(
                scenario_key=scenario_key,
                batch_context=batch_context,
                external_userid=external_userid,
                dispatch_status=_ROUTER_BLOCKED_DISPATCH_STATUS,
                preview=preview,
                existing_log=existing_dispatch_log,
            )
            wrote_dispatch_logs = wrote_dispatch_logs or did_write
            skipped_customers.append(
                _candidate_skip_entry(
                    external_userid,
                    "blocked_quiet_hours",
                    dispatch_status=_normalized_text(dispatch_log.get("dispatch_status")) or _ROUTER_BLOCKED_DISPATCH_STATUS,
                )
            )
            blocked_count += 1
            continue

        dispatch_log, did_write = _ensure_router_dispatch_log(
            scenario_key=scenario_key,
            batch_context=batch_context,
            external_userid=external_userid,
            dispatch_status=_ROUTER_PENDING_DISPATCH_STATUS,
            preview=preview,
            existing_log=existing_dispatch_log,
        )
        wrote_dispatch_logs = wrote_dispatch_logs or did_write
        profile = get_customer_marketing_profile(
            external_userid,
            scenario_key=scenario_key,
            batch_context=batch_context,
        )
        candidates.append(
            {
                "external_userid": external_userid,
                "customer_name": _normalized_text(base.get("customer_name")) or external_userid,
                "owner_userid": _normalized_text(base.get("owner_userid")),
                "marketing_profile": profile,
                "current_stage": current_stage,
                "current_segment": current_segment,
                "eligible_for_conversion": True,
                "dispatch_status": _normalized_text(dispatch_log.get("dispatch_status")) or _ROUTER_PENDING_DISPATCH_STATUS,
                "dispatch_log": dispatch_log,
                "trigger_reason": "pending_text_message_batch",
                "latest_customer_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
                "candidate_messages": batch_context.get("candidate_messages") or [],
                "candidate_message_count": int(batch_context.get("customer_text_count") or 0),
            }
        )

    if wrote_dispatch_logs:
        get_db().commit()

    candidates.sort(
        key=lambda item: (
            int(((((item.get("dispatch_log") or {}).get("dispatch_payload") or {}).get("hit_count")) or 0)),
            _normalized_text(item.get("latest_customer_message_at")),
            _normalized_text(item.get("external_userid")),
        ),
        reverse=True,
    )
    return {
        "scenario_key": scenario_key,
        "batch": batch,
        "messages": messages,
        "paging": batch_payload.get("paging") or {},
        "candidates": candidates,
        "candidate_count": len(candidates),
        "blocked_count": blocked_count,
        "quiet_hours_blocked": quiet_hours_blocked,
        "skipped_customers": skipped_customers,
        "skipped_count": len(skipped_customers),
    }


def get_signup_conversion_batch(batch_id: int, *, scenario_key: str = DEFAULT_SCENARIO_KEY) -> dict[str, Any] | None:
    return route_signup_conversion_batch_candidates(batch_id, scenario_key=scenario_key)


def list_signup_conversion_batches(
    *,
    limit: int = 20,
    cursor: str = "",
    scenario_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    from ..archive.service import list_message_batches, materialize_message_batches

    safe_limit = max(1, min(int(limit), 50))
    config = get_signup_conversion_config(automation_key=scenario_key)
    if not bool(config.get("enabled")):
        return {
            "scenario_key": scenario_key,
            "items": [],
            "count": 0,
            "filters": {"limit": str(safe_limit), "cursor": _normalized_text(cursor)},
            "source_cursor": "",
            "next_cursor": "",
        }
    materialize_message_batches(window_minutes=3)
    pending_batches = list_message_batches(status="pending", limit=safe_limit, cursor=cursor)
    items: list[dict[str, Any]] = []
    for batch in pending_batches.get("items") or []:
        batch_id = int(batch.get("id") or 0)
        if not batch_id:
            continue
        detail = route_signup_conversion_batch_candidates(batch_id, scenario_key=scenario_key)
        if not detail:
            continue
        if int(detail.get("candidate_count") or 0) <= 0 and int(detail.get("blocked_count") or 0) <= 0:
            continue
        preview = [
            {
                "external_userid": _normalized_text(item.get("external_userid")),
                "customer_name": _normalized_text(item.get("customer_name")),
                "owner_userid": _normalized_text(item.get("owner_userid")),
                "current_stage": _normalized_text(item.get("current_stage")),
                "marketing_phase": _normalized_text((((item.get("marketing_profile") or {}).get("marketing_state") or {}).get("marketing_phase"))),
                "value_segment": _normalized_text(item.get("current_segment")),
                "score": int((((item.get("dispatch_log") or {}).get("dispatch_payload") or {}).get("hit_count") or 0)),
                "dispatch_status": _normalized_text(item.get("dispatch_status")),
            }
            for item in detail.get("candidates") or []
        ]
        items.append(
            {
                "id": batch_id,
                "status": _normalized_text(batch.get("status")),
                "window_start": _normalized_text(batch.get("window_start")),
                "window_end": _normalized_text(batch.get("window_end")),
                "message_count": int(batch.get("message_count") or 0),
                "candidate_count": int(detail.get("candidate_count") or 0),
                "blocked_count": int(detail.get("blocked_count") or 0),
                "skipped_count": int(detail.get("skipped_count") or 0),
                "candidates_preview": preview,
            }
        )
    return {
        "scenario_key": scenario_key,
        "items": items,
        "count": len(items),
        "filters": {"limit": str(safe_limit), "cursor": _normalized_text(cursor)},
        "source_cursor": _normalized_text(pending_batches.get("next_cursor")),
        "next_cursor": _normalized_text(pending_batches.get("next_cursor")),
    }

