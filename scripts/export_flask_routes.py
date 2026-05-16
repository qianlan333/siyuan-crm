from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import REPO_ROOT, ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import REPO_ROOT, ensure_repo_root_on_path

ROOT = ensure_repo_root_on_path()
assert ROOT == REPO_ROOT

EXCLUDED_METHODS = {"HEAD", "OPTIONS"}


def infer_auth_hint(rule: str) -> str:
    if (
        rule in {"/login", "/logout", "/favicon.ico"}
        or rule.startswith("/auth/wecom/")
        or rule.startswith("/s/")
        or rule.startswith("/api/h5/")
        or rule == "/<path:filename>"
        or rule.startswith("/static/")
    ):
        return "public_or_entry"
    if rule == "/mcp":
        return "mcp_bearer"
    if rule.startswith("/wecom/") or rule == "/api/wecom/events":
        return "wecom_callback_signature"
    if rule.startswith("/internal/"):
        return "internal_token"
    if rule.startswith("/admin") or rule.startswith("/api/admin/"):
        return "admin_session"
    if rule.startswith("/api/"):
        return "api_existing_behavior"
    return "existing_behavior"


def module_hint_for(app: Any, endpoint: str) -> str:
    view_func = app.view_functions.get(endpoint)
    if view_func is None:
        return ""
    return str(getattr(view_func, "__module__", "") or "")


def export_routes(app: Any | None = None) -> list[dict[str, Any]]:
    if app is None:
        from wecom_ability_service import create_app

        app = create_app({"TESTING": True})

    rows: list[dict[str, Any]] = []
    for rule in app.url_map.iter_rules():
        methods = sorted(str(method) for method in rule.methods if method not in EXCLUDED_METHODS)
        for method in methods:
            rows.append(
                {
                    "rule": rule.rule,
                    "endpoint": rule.endpoint,
                    "methods": [method],
                    "arguments": sorted(rule.arguments),
                    "auth_hint": infer_auth_hint(rule.rule),
                    "module_hint": module_hint_for(app, rule.endpoint),
                }
            )
    return sorted(rows, key=lambda row: (row["rule"], row["methods"][0] if row["methods"] else "", row["endpoint"]))


def build_inventory_payload(routes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = export_routes() if routes is None else routes
    return {
        "source": "wecom_ability_service.create_app({'TESTING': True}).url_map.iter_rules()",
        "route_count": len(rows),
        "routes": rows,
    }


def write_json(payload: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown_cell(value: object) -> str:
    text = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Generated Flask Route Inventory",
        "",
        "Source: `wecom_ability_service.create_app({'TESTING': True}).url_map.iter_rules()`",
        "",
        f"Route rows: `{payload['route_count']}`",
        "",
        "| Rule | Methods | Endpoint | Arguments | Auth hint | Module hint |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for route in payload["routes"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_markdown_cell(route['rule'])}`",
                    f"`{_markdown_cell(route['methods'])}`",
                    f"`{_markdown_cell(route['endpoint'])}`",
                    f"`{_markdown_cell(route['arguments'])}`",
                    f"`{_markdown_cell(route['auth_hint'])}`",
                    f"`{_markdown_cell(route['module_hint'])}`",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_markdown(payload: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_markdown(payload), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Flask routes from the current app url_map.")
    parser.add_argument("--json-out", help="Write JSON inventory to this path.")
    parser.add_argument("--markdown-out", help="Write Markdown inventory to this path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_inventory_payload()

    if args.json_out:
        write_json(payload, args.json_out)
    if args.markdown_out:
        write_markdown(payload, args.markdown_out)
    if not args.json_out and not args.markdown_out:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
