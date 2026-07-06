#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json, read_int_env
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json, read_int_env

ensure_repo_root_on_path()

from aicrm_next.channel_entry.callback_worker import WeComCallbackWorker


EXECUTE_ENV = "AICRM_WECOM_CALLBACK_INBOX_WORKER_EXECUTE"
MAX_EXECUTE_LIMIT_ENV = "AICRM_WECOM_CALLBACK_INBOX_WORKER_MAX_EXECUTE_BATCH_SIZE"


def _default_limit() -> int:
    return read_int_env("AICRM_WECOM_CALLBACK_INBOX_WORKER_BATCH_SIZE", 50)


def _max_execute_limit() -> int:
    return read_int_env(MAX_EXECUTE_LIMIT_ENV, 20)


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _execute_gate(limit: int) -> dict:
    max_limit = max(1, int(_max_execute_limit()))
    if not _truthy_env(EXECUTE_ENV):
        return {
            "ok": False,
            "error": "wecom_callback_worker_execute_not_enabled",
            "message": f"--execute requires {EXECUTE_ENV}=1",
            "limit": int(limit),
            "max_execute_limit": max_limit,
        }
    if int(limit) > max_limit:
        return {
            "ok": False,
            "error": "wecom_callback_worker_execute_limit_exceeded",
            "message": f"--execute limit must be <= {max_limit}; set {MAX_EXECUTE_LIMIT_ENV} intentionally to raise it",
            "limit": int(limit),
            "max_execute_limit": max_limit,
        }
    return {"ok": True, "limit": int(limit), "max_execute_limit": max_limit}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run due WeCom callback webhook inbox jobs.")
    parser.add_argument("--limit", "--batch-size", dest="limit", type=int, default=_default_limit())
    parser.add_argument("--execute", action="store_true", default=False, help="Process claimed inbox rows. Without this flag the worker dry-runs.")
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be >= 1")
    return args


def run(*, limit: int | None = None, dry_run: bool = True) -> dict:
    return WeComCallbackWorker().run_due(limit=int(limit or _default_limit()), dry_run=bool(dry_run))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.execute:
        gate = _execute_gate(int(args.limit))
        if not gate.get("ok"):
            print_json({"ok": False, "dry_run": False, **gate})
            return 1
    payload = run(limit=int(args.limit), dry_run=not bool(args.execute))
    print_json(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
