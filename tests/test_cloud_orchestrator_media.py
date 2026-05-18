from __future__ import annotations

import pytest

from wecom_ability_service.domains.cloud_orchestrator import media
from wecom_ability_service.wecom_client import WeComClientError


def test_upload_cloud_orchestrator_image_validates_and_uploads_to_wecom(monkeypatch):
    uploaded: dict[str, object] = {}

    class _FakeWeComClient:
        def _upload_private_message_image(self, file_name: str, file_bytes: bytes, content_type: str) -> str:
            uploaded.update(
                {
                    "file_name": file_name,
                    "file_bytes": file_bytes,
                    "content_type": content_type,
                }
            )
            return "media-cloud-001"

    monkeypatch.setattr(media.WeComClient, "from_app", staticmethod(lambda: _FakeWeComClient()))

    file_bytes = b"\x89PNG\r\n\x1a\nvalid"
    result = media.upload_cloud_orchestrator_image(
        file_name="campaign.png",
        file_bytes=file_bytes,
        content_type="image/png",
    )

    assert uploaded == {
        "file_name": "campaign.png",
        "file_bytes": file_bytes,
        "content_type": "image/png",
    }
    assert result == {
        "media_id": "media-cloud-001",
        "file_name": "campaign.png",
        "content_type": "image/png",
        "size": len(file_bytes),
    }


def test_upload_cloud_orchestrator_image_wraps_wecom_upload_errors(monkeypatch):
    class _FakeWeComClient:
        def _upload_private_message_image(self, file_name: str, file_bytes: bytes, content_type: str) -> str:
            raise WeComClientError("token expired")

    monkeypatch.setattr(media.WeComClient, "from_app", staticmethod(lambda: _FakeWeComClient()))

    with pytest.raises(media.CloudOrchestratorMediaUploadError, match="wecom upload failed: token expired"):
        media.upload_cloud_orchestrator_image(
            file_name="campaign.png",
            file_bytes=b"\x89PNG\r\n\x1a\nvalid",
            content_type="image/png",
        )
