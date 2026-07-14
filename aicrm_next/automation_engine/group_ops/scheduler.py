from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aicrm_next.shared.errors import ContractError

from .domain import build_node_group_message_content, clean_text, derive_node_scheduled_time
from .external_effects import GROUP_OPS_MESSAGE_LOOPBACK, plan_group_ops_external_effect
from .integration_gateway import resolve_group_ops_content_package_materials
from .repo import GroupOpsRepository, build_group_ops_repository


DEFAULT_GROUP_OPS_TIMEZONE = "Asia/Shanghai"


def _business_timezone() -> ZoneInfo:
    name = clean_text(os.getenv("AICRM_GROUP_OPS_TIMEZONE")) or DEFAULT_GROUP_OPS_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_GROUP_OPS_TIMEZONE)


def _parse_datetime(value: Any, *, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = clean_text(value).replace("Z", "+00:00")
        if not text:
            return fallback
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _due_at_for_group(*, plan: dict[str, Any], node: dict[str, Any], group: dict[str, Any], business_tz: ZoneInfo | None = None) -> datetime:
    tz = business_tz or _business_timezone()
    fallback_start = _parse_datetime(plan.get("created_at"), fallback=datetime.now(timezone.utc))
    group_start = _parse_datetime(group.get("created_at"), fallback=fallback_start)
    scheduled_time = derive_node_scheduled_time(node)
    if not scheduled_time:
        raise ContractError("group ops node scheduled_time must use HH:MM")
    hour, minute = [int(item) for item in scheduled_time.split(":", 1)]
    day_index = max(1, int(node.get("day_index") or 1))
    start_anchor_local = group_start.astimezone(tz)
    due_date = start_anchor_local.date() + timedelta(days=day_index - 1)
    return datetime.combine(due_date, time(hour=hour, minute=minute), tzinfo=tz)


def _minute_key(value: datetime) -> str:
    return value.replace(second=0, microsecond=0).astimezone(timezone.utc).strftime("%Y%m%dT%H%MZ")


def _stable_hash(value: Any, *, length: int = 12) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:length]


def _content_hash(payload: dict[str, Any]) -> str:
    payload_for_hash = dict(payload or {})
    payload_for_hash.pop("chat_ids", None)
    return _stable_hash(payload_for_hash, length=16)


@dataclass
class GroupOpsSchedulerSummary:
    scanned_at: str
    group_ops_scanned_plans: int = 0
    group_ops_due_nodes: int = 0
    group_ops_enqueued_jobs: int = 0
    group_ops_external_effect_jobs: int = 0
    group_ops_reused_external_effect_jobs: int = 0
    group_ops_skipped_future: int = 0
    group_ops_skipped_duplicate: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "group_ops_scanned_plans": self.group_ops_scanned_plans,
            "group_ops_due_nodes": self.group_ops_due_nodes,
            "group_ops_enqueued_jobs": self.group_ops_enqueued_jobs,
            "group_ops_external_effect_jobs": self.group_ops_external_effect_jobs,
            "group_ops_reused_external_effect_jobs": self.group_ops_reused_external_effect_jobs,
            "group_ops_skipped_future": self.group_ops_skipped_future,
            "group_ops_skipped_duplicate": self.group_ops_skipped_duplicate,
            "errors": self.errors,
        }


class GroupOpsDueScheduler:
    def __init__(
        self,
        *,
        repo: GroupOpsRepository | None = None,
    ) -> None:
        self._repo = repo

    def run_due(self, *, now: datetime | None = None, operator: str = "automation_ops_scheduler") -> dict[str, Any]:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        summary = GroupOpsSchedulerSummary(scanned_at=current_time.isoformat())
        business_tz = _business_timezone()
        repo = self._repo or build_group_ops_repository()
        if repo is None:
            summary.errors.append({"scope": "group_ops", "error": "group ops repository unavailable"})
            return summary.as_dict()
        plans, _total = repo.list_plans({"plan_type": "standard", "status": "active", "limit": 500, "offset": 0})
        for plan in plans:
            summary.group_ops_scanned_plans += 1
            plan_id = int(plan.get("id") or 0)
            try:
                groups = [
                    group
                    for group in repo.list_bound_groups(plan_id)
                    if clean_text(group.get("status") or "active") == "active" and clean_text(group.get("chat_id"))
                ]
                if not groups:
                    continue
                nodes = [
                    node
                    for node in repo.list_nodes(plan_id)
                    if clean_text(node.get("status") or "active") == "active"
                ]
                for node in nodes:
                    node_id = int(node.get("id") or 0)
                    try:
                        self._schedule_node(
                            summary=summary,
                            plan=plan,
                            node=node,
                            groups=groups,
                            now=current_time,
                            operator=operator,
                            business_tz=business_tz,
                        )
                    except Exception as exc:
                        summary.errors.append(
                            {
                                "scope": "group_ops_node",
                                "plan_id": plan_id,
                                "node_id": node_id,
                                "error": str(exc),
                            }
                        )
            except Exception as exc:
                summary.errors.append({"scope": "group_ops_plan", "plan_id": plan_id, "error": str(exc)})
        return summary.as_dict()

    def _schedule_node(
        self,
        *,
        summary: GroupOpsSchedulerSummary,
        plan: dict[str, Any],
        node: dict[str, Any],
        groups: list[dict[str, Any]],
        now: datetime,
        operator: str,
        business_tz: ZoneInfo,
    ) -> None:
        content_package = node.get("content_package_json") if isinstance(node.get("content_package_json"), dict) else {}
        resolved_attachments, resolved_image_media_ids = resolve_group_ops_content_package_materials(content_package)
        content = build_node_group_message_content(
            node=node,
            sender=clean_text(plan.get("owner_userid")),
            resolved_attachments=resolved_attachments,
            resolved_image_media_ids=resolved_image_media_ids,
        )
        base_payload = dict(content)
        base_payload.setdefault("attachments", [])
        base_payload["channel"] = "wecom_customer_group"
        base_payload["sender"] = clean_text(plan.get("owner_userid"))
        base_payload["plan_id"] = int(plan.get("id") or 0)
        base_payload["node_id"] = int(node.get("id") or 0)
        content_hash = _content_hash(base_payload)
        due_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        for group in groups:
            due_at = _due_at_for_group(plan=plan, node=node, group=group, business_tz=business_tz)
            if due_at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                summary.group_ops_skipped_future += 1
                continue
            summary.group_ops_due_nodes += 1
            key = (
                due_at.isoformat(timespec="minutes"),
                clean_text(plan.get("owner_userid")),
                content_hash,
            )
            bucket = due_groups.setdefault(key, {"due_at": due_at, "chat_ids": []})
            bucket["chat_ids"].append(clean_text(group.get("chat_id")))

        for bucket in due_groups.values():
            chat_ids = sorted(dict.fromkeys(bucket["chat_ids"]))
            due_at = bucket["due_at"]
            chat_hash = _stable_hash(chat_ids)
            source_id = f"{int(plan['id'])}:node:{int(node['id'])}:due:{_minute_key(due_at)}:groups:{chat_hash}"
            scheduled_at = due_at.isoformat(timespec="seconds")
            idempotency_key = f"group_ops:{source_id}:{scheduled_at}"
            content_payload = dict(base_payload)
            content_payload["chat_ids"] = chat_ids
            planned = plan_group_ops_external_effect(
                effect_type=GROUP_OPS_MESSAGE_LOOPBACK,
                plan_id=int(plan["id"]),
                target_type="group_ops_node",
                target_id=str(node.get("id") or 0),
                business_id=str(plan.get("id") or 0),
                node_id=int(node.get("id") or 0),
                chat_ids=chat_ids,
                content_summary=(content.get("text") or {}).get("content", "") or clean_text(node.get("action_title")),
                content_payload=content_payload,
                operator_member_id=clean_text(operator) or "automation_ops_scheduler",
                source_module="automation_engine.group_ops.scheduler",
                source_route="group_ops_due_scheduler",
                source_command_id=source_id,
                idempotency_key=idempotency_key,
                scheduled_at=scheduled_at,
            )
            if planned and int(planned.get("id") or 0):
                if planned.get("created_on_plan") is False:
                    summary.group_ops_reused_external_effect_jobs += 1
                    summary.group_ops_skipped_duplicate += 1
                else:
                    summary.group_ops_external_effect_jobs += 1


def run_group_ops_due_scheduler(
    *,
    repo: GroupOpsRepository | None = None,
    now: datetime | None = None,
    operator: str = "automation_ops_scheduler",
) -> dict[str, Any]:
    return GroupOpsDueScheduler(
        repo=repo,
    ).run_due(now=now, operator=operator)
