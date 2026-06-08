from __future__ import annotations

from typing import Any

from aicrm_next.send_content.application import normalize_send_content_package

from .repository import CloudPlanRepository, build_cloud_plan_repository


class CloudPlanNotFoundError(LookupError):
    pass


def _clean_limit(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _clean_offset(value: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class ListCloudPlansQuery:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> dict[str, Any]:
        normalized_limit = _clean_limit(limit, default=20, maximum=100)
        normalized_offset = _clean_offset(offset)
        plans, total = self._repo.list_plans(status=status, keyword=keyword, limit=normalized_limit, offset=normalized_offset)
        return {"ok": True, "plans": plans, "limit": normalized_limit, "offset": normalized_offset, "total": total}

    __call__ = execute


class GetCloudPlanQuery:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str) -> dict[str, Any]:
        plan = self._repo.get_plan(plan_id)
        if not plan:
            raise CloudPlanNotFoundError("plan not found")
        return {"ok": True, "plan": plan, "stats": self._repo.plan_stats(plan_id)}

    __call__ = execute


class ListCloudPlanRecipientsQuery:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        plan = self._repo.get_plan(plan_id)
        if not plan:
            raise CloudPlanNotFoundError("plan not found")
        normalized_limit = _clean_limit(limit, default=50, maximum=200)
        normalized_offset = _clean_offset(offset)
        rows, total = self._repo.list_recipients(plan_id, status=status, limit=normalized_limit, offset=normalized_offset)
        return {"ok": True, "plan": plan, "rows": rows, "limit": normalized_limit, "offset": normalized_offset, "total": total}

    __call__ = execute


class GetCloudPlanRecipientQuery:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str, recipient_id: int) -> dict[str, Any]:
        recipient = self._repo.get_recipient(plan_id, recipient_id)
        if not recipient:
            raise CloudPlanNotFoundError("recipient not found")
        messages = self._repo.list_recipient_messages(int(recipient["recipient_id"]))
        return {"ok": True, "recipient": recipient, "messages": messages}

    __call__ = execute


class ApproveCloudPlanCommand:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str, *, operator: str) -> dict[str, Any]:
        plan = self._repo.approve_plan(plan_id, operator=operator)
        if not plan:
            raise CloudPlanNotFoundError("plan not found")
        return {"ok": True, "plan": plan, "stats": self._repo.plan_stats(plan_id)}

    __call__ = execute


class RejectCloudPlanCommand:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any]:
        plan = self._repo.reject_plan(plan_id, operator=operator, reason=reason)
        if not plan:
            raise CloudPlanNotFoundError("plan not found")
        return {"ok": True, "plan": plan, "stats": self._repo.plan_stats(plan_id)}

    __call__ = execute


class ApproveCloudPlanRecipientCommand:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]:
        result = self._repo.approve_recipient(plan_id, recipient_id, operator=operator)
        return {"ok": True, **result, "stats": self._repo.plan_stats(plan_id)}

    __call__ = execute


class RejectCloudPlanRecipientCommand:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]:
        result = self._repo.reject_recipient(plan_id, recipient_id, operator=operator, reason=reason)
        return {"ok": True, **result, "stats": self._repo.plan_stats(plan_id)}

    __call__ = execute


class UpdateCloudPlanRecipientMessageCommand:
    def __init__(self, repo: CloudPlanRepository | None = None) -> None:
        self._repo = repo or build_cloud_plan_repository()

    def execute(
        self,
        plan_id: str,
        recipient_id: int,
        message_id: int,
        *,
        payload: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        content_payload = payload.get("content_payload") if isinstance(payload.get("content_payload"), dict) else {}
        content_package = payload.get("content_package")
        if not isinstance(content_package, dict):
            content_package = content_payload.get("content_package") if isinstance(content_payload.get("content_package"), dict) else content_payload
        normalized = normalize_send_content_package(content_package, text_enabled=True, require_body=False)
        result = self._repo.update_recipient_message(
            plan_id,
            recipient_id,
            message_id,
            content_package=normalized,
            day_offset=payload.get("day_offset"),
            send_time=payload.get("send_time"),
            operator=operator,
        )
        return {"ok": True, **result, "stats": self._repo.plan_stats(plan_id)}

    __call__ = execute
