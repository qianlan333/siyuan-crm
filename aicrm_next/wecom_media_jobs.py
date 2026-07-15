from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aicrm_next.media_library.wecom_lease import build_wecom_media_lease_manager
from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    WECOM_MEDIA_UPLOAD,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from aicrm_next.platform_foundation.external_effects.repo import build_external_effect_repository
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.shared.runtime import production_data_ready, production_environment


ADAPTER_NAME = "wecom_media_upload"


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


class WeComMediaUploadAdapter:
    def __init__(self, manager_factory=None) -> None:
        self._manager_factory = manager_factory

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        request_summary = {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "material_kind": str(payload.get("material_kind") or ""),
            "material_id": int(payload.get("material_id") or 0),
            "upload_kind": str(payload.get("upload_kind") or ""),
            "force_refresh": bool(payload.get("force_refresh", True)),
        }
        if job.effect_type != WECOM_MEDIA_UPLOAD:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": False, "wecom_media_upload_executed": False},
                error_code="unsupported_effect_type",
                error_message="WeCom media upload adapter received an unsupported effect type.",
                real_external_call_executed=False,
            )
        try:
            lease = self._build_manager().ensure_ready(
                request_summary["material_kind"],
                request_summary["material_id"],
                upload_kind=request_summary["upload_kind"],
                force_refresh=request_summary["force_refresh"],
            )
        except Exception as exc:
            retryable = bool(getattr(exc, "retryable", False))
            error_code = str(getattr(exc, "code", "wecom_media_upload_failed") or "wecom_media_upload_failed")
            external_call_executed = error_code in {"wecom_media_upload_failed", "empty_media_id"}
            return ExternalEffectDispatchResult(
                status="failed_retryable" if retryable else "failed_terminal",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={
                    "real_external_call_executed": external_call_executed,
                    "wecom_media_upload_executed": external_call_executed,
                    "provider_result_received": False,
                },
                error_code=error_code,
                error_message=str(exc)[:500],
                real_external_call_executed=external_call_executed,
                provider_result_received=False,
            )
        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={
                "provider_status": "ready",
                "media_id_present": bool(str(lease.get("media_id") or "").strip()),
                "provider_expires_at": str(lease.get("provider_expires_at") or ""),
                "lease_version": int(lease.get("lease_version") or 0),
                "real_external_call_executed": True,
                "wecom_media_upload_executed": True,
                "provider_result_received": True,
            },
            real_external_call_executed=True,
            provider_result_received=True,
        )

    def _build_manager(self):
        if self._manager_factory is not None:
            return self._manager_factory()
        return build_wecom_media_lease_manager()


def build_wecom_media_upload_adapter_registry():
    from aicrm_next.external_effect_composition import build_external_effect_adapter_registry

    return build_external_effect_adapter_registry()


def _plan_upload_job(
    *,
    material_kind: str,
    material_id: int,
    upload_kind: str,
    actor: str,
    source_route: str,
    idempotency_key: str,
    force_refresh: bool,
    repository=None,
) -> dict[str, Any]:
    repo = repository or build_external_effect_repository()
    return ExternalEffectService(repo).plan_effect(
        effect_type=WECOM_MEDIA_UPLOAD,
        adapter_name=ADAPTER_NAME,
        operation="refresh_temporary_media",
        target_type="media_library_material",
        target_id=f"{material_kind}:{int(material_id)}:{upload_kind}",
        payload={
            "material_kind": material_kind,
            "material_id": int(material_id),
            "upload_kind": upload_kind,
            "force_refresh": bool(force_refresh),
            "bypass_push_capability": True,
        },
        payload_summary={
            "material_kind": material_kind,
            "material_id": int(material_id),
            "upload_kind": upload_kind,
            "source_payload_persisted": False,
        },
        context=CommandContext(actor_id=actor, actor_type="system", source_route=source_route),
        business_type="media_library_lease",
        business_id=f"{material_kind}:{int(material_id)}",
        source_module="wecom_media_jobs",
        risk_level="low",
        requires_approval=False,
        execution_mode="execute",
        priority=30,
        max_attempts=5,
        idempotency_key=idempotency_key,
    )


def sync_uploaded_material(
    *,
    material_kind: str,
    material_id: int,
    upload_kind: str,
    actor: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if not production_data_ready():
        return {"status": "skipped", "reason": "production_data_not_ready", "real_external_call_executed": False}
    repo = build_external_effect_repository()
    job = _plan_upload_job(
        material_kind=material_kind,
        material_id=material_id,
        upload_kind=upload_kind,
        actor=actor,
        source_route=f"/api/admin/{'image' if material_kind == 'image' else 'attachment'}-library/upload",
        idempotency_key=f"media-upload:{material_kind}:{material_id}:{idempotency_key or 'initial'}",
        force_refresh=True,
        repository=repo,
    )
    result = ExternalEffectWorker(
        repo,
        build_wecom_media_upload_adapter_registry(),
        locked_by=f"media-upload-inline-{material_kind}-{material_id}",
    ).dispatch_one(int(job.get("id") or 0))
    current = (result.get("job") or {}) if isinstance(result, dict) else {}
    return {
        "status": str(current.get("status") or "unknown"),
        "job_id": int(current.get("id") or job.get("id") or 0),
        "real_external_call_executed": bool(result.get("real_external_call_executed")),
        "error_code": str(current.get("last_error_code") or ""),
    }


def enqueue_due_media_refreshes(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    operator: str = "automation_ops_scheduler",
    limit: int = 50,
    manager=None,
    repository=None,
) -> dict[str, Any]:
    scanned_at = _utc(now)
    if production_environment() and not production_data_ready():
        return {
            "component": "wecom_media_lease_refresher",
            "status": "failed",
            "candidate_count": 0,
            "enqueued_count": 0,
            "errors": [{"scope": "wecom_media_lease_refresher", "error": "production_data_not_ready"}],
        }
    lease_manager = manager or build_wecom_media_lease_manager(now=scanned_at)
    candidates = lease_manager.list_due_materials(limit=limit)
    if dry_run:
        return {
            "component": "wecom_media_lease_refresher",
            "status": "skipped",
            "reason": "dry_run",
            "candidate_count": len(candidates),
            "enqueued_count": 0,
            "items": candidates,
            "errors": [],
        }
    repo = repository or build_external_effect_repository()
    enqueued: list[dict[str, Any]] = []
    bucket = scanned_at.strftime("%Y%m%d%H")
    for candidate in candidates:
        kind = str(candidate.get("material_kind") or "")
        material_id = int(candidate.get("material_id") or 0)
        upload_kind = str(candidate.get("upload_kind") or "")
        job = _plan_upload_job(
            material_kind=kind,
            material_id=material_id,
            upload_kind=upload_kind,
            actor=operator,
            source_route="automation_ops_scheduler:wecom_media_lease_refresher",
            idempotency_key=f"media-refresh:{kind}:{material_id}:{upload_kind}:{bucket}",
            force_refresh=True,
            repository=repo,
        )
        enqueued.append({"job_id": int(job.get("id") or 0), **candidate})
    return {
        "component": "wecom_media_lease_refresher",
        "status": "ok",
        "candidate_count": len(candidates),
        "enqueued_count": len(enqueued),
        "items": enqueued,
        "metrics": lease_manager.metrics(),
        "errors": [],
    }
