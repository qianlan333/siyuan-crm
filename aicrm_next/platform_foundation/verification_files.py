from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter()

_ROOT = Path(__file__).resolve().parents[2]
_VERIFY_FILE_RE = re.compile(r"^(?:WW|MP)_verify_[A-Za-z0-9_-]+\.txt$")


@router.get("/{filename}", name="wechat_domain_verification_file")
def wechat_domain_verification_file(filename: str) -> PlainTextResponse:
    if not _VERIFY_FILE_RE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Not Found")
    path = _ROOT / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return PlainTextResponse(
        path.read_text(encoding="utf-8").strip(),
        headers={"Cache-Control": "no-store"},
    )
