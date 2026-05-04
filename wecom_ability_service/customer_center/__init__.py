from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["get_customer_detail", "list_customers"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    service = import_module(".service", __name__)
    value = getattr(service, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))
