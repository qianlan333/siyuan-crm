from __future__ import annotations

import logging
from typing import Any

from ...db import get_db
from . import member_state_service, repo, workflow_runtime


logger = logging.getLogger("automation_conversion.questionnaire_bridge")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _member_from_sync_result(sync_result: dict[str, Any], *, external_contact_id: str = "", phone: str = "") -> dict[str, Any] | None:
    member = dict(sync_result.get("member") or {})
    member_id = int(member.get("id") or 0)
    if member_id > 0:
        return repo.get_member_by_id(member_id) or member
    return repo.get_member_by_external_contact_id(_normalized_text(external_contact_id)) or repo.get_member_by_phone(
        _normalized_text(phone)
    )


def _hook_reason(hook: dict[str, Any]) -> str:
    return (
        _normalized_text(hook.get("realtime_operation_tasks_reason"))
        or _normalized_text(hook.get("realtime_operation_tasks_error"))
        or ("ok" if bool(hook.get("ok", True)) else "realtime_hook_failed")
    )


def sync_questionnaire_submission_audience_transition(
    *,
    external_contact_id: str = "",
    phone: str = "",
    questionnaire_id: int | None = None,
    submission_id: int | None = None,
    operator_id: str = "questionnaire_submit",
) -> dict[str, Any]:
    """Sync a questionnaire submission into the committed audience-transition flow."""

    normalized_external = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    normalized_operator = _normalized_text(operator_id) or "questionnaire_submit"
    normalized_questionnaire_id = int(questionnaire_id or 0)
    normalized_submission_id = int(submission_id or 0)
    try:
        member_sync = member_state_service.sync_member_from_questionnaire_submission(
            external_contact_id=normalized_external,
            phone=normalized_phone,
            questionnaire_id=normalized_questionnaire_id,
            operator_id=normalized_operator,
        )
        member = _member_from_sync_result(
            member_sync,
            external_contact_id=normalized_external,
            phone=normalized_phone,
        )
        if not member:
            return {
                "ok": True,
                "updated": False,
                "reason": "member_not_found",
                "member_sync": member_sync,
                "submission_id": normalized_submission_id,
                "questionnaire_id": normalized_questionnaire_id,
            }

        source_channel_missing = _positive_int(member.get("source_channel_id")) <= 0
        audience_sync = workflow_runtime.sync_conversion_member_audience(member)
        get_db().commit()

        if source_channel_missing:
            hook_payload = {
                "ok": True,
                "audience_entry_id": 0,
                "audience_code": "",
                "entry_reason": "",
                "realtime_operation_tasks_ran": 0,
                "realtime_operation_tasks_enqueued_count": 0,
                "realtime_operation_tasks_results": [],
                "realtime_operation_tasks_error": "",
                "realtime_operation_tasks_reason": "source_channel_missing",
            }
            return {
                "ok": True,
                "updated": bool(member_sync.get("updated")) or bool(audience_sync.get("updated")),
                "reason": "source_channel_missing",
                "member_id": int(member.get("id") or 0),
                "submission_id": normalized_submission_id,
                "questionnaire_id": normalized_questionnaire_id,
                "member_sync": member_sync,
                "audience_sync": audience_sync,
                "realtime_task_hook": hook_payload,
            }

        from aicrm_next.automation_engine.audience_transition.application import handle_committed_audience_transition

        hook = handle_committed_audience_transition(
            member_id=int(member.get("id") or 0),
            external_userid=_normalized_text(member.get("external_contact_id")) or normalized_external,
            operator_id=normalized_operator,
            entry_source="questionnaire_submit",
        )
        hook_payload = dict(hook or {})
        hook_payload["ok"] = not bool(_normalized_text(hook_payload.get("realtime_operation_tasks_error")))
        result = {
            "ok": bool(hook_payload.get("ok", True)),
            "updated": bool(member_sync.get("updated")) or bool(audience_sync.get("updated")),
            "reason": _hook_reason(hook_payload),
            "member_id": int(member.get("id") or 0),
            "submission_id": normalized_submission_id,
            "questionnaire_id": normalized_questionnaire_id,
            "member_sync": member_sync,
            "audience_sync": audience_sync,
            "realtime_task_hook": hook_payload,
        }
        logger.info(
            "questionnaire audience transition sync submission_id=%s questionnaire_id=%s member_id=%s reason=%s enqueued=%s",
            normalized_submission_id,
            normalized_questionnaire_id,
            result["member_id"],
            result["reason"],
            int(hook_payload.get("realtime_operation_tasks_enqueued_count") or 0),
        )
        return result
    except Exception as exc:
        try:
            get_db().rollback()
        except Exception:
            pass
        logger.exception(
            "questionnaire audience transition sync failed submission_id=%s questionnaire_id=%s external_userid=%s",
            normalized_submission_id,
            normalized_questionnaire_id,
            normalized_external,
        )
        return {
            "ok": False,
            "updated": False,
            "reason": "questionnaire_audience_transition_sync_failed",
            "error": str(exc),
            "submission_id": normalized_submission_id,
            "questionnaire_id": normalized_questionnaire_id,
        }
