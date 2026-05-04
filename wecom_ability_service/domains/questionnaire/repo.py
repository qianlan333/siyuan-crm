from __future__ import annotations

from ...db import get_db


def db():
    return get_db()
