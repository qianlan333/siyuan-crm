from __future__ import annotations

import json
import sys
from typing import Any

from .service import LegacyWebhookCleanupService


def _write_json_result(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def mark_deprecated_cli(*, operator: str = "cli") -> dict[str, Any]:
    return LegacyWebhookCleanupService().mark_default_deprecations(operator=operator)


def print_mark_deprecated_result(*, operator: str = "cli") -> None:
    _write_json_result(mark_deprecated_cli(operator=operator))


def run_due_cli(*, dry_run: bool = True, limit: int = 50, operator: str = "cli") -> dict[str, Any]:
    return LegacyWebhookCleanupService().run_due(dry_run=dry_run, limit=limit, operator=operator)


def print_run_due_result(*, dry_run: bool = True, limit: int = 50, operator: str = "cli") -> None:
    _write_json_result(run_due_cli(dry_run=dry_run, limit=limit, operator=operator))


def retire_now_cli(*, dry_run: bool = True, limit: int = 50, operator: str = "cli") -> dict[str, Any]:
    return LegacyWebhookCleanupService().retire_now(dry_run=dry_run, limit=limit, operator=operator)


def print_retire_now_result(*, dry_run: bool = True, limit: int = 50, operator: str = "cli") -> None:
    _write_json_result(retire_now_cli(dry_run=dry_run, limit=limit, operator=operator))
