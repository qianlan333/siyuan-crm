from __future__ import annotations

import argparse
from collections.abc import Sequence


def run() -> None:
    from wecom_ability_service import create_app

    app = create_app()
    host = app.config["APP_HOST"]
    port = int(app.config["APP_PORT"])
    app.run(host=host, port=port, debug=app.config["DEBUG"])


def init_db() -> None:
    from wecom_ability_service import create_app
    from wecom_ability_service.db import init_db as do_init_db

    app = create_app()
    with app.app_context():
        do_init_db()
    print("Legacy Flask database initialized.")


def delete_questionnaire_submissions(slug: str) -> None:
    from wecom_ability_service import create_app
    from wecom_ability_service.services import delete_questionnaire_submissions_by_slug

    app = create_app()
    with app.app_context():
        result = delete_questionnaire_submissions_by_slug(str(slug or "").strip())
    print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explicit legacy Flask fallback runner. The default app.py runtime is AI-CRM Next."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="Run the legacy Flask fallback service.")
    subparsers.add_parser("init-db", help="Initialize the legacy Flask database.")
    delete_parser = subparsers.add_parser(
        "delete-questionnaire-submissions",
        help="Legacy fallback helper for deleting questionnaire submissions by slug.",
    )
    delete_parser.add_argument("slug")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "run":
        run()
        return
    if command == "init-db":
        init_db()
        return
    if command == "delete-questionnaire-submissions":
        delete_questionnaire_submissions(args.slug)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
