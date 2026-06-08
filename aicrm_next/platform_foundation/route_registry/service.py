from __future__ import annotations

import re
from functools import lru_cache

from .manifest_loader import load_route_registry
from .models import LegacyDeletionLifecycleItem, RouteRegistry, RouteRegistryEntry


def pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*")
    escaped = re.sub(r"\\\{[^{}]+:path\\\}", ".*", escaped)
    escaped = re.sub(r"\\\{[^{}]+\\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def route_matches(entry: RouteRegistryEntry, path: str, methods: set[str] | None = None) -> bool:
    if not pattern_to_regex(entry.path_pattern).match(path):
        return False
    if methods is None:
        return True
    entry_methods = set(entry.methods)
    normalized_methods = {"GET" if method == "HEAD" else method for method in methods}
    return bool(entry_methods & normalized_methods)


class RouteRegistryService:
    def __init__(self, registry: RouteRegistry | None = None):
        self._registry = registry or load_route_registry()

    def list_routes(self) -> list[RouteRegistryEntry]:
        return sorted(self._registry.routes, key=lambda item: (item.path_pattern, item.methods))

    def list_lifecycle_items(self, *, include_samples: bool = True) -> list[LegacyDeletionLifecycleItem]:
        items = list(self._registry.lifecycle_items)
        if not include_samples:
            items = [item for item in items if not item.sample]
        return sorted(items, key=lambda item: item.legacy_item_id)

    def lifecycle_for_route(self, path_pattern: str, *, include_samples: bool = True) -> list[LegacyDeletionLifecycleItem]:
        items = self.list_lifecycle_items(include_samples=include_samples)
        return [
            item
            for item in items
            if item.legacy_path == path_pattern or item.replacement_path == path_pattern
        ]

    def find_route(self, path: str, methods: set[str] | None = None) -> RouteRegistryEntry | None:
        matches = [entry for entry in self._registry.routes if route_matches(entry, path, methods)]
        if not matches:
            return None
        return sorted(matches, key=lambda item: _match_specificity(item, path), reverse=True)[0]

    def filtered_routes(self, filters: dict[str, str]) -> list[RouteRegistryEntry]:
        routes = self.list_routes()
        for key, value in filters.items():
            if value == "":
                continue
            if key == "legacy_fallback_allowed":
                expected = value.lower() in {"1", "true", "yes"}
                routes = [route for route in routes if route.legacy_fallback_allowed is expected]
            else:
                routes = [route for route in routes if str(getattr(route, key, "")) == value]
        return routes


@lru_cache(maxsize=1)
def get_route_registry_service() -> RouteRegistryService:
    return RouteRegistryService()


def _match_specificity(entry: RouteRegistryEntry, path: str) -> tuple[int, int]:
    wildcard_runtime_bonus = 0
    if "{path:path}" in path and ("*" in entry.path_pattern or "{path:path}" in entry.path_pattern):
        wildcard_runtime_bonus = 1
    exact_pattern_bonus = 1 if "*" not in entry.path_pattern and "{path:path}" not in entry.path_pattern else 0
    return (wildcard_runtime_bonus, exact_pattern_bonus, len(entry.path_pattern.replace("*", "")))
