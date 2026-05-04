from __future__ import annotations

from flask import jsonify, request

from ..application.automation_engine.commands import (
    ApplyActivationWebhookCommand,
    RetryOutboundWebhookDeliveryCommand,
    RunDueOutboundWebhookRetriesCommand,
)
from ..application.automation_engine.dto import (
    ActivationWebhookCommandDTO,
    OutboundWebhookListQueryDTO,
    OutboundWebhookRetryBatchCommandDTO,
    OutboundWebhookRetryCommandDTO,
    SignupConversionBatchDetailQueryDTO,
    SignupConversionBatchListQueryDTO,
)
from ..application.automation_engine.queries import (
    GetSignupConversionBatchQuery,
    ListOutboundWebhookDeliveriesQuery,
    ListSignupConversionBatchesQuery,
)
from ..application.customer_read_model import CustomerChatContextQueryDTO, GetCustomerChatContextQuery
from ..application.customer_read_model.dto import InternalAuthQueryDTO
from ..application.platform_foundation import AuthorizeInternalRequestQuery


def _candidate_context(external_userid: str) -> dict[str, object]:
    payload = GetCustomerChatContextQuery()(
        CustomerChatContextQueryDTO(
            external_userid=external_userid,
            recent_message_limit=20,
            timeline_limit=20,
        )
    )
    return {
        "external_userid": str(payload.get("external_userid") or external_userid).strip() or external_userid,
        "customer": payload.get("customer"),
        "recent_messages": list(payload.get("recent_messages") or []),
        "timeline": dict(payload.get("timeline") or {}),
        "recent_timeline_events": list(payload.get("recent_timeline_events") or []),
        "source_status": str(payload.get("source_status") or "live"),
        "degraded": bool(payload.get("degraded")),
        "warnings": list(payload.get("warnings") or []),
    }


def _authorize_internal_request(
    *,
    token_keys: tuple[str, ...] = (),
    legacy_header_names: tuple[str, ...] = (),
):
    return AuthorizeInternalRequestQuery()(
        InternalAuthQueryDTO(
            token_keys=token_keys,
            legacy_header_names=legacy_header_names,
        )
    )


def signup_conversion_batch_list():
    limit = request.args.get("limit", 20)
    cursor = str(request.args.get("cursor", "") or "")
    try:
        payload = ListSignupConversionBatchesQuery()(
            SignupConversionBatchListQueryDTO(limit=int(limit), cursor=cursor)
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "automation_batches": payload})


def signup_conversion_batch_detail(batch_id: int):
    payload = GetSignupConversionBatchQuery()(SignupConversionBatchDetailQueryDTO(batch_id=int(batch_id)))
    if not payload:
        return jsonify({"ok": False, "error": "batch not found"}), 404
    candidates = []
    for item in payload.get("candidates") or []:
        candidate = dict(item)
        external_userid = str(candidate.get("external_userid") or "").strip()
        candidate["customer_context"] = _candidate_context(external_userid) if external_userid else {}
        candidates.append(candidate)
    payload["candidates"] = candidates
    return jsonify({"ok": True, "automation_batch": payload})

def activation_webhook():
    auth_failure = _authorize_internal_request(
        token_keys=("AUTOMATION_ACTIVATION_WEBHOOK_TOKEN",),
        legacy_header_names=("X-Automation-Token",),
    )
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    mobile = str(payload.get("mobile") or "").strip()
    activated_at = str(payload.get("activated_at") or payload.get("last_activation_at") or "").strip()
    operator = str(payload.get("operator") or "").strip() or "activation_webhook"
    source = str(payload.get("source") or "").strip() or "activation_webhook"
    try:
        result = ApplyActivationWebhookCommand()(
            ActivationWebhookCommandDTO(
                mobile=mobile,
                activated_at=activated_at,
                operator=operator,
                source=source,
            )
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def webhook_delivery_list():
    event_type = str(request.args.get("event_type", "") or "")
    status = str(request.args.get("status", "") or "")
    limit = request.args.get("limit", 50)
    try:
        payload = ListOutboundWebhookDeliveriesQuery()(
            OutboundWebhookListQueryDTO(
                event_type=event_type,
                status=status,
                limit=int(limit),
            )
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "deliveries": payload})


def webhook_delivery_retry(delivery_id: int):
    auth_failure = _authorize_internal_request()
    if auth_failure is not None:
        return auth_failure
    try:
        payload = RetryOutboundWebhookDeliveryCommand()(
            OutboundWebhookRetryCommandDTO(delivery_id=int(delivery_id))
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "delivery": payload})


def webhook_delivery_retry_due():
    auth_failure = _authorize_internal_request()
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    limit = payload.get("limit", request.args.get("limit", 20))
    try:
        result = RunDueOutboundWebhookRetriesCommand()(
            OutboundWebhookRetryBatchCommandDTO(limit=int(limit))
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def register_routes(bp):
    bp.route("/api/customers/automation/signup-conversion/batches", methods=["GET"])(signup_conversion_batch_list)
    bp.route("/api/customers/automation/signup-conversion/batches/<int:batch_id>", methods=["GET"])(
        signup_conversion_batch_detail
    )
    bp.route("/api/customers/automation/activation-webhook", methods=["POST"])(activation_webhook)
    bp.route("/api/customers/automation/webhook-deliveries", methods=["GET"])(webhook_delivery_list)
    bp.route("/api/customers/automation/webhook-deliveries/<int:delivery_id>/retry", methods=["POST"])(webhook_delivery_retry)
    bp.route("/api/customers/automation/webhook-deliveries/retry-due", methods=["POST"])(webhook_delivery_retry_due)
