from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


UrlOpen = Callable[[urllib.request.Request, int], Any]


def build_json_post_request(
    *,
    host: str,
    port: str,
    path: str,
    payload: dict[str, object],
    token: str = "",
) -> urllib.request.Request:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def post_json(
    *,
    host: str,
    port: str,
    path: str,
    payload: dict[str, object],
    token: str = "",
    retry_count: int = 1,
    retry_interval_seconds: int = 0,
    timeout_seconds: int = 180,
    urlopen: UrlOpen = urllib.request.urlopen,
) -> dict[str, object]:
    request = build_json_post_request(host=host, port=port, path=path, payload=payload, token=token)
    attempts = max(1, int(retry_count))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            print(exc.read().decode("utf-8", errors="replace"))
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(max(0, int(retry_interval_seconds)))
    assert last_error is not None
    raise last_error
