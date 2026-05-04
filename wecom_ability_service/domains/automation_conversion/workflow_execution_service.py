from __future__ import annotations

from . import workflow_service as _workflow_service


def get_conversion_dashboard_payload() -> dict:
    """Internal-only owner wrapper for workflow dashboard read model."""

    return _workflow_service.get_conversion_dashboard_payload()


def list_conversion_workflow_executions(*, workflow_id: int | None = None, node_id: int | None = None, limit: int = 20) -> dict:
    """Internal-only owner wrapper for workflow execution list queries."""

    return _workflow_service.list_conversion_workflow_executions(workflow_id=workflow_id, node_id=node_id, limit=limit)


def get_conversion_workflow_execution_detail(execution_row_id: int) -> dict:
    """Internal-only owner wrapper for workflow execution detail queries."""

    return _workflow_service.get_conversion_workflow_execution_detail(execution_row_id)


def get_conversion_workflow_execution_item_detail(execution_item_id: int) -> dict:
    """Internal-only owner wrapper for workflow execution item detail queries."""

    return _workflow_service.get_conversion_workflow_execution_item_detail(execution_item_id)


def get_conversion_workflow_execution_bundle(execution_row_id: int) -> dict:
    """Internal-only owner wrapper for workflow execution bundle reads."""

    return _workflow_service.get_conversion_workflow_execution_bundle(execution_row_id)


__all__ = [
    "get_conversion_dashboard_payload",
    "get_conversion_workflow_execution_bundle",
    "get_conversion_workflow_execution_detail",
    "get_conversion_workflow_execution_item_detail",
    "list_conversion_workflow_executions",
]
