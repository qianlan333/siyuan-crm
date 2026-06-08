from __future__ import annotations

import argparse
import os
from collections.abc import Sequence


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "5001"
NEXT_APP_IMPORT = "aicrm_next.main:app"


def _host() -> str:
    return os.getenv("APP_HOST", DEFAULT_HOST)


def _port() -> int:
    return int(os.getenv("APP_PORT", DEFAULT_PORT))


def run_next() -> None:
    import uvicorn

    uvicorn.run(NEXT_APP_IMPORT, host=_host(), port=_port())


def run_legacy() -> None:
    from wecom_ability_service import create_app

    app = create_app()
    host = app.config.get("APP_HOST") or _host()
    port = int(app.config.get("APP_PORT") or _port())
    app.run(host=host, port=port, debug=bool(app.config.get("DEBUG")))


def init_db_legacy() -> None:
    from wecom_ability_service import create_app
    from wecom_ability_service.db import init_db

    app = create_app()
    with app.app_context():
        init_db()
    print("Legacy Flask database initialized.")


def delete_questionnaire_submissions_legacy(slug: str) -> None:
    from wecom_ability_service import create_app
    from wecom_ability_service.services import delete_questionnaire_submissions_by_slug

    app = create_app()
    with app.app_context():
        result = delete_questionnaire_submissions_by_slug(str(slug or "").strip())
    print(result)


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

    for route in sorted(app.routes, key=lambda item: getattr(item, "path", "")):
        path = getattr(route, "path", "")
        methods = sorted(getattr(route, "methods", []) or [])
        if path:
            print(f"{','.join(methods) or '-'} {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "AI-CRM runtime entry. Default runtime is AI-CRM Next; "
            "legacy Flask is available only through explicit fallback commands."
        )
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run AI-CRM Next FastAPI app (default runtime).")
    subparsers.add_parser("health", help="Check AI-CRM Next health via TestClient.")
    subparsers.add_parser("routes", help="Print AI-CRM Next route inventory.")
    subparsers.add_parser("run-legacy", help="Run legacy Flask fallback explicitly.")
    subparsers.add_parser("init-db-legacy", help="Initialize the legacy Flask database explicitly.")
    subparsers.add_parser("init-db", help="Deprecated alias for init-db-legacy.")
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
        run_legacy()
        return
    if command in {"init-db", "init-db-legacy"}:
        init_db_legacy()
        return
    if command in {"delete-questionnaire-submissions", "delete-questionnaire-submissions-legacy"}:
        delete_questionnaire_submissions_legacy(args.slug)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
