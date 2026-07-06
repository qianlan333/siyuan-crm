from __future__ import annotations

from .checks import run_all_checks, run_check
from .dto import DataHealthCheckResult, DataHealthSummary
from .quality_registry import (
    data_quality_checks_by_group,
    get_data_quality_check_definition,
    list_data_quality_check_definitions,
    list_data_quality_groups,
)


def data_health_summary() -> dict:
    checks = run_all_checks()
    counts = {"ok": 0, "warn": 0, "fail": 0, "not_applicable": 0}
    for check in checks:
        counts[check.status] += 1
    overall_status = "fail" if counts["fail"] else "warn" if counts["warn"] else "ok"
    return DataHealthSummary(
        ok=counts["fail"] == 0,
        overall_status=overall_status,
        counts=counts,
        checks=checks,
    ).model_dump()


def data_health_checks() -> dict:
    checks = run_all_checks()
    return {
        "ok": all(check.status != "fail" for check in checks),
        "checks": [check.model_dump() for check in checks],
    }


def data_health_check_detail(check_id: str) -> dict:
    result: DataHealthCheckResult | None = run_check(check_id)
    if result is None:
        return {
            "ok": False,
            "status_code": 404,
            "error_code": "data_health_check_not_found",
            "check_id": check_id,
        }
    return {"ok": result.status != "fail", "check": result.model_dump()}


def data_quality_summary() -> dict:
    groups = list_data_quality_groups()
    checks = list_data_quality_check_definitions()
    grouped = data_quality_checks_by_group()
    group_counts = {group["group"]: len(grouped[group["group"]]) for group in groups}
    severity_counts = {"red": 0, "yellow": 0}
    probe_status_counts = {"needs_probe": 0, "registered": 0}
    for check in checks:
        severity_counts[check["severity"]] += 1
        probe_status_counts[check["probe_status"]] += 1
    return {
        "ok": True,
        "group_counts": group_counts,
        "severity_counts": severity_counts,
        "probe_status_counts": probe_status_counts,
        "total_checks": len(checks),
        "groups": groups,
    }


def data_quality_groups() -> dict:
    groups = list_data_quality_groups()
    grouped = data_quality_checks_by_group()
    return {
        "ok": True,
        "groups": [
            {
                **group,
                "check_count": len(grouped[group["group"]]),
            }
            for group in groups
        ],
    }


def data_quality_checks() -> dict:
    return {
        "ok": True,
        "checks": list_data_quality_check_definitions(),
    }


def data_quality_check_detail(check_id: str) -> dict:
    definition = get_data_quality_check_definition(check_id)
    if definition is None:
        return {
            "ok": False,
            "status_code": 404,
            "error_code": "data_quality_check_not_found",
            "check_id": check_id,
        }
    return {"ok": True, "check": definition}
