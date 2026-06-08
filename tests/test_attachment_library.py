from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains import attachment_library
from wecom_ability_service.domains.wecom_media_limits import validate_wecom_attachment_upload


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def test_validate_wecom_attachment_upload_allows_pdf_and_rejects_oversize():
    assert (
        validate_wecom_attachment_upload(
            PDF_BYTES,
            file_name="welcome-guide.pdf",
            mime_type="application/pdf",
        )
        == "application/pdf"
    )

    with pytest.raises(ValueError, match="too large"):
        validate_wecom_attachment_upload(
            b"%PDF-" + (b"x" * (10 * 1024 * 1024)),
            file_name="large.pdf",
            mime_type="application/pdf",
        )


def test_attachment_library_upload_and_resolve_media_id(app):
    with app.app_context():
        item = attachment_library.create_attachment_from_upload(
            file_bytes=PDF_BYTES,
            file_name="welcome-guide.pdf",
            mime_type="application/pdf",
            name="欢迎资料 PDF",
            tags=["欢迎语", "PDF"],
        )
        upload_calls = []

        def _upload(file_name: str, file_bytes: bytes, content_type: str) -> str:
            upload_calls.append((file_name, file_bytes, content_type))
            return "file-media-pdf-001"

        media_id = attachment_library.resolve_attachment_media_id(item["id"], upload_file=_upload)

        assert media_id == "file-media-pdf-001"
        assert upload_calls == [("welcome-guide.pdf", PDF_BYTES, "application/pdf")]
        refreshed = attachment_library.get_attachment(item["id"])
        assert refreshed["media_id"] == "file-media-pdf-001"


def test_attachment_library_upload_endpoint_accepts_pdf(app, client):
    response = client.post(
        "/api/admin/attachment-library/upload",
        data={
            "file": (BytesIO(PDF_BYTES), "welcome-guide.pdf"),
            "name": "欢迎资料 PDF",
            "tags": "欢迎语,PDF",
        },
        content_type="multipart/form-data",
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["item"]["file_name"] == "welcome-guide.pdf"
    assert payload["item"]["tags"] == ["欢迎语", "PDF"]


def test_private_message_payload_expands_attachment_library_ids(app):
    from wecom_ability_service.domains.user_ops import page_service

    with app.app_context():
        item = attachment_library.create_attachment_from_upload(
            file_bytes=PDF_BYTES,
            file_name="pool-guide.pdf",
            mime_type="application/pdf",
            name="群发资料 PDF",
        )
        get_db().execute(
            """
            UPDATE attachment_library
            SET media_id = ?, media_id_expires_at = ?
            WHERE id = ?
            """,
            (
                "file-media-pool-guide",
                (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                item["id"],
            ),
        )
        get_db().commit()

        payload, content_preview, image_count = page_service._build_private_message_payload(
            {"content": "", "attachment_library_ids": [item["id"]]}
        )

    assert content_preview == ""
    assert image_count == 0
    assert payload == {"attachments": [{"msgtype": "file", "file": {"media_id": "file-media-pool-guide"}}]}
