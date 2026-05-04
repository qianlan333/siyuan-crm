from __future__ import annotations

from typing import Callable

from .crm_nl_router import render_context_reply, route_crm_text
from openclaw_service.services.crm_operator_service import get_customer_context
from openclaw_service.services.customer_chat_context_preflight import run_customer_chat_context_preflight

ContextLoader = Callable[..., dict]
PreflightRunner = Callable[..., dict]
CrmRouter = Callable[..., str]


def handle_text_command(
    text: str,
    *,
    chat_id: str = "",
    context_loader: ContextLoader = get_customer_context,
    preflight_runner: PreflightRunner = run_customer_chat_context_preflight,
    crm_router: CrmRouter = route_crm_text,
) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return _help_text()

    parts = normalized.split(" ")
    command = parts[0].lower().lstrip("/")
    args = parts[1:]

    if command in {"help", "h", "?"}:
        return _help_text()

    if command in {"context", "ctx"}:
        if not args:
            return "请提供 external_userid，例如：/context wmb..."
        context = context_loader(args[0], recent_message_limit=10, timeline_limit=10)
        return render_context_reply(context)

    if command in {"preflight", "pf"}:
        if not args:
            return "请提供 external_userid，例如：/preflight wmb..."
        external_userid = args[0]
        result = preflight_runner(external_userid, recent_message_limit=5, timeline_limit=5)
        return _render_preflight_summary(result)

    if normalized.startswith("/"):
        return _help_text()

    return crm_router(normalized, context_loader=context_loader)


def _render_preflight_summary(result: dict) -> str:
    lines = [
        "Customer Chat Context Preflight",
        f"- ok: {'true' if result.get('ok') else 'false'}",
        f"- external_userid: {result.get('external_userid') or ''}",
        f"- source_status: {result.get('source_status') or 'error'}",
        f"- degraded: {'true' if result.get('degraded') else 'false'}",
        f"- customer_present: {'true' if result.get('customer_present') else 'false'}",
        f"- recent_messages_count: {result.get('recent_messages_count') or 0}",
        f"- recent_timeline_events_count: {result.get('recent_timeline_events_count') or 0}",
    ]
    env = result.get("env") or {}
    missing_required = env.get("missing_required") or []
    if missing_required:
        lines.append(f"- missing_required: {', '.join(missing_required)}")
    warnings = result.get("warnings") or []
    if warnings:
        lines.append(f"- warnings: {' | '.join(str(item) for item in warnings)}")
    if result.get("error"):
        lines.append(f"- error: {result['error']}")
    return "\n".join(lines)


def _help_text() -> str:
    return (
        "OpenClaw 飞书 CRM 助手：\n"
        "/context <external_userid>  查询客户上下文摘要\n"
        "/preflight <external_userid>  运行链路自检\n"
        "/help  查看帮助\n\n"
        "也支持自然语言，例如：\n"
        "看看这个用户 wmb... 什么情况\n"
        "给用户 wmb... 打标签 高意向\n"
        "把用户 wmb... 的标签 高意向 去掉\n"
        "这个用户 wmb... 我该怎么聊"
    )
