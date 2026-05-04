from __future__ import annotations

import argparse
import json

from openclaw_service.services.customer_chat_context_preflight import run_customer_chat_context_preflight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run preflight checks for customer chat context.")
    parser.add_argument("--external-userid", required=True, help="CRM external_userid")
    parser.add_argument("--recent-message-limit", type=int, default=5, help="Recent messages to load for preflight")
    parser.add_argument("--timeline-limit", type=int, default=5, help="Timeline events to load for preflight")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_customer_chat_context_preflight(
        args.external_userid,
        recent_message_limit=args.recent_message_limit,
        timeline_limit=args.timeline_limit,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("ok"):
        return 1
    if result.get("source_status") == "live":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
