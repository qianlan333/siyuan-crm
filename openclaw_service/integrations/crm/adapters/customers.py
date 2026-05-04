from __future__ import annotations

from typing import Any

from ..client import CrmApiClient
from ..errors import CrmBusinessError, CrmHttpError, CrmMappingError, CrmTransportError
from ..models import Customer
from .contacts import ContactsAdapter, map_contact_to_customer


CRM_READ_ERRORS = (CrmTransportError, CrmHttpError, CrmBusinessError, CrmMappingError)


class CustomersAdapter:
    def __init__(self, client: CrmApiClient) -> None:
        self.client = client
        self.contacts = ContactsAdapter(client)

    def list_customers(self, filters: dict[str, Any] | None = None) -> list[Customer]:
        if self.client.config.prefer_customer_endpoints:
            try:
                payload = self.client.get("/api/customers", params=filters or {})
                return [map_contact_to_customer(item) for item in self._extract_items(payload)]
            except CRM_READ_ERRORS:
                pass
        try:
            return self.contacts.list_contacts(filters)
        except CRM_READ_ERRORS:
            return []

    def get_customer(self, external_userid: str) -> Customer:
        if self.client.config.prefer_customer_endpoints:
            try:
                payload = self.client.get(f"/api/customers/{external_userid}")
                return map_contact_to_customer(self._extract_customer(payload))
            except CRM_READ_ERRORS as exc:
                fallback_error = exc
            else:
                fallback_error = None
        else:
            fallback_error = None

        try:
            return self.contacts.get_contact(external_userid)
        except CRM_READ_ERRORS as exc:
            reason = str(fallback_error or exc)
            return Customer(
                external_userid=external_userid,
                status="degraded",
                raw={"degraded": True, "reason": reason},
            )

    @staticmethod
    def _extract_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            customers_value = payload.get("customers")
            items_value = payload.get("items")
            if isinstance(customers_value, list):
                return [item for item in customers_value if isinstance(item, dict)]
            if isinstance(items_value, list):
                return [item for item in items_value if isinstance(item, dict)]
            data_value = payload.get("data")
            if isinstance(data_value, list):
                return [item for item in data_value if isinstance(item, dict)]
        raise CrmMappingError("customer list payload must contain a list", response_payload=payload)

    @staticmethod
    def _extract_customer(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise CrmMappingError("customer detail payload must be a JSON object", response_payload=payload)
        customer_value = payload.get("customer")
        if isinstance(customer_value, dict):
            return customer_value
        return payload
