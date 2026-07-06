from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Callable

from sqlalchemy import text

from aicrm_next.shared.db_session import get_session_factory
from tools.check_data_table_lifecycle import check_data_table_lifecycle

from .dto import DataHealthCheckResult
from .schema_drift import (
    database_schema_available,
    evaluate_schema_drift,
    load_table_lifecycle_manifest,
    public_schema_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
PROJECTION_FRESHNESS_MAX_MINUTES = int(os.getenv("AICRM_DATA_HEALTH_PROJECTION_FRESHNESS_MAX_MINUTES", "60") or 60)
BROADCAST_BLOCKED_MAX_COUNT = int(os.getenv("AICRM_DATA_HEALTH_BROADCAST_BLOCKED_MAX_COUNT", "0") or 0)
BROADCAST_RETRYABLE_DUE_MAX_COUNT = int(os.getenv("AICRM_DATA_HEALTH_BROADCAST_RETRYABLE_DUE_MAX_COUNT", "100") or 100)
EXTERNAL_EFFECT_RETRYABLE_DUE_MAX_COUNT = int(os.getenv("AICRM_DATA_HEALTH_EXTERNAL_EFFECT_RETRYABLE_DUE_MAX_COUNT", "100") or 100)


def run_all_checks() -> list[DataHealthCheckResult]:
    return [check() for check in _CHECKS]


def run_check(check_id: str) -> DataHealthCheckResult | None:
    for check in _CHECKS:
        result = check()
        if result.check_id == check_id:
            return result
    return None


def _table_lifecycle_manifest_guard() -> DataHealthCheckResult:
    violations = list(_lifecycle_violations())
    return _static_guard_result(
        check_id="table_lifecycle_manifest_guard",
        title="Lifecycle manifest guard",
        violations=violations,
        ok_summary="Lifecycle manifest and table registrations are valid.",
        remediation="Run tools/check_data_table_lifecycle.py and register or fix the reported table entries.",
    )


def _retired_table_runtime_reference_guard() -> DataHealthCheckResult:
    violations = [
        violation
        for violation in _lifecycle_violations()
        if "references retired table" in violation
    ]
    return _static_guard_result(
        check_id="retired_table_runtime_reference_guard",
        title="Retired table runtime reference guard",
        violations=violations,
        ok_summary="No Next runtime SQL references retired lifecycle tables.",
        remediation="Remove the runtime SQL reference or move the table out of retired lifecycle with an approved owner.",
    )


def _schema_drift_guard() -> DataHealthCheckResult:
    if not database_schema_available():
        return DataHealthCheckResult(
            check_id="schema_drift_guard",
            title="Schema drift guard",
            status="not_applicable",
            severity="gray",
            summary="DATABASE_URL is not configured, so live information_schema drift cannot be checked.",
            evidence={"runtime_probe": "database_url_not_configured"},
            remediation="Run this check in an environment with a migrated read-only database connection.",
        )
    try:
        violations = evaluate_schema_drift(
            manifest=load_table_lifecycle_manifest(),
            actual_schema=public_schema_snapshot(),
        )
    except Exception as exc:  # pragma: no cover - defensive health endpoint guard
        return DataHealthCheckResult(
            check_id="schema_drift_guard",
            title="Schema drift guard",
            status="fail",
            severity="red",
            summary="Schema drift check could not read the live schema.",
            evidence={"error": type(exc).__name__, "message": str(exc)[:300]},
            remediation="Verify DATABASE_URL, migration state, and information_schema access.",
        )
    return _static_guard_result(
        check_id="schema_drift_guard",
        title="Schema drift guard",
        violations=violations,
        ok_summary="Live public schema is aligned with the lifecycle manifest.",
        remediation="Register missing tables, remove retired physical tables, or add required ownership/PII/queue metadata.",
    )


@lru_cache(maxsize=1)
def _lifecycle_violations() -> tuple[str, ...]:
    return tuple(check_data_table_lifecycle(root=ROOT))


def _identity_legacy_column_guard() -> DataHealthCheckResult:
    guard_path = ROOT / "tests" / "test_unionid_final_schema_guard.py"
    source = guard_path.read_text(encoding="utf-8") if guard_path.exists() else ""
    required_tokens = (
        "LEGACY_IDENTITY_COLUMN_NAMES",
        "ALLOWED_FINAL_LEGACY_IDENTITY_COLUMNS",
        "BOUNDARY_PREFIXES",
    )
    missing = [token for token in required_tokens if token not in source]
    return _static_guard_result(
        check_id="identity_legacy_column_guard",
        title="Legacy identity column guard",
        violations=[f"{guard_path.relative_to(ROOT)} missing {token}" for token in missing],
        ok_summary="Final schema guard restricts legacy identity columns to approved identity boundaries.",
        remediation="Restore tests/test_unionid_final_schema_guard.py allowed-boundary assertions.",
    )


def _static_guard_result(
    *,
    check_id: str,
    title: str,
    violations: list[str],
    ok_summary: str,
    remediation: str,
) -> DataHealthCheckResult:
    if violations:
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary=f"{len(violations)} violation(s) found.",
            evidence={"violations": violations[:50], "violation_count": len(violations)},
            remediation=remediation,
        )
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="ok",
        severity="green",
        summary=ok_summary,
        evidence={"violation_count": 0},
        remediation="",
    )


def _db_backed_placeholder(check_id: str, title: str, source_tables: list[str]) -> DataHealthCheckResult:
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="not_applicable",
        severity="gray",
        summary="Runtime data check is registered but no production database probe is attached in this PR.",
        evidence={"source_tables": source_tables, "runtime_probe": "not_configured"},
        remediation="Attach a production-safe read repository before turning this into a red/yellow operational check.",
    )


def _db_unavailable_placeholder(check_id: str, title: str, source_tables: list[str]) -> DataHealthCheckResult:
    return _db_backed_placeholder(check_id, title, source_tables)


def _unionid_orphan_fact_guard() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "unionid_orphan_fact_guard",
        "Unionid orphan fact guard",
        ["questionnaire_submissions", "wechat_pay_orders", "broadcast_jobs"],
    )


def _identity_resolution_queue_backlog() -> DataHealthCheckResult:
    if not database_schema_available():
        return _db_backed_placeholder(
            "identity_resolution_queue_backlog",
            "Identity resolution queue backlog",
            ["crm_user_identity_resolution_queue"],
        )
    try:
        with get_session_factory()() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
                            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(first_seen_at) FILTER (WHERE status = 'pending'))) / 3600
                                AS oldest_pending_hours
                        FROM crm_user_identity_resolution_queue
                        """
                    )
                )
                .mappings()
                .first()
                or {}
            )
    except Exception as exc:  # pragma: no cover - defensive health endpoint guard
        return DataHealthCheckResult(
            check_id="identity_resolution_queue_backlog",
            title="Identity resolution queue backlog",
            status="fail",
            severity="red",
            summary="Identity resolution queue backlog check could not read the live queue.",
            evidence={"error": type(exc).__name__, "message": str(exc)[:300]},
            remediation="Verify crm_user_identity_resolution_queue exists and DATABASE_URL has read access.",
        )
    pending_count = int(row.get("pending_count") or 0)
    oldest_pending_hours = float(row.get("oldest_pending_hours") or 0)
    violations = []
    if pending_count > 100:
        violations.append(f"pending_count={pending_count} exceeds 100")
    if oldest_pending_hours > 24:
        violations.append(f"oldest_pending_hours={oldest_pending_hours:.1f} exceeds 24")
    if violations:
        return DataHealthCheckResult(
            check_id="identity_resolution_queue_backlog",
            title="Identity resolution queue backlog",
            status="fail",
            severity="red",
            summary="Identity resolution queue backlog exceeded the production threshold.",
            evidence={"pending_count": pending_count, "oldest_pending_hours": oldest_pending_hours, "violations": violations},
            remediation="Run the identity resolution backfill worker and inspect terminal failures.",
        )
    return DataHealthCheckResult(
        check_id="identity_resolution_queue_backlog",
        title="Identity resolution queue backlog",
        status="ok",
        severity="green",
        summary="Identity resolution queue backlog is within threshold.",
        evidence={"pending_count": pending_count, "oldest_pending_hours": oldest_pending_hours},
        remediation="",
    )


def _projection_freshness_customer_read_model() -> DataHealthCheckResult:
    check_id = "projection_freshness_customer_read_model"
    title = "Customer read model projection freshness"
    source_tables = ["customer_list_index_next", "customer_detail_snapshot_next"]
    if not database_schema_available():
        return _db_unavailable_placeholder(check_id, title, source_tables)
    try:
        with get_session_factory()() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT
                            (SELECT COUNT(*) FROM customer_list_index_next) AS list_count,
                            (SELECT COUNT(*) FROM customer_detail_snapshot_next) AS detail_count,
                            EXTRACT(EPOCH FROM (
                                CURRENT_TIMESTAMP - (SELECT MAX(updated_at) FROM customer_list_index_next)
                            )) / 60 AS list_stale_minutes,
                            EXTRACT(EPOCH FROM (
                                CURRENT_TIMESTAMP - (SELECT MAX(updated_at) FROM customer_detail_snapshot_next)
                            )) / 60 AS detail_stale_minutes
                        """
                    )
                )
                .mappings()
                .first()
                or {}
            )
    except Exception as exc:  # pragma: no cover - defensive health endpoint guard
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary="Customer read model freshness check could not read the live projection tables.",
            evidence={"error": type(exc).__name__, "message": str(exc)[:300]},
            remediation="Verify customer read model migrations and DATABASE_URL read access.",
        )

    list_count = int(row.get("list_count") or 0)
    detail_count = int(row.get("detail_count") or 0)
    list_stale_minutes = float(row.get("list_stale_minutes") or 0)
    detail_stale_minutes = float(row.get("detail_stale_minutes") or 0)
    violations = []
    if list_count <= 0:
        violations.append("customer_list_index_next is empty")
    if detail_count <= 0:
        violations.append("customer_detail_snapshot_next is empty")
    if list_stale_minutes > PROJECTION_FRESHNESS_MAX_MINUTES:
        violations.append(f"list_stale_minutes={list_stale_minutes:.1f} exceeds {PROJECTION_FRESHNESS_MAX_MINUTES}")
    if detail_stale_minutes > PROJECTION_FRESHNESS_MAX_MINUTES:
        violations.append(f"detail_stale_minutes={detail_stale_minutes:.1f} exceeds {PROJECTION_FRESHNESS_MAX_MINUTES}")
    evidence = {
        "list_count": list_count,
        "detail_count": detail_count,
        "list_stale_minutes": list_stale_minutes,
        "detail_stale_minutes": detail_stale_minutes,
        "max_stale_minutes": PROJECTION_FRESHNESS_MAX_MINUTES,
    }
    if violations:
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary="Customer read model projections are empty or stale.",
            evidence={**evidence, "violations": violations},
            remediation="Run the customer read model projection refresh and inspect failed projection jobs.",
        )
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="ok",
        severity="green",
        summary="Customer read model projections are populated and fresh.",
        evidence=evidence,
        remediation="",
    )


def _broadcast_job_blocked_backlog() -> DataHealthCheckResult:
    check_id = "broadcast_job_blocked_backlog"
    title = "Broadcast job blocked backlog"
    source_tables = ["broadcast_jobs", "broadcast_job_events"]
    if not database_schema_available():
        return _db_unavailable_placeholder(check_id, title, source_tables)
    try:
        with get_session_factory()() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) FILTER (WHERE status = 'blocked') AS blocked_count,
                            COUNT(*) FILTER (WHERE status = 'failed_terminal') AS failed_terminal_count,
                            COUNT(*) FILTER (
                                WHERE status = 'failed_retryable'
                                  AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                            ) AS due_retryable_count,
                            EXTRACT(EPOCH FROM (
                                CURRENT_TIMESTAMP - MIN(updated_at) FILTER (
                                    WHERE status IN ('blocked', 'failed_terminal')
                                )
                            )) / 3600 AS oldest_terminal_hours
                        FROM broadcast_jobs
                        """
                    )
                )
                .mappings()
                .first()
                or {}
            )
    except Exception as exc:  # pragma: no cover - defensive health endpoint guard
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary="Broadcast backlog check could not read the live queue.",
            evidence={"error": type(exc).__name__, "message": str(exc)[:300]},
            remediation="Verify broadcast_jobs migrations and DATABASE_URL read access.",
        )

    blocked_count = int(row.get("blocked_count") or 0)
    failed_terminal_count = int(row.get("failed_terminal_count") or 0)
    due_retryable_count = int(row.get("due_retryable_count") or 0)
    oldest_terminal_hours = float(row.get("oldest_terminal_hours") or 0)
    violations = []
    if blocked_count > BROADCAST_BLOCKED_MAX_COUNT:
        violations.append(f"blocked_count={blocked_count} exceeds {BROADCAST_BLOCKED_MAX_COUNT}")
    if failed_terminal_count > 0:
        violations.append(f"failed_terminal_count={failed_terminal_count} exceeds 0")
    if due_retryable_count > BROADCAST_RETRYABLE_DUE_MAX_COUNT:
        violations.append(f"due_retryable_count={due_retryable_count} exceeds {BROADCAST_RETRYABLE_DUE_MAX_COUNT}")
    evidence = {
        "blocked_count": blocked_count,
        "failed_terminal_count": failed_terminal_count,
        "due_retryable_count": due_retryable_count,
        "oldest_terminal_hours": oldest_terminal_hours,
        "due_retryable_threshold": BROADCAST_RETRYABLE_DUE_MAX_COUNT,
    }
    if violations:
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary="Broadcast queue has blocked, terminal, or excessive due retryable jobs.",
            evidence={**evidence, "violations": violations},
            remediation="Inspect broadcast_job_events, fix terminal causes, and requeue only after operator approval.",
        )
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="ok",
        severity="green",
        summary="Broadcast blocked backlog is within threshold.",
        evidence=evidence,
        remediation="",
    )


def _external_effect_failed_retryable_backlog() -> DataHealthCheckResult:
    check_id = "external_effect_failed_retryable_backlog"
    title = "External effect failed retryable backlog"
    source_tables = ["external_effect_job", "external_effect_attempt"]
    if not database_schema_available():
        return _db_unavailable_placeholder(check_id, title, source_tables)
    try:
        with get_session_factory()() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) FILTER (WHERE status = 'failed_retryable') AS failed_retryable_count,
                            COUNT(*) FILTER (WHERE status = 'failed_terminal') AS failed_terminal_count,
                            COUNT(*) FILTER (WHERE status = 'blocked') AS blocked_count,
                            COUNT(*) FILTER (
                                WHERE status = 'failed_retryable'
                                  AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                            ) AS due_retryable_count,
                            EXTRACT(EPOCH FROM (
                                CURRENT_TIMESTAMP - MIN(COALESCE(next_retry_at, updated_at)) FILTER (
                                    WHERE status = 'failed_retryable'
                                )
                            )) AS oldest_failed_retryable_age_seconds
                        FROM external_effect_job
                        """
                    )
                )
                .mappings()
                .first()
                or {}
            )
    except Exception as exc:  # pragma: no cover - defensive health endpoint guard
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary="External effect backlog check could not read the live queue.",
            evidence={"error": type(exc).__name__, "message": str(exc)[:300]},
            remediation="Verify external_effect_job migrations and DATABASE_URL read access.",
        )

    failed_retryable_count = int(row.get("failed_retryable_count") or 0)
    failed_terminal_count = int(row.get("failed_terminal_count") or 0)
    blocked_count = int(row.get("blocked_count") or 0)
    due_retryable_count = int(row.get("due_retryable_count") or 0)
    oldest_failed_retryable_age_seconds = int(float(row.get("oldest_failed_retryable_age_seconds") or 0))
    violations = []
    if failed_terminal_count > 0:
        violations.append(f"failed_terminal_count={failed_terminal_count} exceeds 0")
    if blocked_count > 0:
        violations.append(f"blocked_count={blocked_count} exceeds 0")
    if due_retryable_count > EXTERNAL_EFFECT_RETRYABLE_DUE_MAX_COUNT:
        violations.append(f"due_retryable_count={due_retryable_count} exceeds {EXTERNAL_EFFECT_RETRYABLE_DUE_MAX_COUNT}")
    evidence = {
        "failed_retryable_count": failed_retryable_count,
        "failed_terminal_count": failed_terminal_count,
        "blocked_count": blocked_count,
        "due_retryable_count": due_retryable_count,
        "oldest_failed_retryable_age_seconds": oldest_failed_retryable_age_seconds,
        "due_retryable_threshold": EXTERNAL_EFFECT_RETRYABLE_DUE_MAX_COUNT,
    }
    if violations:
        return DataHealthCheckResult(
            check_id=check_id,
            title=title,
            status="fail",
            severity="red",
            summary="External effect queue has blocked, terminal, or excessive due retryable jobs.",
            evidence={**evidence, "violations": violations},
            remediation="Inspect external_effect_attempt, repair adapter/runtime failures, and requeue explicitly.",
        )
    return DataHealthCheckResult(
        check_id=check_id,
        title=title,
        status="ok",
        severity="green",
        summary="External effect retryable backlog is within threshold.",
        evidence=evidence,
        remediation="",
    )


def _deprecated_execution_settings_present() -> DataHealthCheckResult:
    deprecated = [
        key
        for key in (
            "AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE",
            "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
            "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
            "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS",
        )
        if str(os.getenv(key) or "").strip()
    ]
    if deprecated:
        return DataHealthCheckResult(
            check_id="deprecated_execution_settings_present",
            title="Deprecated execution settings present",
            status="warn",
            severity="yellow",
            summary="Deprecated execution config is still present in the runtime environment.",
            evidence={"deprecated_settings_present": deprecated},
            remediation="Move WeCom execution to AICRM_WECOM_EXECUTION_MODE and AICRM_WECOM_ENABLED_EFFECT_TYPES; keep questionnaire external push fixed to queue.",
        )
    return DataHealthCheckResult(
        check_id="deprecated_execution_settings_present",
        title="Deprecated execution settings present",
        status="ok",
        severity="green",
        summary="No deprecated execution env settings are present in this process.",
        evidence={"deprecated_settings_present": []},
        remediation="",
    )


def _fake_stub_route_exposed() -> DataHealthCheckResult:
    api_path = ROOT / "aicrm_next" / "customer_tags" / "api.py"
    source = api_path.read_text(encoding="utf-8") if api_path.exists() else ""
    fake_stub_routes = source.count("/api/admin/wecom/tags/fake-stub")
    violations = []
    if fake_stub_routes:
        violations.append("fake-stub routes must not be registered in runtime routers")
    return _static_guard_result(
        check_id="fake_stub_route_exposed",
        title="Fake-stub route exposure guard",
        violations=violations,
        ok_summary="WeCom tag fake-stub runtime routes are not registered.",
        remediation="Keep fake-stub fixtures under tests; runtime routers must use the real read/write models.",
    )


def _external_effect_approved_not_queued() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "external_effect_approved_not_queued",
        "External effect approved-not-queued guard",
        ["external_effect_job"],
    )


def _questionnaire_submission_without_user_guard() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "questionnaire_submission_without_user_guard",
        "Questionnaire submissions without identity",
        ["questionnaire_submissions", "crm_user_identity"],
    )


def _payment_order_without_user_guard() -> DataHealthCheckResult:
    return _db_backed_placeholder(
        "payment_order_without_user_guard",
        "Payment orders without identity",
        ["wechat_pay_orders", "alipay_pay_orders", "crm_user_identity"],
    )


def _customer_360_freshness_guard() -> DataHealthCheckResult:
    return DataHealthCheckResult(
        check_id="customer_360_freshness_guard",
        title="Customer 360 freshness guard",
        status="not_applicable",
        severity="gray",
        summary="Customer 360 freshness probes are registered but no production-safe database reader is attached in this PR.",
        evidence={
            "freshness_probes": [
                "latest_identity_update",
                "latest_order",
                "latest_questionnaire",
                "latest_message",
                "latest_projection_refresh",
            ],
            "source_tables": [
                "crm_user_identity",
                "wechat_pay_orders",
                "alipay_pay_orders",
                "wechat_shop_orders",
                "questionnaire_submissions",
                "archived_messages",
                "customer_list_index_next",
                "customer_detail_snapshot_next",
            ],
            "runtime_probe": "not_configured",
        },
        remediation="Attach a production-safe read repository that computes max freshness timestamps by unionid before turning this into a red/yellow operational check.",
    )


_CHECKS: tuple[Callable[[], DataHealthCheckResult], ...] = (
    _identity_legacy_column_guard,
    _table_lifecycle_manifest_guard,
    _retired_table_runtime_reference_guard,
    _schema_drift_guard,
    _unionid_orphan_fact_guard,
    _identity_resolution_queue_backlog,
    _projection_freshness_customer_read_model,
    _broadcast_job_blocked_backlog,
    _external_effect_failed_retryable_backlog,
    _deprecated_execution_settings_present,
    _fake_stub_route_exposed,
    _external_effect_approved_not_queued,
    _questionnaire_submission_without_user_guard,
    _payment_order_without_user_guard,
    _customer_360_freshness_guard,
)
