from __future__ import annotations

from aicrm_next.shared.repository_provider import RepositoryProviderError
from aicrm_next.shared.runtime import production_data_ready
from aicrm_next.shared.typing import JsonDict

from .repo import MessageArchiveRepository, build_message_archive_repository


def _normalize_limit(value: int | None, *, default: int = 20) -> int:
    if value is None:
        return default
    return max(1, min(int(value), 200))


def _normalize_offset(value: int | None) -> int:
    return max(0, int(value or 0))


def _normalize_chat_type(value: str | None) -> str:
    chat_type = str(value or "").strip().lower()
    if chat_type and chat_type not in {"private", "group"}:
        raise ValueError("chat_type must be private or group")
    return chat_type


def _source_status() -> tuple[str, str]:
    if production_data_ready():
        return "message_archive_read_model", "primary"
    return "message_archive_fixture", "fixture"


def _production_unavailable(exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "degraded": True,
        "messages": [],
        "items": [],
        "count": 0,
        "source_status": "production_unavailable",
        "read_model_status": "unavailable",
        "fallback_used": False,
        "route_owner": "ai_crm_next",
        "error_code": "message_archive_read_unavailable",
        "page_error": str(exc).replace("production/postgres/legacy facade data", "production/postgres message archive data"),
        "status_code": 503,
    }


class ListArchivedMessagesQuery:
    def __init__(self, repo: MessageArchiveRepository | None = None) -> None:
        self._repo = repo

    def execute(
        self,
        *,
        external_userid: str,
        chat_type: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> JsonDict:
        try:
            normalized_chat_type = _normalize_chat_type(chat_type)
            safe_limit = _normalize_limit(limit)
            safe_offset = _normalize_offset(offset)
            repo = self._repo or build_message_archive_repository()
            rows = repo.list_messages(
                str(external_userid or "").strip(),
                chat_type=normalized_chat_type,
                limit=safe_limit,
                offset=safe_offset,
            )
        except RepositoryProviderError as exc:
            return _production_unavailable(exc)
        except ValueError as exc:
            return _input_error(str(exc))
        source_status, read_model_status = _source_status()
        return {
            "ok": True,
            "messages": rows,
            "items": rows,
            "count": len(rows),
            "external_userid": str(external_userid or "").strip(),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {"chat_type": normalized_chat_type},
            "source_status": source_status,
            "read_model_status": read_model_status,
            "fallback_used": False,
            "route_owner": "ai_crm_next",
            "status_code": 200,
        }

    __call__ = execute


class SearchArchivedMessagesQuery:
    def __init__(self, repo: MessageArchiveRepository | None = None) -> None:
        self._repo = repo

    def execute(
        self,
        *,
        external_userid: str,
        keyword: str,
        chat_type: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> JsonDict:
        if not str(external_userid or "").strip() or not str(keyword or "").strip():
            return _input_error("external_userid and keyword are required")
        try:
            normalized_chat_type = _normalize_chat_type(chat_type)
            safe_limit = _normalize_limit(limit)
            safe_offset = _normalize_offset(offset)
            repo = self._repo or build_message_archive_repository()
            rows = repo.search_messages(
                external_userid=str(external_userid or "").strip(),
                keyword=str(keyword or "").strip(),
                chat_type=normalized_chat_type,
                limit=safe_limit,
                offset=safe_offset,
            )
        except RepositoryProviderError as exc:
            return _production_unavailable(exc)
        except ValueError as exc:
            return _input_error(str(exc))
        source_status, read_model_status = _source_status()
        return {
            "ok": True,
            "messages": rows,
            "items": rows,
            "count": len(rows),
            "external_userid": str(external_userid or "").strip(),
            "keyword": str(keyword or "").strip(),
            "limit": safe_limit,
            "offset": safe_offset,
            "filters": {"chat_type": normalized_chat_type},
            "source_status": source_status,
            "read_model_status": read_model_status,
            "fallback_used": False,
            "route_owner": "ai_crm_next",
            "status_code": 200,
        }

    __call__ = execute


def deprecated_messages_route(*, replacement_route: str = "") -> JsonDict:
    return {
        "ok": False,
        "error_code": "messages_route_deprecated",
        "message": "This legacy messages route has been replaced by exact Next routes.",
        "replacement_route": replacement_route,
        "route_owner": "ai_crm_next",
        "source_status": "deprecated",
        "read_model_status": "not_applicable",
        "fallback_used": False,
        "status_code": 410,
    }


def blocked_messages_side_effect(*, action: str) -> JsonDict:
    return {
        "ok": False,
        "error_code": "external_call_blocked",
        "message": "Message write/send routes are blocked in this Legacy Exit replacement phase.",
        "action": action,
        "route_owner": "ai_crm_next",
        "source_status": "external_call_blocked",
        "side_effect_plan": {
            "would_call": "wecom_message_send",
            "real_external_call_executed": False,
            "next_step": "requires_platform_jobs",
        },
        "status_code": 503,
    }


def _input_error(message: str) -> JsonDict:
    return {
        "ok": False,
        "error": message,
        "source_status": "input_error",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "status_code": 400,
    }

