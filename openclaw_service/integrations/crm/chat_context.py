from __future__ import annotations

from typing import Any

from .adapters.customers import CustomersAdapter
from .adapters.messages import MessagesAdapter
from .adapters.timeline import TimelineAdapter
from .errors import CrmBusinessError, CrmHttpError, CrmMappingError, CrmTransportError
from .models import Customer, TimelineEvent

CRM_READ_ERRORS = (CrmTransportError, CrmHttpError, CrmBusinessError, CrmMappingError)


def build_customer_chat_context(
    external_userid: str,
    *,
    customers: CustomersAdapter,
    messages: MessagesAdapter,
    timeline: TimelineAdapter,
    recent_message_limit: int = 20,
    timeline_limit: int = 20,
) -> dict[str, Any]:
    warnings: list[str] = []
    degraded = False

    customer_obj: Customer | None
    recent_messages: list[dict[str, Any]] = []
    timeline_events: list[TimelineEvent] = []

    try:
        customer_obj = customers.get_customer(external_userid)
        if customer_obj.status == "degraded":
            degraded = True
            warnings.append("customer detail degraded")
    except CRM_READ_ERRORS as exc:
        degraded = True
        customer_obj = None
        warnings.append(f"customer unavailable: {exc}")

    try:
        recent_messages = messages.get_recent_messages(external_userid, limit=recent_message_limit)
    except CRM_READ_ERRORS as exc:
        degraded = True
        warnings.append(f"recent messages unavailable: {exc}")

    try:
        timeline_events = timeline.get_customer_timeline(external_userid, limit=timeline_limit)
        if timeline_events and any(event.source == "degraded" for event in timeline_events):
            degraded = True
            warnings.append("timeline degraded")
        elif timeline_events and any(event.source != "crm" for event in timeline_events):
            degraded = True
            warnings.append("timeline fallback in use")
    except CRM_READ_ERRORS as exc:
        degraded = True
        warnings.append(f"timeline unavailable: {exc}")

    if customer_obj is None and not recent_messages:
        source_status = "degraded"
    elif degraded:
        source_status = "fallback"
    else:
        source_status = "live"

    return {
        "external_userid": external_userid,
        "customer": customer_obj.to_dict() if customer_obj else None,
        "recent_messages": recent_messages,
        "recent_timeline_events": [event.to_dict() for event in timeline_events],
        "source_status": source_status,
        "degraded": degraded,
        "warnings": warnings,
    }
