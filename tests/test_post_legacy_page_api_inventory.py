from __future__ import annotations

import re
from pathlib import Path

from aicrm_next.main import create_app
from tests.post_legacy_baseline import (
    API_CONTRACT_CASES,
    ADMIN_PAGE_CASES,
    DEFERRED_FRONTEND_API_PATTERNS,
    INVENTORY_PATH,
    PUBLIC_H5_PAGE_CASES,
    baseline_env,
    first_matching_route,
)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SOURCE_GLOBS = (
    "aicrm_next/frontend_compat/templates/**/*.html",
    "aicrm_next/frontend_compat/static/**/*.js",
    "aicrm_next/admin_jobs/templates/**/*.html",
    "aicrm_next/commerce/templates/**/*.html",
)
API_LITERAL_RE = re.compile(r"""(?P<quote>["'`])(?P<url>/api/[^"'`\s<>)]+)(?P=quote)""")
DATA_API_RE = re.compile(r"""data-[\w-]*api[\w-]*=["'](?P<url>[^"']*)["']""", re.IGNORECASE)
EMPTY_API_BUTTON_RE = re.compile(
    r"""<button\b(?=[^>]*\bdata-[\w-]*api[\w-]*=)[^>]*>\s*</button>""",
    re.IGNORECASE | re.DOTALL,
)


def _inventory_text() -> str:
    return INVENTORY_PATH.read_text(encoding="utf-8")


def _frontend_files() -> list[Path]:
    files: list[Path] = []
    for pattern in FRONTEND_SOURCE_GLOBS:
        files.extend(ROOT.glob(pattern))
    return sorted(set(files))


def _api_literals() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in _frontend_files():
        text = path.read_text(encoding="utf-8")
        for match in API_LITERAL_RE.finditer(text):
            found.setdefault(_normalize_frontend_url(match.group("url")), set()).add(str(path.relative_to(ROOT)))
    return found


def _normalize_frontend_url(url: str) -> str:
    url = url.split("?", 1)[0].split("#", 1)[0]
    url = re.sub(r"(export)\$\{[^}]+\}", r"\1", url)
    url = re.sub(r"\$\{[^}]+\}", "1", url)
    url = re.sub(r"\{\{[^}]+\}\}", "1", url)
    url = url.replace("<external_userid>", "wx_ext_001")
    url = url.replace("<id>", "1")
    url = re.sub(r"/+", "/", url)
    if len(url) > 1:
        url = url.rstrip("/")
    return url


def _is_deferred(url: str) -> bool:
    return any(url == pattern.rstrip("/") or url.startswith(pattern) for pattern in DEFERRED_FRONTEND_API_PATTERNS)


def test_post_legacy_inventory_document_has_required_matrices() -> None:
    text = _inventory_text()

    assert "## Admin Page Matrix" in text
    assert "## Public/H5 Page Matrix" in text
    assert "## API Contract Matrix" in text
    assert "## Deferred API Closeout References" in text
    assert "production_compat" in text
    assert "X-AICRM-Compatibility-Facade" in text
    assert "fallback_used=true" in text
    assert "explicit gated adapter PR" in text
    assert "never restoration of `production_compat`" in text


def test_post_legacy_inventory_lists_all_baseline_cases() -> None:
    text = _inventory_text()
    missing: list[str] = []

    for case in ADMIN_PAGE_CASES + PUBLIC_H5_PAGE_CASES:
        if case.path not in text:
            missing.append(case.path)
    for case in API_CONTRACT_CASES:
        if case.path not in text:
            missing.append(case.path)
    for pattern in DEFERRED_FRONTEND_API_PATTERNS:
        if pattern not in text:
            missing.append(pattern)

    assert "Deferred frontend API whitelist count: 0" in text

    assert missing == []


def test_post_legacy_frontend_api_literals_are_registered_or_documented_deferred(monkeypatch) -> None:
    baseline_env(monkeypatch)
    app = create_app()
    inventory = _inventory_text()
    unresolved: dict[str, list[str]] = {}

    for url, sources in _api_literals().items():
        route = (
            first_matching_route(app, "GET", url)
            or first_matching_route(app, "POST", url)
            or first_matching_route(app, "PUT", url)
            or first_matching_route(app, "PATCH", url)
            or first_matching_route(app, "DELETE", url)
            or first_matching_route(app, "OPTIONS", url)
        )
        if route is not None:
            continue
        if _is_deferred(url) and any(pattern.rstrip("/") in inventory for pattern in DEFERRED_FRONTEND_API_PATTERNS if url.startswith(pattern.rstrip("/"))):
            continue
        unresolved[url] = sorted(sources)

    assert unresolved == {}


def test_post_legacy_frontend_data_api_attributes_are_not_legacy_or_empty() -> None:
    offenders: list[str] = []
    empty_buttons: list[str] = []
    for path in _frontend_files():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        for match in DATA_API_RE.finditer(text):
            value = match.group("url")
            if "production_compat" in value or "prod_compat" in value:
                offenders.append(f"{rel}: {value}")
        if EMPTY_API_BUTTON_RE.search(text):
            empty_buttons.append(rel)

    assert offenders == []
    assert empty_buttons == []


def test_post_legacy_frontend_sources_do_not_reference_compatibility_facade_header() -> None:
    offenders: list[str] = []
    for path in _frontend_files():
        text = path.read_text(encoding="utf-8")
        if "X-AICRM-Compatibility-Facade" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
