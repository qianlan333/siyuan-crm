from __future__ import annotations

import os
import urllib.request

from scripts import internal_http
from scripts.script_runtime import emit_json, read_app_host, read_app_port, read_int_env, read_internal_api_token


DEFAULT_OPERATOR = "automation_sop_runner"
DEFAULT_PATH = "/api/admin/automation-conversion/sop/run-due"
DEFAULT_RETRY_COUNT = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 10


def run() -> str:
    host = read_app_host()
    port = read_app_port()
    token = read_internal_api_token()
    operator = os.getenv("AUTOMATION_SOP_OPERATOR", DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    path = os.getenv("AUTOMATION_SOP_RUNNER_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    retry_count = read_int_env("AUTOMATION_SOP_RETRY_COUNT", DEFAULT_RETRY_COUNT)
    retry_interval_seconds = read_int_env(
        "AUTOMATION_SOP_RETRY_INTERVAL_SECONDS",
        DEFAULT_RETRY_INTERVAL_SECONDS,
    )
    payload = internal_http.post_json(
        host=host,
        port=port,
        token=token,
        path=path,
        payload={"operator": operator, "jobs": ["sop"]},
        retry_count=retry_count,
        retry_interval_seconds=retry_interval_seconds,
        urlopen=urllib.request.urlopen,
    )
    return emit_json(payload)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
