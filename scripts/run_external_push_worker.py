from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json, read_int_env
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json, read_int_env

ensure_repo_root_on_path()

from aicrm_next.external_push import service as external_push_service

DEFAULT_BATCH_SIZE = 50


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run due external push webhook jobs.")
    parser.add_argument("--limit", type=int, default=read_int_env("EXTERNAL_PUSH_WORKER_BATCH_SIZE", DEFAULT_BATCH_SIZE))
    parser.add_argument("--skip-events", action="store_true")
    parser.add_argument("--skip-retries", action="store_true")
    args = parser.parse_args(argv)

    payload: dict[str, object] = {"ok": True}
    if not args.skip_events:
        payload["events"] = external_push_service.run_due_external_push_events(limit=args.limit)
    if not args.skip_retries:
        payload["retries"] = external_push_service.run_due_external_push_retries(limit=args.limit)
    print_json(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
