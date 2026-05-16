from __future__ import annotations

import os
import urllib.request

from scripts import internal_http
from scripts.script_runtime import emit_json, read_app_host, read_app_port


DEFAULT_PATH = "/api/archive/sync"


def run() -> str:
    host = read_app_host()
    port = read_app_port()
    owner_userid = os.getenv("WECOM_DEFAULT_OWNER_USERID", "")
    payload = {
        "start_time": "2000-01-01 00:00:00",
        "end_time": "2099-12-31 23:59:59",
        "owner_userid": owner_userid,
        "cursor": "",
    }
    response_payload = internal_http.post_json(
        host=host,
        port=port,
        path=DEFAULT_PATH,
        payload=payload,
        timeout_seconds=120,
        urlopen=urllib.request.urlopen,
    )
    return emit_json(response_payload)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
