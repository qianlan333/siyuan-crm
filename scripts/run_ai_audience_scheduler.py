#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json, read_int_env
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json, read_int_env

ensure_repo_root_on_path()

from aicrm_next.ai_audience_ops import register_ai_audience_event_consumers
from aicrm_next.ai_audience_ops.scheduler import (
    DEFAULT_DAILY_REFRESH_TIME,
    DEFAULT_DAILY_TICK_WINDOW_MINUTES,
    emit_due_ticks,
    run_due_ai_audience_consumers,
    run_due_refresh_consumers,
)

register_ai_audience_event_consumers()


def _default_batch_size() -> int:
    return read_int_env("AICRM_AI_AUDIENCE_SCHEDULER_BATCH_SIZE", 20)


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit AI audience refresh ticks and optionally run due internal consumers.")
    parser.add_argument("--run-consumers", action="store_true", help="Run existing internal_event consumers after emitting ticks.")
    parser.add_argument("--execute", action="store_true", help="Execute consumers instead of dry-run preview.")
    parser.add_argument("--batch-size", type=int, default=_default_batch_size())
    parser.add_argument("--incremental-only", action="store_true")
    parser.add_argument("--daily-only", action="store_true")
    parser.add_argument("--daily-at", default=DEFAULT_DAILY_REFRESH_TIME)
    parser.add_argument("--daily-window-minutes", type=int, default=DEFAULT_DAILY_TICK_WINDOW_MINUTES)
    parser.add_argument("--refresh-consumers-only", action="store_true")
    args = parser.parse_args()

    include_incremental = not args.daily_only
    include_daily = not args.incremental_only
    payload = {
        "ticks": emit_due_ticks(
            include_daily=include_daily,
            include_incremental=include_incremental,
            daily_refresh_time=args.daily_at,
            daily_window_minutes=args.daily_window_minutes,
        )
    }
    if args.run_consumers:
        run_daily_consumers = include_daily and bool(payload["ticks"].get("daily_tick_due"))
        if args.refresh_consumers_only:
            payload["consumers"] = run_due_refresh_consumers(
                dry_run=not args.execute,
                batch_size=args.batch_size,
                include_incremental=include_incremental,
                include_daily=run_daily_consumers,
            )
        else:
            payload["consumers"] = run_due_ai_audience_consumers(
                dry_run=not args.execute,
                batch_size=args.batch_size,
                include_incremental_refresh=include_incremental,
                include_daily_refresh=run_daily_consumers,
            )
    print_json(payload, indent=2)
    return 0 if payload["ticks"].get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
