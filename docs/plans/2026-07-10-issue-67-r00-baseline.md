# Issue 67 R00 Executable Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the current AI-CRM behavior and full regression reproducible so later Issue #67 refactors cannot silently change routes, contracts, runtime units, tables, jobs, effects, flags, or high-risk behavior.

**Architecture:** Generate a deterministic inventory from the real FastAPI composition root plus existing table, effect, worker, and systemd manifests. Add a checked-in snapshot and drift checker, map high-risk domains to success/failure/replay tests, and make `needs_full_ci` invoke a reusable full-regression workflow whose result is required by `CI Fast`.

**Tech Stack:** Python 3.10, FastAPI/OpenAPI, PyYAML, pytest, PostgreSQL 16, GitHub Actions, JSON/YAML governance manifests.

---

### Task 1: Freeze and classify the current baseline

**Files:**
- Modify: `docs/cleanup/full_pytest_baseline_failure_classification.md`
- Create: `docs/architecture/high_risk_contract_inventory.yml`

**Step 1: Capture the current complete regression**

Run the target repository `Full Regression` workflow for the exact baseline SHA and retain the run URL and job results.

**Step 2: Classify every failure**

Record each failure as `代码缺陷`, `测试过期`, `环境缺失`, or `能力已退休`. Do not delete or weaken assertions. If there are no current failures, explicitly reconcile the prior 34-failure Epic baseline with the commits/runs that closed them.

**Step 3: Define high-risk golden contracts**

For each of `auth`, `callback`, `payment`, `refund_entitlement`, `questionnaire`, `group_ops`, and `delivery`, list one existing success node ID, one failure node ID, and one replay/concurrency node ID. Include owner, CI scope, and real-external-call expectation.

**Step 4: Verify selected nodes**

Run each node ID with PostgreSQL test settings and prove no real provider call occurs.

### Task 2: Add the deterministic runtime-contract inventory

**Files:**
- Create: `scripts/ci/runtime_contract_inventory.py`
- Create: `docs/architecture/runtime_contract_inventory.json`
- Create: `tests/test_runtime_contract_inventory.py`
- Modify: `aicrm_next/router_registry.py` only if a stable public summary is required

**Step 1: Write failing inventory tests**

Test that generation includes schema version, source SHA-independent content, route/page OpenAPI contracts, the current Alembic head, table ownership/lifecycle, internal-event consumers, external effects, runtime units, and AST-discovered environment variables. Test stable ordering and fixture labelling.

Run: `python -m pytest tests/test_runtime_contract_inventory.py -q`

Expected: FAIL because the generator and snapshot do not exist.

**Step 2: Implement generation**

Build the real application without production data access, derive OpenAPI operations and router ownership, parse existing governance manifests, inspect the internal-event consumer registry, parse `deploy/production_runtime_units.json`, and AST-scan runtime/deploy Python for literal environment-variable reads. Serialize normalized JSON with sorted keys and stable lists.

**Step 3: Add drift check**

Support `--write <path>` and `--check <path>`. `--check` prints a unified diff and exits non-zero on drift.

**Step 4: Generate and verify**

Run:

```bash
python scripts/ci/runtime_contract_inventory.py --write docs/architecture/runtime_contract_inventory.json
python scripts/ci/runtime_contract_inventory.py --check docs/architecture/runtime_contract_inventory.json
python -m pytest tests/test_runtime_contract_inventory.py -q
```

Expected: all commands succeed and a second generation leaves `git diff` unchanged.

### Task 3: Make high-risk contract coverage executable

**Files:**
- Create: `scripts/ci/check_high_risk_contract_inventory.py`
- Create: `tests/test_high_risk_contract_inventory.py`
- Modify: `docs/ci/test_scope_manifest.yml`

**Step 1: Write failing checker tests**

Cover missing domain, missing success/failure/replay case, nonexistent pytest node, duplicate node, missing CI scope, and unsafe `real_external_call_expected=true`.

**Step 2: Implement the checker**

Parse the manifest, discover pytest functions without executing imports, and ensure each node exists and is selected by the named scope. Reject incomplete domain coverage and unapproved real-call expectations.

**Step 3: Verify negative and positive cases**

Run: `python -m pytest tests/test_high_risk_contract_inventory.py -q`

Expected: all positive and deliberate-drift tests pass.

### Task 4: Make full regression a required high-risk CI result

**Files:**
- Modify: `.github/workflows/full-regression.yml`
- Modify: `.github/workflows/ci-fast.yml`
- Modify: `tests/test_ci_workflow_contract.py`
- Modify: `tests/test_select_test_scope.py`

**Step 1: Write failing workflow contract tests**

Assert `Full Regression` supports `workflow_call`, `CI Fast` invokes it only when `needs_full_ci == 'true'`, and `ci-fast-result` requires the reusable workflow result. Assert callback, payment, refund, adapter, migration, deployment, and contract-inventory paths set `needs_full_ci=true`.

**Step 2: Make Full Regression reusable**

Add `workflow_call` without removing manual or nightly triggers. Keep PostgreSQL, architecture, full pytest, frontend build, and frontend tests identical for all callers.

**Step 3: Require it from CI Fast**

Add a conditional reusable-workflow job and include it in `ci-fast-result.needs`. A failed/cancelled full regression must fail the required result; a skipped job is allowed only when selector output is false.

**Step 4: Verify workflow contracts**

Run:

```bash
python -m pytest tests/test_ci_workflow_contract.py tests/test_select_test_scope.py -q
```

Expected: all tests pass.

### Task 5: Install the baseline gates

**Files:**
- Modify: `scripts/ci/run_architecture_gates.sh`
- Modify: `docs/ci/test_scope_manifest.yml`
- Modify: `tests/test_architecture_boundaries.py` if gate enumeration is asserted

**Step 1: Add inventory checks to full architecture mode**

Run the runtime-contract drift checker and high-risk-contract checker in `full` mode. Ensure edits to their scripts/manifests/snapshot select the CI/deploy scope and force full regression.

**Step 2: Verify all architecture modes**

Run:

```bash
bash scripts/ci/run_architecture_gates.sh --mode fast
bash scripts/ci/run_architecture_gates.sh --mode db
bash scripts/ci/run_architecture_gates.sh --mode full
```

Expected: all pass.

### Task 6: Complete R00 validation and publication

**Files:**
- Modify only files authorized by Issue #67 R00.

**Step 1: Run focused suites**

Run the inventory, CI workflow, selector, router registry, Alembic revision-chain, background job, and external-effect contract tests.

**Step 2: Run full local regression**

Run:

```bash
DATABASE_URL=postgresql://test:test@localhost:5432/test AICRM_PYTEST_FIXTURE_DEFAULT=1 python -m pytest tests/ -n auto --dist=loadfile -v --tb=short --timeout=120 --timeout-method=thread
npm ci
npm run typecheck
npm run build:frontend
git diff --exit-code
npm run test:frontend:all
```

Expected: zero failures and no generated drift.

**Step 3: Publish one R00 PR**

Use the Issue #67 PR template fields, link the R00 child issue, and include architecture boundary, safety/non-goals, verification, risk/rollback, and next action. Wait for scoped and forced full CI.

**Step 4: Merge and verify**

Merge only after all required checks pass. Verify target `main`, deployment workflow, server release SHA, `/health`, and callback ingress health. R00 does not close until generated inventory and the post-merge full run are both green.
