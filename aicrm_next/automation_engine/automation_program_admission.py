from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aicrm_next.automation_engine.operation_task_contract import (
    agent_runtime_diagnostics,
    has_send_body as contract_has_send_body,
    publishable_diagnostics,
)
from aicrm_next.shared.postgres_connection import get_db

from .audience_transition.domain import AudienceTransitionEvent


ADMISSION_ACCEPTED = "accepted"
ADMISSION_WAITING = "waiting"
ADMISSION_CONVERTED = "converted"
ADMISSION_REJECTED = "rejected"
ADMISSION_DUPLICATE_ACTIVE = "duplicate_active"
ADMISSION_MANUAL_REVIEW = "manual_review"

AUDIENCE_PENDING_QUESTIONNAIRE = "pending_questionnaire"
AUDIENCE_OPERATING = "operating"
AUDIENCE_CONVERTED = "converted"
VALID_AUDIENCES = {AUDIENCE_PENDING_QUESTIONNAIRE, AUDIENCE_OPERATING, AUDIENCE_CONVERTED}

STAGE_ORDER_REVIEW = "order_review"
STAGE_QUESTIONNAIRE_REVIEW = "questionnaire_review"
STAGE_OPERATING = "operating"
STAGE_CONVERTED = "converted"

ENTRY_REASON_ORDER_REVIEW_PENDING = "order_review_pending"
ENTRY_REASON_QUESTIONNAIRE_REVIEW_PENDING = "questionnaire_review_pending"
ENTRY_REASON_AUDIENCE_RULE_PASSED = "audience_entry_rule_passed"
ENTRY_REASON_CONVERSION_PRODUCT_PAID = "conversion_product_paid"

POOL_PENDING_QUESTIONNAIRE = "pending_questionnaire"
POOL_OPERATING = "operating"
POOL_CONVERTED = "converted"
SOURCE_TYPE_QRCODE = "qrcode"
DEFAULT_OWNER_STAFF_ID = "HuangYouCan"
CHANNEL_ENTER_TRIGGERS = {"channel_enter", "qrcode_enter", "customer_acquisition_enter"}
POOL_BY_AUDIENCE = {
    AUDIENCE_PENDING_QUESTIONNAIRE: POOL_PENDING_QUESTIONNAIRE,
    AUDIENCE_OPERATING: POOL_OPERATING,
    AUDIENCE_CONVERTED: POOL_CONVERTED,
}
BEHAVIOR_TIERS = (
    {"tier_code": "lt_2", "label": "消息少于 2", "min_value": None, "max_value": 1},
    {"tier_code": "between_2_9", "label": "消息 2 ~ 9", "min_value": 2, "max_value": 9},
    {"tier_code": "gte_10", "label": "消息大于等于 10", "min_value": 10, "max_value": None},
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    if minimum is not None:
        result = max(result, minimum)
    return result


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return _text(value)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _trigger_time_text(trigger_time: datetime | str | None) -> str:
    return _dt_text(trigger_time) or _now_text()


def _fetchone(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _serialize_program_member(row: dict[str, Any] | None) -> dict[str, Any]:
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
        item[key] = _int(item.get(key))
    item["master_customer_id"] = _int(item.get("master_customer_id")) or None
    item["in_program"] = bool(item.get("in_program"))
    item["state_payload_json"] = _json_loads(item.get("state_payload_json"), default={})
    for key in ("current_stage_entered_at", "pool_entered_at", "exited_at", "created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    return item


def _serialize_attempt(row: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(row or {})
    if not item:
        return {}
    for key in ("id", "program_id", "channel_id", "binding_id"):
        item[key] = _int(item.get(key)) or (None if key in {"channel_id", "binding_id"} else 0)
    item["master_customer_id"] = _int(item.get("master_customer_id")) or None
    item["trigger_payload_json"] = _json_loads(item.get("trigger_payload_json"), default={})
    item["cleaning_result_json"] = _json_loads(item.get("cleaning_result_json"), default={})
    for key in ("pool_entered_at", "stage_entered_at", "created_at", "updated_at"):
        item[key] = _dt_text(item.get(key))
    return item


def _config_payload(program_id: int, block_key: str) -> dict[str, Any]:
    row = _fetchone(
        """
        SELECT payload_json
        FROM automation_program_config_block
        WHERE program_id = ?
          AND block_key = ?
        LIMIT 1
        """,
        (int(program_id), _text(block_key)),
    )
    return dict(_json_loads((row or {}).get("payload_json"), default={}) or {})


def _program_entry_allowed(program: dict[str, Any] | None, program_id: int) -> tuple[bool, str]:
    if not program:
        return False, "program_not_found"
    status = _text(program.get("status"))
    if status == "archived":
        return False, "program_archived"
    if status == "active":
        return True, "program_active"
    publish_state = _config_payload(int(program_id), "publish_state")
    if bool(publish_state.get("entry_published")):
        return True, "entry_published"
    return False, "program_not_active"


def _is_channel_enter_trigger(trigger_type: Any) -> bool:
    return (_text(trigger_type) or "channel_enter") in CHANNEL_ENTER_TRIGGERS


def _find_program_member(program_id: int, external_contact_id: str) -> dict[str, Any] | None:
    if not _text(external_contact_id):
        return None
    row = _fetchone(
        """
        SELECT *
        FROM automation_program_member
        WHERE program_id = ?
          AND external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_id), _text(external_contact_id)),
    )
    return _serialize_program_member(row) if row else None


def _lookup_person_id_by_external_contact_id(external_contact_id: str) -> int | None:
    if not _text(external_contact_id):
        return None
    row = _fetchone(
        """
        SELECT person_id
        FROM external_contact_bindings
        WHERE external_userid = ?
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """,
        (_text(external_contact_id),),
    )
    return _int((row or {}).get("person_id")) or None


def _reentry_policy(program: dict[str, Any], binding: dict[str, Any]) -> str:
    config = dict(_json_loads(program.get("config_json"), default={}) or {})
    admission = dict(config.get("admission") or {})
    binding_rules = dict(_json_loads(binding.get("entry_rule_json"), default={}) or {})
    policy = _text(binding_rules.get("reentry_policy") or admission.get("reentry_policy")) or "deny"
    return policy if policy in {"deny", "manual_review", "new_cycle", "resume"} else "deny"


def _insert_admission_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    row = _fetchone(
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
            _int(payload.get("program_id")),
            _int(payload.get("channel_id")) or None,
            _int(payload.get("binding_id")) or None,
            _text(payload.get("external_contact_id")),
            _int(payload.get("master_customer_id")) or None,
            _text(payload.get("trigger_type")) or "channel_enter",
            _text(payload.get("trigger_event_id")),
            _json_dumps(payload.get("trigger_payload_json") or {}),
            _text(payload.get("admission_status")) or "pending",
            _text(payload.get("pool_entered_at")),
            _text(payload.get("stage_code")),
            _text(payload.get("audience_code")),
            _text(payload.get("stage_entered_at")),
            _text(payload.get("entry_reason")),
            _json_dumps(payload.get("cleaning_result_json") or {}),
        ),
    )
    return _serialize_attempt(row)


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
            "trigger_event_id": _text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
            "trigger_payload_json": trigger_payload,
            "admission_status": status,
            "entry_reason": reason,
            "cleaning_result_json": {"reason": reason},
        }
    )
    get_db().commit()
    return {
        "admission_status": status,
        "accepted": False,
        "reason": reason,
        "admission_attempt": attempt,
        "source_status": "next_command",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


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
        row = _fetchone(
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
                _int(master_customer_id) or None,
                _int(channel_id) or None,
                _int(binding_id) or None,
                _int(channel_id) or None,
                _int(channel_id) or None,
                mode,
                trigger_time,
                mode,
                _json_dumps(state_payload),
                int(existing["id"]),
            ),
        )
    else:
        row = _fetchone(
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
                _text(external_contact_id),
                _int(master_customer_id) or None,
                _int(channel_id) or None,
                _int(binding_id) or None,
                _int(channel_id) or None,
                _int(channel_id) or None,
                trigger_time,
            ),
        )
    return _serialize_program_member(row)


def _update_program_member_stage(
    *,
    program_member_id: int,
    stage_code: str,
    audience_code: str,
    stage_entered_at: str,
    state_payload: dict[str, Any],
) -> dict[str, Any]:
    row = _fetchone(
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
            _text(stage_code),
            _text(audience_code) if _text(audience_code) in VALID_AUDIENCES else AUDIENCE_PENDING_QUESTIONNAIRE,
            _text(stage_entered_at),
            _json_dumps(state_payload),
            int(program_member_id),
        ),
    )
    return _serialize_program_member(row)


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
    current_stage = _text(program_member.get("current_stage_code"))
    current_entered = _dt_text(program_member.get("current_stage_entered_at"))
    open_history = _fetchone(
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
        (_text(entered_at), int(program_member["id"])),
    )
    row = _fetchone(
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
            _text(stage_code),
            _text(audience_code),
            _text(entered_at),
            _text(entry_reason),
            _text(source_event_type),
            _text(source_event_id),
            _json_dumps(snapshot),
        ),
    )
    return dict(row or {}) if row else None


def _member_has_paid_product(member_identity: dict[str, Any], product_id: Any) -> bool:
    product_code = _text(product_id)
    external_contact_id = _text(member_identity.get("external_contact_id"))
    phone = _text(member_identity.get("phone"))
    if not product_code:
        return False
    identity_clauses: list[str] = []
    params: list[Any] = [product_code]
    if external_contact_id:
        identity_clauses.append("(external_userid = ? OR userid_snapshot = ? OR respondent_key = ?)")
        params.extend([external_contact_id, external_contact_id, external_contact_id])
    if phone:
        identity_clauses.append("mobile_snapshot = ?")
        params.append(phone)
    if not identity_clauses:
        return False
    row = _fetchone(
        """
        SELECT id
        FROM wechat_pay_orders
        WHERE product_code = ?
          AND COALESCE(refunded_amount_total, 0) = 0
          AND (COALESCE(status, '') = 'paid' OR COALESCE(trade_state, '') = 'SUCCESS')
          AND (
        """
        + " OR ".join(identity_clauses)
        + """
          )
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return bool(row)


def _member_has_questionnaire_submission(member_identity: dict[str, Any], questionnaire_id: Any) -> bool:
    qid = _int(questionnaire_id)
    external_contact_id = _text(member_identity.get("external_contact_id"))
    phone = _text(member_identity.get("phone"))
    if not external_contact_id and not phone:
        return False
    clauses: list[str] = []
    params: list[Any] = []
    if qid:
        clauses.append("questionnaire_id = ?")
        params.append(qid)
    identity_clauses: list[str] = []
    if external_contact_id:
        identity_clauses.append("external_userid = ?")
        params.append(external_contact_id)
    if phone:
        identity_clauses.append("mobile_snapshot = ?")
        params.append(phone)
    clauses.append("(" + " OR ".join(identity_clauses) + ")")
    row = _fetchone(f"SELECT id FROM questionnaire_submissions WHERE {' AND '.join(clauses)} ORDER BY submitted_at DESC NULLS LAST, id DESC LIMIT 1", tuple(params))
    return bool(row)


def _phone_match_key(value: Any) -> str:
    digits = "".join(char for char in _text(value) if char.isdigit())
    if len(digits) < 7:
        return ""
    return f"{digits[:3]}_{digits[-4:]}"


def _behavior_tier_for_count(message_count: int) -> dict[str, Any]:
    count = int(message_count or 0)
    for item in BEHAVIOR_TIERS:
        key = _text(item.get("tier_code"))
        if key == "lt_2" and count < 2:
            return dict(item)
        if key == "between_2_9" and 2 <= count <= 9:
            return dict(item)
        if key == "gte_10" and count >= 10:
            return dict(item)
    return dict(BEHAVIOR_TIERS[0])


def get_message_activity_db_status() -> dict[str, Any]:
    return {"configured": True}


def query_message_activity_counts() -> list[dict[str, Any]]:
    rows = _fetchall(
        """
        SELECT phone_match_key, COALESCE(SUM(message_count), 0) AS message_count
        FROM automation_message_activity_sync_item
        WHERE NULLIF(phone_match_key, '') IS NOT NULL
        GROUP BY phone_match_key
        """
    )
    return rows


def _behavior_phone_for_member(member_identity: dict[str, Any]) -> tuple[str, str]:
    phone = _text(member_identity.get("phone"))
    if phone:
        return phone, "member_phone"
    external_contact_id = _text(member_identity.get("external_contact_id"))
    if not external_contact_id:
        return "", ""
    submission = _fetchone(
        """
        SELECT mobile_snapshot
        FROM questionnaire_submissions
        WHERE external_userid = ?
          AND NULLIF(mobile_snapshot, '') IS NOT NULL
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (external_contact_id,),
    )
    mobile = _text((submission or {}).get("mobile_snapshot"))
    if mobile:
        return mobile, "questionnaire_mobile_snapshot"
    return "", ""


def _resolve_behavior_segmentation(member_identity: dict[str, Any], *, audience_code: str) -> dict[str, Any]:
    phone, phone_source = _behavior_phone_for_member(member_identity)
    phone_match_key = _phone_match_key(phone)
    if not phone_match_key:
        return {"matched": False, "reason": "behavior_phone_missing", "phone_source": phone_source}
    status = get_message_activity_db_status()
    if not bool(status.get("configured")):
        return {
            "matched": False,
            "reason": "message_activity_db_not_configured",
            "phone_match_key": phone_match_key,
            "phone_source": phone_source,
        }
    try:
        counts_by_match_key = {
            _text(row.get("phone_match_key")): _int(row.get("message_count"))
            for row in query_message_activity_counts()
            if _text(row.get("phone_match_key"))
        }
    except Exception as exc:
        return {
            "matched": False,
            "reason": _text(exc) or "message_activity_query_failed",
            "phone_match_key": phone_match_key,
            "phone_source": phone_source,
        }
    if phone_match_key not in counts_by_match_key and _text(audience_code) not in {AUDIENCE_OPERATING, AUDIENCE_CONVERTED}:
        return {
            "matched": False,
            "reason": "usage_source_not_found",
            "phone_match_key": phone_match_key,
            "phone_source": phone_source,
        }
    message_count = int(counts_by_match_key.get(phone_match_key) or 0)
    tier = _behavior_tier_for_count(message_count)
    tier_code = _text(tier.get("tier_code"))
    return {
        "matched": bool(tier_code),
        "behavior_tier_key": tier_code,
        "behavior_tier_label": _text(tier.get("label")) or tier_code,
        "message_count": message_count,
        "phone_match_key": phone_match_key,
        "phone_source": phone_source,
        "source": "message_activity_db" if phone_match_key in counts_by_match_key else "message_activity_db_missing_as_zero",
        "reason": "",
    }


def _resolve_segmentation(program_id: int, member_identity: dict[str, Any]) -> dict[str, Any]:
    setup_payload = _config_payload(int(program_id), "segmentation")
    questionnaire_id = _int(setup_payload.get("questionnaire_id"))
    if questionnaire_id > 0 and not _member_has_questionnaire_submission(member_identity, questionnaire_id):
        return {"segmentation_status": "questionnaire_missing"}
    return {"segmentation_status": "not_configured" if not setup_payload else "fallback"}


def resolve_admission_stage(
    program_id: int,
    program_member: dict[str, Any],
    trigger_time: datetime | str | None,
    trigger_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    trigger_time_text = _trigger_time_text(trigger_time)
    audience_payload = _config_payload(int(program_id), "audience_entry_rule")
    order_review = dict((audience_payload.get("order_review") or {}))
    questionnaire_review = dict((audience_payload.get("questionnaire_review") or {}))
    conversion_review = dict((audience_payload.get("conversion_review") or {}))
    member_identity = {
        "external_contact_id": _text(program_member.get("external_contact_id")),
        "phone": _text((trigger_payload or {}).get("phone")),
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
        submitted = _member_has_questionnaire_submission(member_identity, questionnaire_review.get("selected_questionnaire_id"))
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
    behavior_segmentation = _resolve_behavior_segmentation(member_identity, audience_code=AUDIENCE_OPERATING)
    segmentation = {**segmentation, "behavior_result": behavior_segmentation}
    if bool(behavior_segmentation.get("matched")):
        segmentation["behavior_tier_key"] = _text(behavior_segmentation.get("behavior_tier_key"))
        segmentation["behavior_tier_label"] = _text(behavior_segmentation.get("behavior_tier_label"))
    return {
        "stage_code": STAGE_OPERATING,
        "audience_code": AUDIENCE_OPERATING,
        "entry_reason": ENTRY_REASON_AUDIENCE_RULE_PASSED,
        "admission_status": ADMISSION_ACCEPTED,
        "stage_entered_at": trigger_time_text,
        "cleaning_facts": cleaning_facts,
        "segmentation": segmentation,
    }


def _upsert_member_projection(
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
    external_contact_id = _text(program_member.get("external_contact_id"))
    if not external_contact_id:
        return None
    state = dict(program_member.get("state_payload_json") or {})
    existing = _fetchone("SELECT * FROM automation_member WHERE external_contact_id = ? LIMIT 1", (external_contact_id,))
    payload = {
        "phone": _text((existing or {}).get("phone")),
        "master_customer_id": _int(program_member.get("master_customer_id")) or _int((existing or {}).get("master_customer_id")) or None,
        "owner_staff_id": _text((existing or {}).get("owner_staff_id")) or _text(owner_staff_id) or DEFAULT_OWNER_STAFF_ID,
        "current_pool": POOL_BY_AUDIENCE.get(audience_code, POOL_PENDING_QUESTIONNAIRE),
        "follow_type": _text((existing or {}).get("follow_type")),
        "questionnaire_status": _text((existing or {}).get("questionnaire_status")) or "pending",
        "source_type": _text(source_type) or SOURCE_TYPE_QRCODE,
        "source_channel_id": _int(channel_id) or None,
        "last_active_pool": _text((existing or {}).get("last_active_pool")),
        "joined_at": _dt_text(program_member.get("pool_entered_at")),
        "profile_segment_key": _text(state.get("profile_segment_key")),
        "behavior_tier_key": _text(state.get("behavior_tier_key")),
    }
    if existing:
        row = _fetchone(
            """
            UPDATE automation_member
            SET phone = ?,
                master_customer_id = COALESCE(?, master_customer_id),
                owner_staff_id = ?,
                in_pool = TRUE,
                current_pool = ?,
                follow_type = ?,
                questionnaire_status = ?,
                decision_source = 'program_admission',
                source_type = ?,
                source_channel_id = ?,
                last_active_pool = ?,
                joined_at = ?,
                current_audience_code = ?,
                current_audience_entered_at = ?,
                profile_segment_key = ?,
                behavior_tier_key = ?,
                segment_refreshed_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                payload["phone"],
                payload["master_customer_id"],
                payload["owner_staff_id"],
                payload["current_pool"],
                payload["follow_type"],
                payload["questionnaire_status"],
                payload["source_type"],
                payload["source_channel_id"],
                payload["last_active_pool"],
                payload["joined_at"],
                audience_code,
                audience_entered_at,
                payload["profile_segment_key"],
                payload["behavior_tier_key"],
                audience_entered_at,
                int(existing["id"]),
            ),
        )
    else:
        row = _fetchone(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, master_customer_id, owner_staff_id, in_pool,
                current_pool, follow_type, questionnaire_status, decision_source, source_type,
                source_channel_id, last_active_pool, joined_at, current_audience_code,
                current_audience_entered_at, profile_segment_key, behavior_tier_key,
                segment_refreshed_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, TRUE, ?, ?, ?, 'program_admission', ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            (
                external_contact_id,
                payload["phone"],
                payload["master_customer_id"],
                payload["owner_staff_id"],
                payload["current_pool"],
                payload["follow_type"],
                payload["questionnaire_status"],
                payload["source_type"],
                payload["source_channel_id"],
                payload["last_active_pool"],
                payload["joined_at"],
                audience_code,
                audience_entered_at,
                payload["profile_segment_key"],
                payload["behavior_tier_key"],
                audience_entered_at,
            ),
        )
    projection_member = dict(row or {})
    projection_member_id = _int(projection_member.get("id"))
    if projection_member_id <= 0:
        return None
    _write_current_audience_entry(
        member_id=projection_member_id,
        audience_code=audience_code,
        entered_at=audience_entered_at,
        entry_reason=entry_reason,
        snapshot=snapshot,
    )
    return projection_member


def _write_current_audience_entry(*, member_id: int, audience_code: str, entered_at: str, entry_reason: str, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    current = _fetchone(
        """
        SELECT *
        FROM automation_member_audience_entry
        WHERE member_id = ?
          AND is_current = TRUE
        LIMIT 1
        """,
        (int(member_id),),
    )
    if current and _text(current.get("audience_code")) == _text(audience_code) and _text(current.get("entered_at")) == _text(entered_at):
        return current
    get_db().execute(
        """
        UPDATE automation_member_audience_entry
        SET exited_at = ?, is_current = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE member_id = ?
          AND is_current = TRUE
        """,
        (_text(entered_at), int(member_id)),
    )
    return _fetchone(
        """
        INSERT INTO automation_member_audience_entry (
            member_id, audience_code, entered_at, exited_at, is_current,
            entry_source, entry_reason, source_snapshot_json, created_at, updated_at
        )
        VALUES (?, ?, ?, '', TRUE, 'program_admission', ?, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (int(member_id), _text(audience_code), _text(entered_at), _text(entry_reason), _json_dumps(snapshot)),
    )


def _realtime_operation_task_hook(*, member_id: int = 0, external_contact_id: str = "", operator_id: str = "", entry_source: str = "program_admission") -> dict[str, Any]:
    try:
        from aicrm_next.automation_engine.audience_transition.application import handle_committed_audience_transition

        hook = handle_committed_audience_transition(
            member_id=int(member_id or 0),
            external_userid=_text(external_contact_id),
            operator_id=_text(operator_id) or entry_source,
            entry_source=entry_source,
        )
    except Exception as exc:
        try:
            get_db().rollback()
        except Exception:
            pass
        hook = {
            "audience_entry_id": 0,
            "audience_code": "",
            "entry_reason": "",
            "realtime_operation_tasks_ran": 0,
            "realtime_operation_tasks_enqueued_count": 0,
            "realtime_operation_tasks_results": [],
            "realtime_operation_tasks_error": str(exc),
            "realtime_operation_tasks_reason": "realtime_hook_exception",
        }
    payload = dict(hook or {})
    payload["ok"] = not bool(_text(payload.get("realtime_operation_tasks_error")))
    return payload


def _with_realtime_operation_task_hook(result: dict[str, Any], hook: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result or {})
    for key in (
        "audience_entry_id",
        "audience_code",
        "entry_reason",
        "realtime_operation_tasks_ran",
        "realtime_operation_tasks_enqueued_count",
        "realtime_operation_tasks_results",
        "realtime_operation_tasks_error",
        "realtime_operation_tasks_reason",
    ):
        payload[key] = hook.get(key)
    payload["realtime_task_hook"] = dict(hook or {})
    payload.setdefault("source_status", "next_command")
    payload.setdefault("fallback_used", False)
    payload.setdefault("real_external_call_executed", False)
    return payload


@dataclass(frozen=True)
class AutomationAdmissionCommand:
    program_id: int
    channel_id: int
    binding_id: int
    external_contact_id: str
    follow_user_userid: str = ""
    trigger_payload: dict[str, Any] | None = None
    trigger_time: datetime | str | None = None
    trigger_type: str = "qrcode_enter"


class AudienceEntryResolver:
    def resolve(self, *, member_id: int = 0, external_userid: str = "", operator_id: str = "", entry_source: str = "") -> AudienceTransitionEvent | None:
        from .audience_transition.repository import AudienceTransitionRepository

        return AudienceTransitionRepository().build_current_event(
            member_id=int(member_id or 0),
            external_userid=_text(external_userid),
            operator_id=_text(operator_id),
            entry_source=_text(entry_source),
        )


class AutomationEntryAuditWriter:
    def from_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return dict(result.get("admission_attempt") or {})


class AutomationEntrySideEffectPlanner:
    def plan(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "planned": False,
            "reason": "no_real_external_call_for_channel_admission",
            "admission_status": result.get("admission_status"),
            "realtime_operation_tasks_enqueued_count": _int(result.get("realtime_operation_tasks_enqueued_count")),
            "real_external_call_executed": False,
        }


QuestionnaireExternalPushConfigPlanner = AutomationEntrySideEffectPlanner


class AutomationProgramAdmissionService:
    def __init__(
        self,
        *,
        audit_writer: AutomationEntryAuditWriter | None = None,
        external_push_planner: AutomationEntrySideEffectPlanner | None = None,
    ) -> None:
        self._audit_writer = audit_writer or AutomationEntryAuditWriter()
        self._external_push_planner = external_push_planner or AutomationEntrySideEffectPlanner()

    def _complete_result(self, result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result or {})
        payload.setdefault("source_status", "next_command")
        payload.setdefault("fallback_used", False)
        payload.setdefault("real_external_call_executed", False)
        payload["audit"] = self._audit_writer.from_result(payload)
        payload["external_push_plan"] = self._external_push_planner.plan(payload)
        return payload

    def admit(self, command: AutomationAdmissionCommand) -> dict[str, Any]:
        trigger_payload = dict(command.trigger_payload or {})
        trigger_time_text = _trigger_time_text(command.trigger_time)
        external_contact_id = _text(command.external_contact_id)
        master_customer_id = _int(trigger_payload.get("master_customer_id")) or _lookup_person_id_by_external_contact_id(external_contact_id)
        program = _fetchone("SELECT * FROM automation_program WHERE id = ? LIMIT 1", (int(command.program_id),))
        allowed, allow_reason = _program_entry_allowed(program, int(command.program_id))
        if not allowed:
            return self._complete_result(
                _reject_attempt(
                    program_id=int(command.program_id),
                    channel_id=int(command.channel_id),
                    binding_id=int(command.binding_id),
                    external_contact_id=external_contact_id,
                    master_customer_id=master_customer_id,
                    trigger_type=command.trigger_type,
                    trigger_payload=trigger_payload,
                    reason=allow_reason,
                )
            )
        binding = _fetchone(
            """
            SELECT *
            FROM automation_program_channel_binding
            WHERE id = ?
              AND program_id = ?
              AND channel_id = ?
            LIMIT 1
            """,
            (int(command.binding_id), int(command.program_id), int(command.channel_id)),
        )
        if not binding or _text(binding.get("binding_status")) != "active":
            return self._complete_result(
                _reject_attempt(
                    program_id=int(command.program_id),
                    channel_id=int(command.channel_id),
                    binding_id=int(command.binding_id),
                    external_contact_id=external_contact_id,
                    master_customer_id=master_customer_id,
                    trigger_type=command.trigger_type,
                    trigger_payload=trigger_payload,
                    reason="binding_not_active",
                )
            )
        binding["entry_rule_json"] = _json_loads(binding.get("entry_rule_json"), default={})
        if not bool(binding.get("auto_enter_pool")):
            manual_status = _text((binding.get("entry_rule_json") or {}).get("auto_enter_disabled_status")) or ADMISSION_MANUAL_REVIEW
            if manual_status not in {ADMISSION_MANUAL_REVIEW, ADMISSION_REJECTED}:
                manual_status = ADMISSION_MANUAL_REVIEW
            return self._complete_result(
                _reject_attempt(
                    program_id=int(command.program_id),
                    channel_id=int(command.channel_id),
                    binding_id=int(command.binding_id),
                    external_contact_id=external_contact_id,
                    master_customer_id=master_customer_id,
                    trigger_type=command.trigger_type,
                    trigger_payload=trigger_payload,
                    reason="auto_enter_pool_disabled",
                    status=manual_status,
                )
            )
        if not external_contact_id and not master_customer_id:
            return self._complete_result(
                _reject_attempt(
                    program_id=int(command.program_id),
                    channel_id=int(command.channel_id),
                    binding_id=int(command.binding_id),
                    external_contact_id=external_contact_id,
                    master_customer_id=master_customer_id,
                    trigger_type=command.trigger_type,
                    trigger_payload=trigger_payload,
                    reason="identity_missing",
                )
            )
        existing = _find_program_member(int(command.program_id), external_contact_id)
        if existing and bool(existing.get("in_program")) and _is_channel_enter_trigger(command.trigger_type):
            row = _fetchone(
                """
                UPDATE automation_program_member
                SET latest_source_channel_id = ?,
                    source_channel_id = ?,
                    source_binding_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                RETURNING *
                """,
                (int(command.channel_id), int(command.channel_id), int(command.binding_id), int(existing["id"])),
            )
            program_member = _serialize_program_member(row or existing)
            attempt = _insert_admission_attempt(
                {
                    "program_id": command.program_id,
                    "channel_id": command.channel_id,
                    "binding_id": command.binding_id,
                    "external_contact_id": external_contact_id,
                    "master_customer_id": master_customer_id,
                    "trigger_type": command.trigger_type,
                    "trigger_event_id": _text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
                    "trigger_payload_json": trigger_payload,
                    "admission_status": ADMISSION_DUPLICATE_ACTIVE,
                    "pool_entered_at": _dt_text(program_member.get("pool_entered_at")),
                    "stage_code": _text(program_member.get("current_stage_code")),
                    "audience_code": _text(program_member.get("current_audience_code")),
                    "stage_entered_at": _dt_text(program_member.get("current_stage_entered_at")),
                    "entry_reason": "duplicate_active_member",
                    "cleaning_result_json": {"reason": "duplicate_active_member", "pool_entered_at_kept": True, "stage_entered_at_kept": True},
                }
            )
            get_db().commit()
            projection_member = _fetchone("SELECT id FROM automation_member WHERE external_contact_id = ? LIMIT 1", (external_contact_id,))
            hook = _realtime_operation_task_hook(
                member_id=_int((projection_member or {}).get("id")),
                external_contact_id=external_contact_id,
                operator_id=_text(command.trigger_type) or "program_admission",
                entry_source="program_admission",
            )
            return self._complete_result(
                _with_realtime_operation_task_hook(
                    {
                        "admission_status": ADMISSION_DUPLICATE_ACTIVE,
                        "accepted": False,
                        "reason": "duplicate_active_member",
                        "program_member": program_member,
                        "member_id": _int((projection_member or {}).get("id")),
                        "projection_member": projection_member or {},
                        "legacy_member": projection_member or {},
                        "admission_attempt": attempt,
                    },
                    hook,
                )
            )
        member_mode = "new"
        if existing and not bool(existing.get("in_program")):
            policy = _reentry_policy(program or {}, binding)
            if policy in {"deny", "manual_review"}:
                return self._complete_result(
                    _reject_attempt(
                        program_id=int(command.program_id),
                        channel_id=int(command.channel_id),
                        binding_id=int(command.binding_id),
                        external_contact_id=external_contact_id,
                        master_customer_id=master_customer_id,
                        trigger_type=command.trigger_type,
                        trigger_payload=trigger_payload,
                        reason=f"reentry_{policy}",
                        status=ADMISSION_MANUAL_REVIEW if policy == "manual_review" else ADMISSION_REJECTED,
                    )
                )
            member_mode = policy
        elif existing:
            member_mode = "active_event"
        program_member = _upsert_program_member(
            program_id=int(command.program_id),
            channel_id=int(command.channel_id),
            binding_id=int(command.binding_id),
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_time=trigger_time_text,
            mode=member_mode,
            existing=existing,
        )
        resolved = resolve_admission_stage(int(command.program_id), program_member, trigger_time_text, trigger_payload)
        state_payload = dict(program_member.get("state_payload_json") or {})
        segmentation = dict(resolved.get("segmentation") or {})
        if _text(segmentation.get("profile_segment_key")):
            state_payload["profile_segment_key"] = _text(segmentation.get("profile_segment_key"))
        if _text(segmentation.get("behavior_tier_key")):
            state_payload["behavior_tier_key"] = _text(segmentation.get("behavior_tier_key"))
        state_payload["admission"] = {
            "last_channel_id": int(command.channel_id),
            "last_binding_id": int(command.binding_id),
            "last_trigger_type": _text(command.trigger_type) or "channel_enter",
            "last_triggered_at": trigger_time_text,
            "last_entry_reason": _text(resolved.get("entry_reason")),
            "segmentation_status": _text(segmentation.get("segmentation_status")),
        }
        attempt = _insert_admission_attempt(
            {
                "program_id": command.program_id,
                "channel_id": command.channel_id,
                "binding_id": command.binding_id,
                "external_contact_id": external_contact_id,
                "master_customer_id": master_customer_id,
                "trigger_type": command.trigger_type,
                "trigger_event_id": _text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
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
            "program_id": int(command.program_id),
            "program_member_id": int(program_member["id"]),
            "admission_attempt_id": int(attempt["id"]),
            "channel_id": int(command.channel_id),
            "binding_id": int(command.binding_id),
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
            source_event_type=_text(command.trigger_type) or "channel_enter",
            source_event_id=_text(trigger_payload.get("event_log_id") or trigger_payload.get("event_id")),
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
        projection_member = _upsert_member_projection(
            program_member=program_member,
            channel_id=int(command.channel_id),
            owner_staff_id=command.follow_user_userid,
            source_type=_text(trigger_payload.get("source_type")) or SOURCE_TYPE_QRCODE,
            audience_code=resolved["audience_code"],
            audience_entered_at=resolved["stage_entered_at"],
            entry_reason=resolved["entry_reason"],
            snapshot=snapshot,
        )
        get_db().commit()
        hook = _realtime_operation_task_hook(
            member_id=_int((projection_member or {}).get("id")),
            external_contact_id=external_contact_id,
            operator_id=_text(command.trigger_type) or "program_admission",
            entry_source="program_admission",
        )
        payload = _with_realtime_operation_task_hook(
            {
                "admission_status": resolved["admission_status"],
                "accepted": resolved["admission_status"] in {ADMISSION_ACCEPTED, ADMISSION_WAITING, ADMISSION_CONVERTED},
                "reason": resolved["entry_reason"],
                "program_member": program_member,
                "stage_history": stage_history,
                "admission_attempt": attempt,
                "projection_member": projection_member,
                "legacy_member": projection_member,
                "member_id": _int((projection_member or {}).get("id")),
                "cleaning_result": resolved,
                "segmentation": segmentation,
            },
            hook,
        )
        return self._complete_result(payload)


def admit_channel_contact_to_program(
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    *,
    follow_user_userid: str = "",
    trigger_payload: dict[str, Any] | None = None,
    trigger_time: datetime | str | None = None,
    trigger_type: str = "qrcode_enter",
) -> dict[str, Any]:
    return AutomationProgramAdmissionService().admit(
        AutomationAdmissionCommand(
            program_id=int(program_id),
            channel_id=int(channel_id),
            binding_id=int(binding_id),
            external_contact_id=_text(external_contact_id),
            follow_user_userid=_text(follow_user_userid),
            trigger_payload=dict(trigger_payload or {}),
            trigger_time=trigger_time,
            trigger_type=_text(trigger_type) or "qrcode_enter",
        )
    )


def _event_execution_id_for_task(task_id: int, audience_entry_id: int) -> str:
    return f"actask-event-{int(task_id)}-{int(audience_entry_id)}"


def _stage_filter(task: dict[str, Any]) -> dict[str, str]:
    stage_code = _text(task.get("target_stage_code"))
    audience_code = _text(task.get("target_audience_code")) or AUDIENCE_OPERATING
    if stage_code == STAGE_ORDER_REVIEW:
        return {"audience_code": AUDIENCE_PENDING_QUESTIONNAIRE, "entry_reason": ENTRY_REASON_ORDER_REVIEW_PENDING}
    if stage_code == STAGE_QUESTIONNAIRE_REVIEW:
        return {"audience_code": AUDIENCE_PENDING_QUESTIONNAIRE, "entry_reason": ENTRY_REASON_QUESTIONNAIRE_REVIEW_PENDING}
    if stage_code == STAGE_CONVERTED or audience_code == AUDIENCE_CONVERTED:
        return {"audience_code": AUDIENCE_CONVERTED, "entry_reason": ""}
    return {"audience_code": audience_code if audience_code in VALID_AUDIENCES else AUDIENCE_OPERATING, "entry_reason": ""}


def _program_channel_ids(program_id: int) -> set[int]:
    rows = _fetchall(
        """
        SELECT DISTINCT id
        FROM automation_channel
        WHERE program_id = ?
        UNION
        SELECT DISTINCT channel_id AS id
        FROM automation_program_channel_binding
        WHERE program_id = ?
        """,
        (int(program_id), int(program_id)),
    )
    return {_int(row.get("id")) for row in rows if _int(row.get("id"))}


def _member_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return dict(entry.get("member") or {})


def _program_scoped_member(task: dict[str, Any], member: dict[str, Any]) -> dict[str, Any]:
    program_id = _int(task.get("program_id"))
    external_contact_id = _text(member.get("external_contact_id"))
    if program_id <= 0 or not external_contact_id:
        return dict(member)
    row = _fetchone(
        """
        SELECT
            COALESCE(latest_source_channel_id, source_channel_id) AS source_channel_id,
            NULLIF(state_payload_json ->> 'profile_segment_key', '') AS profile_segment_key,
            NULLIF(state_payload_json ->> 'behavior_tier_key', '') AS behavior_tier_key
        FROM automation_program_member
        WHERE program_id = ?
          AND external_contact_id = ?
          AND in_program = TRUE
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (program_id, external_contact_id),
    )
    if not row:
        return dict(member)
    scoped = dict(member)
    source_channel_id = _int(row.get("source_channel_id"))
    if source_channel_id > 0:
        scoped["source_channel_id"] = source_channel_id
    for key in ("profile_segment_key", "behavior_tier_key"):
        value = _text(row.get(key))
        if value:
            scoped[key] = value
    return scoped


def _entry_for_event(*, member_id: int, audience_entry_id: int = 0) -> dict[str, Any] | None:
    member = _fetchone("SELECT * FROM automation_member WHERE id = ? LIMIT 1", (int(member_id),))
    if not member:
        return None
    sql = """
        SELECT *
        FROM automation_member_audience_entry
        WHERE member_id = ?
          AND is_current = TRUE
    """
    params: list[Any] = [int(member_id)]
    if int(audience_entry_id or 0) > 0:
        sql += " AND id = ?"
        params.append(int(audience_entry_id))
    sql += " ORDER BY entered_at DESC, id DESC LIMIT 1"
    entry = _fetchone(sql, tuple(params))
    if not entry:
        return None
    return {**entry, "member": dict(member)}


def _behavior_key(member: dict[str, Any]) -> str:
    return _text(member.get("behavior_tier_key"))


def _profile_key(member: dict[str, Any]) -> str:
    return _text(member.get("profile_segment_key"))


def _entry_matches_event_task(task: dict[str, Any], entry: dict[str, Any]) -> bool:
    if _text(task.get("status")) != "active":
        return False
    if _text(task.get("trigger_type")) != "audience_entered":
        return False
    stage = _stage_filter(task)
    if stage["audience_code"] != _text(entry.get("audience_code")):
        return False
    if stage["entry_reason"] and stage["entry_reason"] != _text(entry.get("entry_reason")):
        return False
    member = _program_scoped_member(task, _member_for_entry(entry))
    if _int(member.get("source_channel_id")) not in _program_channel_ids(_int(task.get("program_id"))):
        return False
    behavior_filter = _text(task.get("behavior_filter")) or "none"
    if behavior_filter != "none" and _behavior_key(member) != behavior_filter:
        return False
    if _text(task.get("content_mode")) == "profile_layered" and not _profile_key(member):
        return False
    return True


def _segment_content(task: dict[str, Any], segment_key: str) -> dict[str, Any]:
    for item in list(_json_loads(task.get("segment_contents_json"), default=[]) or []):
        if _text((item or {}).get("segment_key")) == _text(segment_key):
            return dict(item or {})
    return {}


def _agent_published_prompt_context(task: dict[str, Any]) -> dict[str, Any]:
    config = dict(_json_loads(task.get("agent_config_json"), default={}) or {})
    agent_code = _text(config.get("agent_code"))
    if not agent_code:
        return {
            "agent_published_prompt_present": False,
            "agent_published_role_prompt_present": False,
            "agent_published_task_prompt_present": False,
            "enabled_context_sources": [],
            "agent_prompt_error": "agent_code_missing",
        }
    try:
        row = _fetchone(
            """
            SELECT published_role_prompt, published_task_prompt, published_variables_json
            FROM automation_agent_config
            WHERE agent_code = ?
              AND enabled = TRUE
            LIMIT 1
            """,
            (agent_code,),
        )
    except Exception as exc:
        return {
            "agent_published_prompt_present": False,
            "agent_published_role_prompt_present": False,
            "agent_published_task_prompt_present": False,
            "enabled_context_sources": [],
            "agent_prompt_error": str(exc),
        }
    if not row:
        return {
            "agent_published_prompt_present": False,
            "agent_published_role_prompt_present": False,
            "agent_published_task_prompt_present": False,
            "enabled_context_sources": [],
            "agent_prompt_error": "agent_config_not_found",
        }
    role_prompt = _text(row.get("published_role_prompt"))
    task_prompt = _text(row.get("published_task_prompt"))
    variables = _json_loads(row.get("published_variables_json"), default=[])
    enabled_sources: list[str] = []
    for item in list(variables or []):
        source = _text((item or {}).get("source") if isinstance(item, dict) else "")
        if source:
            enabled_sources.append(source)
    return {
        "agent_published_prompt_present": bool(role_prompt or task_prompt),
        "agent_published_role_prompt_present": bool(role_prompt),
        "agent_published_task_prompt_present": bool(task_prompt),
        "enabled_context_sources": list(dict.fromkeys(enabled_sources)),
        "agent_prompt_error": "",
    }


def _member_questionnaire_context(member: dict[str, Any]) -> dict[str, Any]:
    external_contact_id = _text(member.get("external_contact_id"))
    phone = _text(member.get("phone"))
    if not external_contact_id and not phone:
        return {"questionnaire_context_available": False, "questionnaire_submission_id": 0, "questionnaire_answer_count": 0}
    clauses: list[str] = []
    params: list[Any] = []
    if external_contact_id:
        clauses.append("external_userid = ?")
        params.append(external_contact_id)
    if phone:
        clauses.append("mobile_snapshot = ?")
        params.append(phone)
    latest_submission = _fetchone(
        """
        SELECT id
        FROM questionnaire_submissions
        WHERE """
        + " OR ".join(clauses)
        + """
        ORDER BY submitted_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    submission_id = _int((latest_submission or {}).get("id"))
    answer_count = 0
    if submission_id > 0:
        row = _fetchone("SELECT COUNT(*) AS count FROM questionnaire_submission_answers WHERE submission_id = ?", (submission_id,))
        answer_count = _int((row or {}).get("count"))
    return {
        "questionnaire_context_available": answer_count > 0,
        "questionnaire_submission_id": submission_id,
        "questionnaire_answer_count": answer_count,
    }


def _agent_runtime_context(task: dict[str, Any], *, member: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(_json_loads(task.get("agent_config_json"), default={}) or {})
    context = _agent_published_prompt_context(task)
    enabled_sources = list(context.get("enabled_context_sources") or [])
    context.update(_member_questionnaire_context(member or {}) if member is not None else {
        "questionnaire_context_available": False,
        "questionnaire_submission_id": 0,
        "questionnaire_answer_count": 0,
    })
    context["questionnaire_context_required"] = bool(config.get("questionnaire_context_required")) or "questionnaire" in enabled_sources
    return context


def _agent_standard_content_text(task: dict[str, Any]) -> str:
    config = dict(_json_loads(task.get("agent_config_json"), default={}) or {})
    return (
        _text(config.get("fallback_content"))
        or _text(config.get("requirement"))
        or _text(config.get("prompt"))
        or _text(config.get("material_prompt"))
        or _text(task.get("description"))
    )


def _agent_runtime_plan(task: dict[str, Any], member: dict[str, Any], *, request_id: str, context: dict[str, Any]) -> dict[str, Any]:
    config = dict(_json_loads(task.get("agent_config_json"), default={}) or {})
    agent_code = _text(config.get("agent_code"))
    try:
        from aicrm_next.integration_gateway.automation_adapters import build_automation_agent_runtime_adapter

        adapter_result = build_automation_agent_runtime_adapter().generate_agent_output(
            agent_task_id=agent_code or f"operation_task:{_int(task.get('id'))}",
            member_id=str(_int(member.get("id"))),
            workflow_id=f"operation_task:{_int(task.get('program_id'))}",
            execution_id=_text(request_id),
            payload_summary={
                "task_id": _int(task.get("id")),
                "program_id": _int(task.get("program_id")),
                "questionnaire_submission_id": _int(context.get("questionnaire_submission_id")),
                "questionnaire_answer_count": _int(context.get("questionnaire_answer_count")),
            },
            idempotency_key=f"operation_task_agent:{_int(task.get('id'))}:{_int(member.get('id'))}:{_text(request_id)}",
        )
    except Exception as exc:
        adapter_result = {
            "ok": False,
            "result": {},
            "error_code": "agent_runtime_plan_failed",
            "error_message": str(exc),
            "side_effect_executed": False,
        }
    result = dict(adapter_result.get("result") or {})
    return {
        "adapter_contract": adapter_result,
        "agent_run_id": _text(result.get("agent_run_id")),
        "agent_output_id": _text(result.get("output_id") or result.get("agent_output_id")),
        "real_agent_runtime_executed": bool(result.get("real_agent_runtime_executed")) or bool(adapter_result.get("side_effect_executed")),
        "agent_runtime_planned": True,
    }


def _render_for_member(task: dict[str, Any], member: dict[str, Any], *, request_id: str = "") -> tuple[str, str, dict[str, Any]]:
    mode = _text(task.get("content_mode")) or "unified"
    if mode == "behavior_layered":
        segment_key = _behavior_key(member)
        content = _segment_content(task, segment_key)
        return segment_key, _text(content.get("content_text")), content
    if mode == "profile_layered":
        segment_key = _profile_key(member)
        content = _segment_content(task, segment_key)
        return segment_key, _text(content.get("content_text")), content
    if mode == "agent":
        config = dict(_json_loads(task.get("agent_config_json"), default={}) or {})
        agent_context = _agent_runtime_context(task, member=member)
        content_text = _agent_standard_content_text(task)
        plan = _agent_runtime_plan(task, member, request_id=request_id, context=agent_context)
        content = {
            **config,
            "agent_config": config,
            "agent_code": _text(config.get("agent_code")),
            "generation_source": "automation_operation_task",
            "content_source": "agent_runtime_plan" if not content_text else "standard_content",
            "request_id": _text(request_id),
            "fallback_reason": "" if content_text else "agent_runtime_plan_pending",
            "agent_published_prompt_present": bool(agent_context.get("agent_published_prompt_present")),
            "agent_published_role_prompt_present": bool(agent_context.get("agent_published_role_prompt_present")),
            "agent_published_task_prompt_present": bool(agent_context.get("agent_published_task_prompt_present")),
            "questionnaire_context_required": bool(agent_context.get("questionnaire_context_required")),
            "questionnaire_context_available": bool(agent_context.get("questionnaire_context_available")),
            "questionnaire_submission_id": _int(agent_context.get("questionnaire_submission_id")),
            "questionnaire_answer_count": _int(agent_context.get("questionnaire_answer_count")),
            "agent_runtime_context": agent_context,
            **plan,
        }
        return "agent", content_text, content
    content = dict(_json_loads(task.get("unified_content_json"), default={}) or {})
    return "unified", _text(content.get("content_text")), content


def _diagnostic_reason_from_contract(task: dict[str, Any], diagnostics: dict[str, Any]) -> str:
    errors = list(diagnostics.get("errors") or [])
    if not errors:
        return ""
    if "questionnaire_context_missing" in errors:
        return "questionnaire_context_missing"
    if "agent_runtime_content_missing" in errors:
        return "agent_runtime_content_missing"
    if "behavior_segment_content_missing" in errors:
        return "behavior_segment_content_missing"
    if "content_missing" in errors:
        return "content_missing"
    return "task_unpublishable"


def _diagnostic_reason_from_render(task: dict[str, Any], summary: dict[str, Any]) -> str:
    if not bool(summary.get("external_contact_id_present")):
        return "external_contact_id_missing"
    if bool(summary.get("send_body_present")):
        return ""
    if _text(task.get("content_mode")) == "agent":
        agent_diag = dict(summary.get("agent_runtime_diagnostics") or {})
        if (
            agent_diag.get("agent_published_prompt_present")
            and agent_diag.get("questionnaire_context_required")
            and not agent_diag.get("questionnaire_context_available")
            and not agent_diag.get("task_instruction_present")
            and not agent_diag.get("task_material_present")
        ):
            return "questionnaire_context_missing"
        return "agent_runtime_content_missing"
    if _text(task.get("content_mode")) == "behavior_layered":
        return "behavior_segment_content_missing"
    return "content_missing"


def _execution_without_items(execution: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if not execution or items:
        return False
    summary = dict(_json_loads(execution.get("summary_json"), default={}) or {})
    return _text(execution.get("status")) in {"failed", "finished", "queued"} and _int(summary.get("created_item_count")) == 0


def _event_task_diagnostic_result(
    *,
    task: dict[str, Any],
    execution_id: str,
    audience_entry_id: int,
    enqueued_count: int,
    status: str = "",
    reason: str = "",
    render_result_summary: Any = None,
    blocked_by_existing_execution: bool = False,
    blocked_by_existing_job: bool = False,
) -> dict[str, Any]:
    agent_context = (
        dict((render_result_summary or {}).get("agent_runtime_context") or {})
        if isinstance(render_result_summary, dict)
        else None
    )
    diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_context)
    return {
        "task_id": int(task.get("id") or 0),
        "task_name": _text(task.get("task_name")),
        "execution_id": _text(execution_id),
        "audience_entry_id": int(audience_entry_id or 0),
        "enqueued_count": int(enqueued_count or 0),
        "status": _text(status),
        "reason": _text(reason) or _diagnostic_reason_from_contract(task, diagnostics) or "ok",
        "content_diagnostics": diagnostics,
        "agent_runtime_diagnostics": agent_runtime_diagnostics(task, agent_runtime_context=agent_context) if _text(task.get("content_mode")) == "agent" else {},
        "render_result_summary": render_result_summary if isinstance(render_result_summary, dict) else {},
        "blocked_by_existing_execution": bool(blocked_by_existing_execution),
        "blocked_by_existing_job": bool(blocked_by_existing_job),
    }


def _insert_execution(payload: dict[str, Any]) -> dict[str, Any]:
    existing = _fetchone("SELECT * FROM automation_operation_task_execution WHERE execution_id = ? LIMIT 1", (_text(payload.get("execution_id")),))
    if existing:
        return existing
    return _fetchone(
        """
        INSERT INTO automation_operation_task_execution (
            execution_id, program_id, task_id, scheduled_for, status, target_count,
            enqueued_count, sent_count, failed_count, summary_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _text(payload.get("execution_id")),
            _int(payload.get("program_id")),
            _int(payload.get("task_id")),
            payload.get("scheduled_for"),
            _text(payload.get("status")) or "running",
            _int(payload.get("target_count")),
            _int(payload.get("enqueued_count")),
            _int(payload.get("sent_count")),
            _int(payload.get("failed_count")),
            _json_dumps(payload.get("summary_json") or {}),
        ),
    ) or {}


def _update_execution(execution_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _fetchone(
        """
        UPDATE automation_operation_task_execution
        SET status = ?, target_count = ?, enqueued_count = ?, sent_count = ?, failed_count = ?,
            summary_json = CAST(? AS jsonb),
            finished_at = CASE WHEN ? IN ('finished', 'failed', 'partial_failed') THEN CURRENT_TIMESTAMP ELSE finished_at END
        WHERE execution_id = ?
        RETURNING *
        """,
        (
            _text(payload.get("status")) or "running",
            _int(payload.get("target_count")),
            _int(payload.get("enqueued_count")),
            _int(payload.get("sent_count")),
            _int(payload.get("failed_count")),
            _json_dumps(payload.get("summary_json") or {}),
            _text(payload.get("status")),
            _text(execution_id),
        ),
    ) or {}


def _list_execution_items(execution_id: str) -> list[dict[str, Any]]:
    return _fetchall("SELECT * FROM automation_operation_task_execution_item WHERE execution_id = ? ORDER BY id ASC", (_text(execution_id),))


def _insert_execution_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    if _int(payload.get("audience_entry_id")):
        existing = _fetchone(
            """
            SELECT *
            FROM automation_operation_task_execution_item
            WHERE task_id = ?
              AND audience_entry_id = ?
            LIMIT 1
            """,
            (_int(payload.get("task_id")), _int(payload.get("audience_entry_id"))),
        )
        if existing:
            return None
    return _fetchone(
        """
        INSERT INTO automation_operation_task_execution_item (
            execution_id, task_id, member_id, audience_entry_id, external_contact_id,
            segment_key, rendered_content_text, content_snapshot_json, send_record_id,
            status, error_message, sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        RETURNING *
        """,
        (
            _text(payload.get("execution_id")),
            _int(payload.get("task_id")),
            _int(payload.get("member_id")),
            _int(payload.get("audience_entry_id")) or None,
            _text(payload.get("external_contact_id")),
            _text(payload.get("segment_key")),
            _text(payload.get("rendered_content_text")),
            _json_dumps(payload.get("content_snapshot_json") or {}),
            payload.get("send_record_id"),
            _text(payload.get("status")) or "pending",
            _text(payload.get("error_message")),
            payload.get("sent_at"),
        ),
    )


def _enqueue_broadcast_job(*, task: dict[str, Any], execution: dict[str, Any], item: dict[str, Any], scheduled_for: datetime, content_text: str, content: dict[str, Any]) -> dict[str, Any]:
    source_id = f"{int(task['id'])}:audience_entered:{int(item.get('audience_entry_id') or 0)}"
    existing = _fetchone(
        """
        SELECT *
        FROM broadcast_jobs
        WHERE source_type = 'operation_task'
          AND source_table = 'automation_operation_task_execution'
          AND source_id = ?
        LIMIT 1
        """,
        (source_id,),
    )
    if existing:
        return existing
    return _fetchone(
        """
        INSERT INTO broadcast_jobs (
            source_type, source_id, source_table, scheduled_for, priority, batch_key,
            business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
            status, requires_approval, target_external_userids, target_count, target_summary,
            content_type, content_payload, content_summary, trace_id, created_by,
            created_at, updated_at
        )
        VALUES (
            'operation_task', ?, 'automation_operation_task_execution', ?, 50, ?,
            'automation_ops', ?, 'wecom_private', 'external_userid', '{}'::jsonb, CAST(? AS jsonb),
            'queued', FALSE, CAST(? AS jsonb), 1, ?,
            'private_message', CAST(? AS jsonb), ?, ?, ?,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING *
        """,
        (
            source_id,
            scheduled_for,
            f"operation_task:{int(task.get('id') or 0)}",
            f"operation_task:{source_id}",
            _json_dumps({"real_external_call_executed": False, "side_effect_plan": "broadcast_job"}),
            _json_dumps([_text(item.get("external_contact_id"))]),
            _text(item.get("external_contact_id")),
            _json_dumps(
                {
                    "content_text": content_text,
                    "content": content,
                    "task_id": int(task.get("id") or 0),
                    "execution_id": _text(execution.get("execution_id")),
                    "execution_item_id": int(item.get("id") or 0),
                    "trigger_type": "audience_entered",
                }
            ),
            _text(content_text)[:500],
            f"operation_task:{source_id}",
            _text(task.get("updated_by") or task.get("created_by") or "automation"),
        ),
    ) or {}


def _materialize_event_task_execution(*, task: dict[str, Any], entry: dict[str, Any], operator_id: str) -> dict[str, Any]:
    scheduled_for = datetime.now()
    audience_entry_id = _int(entry.get("id"))
    execution_id = _event_execution_id_for_task(_int(task.get("id")), audience_entry_id)
    execution = _insert_execution(
        {
            "execution_id": execution_id,
            "program_id": task["program_id"],
            "task_id": task["id"],
            "scheduled_for": scheduled_for,
            "status": "running",
            "target_count": 0,
        }
    )
    existing_items = _list_execution_items(execution_id)
    if _execution_without_items(execution, existing_items):
        return _event_task_diagnostic_result(
            task=task,
            execution_id=execution_id,
            audience_entry_id=audience_entry_id,
            enqueued_count=0,
            status=_text(execution.get("status")),
            reason="existing_execution_without_items",
            blocked_by_existing_execution=True,
        )
    if existing_items:
        return _event_task_diagnostic_result(
            task=task,
            execution_id=execution_id,
            audience_entry_id=audience_entry_id,
            enqueued_count=0,
            status=_text(execution.get("status")),
            reason="existing_execution",
            blocked_by_existing_execution=True,
        )
    member = _program_scoped_member(task, _member_for_entry(entry))
    agent_context = _agent_runtime_context(task, member=member) if _text(task.get("content_mode")) == "agent" else None
    diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_context)
    contract_reason = _diagnostic_reason_from_contract(task, diagnostics)
    if contract_reason:
        render_summary = {
            "audience_entry_id": audience_entry_id,
            "member_id": _int(member.get("id") or entry.get("member_id")),
            "segment_key": "agent" if _text(task.get("content_mode")) == "agent" else "",
            "content_text_present": False,
            "send_body_present": False,
            "external_contact_id_present": bool(_text(member.get("external_contact_id"))),
            "agent_runtime_diagnostics": diagnostics.get("details", {}).get("agent_runtime_diagnostics") or {},
            "agent_runtime_context": agent_context or {},
        }
        execution = _update_execution(
            execution_id,
            {
                "status": "failed",
                "target_count": 1,
                "enqueued_count": 0,
                "sent_count": 0,
                "failed_count": 1,
                "summary_json": {
                    "created_item_count": 0,
                    "materialized_by": _text(operator_id) or "operation_task_runner",
                    "reason": contract_reason,
                    "content_diagnostics": diagnostics,
                    "no_execution_items": True,
                    "trigger_type": "audience_entered",
                    "render_result_summary": render_summary,
                },
            },
        )
        return _event_task_diagnostic_result(
            task=task,
            execution_id=execution_id,
            audience_entry_id=audience_entry_id,
            enqueued_count=0,
            status=_text(execution.get("status")),
            reason=contract_reason,
            render_result_summary=render_summary,
        )
    segment_key, content_text, content = _render_for_member(task, member, request_id=f"{execution_id}:{audience_entry_id}")
    render_summary = {
        "audience_entry_id": audience_entry_id,
        "member_id": _int(member.get("id") or entry.get("member_id")),
        "segment_key": segment_key,
        "content_text_present": bool(_text(content_text)),
        "send_body_present": (
            bool(agent_runtime_diagnostics(task, agent_runtime_context=agent_context).get("expected_send_body_present"))
            if _text(task.get("content_mode")) == "agent"
            else contract_has_send_body(content, content_text=content_text)
        ),
        "external_contact_id_present": bool(_text(member.get("external_contact_id"))),
        "agent_runtime_diagnostics": agent_runtime_diagnostics(task, agent_runtime_context=agent_context) if _text(task.get("content_mode")) == "agent" else {},
        "agent_runtime_context": agent_context or {},
    }
    if not render_summary["send_body_present"] or not render_summary["external_contact_id_present"]:
        reason = _diagnostic_reason_from_render(task, render_summary)
        execution = _update_execution(
            execution_id,
            {
                "status": "failed",
                "target_count": 1,
                "enqueued_count": 0,
                "sent_count": 0,
                "failed_count": 1,
                "summary_json": {
                    "created_item_count": 0,
                    "materialized_by": _text(operator_id) or "operation_task_runner",
                    "reason": reason,
                    "render_result_summary": [render_summary],
                    "no_execution_items": True,
                    "trigger_type": "audience_entered",
                },
            },
        )
        return _event_task_diagnostic_result(
            task=task,
            execution_id=execution_id,
            audience_entry_id=audience_entry_id,
            enqueued_count=0,
            status=_text(execution.get("status")),
            reason=reason,
            render_result_summary=render_summary,
        )
    item = _insert_execution_item(
        {
            "execution_id": execution_id,
            "task_id": task["id"],
            "member_id": member.get("id") or entry.get("member_id"),
            "audience_entry_id": audience_entry_id,
            "external_contact_id": member.get("external_contact_id"),
            "segment_key": segment_key,
            "rendered_content_text": content_text,
            "content_snapshot_json": content,
            "status": "queued",
        }
    )
    created_count = 1 if item else 0
    job = None
    if item:
        job = _enqueue_broadcast_job(task=task, execution=execution, item=item, scheduled_for=scheduled_for, content_text=content_text, content=content)
    execution = _update_execution(
        execution_id,
        {
            "status": "queued" if created_count else "finished",
            "target_count": 1,
            "enqueued_count": created_count,
            "sent_count": 0,
            "failed_count": 0 if created_count else 1,
            "summary_json": {
                "created_item_count": created_count,
                "materialized_by": _text(operator_id) or "operation_task_runner",
                "reason": "" if created_count else "duplicate_execution_item",
                "trigger_type": "audience_entered",
                "broadcast_job_id": _int((job or {}).get("id")),
            },
        },
    )
    return _event_task_diagnostic_result(
        task=task,
        execution_id=execution_id,
        audience_entry_id=audience_entry_id,
        enqueued_count=created_count,
        status=_text(execution.get("status")),
        reason="ok" if created_count else "duplicate_execution_item",
        render_result_summary=render_summary,
    )


class OperationTaskRealtimeTriggerService:
    def trigger(self, event: AudienceTransitionEvent) -> dict[str, Any]:
        return run_audience_entered_operation_tasks(
            member_id=int(event.member_id),
            audience_code=event.audience_code,
            audience_entry_id=int(event.audience_entry_id),
            operator_id=event.operator_id or event.entry_source or "audience_entered",
            entry_source=event.entry_source,
        )


def run_audience_entered_operation_tasks(
    *,
    member_id: int,
    audience_code: str,
    audience_entry_id: int = 0,
    now: datetime | None = None,
    operator_id: str = "operation_task_event",
    entry_source: str = "",
) -> dict[str, Any]:
    entry = _entry_for_event(member_id=int(member_id), audience_entry_id=int(audience_entry_id or 0))
    if not entry:
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "audience_entry_not_found"}
    if _text(entry.get("audience_code")) != _text(audience_code):
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "audience_code_not_matched"}
    member = _member_for_entry(entry)
    if _text(entry_source) == "questionnaire_submit" and _int(member.get("source_channel_id")) <= 0:
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "source_channel_missing"}
    snapshot = dict(_json_loads(entry.get("source_snapshot_json"), default={}) or {})
    program_id = _int(snapshot.get("program_id"))
    if program_id <= 0:
        program_member = _fetchone(
            """
            SELECT program_id
            FROM automation_program_member
            WHERE external_contact_id = ?
              AND in_program = TRUE
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (_text(member.get("external_contact_id")),),
        )
        program_id = _int((program_member or {}).get("program_id"))
    if program_id <= 0:
        return {"ok": True, "ran": 0, "enqueued_count": 0, "results": [], "reason": "program_member_not_found"}
    tasks = _fetchall(
        """
        SELECT *
        FROM automation_operation_task
        WHERE program_id = ?
          AND status = 'active'
          AND trigger_type = 'audience_entered'
        ORDER BY id ASC
        """,
        (program_id,),
    )
    results: list[dict[str, Any]] = []
    for task in tasks:
        task = {
            **task,
            "unified_content_json": _json_loads(task.get("unified_content_json"), default={}),
            "segment_contents_json": _json_loads(task.get("segment_contents_json"), default=[]),
            "agent_config_json": _json_loads(task.get("agent_config_json"), default={}),
        }
        if not _entry_matches_event_task(task, entry):
            continue
        results.append(_materialize_event_task_execution(task=task, entry=entry, operator_id=operator_id))
    get_db().commit()
    enqueued_count = sum(_int(item.get("enqueued_count")) for item in results)
    queued_jobs = [
        {
            "task_id": _int(item.get("task_id")),
            "audience_entry_id": _int(item.get("audience_entry_id")),
            "execution_id": _text(item.get("execution_id")),
        }
        for item in results
        if _int(item.get("enqueued_count")) > 0
    ]
    return {
        "ok": True,
        "ran": len([item for item in results if _text(item.get("reason")) != "existing_execution"]),
        "enqueued_count": enqueued_count,
        "results": results,
        "reason": "" if results else "no_matching_audience_entered_tasks",
        "side_effect_plan": {
            "planned": bool(queued_jobs),
            "effect_type": "operation_task.broadcast_job",
            "queued_job_count": enqueued_count,
            "items": queued_jobs,
            "real_external_call_executed": False,
        },
        "source_status": "next_command",
        "fallback_used": False,
        "real_external_call_executed": False,
    }
