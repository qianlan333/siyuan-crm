from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.external_calls import scrub_summary
from aicrm_next.platform_foundation.external_effects.models import public_datetime, utcnow

from .models import LegacyDeprecationEntry
from .repo import LegacyCleanupRepository, build_legacy_cleanup_repository

DEFAULT_DEPRECATED_BY = "p0_1_external_effect_queue_migration"
DEFAULT_DEPRECATION_REASON = "All outbound effects now use External Effect Queue"
DEFAULT_REPLACEMENT_ROUTE = "/admin/push-center"

DEFAULT_LEGACY_DEPRECATIONS: tuple[dict[str, Any], ...] = (
    {
        "legacy_key": "old_payment_direct_automation_bridge",
        "legacy_type": "direct_automation",
        "legacy_route": "public_product.h5_wechat_pay.process_payment_succeeded_event",
        "legacy_module": "payment",
    },
    {
        "legacy_key": "old_ai_assist_direct_send",
        "legacy_type": "direct_send",
        "legacy_route": "/api/ai-assist/legacy/direct-send",
        "legacy_module": "ai_assist",
    },
    {
        "legacy_key": "old_ai_assist_webhook_outbound",
        "legacy_type": "webhook_outbound",
        "legacy_route": "/api/ai-assist/legacy/webhook-outbound",
        "legacy_module": "ai_assist",
    },
    {
        "legacy_key": "old_ai_assist_campaign_run_due_direct",
        "legacy_type": "campaign_run_due_direct",
        "legacy_route": "/api/cloud-orchestrator/campaigns/run-due",
        "legacy_module": "cloud_orchestrator",
    },
    {
        "legacy_key": "old_group_ops_queue_gateway_send",
        "legacy_type": "queue_gateway",
        "legacy_route": "integration_gateway.wecom_group_adapter.queue_gateway",
        "legacy_module": "group_ops",
    },
    {
        "legacy_key": "old_group_ops_broadcast_job_send",
        "legacy_type": "broadcast_job",
        "legacy_route": "/api/admin/broadcast-jobs/*/send",
        "legacy_module": "group_ops",
    },
    {
        "legacy_key": "old_broadcast_jobs_direct_approve_cancel",
        "legacy_type": "broadcast_job_control_plane",
        "legacy_route": "/api/admin/broadcast-jobs/{job_id}/approve|cancel",
        "legacy_module": "admin_jobs",
    },
    {
        "legacy_key": "old_group_ops_webhook_outbound",
        "legacy_type": "webhook_outbound",
        "legacy_route": "/api/automation/group-ops/webhooks/{webhook_key}",
        "legacy_module": "group_ops",
    },
    {
        "legacy_key": "old_questionnaire_sync_external_push",
        "legacy_type": "sync_webhook",
        "legacy_route": "questionnaire.external_push_logs.retry_one",
        "legacy_module": "questionnaire",
    },
    {
        "legacy_key": "old_order_webhook_push",
        "legacy_type": "webhook_outbound",
        "legacy_route": "commerce.domain_event_outbox_legacy_delivery",
        "legacy_module": "commerce",
    },
    {
        "legacy_key": "old_external_push_outbox_worker",
        "legacy_type": "webhook_outbox_worker",
        "legacy_route": "external_push.service.run_due_external_push_events",
        "legacy_module": "external_push",
    },
    {
        "legacy_key": "old_external_push_delivery_retry",
        "legacy_type": "webhook_retry",
        "legacy_route": "external_push.service.retry_order_delivery",
        "legacy_module": "external_push",
    },
    {
        "legacy_key": "old_payment_refund_direct_request",
        "legacy_type": "payment_refund_request",
        "legacy_route": "/api/admin/refunds|/api/admin/wechat-pay/orders/{order_id}/refunds",
        "legacy_module": "commerce",
    },
    {
        "legacy_key": "old_admin_jobs_deferred_run",
        "legacy_type": "deferred_job_runner",
        "legacy_route": "/api/admin/jobs/deferred-jobs/run",
        "legacy_module": "admin_jobs",
    },
    {
        "legacy_key": "old_customer_webhook_delivery_retry",
        "legacy_type": "webhook_retry",
        "legacy_route": "/api/admin/jobs/webhook-deliveries/*/retry",
        "legacy_module": "admin_jobs",
    },
    {
        "legacy_key": "old_broadcast_jobs_feishu_hourly_report",
        "legacy_type": "feishu_notification",
        "legacy_route": "/api/admin/broadcast-jobs/feishu-hourly-report/run",
        "legacy_module": "admin_jobs",
    },
    {
        "legacy_key": "old_owner_migration_legacy_execute_path",
        "legacy_type": "legacy_application_path",
        "legacy_route": "owner_migration.OwnerMigrationService._run_legacy",
        "legacy_module": "owner_migration",
    },
    {
        "legacy_key": "old_external_direct_wecom_webhook_payment_feishu_openclaw",
        "legacy_type": "direct_external_call",
        "legacy_route": "legacy_external_adapters/*",
        "legacy_module": "platform_foundation",
    },
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now(value: datetime | None = None) -> datetime:
    now = value or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _counts(items: list[LegacyDeprecationEntry]) -> dict[str, int]:
    status: dict[str, int] = {}
    delete_status: dict[str, int] = {}
    for item in items:
        status[item.status] = status.get(item.status, 0) + 1
        delete_status[item.delete_status] = delete_status.get(item.delete_status, 0) + 1
    return {
        "total": len(items),
        "deprecated": status.get("deprecated", 0),
        "scheduled": delete_status.get("scheduled", 0),
        "deleted": delete_status.get("deleted", 0),
        "failed": delete_status.get("failed", 0),
    }


def _next_delete_time(items: list[LegacyDeprecationEntry]) -> str:
    scheduled = [item.delete_scheduled_at for item in items if item.delete_status == "scheduled" and item.delete_scheduled_at]
    return sorted(scheduled)[0] if scheduled else ""


def _with_observation_metrics(
    items: list[LegacyDeprecationEntry],
    *,
    counts_by_key: dict[str, dict[str, int]],
    window_days: int,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        payload = item.to_dict()
        counters = counts_by_key.get(item.legacy_key, {})
        invoked = int(counters.get("legacy_path_invoked") or 0)
        real_execution = int(counters.get("legacy_real_execution") or 0)
        payload["runtime_observation"] = {
            "window_days": int(window_days),
            "legacy_path_invoked_count": invoked,
            "legacy_real_execution_count": real_execution,
            "no_recent_real_execution": real_execution == 0,
        }
        enriched.append(payload)
    return enriched


class LegacyWebhookCleanupService:
    def __init__(self, repository: LegacyCleanupRepository | None = None) -> None:
        self._repo = repository or build_legacy_cleanup_repository()

    def ensure_default_deprecations(self, *, now: datetime | None = None) -> list[LegacyDeprecationEntry]:
        timestamp = _now(now)
        delete_at = timestamp + timedelta(days=7)
        entries: list[LegacyDeprecationEntry] = []
        for item in DEFAULT_LEGACY_DEPRECATIONS:
            payload = {
                **item,
                "status": "deprecated",
                "deprecated_by": DEFAULT_DEPRECATED_BY,
                "deprecation_reason": DEFAULT_DEPRECATION_REASON,
                "replacement_route": DEFAULT_REPLACEMENT_ROUTE,
                "delete_status": "scheduled",
                "notes_json": {
                    "replacement_capability": "external_effect_queue",
                    "real_external_call_executed": False,
                    "physical_delete": False,
                },
            }
            entries.append(self._repo.upsert_deprecation(payload, deprecated_at=timestamp, delete_scheduled_at=delete_at))
        return entries

    def mark_default_deprecations(self, *, now: datetime | None = None, operator: str = DEFAULT_DEPRECATED_BY) -> dict[str, Any]:
        timestamp = _now(now)
        entries = self.ensure_default_deprecations(now=timestamp)
        for item in entries:
            self._repo.record_audit(
                legacy_key=item.legacy_key,
                action="mark_legacy_deprecated",
                operator=_text(operator) or DEFAULT_DEPRECATED_BY,
                before={},
                after=item.to_dict(),
            )
        counts = _counts(entries)
        return {
            "ok": True,
            "items": [item.to_dict() for item in entries],
            "total": len(entries),
            "counts": counts,
            "next_delete_scheduled_at": _next_delete_time(entries),
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        }

    def status(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        items, total = self._repo.list_deprecations(filters or {}, limit=500, offset=0)
        counts = _counts(items)
        window_days = 7
        since = _now() - timedelta(days=window_days)
        observation_counts = self._repo.legacy_action_counts(since=since)
        enriched_items = _with_observation_metrics(items, counts_by_key=observation_counts, window_days=window_days)
        recent_invoked = sum(item["runtime_observation"]["legacy_path_invoked_count"] for item in enriched_items)
        recent_real_execution = sum(item["runtime_observation"]["legacy_real_execution_count"] for item in enriched_items)
        return {
            "ok": True,
            "items": enriched_items,
            "total": total,
            "counts": counts,
            "runtime_observation": {
                "window_days": window_days,
                "legacy_path_invoked_count": recent_invoked,
                "legacy_real_execution_count": recent_real_execution,
                "no_recent_real_execution": recent_real_execution == 0,
            },
            "next_delete_scheduled_at": _next_delete_time(items),
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        }

    def preview_due(self, *, now: datetime | None = None, limit: int = 50) -> dict[str, Any]:
        timestamp = _now(now)
        due = self._repo.due_deprecations(now=timestamp, limit=limit)
        return {
            "ok": True,
            "dry_run": True,
            "items": [item.to_dict() for item in due],
            "counts": {"candidate_count": len(due), "deleted": 0, "failed": 0},
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        }

    def run_due(self, *, dry_run: bool = True, now: datetime | None = None, limit: int = 50, operator: str = "system") -> dict[str, Any]:
        timestamp = _now(now)
        due = self._repo.due_deprecations(now=timestamp, limit=limit)
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "items": [item.to_dict() for item in due],
                "counts": {"candidate_count": len(due), "deleted": 0, "failed": 0},
                "route_owner": "ai_crm_next",
                "real_external_call_executed": False,
            }
        delete_job_id = "legacy_cleanup_" + uuid4().hex
        results: list[dict[str, Any]] = []
        deleted = 0
        failed = 0
        for item in due:
            before = item.to_dict()
            try:
                self._validate_delete_candidate(item, now=timestamp)
                after_item = self._repo.mark_deleted(
                    item.legacy_key,
                    delete_job_id=delete_job_id,
                    notes={
                        "cleanup_deleted_at": public_datetime(timestamp),
                        "cleanup_strategy": "disable_legacy_entry_only",
                        "history_data_deleted": False,
                    },
                )
                after = after_item.to_dict() if after_item else {}
                self._repo.record_audit(legacy_key=item.legacy_key, action="delete_legacy_entry", operator=operator, before=before, after=after)
                deleted += 1
                results.append({"legacy_key": item.legacy_key, "delete_status": "deleted", "item": after})
            except Exception as exc:  # defensive: one bad entry must not hide others
                failed_item = self._repo.mark_failed(
                    item.legacy_key,
                    error=str(exc),
                    notes={"cleanup_failed_at": public_datetime(timestamp), "cleanup_strategy": "disable_legacy_entry_only"},
                )
                after = failed_item.to_dict() if failed_item else {"error": str(exc)}
                self._repo.record_audit(legacy_key=item.legacy_key, action="delete_legacy_entry_failed", operator=operator, before=before, after=after)
                failed += 1
                results.append({"legacy_key": item.legacy_key, "delete_status": "failed", "error": str(exc), "item": after})
        return {
            "ok": True,
            "dry_run": False,
            "delete_job_id": delete_job_id,
            "items": results,
            "counts": {"candidate_count": len(due), "deleted": deleted, "failed": failed},
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        }

    def retire_now(self, *, dry_run: bool = True, now: datetime | None = None, limit: int = 50, operator: str = "system") -> dict[str, Any]:
        timestamp = _now(now)
        candidates, _total = self._repo.list_deprecations(
            {"status": "deprecated", "delete_status": "scheduled"},
            limit=limit,
            offset=0,
        )
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "items": [item.to_dict() for item in candidates],
                "counts": {"candidate_count": len(candidates), "deleted": 0, "failed": 0},
                "route_owner": "ai_crm_next",
                "real_external_call_executed": False,
            }
        delete_job_id = "legacy_retire_now_" + uuid4().hex
        results: list[dict[str, Any]] = []
        deleted = 0
        failed = 0
        for item in candidates:
            before = item.to_dict()
            try:
                self._validate_retire_now_candidate(item, now=timestamp)
                after_item = self._repo.mark_deleted(
                    item.legacy_key,
                    delete_job_id=delete_job_id,
                    notes={
                        "cleanup_deleted_at": public_datetime(timestamp),
                        "cleanup_strategy": "operator_authorized_immediate_retire",
                        "delete_scheduled_at_bypassed": True,
                        "history_data_deleted": False,
                    },
                )
                after = after_item.to_dict() if after_item else {}
                self._repo.record_audit(legacy_key=item.legacy_key, action="retire_legacy_entry_now", operator=operator, before=before, after=after)
                deleted += 1
                results.append({"legacy_key": item.legacy_key, "delete_status": "deleted", "item": after})
            except Exception as exc:  # defensive: one bad entry must not hide others
                failed_item = self._repo.mark_failed(
                    item.legacy_key,
                    error=str(exc),
                    notes={"cleanup_failed_at": public_datetime(timestamp), "cleanup_strategy": "operator_authorized_immediate_retire"},
                )
                after = failed_item.to_dict() if failed_item else {"error": str(exc)}
                self._repo.record_audit(legacy_key=item.legacy_key, action="retire_legacy_entry_now_failed", operator=operator, before=before, after=after)
                failed += 1
                results.append({"legacy_key": item.legacy_key, "delete_status": "failed", "error": str(exc), "item": after})
        return {
            "ok": True,
            "dry_run": False,
            "delete_job_id": delete_job_id,
            "items": results,
            "counts": {"candidate_count": len(candidates), "deleted": deleted, "failed": failed},
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        }

    def disabled_payload(self, legacy_key: str, *, error: str = "legacy_webhook_deprecated") -> dict[str, Any]:
        self.record_runtime_marker(
            legacy_key,
            marker="legacy_path_invoked",
            operator="legacy_cleanup.disabled_payload",
            metadata={"disabled": True, "error": error},
            real_external_call_executed=False,
        )
        item = self._repo.get_deprecation(legacy_key)
        delete_scheduled_at = item.delete_scheduled_at if item else public_datetime(utcnow() + timedelta(days=7))
        return legacy_disabled_payload(legacy_key, delete_scheduled_at=delete_scheduled_at, error=error)

    def record_runtime_marker(
        self,
        legacy_key: str,
        *,
        marker: str = "legacy_path_invoked",
        operator: str = "system",
        metadata: dict[str, Any] | None = None,
        real_external_call_executed: bool = False,
    ) -> dict[str, Any]:
        key = _text(legacy_key)
        if not key:
            return {"ok": False, "error": "legacy_key_required", "real_external_call_executed": False}
        action = "legacy_real_execution" if real_external_call_executed or marker == "legacy_real_execution" else "legacy_path_invoked"
        after = scrub_summary(
            {
                "legacy_key": key,
                "legacy_runtime_marker": True,
                "marker": action,
                "metadata": dict(metadata or {}),
                "observation_window_days": 7,
                "real_external_call_executed": bool(real_external_call_executed),
            }
        )
        try:
            audit = self._repo.record_audit(
                legacy_key=key,
                action=action,
                operator=_text(operator) or "system",
                before={},
                after=after,
            )
        except Exception:
            return {"ok": False, "error": "legacy_runtime_marker_failed", "real_external_call_executed": False}
        return {
            "ok": True,
            "audit_id": audit.audit_id,
            "legacy_key": key,
            "marker": action,
            "real_external_call_executed": bool(real_external_call_executed),
        }

    def _validate_delete_candidate(self, item: LegacyDeprecationEntry, *, now: datetime) -> None:
        scheduled = _text(item.delete_scheduled_at)
        if not scheduled:
            raise ValueError("delete_scheduled_at_missing")
        scheduled_at = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        if scheduled_at.astimezone(timezone.utc) > now:
            raise ValueError("delete_not_due")
        if item.delete_status != "scheduled":
            raise ValueError("delete_status_not_scheduled")
        if item.replacement_route != DEFAULT_REPLACEMENT_ROUTE:
            raise ValueError("replacement_route_unavailable")
        recent_count = self._repo.recent_legacy_execution_count(legacy_key=item.legacy_key, since=now - timedelta(days=7))
        if recent_count:
            raise ValueError("recent_legacy_execution_detected")

    def _validate_retire_now_candidate(self, item: LegacyDeprecationEntry, *, now: datetime) -> None:
        if item.status != "deprecated":
            raise ValueError("legacy_status_not_deprecated")
        if item.delete_status != "scheduled":
            raise ValueError("delete_status_not_scheduled")
        if item.replacement_route != DEFAULT_REPLACEMENT_ROUTE:
            raise ValueError("replacement_route_unavailable")
        recent_count = self._repo.recent_legacy_execution_count(legacy_key=item.legacy_key, since=now - timedelta(days=7))
        if recent_count:
            raise ValueError("recent_legacy_execution_detected")


def legacy_disabled_payload(legacy_key: str = "", *, delete_scheduled_at: str = "", error: str = "legacy_webhook_deprecated") -> dict[str, Any]:
    return scrub_summary(
        {
            "ok": False,
            "error": error,
            "legacy_key": _text(legacy_key),
            "legacy_outbound_disabled": True,
            "external_effect_required": True,
            "migration_target": "external_effect_queue",
            "push_center_url": DEFAULT_REPLACEMENT_ROUTE,
            "delete_scheduled_at": _text(delete_scheduled_at),
            "real_external_call_executed": False,
        }
    )
