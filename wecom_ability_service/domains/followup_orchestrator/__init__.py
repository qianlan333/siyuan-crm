from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "FOLLOWUP_ORCHESTRATOR_FLAG_KEY",
    "FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS",
    "FOLLOWUP_ORCHESTRATOR_MISSION_STATES",
    "apply_followup_orchestrator_mission_action",
    "build_followup_orchestrator_customer_payload",
    "build_followup_orchestrator_my_missions_payload",
    "build_followup_orchestrator_overview_payload",
    "build_followup_orchestrator_team_board_payload",
    "execute_followup_orchestrator_mission_item_action",
    "followup_orchestrator_feature_gate_summary",
    "get_followup_orchestrator_mission_detail_payload",
    "is_followup_orchestrator_enabled",
    "preview_followup_orchestrator_mission_item_action",
    "sync_followup_orchestrator_missions",
    "undo_followup_orchestrator_mission_item_action",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    service = import_module(".service", __name__)
    value = getattr(service, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
