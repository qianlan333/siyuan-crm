# AI-CRM Codex Autopilot Runtime Runbook

## Summary

This runbook describes the local/server runtime runner for the AI-CRM Codex autopilot loop. It turns the protocol from `docs/development/autonomous_development_loop.md` into a single tick command that can be called by cron, launchd, or systemd every 15 minutes.

## Architecture boundary

The runner is a local orchestration wrapper. It reads repository protocol files, checks for open autopilot PRs, chooses one bounded low-risk work package from `next_allowed_actions`, and writes a Codex prompt to `/tmp/aicrm_codex_next_prompt.md`. It does not implement business behavior inside Python and does not modify runtime code.

## Business value

The runner lets AI-CRM continue safe low-risk Phase 4 housekeeping without manual polling. It prevents action-templates from advancing past staging approval/config gaps while still preparing useful 20-35 minute compressed bundles instead of repeated tiny state-only updates.

## Business continuity

This PR only adds a local/server runner, shell wrapper, docs, and tests. It does not change production routes, `production_compat`, schema, migrations, deploy/nginx/systemd production configuration, legacy fallback, production data access, or external-call behavior.

## How To Run One Tick

```bash
AICRM_CODEX_COMMAND="codex" \
scripts/codex_autopilot_tick.sh
```

Logs are written under:

```text
logs/codex-autopilot/
```

The Codex command is configurable with `AICRM_CODEX_COMMAND`. The shell wrapper fetches latest `origin/main`, runs `tools/run_codex_autopilot_tick.py`, and invokes the configured Codex CLI only if a next prompt was generated.

## Runtime Gate Behavior

Each tick:

- Uses a single-flight lock under `logs/codex-autopilot/tick.lock`.
- Checks for open autopilot PRs.
- Exits if checks are pending.
- Allows only one bounded repair marker for failed checks.
- Exits if `owner-decision-required` or `automerge-blocked` labels exist.
- Reads `docs/development/phase_execution_state.yaml`.
- Selects only one bounded low-risk work package from `next_allowed_actions`.
- Reads `docs/development/autonomous_stop_conditions.yaml`.
- Generates an owner decision package instead of an implementation prompt when a stop condition appears.

Each compressed bundle should be completable in 20-35 minutes. A package may include adjacent safe stages that share one route family and risk boundary, plus state updates, checker/test coverage, and a concrete next action. State-only updates are allowed only when the PR explains why they cannot be merged into a fuller package.

## Auto-Merge Boundary

GitHub native auto-merge may be enabled when available. If native auto-merge is unavailable, the runner may use admin merge for eligible low-risk PRs.

Admin merge is allowed only when all are true:

- `tools/check_automerge_eligibility.py` reports `eligible=true`.
- Required GitHub checks are green.
- No stop condition is present.
- No owner decision package is required.
- The diff is limited to docs/tools/tests/checker/state files.
- The diff does not touch runtime, `production_compat`, business routes, schema/migrations, deploy/nginx/systemd, real external calls, or legacy fallback.

Owner-decision packages remain manual and must not be auto-merged.

## Safety / non-goals

The runner must not:

- switch production owner;
- write production;
- delete fallback;
- modify `production_compat`;
- modify business routes;
- modify schema/migration;
- modify real deploy/nginx/systemd production config;
- enable real WeCom, Payment, OAuth, OpenClaw, MCP, timer, automation execution, or outbound send.

## Verification

Run:

```bash
python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json
python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json
python3 -m pytest tests/test_autonomous_development_loop.py tests/test_automerge_eligibility.py tests/test_codex_autopilot_runtime_contract.py -q
python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json
python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json
git diff --check
```

## Risk / rollback

Risk is limited to local orchestration behavior or prompt generation. Rollback is to stop the scheduler and revert this PR. Production runtime paths and legacy fallback are unchanged.

## Autopilot runtime decision

The runtime runner is approved only as a local/server tick generator and low-risk PR steward. It may generate prompts, owner decision packages, and admin-merge eligible low-risk PRs after checks pass, but it does not authorize production route switch, production writes, fallback removal, or real external calls.

## Next action

Install a scheduler only after choosing the host and Codex CLI command. Keep Phase 4AM bounded to staging execution / approval config closure / blocked evidence review until owner approval/config is complete.
