from __future__ import annotations

import json
import os
import urllib.request


def main() -> None:
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = os.getenv("APP_PORT", "5000")
    token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "").strip()
    payload = {
        "trigger_source": "scheduled",
        "operator": "cron_message_activity_sync",
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"http://{host}:{port}/api/admin/automation-conversion/message-activity-sync/run",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
