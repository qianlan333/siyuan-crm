from __future__ import annotations

from typing import Any

from .ai_enhancement import (
    apply_followup_orchestrator_ai_enhancement,
    generate_followup_orchestrator_ai_enhancement,
)


def generate_followup_ai_enhancement(*, mission: dict[str, Any]) -> dict[str, Any]:
    """Internal owner for followup AI recommendation generation."""
    return generate_followup_orchestrator_ai_enhancement(mission=mission)


def apply_followup_ai_enhancement(*, mission: dict[str, Any]) -> dict[str, Any]:
    """Internal owner for followup AI recommendation projection."""
    return apply_followup_orchestrator_ai_enhancement(mission=mission)


def apply_mission_ai_if_enabled(mission: dict[str, Any]) -> dict[str, Any]:
    """Internal helper used by followup mission read projections."""
    if not isinstance(mission, dict):
        return {}
    return apply_followup_ai_enhancement(mission=dict(mission))
