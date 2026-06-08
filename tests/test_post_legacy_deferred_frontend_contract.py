from __future__ import annotations

import re
from pathlib import Path

from aicrm_next.main import create_app
from tests.post_legacy_baseline import DEFERRED_FRONTEND_API_PATTERNS, baseline_env, first_matching_route

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_FILES = (
    ROOT / "aicrm_next/frontend_compat/templates/admin_console/operations.html",
    ROOT / "aicrm_next/frontend_compat/templates/admin_console/cloud_observability.html",
    ROOT / "aicrm_next/frontend_compat/templates/admin_console/wecom_customer_acquisition_links.html",
)
API_LITERAL_RE = re.compile(r"""(?P<quote>["'`])(?P<url>/api/[^"'`\s<>)]+)(?P=quote)""")


def _normalize(url: str) -> str:
    url = url.split("?", 1)[0].split("#", 1)[0]
    url = re.sub(r"\$\{[^}]+\}", "1", url)
    return url.rstrip("/") if len(url) > 1 else url


def test_deferred_frontend_api_patterns_are_empty() -> None:
    assert DEFERRED_FRONTEND_API_PATTERNS == ()


def test_previous_deferred_frontend_literals_resolve_to_next_routes(monkeypatch) -> None:
    baseline_env(monkeypatch)
    app = create_app()
    unresolved: dict[str, str] = {}

    for path in FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        for match in API_LITERAL_RE.finditer(text):
            url = _normalize(match.group("url"))
            if not any(
                url.startswith(prefix)
                for prefix in (
                    "/api/admin/class-user-management/export",
                    "/api/admin/cloud-orchestrator/audit",
                    "/api/admin/cloud-orchestrator/observability",
                    "/api/admin/wecom-customer-acquisition-links",
                )
            ):
                continue
            route = (
                first_matching_route(app, "GET", url)
                or first_matching_route(app, "POST", url)
                or first_matching_route(app, "PATCH", url)
                or first_matching_route(app, "DELETE", url)
                or first_matching_route(app, "OPTIONS", url)
            )
            if route is None:
                unresolved[url] = str(path.relative_to(ROOT))
                continue
            endpoint_module = getattr(getattr(route, "endpoint", None), "__module__", "")
            assert endpoint_module != "aicrm_next.production_compat.api"

    assert unresolved == {}
