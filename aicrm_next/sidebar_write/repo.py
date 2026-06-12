from __future__ import annotations

from copy import deepcopy
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
            profile = self._contact_profile(conn, normalized_external_userid)
            normalized_owner_userid = str(owner_userid or "").strip() or str(profile.get("owner_userid") or "").strip()
            normalized_bind_by_userid = str(bind_by_userid or "").strip() or normalized_owner_userid or "sidebar_bind"
            existing = self._binding_row(conn, normalized_external_userid)

            if existing and str(existing.get("mobile") or "").strip() == normalized_mobile:
                binding = self._binding_response(existing, profile=profile, owner_userid=normalized_owner_userid)
                return {
                    "external_userid": normalized_external_userid,
                    "write_type": "binding_noop",
                    "write_model_status": "updated",
                    "updated_at": str(existing.get("updated_at") or ""),
                    "changes": {},
                    "binding": binding,
                    "lead_pool_merge": {"ok": True, "merge_applied": False, "action_type": "lead_pool_noop"},
                }

            if existing and str(existing.get("mobile") or "").strip() != normalized_mobile and not force_rebind:
                raise ValueError("external_userid already bound to another mobile")

            person = self._get_or_create_person(conn, normalized_mobile)
            if existing:
                conn.execute(
                    """
                    UPDATE external_contact_bindings
                    SET person_id = %s,
                        last_owner_userid = %s,
                        updated_at = NOW()
                    WHERE external_userid = %s
                    """,
                    (person["id"], normalized_owner_userid, normalized_external_userid),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO external_contact_bindings (
                        external_userid,
                        person_id,
                        first_bound_by_userid,
                        first_owner_userid,
                        last_owner_userid,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    """,
                    (
                        normalized_external_userid,
                        person["id"],
                        normalized_bind_by_userid,
                        normalized_owner_userid,
                        normalized_owner_userid,
                    ),
                )

            lead_pool_merge = self._merge_lead_pool(
                conn,
                external_userid=normalized_external_userid,
                owner_userid=normalized_owner_userid,
                mobile=normalized_mobile,
                customer_name=str(profile.get("customer_name") or "").strip(),
            )
            conn.commit()

            updated = self._binding_row(conn, normalized_external_userid) or {
                "external_userid": normalized_external_userid,
                "person_id": person["id"],
                "mobile": normalized_mobile,
                "third_party_user_id": person.get("third_party_user_id") or "",
            }
            binding = self._binding_response(updated, profile=profile, owner_userid=normalized_owner_userid)
            return {
                "external_userid": normalized_external_userid,
                "write_type": "binding_update",
                "write_model_status": "updated",
                "updated_at": str(updated.get("updated_at") or ""),
                "changes": {
                    "mobile": normalized_mobile,
                    "binding": {
                        "is_bound": True,
                        "mobile": normalized_mobile,
                        "binding_status": "bound",
                    },
                },
                "binding": binding,
                "lead_pool_merge": lead_pool_merge,
            }

    def _contact_profile(self, conn, external_userid: str) -> JsonDict:
        row = conn.execute(
            """
            SELECT customer_name, owner_userid, remark
            FROM contacts
            WHERE external_userid = %s
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()
        return dict(row or {})

    def _binding_row(self, conn, external_userid: str) -> JsonDict | None:
        row = conn.execute(
            """
            SELECT
                b.external_userid,
                b.person_id,
                b.first_bound_by_userid,
                b.first_owner_userid,
                b.last_owner_userid,
                b.created_at,
                b.updated_at,
                p.mobile,
                p.third_party_user_id
            FROM external_contact_bindings b
            JOIN people p ON p.id = b.person_id
            WHERE b.external_userid = %s
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()
        return dict(row) if row else None

    def _get_or_create_person(self, conn, mobile: str) -> JsonDict:
        existing = conn.execute(
            """
            SELECT id, third_party_user_id
            FROM people
            WHERE mobile = %s
            ORDER BY id ASC
            LIMIT 1
            """,
            (mobile,),
        ).fetchone()
        if existing:
            return dict(existing)
        created = conn.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (%s, '', NOW(), NOW())
            RETURNING id, third_party_user_id
            """,
            (mobile,),
        ).fetchone()
        if not created:
            raise RuntimeError("person create failed")
        return dict(created)

    def _merge_lead_pool(
        self,
        conn,
        *,
        external_userid: str,
        owner_userid: str,
        mobile: str,
        customer_name: str,
    ) -> JsonDict:
        external_row = self._lead_pool_row(conn, "external_userid", external_userid)
        mobile_row = self._lead_pool_row(conn, "mobile", mobile)
        merge_applied = bool(external_row and (not external_row.get("mobile") or (mobile_row and mobile_row.get("id") != external_row.get("id"))))
        if external_row and mobile_row and int(external_row["id"]) != int(mobile_row["id"]):
            conn.execute("DELETE FROM user_ops_lead_pool_current WHERE id = %s", (external_row["id"],))
            target_row = mobile_row
            action_type = "lead_pool_merge_upsert"
        else:
            target_row = mobile_row or external_row
            action_type = "lead_pool_update" if target_row else "lead_pool_insert"

        if target_row:
            conn.execute(
                """
                UPDATE user_ops_lead_pool_current
                SET mobile = %s,
                    external_userid = %s,
                    customer_name = %s,
                    owner_userid = %s,
                    is_wecom_added = TRUE,
                    is_mobile_bound = TRUE,
                    last_entry_source = 'mobile_bind',
                    updated_at = NOW()
                WHERE id = %s
                """,
                (mobile, external_userid, customer_name, owner_userid, target_row["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_ops_lead_pool_current (
                    mobile,
                    external_userid,
                    customer_name,
                    owner_userid,
                    is_wecom_added,
                    is_mobile_bound,
                    first_entry_source,
                    last_entry_source,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, TRUE, TRUE, 'mobile_bind', 'mobile_bind', NOW(), NOW())
                """,
                (mobile, external_userid, customer_name, owner_userid),
            )

        return {"ok": True, "merge_applied": merge_applied, "action_type": action_type}

    def _lead_pool_row(self, conn, column: str, value: str) -> JsonDict | None:
        row = conn.execute(
            f"""
            SELECT id, mobile, external_userid, class_term_no, class_term_label, huangxiaocan_activation_state
            FROM user_ops_lead_pool_current
            WHERE {column} = %s
            LIMIT 1
            """,
            (value,),
        ).fetchone()
        return dict(row) if row else None

    def _binding_response(self, row: JsonDict, *, profile: JsonDict, owner_userid: str) -> JsonDict:
        external_userid = str(row.get("external_userid") or "").strip()
        display_name = str(profile.get("customer_name") or profile.get("remark") or "").strip() or f"客户 {external_userid[-6:]}"
        return {
            "is_bound": True,
            "person_id": row.get("person_id"),
            "external_userid": external_userid,
            "owner_userid": owner_userid or str(profile.get("owner_userid") or "").strip() or str(row.get("last_owner_userid") or row.get("first_owner_userid") or "").strip(),
            "customer_name": str(profile.get("customer_name") or "").strip(),
            "remark": str(profile.get("remark") or "").strip(),
            "display_name": display_name,
            "mobile": str(row.get("mobile") or "").strip(),
            "third_party_user_id": str(row.get("third_party_user_id") or "").strip(),
            "first_bound_by_userid": str(row.get("first_bound_by_userid") or "").strip(),
            "first_owner_userid": str(row.get("first_owner_userid") or "").strip(),
            "last_owner_userid": str(row.get("last_owner_userid") or "").strip(),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
            "detail_url": f"/admin/customers/{external_userid}",
        }
