from __future__ import annotations

import json
import logging
from typing import Any, Callable

from . import repo

archive_domain_logger = logging.getLogger("archive_sync")


def normalize_archived_message(item: dict[str, Any]) -> dict[str, Any]:
    if "raw_payload" in item and "sender" in item and "receiver" in item and "external_userid" in item:
        return {
            "seq": item.get("seq"),
            "msgid": item["msgid"],
            "chat_type": item.get("chat_type", "private"),
            "external_userid": item["external_userid"],
            "owner_userid": item["owner_userid"],
            "sender": item["sender"],
            "receiver": item["receiver"],
            "msgtype": item["msgtype"],
            "content": item["content"],
            "send_time": item["send_time"],
            "raw_payload": item["raw_payload"],
        }
    msgtype = item.get("msgtype", "text")
    content = (item.get("text") or {}).get("content") or item.get("content") or ""
    from_type = item.get("from_type", "")
    from_userid = item.get("from_userid", "")
    external_userid = item.get("external_userid") or (from_userid if from_type == "external" else "")
    owner_userid = item.get("owner_userid", "")
    sender = from_userid or owner_userid
    receiver = owner_userid if from_type == "external" else external_userid
    return {
        "seq": item.get("seq"),
        "msgid": item["msgid"],
        "chat_type": item.get("chat_type", "private"),
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "sender": sender,
        "receiver": receiver,
        "msgtype": msgtype,
        "content": content,
        "send_time": item["send_time"],
        "raw_payload": json.dumps(item, ensure_ascii=False),
    }


def format_message_row(row: dict[str, Any], group_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    raw_payload = row.get("raw_payload")
    decrypted_message = {}
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
            decrypted_message = payload.get("decrypted_message") or {}
        except (TypeError, json.JSONDecodeError):
            decrypted_message = {}
    tolist = decrypted_message.get("tolist") or []
    if isinstance(tolist, str):
        tolist = [tolist]
    chat_id = decrypted_message.get("roomid", "") or ""
    group_info = (group_map or {}).get(chat_id) or {}
    return {
        "seq": row["seq"],
        "msgid": row["msgid"],
        "chat_type": row.get("chat_type") or ("group" if decrypted_message.get("roomid") else ("private" if len(tolist) == 1 else "group")),
        "external_userid": row["external_userid"],
        "owner_userid": row["owner_userid"],
        "sender": row["sender"],
        "from": decrypted_message.get("from") or row["sender"],
        "tolist": tolist,
        "roomid": chat_id,
        "chat_id": chat_id,
        "group_name": group_info.get("group_name", ""),
        "msgtype": row["msgtype"],
        "content": row["content"],
        "send_time": row["send_time"],
    }


def extract_roomid_from_raw_payload(raw_payload: str | None) -> str:
    if not raw_payload:
        return ""
    try:
        payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return ""
    return ((payload.get("decrypted_message") or {}).get("roomid")) or ""


def _normalize_chat_type_filter(chat_type: str | None) -> str | None:
    if not chat_type:
        return None
    value = chat_type.strip().lower()
    if value not in {"private", "group"}:
        raise ValueError("chat_type must be private or group")
    return value


def count_archived_messages() -> int:
    return repo.count_archived_messages()


def insert_archived_messages(messages: list[dict[str, Any]], *, commit: bool = True) -> int:
    normalized_messages = [normalize_archived_message(item) for item in messages]
    inserted_rows = repo.insert_archived_messages_detailed(normalized_messages, commit=commit)
    if inserted_rows:
        should_run_marketing_openclaw = False
        try:
            from ..marketing_automation import evaluate_customer_marketing_state

            for external_userid in {
                str(row.get("external_userid") or "").strip()
                for row in inserted_rows
                if str(row.get("external_userid") or "").strip()
            }:
                marketing_state = evaluate_customer_marketing_state(
                    external_userid=external_userid,
                    persist=False,
                )
                if str((marketing_state or {}).get("pool_key") or "").strip() in {"inactive_focus", "active_focus"}:
                    should_run_marketing_openclaw = True
                    break
        except Exception:
            archive_domain_logger.exception("pre-check marketing openclaw scope failed")
        if should_run_marketing_openclaw:
            try:
                from ..marketing_automation.service import process_inbound_messages_for_openclaw

                process_inbound_messages_for_openclaw(inserted_rows)
            except Exception:
                archive_domain_logger.exception("post-insert inbound message automation failed")
    return len(inserted_rows)


def get_messages_by_user(
    external_userid: str,
    chat_type: str | None = None,
    *,
    group_chat_map_loader: Callable[[list[str]], dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    normalized_chat_type = _normalize_chat_type_filter(chat_type)
    rows = repo.fetch_messages_by_user_rows(external_userid, normalized_chat_type)
    group_map = group_chat_map_loader([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def get_recent_messages_by_user(
    external_userid: str,
    limit: int = 20,
    chat_type: str | None = None,
    *,
    group_chat_map_loader: Callable[[list[str]], dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    normalized_chat_type = _normalize_chat_type_filter(chat_type)
    rows = repo.fetch_recent_messages_by_user_rows(external_userid, safe_limit, normalized_chat_type)
    group_map = group_chat_map_loader([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def search_messages(
    external_userid: str,
    keyword: str,
    *,
    group_chat_map_loader: Callable[[list[str]], dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = repo.search_messages_rows(external_userid, keyword)
    group_map = group_chat_map_loader([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def list_archived_messages_by_window(start_time: str, end_time: str, owner_userid: str, cursor: str = "", limit: int = 100) -> dict[str, Any]:
    rows, offset = repo.list_archived_messages_by_window(start_time, end_time, owner_userid, cursor, limit)
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = str(offset + limit) if has_more else ""
    messages = [
        row["raw_payload"] if isinstance(row["raw_payload"], (dict, list)) else json.loads(row["raw_payload"])
        for row in page_rows
    ]
    return {"messages": messages, "has_more": has_more, "next_cursor": next_cursor}


def create_sync_run(start_time: str, end_time: str, owner_userid: str, cursor: str) -> int:
    return repo.create_sync_run(start_time, end_time, owner_userid, cursor)


def finish_sync_run(
    run_id: int,
    status: str,
    fetched_count: int,
    inserted_count: int,
    raw_response: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    repo.finish_sync_run(run_id, status, fetched_count, inserted_count, raw_response, error_message)


def get_archive_last_seq() -> int:
    return repo.get_archive_last_seq()


def set_archive_last_seq(last_seq: int, *, commit: bool = True) -> None:
    repo.set_archive_last_seq(last_seq, commit=commit)


def get_last_sync_run():
    return repo.get_last_sync_run()


def materialize_message_batches(window_minutes: int = 3) -> dict[str, int]:
    return repo.materialize_message_batches(window_minutes=window_minutes)


def list_message_batches(status: str = "pending", limit: int = 20, cursor: str = "") -> dict[str, Any]:
    return repo.list_message_batches(status=status, limit=limit, cursor=cursor)


def get_message_batch(
    batch_id: int,
    *,
    limit: int = 200,
    cursor: str = "",
    group_chat_map_loader: Callable[[list[str]], dict[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    result = repo.get_message_batch(batch_id, limit=limit, cursor=cursor)
    if not result:
        return None
    batch, rows, safe_limit, cursor_text = result
    page_rows = list(rows[:safe_limit])
    next_cursor = str(page_rows[-1]["batch_item_id"]) if len(rows) > safe_limit and page_rows else ""
    group_map = group_chat_map_loader([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in page_rows])
    return {
        "batch": batch,
        "messages": [format_message_row(row, group_map=group_map) for row in page_rows],
        "paging": {
            "limit": safe_limit,
            "cursor": cursor_text,
            "next_cursor": next_cursor,
        },
    }


def ack_message_batch(batch_id: int, ack_note: str = "", acked_by: str = ""):
    return repo.ack_message_batch(batch_id, ack_note=ack_note, acked_by=acked_by)
