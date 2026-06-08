from __future__ import annotations

import base64
import mimetypes
import re
from urllib.parse import urlparse


def _download_filename(channel: dict) -> str:
    name = str(channel.get("channel_name") or "").strip()
    code = str(channel.get("channel_code") or channel.get("id") or "channel").strip()
    raw = "_".join(part for part in (name, code) if part)
    safe = re.sub(r"[^\w.-]+", "_", raw, flags=re.UNICODE).strip("._") or "channel"
    return f"{safe}.png"


def _image_mimetype_from_bytes(content: bytes, fallback: str = "image/png") -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def _downloadable_qrcode_image(qr_url: str) -> tuple[bytes, str] | None:
    value = str(qr_url or "").strip()
    if not value:
        return None
    if value.startswith("data:image/") and "," in value:
        header, encoded = value.split(",", 1)
        try:
            mime = header.split(";", 1)[0].removeprefix("data:") or "image/png"
            return base64.b64decode(encoded), mime
        except Exception:
            return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        import requests

        response = requests.get(value, timeout=8)
        if response.status_code >= 400:
            return None
        content = bytes(response.content or b"")
        if not content:
            return None
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        guessed = mimetypes.guess_type(parsed.path or "")[0] or ""
        if content_type.startswith("image/"):
            return content, content_type
        if guessed.startswith("image/") or content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")):
            return content, _image_mimetype_from_bytes(content, guessed or "image/png")
    except Exception:
        return None
    return None


def build_channel_qrcode_download(channel: dict) -> dict | None:
    image = _downloadable_qrcode_image(str(channel.get("qr_url") or ""))
    if image:
        content, mimetype = image
        return {"content": content, "mimetype": mimetype, "filename": _download_filename(channel)}
    return None
