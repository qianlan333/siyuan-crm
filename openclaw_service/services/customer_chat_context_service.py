from __future__ import annotations

from openclaw_service.integrations.crm.adapters.customers import CustomersAdapter
from openclaw_service.integrations.crm.adapters.messages import MessagesAdapter
from openclaw_service.integrations.crm.adapters.timeline import TimelineAdapter
from openclaw_service.integrations.crm.chat_context import build_customer_chat_context
from openclaw_service.integrations.crm.client import CrmApiClient
from openclaw_service.integrations.crm.config import CrmApiConfig


def get_customer_chat_context(
    external_userid: str,
    *,
    recent_message_limit: int = 20,
    timeline_limit: int = 20,
) -> dict:
    config = CrmApiConfig.from_env()
    client = CrmApiClient(config)
    return build_customer_chat_context(
        external_userid,
        customers=CustomersAdapter(client),
        messages=MessagesAdapter(client),
        timeline=TimelineAdapter(client),
        recent_message_limit=recent_message_limit,
        timeline_limit=timeline_limit,
    )
