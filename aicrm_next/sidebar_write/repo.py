from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from aicrm_next.customer_read_model.repo import FixtureCustomerReadRepository
from aicrm_next.platform_foundation.command_bus.models import utcnow_iso
from aicrm_next.shared.repository_provider import RepositoryProviderError
from aicrm_next.shared.runtime import raw_database_url
from aicrm_next.shared.typing import JsonDict

from .models import SidebarWriteProjection


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def normalize_mobile(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or "").strip())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if not re.fullmatch(r"1\d{10}", digits):
        raise ValueError("mobile must be a valid mainland China mobile number")
    return digits


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


class PostgresSidebarWriteRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(str(database_url or raw_database_url()).strip())
        if not self._database_url:
            raise RepositoryProviderError("sidebar_write production repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RepositoryProviderError(f"sidebar_write production repository unavailable: {exc}") from exc

    def bind_mobile(
        self,
        *,
        command_id: str,
        external_userid: str,
        mobile: str,
        owner_userid: str = "",
        bind_by_userid: str = "",
        force_rebind: bool = False,
    ) -> JsonDict:
        normalized_external_userid = str(external_userid or "").strip()
        normalized_mobile = normalize_mobile(mobile)
        if not normalized_external_userid:
            raise ValueError("external_userid is required")

        with self._connect() as conn:
            identity = self._identity_row(conn, normalized_external_userid)
            normalized_owner_userid = str(owner_userid or "").strip() or str((identity or {}).get("primary_owner_userid") or "").strip()
            normalized_bind_by_userid = str(bind_by_userid or "").strip() or normalized_owner_userid or "sidebar_bind"
            identity_owner_userid = str((identity or {}).get("primary_owner_userid") or "").strip()
            if identity and str(owner_userid or "").strip() and identity_owner_userid and str(owner_userid or "").strip() != identity_owner_userid:
                raise KeyError("customer not found")

            if not identity:
                resolution = self._enqueue_identity_resolution(
                    conn,
                    command_id=command_id,
                    external_userid=normalized_external_userid,
                    mobile=normalized_mobile,
                    owner_userid=normalized_owner_userid,
                    bind_by_userid=normalized_bind_by_userid,
                )
                conn.commit()
                return {
                    "external_userid": normalized_external_userid,
                    "write_type": "identity_pending",
                    "write_model_status": "pending_identity",
                    "updated_at": "",
                    "changes": {},
                    "binding": {},
                    "identity_resolution": resolution,
                }

            existing_mobile = str(identity.get("mobile") or "").strip()
            if existing_mobile == normalized_mobile:
                binding = self._binding_response(identity, owner_userid=normalized_owner_userid)
                return {
                    "external_userid": normalized_external_userid,
                    "unionid": str(identity.get("unionid") or "").strip(),
                    "write_type": "binding_noop",
                    "write_model_status": "updated",
                    "updated_at": str(identity.get("updated_at") or ""),
                    "changes": {},
                    "binding": binding,
                    "lead_pool_merge": {"ok": True, "merge_applied": False, "action_type": "customer_mobile_bound_event"},
                }
            if existing_mobile and existing_mobile != normalized_mobile and not force_rebind:
                raise ValueError("unionid already bound to another mobile")

            updated = conn.execute(
                """
                UPDATE crm_user_identity
                SET mobile = %s,
                    mobile_normalized = %s,
                    mobile_verified = TRUE,
                    mobile_source = 'sidebar_bind',
                    primary_owner_userid = COALESCE(NULLIF(%s, ''), primary_owner_userid),
                    profile_json = profile_json || jsonb_build_object(
                        'sidebar_bind_by_userid', %s,
                        'sidebar_external_userid', %s
                    ),
                    last_seen_at = NOW(),
                    updated_at = NOW()
                WHERE unionid = %s
                RETURNING
                    unionid,
                    primary_external_userid,
                    external_userids_json,
                    mobile,
                    mobile_normalized,
                    mobile_source,
                    primary_owner_userid,
                    customer_name,
                    remark,
                    created_at,
                    updated_at
                """,
                (
                    normalized_mobile,
                    normalized_mobile,
                    normalized_owner_userid,
                    normalized_bind_by_userid,
                    normalized_external_userid,
                    identity["unionid"],
                ),
            ).fetchone()
            if not updated:
                raise RuntimeError("crm_user_identity mobile bind failed")
            conn.commit()

            binding = self._binding_response(dict(updated), owner_userid=normalized_owner_userid)
            return {
                "external_userid": normalized_external_userid,
                "unionid": str(updated.get("unionid") or "").strip(),
                "write_type": "binding_update",
                "write_model_status": "updated",
                "updated_at": str(updated.get("updated_at") or ""),
                "changes": {
                    "mobile": normalized_mobile,
                    "binding": {
                        "is_bound": True,
                        "mobile": normalized_mobile,
                        "binding_status": "bound",
                        "unionid": str(updated.get("unionid") or "").strip(),
                    },
                },
                "binding": binding,
                "lead_pool_merge": {"ok": True, "merge_applied": False, "action_type": "customer_mobile_bound_event"},
            }

    def _identity_row(self, conn, external_userid: str) -> JsonDict | None:
        row = conn.execute(
            """
            SELECT
                unionid,
                primary_external_userid,
                external_userids_json,
                mobile,
                mobile_normalized,
                mobile_source,
                primary_owner_userid,
                customer_name,
                remark,
                created_at,
                updated_at
            FROM crm_user_identity
            WHERE primary_external_userid = %s
                   OR jsonb_exists(external_userids_json, %s)
            ORDER BY CASE WHEN primary_external_userid = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (external_userid, external_userid, external_userid),
        ).fetchone()
        return dict(row) if row else None

    def _enqueue_identity_resolution(
        self,
        conn,
        *,
        command_id: str,
        external_userid: str,
        mobile: str,
        owner_userid: str,
        bind_by_userid: str,
    ) -> JsonDict:
        source_key = f"sidebar_bind_mobile:{external_userid}:{command_id}"
        conn.execute(
            """
            INSERT INTO crm_user_identity_resolution_queue (
                source_type,
                source_key,
                external_userid,
                mobile,
                payload_json,
                reason,
                status,
                next_attempt_at,
                first_seen_at,
                last_seen_at,
                created_at,
                updated_at
            )
            VALUES ('sidebar_bind_mobile', %s, %s, %s, CAST(%s AS jsonb), 'missing_unionid', 'pending', NOW(), NOW(), NOW(), NOW(), NOW())
            ON CONFLICT (source_type, source_key) WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
            DO UPDATE SET
                external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                mobile = COALESCE(NULLIF(EXCLUDED.mobile, ''), crm_user_identity_resolution_queue.mobile),
                payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                reason = EXCLUDED.reason,
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            (
                source_key,
                external_userid,
                mobile,
                json.dumps(
                    {
                        "external_userid": external_userid,
                        "mobile": mobile,
                        "owner_userid": owner_userid,
                        "bind_by_userid": bind_by_userid,
                        "source": "sidebar_bind_mobile",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            ),
        )
        return {"status": "pending", "reason": "identity_pending_unionid", "source_key": source_key}

    def _binding_response(self, row: JsonDict, *, owner_userid: str) -> JsonDict:
        unionid = str(row.get("unionid") or "").strip()
        external_userid = str(row.get("primary_external_userid") or "").strip()
        display_name = str(row.get("customer_name") or row.get("remark") or "").strip() or f"客户 {unionid[-6:]}"
        return {
            "is_bound": True,
            "unionid": unionid,
            "external_userid": external_userid,
            "owner_userid": owner_userid or str(row.get("primary_owner_userid") or "").strip(),
            "customer_name": str(row.get("customer_name") or "").strip(),
            "remark": str(row.get("remark") or "").strip(),
            "display_name": display_name,
            "mobile": str(row.get("mobile") or "").strip(),
            "mobile_source": str(row.get("mobile_source") or "sidebar_bind").strip(),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "detail_url": f"/admin/customers/{unionid}",
        }
