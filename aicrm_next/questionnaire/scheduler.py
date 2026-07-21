from __future__ import annotations

from typing import Any

from .continuation import QuestionnaireContinuationService, questionnaire_continuation_enabled


def run_questionnaire_continuation_reconciliation(
    *,
    execute: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    if not questionnaire_continuation_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "reason": "questionnaire_continuation_disabled",
            "database_mutation_performed": False,
            "real_external_call_executed": False,
        }
    if not execute:
        return {
            "ok": True,
            "status": "dry_run",
            "reason": "execute_flag_required",
            "database_mutation_performed": False,
            "real_external_call_executed": False,
        }
    result = QuestionnaireContinuationService().reconcile(limit=max(1, min(int(limit or 100), 500)))
    return {
        **result,
        "status": "completed",
        "database_mutation_performed": bool(
            int(result.get("expired_count") or 0) or int(result.get("claimed_count") or 0)
        ),
    }


__all__ = ["run_questionnaire_continuation_reconciliation"]
