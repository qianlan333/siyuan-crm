from __future__ import annotations

import mimetypes
from typing import Any


WECOM_IMAGE_MIN_BYTES = 5
WECOM_IMAGE_MAX_BYTES = 2 * 1024 * 1024
WECOM_IMAGE_MAX_MB = 2
WECOM_IMAGE_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}


def detect_wecom_image_mime_type(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return ""


def normalize_wecom_image_mime_type(
    mime_type: Any = "",
    *,
    file_name: str = "",
) -> str:
    normalized = str(mime_type or "").split(";", 1)[0].strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if not normalized and file_name:
        guessed = mimetypes.guess_type(str(file_name))[0] or ""
        normalized = normalize_wecom_image_mime_type(guessed)
    return normalized


def validate_wecom_image_upload(
    file_bytes: bytes,
    *,
    file_name: str = "",
    mime_type: Any = "",
) -> str:
    size = len(file_bytes or b"")
    if size < WECOM_IMAGE_MIN_BYTES:
        raise ValueError(f"image file is too small (min {WECOM_IMAGE_MIN_BYTES}B)")
    if size > WECOM_IMAGE_MAX_BYTES:
        raise ValueError(f"image file is too large (max {WECOM_IMAGE_MAX_MB}MB)")

    declared_type = normalize_wecom_image_mime_type(mime_type, file_name=file_name)
    detected_type = detect_wecom_image_mime_type(file_bytes)
    if not detected_type or detected_type not in WECOM_IMAGE_ALLOWED_MIME_TYPES:
        raise ValueError("only JPG/PNG images are supported by WeCom")
    if declared_type and detected_type and declared_type != detected_type:
        raise ValueError("image content type does not match file bytes")
    return detected_type


__all__ = [
    "WECOM_IMAGE_ALLOWED_MIME_TYPES",
    "WECOM_IMAGE_MAX_BYTES",
    "WECOM_IMAGE_MAX_MB",
    "WECOM_IMAGE_MIN_BYTES",
    "detect_wecom_image_mime_type",
    "normalize_wecom_image_mime_type",
    "validate_wecom_image_upload",
]
