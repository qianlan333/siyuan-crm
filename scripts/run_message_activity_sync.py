from __future__ import annotations

import urllib.request

from scripts import internal_http
from scripts.script_runtime import emit_json, read_app_host, read_app_port, read_internal_api_token


DEFAULT_PATH = "/api/admin/automation-conversion/message-activity-sync/run"


def run() -> str:
    host = read_app_host()
    port = read_app_port()
    token = read_internal_api_token()
    payload = {
        "trigger_source": "scheduled",
        "operator": "cron_message_activity_sync",
    }
    response_payload = internal_http.post_json(
        host=host,
        port=port,
        token=token,
        path=DEFAULT_PATH,
        payload=payload,
        timeout_seconds=180,
        urlopen=urllib.request.urlopen,
    )
    return emit_json(response_payload)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
