# AI-CRM Codex Autopilot Development Loop

## Purpose

This protocol defines a bounded Codex autopilot loop for AI-CRM. The loop may inspect repository state every 15 minutes, choose one bounded low-risk work package, open a PR, and allow low-risk admin merge only when the auto-merge eligibility gate passes and GitHub required checks pass.

The protocol does not authorize production owner switch, fallback removal, production write, real external calls, destructive migrations, deploy config changes, or canary approval.

## Business value

This gives future Codex runs a repeatable protocol for advancing useful low-risk Phase 4 work without waiting on manual orchestration for every docs/checker/test handoff. It keeps action-templates in staging-approval wait while discouraging tiny state-only churn and steering the next package toward staging approval/config closure or an owner decision package.

## Business continuity

This protocol does not change runtime behavior. It does not modify production routes, `production_compat`, deploy config, schema, migrations, or legacy fallback ownership. When a stop condition is detected, autonomous work stops and only an owner decision package may be produced.

## Risk / rollback

Risk is limited to protocol/checker misclassification. Rollback is to revert this PR and return to manual Phase 4 execution. Runtime production traffic remains on the existing owner paths.

## Next action

Future Codex loops may run the autonomous development checker and auto-merge eligibility checker before selecting a low-risk work package. Action-templates remains limited to Phase 4AM staging execution / approval config closure / blocked evidence review until owner approval/config is complete.

## Required Preflight

Every autopilot iteration must read and follow:

- `docs/development/ai_crm_next_architecture_skill.md`
- `skills/ai-crm-next-architecture/SKILL.md`
- `docs/development/phase_execution_state.yaml`
- `docs/development/autonomous_stop_conditions.yaml`

## Loop Cadence

The loop may run every 15 minutes. Each run must:

1. Fetch latest `origin/main`.
2. Read `phase_execution_state.yaml`.
3. Select only one bounded low-risk work package from `next_allowed_actions`.
4. Stop if the selected action or current diff matches any stop condition.
5. Create a PR only for low-risk docs/checker/test/protocol work.
6. Run task-specific checkers and `tools/check_automerge_eligibility.py`.
7. Allow low-risk admin merge only when GitHub required checks are green, the eligibility gate says `eligible: true`, no stop condition exists, and the diff remains docs/tools/tests/checker/state only.

## Low-Risk Autopilot Actions

Low-risk work packages are limited to:

- Docs/YAML planning or handoff updates.
- Checker/test additions for existing planning gates.
- Blocked evidence review summaries folded into a broader closure package.
- Owner decision package creation.
- Narrow allowlist maintenance in prior checker files.

Each package should target 10-13 minutes of focused work. It should be small enough to verify quickly, but large enough to avoid one- or two-line state-only churn. If a state-only PR is unavoidable, the PR body must explain why the state update could not be folded into a fuller low-risk work package.

## High-Risk Stop Behavior

When a high-risk stop condition appears, Codex must stop autonomous execution and generate only an owner decision package. It must not auto-merge.

High-risk stop examples:

- Production route owner switch.
- Fallback removal.
- Production write.
- Real external call.
- Timer or automation execution.
- Outbound send.
- Deploy config.
- Destructive migration.
- `delete_ready`.
- Canary approval.

## Current Action-Templates State

`/api/admin/automation-conversion/action-templates*` is waiting for staging approval/config. The current allowed next actions are limited to Phase 4AM staging execution / approval config closure / blocked evidence review. Production owner switch, production write, fallback removal, and production route enablement are not ready.

If PR #641 has merged, autopilot must not repeat a standalone blocked evidence review. The next action-templates package should be either:

- Phase 4AM staging approval/config closure package; or
- an owner decision package if approval/config cannot be closed autonomously.

The package may combine blocked evidence summary, staging approval/config checklist, owner approval closure form, `phase_execution_state.yaml` updates, checker/test coverage, and a concrete Next action. It must still avoid staging smoke execution unless approval/config is satisfied.

## Auto-Merge Rule

Low-risk admin merge is allowed only when all are true:

- The diff is low-risk.
- The PR body includes Business value, Business continuity, Risk / rollback, and Next action.
- `tools/check_autonomous_development_loop.py` passes.
- `tools/check_automerge_eligibility.py` passes with `eligible: true`.
- GitHub required checks pass.
- No stop condition is touched.
- No unauthorized production readiness claim appears.
- The diff contains only docs/tools/tests/checker/state files.
- The diff does not modify runtime, `production_compat`, business routes, schema/migrations, deploy/nginx/systemd, real external call paths, or legacy fallback.

If GitHub native auto-merge is available, it may be enabled. If native auto-merge is unavailable, Codex autopilot may use admin merge for eligible low-risk PRs after required checks are green. If any condition fails, auto-merge is forbidden and Codex must output a blocked status or owner decision package.
