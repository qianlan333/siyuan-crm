#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
DEFAULT_OUTPUT_YAML = ROOT / "docs/development/legacy_replacement_backlog.yaml"
DEFAULT_OUTPUT_MD = ROOT / "docs/development/legacy_replacement_backlog.md"

MANIFEST_REQUIRED_FIELDS = {
    "route_pattern",
    "methods",
    "capability_owner",
    "current_runtime_owner",
    "production_behavior",
    "legacy_fallback_allowed",
    "fixture_allowed_in_production",
    "external_side_effect_risk",
    "checker",
    "notes",
}
BACKLOG_REQUIRED_FIELDS = {
    "id",
    "route_pattern",
    "methods",
    "capability_owner",
    "current_runtime_owner",
    "production_behavior",
    "legacy_fallback_allowed",
    "fixture_allowed_in_production",
    "external_side_effect_risk",
    "checker",
    "replacement_phase",
    "replacement_category",
    "priority",
    "daily_business_critical",
    "business_continuity_requirement",
    "replacement_owner",
    "replacement_strategy",
    "fallback_required_until",
    "rollback_path",
    "delete_condition",
    "recommended_verification",
    "notes",
}
ALLOWED_CATEGORIES = {
    "readonly",
    "internal_write",
    "external_side_effect",
    "timer_or_automation_execution",
    "shell_or_navigation",
    "adapter_contract",
    "blocked_or_guarded",
}
ALLOWED_PHASES = {
    "phase_3_readonly",
    "phase_4_internal_write",
    "phase_5_external_adapter",
    "phase_6_timer_automation",
    "phase_7_retirement",
    "keep_guarded_until_adapter_ready",
}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_SIDE_EFFECT_RISKS = {"none", "guarded", "low", "medium", "high", "real_blocked"}
REAL_ALLOWED_VALUES = {
    "allowed",
    "enabled",
    "external_allowed",
    "production_allowed",
    "real",
    "real_allowed",
    "real_enabled",
    "true",
}
FALLBACK_REQUIRED_BEHAVIORS = {"legacy_forward", "scheduled_safe_mode", "fake_adapter", "guarded_preview"}
NO_FALLBACK_RUNTIME_OWNERS = {
    "next",
    "ai_crm_next",
    "next_native",
    "next_command",
    "next_adapter",
    "next_exact",
    "next_read_model",
    "next_read_model_only",
    "readonly_transaction_page",
    "archived_no_runtime",
}
NO_FALLBACK_PRODUCTION_BEHAVIORS = {
    "next",
    "next_native",
    "next_admin_shell",
    "next_command",
    "next_adapter",
    "next_exact",
    "next_read_model",
    "next_read_model_only",
    "readonly_transaction_page",
    "archived_no_runtime",
}
DAILY_BUSINESS_KEYWORDS = (
    "admin",
    "customers",
    "questionnaires",
    "channels",
    "wechat-pay",
    "alipay",
    "payment",
    "products",
    "orders",
    "checkout",
    "automation",
    "sidebar",
    "media",
    "image-library",
    "attachment-library",
    "miniprogram-library",
    "wecom",
)
EXTERNAL_ADAPTER_KEYWORDS = (
    "wechat-pay",
    "alipay",
    "checkout",
    "products",
    "orders",
    "pay/",
    "oauth",
    "wecom",
    "mcp",
    "openclaw",
    "callback",
    "media",
    "image-library",
    "attachment-library",
    "miniprogram-library",
    "upload",
)
TIMER_KEYWORDS = ("scheduled_safe_mode", "timer", "run-due", "reply-monitor", "capture", "campaigns/run-due", "jobs")


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _route_text(route: dict[str, Any]) -> str:
    return f"{route.get('route_pattern', '')} {route.get('production_behavior', '')} {route.get('external_side_effect_risk', '')} {route.get('notes', '')}".lower()


def _methods(route: dict[str, Any]) -> list[str]:
    methods = route.get("methods") or []
    return [str(method).upper() for method in methods]


def _has_write_method(route: dict[str, Any]) -> bool:
    return bool({"POST", "PUT", "PATCH", "DELETE"} & set(_methods(route)))


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _load_manifest_without_yaml(path: Path) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    in_routes = False
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "routes:":
            in_routes = True
            continue
        if not in_routes:
            continue
        if line.startswith("  - "):
            if current is not None:
                routes.append(current)
            current = {}
            item = line[4:].strip()
            if ":" in item:
                key, value = item.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
            continue
        if current is not None and line.startswith("    ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value)
    if current is not None:
        routes.append(current)
    return {"routes": routes}


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        return _load_manifest_without_yaml(path)


def classify_replacement_category(route: dict[str, Any]) -> str:
    text = _route_text(route)
    behavior = _normalize(route.get("production_behavior"))
    risk = _normalize(route.get("external_side_effect_risk"))
    pattern = str(route.get("route_pattern") or "").lower()

    if behavior == "scheduled_safe_mode" or _contains_any(text, TIMER_KEYWORDS):
        return "timer_or_automation_execution"
    if behavior == "fake_adapter":
        return "adapter_contract"
    if risk == "real_blocked" or _contains_any(text, EXTERNAL_ADAPTER_KEYWORDS):
        return "external_side_effect"
    if behavior == "guarded_preview":
        return "internal_write" if _has_write_method(route) else "blocked_or_guarded"
    if behavior == "readonly_facade":
        if pattern.startswith("/admin") or pattern.startswith("/sidebar") or "frontend_compat" in str(route.get("capability_owner")):
            return "shell_or_navigation"
        return "readonly"
    if behavior == "legacy_forward":
        if _has_write_method(route):
            return "internal_write"
        return "readonly"
    if behavior == "next_exact":
        return "readonly"
    return "blocked_or_guarded"


def classify_replacement_phase(route: dict[str, Any]) -> str:
    category = classify_replacement_category(route)
    risk = _normalize(route.get("external_side_effect_risk"))
    if category == "timer_or_automation_execution":
        return "phase_6_timer_automation"
    if category in {"external_side_effect", "adapter_contract"}:
        return "phase_5_external_adapter"
    if category == "blocked_or_guarded":
        return "keep_guarded_until_adapter_ready"
    if category == "internal_write":
        return "phase_4_internal_write"
    if category in {"readonly", "shell_or_navigation"}:
        return "phase_3_readonly" if risk == "none" else "phase_4_internal_write"
    return "phase_7_retirement"


def classify_priority(route: dict[str, Any]) -> str:
    phase = classify_replacement_phase(route)
    if phase == "phase_3_readonly":
        return "P0"
    if phase == "phase_4_internal_write":
        return "P1"
    if phase in {"phase_5_external_adapter", "keep_guarded_until_adapter_ready"}:
        return "P2"
    return "P3"


def infer_daily_business_critical(route: dict[str, Any]) -> bool:
    pattern = str(route.get("route_pattern") or "").lower()
    if pattern in {"/health", "/api/system/health", "/mcp"}:
        return False
    return _contains_any(_route_text(route), DAILY_BUSINESS_KEYWORDS)


def _continuity_requirement(route: dict[str, Any]) -> str:
    if route.get("legacy_fallback_allowed") is False:
        return (
            "Current route is documented with no legacy fallback. Preserve the current owner and production behavior, "
            "do not restore production_compat or legacy facade fallback, and verify the route does not regress to 404, "
            "500, empty-data false success, fixture/local_contract success, or accidental external side effects."
        )
    if not infer_daily_business_critical(route):
        return "Planning only; preserve current behavior and do not promote fixture/local_contract data into production success paths."
    return (
        "During replacement, do not interrupt the current production path. Keep legacy fallback until Next native parity, "
        "checker, smoke verification, and rollback are all satisfied. The route must not regress to 404, 500, empty-data "
        "false success, or accidental external side effects."
    )


def _replacement_strategy(route: dict[str, Any]) -> str:
    owner = _normalize(route.get("current_runtime_owner"))
    behavior = _normalize(route.get("production_behavior"))
    legacy_fallback_allowed = route.get("legacy_fallback_allowed") is True
    if not legacy_fallback_allowed and "frontend_compat" in owner:
        return (
            "Treat this as a frontend_compat page-shell migration candidate only; business APIs remain Next-owned. "
            "Do not classify it as legacy Flask fallback."
        )
    if not legacy_fallback_allowed and (owner in NO_FALLBACK_RUNTIME_OWNERS or behavior in NO_FALLBACK_PRODUCTION_BEHAVIORS):
        return (
            "Keep the current Next-owned route owner accurate, run the declared checker and smoke tests, "
            "and prevent registry/backlog drift. Do not add legacy fallback."
        )
    category = classify_replacement_category(route)
    if category in {"readonly", "shell_or_navigation"}:
        return "Build or harden a Next native read model/page first, compare parity, then narrow fallback only after smoke passes."
    if category == "internal_write":
        return "Move command validation and persistence into Next behind idempotent contracts while preserving legacy fallback."
    if category in {"external_side_effect", "adapter_contract"}:
        return "Define a Next adapter contract, keep real external calls blocked, and use fake/staging-disabled checks before any live enablement."
    if category == "timer_or_automation_execution":
        return "Keep scheduled safe mode and preview/dry-run guards until bounded execution, allowlists, audit, and rollback are proven."
    return "Keep guarded until the owning capability publishes a replacement adapter and delete condition."


def _fallback_required_until(route: dict[str, Any]) -> str:
    if route.get("legacy_fallback_allowed") is False:
        return (
            "No legacy fallback is required or allowed for this manifest entry; keep route owner checks current and "
            "do not restore production_compat or legacy facade fallback."
        )
    behavior = _normalize(route.get("production_behavior"))
    if behavior == "next_exact" and not route.get("legacy_fallback_allowed"):
        return "No legacy fallback required for this manifest entry; keep route owner checks in place."
    return "Next native parity, checker pass, smoke verification, rollback path, and owner approval are all complete."


def _rollback_path(route: dict[str, Any]) -> str:
    if route.get("legacy_fallback_allowed"):
        return "Keep or restore the manifest-owned legacy fallback / production_compat path; revert the replacement PR if parity or smoke fails."
    return "Revert the replacement PR; this manifest route does not rely on legacy fallback."


def _delete_condition(route: dict[str, Any]) -> str:
    if route.get("legacy_fallback_allowed"):
        return "Delete or narrow legacy fallback only after production parity, checker, smoke, observability, and rollback acceptance are complete."
    return "No legacy fallback delete action remains for this manifest entry; keep manifest, registry, and checker state current."


def _recommended_verification(route: dict[str, Any]) -> list[str]:
    checks = [str(route.get("checker") or "").strip() or "route owner checker"]
    category = classify_replacement_category(route)
    if category in {"readonly", "shell_or_navigation"}:
        checks.extend(["read-model parity check", "admin/browser smoke for the current page or API"])
    elif category == "internal_write":
        checks.extend(["contract test for write validation", "idempotency and rollback smoke"])
    elif category in {"external_side_effect", "adapter_contract"}:
        checks.extend(["fake/staging-disabled adapter check", "assert real external call is not enabled"])
    elif category == "timer_or_automation_execution":
        checks.extend(["dry-run or preview smoke", "allowlist and audit guard check"])
    if route.get("legacy_fallback_allowed"):
        checks.append("legacy fallback rollback check")
    else:
        checks.append("route owner drift guard")
    return checks


def build_backlog_entry(route: dict[str, Any], index: int = 0) -> dict[str, Any]:
    return {
        "id": f"LRB-{index + 1:03d}",
        "route_pattern": route["route_pattern"],
        "methods": _methods(route),
        "capability_owner": route["capability_owner"],
        "current_runtime_owner": route["current_runtime_owner"],
        "production_behavior": route["production_behavior"],
        "legacy_fallback_allowed": bool(route["legacy_fallback_allowed"]),
        "fixture_allowed_in_production": bool(route["fixture_allowed_in_production"]),
        "external_side_effect_risk": route["external_side_effect_risk"],
        "checker": route["checker"],
        "replacement_phase": classify_replacement_phase(route),
        "replacement_category": classify_replacement_category(route),
        "priority": classify_priority(route),
        "daily_business_critical": infer_daily_business_critical(route),
        "business_continuity_requirement": _continuity_requirement(route),
        "replacement_owner": route["capability_owner"],
        "replacement_strategy": _replacement_strategy(route),
        "fallback_required_until": _fallback_required_until(route),
        "rollback_path": _rollback_path(route),
        "delete_condition": _delete_condition(route),
        "recommended_verification": _recommended_verification(route),
        "notes": route.get("notes") or "",
    }


def build_backlog(routes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "status": "current_progress_snapshot_no_runtime_change",
        "source_manifest": "docs/route_ownership/production_route_ownership_manifest.yaml",
        "business_continuity": (
            "This is the current progress snapshot generated from production_route_ownership_manifest.yaml. It does "
            "not change runtime behavior, restore legacy fallback, enable real external calls, or allow "
            "fixture/local_contract data in production success paths. If a route has legacy_fallback_allowed=false, "
            "the backlog must not require continuing fallback."
        ),
        "entries": [build_backlog_entry(route, index) for index, route in enumerate(routes)],
    }


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_yaml_scalar(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def _write_mapping(lines: list[str], mapping: dict[str, Any], indent: int = 0) -> None:
    prefix = " " * indent
    for key, value in mapping.items():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            lines.append(f"{prefix}{key}:")
            for item in value:
                lines.append(f"{prefix}  - id: {_yaml_scalar(item['id'])}")
                for child_key, child_value in item.items():
                    if child_key == "id":
                        continue
                    lines.append(f"{prefix}    {child_key}: {_yaml_scalar(child_value)}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")


def render_backlog_yaml(backlog: dict[str, Any]) -> str:
    lines: list[str] = []
    _write_mapping(lines, backlog)
    return "\n".join(lines) + "\n"


def _count(entries: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(entry[field]) for entry in entries).items()))


def _phase_sort_key(entry: dict[str, Any]) -> tuple[int, int, str]:
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    category_bonus = 0 if entry["replacement_category"] in {"readonly", "shell_or_navigation"} else 1
    return (priority_order.get(entry["priority"], 9), category_bonus, str(entry["route_pattern"]))


def _top_ten(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [
        entry
        for entry in entries
        if entry["replacement_phase"] == "phase_3_readonly"
        and entry["external_side_effect_risk"] == "none"
        and entry["fixture_allowed_in_production"] is False
        and entry["checker"]
    ]
    return sorted(eligible, key=_phase_sort_key)[:10]


def render_backlog_markdown(backlog: dict[str, Any]) -> str:
    entries = list(backlog["entries"])
    has_legacy_fallback = any(entry.get("legacy_fallback_allowed") is True for entry in entries)
    by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_phase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_owner[entry["capability_owner"]].append(entry)
        by_phase[entry["replacement_phase"]].append(entry)

    lines = [
        "# Legacy Replacement Backlog - Current Progress Snapshot",
        "",
        "Status: Current progress snapshot, no runtime change. This document is generated from the production route ownership manifest and must stay synchronized with the route registry and checker.",
        "",
        "## Replacement Principles",
        "",
        "1. read-only first",
        "2. internal write second",
        "3. external side-effect third",
        "4. timer / automation execution last",
        "",
        "## Business Continuity",
        "",
        "- Do not interrupt current production daily use.",
        "- Do not restore production_compat or legacy facade fallback.",
        "- Do not enable real external calls.",
        "- Do not let fixture/local_contract data enter production success paths.",
        "- Keep route registry, manifest, and generated backlog synchronized.",
    ]
    if has_legacy_fallback:
        lines.append("- Routes that still explicitly allow fallback must keep fallback until parity, checker, smoke, and rollback conditions are satisfied.")
    lines.extend(["", "## Summary By Capability Owner", ""])
    for owner in sorted(by_owner):
        owner_entries = by_owner[owner]
        priorities = Counter(entry["priority"] for entry in owner_entries)
        lines.append(
            f"- `{owner}`: {len(owner_entries)} routes; "
            + ", ".join(f"{key}={priorities[key]}" for key in sorted(priorities))
        )

    lines.extend(["", "## Summary By Replacement Phase", ""])
    for phase in sorted(by_phase):
        phase_entries = by_phase[phase]
        categories = Counter(entry["replacement_category"] for entry in phase_entries)
        lines.append(
            f"- `{phase}`: {len(phase_entries)} routes; "
            + ", ".join(f"{key}={categories[key]}" for key in sorted(categories))
        )

    lines.extend(["", "## Top 10 Suggested First Replacements", ""])
    for index, entry in enumerate(_top_ten(entries), start=1):
        lines.extend(
            [
                f"### {index}. `{entry['route_pattern']}`",
                "",
                f"- owner: `{entry['capability_owner']}`",
                f"- priority: `{entry['priority']}` / `{entry['replacement_phase']}` / `{entry['replacement_category']}`",
                "- why first: read-only or shell/navigation path, no external side effect, fixture is blocked in production, and checker is already declared.",
                f"- continuity: {entry['business_continuity_requirement']}",
                f"- owner/drift guard: {entry['fallback_required_until']}",
                "- verification: " + "; ".join(entry["recommended_verification"]),
                "",
            ]
        )

    lines.extend(["## Full Backlog Index", ""])
    for entry in entries:
        lines.append(
            f"- `{entry['id']}` `{entry['route_pattern']}`: `{entry['priority']}` / "
            f"`{entry['replacement_phase']}` / `{entry['replacement_category']}` / owner `{entry['capability_owner']}`"
        )
    return "\n".join(lines) + "\n"


def _invalid_real_external_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value is True
    return _normalize(value) in REAL_ALLOWED_VALUES


def validate_manifest_routes(routes: list[dict[str, Any]], root: Path = ROOT) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    for index, route in enumerate(routes):
        label = str(route.get("route_pattern") or f"routes[{index}]")
        missing = sorted(MANIFEST_REQUIRED_FIELDS - set(route))
        if missing:
            blockers.append(f"{label} missing manifest fields: {missing}")
            continue
        if route.get("fixture_allowed_in_production") is not False:
            blockers.append(f"{label} fixture_allowed_in_production must be false")
        risk = _normalize(route.get("external_side_effect_risk"))
        if risk not in ALLOWED_SIDE_EFFECT_RISKS:
            blockers.append(f"{label} invalid external_side_effect_risk={route.get('external_side_effect_risk')}")
        if _invalid_real_external_value(route.get("external_side_effect_risk")):
            blockers.append(f"{label} external side effect cannot be marked allowed/enabled")
        if not (root / str(route.get("checker"))).exists():
            warnings.append(f"{label} checker does not exist locally: {route.get('checker')}")
    return blockers, warnings


def validate_backlog_entries(entries: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for entry in entries:
        label = str(entry.get("route_pattern") or entry.get("id") or "entry")
        missing = sorted(BACKLOG_REQUIRED_FIELDS - set(entry))
        if missing:
            blockers.append(f"{label} missing backlog fields: {missing}")
        if entry.get("replacement_category") not in ALLOWED_CATEGORIES:
            blockers.append(f"{label} invalid replacement_category={entry.get('replacement_category')}")
        if entry.get("replacement_phase") not in ALLOWED_PHASES:
            blockers.append(f"{label} invalid replacement_phase={entry.get('replacement_phase')}")
        if entry.get("priority") not in ALLOWED_PRIORITIES:
            blockers.append(f"{label} invalid priority={entry.get('priority')}")
        if entry.get("fixture_allowed_in_production") is not False:
            blockers.append(f"{label} fixture_allowed_in_production must be false")
        if _invalid_real_external_value(entry.get("external_side_effect_risk")):
            blockers.append(f"{label} external side effect cannot be marked allowed/enabled")
        if entry.get("production_behavior") in FALLBACK_REQUIRED_BEHAVIORS and not entry.get("fallback_required_until"):
            blockers.append(f"{label} missing fallback_required_until")
        if entry.get("daily_business_critical") is True and not entry.get("business_continuity_requirement"):
            blockers.append(f"{label} daily business critical route missing business_continuity_requirement")
    return blockers


def build_report(
    manifest_path: Path = DEFAULT_MANIFEST,
    output_yaml: Path = DEFAULT_OUTPUT_YAML,
    output_md: Path = DEFAULT_OUTPUT_MD,
    *,
    check: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not manifest_path.exists():
        return {
            "overall": "FAIL",
            "total_routes": 0,
            "counts_by_phase": {},
            "counts_by_category": {},
            "counts_by_priority": {},
            "blockers": [f"manifest does not exist: {manifest_path}"],
            "warnings": [],
        }

    manifest = load_manifest(manifest_path)
    routes = manifest.get("routes") or []
    if not isinstance(routes, list):
        routes = []
        blockers.append("manifest routes must be a list")

    manifest_blockers, manifest_warnings = validate_manifest_routes(routes, root=root)
    blockers.extend(manifest_blockers)
    warnings.extend(manifest_warnings)
    backlog = build_backlog(routes)
    entries = list(backlog["entries"])
    blockers.extend(validate_backlog_entries(entries))

    rendered_yaml = render_backlog_yaml(backlog)
    rendered_md = render_backlog_markdown(backlog)
    if check:
        if not output_yaml.exists():
            blockers.append(f"--check output yaml missing: {output_yaml}")
        elif output_yaml.read_text(encoding="utf-8") != rendered_yaml:
            blockers.append(f"--check output yaml differs from generated backlog: {output_yaml}")
        if not output_md.exists():
            blockers.append(f"--check output md missing: {output_md}")
        elif output_md.read_text(encoding="utf-8") != rendered_md:
            blockers.append(f"--check output md differs from generated backlog: {output_md}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "total_routes": len(routes),
        "counts_by_phase": _count(entries, "replacement_phase"),
        "counts_by_category": _count(entries, "replacement_category"),
        "counts_by_priority": _count(entries, "priority"),
        "blockers": blockers,
        "warnings": warnings,
        "backlog": backlog,
        "rendered_yaml": rendered_yaml,
        "rendered_md": rendered_md,
    }


def _report_for_output(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall": report["overall"],
        "total_routes": report["total_routes"],
        "counts_by_phase": report["counts_by_phase"],
        "counts_by_category": report["counts_by_category"],
        "counts_by_priority": report["counts_by_priority"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check the AI-CRM legacy replacement backlog.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-yaml", default=str(DEFAULT_OUTPUT_YAML))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    output_yaml = Path(args.output_yaml)
    output_md = Path(args.output_md)
    report = build_report(manifest_path, output_yaml, output_md, check=args.check)

    if not args.check and report["overall"] == "PASS":
        output_yaml.parent.mkdir(parents=True, exist_ok=True)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_yaml.write_text(report["rendered_yaml"], encoding="utf-8")
        output_md.write_text(report["rendered_md"], encoding="utf-8")

    output_report = _report_for_output(report)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(output_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"overall: {report['overall']}")
    print(f"total_routes: {report['total_routes']}")
    if report["blockers"]:
        print("blockers:")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    if report["warnings"]:
        print("warnings:")
        for warning in report["warnings"]:
            print(f"- {warning}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
