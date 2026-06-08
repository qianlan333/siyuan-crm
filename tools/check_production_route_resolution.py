#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from starlette.routing import Match

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report

MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"

NEXT_OWNED_BEHAVIORS = {
    "next_exact",
    "next_command",
    "next_adapter",
    "guarded_preview",
    "fake_adapter",
    "readonly_facade",
    "next_export",
    "next_cloud_observability",
    "next_wecom_customer_acquisition",
}
PRODUCTION_COMPAT_BEHAVIORS = {"legacy_forward", "scheduled_safe_mode"}

RESOLUTION_SAMPLES = [
    ("GET", "/health"),
    ("GET", "/api/system/health"),
    ("GET", "/login"),
    ("POST", "/login"),
    ("OPTIONS", "/login"),
    ("GET", "/logout"),
    ("OPTIONS", "/logout"),
    ("GET", "/auth/wecom/start"),
    ("GET", "/api/customers"),
    ("GET", "/api/customers/wx_ext_001"),
    ("GET", "/api/customers/wx_ext_001/timeline"),
    ("GET", "/api/messages/wx_ext_001/recent"),
    ("GET", "/api/admin/questionnaires"),
    ("GET", "/admin/questionnaires"),
    ("GET", "/admin/questionnaires/new"),
    ("GET", "/admin/questionnaires/21"),
    ("GET", "/api/admin/questionnaires/21"),
    ("GET", "/api/h5/questionnaires/hxc-activation-v1"),
    ("GET", "/api/h5/wechat/oauth/start"),
    ("GET", "/api/admin/wecom/tags"),
    ("POST", "/api/admin/wecom/tags"),
    ("PATCH", "/api/admin/wecom/tags/tag_fixture_active"),
    ("DELETE", "/api/admin/wecom/tags/tag_fixture_active"),
    ("POST", "/api/admin/wecom/tags/sync"),
    ("POST", "/api/admin/wecom/tags/sync-due"),
    ("GET", "/api/admin/wecom/tag-groups"),
    ("POST", "/api/admin/wecom/tag-groups"),
    ("PATCH", "/api/admin/wecom/tag-groups/group_fixture_lifecycle"),
    ("DELETE", "/api/admin/wecom/tag-groups/group_fixture_lifecycle"),
    ("GET", "/api/admin/automation-conversion/overview"),
    ("GET", "/api/admin/automation-conversion/agents/options"),
    ("POST", "/api/customer-automation/activation-webhook"),
    ("GET", "/admin/hxc-dashboard"),
    ("GET", "/admin/hxc-send-config"),
    ("GET", "/api/admin/hxc-dashboard"),
    ("POST", "/api/admin/hxc-dashboard/refresh"),
    ("POST", "/api/admin/hxc-dashboard/refresh-directory"),
    ("GET", "/api/admin/hxc-dashboard/send-config"),
    ("POST", "/api/admin/hxc-dashboard/send-config"),
    ("DELETE", "/api/admin/hxc-dashboard/send-config/hxc_sender_fixture"),
    ("POST", "/api/admin/hxc-dashboard/broadcast"),
    ("GET", "/api/admin/hxc-dashboard/unknown"),
    ("GET", "/admin/wechat-pay/products"),
    ("GET", "/admin/wechat-pay/products/new"),
    ("GET", "/api/admin/wechat-pay/products"),
    ("POST", "/api/admin/wechat-pay/products"),
    ("GET", "/api/admin/wechat-pay/products/lead-channels"),
    ("GET", "/api/admin/wechat-pay/products/1"),
    ("GET", "/api/admin/wechat-pay/products/1/share"),
    ("POST", "/api/admin/wechat-pay/products/1/copy"),
    ("GET", "/api/admin/wechat-pay/products/1/external-push"),
    ("PUT", "/api/admin/wechat-pay/products/1/external-push"),
    ("POST", "/api/admin/wechat-pay/products/1/external-push/test"),
    ("GET", "/p/prd_20260518095708_9f77db"),
    ("OPTIONS", "/p/prd_20260518095708_9f77db"),
    ("GET", "/pay/prd_20260518095708_9f77db"),
    ("OPTIONS", "/pay/prd_20260518095708_9f77db"),
    ("GET", "/api/products/prd_20260518095708_9f77db"),
    ("POST", "/api/products/prd_20260518095708_9f77db"),
    ("OPTIONS", "/api/products/prd_20260518095708_9f77db"),
    ("POST", "/api/checkout/wechat"),
    ("POST", "/api/checkout/alipay"),
    ("OPTIONS", "/api/checkout/wechat"),
    ("OPTIONS", "/api/checkout/alipay"),
    ("GET", "/api/checkout/unknown-child"),
    ("GET", "/api/orders/smoke"),
    ("GET", "/api/orders/smoke/status"),
    ("OPTIONS", "/api/orders/smoke"),
    ("OPTIONS", "/api/orders/smoke/status"),
    ("GET", "/api/orders/smoke/legacy-child"),
    ("POST", "/api/wechat-pay/notify"),
    ("OPTIONS", "/api/wechat-pay/notify"),
    ("GET", "/api/wechat-pay/unknown-child"),
    ("POST", "/api/alipay/notify"),
    ("GET", "/api/alipay/return"),
    ("OPTIONS", "/api/alipay/return"),
    ("GET", "/api/alipay/unknown-child"),
    ("GET", "/api/admin/wechat-pay/unknown-child"),
    ("OPTIONS", "/api/admin/wechat-pay/products"),
    ("GET", "/api/admin/alipay/transactions"),
    ("GET", "/api/admin/alipay/unknown-child"),
    ("GET", "/api/h5/wechat-pay/legacy-probe"),
    ("GET", "/api/h5/alipay/legacy-probe"),
    ("GET", "/api/admin/image-library"),
    ("POST", "/api/admin/image-library"),
    ("POST", "/api/admin/image-library/from-url"),
    ("POST", "/api/admin/image-library/from-base64"),
    ("POST", "/api/admin/image-library/upload"),
    ("GET", "/api/admin/image-library/image_masked_001"),
    ("PUT", "/api/admin/image-library/image_masked_001"),
    ("DELETE", "/api/admin/image-library/image_masked_001"),
    ("GET", "/api/admin/image-library/image_masked_001/thumbnail"),
    ("GET", "/api/admin/image-library/image_masked_001/variants/thumb_160"),
    ("GET", "/api/admin/attachment-library"),
    ("POST", "/api/admin/attachment-library"),
    ("POST", "/api/admin/attachment-library/upload"),
    ("GET", "/api/admin/attachment-library/attachment_masked_001"),
    ("PUT", "/api/admin/attachment-library/attachment_masked_001"),
    ("DELETE", "/api/admin/attachment-library/attachment_masked_001"),
    ("GET", "/api/admin/miniprogram-library"),
    ("POST", "/api/admin/miniprogram-library"),
    ("GET", "/api/admin/miniprogram-library/miniprogram_masked_001"),
    ("PUT", "/api/admin/miniprogram-library/miniprogram_masked_001"),
    ("DELETE", "/api/admin/miniprogram-library/miniprogram_masked_001"),
    ("GET", "/admin/image-library"),
    ("GET", "/admin/attachment-library"),
    ("GET", "/admin/miniprogram-library"),
    ("POST", "/api/admin/cloud-orchestrator/media/upload"),
    ("GET", "/admin/cloud-orchestrator/campaigns"),
    ("GET", "/api/admin/cloud-orchestrator/campaigns"),
    ("GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture"),
    ("GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members"),
    ("GET", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps"),
    ("POST", "/api/admin/cloud-orchestrator/campaigns/batch-start"),
    ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve"),
    ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/start"),
    ("PATCH", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps/0"),
    ("POST", "/api/admin/cloud-orchestrator/campaigns/run-due"),
    ("GET", "/api/admin/cloud-orchestrator/audit"),
    ("GET", "/api/admin/cloud-orchestrator/observability"),
    ("GET", "/api/admin/class-user-management/export"),
    ("GET", "/api/admin/wecom-customer-acquisition-links"),
    ("POST", "/api/admin/wecom-customer-acquisition-links"),
    ("POST", "/api/admin/automation-conversion/reply-monitor/capture"),
    ("POST", "/api/admin/automation-conversion/reply-monitor/run-due"),
    ("POST", "/api/admin/automation-conversion/jobs/run-due/preview"),
    ("POST", "/api/admin/automation-conversion/jobs/run-due"),
    ("POST", "/api/admin/automation-conversion/tasks/run-due"),
    ("POST", "/api/admin/automation-conversion/execution-items/123/send-via-bazhuayu"),
    ("GET", "/api/admin/automation-conversion/member"),
    ("POST", "/api/admin/automation-conversion/member/put-in-pool"),
    ("POST", "/api/admin/automation-conversion/member/remove-from-pool"),
    ("POST", "/api/admin/automation-conversion/member/set-focus"),
    ("POST", "/api/admin/automation-conversion/member/set-normal"),
    ("POST", "/api/admin/automation-conversion/member/mark-won"),
    ("POST", "/api/admin/automation-conversion/member/unmark-won"),
    ("POST", "/api/admin/automation-conversion/member/push-openclaw"),
    ("POST", "/wecom/external-contact/callback"),
    ("POST", "/api/wecom/events"),
    ("GET", "/api/customers/automation/signup-conversion/batches"),
    ("GET", "/api/customers/automation/signup-conversion/batches/1"),
    ("POST", "/api/customers/automation/activation-webhook"),
    ("GET", "/api/customers/automation/webhook-deliveries"),
    ("POST", "/api/customers/automation/webhook-deliveries/1/retry"),
    ("POST", "/api/customers/automation/webhook-deliveries/retry-due"),
    ("GET", "/sidebar/bind-mobile"),
    ("GET", "/api/sidebar/contact-binding-status"),
    ("GET", "/api/sidebar/customer-context"),
    ("GET", "/api/sidebar/jssdk-config"),
    ("GET", "/api/sidebar/lead-pool/status"),
    ("GET", "/api/sidebar/signup-tags/status"),
    ("GET", "/api/sidebar/marketing-status"),
    ("GET", "/api/sidebar/v2/workbench"),
    ("GET", "/api/sidebar/v2/materials"),
    ("GET", "/api/admin/customers/profile"),
    ("GET", "/api/admin/customers/profile/tags"),
    ("POST", "/api/sidebar/bind-mobile"),
    ("POST", "/api/sidebar/v2/materials/send"),
]


@contextmanager
def production_route_env():
    keys = {
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
    }
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ.pop("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", None)
    os.environ.setdefault("DATABASE_URL", "postgresql://route:route@127.0.0.1:1/aicrm_route")
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("SECRET_KEY", "production-route-resolution")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "route-resolution-token")
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_manifest(path: Path | None = None) -> list[dict[str, Any]]:
    manifest = yaml.safe_load((path or MANIFEST).read_text(encoding="utf-8"))
    return list(manifest.get("routes") or [])


def collect_app_routes() -> list[dict[str, Any]]:
    with production_route_env():
        module = importlib.import_module("aicrm_next.main")
        app = module.create_app()
    routes: list[dict[str, Any]] = []
    for index, route in enumerate(app.routes):
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        module_name = getattr(endpoint, "__module__", "") if endpoint else ""
        name = getattr(endpoint, "__name__", "") if endpoint else ""
        methods = sorted((getattr(route, "methods", None) or set()) - {"HEAD"})
        if path:
            routes.append(
                {
                    "index": index,
                    "path": path,
                    "methods": methods,
                    "endpoint_module": module_name,
                    "endpoint_name": name,
                    "is_production_compat": module_name == "aicrm_next.production_compat.api",
                    "is_catch_all": "{path:path}" in path,
                    "_route": route,
                }
            )
    return routes


def public_route(route: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in route.items() if key != "_route"}


def first_matching_route(routes: list[dict[str, Any]], *, method: str, path: str) -> dict[str, Any] | None:
    scope = {"type": "http", "method": method.upper(), "path": path, "root_path": "", "headers": []}
    for route in routes:
        match, _ = route["_route"].matches(scope)
        if match == Match.FULL:
            return route
    return None


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*")
    escaped = re.sub(r"\\\{[^{}]+:path\\\}", ".*", escaped)
    escaped = re.sub(r"\\\{[^{}]+\\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _record_supports_method(record: dict[str, Any], method: str | None) -> bool:
    if method is None:
        return True
    return method.upper() in {str(item).upper() for item in record.get("methods") or []}


def manifest_record_for_path(records: list[dict[str, Any]], path: str, method: str | None = None) -> dict[str, Any] | None:
    exact = [record for record in records if str(record["route_pattern"]) == path and _record_supports_method(record, method)]
    if exact:
        return exact[0]
    matches = [
        record
        for record in records
        if _record_supports_method(record, method) and _pattern_to_regex(str(record["route_pattern"])).match(path)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: len(str(item["route_pattern"]).replace("*", "")), reverse=True)[0]


def shadowed_exact_routes(routes: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shadowed: list[dict[str, Any]] = []
    for route in routes:
        if route["is_production_compat"] or route["is_catch_all"]:
            continue
        if "GET" not in route["methods"] and "POST" not in route["methods"]:
            continue
        method = "GET" if "GET" in route["methods"] else "POST"
        first = first_matching_route(routes, method=method, path=route["path"])
        if not first or not first["is_production_compat"]:
            continue
        manifest = manifest_record_for_path(records, route["path"], method) or {}
        shadowed.append(
            {
                "method": method,
                "path": route["path"],
                "expected_endpoint_module": route["endpoint_module"],
                "caught_by": public_route(first),
                "manifest_route_pattern": manifest.get("route_pattern", ""),
                "manifest_current_runtime_owner": manifest.get("current_runtime_owner", ""),
                "manifest_production_behavior": manifest.get("production_behavior", ""),
            }
        )
    return shadowed


def resolution_samples(routes: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for method, path in RESOLUTION_SAMPLES:
        first = first_matching_route(routes, method=method, path=path)
        manifest = manifest_record_for_path(records, path, method) or {}
        samples.append(
            {
                "method": method,
                "path": path,
                "route_owner": "production_compat" if first and first["is_production_compat"] else "next",
                "endpoint_module": first["endpoint_module"] if first else "",
                "endpoint_name": first["endpoint_name"] if first else "",
                "matched_route_path": first["path"] if first else "",
                "manifest_route_pattern": manifest.get("route_pattern", ""),
                "manifest_current_runtime_owner": manifest.get("current_runtime_owner", ""),
                "manifest_production_behavior": manifest.get("production_behavior", ""),
            }
        )
    return samples


def run_check() -> dict[str, Any]:
    records = load_manifest()
    routes = collect_app_routes()
    registry_report = build_route_check_report(strict=True)
    shadowed = shadowed_exact_routes(routes, records)
    samples = resolution_samples(routes, records)
    blockers: list[str] = []
    warnings: list[str] = []

    for item in shadowed:
        behavior = str(item.get("manifest_production_behavior") or "")
        owner = str(item.get("manifest_current_runtime_owner") or "")
        if behavior == "next_exact":
            blockers.append(f"manifest_next_exact_caught_by_production_compat:{item['method']} {item['path']}")
        elif owner == "next" and behavior in NEXT_OWNED_BEHAVIORS:
            blockers.append(f"manifest_next_owned_exact_caught_by_production_compat:{item['method']} {item['path']}")

    for sample in samples:
        behavior = str(sample.get("manifest_production_behavior") or "")
        owner = str(sample.get("manifest_current_runtime_owner") or "")
        route_owner = str(sample.get("route_owner") or "")
        route_label = f"{sample['method']} {sample['path']}"
        if behavior == "next_exact" and route_owner == "production_compat":
            blockers.append(f"manifest_next_exact_sample_caught_by_production_compat:{route_label}")
        if owner == "production_compat" and behavior in PRODUCTION_COMPAT_BEHAVIORS and route_owner != "production_compat":
            blockers.append(f"manifest_production_compat_sample_not_forwarded:{route_label}")
        if owner == "next" and behavior in NEXT_OWNED_BEHAVIORS and route_owner == "production_compat":
            blockers.append(f"manifest_next_owned_sample_caught_by_production_compat:{route_label}")

    categories = {
        "must_legacy_forward": [record for record in records if record.get("production_behavior") == "legacy_forward"],
        "must_next_exact": [record for record in records if record.get("production_behavior") == "next_exact"],
        "must_guarded_or_blocked": [
            record
            for record in records
            if record.get("production_behavior") in {"guarded_preview", "scheduled_safe_mode", "fake_adapter", "local_contract_only"}
            or record.get("current_runtime_owner") == "blocked"
        ],
    }
    registry_final_counts = {
        "undocumented_routes_count": len(registry_report["undocumented_routes"]),
        "legacy_fallback_routes_count": len(registry_report["legacy_fallback_routes"]),
        "unknown_owner_routes_count": len(registry_report["unknown_owner_routes"]),
        "deleted_but_still_registered_count": len(registry_report["deleted_but_still_registered_routes"]),
    }
    for name, value in registry_final_counts.items():
        if value:
            blockers.append(f"route_registry_final_count_nonzero:{name}={value}")
    return {
        "ok": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": warnings,
        "route_count": len(routes),
        "production_compat_route_count": len([route for route in routes if route["is_production_compat"]]),
        "production_compat_catch_all_count": len([route for route in routes if route["is_production_compat"] and route["is_catch_all"]]),
        "wildcard_legacy_forward_count": len([route for route in routes if route["is_production_compat"] and route["is_catch_all"]]),
        **registry_final_counts,
        "shadowed_exact_routes": shadowed,
        "resolution_samples": samples,
        "categories": {
            name: [
                {
                    "route_pattern": record["route_pattern"],
                    "current_runtime_owner": record["current_runtime_owner"],
                    "production_behavior": record["production_behavior"],
                }
                for record in values
            ]
            for name, values in categories.items()
        },
    }


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Production Route Resolution",
            "",
            f"- ok: `{str(result['ok']).lower()}`",
            f"- route_count: `{result['route_count']}`",
            f"- production_compat_route_count: `{result['production_compat_route_count']}`",
            f"- production_compat_catch_all_count: `{result['production_compat_catch_all_count']}`",
            f"- legacy_fallback_routes_count: `{result['legacy_fallback_routes_count']}`",
            f"- wildcard_legacy_forward_count: `{result['wildcard_legacy_forward_count']}`",
            f"- undocumented_routes_count: `{result['undocumented_routes_count']}`",
            f"- unknown_owner_routes_count: `{result['unknown_owner_routes_count']}`",
            f"- deleted_but_still_registered_count: `{result['deleted_but_still_registered_count']}`",
            f"- blockers: `{len(result['blockers'])}`",
            "",
            "## Resolution Samples",
        ]
        for item in result["resolution_samples"]:
            lines.append(
                f"- {item['method']} {item['path']}: `{item['route_owner']}` -> "
                f"`{item['endpoint_module']}.{item['endpoint_name']}` "
                f"(manifest `{item['manifest_route_pattern']}` / `{item['manifest_production_behavior']}`)"
            )
        lines.extend(["", "## Shadowed Exact Routes"])
        if result["shadowed_exact_routes"]:
            for item in result["shadowed_exact_routes"]:
                lines.append(f"- {item['method']} {item['path']} caught by `{item['caught_by']['path']}`")
        else:
            lines.append("- none")
        lines.extend(["", "## Blockers"])
        lines.extend(f"- {item}" for item in result["blockers"])
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI-CRM Next production route resolution.")
    parser.add_argument("--output-md")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_check()
    write_outputs(result, args.output_md, args.output_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
