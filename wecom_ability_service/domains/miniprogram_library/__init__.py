"""租户级小程序素材库

集中管理可被群发链路（AI 群发 / 自动化工作流 / 手动 user_ops / 欢迎语 / SOP）
引用的小程序卡片配置。每条记录持有 appid + pagepath + 标题 + 缩略图原图，
发送前调 ``resolve_thumb_media_id`` 把缩略图上传到企业微信换出 ``thumb_media_id``，
并把结果缓存 2 天（企微临时素材有效期 3 天，留 1 天 buffer 自动重传）。

核心 API:
- ``list_miniprograms`` / ``get_miniprogram`` / ``create_miniprogram`` /
  ``update_miniprogram`` / ``delete_miniprogram``
- ``resolve_thumb_media_id(library_id)`` —— 发送前调用，返回有效 ``thumb_media_id``
- ``materialize_miniprogram_attachment(library_id, ...)`` —— 把库 id 展开成
  ``{"msgtype": "miniprogram", "miniprogram": {...}}`` 形式的附件项
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from datetime import datetime, timedelta
from typing import Any

import requests

from ...db import get_db
from ...wecom_client import WeComClient
from ..media_library._utils import (
    iso as _iso,
    now_utc as _now_utc,
    parse_iso as _parse_iso,
    row_to_dict as _row_to_dict,
)
from ..wecom_media_limits import validate_wecom_image_upload

_logger = logging.getLogger(__name__)

THUMB_MEDIA_TTL_DAYS = 2  # 企微临时素材 3 天，留 1 天 buffer
_THUMB_DEFAULT_FILENAME = "miniprogram-thumb.png"


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
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
    thumb_image_id_raw = row.get("thumb_image_id")
    try:
        thumb_image_id = int(thumb_image_id_raw) if thumb_image_id_raw else 0
    except (TypeError, ValueError):
        thumb_image_id = 0
    return {
        "id": int(row.get("id") or 0),
        "name": str(row.get("name") or ""),
        "appid": str(row.get("appid") or ""),
        "pagepath": str(row.get("pagepath") or ""),
        "title": str(row.get("title") or ""),
        "thumb_image_url": str(row.get("thumb_image_url") or ""),
        "thumb_image_base64": str(row.get("thumb_image_base64") or ""),
        "thumb_image_id": thumb_image_id,
        "thumb_media_id": str(row.get("thumb_media_id") or ""),
        "thumb_media_id_expires_at": str(row.get("thumb_media_id_expires_at") or ""),
        "enabled": enabled,
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def list_miniprograms(*, enabled_only: bool = True) -> list[dict[str, Any]]:
    db = get_db()
    cur = db.cursor()
    if enabled_only:
        cur.execute(
            "SELECT * FROM miniprogram_library WHERE enabled ORDER BY updated_at DESC, id DESC"
        )
    else:
        cur.execute("SELECT * FROM miniprogram_library ORDER BY updated_at DESC, id DESC")
    return [_serialize(_row_to_dict(row)) for row in cur.fetchall() or []]


def get_miniprogram(library_id: int) -> dict[str, Any]:
    if not library_id:
        return {}
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM miniprogram_library WHERE id = ?", (int(library_id),))
    row = cur.fetchone()
    return _serialize(_row_to_dict(row)) if row else {}


def _validate_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    appid = str(payload.get("appid") or "").strip()
    pagepath = str(payload.get("pagepath") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not appid:
        raise ValueError("appid 不能为空")
    if not pagepath:
        raise ValueError("pagepath 不能为空")
    if not title:
        raise ValueError("title 不能为空")
    name = str(payload.get("name") or title).strip() or appid
    thumb_image_url = str(payload.get("thumb_image_url") or "").strip()
    thumb_image_base64 = str(payload.get("thumb_image_base64") or "").strip()
    thumb_image_id_raw = payload.get("thumb_image_id")
    try:
        thumb_image_id = int(thumb_image_id_raw) if thumb_image_id_raw else 0
    except (TypeError, ValueError) as exc:
        raise ValueError("thumb_image_id 必须是整数") from exc
    if not thumb_image_id and not thumb_image_url and not thumb_image_base64:
        raise ValueError("缩略图必须提供 thumb_image_id（推荐）/ thumb_image_url / thumb_image_base64 之一")
    if not thumb_image_id and thumb_image_base64:
        file_bytes, content_type, file_name = _decode_thumb_bytes(
            {"thumb_image_base64": thumb_image_base64, "thumb_image_url": ""}
        )
        validate_wecom_image_upload(
            file_bytes,
            file_name=file_name,
            mime_type=content_type,
        )
    return {
        "name": name,
        "appid": appid,
        "pagepath": pagepath,
        "title": title,
        "thumb_image_url": thumb_image_url,
        "thumb_image_base64": thumb_image_base64,
        "thumb_image_id": thumb_image_id,
    }


def create_miniprogram(payload: dict[str, Any]) -> dict[str, Any]:
    fields = _validate_create_payload(payload)
    enabled = bool(payload.get("enabled", True))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO miniprogram_library
            (name, appid, pagepath, title, thumb_image_url, thumb_image_base64,
             thumb_image_id, thumb_media_id, thumb_media_id_expires_at, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, '', NULL, ?)
        """,
        (
            fields["name"],
            fields["appid"],
            fields["pagepath"],
            fields["title"],
            fields["thumb_image_url"],
            fields["thumb_image_base64"],
            fields["thumb_image_id"] or None,
            bool(enabled),
        ),
    )
    db.commit()
    library_id = int(cur.lastrowid or 0)
    return get_miniprogram(library_id)


_UPDATABLE_FIELDS = (
    "name",
    "appid",
    "pagepath",
    "title",
    "thumb_image_url",
    "thumb_image_base64",
    "thumb_image_id",
    "enabled",
)
_THUMB_FIELDS = {"thumb_image_url", "thumb_image_base64", "thumb_image_id"}


def update_miniprogram(library_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_miniprogram(library_id)
    if not existing:
        raise ValueError(f"miniprogram_library id={library_id} 不存在")
    set_clauses: list[str] = []
    params: list[Any] = []
    invalidate_thumb_cache = False
    for key in _UPDATABLE_FIELDS:
        if key not in payload:
            continue
        value = payload[key]
        if key == "enabled":
            set_clauses.append("enabled = ?")
            params.append(bool(value))
            continue
        if key == "thumb_image_id":
            try:
                int_value = int(value) if value else 0
            except (TypeError, ValueError) as exc:
                raise ValueError("thumb_image_id 必须是整数") from exc
            set_clauses.append("thumb_image_id = ?")
            params.append(int_value or None)
            if int_value != (existing.get("thumb_image_id") or 0):
                invalidate_thumb_cache = True
            continue
        text = str(value or "").strip()
        if key in {"appid", "pagepath", "title"} and not text:
            raise ValueError(f"{key} 不能为空")
        set_clauses.append(f"{key} = ?")
        params.append(text)
        if key in _THUMB_FIELDS and text != existing.get(key, ""):
            invalidate_thumb_cache = True
    if not set_clauses:
        return existing
    if invalidate_thumb_cache:
        set_clauses.append("thumb_media_id = ?")
        params.append("")
        set_clauses.append("thumb_media_id_expires_at = NULL")
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    params.append(int(library_id))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"UPDATE miniprogram_library SET {', '.join(set_clauses)} WHERE id = ?",
        tuple(params),
    )
    db.commit()
    return get_miniprogram(library_id)


def delete_miniprogram(library_id: int) -> bool:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM miniprogram_library WHERE id = ?", (int(library_id),))
    db.commit()
    return (cur.rowcount or 0) > 0


def _decode_thumb_bytes(record: dict[str, Any]) -> tuple[bytes, str, str]:
    """从库记录里取出缩略图原始字节 + content-type + 文件名。"""
    base64_payload = (record.get("thumb_image_base64") or "").strip()
    if base64_payload:
        encoded = base64_payload
        content_type = "image/png"
        if encoded.startswith("data:"):
            header, _, body = encoded.partition(",")
            if not body:
                raise ValueError("thumb_image_base64 data url 不合法")
            if header.startswith("data:") and ";" in header:
                content_type = header[5:].split(";", 1)[0] or content_type
            encoded = body
        try:
            file_bytes = base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise ValueError("thumb_image_base64 解码失败") from exc
        return file_bytes, content_type, _THUMB_DEFAULT_FILENAME

    url = (record.get("thumb_image_url") or "").strip()
    if not url:
        raise ValueError("缩略图未配置（thumb_image_url / thumb_image_base64 都为空）")
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "image/png").split(";", 1)[0].strip() or "image/png"
    file_name = url.rsplit("/", 1)[-1].split("?", 1)[0] or _THUMB_DEFAULT_FILENAME
    if "." not in file_name:
        ext = mimetypes.guess_extension(content_type) or ".png"
        file_name += ext
    return response.content, content_type, file_name


def _persist_thumb_media_id(library_id: int, media_id: str, expires_at: datetime) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE miniprogram_library
        SET thumb_media_id = ?, thumb_media_id_expires_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (media_id, _iso(expires_at), int(library_id)),
    )
    db.commit()


def resolve_thumb_media_id(
    library_id: int,
    *,
    upload_image: Any | None = None,
    now: datetime | None = None,
) -> str:
    """返回有效的 thumb_media_id；过期则重新上传。

    ``upload_image`` 可在测试里注入 ``(file_name, file_bytes, content_type) -> media_id``，
    生产路径默认用 ``WeComClient.from_app()._upload_private_message_image``。
    """
    record = get_miniprogram(library_id)
    if not record:
        raise ValueError(f"miniprogram_library id={library_id} 不存在")
    if not record.get("enabled", False):
        raise ValueError(f"miniprogram_library id={library_id} 已停用")

    # 新通道：thumb_image_id 关联 image_library 时，直接复用图片素材库的缓存机制，
    # 不再各自维护 media_id（避免双层缓存不一致）
    thumb_image_id = int(record.get("thumb_image_id") or 0)
    if thumb_image_id:
        from .. import image_library as _img_lib  # 局部 import 避免循环依赖
        return _img_lib.resolve_image_media_id(thumb_image_id, upload_image=upload_image, now=now)

    # 老通道：thumb_image_url / thumb_image_base64 直接存在 miniprogram_library 表里
    current = now or _now_utc()
    cached_id = (record.get("thumb_media_id") or "").strip()
    expires_at = _parse_iso(record.get("thumb_media_id_expires_at"))
    if cached_id and expires_at and expires_at > current:
        return cached_id

    file_bytes, content_type, file_name = _decode_thumb_bytes(record)
    content_type = validate_wecom_image_upload(
        file_bytes,
        file_name=file_name,
        mime_type=content_type,
    )
    uploader = upload_image
    if uploader is None:
        client = WeComClient.from_app()
        uploader = client._upload_private_message_image  # noqa: SLF001 — 复用现有上传通道
    media_id = uploader(file_name, file_bytes, content_type)
    if not media_id:
        raise ValueError("缩略图上传企微失败：未返回 media_id")
    new_expires_at = current + timedelta(days=THUMB_MEDIA_TTL_DAYS)
    _persist_thumb_media_id(int(library_id), media_id, new_expires_at)
    return media_id


def materialize_miniprogram_attachment(
    library_id: int,
    *,
    override_pagepath: str | None = None,
    override_title: str | None = None,
    upload_image: Any | None = None,
) -> dict[str, Any]:
    """把库 id 展开成可直接塞进 attachments 的 dict。"""
    record = get_miniprogram(library_id)
    if not record:
        raise ValueError(f"miniprogram_library id={library_id} 不存在")
    pagepath = (override_pagepath or record.get("pagepath") or "").strip()
    title = (override_title or record.get("title") or "").strip()
    if not pagepath:
        raise ValueError("miniprogram pagepath 为空")
    if not title:
        raise ValueError("miniprogram title 为空")
    thumb_media_id = resolve_thumb_media_id(library_id, upload_image=upload_image)
    return {
        "msgtype": "miniprogram",
        "miniprogram": {
            "appid": record["appid"],
            "pagepath": pagepath,
            "title": title,
            "thumb_media_id": thumb_media_id,
        },
    }


def expand_attachments_with_library(
    attachments: list[dict[str, Any]] | None,
    *,
    upload_image: Any | None = None,
) -> list[dict[str, Any]]:
    """把 attachments 列表里所有 miniprogram 项的 ``library_id`` 占位展开为完整字段。

    其他类型（file / 已含 appid+thumb_media_id 的 miniprogram）原样透传。
    """
    if not attachments:
        return []
    expanded: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            expanded.append(item)
            continue
        msgtype = str(item.get("msgtype") or "").strip().lower()
        if msgtype != "miniprogram":
            expanded.append(item)
            continue
        mp = item.get("miniprogram") or {}
        if not isinstance(mp, dict):
            mp = {}
        library_id = mp.get("library_id")
        if library_id:
            try:
                lib_id_int = int(library_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("miniprogram library_id 必须是整数") from exc
            override_pagepath = str(mp.get("pagepath") or "").strip() or None
            override_title = str(mp.get("title") or "").strip() or None
            expanded.append(
                materialize_miniprogram_attachment(
                    lib_id_int,
                    override_pagepath=override_pagepath,
                    override_title=override_title,
                    upload_image=upload_image,
                )
            )
        else:
            expanded.append(item)
    return expanded
