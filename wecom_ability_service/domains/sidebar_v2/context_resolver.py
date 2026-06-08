from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_named_value(*candidates: tuple[str, Any]) -> tuple[str, str]:
    for source, value in candidates:
        text = _text(value)
        if text:
            return text, source
    return "未命名客户", "default"


def resolve_customer_payload(
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
        ("customer.display_name", customer.get("display_name")),
        ("customer.customer_name", customer.get("customer_name")),
        ("customer.remark", customer.get("remark")),
        ("customer.contact.name", contact.get("name")),
        ("binding.display_name", binding.get("display_name")),
        ("binding.customer_name", binding.get("customer_name")),
        ("binding.remark", binding.get("remark")),
        ("contacts.customer_name", contacts_row.get("customer_name")),
        ("contacts.remark", contacts_row.get("remark")),
        ("wecom_external_contact_identity_map.name", identity_row.get("name")),
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
