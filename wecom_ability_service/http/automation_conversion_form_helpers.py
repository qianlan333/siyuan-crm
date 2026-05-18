from __future__ import annotations

from flask import redirect, request, url_for


def _program_form_payload() -> dict[str, object]:
    return {
        "program_code": str(request.form.get("program_code") or "").strip(),
        "program_name": str(request.form.get("program_name") or "").strip(),
        "description": str(request.form.get("description") or "").strip(),
        "status": str(request.form.get("status") or "draft").strip() or "draft",
        "copy_source_program_id": int(str(request.form.get("copy_source_program_id") or "0").strip() or 0),
    }


def _program_basic_info_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "program_name": str(request.form.get("program_name") or "").strip(),
    }
    if "description" in request.form:
        payload["description"] = str(request.form.get("description") or "").strip()
    return payload


def _program_action_redirect(default_path: str = ""):
    target = str(request.form.get("next") or "").strip() or default_path
    if not target.startswith("/admin/automation-conversion") or target.startswith("//"):
        target = default_path or url_for("api.admin_automation_conversion")
    return redirect(target, code=302)
