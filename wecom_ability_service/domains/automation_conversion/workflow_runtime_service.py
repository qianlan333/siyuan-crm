from __future__ import annotations

from typing import Any

from . import workflow_runtime as _runtime


def run_due_conversion_workflows(*, operator_id: str = "", operator_type: str = "system") -> dict[str, Any]:
    """Internal-only owner wrapper for workflow due-runner execution."""

    return _runtime.run_due_conversion_workflows(operator_id=operator_id, operator_type=operator_type)


def sync_conversion_member_audience(member: dict[str, Any]) -> dict[str, Any]:
    """Internal-only owner wrapper for single-member audience sync."""

    return _runtime.sync_conversion_member_audience(member)


def sync_all_conversion_member_audiences() -> dict[str, Any]:
    """Internal-only owner wrapper for full audience sweep."""

    return _runtime.sync_all_conversion_member_audiences()


__all__ = [
    "run_due_conversion_workflows",
    "sync_all_conversion_member_audiences",
    "sync_conversion_member_audience",
]
