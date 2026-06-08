from __future__ import annotations

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .application import (
    ListArchivedMessagesQuery,
    SearchArchivedMessagesQuery,
    blocked_messages_side_effect,
    deprecated_messages_route,
)

router = APIRouter()


def _response(payload: dict) -> JSONResponse:
    status_code = int(payload.pop("status_code", 200) or 200)
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


@router.get("/api/messages/search")
def search_messages(
    external_userid: str | None = None,
    keyword: str | None = None,
    chat_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    payload = SearchArchivedMessagesQuery()(
        external_userid=external_userid or "",
        keyword=keyword or "",
        chat_type=chat_type or "",
        limit=limit,
        offset=offset,
    )
    return _response(payload)


@router.api_route("/api/messages/send", methods=["GET", "POST", "OPTIONS"])
def blocked_message_send():
    return _response(blocked_messages_side_effect(action="send"))


@router.api_route("/api/messages/broadcast", methods=["GET", "POST", "OPTIONS"])
def blocked_message_broadcast():
    return _response(blocked_messages_side_effect(action="broadcast"))


@router.api_route("/api/messages/archive/sync", methods=["GET", "POST", "OPTIONS"])
def blocked_message_archive_sync():
    return _response(blocked_messages_side_effect(action="archive_sync"))


@router.get("/api/messages/archive")
def deprecated_message_archive():
    return _response(deprecated_messages_route(replacement_route="/api/messages/search"))


@router.get("/api/messages/{external_userid}/archive")
def deprecated_external_message_archive(external_userid: str):
    return _response(deprecated_messages_route(replacement_route=f"/api/messages/{external_userid}"))


@router.get("/api/messages/{external_userid}/history")
def deprecated_external_message_history(external_userid: str):
    return _response(deprecated_messages_route(replacement_route=f"/api/messages/{external_userid}"))


@router.get("/api/messages/{external_userid}")
def list_messages(
    external_userid: str,
    chat_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    payload = ListArchivedMessagesQuery()(
        external_userid=external_userid,
        chat_type=chat_type or "",
        limit=limit,
        offset=offset,
    )
    return _response(payload)
