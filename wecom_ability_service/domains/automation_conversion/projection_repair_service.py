from __future__ import annotations

import json
from typing import Any

from ...db import get_db
from . import repo as member_repo
from . import workflow_repo


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _latest_submission(external_userid: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT *
        FROM questionnaire_submissions
        WHERE external_userid = ?
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (_text(external_userid),),
    ).fetchone()
    return dict(row or {})


def _program_member(program_id: int, external_userid: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT *
        FROM automation_program_member
        WHERE program_id = ?
          AND external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_id), _text(external_userid)),
    ).fetchone()
    return dict(row or {})


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted(after)
        if before.get(key) != after.get(key)
    }


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def repair_automation_member_projection(
    *,
    external_userid: str,
    program_id: int,
    dry_run: bool = True,
    apply: bool = False,
    operator_id: str = "projection_repair",
) -> dict[str, Any]:
    normalized_external = _text(external_userid)
    if not normalized_external:
        raise ValueError("external_userid is required")
    if _int(program_id) <= 0:
        raise ValueError("program_id is required")
    do_apply = bool(apply) and not bool(dry_run)

    member = member_repo.get_member_by_external_contact_id(normalized_external) or {}
    if not member:
        return {"ok": True, "dry_run": not do_apply, "updated": False, "reason": "member_not_found"}
    if _text(member.get("current_audience_code")) == "converted":
        return {"ok": True, "dry_run": not do_apply, "updated": False, "reason": "converted_member_not_repaired", "member": member}

    submission = _latest_submission(normalized_external)
    entries = workflow_repo.list_member_audience_entry_rows(_int(member.get("id")), current_only=True)
    current_entry = dict(entries[0] if entries else {})
    program_member = _program_member(_int(program_id), normalized_external)
    should_operating = bool(
        submission
        and _text(current_entry.get("audience_code")) == "operating"
        and _text(current_entry.get("entry_reason")) == "audience_entry_rule_passed"
    )

    member_after = dict(member)
    program_member_after = dict(program_member)
    reason = "already_consistent"
    if should_operating:
        member_after.update(
            {
                "questionnaire_status": "submitted",
                "current_pool": "operating",
                "current_audience_code": "operating",
                "current_audience_entered_at": _text(current_entry.get("entered_at")) or _text(member.get("current_audience_entered_at")),
                "phone": _text(member.get("phone")) or _text(submission.get("mobile_snapshot")),
            }
        )
        if program_member:
            state_payload = program_member.get("state_payload_json") or {}
            if isinstance(state_payload, str):
                try:
                    state_payload = json.loads(state_payload)
                except (TypeError, ValueError):
                    state_payload = {}
            program_member_after.update(
                {
                    "current_stage_code": "operating",
                    "current_audience_code": "operating",
                    "state_payload_json": {
                        **dict(state_payload or {}),
                        "questionnaire_status": "submitted",
                        "questionnaire_submitted_at": _text(submission.get("submitted_at")),
                    },
                }
            )
        reason = "projection_repair_ready"
    else:
        reason = "no_operating_questionnaire_projection_rule_matched"

    member_diff = _diff(member, member_after)
    program_member_diff = _diff(program_member, program_member_after) if program_member else {}
    updated = bool(member_diff or program_member_diff)

    if do_apply and updated:
        before = _json_safe({"member": member, "program_member": program_member})
        after = _json_safe({"member": member_after, "program_member": program_member_after})
        member_repo.update_member(_int(member["id"]), member_after)
        if program_member and program_member_diff:
            get_db().execute(
                """
                UPDATE automation_program_member
                SET current_stage_code = ?,
                    current_audience_code = ?,
                    state_payload_json = CAST(? AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    _text(program_member_after.get("current_stage_code")),
                    _text(program_member_after.get("current_audience_code")),
                    json.dumps(program_member_after.get("state_payload_json") or {}, ensure_ascii=False),
                    _int(program_member_after.get("id")),
                ),
            )
        member_repo.insert_event(
            member_id=_int(member["id"]),
            action="projection_repair",
            operator_type="system",
            operator_id=_text(operator_id) or "projection_repair",
            before_snapshot=before,
            after_snapshot=after,
            remark="repair automation member questionnaire/audience projection",
        )
        get_db().commit()

    return {
        "ok": True,
        "dry_run": not do_apply,
        "updated": updated and do_apply,
        "would_update": updated and not do_apply,
        "reason": reason,
        "external_userid": normalized_external,
        "program_id": int(program_id),
        "submission": {
            "id": _int(submission.get("id")),
            "questionnaire_id": _int(submission.get("questionnaire_id")),
            "submitted_at": _text(submission.get("submitted_at")),
            "mobile_snapshot": _text(submission.get("mobile_snapshot")),
        },
        "current_entry": {
            "id": _int(current_entry.get("id")),
            "audience_code": _text(current_entry.get("audience_code")),
            "entry_reason": _text(current_entry.get("entry_reason")),
            "is_current": bool(current_entry.get("is_current")),
        },
        "diff": {"member": member_diff, "program_member": program_member_diff},
    }
