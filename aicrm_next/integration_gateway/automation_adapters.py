from __future__ import annotations

import hashlib
import os
from typing import Any

from .audit import record_audit_event
from .automation_contracts import AdapterMode, Json
from .idempotency import get_or_create, make_idempotency_key


VALID_MODES = {"fake", "disabled", "staging", "production"}


def _normalise_mode(value: str | None, *, default: AdapterMode = "fake") -> AdapterMode:
    mode = (value or default).strip().lower()
    if mode not in VALID_MODES:
        return default
    return mode  # type: ignore[return-value]


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mode_prefix(mode: AdapterMode) -> str:
    return "staging" if mode == "staging" else "fake"


def _safe_target(target: dict[str, Any]) -> dict[str, Any]:
    forbidden = {
        "secret",
        "token",
        "access_token",
        "client_secret",
        "app_secret",
        "credential",
        "password",
        "api_key",
        "private_key",
        "cert",
        "certificate",
        "webhook_token",
        "openclaw_token",
    }

    def is_secret_key(key: str) -> bool:
        lowered = key.lower()
        return any(marker in lowered for marker in forbidden)

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if not is_secret_key(key)}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub(target)


def _payload_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    safe = _safe_target(payload or {})
    return {"payload_hash": _digest(repr(sorted(safe.items())))[:24], "payload_keys": sorted(safe.keys())}


def _base_result(
    *,
    ok: bool,
    adapter: str,
    mode: AdapterMode,
    operation: str,
    idempotency_key: str,
    target: dict[str, Any],
    result: dict[str, Any] | None,
    audit_id: str,
    error_code: str = "",
    error_message: str = "",
) -> Json:
    return {
        "ok": ok,
        "adapter": adapter,
        "mode": mode,
        "operation": operation,
        "idempotency_key": idempotency_key,
        "target": _safe_target(target),
        "result": result or {},
        "audit_id": audit_id,
        "side_effect_executed": False,
        "error_code": error_code,
        "error_message": error_message,
    }


class _GuardedAutomationAdapter:
    adapter_name = "AutomationAdapter"
    production_flag = ""

    def __init__(self, mode: AdapterMode | str = "fake") -> None:
        self.mode = _normalise_mode(str(mode), default="fake")

    def _guarded_result(self, *, operation: str, idempotency_key: str, target: dict[str, Any]) -> Json | None:
        if self.mode == "disabled":
            audit = record_audit_event(
                adapter=self.adapter_name,
                operation=operation,
                mode=self.mode,
                idempotency_key=idempotency_key,
                side_effect_executed=False,
                status="blocked",
                error_code="adapter_disabled",
            )
            return _base_result(
                ok=False,
                adapter=self.adapter_name,
                mode=self.mode,
                operation=operation,
                idempotency_key=idempotency_key,
                target=target,
                result={},
                audit_id=audit["audit_id"],
                error_code="adapter_disabled",
                error_message=f"{self.adapter_name} is disabled",
            )
        if self.mode == "production":
            error_code = "production_guard_failed" if not _env_true(self.production_flag) else "production_not_implemented"
            audit = record_audit_event(
                adapter=self.adapter_name,
                operation=operation,
                mode=self.mode,
                idempotency_key=idempotency_key,
                side_effect_executed=False,
                status="blocked",
                error_code=error_code,
            )
            return _base_result(
                ok=False,
                adapter=self.adapter_name,
                mode=self.mode,
                operation=operation,
                idempotency_key=idempotency_key,
                target=target,
                result={},
                audit_id=audit["audit_id"],
                error_code=error_code,
                error_message=f"{self.adapter_name} production mode is not implemented in D7.5",
            )
        return None

    def _successful_result(self, *, operation: str, idempotency_key: str, target: dict[str, Any], factory) -> Json:
        cached = get_or_create(idempotency_key, factory)
        audit = record_audit_event(
            adapter=self.adapter_name,
            operation=operation,
            mode=self.mode,
            idempotency_key=idempotency_key,
            side_effect_executed=False,
            status="ok",
        )
        return _base_result(
            ok=True,
            adapter=self.adapter_name,
            mode=self.mode,
            operation=operation,
            idempotency_key=idempotency_key,
            target=target,
            result=cached,
            audit_id=audit["audit_id"],
        )

    def _operation(self, operation: str, *, target: dict[str, Any], result_factory, idempotency_key: str | None = None) -> Json:
        key = idempotency_key or make_idempotency_key(operation=operation, payload=_safe_target(target))
        guarded = self._guarded_result(operation=operation, idempotency_key=key, target=target)
        if guarded:
            return guarded
        return self._successful_result(operation=operation, idempotency_key=key, target=target, factory=result_factory)

    def _audit_only(
        self,
        *,
        operation: str,
        target: dict[str, Any],
        result: dict[str, Any] | None = None,
        error_code: str = "",
        idempotency_key: str | None = None,
    ) -> Json:
        key = idempotency_key or make_idempotency_key(operation=operation, payload={"target": _safe_target(target), "result": result or {}})
        audit = record_audit_event(
            adapter=self.adapter_name,
            operation=operation,
            mode=self.mode,
            idempotency_key=key,
            side_effect_executed=False,
            status="blocked" if error_code else "ok",
            error_code=error_code,
        )
        return _base_result(
            ok=not error_code,
            adapter=self.adapter_name,
            mode=self.mode,
            operation=operation,
            idempotency_key=key,
            target=target,
            result=result or {},
            audit_id=audit["audit_id"],
            error_code=error_code,
            error_message="" if not error_code else "audit recorded as blocked",
        )


class AutomationWriteGateway(_GuardedAutomationAdapter):
    adapter_name = "AutomationWriteGateway"
    production_flag = "AICRM_NEXT_ENABLE_REAL_AUTOMATION_WRITES"

    def override_followup_type(self, *, member_id: str, followup_type: str, operator: str = "system", reason: str = "", external_userid: str = "", idempotency_key: str | None = None) -> Json:
        return self._write_operation("override_followup_type", member_id=member_id, external_userid=external_userid, operator=operator, reason=reason, write_payload={"followup_type": followup_type}, idempotency_key=idempotency_key)

    def confirm_conversion(self, *, member_id: str, operator: str = "system", reason: str = "", external_userid: str = "", idempotency_key: str | None = None) -> Json:
        return self._write_operation("confirm_conversion", member_id=member_id, external_userid=external_userid, operator=operator, reason=reason, write_payload={"converted": True}, idempotency_key=idempotency_key)

    def enter_silent(self, *, member_id: str, operator: str = "system", reason: str = "", external_userid: str = "", idempotency_key: str | None = None) -> Json:
        return self._write_operation("enter_silent", member_id=member_id, external_userid=external_userid, operator=operator, reason=reason, write_payload={"silent": True}, idempotency_key=idempotency_key)

    def exit_marketing(self, *, member_id: str, operator: str = "system", reason: str = "", external_userid: str = "", idempotency_key: str | None = None) -> Json:
        return self._write_operation("exit_marketing", member_id=member_id, external_userid=external_userid, operator=operator, reason=reason, write_payload={"exited": True}, idempotency_key=idempotency_key)

    def build_write_preview(self, *, operation: str, member_id: str = "", external_userid: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        return self._write_operation(operation, member_id=member_id, external_userid=external_userid, write_payload=_payload_summary(payload_summary), idempotency_key=idempotency_key)

    def record_write_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json:
        return self._audit_only(operation=operation, target=target, result=result, error_code=error_code, idempotency_key=idempotency_key)

    def _write_operation(self, operation: str, *, member_id: str, external_userid: str = "", operator: str = "system", reason: str = "", write_payload: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"member_id": member_id, "external_userid": external_userid, "operator": operator, "reason": reason, "write_payload": _safe_target(write_payload or {})}
        mode_prefix = _mode_prefix(self.mode)
        return self._operation(
            operation,
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {
                "write_id": f"{mode_prefix}_automation_write_{_digest(operation + repr(target))[:16]}",
                "operation": operation,
                "source_status": mode_prefix,
                "applied": False,
                "real_automation_write_executed": False,
            },
        )


class AutomationActivationGateway(_GuardedAutomationAdapter):
    adapter_name = "AutomationActivationGateway"
    production_flag = "AICRM_NEXT_ENABLE_REAL_AUTOMATION_ACTIVATION"

    def receive_activation_event(self, *, activation_event_id: str = "", member_id: str = "", external_userid: str = "", mobile: str = "", source: str = "activation_webhook", idempotency_key: str | None = None) -> Json:
        target = {"activation_event_id": activation_event_id, "member_id": member_id, "external_userid": external_userid, "mobile": mobile, "source": source}
        mode_prefix = _mode_prefix(self.mode)
        return self._operation(
            "receive_activation_event",
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {
                "activation_event_id": activation_event_id or f"{mode_prefix}_activation_{_digest(repr(target))[:16]}",
                "accepted": True,
                "normalized": True,
                "applied": False,
                "real_activation_webhook_executed": False,
            },
        )

    def normalize_activation_payload(self, *, activation_event_id: str = "", payload: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"activation_event_id": activation_event_id, "payload_summary": _payload_summary(payload)}
        return self._operation(
            "normalize_activation_payload",
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {
                "normalized": True,
                "payload_summary": target["payload_summary"],
                "applied": False,
                "real_activation_webhook_executed": False,
            },
        )

    def build_activation_preview(self, *, activation_event_id: str = "", member_id: str = "", external_userid: str = "", mobile: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"activation_event_id": activation_event_id, "member_id": member_id, "external_userid": external_userid, "mobile": mobile, "payload_summary": _payload_summary(payload_summary)}
        return self._operation(
            "build_activation_preview",
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {"would_apply_activation": False, "source_status": _mode_prefix(self.mode)},
        )

    def record_activation_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json:
        return self._audit_only(operation=operation, target=target, result=result, error_code=error_code, idempotency_key=idempotency_key)


class OpenClawWebhookAdapter(_GuardedAutomationAdapter):
    adapter_name = "OpenClawWebhookAdapter"
    production_flag = "AICRM_NEXT_ENABLE_REAL_OPENCLAW_WEBHOOK"

    def push_member_context(self, *, member_id: str, external_userid: str = "", openclaw_context_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"member_id": member_id, "external_userid": external_userid, "openclaw_context_id": openclaw_context_id, "payload_summary": _payload_summary(payload_summary)}
        return self._openclaw_operation("push_member_context", target=target, idempotency_key=idempotency_key)

    def push_workflow_context(self, *, workflow_id: str, member_id: str = "", execution_id: str = "", openclaw_context_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"workflow_id": workflow_id, "member_id": member_id, "execution_id": execution_id, "openclaw_context_id": openclaw_context_id, "payload_summary": _payload_summary(payload_summary)}
        return self._openclaw_operation("push_workflow_context", target=target, idempotency_key=idempotency_key)

    def build_openclaw_payload_preview(self, *, member_id: str = "", workflow_id: str = "", openclaw_context_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"member_id": member_id, "workflow_id": workflow_id, "openclaw_context_id": openclaw_context_id, "payload_summary": _payload_summary(payload_summary)}
        return self._openclaw_operation("build_openclaw_payload_preview", target=target, idempotency_key=idempotency_key)

    def record_openclaw_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json:
        return self._audit_only(operation=operation, target=target, result=result, error_code=error_code, idempotency_key=idempotency_key)

    def _openclaw_operation(self, operation: str, *, target: dict[str, Any], idempotency_key: str | None) -> Json:
        mode_prefix = _mode_prefix(self.mode)
        return self._operation(
            operation,
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {
                "openclaw_request_id": f"{mode_prefix}_openclaw_{_digest(operation + repr(target))[:16]}",
                "queued": False,
                "sent": False,
                "real_openclaw_push_executed": False,
                "real_external_webhook_executed": False,
            },
        )


class AutomationWorkflowRuntimeAdapter(_GuardedAutomationAdapter):
    adapter_name = "AutomationWorkflowRuntimeAdapter"
    production_flag = "AICRM_NEXT_ENABLE_REAL_AUTOMATION_WORKFLOW_RUNTIME"

    def enqueue_workflow_run(self, *, workflow_id: str, member_id: str = "", execution_id: str = "", program_id: str = "", idempotency_key: str | None = None) -> Json:
        return self._workflow_operation("enqueue_workflow_run", workflow_id=workflow_id, member_id=member_id, execution_id=execution_id, program_id=program_id, idempotency_key=idempotency_key)

    def run_workflow_node(self, *, workflow_id: str, node_id: str, member_id: str = "", execution_id: str = "", idempotency_key: str | None = None) -> Json:
        return self._workflow_operation("run_workflow_node", workflow_id=workflow_id, node_id=node_id, member_id=member_id, execution_id=execution_id, idempotency_key=idempotency_key)

    def run_due_workflows(self, *, workflow_id: str = "", program_id: str = "", limit: int = 50, idempotency_key: str | None = None) -> Json:
        return self._workflow_operation("run_due_workflows", workflow_id=workflow_id, program_id=program_id, limit=limit, idempotency_key=idempotency_key)

    def build_workflow_runtime_preview(self, *, workflow_id: str = "", node_id: str = "", member_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        return self._workflow_operation("build_workflow_runtime_preview", workflow_id=workflow_id, node_id=node_id, member_id=member_id, execution_id=execution_id, payload_summary=payload_summary, idempotency_key=idempotency_key)

    def record_workflow_runtime_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json:
        return self._audit_only(operation=operation, target=target, result=result, error_code=error_code, idempotency_key=idempotency_key)

    def _workflow_operation(self, operation: str, *, workflow_id: str = "", node_id: str = "", member_id: str = "", execution_id: str = "", program_id: str = "", limit: int | None = None, payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"workflow_id": workflow_id, "node_id": node_id, "member_id": member_id, "execution_id": execution_id, "program_id": program_id, "limit": limit, "payload_summary": _payload_summary(payload_summary)}
        mode_prefix = _mode_prefix(self.mode)
        return self._operation(
            operation,
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {
                "workflow_run_id": f"{mode_prefix}_workflow_{_digest(operation + repr(target))[:16]}",
                "queued": False,
                "would_enqueue": operation == "enqueue_workflow_run",
                "executed": False,
                "executed_count": 0,
                "real_workflow_runtime_executed": False,
            },
        )


class AutomationAgentRuntimeAdapter(_GuardedAutomationAdapter):
    adapter_name = "AutomationAgentRuntimeAdapter"
    production_flag = "AICRM_NEXT_ENABLE_REAL_AUTOMATION_AGENT_RUNTIME"

    def run_agent_task(self, *, agent_task_id: str, member_id: str = "", workflow_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        return self._agent_operation("run_agent_task", agent_task_id=agent_task_id, member_id=member_id, workflow_id=workflow_id, execution_id=execution_id, payload_summary=payload_summary, idempotency_key=idempotency_key)

    def generate_agent_output(self, *, agent_task_id: str, member_id: str = "", workflow_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        return self._agent_operation("generate_agent_output", agent_task_id=agent_task_id, member_id=member_id, workflow_id=workflow_id, execution_id=execution_id, payload_summary=payload_summary, idempotency_key=idempotency_key)

    def review_agent_output(self, *, agent_task_id: str, output_id: str = "", reviewer: str = "system", decision: str = "preview", idempotency_key: str | None = None) -> Json:
        return self._agent_operation("review_agent_output", agent_task_id=agent_task_id, output_id=output_id, reviewer=reviewer, decision=decision, idempotency_key=idempotency_key)

    def build_agent_runtime_preview(self, *, agent_task_id: str = "", member_id: str = "", workflow_id: str = "", execution_id: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        return self._agent_operation("build_agent_runtime_preview", agent_task_id=agent_task_id, member_id=member_id, workflow_id=workflow_id, execution_id=execution_id, payload_summary=payload_summary, idempotency_key=idempotency_key)

    def record_agent_runtime_audit(self, *, operation: str, target: dict[str, Any], result: dict[str, Any] | None = None, error_code: str = "", idempotency_key: str | None = None) -> Json:
        return self._audit_only(operation=operation, target=target, result=result, error_code=error_code, idempotency_key=idempotency_key)

    def _agent_operation(self, operation: str, *, agent_task_id: str = "", member_id: str = "", workflow_id: str = "", execution_id: str = "", output_id: str = "", reviewer: str = "", decision: str = "", payload_summary: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Json:
        target = {"agent_task_id": agent_task_id, "member_id": member_id, "workflow_id": workflow_id, "execution_id": execution_id, "output_id": output_id, "reviewer": reviewer, "decision": decision, "payload_summary": _payload_summary(payload_summary)}
        mode_prefix = _mode_prefix(self.mode)
        return self._operation(
            operation,
            target=target,
            idempotency_key=idempotency_key,
            result_factory=lambda: {
                "agent_run_id": f"{mode_prefix}_agent_{_digest(operation + repr(target))[:16]}",
                "output_id": output_id or f"{mode_prefix}_agent_output_{_digest(repr(target))[:12]}",
                "generated": operation == "generate_agent_output",
                "reviewed": operation == "review_agent_output",
                "executed": False,
                "real_agent_runtime_executed": False,
            },
        )


def build_automation_write_gateway() -> AutomationWriteGateway:
    return AutomationWriteGateway(os.getenv("AICRM_NEXT_AUTOMATION_WRITE_MODE", "fake"))


def build_automation_activation_gateway() -> AutomationActivationGateway:
    return AutomationActivationGateway(os.getenv("AICRM_NEXT_AUTOMATION_ACTIVATION_MODE", "fake"))


def build_openclaw_webhook_adapter() -> OpenClawWebhookAdapter:
    return OpenClawWebhookAdapter(os.getenv("AICRM_NEXT_OPENCLAW_WEBHOOK_MODE", "fake"))


def build_automation_workflow_runtime_adapter() -> AutomationWorkflowRuntimeAdapter:
    return AutomationWorkflowRuntimeAdapter(os.getenv("AICRM_NEXT_AUTOMATION_WORKFLOW_RUNTIME_MODE", "fake"))


def build_automation_agent_runtime_adapter() -> AutomationAgentRuntimeAdapter:
    return AutomationAgentRuntimeAdapter(os.getenv("AICRM_NEXT_AUTOMATION_AGENT_RUNTIME_MODE", "fake"))
