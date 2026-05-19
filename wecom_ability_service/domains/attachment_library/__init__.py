"""租户级附件素材库。

集中维护可被欢迎语和后续群发链路复用的普通文件附件。发送前通过
``resolve_attachment_media_id`` 上传到企业微信 ``upload_attachment`` 换取
临时 ``media_id``，本地缓存 2 天，避开企微 3 天临时素材过期窗口。
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from ...wecom_client import WeComClient
from ..media_library._utils import (
    decode_jsonb as _decode_jsonb,
    iso as _iso,
    normalize_tags as _normalize_tags,
    now_utc as _now_utc,
    parse_iso as _parse_iso,
    row_to_dict as _row_to_dict,
    to_jsonb_text as _to_jsonb_text,
)
from ..wecom_media_limits import (
    WECOM_ATTACHMENT_ALLOWED_EXTENSIONS,
    WECOM_ATTACHMENT_MAX_MB,
    WECOM_ATTACHMENT_MEDIA_TTL_DAYS,
    normalize_wecom_attachment_mime_type,
    validate_wecom_attachment_upload,
)

_DEFAULT_FILENAME = "attachment.pdf"
_LIST_COLUMNS = (
    "id, name, file_name, mime_type, file_size, media_id, media_id_expires_at, "
    "enabled, description, tags, created_at, updated_at"
)


def _serialize(row: dict[str, Any], *, include_data: bool = False) -> dict[str, Any]:
    if not row:
        return {}
    enabled_raw = row.get("enabled")
    if isinstance(enabled_raw, bool):
        enabled = enabled_raw
    else:
        try:
            enabled = bool(int(enabled_raw or 0))
        except (TypeError, ValueError):
            enabled = bool(enabled_raw)
    out = {
        "id": int(row.get("id") or 0),
        "name": str(row.get("name") or ""),
        "file_name": str(row.get("file_name") or ""),
        "mime_type": str(row.get("mime_type") or "application/pdf"),
        "file_size": int(row.get("file_size") or 0),
        "media_id": str(row.get("media_id") or ""),
        "media_id_expires_at": str(row.get("media_id_expires_at") or ""),
        "enabled": enabled,
        "description": str(row.get("description") or ""),
        "tags": _decode_jsonb(row.get("tags"), default=[]),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
    if include_data:
        out["data_base64"] = str(row.get("data_base64") or "")
    return out


def _normalize_id_list(value: Any, *, max_count: int = 9) -> list[int]:
    if value in (None, ""):
        return []
    raw = value
    if isinstance(value, str):
        import json

        try:
            raw = json.loads(value)
        except (TypeError, ValueError):
            raw = [part.strip() for part in value.split(",")]
    if not isinstance(raw, list):
        raw = [raw]
    ids: list[int] = []
    for item in raw:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in ids:
            ids.append(item_id)
    return ids[:max_count]


def list_attachments(
    *,
    enabled_only: bool = True,
    limit: int = 200,
    q: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    where: list[str] = []
    params: list[Any] = []
    if enabled_only:
        where.append("enabled")
    q_clean = (q or "").strip()
    if q_clean:
        like = f"%{q_clean}%"
        where.append("(name ILIKE ? OR file_name ILIKE ? OR description ILIKE ?)")
        params.extend([like, like, like])
    tag_filters = _normalize_tags(tags)
    if tag_filters:
        where.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements_text(tags) AS tt "
            "WHERE tt = ANY(?))"
        )
        params.append(tag_filters)
    sql = f"SELECT {_LIST_COLUMNS} FROM attachment_library"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    cur.execute(sql, tuple(params))
    return [_serialize(_row_to_dict(row)) for row in cur.fetchall() or []]


def get_attachment(attachment_id: int, *, include_data: bool = False) -> dict[str, Any]:
    if not attachment_id:
        return {}
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM attachment_library WHERE id = ?", (int(attachment_id),))
    row = cur.fetchone()
    return _serialize(_row_to_dict(row), include_data=include_data) if row else {}


def create_attachment_from_upload(
    *,
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    name: str = "",
    description: str = "",
    tags: Any = None,
) -> dict[str, Any]:
    if not file_bytes:
        raise ValueError("file_bytes is empty")
    normalized_mime = validate_wecom_attachment_upload(
        file_bytes,
        file_name=file_name,
        mime_type=mime_type,
    )
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO attachment_library
            (name, file_name, mime_type, file_size, data_base64, media_id,
             media_id_expires_at, enabled, description, tags)
        VALUES (?, ?, ?, ?, ?, '', NULL, ?, ?, ?)
        """,
        (
            (name or file_name or _DEFAULT_FILENAME).strip()[:200],
            (file_name or _DEFAULT_FILENAME).strip()[:200],
            normalized_mime,
            len(file_bytes),
            base64.b64encode(file_bytes).decode("ascii"),
            True,
            (description or "").strip()[:4000],
            _to_jsonb_text(_normalize_tags(tags), default="[]"),
        ),
    )
    db.commit()
    return get_attachment(int(cur.lastrowid or 0))


def update_attachment(
    attachment_id: int,
    *,
    name: str | None = None,
    enabled: bool | None = None,
    description: str | None = None,
    tags: Any = None,
) -> dict[str, Any]:
    existing = get_attachment(attachment_id)
    if not existing:
        raise ValueError(f"attachment_library id={attachment_id} not found")
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = ?")
        params.append(str(name).strip()[:200])
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(bool(enabled))
    if description is not None:
        sets.append("description = ?")
        params.append(str(description).strip()[:4000])
    if tags is not None:
        sets.append("tags = ?")
        params.append(_to_jsonb_text(_normalize_tags(tags), default="[]"))
    if not sets:
        return existing
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(int(attachment_id))
    db = get_db()
    cur = db.cursor()
    cur.execute(f"UPDATE attachment_library SET {', '.join(sets)} WHERE id = ?", tuple(params))
    db.commit()
    return get_attachment(attachment_id)


def find_attachment_references(attachment_id: int) -> dict[str, list[dict[str, Any]]]:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        SELECT id, channel_code, channel_name
        FROM automation_channel
        WHERE EXISTS (
          SELECT 1 FROM jsonb_array_elements_text(
            COALESCE(welcome_attachment_library_ids, '[]'::jsonb)
          ) AS aid WHERE aid = ?
        )
        """,
        (str(int(attachment_id)),),
    )
    return {"automation_channels": [dict(row) for row in (cur.fetchall() or [])]}


def delete_attachment(attachment_id: int, *, force: bool = False) -> dict[str, Any]:
    attachment_id = int(attachment_id)
    existing = get_attachment(attachment_id)
    if not existing:
        raise ValueError(f"attachment_library id={attachment_id} not found")
    refs = find_attachment_references(attachment_id)
    has_refs = bool(refs["automation_channels"])
    if has_refs and not force:
        raise ValueError(
            "attachment_library id={id} 被欢迎语引用：channels={count}；"
            "若确认删除请先移除引用或用 force=True".format(
                id=attachment_id,
                count=len(refs["automation_channels"]),
            )
        )
    if has_refs:
        db = get_db()
        db.execute(
            """
            UPDATE automation_channel
            SET welcome_attachment_library_ids = COALESCE(
                (
                  SELECT jsonb_agg(elem)
                  FROM jsonb_array_elements(welcome_attachment_library_ids) AS elem
                  WHERE elem::text::int <> ?
                ),
                '[]'::jsonb
            ),
            updated_at = CURRENT_TIMESTAMP
            WHERE EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(
                COALESCE(welcome_attachment_library_ids, '[]'::jsonb)
              ) AS aid WHERE aid = ?
            )
            """,
            (attachment_id, str(attachment_id)),
        )
        db.commit()
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM attachment_library WHERE id = ?", (attachment_id,))
    db.commit()
    return {"ok": (cur.rowcount or 0) > 0, "deleted_id": attachment_id}


def resolve_attachment_media_id(
    attachment_id: int,
    *,
    upload_file: Any | None = None,
    now: datetime | None = None,
) -> str:
    record = get_attachment(attachment_id, include_data=True)
    if not record:
        raise ValueError(f"attachment_library id={attachment_id} not found")
    if not record.get("enabled", False):
        raise ValueError(f"attachment_library id={attachment_id} is disabled")
    current = now or _now_utc()
    cached_id = (record.get("media_id") or "").strip()
    expires_at = _parse_iso(record.get("media_id_expires_at"))
    if cached_id and expires_at and expires_at > current:
        return cached_id
    encoded = str(record.get("data_base64") or "")
    if not encoded:
        raise ValueError(f"attachment_library id={attachment_id} has no data")
    try:
        file_bytes = base64.b64decode(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"attachment_library id={attachment_id} base64 decode failed") from exc
    content_type = validate_wecom_attachment_upload(
        file_bytes,
        file_name=str(record.get("file_name") or _DEFAULT_FILENAME),
        mime_type=normalize_wecom_attachment_mime_type(record.get("mime_type"), file_name=record.get("file_name")),
    )
    uploader = upload_file
    if uploader is None:
        client = WeComClient.from_contact_app()
        uploader = client._upload_attachment_file
    media_id = uploader(str(record.get("file_name") or _DEFAULT_FILENAME), file_bytes, content_type)
    if not media_id:
        raise ValueError("附件上传企微失败：未返回 media_id")
    db = get_db()
    db.execute(
        """
        UPDATE attachment_library
        SET media_id = ?, media_id_expires_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (media_id, _iso(current + timedelta(days=WECOM_ATTACHMENT_MEDIA_TTL_DAYS)), int(record["id"])),
    )
    db.commit()
    return media_id


def materialize_file_attachment(attachment_id: int, *, upload_file: Any | None = None) -> dict[str, Any]:
    return {
        "msgtype": "file",
        "file": {"media_id": resolve_attachment_media_id(attachment_id, upload_file=upload_file)},
    }


def expand_attachments_with_library(attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for item in list(attachments or []):
        if not isinstance(item, dict):
            expanded.append(item)
            continue
        msgtype = str(item.get("msgtype") or "").strip().lower()
        if msgtype != "file":
            expanded.append(item)
            continue
        file_payload = item.get("file") or {}
        if not isinstance(file_payload, dict):
            expanded.append(item)
            continue
        raw_library_id = (
            file_payload.get("library_id")
            or file_payload.get("attachment_library_id")
            or item.get("attachment_library_id")
        )
        if not raw_library_id:
            expanded.append(item)
            continue
        try:
            library_id = int(raw_library_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("file attachment library_id must be integer") from exc
        expanded.append(materialize_file_attachment(library_id))
    return expanded


__all__ = [
    "WECOM_ATTACHMENT_ALLOWED_EXTENSIONS",
    "WECOM_ATTACHMENT_MAX_MB",
    "create_attachment_from_upload",
    "delete_attachment",
    "expand_attachments_with_library",
    "find_attachment_references",
    "get_attachment",
    "list_attachments",
    "materialize_file_attachment",
    "resolve_attachment_media_id",
    "update_attachment",
    "_normalize_id_list",
]
