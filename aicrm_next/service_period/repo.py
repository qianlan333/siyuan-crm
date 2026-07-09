from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
import logging
from typing import Any, Protocol

from aicrm_next.commerce.repo import build_commerce_repository
from aicrm_next.shared.db_session import connect_pooled_postgres
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import assert_repository_allowed
from aicrm_next.shared.runtime import production_data_ready, raw_database_url

from .domain import (
    TENANT_ID,
    cta_text_for_status,
    entitlement_status,
    event_id_for,
    isoformat,
    normalize_link_slug,
    parse_datetime,
    remaining_days,
    text,
    utcnow,
    validate_duration_days,
)


LOGGER = logging.getLogger(__name__)


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value if isinstance(value, (dict, list)) else {}, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _paid_order(order: dict[str, Any]) -> bool:
    return text(order.get("status")).lower() == "paid" or text(order.get("trade_state")).upper() == "SUCCESS"


def _order_identity(order: dict[str, Any]) -> dict[str, str]:
    metadata = _json_object(order.get("metadata_json"))
    identity = metadata.get("payer_identity") if isinstance(metadata.get("payer_identity"), dict) else {}
    return {
        "unionid": text(order.get("unionid") or identity.get("unionid")),
        "external_userid": text(identity.get("external_userid") or order.get("external_userid")),
        "mobile": text(identity.get("mobile") or order.get("mobile") or order.get("mobile_snapshot")),
        "payer_name": text(order.get("payer_name_snapshot") or identity.get("payer_name")),
        "openid": text(identity.get("openid") or order.get("openid")),
    }


def _order_paid_at(order: dict[str, Any], transaction: dict[str, Any] | None = None) -> datetime:
    transaction = transaction or {}
    return parse_datetime(order.get("paid_at")) or parse_datetime(transaction.get("success_time")) or utcnow()


def _duration_end(start: datetime, duration_days: int) -> datetime:
    return start + timedelta(days=duration_days)


def _to_service_id(value: Any) -> str:
    return text(value)


def _compact_trade_product_payload(product: dict[str, Any], *, product_id: Any | None = None) -> dict[str, Any]:
    price = int(product.get("price_cents") or product.get("amount_total") or 0)
    slice_count = int(product.get("slice_count") or len(product.get("slices") or []))
    return {
        "id": text(product_id if product_id is not None else product.get("id")),
        "product_code": text(product.get("product_code")),
        "title": text(product.get("title") or product.get("name")),
        "name": text(product.get("title") or product.get("name")),
        "description": text(product.get("description")),
        "price_cents": price,
        "amount_total": price,
        "currency": text(product.get("currency")) or "CNY",
        "status": text(product.get("status")) or "draft",
        "enabled": bool(product.get("enabled")),
        "slice_count": slice_count,
        "updated_at": isoformat(product.get("trade_updated_at") or product.get("updated_at")),
    }


class ServicePeriodRepository(Protocol):
    def list_products(self, *, limit: int, offset: int) -> dict[str, Any]: ...
    def create_service_product(self, *, trade_product: dict[str, Any], duration_days: int, membership_config_id: str, membership_config_name: str, link_slug: str, metadata_json: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def get_product(self, service_product_id: str) -> dict[str, Any] | None: ...
    def get_product_by_slug(self, link_slug: str) -> dict[str, Any] | None: ...
    def get_public_product_by_slug(self, link_slug: str) -> dict[str, Any] | None: ...
    def update_service_product(self, service_product_id: str, *, trade_product: dict[str, Any], duration_days: int, membership_config_id: str, membership_config_name: str, metadata_json: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def copy_service_product(self, service_product_id: str, *, copied_trade_product: dict[str, Any]) -> dict[str, Any]: ...
    def delete_service_product(self, service_product_id: str) -> dict[str, Any]: ...
    def has_entitlements(self, service_product_id: str) -> bool: ...
    def stats(self, service_product_id: str) -> dict[str, Any]: ...
    def members(self, service_product_id: str, *, status: str | None, limit: int, offset: int) -> dict[str, Any]: ...
    def entitlement_for_unionid(self, service_product_id: str, unionid: str) -> dict[str, Any] | None: ...
    def grant_or_renew_from_paid_order(self, *, order: dict[str, Any], transaction: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def expire_due_entitlements(self, *, now: datetime | None = None) -> dict[str, Any]: ...


class InMemoryServicePeriodRepository:
    def __init__(self) -> None:
        self._products: list[dict[str, Any]] = []
        self._entitlements: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._next_product_id = 1
        self._next_entitlement_id = 1
        self._next_event_id = 1

    def list_products(self, *, limit: int, offset: int) -> dict[str, Any]:
        rows = [self._serialize_product(row, include_trade_product=False) for row in self._products if not row.get("deleted")]
        rows.sort(key=lambda item: (text(item.get("updated_at")), text(item.get("id"))), reverse=True)
        return {"ok": True, "items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    def create_service_product(
        self,
        *,
        trade_product: dict[str, Any],
        duration_days: int,
        membership_config_id: str,
        membership_config_name: str,
        link_slug: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trade_id = text(trade_product.get("id"))
        slug = normalize_link_slug(link_slug)
        if any(text(row.get("trade_product_id")) == trade_id and not row.get("deleted") for row in self._products):
            raise ContractError("trade_product_id is already bound to a service period product")
        if any(text(row.get("link_slug")) == slug and not row.get("deleted") for row in self._products):
            raise ContractError("link_slug must be unique")
        now = utcnow().isoformat()
        row = {
            "id": f"sp_{self._next_product_id:03d}",
            "tenant_id": TENANT_ID,
            "trade_product_id": trade_id,
            "link_slug": slug,
            "membership_config_id": text(membership_config_id),
            "membership_config_name": text(membership_config_name),
            "duration_days": validate_duration_days(duration_days),
            "deleted": False,
            "metadata_json": deepcopy(metadata_json or {}),
            "created_at": now,
            "updated_at": now,
        }
        self._next_product_id += 1
        self._products.append(row)
        return self._serialize_product(row)

    def get_product(self, service_product_id: str) -> dict[str, Any] | None:
        row = self._find_product(service_product_id)
        return self._serialize_product(row) if row else None

    def get_product_by_slug(self, link_slug: str) -> dict[str, Any] | None:
        slug = text(link_slug)
        for row in self._products:
            if not row.get("deleted") and text(row.get("link_slug")) == slug:
                return self._serialize_product(row)
        return None

    def get_public_product_by_slug(self, link_slug: str) -> dict[str, Any] | None:
        slug = text(link_slug)
        for row in self._products:
            if row.get("deleted") or text(row.get("link_slug")) != slug:
                continue
            item = self._serialize_product(row)
            trade_product = item.get("trade_product") or {}
            if not trade_product.get("enabled") or text(trade_product.get("status")) != "active":
                return None
            return item
        return None

    def update_service_product(
        self,
        service_product_id: str,
        *,
        trade_product: dict[str, Any],
        duration_days: int,
        membership_config_id: str,
        membership_config_name: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self._find_product(service_product_id)
        if not row:
            raise NotFoundError("service period product not found")
        row.update(
            {
                "duration_days": validate_duration_days(duration_days),
                "membership_config_id": text(membership_config_id),
                "membership_config_name": text(membership_config_name),
                "metadata_json": deepcopy(metadata_json if metadata_json is not None else row.get("metadata_json") or {}),
                "updated_at": utcnow().isoformat(),
            }
        )
        return self._serialize_product(row)

    def copy_service_product(self, service_product_id: str, *, copied_trade_product: dict[str, Any]) -> dict[str, Any]:
        source = self._find_product(service_product_id)
        if not source:
            raise NotFoundError("service period product not found")
        return self.create_service_product(
            trade_product=copied_trade_product,
            duration_days=int(source.get("duration_days") or 0),
            membership_config_id=text(source.get("membership_config_id")),
            membership_config_name=text(source.get("membership_config_name")),
            link_slug=text(copied_trade_product.get("product_code")),
            metadata_json=deepcopy(source.get("metadata_json") or {}),
        )

    def delete_service_product(self, service_product_id: str) -> dict[str, Any]:
        row = self._find_product(service_product_id)
        if not row:
            raise NotFoundError("service period product not found")
        if self.has_entitlements(service_product_id):
            raise ContractError("已有服务期凭证的周期商品不能硬删除，请先下架")
        self._products = [item for item in self._products if item is not row]
        return {"ok": True, "deleted": True, "service_product_id": service_product_id, "trade_product_id": text(row.get("trade_product_id"))}

    def has_entitlements(self, service_product_id: str) -> bool:
        return any(text(row.get("service_product_id")) == text(service_product_id) for row in self._entitlements)

    def stats(self, service_product_id: str) -> dict[str, Any]:
        now = utcnow()
        entitlements = [row for row in self._entitlements if text(row.get("service_product_id")) == text(service_product_id)]
        active = [row for row in entitlements if entitlement_status(row.get("end_at"), row.get("status"), now=now) == "active"]
        def _expiring_soon(row: dict[str, Any]) -> bool:
            end = parse_datetime(row.get("end_at"))
            return bool(end and now < end <= now + timedelta(days=7))

        return {
            "ok": True,
            "active_user_count": len(active),
            "expiring_7d_count": sum(1 for row in active if _expiring_soon(row)),
            "renewal_order_count": sum(1 for row in self._events if text(row.get("service_product_id")) == text(service_product_id) and row.get("event_type") == "renewed"),
            "total_paid_amount_cents": sum(int((row.get("payload_json") or {}).get("amount_total") or 0) for row in self._events if text(row.get("service_product_id")) == text(service_product_id) and row.get("event_type") in {"activated", "renewed"}),
        }

    def members(self, service_product_id: str, *, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        now = utcnow()
        rows = [row for row in self._entitlements if text(row.get("service_product_id")) == text(service_product_id)]
        if status:
            rows = [row for row in rows if entitlement_status(row.get("end_at"), row.get("status"), now=now) == status]
        items = [self._member_payload(row, now=now) for row in rows]
        items.sort(key=lambda item: text(item.get("end_at")), reverse=True)
        return {"ok": True, "items": items[offset : offset + limit], "total": len(items), "limit": limit, "offset": offset}

    def entitlement_for_unionid(self, service_product_id: str, unionid: str) -> dict[str, Any] | None:
        normalized = text(unionid)
        for row in self._entitlements:
            if text(row.get("service_product_id")) == text(service_product_id) and text(row.get("unionid")) == normalized:
                return self._entitlement_payload(row)
        return None

    def grant_or_renew_from_paid_order(self, *, order: dict[str, Any], transaction: dict[str, Any] | None = None) -> dict[str, Any]:
        if not _paid_order(order):
            return {"ok": True, "skipped": True, "reason": "order_not_paid"}
        product = self._find_product_for_order(order)
        if not product:
            return {"ok": True, "skipped": True, "reason": "not_service_period_product"}
        out_trade_no = text(order.get("out_trade_no") or (transaction or {}).get("out_trade_no"))
        if self._event_for_out_trade_no(out_trade_no, {"activated", "renewed"}):
            return {"ok": True, "idempotent": True, "skipped": True, "reason": "event_already_applied"}
        identity = _order_identity(order)
        unionid = identity["unionid"]
        if not unionid:
            event = self._append_event(
                product=product,
                entitlement_id="",
                order=order,
                out_trade_no=out_trade_no,
                unionid="",
                event_type="grant_failed_missing_unionid",
                duration_days=0,
                before=None,
                after=None,
                payload={"reason": "missing_unionid", "order": order, "transaction": transaction or {}},
            )
            LOGGER.warning("service_period_grant_failed_missing_unionid", extra={"out_trade_no": out_trade_no, "service_product_id": product.get("id")})
            return {"ok": False, "skipped": True, "reason": "missing_unionid", "event": event}
        now = utcnow()
        paid_at = _order_paid_at(order, transaction)
        entitlement = self._find_entitlement(text(product.get("id")), unionid)
        before = deepcopy(entitlement) if entitlement else None
        duration_days = int(product.get("duration_days") or 0)
        if entitlement and entitlement_status(entitlement.get("end_at"), entitlement.get("status"), now=now) == "active":
            start_at = parse_datetime(entitlement.get("start_at")) or paid_at
            end_at = _duration_end(parse_datetime(entitlement.get("end_at")) or paid_at, duration_days)
            event_type = "renewed"
            renewal_count = int(entitlement.get("renewal_count") or 0) + 1
        else:
            start_at = paid_at
            end_at = _duration_end(start_at, duration_days)
            event_type = "activated"
            renewal_count = 0 if not entitlement else int(entitlement.get("renewal_count") or 0) + 1
        if entitlement:
            entitlement.update(
                {
                    "trade_product_id": text(product.get("trade_product_id")),
                    "external_userid_snapshot": identity["external_userid"],
                    "mobile_snapshot": identity["mobile"],
                    "membership_config_id": text(product.get("membership_config_id")),
                    "status": "active",
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "last_order_id": order.get("id"),
                    "last_out_trade_no": out_trade_no,
                    "renewal_count": renewal_count,
                    "metadata_json": {"last_order": order, "payer_name": identity["payer_name"]},
                    "updated_at": now.isoformat(),
                }
            )
        else:
            entitlement = {
                "id": f"spe_{self._next_entitlement_id:03d}",
                "tenant_id": TENANT_ID,
                "service_product_id": text(product.get("id")),
                "trade_product_id": text(product.get("trade_product_id")),
                "unionid": unionid,
                "external_userid_snapshot": identity["external_userid"],
                "mobile_snapshot": identity["mobile"],
                "membership_config_id": text(product.get("membership_config_id")),
                "status": "active",
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "last_order_id": order.get("id"),
                "last_out_trade_no": out_trade_no,
                "renewal_count": renewal_count,
                "metadata_json": {"last_order": order, "payer_name": identity["payer_name"]},
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            self._next_entitlement_id += 1
            self._entitlements.append(entitlement)
        event = self._append_event(
            product=product,
            entitlement_id=text(entitlement.get("id")),
            order=order,
            out_trade_no=out_trade_no,
            unionid=unionid,
            event_type=event_type,
            duration_days=duration_days,
            before=before,
            after=entitlement,
            payload={"order": order, "transaction": transaction or {}, "amount_total": int(order.get("amount_total") or 0)},
        )
        return {"ok": True, "event_type": event_type, "entitlement": self._entitlement_payload(entitlement), "event": event}

    def expire_due_entitlements(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        expired_count = 0
        for entitlement in self._entitlements:
            if entitlement_status(entitlement.get("end_at"), entitlement.get("status"), now=now) != "expired":
                continue
            if text(entitlement.get("status")) == "expired":
                continue
            product = self._find_product(entitlement.get("service_product_id"))
            if not product:
                continue
            before = deepcopy(entitlement)
            entitlement["status"] = "expired"
            entitlement["updated_at"] = now.isoformat()
            self._append_event(
                product=product,
                entitlement_id=text(entitlement.get("id")),
                order={},
                out_trade_no="",
                unionid=text(entitlement.get("unionid")),
                event_type="expired",
                duration_days=0,
                before=before,
                after=entitlement,
                payload={"source": "expire_due_entitlements"},
            )
            expired_count += 1
        return {"ok": True, "expired_count": expired_count}

    def _find_product(self, service_product_id: Any) -> dict[str, Any] | None:
        normalized = text(service_product_id)
        for row in self._products:
            if text(row.get("id")) == normalized and not row.get("deleted"):
                return row
        return None

    def _find_product_for_order(self, order: dict[str, Any]) -> dict[str, Any] | None:
        code = text(order.get("product_code"))
        commerce = build_commerce_repository()
        for row in self._products:
            if row.get("deleted"):
                continue
            trade = commerce.get_product(text(row.get("trade_product_id"))) or {}
            if text(trade.get("product_code")) == code:
                return row
        return None

    def _find_entitlement(self, service_product_id: str, unionid: str) -> dict[str, Any] | None:
        for row in self._entitlements:
            if text(row.get("service_product_id")) == text(service_product_id) and text(row.get("unionid")) == text(unionid):
                return row
        return None

    def _event_for_out_trade_no(self, out_trade_no: str, event_types: set[str]) -> dict[str, Any] | None:
        if not out_trade_no:
            return None
        for row in self._events:
            if text(row.get("out_trade_no")) == out_trade_no and text(row.get("event_type")) in event_types:
                return row
        return None

    def _append_event(
        self,
        *,
        product: dict[str, Any],
        entitlement_id: str,
        order: dict[str, Any],
        out_trade_no: str,
        unionid: str,
        event_type: str,
        duration_days: int,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self._event_for_out_trade_no(out_trade_no, {event_type})
        if existing:
            return deepcopy(existing)
        row = {
            "id": f"spev_{self._next_event_id:03d}",
            "tenant_id": TENANT_ID,
            "event_id": event_id_for(event_type, out_trade_no or f"{product.get('id')}:{entitlement_id}:{self._next_event_id}"),
            "service_product_id": text(product.get("id")),
            "entitlement_id": entitlement_id,
            "trade_product_id": text(product.get("trade_product_id")),
            "order_id": order.get("id"),
            "out_trade_no": out_trade_no,
            "unionid": unionid,
            "event_type": event_type,
            "duration_days": int(duration_days or 0),
            "before_start_at": before.get("start_at") if before else None,
            "before_end_at": before.get("end_at") if before else None,
            "after_start_at": after.get("start_at") if after else None,
            "after_end_at": after.get("end_at") if after else None,
            "payload_json": deepcopy(payload),
            "created_at": utcnow().isoformat(),
        }
        self._next_event_id += 1
        self._events.append(row)
        return deepcopy(row)

    def _serialize_product(self, row: dict[str, Any], *, include_trade_product: bool = True) -> dict[str, Any]:
        commerce = build_commerce_repository()
        full_trade_product = commerce.get_product(text(row.get("trade_product_id"))) or {}
        trade_product = deepcopy(full_trade_product) if include_trade_product else _compact_trade_product_payload(full_trade_product)
        product_code = text(full_trade_product.get("product_code"))
        sold_count = commerce.count_orders_for_product_code(product_code) if product_code else 0
        updated_at = text(full_trade_product.get("updated_at") or row.get("updated_at"))
        return {
            **deepcopy(row),
            "id": text(row.get("id")),
            "trade_product_id": text(row.get("trade_product_id")),
            "product_code": product_code,
            "title": text(full_trade_product.get("title") or full_trade_product.get("name")),
            "name": text(full_trade_product.get("title") or full_trade_product.get("name")),
            "description": text(full_trade_product.get("description")),
            "price_cents": int(full_trade_product.get("price_cents") or full_trade_product.get("amount_total") or 0),
            "amount_total": int(full_trade_product.get("price_cents") or full_trade_product.get("amount_total") or 0),
            "currency": text(full_trade_product.get("currency")) or "CNY",
            "status": text(full_trade_product.get("status")) or "draft",
            "enabled": bool(full_trade_product.get("enabled")),
            "sold_count": sold_count,
            "updated_at": updated_at,
            "trade_product": trade_product,
        }

    def _entitlement_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        status = entitlement_status(row.get("end_at"), row.get("status"))
        return {**deepcopy(row), "status": status, "remaining_days": remaining_days(row.get("end_at")), "end_at": isoformat(row.get("end_at"))}

    def _member_payload(self, row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        metadata = row.get("metadata_json") or {}
        last_order = metadata.get("last_order") if isinstance(metadata.get("last_order"), dict) else {}
        status = entitlement_status(row.get("end_at"), row.get("status"), now=now)
        return {
            "unionid": text(row.get("unionid")),
            "display_name": text(metadata.get("payer_name")) or text(last_order.get("payer_name_snapshot")),
            "mobile": text(row.get("mobile_snapshot")),
            "status": status,
            "remaining_days": remaining_days(row.get("end_at"), now=now),
            "end_at": isoformat(row.get("end_at")),
            "last_order_amount": int(last_order.get("amount_total") or 0),
            "last_order_duration_days": int((self._find_product(row.get("service_product_id")) or {}).get("duration_days") or 0),
        }


class PostgresServicePeriodRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self):
        return connect_pooled_postgres(self._database_url)

    def list_products(self, *, limit: int, offset: int) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    sp.*,
                    p.product_code,
                    p.name,
                    p.amount_total,
                    p.currency,
                    p.status,
                    p.enabled,
                    p.updated_at AS trade_updated_at,
                    COALESCE(sold.sold_count, 0) AS sold_count
                FROM service_period_products sp
                JOIN wechat_pay_products p ON p.id = sp.trade_product_id
                LEFT JOIN LATERAL (
                    SELECT count(*) AS sold_count
                    FROM wechat_pay_orders o
                    WHERE o.product_code = p.product_code
                      AND (o.status = 'paid' OR o.trade_state = 'SUCCESS')
                ) sold ON TRUE
                WHERE sp.tenant_id = 'aicrm'
                  AND sp.deleted = FALSE
                ORDER BY sp.updated_at DESC, sp.id DESC
                LIMIT %s OFFSET %s
                """,
                (int(limit), int(offset)),
            ).fetchall()
            total_row = conn.execute(
                "SELECT count(*) AS total FROM service_period_products WHERE tenant_id = 'aicrm' AND deleted = FALSE"
            ).fetchone() or {}
            items = [self._serialize_join_row(dict(row), include_trade_product=False) for row in rows]
        return {"ok": True, "items": items, "total": int(total_row.get("total") or 0), "limit": limit, "offset": offset}

    def create_service_product(
        self,
        *,
        trade_product: dict[str, Any],
        duration_days: int,
        membership_config_id: str,
        membership_config_name: str,
        link_slug: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO service_period_products (
                    tenant_id, trade_product_id, link_slug, membership_config_id,
                    membership_config_name, duration_days, metadata_json, created_at, updated_at
                )
                VALUES ('aicrm', %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING *
                """,
                (
                    int(trade_product["id"]),
                    normalize_link_slug(link_slug),
                    text(membership_config_id),
                    text(membership_config_name),
                    validate_duration_days(duration_days),
                    _jsonb(metadata_json or {}),
                ),
            ).fetchone()
            conn.commit()
        return self.get_product(text(row.get("id"))) or {}

    def get_product(self, service_product_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    sp.*,
                    p.product_code,
                    p.name,
                    p.amount_total,
                    p.currency,
                    p.status,
                    p.enabled,
                    p.updated_at AS trade_updated_at,
                    COALESCE(sold.sold_count, 0) AS sold_count
                FROM service_period_products sp
                JOIN wechat_pay_products p ON p.id = sp.trade_product_id
                LEFT JOIN LATERAL (
                    SELECT count(*) AS sold_count
                    FROM wechat_pay_orders o
                    WHERE o.product_code = p.product_code
                      AND (o.status = 'paid' OR o.trade_state = 'SUCCESS')
                ) sold ON TRUE
                WHERE sp.id::text = %s
                  AND sp.tenant_id = 'aicrm'
                  AND sp.deleted = FALSE
                LIMIT 1
                """,
                (text(service_product_id),),
            ).fetchone()
        return self._serialize_join_row(dict(row)) if row else None

    def get_product_by_slug(self, link_slug: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sp.id
                FROM service_period_products sp
                WHERE sp.tenant_id = 'aicrm'
                  AND sp.deleted = FALSE
                  AND sp.link_slug = %s
                LIMIT 1
                """,
                (text(link_slug),),
            ).fetchone()
        return self.get_product(text(row.get("id"))) if row else None

    def get_public_product_by_slug(self, link_slug: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sp.id
                FROM service_period_products sp
                JOIN wechat_pay_products p ON p.id = sp.trade_product_id
                WHERE sp.tenant_id = 'aicrm'
                  AND sp.deleted = FALSE
                  AND sp.link_slug = %s
                  AND p.enabled = TRUE
                  AND p.status = 'active'
                LIMIT 1
                """,
                (text(link_slug),),
            ).fetchone()
        return self.get_product(text(row.get("id"))) if row else None

    def update_service_product(
        self,
        service_product_id: str,
        *,
        trade_product: dict[str, Any],
        duration_days: int,
        membership_config_id: str,
        membership_config_name: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE service_period_products
                SET duration_days = %s,
                    membership_config_id = %s,
                    membership_config_name = %s,
                    metadata_json = COALESCE(%s::jsonb, metadata_json),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id::text = %s
                  AND tenant_id = 'aicrm'
                  AND deleted = FALSE
                RETURNING id
                """,
                (
                    validate_duration_days(duration_days),
                    text(membership_config_id),
                    text(membership_config_name),
                    _jsonb(metadata_json or {}),
                    text(service_product_id),
                ),
            ).fetchone()
            conn.commit()
        if not row:
            raise NotFoundError("service period product not found")
        return self.get_product(service_product_id) or {}

    def copy_service_product(self, service_product_id: str, *, copied_trade_product: dict[str, Any]) -> dict[str, Any]:
        source = self.get_product(service_product_id)
        if not source:
            raise NotFoundError("service period product not found")
        return self.create_service_product(
            trade_product=copied_trade_product,
            duration_days=int(source.get("duration_days") or 0),
            membership_config_id=text(source.get("membership_config_id")),
            membership_config_name=text(source.get("membership_config_name")),
            link_slug=text(copied_trade_product.get("product_code")),
            metadata_json=_json_object(source.get("metadata_json")),
        )

    def delete_service_product(self, service_product_id: str) -> dict[str, Any]:
        product = self.get_product(service_product_id)
        if not product:
            raise NotFoundError("service period product not found")
        if self.has_entitlements(service_product_id):
            raise ContractError("已有服务期凭证的周期商品不能硬删除，请先下架")
        with self._connect() as conn:
            row = conn.execute(
                """
                DELETE FROM service_period_products
                WHERE id::text = %s
                  AND tenant_id = 'aicrm'
                  AND deleted = FALSE
                RETURNING id, trade_product_id
                """,
                (text(service_product_id),),
            ).fetchone()
            conn.commit()
        if not row:
            raise NotFoundError("service period product not found")
        return {"ok": True, "deleted": True, "service_product_id": text(row.get("id")), "trade_product_id": text(row.get("trade_product_id"))}

    def has_entitlements(self, service_product_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM service_period_entitlements WHERE service_product_id::text = %s LIMIT 1",
                (text(service_product_id),),
            ).fetchone()
        return bool(row)

    def stats(self, service_product_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'active' AND end_at > CURRENT_TIMESTAMP) AS active_user_count,
                    count(*) FILTER (WHERE status = 'active' AND end_at > CURRENT_TIMESTAMP AND end_at <= CURRENT_TIMESTAMP + INTERVAL '7 days') AS expiring_7d_count
                FROM service_period_entitlements
                WHERE service_product_id::text = %s
                """,
                (text(service_product_id),),
            ).fetchone() or {}
            renewal = conn.execute(
                """
                SELECT count(*) AS total
                FROM service_period_events
                WHERE service_product_id::text = %s
                  AND event_type = 'renewed'
                """,
                (text(service_product_id),),
            ).fetchone() or {}
            amount = conn.execute(
                """
                SELECT COALESCE(sum(o.amount_total), 0) AS total
                FROM service_period_events e
                JOIN wechat_pay_orders o ON o.out_trade_no = e.out_trade_no
                WHERE e.service_product_id::text = %s
                  AND e.event_type IN ('activated', 'renewed')
                """,
                (text(service_product_id),),
            ).fetchone() or {}
        return {
            "ok": True,
            "active_user_count": int(row.get("active_user_count") or 0),
            "expiring_7d_count": int(row.get("expiring_7d_count") or 0),
            "renewal_order_count": int(renewal.get("total") or 0),
            "total_paid_amount_cents": int(amount.get("total") or 0),
        }

    def members(self, service_product_id: str, *, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        status_filter = text(status)
        params: list[Any] = [text(service_product_id)]
        where = ["e.service_product_id::text = %s"]
        if status_filter:
            where.append("e.status = %s")
            params.append(status_filter)
        params.extend([int(limit), int(offset)])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    e.*,
                    p.duration_days AS last_order_duration_days,
                    o.amount_total AS last_order_amount,
                    COALESCE(NULLIF(c.customer_name, ''), NULLIF(e.metadata_json->>'payer_name', ''), NULLIF(o.payer_name_snapshot, '')) AS display_name,
                    COALESCE(NULLIF(e.mobile_snapshot, ''), NULLIF(c.mobile, '')) AS mobile
                FROM service_period_entitlements e
                JOIN service_period_products p ON p.id = e.service_product_id
                LEFT JOIN wechat_pay_orders o ON o.id = e.last_order_id
                LEFT JOIN crm_user_identity c ON c.unionid = e.unionid
                WHERE {" AND ".join(where)}
                ORDER BY e.end_at DESC, e.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            ).fetchall()
            total_row = conn.execute(
                f"SELECT count(*) AS total FROM service_period_entitlements e WHERE {' AND '.join(where)}",
                tuple(params[:-2]),
            ).fetchone() or {}
        now = utcnow()
        items = [
            {
                "unionid": text(row.get("unionid")),
                "display_name": text(row.get("display_name")),
                "mobile": text(row.get("mobile")),
                "status": entitlement_status(row.get("end_at"), row.get("status"), now=now),
                "remaining_days": remaining_days(row.get("end_at"), now=now),
                "end_at": isoformat(row.get("end_at")),
                "last_order_amount": int(row.get("last_order_amount") or 0),
                "last_order_duration_days": int(row.get("last_order_duration_days") or 0),
            }
            for row in rows
        ]
        return {"ok": True, "items": items, "total": int(total_row.get("total") or 0), "limit": limit, "offset": offset}

    def entitlement_for_unionid(self, service_product_id: str, unionid: str) -> dict[str, Any] | None:
        if not text(unionid):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM service_period_entitlements
                WHERE tenant_id = 'aicrm'
                  AND service_product_id::text = %s
                  AND unionid = %s
                LIMIT 1
                """,
                (text(service_product_id), text(unionid)),
            ).fetchone()
        return self._entitlement_payload(dict(row)) if row else None

    def grant_or_renew_from_paid_order(self, *, order: dict[str, Any], transaction: dict[str, Any] | None = None) -> dict[str, Any]:
        if not _paid_order(order):
            return {"ok": True, "skipped": True, "reason": "order_not_paid"}
        out_trade_no = text(order.get("out_trade_no") or (transaction or {}).get("out_trade_no"))
        with self._connect() as conn:
            product = self._find_product_for_order(conn, order)
            if not product:
                return {"ok": True, "skipped": True, "reason": "not_service_period_product"}
            if self._event_exists(conn, out_trade_no, {"activated", "renewed"}):
                return {"ok": True, "idempotent": True, "skipped": True, "reason": "event_already_applied"}
            unionid = self._resolve_order_unionid(conn, order)
            if not unionid:
                event = self._insert_event(
                    conn,
                    product=product,
                    entitlement_id=None,
                    order=order,
                    out_trade_no=out_trade_no,
                    unionid="",
                    event_type="grant_failed_missing_unionid",
                    duration_days=0,
                    before=None,
                    after=None,
                    payload={"reason": "missing_unionid", "order": order, "transaction": transaction or {}},
                )
                conn.commit()
                LOGGER.warning("service_period_grant_failed_missing_unionid", extra={"out_trade_no": out_trade_no, "service_product_id": product.get("id")})
                return {"ok": False, "skipped": True, "reason": "missing_unionid", "event": event}
            result = self._grant_or_renew_with_unionid(conn, product=product, order=order, transaction=transaction or {}, unionid=unionid, out_trade_no=out_trade_no)
            conn.commit()
            return result

    def expire_due_entitlements(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        expired_count = 0
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*, p.trade_product_id, p.duration_days
                FROM service_period_entitlements e
                JOIN service_period_products p ON p.id = e.service_product_id
                WHERE e.status = 'active'
                  AND e.end_at <= %s
                ORDER BY e.end_at ASC, e.id ASC
                """,
                (now,),
            ).fetchall()
            for row in rows:
                before = dict(row)
                updated = conn.execute(
                    """
                    UPDATE service_period_entitlements
                    SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND status = 'active'
                    RETURNING *
                    """,
                    (int(row.get("id")),),
                ).fetchone()
                if not updated:
                    continue
                self._insert_event(
                    conn,
                    product={"id": row.get("service_product_id"), "trade_product_id": row.get("trade_product_id")},
                    entitlement_id=int(row.get("id")),
                    order={},
                    out_trade_no="",
                    unionid=text(row.get("unionid")),
                    event_type="expired",
                    duration_days=0,
                    before=before,
                    after=dict(updated),
                    payload={"source": "expire_due_entitlements"},
                )
                expired_count += 1
            conn.commit()
        return {"ok": True, "expired_count": expired_count}

    def _serialize_join_row(self, row: dict[str, Any], *, include_trade_product: bool = True) -> dict[str, Any]:
        if include_trade_product:
            trade_product = build_commerce_repository().get_product(text(row.get("trade_product_id"))) or {}
        else:
            trade_product = _compact_trade_product_payload(row, product_id=row.get("trade_product_id"))
        price = int(row.get("amount_total") or trade_product.get("price_cents") or 0)
        return {
            **row,
            "id": text(row.get("id")),
            "trade_product_id": text(row.get("trade_product_id")),
            "product_code": text(row.get("product_code") or trade_product.get("product_code")),
            "title": text(row.get("name") or trade_product.get("title")),
            "name": text(row.get("name") or trade_product.get("title")),
            "description": text(trade_product.get("description")),
            "price_cents": price,
            "amount_total": price,
            "currency": text(row.get("currency") or trade_product.get("currency")) or "CNY",
            "status": text(row.get("status") or trade_product.get("status")),
            "enabled": bool(row.get("enabled")),
            "sold_count": int(row.get("sold_count") or 0),
            "duration_days": int(row.get("duration_days") or 0),
            "updated_at": isoformat(row.get("trade_updated_at") or row.get("updated_at")),
            "trade_product": trade_product,
        }

    def _find_product_for_order(self, conn: Any, order: dict[str, Any]) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT sp.*
            FROM service_period_products sp
            JOIN wechat_pay_products p ON p.id = sp.trade_product_id
            WHERE sp.tenant_id = 'aicrm'
              AND sp.deleted = FALSE
              AND p.product_code = %s
            LIMIT 1
            """,
            (text(order.get("product_code")),),
        ).fetchone()
        return dict(row) if row else None

    def _event_exists(self, conn: Any, out_trade_no: str, event_types: set[str]) -> bool:
        if not out_trade_no:
            return False
        row = conn.execute(
            """
            SELECT 1
            FROM service_period_events
            WHERE tenant_id = 'aicrm'
              AND out_trade_no = %s
              AND event_type = ANY(%s)
            LIMIT 1
            """,
            (out_trade_no, list(event_types)),
        ).fetchone()
        return bool(row)

    def _resolve_order_unionid(self, conn: Any, order: dict[str, Any]) -> str:
        identity = _order_identity(order)
        if identity["unionid"]:
            return identity["unionid"]
        clauses: list[str] = []
        params: list[Any] = []
        if identity["openid"]:
            clauses.append("(primary_openid = %s OR jsonb_exists(openids_json, %s))")
            params.extend([identity["openid"], identity["openid"]])
        if identity["external_userid"]:
            clauses.append("(primary_external_userid = %s OR jsonb_exists(external_userids_json, %s))")
            params.extend([identity["external_userid"], identity["external_userid"]])
        if not clauses:
            return ""
        row = conn.execute(
            f"""
            SELECT unionid
            FROM crm_user_identity
            WHERE {" OR ".join(clauses)}
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
        return text((row or {}).get("unionid"))

    def _grant_or_renew_with_unionid(
        self,
        conn: Any,
        *,
        product: dict[str, Any],
        order: dict[str, Any],
        transaction: dict[str, Any],
        unionid: str,
        out_trade_no: str,
    ) -> dict[str, Any]:
        now = utcnow()
        paid_at = _order_paid_at(order, transaction)
        identity = _order_identity(order)
        identity["unionid"] = unionid
        entitlement = conn.execute(
            """
            SELECT *
            FROM service_period_entitlements
            WHERE tenant_id = 'aicrm'
              AND service_product_id = %s
              AND unionid = %s
            FOR UPDATE
            """,
            (int(product["id"]), unionid),
        ).fetchone()
        before = dict(entitlement) if entitlement else None
        duration_days = int(product.get("duration_days") or 0)
        if entitlement and entitlement_status(entitlement.get("end_at"), entitlement.get("status"), now=now) == "active":
            start_at = parse_datetime(entitlement.get("start_at")) or paid_at
            end_at = _duration_end(parse_datetime(entitlement.get("end_at")) or paid_at, duration_days)
            event_type = "renewed"
            renewal_count = int(entitlement.get("renewal_count") or 0) + 1
        else:
            start_at = paid_at
            end_at = _duration_end(start_at, duration_days)
            event_type = "activated"
            renewal_count = 0 if not entitlement else int(entitlement.get("renewal_count") or 0) + 1
        metadata = {"last_order": order, "payer_name": identity["payer_name"]}
        if entitlement:
            updated = conn.execute(
                """
                UPDATE service_period_entitlements
                SET trade_product_id = %s,
                    external_userid_snapshot = %s,
                    mobile_snapshot = %s,
                    membership_config_id = %s,
                    status = 'active',
                    start_at = %s,
                    end_at = %s,
                    last_order_id = %s,
                    last_out_trade_no = %s,
                    renewal_count = %s,
                    metadata_json = %s::jsonb,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (
                    int(product["trade_product_id"]),
                    identity["external_userid"],
                    identity["mobile"],
                    text(product.get("membership_config_id")),
                    start_at,
                    end_at,
                    order.get("id"),
                    out_trade_no,
                    renewal_count,
                    _jsonb(metadata),
                    int(entitlement["id"]),
                ),
            ).fetchone()
        else:
            updated = conn.execute(
                """
                INSERT INTO service_period_entitlements (
                    tenant_id, service_product_id, trade_product_id, unionid,
                    external_userid_snapshot, mobile_snapshot, membership_config_id,
                    status, start_at, end_at, last_order_id, last_out_trade_no,
                    renewal_count, metadata_json, created_at, updated_at
                )
                VALUES (
                    'aicrm', %s, %s, %s, %s, %s, %s,
                    'active', %s, %s, %s, %s, %s, %s::jsonb,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING *
                """,
                (
                    int(product["id"]),
                    int(product["trade_product_id"]),
                    unionid,
                    identity["external_userid"],
                    identity["mobile"],
                    text(product.get("membership_config_id")),
                    start_at,
                    end_at,
                    order.get("id"),
                    out_trade_no,
                    renewal_count,
                    _jsonb(metadata),
                ),
            ).fetchone()
        event = self._insert_event(
            conn,
            product=product,
            entitlement_id=int(updated["id"]),
            order=order,
            out_trade_no=out_trade_no,
            unionid=unionid,
            event_type=event_type,
            duration_days=duration_days,
            before=before,
            after=dict(updated),
            payload={"order": order, "transaction": transaction, "amount_total": int(order.get("amount_total") or 0)},
        )
        return {"ok": True, "event_type": event_type, "entitlement": self._entitlement_payload(dict(updated)), "event": event}

    def _insert_event(
        self,
        conn: Any,
        *,
        product: dict[str, Any],
        entitlement_id: int | None,
        order: dict[str, Any],
        out_trade_no: str,
        unionid: str,
        event_type: str,
        duration_days: int,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO service_period_events (
                tenant_id, event_id, service_product_id, entitlement_id,
                trade_product_id, order_id, out_trade_no, unionid, event_type,
                duration_days, before_start_at, before_end_at,
                after_start_at, after_end_at, payload_json, created_at
            )
            VALUES (
                'aicrm', %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP
            )
            ON CONFLICT (event_id) DO UPDATE SET event_id = EXCLUDED.event_id
            RETURNING *
            """,
            (
                event_id_for(event_type, out_trade_no or f"{product.get('id')}:{entitlement_id}:{event_type}:{utcnow().timestamp():.6f}"),
                int(product["id"]),
                entitlement_id,
                int(product["trade_product_id"]),
                order.get("id"),
                out_trade_no,
                unionid,
                event_type,
                int(duration_days or 0),
                before.get("start_at") if before else None,
                before.get("end_at") if before else None,
                after.get("start_at") if after else None,
                after.get("end_at") if after else None,
                _jsonb(payload),
            ),
        ).fetchone()
        return dict(row or {})

    def _entitlement_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        status = entitlement_status(row.get("end_at"), row.get("status"))
        return {
            **row,
            "id": text(row.get("id")),
            "service_product_id": text(row.get("service_product_id")),
            "trade_product_id": text(row.get("trade_product_id")),
            "status": status,
            "remaining_days": remaining_days(row.get("end_at")),
            "start_at": isoformat(row.get("start_at")),
            "end_at": isoformat(row.get("end_at")),
        }


_GLOBAL_REPO = InMemoryServicePeriodRepository()


def build_service_period_repository() -> ServicePeriodRepository:
    if production_data_ready():
        return assert_repository_allowed(PostgresServicePeriodRepository(raw_database_url()), capability_owner="service_period")
    return assert_repository_allowed(_GLOBAL_REPO, capability_owner="service_period")


def reset_service_period_fixture_state() -> None:
    global _GLOBAL_REPO
    _GLOBAL_REPO = InMemoryServicePeriodRepository()
