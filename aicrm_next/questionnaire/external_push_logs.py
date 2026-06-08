from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import requests

from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan
from aicrm_next.shared.errors import NotFoundError

from .repo import QuestionnaireRepository, build_questionnaire_repository

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_PLANNED = "planned"
_REAL_RETRY_ENV = "AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_RETRY_REAL_ENABLED"
_plans = InMemorySideEffectPlanRepository()


@dataclass(frozen=True)
class QuestionnaireExternalPushRetryCommand:
    push_log_id: int
    command_id: str = field(default_factory=lambda: uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "questionnaire_admin"
    actor_type: str = "user"
    source_route: str = ""


@dataclass(frozen=True)
class QuestionnaireExternalPushRetryBatchCommand:
    push_log_ids: list[int] = field(default_factory=list)
    questionnaire_id: int | None = None
    command_id: str = field(default_factory=lambda: uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "questionnaire_admin"
    actor_type: str = "user"
    source_route: str = ""


class ExternalPushDeliveryAdapter:
    def __init__(self, *, real_enabled: bool | None = None, timeout_seconds: float = 3.0) -> None:
        self._real_enabled = real_enabled
        self._timeout_seconds = max(0.5, min(float(timeout_seconds or 3.0), 10.0))

    @property
    def adapter_mode(self) -> str:
        return "real_enabled" if self.real_enabled else "real_blocked"

    @property
    def real_enabled(self) -> bool:
        if self._real_enabled is not None:
            return bool(self._real_enabled)
        return str(os.getenv(_REAL_RETRY_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}

    def deliver(self, *, target_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.real_enabled:
            return {
                "ok": False,
                "attempted": False,
                "status": STATUS_PLANNED,
                "response_status_code": None,
                "response_body": "",
                "failure_reason": "retry side-effect planned; real external call blocked",
                "real_external_call_executed": False,
            }
        if not target_url:
            return {
                "ok": False,
                "attempted": False,
                "status": STATUS_FAILED,
                "response_status_code": None,
                "response_body": "",
                "failure_reason": "external push url is empty",
                "real_external_call_executed": False,
            }
        try:
            response = requests.post(
                target_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self._timeout_seconds,
            )
        except requests.Timeout as exc:
            return {
                "ok": False,
                "attempted": True,
                "status": STATUS_FAILED,
                "response_status_code": None,
                "response_body": "",
                "failure_reason": f"request timeout: {exc}",
                "real_external_call_executed": True,
            }
        except requests.RequestException as exc:
            return {
                "ok": False,
                "attempted": True,
                "status": STATUS_FAILED,
                "response_status_code": None,
                "response_body": "",
                "failure_reason": f"network error: {exc}",
                "real_external_call_executed": True,
            }
        status_code = int(response.status_code)
        return {
            "ok": status_code == 200,
            "attempted": True,
            "status": STATUS_SUCCESS if status_code == 200 else STATUS_FAILED,
            "response_status_code": status_code,
            "response_body": (response.text or "")[:5000],
            "failure_reason": "" if status_code == 200 else f"HTTP {status_code}",
            "real_external_call_executed": True,
        }


class QuestionnaireExternalPushLogReadService:
    def __init__(self, repository: QuestionnaireRepository | None = None) -> None:
        self._repo = repository or build_questionnaire_repository()

    def questionnaire_logs(self, questionnaire_id: int, *, status: str = "", limit: int | str = 50) -> dict[str, Any] | None:
        questionnaire = self._repo.get_questionnaire(int(questionnaire_id))
        if not questionnaire:
            return None
        logs_path = f"/admin/questionnaires/{int(questionnaire_id)}/external-push-logs"
        normalized_status, effective_status = _normalize_status_filter(status)
        normalized_limit = _bounded_int(limit, default=50, minimum=1, maximum=200)
        rows = self._repo.list_external_push_log_threads(
            int(questionnaire_id),
            status=effective_status,
            limit=normalized_limit,
        )
        normalized_rows = [_normalize_thread(row) for row in rows]
        return {
            "is_global": False,
            "questionnaire": {**questionnaire, **_questionnaire_paths(questionnaire)},
            "paths": {
                "index": logs_path,
                "retry_batch": f"{logs_path}/retry-batch",
            },
            "filters": {"status": normalized_status, "limit": normalized_limit},
            "status_options": _status_options(),
            "summary": self._repo.summarize_external_push_logs(int(questionnaire_id)),
            "logs": normalized_rows,
            "retryable_count": sum(1 for row in normalized_rows if row.get("can_retry")),
            "source_status": getattr(self._repo, "source_status", "local_contract_probe"),
            "route_owner": "ai_crm_next",
            "fallback_used": False,
        }

    def global_logs(
        self,
        *,
        questionnaire_id: str = "",
        questionnaire_title: str = "",
        status: str = "",
        user_id: str = "",
        target_url: str = "",
        limit: int | str = 50,
    ) -> dict[str, Any]:
        normalized_questionnaire_id = _bounded_int(questionnaire_id, default=0, minimum=0, maximum=10**9)
        questionnaire_filter = normalized_questionnaire_id or None
        normalized_status, effective_status = _normalize_status_filter(status)
        normalized_limit = _bounded_int(limit, default=50, minimum=1, maximum=200)
        rows = self._repo.list_external_push_log_threads(
            questionnaire_filter,
            questionnaire_title=_text(questionnaire_title),
            user_id=_text(user_id),
            target_url=_text(target_url),
            status=effective_status,
            limit=normalized_limit,
        )
        all_rows = self._repo.list_external_push_log_threads(None, limit=None)
        normalized_rows = [_normalize_thread(row) for row in rows]
        for row in normalized_rows:
            row["questionnaire_path"] = f"/admin/questionnaires/{int(row.get('questionnaire_id') or 0)}"
            row["questionnaire_logs_path"] = f"/admin/questionnaires/{int(row.get('questionnaire_id') or 0)}/external-push-logs"
        questionnaires, total_questionnaires = self._repo.list_questionnaires(limit=1000, offset=0)
        recent_since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        logs_path = "/admin/questionnaires/external-push-logs"
        return {
            "is_global": True,
            "questionnaire": None,
            "paths": {
                "index": logs_path,
                "retry_batch": f"{logs_path}/retry-batch",
            },
            "filters": {
                "questionnaire_id": normalized_questionnaire_id,
                "questionnaire_title": _text(questionnaire_title),
                "status": normalized_status,
                "user_id": _text(user_id),
                "target_url": _text(target_url),
                "limit": normalized_limit,
            },
            "status_options": _status_options(),
            "summary": {
                "questionnaire_total_count": total_questionnaires,
                "enabled_questionnaire_count": sum(1 for item in questionnaires if _external_push_enabled(item)),
                "matched_questionnaire_count": len({int(row.get("questionnaire_id") or 0) for row in normalized_rows}),
                "total_log_count": self._repo.count_external_push_logs(),
                "current_failed_count": sum(1 for row in all_rows if row.get("can_retry")),
                "current_success_count": sum(1 for row in all_rows if _text(row.get("latest_status")) == STATUS_SUCCESS),
                "current_skipped_count": sum(1 for row in all_rows if _text(row.get("latest_status")) == STATUS_SKIPPED),
                "recent_success_count": self._repo.count_external_push_logs(status=STATUS_SUCCESS, created_at_gte=recent_since),
                "recent_failed_count": self._repo.count_external_push_logs(status=STATUS_FAILED, created_at_gte=recent_since),
                "global_switch_enabled": True,
                "global_switch_label": "已开启",
                "global_switch_tone": "ok",
            },
            "logs": normalized_rows,
            "retryable_count": sum(1 for row in normalized_rows if row.get("can_retry")),
            "source_status": getattr(self._repo, "source_status", "local_contract_probe"),
            "route_owner": "ai_crm_next",
            "fallback_used": False,
        }


class QuestionnaireExternalPushRetryService:
    def __init__(
        self,
        repository: QuestionnaireRepository | None = None,
        adapter: ExternalPushDeliveryAdapter | None = None,
    ) -> None:
        self._repo = repository or build_questionnaire_repository()
        self._adapter = adapter or ExternalPushDeliveryAdapter()

    def retry_one(self, command: QuestionnaireExternalPushRetryCommand) -> dict[str, Any]:
        source = self._repo.get_external_push_log(int(command.push_log_id))
        if not source:
            raise NotFoundError("questionnaire external push log not found")
        root_id = int(source.get("retry_from_log_id") or source.get("id") or 0)
        latest = self._latest_thread_log(root_id)
        if _text(latest.get("status")) != STATUS_FAILED:
            plan = _retry_plan(command.command_id, self._adapter.adapter_mode, latest, skipped=True)
            return _retry_response(
                command=command,
                source_log=source,
                log=latest,
                plan=plan,
                skipped=True,
                skip_reason="latest external push log is not failed",
                adapter=self._adapter,
            )
        delivery = self._adapter.deliver(
            target_url=_text(latest.get("target_url")),
            payload=dict(latest.get("request_payload") or {}),
        )
        retry_log = self._repo.create_external_push_log(
            questionnaire_id=int(latest.get("questionnaire_id") or 0),
            questionnaire_title_snapshot=_text(latest.get("questionnaire_title_snapshot")),
            submission_record_id=int(latest.get("submission_record_id") or 0),
            retry_from_log_id=root_id,
            retry_attempt=self._repo.count_external_push_retry_logs(root_id) + 1,
            user_id=_text(latest.get("user_id")),
            target_url=_text(latest.get("target_url")),
            request_payload=dict(latest.get("request_payload") or {}),
            response_status_code=delivery.get("response_status_code"),
            response_body=_text(delivery.get("response_body")),
            status=_text(delivery.get("status") or STATUS_PLANNED),
            failure_reason=_text(delivery.get("failure_reason")),
        )
        plan = _retry_plan(command.command_id, self._adapter.adapter_mode, retry_log, skipped=False)
        return _retry_response(
            command=command,
            source_log=source,
            log=retry_log,
            plan=plan,
            skipped=False,
            skip_reason="",
            adapter=self._adapter,
        )

    def retry_batch(self, command: QuestionnaireExternalPushRetryBatchCommand) -> dict[str, Any]:
        ids = _dedupe_positive_ints(command.push_log_ids)
        result = {
            "ok": True,
            "command_name": "questionnaire.external_push.retry_batch",
            "command_id": command.command_id,
            "source_status": "next_command",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "adapter_mode": self._adapter.adapter_mode,
            "real_external_call_executed": False,
            "selected_count": len(ids),
            "retried_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "planned_count": 0,
            "skipped_count": 0,
            "items": [],
        }
        for push_log_id in ids:
            item = self.retry_one(
                QuestionnaireExternalPushRetryCommand(
                    push_log_id=push_log_id,
                    command_id=f"{command.command_id}:{push_log_id}",
                    idempotency_key=command.idempotency_key,
                    actor_id=command.actor_id,
                    actor_type=command.actor_type,
                    source_route=command.source_route,
                )
            )
            result["items"].append(item)
            result["real_external_call_executed"] = bool(result["real_external_call_executed"] or item.get("real_external_call_executed"))
            if item.get("skipped"):
                result["skipped_count"] += 1
                continue
            result["retried_count"] += 1
            status = _text((item.get("log") or {}).get("status"))
            if status == STATUS_SUCCESS:
                result["success_count"] += 1
            elif status == STATUS_PLANNED:
                result["planned_count"] += 1
            else:
                result["failed_count"] += 1
        return result

    def _latest_thread_log(self, root_id: int) -> dict[str, Any]:
        threads = self._repo.list_external_push_log_threads(None, limit=None)
        for thread in threads:
            if int(thread.get("id") or 0) == int(root_id):
                latest = thread.get("latest_log")
                return dict(latest) if isinstance(latest, dict) else dict(thread)
        root = self._repo.get_external_push_log(root_id)
        if not root:
            raise NotFoundError("questionnaire external push log not found")
        return root


def reset_questionnaire_external_push_retry_state() -> None:
    global _plans
    _plans = InMemorySideEffectPlanRepository()


def get_questionnaire_external_push_retry_side_effect_plans() -> list[dict[str, Any]]:
    return [plan.to_dict() for plan in _plans.list_plans()]


def _retry_plan(command_id: str, adapter_mode: str, log: dict[str, Any], *, skipped: bool) -> SideEffectPlan:
    return _plans.create_plan(
        command_id=command_id,
        effect_type="questionnaire.external_push.retry",
        adapter_name="questionnaire_external_push",
        adapter_mode=adapter_mode,
        target_type="questionnaire_external_push_log",
        target_id=str(log.get("id") or ""),
        payload={
            "payload_summary": {
                "questionnaire_id": int(log.get("questionnaire_id") or 0),
                "source_log_id": int(log.get("retry_from_log_id") or log.get("id") or 0),
                "retry_log_id": int(log.get("id") or 0),
                "target_url": _text(log.get("target_url")),
                "status": _text(log.get("status")),
                "skipped": bool(skipped),
            }
        },
        risk_level="medium",
        requires_approval=adapter_mode != "real_enabled",
    )


def _retry_response(
    *,
    command: QuestionnaireExternalPushRetryCommand,
    source_log: dict[str, Any],
    log: dict[str, Any],
    plan: SideEffectPlan,
    skipped: bool,
    skip_reason: str,
    adapter: ExternalPushDeliveryAdapter,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command_name": "questionnaire.external_push.retry",
        "command_id": command.command_id,
        "source_status": "next_command",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "adapter_mode": adapter.adapter_mode,
        "real_external_call_executed": adapter.real_enabled and not skipped,
        "skipped": bool(skipped),
        "skip_reason": skip_reason,
        "source_log": source_log,
        "log": log,
        "side_effect_plan": plan.to_dict(),
    }


def _normalize_thread(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["first_status_label"] = _status_label(_text(payload.get("status")))
    payload["first_status_tone"] = _status_tone(_text(payload.get("status")))
    payload["effective_status_label"] = _status_label(_text(payload.get("latest_status")))
    payload["effective_status_tone"] = _status_tone(_text(payload.get("latest_status")))
    payload["latest_log"] = _normalize_log(dict(payload.get("latest_log") or {}))
    payload["latest_response_status_code"] = payload["latest_log"].get("response_status_code")
    payload["latest_response_body"] = payload["latest_log"].get("response_body")
    payload["latest_failure_reason"] = payload["latest_log"].get("failure_reason")
    payload["latest_updated_at"] = payload["latest_log"].get("updated_at") or payload["latest_log"].get("created_at")
    payload["retries"] = [_normalize_log(dict(item)) for item in payload.get("retries") or []]
    return payload


def _normalize_log(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["status_label"] = _status_label(_text(payload.get("status")))
    payload["status_tone"] = _status_tone(_text(payload.get("status")))
    return payload


def _status_options() -> list[dict[str, str]]:
    return [
        {"value": "", "label": "全部"},
        {"value": "failed_current", "label": "仅待补发"},
        {"value": "success_current", "label": "仅当前成功"},
        {"value": "planned_current", "label": "仅已生成补发计划"},
    ]


def _normalize_status_filter(value: Any) -> tuple[str, str]:
    normalized = _text(value)
    if normalized in {"failed", "failed_current"}:
        return "failed_current", STATUS_FAILED
    if normalized in {"success", "success_current"}:
        return "success_current", STATUS_SUCCESS
    if normalized in {"planned", "planned_current"}:
        return "planned_current", STATUS_PLANNED
    return "", ""


def _status_label(value: str) -> str:
    return {
        STATUS_SUCCESS: "成功",
        STATUS_FAILED: "失败",
        STATUS_SKIPPED: "已跳过",
        STATUS_PLANNED: "已生成补发计划",
    }.get(_text(value), _text(value) or "未知")


def _status_tone(value: str) -> str:
    return {
        STATUS_SUCCESS: "ok",
        STATUS_FAILED: "danger",
        STATUS_SKIPPED: "warning",
        STATUS_PLANNED: "warning",
    }.get(_text(value), "muted")


def _questionnaire_paths(questionnaire: dict[str, Any]) -> dict[str, str]:
    questionnaire_id = int(questionnaire.get("id") or 0)
    slug = _text(questionnaire.get("slug"))
    return {
        "admin_path": f"/admin/questionnaires/{questionnaire_id}",
        "public_path": f"/s/{slug}" if slug else "",
        "external_push_logs_path": f"/admin/questionnaires/{questionnaire_id}/external-push-logs",
    }


def _external_push_enabled(questionnaire: dict[str, Any]) -> bool:
    config = questionnaire.get("external_push_config") if isinstance(questionnaire.get("external_push_config"), dict) else {}
    return _bool(questionnaire.get("external_push_enabled", config.get("enabled")))


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return max(minimum, min(normalized, maximum))


def _dedupe_positive_ints(values: list[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values or []:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}
