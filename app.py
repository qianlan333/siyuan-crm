from __future__ import annotations

import sys

from wecom_ability_service import create_app
from wecom_ability_service.db import init_db
from wecom_ability_service.services import delete_questionnaire_submissions_by_slug


def main() -> None:
    app = create_app()

    if len(sys.argv) > 1 and sys.argv[1] == "init-db":
        with app.app_context():
            init_db()
        print("Database initialized.")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "delete-questionnaire-submissions":
        if len(sys.argv) < 3 or not str(sys.argv[2] or "").strip():
            print("Usage: python app.py delete-questionnaire-submissions <slug>")
            return
        with app.app_context():
            result = delete_questionnaire_submissions_by_slug(str(sys.argv[2]).strip())
        print(result)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        host = app.config["APP_HOST"]
        port = int(app.config["APP_PORT"])
        app.run(host=host, port=port, debug=app.config["DEBUG"])
        return

    print("Usage: python app.py [init-db|delete-questionnaire-submissions <slug>|run]")


if __name__ == "__main__":
    main()
