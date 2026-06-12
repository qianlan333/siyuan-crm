from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPAT_ROUTER = "production_compat" + "_router"
COMPAT_WILDCARD_ROUTER = "production_compat" + "_wildcard_router"


def test_production_compat_module_is_removed() -> None:
    assert not (ROOT / "aicrm_next/production_compat/api.py").exists()


def test_app_startup_no_longer_imports_or_includes_production_compat() -> None:
    source = (ROOT / "aicrm_next/main.py").read_text(encoding="utf-8")

    assert COMPAT_ROUTER not in source
    assert COMPAT_WILDCARD_ROUTER not in source
    assert "aicrm_next.production_compat.api" not in source


def test_api_docs_router_sources_do_not_include_production_compat() -> None:
    source = (ROOT / "aicrm_next/admin_config/api_docs_view_model.py").read_text(encoding="utf-8")

    assert COMPAT_ROUTER not in source
    assert COMPAT_WILDCARD_ROUTER not in source
    assert "production_compat.api" not in source
    assert "legacy_proxy" not in source
