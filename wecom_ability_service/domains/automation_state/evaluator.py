from __future__ import annotations

from typing import Any

from .state_defs import (
    FOCUS_POOL_KEYS,
    POOL_SILENT,
)

POOL_STAGE = "pool"
ACTIONABLE_POOL_STAGE_KEYS = {f"{POOL_STAGE}/{pool_key}" for pool_key in FOCUS_POOL_KEYS}


def _text(value: Any) -> str:
    return str(value or "").strip()


def evaluate_marketing_eligibility(
    *,
    trial_opened: bool,
    activated: bool,
    has_questionnaire_submission: bool,
    converted: bool,
    has_external_userid: bool,
    final_pool_key: str,
    stage_key: str,
    exit_reason: str = "",
) -> dict[str, Any]:
    eligible_for_conversion = bool(
        (trial_opened or activated)
        and has_questionnaire_submission
        and final_pool_key != POOL_SILENT
        and not converted
    )
    openclaw_eligible = bool(
        stage_key in ACTIONABLE_POOL_STAGE_KEYS
        and has_external_userid
        and not converted
        and final_pool_key != POOL_SILENT
    )
    return {
        "eligible_for_conversion": eligible_for_conversion,
        "openclaw_eligible": openclaw_eligible,
        "ineligible_reason": "" if eligible_for_conversion else _text(exit_reason),
    }
