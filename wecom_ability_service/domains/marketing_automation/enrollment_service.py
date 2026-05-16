from __future__ import annotations

from typing import Any

from ...db import get_db
from . import repo
from .service import (
    DEFAULT_CHANNEL_TYPE,
    DEFAULT_ENROLLED_SIGNUP_STATUS,
    DEFAULT_SCENARIO_KEY,
    FOLLOWUP_SEGMENT_FOCUS,
    FOLLOWUP_SEGMENT_NORMAL,
    POOL_ACTIVE_FOCUS,
    POOL_ACTIVE_NORMAL,
    POOL_INACTIVE_FOCUS,
    POOL_INACTIVE_NORMAL,
    POOL_SILENT,
    _ACTIONABLE_POOL_STAGE_KEYS,
    _ROUTER_BLOCKED_DISPATCH_STATUS,
    _ROUTER_PENDING_DISPATCH_STATUS,
    _apply_class_user_status_change,
    _clear_class_user_status_current,
    _followup_segment_label,
    _get_class_user_status_current,
    _get_class_user_status_definition,
    _is_signup_success,
    _json_loads,
    _normalize_followup_segment,
    _normalize_int,
    _normalized_text,
    _pool_stage_key,
    evaluate_customer_marketing_state,
    preview_signup_conversion_customer,
)


def _iso_now() -> str:
    from . import service as _svc
    return _svc._iso_now()


def _normalize_conversion_source(value: Any, *, default: str) -> str:
    return _normalized_text(value) or default


def _normalize_enrolled_signup_status(value: Any) -> str:
    normalized = _normalized_text(value) or DEFAULT_ENROLLED_SIGNUP_STATUS
    definition = _get_class_user_status_definition(normalized)
    if not definition or not _is_signup_success(normalized):
        raise ValueError("signup_status must be an enrolled status")
    return normalized


def _restore_signup_status_for_unmark(external_userid: str, *, restore_signup_status: str = "") -> str:
    normalized_restore_signup_status = _normalized_text(restore_signup_status)
    if normalized_restore_signup_status:
        definition = _get_class_user_status_definition(normalized_restore_signup_status)
        if not definition:
            raise ValueError("restore_signup_status is invalid")
        if _is_signup_success(normalized_restore_signup_status):
            raise ValueError("restore_signup_status must be a non-enrolled status")
        return normalized_restore_signup_status
    restore_row = repo.get_latest_class_user_restore_status(external_userid) or {}
    restored = _normalized_text(restore_row.get("old_signup_status"))
    if restored and _get_class_user_status_definition(restored) and not _is_signup_success(restored):
        return restored
    return ""


def _build_class_user_snapshot_for_conversion(
    external_userid: str,
    *,
    owner_userid: str = "",
) -> dict[str, str]:
    current = _get_class_user_status_current(external_userid) or {}
    base = repo.load_customer_marketing_base(external_userid)
    if not _normalized_text(base.get("external_userid")) and not current:
        raise LookupError("customer not found")
    normalized_owner_userid = (
        _normalized_text(owner_userid)
        or _normalized_text(current.get("owner_userid_snapshot"))
        or _normalized_text(base.get("owner_userid"))
    )
    return {
        "customer_name_snapshot": _normalized_text(current.get("customer_name_snapshot"))
        or _normalized_text(base.get("customer_name"))
        or external_userid,
        "owner_userid_snapshot": normalized_owner_userid,
        "mobile_snapshot": _normalized_text(current.get("mobile_snapshot")) or _normalized_text(base.get("mobile")),
    }


def _list_pending_conversion_candidate_batch_ids(
    external_userid: str,
    *,
    scenario_key: str,
) -> list[int]:
    from ..archive.service import list_message_batches, materialize_message_batches
    from . import service as _svc

    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return []
    materialize_message_batches(window_minutes=3)
    cursor = ""
    batch_ids: list[int] = []
    seen_batch_ids: set[int] = set()
    while True:
        page = list_message_batches(status="pending", limit=200, cursor=cursor)
        items = page.get("items") or []
        for batch in items:
            batch_id = int(batch.get("id") or 0)
            if not batch_id or batch_id in seen_batch_ids:
                continue
            detail = _svc.get_signup_conversion_batch(batch_id, scenario_key=scenario_key)
            if not detail:
                continue
            candidate_external_userids = {
                _normalized_text(item.get("external_userid"))
                for item in detail.get("candidates") or []
                if _normalized_text(item.get("external_userid"))
            }
            if normalized_external_userid in candidate_external_userids:
                seen_batch_ids.add(batch_id)
                batch_ids.append(batch_id)
        cursor = _normalized_text(page.get("next_cursor"))
        if not cursor:
            break
    return batch_ids


def _cancel_pending_conversion_dispatches(
    *,
    external_userid: str,
    batch_ids: list[int],
    operator: str,
    source: str,
    scenario_key: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    normalized_external_userid = _normalized_text(external_userid)
    normalized_operator = _normalized_text(operator)
    normalized_source = _normalized_text(source)
    for batch_id in batch_ids:
        existing = repo.get_conversion_dispatch_log(int(batch_id), normalized_external_userid) or {}
        existing_status = _normalized_text(existing.get("dispatch_status"))
        dispatch_status = (
            "converted_before_dispatch"
            if existing_status in {"", "pending", "converted_before_dispatch"}
            else "cancelled"
        )
        row = repo.upsert_conversion_dispatch_log(
            automation_key=scenario_key,
            batch_id=int(batch_id),
            external_userid=normalized_external_userid,
            dispatch_status=dispatch_status,
            dispatch_channel="text_message",
            dispatch_payload={
                "action": "mark_enrolled",
                "operator": normalized_operator,
                "source": normalized_source,
                "previous_dispatch_status": existing_status,
            },
            dispatch_note=f"conversion marked by {normalized_source or 'unknown'}",
        )
        if row:
            results.append(row)
    return results


def _cancel_dispatches_for_pool_change(
    *,
    external_userid: str,
    previous_stage_key: str,
    current_stage_key: str,
    automation_key: str,
) -> list[dict[str, Any]]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid or previous_stage_key == current_stage_key:
        return []
    if previous_stage_key not in _ACTIONABLE_POOL_STAGE_KEYS:
        return []
    results: list[dict[str, Any]] = []
    for row in repo.list_conversion_dispatch_logs(external_userid=normalized_external_userid):
        batch_id = _normalize_int(row.get("batch_id"), "batch_id", allow_none=True)
        if batch_id is None:
            continue
        existing_status = _normalized_text(row.get("dispatch_status"))
        if existing_status not in {_ROUTER_PENDING_DISPATCH_STATUS, _ROUTER_BLOCKED_DISPATCH_STATUS}:
            continue
        payload = _json_loads(row.get("dispatch_payload_json"), default={})
        if not isinstance(payload, dict):
            payload = {}
        payload.update(
            {
                "action": "pool_changed",
                "previous_stage_key": previous_stage_key,
                "current_stage_key": current_stage_key,
            }
        )
        updated = repo.upsert_conversion_dispatch_log(
            automation_key=automation_key,
            batch_id=int(batch_id),
            external_userid=normalized_external_userid,
            dispatch_status="cancelled",
            dispatch_channel=_normalized_text(row.get("dispatch_channel")) or DEFAULT_CHANNEL_TYPE,
            dispatch_payload=payload,
            dispatch_note=f"pool changed: {previous_stage_key} -> {current_stage_key}",
            dispatched_at=_normalized_text(row.get("dispatched_at")),
            acked_at=_normalized_text(row.get("acked_at")),
        )
        if updated:
            results.append(updated)
    return results


def mark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    signup_status: str = DEFAULT_ENROLLED_SIGNUP_STATUS,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_source = _normalize_conversion_source(source, default="manual")
    normalized_signup_status = _normalize_enrolled_signup_status(signup_status)
    snapshot = _build_class_user_snapshot_for_conversion(
        normalized_external_userid,
        owner_userid=owner_userid,
    )
    normalized_operator = _normalized_text(operator) or _normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_source
    pending_candidate_batch_ids = _list_pending_conversion_candidate_batch_ids(
        normalized_external_userid,
        scenario_key=automation_key,
    )
    current_class_status = _get_class_user_status_current(normalized_external_userid) or {}
    if _normalized_text(current_class_status.get("signup_status")) != normalized_signup_status:
        current_class_status = _apply_class_user_status_change(
            external_userid=normalized_external_userid,
            signup_status=normalized_signup_status,
            set_by_userid=normalized_operator,
            customer_name_snapshot=_normalized_text(snapshot.get("customer_name_snapshot")) or normalized_external_userid,
            owner_userid_snapshot=_normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_operator,
            mobile_snapshot=_normalized_text(snapshot.get("mobile_snapshot")),
        )
    marketing_state = evaluate_customer_marketing_state(
        external_userid=normalized_external_userid,
        automation_key=automation_key,
        state_payload_overrides={
            "manual_conversion_operator": normalized_operator,
            "manual_conversion_source": normalized_source,
            "manual_conversion_action": "mark_enrolled",
        },
        history_change_reason="mark_enrolled",
    )
    cancelled_dispatch_logs = _cancel_pending_conversion_dispatches(
        external_userid=normalized_external_userid,
        batch_ids=pending_candidate_batch_ids,
        operator=normalized_operator,
        source=normalized_source,
        scenario_key=automation_key,
    )
    get_db().commit()
    return {
        "external_userid": normalized_external_userid,
        "signup_status": normalized_signup_status,
        "class_user_status": current_class_status,
        "marketing_state": marketing_state,
        "pending_candidate_batch_ids": pending_candidate_batch_ids,
        "cancelled_dispatches": cancelled_dispatch_logs,
        "cancelled_dispatch_count": len(cancelled_dispatch_logs),
        "operator": normalized_operator,
        "source": normalized_source,
    }


def unmark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    restore_signup_status: str = "",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_source = _normalize_conversion_source(source, default="manual")
    snapshot = _build_class_user_snapshot_for_conversion(
        normalized_external_userid,
        owner_userid=owner_userid,
    )
    normalized_operator = _normalized_text(operator) or _normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_source
    previous_marketing_state = repo.get_customer_marketing_state_current(external_userid=normalized_external_userid)
    target_signup_status = _restore_signup_status_for_unmark(
        normalized_external_userid,
        restore_signup_status=restore_signup_status,
    )
    current_class_status = _get_class_user_status_current(normalized_external_userid) or {}
    if target_signup_status and _normalized_text(current_class_status.get("signup_status")) != target_signup_status:
        current_class_status = _apply_class_user_status_change(
            external_userid=normalized_external_userid,
            signup_status=target_signup_status,
            set_by_userid=normalized_operator,
            customer_name_snapshot=_normalized_text(snapshot.get("customer_name_snapshot")) or normalized_external_userid,
            owner_userid_snapshot=_normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_operator,
            mobile_snapshot=_normalized_text(snapshot.get("mobile_snapshot")),
        )
    elif not target_signup_status:
        _clear_class_user_status_current(
            external_userid=normalized_external_userid,
            set_by_userid=normalized_operator,
            customer_name_snapshot=_normalized_text(snapshot.get("customer_name_snapshot")) or normalized_external_userid,
            owner_userid_snapshot=_normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_operator,
            mobile_snapshot=_normalized_text(snapshot.get("mobile_snapshot")),
        )
        current_class_status = {}
    marketing_state_lookup = {
        "person_id": previous_marketing_state.get("person_id")
        if isinstance(previous_marketing_state, dict)
        else None,
        "external_userid": normalized_external_userid,
    }
    if marketing_state_lookup["person_id"] is not None:
        marketing_state = evaluate_customer_marketing_state(
            person_id=int(marketing_state_lookup["person_id"]),
            automation_key=automation_key,
            state_payload_overrides={
                "manual_conversion_operator": normalized_operator,
                "manual_conversion_source": normalized_source,
                "manual_conversion_action": "unmark_enrolled",
            },
            history_change_reason="unmark_enrolled",
        )
    else:
        marketing_state = evaluate_customer_marketing_state(
            external_userid=normalized_external_userid,
            automation_key=automation_key,
            state_payload_overrides={
                "manual_conversion_operator": normalized_operator,
                "manual_conversion_source": normalized_source,
                "manual_conversion_action": "unmark_enrolled",
            },
            history_change_reason="unmark_enrolled",
        )
    return {
        "external_userid": normalized_external_userid,
        "signup_status": target_signup_status,
        "class_user_status": current_class_status,
        "marketing_state": marketing_state,
        "operator": normalized_operator,
        "source": normalized_source,
    }


def set_manual_followup_segment(
    *,
    external_userid: str,
    followup_segment: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_segment = _normalize_followup_segment(followup_segment)
    if normalized_segment not in {FOLLOWUP_SEGMENT_NORMAL, FOLLOWUP_SEGMENT_FOCUS}:
        raise ValueError("followup_segment must be normal or focus")
    normalized_source = _normalize_conversion_source(source, default="manual")
    snapshot = _build_class_user_snapshot_for_conversion(
        normalized_external_userid,
        owner_userid=owner_userid,
    )
    normalized_operator = _normalized_text(operator) or _normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_source
    existing_state = repo.get_customer_marketing_state_current(external_userid=normalized_external_userid)
    if not existing_state:
        evaluate_customer_marketing_state(
            external_userid=normalized_external_userid,
            automation_key=automation_key,
        )
    preview = preview_signup_conversion_customer(
        external_userid=normalized_external_userid,
        automation_key=automation_key,
        persist=False,
    )
    current_stage_key = _normalized_text(((preview.get("marketing_state") or {}).get("stage_key")))
    if current_stage_key == "converted/enrolled":
        raise ValueError("converted customer cannot switch followup segment")
    if current_stage_key not in {
        _pool_stage_key(POOL_INACTIVE_NORMAL),
        _pool_stage_key(POOL_INACTIVE_FOCUS),
        _pool_stage_key(POOL_ACTIVE_NORMAL),
        _pool_stage_key(POOL_ACTIVE_FOCUS),
        _pool_stage_key(POOL_SILENT),
    }:
        raise ValueError("current pool does not support manual followup switching")
    marketing_state = evaluate_customer_marketing_state(
        external_userid=normalized_external_userid,
        automation_key=automation_key,
        state_payload_overrides={
            "manual_followup_segment": normalized_segment,
            "manual_followup_segment_label": _followup_segment_label(normalized_segment),
            "manual_followup_segment_source": normalized_source,
            "manual_followup_segment_operator": normalized_operator,
            "manual_followup_segment_at": _iso_now(),
        },
        history_change_reason="manual_followup_segment_changed",
    )
    return {
        "external_userid": normalized_external_userid,
        "followup_segment": normalized_segment,
        "followup_segment_label": _followup_segment_label(normalized_segment),
        "marketing_state": marketing_state,
        "operator": normalized_operator,
        "source": normalized_source,
    }

