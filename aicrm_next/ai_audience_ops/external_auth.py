from __future__ import annotations

import hmac
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from aicrm_next.shared.runtime_settings import runtime_setting


def external_spec_auth_error(request: Request) -> JSONResponse | None:
    expected = runtime_setting("AICRM_AI_AUDIENCE_SPEC_API_TOKEN")
    if not expected:
        return _json({"ok": False, "error": "external_token_not_configured"}, status_code=503)
    auth = str(request.headers.get("Authorization") or "").strip()
    if not auth.startswith("Bearer "):
        return _json({"ok": False, "error": "external_token_required"}, status_code=401)
    provided = auth[7:].strip()
    if not provided:
        return _json({"ok": False, "error": "external_token_required"}, status_code=401)
    if not hmac.compare_digest(provided, expected):
        return _json({"ok": False, "error": "external_token_invalid"}, status_code=401)
    return None


def _json(payload: dict[str, Any], *, status_code: int) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Real-External-Call-Executed": "false",
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
