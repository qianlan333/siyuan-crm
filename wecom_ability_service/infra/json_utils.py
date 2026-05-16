from __future__ import annotations

import json
from typing import Any, Callable


def safe_json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def json_dumps(
    value: Any,
    *,
    none_as_empty_object: bool = False,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    indent: int | None = None,
    default: Callable[[Any], Any] | None = None,
) -> str:
    payload = {} if none_as_empty_object and value is None else value
    kwargs: dict[str, Any] = {
        "ensure_ascii": ensure_ascii,
        "sort_keys": sort_keys,
    }
    if indent is not None:
        kwargs["indent"] = indent
    if default is not None:
        kwargs["default"] = default
    return json.dumps(payload, **kwargs)


def json_array(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        parsed = safe_json_loads(value, default=[])
        return parsed if isinstance(parsed, list) else []
    return []
