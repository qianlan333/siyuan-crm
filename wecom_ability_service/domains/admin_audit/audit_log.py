"""Unified audit logging entry point.

Three domains (``admin_console``, ``admin_config``, ``admin_jobs``) had
parallel ``_audit_log`` implementations with subtly different signatures.
They all wrote to ``admin_operation_logs`` via
``admin_config_repo.insert_admin_operation_log``, so consolidating them here
keeps the row format consistent and gives us a single place to add things
like ``request_id`` propagation, structured logging, or future PII scrub.

``AuditEvent`` is a lightweight value object for callers that prefer keyword
construction over positional args. ``record_audit_event`` is the canonical
write path; the per-domain wrappers stay in place as thin shims so existing
imports keep working without forcing every call site to change at once.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

audit_logger = logging.getLogger("admin_audit")


@dataclass
class AuditEvent:
    operator: str
    action_type: str
    target_type: str
    target_id: str = ""
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""

    def normalized(self) -> "AuditEvent":
        return AuditEvent(
            operator=str(self.operator or "").strip(),
            action_type=str(self.action_type or "").strip(),
            target_type=str(self.target_type or "").strip(),
            target_id=str(self.target_id or "").strip(),
            before=dict(self.before or {}),
            after=dict(self.after or {}),
            request_id=str(self.request_id or "").strip(),
        )


def record_audit_event(event: AuditEvent) -> None:
    """Persist ``event`` to the admin operation log + emit a structured log line.

    Importing the repo lazily keeps the module load order tolerant — earlier
    modules import this file before ``admin_config`` is fully initialized.
    """
    from ..admin_config import repo as admin_config_repo
    from ...observability import get_request_id

    e = event.normalized()
    request_id = e.request_id or get_request_id()
    audit_logger.info(
        "audit operator=%s action=%s target=%s/%s request_id=%s",
        e.operator,
        e.action_type,
        e.target_type,
        e.target_id,
        request_id,
    )
    admin_config_repo.insert_admin_operation_log(
        operator=e.operator,
        action_type=e.action_type,
        target_type=e.target_type,
        target_id=e.target_id,
        before_json=e.before,
        after_json=e.after,
    )


def record_audit(
    *,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str = "",
) -> None:
    """Keyword-arg convenience wrapper around ``record_audit_event``.

    Existing per-domain ``_audit_log`` shims call this so all three reach the
    same code path / log format / future PII handling.
    """
    record_audit_event(
        AuditEvent(
            operator=operator,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before=before or {},
            after=after or {},
            request_id=request_id,
        )
    )
