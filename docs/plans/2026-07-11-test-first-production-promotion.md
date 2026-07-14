# Test-First Production Promotion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every automatic release deploy only to `49.232.57.128`, while production `150.158.82.186` can only receive an explicitly approved manual promotion of a test-verified SHA.

**Architecture:** Keep the existing exact-SHA bundle deployment as the implementation core, but split its entrypoints by environment. The automatic workflow uses repository-scoped `TEST_DEPLOY_*` secrets and test-domain verification; a new manual workflow uses only production environment secrets, an explicit confirmation input, a test-SHA preflight, and required environment approval.

**Tech Stack:** GitHub Actions YAML, appleboy SCP/SSH actions, Bash, pytest workflow-contract tests, GitHub Environments.

---

### Task 1: Lock the environment separation contract

**Files:**
- Modify: `tests/test_ci_workflow_contract.py`
- Modify: `tests/test_deploy_workflow_contract.py`

**Step 1: Write failing workflow tests**

Add assertions that the automatic workflow is named `Deploy to Test`, only uses `TEST_DEPLOY_*`, verifies `id-dev.youcangogogo.com`, and cannot invoke the production route mutator. Add assertions that the production workflow is `workflow_dispatch` only, requires `release_sha` plus an exact confirmation string, uses the `production` environment, verifies the test SHA before transfer, and has no automatic trigger.

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_ci_workflow_contract.py tests/test_deploy_workflow_contract.py`

Expected: failures for missing manual workflow and the old automatic production contract.

### Task 2: Convert the automatic workflow to test-only

**Files:**
- Modify: `.github/workflows/deploy.yml`

**Step 1: Rename and re-scope the workflow**

Keep the successful-main `workflow_run` trigger, rename it to `Deploy to Test`, and replace all generic deploy secrets with `TEST_DEPLOY_HOST`, `TEST_DEPLOY_USER`, and `TEST_DEPLOY_SSH_KEY`.

**Step 2: Replace production public-route mutation**

Remove `ensure_production_public_release_route.py --execute` from the automatic workflow. Add a bounded public health poll for `https://id-dev.youcangogogo.com/health` that requires `x-aicrm-release-sha` to equal the verified SHA.

**Step 3: Run the focused tests**

Run: `.venv/bin/python -m pytest -q tests/test_ci_workflow_contract.py tests/test_deploy_workflow_contract.py`

Expected: automatic-test assertions pass; manual workflow assertions remain failing.

### Task 3: Add approved manual production promotion

**Files:**
- Create: `.github/workflows/promote-production.yml`

**Step 1: Add manual-only inputs and guards**

Use only `workflow_dispatch`, require a 40-character `release_sha`, require confirmation text `DEPLOY 150.158.82.186`, set `environment: production`, and use environment-scoped `DEPLOY_*` secrets.

**Step 2: Prove test verification before production transfer**

Checkout the requested SHA, prove it is an ancestor of current `origin/main`, then require `https://id-dev.youcangogogo.com/health` to advertise the same SHA before building or transferring the bundle.

**Step 3: Reuse the exact-SHA production deployment sequence**

Retain checksum, bundle, migration, secret reconciliation, service health, callback/runtime-unit verification, and production public-route exact-SHA enforcement.

**Step 4: Run the focused tests**

Run: `.venv/bin/python -m pytest -q tests/test_ci_workflow_contract.py tests/test_deploy_workflow_contract.py`

Expected: all focused tests pass.

### Task 4: Verify and publish

**Files:**
- Modify if needed: `docs/ci/test_scope_manifest.yml`

**Step 1: Verify formatting and workflow syntax**

Run: `git diff --check`

Run: `.venv/bin/python -c 'import pathlib, yaml; [yaml.safe_load(path.read_text()) for path in pathlib.Path(".github/workflows").glob("*.yml")]'`

Expected: zero errors.

**Step 2: Run architecture and selector gates**

Run: `bash scripts/ci/run_architecture_gates.sh --mode full`

Run: `.venv/bin/python scripts/ci/select_test_scope.py --github-output /tmp/test-first-deploy-scope.txt`

Expected: architecture gates pass and all changed files map to a CI scope.

**Step 3: Commit and open one PR**

Commit the workflow, tests, design, and plan on `codex/test-first-deploy-policy`; push and open a Chinese PR with safety and rollback details.

**Step 4: Merge and verify environments**

After required CI passes, merge the PR, re-enable `.github/workflows/deploy.yml`, and verify the automatic deployment updates 49 to the merge SHA while 150 remains unchanged. Keep `qianlan333/AI-CRM` production deploy disabled.
