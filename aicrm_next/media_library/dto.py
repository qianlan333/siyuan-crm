from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImageUpsertRequest(BaseModel):
    name: str | None = None
    file_name: str = "fixture.png"
    content_type: str = "image/png"
    mime_type: str | None = None
    file_size: int = 0
    width: int = 1
    height: int = 1
    data_url: str = "data:image/png;base64,ZmFrZQ=="
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    category: str = ""
    enabled: bool | None = None
    ai_metadata: dict[str, Any] = Field(default_factory=dict)


class ImageFromUrlRequest(BaseModel):
    url: str
    name: str | None = None
    tags: list[str] = Field(default_factory=list)


class ImageFromBase64Request(BaseModel):
    data_base64: str = ""
    data_url: str = ""
    name: str | None = None
    file_name: str = "base64.png"
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_data_url_alias(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        data_base64 = str(values.get("data_base64") or "").strip()
        data_url = str(values.get("data_url") or "").strip()
        if not data_base64 and data_url:
            _, separator, body = data_url.partition(",")
            values = {**values, "data_base64": body if separator else data_url}
        if not str(values.get("data_base64") or "").strip():
            raise ValueError("data_base64 or data_url is required")
        return values


class AttachmentUpsertRequest(BaseModel):
    name: str | None = None
    file_name: str = "attachment.bin"
    mime_type: str = "application/octet-stream"
    file_size: int = 0
    data_base64: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class MiniprogramUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    title: str | None = None
    appid: str | None = None
    page_path: str | None = Field(default=None, alias="pagepath")
    thumb_image_id: str | int | None = None
    thumb_media_id: str | None = None
    resolve_thumb_media: bool = True
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_page_path_aliases(cls, values: Any) -> Any:
        if isinstance(values, dict):
            updated = dict(values)
            if "pagepath" not in updated and "page_path" in updated:
                updated["pagepath"] = updated.get("page_path")
            if "appid" not in updated and "app_id" in updated:
                updated["appid"] = updated.get("app_id")
            return updated
        return values
