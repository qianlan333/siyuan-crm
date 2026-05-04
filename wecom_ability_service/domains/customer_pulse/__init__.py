from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "build_customer_pulse_dashboard_group",
    "build_customer_pulse_customer_detail_payload",
    "build_customer_pulse_first_wave_review_report",
    "build_customer_pulse_inbox_payload",
    "build_customer_pulse_ops_dashboard_payload",
    "build_customer_pulse_tenant_rollout_report",
    "customer_pulse_feature_gate_summary",
    "customer_pulse_rollout_whitelist_summary",
    "enqueue_customer_pulse_recompute",
    "execute_customer_pulse_card_action",
    "get_customer_pulse_card_evidence_payload",
    "get_customer_pulse_card_payload",
    "is_customer_pulse_inbox_enabled",
    "preview_customer_pulse_card_action",
    "refresh_customer_pulse_cards",
    "run_due_customer_pulse_recompute_jobs",
    "run_due_customer_pulse_snapshot_job",
    "submit_customer_pulse_feedback",
    "undo_customer_pulse_card_action_execution",
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
