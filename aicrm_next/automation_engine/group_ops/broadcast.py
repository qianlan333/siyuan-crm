from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from aicrm_next.cloud_orchestrator.media_upload import (
    CloudOrchestratorMediaUploadError,
    build_upload_command,
)
from aicrm_next.integration_gateway.lesson_card_cover_client import (
    LessonCardCoverClientError,
    build_lesson_card_cover_client,
)
from aicrm_next.platform_foundation.external_effects import WECOM_MESSAGE_GROUP_SEND
from aicrm_next.platform_foundation.external_effects.models import utcnow
from aicrm_next.platform_foundation.external_effects.repo import (
    ExternalEffectRepository,
    build_external_effect_repository,
)
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.shared.internal_service_tokens import validate_internal_service_token

from .application import ReceiveTrustedGroupOpsBroadcastCommand
from .domain import clean_text
from .dto import GroupOpsTokenBroadcastRequest, GroupOpsWebhookReceiveRequest
from .repo import GroupOpsRepository, build_group_ops_repository


ROUTE_OWNER = "ai_crm_next"
SOURCE_ROUTE = "/api/automation/group-ops/broadcast"
DEFAULT_PLAN_ID = 11
DEFAULT_MINIPROGRAM_APPID = "wx0ca836834b18e989"
MAX_TEXT_LENGTH = 4000
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = MAX_IMAGES * MAX_IMAGE_BYTES
_CARD_PATH = "pages/article/article"
_TITLE_PATTERN = re.compile(r"《([^》]+)》")


class GroupOpsBroadcastError(RuntimeError):
    def __init__(self, error_code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


@dataclass(frozen=True)
class BroadcastImage:
    file_name: str
    content_type: str
    file_bytes: bytes


@dataclass(frozen=True)
class ParsedCardPath:
    normalized_path: str
    lesson_id: str


def internal_broadcast_token_error(headers: Mapping[str, Any]) -> tuple[str, int] | None:
    authorization = clean_text(headers.get("authorization") or headers.get("Authorization"))
    provided = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    result = validate_internal_service_token("group_broadcast", provided)
    if result.error == "internal_token_not_configured":
        return ("broadcast_token_not_configured", 503)
    if not result.ok:
        return ("internal_token_required", 401)
    return None


def parse_card_path(value: str) -> ParsedCardPath:
    raw = clean_text(value)
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or parsed.path != _CARD_PATH or parsed.fragment:
        raise GroupOpsBroadcastError("invalid_card_path", "card_path must be a canonical article mini-program path")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise GroupOpsBroadcastError("invalid_card_path", "card_path query is invalid") from exc
    lesson_values = query.get("lesson_id") or []
    from_values = query.get("from") or []
    if len(lesson_values) != 1 or from_values != ["learn"] or set(query) != {"lesson_id", "from"}:
        raise GroupOpsBroadcastError("invalid_card_path", "card_path must include lesson_id and from=learn")
    try:
        lesson_id = str(UUID(clean_text(lesson_values[0])))
    except (ValueError, AttributeError) as exc:
        raise GroupOpsBroadcastError("invalid_card_path", "card_path lesson_id must be a UUID") from exc
    return ParsedCardPath(
        normalized_path=f"{_CARD_PATH}?lesson_id={lesson_id}&from=learn",
        lesson_id=lesson_id,
    )


def _bounded_utf8(value: str, *, max_bytes: int) -> str:
    result = ""
    for char in clean_text(value):
        candidate = result + char
        if len(candidate.encode("utf-8")) > max_bytes:
            break
        result = candidate
    return result


def derive_card_title(text: str, explicit_title: str = "") -> str:
    title = clean_text(explicit_title)
    if not title:
        match = _TITLE_PATTERN.search(clean_text(text))
        title = clean_text(match.group(1)) if match else "黄小璨 AI 日课"
    return _bounded_utf8(title, max_bytes=128) or "黄小璨 AI 日课"


def _detected_image_type(file_bytes: bytes) -> str:
    data = bytes(file_bytes or b"")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def validate_image(image: BroadcastImage) -> BroadcastImage:
    size = len(image.file_bytes or b"")
    if not size:
        raise GroupOpsBroadcastError("empty_image", "uploaded image is empty")
    if size > MAX_IMAGE_BYTES:
        raise GroupOpsBroadcastError("image_too_large", "each image must be at most 10 MB")
    detected = _detected_image_type(image.file_bytes)
    if not detected:
        raise GroupOpsBroadcastError("invalid_image_content", "uploaded image content is not supported")
    declared = clean_text(image.content_type).lower()
    if declared and declared not in {detected, "image/jpg" if detected == "image/jpeg" else detected}:
        raise GroupOpsBroadcastError("image_content_type_mismatch", "uploaded image content type does not match its bytes")
    return BroadcastImage(
        file_name=clean_text(image.file_name) or "broadcast-image",
        content_type=detected,
        file_bytes=bytes(image.file_bytes),
    )


class ExecuteGroupOpsTokenBroadcastCommand:
    def __init__(
        self,
        *,
        group_repo: GroupOpsRepository | None = None,
        external_effect_repo: ExternalEffectRepository | None = None,
    ) -> None:
        self._group_repo = group_repo or build_group_ops_repository()
        self._external_effect_repo = external_effect_repo or build_external_effect_repository()
        self._external_effect_service = ExternalEffectService(self._external_effect_repo)

    def __call__(
        self,
        request: GroupOpsTokenBroadcastRequest,
        *,
        idempotency_key: str,
        images: list[BroadcastImage] | None = None,
        actor_id: str = "external_group_ops_api",
    ) -> dict[str, Any]:
        key = clean_text(idempotency_key or request.idempotency_key)
        if not key:
            raise GroupOpsBroadcastError("idempotency_key_required", "Idempotency-Key is required")
        if len(key) > 200:
            raise GroupOpsBroadcastError("invalid_idempotency_key", "Idempotency-Key is too long")

        text = clean_text(request.text)
        if len(text) > MAX_TEXT_LENGTH:
            raise GroupOpsBroadcastError("text_too_long", f"text must be at most {MAX_TEXT_LENGTH} characters")
        uploaded_images = list(images or [])
        existing_media_ids = [clean_text(item) for item in request.image_media_ids if clean_text(item)]
        if any(len(item) > 255 or any(char.isspace() for char in item) for item in existing_media_ids):
            raise GroupOpsBroadcastError("invalid_image_media_id", "image media ids must be non-whitespace values up to 255 characters")
        if len(uploaded_images) + len(existing_media_ids) > MAX_IMAGES:
            raise GroupOpsBroadcastError("too_many_images", f"at most {MAX_IMAGES} images are allowed")
        if sum(len(item.file_bytes or b"") for item in uploaded_images) > MAX_TOTAL_IMAGE_BYTES:
            raise GroupOpsBroadcastError("images_too_large", "total uploaded images are too large")

        parsed_card = parse_card_path(request.card_path) if clean_text(request.card_path) else None
        if not text and not parsed_card and not uploaded_images and not existing_media_ids:
            raise GroupOpsBroadcastError("broadcast_content_required", "text, images, or card_path is required")

        plan_id = self._plan_id()
        plan = self._group_repo.get_plan(plan_id)
        if not plan:
            raise GroupOpsBroadcastError("broadcast_plan_not_found", "configured group broadcast plan was not found", status_code=404)
        if plan.get("plan_type") != "webhook":
            raise GroupOpsBroadcastError("broadcast_plan_invalid", "configured group broadcast plan must be a webhook plan", status_code=409)
        if plan.get("status") != "active":
            raise GroupOpsBroadcastError("broadcast_plan_inactive", "configured group broadcast plan is not active", status_code=409)
        if not self._group_repo.list_bound_groups(plan_id):
            raise GroupOpsBroadcastError("broadcast_groups_missing", "configured group broadcast plan has no bound groups", status_code=409)
        duplicate_event = self._group_repo.find_webhook_event(plan_id, key)
        if duplicate_event:
            return self._existing_result(duplicate_event)

        media_ids = list(existing_media_ids)
        for index, image in enumerate(uploaded_images):
            normalized = validate_image(image)
            media_ids.append(
                self._upload_image(
                    image=normalized,
                    idempotency_key=f"{key}:image:{index + 1}",
                    actor_id=actor_id,
                )
            )

        card_media_id = ""
        card_title = ""
        if parsed_card:
            card_image = self._download_lesson_cover(parsed_card.lesson_id)
            card_media_id = self._upload_image(
                image=card_image,
                idempotency_key=f"{key}:card-cover",
                actor_id=actor_id,
            )
            card_title = derive_card_title(text, request.card_title)

        attachments: list[dict[str, Any]] = [
            {"msgtype": "image", "image": {"media_id": media_id}}
            for media_id in media_ids
        ]
        if parsed_card:
            attachments.append(
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {
                        "appid": self._miniprogram_appid(),
                        "page": parsed_card.normalized_path,
                        "title": card_title,
                        "pic_media_id": card_media_id,
                    },
                }
            )

        enqueue = ReceiveTrustedGroupOpsBroadcastCommand(self._group_repo)(
            plan_id,
            GroupOpsWebhookReceiveRequest(
                idempotency_key=key,
                send_mode="queued",
                scheduled_at=(utcnow() + timedelta(minutes=2)).isoformat(),
                event="group_ops_api_broadcast",
                source="group_ops_token_broadcast_api",
                content={"text": text, "attachments": attachments},
            ),
            idempotency_key=key,
        )
        job_ids = [int(item) for item in list(enqueue.get("external_effect_job_ids") or []) if int(item or 0) > 0]
        if len(job_ids) != 1:
            raise GroupOpsBroadcastError("broadcast_job_not_created", "group broadcast job was not created", status_code=503)
        return self._dispatch_result(
            job_ids[0],
            event_id=int((enqueue.get("event") or {}).get("id") or 0),
            duplicate=False,
            text_present=bool(text),
            image_count=len(media_ids),
            uploaded_image_count=len(uploaded_images),
            card_attached=bool(parsed_card),
            card_title=card_title,
        )

    def _plan_id(self) -> int:
        try:
            value = int(clean_text(os.getenv("AICRM_GROUP_OPS_BROADCAST_PLAN_ID")) or DEFAULT_PLAN_ID)
        except ValueError as exc:
            raise GroupOpsBroadcastError("broadcast_plan_not_configured", "group broadcast plan id is invalid", status_code=503) from exc
        if value <= 0:
            raise GroupOpsBroadcastError("broadcast_plan_not_configured", "group broadcast plan id is invalid", status_code=503)
        return value

    def _miniprogram_appid(self) -> str:
        appid = clean_text(os.getenv("AICRM_GROUP_OPS_MINIPROGRAM_APPID")) or DEFAULT_MINIPROGRAM_APPID
        if not appid:
            raise GroupOpsBroadcastError("miniprogram_appid_not_configured", "mini-program appid is not configured", status_code=503)
        return appid

    def _download_lesson_cover(self, lesson_id: str) -> BroadcastImage:
        try:
            cover = build_lesson_card_cover_client().download(lesson_id)
        except LessonCardCoverClientError as exc:
            raise GroupOpsBroadcastError("lesson_cover_download_failed", "lesson card cover download failed", status_code=502) from exc
        return validate_image(
            BroadcastImage(
                file_name=cover.file_name,
                content_type=cover.content_type,
                file_bytes=cover.file_bytes,
            )
        )

    def _upload_image(self, *, image: BroadcastImage, idempotency_key: str, actor_id: str) -> str:
        try:
            result = build_upload_command(
                idempotency_key=idempotency_key,
                actor_id=clean_text(actor_id) or "external_group_ops_api",
                actor_type="machine_api",
                trace_id=idempotency_key,
            )(
                file_name=image.file_name,
                file_bytes=image.file_bytes,
                content_type=image.content_type,
            )
        except (CloudOrchestratorMediaUploadError, ValueError) as exc:
            raise GroupOpsBroadcastError("media_upload_failed", "WeCom media upload failed", status_code=502) from exc
        media_id = clean_text(result.get("media_id"))
        if not media_id:
            raise GroupOpsBroadcastError("media_upload_failed", "WeCom media upload returned no media id", status_code=502)
        return media_id

    def _existing_result(self, event: dict[str, Any]) -> dict[str, Any]:
        job = self._external_effect_service.find_existing_job(
            effect_type=WECOM_MESSAGE_GROUP_SEND,
            target_type="group_ops_webhook_event",
            target_id=str(int(event.get("id") or 0)),
            business_type="group_ops_plan",
            business_id=str(int(event.get("plan_id") or self._plan_id())),
        )
        if job is None:
            raise GroupOpsBroadcastError("broadcast_job_not_found", "idempotent broadcast job was not found", status_code=503)
        return self._job_result(job.id, event_id=int(event.get("id") or 0), duplicate=True)

    def _dispatch_result(
        self,
        job_id: int,
        *,
        event_id: int,
        duplicate: bool,
        text_present: bool,
        image_count: int,
        uploaded_image_count: int,
        card_attached: bool,
        card_title: str,
    ) -> dict[str, Any]:
        ExternalEffectWorker(
            self._external_effect_repo,
            locked_by=f"group-ops-broadcast-{job_id}",
        ).dispatch_one(job_id)
        return self._job_result(
            job_id,
            event_id=event_id,
            duplicate=duplicate,
            content={
                "text_present": text_present,
                "image_count": image_count,
                "uploaded_image_count": uploaded_image_count,
                "card_attached": card_attached,
                "card_title": card_title,
            },
        )

    def _job_result(
        self,
        job_id: int,
        *,
        event_id: int,
        duplicate: bool,
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = self._external_effect_service.get(job_id)
        attempts = self._external_effect_service.list_attempts(job_id)
        attempt = attempts[-1] if attempts else None
        summary = dict(attempt.response_summary_json or {}) if attempt else {}
        status = clean_text(job.status if job else "")
        ok = status == "succeeded" and bool(summary.get("exact_target_verified"))
        return {
            "ok": ok,
            "status": status or "unknown",
            "duplicate": bool(duplicate),
            "event_id": int(event_id or 0),
            "external_effect_job_id": int(job_id),
            "attempt_status": clean_text(attempt.status if attempt else ""),
            "error_code": clean_text((attempt.error_code if attempt else "") or (job.last_error_code if job else "")),
            "error_message": clean_text((attempt.error_message if attempt else "") or (job.last_error_message if job else "")),
            "requested_chat_count": int(summary.get("requested_chat_count") or 0),
            "exact_target_verified": bool(summary.get("exact_target_verified")),
            "wecom_msgid_present": bool(summary.get("wecom_msgid_present")),
            "real_external_call_executed": bool(summary.get("real_external_call_executed")),
            "wecom_send_executed": bool(summary.get("wecom_send_executed")),
            "content": dict(content or {}),
            "route_owner": ROUTE_OWNER,
        }
