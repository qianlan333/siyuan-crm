from __future__ import annotations

from typing import Any

from aicrm_next.media_library.postgres_repo import PostgresMediaLibraryRepository
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .repo import SendContentRepository, _assert_material_type, _clamp_limit


class PostgresSendContentRepository(SendContentRepository):
    source_status = "production_postgres_send_content"

    def __init__(self, database_url: str) -> None:
        self._media_repo = PostgresMediaLibraryRepository(database_url)

    def list_materials(
        self,
        material_type: str,
        *,
        q: str = "",
        enabled_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        _assert_material_type(material_type)
        limit = _clamp_limit(limit)
        offset = max(0, int(offset or 0))
        try:
            result = self._media_repo.list_items(
                material_type,
                limit=limit,
                offset=offset,
                filters={"q": q, "enabled_only": enabled_only},
            )
        except Exception as exc:
            raise RepositoryProviderError(f"send content production repository unavailable: {exc}") from exc
        return {
            "items": [self._to_picker_item(material_type, item) for item in result.get("items") or []],
            "total": int(result.get("total") or 0),
            "limit": limit,
            "offset": offset,
        }

    def get_materials_by_ids(self, material_type: str, ids: list[int]) -> list[dict[str, Any]]:
        _assert_material_type(material_type)
        rows: list[dict[str, Any]] = []
        for item_id in ids:
            try:
                item = self._media_repo.get_item(material_type, str(item_id), include_data=False)
            except Exception as exc:
                raise RepositoryProviderError(f"send content production repository unavailable: {exc}") from exc
            if item:
                rows.append(self._to_picker_item(material_type, item))
        by_id = {int(item["library_id"]): item for item in rows}
        return [by_id[item_id] for item_id in ids if item_id in by_id]

    def _to_picker_item(self, material_type: str, item: dict[str, Any]) -> dict[str, Any]:
        if material_type == "image":
            library_id = int(item.get("id") or 0)
            title = str(item.get("name") or item.get("file_name") or f"图片素材 {library_id}")
            thumbnail_url = str(
                item.get("thumb_160_url")
                or item.get("thumb_url")
                or item.get("thumb_320_url")
                or f"/api/admin/image-library/{library_id}/thumbnail?size=160"
            )
            mime_type = str(item.get("mime_type") or item.get("content_type") or "")
            file_size = int(item.get("file_size") or 0)
            return {
                "type": "image",
                "library_id": library_id,
                "title": title,
                "subtitle": _join_subtitle(mime_type, _format_file_size(file_size)),
                "thumbnail_url": thumbnail_url,
                "enabled": bool(item.get("enabled", True)),
                "metadata": {
                    "file_name": str(item.get("file_name") or ""),
                    "mime_type": mime_type,
                    "category": str(item.get("category") or ""),
                    "tags": list(item.get("tags") or []),
                },
            }
        if material_type == "miniprogram":
            library_id = int(item.get("id") or 0)
            thumb_image_id = item.get("thumb_image_id")
            fallback = f"/api/admin/image-library/{thumb_image_id}/thumbnail?size=160" if thumb_image_id not in (None, "") else ""
            thumbnail_url = str(
                item.get("thumb_160_url")
                or item.get("thumb_url")
                or item.get("thumb_image_url")
                or fallback
            )
            appid = str(item.get("appid") or "")
            pagepath = str(item.get("pagepath") or item.get("page_path") or "")
            return {
                "type": "miniprogram",
                "library_id": library_id,
                "title": str(item.get("title") or item.get("name") or f"小程序素材 {library_id}"),
                "subtitle": _join_subtitle(appid, pagepath),
                "thumbnail_url": thumbnail_url,
                "enabled": bool(item.get("enabled", True)),
                "metadata": {
                    "appid": appid,
                    "pagepath": pagepath,
                    "thumb_image_id": thumb_image_id,
                    "thumb_media_id": str(item.get("thumb_media_id") or ""),
                },
            }
        library_id = int(item.get("id") or 0)
        mime_type = str(item.get("mime_type") or "")
        file_size = int(item.get("file_size") or 0)
        return {
            "type": "attachment",
            "library_id": library_id,
            "title": str(item.get("name") or item.get("file_name") or f"附件素材 {library_id}"),
            "subtitle": _join_subtitle(mime_type, _format_file_size(file_size)),
            "thumbnail_url": "",
            "enabled": bool(item.get("enabled", True)),
            "metadata": {
                "file_name": str(item.get("file_name") or ""),
                "mime_type": mime_type,
                "file_size": file_size,
                "tags": list(item.get("tags") or []),
            },
        }


def _join_subtitle(*parts: str) -> str:
    return " · ".join(part for part in (str(part or "").strip() for part in parts) if part)


def _format_file_size(size: int) -> str:
    if size <= 0:
        return ""
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{round(size / 1024)}KB"
    return f"{round(size / 1024 / 1024, 1)}MB"

