from __future__ import annotations

import json
from typing import Any

from flask import request


def _parse_bool_arg(raw: Any, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "")


def _parse_tags_arg(raw: Any) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(s) for s in parsed]
        except (TypeError, ValueError):
            pass
    return [s for s in (p.strip() for p in text.split(",")) if s]


def _form_metadata_kwargs() -> dict[str, Any]:
    return {
        "description": (request.form.get("description") or "").strip(),
        "tags": _parse_tags_arg(request.form.get("tags")),
        "category": (request.form.get("category") or "").strip(),
        "ai_metadata": request.form.get("ai_metadata"),
    }


def _json_metadata_kwargs(body: dict) -> dict[str, Any]:
    return {
        "description": str(body.get("description") or ""),
        "tags": body.get("tags"),
        "category": str(body.get("category") or ""),
        "ai_metadata": body.get("ai_metadata"),
    }
