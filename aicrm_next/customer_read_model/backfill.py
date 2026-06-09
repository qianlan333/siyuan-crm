from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from aicrm_next.shared.typing import JsonDict

from .repo import CustomerReadRepository, FixtureCustomerReadRepository, build_customer_read_model_repository
from .reconciliation import CustomerReadModelReconciliationRun, reconcile_customer_read_model

LOGGER = logging.getLogger(__name__)


class CustomerReadModelSource(Protocol):
    source_name: str

    def list_customers(self, *, limit: int | None = None, external_userids: set[str] | None = None) -> list[JsonDict]: ...

    def get_customer_detail(self, external_userid: str) -> JsonDict | None: ...

    def list_timeline(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]: ...

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]: ...


class FixtureCustomerReadModelSource:
    source_name = "fixture"

    def __init__(self, repo: FixtureCustomerReadRepository | None = None) -> None:
        self._repo = repo or FixtureCustomerReadRepository()

    def list_customers(self, *, limit: int | None = None, external_userids: set[str] | None = None) -> list[JsonDict]:
        rows = self._repo.list_customers(limit=limit, offset=0)
        if external_userids:
            rows = [item for item in rows if str(item.get("external_userid") or "") in external_userids]
        return rows

    def get_customer_detail(self, external_userid: str) -> JsonDict | None:
        return self._repo.get_customer(external_userid)

    def list_timeline(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        return self._repo.list_timeline(external_userid, limit=limit, offset=0)

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        return self._repo.list_recent_messages(external_userid, limit=limit)


class JsonFileCustomerReadModelSource:
    source_name = "file_json"

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            payload = {"customers": payload}
        self._customers = list(payload.get("customers") or [])
        self._details = {
            str(item.get("external_userid") or ""): item
            for item in list(payload.get("customer_details") or []) + self._customers
            if str(item.get("external_userid") or "").strip()
        }
        self._timeline = dict(payload.get("timeline_by_external_userid") or {})
        self._messages = dict(payload.get("messages_by_external_userid") or {})

    def list_customers(self, *, limit: int | None = None, external_userids: set[str] | None = None) -> list[JsonDict]:
        rows = list(self._customers)
        if external_userids:
            rows = [item for item in rows if str(item.get("external_userid") or "") in external_userids]
        return rows[:limit] if limit is not None else rows

    def get_customer_detail(self, external_userid: str) -> JsonDict | None:
        return self._details.get(external_userid)

    def list_timeline(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        rows = list(self._timeline.get(external_userid) or [])
        return rows[:limit] if limit is not None else rows

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        rows = list(self._messages.get(external_userid) or [])
        return rows[:limit] if limit is not None else rows


class LiveSourceCustomerReadModelSource:
    """Production-safe source reader for syncing live siyuan rows into Next projections.

    The source intentionally degrades when optional tables are absent. It only reads
    source tables and returns projection-shaped dictionaries for the backfill service.
    """

    source_name = "live"

    def __init__(self, session: Session) -> None:
        self._session = session
        self._inspector = inspect(session.get_bind())

    def list_customers(self, *, limit: int | None = None, external_userids: set[str] | None = None) -> list[JsonDict]:
        customers = self._load_customer_map(external_userids=external_userids)
        rows = list(customers.values())
        rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return rows[:limit] if limit is not None else rows

    def get_customer_detail(self, external_userid: str) -> JsonDict | None:
        rows = self.list_customers(external_userids={external_userid})
        return rows[0] if rows else None

    def list_timeline(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        rows = [
            {
                "event_id": f"message:{item.get('source_id') or item.get('msgid')}",
                "event_type": "message",
                "event_time": item.get("send_time") or _now_iso(),
                "title": f"消息 · {item.get('msgtype') or 'unknown'}",
                "summary": item.get("content") or "",
                "source_table": "archived_messages",
                "source_id": str(item.get("source_id") or item.get("msgid") or ""),
                "metadata": {
                    "msgtype": item.get("msgtype") or "text",
                    "owner_userid": item.get("owner_userid") or "",
                    "chat_type": item.get("chat_type") or "single",
                },
            }
            for item in self.list_recent_messages(external_userid, limit=limit)
        ]
        return rows[:limit] if limit is not None else rows

    def list_recent_messages(self, external_userid: str, *, limit: int | None = None) -> list[JsonDict]:
        if not self._has_table("archived_messages") or not self._has_column("archived_messages", "external_userid"):
            return []
        columns = self._columns("archived_messages")
        select_sql = self._select_list(
            "archived_messages",
            {
                "id": "id",
                "msgid": "msgid",
                "external_userid": "external_userid",
                "msgtype": "msgtype",
                "content": "content",
                "send_time": "send_time",
                "owner_userid": "owner_userid",
                "chat_type": "chat_type",
                "sender": "sender",
                "receiver": "receiver",
            },
        )
        order_column = "send_time" if "send_time" in columns else "id" if "id" in columns else "external_userid"
        rows = self._session.execute(
            text(
                f"""
                SELECT {select_sql}
                FROM archived_messages
                WHERE external_userid = :external_userid
                ORDER BY {order_column} DESC
                LIMIT :limit
                """
            ),
            {"external_userid": str(external_userid or "").strip(), "limit": max(1, int(limit or 20))},
        ).mappings()
        return [
            {
                "msgid": str(row.get("msgid") or row.get("id") or ""),
                "external_userid": str(row.get("external_userid") or ""),
                "msgtype": str(row.get("msgtype") or "text"),
                "content": str(row.get("content") or ""),
                "send_time": _iso_or_now(row.get("send_time")),
                "owner_userid": str(row.get("owner_userid") or ""),
                "chat_type": str(row.get("chat_type") or "single"),
                "sender": str(row.get("sender") or ""),
                "receiver": str(row.get("receiver") or ""),
                "source_id": str(row.get("id") or row.get("msgid") or ""),
            }
            for row in rows
        ]

    def _load_customer_map(self, *, external_userids: set[str] | None = None) -> dict[str, JsonDict]:
        customers: dict[str, JsonDict] = {}
        external_filter = {str(item or "").strip() for item in (external_userids or set()) if str(item or "").strip()}
        for row in self._contact_rows(external_filter):
            external_userid = str(row.get("external_userid") or "").strip()
            if not external_userid:
                continue
            customers.setdefault(external_userid, self._empty_customer(external_userid))
            customer = customers[external_userid]
            customer["customer_name"] = row.get("customer_name") or row.get("name") or external_userid
            customer["remark"] = row.get("remark") or ""
            customer["description"] = row.get("description") or ""
            customer["owner_userid"] = row.get("owner_userid") or customer.get("owner_userid") or ""
            customer["updated_at"] = _prefer_time(row.get("updated_at"), customer.get("updated_at"))
            customer["created_at"] = _prefer_time(row.get("created_at"), customer.get("created_at"))
            customer["contact"] = {
                "external_userid": external_userid,
                "name": customer["customer_name"],
                "remark": customer["remark"],
                "description": customer["description"],
            }

        person_ids: set[object] = set()
        for row in self._binding_rows(external_filter):
            external_userid = str(row.get("external_userid") or "").strip()
            if not external_userid:
                continue
            customers.setdefault(external_userid, self._empty_customer(external_userid))
            customer = customers[external_userid]
            person_id = row.get("person_id")
            if person_id not in (None, ""):
                person_ids.add(person_id)
            owner_userid = row.get("last_owner_userid") or row.get("first_owner_userid") or row.get("first_bound_by_userid") or ""
            customer["person_id"] = str(person_id or customer.get("person_id") or "")
            customer["owner_userid"] = customer.get("owner_userid") or owner_userid
            customer["updated_at"] = _prefer_time(row.get("updated_at"), customer.get("updated_at"))
            customer["created_at"] = _prefer_time(row.get("created_at"), customer.get("created_at"))
            customer["binding"] = {
                "is_bound": True,
                "person_id": person_id,
                "binding_status": "bound",
                "owner_userid": owner_userid,
                "first_owner_userid": row.get("first_owner_userid") or "",
                "last_owner_userid": row.get("last_owner_userid") or "",
            }

        people = self._people_map(person_ids)
        for customer in customers.values():
            person_id = str(customer.get("person_id") or "")
            person = people.get(person_id) or {}
            mobile = str(person.get("mobile") or "").strip()
            if mobile:
                customer["mobile"] = mobile
                customer.setdefault("binding", {})["mobile"] = mobile
            customer.setdefault("binding", {})["third_party_user_id"] = person.get("third_party_user_id") or ""
            customer["identity"] = {
                **dict(customer.get("identity") or {}),
                "person_id": customer.get("person_id") or "",
                "external_userid": customer.get("external_userid") or "",
                "mobile": mobile or customer.get("mobile") or "",
                "third_party_user_id": person.get("third_party_user_id") or "",
            }

        self._merge_identity(customers, external_filter)
        self._merge_follow_users(customers, external_filter)
        self._merge_tags(customers, external_filter)
        self._merge_class_status(customers, external_filter)
        self._merge_last_messages(customers, external_filter)
        return customers

    def _empty_customer(self, external_userid: str) -> JsonDict:
        now = _now_iso()
        return {
            "person_id": "",
            "external_userid": external_userid,
            "customer_name": external_userid,
            "remark": "",
            "description": "",
            "owner_userid": "",
            "owner_display_name": "",
            "mobile": None,
            "tags": [],
            "class_user_status": {},
            "last_message_at": None,
            "last_touch_at": None,
            "updated_at": now,
            "created_at": now,
            "binding": {"is_bound": False, "binding_status": "unbound"},
            "identity": {"external_userid": external_userid},
            "follow_users": [],
            "marketing_summary": {},
            "marketing_profile": {},
            "contact": {"external_userid": external_userid, "name": external_userid},
            "sidebar_context": {
                "can_open_sidebar": True,
                "customer_profile_url": f"/admin/customers/{external_userid}",
            },
        }

    def _contact_rows(self, external_filter: set[str]) -> list[JsonDict]:
        if not self._has_table("contacts") or not self._has_column("contacts", "external_userid"):
            return []
        return self._select_source_rows(
            "contacts",
            {
                "external_userid": "external_userid",
                "customer_name": "customer_name",
                "name": "name",
                "remark": "remark",
                "description": "description",
                "owner_userid": "owner_userid",
                "updated_at": "updated_at",
                "created_at": "created_at",
            },
            external_filter,
        )

    def _binding_rows(self, external_filter: set[str]) -> list[JsonDict]:
        if not self._has_table("external_contact_bindings") or not self._has_column("external_contact_bindings", "external_userid"):
            return []
        return self._select_source_rows(
            "external_contact_bindings",
            {
                "external_userid": "external_userid",
                "person_id": "person_id",
                "first_bound_by_userid": "first_bound_by_userid",
                "first_owner_userid": "first_owner_userid",
                "last_owner_userid": "last_owner_userid",
                "updated_at": "updated_at",
                "created_at": "created_at",
            },
            external_filter,
        )

    def _people_map(self, person_ids: set[object]) -> dict[str, JsonDict]:
        if not person_ids or not self._has_table("people") or not self._has_column("people", "id"):
            return {}
        columns = {
            "id": "id",
            "mobile": "mobile",
            "third_party_user_id": "third_party_user_id",
            "updated_at": "updated_at",
        }
        stmt = text(
            f"""
            SELECT {self._select_list("people", columns)}
            FROM people
            WHERE id IN :person_ids
            """
        ).bindparams(bindparam("person_ids", expanding=True))
        rows = self._session.execute(stmt, {"person_ids": list(person_ids)}).mappings()
        return {str(row.get("id") or ""): dict(row) for row in rows if str(row.get("id") or "")}

    def _merge_identity(self, customers: dict[str, JsonDict], external_filter: set[str]) -> None:
        if not customers or not self._has_table("wecom_external_contact_identity_map") or not self._has_column("wecom_external_contact_identity_map", "external_userid"):
            return
        for row in self._select_source_rows(
            "wecom_external_contact_identity_map",
            {
                "external_userid": "external_userid",
                "unionid": "unionid",
                "openid": "openid",
                "follow_user_userid": "follow_user_userid",
                "name": "name",
                "status": "status",
                "updated_at": "updated_at",
            },
            external_filter or set(customers),
            order_by="updated_at",
        ):
            external_userid = str(row.get("external_userid") or "").strip()
            if external_userid not in customers:
                continue
            identity = dict(customers[external_userid].get("identity") or {})
            identity.update(
                {
                    "unionid": row.get("unionid") or identity.get("unionid") or "",
                    "openid": row.get("openid") or identity.get("openid") or "",
                    "status": row.get("status") or identity.get("status") or "",
                }
            )
            customers[external_userid]["identity"] = identity
            if row.get("name") and customers[external_userid].get("customer_name") == external_userid:
                customers[external_userid]["customer_name"] = row.get("name")
            if row.get("follow_user_userid") and not customers[external_userid].get("owner_userid"):
                customers[external_userid]["owner_userid"] = row.get("follow_user_userid")

    def _merge_follow_users(self, customers: dict[str, JsonDict], external_filter: set[str]) -> None:
        if not customers or not self._has_table("wecom_external_contact_follow_users") or not self._has_column("wecom_external_contact_follow_users", "external_userid"):
            return
        for row in self._select_source_rows(
            "wecom_external_contact_follow_users",
            {
                "external_userid": "external_userid",
                "user_id": "user_id",
                "relation_status": "relation_status",
                "is_primary": "is_primary",
                "remark": "remark",
                "description": "description",
                "updated_at": "updated_at",
            },
            external_filter or set(customers),
        ):
            external_userid = str(row.get("external_userid") or "").strip()
            userid = str(row.get("user_id") or "").strip()
            if external_userid not in customers or not userid:
                continue
            customers[external_userid].setdefault("follow_users", []).append(
                {
                    "userid": userid,
                    "display_name": userid,
                    "relation_status": row.get("relation_status") or "",
                    "is_primary": bool(row.get("is_primary")),
                    "remark": row.get("remark") or "",
                    "description": row.get("description") or "",
                    "updated_at": _iso_or_empty(row.get("updated_at")),
                }
            )
            if not customers[external_userid].get("owner_userid"):
                customers[external_userid]["owner_userid"] = userid

    def _merge_tags(self, customers: dict[str, JsonDict], external_filter: set[str]) -> None:
        if not customers or not self._has_table("contact_tags") or not self._has_column("contact_tags", "external_userid"):
            return
        for row in self._select_source_rows(
            "contact_tags",
            {"external_userid": "external_userid", "tag_name": "tag_name", "tag_id": "tag_id"},
            external_filter or set(customers),
        ):
            external_userid = str(row.get("external_userid") or "").strip()
            tag = str(row.get("tag_name") or row.get("tag_id") or "").strip()
            if external_userid in customers and tag and tag not in customers[external_userid].setdefault("tags", []):
                customers[external_userid]["tags"].append(tag)

    def _merge_class_status(self, customers: dict[str, JsonDict], external_filter: set[str]) -> None:
        if not customers or not self._has_table("class_user_status_current") or not self._has_column("class_user_status_current", "external_userid"):
            return
        for row in self._select_source_rows(
            "class_user_status_current",
            {
                "external_userid": "external_userid",
                "signup_status": "signup_status",
                "signup_label_name": "signup_label_name",
                "activation_bucket": "activation_bucket",
                "owner_userid_snapshot": "owner_userid_snapshot",
                "customer_name_snapshot": "customer_name_snapshot",
                "mobile_snapshot": "mobile_snapshot",
                "updated_at": "updated_at",
            },
            external_filter or set(customers),
        ):
            external_userid = str(row.get("external_userid") or "").strip()
            if external_userid not in customers:
                continue
            customers[external_userid]["class_user_status"] = {
                "current_status": row.get("signup_status") or "",
                "signup_status": row.get("signup_status") or "",
                "signup_label_name": row.get("signup_label_name") or "",
                "activation_bucket": row.get("activation_bucket") or "",
                "updated_at": _iso_or_empty(row.get("updated_at")),
            }
            customers[external_userid]["owner_userid"] = customers[external_userid].get("owner_userid") or row.get("owner_userid_snapshot") or ""
            customers[external_userid]["customer_name"] = row.get("customer_name_snapshot") or customers[external_userid].get("customer_name")
            if row.get("mobile_snapshot") and not customers[external_userid].get("mobile"):
                customers[external_userid]["mobile"] = row.get("mobile_snapshot")
            customers[external_userid]["updated_at"] = _prefer_time(row.get("updated_at"), customers[external_userid].get("updated_at"))
            customers[external_userid]["last_touch_at"] = _prefer_time(row.get("updated_at"), customers[external_userid].get("last_touch_at"))

    def _merge_last_messages(self, customers: dict[str, JsonDict], external_filter: set[str]) -> None:
        if not customers or not self._has_table("archived_messages") or not self._has_column("archived_messages", "external_userid"):
            return
        rows = self._select_source_rows(
            "archived_messages",
            {"external_userid": "external_userid", "send_time": "send_time"},
            external_filter or set(customers),
            order_by="send_time",
        )
        for row in rows:
            external_userid = str(row.get("external_userid") or "").strip()
            if external_userid in customers:
                customers[external_userid]["last_message_at"] = _prefer_time(
                    row.get("send_time"),
                    customers[external_userid].get("last_message_at"),
                )

    def _select_source_rows(
        self,
        table: str,
        columns: dict[str, str],
        external_filter: set[str],
        *,
        order_by: str = "updated_at",
    ) -> list[JsonDict]:
        if not self._has_table(table):
            return []
        select_sql = self._select_list(table, columns)
        where_sql = ""
        params: JsonDict = {}
        stmt = text(f"SELECT {select_sql} FROM {table}")
        if external_filter and self._has_column(table, "external_userid"):
            where_sql = " WHERE external_userid IN :external_userids"
            stmt = text(f"SELECT {select_sql} FROM {table}{where_sql}").bindparams(
                bindparam("external_userids", expanding=True)
            )
            params["external_userids"] = list(external_filter)
        order_sql = ""
        if self._has_column(table, order_by):
            order_sql = f" ORDER BY {order_by} DESC"
        elif self._has_column(table, "id"):
            order_sql = " ORDER BY id DESC"
        if order_sql:
            base_sql = f"SELECT {select_sql} FROM {table}{where_sql}{order_sql}"
            stmt = text(base_sql)
            if external_filter and self._has_column(table, "external_userid"):
                stmt = stmt.bindparams(bindparam("external_userids", expanding=True))
        return [dict(row) for row in self._session.execute(stmt, params).mappings()]

    def _select_list(self, table: str, aliases: dict[str, str]) -> str:
        columns = self._columns(table)
        parts = []
        for alias, column in aliases.items():
            if column in columns:
                parts.append(column if alias == column else f"{column} AS {alias}")
            else:
                parts.append(f"NULL AS {alias}")
        return ", ".join(parts)

    def _has_table(self, table: str) -> bool:
        try:
            return bool(self._inspector.has_table(table))
        except Exception:
            LOGGER.warning("failed to inspect live source table %s", table, exc_info=True)
            return False

    def _columns(self, table: str) -> set[str]:
        if not self._has_table(table):
            return set()
        try:
            return {str(column.get("name") or "") for column in self._inspector.get_columns(table)}
        except Exception:
            LOGGER.warning("failed to inspect live source columns for %s", table, exc_info=True)
            return set()

    def _has_column(self, table: str, column: str) -> bool:
        return column in self._columns(table)


@dataclass(frozen=True)
class CustomerReadModelBackfillResult:
    run_id: str = field(default_factory=lambda: uuid4().hex)
    source_name: str = ""
    dry_run: bool = True
    replace: bool = False
    source_customer_count: int = 0
    projected_customer_count: int = 0
    detail_snapshot_count: int = 0
    timeline_event_count: int = 0
    recent_message_count: int = 0
    skipped_count: int = 0
    skipped_reasons: JsonDict = field(default_factory=dict)
    source_count: int = 0
    target_count: int = 0
    written_customers: int = 0
    written_timeline_events: int = 0
    written_recent_messages: int = 0
    reconciliation: JsonDict = field(default_factory=dict)
    masked_samples: list[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return asdict(self)


def _masked_samples(customers: list[JsonDict], *, limit: int = 3) -> list[JsonDict]:
    samples: list[JsonDict] = []
    for item in customers[:limit]:
        external_userid = str(item.get("external_userid") or "")
        mobile = str(item.get("mobile") or "")
        samples.append(
            {
                "external_userid": _mask_identifier(external_userid),
                "mobile": _mask_mobile(mobile),
                "owner_userid_present": bool(str(item.get("owner_userid") or "").strip()),
            }
        )
    return samples


def _mask_identifier(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _mask_mobile(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 5:
        return "***"
    return f"{digits[:3]}****{digits[-2:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_or_now(value) -> str:
    return _iso_or_empty(value) or _now_iso()


def _iso_or_empty(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _prefer_time(candidate, fallback) -> str:
    candidate_text = _iso_or_empty(candidate)
    fallback_text = _iso_or_empty(fallback)
    if not candidate_text:
        return fallback_text or _now_iso()
    if not fallback_text:
        return candidate_text
    return max(candidate_text, fallback_text)


class CustomerReadModelBackfillService:
    def __init__(
        self,
        *,
        source: CustomerReadModelSource | None = None,
        target_repo: CustomerReadRepository | None = None,
    ) -> None:
        self._source = source or FixtureCustomerReadModelSource()
        self._owns_target_repo = target_repo is None
        self._target_repo = target_repo or build_customer_read_model_repository()

    def _close_owned_target_repo(self) -> None:
        if not self._owns_target_repo:
            return
        close = getattr(self._target_repo, "close", None)
        if not callable(close):
            return
        try:
            close()
        except Exception:
            LOGGER.warning("failed to close customer read model backfill target repository", exc_info=True)

    def run(
        self,
        *,
        dry_run: bool = True,
        limit: int | None = None,
        external_userids: list[str] | None = None,
        replace: bool = False,
    ) -> CustomerReadModelBackfillResult:
        try:
            allowlist = {str(item).strip() for item in (external_userids or []) if str(item).strip()} or None
            customers = self._source.list_customers(limit=limit, external_userids=allowlist)
            detailed_customers: list[JsonDict] = []
            timeline_by_external_userid: dict[str, list[JsonDict]] = {}
            messages_by_external_userid: dict[str, list[JsonDict]] = {}
            skipped_reasons: dict[str, int] = {}
            for customer in customers:
                external_userid = str(customer.get("external_userid") or "").strip()
                if not external_userid:
                    skipped_reasons["empty_external_userid"] = skipped_reasons.get("empty_external_userid", 0) + 1
                    continue
                detail = self._source.get_customer_detail(external_userid) or customer
                detailed_customers.append(detail)
                timeline_by_external_userid[external_userid] = self._source.list_timeline(external_userid, limit=limit)
                messages_by_external_userid[external_userid] = self._source.list_recent_messages(external_userid, limit=limit)

            reconciliation: CustomerReadModelReconciliationRun
            if dry_run:
                reconciliation = CustomerReadModelReconciliationRun(
                    source_count=len(detailed_customers),
                    target_count=len(self._target_repo.list_customers(limit=None, offset=0)),
                    diff_count=0,
                    status="dry_run",
                )
                written_customers = 0
                write_result = {
                    "projected_customer_count": 0,
                    "detail_snapshot_count": 0,
                    "timeline_event_count": 0,
                    "recent_message_count": 0,
                }
            else:
                merge_projection = getattr(self._target_repo, "merge_projection", None)
                if not callable(merge_projection):
                    raise RuntimeError("target repository does not support merge_projection")
                write_result = merge_projection(
                    customers=detailed_customers,
                    timeline_by_external_userid=timeline_by_external_userid,
                    messages_by_external_userid=messages_by_external_userid,
                    replace=replace,
                )
                reconciliation = reconcile_customer_read_model(source_customers=detailed_customers, target_repo=self._target_repo)
                written_customers = len(detailed_customers)

            return CustomerReadModelBackfillResult(
                source_name=self._source.source_name,
                dry_run=dry_run,
                replace=replace,
                source_customer_count=len(customers),
                projected_customer_count=len(detailed_customers),
                detail_snapshot_count=int(write_result.get("detail_snapshot_count") or 0) if not dry_run else len(detailed_customers),
                timeline_event_count=sum(len(items) for items in timeline_by_external_userid.values()),
                recent_message_count=sum(len(items) for items in messages_by_external_userid.values()),
                skipped_count=sum(skipped_reasons.values()),
                skipped_reasons=skipped_reasons,
                source_count=len(detailed_customers),
                target_count=len(self._target_repo.list_customers(limit=None, offset=0)),
                written_customers=written_customers,
                written_timeline_events=0 if dry_run else sum(len(items) for items in timeline_by_external_userid.values()),
                written_recent_messages=0 if dry_run else sum(len(items) for items in messages_by_external_userid.values()),
                reconciliation=reconciliation.to_dict(),
                masked_samples=_masked_samples(detailed_customers),
            )
        finally:
            self._close_owned_target_repo()
