from __future__ import annotations

import mimetypes
from typing import Any


WECOM_IMAGE_MIN_BYTES = 5
WECOM_IMAGE_MAX_BYTES = 2 * 1024 * 1024
WECOM_IMAGE_MAX_MB = 2
WECOM_IMAGE_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}

WECOM_ATTACHMENT_MIN_BYTES = 5
WECOM_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
WECOM_ATTACHMENT_MAX_MB = 10
WECOM_ATTACHMENT_MEDIA_TTL_DAYS = 2
WECOM_ATTACHMENT_ALLOWED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rar",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}
WECOM_ATTACHMENT_ALLOWED_MIME_TYPES = {
    "application/msword",
    "application/octet-stream",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-rar-compressed",
    "application/zip",
    "text/csv",
    "text/plain",
}


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


def normalize_wecom_attachment_mime_type(
    mime_type: Any = "",
    *,
    file_name: str = "",
) -> str:
    normalized = str(mime_type or "").split(";", 1)[0].strip().lower()
    if normalized == "application/x-zip-compressed":
        normalized = "application/zip"
    if not normalized and file_name:
        guessed = mimetypes.guess_type(str(file_name))[0] or ""
        normalized = normalize_wecom_attachment_mime_type(guessed)
    return normalized or "application/octet-stream"


def validate_wecom_attachment_upload(
    file_bytes: bytes,
    *,
    file_name: str = "",
    mime_type: Any = "",
) -> str:
    size = len(file_bytes or b"")
    if size < WECOM_ATTACHMENT_MIN_BYTES:
        raise ValueError(f"attachment file is too small (min {WECOM_ATTACHMENT_MIN_BYTES}B)")
    if size > WECOM_ATTACHMENT_MAX_BYTES:
        raise ValueError(f"attachment file is too large (max {WECOM_ATTACHMENT_MAX_MB}MB)")

    suffix = ""
    if file_name:
        import os

        suffix = os.path.splitext(str(file_name).strip().lower())[1]
    if suffix not in WECOM_ATTACHMENT_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(WECOM_ATTACHMENT_ALLOWED_EXTENSIONS))
        raise ValueError(f"attachment file type is not supported by WeCom ({allowed})")

    normalized = normalize_wecom_attachment_mime_type(mime_type, file_name=file_name)
    if normalized not in WECOM_ATTACHMENT_ALLOWED_MIME_TYPES:
        guessed = normalize_wecom_attachment_mime_type("", file_name=file_name)
        if guessed in WECOM_ATTACHMENT_ALLOWED_MIME_TYPES:
            normalized = guessed
        else:
            raise ValueError("attachment content type is not supported by WeCom")

    if suffix == ".pdf" and not (file_bytes or b"").startswith(b"%PDF"):
        raise ValueError("PDF attachment content does not look like a valid PDF")
    return normalized


__all__ = [
    "WECOM_IMAGE_ALLOWED_MIME_TYPES",
    "WECOM_ATTACHMENT_ALLOWED_EXTENSIONS",
    "WECOM_ATTACHMENT_ALLOWED_MIME_TYPES",
    "WECOM_ATTACHMENT_MAX_BYTES",
    "WECOM_ATTACHMENT_MAX_MB",
    "WECOM_ATTACHMENT_MEDIA_TTL_DAYS",
    "WECOM_ATTACHMENT_MIN_BYTES",
    "WECOM_IMAGE_MAX_BYTES",
    "WECOM_IMAGE_MAX_MB",
    "WECOM_IMAGE_MIN_BYTES",
    "detect_wecom_image_mime_type",
    "normalize_wecom_attachment_mime_type",
    "normalize_wecom_image_mime_type",
    "validate_wecom_attachment_upload",
    "validate_wecom_image_upload",
]
