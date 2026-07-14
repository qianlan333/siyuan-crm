#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from aicrm_next.customer_read_model.refresh import CustomerReadModelRefreshService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the production customer list/detail read model.")
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--max-customers", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        result = CustomerReadModelRefreshService().run(
            dry_run=not bool(args.execute),
            max_customers=args.max_customers,
        )
    except Exception as exc:
        message = str(exc)
        reason = (
            message
            if isinstance(exc, RuntimeError) and message.startswith("customer_read_model_")
            else "customer_read_model_refresh_failed"
        )
        print_json({"ok": False, "error": type(exc).__name__, "reason": reason})
        return 1
    print_json(result.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
