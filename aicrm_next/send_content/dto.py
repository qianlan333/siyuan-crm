from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


class SendContentPackage(BaseModel):
    content_text: str = ""
    image_library_ids: list[Any] = Field(default_factory=list)
    miniprogram_library_ids: list[Any] = Field(default_factory=list)
    attachment_library_ids: list[Any] = Field(default_factory=list)


class SendContentValidateRequest(BaseModel):
    content_package: SendContentPackage = Field(default_factory=SendContentPackage)
    text_enabled: bool = True
    require_body: bool = True


class SendContentPreviewRequest(BaseModel):
    content_package: SendContentPackage = Field(default_factory=SendContentPackage)
    text_enabled: bool = True
    require_body: bool = True


class MaterialPickerListRequest(BaseModel):
    type: Literal["image", "miniprogram", "attachment"]
    q: str = ""
    enabled_only: bool = True
    limit: int = 50
    offset: int = 0
