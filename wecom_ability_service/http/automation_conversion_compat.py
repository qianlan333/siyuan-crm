from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T", bound=Callable)
_PARENT_MODULE = "wecom_ability_service.http.automation_conversion"


def parent_patch(name: str, fallback: _T) -> _T:
    parent = sys.modules.get(_PARENT_MODULE)
    patched = getattr(parent, name, None) if parent is not None else None
    if callable(patched) and patched is not fallback:
        return patched
    return fallback
