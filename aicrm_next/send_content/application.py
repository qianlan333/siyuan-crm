from __future__ import annotations

from typing import Any

from aicrm_next.shared.errors import ContractError
from aicrm_next.shared.repository_provider import RepositoryProviderError, blocked_production_payload

from .dto import MaterialPickerListRequest, SendContentPackage, SendContentPreviewRequest, SendContentValidateRequest
from .repo import SendContentRepository, build_send_content_repository


def normalize_send_content_package(
    content_package: SendContentPackage | dict[str, Any] | None,
    *,
    text_enabled: bool = True,
    require_body: bool = True,
) -> dict[str, Any]:
    if content_package is None:
        content_package = SendContentPackage()
    if not isinstance(content_package, SendContentPackage):
        content_package = SendContentPackage.model_validate(content_package)
    content_text = str(content_package.content_text or "").strip()
    if not text_enabled:
        content_text = ""
    if len(content_text) > 4000:
        raise ContractError("文本内容不能超过 4000 字")
    image_ids = _normalize_ids(content_package.image_library_ids, field_name="image_library_ids", max_count=3)
    miniprogram_ids = _normalize_ids(content_package.miniprogram_library_ids, field_name="miniprogram_library_ids", max_count=1)
    attachment_ids = _normalize_ids(content_package.attachment_library_ids, field_name="attachment_library_ids", max_count=9)
    normalized = {
        "content_text": content_text,
        "image_library_ids": image_ids,
        "miniprogram_library_ids": miniprogram_ids,
        "attachment_library_ids": attachment_ids,
    }
    if require_body and not any([content_text, image_ids, miniprogram_ids, attachment_ids]):
        raise ContractError("内容包不能为空，请填写文本或选择素材")
    return normalized


class NormalizeSendContentPackageCommand:
    def execute(
        self,
        content_package: SendContentPackage | dict[str, Any],
        *,
        text_enabled: bool = True,
        require_body: bool = True,
    ) -> dict[str, Any]:
        return normalize_send_content_package(
            content_package,
            text_enabled=text_enabled,
            require_body=require_body,
        )

    __call__ = execute


class PreviewSendContentPackageQuery:
    def __init__(self, repo: SendContentRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: SendContentPreviewRequest) -> dict[str, Any]:
        content_package = normalize_send_content_package(
            request.content_package,
            text_enabled=request.text_enabled,
            require_body=request.require_body,
        )
        repo = self._repo_or_build()
        materials = _preview_materials(repo, content_package)
        return {
            "ok": True,
            "content_package": content_package,
            "preview": {
                "content_text": content_package["content_text"],
                "material_summary": {
                    "image_count": len(content_package["image_library_ids"]),
                    "miniprogram_count": len(content_package["miniprogram_library_ids"]),
                    "attachment_count": len(content_package["attachment_library_ids"]),
                },
                "materials": materials,
            },
        }

    def _repo_or_build(self) -> SendContentRepository:
        if self._repo is None:
            self._repo = build_send_content_repository()
        return self._repo

    __call__ = execute


class ListMaterialPickerItemsQuery:
    def __init__(self, repo: SendContentRepository | None = None) -> None:
        self._repo = repo

    def execute(self, request: MaterialPickerListRequest) -> dict[str, Any]:
        repo = self._repo_or_build()
        limit = max(1, min(int(request.limit or 50), 100))
        offset = max(0, int(request.offset or 0))
        result = repo.list_materials(
            request.type,
            q=request.q,
            enabled_only=request.enabled_only,
            limit=limit,
            offset=offset,
        )
        items = [_picker_item_with_flat_metadata(item) for item in result.get("items") or []]
        if request.type == "attachment":
            items = [item for item in items if str(item.get("mime_type") or "").split(";")[0].strip().lower() == "application/pdf"]
        return {
            "ok": True,
            "type": request.type,
            "items": items,
            "total": len(items) if request.type == "attachment" else int(result.get("total") or 0),
            "limit": limit,
            "offset": offset,
        }

    def _repo_or_build(self) -> SendContentRepository:
        if self._repo is None:
            self._repo = build_send_content_repository()
        return self._repo

    __call__ = execute


def _picker_item_with_flat_metadata(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
    for key in ("file_name", "mime_type", "file_size"):
        if key not in normalized and key in metadata:
            normalized[key] = metadata[key]
    return normalized


def send_content_production_unavailable_payload(detail: str | None = None) -> dict[str, Any]:
    payload = blocked_production_payload(
        capability_owner="aicrm_next.send_content",
        detail=detail or "send content production repository is unavailable.",
    )
    payload.update({"status_code": 503, "error_code": "production_unavailable", "route_owner": "ai_crm_next"})
    return payload


def _normalize_ids(values: list[Any], *, field_name: str, max_count: int) -> list[int]:
    normalized: list[int] = []
    for raw in values or []:
        if isinstance(raw, bool):
            raise ContractError(f"{field_name} 必须是正整数")
        try:
            item_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise ContractError(f"{field_name} 必须是正整数") from exc
        if item_id <= 0:
            raise ContractError(f"{field_name} 必须是正整数")
        if item_id not in normalized:
            normalized.append(item_id)
    if len(normalized) > max_count:
        raise ContractError(f"{field_name} 最多允许 {max_count} 个")
    return normalized


def _preview_materials(repo: SendContentRepository, content_package: dict[str, Any]) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for material_type, field in (
        ("image", "image_library_ids"),
        ("miniprogram", "miniprogram_library_ids"),
        ("attachment", "attachment_library_ids"),
    ):
        rows = repo.get_materials_by_ids(material_type, list(content_package.get(field) or []))
        materials.extend(
            {
                "type": item["type"],
                "library_id": item["library_id"],
                "title": item.get("title") or "",
                "thumbnail_url": item.get("thumbnail_url") or "",
                "subtitle": item.get("subtitle") or "",
                "enabled": bool(item.get("enabled", True)),
                "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            }
            for item in rows
        )
    return materials
