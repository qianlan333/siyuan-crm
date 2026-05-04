from __future__ import annotations

import argparse
import json
import sys

from openclaw_service.tools.registry import call_tool_by_name

TOOL_NAME = "get_customer_chat_context"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load CRM-backed customer chat context as JSON.")
    parser.add_argument("--external-userid", required=True, help="CRM external_userid")
    parser.add_argument("--recent-message-limit", type=int, default=20, help="Recent messages to load")
    parser.add_argument("--timeline-limit", type=int, default=20, help="Timeline events to load")
    return parser


def load_customer_chat_context(
    external_userid: str,
    *,
    recent_message_limit: int = 20,
    timeline_limit: int = 20,
) -> dict:
    return call_tool_by_name(
        TOOL_NAME,
        {
            "external_userid": external_userid,
            "recent_message_limit": recent_message_limit,
            "timeline_limit": timeline_limit,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        payload = load_customer_chat_context(
            args.external_userid,
            recent_message_limit=args.recent_message_limit,
            timeline_limit=args.timeline_limit,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "external_userid": args.external_userid,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
