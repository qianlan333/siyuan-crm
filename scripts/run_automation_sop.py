from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


DEFAULT_OPERATOR = "automation_sop_runner"
DEFAULT_PATH = "/api/admin/automation-conversion/jobs/run-due"
DEFAULT_RETRY_COUNT = 6
DEFAULT_RETRY_INTERVAL_SECONDS = 10


def build_request(*, host: str, port: str, token: str, operator: str, path: str = DEFAULT_PATH) -> urllib.request.Request:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=json.dumps({"operator": operator, "jobs": ["conversion_workflow"]}).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def run() -> str:
    host = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("APP_PORT", "5000").strip() or "5000"
    token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "").strip()
    operator = os.getenv("AUTOMATION_SOP_OPERATOR", DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    path = os.getenv("AUTOMATION_SOP_RUNNER_PATH", DEFAULT_PATH).strip() or DEFAULT_PATH
    retry_count = int((os.getenv("AUTOMATION_SOP_RETRY_COUNT") or DEFAULT_RETRY_COUNT))
    retry_interval_seconds = int((os.getenv("AUTOMATION_SOP_RETRY_INTERVAL_SECONDS") or DEFAULT_RETRY_INTERVAL_SECONDS))
    request = build_request(host=host, port=port, token=token, operator=operator, path=path)

    last_error: Exception | None = None
    for attempt in range(1, max(1, retry_count) + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read().decode("utf-8")
            print(body)
            return body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(body)
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= max(1, retry_count):
                raise
            time.sleep(max(0, retry_interval_seconds))
    assert last_error is not None
    raise last_error


def main() -> None:
    run()


if __name__ == "__main__":
    main()
