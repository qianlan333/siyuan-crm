from __future__ import annotations

from copy import deepcopy
from typing import Any

from aicrm_next.customer_read_model.repo import FixtureCustomerReadRepository
from aicrm_next.platform_foundation.command_bus.models import utcnow_iso
from aicrm_next.shared.typing import JsonDict

from .models import SidebarWriteProjection


class SidebarWriteRepository:
    def __init__(self) -> None:
        fixture = FixtureCustomerReadRepository()
        self._customers: dict[str, JsonDict] = {
            str(item.get("external_userid") or ""): deepcopy(item)
            for item in fixture.list_customers()
            if str(item.get("external_userid") or "").strip()
        }
        self._writes: list[SidebarWriteProjection] = []

    def get_customer(self, external_userid: str) -> JsonDict | None:
        customer = self._customers.get(external_userid)
        return deepcopy(customer) if customer else None

    def list_writes(self) -> list[SidebarWriteProjection]:
        return list(self._writes)

    def bind_mobile(self, *, command_id: str, external_userid: str, mobile: str) -> JsonDict:
        return self._update_customer(
            command_id=command_id,
            external_userid=external_userid,
            write_type="binding_update",
            changes={"mobile": mobile, "binding": {"is_bound": True, "mobile": mobile, "binding_status": "bound"}},
        )

    def upsert_lead_pool_class_term(
        self,
        *,
        command_id: str,
        external_userid: str,
        class_term: str,
        status: str,
    ) -> JsonDict:
        return self._update_nested_status(
            command_id=command_id,
            external_userid=external_userid,
            write_type="lead_pool_local_status",
            status_changes={"class_term": class_term, "lead_pool_status": status},
        )

    def mark_signup_tag(
        self,
        *,
        command_id: str,
        external_userid: str,
        tag_id: str,
        tag_name: str,
        marked: bool,
        source: str,
    ) -> JsonDict:
        customer = self._require_customer(external_userid)
        tags = list(customer.get("tags") or [])
        if marked and tag_name and tag_name not in tags:
            tags.append(tag_name)
        if not marked and tag_name in tags:
            tags.remove(tag_name)
        return self._update_nested_status(
            command_id=command_id,
            external_userid=external_userid,
            write_type="signup_tag_local_marker",
            status_changes={
                "signup_tag_id": tag_id,
                "signup_label_name": tag_name,
                "signup_tag_marked": marked,
                "signup_tag_source": source,
            },
            top_level_changes={"tags": tags},
        )

    def set_followup_segment(self, *, command_id: str, external_userid: str, segment: str) -> JsonDict:
        customer = self._require_customer(external_userid)
        summary = dict(customer.get("marketing_summary") or {})
        summary["value_segment"] = segment
        profile = dict(customer.get("marketing_profile") or {})
        profile["followup_segment"] = segment
        return self._update_customer(
            command_id=command_id,
            external_userid=external_userid,
            write_type="marketing_status_local_marker",
            changes={"marketing_summary": summary, "marketing_profile": profile},
        )

    def mark_enrolled(self, *, command_id: str, external_userid: str, enrolled: bool) -> JsonDict:
        customer = self._require_customer(external_userid)
        summary = dict(customer.get("marketing_summary") or {})
        summary["enrolled"] = enrolled
        summary["main_stage"] = "converted" if enrolled else summary.get("main_stage") or "trial"
        return self._update_customer(
            command_id=command_id,
            external_userid=external_userid,
            write_type="marketing_status_local_marker",
            changes={"marketing_summary": summary},
        )

    def update_profile(
        self,
        *,
        command_id: str,
        external_userid: str,
        remark: str,
        description: str,
        display_name: str,
    ) -> JsonDict:
        customer = self._require_customer(external_userid)
        changes: dict[str, Any] = {}
        contact = dict(customer.get("contact") or {})
        if remark:
            changes["remark"] = remark
            contact["remark"] = remark
        if description:
            changes["description"] = description
            contact["description"] = description
        if display_name:
            changes["customer_name"] = display_name
            contact["name"] = display_name
        if contact:
            changes["contact"] = contact
        return self._update_customer(
            command_id=command_id,
            external_userid=external_userid,
            write_type="profile_update",
            changes=changes,
        )

    def record_material_send_plan(self, *, command_id: str, external_userid: str, material_id: str) -> JsonDict:
        return self._update_customer(
            command_id=command_id,
            external_userid=external_userid,
            write_type="material_send_planned",
            changes={"last_material_send_plan": {"material_id": material_id}},
        )

    def _require_customer(self, external_userid: str) -> JsonDict:
        customer = self._customers.get(external_userid)
        if not customer:
            raise KeyError("customer not found")
        return customer

    def _update_nested_status(
        self,
        *,
        command_id: str,
        external_userid: str,
        write_type: str,
        status_changes: dict[str, Any],
        top_level_changes: dict[str, Any] | None = None,
    ) -> JsonDict:
        customer = self._require_customer(external_userid)
        class_user_status = dict(customer.get("class_user_status") or {})
        class_user_status.update(status_changes)
        return self._update_customer(
            command_id=command_id,
            external_userid=external_userid,
            write_type=write_type,
            changes={"class_user_status": class_user_status, **(top_level_changes or {})},
        )

    def _update_customer(
        self,
        *,
        command_id: str,
        external_userid: str,
        write_type: str,
        changes: dict[str, Any],
    ) -> JsonDict:
        customer = self._require_customer(external_userid)
        now = utcnow_iso()
        for key, value in changes.items():
            customer[key] = deepcopy(value)
        customer["updated_at"] = now
        self._writes.append(
            SidebarWriteProjection(
                command_id=command_id,
                external_userid=external_userid,
                write_type=write_type,
                payload=deepcopy(changes),
                updated_at=now,
            )
        )
        return {"external_userid": external_userid, "write_type": write_type, "updated_at": now, "changes": deepcopy(changes)}
