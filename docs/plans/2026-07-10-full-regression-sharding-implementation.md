# Full Regression Sharding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve the complete Python/PostgreSQL regression while reducing representative PR and `main` full-CI wall-clock time from about 29 minutes to at most 14 minutes.

**Architecture:** Collect the actual pytest node IDs, group them by file, and deterministically bin-pack files into four duration-weighted shards using a validated JUnit baseline. Run those shards concurrently on isolated GitHub runners/PostgreSQL services, retain xdist inside each shard, and upload refreshed per-shard JUnit timing evidence.

**Tech Stack:** Python 3.10, pytest/pytest-xdist, PostgreSQL 16 service containers, GitHub Actions reusable workflows, PyYAML contract parsing.

---

### Task 1: Specify shard and workflow contracts

**Files:**
- Create: `tests/test_pytest_shard_selector.py`
- Create: `tests/test_pytest_duration_baseline_builder.py`
- Modify: `tests/test_ci_workflow_contract.py`

**Step 1: Write failing selector tests**

Cover deterministic assignment, exhaustive and mutually exclusive files, duration weighting, baseline validation, file preservation, invalid indexes, empty collection, and exact output-file contents.

**Step 2: Write failing workflow contracts**

Require a three-entry non-fail-fast matrix, isolated PostgreSQL per shard, the selector command, xdist/loadfile execution, JUnit upload, a 25-minute shard timeout, and one governance job that CI Fast may skip only because its existing jobs own those gates.

**Step 3: Prove RED**

Run:

```bash
python -m pytest tests/test_pytest_shard_selector.py tests/test_ci_workflow_contract.py -q --tb=short
```

Expected: selector import and new workflow assertions fail.

### Task 2: Implement the deterministic file-level selector

**Files:**
- Create: `scripts/ci/select_pytest_shard.py`
- Create: `scripts/ci/build_pytest_duration_baseline.py`
- Create: `docs/ci/pytest_duration_baseline.json`
- Test: `tests/test_pytest_shard_selector.py`

**Step 1: Add pure parsing and partition functions**

Parse only collected `tests/**/*.py::node` IDs, scale known file durations by current item count, use a suite-wide fallback for new files, sort by descending estimated duration/count/path, and greedily assign the next file to the shard with the lowest `(estimated_seconds, item_count, file_count, index)` tuple.

**Step 2: Add the fail-closed CLI**

Accept `--shard-index`, `--shard-total`, `--duration-baseline`, and `--output-file`; invoke `python -m pytest tests/ --collect-only -q --disable-warnings`; reject failed/empty collection, a malformed baseline, and an empty selected shard; atomically write one selected file per line; print a JSON count/duration summary.

**Step 3: Prove GREEN**

Run the selector/baseline unit tests and invoke all four shards against the real repository collection. Verify that selected file sets are disjoint, their union equals all collected test files, selected item counts sum to the collected total, and estimated durations are near-equal.

### Task 3: Parallelize Full Regression without removing gates

**Files:**
- Modify: `.github/workflows/full-regression.yml`
- Modify: `.github/workflows/ci-fast.yml`
- Test: `tests/test_ci_workflow_contract.py`

**Step 1: Split governance from pytest**

Create one `full-governance` job for direct/nightly runs. Add a boolean `workflow_call` input and have CI Fast pass `run_governance: false`, because its `architecture-gates` and `dependency-audit` jobs remain required.

**Step 2: Add four Python shards**

Use a static include matrix for indexes 0 through 3 with `fail-fast: false` and `max-parallel: 4`. Give every shard its own PostgreSQL service, select files at runtime, run pytest with `-n auto --dist=loadfile`, and upload JUnit timing artifacts even on failure.

**Step 3: Verify contracts and YAML**

Run:

```bash
python -m pytest tests/test_pytest_shard_selector.py tests/test_ci_workflow_contract.py -q --tb=short
python -c 'import pathlib,yaml; [yaml.safe_load(pathlib.Path(p).read_text()) for p in [".github/workflows/ci-fast.yml", ".github/workflows/full-regression.yml"]]'
```

Expected: all tests pass and both workflows parse.

### Task 4: Verify and publish measurable evidence

**Files:**
- Modify only if evidence requires correction: selector, workflows, tests, and these plan documents.

**Step 1: Run local gates**

Run CI/workflow tests, selector real-collection validation, full architecture gates, `git diff --check`, and a secret/diff audit.

**Step 2: Publish an isolated PR**

Commit only CI optimization files, push `codex/ci-full-regression-shards`, and create a Chinese PR with architecture, safety, verification, risk/rollback, and explicit no-product-capability scope.

**Step 3: Benchmark the PR**

Wait for every check. Acceptance requires all four shard item counts to sum to the full collection, every shard to pass, and CI Fast wall-clock time at or below 14 minutes. If skew or timeout violates the target, rebuild the checked-in duration baseline from JUnit artifacts and rebalance before merge.

**Step 4: Benchmark `main` and resume the Epic**

Merge only after explicit success, verify the resulting `main` run against the same target, then update PR #77 onto optimized `main`, rerun its checks, and resume Epic #67.
