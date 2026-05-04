#!/usr/bin/env python3
"""Inventory the automation Agent Config workspace before JS extraction.

The script is report-only by default. It intentionally uses lightweight
pathlib/regex/string scans instead of a full HTML or JavaScript parser; the
goal is a stable Phase 8A migration inventory for the current template and
related tests, not semantic execution.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "wecom_ability_service" / "templates" / "admin_console" / "automation_conversion_agent_config_workspace.html"
AUTOMATION_HTTP = ROOT / "wecom_ability_service" / "http" / "automation_conversion.py"
TEST_FILES = [
    ROOT / "tests" / "test_api.py",
    ROOT / "tests" / "test_automation_conversion_v1.py",
    ROOT / "tests" / "test_automation_program_phase1.py",
    ROOT / "tests" / "test_admin_static_contract.py",
]

EXPECTED_ROOT_ID = "automation-agent-config-root"
EXPECTED_ROOT_DATA_ATTRIBUTES = [
    "data-api-urls",
    "data-selected-template-id",
    "data-admin-action-token",
]
EXPECTED_INITIAL_JSON_BLOCKS = [
    "automation-agent-config-initial-agents",
]
EXPECTED_API_URL_KEYS = [
    "registry",
    "agents_options",
    "agent_create",
    "agent_detail_base",
    "agent_draft_base",
    "agent_delete_base",
    "agent_publish_base",
    "model_settings",
    "model_settings_test",
]
MODULE_PROPOSAL = [
    "automation_agent_config_core.js",
    "automation_agent_config_agents.js",
    "automation_agent_config_channel_model.js",
    "automation_agent_config_boot.js",
    "automation_agent_config.js",
]
TEST_KEYWORDS = [
    "automation-conversion/shared/agents",
    "automation-agent-config",
    "agent-config",
    "agent_create",
    "agent_detail",
    "agent_draft",
    "agent_publish",
    "profile-segment",
    "profile_segment",
    "default_channel",
    "model_settings",
    "data-agent-edit",
    "data-agent-delete",
    "data-agent-placeholder",
    "conversion_followup_agent",
    "基础画像分层",
    "智能体",
    "变量插入区",
    "发布",
    "删除",
]


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def line_number(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def inline_script_blocks(source: str) -> Iterable[tuple[str, str, int]]:
    pattern = re.compile(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(source):
        yield match.group("attrs"), match.group("body"), line_number(source, match.start())


def extract_inline_logic(source: str) -> str:
    bodies: list[str] = []
    for attrs, body, _line in inline_script_blocks(source):
        if "src=" in attrs or "application/json" in attrs:
            continue
        stripped = body.strip()
        if stripped:
            bodies.append(stripped)
    return "\n\n".join(bodies)


def remove_large_inline_script_bodies(source: str) -> str:
    def replace(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        body = match.group("body")
        if "src=" in attrs or "application/json" in attrs:
            return match.group(0)
        return f"<script{attrs}></script>"

    return re.sub(
        r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>",
        replace,
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )


def extract_root_contract(source: str) -> dict[str, object]:
    match = re.search(r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bid=[\"']automation-agent-config-root[\"'][^>]*)>", source, re.DOTALL)
    attrs = match.group("attrs") if match else ""
    data_attrs = sorted(set(re.findall(r"\b(data-[\w-]+)(?:\s*=|\s|>)", attrs)))
    return {
        "id": EXPECTED_ROOT_ID if match else "",
        "tag": match.group("tag") if match else "",
        "data_attributes": data_attrs,
        "has_api_urls": "data-api-urls" in data_attrs,
        "has_admin_action_token": "data-admin-action-token" in data_attrs,
        "has_selected_template_id": "data-selected-template-id" in data_attrs,
    }


def extract_initial_json_blocks(source: str) -> list[str]:
    blocks = re.findall(r"<script\b[^>]*type=[\"']application/json[\"'][^>]*\bid=[\"']([^\"']+)[\"']", source, re.IGNORECASE)
    return [block_id for block_id in blocks if block_id.startswith("automation-agent-config-")]


def extract_api_url_keys(template_source: str, backend_source: str) -> list[str]:
    workspace_match = re.search(
        r"def _build_agent_config_workspace\([^)]*\).*?(?=\n\ndef |\Z)",
        backend_source,
        re.DOTALL,
    )
    workspace_source = workspace_match.group(0) if workspace_match else backend_source
    found = {
        key
        for key in EXPECTED_API_URL_KEYS
        if f'"{key}":' in workspace_source
        or f"'{key}':" in workspace_source
        or f"apiUrls.{key}" in template_source
    }
    return [key for key in EXPECTED_API_URL_KEYS if key in found]


def extract_dom_sections(source: str) -> list[dict[str, object]]:
    sections = [
        ("summary grid", "agent-config-summary-grid", "Agent/template/catalog counters at the page top."),
        ("agent table", "agent-table-body", "Current agent rows and edit/delete row actions."),
        ("agent form panel", "agent-form-panel", "Agent draft editor, prompt placeholders, save and publish controls."),
        ("published preview", "agent-published-role-prompt", "Published role/task prompt comparison area."),
        ("draft diff summary", "agent-diff-summary", "Draft versus published diff summary."),
        ("model infra settings", "model-settings-form", "DeepSeek/model infra form and connection test."),
        ("feedback / loading blocks", "agent-config-feedback", "Top-level feedback and loading state blocks."),
    ]
    return [
        {
            "name": name,
            "marker": marker,
            "present": marker in source,
            "notes": notes,
        }
        for name, marker, notes in sections
    ]


def classify_id(node_id: str) -> str:
    if node_id.startswith("agent-") or node_id.startswith("automation-agent"):
        return "agent_related_ids"
    if node_id.startswith("template-") or "category" in node_id:
        return "template_related_ids"
    if "tag" in node_id:
        return "tag_picker_ids"
    if node_id.startswith("default-channel"):
        return "default_channel_ids"
    if node_id.startswith("model-settings"):
        return "model_infra_ids"
    if "feedback" in node_id or "loading" in node_id or "empty" in node_id:
        return "feedback_loading_ids"
    return "misc_ids"


def extract_important_ids(source: str) -> dict[str, list[str]]:
    groups = {
        "agent_related_ids": [],
        "template_related_ids": [],
        "tag_picker_ids": [],
        "default_channel_ids": [],
        "model_infra_ids": [],
        "feedback_loading_ids": [],
        "misc_ids": [],
    }
    for node_id in sorted(set(re.findall(r"\bid=[\"']([^\"']+)[\"']", source))):
        if "{" in node_id or "$" in node_id:
            continue
        groups[classify_id(node_id)].append(node_id)
    return groups


def extract_data_attributes(source: str) -> dict[str, object]:
    attrs = re.findall(r"\b(data-[\w-]+)(?:\s*=|\s|>)", source)
    counts = Counter(attrs)
    notable = [
        "data-agent-edit",
        "data-agent-delete",
        "data-agent-placeholder",
        "data-template-id",
        "data-tag-picker",
        "data-tag-id",
        "data-api-urls",
        "data-admin-action-token",
        "data-selected-template-id",
    ]
    return {
        "counts": dict(sorted(counts.items())),
        "notable": {name: counts.get(name, 0) for name in notable},
    }


def classify_function(name: str) -> str:
    lowered = name.lower()
    if name in {"escapeHtml", "withId", "withCode", "prettyJson", "statusLabel", "statusBadgeClass"}:
        return "core/helpers"
    if "placeholder" in lowered or "contextsource" in lowered:
        return "placeholder insertion"
    if "agent" in lowered and any(token in lowered for token in ["delete", "publish", "payload", "collect"]):
        return "agent save/publish/delete"
    if "agent" in lowered:
        return "agent list/detail/form"
    if "tag" in lowered:
        return "tag picker"
    if "template" in lowered or "category" in lowered or "question" in lowered or "catalog" in lowered:
        if "option" in lowered or "category" in lowered:
            return "template category/options"
        return "template list/detail/form"
    if "defaultchannel" in lowered or "modelsettings" in lowered or "channel" in lowered or "model" in lowered:
        return "default channel/QR" if "channel" in lowered else "model settings/test"
    if lowered in {"initialize", "syncinitialstate"} or "refresh" in lowered:
        return "boot/event wiring"
    if "request" in lowered or "normalize" in lowered or "format" in lowered or "show" in lowered:
        return "core/helpers"
    return "unknown"


def function_chunks(script_source: str) -> list[tuple[str, int, str]]:
    lines = script_source.splitlines()
    starts: list[tuple[int, str]] = []
    function_re = re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
    arrow_re = re.compile(r"^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")
    for index, line in enumerate(lines):
        match = function_re.search(line) or arrow_re.search(line)
        if match:
            starts.append((index, match.group(1)))
    chunks: list[tuple[str, int, str]] = []
    for offset, (start_index, name) in enumerate(starts):
        end_index = starts[offset + 1][0] if offset + 1 < len(starts) else len(lines)
        chunks.append((name, start_index + 1, "\n".join(lines[start_index:end_index])))
    return chunks


def extract_inline_functions(script_source: str) -> list[dict[str, object]]:
    functions = []
    for name, line, chunk in function_chunks(script_source):
        functions.append(
            {
                "name": name,
                "line": line,
                "category": classify_function(name),
                "likely_uses_fetch_or_request": "fetch(" in chunk or "requestJson(" in chunk,
                "likely_uses_admin_action_token": "adminActionToken" in chunk or "admin_action_token" in chunk,
                "likely_touches_dom": any(token in chunk for token in ["document.", "elements.", "querySelector", "addEventListener", "scrollIntoView"]),
                "likely_renders_html": "innerHTML" in chunk or "`<" in chunk or "join('')" in chunk,
                "likely_mutates_state": bool(re.search(r"\bstate\.[A-Za-z0-9_]+(?:\s*=|\.push|\.splice|\.map|\.filter)", chunk)),
            }
        )
    return functions


def extract_request_inventory(script_source: str) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    request_re = re.compile(r"requestJson\((?P<url>[^,\n)]+)", re.MULTILINE)
    lines = script_source.splitlines()
    for match in request_re.finditer(script_source):
        start_line = line_number(script_source, match.start())
        nearby = "\n".join(lines[max(0, start_line - 4): min(len(lines), start_line + 12)])
        method_match = re.search(r"method:\s*[\"']([A-Z]+)[\"']", nearby)
        url_source = " ".join(match.group("url").strip().split())
        if "JSON.stringify" in nearby:
            payload_type = "JSON"
        elif "FormData" in nearby:
            payload_type = "FormData"
        elif "query" in nearby.lower():
            payload_type = "query"
        else:
            payload_type = "none_or_query"
        requests.append(
            {
                "line": start_line,
                "method": method_match.group(1) if method_match else "GET",
                "url_source": url_source,
                "payload_type": payload_type,
                "admin_action_token_nearby": "adminActionToken" in nearby or "admin_action_token" in nearby,
                "mutates_state_or_reloads_list": any(token in nearby for token in ["state.", "refresh", "render", "load"]),
            }
        )
    if "fetch(" in script_source:
        fetch_index = script_source.index("fetch(")
        requests.insert(
            0,
            {
                "line": line_number(script_source, fetch_index),
                "method": "dynamic",
                "url_source": "requestJson(url)",
                "payload_type": "options passthrough",
                "admin_action_token_nearby": False,
                "mutates_state_or_reloads_list": False,
            },
        )
    return requests


def extract_state_inventory(script_source: str) -> list[dict[str, object]]:
    expected = [
        ("agents", "agent list state"),
        ("templates", "profile segment template list state"),
        ("templateCatalog", "initial/catalog questionnaire state"),
        ("selectedAgentCode", "selected agent state"),
        ("selectedAgentDetail", "selected agent detail state"),
        ("selectedTemplateId", "selected template state"),
        ("selectedTemplateDetail", "selected template detail state"),
        ("tagModal", "tag picker modal state"),
        ("categoryDrafts", "template form category draft state"),
        ("defaultChannel", "default channel state"),
        ("defaultChannelSelectedTag", "default channel selected tag state"),
        ("modelSettings", "model/default channel state"),
    ]
    return [
        {
            "name": name,
            "present": bool(re.search(rf"\b{name}\b", script_source)),
            "notes": notes,
        }
        for name, notes in expected
    ]


def classify_test_match(line: str, keyword: str) -> str:
    lowered = line.lower()
    if ".js" in line or "static" in lowered:
        return "static_js_expected_after_migration"
    if "/api/" in line or "response.get_json" in line or "client.post" in line or "client.put" in line or "client.delete" in line:
        return "api_contract_assertion"
    if "assert" in line and ("html" in line or "data-" in line or keyword.startswith("data-") or any(ord(char) > 127 for char in line)):
        return "html_contract_assertion"
    if "client.get" in line or "status_code" in line:
        return "behavior_flow_test"
    return "unknown"


def migration_note_for_category(category: str) -> str:
    if category == "html_contract_assertion":
        return "If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file."
    if category == "api_contract_assertion":
        return "API response and payload contract assertions should not change in Phase 8B."
    if category == "behavior_flow_test":
        return "Route/page status and navigation behavior should not change in Phase 8B."
    if category == "static_js_expected_after_migration":
        return "Static-JS assertions are the expected destination after inline JS is extracted."
    return "Review during Phase 8B test migration."


def extract_test_impact_inventory() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for path in TEST_FILES:
        if not path.exists():
            continue
        lines = read_text(path).splitlines()
        for index, line in enumerate(lines, start=1):
            matched_keywords = [keyword for keyword in TEST_KEYWORDS if keyword in line]
            for keyword in matched_keywords:
                category = classify_test_match(line, keyword)
                items.append(
                    {
                        "file": rel(path),
                        "line": index,
                        "line_number": index,
                        "matched_keyword": keyword,
                        "matched_line": line.strip(),
                        "category": category,
                        "migration_note": migration_note_for_category(category),
                    }
                )
    return items


def build_risk_flags(template_source: str, script_source: str, api_keys: list[str], test_impacts: list[dict[str, object]]) -> list[str]:
    flags: list[str] = []
    if not script_source.strip():
        flags.append("remaining inline behavior is empty after Phase 8B-3")
    if len(script_source.splitlines()) > 500:
        flags.append("very large inline script")
    if "function requestJson" in script_source or "function escapeHtml" in script_source:
        flags.append("duplicate requestJson / escapeHtml")
    if len(api_keys) >= 10:
        flags.append("many API endpoints in one page")
    if "adminActionToken" in script_source or "admin_action_token" in script_source or "data-admin-action-token" in template_source:
        flags.append("admin_action_token required for writes")
    if "tagModal" in script_source or "default-channel-tag-modal" in template_source:
        flags.append("tag picker modal state")
    if "textarea" in template_source and ("role_prompt" in template_source or "task_prompt" in template_source):
        flags.append("JSON editor or prompt textarea state")
    if "deleteAgent" in script_source or "agent_publish_base" in script_source or "data-agent-delete" in template_source:
        flags.append("publish/delete destructive actions")
    flags.append("backend API paths should not change")
    if all(block in template_source for block in EXPECTED_INITIAL_JSON_BLOCKS):
        flags.append("page has initial JSON blocks that must be preserved")
    if test_impacts:
        flags.append("tests may assert inline HTML that will move into static JS after Phase 8B")
    return flags


def strict_failures(payload: dict[str, object]) -> list[str]:
    failures: list[str] = []
    root_contract = payload["root_contract"]
    if root_contract.get("id") != EXPECTED_ROOT_ID:
        failures.append("missing root id automation-agent-config-root")
    for attr in EXPECTED_ROOT_DATA_ATTRIBUTES:
        if attr not in root_contract.get("data_attributes", []):
            failures.append(f"missing root data attribute {attr}")
    for block_id in EXPECTED_INITIAL_JSON_BLOCKS:
        if block_id not in payload["initial_json_blocks"]:
            failures.append(f"missing initial JSON block {block_id}")
    all_ids = [node_id for group in payload["important_ids"].values() for node_id in group]
    if len(all_ids) < 15:
        failures.append("expected at least 15 id attributes")
    markers = {
        "agent": ["agent-table-body", "agent-form-panel"],
        "model settings": ["model-settings-form", "model-settings-test-button"],
    }
    template_source = read_text(TEMPLATE)
    for label, required_markers in markers.items():
        if not any(marker in template_source for marker in required_markers):
            failures.append(f"missing {label} marker")
    if "test_impact_inventory" not in payload:
        failures.append("missing test_impact_inventory key")
    if not payload["module_proposal"]:
        failures.append("module_proposal is empty")
    if not payload["risk_flags"]:
        failures.append("risk_flags is empty")
    return failures


def build_payload() -> dict[str, object]:
    template_source = read_text(TEMPLATE)
    backend_source = read_text(AUTOMATION_HTTP)
    template_markup_source = remove_large_inline_script_bodies(template_source)
    script_source = extract_inline_logic(template_source)
    api_keys = extract_api_url_keys(template_source, backend_source)
    test_impacts = extract_test_impact_inventory()
    payload: dict[str, object] = {
        "ok": True,
        "template": rel(TEMPLATE),
        "root_contract": extract_root_contract(template_source),
        "initial_json_blocks": extract_initial_json_blocks(template_source),
        "api_url_keys": api_keys,
        "dom_sections": extract_dom_sections(template_source),
        "important_ids": extract_important_ids(template_markup_source),
        "data_attributes": extract_data_attributes(template_source),
        "inline_functions": extract_inline_functions(script_source),
        "request_inventory": extract_request_inventory(script_source),
        "state_inventory": extract_state_inventory(script_source),
        "test_impact_inventory": test_impacts,
        "module_proposal": MODULE_PROPOSAL,
        "risk_flags": [],
        "strict_failures": [],
    }
    payload["risk_flags"] = build_risk_flags(template_source, script_source, api_keys, test_impacts)
    payload["strict_failures"] = strict_failures(payload)
    payload["ok"] = not payload["strict_failures"]
    return payload


def text_report(payload: dict[str, object]) -> str:
    lines = [
        f"Agent Config workspace inventory: {'OK' if payload['ok'] else 'FAIL'}",
        f"template: {payload['template']}",
        f"root: {payload['root_contract'].get('id')}",
        f"root data attributes: {', '.join(payload['root_contract'].get('data_attributes', []))}",
        f"initial JSON blocks: {', '.join(payload['initial_json_blocks'])}",
        f"api url keys ({len(payload['api_url_keys'])}): {', '.join(payload['api_url_keys'])}",
        f"ids: {sum(len(group) for group in payload['important_ids'].values())}",
        f"data attributes: {len(payload['data_attributes']['counts'])} unique",
        f"inline functions: {len(payload['inline_functions'])}",
        f"requests: {len(payload['request_inventory'])}",
        f"test impact matches: {len(payload['test_impact_inventory'])}",
        f"module proposal: {', '.join(payload['module_proposal'])}",
        "risk flags:",
    ]
    lines.extend(f"- {flag}" for flag in payload["risk_flags"])
    if payload["strict_failures"]:
        lines.append("strict failures:")
        lines.extend(f"- {failure}" for failure in payload["strict_failures"])
    return "\n".join(lines)


def markdown_report(payload: dict[str, object]) -> str:
    def bullet(items: Iterable[str]) -> list[str]:
        return [f"- `{item}`" for item in items]

    function_lines = [
        f"- `{item['name']}`: {item['category']}; request={item['likely_uses_fetch_or_request']}; token={item['likely_uses_admin_action_token']}; dom={item['likely_touches_dom']}; html={item['likely_renders_html']}; state={item['likely_mutates_state']}"
        for item in payload["inline_functions"]
    ]
    request_lines = [
        f"- line {item['line']}: `{item['method']}` via `{item['url_source']}`; payload={item['payload_type']}; token={item['admin_action_token_nearby']}; state/list={item['mutates_state_or_reloads_list']}"
        for item in payload["request_inventory"]
    ]
    state_lines = [
        f"- `{item['name']}`: {'present' if item['present'] else 'missing'}; {item['notes']}"
        for item in payload["state_inventory"]
    ]
    test_lines = [
        f"- `{item['file']}:{item.get('line_number') or item.get('line')}` `{item['matched_keyword']}` ({item['category']}): {item['matched_line']} -- {item['migration_note']}"
        for item in payload["test_impact_inventory"]
    ]
    dom_lines = [
        f"- {item['name']}: `{item['marker']}` {'present' if item['present'] else 'missing'} - {item['notes']}"
        for item in payload["dom_sections"]
    ]
    id_lines = []
    for group, values in payload["important_ids"].items():
        if values:
            id_lines.append(f"- {group}: " + ", ".join(f"`{value}`" for value in values))

    lines = [
        "# JS/API Phase 8A: Agent Config Workspace Inventory",
        "",
        "## Current Stage Goal",
        "",
        "- Phase 8A is inventory-only.",
        "- Do not split JavaScript in this phase.",
        "- Do not change API paths or backend business logic.",
        "- Prepare the Phase 8B module split for `automation_conversion_agent_config_workspace.html`.",
        "- Include test-impact inventory using the PR #121 static-JS assertion migration pattern.",
        "",
        "## Phase 8A 非目标 / Non-goals",
        "",
        "- 不拆 JS：本阶段只做 inventory，不把 inline JS 迁移到静态文件。",
        "- 不改 API：不修改任何 API path、method、payload 或 response contract。",
        "- 不改后端：不修改 automation_conversion.py 或其他后端业务逻辑。",
        "- 不改 Agent Config 模板行为：不修改 automation_conversion_agent_config_workspace.html 的运行行为。",
        "- 不改数据库：不修改 schema、迁移或数据写入逻辑。",
        "- 不改认证：不修改 session、RBAC、admin_action_token 或 internal token 逻辑。",
        "- 不引入 Vite/TypeScript/React/Vue：本阶段仍然保持普通静态 JS 路线。",
        "",
        "## Root Contract",
        "",
        f"- root id: `{payload['root_contract'].get('id')}`",
        *bullet(payload["root_contract"].get("data_attributes", [])),
        "",
        "## Initial JSON Blocks",
        "",
        *bullet(payload["initial_json_blocks"]),
        "",
        "## API URL Inventory",
        "",
        *bullet(payload["api_url_keys"]),
        "",
        "## DOM / Form / Modal Inventory",
        "",
        *dom_lines,
        "",
        "## Important ID Inventory",
        "",
        *id_lines,
        "",
        "## Inline JS Function Inventory",
        "",
        *function_lines,
        "",
        "## Request/action Inventory",
        "",
        *request_lines,
        "",
        "## State Inventory",
        "",
        *state_lines,
        "",
        "## Test Impact Inventory / Test impact inventory",
        "",
        "Phase 8B migration rules:",
        "",
        "- HTML should keep checking root/data/script/initial JSON blocks.",
        "- Button copy, data-action markers, placeholders, and modal text moved to static JS should be asserted from the target JS file.",
        "- API response, route status, and DB contract tests should not change.",
        "- Follow the PR #121 pattern: page HTML checks script references, while moved copy/actions are checked in static JS.",
        "",
        *test_lines,
        "",
        "## Phase 8B Module Plan",
        "",
        *bullet(payload["module_proposal"]),
        "",
        "## Risk Flags",
        "",
        *[f"- {flag}" for flag in payload["risk_flags"]],
        "",
        "## Phase 8B Forbidden Changes",
        "",
        "- Do not change backend APIs.",
        "- Do not change the root data contract.",
        "- Do not change the initial JSON blocks.",
        "- Do not change `admin_action_token` payload semantics.",
        "- Do not change destructive action confirm flows.",
        "- Do not introduce Vite, TypeScript, React, or Vue.",
        "",
        "## Recommended Order for Phase 8B",
        "",
        "- Phase 8B-1: core + boot + agent list/form + related test migration.",
        "- Phase 8B-2: templates + tag picker + related test migration.",
        "- Phase 8B-3: default channel + model settings + guardrails.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory the automation Agent Config workspace.")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument("--markdown-out", help="write Markdown report to path")
    parser.add_argument("--strict", action="store_true", help="exit 1 when core inventory contracts are missing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = build_payload()
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown_report(payload), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text_report(payload))
    if args.strict and not payload["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
