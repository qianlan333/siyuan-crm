#!/usr/bin/env python3
"""Static audit for Internal Event Queue coverage candidates.

This script intentionally does not import application modules, connect to
production, or execute business code. It scans repository text/AST and emits
JSON for human review.
"""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import print_json


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("aicrm_next", "tests", "docs/queue", "scripts", "migrations")
INCLUDE_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".sh", ".mako", ".html", ".js", ".css"}
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}

P0_2_EVENT_TYPES = {
    "payment.succeeded",
    "questionnaire.submitted",
    "customer.tagged",
    "customer.untagged",
    "customer.phone_bound",
    "ai_campaign.created",
    "ai_campaign.approved",
    "ai_campaign.started",
    "ops_plan.approved",
    "broadcast_task.created",
    "owner_migration.executed",
}

KEYWORDS = (
    "safe_emit",
    "emit_event",
    "internal_event",
    "ExternalEffectService",
    "external_effect_job",
    "external_effect_attempt",
    "webhook",
    "requests.post",
    "httpx",
    "aiohttp",
    "wecom",
    "feishu",
    "broadcast",
    "queue",
    "outbox",
    "side_effect",
    "automation_event",
    "automation_runtime",
    "payment",
    "refund",
    "tag",
    "phone",
    "bind_mobile",
    "owner_migration",
    "campaign",
    "ops_plan",
    "questionnaire",
    "notify",
    "send",
    "dispatch",
    "approve",
    "start",
    "create",
    "execute",
)

DIRECT_HTTP_PATTERNS = (
    "requests.post",
    "requests.request",
    "requests.get",
    "httpx.post",
    "httpx.request",
    "httpx.AsyncClient",
    "aiohttp.ClientSession",
    "urllib.request",
)

QUEUE_PATTERNS = (
    "broadcast_jobs",
    "external_effect_job",
    "domain_event_outbox",
    "side_effect_plan",
    "queue",
    "outbox",
    "run_due",
)

BUSINESS_FACT_WORDS = (
    "create",
    "approve",
    "start",
    "submit",
    "bind",
    "tag",
    "untag",
    "pay",
    "paid",
    "migrate",
    "execute",
    "refund",
    "cancel",
    "retry",
    "send",
)

BUSINESS_DOMAIN_WORDS = (
    "payment",
    "refund",
    "tag",
    "phone",
    "mobile",
    "bind_mobile",
    "owner_migration",
    "campaign",
    "ops_plan",
    "questionnaire",
    "broadcast",
    "automation",
)

EVENT_TYPE_RE = re.compile(r"\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*\b")
REGISTER_RE = re.compile(
    r"\.register\(\s*(?P<event>[^,\n]+)\s*,\s*[\"'](?P<consumer>[a-zA-Z0-9_:-]+)[\"']",
    re.MULTILINE,
)


@dataclass(frozen=True)
class FunctionSpan:
    name: str
    start: int
    end: int


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _is_scannable(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    return path.is_file() and path.suffix in INCLUDE_SUFFIXES


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        if base.is_file():
            if _is_scannable(base):
                files.append(base)
            continue
        for path in base.rglob("*"):
            if _is_scannable(path):
                files.append(path)
    return sorted(files)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _function_spans(path: Path, text: str) -> list[FunctionSpan]:
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    spans: list[FunctionSpan] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append(FunctionSpan(node.name, int(getattr(node, "lineno", 1)), int(getattr(node, "end_lineno", getattr(node, "lineno", 1)))))
    return sorted(spans, key=lambda item: (item.start, item.end))


def _nearest_function(spans: list[FunctionSpan], line: int) -> str:
    for span in spans:
        if span.start <= line <= span.end:
            return span.name
    return ""


def _string_value(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _ast_calls(path: Path, text: str, spans: list[FunctionSpan]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "safe_emit": [],
        "external_effect": [],
        "direct_http": [],
        "legacy_marker": [],
    }
    if path.suffix != ".py":
        return result
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return result
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        line = int(getattr(node, "lineno", 0) or 0)
        base = {"path": _rel(path), "line": line, "function": _nearest_function(spans, line), "call": name}
        if name.endswith("safe_emit") or name == "safe_emit":
            event_type = _string_value(node.args[0]) if node.args else ""
            result["safe_emit"].append({**base, "event_type": event_type})
        if "ExternalEffectService" in name or name.endswith("plan_effect") or name.endswith(".execute_due") or name.endswith(".retry"):
            result["external_effect"].append(base)
        if name in DIRECT_HTTP_PATTERNS:
            result["direct_http"].append(base)
        if name.endswith("record_runtime_marker") or name == "record_runtime_marker":
            legacy_key = _string_value(node.args[0]) if node.args else ""
            result["legacy_marker"].append({**base, "legacy_key": legacy_key})
    return result


def _keyword_hits(path: Path, text: str, spans: list[FunctionSpan]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lower = text.lower()
    if not any(keyword.lower() in lower for keyword in KEYWORDS):
        return hits
    for line_number, line in enumerate(text.splitlines(), start=1):
        matched = [keyword for keyword in KEYWORDS if keyword.lower() in line.lower()]
        if matched:
            hits.append(
                {
                    "path": _rel(path),
                    "line": line_number,
                    "function": _nearest_function(spans, line_number),
                    "keywords": sorted(set(matched)),
                    "snippet": line.strip()[:240],
                }
            )
    return hits


def _event_constants(path: Path, text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for match in EVENT_TYPE_RE.finditer(text):
        event_type = match.group(0)
        if "." not in event_type or event_type.startswith(("http.", "https.")):
            continue
        events.append({"path": _rel(path), "line": _line_for_offset(text, match.start()), "event_type": event_type})
    return events


def _consumer_registrations(path: Path, text: str) -> list[dict[str, Any]]:
    registrations: list[dict[str, Any]] = []
    for match in REGISTER_RE.finditer(text):
        event_expr = match.group("event").strip()
        registrations.append(
            {
                "path": _rel(path),
                "line": _line_for_offset(text, match.start()),
                "event_expr": event_expr,
                "consumer_name": match.group("consumer"),
            }
        )
    return registrations


def _classify_candidate_gap(hit: dict[str, Any], file_has_safe_emit: bool, file_has_external_effect: bool, file_has_marker: bool) -> dict[str, Any] | None:
    path = hit["path"]
    if path.startswith("tests/") or path.startswith("docs/"):
        return None
    line = " ".join([hit.get("snippet", ""), " ".join(hit.get("keywords", []))]).lower()
    keywords = set(hit.get("keywords") or [])
    if any(pattern.lower() in line for pattern in DIRECT_HTTP_PATTERNS):
        if "external_effect" not in path and "external_calls" not in path:
            return {
                "path": path,
                "line": hit["line"],
                "function": hit.get("function", ""),
                "candidate_type": "direct_http_call",
                "coverage_status": "legacy_direct_only" if not file_has_external_effect else "external_effect_only",
                "suggested_severity": "P1",
                "reason": "Direct HTTP client pattern found outside the External Effect boundary.",
            }
    if {"wecom", "feishu", "webhook"} & keywords and ("send" in keywords or "notify" in keywords or "dispatch" in keywords):
        if not file_has_external_effect and not file_has_marker:
            return {
                "path": path,
                "line": hit["line"],
                "function": hit.get("function", ""),
                "candidate_type": "external_side_effect_without_visible_gate",
                "coverage_status": "legacy_direct_only",
                "suggested_severity": "P1",
                "reason": "External side-effect wording without visible ExternalEffectService or legacy marker in the same file.",
            }
    if any(keyword in keywords for keyword in QUEUE_PATTERNS) and not file_has_safe_emit and not file_has_external_effect:
        return {
            "path": path,
            "line": hit["line"],
            "function": hit.get("function", ""),
            "candidate_type": "queue_or_outbox_without_internal_event",
            "coverage_status": "event_missing",
            "suggested_severity": "P2",
            "reason": "Queue/outbox wording found without safe_emit or ExternalEffectService in the same file.",
        }
    domain_hit = any(word in keywords or word in path.lower() for word in BUSINESS_DOMAIN_WORDS)
    if domain_hit and any(keyword in keywords for keyword in BUSINESS_FACT_WORDS) and not file_has_safe_emit and ("application.py" in path or path.endswith("/api.py")):
        return {
            "path": path,
            "line": hit["line"],
            "function": hit.get("function", ""),
            "candidate_type": "business_write_without_visible_internal_event",
            "coverage_status": "event_missing",
            "suggested_severity": "P2",
            "reason": "Application/API write-like wording found without safe_emit in the same file.",
        }
    return None


def main() -> None:
    files = _iter_files()
    keyword_hits: list[dict[str, Any]] = []
    event_constants: list[dict[str, Any]] = []
    consumer_regs: list[dict[str, Any]] = []
    safe_emits: list[dict[str, Any]] = []
    external_effect_calls: list[dict[str, Any]] = []
    direct_http_calls: list[dict[str, Any]] = []
    legacy_markers: list[dict[str, Any]] = []
    candidate_gaps: list[dict[str, Any]] = []
    per_file_flags: dict[str, dict[str, bool]] = {}

    for path in files:
        text = _read(path)
        spans = _function_spans(path, text)
        rel = _rel(path)
        ast_calls = _ast_calls(path, text, spans)
        safe_emits.extend(ast_calls["safe_emit"])
        external_effect_calls.extend(ast_calls["external_effect"])
        direct_http_calls.extend(ast_calls["direct_http"])
        legacy_markers.extend(ast_calls["legacy_marker"])
        event_constants.extend(_event_constants(path, text))
        consumer_regs.extend(_consumer_registrations(path, text))
        hits = _keyword_hits(path, text, spans)
        keyword_hits.extend(hits)
        flags = {
            "has_safe_emit": bool(ast_calls["safe_emit"]) or "safe_emit(" in text,
            "has_external_effect": bool(ast_calls["external_effect"]) or "ExternalEffectService" in text,
            "has_legacy_marker": bool(ast_calls["legacy_marker"]) or "record_runtime_marker" in text,
        }
        per_file_flags[rel] = flags
        for hit in hits:
            gap = _classify_candidate_gap(hit, flags["has_safe_emit"], flags["has_external_effect"], flags["has_legacy_marker"])
            if gap:
                candidate_gaps.append(gap)

    emitted_event_types = sorted({item.get("event_type") for item in safe_emits if "." in str(item.get("event_type"))})
    registered_by_expr: dict[str, list[str]] = defaultdict(list)
    for reg in consumer_regs:
        registered_by_expr[reg["event_expr"]].append(reg["consumer_name"])

    consumer_name_counts = Counter(reg["consumer_name"] for reg in consumer_regs)
    shared_consumers = {name: count for name, count in sorted(consumer_name_counts.items()) if count > 1}

    event_like_prefixes = (
        "payment.wechat.",
        "payment.alipay.",
        "payment.refund",
        "broadcast_task.",
        "customer.tag",
        "customer.phone_bound",
        "ai_campaign.",
        "ops_plan.",
        "owner_migration.",
        "questionnaire.submitted",
    )
    known_event_constants = sorted(
        {
            item["event_type"]
            for item in event_constants
            if item["event_type"] in P0_2_EVENT_TYPES or item["event_type"].startswith(event_like_prefixes)
        }
    )

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "repo_root": str(REPO_ROOT),
            "static_only": True,
            "production_accessed": False,
            "scan_roots": list(SCAN_ROOTS),
            "file_count": len(files),
            "keyword_hit_count": len(keyword_hits),
        },
        "summary": {
            "safe_emit_call_count": len(safe_emits),
            "emitted_event_types_literal": emitted_event_types,
            "known_event_constants": known_event_constants,
            "consumer_registration_count": len(consumer_regs),
            "shared_consumer_names": shared_consumers,
            "external_effect_call_count": len(external_effect_calls),
            "direct_http_call_count": len(direct_http_calls),
            "legacy_marker_call_count": len(legacy_markers),
            "candidate_gap_count": len(candidate_gaps),
        },
        "safe_emit_calls": safe_emits,
        "consumer_registrations": consumer_regs,
        "external_effect_calls": external_effect_calls,
        "direct_http_calls": direct_http_calls,
        "legacy_marker_calls": legacy_markers,
        "candidate_gaps": candidate_gaps[:500],
        "notes": [
            "candidate_gaps are heuristic and require human review before severity assignment",
            "consumer registrations using constants are reported by expression, not runtime-resolved values",
            "tests and docs are scanned for evidence but excluded from gap heuristics",
        ],
    }
    print_json(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
