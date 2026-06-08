from __future__ import annotations

from pathlib import Path

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_forwarder_is_not_reachable_through_production_compat_runtime(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    app = create_app()

    modules = {
        getattr(getattr(route, "endpoint", None), "__module__", "")
        for route in app.routes
    }

    assert "aicrm_next.production_compat.api" not in modules


def test_production_compat_and_main_do_not_reference_legacy_facade() -> None:
    assert not (ROOT / "aicrm_next/production_compat/api.py").exists()
    source = (ROOT / "aicrm_next/main.py").read_text(encoding="utf-8")
    assert "forward_to_legacy_flask" not in source
    assert "legacy_flask_facade" not in source
