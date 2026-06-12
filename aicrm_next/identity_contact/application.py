from __future__ import annotations

from aicrm_next.customer_read_model.application import GetCustomerDetailQuery
from aicrm_next.customer_read_model.dto import CustomerDetailRequest
from aicrm_next.integration_gateway.customer_sync_adapters import build_identity_mapping_adapter
from aicrm_next.shared.runtime import production_data_ready
from aicrm_next.shared.typing import JsonDict

from .domain import normalize_identity_request, normalize_mobile_binding_request
from .dto import BindMobileToExternalContactRequest, IdentityResolution, ResolvePersonIdentityRequest
from .repo import FixtureIdentityRepository, IdentityBindingRepository, PostgresIdentityRepository, build_identity_binding_repository


class ResolvePersonIdentityQuery:
    def __init__(
        self,
        repo: FixtureIdentityRepository | None = None,
        identity_adapter=None,
        postgres_repo: PostgresIdentityRepository | None = None,
    ) -> None:
        self._repo = repo or FixtureIdentityRepository()
        self._postgres_repo = postgres_repo or PostgresIdentityRepository()
        self._identity_adapter = identity_adapter or build_identity_mapping_adapter()

    def execute(self, query: ResolvePersonIdentityRequest) -> IdentityResolution | None:
        normalized = normalize_identity_request(query)
        if production_data_ready():
            return self._postgres_repo.resolve(normalized)
        self._identity_adapter.resolve_person_identity(
            external_userid=normalized.external_userid or "",
            openid=normalized.openid or "",
            unionid=normalized.unionid or "",
            mobile=normalized.mobile or "",
        )
        return self._repo.resolve(normalized)

    __call__ = execute


def _empty_binding_status_payload(
    *,
    external_userid: str,
    owner_userid: str = "",
    source_status: str,
) -> JsonDict:
    return {
        "ok": True,
        "is_bound": False,
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "customer_name": "",
        "remark": "",
        "display_name": f"客户 {external_userid[-6:]}",
        "person_id": None,
        "mobile": None,
        "third_party_user_id": None,
        "detail_url": f"/admin/customers/{external_userid}",
        "source_status": source_status,
        "read_model_status": source_status,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "degraded": False,
        "status_code": 200,
    }


def _production_unavailable_payload(external_userid: str, exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "degraded": True,
        "is_bound": False,
        "external_userid": external_userid,
        "owner_userid": "",
        "customer_name": "",
        "remark": "",
        "display_name": "",
        "person_id": None,
        "mobile": None,
        "third_party_user_id": None,
        "detail_url": f"/admin/customers/{external_userid}" if external_userid else "",
        "source_status": "production_unavailable",
        "read_model_status": "unavailable",
        "error_code": "contact_binding_status_unavailable",
        "page_error": str(exc),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "status_code": 503,
    }


def _customer_read_model_binding_status_payload(
    customer: JsonDict,
    *,
    external_userid: str,
    owner_userid: str = "",
    source_status: str = "next_read_model",
) -> JsonDict:
    binding = dict(customer.get("binding") or {})
    identity = dict(customer.get("identity") or {})
    mobile = binding.get("mobile") or identity.get("mobile") or customer.get("mobile")
    is_bound = bool(binding.get("is_bound") or mobile)
    return {
        "ok": True,
        "is_bound": is_bound,
        "external_userid": external_userid,
        "owner_userid": owner_userid or customer.get("owner_userid") or "",
        "customer_name": customer.get("customer_name") or "",
        "remark": customer.get("remark") or "",
        "display_name": customer.get("customer_name")
        or customer.get("remark")
        or f"客户 {external_userid[-6:]}",
        "person_id": identity.get("person_id") or binding.get("person_id"),
        "mobile": mobile,
        "third_party_user_id": binding.get("third_party_user_id") or identity.get("third_party_user_id"),
        "detail_url": customer.get("sidebar_context", {}).get("customer_profile_url")
        or f"/admin/customers/{external_userid}",
        "source_status": source_status,
        "read_model_status": source_status,
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "degraded": False,
        "status_code": 200,
    }


def _identity_binding_status_payload(
    result: IdentityResolution,
    *,
    external_userid: str,
    owner_userid: str = "",
) -> JsonDict:
    return {
        "ok": True,
        "is_bound": bool(result.mobile),
        "external_userid": external_userid,
        "owner_userid": owner_userid or result.owner_userid or "",
        "customer_name": "",
        "remark": "",
        "display_name": f"客户 {external_userid[-6:]}",
        "person_id": result.person_id,
        "mobile": result.mobile,
        "third_party_user_id": None,
        "detail_url": f"/admin/customers/{external_userid}",
        "source_status": "identity_contact",
        "read_model_status": "identity_contact",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "degraded": False,
        "status_code": 200,
    }


class GetSidebarContactBindingStatusQuery:
    def __init__(
        self,
        identity_query: ResolvePersonIdentityQuery | None = None,
        customer_detail_query=None,
    ) -> None:
        self._identity_query = identity_query or ResolvePersonIdentityQuery()
        self._customer_detail_query = customer_detail_query or GetCustomerDetailQuery()

    def execute(self, *, external_userid: str | None = None, owner_userid: str | None = None) -> JsonDict:
        resolved_external_userid = str(external_userid or "").strip()
        resolved_owner_userid = str(owner_userid or "").strip()
        if not resolved_external_userid:
            return {
                "ok": False,
                "error": "external_userid is required",
                "source_status": "input_error",
                "read_model_status": "input_error",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "degraded": False,
                "status_code": 400,
            }

        if production_data_ready():
            try:
                payload = self._customer_detail_query(CustomerDetailRequest(external_userid=resolved_external_userid))
                if not payload.get("ok"):
                    raise RuntimeError(str(payload.get("page_error") or payload.get("error_code") or "customer detail unavailable"))
                customer = dict(payload.get("customer") or {})
            except Exception as exc:
                return _production_unavailable_payload(resolved_external_userid, exc)
            return _customer_read_model_binding_status_payload(
                customer,
                external_userid=resolved_external_userid,
                owner_userid=resolved_owner_userid,
                source_status=str(payload.get("source_status") or "next_read_model"),
            )

        result = self._identity_query(
            ResolvePersonIdentityRequest(
                external_userid=resolved_external_userid,
            )
        )
        if result is None:
            return _empty_binding_status_payload(
                external_userid=resolved_external_userid,
                owner_userid=resolved_owner_userid,
                source_status="identity_contact",
            )
        return _identity_binding_status_payload(
            result,
            external_userid=resolved_external_userid,
            owner_userid=resolved_owner_userid,
        )

    __call__ = execute


class UpsertIdentityMappingCommand:
    def __init__(self, identity_adapter=None) -> None:
        self._identity_adapter = identity_adapter or build_identity_mapping_adapter()

    def execute(
        self,
        *,
        external_userid: str = "",
        openid: str = "",
        unionid: str = "",
        mobile: str = "",
        person_id: str = "",
        corp_id: str = "",
        idempotency_key: str | None = None,
    ) -> JsonDict:
        return self._identity_adapter.upsert_identity_mapping(
            external_userid=external_userid,
            openid=openid,
            unionid=unionid,
            mobile=mobile,
            person_id=person_id,
            corp_id=corp_id,
            idempotency_key=idempotency_key,
        )

    __call__ = execute


class BindMobileToExternalContactCommand:
    def __init__(self, repo: IdentityBindingRepository | None = None) -> None:
        self._repo = repo or build_identity_binding_repository()

    def execute(self, request: BindMobileToExternalContactRequest) -> JsonDict:
        normalized = normalize_mobile_binding_request(request)
        return self._repo.bind_mobile_to_external_contact(
            external_userid=normalized.external_userid,
            mobile=normalized.mobile,
            owner_userid=normalized.owner_userid or "",
            bind_by_userid=normalized.bind_by_userid or "",
            customer_name=normalized.customer_name or "",
            force_rebind=normalized.force_rebind,
        )

    __call__ = execute


class LinkOpenidUnionidExternalUseridCommand:
    def __init__(self, identity_adapter=None) -> None:
        self._identity_adapter = identity_adapter or build_identity_mapping_adapter()

    def execute(
        self,
        *,
        external_userid: str,
        openid: str = "",
        unionid: str = "",
        corp_id: str = "",
        idempotency_key: str | None = None,
    ) -> JsonDict:
        return self._identity_adapter.link_openid_unionid_external_userid(
            external_userid=external_userid,
            openid=openid,
            unionid=unionid,
            corp_id=corp_id,
            idempotency_key=idempotency_key,
        )

    __call__ = execute
