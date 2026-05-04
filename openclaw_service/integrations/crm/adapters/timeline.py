from __future__ import annotations

from typing import Any

from ..client import CrmApiClient
from ..errors import CrmBusinessError, CrmHttpError, CrmMappingError, CrmTransportError
from ..models import TimelineEvent
from .messages import MessagesAdapter


CRM_READ_ERRORS = (CrmTransportError, CrmHttpError, CrmBusinessError, CrmMappingError)


class TimelineAdapter:
    def __init__(self, client: CrmApiClient) -> None:
        self.client = client
        self.messages = MessagesAdapter(client)

    def get_customer_timeline(
        self,
        external_userid: str,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        cursor: str | None = None,
    ) -> list[TimelineEvent]:
        if self.client.config.prefer_timeline_endpoint:
            try:
                params: dict[str, Any] = {"limit": limit, "offset": offset}
                if cursor:
                    params["cursor"] = cursor
                if event_type:
                    params["event_type"] = event_type
                payload = self.client.get(f"/api/customers/{external_userid}/timeline", params=params)
                return self._map_timeline_payload(external_userid, payload)
            except CRM_READ_ERRORS:
                pass

        try:
            messages = self.messages.get_recent_messages(external_userid, limit=limit)
            return [self._map_legacy_message_to_event(external_userid, item) for item in messages]
        except CRM_READ_ERRORS as exc:
            return [
                TimelineEvent(
                    event_id=f"degraded:{external_userid}",
                    external_userid=external_userid,
                    event_type="degraded",
                    summary="CRM timeline temporarily unavailable",
                    payload={"reason": str(exc)},
                    source="degraded",
                )
            ]

    def _map_timeline_payload(self, external_userid: str, payload: Any) -> list[TimelineEvent]:
        items: list[dict[str, Any]]
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            timeline_payload = payload.get("timeline")
            if isinstance(timeline_payload, dict):
                raw_items = timeline_payload.get("items") or timeline_payload.get("events") or []
            else:
                raw_items = payload.get("items") or payload.get("events") or payload.get("data") or []
            if not isinstance(raw_items, list):
                raise CrmMappingError("timeline payload must contain a list", response_payload=payload)
            items = [item for item in raw_items if isinstance(item, dict)]
        else:
            raise CrmMappingError("timeline payload must be a list or object", response_payload=payload)
        return [self._map_event(external_userid, item) for item in items]

    @staticmethod
    def _map_event(external_userid: str, payload: dict[str, Any]) -> TimelineEvent:
        event_id = str(payload.get("event_id") or payload.get("id") or "").strip()
        if not event_id:
            event_id = f"{payload.get('event_type') or 'event'}:{payload.get('occurred_at') or payload.get('send_time') or ''}"
        return TimelineEvent(
            event_id=event_id,
            external_userid=str(payload.get("external_userid") or external_userid).strip(),
            event_type=str(payload.get("event_type") or payload.get("type") or "event").strip(),
            occurred_at=str(payload.get("occurred_at") or payload.get("send_time") or payload.get("created_at") or "").strip(),
            summary=str(payload.get("summary") or payload.get("content") or payload.get("title") or "").strip(),
            payload=payload,
            source=str(payload.get("source") or "crm").strip(),
        )

    @staticmethod
    def _map_legacy_message_to_event(external_userid: str, payload: dict[str, Any]) -> TimelineEvent:
        message_id = str(payload.get("msgid") or payload.get("id") or "").strip()
        occurred_at = str(payload.get("send_time") or payload.get("created_at") or "").strip()
        return TimelineEvent(
            event_id=message_id or f"message:{occurred_at}",
            external_userid=external_userid,
            event_type="message",
            occurred_at=occurred_at,
            summary=str(payload.get("content") or "").strip(),
            payload=payload,
            source="legacy_messages",
        )
