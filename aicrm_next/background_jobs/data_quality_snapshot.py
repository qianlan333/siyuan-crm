from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from aicrm_next.data_health.quality_registry import (
    data_quality_checks_by_group,
    list_data_quality_check_definitions,
    list_data_quality_groups,
)


DEFAULT_DATA_QUALITY_SNAPSHOT_OPERATOR = "data_quality_snapshot_scheduler"


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _operator(value: str | None) -> str:
    configured = value or os.getenv("DATA_QUALITY_SNAPSHOT_OPERATOR", DEFAULT_DATA_QUALITY_SNAPSHOT_OPERATOR)
    return configured.strip() or DEFAULT_DATA_QUALITY_SNAPSHOT_OPERATOR


def _snapshot_id(*, scanned_at: datetime, checks: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    digest.update(scanned_at.isoformat().encode("utf-8"))
    for check in checks:
        digest.update(str(check.get("check_id") or "").encode("utf-8"))
        digest.update(str(check.get("probe_status") or "").encode("utf-8"))
    return f"dqs_{digest.hexdigest()[:16]}"


def run_scheduled_data_quality_snapshot(
    *,
    dry_run: bool = True,
    now: datetime | None = None,
    operator: str | None = None,
) -> dict[str, Any]:
    scanned_at = _utc(now)
    groups = _groups_with_counts()
    checks = list_data_quality_check_definitions()
    summary = _summary(groups=groups, checks=checks)
    return {
        "ok": True,
        "job": "data_quality_snapshot",
        "dry_run": bool(dry_run),
        "operator": _operator(operator),
        "scanned_at": scanned_at.isoformat(),
        "snapshot_id": _snapshot_id(scanned_at=scanned_at, checks=checks),
        "source_status": "registry_metadata_only",
        "snapshot_status": "generated",
        "persistence_status": "not_configured",
        "persisted": False,
        "database_probe_executed": False,
        "real_external_call_executed": False,
        "summary": summary,
        "groups": groups,
        "checks": checks,
        "errors": [],
    }


def _groups_with_counts() -> list[dict[str, Any]]:
    groups = list_data_quality_groups()
    grouped = data_quality_checks_by_group()
    return [
        {
            **group,
            "check_count": len(grouped[group["group"]]),
        }
        for group in groups
    ]


def _summary(*, groups: list[dict[str, Any]], checks: list[dict[str, Any]]) -> dict[str, Any]:
    group_counts = {group["group"]: int(group.get("check_count") or 0) for group in groups}
    severity_counts = {"red": 0, "yellow": 0}
    probe_status_counts = {"needs_probe": 0, "registered": 0}
    for check in checks:
        severity_counts[str(check.get("severity") or "")] += 1
        probe_status_counts[str(check.get("probe_status") or "")] += 1
    return {
        "ok": True,
        "group_counts": group_counts,
        "severity_counts": severity_counts,
        "probe_status_counts": probe_status_counts,
        "total_checks": len(checks),
        "groups": list_data_quality_groups(),
    }
