from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from aicrm_next.commerce.application import ListProductsQuery
from aicrm_next.customer_read_model.application import GetCustomerContextQuery, _close_repository
from aicrm_next.customer_read_model.dto import CustomerContextRequest
from aicrm_next.customer_read_model.repo import CustomerReadRepository, build_customer_live_source_repository
from aicrm_next.media_library.application import GetImageThumbnailQuery, GetMediaItemQuery, ListMediaItemsQuery
from aicrm_next.media_library.variants import decode_image_base64
from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import raw_database_url
from aicrm_next.shared.signed_context import append_ctx_query, build_sidebar_product_context_token

MODULES = ["profile", "questionnaires", "products", "orders", "materials", "other_staff_messages"]
ORDER_STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "refund_processing": "退款处理中",
    "partial_refunded": "部分退款",
    "full_refunded": "全额退款",
    "closed": "已关闭",
    "failed": "支付失败",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _limit(value: Any, *, default: int = 50, maximum: int = 200) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _format_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    beijing = timezone(timedelta(hours=8))
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(beijing).strftime("%Y-%m-%d %H:%M")
        return value.strftime("%Y-%m-%d %H:%M")
    value_text = _text(value).replace("T", " ")
    if not value_text:
        return ""
    try:
        parsed = datetime.fromisoformat(value_text)
        if parsed.tzinfo is not None:
            return parsed.astimezone(beijing).strftime("%Y-%m-%d %H:%M")
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value_text[:16]


def _money_label(amount_total: Any) -> str:
    cents = _int(amount_total)
    yuan = cents / 100
    if cents % 100 == 0:
        return f"¥{int(yuan)}"
    return f"¥{yuan:.2f}"


def _normalize_mobile(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _diagnostics(**extra: Any) -> dict[str, Any]:
    return {
        "source_status": "next_read_model",
        "read_model_status": "primary",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "degraded": False,
        **extra,
    }


def _with_route_owner(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("route_owner", "ai_crm_next")
    payload.setdefault("fallback_used", False)
    payload.setdefault("source_status", "next_read_model")
    payload.setdefault("read_model_status", "primary")
    payload.setdefault("degraded", False)
    return payload


def _database_url() -> str:
    url = raw_database_url()
    if not url:
        raise ContractError("DATABASE_URL is required for sidebar v2 read model")
    return url


class SidebarV2SqlRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine(database_url=_database_url())

    def get_profile_fields(self, external_userid: str) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT external_userid, source, industry, industry_description,
                   needs_blockers_followup, updated_by, updated_at
            FROM sidebar_customer_profile_fields
            WHERE external_userid = :external_userid
            """,
            {"external_userid": external_userid},
        )

    def get_workflow_title_for_customer(self, external_userid: str) -> str:
        row = self._one(
            """
            SELECT COALESCE(NULLIF(w.workflow_name, ''), NULLIF(p.program_name, ''), NULLIF(c.channel_name, '')) AS title
            FROM automation_member m
            LEFT JOIN automation_channel c ON c.id = m.source_channel_id
            LEFT JOIN automation_program p ON p.id = c.program_id
            LEFT JOIN wecom_customer_acquisition_links l ON l.automation_channel_id = c.id
            LEFT JOIN automation_workflow w ON w.id = l.workflow_id
            WHERE m.external_contact_id = :external_userid
            ORDER BY m.updated_at DESC, m.id DESC
            LIMIT 1
            """,
            {"external_userid": external_userid},
        )
        return _text((row or {}).get("title"))

    def get_contact_snapshot(self, external_userid: str) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT external_userid, customer_name, owner_userid, remark, description
            FROM contacts
            WHERE external_userid = :external_userid
            """,
            {"external_userid": external_userid},
        )

    def get_external_identity_snapshot(self, external_userid: str) -> dict[str, Any] | None:
        return self._one(
            """
            SELECT external_userid, follow_user_userid, name, unionid, openid, status
            FROM wecom_external_contact_identity_map
            WHERE external_userid = :external_userid
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            {"external_userid": external_userid},
        )

    def get_contact_binding_status(self, external_userid: str) -> dict[str, Any]:
        row = self._one(
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
            WHERE b.external_userid = :external_userid
            """,
            {"external_userid": external_userid},
        )
        if not row:
            return {"is_bound": False, "external_userid": external_userid}
        return {
            "is_bound": True,
            "external_userid": _text(row.get("external_userid")),
            "person_id": row.get("person_id"),
            "mobile": _text(row.get("mobile")),
            "third_party_user_id": _text(row.get("third_party_user_id")),
            "first_bound_by_userid": _text(row.get("first_bound_by_userid")),
            "first_owner_userid": _text(row.get("first_owner_userid")),
            "last_owner_userid": _text(row.get("last_owner_userid")),
            "owner_userid": _text(row.get("last_owner_userid") or row.get("first_owner_userid")),
            "created_at": _text(row.get("created_at")),
            "updated_at": _text(row.get("updated_at")),
        }

    def get_bindable_wechat_pay_order_mobile(self, external_userid: str) -> dict[str, Any] | None:
        rows = self._all(
            """
            WITH target(external_userid) AS (VALUES (:external_userid)),
            identity_openids AS (
                SELECT m.openid
                FROM wecom_external_contact_identity_map m
                JOIN target t ON m.external_userid = t.external_userid
                WHERE COALESCE(m.openid, '') <> ''
            ),
            identity_unionids AS (
                SELECT m.unionid
                FROM wecom_external_contact_identity_map m
                JOIN target t ON m.external_userid = t.external_userid
                WHERE COALESCE(m.unionid, '') <> ''
            ),
            matching_orders AS (
                SELECT mobile_snapshot, userid_snapshot, paid_at, created_at, id
                FROM wechat_pay_orders
                WHERE COALESCE(mobile_snapshot, '') <> ''
                  AND (status = 'paid' OR trade_state = 'SUCCESS')
                  AND (
                    (COALESCE(external_userid, '') <> '' AND external_userid = (SELECT external_userid FROM target))
                    OR (COALESCE(payer_openid, '') <> '' AND payer_openid IN (SELECT openid FROM identity_openids))
                    OR (COALESCE(unionid, '') <> '' AND unionid IN (SELECT unionid FROM identity_unionids))
                  )
            )
            SELECT
                mobile_snapshot,
                MAX(COALESCE(NULLIF(userid_snapshot, ''), '')) AS userid_snapshot,
                COUNT(*) AS order_count,
                MAX(COALESCE(paid_at, created_at)) AS latest_order_at
            FROM matching_orders
            GROUP BY mobile_snapshot
            ORDER BY latest_order_at DESC, mobile_snapshot ASC
            LIMIT 2
            """,
            {"external_userid": external_userid},
        )
        return rows[0] if len(rows) == 1 else None

    def list_customer_wechat_pay_orders(self, *, external_userid: str, mobile: str = "", limit: int = 20) -> list[dict[str, Any]]:
        return self._all(
            """
            WITH target(external_userid, mobile) AS (VALUES (:external_userid, :mobile)),
            bound_mobiles AS (
                SELECT p.mobile
                FROM external_contact_bindings b
                JOIN people p ON p.id = b.person_id
                JOIN target t ON b.external_userid = t.external_userid
                WHERE COALESCE(p.mobile, '') <> ''
                UNION
                SELECT mobile FROM target WHERE COALESCE(mobile, '') <> ''
            ),
            identity_openids AS (
                SELECT m.openid
                FROM wecom_external_contact_identity_map m
                JOIN target t ON m.external_userid = t.external_userid
                WHERE COALESCE(m.openid, '') <> ''
            ),
            identity_unionids AS (
                SELECT m.unionid
                FROM wecom_external_contact_identity_map m
                JOIN target t ON m.external_userid = t.external_userid
                WHERE COALESCE(m.unionid, '') <> ''
            )
            SELECT
                id, out_trade_no, transaction_id, product_code,
                COALESCE(NULLIF(product_name, ''), product_code) AS product_name,
                amount_total, currency, external_userid AS order_external_userid,
                mobile_snapshot, payer_openid, unionid, status, trade_state,
                refunded_amount_total, refund_status, paid_at, created_at
            FROM wechat_pay_orders
            WHERE (
                (COALESCE(external_userid, '') <> '' AND external_userid = (SELECT external_userid FROM target))
                OR (COALESCE(mobile_snapshot, '') <> '' AND mobile_snapshot IN (SELECT mobile FROM bound_mobiles))
                OR (COALESCE(payer_openid, '') <> '' AND payer_openid IN (SELECT openid FROM identity_openids))
                OR (COALESCE(unionid, '') <> '' AND unionid IN (SELECT unionid FROM identity_unionids))
            )
            ORDER BY COALESCE(paid_at, created_at) DESC, id DESC
            LIMIT :limit
            """,
            {"external_userid": external_userid, "mobile": mobile, "limit": _limit(limit, default=20, maximum=100)},
        )

    def list_questionnaire_answers(self, *, external_userid: str, mobile: str = "") -> list[dict[str, Any]]:
        normalized_mobile = _normalize_mobile(mobile)
        return self._all(
            """
            SELECT
                s.id AS submission_id,
                q.id AS questionnaire_id,
                COALESCE(NULLIF(q.title, ''), NULLIF(q.name, ''), q.slug, '未命名问卷') AS questionnaire_title,
                s.submitted_at,
                a.question_id,
                COALESCE(NULLIF(a.question_title_snapshot, ''), '未命名问题') AS question,
                a.selected_option_texts_snapshot,
                a.text_value
            FROM questionnaire_submissions s
            LEFT JOIN questionnaires q ON q.id = s.questionnaire_id
            LEFT JOIN questionnaire_submission_answers a ON a.submission_id = s.id
            WHERE (
                s.external_userid = :external_userid
                OR (
                    COALESCE(s.external_userid, '') = ''
                    AND :mobile <> ''
                    AND regexp_replace(COALESCE(s.mobile_snapshot, ''), '[^0-9]', '', 'g') = :mobile
                )
            )
            ORDER BY s.submitted_at DESC, s.id DESC, a.id ASC
            """,
            {"external_userid": external_userid, "mobile": normalized_mobile},
        )

    def list_other_staff_messages(self, external_userid: str, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                   msgtype, content, send_time, raw_payload, created_at
            FROM archived_messages
            WHERE external_userid = :external_userid
            ORDER BY send_time ASC, id ASC
            LIMIT :limit
            """,
            {"external_userid": external_userid, "limit": _limit(limit, default=200, maximum=500)},
        )

    def owner_names(self, userids: set[str]) -> dict[str, str]:
        normalized = sorted({_text(value) for value in userids if _text(value)})
        if not normalized:
            return {}
        rows = self._all(
            """
            SELECT userid, display_name
            FROM owner_role_map
            WHERE userid = ANY(:userids)
            """,
            {"userids": normalized},
        )
        return {_text(row.get("userid")): _text(row.get("display_name")) for row in rows if _text(row.get("userid"))}

    def group_names(self, chat_ids: set[str]) -> dict[str, str]:
        normalized = sorted({_text(value) for value in chat_ids if _text(value)})
        if not normalized:
            return {}
        rows = self._all(
            """
            SELECT chat_id, group_name
            FROM group_chats
            WHERE chat_id = ANY(:chat_ids)
            """,
            {"chat_ids": normalized},
        )
        return {_text(row.get("chat_id")): _text(row.get("group_name")) for row in rows if _text(row.get("chat_id"))}

    def _one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        rows = self._all(sql, params)
        return rows[0] if rows else None

    def _all(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings()]


def _first_named_value(*candidates: tuple[str, Any]) -> tuple[str, str]:
    for source, value in candidates:
        value_text = _text(value)
        if value_text:
            return value_text, source
    return "未命名客户", "default"


def _resolve_customer_payload(
    *,
    context: dict[str, Any],
    binding: dict[str, Any],
    contacts: dict[str, Any] | None,
    identity_map: dict[str, Any] | None,
    external_userid: str,
    owner_userid: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    customer = dict(context.get("customer") or {})
    customer_binding = dict(customer.get("binding") or {})
    contact = dict(customer.get("contact") or {})
    contacts_row = dict(contacts or {})
    identity_row = dict(identity_map or {})
    display_name, display_name_source = _first_named_value(
        ("contacts.remark", contacts_row.get("remark")),
        ("contacts.customer_name", contacts_row.get("customer_name")),
        ("wecom_external_contact_identity_map.name", identity_row.get("name")),
        ("customer.display_name", customer.get("display_name")),
        ("customer.customer_name", customer.get("customer_name")),
        ("customer.remark", customer.get("remark")),
        ("customer.contact.name", contact.get("name")),
        ("binding.display_name", binding.get("display_name")),
        ("binding.customer_name", binding.get("customer_name")),
        ("binding.remark", binding.get("remark")),
    )
    resolved_owner = (
        _text(owner_userid)
        or _text(customer.get("owner_userid"))
        or _text(binding.get("owner_userid"))
        or _text(binding.get("last_owner_userid"))
        or _text(contacts_row.get("owner_userid"))
        or _text(identity_row.get("follow_user_userid"))
    )
    mobile = _text(binding.get("mobile")) or _text(customer.get("mobile")) or _text(customer_binding.get("mobile"))
    is_bound = bool(binding.get("is_bound")) or bool(customer_binding.get("is_bound")) or bool(mobile)
    payload = {
        "display_name": display_name,
        "avatar_text": display_name[:1] if display_name else "",
        "mobile": mobile,
        "is_bound": is_bound,
        "external_userid": _text(external_userid),
        "owner_userid": resolved_owner,
    }
    context_binding = dict(context.get("binding") or {})
    if not binding:
        binding_source = "none"
    elif context_binding and binding == context_binding:
        binding_source = "context.binding"
    else:
        binding_source = "fresh_binding_status"
    diagnostics = {
        "display_name_source": display_name_source,
        "binding_source": binding_source,
    }
    return payload, diagnostics


class SidebarWorkbenchReadModel:
    def __init__(
        self,
        repo: SidebarV2SqlRepository | None = None,
        *,
        context_query: GetCustomerContextQuery | None = None,
        live_source_repo: CustomerReadRepository | None = None,
    ) -> None:
        self._repo = repo or SidebarV2SqlRepository()
        self._context_query = context_query or GetCustomerContextQuery()
        self._live_source_repo = live_source_repo

    def __call__(self, *, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
        normalized_external = _text(external_userid)
        if not normalized_external:
            raise ValueError("external_userid is required")
        normalized_owner = _text(owner_userid)
        context, context_diagnostics = self._context(normalized_external)
        contact = self._repo.get_contact_snapshot(normalized_external) or {}
        identity = self._repo.get_external_identity_snapshot(normalized_external) or {}
        profile = self._repo.get_profile_fields(normalized_external) or {}
        binding = self._repo.get_contact_binding_status(normalized_external)
        if not context.get("customer") and not contact and not identity and not profile and not binding.get("is_bound"):
            raise NotFoundError("customer not found")
        customer, resolution = _resolve_customer_payload(
            context=context,
            binding=binding,
            contacts=contact,
            identity_map=identity,
            external_userid=normalized_external,
            owner_userid=normalized_owner,
        )
        self._overlay_paid_order_mobile(customer, diagnostics := {**context_diagnostics, **resolution})
        sidebar_context = dict((context.get("customer") or {}).get("sidebar_context") or {})
        workflow_title = (
            _text(sidebar_context.get("workflow_title"))
            or _text(sidebar_context.get("sop_title"))
            or _text(sidebar_context.get("program_name"))
            or self._repo.get_workflow_title_for_customer(normalized_external)
        )
        payload = {
            "ok": True,
            "customer": customer,
            "workflow": {"title": workflow_title},
            "profile": self._profile_payload(normalized_external, context, persisted=profile),
            "modules": list(MODULES),
            "diagnostics": diagnostics,
        }
        return _with_route_owner(payload)

    def customer_with_overlay(self, *, external_userid: str, owner_userid: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self(external_userid=external_userid, owner_userid=owner_userid)
        return dict(payload.get("customer") or {}), dict(payload.get("diagnostics") or {})

    def _context(self, external_userid: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            payload = self._context_query(
                CustomerContextRequest(external_userid=external_userid, recent_message_limit=20, timeline_limit=20)
            )
            if (payload or {}).get("ok", True) and payload.get("customer"):
                return dict(payload or {}), {"context_source_status": payload.get("source_status") or "next_read_model"}
        except Exception:
            pass
        repo = self._live_source_repo
        owned_repo = repo is None
        try:
            repo = repo or build_customer_live_source_repository()
            customer = repo.get_customer(external_userid)
            if not customer:
                return {}, {"context_source_status": "missing"}
            messages = repo.list_recent_messages(external_userid, limit=20)
            timeline = repo.list_timeline(external_userid, limit=20)
            return (
                {
                    "ok": True,
                    "customer": customer,
                    "binding": dict(customer.get("binding") or {}),
                    "messages": messages,
                    "timeline": {"items": timeline},
                },
                {"context_source_status": "live_source"},
            )
        except Exception as exc:
            return {}, {"context_source_status": "error", "context_error": str(exc).strip() or exc.__class__.__name__}
        finally:
            if owned_repo:
                _close_repository(repo)

    def _overlay_paid_order_mobile(self, customer: dict[str, Any], diagnostics: dict[str, Any]) -> None:
        if customer.get("is_bound") or _text(customer.get("mobile")):
            diagnostics["paid_order_mobile_binding"] = {"ok": True, "status": "already_bound"}
            return
        candidate = self._repo.get_bindable_wechat_pay_order_mobile(_text(customer.get("external_userid")))
        mobile = _text((candidate or {}).get("mobile_snapshot"))
        if not mobile:
            diagnostics["paid_order_mobile_binding"] = {"ok": True, "status": "no_single_candidate"}
            return
        customer["mobile"] = mobile
        customer["is_bound"] = True
        diagnostics["paid_order_mobile_binding"] = {"ok": True, "status": "read_overlay"}

    def _profile_payload(self, external_userid: str, context: dict[str, Any], *, persisted: dict[str, Any] | None = None) -> dict[str, str]:
        persisted = persisted if persisted is not None else self._repo.get_profile_fields(external_userid) or {}
        if persisted:
            return {
                "source": _text(persisted.get("source")),
                "industry": _text(persisted.get("industry")),
                "industry_description": _text(persisted.get("industry_description")),
                "needs_blockers_followup": _text(persisted.get("needs_blockers_followup")),
            }
        sidebar_context = dict((context.get("customer") or {}).get("sidebar_context") or {})
        return {
            "source": _text(sidebar_context.get("source")),
            "industry": _text(sidebar_context.get("industry")),
            "industry_description": _text(sidebar_context.get("industry_description")),
            "needs_blockers_followup": _text(sidebar_context.get("needs_blockers_followup")),
        }


class SidebarQuestionnaireReadModel:
    def __init__(
        self,
        repo: SidebarV2SqlRepository | None = None,
        *,
        context_query: GetCustomerContextQuery | None = None,
        live_source_repo: CustomerReadRepository | None = None,
    ) -> None:
        self._repo = repo or SidebarV2SqlRepository()
        self._context_query = context_query
        self._live_source_repo = live_source_repo

    def __call__(self, *, external_userid: str) -> dict[str, Any]:
        customer, diagnostics = SidebarWorkbenchReadModel(
            self._repo,
            context_query=self._context_query,
            live_source_repo=self._live_source_repo,
        ).customer_with_overlay(external_userid=external_userid)
        rows = self._repo.list_questionnaire_answers(external_userid=_text(external_userid), mobile=_text(customer.get("mobile")))
        return _with_route_owner({"ok": True, "questionnaires": self._group(rows), "diagnostics": diagnostics})

    def _group(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        order: list[tuple[str, str, str]] = []
        for row in rows:
            submission_id = _text(row.get("submission_id"))
            questionnaire_id = _text(row.get("questionnaire_id"))
            submitted_at = _format_time(row.get("submitted_at"))
            title = _text(row.get("questionnaire_title")) or "未命名问卷"
            key = (submission_id or questionnaire_id, title, submitted_at)
            if key not in grouped:
                order.append(key)
                grouped[key] = {
                    "id": submission_id or questionnaire_id or f"q_{len(order)}",
                    "title": title,
                    "submitted_at": submitted_at,
                    "answer_count": 0,
                    "total_count": 0,
                    "answers": [],
                }
            answer = self._answer_text(row)
            if _text(row.get("question")) or answer:
                grouped[key]["answers"].append({"question": _text(row.get("question")) or "未命名问题", "answer": answer})
                grouped[key]["answer_count"] += 1
                grouped[key]["total_count"] += 1
        return [grouped[key] for key in order]

    def _answer_text(self, row: dict[str, Any]) -> str:
        selected = _json(row.get("selected_option_texts_snapshot"), [])
        if isinstance(selected, list) and selected:
            return "、".join(_text(item) for item in selected if _text(item))
        return _text(row.get("text_value"))


class SidebarMaterialReadModel:
    def __call__(self, *, material_type: str, limit: int = 50) -> dict[str, Any]:
        normalized_type = _text(material_type)
        safe_limit = _limit(limit, default=50, maximum=200)
        kind_map = {"image": "image", "mini": "miniprogram", "pdf": "attachment"}
        if normalized_type not in kind_map:
            raise ValueError("type must be image, mini, or pdf")
        payload = ListMediaItemsQuery(kind_map[normalized_type])(limit=safe_limit, offset=0, filters={"enabled_only": True})
        rows = list(payload.get("items") or [])
        return _with_route_owner({"ok": True, "materials": [self._material_item(dict(item), normalized_type) for item in rows]})

    def thumbnail(self, image_id: int) -> dict[str, Any]:
        original = self._original_image_payload(image_id)
        if original:
            return original
        try:
            payload = GetImageThumbnailQuery()(str(int(image_id)), 160)
        except NotFoundError:
            raise LookupError("image not found") from None
        except ContractError as exc:
            raise ValueError("invalid image data") from exc
        thumbnail = dict(payload.get("thumbnail") or {})
        return {
            "body": thumbnail.get("bytes") or b"",
            "mime_type": _text(thumbnail.get("mime_type")) or "image/png",
        }

    def _original_image_payload(self, image_id: int) -> dict[str, Any] | None:
        try:
            item = dict(GetMediaItemQuery("image")(str(int(image_id)), include_data=True).get("item") or {})
        except NotFoundError:
            raise LookupError("image not found") from None
        except ContractError as exc:
            raise ValueError("invalid image data") from exc
        except Exception:
            return None
        source_url = _text(item.get("source_url"))
        if _text(item.get("source")) == "url" and source_url:
            return None
        data_base64 = _text(item.get("data_base64"))
        if not data_base64:
            return None
        try:
            return {
                "body": decode_image_base64(data_base64),
                "mime_type": _text(item.get("mime_type")) or "image/png",
            }
        except ContractError as exc:
            raise ValueError("invalid image data") from exc

    def _material_item(self, item: dict[str, Any], material_type: str) -> dict[str, Any]:
        item_id = _int(item.get("id"))
        thumbnail_url = ""
        if material_type == "image":
            title = _text(item.get("name")) or _text(item.get("file_name")) or "未命名图片素材"
            label = "图"
            if item_id:
                thumbnail_url = f"/api/sidebar/v2/materials/image/{item_id}/thumbnail"
        elif material_type == "mini":
            title = _text(item.get("title")) or _text(item.get("name")) or "未命名小程序素材"
            label = "小"
        else:
            title = _text(item.get("name")) or _text(item.get("file_name")) or "未命名 PDF 素材"
            label = "PDF"
        tags = [_text(tag) for tag in list(item.get("tags") or []) if _text(tag)][:3]
        return {
            "id": item_id,
            "type": material_type,
            "title": title,
            "thumbnail_label": label,
            "thumbnail_url": thumbnail_url,
            "tags": tags,
            "enabled": bool(item.get("enabled", True)),
        }


class SidebarOtherStaffMessagesReadModel:
    def __init__(self, repo: SidebarV2SqlRepository | None = None) -> None:
        self._repo = repo or SidebarV2SqlRepository()

    def __call__(self, *, external_userid: str, current_userid: str = "", limit: int = 20) -> dict[str, Any]:
        if not _text(external_userid):
            raise ValueError("external_userid is required")
        safe_limit = _limit(limit, default=20, maximum=100)
        rows = self._repo.list_other_staff_messages(_text(external_userid), limit=200)
        current_staff = {_text(current_userid)}
        filtered: list[dict[str, Any]] = []
        for row in rows:
            sender = _text(row.get("sender"))
            msgtype = _text(row.get("msgtype"))
            if not sender or sender == _text(external_userid) or sender in current_staff or msgtype not in {"text", "image"}:
                continue
            filtered.append(row)
        selected = filtered[-safe_limit:]
        staff_names = self._repo.owner_names({_text(item.get("sender")) for item in selected})
        chat_ids = {self._chat_id(item) for item in selected}
        group_names = self._repo.group_names(chat_ids)
        return _with_route_owner({"ok": True, "messages": [self._message_item(item, staff_names, group_names) for item in selected]})

    def _chat_id(self, message: dict[str, Any]) -> str:
        payload = _json(message.get("raw_payload"), {})
        decrypted = dict(payload.get("decrypted_message") or {}) if isinstance(payload, dict) else {}
        return _text(message.get("chat_id")) or _text(message.get("roomid")) or _text(decrypted.get("roomid"))

    def _message_item(self, message: dict[str, Any], staff_names: dict[str, str], group_names: dict[str, str]) -> dict[str, Any]:
        sender = _text(message.get("sender"))
        msgtype = _text(message.get("msgtype"))
        chat_id = self._chat_id(message)
        scene = "group" if _text(message.get("chat_type")) == "group" or chat_id else "private"
        scene_label = group_names.get(chat_id) or ("群聊" if scene == "group" else "私聊")
        staff_name = staff_names.get(sender) or sender
        return {
            "id": _text(message.get("id")) or _text(message.get("msgid")),
            "type": msgtype,
            "content": _text(message.get("content")) if msgtype == "text" else "发送了图片",
            "send_time": _format_time(message.get("send_time")),
            "scene": scene,
            "scene_label": scene_label,
            "staff_name": staff_name,
            "staff_userid": sender,
            "sender_label": staff_name,
        }


class SidebarCommerceReadModel:
    def __init__(
        self,
        repo: SidebarV2SqlRepository | None = None,
        *,
        context_query: GetCustomerContextQuery | None = None,
        live_source_repo: CustomerReadRepository | None = None,
    ) -> None:
        self._repo = repo or SidebarV2SqlRepository()
        self._context_query = context_query
        self._live_source_repo = live_source_repo

    def products(self, *, external_userid: str, owner_userid: str = "", bind_by_userid: str = "") -> dict[str, Any]:
        normalized_external = _text(external_userid)
        if not normalized_external:
            raise ValueError("external_userid is required")
        diagnostics = {"context_source": "sidebar_product_link"}
        context_token = ""
        context_status = "missing"
        try:
            context_token = build_sidebar_product_context_token(
                external_userid=normalized_external,
                owner_userid=_text(owner_userid),
                bind_by_userid=_text(bind_by_userid) or _text(owner_userid),
            )
            context_status = "signed"
        except Exception as exc:
            context_status = "sign_failed"
            diagnostics["context_error"] = str(exc).strip() or exc.__class__.__name__
        diagnostics["context_status"] = context_status
        rows = list(ListProductsQuery()(limit=100, offset=0).get("items") or [])
        active = [dict(item) for item in rows if bool(item.get("enabled")) and _text(item.get("status")) == "active"]
        return _with_route_owner(
            {
                "ok": True,
                "products": [self._product_item(item, context_token=context_token, context_status=context_status) for item in active],
                "diagnostics": diagnostics,
            }
        )

    def orders(self, *, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
        customer, diagnostics = SidebarWorkbenchReadModel(
            self._repo,
            context_query=self._context_query,
            live_source_repo=self._live_source_repo,
        ).customer_with_overlay(
            external_userid=external_userid,
            owner_userid=owner_userid,
        )
        rows = self._repo.list_customer_wechat_pay_orders(
            external_userid=_text(external_userid),
            mobile=_text(customer.get("mobile")),
            limit=20,
        )
        return _with_route_owner(
            {
                "ok": True,
                "orders": [self._order_item(dict(item)) for item in rows],
                "customer": customer,
                "diagnostics": diagnostics,
            }
        )

    def _product_item(self, item: dict[str, Any], *, context_token: str = "", context_status: str = "") -> dict[str, Any]:
        product_code = _text(item.get("product_code"))
        product_id = _text(item.get("id"))
        public_path = f"/p/{product_code}" if product_code else ""
        checkout_path = f"/pay/{product_code}" if product_code else ""
        product_url = append_ctx_query(public_path, context_token) if context_token else public_path
        checkout_url = append_ctx_query(checkout_path, context_token) if context_token else checkout_path
        return {
            "id": product_code or product_id,
            "title": _text(item.get("title") or item.get("name")) or product_code or "未命名商品",
            "price_label": _money_label(item.get("price_cents") or item.get("amount_total")),
            "product_url": product_url,
            "checkout_url": checkout_url,
            "context_source": "sidebar_product_link" if context_token else "",
            "context_status": context_status,
        }

    def _order_item(self, order: dict[str, Any]) -> dict[str, Any]:
        order_id = _text(order.get("id"))
        product_code = _text(order.get("product_code"))
        product_name = _text(order.get("product_name")) or product_code or "未命名商品"
        status = self._order_status(order)
        return {
            "id": _text(order.get("out_trade_no")) or order_id,
            "order_id": order_id,
            "title": product_name,
            "amount_label": _money_label(order.get("amount_total")),
            "status_label": ORDER_STATUS_LABELS.get(status, status),
            "paid_at": _format_time(order.get("paid_at") or order.get("created_at")),
            "detail_url": f"/admin/wechat-pay/transactions/{order_id}" if order_id else "",
        }

    def _order_status(self, order: dict[str, Any]) -> str:
        amount_total = _int(order.get("amount_total"))
        refunded = _int(order.get("refunded_amount_total"))
        refund_status = _text(order.get("refund_status"))
        status = _text(order.get("status"))
        trade_state = _text(order.get("trade_state"))
        if refund_status == "full_refunded" or (amount_total > 0 and refunded >= amount_total):
            return "full_refunded"
        if refund_status == "partial_refunded" or refunded > 0:
            return "partial_refunded"
        if status == "paid" or trade_state == "SUCCESS":
            return "paid"
        if status in {"closed", "cancelled"} or trade_state in {"CLOSED", "REVOKED"}:
            return "closed"
        if status in {"failed", "error"} or trade_state == "PAYERROR":
            return "failed"
        return "pending"
