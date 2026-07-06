from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class LegacyDeprecationEntry:
    id: int = 0
    legacy_key: str = ""
    legacy_type: str = ""
    legacy_route: str = ""
    legacy_module: str = ""
    status: str = "deprecated"
    deprecated_at: str = ""
    deprecated_by: str = ""
    deprecation_reason: str = ""
    replacement_route: str = "/admin/push-center"
    delete_scheduled_at: str = ""
    delete_status: str = "scheduled"
    delete_job_id: str = ""
    notes_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LegacyCleanupAudit:
    id: int = 0
    audit_id: str = ""
    legacy_key: str = ""
    action: str = ""
    operator: str = ""
    before_json: dict[str, Any] = field(default_factory=dict)
    after_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
