from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import current_app, g, has_app_context

from ...db import get_db
from ...services import get_recent_messages_by_user
from . import repo as legacy_repo
from .agents import DeepSeekClientError, call_deepseek_agent
from .orchestration_service import (
    _agent_context_source_sections,
    _fixed_agent_output_schema,
    _replace_agent_prompt_placeholders,
    _resolve_effective_enabled_context_sources,
    get_agent_config_detail,
)
from .message_activity_client import get_message_activity_db_status, query_message_activity_counts
from .workflow_definitions import (
    AGENT_BINDING_SCOPE_BEHAVIOR_TIER,
    AGENT_BINDING_SCOPE_PERSONALIZED,
    AGENT_BINDING_SCOPE_PROFILE_CATEGORY,
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    GENERATION_MODE_AUTO_LAYERED_REWRITE,
    GENERATION_MODE_MANUAL_LAYERED,
    GENERATION_MODE_PERSONALIZED_SINGLE,
    NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
    NODE_TRIGGER_MODE_DAILY_RECURRING,
    NODE_TRIGGER_MODE_SCHEDULED,
    RECIPIENT_FILTER_BASIS_BEHAVIOR,
    RECIPIENT_FILTER_BASIS_NONE,
    SEGMENTATION_BASIS_BEHAVIOR,
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    WORKFLOW_STATUS_ACTIVE,
    list_supported_behavior_tiers,
)
from .workflow_service import get_conversion_workflow_model_bundle
from . import workflow_repo
from .workflow_execution_runner import run_workflow_execution  # noqa: F401


DEFAULT_AUTOMATION_SENDER = "HuangYouCan"
_FINAL_EXECUTION_STATUSES = {"finished", "partial_failed", "failed"}
_USAGE_ACTIVITY_CACHE_KEY = "automation_conversion_usage_activity_counts"


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    if minimum is not None:
        result = max(result, minimum)
    return result


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    text = _normalized_text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _parse_timestamp(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
    except ValueError:
        pass
    for pattern in (
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
        except ValueError:
            continue
    return None


def _parse_send_time(value: Any) -> tuple[int, int]:
    text = _normalized_text(value) or "09:00"
    parsed = datetime.strptime(text, "%H:%M")
    return parsed.hour, parsed.minute


def _node_trigger_mode(node: dict[str, Any]) -> str:
    normalized = _normalized_text(node.get("trigger_mode"))
    if normalized == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        return NODE_TRIGGER_MODE_AUDIENCE_ENTERED
    if normalized == NODE_TRIGGER_MODE_DAILY_RECURRING:
        return NODE_TRIGGER_MODE_DAILY_RECURRING
    return NODE_TRIGGER_MODE_SCHEDULED


def _iso_now() -> str:
    return _now_dt().strftime("%Y-%m-%d %H:%M:%S")


def _now_dt() -> datetime:
    return datetime.now()


def _date_text(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) >= 10:
        return text[:10]
    parsed = _parse_timestamp(text)
    return parsed.strftime("%Y-%m-%d") if parsed else ""


def _log_runtime_event(event: str, payload: dict[str, Any]) -> None:
    if not has_app_context():
        return
    try:
        current_app.logger.info(
            "automation_conversion_workflow event=%s payload=%s",
            _normalized_text(event) or "unknown",
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    except Exception:
        current_app.logger.info("automation_conversion_workflow event=%s", _normalized_text(event) or "unknown")


def _phone_match_key(phone: Any) -> str:
    digits = "".join(char for char in _normalized_text(phone) if char.isdigit())
    if len(digits) < 7:
        return ""
    return f"{digits[:3]}_{digits[-4:]}"


def _behavior_tier_items() -> list[dict[str, Any]]:
    return [dict(item) for item in list_supported_behavior_tiers()]


def _behavior_tier_for_count(usage_count: int) -> dict[str, Any]:
    normalized_count = max(0, int(usage_count or 0))
    for item in _behavior_tier_items():
        min_value = item.get("min_value")
        max_value = item.get("max_value")
        if min_value is not None and normalized_count < int(min_value):
            continue
        if max_value is not None and normalized_count > int(max_value):
            continue
        return dict(item)
    return dict(_behavior_tier_items()[0])


def _behavior_tier_for_key(tier_key: str) -> dict[str, Any]:
    normalized_tier_key = _normalized_text(tier_key)
    if not normalized_tier_key:
        return {}
    for item in _behavior_tier_items():
        if _normalized_text(item.get("tier_code")) == normalized_tier_key:
            return dict(item)
    return {}


def _usage_activity_snapshot() -> dict[str, Any]:
    cached = getattr(g, _USAGE_ACTIVITY_CACHE_KEY, None)
    if isinstance(cached, dict):
        return cached
    status = get_message_activity_db_status()
    if not bool(status.get("configured")):
        snapshot = {
            "available": False,
            "error": "message_activity_db_not_configured",
            "counts_by_match_key": {},
            "source": "message_activity_db",
            "missing_keys": list(status.get("missing_keys") or []),
        }
        setattr(g, _USAGE_ACTIVITY_CACHE_KEY, snapshot)
        return snapshot
    try:
        rows = query_message_activity_counts()
    except Exception as exc:
        snapshot = {
            "available": False,
            "error": _normalized_text(exc) or "message_activity_query_failed",
            "counts_by_match_key": {},
            "source": "message_activity_db",
            "missing_keys": list(status.get("missing_keys") or []),
        }
        setattr(g, _USAGE_ACTIVITY_CACHE_KEY, snapshot)
        return snapshot
    counts_by_match_key = {
        _normalized_text(row.get("phone_match_key")): {
            "phone_match_key": _normalized_text(row.get("phone_match_key")),
            "phone_prefix3": _normalized_text(row.get("phone_prefix3")),
            "phone_last4": _normalized_text(row.get("phone_last4")),
            "usage_count": int(row.get("message_count") or 0),
            "source": "message_activity_db",
        }
        for row in rows
        if _normalized_text(row.get("phone_match_key"))
    }
    snapshot = {
        "available": True,
        "error": "",
        "counts_by_match_key": counts_by_match_key,
        "source": "message_activity_db",
        "missing_keys": list(status.get("missing_keys") or []),
    }
    setattr(g, _USAGE_ACTIVITY_CACHE_KEY, snapshot)
    return snapshot


def _usage_activity_for_member(member: dict[str, Any]) -> dict[str, Any]:
    phone_match_key = _phone_match_key(member.get("phone"))
    if not phone_match_key:
        return {
            "available": False,
            "reason": "usage_phone_missing",
            "usage_count": 0,
            "phone_match_key": "",
            "source": "message_activity_db",
        }
    snapshot = _usage_activity_snapshot()
    if not bool(snapshot.get("available")):
        return {
            "available": False,
            "reason": _normalized_text(snapshot.get("error")) or "usage_source_unavailable",
            "usage_count": 0,
            "phone_match_key": phone_match_key,
            "source": _normalized_text(snapshot.get("source")) or "message_activity_db",
            "missing_keys": list(snapshot.get("missing_keys") or []),
        }
    usage_row = dict((snapshot.get("counts_by_match_key") or {}).get(phone_match_key) or {})
    if not usage_row:
        current_audience_code = _normalized_text(member.get("current_audience_code"))
        if current_audience_code in {AUDIENCE_OPERATING, AUDIENCE_CONVERTED}:
            return {
                "available": True,
                "reason": "usage_source_missing_treated_as_zero",
                "usage_count": 0,
                "phone_match_key": phone_match_key,
                "source": "message_activity_db_missing_as_zero",
            }
        return {
            "available": False,
            "reason": "usage_source_not_found",
            "usage_count": 0,
            "phone_match_key": phone_match_key,
            "source": _normalized_text(snapshot.get("source")) or "message_activity_db",
        }
    return {
        "available": True,
        "reason": "",
        "usage_count": int(usage_row.get("usage_count") or 0),
        "phone_match_key": phone_match_key,
        "source": _normalized_text(usage_row.get("source")) or _normalized_text(snapshot.get("source")) or "message_activity_db",
    }


def _workflow_recipient_filter_config(workflow_bundle: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(workflow_bundle.get("workflow") or {})
    basis = _normalized_text(workflow.get("recipient_filter_basis")) or RECIPIENT_FILTER_BASIS_NONE
    if basis not in {RECIPIENT_FILTER_BASIS_NONE, RECIPIENT_FILTER_BASIS_BEHAVIOR}:
        basis = RECIPIENT_FILTER_BASIS_NONE
    tier_keys = []
    seen: set[str] = set()
    allowed = {_normalized_text(item.get("tier_code")) for item in _behavior_tier_items()}
    for item in workflow.get("recipient_behavior_tier_keys") or []:
        tier_key = _normalized_text(item)
        if not tier_key or tier_key in seen or tier_key not in allowed:
            continue
        seen.add(tier_key)
        tier_keys.append(tier_key)
    if basis != RECIPIENT_FILTER_BASIS_BEHAVIOR:
        tier_keys = []
    return {
        "recipient_filter_basis": basis,
        "recipient_behavior_tier_keys": tier_keys,
    }


def _member_behavior_tier_match(member: dict[str, Any], selected_tier_keys: list[str]) -> dict[str, Any]:
    resolved = _resolve_behavior_segment_match(member)
    selected = {_normalized_text(item) for item in selected_tier_keys or [] if _normalized_text(item)}
    tier_key = _normalized_text(resolved.get("segment_key"))
    return {
        **resolved,
        "selected_tier_keys": sorted(selected),
        "matched": bool(tier_key) and tier_key in selected,
    }


def _member_workflow_recipient_filter_result(member: dict[str, Any], workflow_bundle: dict[str, Any]) -> dict[str, Any]:
    config = _workflow_recipient_filter_config(workflow_bundle)
    basis = _normalized_text(config.get("recipient_filter_basis"))
    if basis != RECIPIENT_FILTER_BASIS_BEHAVIOR:
        return {
            "matched": True,
            "basis": basis or RECIPIENT_FILTER_BASIS_NONE,
            "reason": "",
        }
    if not (
        int(member.get("id") or 0)
        or _normalized_text(member.get("external_contact_id"))
        or _normalized_text(member.get("phone"))
    ):
        return {
            "matched": False,
            "basis": basis,
            "reason": "member_identity_missing",
        }
    behavior_match = _member_behavior_tier_match(member, list(config.get("recipient_behavior_tier_keys") or []))
    return {
        **behavior_match,
        "basis": basis,
        "reason": _normalized_text(behavior_match.get("reason")) or ("recipient_filter_not_matched" if not bool(behavior_match.get("matched")) else ""),
    }


def _member_matches_workflow_recipient_filter(member: dict[str, Any], workflow_bundle: dict[str, Any]) -> bool:
    return bool(_member_workflow_recipient_filter_result(member, workflow_bundle).get("matched"))


def _current_audience_source_snapshot(
    member: dict[str, Any],
    marketing_state: dict[str, Any] | None,
    *,
    questionnaire_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_questionnaire = dict(questionnaire_state or {})
    return {
        "member_id": int(member.get("id") or 0),
        "external_contact_id": _normalized_text(member.get("external_contact_id")),
        "phone": _normalized_text(member.get("phone")),
        "current_pool": _normalized_text(member.get("current_pool")),
        "questionnaire_status": _normalized_text(resolved_questionnaire.get("questionnaire_status")) or _normalized_text(member.get("questionnaire_status")),
        "questionnaire_submitted_at": _normalized_text(resolved_questionnaire.get("submitted_at")),
        "marketing_state": {
            "main_stage": _normalized_text((marketing_state or {}).get("main_stage")),
            "sub_stage": _normalized_text((marketing_state or {}).get("sub_stage")),
            "converted": bool((marketing_state or {}).get("converted")),
            "last_conversion_marked_at": _normalized_text((marketing_state or {}).get("last_conversion_marked_at")),
        },
    }


def _resolve_member_conversion_audience(member: dict[str, Any]) -> dict[str, Any]:
    from .service import resolve_member_questionnaire_truth

    marketing_state = workflow_repo.get_customer_marketing_state_current_row(
        external_userid=_normalized_text(member.get("external_contact_id")),
        person_id=int(member.get("master_customer_id") or 0) or None,
    )
    questionnaire_state = resolve_member_questionnaire_truth(
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
        member=member,
    )
    questionnaire_status = _normalized_text(questionnaire_state.get("questionnaire_status"))
    questionnaire_submitted_at = _normalized_text(questionnaire_state.get("submitted_at"))
    current_audience_code = _normalized_text(member.get("current_audience_code"))
    current_audience_entered_at = _normalized_text(member.get("current_audience_entered_at"))
    if (
        _normalized_text(member.get("source_type")) == "wecom_customer_acquisition"
        and current_audience_code in {AUDIENCE_PENDING_QUESTIONNAIRE, AUDIENCE_OPERATING, AUDIENCE_CONVERTED}
        and questionnaire_status != "submitted"
        and not bool((marketing_state or {}).get("converted"))
        and _normalized_text((marketing_state or {}).get("main_stage")) != "converted"
    ):
        return {
            "audience_code": current_audience_code,
            "entered_at": current_audience_entered_at
            or _normalized_text(member.get("joined_at"))
            or _normalized_text(member.get("updated_at"))
            or _iso_now(),
            "entry_source": "wecom_customer_acquisition",
            "entry_reason": "customer_acquisition_initial_audience",
            "source_snapshot_json": _current_audience_source_snapshot(
                member,
                marketing_state,
                questionnaire_state=questionnaire_state,
            ),
        }
    if (
        bool((marketing_state or {}).get("converted"))
        or _normalized_text((marketing_state or {}).get("main_stage")) == "converted"
        or _normalized_text(member.get("current_pool")) in {"won", "converted"}
    ):
        return {
            "audience_code": AUDIENCE_CONVERTED,
            "entered_at": current_audience_entered_at if current_audience_code == AUDIENCE_CONVERTED and current_audience_entered_at else (
                _normalized_text((marketing_state or {}).get("last_conversion_marked_at"))
                or _normalized_text((marketing_state or {}).get("entered_at"))
                or _normalized_text(member.get("updated_at"))
                or _normalized_text(member.get("joined_at"))
                or _iso_now()
            ),
            "entry_source": "marketing_state",
            "entry_reason": "customer_marketing_state_converted",
            "source_snapshot_json": _current_audience_source_snapshot(member, marketing_state, questionnaire_state=questionnaire_state),
        }
    if questionnaire_status == "submitted":
        return {
            "audience_code": AUDIENCE_OPERATING,
            "entered_at": current_audience_entered_at if current_audience_code == AUDIENCE_OPERATING and current_audience_entered_at else (
                questionnaire_submitted_at
                or _normalized_text(member.get("updated_at"))
                or _normalized_text(member.get("joined_at"))
                or _iso_now()
            ),
            "entry_source": "questionnaire_submission" if int(questionnaire_state.get("submission_id") or 0) > 0 else "automation_member",
            "entry_reason": "questionnaire_submitted",
            "source_snapshot_json": _current_audience_source_snapshot(member, marketing_state, questionnaire_state=questionnaire_state),
        }
    return {
        "audience_code": AUDIENCE_PENDING_QUESTIONNAIRE,
        "entered_at": current_audience_entered_at if current_audience_code == AUDIENCE_PENDING_QUESTIONNAIRE and current_audience_entered_at else (
            _normalized_text(member.get("joined_at"))
            or _normalized_text(member.get("created_at"))
            or _normalized_text(member.get("updated_at"))
            or _iso_now()
        ),
        "entry_source": "automation_member",
        "entry_reason": "questionnaire_not_submitted",
        "source_snapshot_json": _current_audience_source_snapshot(member, marketing_state, questionnaire_state=questionnaire_state),
    }


def sync_conversion_member_audience(member: dict[str, Any]) -> dict[str, Any]:
    member_id = int(member.get("id") or 0)
    if member_id <= 0:
        return {"updated": False, "reason": "member_id_missing"}
    resolved = _resolve_member_conversion_audience(member)
    current_entry = workflow_repo.get_current_member_audience_entry_row(member_id)
    current_code = _normalized_text(member.get("current_audience_code"))
    current_entered_at = _normalized_text(member.get("current_audience_entered_at"))
    target_code = _normalized_text(resolved.get("audience_code"))
    target_entered_at = _normalized_text(resolved.get("entered_at")) or _iso_now()

    if current_entry and _normalized_text(current_entry.get("audience_code")) == target_code:
        if current_code != target_code or current_entered_at != _normalized_text(current_entry.get("entered_at")):
            workflow_repo.update_member_current_audience_row(
                member_id,
                audience_code=target_code,
                entered_at=_normalized_text(current_entry.get("entered_at")) or target_entered_at,
            )
            return {"updated": True, "member_id": member_id, "audience_code": target_code, "entered_at": _normalized_text(current_entry.get("entered_at")) or target_entered_at}
        return {"updated": False, "member_id": member_id, "audience_code": target_code, "entered_at": _normalized_text(current_entry.get("entered_at")) or target_entered_at}

    if current_entry:
        workflow_repo.close_current_member_audience_entries(
            member_id,
            exited_at=target_entered_at,
            entry_reason=_normalized_text(resolved.get("entry_reason")),
            source_snapshot_json=dict(resolved.get("source_snapshot_json") or {}),
        )

    workflow_repo.insert_member_audience_entry_row(
        {
            "member_id": member_id,
            "audience_code": target_code,
            "entered_at": target_entered_at,
            "exited_at": "",
            "is_current": True,
            "entry_source": _normalized_text(resolved.get("entry_source")) or "system",
            "entry_reason": _normalized_text(resolved.get("entry_reason")),
            "source_snapshot_json": dict(resolved.get("source_snapshot_json") or {}),
        }
    )
    workflow_repo.update_member_current_audience_row(
        member_id,
        audience_code=target_code,
        entered_at=target_entered_at,
    )
    return {"updated": True, "member_id": member_id, "audience_code": target_code, "entered_at": target_entered_at}


def sync_all_conversion_member_audiences() -> dict[str, Any]:
    scanned_count = 0
    updated_count = 0
    updated_member_ids: list[int] = []
    for member in workflow_repo.list_automation_member_rows():
        scanned_count += 1
        result = sync_conversion_member_audience(member)
        if bool(result.get("updated")):
            updated_count += 1
            updated_member_ids.append(int(result.get("member_id") or 0))
    get_db().commit()
    return {"ok": True, "scanned_count": scanned_count, "updated_count": updated_count, "updated_member_ids": updated_member_ids}


def _node_schedule_anchor_date(*, entered_at: str, send_time: str) -> datetime.date | None:
    entered_dt = _parse_timestamp(entered_at)
    if entered_dt is None:
        return None
    hour, minute = _parse_send_time(send_time)
    scheduled_same_day = entered_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    anchor_dt = entered_dt if entered_dt <= scheduled_same_day else entered_dt + timedelta(days=1)
    return anchor_dt.date()


def _node_day_index(*, entered_at: str, send_time: str, scheduled_for: str) -> int | None:
    scheduled_dt = _parse_timestamp(scheduled_for)
    if scheduled_dt is None:
        return None
    anchor_date = _node_schedule_anchor_date(entered_at=entered_at, send_time=send_time)
    if anchor_date is None:
        return None
    return (scheduled_dt.date() - anchor_date).days + 1


def _node_day_index_matches(*, entered_at: str, send_time: str, scheduled_for: str, expected_day_offset: int) -> bool:
    day_index = _node_day_index(entered_at=entered_at, send_time=send_time, scheduled_for=scheduled_for)
    return day_index == int(expected_day_offset) if day_index is not None else False


def _execution_can_recompute_day_offset_miss(execution: dict[str, Any]) -> bool:
    if _normalized_text(execution.get("status")) not in _FINAL_EXECUTION_STATUSES:
        return False
    if any(
        int(execution.get(counter_key) or 0) > 0
        for counter_key in ("total_count", "success_count", "skipped_count", "failed_count")
    ):
        return False
    summary = execution.get("summary_json") or {}
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = {}
    if not isinstance(summary, dict):
        return False
    zero_hit_reasons = summary.get("zero_hit_reasons") or []
    return "day_offset_not_due" in {str(item) for item in zero_hit_reasons}


def _resolve_profile_segment_match(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
) -> dict[str, Any]:
    from .workflow_service import _resolve_profile_segment_for_member

    resolved = _resolve_profile_segment_for_member(
        member=member,
        profile_segment_template_bundle=dict(workflow_bundle.get("profile_segment_template") or {}),
    )
    return {
        "matched": bool(resolved.get("matched")),
        "reason": _normalized_text(resolved.get("reason")),
        "segment_key": _normalized_text(resolved.get("segment_key")),
        "segment_label": _normalized_text(resolved.get("segment_label")),
        "submission_id": int(resolved.get("submission_id") or 0) or None,
        "selected_option_ids": list(resolved.get("selected_option_ids") or []),
        "matched_categories": list(resolved.get("matched_categories") or []),
    }


def _resolve_behavior_segment_match(member: dict[str, Any]) -> dict[str, Any]:
    materialized_tier = _behavior_tier_for_key(_normalized_text(member.get("behavior_tier_key")))
    if materialized_tier:
        return {
            "matched": True,
            "reason": "",
            "segment_key": _normalized_text(materialized_tier.get("tier_code")),
            "segment_label": _normalized_text(materialized_tier.get("label")),
            "usage_count": 0,
            "message_count": 0,
            "usage_source": "automation_member.behavior_tier_key",
            "phone_match_key": _phone_match_key(member.get("phone")),
        }
    usage_activity = _usage_activity_for_member(member)
    if not bool(usage_activity.get("available")):
        return {
            "matched": False,
            "reason": _normalized_text(usage_activity.get("reason")) or "usage_source_unavailable",
            "segment_key": "",
            "segment_label": "",
            "usage_count": int(usage_activity.get("usage_count") or 0),
            "message_count": int(usage_activity.get("usage_count") or 0),
            "usage_source": _normalized_text(usage_activity.get("source")) or "message_activity_db",
            "phone_match_key": _normalized_text(usage_activity.get("phone_match_key")),
        }
    usage_count = int(usage_activity.get("usage_count") or 0)
    tier = _behavior_tier_for_count(usage_count)
    return {
        "matched": True,
        "reason": "",
        "segment_key": _normalized_text(tier.get("tier_code")),
        "segment_label": _normalized_text(tier.get("label")),
        "usage_count": usage_count,
        "message_count": usage_count,
        "usage_source": _normalized_text(usage_activity.get("source")) or "message_activity_db",
        "phone_match_key": _normalized_text(usage_activity.get("phone_match_key")),
    }


def _resolve_segment_match_for_basis(
    *,
    segmentation_basis: str,
    workflow_bundle: dict[str, Any],
    member: dict[str, Any],
) -> dict[str, Any]:
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        return _resolve_profile_segment_match(member=member, workflow_bundle=workflow_bundle)
    if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR:
        return _resolve_behavior_segment_match(member)
    return {"matched": False, "reason": "segmentation_none"}


def _node_content_mode(node: dict[str, Any], workflow_bundle: dict[str, Any]) -> str:
    content_mode = _normalized_text(node.get("content_mode"))
    if content_mode:
        return content_mode
    workflow = dict(workflow_bundle.get("workflow") or {})
    generation_mode = _normalized_text(workflow.get("generation_mode"))
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        return "manual_layered"
    if generation_mode == GENERATION_MODE_AUTO_LAYERED_REWRITE:
        return "standard_layered_rewrite"
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return "personalized_single"
    return "standard_direct"


def _node_segmentation_basis(node: dict[str, Any], workflow_bundle: dict[str, Any]) -> str:
    node_basis = _normalized_text(node.get("segmentation_basis"))
    if node_basis in {SEGMENTATION_BASIS_NONE, SEGMENTATION_BASIS_PROFILE, SEGMENTATION_BASIS_BEHAVIOR}:
        return node_basis
    workflow = dict(workflow_bundle.get("workflow") or {})
    workflow_basis = _normalized_text(workflow.get("segmentation_basis"))
    if workflow_basis in {SEGMENTATION_BASIS_PROFILE, SEGMENTATION_BASIS_BEHAVIOR}:
        return workflow_basis
    return SEGMENTATION_BASIS_NONE


def _node_generation_mode(node: dict[str, Any], workflow_bundle: dict[str, Any]) -> str:
    content_mode = _node_content_mode(node, workflow_bundle)
    if content_mode == "manual_layered":
        return GENERATION_MODE_MANUAL_LAYERED
    if content_mode == "standard_layered_rewrite":
        return GENERATION_MODE_AUTO_LAYERED_REWRITE
    if content_mode == "personalized_single":
        return GENERATION_MODE_PERSONALIZED_SINGLE
    return ""


def _select_agent_binding(
    *,
    generation_mode: str,
    segmentation_basis: str,
    bindings: list[dict[str, Any]],
    segment_match: dict[str, Any],
) -> dict[str, Any] | None:
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return next(
            (
                item
                for item in bindings
                if _normalized_text(item.get("binding_scope")) == AGENT_BINDING_SCOPE_PERSONALIZED
            ),
            None,
        )
    if not bool(segment_match.get("matched")):
        return None
    segment_key = _normalized_text(segment_match.get("segment_key"))
    binding_scope = (
        AGENT_BINDING_SCOPE_PROFILE_CATEGORY
        if segmentation_basis == SEGMENTATION_BASIS_PROFILE
        else AGENT_BINDING_SCOPE_BEHAVIOR_TIER
    )
    return next(
        (
            item
            for item in bindings
            if _normalized_text(item.get("binding_scope")) == binding_scope
            and _normalized_text(item.get("segment_key")) == segment_key
        ),
        None,
    )


def _select_manual_layered_content(
    *,
    node: dict[str, Any],
    segment_match: dict[str, Any],
) -> dict[str, Any]:
    selected_variant = None
    if bool(segment_match.get("matched")):
        selected_variant = next(
            (
                dict(item)
                for item in node.get("content_variants") or []
                if _normalized_text(item.get("segment_key")) == _normalized_text(segment_match.get("segment_key"))
            ),
            None,
        )
    if selected_variant and _normalized_text(selected_variant.get("content_text")):
        return {
            "content_text": _normalized_text(selected_variant.get("content_text")),
            "content_source": "manual_variant",
            "fallback_reason": "",
        }
    fallback_reason = (
        "segment_content_missing"
        if bool(segment_match.get("matched"))
        else (_normalized_text(segment_match.get("reason")) or "segment_not_matched")
    )
    standard_content_text = _normalized_text(node.get("standard_content_text"))
    if (
        _normalized_text(node.get("segmentation_basis")) == SEGMENTATION_BASIS_PROFILE
        and bool(node.get("fallback_to_standard_content"))
        and standard_content_text
    ):
        return {
            "content_text": standard_content_text,
            "content_source": "standard_content_fallback",
            "fallback_reason": fallback_reason,
        }
    return {
        "content_text": "",
        "content_source": "",
        "fallback_reason": fallback_reason,
    }


def _build_generation_variables(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    standard_content_text: str,
    segment_match: dict[str, Any],
    behavior_match: dict[str, Any],
) -> dict[str, Any]:
    from ..admin_console.customer_profile_service import get_customer_profile_tags_payload

    latest_submission = workflow_repo.get_latest_any_questionnaire_submission_row(
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    questionnaire_answers = []
    if latest_submission:
        for answer in workflow_repo.list_questionnaire_submission_answer_rows(int(latest_submission["id"])):
            questionnaire_answers.append(
                {
                    "question_id": int(answer.get("question_id") or 0),
                    "question_title": _normalized_text(answer.get("question_title_snapshot")),
                    "selected_option_ids": _json_list(answer.get("selected_option_ids")),
                    "selected_option_texts": _json_list(answer.get("selected_option_texts_snapshot")),
                    "text_value": _normalized_text(answer.get("text_value")),
                }
            )
    recent_messages = [
        {
            "role": "客户" if _normalized_text(item.get("sender")) == _normalized_text(member.get("external_contact_id")) else "员工",
            "time": _normalized_text(item.get("send_time")),
            "content": _normalized_text(item.get("content") or item.get("message_text") or item.get("text")),
        }
        for item in get_recent_messages_by_user(_normalized_text(member.get("external_contact_id")), limit=20)
    ] if _normalized_text(member.get("external_contact_id")) else []
    tags_payload = get_customer_profile_tags_payload(external_userid=_normalized_text(member.get("external_contact_id"))) if _normalized_text(member.get("external_contact_id")) else {"tags": []}
    user_tags = [
        _normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))
        for item in tags_payload.get("tags") or []
        if _normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))
    ]
    workflow = dict(workflow_bundle.get("workflow") or {})
    node_generation_mode = _node_generation_mode(node, workflow_bundle)
    node_segmentation_basis = _node_segmentation_basis(node, workflow_bundle)
    return {
        "workflow": {
            "workflow_code": _normalized_text(workflow.get("workflow_code")),
            "workflow_name": _normalized_text(workflow.get("workflow_name")),
            "generation_mode": _normalized_text(workflow.get("generation_mode")),
            "segmentation_basis": _normalized_text(workflow.get("segmentation_basis")),
        },
        "node": {
            "node_code": _normalized_text(node.get("node_code")),
            "node_name": _normalized_text(node.get("node_name")),
            "target_audience_code": _normalized_text(node.get("target_audience_code")),
            "trigger_mode": _node_trigger_mode(node),
            "day_offset": int(node.get("day_offset") or 1),
            "send_time": _normalized_text(node.get("send_time")),
            "content_mode": _node_content_mode(node, workflow_bundle),
            "generation_mode": node_generation_mode,
            "segmentation_basis": node_segmentation_basis,
        },
        "member": {
            "member_id": int(member.get("id") or 0),
            "external_contact_id": _normalized_text(member.get("external_contact_id")),
            "phone": _normalized_text(member.get("phone")),
            "owner_staff_id": _normalized_text(member.get("owner_staff_id")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_audience_code": _normalized_text(member.get("current_audience_code")),
            "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
        },
        "standard_content_text": _normalized_text(standard_content_text),
        "profile_segment": {
            "matched": bool(segment_match.get("matched")),
            "segment_key": _normalized_text(segment_match.get("segment_key")),
            "segment_label": _normalized_text(segment_match.get("segment_label")),
            "reason": _normalized_text(segment_match.get("reason")),
        },
        "behavior_tier": {
            "tier_code": _normalized_text(behavior_match.get("segment_key")),
            "tier_label": _normalized_text(behavior_match.get("segment_label")),
            "usage_count": int(behavior_match.get("usage_count") or 0),
            "message_count": int(behavior_match.get("message_count") or 0),
            "usage_source": _normalized_text(behavior_match.get("usage_source")),
            "phone_match_key": _normalized_text(behavior_match.get("phone_match_key")),
            "reason": _normalized_text(behavior_match.get("reason")),
        },
        "questionnaire": {
            "submission_id": int((latest_submission or {}).get("id") or 0) or None,
            "submitted_at": _normalized_text((latest_submission or {}).get("submitted_at")),
            "answers": questionnaire_answers,
        },
        "recent_messages": recent_messages,
        "user_tags": user_tags,
    }


def _build_agent_generation_request(
    *,
    agent_code: str,
    standard_content_text: str,
    variables_snapshot: dict[str, Any],
) -> tuple[str, str]:
    agent_detail = get_agent_config_detail(agent_code)
    published = dict(agent_detail.get("published") or {})
    role_prompt = _normalized_text(published.get("role_prompt"))
    task_prompt = _normalized_text(published.get("task_prompt"))
    enabled_context_sources = _resolve_effective_enabled_context_sources(
        role_prompt=role_prompt,
        task_prompt=task_prompt,
        enabled_context_sources=published.get("enabled_context_sources"),
        variables=published.get("variables") or [],
    )
    section_texts = _agent_context_source_sections(variables_snapshot, enabled_context_sources)
    role_prompt = _replace_agent_prompt_placeholders(role_prompt, section_texts)
    task_prompt = _replace_agent_prompt_placeholders(task_prompt, section_texts)
    system_prompt = "\n\n".join(
        part
        for part in [
            role_prompt,
            "你只能基于提示词里实际引用到的信息来源生成一条话术，不能臆测缺失事实。",
            "如果某类信息为空，就忽略它，不要报错。",
            "你必须只返回 JSON 对象。",
            'JSON 只允许包含字段：draft_reply。',
        ]
        if _normalized_text(part)
    )
    user_input = json.dumps(
        {
            "task_prompt": task_prompt,
            "standard_content_text": _normalized_text(standard_content_text),
            "enabled_context_sources": enabled_context_sources,
            "context_sections": section_texts,
            "variables": variables_snapshot,
            "required_output_schema": _fixed_agent_output_schema(),
        },
        ensure_ascii=False,
    )
    return system_prompt, user_input


def _generate_content_with_agent(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    agent_binding: dict[str, Any] | None,
    standard_content_text: str,
    segment_match: dict[str, Any],
    behavior_match: dict[str, Any],
    request_id: str,
    generation_source: str,
) -> dict[str, Any]:
    if not agent_binding:
        return {
            "content_text": _normalized_text(standard_content_text),
            "content_source": "standard_content",
            "fallback_reason": "agent_binding_missing",
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }
    agent_code = _normalized_text(agent_binding.get("agent_code"))
    if not agent_code:
        return {
            "content_text": _normalized_text(standard_content_text),
            "content_source": "standard_content",
            "fallback_reason": "agent_code_missing",
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }
    variables_snapshot = _build_generation_variables(
        member=member,
        workflow_bundle=workflow_bundle,
        node=node,
        standard_content_text=standard_content_text,
        segment_match=segment_match,
        behavior_match=behavior_match,
    )
    last_error = ""
    try:
        system_prompt, user_input = _build_agent_generation_request(
            agent_code=agent_code,
            standard_content_text=standard_content_text,
            variables_snapshot=variables_snapshot,
        )
        result = call_deepseek_agent(
            agent_code=agent_code,
            system_prompt=system_prompt,
            user_input=user_input,
            json_output=True,
            request_id=request_id,
            userid=_normalized_text(member.get("owner_staff_id")) or DEFAULT_AUTOMATION_SENDER,
            external_contact_id=_normalized_text(member.get("external_contact_id")),
            input_snapshot={
                "source": generation_source,
                "workflow_code": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_code")),
                "node_code": _normalized_text(node.get("node_code")),
                "agent_code": agent_code,
            },
            variables_snapshot=variables_snapshot,
            source=generation_source,
        )
        latest_output = legacy_repo.deserialize_agent_output_row(
            legacy_repo.get_latest_agent_output_row_by_request_id(
                _normalized_text(result.get("request_id") or request_id),
                output_types=["agent_reply_final", "agent_reply_draft", "next_action_suggestion", "error_output"],
            )
            or {}
        )
        parsed_output = dict(result.get("parsed_output") or {})
        generated_text = (
            _normalized_text(parsed_output.get("reply_final"))
            or _normalized_text(parsed_output.get("final_reply"))
            or _normalized_text(parsed_output.get("draft_reply"))
            or _normalized_text(parsed_output.get("reply_draft"))
            or _normalized_text(latest_output.get("rendered_output_text"))
        )
        if generated_text:
            return {
                "content_text": generated_text,
                "content_source": "agent_generated",
                "fallback_reason": "",
                "agent_run_id": _normalized_text(result.get("run_id")) or _normalized_text(latest_output.get("run_id")),
                "agent_output_id": _normalized_text(latest_output.get("output_id")),
                "agent_code": agent_code,
            }
        last_error = "agent_generated_content_empty"
    except (LookupError, ValueError, DeepSeekClientError) as exc:
        last_error = str(exc)
    except Exception as exc:
        last_error = str(exc)
    return {
        "content_text": _normalized_text(standard_content_text),
        "content_source": "standard_content",
        "fallback_reason": last_error or "agent_generation_failed",
        "agent_run_id": "",
        "agent_output_id": "",
        "agent_code": "",
    }


def _node_miniprogram_library_ids(*, node: dict[str, Any], workflow_bundle: dict[str, Any]) -> list[int]:
    raw_node_miniprograms = node.get("miniprogram_library_ids") or []
    if not raw_node_miniprograms:
        scp = node.get("standard_content_payload")
        if isinstance(scp, dict):
            raw_node_miniprograms = scp.get("miniprogram_library_ids") or []
    if not raw_node_miniprograms:
        raw_node_miniprograms = workflow_bundle.get("miniprogram_library_ids") or []
    miniprogram_library_ids: list[int] = []
    for value in raw_node_miniprograms:
        try:
            miniprogram_library_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return miniprogram_library_ids


def _render_node_content(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    execution_request_id: str,
) -> dict[str, Any]:
    segmentation_basis = _node_segmentation_basis(node, workflow_bundle)
    generation_mode = _node_generation_mode(node, workflow_bundle)
    content_mode = _node_content_mode(node, workflow_bundle)
    segment_match = _resolve_segment_match_for_basis(
        segmentation_basis=segmentation_basis,
        workflow_bundle=workflow_bundle,
        member=member,
    )
    behavior_match = _resolve_behavior_segment_match(member)
    standard_content_text = _normalized_text(node.get("standard_content_text"))
    node_bindings = [dict(item) for item in (node.get("agent_bindings") or workflow_bundle.get("agent_bindings") or [])]

    if content_mode == "manual_layered":
        content = _select_manual_layered_content(
            node=node,
            segment_match=segment_match,
        )
        return {
            **content,
            "segment_match": segment_match,
            "behavior_match": behavior_match,
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }

    if content_mode == "standard_direct":
        return {
            "content_text": standard_content_text,
            "content_source": "standard_content",
            "fallback_reason": "",
            "segment_match": segment_match,
            "behavior_match": behavior_match,
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }

    effective_segment_match = behavior_match if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR else segment_match
    binding = _select_agent_binding(
        generation_mode=generation_mode,
        segmentation_basis=segmentation_basis,
        bindings=node_bindings,
        segment_match=effective_segment_match,
    )
    generated = _generate_content_with_agent(
        member=member,
        workflow_bundle=workflow_bundle,
        node=node,
        agent_binding=binding,
        standard_content_text=standard_content_text,
        segment_match=segment_match,
        behavior_match=behavior_match,
        request_id=execution_request_id,
        generation_source="automation_conversion_workflow_execution",
    )
    return {
        **generated,
        "segment_match": segment_match,
        "behavior_match": behavior_match,
    }


def _timed_sequence_nodes(
    workflow_bundle: dict[str, Any],
    *,
    target_audience_code: str,
    trigger_mode: str,
) -> list[dict[str, Any]]:
    nodes = [
        dict(item)
        for item in (workflow_bundle.get("nodes") or [])
        if bool(item.get("enabled"))
        and _node_trigger_mode(dict(item)) == _normalized_text(trigger_mode)
        and _normalized_text(item.get("target_audience_code")) == _normalized_text(target_audience_code)
    ]
    return sorted(
        nodes,
        key=lambda item: (
            int(item.get("day_offset") or 1),
            _normalized_text(item.get("send_time")) or "00:00",
            int(item.get("position_index") or 0),
            int(item.get("id") or 0),
        ),
    )


def _timed_history_index(
    *,
    workflow_id: int,
    audience_rows: list[dict[str, Any]],
    trigger_modes: list[str],
) -> dict[str, dict[int, set[Any]]]:
    history_rows = workflow_repo.list_workflow_sent_timed_execution_history_rows(
        workflow_id=int(workflow_id),
        audience_entry_ids=[int(row.get("id") or 0) for row in audience_rows],
        trigger_modes=trigger_modes,
    )
    sent_node_ids_by_entry: dict[int, set[int]] = {}
    sent_dates_by_entry: dict[int, set[str]] = {}
    for row in history_rows:
        entry_id = int(row.get("audience_entry_id") or 0)
        node_id = int(row.get("node_id") or 0)
        scheduled_date = _date_text(row.get("scheduled_for"))
        if entry_id <= 0 or node_id <= 0:
            continue
        sent_node_ids_by_entry.setdefault(entry_id, set()).add(node_id)
        if scheduled_date:
            sent_dates_by_entry.setdefault(entry_id, set()).add(scheduled_date)
    return {
        "sent_node_ids_by_entry": sent_node_ids_by_entry,
        "sent_dates_by_entry": sent_dates_by_entry,
    }


def _current_daily_recurring_node_id(
    *,
    sequence_nodes: list[dict[str, Any]],
    entered_at: str,
    scheduled_for: str,
) -> int | None:
    for sequence_node in sequence_nodes:
        node_day_index = _node_day_index(
            entered_at=entered_at,
            send_time=_normalized_text(sequence_node.get("send_time")),
            scheduled_for=scheduled_for,
        )
        if node_day_index == int(sequence_node.get("day_offset") or 1):
            return int(sequence_node.get("id") or 0) or None
    return None


def _base_execution_diagnostics(*, execution: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": int(execution.get("workflow_id") or 0),
        "node_id": int(node.get("id") or 0),
        "trigger_mode": _node_trigger_mode(node),
        "scheduled_for": _normalized_text(execution.get("scheduled_for")),
        "candidate_audience_total": 0,
        "day_offset_miss_count": 0,
        "audience_miss_count": 0,
        "recipient_filter_miss_count": 0,
        "recipient_filter_usage_source_unavailable_count": 0,
        "recipient_filter_usage_source_not_found_count": 0,
        "recipient_filter_usage_phone_missing_count": 0,
        "recipient_filter_behavior_tier_miss_count": 0,
        "recipient_filter_member_identity_missing_count": 0,
        "already_sent_count": 0,
        "sent_today_count": 0,
        "sequence_wait_count": 0,
        "inserted_pending_count": 0,
    }


def _update_recipient_filter_diagnostics(diagnostics: dict[str, Any], filter_result: dict[str, Any]) -> None:
    if bool(filter_result.get("matched")):
        return
    diagnostics["recipient_filter_miss_count"] = int(diagnostics.get("recipient_filter_miss_count") or 0) + 1
    reason = _normalized_text(filter_result.get("reason"))
    if reason in {"message_activity_db_not_configured", "usage_source_unavailable"}:
        diagnostics["recipient_filter_usage_source_unavailable_count"] = int(
            diagnostics.get("recipient_filter_usage_source_unavailable_count") or 0
        ) + 1
        return
    if reason == "usage_source_not_found":
        diagnostics["recipient_filter_usage_source_not_found_count"] = int(
            diagnostics.get("recipient_filter_usage_source_not_found_count") or 0
        ) + 1
        return
    if reason == "usage_phone_missing":
        diagnostics["recipient_filter_usage_phone_missing_count"] = int(
            diagnostics.get("recipient_filter_usage_phone_missing_count") or 0
        ) + 1
        return
    if reason == "member_identity_missing":
        diagnostics["recipient_filter_member_identity_missing_count"] = int(
            diagnostics.get("recipient_filter_member_identity_missing_count") or 0
        ) + 1
        return
    diagnostics["recipient_filter_behavior_tier_miss_count"] = int(
        diagnostics.get("recipient_filter_behavior_tier_miss_count") or 0
    ) + 1


def _upsert_node_execution_candidates(
    *,
    execution: dict[str, Any],
    node: dict[str, Any],
    workflow_bundle: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    scheduled_for = _normalized_text(execution.get("scheduled_for"))
    audience_rows = workflow_repo.list_current_member_audience_rows(_normalized_text(node.get("target_audience_code")))
    audience_map: dict[int, dict[str, Any]] = {}
    diagnostics = _base_execution_diagnostics(execution=execution, node=node)
    trigger_mode = _node_trigger_mode(node)
    sequence_nodes = _timed_sequence_nodes(
        workflow_bundle,
        target_audience_code=_normalized_text(node.get("target_audience_code")),
        trigger_mode=trigger_mode,
    ) if trigger_mode in {NODE_TRIGGER_MODE_SCHEDULED, NODE_TRIGGER_MODE_DAILY_RECURRING} else []
    history_index = _timed_history_index(
        workflow_id=int(execution.get("workflow_id") or 0),
        audience_rows=audience_rows,
        trigger_modes=[trigger_mode],
    ) if trigger_mode in {NODE_TRIGGER_MODE_SCHEDULED, NODE_TRIGGER_MODE_DAILY_RECURRING} else {"sent_node_ids_by_entry": {}, "sent_dates_by_entry": {}}
    scheduled_date = _date_text(scheduled_for)
    for row in audience_rows:
        entry_id = int(row.get("id") or 0)
        diagnostics["candidate_audience_total"] += 1
        audience_map[entry_id] = dict(row)
        if trigger_mode in {NODE_TRIGGER_MODE_SCHEDULED, NODE_TRIGGER_MODE_DAILY_RECURRING}:
            node_day_index = _node_day_index(
                entered_at=_normalized_text(row.get("entered_at")),
                send_time=_normalized_text(node.get("send_time")),
                scheduled_for=scheduled_for,
            )
            if node_day_index != int(node.get("day_offset") or 1):
                diagnostics["day_offset_miss_count"] += 1
                continue
            sent_dates = set((history_index.get("sent_dates_by_entry") or {}).get(entry_id) or set())
            if scheduled_date and scheduled_date in sent_dates:
                diagnostics["sent_today_count"] += 1
                continue
            if trigger_mode == NODE_TRIGGER_MODE_SCHEDULED:
                sent_node_ids = set((history_index.get("sent_node_ids_by_entry") or {}).get(entry_id) or set())
                if int(node.get("id") or 0) in sent_node_ids:
                    diagnostics["already_sent_count"] += 1
                    continue
            elif trigger_mode == NODE_TRIGGER_MODE_DAILY_RECURRING:
                current_recurring_node_id = _current_daily_recurring_node_id(
                    sequence_nodes=sequence_nodes,
                    entered_at=_normalized_text(row.get("entered_at")),
                    scheduled_for=scheduled_for,
                )
                if current_recurring_node_id != int(node.get("id") or 0):
                    diagnostics["sequence_wait_count"] += 1
                    continue
        member = dict(row.get("member") or {})
        recipient_filter_result = _member_workflow_recipient_filter_result(member, workflow_bundle)
        if not bool(recipient_filter_result.get("matched")):
            _update_recipient_filter_diagnostics(diagnostics, recipient_filter_result)
            continue
        workflow_repo.insert_workflow_execution_item_row(
            {
                "execution_id": int(execution.get("id") or 0),
                "workflow_id": int(execution.get("workflow_id") or 0),
                "node_id": int(execution.get("node_id") or 0),
                "member_id": int(row.get("member_id") or 0),
                "audience_entry_id": entry_id,
                "external_contact_id": _normalized_text((row.get("member") or {}).get("external_contact_id")),
                "rendered_content_text": "",
                "content_snapshot_json": {},
                "agent_code": "",
                "agent_run_id": "",
                "agent_output_id": "",
                "status": "pending",
                "error_message": "",
                "send_record_id": None,
                "sent_at": "",
            }
        )
        diagnostics["inserted_pending_count"] += 1
    return audience_map, diagnostics


def _execution_summary_from_items(items: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    success_count = sum(1 for item in items if _normalized_text(item.get("status")) == "sent")
    skipped_count = sum(1 for item in items if _normalized_text(item.get("status")) == "skipped")
    failed_count = sum(1 for item in items if _normalized_text(item.get("status")) == "failed")
    pending_count = sum(1 for item in items if _normalized_text(item.get("status")) in {"pending", "prepared"})
    content_missing_count = sum(1 for item in items if _normalized_text(item.get("error_message")) == "rendered_content_empty")
    missing_external_contact_id_count = sum(1 for item in items if _normalized_text(item.get("error_message")) == "missing_external_contact_id")
    owner_staff_id_missing_count = sum(
        1
        for item in items
        if bool(dict(item.get("content_snapshot_json") or {}).get("owner_staff_id_missing"))
    )
    segment_or_content_miss_count = sum(
        1
        for item in items
        if _normalized_text(dict(item.get("content_snapshot_json") or {}).get("fallback_reason"))
        in {
            "segment_content_missing",
            "segment_not_matched",
            "segmentation_none",
            "usage_phone_missing",
            "usage_source_not_found",
            "message_activity_db_not_configured",
        }
    )
    send_api_failed_count = sum(
        1
        for item in items
        if _normalized_text(item.get("status")) == "failed"
        and _normalized_text(item.get("error_message"))
        and _normalized_text(item.get("error_message")) not in {"rendered_content_empty", "missing_external_contact_id"}
    )
    if pending_count > 0:
        status = "running"
    elif success_count and (failed_count or skipped_count):
        status = "partial_failed"
    elif failed_count and not success_count and not skipped_count:
        status = "failed"
    else:
        status = "finished"
    return status, {
        "total_count": len(items),
        "success_count": success_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "segment_or_content_miss_count": segment_or_content_miss_count,
        "content_missing_count": content_missing_count,
        "missing_external_contact_id_count": missing_external_contact_id_count,
        "owner_staff_id_missing_count": owner_staff_id_missing_count,
        "send_api_failed_count": send_api_failed_count,
    }


def _zero_hit_reasons(diagnostics: dict[str, Any], counters: dict[str, int]) -> list[str]:
    reasons: list[str] = []
    trigger_mode = _normalized_text(diagnostics.get("trigger_mode"))
    if int(diagnostics.get("candidate_audience_total") or 0) <= 0:
        reasons.append("current_audience_empty")
    if int(counters.get("total_count") or 0) > 0:
        return reasons
    has_specific_recipient_reason = any(
        int(diagnostics.get(counter_key) or 0) > 0
        for counter_key in (
            "recipient_filter_usage_source_unavailable_count",
            "recipient_filter_usage_source_not_found_count",
            "recipient_filter_usage_phone_missing_count",
            "recipient_filter_member_identity_missing_count",
            "recipient_filter_behavior_tier_miss_count",
        )
    )
    reason_map = (
        ("day_offset_miss_count", "day_offset_not_due"),
        ("recipient_filter_usage_source_unavailable_count", "message_activity_db_not_configured"),
        ("recipient_filter_usage_source_not_found_count", "usage_source_not_found"),
        ("recipient_filter_usage_phone_missing_count", "usage_phone_missing"),
        ("recipient_filter_member_identity_missing_count", "member_identity_missing"),
        ("recipient_filter_behavior_tier_miss_count", "recipient_filter_not_matched"),
        ("recipient_filter_miss_count", "recipient_filter_not_matched"),
        ("already_sent_count", "node_already_sent_for_current_audience_entry"),
        ("sent_today_count", "workflow_already_sent_today"),
        (
            "sequence_wait_count",
            "waiting_for_current_recurring_stage" if trigger_mode == NODE_TRIGGER_MODE_DAILY_RECURRING else "waiting_for_earlier_scheduled_node",
        ),
    )
    for counter_key, reason_code in reason_map:
        if counter_key == "recipient_filter_miss_count" and has_specific_recipient_reason:
            continue
        if int(diagnostics.get(counter_key) or 0) > 0:
            reasons.append(reason_code)
    if not reasons:
        reasons.append("no_execution_items_created")
    return reasons


def _execution_summary_json(
    *,
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    diagnostics: dict[str, Any],
    counters: dict[str, int],
) -> dict[str, Any]:
    return {
        "workflow_code": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_code")),
        "workflow_name": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_name")),
        "node_code": _normalized_text(node.get("node_code")),
        "node_name": _normalized_text(node.get("node_name")),
        "trigger_mode": _node_trigger_mode(node),
        "scheduled_for": _normalized_text(diagnostics.get("scheduled_for")),
        "diagnostics": diagnostics,
        "result": counters,
        "zero_hit_reasons": _zero_hit_reasons(diagnostics, counters),
    }


def _collect_execution_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(result.get("execution"), dict) and result.get("execution"):
        return [dict(result.get("execution") or {})]
    return [dict(item) for item in (result.get("executions") or []) if isinstance(item, dict)]


def _run_due_node(
    *,
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    operator_id: str,
) -> dict[str, Any]:
    trigger_mode = _node_trigger_mode(node)
    if trigger_mode == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        return _run_immediate_node(
            workflow_bundle=workflow_bundle,
            node=node,
            operator_id=operator_id,
        )

    now_dt = _now_dt()
    scheduled_for_dt = now_dt.replace(
        hour=_parse_send_time(node.get("send_time"))[0],
        minute=_parse_send_time(node.get("send_time"))[1],
        second=0,
        microsecond=0,
    )
    if now_dt < scheduled_for_dt:
        result = {
            "ok": True,
            "status": "not_due_yet",
            "node_id": int(node.get("id") or 0),
            "trigger_mode": trigger_mode,
            "scheduled_for": scheduled_for_dt.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _log_runtime_event("node_not_due_yet", result)
        return result
    scheduled_for = scheduled_for_dt.strftime("%Y-%m-%d %H:%M:%S")
    execution_key = f"acwf-{int((workflow_bundle.get('workflow') or {}).get('id') or 0)}-{int(node.get('id') or 0)}-{scheduled_for_dt.strftime('%Y%m%d%H%M')}"
    execution = workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
    if not execution:
        execution = workflow_repo.insert_workflow_execution_row(
            {
                "execution_id": execution_key,
                "program_id": int((workflow_bundle.get("workflow") or {}).get("program_id") or 0) or None,
                "workflow_id": int((workflow_bundle.get("workflow") or {}).get("id") or 0),
                "node_id": int(node.get("id") or 0),
                "trigger_type": "daily_recurring_poll" if trigger_mode == NODE_TRIGGER_MODE_DAILY_RECURRING else "scheduled_poll",
                "audience_code": _normalized_text(node.get("target_audience_code")),
                "scheduled_for": scheduled_for,
                "status": "pending",
                "total_count": 0,
                "success_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "summary_json": {},
                "finished_at": "",
            }
        ) or workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
    if not execution:
        return {"ok": False, "status": "execution_create_failed", "node_id": int(node.get("id") or 0)}
    if _normalized_text(execution.get("status")) in _FINAL_EXECUTION_STATUSES and not _execution_can_recompute_day_offset_miss(execution):
        result = {
            "ok": True,
            "status": "already_processed",
            "execution_id": _normalized_text(execution.get("execution_id")),
            "node_id": int(node.get("id") or 0),
            "execution": execution,
        }
        _log_runtime_event("node_already_processed", result)
        return result
    if _normalized_text(execution.get("status")) == "running":
        result = {
            "ok": True,
            "status": "already_enqueued",
            "execution_id": _normalized_text(execution.get("execution_id")),
            "node_id": int(node.get("id") or 0),
            "execution": execution,
        }
        _log_runtime_event("node_already_enqueued", result)
        return result

    execution = workflow_repo.update_workflow_execution_row(
        int(execution["id"]),
        {
            **execution,
            "status": "running",
            "scheduled_for": scheduled_for,
            "finished_at": "",
            "summary_json": dict(execution.get("summary_json") or {}),
        },
    )
    audience_map, diagnostics = _upsert_node_execution_candidates(execution=execution, node=node, workflow_bundle=workflow_bundle)
    _log_runtime_event(
        "scheduled_node_candidates",
        {
            "workflow_id": int(execution.get("workflow_id") or 0),
            "node_id": int(node.get("id") or 0),
            "trigger_mode": _node_trigger_mode(node),
            "scheduled_for": scheduled_for,
            **diagnostics,
        },
    )
    execution_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
    pending_externals = [
        _normalized_text(item.get("external_contact_id"))
        for item in execution_items
        if _normalized_text(item.get("status")) == "pending" and _normalized_text(item.get("external_contact_id"))
    ]
    if not pending_externals:
        # 无候选人 — 立刻标 finished，避免永远卡在 running
        counters = {"total_count": 0, "success_count": 0, "skipped_count": 0, "failed_count": 0,
                    "pending_count": 0, "missing_external_contact_id_count": 0,
                    "owner_staff_id_missing_count": 0, "send_api_failed_count": 0,
                    "segment_or_content_miss_count": 0, "content_missing_count": 0}
        summary_json = _execution_summary_json(
            workflow_bundle=workflow_bundle, node=node, diagnostics=diagnostics, counters=counters,
        )
        workflow_repo.update_workflow_execution_row(
            int(execution["id"]),
            {
                **execution,
                "status": "finished",
                "total_count": 0,
                "success_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "finished_at": _iso_now(),
                "summary_json": summary_json,
            },
        )
        result = {
            "ok": True,
            "status": "finished_no_candidates",
            "execution_id": _normalized_text(execution.get("execution_id")),
            "node_id": int(node.get("id") or 0),
            "pending_count": 0,
            "execution": execution,
        }
        _log_runtime_event("scheduled_node_no_candidates", result)
        return result

    # 入队前把完整 summary（含 diagnostics / result / zero_hit_reasons）快照到
    # execution，方便监控页和测试立即读到；worker 执行后会用最终结果覆盖。
    _enqueue_counters = _execution_summary_from_items(execution_items)[1]
    _enqueue_summary = _execution_summary_json(
        workflow_bundle=workflow_bundle,
        node=node,
        diagnostics=diagnostics,
        counters=_enqueue_counters,
    )
    workflow_repo.update_workflow_execution_row(
        int(execution["id"]),
        {
            **execution,
            "status": "running",
            "total_count": _enqueue_counters["total_count"],
            "summary_json": _enqueue_summary,
        },
    )

    from ..broadcast_jobs import service as queue_service
    from ..broadcast_jobs import repo as queue_repo

    # 去重：如果预排期的 job 已存在（queued/claimed），不重复入队
    exec_id_str = str(execution.get("execution_id") or "")
    existing = queue_repo.fetch_jobs_filtered(
        statuses=["queued", "claimed"],
        source_types=["workflow"],
        limit=50,
    )
    already_scheduled = any(
        str(j.get("source_id") or "") == exec_id_str for j in existing
    )
    if not already_scheduled:
        queue_service.enqueue_job(
            source_type="workflow",
            source_id=exec_id_str,
            source_table="automation_workflow_executions",
            scheduled_for=datetime.now(),
            target_external_userids=pending_externals,
            target_summary=f"workflow node={int(node.get('id') or 0)} — {len(pending_externals)} 人",
            content_type="private_message",
            content_payload={
                "execution_id": _normalized_text(execution.get("execution_id")),
                "workflow_id": int(execution.get("workflow_id") or 0),
                "node_id": int(node.get("id") or 0),
                "operator_id": operator_id,
            },
            content_summary=_normalized_text(node.get("standard_content_text"))[:200],
        )
    result = {
        "ok": True,
        "status": "enqueued",
        "execution_id": _normalized_text(execution.get("execution_id")),
        "node_id": int(node.get("id") or 0),
        "pending_count": len(pending_externals),
    }
    _log_runtime_event("scheduled_node_enqueued", result)
    return result


def _run_immediate_node(
    *,
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    operator_id: str,
) -> dict[str, Any]:
    audience_rows = workflow_repo.list_current_member_audience_rows(_normalized_text(node.get("target_audience_code")))
    processed_executions: list[dict[str, Any]] = []
    diagnostics = {
        "workflow_id": int((workflow_bundle.get("workflow") or {}).get("id") or 0),
        "node_id": int(node.get("id") or 0),
        "trigger_mode": _node_trigger_mode(node),
        "scheduled_for": "",
        "candidate_audience_total": len(audience_rows),
        "day_offset_miss_count": 0,
        "audience_miss_count": 0,
        "recipient_filter_miss_count": 0,
        "recipient_filter_usage_source_unavailable_count": 0,
        "recipient_filter_usage_source_not_found_count": 0,
        "recipient_filter_usage_phone_missing_count": 0,
        "recipient_filter_behavior_tier_miss_count": 0,
        "recipient_filter_member_identity_missing_count": 0,
        "already_sent_count": 0,
        "sent_today_count": 0,
        "sequence_wait_count": 0,
        "inserted_pending_count": 0,
    }
    for audience_entry in audience_rows:
        audience_entry_id = int(audience_entry.get("id") or 0)
        if audience_entry_id <= 0:
            continue
        recipient_filter_result = _member_workflow_recipient_filter_result(dict(audience_entry.get("member") or {}), workflow_bundle)
        if not bool(recipient_filter_result.get("matched")):
            _update_recipient_filter_diagnostics(diagnostics, recipient_filter_result)
            continue
        execution_key = (
            f"acwf-immediate-"
            f"{int((workflow_bundle.get('workflow') or {}).get('id') or 0)}-"
            f"{int(node.get('id') or 0)}-"
            f"{audience_entry_id}"
        )
        execution = workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
        if not execution:
            execution = workflow_repo.insert_workflow_execution_row(
                {
                    "execution_id": execution_key,
                    "program_id": int((workflow_bundle.get("workflow") or {}).get("program_id") or 0) or None,
                    "workflow_id": int((workflow_bundle.get("workflow") or {}).get("id") or 0),
                    "node_id": int(node.get("id") or 0),
                    "trigger_type": "scheduled_poll",
                    "audience_code": _normalized_text(node.get("target_audience_code")),
                    "scheduled_for": _normalized_text(audience_entry.get("entered_at")) or _iso_now(),
                    "status": "pending",
                    "total_count": 0,
                    "success_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "summary_json": {"audience_entry_id": audience_entry_id},
                    "finished_at": "",
                }
            ) or workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
        if not execution:
            continue
        if _normalized_text(execution.get("status")) in _FINAL_EXECUTION_STATUSES:
            diagnostics["already_sent_count"] += 1
            processed_executions.append(execution)
            continue
        if _normalized_text(execution.get("status")) == "running":
            diagnostics["already_sent_count"] += 1
            processed_executions.append(execution)
            continue

        execution = workflow_repo.update_workflow_execution_row(
            int(execution["id"]),
            {
                **execution,
                "trigger_type": "scheduled_poll",
                "status": "running",
                "scheduled_for": _normalized_text(audience_entry.get("entered_at")) or _iso_now(),
                "finished_at": "",
                "summary_json": {
                    **dict(execution.get("summary_json") or {}),
                    "audience_entry_id": audience_entry_id,
                },
            },
        )
        new_item = workflow_repo.insert_workflow_execution_item_row(
            {
                "execution_id": int(execution.get("id") or 0),
                "workflow_id": int(execution.get("workflow_id") or 0),
                "node_id": int(execution.get("node_id") or 0),
                "member_id": int(audience_entry.get("member_id") or 0),
                "audience_entry_id": audience_entry_id,
                "external_contact_id": _normalized_text((audience_entry.get("member") or {}).get("external_contact_id")),
                "rendered_content_text": "",
                "content_snapshot_json": {},
                "agent_pool_id": None,
                "agent_run_id": "",
                "agent_output_id": "",
                "status": "pending",
                "error_message": "",
                "send_record_id": None,
                "sent_at": "",
            }
        )
        diagnostics["inserted_pending_count"] += 1

        # ── 立即渲染内容 ──
        # 内容决策是确定性的（不依赖外部 API），在入队前完成：
        #   - 渲染成功 → 更新 item 保持 pending，入队给 broadcast worker 真发
        #   - 渲染为空 → 标 failed，跳过入队
        _imm_member = dict(audience_entry.get("member") or {})
        _imm_rendered = _render_node_content(
            member=_imm_member,
            workflow_bundle=workflow_bundle,
            node=node,
            execution_request_id=f"workflow-node-{int(node['id'])}-item-{int(new_item.get('id') or 0)}",
        )
        _imm_content = _normalized_text(_imm_rendered.get("content_text"))
        _imm_snapshot = {
            "workflow_code": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_code")),
            "workflow_name": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_name")),
            "node_code": _normalized_text(node.get("node_code")),
            "node_name": _normalized_text(node.get("node_name")),
            "node_content_mode": _node_content_mode(node, workflow_bundle),
            "node_generation_mode": _node_generation_mode(node, workflow_bundle),
            "node_segmentation_basis": _node_segmentation_basis(node, workflow_bundle),
            "workflow_generation_mode": _normalized_text((workflow_bundle.get("workflow") or {}).get("generation_mode")),
            "workflow_segmentation_basis": _normalized_text((workflow_bundle.get("workflow") or {}).get("segmentation_basis")),
            "standard_content_text": _normalized_text(node.get("standard_content_text")),
            "rendered_content_text": _imm_content,
            "content_source": _normalized_text(_imm_rendered.get("content_source")),
            "fallback_reason": _normalized_text(_imm_rendered.get("fallback_reason")),
            "agent_code": _normalized_text(_imm_rendered.get("agent_code")),
            "segment_match": dict(_imm_rendered.get("segment_match") or {}),
            "behavior_match": dict(_imm_rendered.get("behavior_match") or {}),
        }

        external_userid = _normalized_text((audience_entry.get("member") or {}).get("external_contact_id"))

        if not external_userid:
            workflow_repo.update_workflow_execution_item_row(
                int(new_item["id"]),
                {
                    **new_item,
                    "status": "skipped",
                    "error_message": "missing_external_contact_id",
                    "content_snapshot_json": _imm_snapshot,
                    "rendered_content_text": _imm_content,
                },
            )
            workflow_repo.update_workflow_execution_row(
                int(execution["id"]),
                {**execution, "status": "finished", "finished_at": _iso_now(),
                 "summary_json": {"note": "no_external_userid"}},
            )
            processed_executions.append(execution)
            continue

        if not _imm_content:
            # 内容为空 — 标 failed，不入队
            workflow_repo.update_workflow_execution_item_row(
                int(new_item["id"]),
                {
                    **new_item,
                    "status": "failed",
                    "error_message": "rendered_content_empty",
                    "content_snapshot_json": _imm_snapshot,
                    "rendered_content_text": "",
                    "agent_code": _imm_rendered.get("agent_code"),
                    "agent_run_id": _imm_rendered.get("agent_run_id"),
                    "agent_output_id": _imm_rendered.get("agent_output_id"),
                },
            )
            processed_executions.append(execution)
            continue

        # 内容已渲染 — 更新 item 并入队给 broadcast worker 真发
        workflow_repo.update_workflow_execution_item_row(
            int(new_item["id"]),
            {
                **new_item,
                "rendered_content_text": _imm_content,
                "content_snapshot_json": _imm_snapshot,
                "agent_code": _imm_rendered.get("agent_code"),
                "agent_run_id": _imm_rendered.get("agent_run_id"),
                "agent_output_id": _imm_rendered.get("agent_output_id"),
            },
        )

        from ..broadcast_jobs import service as queue_service

        queue_service.enqueue_job(
            source_type="workflow",
            source_id=execution_key,
            source_table="automation_workflow_executions",
            scheduled_for=datetime.now(),
            target_external_userids=[external_userid],
            target_summary=f"workflow immediate node={int(node.get('id') or 0)}",
            content_type="private_message",
            content_payload={
                "execution_id": execution_key,
                "workflow_id": int(execution.get("workflow_id") or 0),
                "node_id": int(node.get("id") or 0),
                "operator_id": operator_id,
            },
            content_summary=_imm_content[:200],
        )
        processed_executions.append(execution)
    result = {
        "ok": True,
        "status": "finished" if processed_executions else "no_candidates",
        "node_id": int(node.get("id") or 0),
        "executions": processed_executions,
        "summary": _execution_summary_json(
            workflow_bundle=workflow_bundle,
            node=node,
            diagnostics=diagnostics,
            counters=_execution_summary_from_items(
                [
                    item
                    for execution_row in processed_executions
                    for item in workflow_repo.list_workflow_execution_item_rows(int(execution_row.get("id") or 0))
                ]
            )[1],
        ),
    }
    _log_runtime_event("immediate_node_finished", result["summary"])
    return result


def run_pre_scheduled_workflow_node(*, workflow_id: int, node_id: int) -> dict[str, Any]:
    """预排期 workflow job 到期后由 worker 调用 — 走完整 node 执行流程。

    与 _run_due_node 相同逻辑，但跳过"时间未到"检查（worker 已确保到期才 claim）。
    创建 execution → 找候选人 → 入队真发 job（或直接返回 no-candidates）。
    """
    workflow_bundle = get_conversion_workflow_model_bundle(workflow_id)
    node = None
    for n in (workflow_bundle.get("nodes") or []):
        if int(n.get("id") or 0) == node_id:
            node = dict(n)
            break
    if not node:
        return {"ok": False, "error": f"node {node_id} not found in workflow {workflow_id}"}
    if not bool(node.get("enabled")):
        return {"ok": True, "sent_count": 0, "failed_count": 0, "status": "node_disabled"}

    # 调用 _run_due_node，它内部会判断时间 — 预排期 job 到期执行时 now >= scheduled 必然成立
    result = _run_due_node(
        workflow_bundle=workflow_bundle,
        node=node,
        operator_id="automation_conversion_workflow_runner",
    )
    # 如果 _run_due_node 返回 enqueued，说明它创建了新的 broadcast_job 来真发
    # 此处 pre-scheduled job 本身视为成功（真发由新 job 接管）
    status = _normalized_text(result.get("status")) if isinstance(result, dict) else ""
    if status in ("enqueued", "already_processed", "already_enqueued"):
        return {"ok": True, "sent_count": 0, "failed_count": 0, "status": status}
    if status == "not_due_yet":
        # 理论上不该发生（worker 到期才 claim），但防御性处理
        return {"ok": True, "sent_count": 0, "failed_count": 0, "status": "not_due_yet"}
    return result


def run_due_conversion_workflows(*, operator_id: str = "", operator_type: str = "system") -> dict[str, Any]:
    sync_summary = sync_all_conversion_member_audiences()
    scanned_workflow_count = 0
    processed_node_count = 0
    execution_items: list[dict[str, Any]] = []
    for workflow_row in workflow_repo.list_workflow_rows(include_archived=False, status=WORKFLOW_STATUS_ACTIVE):
        scanned_workflow_count += 1
        workflow_bundle = get_conversion_workflow_model_bundle(int(workflow_row["id"]))
        for node in workflow_bundle.get("nodes") or []:
            if not bool(node.get("enabled")):
                continue
            processed_node_count += 1
            execution_items.append(
                _run_due_node(
                    workflow_bundle=workflow_bundle,
                    node=dict(node),
                    operator_id=_normalized_text(operator_id) or "automation_conversion_workflow_runner",
                )
            )
    execution_rows = [
        execution_row
        for result in execution_items
        for execution_row in _collect_execution_rows(result)
    ]
    total_success_count = sum(int(item.get("success_count") or 0) for item in execution_rows)
    total_skipped_count = sum(int(item.get("skipped_count") or 0) for item in execution_rows)
    total_failed_count = sum(int(item.get("failed_count") or 0) for item in execution_rows)
    get_db().commit()

    # 阶段 2：为明天要跑的 workflow node 预排期到 broadcast_jobs（让队列页展示排期）
    future_enqueued = _pre_enqueue_future_workflow_nodes()

    result = {
        "ok": True,
        "operator_type": _normalized_text(operator_type) or "system",
        "operator_id": _normalized_text(operator_id) or "automation_conversion_workflow_runner",
        "sync_summary": sync_summary,
        "scanned_workflow_count": scanned_workflow_count,
        "processed_node_count": processed_node_count,
        "execution_count": len(execution_rows),
        "future_enqueued": future_enqueued,
        "total_success_count": total_success_count,
        "total_skipped_count": total_skipped_count,
        "total_failed_count": total_failed_count,
        "executions": execution_items,
    }
    _log_runtime_event(
        "run_due_conversion_workflows_finished",
        {
            "operator_id": result["operator_id"],
            "operator_type": result["operator_type"],
            "sync_summary": sync_summary,
            "scanned_workflow_count": scanned_workflow_count,
            "processed_node_count": processed_node_count,
            "execution_count": len(execution_rows),
            "future_enqueued": future_enqueued,
            "total_success_count": total_success_count,
            "total_skipped_count": total_skipped_count,
            "total_failed_count": total_failed_count,
        },
    )
    return result


def _pre_enqueue_future_workflow_nodes() -> int:
    """为明天（下一个自然日）将触发的 workflow node 预排期到 broadcast_jobs。

    让队列页提前展示"明天 14:00 将执行 xxx 工作流"。到时间后 worker 领取
    预排期 job，handler 走正常 _run_due_node 流程（现场决策候选人）。

    滚动机制：每次 cron 跑完今天的 node 后调用此函数，为下一天排期。
    明天 cron 跑后又为后天排期，依此类推。
    """
    from ..broadcast_jobs import service as queue_service
    from ..broadcast_jobs import repo as queue_repo

    tomorrow = _now_dt() + timedelta(days=1)
    enqueued = 0

    # 已有的 queued workflow jobs → 用于去重
    existing_jobs = queue_repo.fetch_jobs_filtered(
        statuses=["queued", "claimed"],
        source_types=["workflow"],
        limit=200,
    )
    existing_source_ids = {str(j.get("source_id") or "") for j in existing_jobs}

    for workflow_row in workflow_repo.list_workflow_rows(include_archived=False, status=WORKFLOW_STATUS_ACTIVE):
        workflow_bundle = get_conversion_workflow_model_bundle(int(workflow_row["id"]))
        workflow = workflow_bundle.get("workflow") or {}
        for node in workflow_bundle.get("nodes") or []:
            if not bool(node.get("enabled")):
                continue
            trigger_mode = _node_trigger_mode(node)
            # audience_entered 不走定时，跳过
            if trigger_mode == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
                continue
            # 计算明天该 node 的 scheduled_for
            h, m = _parse_send_time(node.get("send_time"))
            scheduled_for_dt = tomorrow.replace(hour=h, minute=m, second=0, microsecond=0)
            # 构造 execution_id（与 _run_due_node 一致）
            execution_key = (
                f"acwf-{int(workflow.get('id') or 0)}-"
                f"{int(node.get('id') or 0)}-"
                f"{scheduled_for_dt.strftime('%Y%m%d%H%M')}"
            )
            if execution_key in existing_source_ids:
                continue
            # 估算候选人数（当前 audience pool 大小，实际到时才确定）
            audience_code = _normalized_text(node.get("target_audience_code"))
            audience_rows = workflow_repo.list_current_member_audience_rows(audience_code)
            estimated_count = len(audience_rows)
            if estimated_count == 0:
                continue
            node_name = _normalized_text(node.get("node_name")) or f"node-{node.get('id')}"
            workflow_name = _normalized_text(workflow.get("workflow_name")) or f"workflow-{workflow.get('id')}"
            queue_service.enqueue_job(
                source_type="workflow",
                source_id=execution_key,
                source_table="automation_workflow_executions",
                scheduled_for=scheduled_for_dt.strftime("%Y-%m-%d %H:%M:%S"),
                target_external_userids=[],
                target_summary=f"workflow node={int(node.get('id') or 0)} — ~{estimated_count} 人",
                content_type="private_message",
                content_payload={
                    "workflow_id": int(workflow.get("id") or 0),
                    "node_id": int(node.get("id") or 0),
                    "pre_scheduled": True,
                },
                content_summary=f"[{workflow_name}] {node_name}",
                allow_empty_targets=True,
            )
            existing_source_ids.add(execution_key)
            enqueued += 1

    return enqueued
