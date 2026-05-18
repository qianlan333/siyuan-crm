"""Cloud Orchestrator media helpers."""

from __future__ import annotations

import logging

from ...wecom_client import WeComClient, WeComClientError
from ..wecom_media_limits import validate_wecom_image_upload


logger = logging.getLogger(__name__)


class CloudOrchestratorMediaUploadError(RuntimeError):
    """Cloud Orchestrator media upload failed at the WeCom boundary."""


def upload_cloud_orchestrator_image(
    *,
    file_name: str,
    file_bytes: bytes,
    content_type: str,
) -> dict[str, object]:
    """Validate and upload an admin-selected Cloud Orchestrator image to WeCom."""

    normalized_file_name = str(file_name or "").strip()
    normalized_content_type = str(content_type or "").strip().lower()
    if not normalized_file_name:
        raise ValueError("missing image")
    if not normalized_content_type.startswith("image/"):
        raise ValueError(f"only image/* allowed, got {normalized_content_type}")
    if not file_bytes:
        raise ValueError("empty file")

    normalized_content_type = validate_wecom_image_upload(
        file_bytes,
        file_name=normalized_file_name,
        mime_type=normalized_content_type,
    )
    try:
        client = WeComClient.from_app()
        media_id = client._upload_private_message_image(
            normalized_file_name,
            file_bytes,
            normalized_content_type,
        )
    except WeComClientError as exc:
        logger.exception("cloud orchestrator image upload failed")
        raise CloudOrchestratorMediaUploadError(f"wecom upload failed: {exc}") from exc
    return {
        "media_id": media_id,
        "file_name": normalized_file_name,
        "content_type": normalized_content_type,
        "size": len(file_bytes),
    }


__all__ = [
    "CloudOrchestratorMediaUploadError",
    "upload_cloud_orchestrator_image",
]
