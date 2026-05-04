from __future__ import annotations

import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from flask import Flask, Response, current_app, g, has_app_context, has_request_context, request

REQUEST_ID_HEADER = "X-Request-Id"
_job_id_ctx: ContextVar[str] = ContextVar("job_id", default="")
_parent_request_id_ctx: ContextVar[str] = ContextVar("parent_request_id", default="")
_task_name_ctx: ContextVar[str] = ContextVar("task_name", default="")

# Two PII patterns we want to mask in *log records* (not in storage):
#   - 11-digit Mainland China mobiles like 13800138000
#   - WeCom external_userid prefixed with ``wm`` followed by 18+ alnum chars
# Both can leak into request paths (``/api/customers/wm.../tags``,
# ``/api/lookup?mobile=...``) and end up in our INFO/WARNING lines. We mask
# at the formatter layer rather than touching call sites.
_MOBILE_RE = re.compile(r"(?<!\d)(1\d{2})(\d{4})(\d{4})(?!\d)")
_EXTERNAL_USERID_RE = re.compile(r"\b(wm[A-Za-z0-9_\-]{4,})\b")


def mask_pii(value: str) -> str:
    """Mask PII tokens for log emission. Empty / non-strings pass through."""
    if not value:
        return value
    text = str(value)
    text = _MOBILE_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", text)
    text = _EXTERNAL_USERID_RE.sub(lambda m: m.group(1)[:4] + "***" + m.group(1)[-2:], text)
    return text


def generate_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str:
    if has_request_context():
        return str(getattr(g, "request_id", "") or "").strip()
    return ""


def get_release_sha() -> str:
    if has_app_context():
        return str(current_app.config.get("RELEASE_SHA", "") or "").strip()
    return ""


def generate_job_id() -> str:
    return uuid.uuid4().hex


def get_job_id() -> str:
    return str(_job_id_ctx.get("") or "").strip()


def get_parent_request_id() -> str:
    return str(_parent_request_id_ctx.get("") or "").strip()


def get_task_name() -> str:
    return str(_task_name_ctx.get("") or "").strip()


def bind_background_context(*, job_id: str, parent_request_id: str, task_name: str) -> dict[str, object]:
    return {
        "job_id": _job_id_ctx.set(str(job_id or "").strip()),
        "parent_request_id": _parent_request_id_ctx.set(str(parent_request_id or "").strip()),
        "task_name": _task_name_ctx.set(str(task_name or "").strip()),
    }


def unbind_background_context(tokens: dict[str, object] | None) -> None:
    if not tokens:
        return
    _job_id_ctx.reset(tokens["job_id"])
    _parent_request_id_ctx.reset(tokens["parent_request_id"])
    _task_name_ctx.reset(tokens["task_name"])


@contextmanager
def background_context(*, job_id: str = "", parent_request_id: str = "", task_name: str = ""):
    """Context-manager flavour of bind/unbind for background scripts and RQ
    workers. Pairs request_id propagation across the HTTP→queue boundary.
    """
    tokens = bind_background_context(
        job_id=job_id or generate_job_id(),
        parent_request_id=parent_request_id,
        task_name=task_name,
    )
    try:
        yield
    finally:
        unbind_background_context(tokens)


def _get_request_method() -> str:
    if has_request_context():
        return str(request.method or "").strip()
    return ""


def _get_request_path() -> str:
    if has_request_context():
        return str(request.path or "").strip()
    return ""


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.release_sha = get_release_sha()
        record.method = _get_request_method()
        # Mask PII before it lands in any handler — primarily request paths
        # like /api/customers/wm.../tags or /api/lookup?mobile=...
        record.path = mask_pii(_get_request_path())
        record.job_id = get_job_id()
        record.parent_request_id = get_parent_request_id()
        record.task_name = get_task_name()
        # Best-effort scrub the rendered message too. Format is unchanged
        # for records without PII tokens.
        try:
            if record.args:
                masked_args = tuple(mask_pii(a) if isinstance(a, str) else a for a in record.args)
                record.args = masked_args
            if isinstance(record.msg, str):
                record.msg = mask_pii(record.msg)
        except Exception:
            pass
        return True


def attach_logging_filter(handler: logging.Handler) -> None:
    if not any(isinstance(item, RequestContextFilter) for item in handler.filters):
        handler.addFilter(RequestContextFilter())


def register_request_observability(app: Flask) -> None:
    @app.before_request
    def _bind_request_id() -> None:
        request_id = str(request.headers.get(REQUEST_ID_HEADER, "") or "").strip()
        g.request_id = request_id or generate_request_id()

    @app.after_request
    def _write_request_id(response: Response) -> Response:
        response.headers[REQUEST_ID_HEADER] = get_request_id()
        return response
