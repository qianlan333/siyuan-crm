from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.domains.customer_pulse import (
    build_customer_pulse_first_wave_review_report,
    build_customer_pulse_tenant_rollout_report,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Customer Pulse tenant rollout daily/weekly report.")
    parser.add_argument(
        "--mode",
        choices=("rollout", "review"),
        default="rollout",
        help="rollout 输出日报/周报；review 输出 7 天灰度复盘。",
    )
    parser.add_argument("--days", type=int, default=7, help="Report window in days. Use 1 for daily and 7 for weekly.")
    parser.add_argument(
        "--tenant",
        action="append",
        default=[],
        dest="tenants",
        help="Optional tenant key filter. Repeat for multiple tenants.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format.",
    )
    return parser.parse_args()


def _markdown_report(report: dict[str, object]) -> str:
    whitelist = dict(report.get("whitelist") or {})
    enabled_tenants = list(whitelist.get("enabled_tenants") or [])
    disabled_tenants = list(whitelist.get("disabled_tenants") or [])
    lines = [
        "# Customer Pulse 首批灰度日报/周报",
        "",
        f"- 生成时间：{report.get('generated_at')}",
        f"- 统计窗口：{report.get('window_days')} 天",
        f"- 全局开关：{'开启' if whitelist.get('global_enabled') else '关闭'}",
        f"- default_enabled：{whitelist.get('default_enabled')}",
        f"- tenant_mode：{whitelist.get('tenant_mode')}",
        f"- external_request_scoped_enforced：{whitelist.get('external_request_scoped_enforced')}",
        f"- whitelist_ready：{whitelist.get('whitelist_ready')}",
        f"- 白名单 tenant：{', '.join(enabled_tenants) if enabled_tenants else '(none)'}",
        f"- 非白名单 tenant：{', '.join(disabled_tenants) if disabled_tenants else '(none)'}",
        "",
        "| tenant | ai_success | ai_error | fallback_count | draft_preview_started | draft_confirmed | writeback_success | unauthorized_denied | cross_tenant_denied | draft_confirm_rate | fallback_rate | writeback_success_rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tenant_report in report.get("tenants") or []:
        item = dict(tenant_report or {})
        counts = dict(item.get("counts") or {})
        rates = dict(item.get("rates") or {})
        lines.append(
            "| {tenant} | {ai_success} | {ai_error} | {fallback_count} | {draft_preview_started} | {draft_confirmed} | {writeback_success} | {unauthorized_denied} | {cross_tenant_denied} | {draft_confirm_rate:.4f} | {fallback_rate:.4f} | {writeback_success_rate:.4f} |".format(
                tenant=item.get("tenant_key") or "",
                ai_success=int(counts.get("ai_success", 0) or 0),
                ai_error=int(counts.get("ai_error", 0) or 0),
                fallback_count=int(counts.get("fallback_count", 0) or 0),
                draft_preview_started=int(counts.get("draft_preview_started", 0) or 0),
                draft_confirmed=int(counts.get("draft_confirmed", 0) or 0),
                writeback_success=int(counts.get("writeback_success", 0) or 0),
                unauthorized_denied=int(counts.get("unauthorized_denied", 0) or 0),
                cross_tenant_denied=int(counts.get("cross_tenant_denied", 0) or 0),
                draft_confirm_rate=float(rates.get("draft_confirm_rate", 0.0) or 0.0),
                fallback_rate=float(rates.get("fallback_rate", 0.0) or 0.0),
                writeback_success_rate=float(rates.get("writeback_success_rate", 0.0) or 0.0),
            )
        )
    return "\n".join(lines)


def _decision_label(decision: str) -> str:
    return {
        "expand": "可扩到下一批 tenant",
        "hold": "继续维持当前灰度规模",
        "rollback": "立即回滚",
    }.get(str(decision or "").strip(), "继续维持当前灰度规模")


def _markdown_review_report(report: dict[str, object]) -> str:
    data_source = dict(report.get("data_source") or {})
    rollout = dict(report.get("rollout") or {})
    whitelist = dict(rollout.get("whitelist") or {})
    lines = [
        "# Customer Pulse 首批 tenant 7 天灰度复盘",
        "",
        f"- 生成时间：{report.get('generated_at')}",
        f"- 复盘窗口：{report.get('window_days')} 天",
        f"- 数据源类型：{data_source.get('source_type')}",
        f"- 数据源说明：{data_source.get('summary')}",
        f"- production_evidence_verified：{data_source.get('production_evidence_verified')}",
        f"- 白名单 tenant：{', '.join(list(whitelist.get('enabled_tenants') or [])) or '(none)'}",
        "",
    ]
    for tenant_review in report.get("tenants") or []:
        item = dict(tenant_review or {})
        totals = dict(item.get("seven_day_totals") or {})
        daily_average = dict(item.get("daily_average") or {})
        rates = dict(item.get("rates") or {})
        trend = dict(item.get("trend") or {})
        lines.extend(
            [
                f"## {item.get('tenant_key')}",
                "",
                f"- 分类：{item.get('status')}",
                f"- 是否满足扩容门槛：{item.get('meets_expansion_gate')}",
                f"- 观察天数：{trend.get('observed_days')}",
                f"- 7 天累计：ai_success={totals.get('ai_success')} ai_error={totals.get('ai_error')} fallback_count={totals.get('fallback_count')} draft_preview_started={totals.get('draft_preview_started')} draft_confirmed={totals.get('draft_confirmed')} writeback_success={totals.get('writeback_success')} unauthorized_denied={totals.get('unauthorized_denied')} cross_tenant_denied={totals.get('cross_tenant_denied')}",
                f"- 日均：ai_success={daily_average.get('ai_success')} ai_error={daily_average.get('ai_error')} fallback_count={daily_average.get('fallback_count')} draft_preview_started={daily_average.get('draft_preview_started')} draft_confirmed={daily_average.get('draft_confirmed')} writeback_success={daily_average.get('writeback_success')}",
                f"- 指标：ai_error_rate={rates.get('ai_error_rate'):.4f} fallback_rate={rates.get('fallback_rate'):.4f} draft_confirm_rate={rates.get('draft_confirm_rate'):.4f} writeback_success_rate={rates.get('writeback_success_rate'):.4f}",
                f"- 趋势：draft_preview_started={trend.get('draft_preview_started')} draft_confirmed={trend.get('draft_confirmed')} fallback_count={trend.get('fallback_count')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 最终结论",
            "",
            _decision_label(str(report.get("final_decision") or "")),
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    app = create_app()
    with app.app_context():
        if args.mode == "review":
            report = build_customer_pulse_first_wave_review_report(days=args.days, tenant_keys=args.tenants)
        else:
            report = build_customer_pulse_tenant_rollout_report(days=args.days, tenant_keys=args.tenants)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_markdown_review_report(report) if args.mode == "review" else _markdown_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
