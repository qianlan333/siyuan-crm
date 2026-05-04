from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from openclaw_service.integrations.crm.adapters.tags import TagsAdapter
from openclaw_service.integrations.crm.client import CrmApiClient
from openclaw_service.integrations.crm.config import CrmApiConfig
from openclaw_service.services.crm_operator_service import get_customer_context, update_customer_tags

ContextLoader = Callable[..., dict[str, Any]]
TagUpdater = Callable[..., dict[str, Any]]
TagReader = Callable[[], list[dict[str, str]]]

_EXTERNAL_USERID_RE = re.compile(r"\b(wm[A-Za-z0-9_-]+)\b")
_ADD_KEYWORDS = ("打标签", "打上", "加标签", "加上标签", "加上", "添加标签")
_REMOVE_KEYWORDS = ("去标签", "去掉标签", "去掉", "移除标签", "移除", "删除标签", "删除", "删掉标签", "删掉")
_GUIDANCE_KEYWORDS = ("怎么聊", "怎么跟进", "如何跟进", "该怎么聊", "怎么回复", "怎么回", "帮我看看怎么跟进")
_CONTEXT_KEYWORDS = ("看看", "查一下", "查下", "看下", "什么情况", "最近聊了什么", "最近聊了啥", "上下文")


def route_crm_text(
    text: str,
    *,
    context_loader: ContextLoader = get_customer_context,
    tag_updater: TagUpdater = update_customer_tags,
    tag_reader: TagReader | None = None,
) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return "请提供客户 external_userid，例如：wmb..."

    external_userid = extract_external_userid(normalized)
    if not external_userid:
        return "请提供客户 external_userid，例如：wmb..."

    tag_reader = tag_reader or _list_tags

    if _is_remove_intent(normalized):
        return _handle_tag_update(
            normalized,
            external_userid=external_userid,
            action="remove",
            context_loader=context_loader,
            tag_updater=tag_updater,
            tag_reader=tag_reader,
        )

    if _is_add_intent(normalized):
        return _handle_tag_update(
            normalized,
            external_userid=external_userid,
            action="add",
            context_loader=context_loader,
            tag_updater=tag_updater,
            tag_reader=tag_reader,
        )

    context = _safe_get_context(context_loader, external_userid)
    if context.get("_error"):
        return f"查询客户上下文失败：{context['_error']}"

    if _is_guidance_intent(normalized):
        return render_context_reply(context, include_guidance_note=True)

    return render_context_reply(context)


def extract_external_userid(text: str) -> str:
    match = _EXTERNAL_USERID_RE.search(str(text or ""))
    if not match:
        return ""
    return match.group(1).strip()


def render_context_reply(context: dict[str, Any], *, include_guidance_note: bool = False) -> str:
    customer = context.get("customer") or {}
    external_userid = str(customer.get("external_userid") or context.get("external_userid") or "").strip()
    customer_name = str(customer.get("name") or customer.get("customer_name") or "").strip() or "未命名客户"
    tags = [str(tag).strip() for tag in (customer.get("tags") or []) if str(tag).strip()]
    status = str(customer.get("status") or "").strip() or "未知"
    lines = [
        f"客户：{customer_name}",
        f"external_userid：{external_userid or '(empty)'}",
        f"标签：{' / '.join(tags) if tags else '暂无'}",
        f"当前状态：{status}",
        "最近消息：",
    ]
    message_lines = _render_recent_messages(context.get("recent_messages") or [])
    if message_lines:
        lines.extend(message_lines)
    else:
        lines.append("- 暂无最近消息")

    source_status = str(context.get("source_status") or "").strip() or "unknown"
    degraded = bool(context.get("degraded"))
    warnings = [str(item).strip() for item in (context.get("warnings") or []) if str(item).strip()]
    if source_status != "live" or degraded or warnings:
        lines.append(f"提示：source_status={source_status}，degraded={'true' if degraded else 'false'}")
        if warnings:
            lines.append(f"提示：{' | '.join(warnings)}")

    if include_guidance_note:
        lines.append("当前版本只返回上下文，话术生成能力后续接入。")

    return "\n".join(lines)


def _handle_tag_update(
    text: str,
    *,
    external_userid: str,
    action: str,
    context_loader: ContextLoader,
    tag_updater: TagUpdater,
    tag_reader: TagReader,
) -> str:
    tag_name = _extract_tag_name(text, external_userid=external_userid, action=action)
    if not tag_name:
        return "请提供要操作的标签名，例如：给用户 wmb... 打标签 高意向"

    try:
        tag_matches = _find_matching_tags(tag_name, tag_reader())
    except Exception as exc:
        return f"读取标签列表失败：{exc}"

    if not tag_matches:
        return f"未找到标签：{tag_name}"

    if len(tag_matches) > 1:
        choices = " | ".join(
            f"{item['tag_name']}（{item['group_name'] or item['group_id'] or '未分组'}）"
            for item in tag_matches[:5]
        )
        return f"找到多个同名标签，请明确标签名/标签ID：{choices}"

    context = _safe_get_context(context_loader, external_userid)
    if context.get("_error"):
        return f"查询客户上下文失败：{context['_error']}"

    customer = context.get("customer") or {}
    operator_userid = str(customer.get("owner_userid") or "").strip()
    if not operator_userid:
        return f"未识别到客户 {external_userid} 的 owner_userid，暂时无法改标签。"

    tag = tag_matches[0]
    try:
        if action == "add":
            result = tag_updater(external_userid, userid=operator_userid, add_tags=[tag["tag_id"]], remove_tags=[])
            operation = (result.get("results") or {}).get("mark") or {}
            if not result.get("ok") or not operation.get("ok"):
                return _render_tag_update_error(external_userid, tag["tag_name"], operation, default_message="打标签失败")
            return f"已给用户 {external_userid} 打上标签：{tag['tag_name']}"

        result = tag_updater(external_userid, userid=operator_userid, add_tags=[], remove_tags=[tag["tag_id"]])
        operation = (result.get("results") or {}).get("unmark") or {}
        if not result.get("ok") or not operation.get("ok"):
            return _render_tag_update_error(external_userid, tag["tag_name"], operation, default_message="去标签失败")
        return f"已给用户 {external_userid} 去掉标签：{tag['tag_name']}"
    except Exception as exc:
        return f"{'打标签' if action == 'add' else '去标签'}失败：{exc}"


def _safe_get_context(context_loader: ContextLoader, external_userid: str) -> dict[str, Any]:
    try:
        return context_loader(external_userid, recent_message_limit=10, timeline_limit=10)
    except Exception as exc:
        return {"_error": str(exc), "external_userid": external_userid}


def _render_recent_messages(messages: list[dict[str, Any]]) -> list[str]:
    rendered: list[str] = []
    for item in messages[:3]:
        if not isinstance(item, dict):
            continue
        timestamp = (
            str(item.get("send_time") or item.get("created_at") or item.get("occurred_at") or "").strip()
            or "-"
        )
        summary = _extract_message_summary(item)
        rendered.append(f"- {timestamp} {summary}")
    return rendered


def _extract_message_summary(message: dict[str, Any]) -> str:
    for key in ("content", "text", "message", "summary", "body"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")[:80]

    content = message.get("content")
    if isinstance(content, dict):
        for key in ("text", "content", "body"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().replace("\n", " ")[:80]

    msgtype = str(message.get("msgtype") or message.get("message_type") or "消息").strip()
    return f"[{msgtype}]"


def _is_add_intent(text: str) -> bool:
    return any(keyword in text for keyword in _ADD_KEYWORDS)


def _is_remove_intent(text: str) -> bool:
    return any(keyword in text for keyword in _REMOVE_KEYWORDS)


def _is_guidance_intent(text: str) -> bool:
    return any(keyword in text for keyword in _GUIDANCE_KEYWORDS)


def _looks_like_context_intent(text: str) -> bool:
    return any(keyword in text for keyword in _CONTEXT_KEYWORDS)


def _extract_tag_name(text: str, *, external_userid: str, action: str) -> str:
    working = str(text or "").replace(external_userid, " ").strip()
    working = re.sub(r"[，。！？,.!?]+$", "", working).strip()

    if action == "add":
        for keyword in _ADD_KEYWORDS:
            if keyword in working:
                tag_name = working.split(keyword, 1)[1].strip()
                return _clean_tag_name(tag_name)
        return ""

    pattern = re.compile(r"标签\s*(?P<tag>.+?)\s*(去掉|移除|删除|删掉)\s*$")
    match = pattern.search(working)
    if match:
        return _clean_tag_name(match.group("tag"))

    for keyword in _REMOVE_KEYWORDS:
        if keyword in working:
            prefix, suffix = working.split(keyword, 1)
            tag_name = suffix.strip() or prefix.strip()
            return _clean_tag_name(tag_name)
    return ""


def _clean_tag_name(tag_name: str) -> str:
    cleaned = str(tag_name or "").strip()
    cleaned = re.sub(r"^(给|把|用户|这个用户|该用户|的|标签)+", "", cleaned).strip()
    cleaned = re.sub(r"[，。！？,.!?]+$", "", cleaned).strip()
    return cleaned


def _find_matching_tags(tag_name: str, tags: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_target = str(tag_name or "").strip()
    if not normalized_target:
        return []

    direct_id_matches = [item for item in tags if item.get("tag_id") == normalized_target]
    if direct_id_matches:
        return direct_id_matches

    return [item for item in tags if item.get("tag_name") == normalized_target]


def _list_tags() -> list[dict[str, str]]:
    config = CrmApiConfig.from_env()
    adapter = TagsAdapter(CrmApiClient(config))
    return adapter.list_tags()


def _render_tag_update_error(
    external_userid: str,
    tag_name: str,
    operation: dict[str, Any],
    *,
    default_message: str,
) -> str:
    error_message = str(operation.get("error") or default_message).strip()
    return f"{default_message}：用户 {external_userid}，标签 {tag_name}，原因：{error_message}"
