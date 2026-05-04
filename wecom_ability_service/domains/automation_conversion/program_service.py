from __future__ import annotations

import re
from typing import Any

from ...db import get_db
from . import program_repo


PROGRAM_STATUS_DRAFT = "draft"
PROGRAM_STATUS_ACTIVE = "active"
PROGRAM_STATUS_PAUSED = "paused"
PROGRAM_STATUS_ARCHIVED = "archived"
PROGRAM_STATUSES = {PROGRAM_STATUS_DRAFT, PROGRAM_STATUS_ACTIVE, PROGRAM_STATUS_PAUSED, PROGRAM_STATUS_ARCHIVED}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_program_code(value: Any) -> str:
    text = _normalized_text(value).lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _validate_status(status: str) -> str:
    normalized = _normalized_text(status) or PROGRAM_STATUS_DRAFT
    if normalized not in PROGRAM_STATUSES:
        raise ValueError("invalid program status")
    return normalized


def _normalize_program_payload(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    program_name = _normalized_text(payload.get("program_name")) or _normalized_text(existing.get("program_name"))
    if not program_name:
        raise ValueError("program_name is required")
    program_code = _normalized_program_code(payload.get("program_code")) or _normalized_program_code(existing.get("program_code"))
    if not program_code:
        program_code = _normalized_program_code(program_name)
    if not program_code:
        raise ValueError("program_code is required")
    return {
        "program_code": program_code,
        "program_name": program_name,
        "description": _normalized_text(payload.get("description")) or _normalized_text(existing.get("description")),
        "status": _validate_status(_normalized_text(payload.get("status")) or _normalized_text(existing.get("status")) or PROGRAM_STATUS_DRAFT),
        "config_json": dict(payload.get("config_json") or existing.get("config_json") or {}),
    }


def get_default_automation_program() -> dict[str, Any]:
    program = program_repo.get_default_program_row()
    if program:
        return program
    return ensure_default_automation_program()


def get_default_automation_program_id() -> int:
    return int(get_default_automation_program().get("id") or 0)


def ensure_default_automation_program() -> dict[str, Any]:
    existing = program_repo.get_default_program_row()
    if existing:
        return existing
    program = program_repo.insert_program_row(
        {
            "program_code": program_repo.DEFAULT_AUTOMATION_PROGRAM_CODE,
            "program_name": program_repo.DEFAULT_AUTOMATION_PROGRAM_NAME,
            "description": "承接历史单例自动化运营能力的默认方案。",
            "status": PROGRAM_STATUS_ACTIVE,
            "config_json": {"flow_design_source": "legacy_singleton"},
            "created_by": "system",
            "updated_by": "system",
        }
    )
    get_db().commit()
    return program


def get_automation_program(program_id: int) -> dict[str, Any]:
    program = program_repo.get_program_row(int(program_id))
    if not program:
        raise LookupError("automation program not found")
    return program


def list_automation_programs(*, include_archived: bool = False) -> dict[str, Any]:
    ensure_default_automation_program()
    items: list[dict[str, Any]] = []
    for program in program_repo.list_program_rows(include_archived=include_archived):
        summary = program_repo.get_program_summary(int(program["id"]))
        items.append({"program": program, "summary": summary})
    return {"items": items, "total": len(items), "default_program": get_default_automation_program()}


def create_automation_program(payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    source_program: dict[str, Any] | None = None
    source_id = int(payload.get("copy_source_program_id") or 0)
    if source_id > 0:
        source_program = get_automation_program(source_id)
    normalized = _normalize_program_payload(payload, existing=source_program)
    duplicate = program_repo.get_program_row_by_code(normalized["program_code"])
    if duplicate:
        raise ValueError("program_code already exists")
    program = program_repo.insert_program_row(
        {
            **normalized,
            "created_by": operator_id,
            "updated_by": operator_id,
        }
    )
    get_db().commit()
    return {"program": program, "summary": program_repo.get_program_summary(int(program["id"]))}


def copy_automation_program(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    source = get_automation_program(int(program_id))
    base_code = _normalized_program_code(payload.get("program_code")) or f"{source['program_code']}_copy"
    candidate_code = base_code
    suffix = 2
    while program_repo.get_program_row_by_code(candidate_code):
        candidate_code = f"{base_code}_{suffix}"
        suffix += 1
    return create_automation_program(
        {
            "program_code": candidate_code,
            "program_name": _normalized_text(payload.get("program_name")) or f"{source['program_name']} 副本",
            "description": _normalized_text(payload.get("description")) or source.get("description") or "",
            "status": PROGRAM_STATUS_DRAFT,
            "config_json": dict(source.get("config_json") or {}),
        },
        operator_id=operator_id,
    )


def update_automation_program_status(program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
    get_automation_program(int(program_id))
    normalized_status = _validate_status(status)
    program = program_repo.update_program_status_row(int(program_id), status=normalized_status, operator_id=operator_id)
    get_db().commit()
    return {"program": program, "summary": program_repo.get_program_summary(int(program["id"]))}


def update_automation_program_basic_info(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    get_automation_program(int(program_id))
    program_name = _normalized_text(payload.get("program_name"))
    if not program_name:
        raise ValueError("program_name is required")
    program = program_repo.update_program_basic_info_row(
        int(program_id),
        program_name=program_name,
        description=_normalized_text(payload.get("description")),
        operator_id=operator_id,
    )
    get_db().commit()
    return {"program": program, "summary": program_repo.get_program_summary(int(program["id"]))}
