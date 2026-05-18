from __future__ import annotations

import base64

from flask import request

from ..domains.wecom_media_limits import (
    detect_wecom_image_mime_type,
    validate_wecom_image_upload,
)


def _detect_stage_send_image_type(file_bytes: bytes) -> str:
    detected = detect_wecom_image_mime_type(file_bytes)
    if detected == "image/png":
        return "png"
    if detected == "image/jpeg":
        return "jpeg"
    return ""


def _stage_send_images_from_request() -> list[dict[str, str]]:
    files = [item for item in list(request.files.getlist("images") or []) if getattr(item, "filename", "")]
    if len(files) > 3:
        raise ValueError("at most 3 images are allowed")
    images: list[dict[str, str]] = []
    for index, file_storage in enumerate(files, start=1):
        file_name = str(getattr(file_storage, "filename", "") or f"image-{index}.png").strip() or f"image-{index}.png"
        mime_type = str(getattr(file_storage, "mimetype", "") or "").strip().lower()
        if not mime_type.startswith("image/"):
            raise ValueError("only image files are allowed")
        file_bytes = file_storage.read()
        content_type = validate_wecom_image_upload(
            file_bytes,
            file_name=file_name,
            mime_type=mime_type,
        )
        images.append(
            {
                "file_name": file_name,
                "content_type": content_type,
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )
    return images
