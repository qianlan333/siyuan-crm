from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CrmError(Exception):
    message: str
    path: str = ""
    request_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        if not self.path:
            return self.message
        return f"{self.message} (path={self.path})"


@dataclass(slots=True)
class CrmTransportError(CrmError):
    """Raised when the CRM cannot be reached or request transport fails."""


@dataclass(slots=True)
class CrmHttpError(CrmError):
    status_code: int = 0
    response_text: str = ""


@dataclass(slots=True)
class CrmBusinessError(CrmError):
    error_code: str = ""
    response_payload: Any = None


@dataclass(slots=True)
class CrmMappingError(CrmError):
    response_payload: Any = None
