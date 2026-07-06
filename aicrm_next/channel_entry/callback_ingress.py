from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.webhook_inbox import WebhookInboxRepository

from .application import decrypt_callback_body
from .inbox import ingest_wecom_callback


class WeComCallbackIngressValidationError(ValueError):
    pass


def ingest_wecom_external_contact_callback(
    *,
    query: dict[str, str],
    headers: dict[str, Any],
    body: bytes,
    route: str,
    repository: WebhookInboxRepository | None = None,
) -> dict[str, Any]:
    try:
        event_data, plain_xml = decrypt_callback_body(query=query, body=body)
    except Exception as exc:
        raise WeComCallbackIngressValidationError(str(exc)) from exc
    return ingest_wecom_callback(
        query=query,
        headers=headers,
        body=body,
        event_data=event_data,
        plain_xml=plain_xml,
        route=route,
        repository=repository,
        process_time_sensitive=True,
    )
