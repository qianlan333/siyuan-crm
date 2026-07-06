#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from aicrm_next.background_jobs.data_quality_snapshot import run_scheduled_data_quality_snapshot


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a data quality registry snapshot.")
    parser.add_argument("--execute", action="store_true", help="Reserve non-dry-run mode for future persistence.")
    parser.add_argument("--operator", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run_scheduled_data_quality_snapshot(
        dry_run=not bool(args.execute),
        operator=str(args.operator or "") or None,
    )
    print_json(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
