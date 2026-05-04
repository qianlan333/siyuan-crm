from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..observability import (
    background_context,
    generate_job_id,
    get_request_id,
)

task_logger = logging.getLogger("task_queue")

_rq_queue = None
_rq_available = False
_thread_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wecom-bg")


def _rq_default_timeout() -> int:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            raw = current_app.config.get("RQ_DEFAULT_TIMEOUT")
            if raw not in (None, ""):
                return max(int(raw), 10)
    except Exception:
        pass
    return 300


def _try_init_rq(redis_url: str) -> bool:
    global _rq_queue, _rq_available
    try:
        from redis import Redis
        from rq import Queue

        conn = Redis.from_url(redis_url)
        conn.ping()
        _rq_queue = Queue(connection=conn, default_timeout=_rq_default_timeout())
        _rq_available = True
        task_logger.info("RQ task queue initialized redis_url=%s", redis_url)
        return True
    except Exception as exc:
        _rq_available = False
        _rq_queue = None
        task_logger.warning("RQ unavailable, falling back to ThreadPoolExecutor: %s", exc)
        return False


def init_task_queue(app) -> None:
    redis_url = app.config.get("REDIS_URL", "").strip()
    if redis_url:
        _try_init_rq(redis_url)
    else:
        task_logger.info("REDIS_URL not configured, using ThreadPoolExecutor fallback")


def enqueue_task(
    task_fn: Callable,
    *args: Any,
    task_name: str = "",
    retry_max: int = 0,
    idempotency_key: str = "",
    task_timeout: int | None = None,
    on_failure: Callable | None = None,
    **kwargs: Any,
) -> str | None:
    """Enqueue ``task_fn`` for background execution.

    ``idempotency_key``: when given, RQ uses ``hash(key)`` as the job id, so
    a second enqueue of the same logical task collapses into the original
    instead of double-running. The thread fallback can't dedup across worker
    processes; document this asymmetry rather than silently misbehave.

    ``task_timeout`` overrides the queue default for this one job (RQ only
    — the thread fallback has no timeout primitive).

    ``on_failure``: optional RQ failure-callback for routing into a DLQ.
    """
    label = task_name or getattr(task_fn, "__name__", "unknown")
    parent_request_id = get_request_id()
    normalized_key = str(idempotency_key or "").strip()
    if normalized_key:
        # Stable, RQ-safe job id derived from the caller-supplied key.
        import hashlib

        job_id_hint = "idem-" + hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:32]
    else:
        job_id_hint = generate_job_id()
    resolved_timeout = int(task_timeout) if task_timeout is not None else _rq_default_timeout()

    if _rq_available and _rq_queue is not None:
        try:
            # Skip enqueue when an in-flight job with this idempotency key
            # already exists.
            if normalized_key:
                from rq.job import Job

                try:
                    existing = Job.fetch(job_id_hint, connection=_rq_queue.connection)
                    if existing and existing.get_status(refresh=False) in {
                        "queued",
                        "started",
                        "deferred",
                        "scheduled",
                    }:
                        task_logger.info(
                            "task dedup hit task=%s idempotency_key=%s job_id=%s",
                            label,
                            normalized_key,
                            existing.id,
                        )
                        return existing.id
                except Exception:
                    # Job not found (or backend hiccup) — fall through and
                    # enqueue normally.
                    pass

            enqueue_kwargs = {
                "args": (task_fn, args, kwargs, {
                    "task_name": label,
                    "parent_request_id": parent_request_id,
                    "job_id": job_id_hint,
                }),
                "job_timeout": resolved_timeout,
                "retry": _build_rq_retry(retry_max) if retry_max else None,
                "description": label,
                "meta": {
                    "task_name": label,
                    "parent_request_id": parent_request_id,
                    "job_id": job_id_hint,
                    "idempotency_key": normalized_key,
                },
            }
            if normalized_key:
                enqueue_kwargs["job_id"] = job_id_hint
            if on_failure is not None:
                enqueue_kwargs["on_failure"] = on_failure

            job = _rq_queue.enqueue(_rq_task_runner, **enqueue_kwargs)
            task_logger.info(
                "task enqueued via RQ task=%s job_id=%s parent_request_id=%s idempotency_key=%s",
                label,
                job.id,
                parent_request_id,
                normalized_key,
            )
            return job.id
        except Exception:
            task_logger.exception("RQ enqueue failed, falling back to thread task=%s", label)

    # Thread fallback also runs the task inside a background_context so log
    # lines emitted by the work include the propagated parent_request_id.
    future = _thread_executor.submit(
        _thread_task_runner,
        task_fn,
        args,
        kwargs,
        label,
        parent_request_id,
        job_id_hint,
    )
    task_logger.info(
        "task submitted to ThreadPoolExecutor task=%s parent_request_id=%s",
        label,
        parent_request_id,
    )
    return None


def _thread_task_runner(
    task_fn: Callable,
    args: tuple,
    kwargs: dict,
    task_name: str,
    parent_request_id: str,
    job_id: str,
) -> Any:
    with background_context(job_id=job_id, parent_request_id=parent_request_id, task_name=task_name):
        try:
            return task_fn(*args, **kwargs)
        except Exception:
            task_logger.exception("background task failed task=%s job_id=%s", task_name, job_id)
            raise


def _rq_task_runner(task_fn: Callable, args: tuple, kwargs: dict, ctx: dict) -> Any:
    """Top-level RQ entry point that re-establishes observability context.

    RQ pickles this function name, so it must remain importable from a stable
    path. The wrapper restores ``parent_request_id`` / ``job_id`` /
    ``task_name`` so worker logs are stitched to the originating HTTP request.
    """
    with background_context(
        job_id=ctx.get("job_id", ""),
        parent_request_id=ctx.get("parent_request_id", ""),
        task_name=ctx.get("task_name", ""),
    ):
        return task_fn(*args, **kwargs)


def _build_rq_retry(max_retries: int):
    try:
        from rq import Retry
        return Retry(max=max_retries, interval=[30, 60, 120])
    except ImportError:
        return None


def get_queue_depth() -> int:
    if _rq_available and _rq_queue is not None:
        try:
            return len(_rq_queue)
        except Exception:
            return -1
    return _thread_executor._work_queue.qsize()


def is_rq_active() -> bool:
    return _rq_available
