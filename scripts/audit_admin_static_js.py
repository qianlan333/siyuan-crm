#!/usr/bin/env python3
"""Audit protected admin static JS surfaces.

This script is intentionally scoped to the admin pages that have already been
converted to the no-build JS/API pattern. It is report-only by default; use
--strict to make blocking findings fail CI or local verification.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
ADMIN_STATIC = ROOT / "wecom_ability_service" / "static" / "admin_console"
ADMIN_TEMPLATES = ROOT / "wecom_ability_service" / "templates" / "admin_console"

PROTECTED_TEMPLATES = [
    ADMIN_TEMPLATES / "customer_detail.html",
    ADMIN_TEMPLATES / "customer_pulse_inbox.html",
    ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html",
    ADMIN_TEMPLATES / "automation_conversion_overview_workspace.html",
    ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html",
    ADMIN_TEMPLATES / "base.html",
]

NO_FRONTEND_TOOLING_PATHS = [
    ROOT / "package.json",
    ROOT / "vite.config.ts",
    ROOT / "tsconfig.json",
    ROOT / "node_modules",
    ROOT / "web" / "package.json",
]

SCRIPT_ORDER_CONTRACTS = {
    ADMIN_TEMPLATES / "base.html": [
        "admin_console/admin_api_client.js",
        "admin_console/admin_console.js",
        "{% block scripts_extra %}",
    ],
    ADMIN_TEMPLATES / "customer_detail.html": [
        "customer_profile_core.js",
        "customer_profile_sections.js",
        "customer_profile_pulse.js",
        "customer_profile_followup.js",
        "customer_profile_automation.js",
        "customer_profile.js",
    ],
    ADMIN_TEMPLATES / "customer_pulse_inbox.html": [
        "customer_pulse_inbox_core.js",
        "customer_pulse_inbox_renderers.js",
        "customer_pulse_inbox_actions.js",
        "customer_pulse_inbox_boot.js",
        "customer_pulse_inbox.js",
    ],
    ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html": [
        "automation_auto_reply_core.js",
        "automation_auto_reply_outputs.js",
        "automation_auto_reply_modal.js",
        "automation_auto_reply_actions.js",
        "automation_auto_reply.js",
    ],
    ADMIN_TEMPLATES / "automation_conversion_overview_workspace.html": [
        "automation_overview_core.js",
        "automation_overview_renderers.js",
        "automation_overview_actions.js",
        "automation_overview.js",
    ],
    ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html": [
        "automation_agent_config_core.js",
        "automation_agent_config_agents.js",
        "automation_agent_config_templates.js",
        "automation_agent_config_tag_picker.js",
        "automation_agent_config_channel_model.js",
        "automation_agent_config_boot.js",
        "automation_agent_config.js",
    ],
}

NAMESPACE_RULES = [
    ("customer_profile", "CustomerProfile"),
    ("customer_pulse_inbox", "CustomerPulseInbox"),
    ("automation_auto_reply", "AutomationAutoReply"),
    ("automation_overview", "AutomationOverview"),
    ("automation_agent_config", "AutomationAgentConfig"),
]


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def protected_js_files() -> list[Path]:
    files = [
        ADMIN_STATIC / "admin_api_client.js",
        ADMIN_STATIC / "admin_console.js",
    ]
    for pattern in [
        "customer_profile*.js",
        "customer_pulse_inbox*.js",
        "automation_auto_reply*.js",
        "automation_overview*.js",
        "automation_agent_config*.js",
    ]:
        files.extend(sorted(ADMIN_STATIC.glob(pattern)))
    return sorted(dict.fromkeys(files))


def check_result(name: str, details: list[str], severity: str = "blocking") -> dict[str, object]:
    return {
        "name": name,
        "ok": not details,
        "severity": severity,
        "details": details,
    }


def check_no_frontend_build_tooling() -> dict[str, object]:
    details = [f"forbidden path exists: {rel(path)}" for path in NO_FRONTEND_TOOLING_PATHS if path.exists()]
    return check_result("no_frontend_build_tooling", details)


def inline_script_blocks(source: str) -> Iterable[tuple[str, str]]:
    pattern = re.compile(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(source):
        yield match.group("attrs"), match.group("body")


def is_allowed_inline_script(attrs: str, body: str) -> bool:
    if "src=" in attrs:
        return True
    if "application/json" in attrs:
        return True
    stripped = body.strip()
    if not stripped:
        return True
    return len(stripped) <= 160 and "function " not in stripped and "=>" not in stripped and "addEventListener" not in stripped


def check_protected_templates_no_large_inline_js() -> dict[str, object]:
    details: list[str] = []
    for path in PROTECTED_TEMPLATES:
        source = read_text(path)
        for attrs, body in inline_script_blocks(source):
            if not is_allowed_inline_script(attrs, body):
                details.append(f"{rel(path)} contains disallowed inline script")
        if path.name == "automation_conversion_auto_reply_workspace.html":
            for token in ["function requestJson", "function renderOutputs", "function runAction"]:
                if token in source:
                    details.append(f"{rel(path)} contains legacy inline marker: {token}")
        if path.name == "automation_conversion_overview_workspace.html":
            for token in [
                "function requestJson",
                "function renderDashboard",
                "function renderMemberGroups",
                "function postAdminAction",
                "(() =>",
            ]:
                if token in source:
                    details.append(f"{rel(path)} contains legacy inline marker: {token}")
        if path.name == "automation_conversion_agent_config_workspace.html":
            for token in [
                "function requestJson",
                "function renderAgentTable",
                "function renderTemplateTable",
                "function saveDefaultChannelSettings",
                "function loadModelSettings",
                "(() =>",
                "document.addEventListener",
            ]:
                if token in source:
                    details.append(f"{rel(path)} contains legacy inline marker: {token}")
    return check_result("protected_templates_no_large_inline_js", details)


def check_protected_js_no_module_system() -> dict[str, object]:
    details: list[str] = []
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]
    for path in protected_js_files():
        source = read_text(path)
        for token in forbidden_tokens:
            if token in source:
                details.append(f"{rel(path)} contains forbidden module-system token: {token.strip()}")
    return check_result("protected_js_no_module_system", details)


def check_protected_js_use_namespaces() -> dict[str, object]:
    details: list[str] = []
    admin_api_client = ADMIN_STATIC / "admin_api_client.js"
    if "window.AdminApi" not in read_text(admin_api_client):
        details.append(f"{rel(admin_api_client)} missing window.AdminApi")
    for path in protected_js_files():
        name = path.name
        source = read_text(path)
        for prefix, namespace in NAMESPACE_RULES:
            if name.startswith(prefix) and namespace not in source and f"window.{namespace}" not in source:
                details.append(f"{rel(path)} missing namespace marker {namespace}")
    return check_result("protected_js_use_namespaces", details)


def check_no_duplicate_request_helpers() -> dict[str, object]:
    details: list[str] = []
    for path in protected_js_files():
        if path.name == "admin_api_client.js":
            continue
        source = read_text(path)
        has_request_function = bool(re.search(r"\bfunction\s+requestJson\s*\(", source))
        looks_like_copied_helper = (
            has_request_function
            and "fetch(" in source
            and ("response.text()" in source or "response.json()" in source)
            and ("payload.ok === false" in source or "!payload.ok" in source)
        )
        if looks_like_copied_helper:
            details.append(f"{rel(path)} appears to duplicate generic requestJson")
    return check_result("no_duplicate_request_helpers", details)


def check_admin_api_client_contract() -> dict[str, object]:
    path = ADMIN_STATIC / "admin_api_client.js"
    source = read_text(path)
    required = [
        "window.AdminApi",
        "safeJsonParse",
        "escapeHtml",
        "requestJson",
        "isPermissionError",
        "FormData",
        "URLSearchParams",
        "JSON.stringify",
        "response.text",
        "same-origin",
    ]
    details = [f"{rel(path)} missing {token}" for token in required if token not in source]
    return check_result("admin_api_client_contract", details)


def check_script_order_contract() -> dict[str, object]:
    details: list[str] = []
    for path, tokens in SCRIPT_ORDER_CONTRACTS.items():
        source = read_text(path)
        positions: list[int] = []
        for token in tokens:
            index = source.find(token)
            if index < 0:
                details.append(f"{rel(path)} missing script-order token: {token}")
            positions.append(index)
        if any(index < 0 for index in positions):
            continue
        if positions != sorted(positions):
            details.append(f"{rel(path)} has incorrect script order: {tokens}")
    return check_result("script_order_contract", details)


def check_action_token_contract() -> dict[str, object]:
    expectations = [
        (ADMIN_STATIC / "customer_profile_pulse.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_STATIC / "customer_pulse_inbox_actions.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_STATIC / "automation_auto_reply_actions.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_STATIC / "automation_auto_reply_outputs.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html", ["data-admin-action-token"]),
        (ADMIN_STATIC / "automation_overview_actions.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_TEMPLATES / "automation_conversion_overview_workspace.html", ["data-admin-action-token"]),
        (ADMIN_STATIC / "automation_agent_config_agents.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_STATIC / "automation_agent_config_templates.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_STATIC / "automation_agent_config_channel_model.js", ["admin_action_token", "adminActionToken"]),
        (ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html", ["data-admin-action-token"]),
    ]
    details: list[str] = []
    for path, markers in expectations:
        source = read_text(path)
        if not any(marker in source for marker in markers):
            details.append(f"{rel(path)} missing action-token marker: {' or '.join(markers)}")
    return check_result("action_token_contract", details)


def check_agent_config_contract() -> dict[str, object]:
    path = ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html"
    source = read_text(path)
    required = [
        'id="automation-agent-config-root"',
        "data-api-urls",
        "data-selected-template-id",
        "data-admin-action-token",
        "automation-agent-config-initial-agents",
        "automation-agent-config-initial-templates",
        "automation-agent-config-initial-catalog",
    ]
    details = [f"{rel(path)} missing Agent Config contract marker: {token}" for token in required if token not in source]
    module_markers = [
        (ADMIN_STATIC / "automation_agent_config_templates.js", [
            "profile_segment_templates",
            "profile_segment_template_detail_base",
            "profile_segment_template_catalog",
            "renderTemplateTable",
            "saveTemplate",
        ]),
        (ADMIN_STATIC / "automation_agent_config_tag_picker.js", [
            "wecom_tags",
            "openTagPicker",
            "renderTagGroups",
            "confirmTagSelection",
        ]),
        (ADMIN_STATIC / "automation_agent_config_channel_model.js", [
            "default_channel_settings",
            "default_channel_generate_qr",
            "model_settings",
            "model_settings_test",
            "saveDefaultChannelSettings",
            "loadModelSettings",
            "testModelSettings",
        ]),
    ]
    for module_path, markers in module_markers:
        module_source = read_text(module_path)
        for marker in markers:
            if marker not in module_source:
                details.append(f"{rel(module_path)} missing Agent Config module marker: {marker}")
    return check_result("agent_config_contract", details)


def run_checks() -> dict[str, object]:
    checks = [
        check_no_frontend_build_tooling(),
        check_protected_templates_no_large_inline_js(),
        check_protected_js_no_module_system(),
        check_protected_js_use_namespaces(),
        check_no_duplicate_request_helpers(),
        check_admin_api_client_contract(),
        check_script_order_contract(),
        check_action_token_contract(),
        check_agent_config_contract(),
    ]
    blocking_count = sum(1 for check in checks if not check["ok"] and check["severity"] == "blocking")
    warnings_count = sum(1 for check in checks if not check["ok"] and check["severity"] == "warning")
    return {
        "ok": blocking_count == 0,
        "blocking_count": blocking_count,
        "warnings_count": warnings_count,
        "checks": checks,
    }


def print_text_report(payload: dict[str, object]) -> None:
    status = "OK" if payload["ok"] else "FAIL"
    print(f"admin static JS audit: {status}")
    print(f"blocking_count: {payload['blocking_count']}")
    print(f"warnings_count: {payload['warnings_count']}")
    for check in payload["checks"]:
        check_status = "OK" if check["ok"] else "FAIL"
        print(f"- {check_status} {check['name']} ({check['severity']})")
        for detail in check["details"]:
            print(f"  - {detail}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit protected admin static JS guardrails.")
    parser.add_argument("--json", action="store_true", help="output JSON report")
    parser.add_argument("--strict", action="store_true", help="exit 1 when blocking findings exist")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = run_checks()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(payload)
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
