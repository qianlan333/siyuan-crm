# AI-CRM Cleanup Batch Status

Updated: 2026-06-29

This status ledger records the cleanup plan after the first hygiene batches. It
is intentionally scoped to repository hygiene, documentation, generated reports,
and read-only checks. It does not authorize runtime behavior changes, deploy
changes, production access, or external calls.

## Current State

| batch | status | evidence | next action |
|---|---|---|---|
| Batch 0 repo hygiene audit | done | `tools/audit_repo_hygiene.py`, `tests/test_repo_hygiene_audit.py`, `docs/cleanup/repo_hygiene_report.md`, `docs/cleanup/repo_hygiene_report.json` | Keep report-only; do not promote findings to CI fail without explicit approval. |
| Batch 1 agent entry docs and safety wording | done | `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/development/ai_crm_next_architecture_skill.md`, `skills/ai-crm-next-architecture/SKILL.md` | Keep production connection details outside the public repo entry docs. |
| Batch 2 lint and hygiene guard expansion | done | `scripts/run_lint.py`, `docs/cleanup/route_inventory_consolidation_inventory.md`, `docs/cleanup/route_inventory_consolidation_inventory.json`, `tools/report_route_inventory_consolidation.py`, `docs/archive/route_inventory/` | Continue with report-backed cleanup; the first 5 manifest-derivable route inventories are archived while tests still validate their closeout evidence. |
| Route inventory parser and archive expansion | done | `tools/report_route_inventory_consolidation.py`, `tests/test_route_inventory_consolidation_report.py`, `docs/archive/route_inventory/customer_automation_webhook_route_inventory.md`, `docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md` | Method-prefixed route refs, query strings, and FastAPI typed path params are normalized before classification; active hand-written route inventories are down to 17. |
| Batch 3 experiment workspace inventory | done | `tools/report_experiments_inventory.py`, `tests/test_experiments_inventory_report.py`, `docs/cleanup/experiments_ai_crm_next_inventory.md`, `docs/cleanup/experiments_ai_crm_next_inventory.json`, `tests/test_retired_automation_artifacts_cleanup.py`, `docs/archive/experiments_ai_crm_next/retired_tools.md`, `docs/archive/experiments_ai_crm_next/docs/remaining_work_queue.md`, `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md`, `docs/archive/experiments_ai_crm_next/docs/real_readonly_http_dual_run.md`, `docs/archive/experiments_ai_crm_next/docs/module_status_matrix.md`, `docs/archive/experiments_ai_crm_next/docs/frontend_route_manifest.md`, `docs/archive/experiments_ai_crm_next/docs/customer_read_model_route_cutover_manifest.md`, `docs/archive/experiments_ai_crm_next/workspace/` | Canary/readiness helpers, local evidence helpers, paired tests, historical planning/status docs, route/parity strategy docs, and the final experiment-local workspace scaffold are archived; active `experiments/ai_crm_next` is now a README stub watched by the duplicate-source guard. |
| Retired production_compat package shell | done | `aicrm_next/production_compat/`, `tests/test_next_source_consolidation.py`, `docs/development/phase_execution_state.yaml`, `docs/development/autonomous_stop_conditions.yaml` | Empty package shell deleted; governance guards now protect the deleted package path from returning. |
| Batch 4 Flask retirement | done | `tests/test_shared_flask_config_retirement.py`, `tests/test_wechat_oauth_client.py` | Keep `from flask`, `import flask`, and `current_app` out of runtime code. |
| Batch 5 fixture reset registry | done | `aicrm_next/fixture_reset_registry.py`, `tests/test_fixture_reset_registry.py` | Preserve reset order and keep router registration behavior unchanged. |
| Deprecated CLI noise | done | `app.py`, `tests/test_startup_entrypoint_next_only.py` | Keep removed-command errors table-driven until the CLI contract is formally deleted. |
| Active legacy path reference guard | done | `tools/audit_repo_hygiene.py`, `tests/test_repo_hygiene_audit.py`, `skills/image-library-curator/README.md`, `docs/queue/broadcast-jobs.md`, `docs/user_ops_v2.md` | Keep active docs from pointing contributors at retired `wecom_ability_service/`, `openclaw_service/`, or legacy OpenClaw source paths. |
| Tracked artifact policy | clean | `python3 tools/audit_repo_hygiene.py` reports zero issues and no tracked `artifacts/`, `.codex_artifacts/`, `tmp/`, `outputs/`, `dist/`, or `exports/` files are present. | Keep generated evidence under `docs/reports/`, `docs/archive/`, or `docs/cleanup/` only when intentionally reviewable. |

## Verified Boundaries

- No `aicrm_next/` runtime business logic is changed by this status document.
- No deploy/nginx/systemd files are changed.
- No production host, SSH alias, or command cookbook is reintroduced.
- No external WeCom, Payment, OAuth, OpenClaw, webhook, or MCP call is executed.
- Real WeCom External Effect execution remains limited to the approved PR #1505
  scope; Webhook, Payment, OAuth, OpenClaw, and MCP real execution remain blocked
  until separately approved with audit, idempotency, and rollback coverage.

## Useful Commands

```bash
python3 tools/audit_repo_hygiene.py
python3 tools/report_experiments_inventory.py \
  --summary-output docs/cleanup/experiments_ai_crm_next_inventory.md \
  --json-output docs/cleanup/experiments_ai_crm_next_inventory.json
python3 tools/report_route_inventory_consolidation.py \
  --summary-output docs/cleanup/route_inventory_consolidation_inventory.md \
  --json-output docs/cleanup/route_inventory_consolidation_inventory.json
```

## Recommended Next Batch

Do not reintroduce an active `experiments/ai_crm_next` test/runtime workspace.
The next safe batches are archive-retention cleanup only: review whether
generated or duplicate evidence under `docs/archive/experiments_ai_crm_next/`
can be consolidated, continue route-inventory consolidation only for files that
the generated report proves are manifest-derivable, and keep active docs free of
retired live-source pointers.
