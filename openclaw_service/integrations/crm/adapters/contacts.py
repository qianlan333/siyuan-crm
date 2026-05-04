from __future__ import annotations

from typing import Any

from ..client import CrmApiClient
from ..errors import CrmMappingError
from ..models import Customer


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _extract_tags(payload: dict[str, Any]) -> list[str]:
    raw_tags = payload.get("tags") or payload.get("tag_names") or payload.get("contact_tags") or []
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, str) and item.strip():
                tags.append(item.strip())
            elif isinstance(item, dict):
                tag_name = str(item.get("tag_name") or item.get("name") or item.get("label") or "").strip()
                if tag_name:
                    tags.append(tag_name)
    return tags


def map_contact_to_customer(payload: dict[str, Any]) -> Customer:
    external_userid = str(payload.get("external_userid") or "").strip()
    if not external_userid:
        raise CrmMappingError("missing external_userid when mapping CRM customer", response_payload=payload)

    binding = payload.get("binding") if isinstance(payload.get("binding"), dict) else {}
    status = str(payload.get("status") or payload.get("signup_status") or "active").strip()
    return Customer(
        external_userid=external_userid,
        name=str(
            payload.get("name")
            or payload.get("customer_name")
            or payload.get("display_name")
            or ""
        ).strip(),
        owner_userid=str(payload.get("owner_userid") or "").strip(),
        remark=str(payload.get("remark") or "").strip(),
        description=str(payload.get("description") or "").strip(),
        tags=_extract_tags(payload),
        status=status,
        is_bound=_coerce_bool(payload.get("is_bound") or binding.get("is_bound") or binding.get("person_id")),
        last_message_at=str(payload.get("last_message_at") or payload.get("updated_at") or "").strip(),
        raw=payload,
    )


class ContactsAdapter:
    def __init__(self, client: CrmApiClient) -> None:
        self.client = client

    def list_contacts(self, filters: dict[str, Any] | None = None) -> list[Customer]:
        payload = self.client.get("/api/contacts", params=filters or {})
        items = self._extract_items(payload, keys=("items", "contacts", "data"))
        return [map_contact_to_customer(item) for item in items]

    def get_contact(self, external_userid: str) -> Customer:
        payload = self.client.get(f"/api/contacts/{external_userid}")
        if not isinstance(payload, dict):
            raise CrmMappingError("contact detail payload must be a JSON object", response_payload=payload)
        return map_contact_to_customer(payload)

    @staticmethod
    def _extract_items(payload: Any, *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise CrmMappingError("contact list payload must contain a list", response_payload=payload)
