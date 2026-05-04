from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.domains.customer_pulse import (
    build_customer_pulse_first_wave_review_report,
    build_customer_pulse_tenant_rollout_report,
    customer_pulse_rollout_whitelist_summary,
)

DEFAULT_STATE_PATH = ROOT / "docs" / "ai-customer-pulse" / "observation-state.json"
DEFAULT_DAILY_DIR = ROOT / "docs" / "ai-customer-pulse" / "observation-daily"
DEFAULT_VERDICT_PATH = ROOT / "docs" / "ai-customer-pulse" / "108-seven-day-verdict.md"


def _iso_now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "awaiting_real_whitelist_tenants",
            "observation_started_at": "",
            "days_observed": 0,
            "observed_tenants": [],
            "rollback_incident_detected": False,
            "rollback_incident_notes": [],
            "last_daily_run_at": "",
            "last_daily_report_path": "",
            "last_verdict_generated_at": "",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decision_label(decision: str) -> str:
    return {
        "expand": "可扩到下一批 tenant",
        "hold": "继续维持当前灰度规模",
        "rollback": "立即回滚",
    }.get(str(decision or "").strip(), "继续维持当前灰度规模")


def _markdown_daily(report: dict[str, Any], *, report_date: str, state: dict[str, Any]) -> str:
    rollout = dict(report or {})
    whitelist = dict(rollout.get("whitelist") or {})
    lines = [
        "# Customer Pulse 首批 tenant 灰度日报",
        "",
        f"- 报告日期：{report_date}",
        f"- 生成时间：{rollout.get('generated_at')}",
        f"- 观察开始时间：{state.get('observation_started_at') or '(pending)'}",
        f"- 已累计天数：{state.get('days_observed')}",
        f"- 观察 tenant：{', '.join(state.get('observed_tenants') or []) or '(none)'}",
        f"- 白名单 tenant：{', '.join(list(whitelist.get('enabled_tenants') or [])) or '(none)'}",
        f"- rollback_incident_detected：{state.get('rollback_incident_detected')}",
        "",
        "| tenant | ai_success | ai_error | fallback_count | draft_preview_started | draft_confirmed | writeback_success | unauthorized_denied | cross_tenant_denied | draft_confirm_rate | fallback_rate | writeback_success_rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tenant_report in rollout.get("tenants") or []:
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


def _markdown_verdict(report: dict[str, Any], *, state: dict[str, Any]) -> str:
    data_source = dict(report.get("data_source") or {})
    lines = [
        "# Customer Pulse 首批 tenant 7 天观察结论",
        "",
        f"- 生成时间：{report.get('generated_at')}",
        f"- 观察开始时间：{state.get('observation_started_at') or '(pending)'}",
        f"- 当前累计天数：{state.get('days_observed')}",
        f"- 观察 tenant：{', '.join(state.get('observed_tenants') or []) or '(none)'}",
        f"- rollback_incident_detected：{state.get('rollback_incident_detected')}",
        f"- 数据源类型：{data_source.get('source_type')}",
        f"- 数据源说明：{data_source.get('summary')}",
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
                f"- 是否达成扩容门槛：{item.get('meets_expansion_gate')}",
                f"- 7 天累计：ai_success={totals.get('ai_success')} ai_error={totals.get('ai_error')} fallback_count={totals.get('fallback_count')} draft_preview_started={totals.get('draft_preview_started')} draft_confirmed={totals.get('draft_confirmed')} writeback_success={totals.get('writeback_success')} unauthorized_denied={totals.get('unauthorized_denied')} cross_tenant_denied={totals.get('cross_tenant_denied')}",
                f"- 日均：ai_success={daily_average.get('ai_success')} ai_error={daily_average.get('ai_error')} fallback_count={daily_average.get('fallback_count')} draft_preview_started={daily_average.get('draft_preview_started')} draft_confirmed={daily_average.get('draft_confirmed')} writeback_success={daily_average.get('writeback_success')}",
                f"- 趋势：draft_preview_started={trend.get('draft_preview_started')} draft_confirmed={trend.get('draft_confirmed')} fallback_count={trend.get('fallback_count')}",
                f"- 指标：ai_error_rate={rates.get('ai_error_rate'):.4f} fallback_rate={rates.get('fallback_rate'):.4f} draft_confirm_rate={rates.get('draft_confirm_rate'):.4f} writeback_success_rate={rates.get('writeback_success_rate'):.4f}",
                "",
            ]
        )
    lines.extend(["## 最终结论", "", _decision_label(str(report.get("final_decision") or "")), ""])
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Customer Pulse seven-day observation cycle.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start or reset an observation cycle.")
    start.add_argument("--tenant", action="append", default=[], dest="tenants", help="Observed tenant key.")
    start.add_argument("--started-at", default="", help="Optional explicit start time.")
    start.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))

    daily = subparsers.add_parser("daily", help="Run daily observation and save daily markdown output.")
    daily.add_argument("--date", default="", help="Optional report date label.")
    daily.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))
    daily.add_argument("--daily-dir", default=str(DEFAULT_DAILY_DIR))
    daily.add_argument("--verdict-path", default=str(DEFAULT_VERDICT_PATH))

    verdict = subparsers.add_parser("verdict", help="Generate the day-7 verdict immediately.")
    verdict.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))
    verdict.add_argument("--verdict-path", default=str(DEFAULT_VERDICT_PATH))

    incident = subparsers.add_parser("incident", help="Record or clear rollback-grade incidents.")
    incident.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))
    incident.add_argument("--set", dest="set_incident", action="store_true")
    incident.add_argument("--clear", dest="clear_incident", action="store_true")
    incident.add_argument("--note", default="", help="Incident note.")

    status = subparsers.add_parser("status", help="Print current observation state.")
    status.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))

    return parser.parse_args()


def _start_cycle(app, *, state_path: Path, tenants: list[str], started_at: str) -> int:
    whitelist = customer_pulse_rollout_whitelist_summary()
    enabled_tenants = set(whitelist.get("enabled_tenants") or [])
    normalized_tenants = [str(item).strip() for item in tenants if str(item).strip()]
    state = _load_state(state_path)
    if normalized_tenants:
        invalid = [tenant for tenant in normalized_tenants if tenant not in enabled_tenants]
        if invalid:
            raise SystemExit(f"observation start failed: tenants not in whitelist: {', '.join(invalid)}")
    state.update(
        {
            "status": "running" if normalized_tenants else "awaiting_real_whitelist_tenants",
            "observation_started_at": started_at or _iso_now(),
            "days_observed": 0,
            "observed_tenants": normalized_tenants,
            "rollback_incident_detected": False,
            "rollback_incident_notes": [],
            "last_daily_run_at": "",
            "last_daily_report_path": "",
            "last_verdict_generated_at": "",
        }
    )
    _save_state(state_path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_verdict(app, *, state_path: Path, verdict_path: Path) -> int:
    state = _load_state(state_path)
    review = build_customer_pulse_first_wave_review_report(days=7, tenant_keys=state.get("observed_tenants") or [])
    final_decision = str(review.get("final_decision") or "hold")
    if bool(state.get("rollback_incident_detected")):
        final_decision = "rollback"
    if int(state.get("days_observed") or 0) < 7:
        final_decision = "hold"
    review["final_decision"] = final_decision
    verdict_path.parent.mkdir(parents=True, exist_ok=True)
    verdict_path.write_text(_markdown_verdict(review, state=state), encoding="utf-8")
    state["last_verdict_generated_at"] = _iso_now()
    _save_state(state_path, state)
    print(str(verdict_path))
    print(_decision_label(final_decision))
    return 0


def _run_daily(app, *, state_path: Path, daily_dir: Path, verdict_path: Path, report_date: str) -> int:
    state = _load_state(state_path)
    rollout = build_customer_pulse_tenant_rollout_report(days=1, tenant_keys=state.get("observed_tenants") or [])
    normalized_report_date = report_date or datetime.now().strftime("%Y-%m-%d")
    daily_dir.mkdir(parents=True, exist_ok=True)
    report_path = daily_dir / f"{normalized_report_date}.md"
    report_path.write_text(_markdown_daily(rollout, report_date=normalized_report_date, state=state), encoding="utf-8")
    if state.get("observed_tenants") and normalized_report_date != str(state.get("last_daily_run_at") or "")[:10]:
        state["days_observed"] = int(state.get("days_observed") or 0) + 1
    state["last_daily_run_at"] = _iso_now()
    state["last_daily_report_path"] = str(report_path)
    if state.get("observed_tenants"):
        state["status"] = "running"
    else:
        state["status"] = "awaiting_real_whitelist_tenants"
    _save_state(state_path, state)
    print(str(report_path))
    if int(state.get("days_observed") or 0) >= 7:
        return _run_verdict(app, state_path=state_path, verdict_path=verdict_path)
    return 0


def _record_incident(*, state_path: Path, set_incident: bool, clear_incident: bool, note: str) -> int:
    state = _load_state(state_path)
    if set_incident:
        state["rollback_incident_detected"] = True
        notes = list(state.get("rollback_incident_notes") or [])
        if note:
            notes.append({"noted_at": _iso_now(), "note": note})
        state["rollback_incident_notes"] = notes
    elif clear_incident:
        state["rollback_incident_detected"] = False
        if note:
            state["rollback_incident_notes"] = [{"noted_at": _iso_now(), "note": f"cleared: {note}"}]
    _save_state(state_path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    args = _parse_args()
    state_path = Path(getattr(args, "state_file", str(DEFAULT_STATE_PATH)))
    app = create_app()
    with app.app_context():
        if args.command == "start":
            return _start_cycle(
                app,
                state_path=state_path,
                tenants=list(args.tenants or []),
                started_at=str(args.started_at or "").strip(),
            )
        if args.command == "daily":
            return _run_daily(
                app,
                state_path=state_path,
                daily_dir=Path(args.daily_dir),
                verdict_path=Path(args.verdict_path),
                report_date=str(args.date or "").strip(),
            )
        if args.command == "verdict":
            return _run_verdict(app, state_path=state_path, verdict_path=Path(args.verdict_path))
        if args.command == "incident":
            return _record_incident(
                state_path=state_path,
                set_incident=bool(args.set_incident),
                clear_incident=bool(args.clear_incident),
                note=str(args.note or "").strip(),
            )
        state = _load_state(state_path)
        print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
