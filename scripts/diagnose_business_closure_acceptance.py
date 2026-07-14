#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


SCENARIOS: dict[str, dict[str, Any]] = {
    "group_ops_gray_send": {
        "title": "Group Ops gray send acceptance",
        "capability_owner": "automation_engine",
        "routes": [
            "/api/automation/group-ops/webhooks/{webhook_key}",
            "/api/admin/push-center/jobs/{job_id}/reconciliation",
        ],
        "required_env": ["AICRM_GROUP_OPS_GRAY_SEND_APPROVED", "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST"],
        "checks": [
            "dry-run plan exists before real receiver execution",
            "receiver is allowlisted before any real send",
            "Push Center reconciliation can explain job/effect/attempt status",
        ],
        "success_criteria": "Approved receiver gray send can be reconciled in Push Center.",
    },
    "ops_plan_to_broadcast": {
        "title": "Ops plan approval to broadcast E2E acceptance",
        "capability_owner": "platform_foundation",
        "routes": [
            "/api/admin/internal-events/{event_id}/reconciliation",
            "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve",
            "/api/admin/push-center/jobs",
        ],
        "required_env": ["AICRM_AUTH_AUTOMATION_WORKER_CLIENT_ID", "AICRM_AUTH_AUTOMATION_WORKER_CLIENT_SECRET_REF"],
        "checks": [
            "approval event creates or reuses one internal_event",
            "consumer run creates or links one business job",
            "duplicate approval does not duplicate jobs",
        ],
        "success_criteria": "Approval can be traced to consumer run, job, and Push Center status.",
    },
    "external_orders_enablement": {
        "title": "External orders enablement acceptance",
        "capability_owner": "commerce",
        "routes": ["/api/external/orders", "/api/external/orders/{order_no}"],
        "required_env": ["AICRM_AUTH_EXTERNAL_AGENT_CLIENT_ID", "AICRM_AUTH_EXTERNAL_AGENT_CLIENT_SECRET_REF"],
        "checks": [
            "missing server token remains controlled unavailable",
            "missing or wrong bearer token is rejected",
            "correct bearer token can read local order projection",
        ],
        "success_criteria": "External systems can safely authenticate and read local order state.",
    },
    "external_orders": {
        "title": "External orders enablement acceptance",
        "capability_owner": "commerce",
        "routes": ["/api/external/orders", "/api/external/orders/{order_no}"],
        "required_env": ["AICRM_AUTH_EXTERNAL_AGENT_CLIENT_ID", "AICRM_AUTH_EXTERNAL_AGENT_CLIENT_SECRET_REF"],
        "checks": [
            "missing server token remains controlled unavailable",
            "missing or wrong bearer token is rejected",
            "correct bearer token can read local order projection",
        ],
        "success_criteria": "External systems can safely authenticate and read local order state.",
    },
    "external_orders_gray": {
        "title": "External orders gray acceptance",
        "capability_owner": "commerce",
        "routes": [
            "/api/external/orders",
            "/api/admin/wechat-shop/orders/{order_id}/sync",
            "/api/admin/push-center/jobs/{job_id}/reconciliation",
        ],
        "required_env": [
            "AICRM_AUTH_EXTERNAL_AGENT_CLIENT_ID",
            "AICRM_AUTH_EXTERNAL_AGENT_CLIENT_SECRET_REF",
            "AICRM_EXTERNAL_ORDERS_GRAY_APPROVED",
        ],
        "checks": [
            "gray source is approved before live order calls",
            "duplicate order payload is idempotent",
            "order/customer/channel/source correlation is visible",
        ],
        "success_criteria": "Gray order lifecycle can be reconciled without leaking token or customer data.",
    },
    "wecom_auth_operator": {
        "title": "WeCom auth operator readiness acceptance",
        "capability_owner": "auth_wecom",
        "routes": ["/auth/wecom/start", "/auth/wecom/callback"],
        "required_env": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "ADMIN_LOGIN_REDIRECT_URI"],
        "checks": [
            "auth start route is reachable",
            "missing code and invalid state are controlled failures",
            "token exchange remains blocked unless separately approved",
        ],
        "success_criteria": "Operator auth readiness is explainable without exposing secrets.",
    },
    "wecom_auth": {
        "title": "WeCom auth and callback evidence acceptance",
        "capability_owner": "auth_wecom",
        "routes": ["/auth/wecom/start", "/auth/wecom/callback", "/wecom/external-contact/callback", "/api/wecom/events"],
        "required_env": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "ADMIN_LOGIN_REDIRECT_URI"],
        "checks": [
            "auth start readiness is explainable without token exchange",
            "callback missing code and invalid state remain controlled failures",
            "callback signature, inbound event, and idempotency evidence can be attached without leaking secrets",
        ],
        "success_criteria": "Operator auth and callback evidence is ready for gray validation without exposing WeCom secrets.",
    },
    "wecom_callback_gray": {
        "title": "WeCom callback gray acceptance",
        "capability_owner": "channel_entry",
        "routes": ["/wecom/external-contact/callback", "/api/wecom/events"],
        "required_env": ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET", "AICRM_WECOM_CALLBACK_GRAY_APPROVED"],
        "checks": [
            "invalid signature does not enqueue work",
            "duplicate callback reuses idempotency key",
            "accepted callback can be traced to event/job status",
        ],
        "success_criteria": "Gray callback can be verified, deduplicated, and reconciled.",
    },
    "core_admin_ops": {
        "title": "Core CRM admin operations acceptance",
        "capability_owner": "automation_engine",
        "routes": ["/admin/channels", "/api/admin/channels/{channel_id:int}", "/api/admin/channels/runtime-diagnosis"],
        "required_env": [],
        "checks": [
            "old draft #974 is closed or rebuilt from current main",
            "channel save errors expose FastAPI detail",
            "static asset cache behavior is covered before channel UX work ships",
        ],
        "success_criteria": "Operators can save and diagnose critical admin channel state.",
    },
}

CORE_CLOSEOUT_SCENARIOS = ["group_ops_gray_send", "ops_plan_to_broadcast", "external_orders", "wecom_auth"]


def _present(env: dict[str, str], key: str) -> bool:
    return bool(str(env.get(key) or "").strip())


def _missing_env(env: dict[str, str], keys: list[str]) -> list[str]:
    return [key for key in keys if not _present(env, key)]


def _csv(value: str) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def _value_or_not_provided(value: str) -> str:
    return str(value or "").strip() or "not_provided"


def _group_ops_blocking_reasons(env: dict[str, str], *, receiver_token: str) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if not _present(env, "AICRM_GROUP_OPS_GRAY_SEND_APPROVED"):
        reasons.append(
            {
                "code": "missing_operator_approval",
                "message": "AICRM_GROUP_OPS_GRAY_SEND_APPROVED must be configured before gray execution readiness.",
            }
        )
    if not _present(env, "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST"):
        reasons.append(
            {
                "code": "missing_receiver_allowlist",
                "message": "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST must contain the approved test receiver token.",
            }
        )
    if not str(receiver_token or "").strip():
        reasons.append(
            {
                "code": "missing_receiver_token",
                "message": "--receiver-token is required for operator execution readiness.",
            }
        )
    elif _present(env, "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST") and str(receiver_token).strip() not in _csv(
        env.get("AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST", "")
    ):
        reasons.append(
            {
                "code": "receiver_not_allowlisted",
                "message": "The supplied receiver token is not present in AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST.",
            }
        )
    return reasons


def _generic_blocking_reasons(missing_env: list[str], *, receiver_required: bool, receiver_token: str) -> list[dict[str, str]]:
    reasons = [{"code": "missing_required_env", "message": f"{key} is required before operator execution readiness."} for key in missing_env]
    if receiver_required and not str(receiver_token or "").strip():
        reasons.append({"code": "missing_receiver_token", "message": "--receiver-token is required for this gray scenario."})
    return reasons


def _group_ops_evidence(
    *,
    plan_id: str,
    event_id: str,
    effect_job_id: str,
    attempt_id: str,
    push_center_job_id: str,
    operator_execute_allowed: bool,
    blocking_reasons: list[dict[str, str]],
) -> dict[str, Any]:
    push_center_status = "ready_for_operator_reconciliation" if operator_execute_allowed else "not_collected"
    return {
        "evidence_status": "READY_FOR_OPERATOR_COLLECTION" if operator_execute_allowed else "READINESS_ONLY",
        "plan_id": _value_or_not_provided(plan_id),
        "event_id": _value_or_not_provided(event_id),
        "effect_job_id": _value_or_not_provided(effect_job_id),
        "attempt_id": _value_or_not_provided(attempt_id),
        "push_center_job_id": _value_or_not_provided(push_center_job_id),
        "push_center_status": push_center_status,
        "push_center_reconciliation_route": (
            "/api/admin/push-center/jobs/{job_id}/reconciliation"
            if not push_center_job_id
            else f"/api/admin/push-center/jobs/{push_center_job_id}/reconciliation"
        ),
        "retryable": False,
        "operator_action_required": bool(blocking_reasons),
        "business_explanation": (
            "Gray-send readiness checks passed; collect real job/effect/attempt evidence only during an approved operator run."
            if operator_execute_allowed
            else "Gray-send evidence is readiness-only until approval, receiver allowlist, and receiver token checks pass."
        ),
        "next_action_label": "Collect Push Center reconciliation" if operator_execute_allowed else "Resolve blocking reasons",
    }


def _ops_plan_e2e_evidence(
    *,
    plan_id: str,
    approval_event_id: str,
    internal_event_id: str,
    consumer_run_id: str,
    broadcast_job_id: str,
    effect_job_id: str,
    push_center_job_id: str,
    approval_status: str,
    consumer_status: str,
    duplicate_handling: str,
) -> dict[str, Any]:
    approval_state = str(approval_status or "").strip().lower()
    consumer_state = str(consumer_status or "").strip().lower()
    blocking_reasons: list[dict[str, str]] = []
    retryable = False
    operator_action_required = False
    pending_reason = ""
    derived_status = "readiness_only"
    business_explanation = "Ops plan evidence is readiness-only until plan, approval, event, consumer, and job identifiers are attached."
    next_action_label = "Attach plan evidence"

    if not str(plan_id or "").strip():
        blocking_reasons.append({"code": "missing_plan_id", "message": "--plan-id is required to trace an ops plan approval E2E."})
        derived_status = "missing_plan_id"
        pending_reason = "plan_id_not_provided"
    elif approval_state in {"", "pending", "not_approved", "draft", "waiting_approval"}:
        derived_status = "pending_approval"
        pending_reason = "plan_not_approved"
        operator_action_required = True
        business_explanation = "Plan exists in the evidence request but is not approved yet; no downstream internal event or job should be claimed."
        next_action_label = "Approve plan or attach approval evidence"
    elif not str(internal_event_id or "").strip():
        derived_status = "missing_internal_event"
        pending_reason = "approval_without_internal_event_evidence"
        operator_action_required = True
        business_explanation = "Approval evidence is present, but no internal_event id was attached; event creation/reuse still needs proof."
        next_action_label = "Attach internal_event reconciliation"
    elif not str(consumer_run_id or "").strip():
        derived_status = "consumer_pending"
        pending_reason = "internal_event_has_no_consumer_run_evidence"
        operator_action_required = False
        business_explanation = "Internal event evidence is present, but no consumer run was attached; wait for or inspect consumer execution."
        next_action_label = "Collect consumer run"
    elif consumer_state in {"failed_retryable", "blocked"}:
        derived_status = "consumer_failed"
        pending_reason = consumer_state
        retryable = True
        operator_action_required = True
        business_explanation = "Consumer evidence indicates a retryable or blocked failure; retry or operator action is required."
        next_action_label = "Retry consumer"
    elif consumer_state in {"failed", "failed_terminal"}:
        derived_status = "consumer_failed"
        pending_reason = consumer_state
        retryable = False
        operator_action_required = True
        business_explanation = "Consumer evidence indicates a terminal failure; manual investigation is required before claiming E2E completion."
        next_action_label = "Manual investigation"
    elif consumer_state == "succeeded" and (str(broadcast_job_id or "").strip() or str(effect_job_id or "").strip()):
        derived_status = "job_linked"
        business_explanation = "Consumer succeeded and a broadcast or external effect job id is attached; collect Push Center reconciliation next."
        next_action_label = "Collect Push Center reconciliation"
    elif consumer_state == "succeeded":
        derived_status = "missing_business_job"
        pending_reason = "consumer_succeeded_without_job_evidence"
        operator_action_required = True
        business_explanation = "Consumer succeeded, but no broadcast_job or external_effect_job id was attached; job creation still needs proof."
        next_action_label = "Attach generated job"
    else:
        derived_status = "consumer_pending"
        pending_reason = consumer_state or "consumer_status_not_provided"
        business_explanation = "Consumer evidence is incomplete; attach consumer status and generated job evidence before E2E completion."
        next_action_label = "Attach consumer status"

    return {
        "evidence_status": "READINESS_ONLY" if blocking_reasons or derived_status != "job_linked" else "E2E_EVIDENCE_ATTACHED",
        "plan_id": _value_or_not_provided(plan_id),
        "approval_event_id": _value_or_not_provided(approval_event_id),
        "internal_event_id": _value_or_not_provided(internal_event_id),
        "consumer_run_id": _value_or_not_provided(consumer_run_id),
        "broadcast_job_id": _value_or_not_provided(broadcast_job_id),
        "external_effect_job_id": _value_or_not_provided(effect_job_id),
        "push_center_job_id": _value_or_not_provided(push_center_job_id),
        "derived_status": derived_status,
        "pending_reason": pending_reason or "not_applicable",
        "retryable": retryable,
        "operator_action_required": operator_action_required,
        "business_explanation": business_explanation,
        "next_action_label": next_action_label,
        "duplicate_handling": str(duplicate_handling or "").strip() or "not_collected",
        "push_center_reconciliation_route": (
            "/api/admin/push-center/jobs/{job_id}/reconciliation"
            if not push_center_job_id
            else f"/api/admin/push-center/jobs/{push_center_job_id}/reconciliation"
        ),
        "blocking_reasons": blocking_reasons,
    }


def _external_orders_request_mode(*, token_configured: bool, request_token: str, request_mode: str) -> str:
    explicit = str(request_mode or "").strip().lower()
    if explicit:
        return explicit
    if not token_configured:
        return "dry_run"
    if not str(request_token or "").strip():
        return "no_token"
    if str(request_token).strip().count(".") != 2:
        return "wrong_token"
    return "valid_token"


def _visible_admin_order(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "yes", "1", "visible", "found", "linked"}


def _external_orders_evidence(
    *,
    env: dict[str, str],
    request_token: str,
    request_mode: str,
    order_no: str,
    external_order_id: str,
    idempotency_key: str,
    customer_id: str,
    channel_id: str,
    source: str,
    internal_event_id: str,
    admin_order_visibility: str,
) -> dict[str, Any]:
    token_configured = all(
        str(env.get(key) or "").strip()
        for key in (
            "AICRM_AUTH_EXTERNAL_AGENT_CLIENT_ID",
            "AICRM_AUTH_EXTERNAL_AGENT_CLIENT_SECRET_REF",
        )
    )
    mode = _external_orders_request_mode(
        token_configured=token_configured,
        request_token=request_token,
        request_mode=request_mode,
    )
    blocking_reasons: list[dict[str, str]] = []

    if not token_configured:
        blocking_reasons.append(
            {
                "code": "missing_internal_token_config",
                "message": "External-agent client credentials are not configured; external order routes should stay controlled-disabled.",
            }
        )
    elif mode == "no_token":
        blocking_reasons.append(
            {
                "code": "missing_request_token",
                "message": "Attach a redacted request-token check before claiming external order API readiness.",
            }
        )
    elif mode == "wrong_token":
        blocking_reasons.append(
            {
                "code": "invalid_request_token",
                "message": "The request token does not match the configured internal token; expect an auth rejection.",
            }
        )

    order_attached = bool(str(order_no or "").strip() or str(external_order_id or "").strip())
    idempotency_attached = bool(str(idempotency_key or "").strip())
    customer_channel_attached = all(str(value or "").strip() for value in [customer_id, channel_id, source])
    event_attached = bool(str(internal_event_id or "").strip())
    admin_visible = _visible_admin_order(admin_order_visibility)
    evidence_complete = bool(order_attached and idempotency_attached and customer_channel_attached and event_attached and admin_visible)

    if token_configured and mode == "valid_token" and not evidence_complete:
        blocking_reasons.append(
            {
                "code": "token_configured_but_not_executed",
                "message": "Valid token readiness is present, but this diagnostic is dry-run and cannot claim order linkage without evidence ids.",
            }
        )
    if not order_attached:
        blocking_reasons.append(
            {
                "code": "missing_order_evidence",
                "message": "Attach order_id or external_order_id evidence from the external order acceptance run.",
            }
        )
    if not idempotency_attached:
        blocking_reasons.append(
            {
                "code": "missing_idempotency_evidence",
                "message": "Attach the idempotency key or duplicate-order evidence before claiming order readiness.",
            }
        )
    if not customer_channel_attached:
        blocking_reasons.append(
            {
                "code": "missing_customer_channel_link",
                "message": "Attach customer_id, channel_id, and source correlation evidence.",
            }
        )
    if not event_attached:
        blocking_reasons.append(
            {
                "code": "missing_internal_event",
                "message": "Attach the internal_event id created or reused by the order flow.",
            }
        )
    if not admin_visible:
        blocking_reasons.append(
            {
                "code": "missing_admin_visibility",
                "message": "Attach admin order visibility evidence from the order page or diagnostic payload.",
            }
        )

    derived_status = (
        "order_linked"
        if token_configured and mode == "valid_token" and evidence_complete
        else ("controlled_disabled" if not token_configured else "readiness_only")
    )
    auth_status = {
        "dry_run": "not_executed",
        "no_token": "missing_request_token",
        "wrong_token": "invalid_request_token",
        "valid_token": "valid_token_readiness",
    }.get(mode, "not_executed")
    if not token_configured:
        auth_status = "controlled_disabled"

    if derived_status == "order_linked":
        blocking_reasons = [
            {"code": "order_linked", "message": "Order, idempotency, customer/channel/source, event, and admin visibility evidence are attached."}
        ]

    return {
        "evidence_status": "ORDER_LINKED_EVIDENCE_ATTACHED" if derived_status == "order_linked" else "READINESS_ONLY",
        "token_configured": token_configured,
        "token_redacted": True,
        "token_never_logged": True,
        "auth_status": auth_status,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "controlled_disabled_reason": "external-agent client credentials not configured" if not token_configured else "",
        "request_mode": mode,
        "order_id": _value_or_not_provided(order_no),
        "external_order_id": _value_or_not_provided(external_order_id),
        "idempotency_key": _value_or_not_provided(idempotency_key),
        "customer_id": _value_or_not_provided(customer_id),
        "channel_id": _value_or_not_provided(channel_id),
        "source": _value_or_not_provided(source),
        "internal_event_id": _value_or_not_provided(internal_event_id),
        "admin_order_visibility": _value_or_not_provided(admin_order_visibility),
        "reconciliation_status": derived_status,
        "derived_status": derived_status,
        "retryable": False,
        "operator_action_required": derived_status != "order_linked",
        "business_explanation": (
            "External order evidence is linked and ready for operator review without exposing token or customer secrets."
            if derived_status == "order_linked"
            else "External order acceptance remains readiness-only until token, order, idempotency, customer/channel/source, event, and admin visibility evidence are attached."
        ),
        "next_action_label": "Attach final evidence report" if derived_status == "order_linked" else "Resolve external order blocking reasons",
        "real_external_call_executed": False,
        "production_write_executed": False,
        "blocking_reasons": blocking_reasons,
    }


def _status_is_verified(value: str, accepted: set[str]) -> bool:
    return str(value or "").strip().lower() in accepted


def _wecom_evidence(
    *,
    env: dict[str, str],
    redirect_uri_expected: str,
    auth_start_status: str,
    callback_missing_code_status: str,
    callback_invalid_state_status: str,
    operator_identity_evidence: str,
    callback_signature_status: str,
    callback_event_id: str,
    inbound_event_id: str,
    idempotency_key: str,
    duplicate_callback_handling: str,
    permission_scope_evidence: str,
    customer_event_visibility: str,
    group_ops_permission_evidence: str,
    material_permission_evidence: str,
) -> dict[str, Any]:
    corp_id_configured = _present(env, "WECOM_CORP_ID")
    agent_id_configured = _present(env, "WECOM_AGENT_ID")
    redirect_uri_configured = _present(env, "ADMIN_LOGIN_REDIRECT_URI")
    callback_secret_configured = _present(env, "WECOM_CONTACT_SECRET")
    auth_status = str(auth_start_status or "").strip() or "expected_302_not_executed"
    missing_code_status = str(callback_missing_code_status or "").strip() or "controlled_400_expected"
    invalid_state_status = str(callback_invalid_state_status or "").strip() or "controlled_400_expected"
    signature_status = str(callback_signature_status or "").strip().lower() or "not_provided"
    duplicate_status = str(duplicate_callback_handling or "").strip() or "not_collected"
    blocking_reasons: list[dict[str, str]] = []

    if not corp_id_configured:
        blocking_reasons.append({"code": "missing_corp_id", "message": "WECOM_CORP_ID must be configured outside git before operator auth readiness."})
    if not agent_id_configured:
        blocking_reasons.append({"code": "missing_agent_id", "message": "WECOM_AGENT_ID must be configured outside git before operator auth readiness."})
    if not redirect_uri_configured:
        blocking_reasons.append(
            {"code": "missing_redirect_uri", "message": "ADMIN_LOGIN_REDIRECT_URI must be configured outside git before auth start readiness."}
        )
    if not _status_is_verified(auth_status, {"verified_302", "observed_302", "expected_302"}):
        blocking_reasons.append(
            {"code": "auth_start_not_verified", "message": "Attach auth start 302 readiness evidence; the diagnostic does not start a real OAuth exchange."}
        )
    if not str(operator_identity_evidence or "").strip():
        blocking_reasons.append({"code": "missing_operator_identity", "message": "Attach redacted operator identity evidence after approved operator auth."})

    signature_invalid = signature_status in {"invalid", "failed", "bad_signature"}
    if signature_status == "not_provided":
        blocking_reasons.append(
            {"code": "missing_callback_signature_evidence", "message": "Attach callback signature verification evidence before claiming callback readiness."}
        )
    elif signature_invalid:
        blocking_reasons.append({"code": "invalid_callback_signature", "message": "Invalid callback signature evidence must not enqueue work."})
    if not str(callback_event_id or "").strip():
        blocking_reasons.append({"code": "missing_callback_event", "message": "Attach redacted callback event id evidence."})
    if not str(inbound_event_id or "").strip():
        blocking_reasons.append({"code": "missing_inbound_event", "message": "Attach inbound/internal event id evidence for the callback."})
    if not str(idempotency_key or "").strip():
        blocking_reasons.append({"code": "missing_idempotency_evidence", "message": "Attach idempotency key or duplicate callback evidence."})
    permission_complete = all(
        str(value or "").strip()
        for value in [permission_scope_evidence, customer_event_visibility, group_ops_permission_evidence, material_permission_evidence]
    )
    if not permission_complete:
        blocking_reasons.append(
            {"code": "missing_permission_scope", "message": "Attach customer, group ops, material, and operator permission scope evidence."}
        )

    auth_ready = bool(
        corp_id_configured
        and agent_id_configured
        and redirect_uri_configured
        and _status_is_verified(auth_status, {"verified_302", "observed_302", "expected_302"})
        and str(operator_identity_evidence or "").strip()
        and permission_complete
        and not signature_invalid
    )
    callback_ready = bool(
        auth_ready
        and signature_status in {"valid", "verified", "passed"}
        and str(callback_event_id or "").strip()
        and str(inbound_event_id or "").strip()
        and str(idempotency_key or "").strip()
    )

    if callback_ready:
        derived_status = "callback_linked"
        blocking_reasons = [
            {
                "code": "callback_linked",
                "message": "Operator auth, signature, callback event, inbound event, idempotency, and permission evidence are attached.",
            }
        ]
    elif auth_ready:
        derived_status = "operator_auth_ready"
        blocking_reasons = [
            {
                "code": "operator_auth_ready",
                "message": "Operator auth readiness and permission evidence are attached; callback linkage still needs gray evidence.",
            }
        ]
    else:
        derived_status = "readiness_only"

    return {
        "evidence_status": "CALLBACK_LINKED_EVIDENCE_ATTACHED"
        if derived_status == "callback_linked"
        else ("OPERATOR_AUTH_READY_EVIDENCE_ATTACHED" if derived_status == "operator_auth_ready" else "READINESS_ONLY"),
        "corp_id_configured": corp_id_configured,
        "agent_id_configured": agent_id_configured,
        "redirect_uri_configured": redirect_uri_configured,
        "redirect_uri_expected": str(redirect_uri_expected or "").strip() or env.get("ADMIN_LOGIN_REDIRECT_URI", "") or "not_provided",
        "auth_start_status": auth_status,
        "callback_missing_code_status": missing_code_status,
        "callback_invalid_state_status": invalid_state_status,
        "operator_identity_evidence": _value_or_not_provided(operator_identity_evidence),
        "token_redacted": True,
        "token_never_logged": True,
        "callback_secret_configured": callback_secret_configured,
        "callback_signature_status": signature_status,
        "callback_event_id": _value_or_not_provided(callback_event_id),
        "inbound_event_id": _value_or_not_provided(inbound_event_id),
        "idempotency_key": _value_or_not_provided(idempotency_key),
        "duplicate_callback_handling": duplicate_status,
        "permission_scope_evidence": _value_or_not_provided(permission_scope_evidence),
        "customer_event_visibility": _value_or_not_provided(customer_event_visibility),
        "group_ops_permission_evidence": _value_or_not_provided(group_ops_permission_evidence),
        "material_permission_evidence": _value_or_not_provided(material_permission_evidence),
        "derived_status": derived_status,
        "retryable": False,
        "operator_action_required": derived_status not in {"callback_linked", "operator_auth_ready"},
        "business_explanation": (
            "WeCom callback evidence is linked and ready for operator review without exposing tokens, secrets, or raw external user ids."
            if derived_status == "callback_linked"
            else (
                "WeCom operator auth readiness is attached; collect callback signature, event, inbound event, and idempotency evidence next."
                if derived_status == "operator_auth_ready"
                else "WeCom auth/callback acceptance remains readiness-only until config, auth start, operator identity, signature, callback, idempotency, and permission evidence are attached."
            )
        ),
        "next_action_label": "Attach final callback evidence report"
        if derived_status == "callback_linked"
        else ("Collect callback gray evidence" if derived_status == "operator_auth_ready" else "Resolve WeCom blocking reasons"),
        "real_external_call_executed": False,
        "production_write_executed": False,
        "callback_enqueue_allowed": derived_status == "callback_linked",
        "blocking_reasons": blocking_reasons,
    }


def _reason_codes(item: dict[str, Any]) -> list[str]:
    return [str(reason.get("code", "")) for reason in item.get("blocking_reasons", []) if reason.get("code")]


def _not_provided(value: Any) -> bool:
    return not str(value or "").strip() or str(value).strip() == "not_provided"


def _closeout_evidence_for_item(item: dict[str, Any]) -> dict[str, Any]:
    scenario = str(item.get("scenario", ""))
    if scenario == "group_ops_gray_send":
        evidence = dict(item.get("operator_evidence") or {})
        missing = [field for field in ["plan_id", "effect_job_id", "attempt_id", "push_center_job_id"] if _not_provided(evidence.get(field))]
        if evidence.get("operator_action_required"):
            missing.append("operator_approval_or_receiver_allowlist")
        return {
            "evidence": evidence,
            "evidence_status": "EVIDENCE_COLLECTED" if not missing and not _reason_codes(item) else evidence.get("evidence_status", "READINESS_ONLY"),
            "derived_status": str(item.get("status") or evidence.get("push_center_status") or "readiness_only"),
            "missing_operator_evidence": missing,
            "next_required_operator_action": ("Attach Push Center reconciliation evidence" if missing else "Operator review of gray-send evidence"),
            "business_explanation": evidence.get("business_explanation", item.get("success_criteria", "")),
        }
    if scenario == "ops_plan_to_broadcast":
        evidence = dict(item.get("e2e_evidence") or {})
        missing = [field for field in ["plan_id", "internal_event_id", "consumer_run_id"] if _not_provided(evidence.get(field))]
        if _not_provided(evidence.get("broadcast_job_id")) and _not_provided(evidence.get("external_effect_job_id")):
            missing.append("broadcast_job_id_or_external_effect_job_id")
        if _not_provided(evidence.get("push_center_job_id")):
            missing.append("push_center_job_id")
        return {
            "evidence": evidence,
            "evidence_status": "EVIDENCE_COLLECTED"
            if evidence.get("derived_status") == "job_linked" and not missing
            else evidence.get("evidence_status", "READINESS_ONLY"),
            "derived_status": evidence.get("derived_status", item.get("status", "readiness_only")),
            "missing_operator_evidence": missing,
            "next_required_operator_action": evidence.get("next_action_label", "Attach ops plan E2E evidence"),
            "business_explanation": evidence.get("business_explanation", item.get("success_criteria", "")),
        }
    if scenario == "external_orders":
        evidence = dict(item.get("external_orders_evidence") or {})
        missing = [
            field
            for field in [
                "order_id",
                "external_order_id",
                "idempotency_key",
                "customer_id",
                "channel_id",
                "source",
                "internal_event_id",
                "admin_order_visibility",
            ]
            if _not_provided(evidence.get(field))
        ]
        return {
            "evidence": evidence,
            "evidence_status": "EVIDENCE_COLLECTED"
            if evidence.get("derived_status") == "order_linked" and not missing
            else evidence.get("evidence_status", "READINESS_ONLY"),
            "derived_status": evidence.get("derived_status", item.get("status", "readiness_only")),
            "missing_operator_evidence": missing,
            "next_required_operator_action": evidence.get("next_action_label", "Attach external order evidence"),
            "business_explanation": evidence.get("business_explanation", item.get("success_criteria", "")),
        }
    if scenario == "wecom_auth":
        evidence = dict(item.get("wecom_evidence") or {})
        missing = [
            field
            for field in [
                "operator_identity_evidence",
                "callback_event_id",
                "inbound_event_id",
                "idempotency_key",
                "permission_scope_evidence",
                "customer_event_visibility",
                "group_ops_permission_evidence",
                "material_permission_evidence",
            ]
            if _not_provided(evidence.get(field))
        ]
        return {
            "evidence": evidence,
            "evidence_status": "EVIDENCE_COLLECTED"
            if evidence.get("derived_status") == "callback_linked" and not missing
            else evidence.get("evidence_status", "READINESS_ONLY"),
            "derived_status": evidence.get("derived_status", item.get("status", "readiness_only")),
            "missing_operator_evidence": missing,
            "next_required_operator_action": evidence.get("next_action_label", "Attach WeCom auth/callback evidence"),
            "business_explanation": evidence.get("business_explanation", item.get("success_criteria", "")),
        }
    return {
        "evidence": {},
        "evidence_status": "READINESS_ONLY",
        "derived_status": str(item.get("status") or "readiness_only"),
        "missing_operator_evidence": ["unsupported_scenario"],
        "next_required_operator_action": "Use one of the core closeout scenarios.",
        "business_explanation": str(item.get("success_criteria") or ""),
    }


def _closeout_readiness_status(
    *,
    item: dict[str, Any],
    evidence_status: str,
    missing_operator_evidence: list[str],
) -> tuple[str, bool]:
    codes = [code for code in _reason_codes(item) if code not in {"order_linked", "operator_auth_ready", "callback_linked"}]
    if codes:
        return "BLOCKED", False
    if missing_operator_evidence:
        return "READINESS_ONLY", False
    if evidence_status == "EVIDENCE_COLLECTED":
        return "EVIDENCE_COLLECTED", False
    return "READINESS_ONLY", False


def _closeout_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {str(item.get("scenario")): item for item in items}
    summary_items: list[dict[str, Any]] = []
    for scenario in CORE_CLOSEOUT_SCENARIOS:
        item = by_name.get(scenario)
        if not item:
            summary_items.append(
                {
                    "scenario": scenario,
                    "readiness_status": "BLOCKED",
                    "evidence_status": "READINESS_ONLY",
                    "derived_status": "missing_scenario_output",
                    "blocking_reasons": [{"code": "missing_scenario_output", "message": "Closeout summary could not find scenario output."}],
                    "missing_operator_evidence": ["scenario_output"],
                    "sensitive_data_redaction_ok": True,
                    "real_external_call_executed": False,
                    "production_write_executed": False,
                    "can_claim_90_plus": False,
                    "next_required_operator_action": "Run the scenario diagnostic and attach evidence.",
                    "business_explanation": "Closeout cannot evaluate this business chain without scenario output.",
                }
            )
            continue
        evidence_info = _closeout_evidence_for_item(item)
        readiness_status, can_claim = _closeout_readiness_status(
            item=item,
            evidence_status=str(evidence_info["evidence_status"]),
            missing_operator_evidence=list(evidence_info["missing_operator_evidence"]),
        )
        summary_items.append(
            {
                "scenario": scenario,
                "readiness_status": readiness_status,
                "evidence_status": evidence_info["evidence_status"],
                "derived_status": evidence_info["derived_status"],
                "blocking_reasons": list(item.get("blocking_reasons") or []),
                "missing_operator_evidence": evidence_info["missing_operator_evidence"],
                "sensitive_data_redaction_ok": True,
                "real_external_call_executed": bool(item.get("real_external_call_executed")),
                "production_write_executed": bool(item.get("production_write_executed")),
                "can_claim_90_plus": can_claim,
                "next_required_operator_action": evidence_info["next_required_operator_action"],
                "business_explanation": evidence_info["business_explanation"],
            }
        )
    all_evidence_collected = all(item["readiness_status"] == "EVIDENCE_COLLECTED" for item in summary_items)
    any_blocked = any(item["readiness_status"] == "BLOCKED" for item in summary_items)
    final_status = "PASS_90_PLUS" if all_evidence_collected else ("BLOCKED" if any_blocked else "READINESS_ONLY")
    if final_status == "PASS_90_PLUS":
        for item in summary_items:
            item["readiness_status"] = "PASS_90_PLUS"
            item["can_claim_90_plus"] = True
    return {
        "closeout_status": final_status,
        "can_claim_90_plus": final_status == "PASS_90_PLUS",
        "claim_rules": {
            "default_pass_90_plus": False,
            "requires_all_core_scenarios": list(CORE_CLOSEOUT_SCENARIOS),
            "requires_no_blocking_reasons": True,
            "requires_complete_operator_evidence": True,
            "requires_sensitive_data_redaction": True,
            "requires_no_real_external_call_from_diagnostic": True,
            "requires_no_production_write_from_diagnostic": True,
        },
        "items": summary_items,
        "next_required_operator_actions": [
            {"scenario": item["scenario"], "action": item["next_required_operator_action"]} for item in summary_items if not item["can_claim_90_plus"]
        ],
    }


def _scenario_payload(
    name: str,
    *,
    execute: bool = False,
    receiver_token: str = "",
    request_token: str = "",
    request_mode: str = "",
    order_no: str = "",
    external_order_id: str = "",
    idempotency_key: str = "",
    customer_id: str = "",
    channel_id: str = "",
    source: str = "",
    admin_order_visibility: str = "",
    plan_id: str = "",
    event_id: str = "",
    effect_job_id: str = "",
    attempt_id: str = "",
    push_center_job_id: str = "",
    approval_event_id: str = "",
    internal_event_id: str = "",
    consumer_run_id: str = "",
    broadcast_job_id: str = "",
    approval_status: str = "",
    consumer_status: str = "",
    duplicate_handling: str = "",
    redirect_uri_expected: str = "",
    auth_start_status: str = "",
    callback_missing_code_status: str = "",
    callback_invalid_state_status: str = "",
    operator_identity_evidence: str = "",
    callback_signature_status: str = "",
    callback_event_id: str = "",
    duplicate_callback_handling: str = "",
    permission_scope_evidence: str = "",
    customer_event_visibility: str = "",
    group_ops_permission_evidence: str = "",
    material_permission_evidence: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(env or os.environ)
    spec = SCENARIOS[name]
    missing = _missing_env(env, list(spec["required_env"]))
    requires_receiver = name in {"group_ops_gray_send", "wecom_callback_gray"}
    if name == "group_ops_gray_send":
        blocking_reasons = _group_ops_blocking_reasons(env, receiver_token=receiver_token)
    else:
        blocking_reasons = _generic_blocking_reasons(missing, receiver_required=requires_receiver, receiver_token=receiver_token)
    execute_allowed = bool(execute and not blocking_reasons)
    unsafe_execute_requested = bool(execute and not execute_allowed)
    status = "blocked" if unsafe_execute_requested else ("ready_for_operator_execute" if execute_allowed else "dry_run_ready")
    payload = {
        "ok": not unsafe_execute_requested,
        "scenario": name,
        "title": spec["title"],
        "capability_owner": spec["capability_owner"],
        "dry_run": not execute_allowed,
        "execute_requested": bool(execute),
        "operator_execute_allowed": execute_allowed,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
        "status": status,
        "routes": list(spec["routes"]),
        "blocking_reasons": blocking_reasons if unsafe_execute_requested else [],
        "required_env": [{"key": key, "configured": _present(env, key), "value": "[redacted]" if _present(env, key) else ""} for key in spec["required_env"]],
        "missing_env": missing,
        "inputs": {
            "receiver_token_configured": bool(receiver_token),
            "receiver_token": "[redacted]" if receiver_token else "",
            "request_token_configured": bool(request_token),
            "request_token": "[redacted]" if request_token else "",
            "request_mode": request_mode,
            "order_no": order_no,
            "external_order_id": external_order_id,
            "idempotency_key": idempotency_key,
            "customer_id": customer_id,
            "channel_id": channel_id,
            "source": source,
            "admin_order_visibility": admin_order_visibility,
            "plan_id": plan_id,
            "event_id": event_id,
            "effect_job_id": effect_job_id,
            "attempt_id": attempt_id,
            "push_center_job_id": push_center_job_id,
            "approval_event_id": approval_event_id,
            "internal_event_id": internal_event_id,
            "consumer_run_id": consumer_run_id,
            "broadcast_job_id": broadcast_job_id,
            "approval_status": approval_status,
            "consumer_status": consumer_status,
            "duplicate_handling": duplicate_handling,
            "redirect_uri_expected": redirect_uri_expected,
            "auth_start_status": auth_start_status,
            "callback_missing_code_status": callback_missing_code_status,
            "callback_invalid_state_status": callback_invalid_state_status,
            "operator_identity_evidence": operator_identity_evidence,
            "callback_signature_status": callback_signature_status,
            "callback_event_id": callback_event_id,
            "duplicate_callback_handling": duplicate_callback_handling,
            "permission_scope_evidence": permission_scope_evidence,
            "customer_event_visibility": customer_event_visibility,
            "group_ops_permission_evidence": group_ops_permission_evidence,
            "material_permission_evidence": material_permission_evidence,
        },
        "redaction_policy": {
            "receiver_token": "redacted",
            "receiver_allowlist": "redacted",
            "token_secret_external_userid": "must_not_be_committed",
        },
        "checks": list(spec["checks"]),
        "success_criteria": spec["success_criteria"],
        "next_action": _next_action(name, unsafe_execute_requested, execute_allowed),
    }
    if name == "group_ops_gray_send":
        payload["operator_evidence"] = _group_ops_evidence(
            plan_id=plan_id,
            event_id=event_id,
            effect_job_id=effect_job_id,
            attempt_id=attempt_id,
            push_center_job_id=push_center_job_id,
            operator_execute_allowed=execute_allowed,
            blocking_reasons=blocking_reasons,
        )
    if name == "ops_plan_to_broadcast":
        evidence = _ops_plan_e2e_evidence(
            plan_id=plan_id,
            approval_event_id=approval_event_id,
            internal_event_id=internal_event_id or event_id,
            consumer_run_id=consumer_run_id,
            broadcast_job_id=broadcast_job_id,
            effect_job_id=effect_job_id,
            push_center_job_id=push_center_job_id,
            approval_status=approval_status,
            consumer_status=consumer_status,
            duplicate_handling=duplicate_handling,
        )
        payload["e2e_evidence"] = evidence
        payload["blocking_reasons"] = list(evidence["blocking_reasons"])
        payload["status"] = evidence["derived_status"]
    if name in {"external_orders", "external_orders_enablement", "external_orders_gray"}:
        evidence = _external_orders_evidence(
            env=env,
            request_token=request_token,
            request_mode=request_mode,
            order_no=order_no,
            external_order_id=external_order_id,
            idempotency_key=idempotency_key,
            customer_id=customer_id,
            channel_id=channel_id,
            source=source,
            internal_event_id=internal_event_id or event_id,
            admin_order_visibility=admin_order_visibility,
        )
        payload["external_orders_evidence"] = evidence
        payload["blocking_reasons"] = list(evidence["blocking_reasons"])
        payload["status"] = evidence["derived_status"]
    if name in {"wecom_auth", "wecom_auth_operator", "wecom_callback_gray"}:
        evidence = _wecom_evidence(
            env=env,
            redirect_uri_expected=redirect_uri_expected,
            auth_start_status=auth_start_status,
            callback_missing_code_status=callback_missing_code_status,
            callback_invalid_state_status=callback_invalid_state_status,
            operator_identity_evidence=operator_identity_evidence,
            callback_signature_status=callback_signature_status,
            callback_event_id=callback_event_id,
            inbound_event_id=internal_event_id or event_id,
            idempotency_key=idempotency_key,
            duplicate_callback_handling=duplicate_callback_handling or duplicate_handling,
            permission_scope_evidence=permission_scope_evidence,
            customer_event_visibility=customer_event_visibility,
            group_ops_permission_evidence=group_ops_permission_evidence,
            material_permission_evidence=material_permission_evidence,
        )
        payload["wecom_evidence"] = evidence
        if not unsafe_execute_requested:
            payload["blocking_reasons"] = list(evidence["blocking_reasons"])
            payload["status"] = evidence["derived_status"]
    return payload


def _next_action(name: str, unsafe_execute_requested: bool, execute_allowed: bool) -> str:
    if unsafe_execute_requested:
        return "Resolve missing approval/env/receiver inputs before any operator execution."
    if execute_allowed:
        return "Run the documented operator-owned gray acceptance steps; this diagnostic script still performs no external call."
    if name == "core_admin_ops":
        return "Close or rebuild #974 from current main before channel admin UX fixes."
    return "Attach this dry-run payload to the next acceptance PR and keep real execution disabled."


def run(
    *,
    scenario: str,
    execute: bool = False,
    receiver_token: str = "",
    request_token: str = "",
    request_mode: str = "",
    order_no: str = "",
    external_order_id: str = "",
    idempotency_key: str = "",
    customer_id: str = "",
    channel_id: str = "",
    source: str = "",
    admin_order_visibility: str = "",
    plan_id: str = "",
    event_id: str = "",
    effect_job_id: str = "",
    attempt_id: str = "",
    push_center_job_id: str = "",
    approval_event_id: str = "",
    internal_event_id: str = "",
    consumer_run_id: str = "",
    broadcast_job_id: str = "",
    approval_status: str = "",
    consumer_status: str = "",
    duplicate_handling: str = "",
    redirect_uri_expected: str = "",
    auth_start_status: str = "",
    callback_missing_code_status: str = "",
    callback_invalid_state_status: str = "",
    operator_identity_evidence: str = "",
    callback_signature_status: str = "",
    callback_event_id: str = "",
    duplicate_callback_handling: str = "",
    permission_scope_evidence: str = "",
    customer_event_visibility: str = "",
    group_ops_permission_evidence: str = "",
    material_permission_evidence: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    names = list(SCENARIOS) if scenario == "all" else [scenario]
    items = [
        _scenario_payload(
            name,
            execute=execute,
            receiver_token=receiver_token,
            request_token=request_token,
            request_mode=request_mode,
            order_no=order_no,
            external_order_id=external_order_id,
            idempotency_key=idempotency_key,
            customer_id=customer_id,
            channel_id=channel_id,
            source=source,
            admin_order_visibility=admin_order_visibility,
            plan_id=plan_id,
            event_id=event_id,
            effect_job_id=effect_job_id,
            attempt_id=attempt_id,
            push_center_job_id=push_center_job_id,
            approval_event_id=approval_event_id,
            internal_event_id=internal_event_id,
            consumer_run_id=consumer_run_id,
            broadcast_job_id=broadcast_job_id,
            approval_status=approval_status,
            consumer_status=consumer_status,
            duplicate_handling=duplicate_handling,
            redirect_uri_expected=redirect_uri_expected,
            auth_start_status=auth_start_status,
            callback_missing_code_status=callback_missing_code_status,
            callback_invalid_state_status=callback_invalid_state_status,
            operator_identity_evidence=operator_identity_evidence,
            callback_signature_status=callback_signature_status,
            callback_event_id=callback_event_id,
            duplicate_callback_handling=duplicate_callback_handling,
            permission_scope_evidence=permission_scope_evidence,
            customer_event_visibility=customer_event_visibility,
            group_ops_permission_evidence=group_ops_permission_evidence,
            material_permission_evidence=material_permission_evidence,
            env=env,
        )
        for name in names
    ]
    payload = {
        "ok": all(item["ok"] for item in items),
        "scenario": scenario,
        "items": items,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
    }
    payload["summary"] = _closeout_summary(items)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run business closure acceptance diagnostics.")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS.keys()], default="all")
    parser.add_argument("--execute", action="store_true", help="Request operator execution readiness; the script still performs no external call.")
    parser.add_argument("--receiver-token", default="")
    parser.add_argument("--request-token", default="")
    parser.add_argument("--request-mode", choices=["dry_run", "no_token", "wrong_token", "valid_token"], default="")
    parser.add_argument("--order-no", default="")
    parser.add_argument("--external-order-id", default="")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--customer-id", default="")
    parser.add_argument("--channel-id", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--admin-order-visibility", default="")
    parser.add_argument("--plan-id", default="")
    parser.add_argument("--event-id", default="")
    parser.add_argument("--effect-job-id", default="")
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--push-center-job-id", default="")
    parser.add_argument("--approval-event-id", default="")
    parser.add_argument("--internal-event-id", default="")
    parser.add_argument("--consumer-run-id", default="")
    parser.add_argument("--broadcast-job-id", default="")
    parser.add_argument("--approval-status", default="")
    parser.add_argument("--consumer-status", default="")
    parser.add_argument("--duplicate-handling", default="")
    parser.add_argument("--redirect-uri-expected", default="")
    parser.add_argument("--auth-start-status", default="")
    parser.add_argument("--callback-missing-code-status", default="")
    parser.add_argument("--callback-invalid-state-status", default="")
    parser.add_argument("--operator-identity-evidence", default="")
    parser.add_argument("--callback-signature-status", default="")
    parser.add_argument("--callback-event-id", default="")
    parser.add_argument("--duplicate-callback-handling", default="")
    parser.add_argument("--permission-scope-evidence", default="")
    parser.add_argument("--customer-event-visibility", default="")
    parser.add_argument("--group-ops-permission-evidence", default="")
    parser.add_argument("--material-permission-evidence", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run(
        scenario=args.scenario,
        execute=bool(args.execute),
        receiver_token=args.receiver_token,
        request_token=args.request_token,
        request_mode=args.request_mode,
        order_no=args.order_no,
        external_order_id=args.external_order_id,
        idempotency_key=args.idempotency_key,
        customer_id=args.customer_id,
        channel_id=args.channel_id,
        source=args.source,
        admin_order_visibility=args.admin_order_visibility,
        plan_id=args.plan_id,
        event_id=args.event_id,
        effect_job_id=args.effect_job_id,
        attempt_id=args.attempt_id,
        push_center_job_id=args.push_center_job_id,
        approval_event_id=args.approval_event_id,
        internal_event_id=args.internal_event_id,
        consumer_run_id=args.consumer_run_id,
        broadcast_job_id=args.broadcast_job_id,
        approval_status=args.approval_status,
        consumer_status=args.consumer_status,
        duplicate_handling=args.duplicate_handling,
        redirect_uri_expected=args.redirect_uri_expected,
        auth_start_status=args.auth_start_status,
        callback_missing_code_status=args.callback_missing_code_status,
        callback_invalid_state_status=args.callback_invalid_state_status,
        operator_identity_evidence=args.operator_identity_evidence,
        callback_signature_status=args.callback_signature_status,
        callback_event_id=args.callback_event_id,
        duplicate_callback_handling=args.duplicate_callback_handling,
        permission_scope_evidence=args.permission_scope_evidence,
        customer_event_visibility=args.customer_event_visibility,
        group_ops_permission_evidence=args.group_ops_permission_evidence,
        material_permission_evidence=args.material_permission_evidence,
    )
    print_json(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
