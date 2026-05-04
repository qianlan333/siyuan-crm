from __future__ import annotations

from openclaw_service.feishu.longconn import run_ws_client


def main() -> int:
    run_ws_client()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
