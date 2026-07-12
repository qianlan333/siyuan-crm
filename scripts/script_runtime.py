from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_repo_root_on_path() -> Path:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return REPO_ROOT


def print_json(payload: Any, *, indent: int | None = None, sort_keys: bool = False) -> None:
    ensure_repo_root_on_path()
    from aicrm_next.shared.sensitive_data import redact_sensitive_data

    print(dump_json(redact_sensitive_data(payload), indent=indent, sort_keys=sort_keys))


def dump_json(payload: Any, *, indent: int | None = None, sort_keys: bool = False) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str, indent=indent, sort_keys=sort_keys)


def emit_json(payload: Any, *, indent: int | None = None, sort_keys: bool = False) -> str:
    ensure_repo_root_on_path()
    from aicrm_next.shared.sensitive_data import redact_sensitive_data

    body = dump_json(redact_sensitive_data(payload), indent=indent, sort_keys=sort_keys)
    print(body)
    return body


def read_int_env(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def read_app_host() -> str:
    return os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"


def read_app_port() -> str:
    return os.getenv("APP_PORT", "5000").strip() or "5000"


def read_internal_api_token(*, purpose: str = "automation_worker") -> str:
    ensure_repo_root_on_path()
    from aicrm_next.shared.internal_service_tokens import internal_service_token_for_purpose

    return internal_service_token_for_purpose(purpose)
