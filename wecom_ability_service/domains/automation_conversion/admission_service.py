from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ...db import get_db
from . import program_repo, repo, workflow_repo
from ._repo_helpers import _fetchall_dicts, _fetchone_dict, _json_dumps, _normalized_text
from .channel_binding_service import list_active_bindings_for_channel
from .service import (
    DEFAULT_OWNER_STAFF_ID,
    POOL_CONVERTED,
    POOL_OPERATING,
    POOL_PENDING_QUESTIONNAIRE,
    SOURCE_TYPE_QRCODE,
    _iso_now,
)
from .workflow_definitions import (
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    ENTRY_REASON_AUDIENCE_RULE_PASSED,
    ENTRY_REASON_CONVERSION_PRODUCT_PAID,
    ENTRY_REASON_ORDER_REVIEW_PENDING,
    ENTRY_REASON_QUESTIONNAIRE_REVIEW_PENDING,
    STAGE_CONVERTED,
    STAGE_OPERATING,
    STAGE_ORDER_REVIEW,
    STAGE_QUESTIONNAIRE_REVIEW,
)

ADMISSION_ACCEPTED = "accepted"
ADMISSION_WAITING = "waiting"
ADMISSION_CONVERTED = "converted"
ADMISSION_REJECTED = "rejected"
ADMISSION_DUPLICATE_ACTIVE = "duplicate_active"
ADMISSION_MANUAL_REVIEW = "manual_review"
ADMISSION_STANDALONE_CHANNEL = "standalone_channel"

VALID_AUDIENCES = {AUDIENCE_PENDING_QUESTIONNAIRE, AUDIENCE_OPERATING, AUDIENCE_CONVERTED}
BLOCK_AUDIENCE_ENTRY_RULE = "audience_entry_rule"
BLOCK_PUBLISH_STATE = "publish_state"
CHANNEL_ENTER_TRIGGERS = {"channel_enter", "qrcode_enter", "customer_acquisition_enter"}
LEGACY_POOL_BY_AUDIENCE = {
    AUDIENCE_PENDING_QUESTIONNAIRE: POOL_PENDING_QUESTIONNAIRE,
    AUDIENCE_OPERATING: POOL_OPERATING,
    AUDIENCE_CONVERTED: POOL_CONVERTED,
}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return _normalized_text(value)


def _trigger_time_text(trigger_time: datetime | str | None) -> str:
    if isinstance(trigger_time, datetime):
        return trigger_time.strftime("%Y-%m-%d %H:%M:%S")
    return _normalized_text(trigger_time) or _iso_now()


def _is_channel_enter_trigger(trigger_type: Any) -> bool:
    return (_normalized_text(trigger_type) or "channel_enter") in CHANNEL_ENTER_TRIGGERS


def _serialize_program_member(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    for key in (
        "id",
        "program_id",
        "source_channel_id",
        "source_binding_id",
        "first_source_channel_id",
        "latest_source_channel_id",
        "reentry_count",
    ):
        item[key] = int(item.get(key) or 0) or (None if key.endswith("_id") and key != "id" and key != "program_id" else 0)
    item["master_customer_id"] = int(item.get("master_customer_id") or 0) or None
    item["in_program"] = bool(item.get("in_program"))
    item["state_payload_json"] = _json_loads(item.get("state_payload_json"), default={})
    for key in ("current_stage_entered_at", "pool_entered_at", "exited_at", "created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    return item


def _serialize_stage_history(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    for key in ("id", "program_member_id", "program_id"):
        item[key] = int(item.get(key) or 0)
    item["snapshot_json"] = _json_loads(item.get("snapshot_json"), default={})
    for key in ("entered_at", "exited_at", "created_at"):
        item[key] = _dt_text(item.get(key))
    return item


def _serialize_attempt(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    for key in ("id", "program_id", "channel_id", "binding_id"):
        item[key] = int(item.get(key) or 0) or (None if key in {"channel_id", "binding_id"} else 0)
    item["master_customer_id"] = int(item.get("master_customer_id") or 0) or None
    item["trigger_payload_json"] = _json_loads(item.get("trigger_payload_json"), default={})
    item["cleaning_result_json"] = _json_loads(item.get("cleaning_result_json"), default={})
    for key in ("pool_entered_at", "stage_entered_at", "created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    return item


def _get_config_payload(program_id: int, block_key: str) -> dict[str, Any]:
    block = program_repo.get_config_block_row(int(program_id), block_key)
    return dict((block or {}).get("payload_json") or {})


def _program_entry_allowed(program: dict[str, Any], program_id: int) -> tuple[bool, str]:
    status = _normalized_text(program.get("status"))
    if not program:
        return False, "program_not_found"
    if status == "archived":
        return False, "program_archived"
    if status == "active":
        return True, "program_active"
    publish_state = _get_config_payload(int(program_id), BLOCK_PUBLISH_STATE)
    if bool(publish_state.get("entry_published")):
        return True, "entry_published"
    return False, "program_not_active"


def _find_program_member(program_id: int, external_contact_id: str) -> dict[str, Any] | None:
    if not _normalized_text(external_contact_id):
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_program_member
        WHERE program_id = ?
          AND external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_id), _normalized_text(external_contact_id)),
    )


def _reentry_policy(program: dict[str, Any], binding: dict[str, Any]) -> str:
    config = dict(program.get("config_json") or {})
    admission = dict(config.get("admission") or {})
    binding_rules = dict(binding.get("entry_rule_json") or {})
    policy = _normalized_text(binding_rules.get("reentry_policy") or admission.get("reentry_policy")) or "deny"
    return policy if policy in {"deny", "manual_review", "new_cycle", "resume"} else "deny"


def _insert_admission_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_program_admission_attempt (
            program_id, channel_id, binding_id, external_contact_id, master_customer_id,
            trigger_type, trigger_event_id, trigger_payload_json, admission_status,
            pool_entered_at, stage_code, audience_code, stage_entered_at, entry_reason,
            cleaning_result_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, NULLIF(?, '')::timestamptz, ?, ?, NULLIF(?, '')::timestamptz, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0),
            int(payload.get("channel_id") or 0) or None,
            int(payload.get("binding_id") or 0) or None,
            _normalized_text(payload.get("external_contact_id")),
            int(payload.get("master_customer_id") or 0) or None,
            _normalized_text(payload.get("trigger_type")) or "channel_enter",
            _normalized_text(payload.get("trigger_event_id")),
            _json_dumps(payload.get("trigger_payload_json") or {}),
            _normalized_text(payload.get("admission_status")) or "pending",
            _normalized_text(payload.get("pool_entered_at")),
            _normalized_text(payload.get("stage_code")),
            _normalized_text(payload.get("audience_code")),
            _normalized_text(payload.get("stage_entered_at")),
            _normalized_text(payload.get("entry_reason")),
            _json_dumps(payload.get("cleaning_result_json") or {}),
        ),
    ).fetchone()
    return _serialize_attempt(dict(row) if row else {})


def _upsert_program_member(
    *,
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    master_customer_id: int | None,
    trigger_time: str,
    mode: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state_payload = dict((existing or {}).get("state_payload_json") or {})
    if mode == "resume":
        state_payload["resumed_at"] = trigger_time
    if existing:
        row = get_db().execute(
            """
            UPDATE automation_program_member
            SET master_customer_id = COALESCE(?, master_customer_id),
                source_channel_id = ?,
                source_binding_id = ?,
                first_source_channel_id = COALESCE(first_source_channel_id, ?),
                latest_source_channel_id = ?,
                in_program = TRUE,
                pool_entered_at = CASE WHEN ? = 'new_cycle' THEN NULLIF(?, '')::timestamptz ELSE pool_entered_at END,
                exited_at = NULL,
                exit_reason = '',
                reentry_count = CASE WHEN ? = 'new_cycle' THEN reentry_count + 1 ELSE reentry_count END,
                state_payload_json = CAST(? AS jsonb),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                int(master_customer_id or 0) or None,
                int(channel_id or 0) or None,
                int(binding_id or 0) or None,
                int(channel_id or 0) or None,
                int(channel_id or 0) or None,
                mode,
                trigger_time,
                mode,
                _json_dumps(state_payload),
                int(existing["id"]),
            ),
        ).fetchone()
    else:
        row = get_db().execute(
            """
            INSERT INTO automation_program_member (
                program_id, external_contact_id, master_customer_id, source_channel_id,
                source_binding_id, first_source_channel_id, latest_source_channel_id,
                in_program, current_stage_code, current_audience_code,
                current_stage_entered_at, pool_entered_at, state_payload_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, '', 'pending_questionnaire', NULL, NULLIF(?, '')::timestamptz, '{}'::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            (
                int(program_id),
                _normalized_text(external_contact_id),
                int(master_customer_id or 0) or None,
                int(channel_id or 0) or None,
                int(binding_id or 0) or None,
                int(channel_id or 0) or None,
                int(channel_id or 0) or None,
                trigger_time,
            ),
        ).fetchone()
    return _serialize_program_member(dict(row) if row else {})


def _update_program_member_stage(
    *,
    program_member_id: int,
    stage_code: str,
    audience_code: str,
    stage_entered_at: str,
    state_payload: dict[str, Any],
) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program_member
        SET current_stage_code = ?,
            current_audience_code = ?,
            current_stage_entered_at = NULLIF(?, '')::timestamptz,
            state_payload_json = CAST(? AS jsonb),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(stage_code),
            _normalized_text(audience_code) if _normalized_text(audience_code) in VALID_AUDIENCES else AUDIENCE_PENDING_QUESTIONNAIRE,
            _normalized_text(stage_entered_at),
            _json_dumps(state_payload),
            int(program_member_id),
        ),
    ).fetchone()
    return _serialize_program_member(dict(row) if row else {})


def _write_stage_history_if_changed(
    *,
    program_member: dict[str, Any],
    stage_code: str,
    audience_code: str,
    entered_at: str,
    entry_reason: str,
    source_event_type: str,
    source_event_id: str,
    snapshot: dict[str, Any],
    force_new_cycle: bool = False,
) -> dict[str, Any] | None:
    current_stage = _normalized_text(program_member.get("current_stage_code"))
    current_entered = _dt_text(program_member.get("current_stage_entered_at"))
    open_history = _fetchone_dict(
        """
        SELECT *
        FROM automation_program_member_stage_history
        WHERE program_member_id = ?
          AND exited_at IS NULL
        ORDER BY entered_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_member["id"]),),
    )
    if not force_new_cycle and current_stage == stage_code and current_entered and open_history:
        return None
    get_db().execute(
        """
        UPDATE automation_program_member_stage_history
        SET exited_at = NULLIF(?, '')::timestamptz
        WHERE program_member_id = ?
          AND exited_at IS NULL
        """,
        (_normalized_text(entered_at), int(program_member["id"])),
    )
    row = get_db().execute(
        """
        INSERT INTO automation_program_member_stage_history (
            program_member_id, program_id, stage_code, audience_code, entered_at,
            entry_reason, source_event_type, source_event_id, snapshot_json, created_at
        )
        VALUES (?, ?, ?, ?, NULLIF(?, '')::timestamptz, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(program_member["id"]),
            int(program_member["program_id"]),
            stage_code,
            audience_code,
            entered_at,
            entry_reason,
            source_event_type,
            source_event_id,
            _json_dumps(snapshot),
        ),
    ).fetchone()
    return _serialize_stage_history(dict(row) if row else {})


def _upsert_legacy_projection(
    *,
    program_member: dict[str, Any],
    channel_id: int,
    owner_staff_id: str,
    source_type: str,
    audience_code: str,
    audience_entered_at: str,
    entry_reason: str,
    snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    external_contact_id = _normalized_text(program_member.get("external_contact_id"))
    if not external_contact_id:
        return None
    existing = repo.get_member_by_external_contact_id(external_contact_id)
    payload = {
        "external_contact_id": external_contact_id,
        "phone": "",
        "master_customer_id": program_member.get("master_customer_id"),
        "owner_staff_id": _normalized_text(owner_staff_id) or DEFAULT_OWNER_STAFF_ID,
        "in_pool": True,
        "current_pool": LEGACY_POOL_BY_AUDIENCE.get(audience_code, POOL_PENDING_QUESTIONNAIRE),
        "follow_type": _normalized_text((existing or {}).get("follow_type")),
        "questionnaire_status": _normalized_text((existing or {}).get("questionnaire_status")) or "pending",
        "decision_source": "program_admission",
        "source_type": _normalized_text(source_type) or SOURCE_TYPE_QRCODE,
        "source_channel_id": int(channel_id or 0) or None,
        "last_active_pool": _normalized_text((existing or {}).get("last_active_pool")),
        "joined_at": _dt_text(program_member.get("pool_entered_at")),
        "last_ai_push_at": _normalized_text((existing or {}).get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text((existing or {}).get("ai_cooldown_until")),
        "current_audience_code": audience_code,
        "current_audience_entered_at": audience_entered_at,
    }
    if existing:
        legacy = repo.update_member(int(existing["id"]), payload)
    else:
        legacy = repo.insert_member(payload)
    legacy_id = int((legacy or {}).get("id") or 0)
    if legacy_id <= 0:
        return None
    current_entry = workflow_repo.get_current_member_audience_entry_row(legacy_id)
    if (
        not current_entry
        or _normalized_text(current_entry.get("audience_code")) != audience_code
        or _normalized_text(current_entry.get("entered_at")) != _normalized_text(audience_entered_at)
    ):
        workflow_repo.close_current_member_audience_entries(
            legacy_id,
            exited_at=audience_entered_at,
            entry_reason=entry_reason,
            source_snapshot_json=snapshot,
        )
        workflow_repo.insert_member_audience_entry_row(
            {
                "member_id": legacy_id,
                "audience_code": audience_code,
                "entered_at": audience_entered_at,
                "is_current": True,
                "entry_source": "program_admission",
                "entry_reason": entry_reason,
                "source_snapshot_json": snapshot,
            }
        )
    return dict(legacy or {})


def _resolve_segmentation(program_id: int, member_identity: dict[str, Any]) -> dict[str, Any]:
    from . import workflow_service

    setup_payload = workflow_service._program_setup_segmentation_payload(program_id=int(program_id))
    if not setup_payload:
        return {"segmentation_status": "not_configured"}
    questionnaire_id = int(setup_payload.get("questionnaire_id") or 0)
    if questionnaire_id <= 0:
        return {"segmentation_status": "config_error", "reason": "questionnaire_missing"}
    from .program_setup_service import _member_has_questionnaire_submission

    if not _member_has_questionnaire_submission(member_identity, questionnaire_id):
        return {"segmentation_status": "questionnaire_missing"}
    bundle = workflow_service._active_profile_segment_template_bundle(program_id=int(program_id))
    profile_result = workflow_service._resolve_profile_segment_for_member(
        member=member_identity,
        profile_segment_template_bundle=bundle,
    )
    if bool(profile_result.get("matched")):
        return {
            "segmentation_status": "matched",
            "profile_segment_key": _normalized_text(profile_result.get("segment_key")),
            "profile_segment_label": _normalized_text(profile_result.get("segment_label")),
            "profile_result": profile_result,
        }
    reason = _normalized_text(profile_result.get("reason"))
    if reason in {"questionnaire_submission_missing", "segmentation_question_answer_missing", "selected_option_ids_empty"}:
        return {"segmentation_status": "questionnaire_missing", "profile_result": profile_result}
    if reason in {"multiple_or_zero_profile_categories"}:
        return {"segmentation_status": "option_not_mapped", "profile_result": profile_result}
    return {"segmentation_status": "fallback", "reason": reason or "not_matched", "profile_result": profile_result}


def resolve_admission_stage(
    program_id: int,
    program_member: dict[str, Any],
    trigger_time: datetime | str | None,
    trigger_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    trigger_time_text = _trigger_time_text(trigger_time)
    audience_payload = _get_config_payload(int(program_id), BLOCK_AUDIENCE_ENTRY_RULE)
    order_review = dict((audience_payload.get("order_review") or {}))
    questionnaire_review = dict((audience_payload.get("questionnaire_review") or {}))
    conversion_review = dict((audience_payload.get("conversion_review") or {}))
    from .program_setup_service import _member_has_paid_product, _member_has_questionnaire_submission

    member_identity = {
        "external_contact_id": _normalized_text(program_member.get("external_contact_id")),
        "phone": _normalized_text((trigger_payload or {}).get("phone")),
        "source_channel_id": program_member.get("source_channel_id"),
    }
    cleaning_facts: dict[str, Any] = {}
    if order_review.get("enabled"):
        paid = _member_has_paid_product(member_identity, order_review.get("selected_product_id"))
        cleaning_facts["order_review_paid"] = paid
        if not paid:
            return {
                "stage_code": STAGE_ORDER_REVIEW,
                "audience_code": AUDIENCE_PENDING_QUESTIONNAIRE,
                "entry_reason": ENTRY_REASON_ORDER_REVIEW_PENDING,
                "admission_status": ADMISSION_WAITING,
                "stage_entered_at": trigger_time_text,
                "cleaning_facts": cleaning_facts,
            }
    if questionnaire_review.get("enabled"):
        submitted = _member_has_questionnaire_submission(
            member_identity,
            questionnaire_review.get("selected_questionnaire_id"),
        )
        cleaning_facts["questionnaire_review_submitted"] = submitted
        if not submitted:
            return {
                "stage_code": STAGE_QUESTIONNAIRE_REVIEW,
                "audience_code": AUDIENCE_PENDING_QUESTIONNAIRE,
                "entry_reason": ENTRY_REASON_QUESTIONNAIRE_REVIEW_PENDING,
                "admission_status": ADMISSION_WAITING,
                "stage_entered_at": trigger_time_text,
                "cleaning_facts": cleaning_facts,
            }
    if conversion_review.get("enabled"):
        converted_paid = _member_has_paid_product(member_identity, conversion_review.get("selected_product_id"))
        cleaning_facts["conversion_review_paid"] = converted_paid
        if converted_paid:
            return {
                "stage_code": STAGE_CONVERTED,
                "audience_code": AUDIENCE_CONVERTED,
                "entry_reason": ENTRY_REASON_CONVERSION_PRODUCT_PAID,
                "admission_status": ADMISSION_CONVERTED,
                "stage_entered_at": trigger_time_text,
                "cleaning_facts": cleaning_facts,
            }
    segmentation = _resolve_segmentation(int(program_id), member_identity)
    return {
        "stage_code": STAGE_OPERATING,
        "audience_code": AUDIENCE_OPERATING,
        "entry_reason": ENTRY_REASON_AUDIENCE_RULE_PASSED,
        "admission_status": ADMISSION_ACCEPTED,
        "stage_entered_at": trigger_time_text,
        "cleaning_facts": cleaning_facts,
        "segmentation": segmentation,
    }


def _reject_attempt(
    *,
    program_id: int,
    channel_id: int,
    binding_id: int | None,
    external_contact_id: str,
    master_customer_id: int | None,
    trigger_type: str,
    trigger_payload: dict[str, Any],
    reason: str,
    status: str = ADMISSION_REJECTED,
) -> dict[str, Any]:
    attempt = _insert_admission_attempt(
        {
            "program_id": program_id,
            "channel_id": channel_id,
            "binding_id": binding_id,
            "external_contact_id": external_contact_id,
            "master_customer_id": master_customer_id,
            "trigger_type": trigger_type,
            "trigger_event_id": _normalized_text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
            "trigger_payload_json": trigger_payload,
            "admission_status": status,
            "entry_reason": reason,
            "cleaning_result_json": {"reason": reason},
        }
    )
    get_db().commit()
    return {"admission_status": status, "accepted": False, "reason": reason, "admission_attempt": attempt}


def admit_channel_contact_to_program(
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    follow_user_userid: str = "",
    trigger_payload: dict[str, Any] | None = None,
    trigger_time: datetime | str | None = None,
    trigger_type: str = "channel_enter",
) -> dict[str, Any]:
    trigger_payload = dict(trigger_payload or {})
    trigger_time_text = _trigger_time_text(trigger_time)
    external_contact_id = _normalized_text(external_contact_id)
    master_customer_id = int(trigger_payload.get("master_customer_id") or 0) or repo.lookup_person_id_by_external_contact_id(external_contact_id)
    program = program_repo.get_program_row(int(program_id))
    if not program:
        return _reject_attempt(
            program_id=program_id,
            channel_id=channel_id,
            binding_id=binding_id,
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            reason="program_not_found",
        )
    allowed, allow_reason = _program_entry_allowed(program, int(program_id))
    if not allowed:
        return _reject_attempt(
            program_id=program_id,
            channel_id=channel_id,
            binding_id=binding_id,
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            reason=allow_reason,
        )
    binding = _fetchone_dict(
        """
        SELECT *
        FROM automation_program_channel_binding
        WHERE id = ?
          AND program_id = ?
          AND channel_id = ?
        LIMIT 1
        """,
        (int(binding_id), int(program_id), int(channel_id)),
    )
    if not binding or _normalized_text(binding.get("binding_status")) != "active":
        return _reject_attempt(
            program_id=program_id,
            channel_id=channel_id,
            binding_id=binding_id,
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            reason="binding_not_active",
        )
    binding["entry_rule_json"] = _json_loads(binding.get("entry_rule_json"), default={})
    if not bool(binding.get("auto_enter_pool")):
        manual_status = _normalized_text((binding.get("entry_rule_json") or {}).get("auto_enter_disabled_status")) or ADMISSION_MANUAL_REVIEW
        if manual_status not in {ADMISSION_MANUAL_REVIEW, ADMISSION_REJECTED}:
            manual_status = ADMISSION_MANUAL_REVIEW
        return _reject_attempt(
            program_id=program_id,
            channel_id=channel_id,
            binding_id=binding_id,
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            reason="auto_enter_pool_disabled",
            status=manual_status,
        )
    if not external_contact_id and not master_customer_id:
        return _reject_attempt(
            program_id=program_id,
            channel_id=channel_id,
            binding_id=binding_id,
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            reason="identity_missing",
        )
    existing = _find_program_member(int(program_id), external_contact_id)
    if existing and bool(existing.get("in_program")) and _is_channel_enter_trigger(trigger_type):
        row = get_db().execute(
            """
            UPDATE automation_program_member
            SET latest_source_channel_id = ?,
                source_channel_id = ?,
                source_binding_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (int(channel_id), int(channel_id), int(binding_id), int(existing["id"])),
        ).fetchone()
        program_member = _serialize_program_member(dict(row) if row else existing)
        attempt = _insert_admission_attempt(
            {
                "program_id": program_id,
                "channel_id": channel_id,
                "binding_id": binding_id,
                "external_contact_id": external_contact_id,
                "master_customer_id": master_customer_id,
                "trigger_type": trigger_type,
                "trigger_event_id": _normalized_text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
                "trigger_payload_json": trigger_payload,
                "admission_status": ADMISSION_DUPLICATE_ACTIVE,
                "pool_entered_at": _dt_text(program_member.get("pool_entered_at")),
                "stage_code": _normalized_text(program_member.get("current_stage_code")),
                "audience_code": _normalized_text(program_member.get("current_audience_code")),
                "stage_entered_at": _dt_text(program_member.get("current_stage_entered_at")),
                "entry_reason": "duplicate_active_member",
                "cleaning_result_json": {"reason": "duplicate_active_member", "pool_entered_at_kept": True, "stage_entered_at_kept": True},
            }
        )
        get_db().commit()
        return {
            "admission_status": ADMISSION_DUPLICATE_ACTIVE,
            "accepted": False,
            "reason": "duplicate_active_member",
            "program_member": program_member,
            "admission_attempt": attempt,
        }
    member_mode = "new"
    if existing and not bool(existing.get("in_program")):
        policy = _reentry_policy(program, binding)
        if policy in {"deny", "manual_review"}:
            return _reject_attempt(
                program_id=program_id,
                channel_id=channel_id,
                binding_id=binding_id,
                external_contact_id=external_contact_id,
                master_customer_id=master_customer_id,
                trigger_type=trigger_type,
                trigger_payload=trigger_payload,
                reason=f"reentry_{policy}",
                status=ADMISSION_MANUAL_REVIEW if policy == "manual_review" else ADMISSION_REJECTED,
            )
        member_mode = policy
    elif existing:
        member_mode = "active_event"
    program_member = _upsert_program_member(
        program_id=int(program_id),
        channel_id=int(channel_id),
        binding_id=int(binding_id),
        external_contact_id=external_contact_id,
        master_customer_id=master_customer_id,
        trigger_time=trigger_time_text,
        mode=member_mode,
        existing=existing,
    )
    resolved = resolve_admission_stage(
        int(program_id),
        program_member,
        trigger_time_text,
        trigger_payload,
    )
    state_payload = dict(program_member.get("state_payload_json") or {})
    segmentation = dict(resolved.get("segmentation") or {})
    if _normalized_text(segmentation.get("profile_segment_key")):
        state_payload["profile_segment_key"] = _normalized_text(segmentation.get("profile_segment_key"))
    state_payload["admission"] = {
        "last_channel_id": int(channel_id),
        "last_binding_id": int(binding_id),
        "last_trigger_type": _normalized_text(trigger_type) or "channel_enter",
        "last_triggered_at": trigger_time_text,
        "last_entry_reason": _normalized_text(resolved.get("entry_reason")),
        "segmentation_status": _normalized_text(segmentation.get("segmentation_status")),
    }
    attempt = _insert_admission_attempt(
        {
            "program_id": program_id,
            "channel_id": channel_id,
            "binding_id": binding_id,
            "external_contact_id": external_contact_id,
            "master_customer_id": master_customer_id,
            "trigger_type": trigger_type,
            "trigger_event_id": _normalized_text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
            "trigger_payload_json": trigger_payload,
            "admission_status": resolved["admission_status"],
            "pool_entered_at": _dt_text(program_member.get("pool_entered_at")),
            "stage_code": resolved["stage_code"],
            "audience_code": resolved["audience_code"],
            "stage_entered_at": resolved["stage_entered_at"],
            "entry_reason": resolved["entry_reason"],
            "cleaning_result_json": resolved,
        }
    )
    snapshot = {
        "program_id": int(program_id),
        "program_member_id": int(program_member["id"]),
        "admission_attempt_id": int(attempt["id"]),
        "channel_id": int(channel_id),
        "binding_id": int(binding_id),
        "entry_reason": resolved["entry_reason"],
        "pool_entered_at": _dt_text(program_member.get("pool_entered_at")),
        "stage_entered_at": resolved["stage_entered_at"],
        "cleaning_result": resolved,
    }
    stage_history = _write_stage_history_if_changed(
        program_member=program_member,
        stage_code=resolved["stage_code"],
        audience_code=resolved["audience_code"],
        entered_at=resolved["stage_entered_at"],
        entry_reason=resolved["entry_reason"],
        source_event_type=_normalized_text(trigger_type) or "channel_enter",
        source_event_id=_normalized_text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
        snapshot=snapshot,
        force_new_cycle=member_mode == "new_cycle",
    )
    program_member = _update_program_member_stage(
        program_member_id=int(program_member["id"]),
        stage_code=resolved["stage_code"],
        audience_code=resolved["audience_code"],
        stage_entered_at=resolved["stage_entered_at"],
        state_payload=state_payload,
    )
    legacy_member = _upsert_legacy_projection(
        program_member=program_member,
        channel_id=int(channel_id),
        owner_staff_id=follow_user_userid,
        source_type=_normalized_text(trigger_payload.get("source_type")) or SOURCE_TYPE_QRCODE,
        audience_code=resolved["audience_code"],
        audience_entered_at=resolved["stage_entered_at"],
        entry_reason=resolved["entry_reason"],
        snapshot=snapshot,
    )
    get_db().commit()
    return {
        "admission_status": resolved["admission_status"],
        "accepted": resolved["admission_status"] in {ADMISSION_ACCEPTED, ADMISSION_WAITING, ADMISSION_CONVERTED},
        "reason": resolved["entry_reason"],
        "program_member": program_member,
        "stage_history": stage_history,
        "admission_attempt": attempt,
        "legacy_member": legacy_member,
        "cleaning_result": resolved,
    }


def record_standalone_channel_attempt(
    *,
    channel_id: int,
    external_contact_id: str,
    master_customer_id: int | None = None,
    trigger_type: str = "channel_enter",
    trigger_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_program_admission_attempt (
            program_id, channel_id, binding_id, external_contact_id, master_customer_id,
            trigger_type, trigger_event_id, trigger_payload_json, admission_status,
            entry_reason, cleaning_result_json, created_at, updated_at
        )
        SELECT p.id, ?, NULL, ?, ?, ?, ?, CAST(? AS jsonb), 'standalone_channel',
               'channel_without_active_binding', '{"reason":"channel_without_active_binding"}'::jsonb,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM automation_program p
        ORDER BY CASE WHEN p.program_code = 'signup_conversion_v1' THEN 0 ELSE 1 END, p.id ASC
        LIMIT 1
        RETURNING *
        """,
        (
            int(channel_id),
            _normalized_text(external_contact_id),
            int(master_customer_id or 0) or None,
            _normalized_text(trigger_type) or "channel_enter",
            _normalized_text((trigger_payload or {}).get("event_log_id") or (trigger_payload or {}).get("event_id")),
            _json_dumps(trigger_payload or {}),
        ),
    ).fetchone()
    get_db().commit()
    return _serialize_attempt(dict(row) if row else {})


def import_channel_contacts_to_program(
    program_id: int,
    *,
    channel_id: int,
    operator_id: str = "",
    use_historical_channel_entered_at: bool = False,
    dry_run: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    bindings = list_active_bindings_for_channel(int(channel_id))
    binding = next((item for item in bindings if int(item.get("program_id") or 0) == int(program_id)), None)
    if not binding:
        raise ValueError("active_binding_required")
    rows = _fetchall_dicts(
        """
        SELECT *
        FROM automation_channel_contact
        WHERE channel_id = ?
        ORDER BY first_channel_entered_at ASC, id ASC
        LIMIT ?
        """,
        (int(channel_id), max(1, min(int(limit or 500), 5000))),
    )
    results = []
    import_time = _iso_now()
    for row in rows:
        trigger_time = _dt_text(row.get("first_channel_entered_at")) if use_historical_channel_entered_at else import_time
        if dry_run:
            results.append(
                {
                    "dry_run": True,
                    "external_contact_id": _normalized_text(row.get("external_contact_id")),
                    "channel_contact_id": int(row.get("id") or 0),
                    "planned_trigger_type": "manual_import",
                    "planned_pool_entered_at": trigger_time,
                    "pool_entered_at_source": "historical_channel_entered_at" if use_historical_channel_entered_at else "import_time",
                    "historical_time_used": bool(use_historical_channel_entered_at),
                }
            )
            continue
        results.append(
            admit_channel_contact_to_program(
                int(program_id),
                int(channel_id),
                int(binding["id"]),
                _normalized_text(row.get("external_contact_id")),
                follow_user_userid=_normalized_text(row.get("owner_staff_id")) or _normalized_text(operator_id),
                trigger_payload={
                    "source_type": "manual_channel_contact_import",
                    "channel_contact_id": int(row.get("id") or 0),
                    "operator_id": _normalized_text(operator_id),
                    "use_historical_channel_entered_at": bool(use_historical_channel_entered_at),
                    "historical_time_used": bool(use_historical_channel_entered_at),
                    "risk_acknowledged": bool(use_historical_channel_entered_at),
                },
                trigger_time=trigger_time,
                trigger_type="manual_import",
            )
        )
    return {
        "imported_count": 0 if dry_run else len(results),
        "planned_count": len(results) if dry_run else 0,
        "dry_run": bool(dry_run),
        "results": results,
        "pool_entered_at_source": "historical_channel_entered_at" if use_historical_channel_entered_at else "import_time",
        "historical_time_used": bool(use_historical_channel_entered_at),
        "risk_acknowledged": bool(use_historical_channel_entered_at),
        "reason": "historical_import_requires_manual_api",
    }


def list_admission_attempts(program_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = _fetchall_dicts(
        """
        SELECT *
        FROM automation_program_admission_attempt
        WHERE program_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(program_id), max(1, min(int(limit or 100), 500))),
    )
    return [_serialize_attempt(row) for row in rows]


def list_program_member_stage_history(program_member_id: int, *, program_id: int | None = None) -> list[dict[str, Any]]:
    params: list[Any] = [int(program_member_id)]
    program_sql = ""
    if int(program_id or 0) > 0:
        program_sql = " AND program_id = ?"
        params.append(int(program_id or 0))
    rows = _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_program_member_stage_history
        WHERE program_member_id = ?
        {program_sql}
        ORDER BY entered_at DESC, id DESC
        """,
        tuple(params),
    )
    return [_serialize_stage_history(row) for row in rows]
