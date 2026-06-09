from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "5001"
NEXT_APP_IMPORT = "aicrm_next.main:app"
LEGACY_STARTUP_REMOVED_MESSAGE = (
    "Legacy Flask runtime has been removed from startup compatibility. "
    "Use `python3 app.py run` for AI-CRM Next."
)


def _host() -> str:
    return os.getenv("APP_HOST", DEFAULT_HOST)


def _port() -> int:
    return int(os.getenv("APP_PORT", DEFAULT_PORT))


def run_next() -> None:
    import uvicorn

    uvicorn.run(NEXT_APP_IMPORT, host=_host(), port=_port())


def legacy_startup_removed(command: str) -> None:
    raise SystemExit(f"{command}: {LEGACY_STARTUP_REMOVED_MESSAGE}")


def init_next_schema_safe() -> None:
    from aicrm_next.schema_init import init_next_schema_safe as run_safe_init

    table_names = run_safe_init()
    print({"ok": True, "initialized_tables": table_names, "drop_or_truncate_executed": False})


def init_db_next_alias() -> None:
    print("init-db is deprecated; running init-next-schema-safe for AI-CRM Next.")
    init_next_schema_safe()


def sync_customer_read_model(args: argparse.Namespace) -> int:
    from aicrm_next.customer_read_model.sync_cli import run_sync

    sync_args: list[str] = []
    if args.dry_run:
        sync_args.append("--dry-run")
    if args.limit is not None:
        sync_args.extend(["--limit", str(args.limit)])
    if args.replace:
        sync_args.append("--replace")
    for external_userid in args.external_userid or []:
        sync_args.extend(["--external-userid", external_userid])
    sync_args.extend(["--source", args.source])
    return run_sync(sync_args)


def print_next_health() -> None:
    from fastapi.testclient import TestClient

    from aicrm_next.main import app

    response = TestClient(app).get("/health")
    print(
        {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "default_runtime": "ai_crm_next",
            "route_owner": response.headers.get("X-AICRM-Route-Owner", ""),
        }
    )


def print_next_routes() -> None:
    from aicrm_next.main import app

    try:
        for route in sorted(app.routes, key=lambda item: getattr(item, "path", "")):
            path = getattr(route, "path", "")
            methods = sorted(getattr(route, "methods", []) or [])
            if path:
                print(f"{','.join(methods) or '-'} {path}")
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AI-CRM runtime entry. Default runtime is AI-CRM Next; "
            "legacy Flask startup commands have been removed."
        )
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run AI-CRM Next FastAPI app (default runtime).")
    subparsers.add_parser("health", help="Check AI-CRM Next health via TestClient.")
    subparsers.add_parser("routes", help="Print AI-CRM Next route inventory.")
    subparsers.add_parser("run-legacy", help="Removed legacy Flask startup command.")
    subparsers.add_parser("init-db-legacy", help="Removed legacy Flask database init command.")
    subparsers.add_parser("init-db", help="Deprecated alias for init-next-schema-safe.")
    subparsers.add_parser("init-next-schema-safe", help="Create missing AI-CRM Next schema safely without dropping data.")
    sync_customer = subparsers.add_parser(
        "sync-customer-read-model",
        help="Sync live customer source rows into AI-CRM Next projection tables.",
    )
    sync_customer.add_argument("--dry-run", action="store_true")
    sync_customer.add_argument("--limit", type=int, default=None)
    sync_customer.add_argument("--replace", action="store_true")
    sync_customer.add_argument("--external-userid", action="append", default=[])
    sync_customer.add_argument("--source", choices=["live"], default="live")
    legacy_delete = subparsers.add_parser(
        "delete-questionnaire-submissions-legacy",
        help="Legacy fallback helper for deleting questionnaire submissions by slug.",
    )
    legacy_delete.add_argument("slug")
    legacy_delete_alias = subparsers.add_parser(
        "delete-questionnaire-submissions",
        help="Deprecated alias for delete-questionnaire-submissions-legacy.",
    )
    legacy_delete_alias.add_argument("slug")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "run":
        run_next()
        return
    if command == "health":
        print_next_health()
        return
    if command == "routes":
        print_next_routes()
        return
    if command == "run-legacy":
        legacy_startup_removed(command)
        return
    if command == "init-db":
        init_db_next_alias()
        return
    if command == "init-db-legacy":
        legacy_startup_removed(command)
        return
    if command == "init-next-schema-safe":
        init_next_schema_safe()
        return
    if command == "sync-customer-read-model":
        raise SystemExit(sync_customer_read_model(args))
    if command in {"delete-questionnaire-submissions", "delete-questionnaire-submissions-legacy"}:
        legacy_startup_removed(command)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
