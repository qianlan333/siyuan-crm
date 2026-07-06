from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_CLOSEOUT = ROOT / "docs/reports/p1_group_ops_workspace_final_closeout_20260624.md"


def _report() -> str:
    return FINAL_CLOSEOUT.read_text(encoding="utf-8")


def test_p1_group_ops_workspace_final_closeout_report_exists_and_has_verdicts() -> None:
    report = _report()

    for expected in [
        "P1_GROUP_OPS_WORKSPACE_READY_FOR_INTERNAL_GRAY",
        "DRAFT_PERSISTENCE_READY",
        "GOVERNANCE_WORKFLOW_READY",
        "PUSH_CENTER_PENDING_BRIDGE_READY",
        "EXECUTION_NOT_IN_SCOPE",
        "EXTERNAL_EFFECT_EXECUTION_NOT_IN_SCOPE",
        "PASS_90_PLUS_NOT_CLAIMED",
        "internal gray usage",
        "operator dry-run",
    ]:
        assert expected in report


def test_p1_group_ops_workspace_final_closeout_capability_and_boundary_contract() -> None:
    report = _report()

    for expected in [
        "## Capability Matrix",
        "### Read-only Workspace",
        "### Draft Persistence",
        "### Request-review",
        "### Governance",
        "### Push Center Bridge",
        "#1369",
        "#1370",
        "#1372",
        "#1374",
        "#1375",
        "#1376",
        "#1377",
        "#1379",
        "#1380",
        "#1381",
        "#1382",
        "#1384",
        "#1387",
        "#1388",
        "#1389",
        "#1391",
        "#1394",
        "#1399",
        "#1402",
        "#1404",
        "#1406",
        "#1408",
        "#1411",
        "#1413",
        "/admin/p1/group-ops-workspace",
        "/admin/automation-conversion/group-ops/ui",
        "draft/audit tables",
        "governance tables/metadata",
        "pending bridge metadata/projection",
        "No external effect execution.",
        "No real external call.",
        "No WeCom send.",
        "No webhook send.",
        "No message-send call.",
    ]:
        assert expected in report


def test_p1_group_ops_workspace_final_closeout_guardrails_and_sensitive_boundary() -> None:
    report = _report()

    for expected in [
        "preview_only",
        "draft is not sent/completed",
        "`ready_for_review` is not approved",
        "`governance_approved` is not execution",
        "Push Center pending projection is not sent/completed",
        "external_effect_job_created=false",
        "broadcast_job_created=false",
        "internal_event_created=false",
        "real_external_call=false",
        "can_claim_pass_90_plus=false",
        "raw receiver",
        "raw `external_userid`",
        "phone / mobile",
        "raw chat/member id",
        "openid / unionid",
        "token / secret / `Authorization`",
        "raw target list",
        "raw message body",
        "raw callback body",
        "sanitized summary",
        "hash",
        "count",
        "audit metadata",
    ]:
        assert expected in report


def test_p1_group_ops_workspace_final_closeout_validation_and_production_status() -> None:
    report = _report()

    for expected in [
        "npm run build:frontend",
        "npm run typecheck",
        "npm run test:frontend",
        ".venv/bin/python -m pytest tests/test_group_ops_frontend_contract.py -q",
        ".venv/bin/python -m pytest tests/test_p1_group_ops_workspace_frontend_contract.py -q",
        ".venv/bin/python -m pytest tests/test_group_ops_workspace_draft_migration.py -q",
        ".venv/bin/python -m pytest tests/test_p1_group_ops_workspace_draft_api.py -q",
        ".venv/bin/python -m pytest tests/test_group_ops_workspace_governance_migration.py -q",
        ".venv/bin/python -m pytest tests/test_p1_group_ops_workspace_governance_api.py -q",
        ".venv/bin/python -m pytest tests/test_p1_group_ops_workspace_bridge_hardening.py -q",
        ".venv/bin/python -m pytest tests/test_alembic_revision_chain.py -q",
        ".venv/bin/python scripts/diagnose_p1_group_ops_workspace_bridge_acceptance.py",
        ".venv/bin/python scripts/diagnose_business_closure_acceptance.py --scenario all",
        "bash scripts/ci/run_architecture_gates.sh",
        "git diff --check",
        "dry-run / read-only",
        "SKIPPED_WRITE_VALIDATION_SAFE_MODE",
        "Local PG write validation is skipped safely",
        "CI/PG environment is expected to cover integration contracts",
    ]:
        assert expected in report


def test_p1_group_ops_workspace_final_closeout_limitations_rollback_acceptance() -> None:
    report = _report()

    for expected in [
        "## Known Limitations",
        "No real sending is included",
        "No external effect execution is included",
        "No sent/completed state is accepted as a final execution result",
        "Push Center pending projection is not a real send task completion",
        "Bridge metadata is not outbound-call evidence",
        "legacy Group Ops remains the daily operations entry",
        "## Rollback / Cleanup",
        "No external effect rollback is required",
        "No outbound message rollback is required",
        "## Acceptance Criteria",
        "internal gray usage",
        "production dry-run validation",
        "operator training",
        "later Push Center real execution design",
        "automatic external effect execution",
        "direct WeCom send",
        "direct webhook send",
        "direct message send",
        "## Frontend Skill Checklist",
        "是否新增组件: 否",
        "P1 workspace 页面不变",
        "legacy Group Ops 页面不变",
    ]:
        assert expected in report


def test_p1_group_ops_workspace_final_closeout_does_not_claim_execution_or_global_pass() -> None:
    report = _report()
    normalized = report
    for allowed in [
        "PASS_90_PLUS_NOT_CLAIMED",
        "can_claim_pass_90_plus=false",
        "global 90-plus pass",
        "global 90-plus pass remains out of scope",
        "No global 90-plus pass is claimed.",
    ]:
        normalized = normalized.replace(allowed, "")

    forbidden_patterns = [
        r"Final verdict:\s*`?PASS_90_PLUS`?",
        r"Executive verdict:\s*`?PASS_90_PLUS`?",
        r"\bPASS_90_PLUS\b",
        r"已发送",
        r"已完成真实外呼",
        r"real external call completed",
        r"external_effect_job_created=true",
        r"broadcast_job_created=true",
        r"internal_event_created=true",
        r"execution_status=sent",
        r"execution_status=completed",
        r"push_center_status=sent",
        r"sent/completed state is claimed",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, normalized, flags=re.IGNORECASE) is None, pattern
