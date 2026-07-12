# Full Regression Sharding Design

## Context and target

The current high-risk CI path runs on both pull requests and `main`. A representative `main` run took 28m48s; its full Python job took 28m25s and the pytest step alone took 26m02s for 2,895 tests. Dependency installation, security audit, architecture checks, and frontend regression all finished in roughly two minutes or less. GitHub supplied four xdist workers, while every test also pays the PostgreSQL isolation cost of resetting the repository schema. The bottleneck is therefore the single-runner Python regression, not dependency caching.

The target is to preserve every collected test and every PostgreSQL isolation boundary while reducing the full-regression wall-clock time to 14 minutes or less on a representative Actions run. The trade-off is explicit: four runner setups increase billed runner minutes, while the dominant testcase work remains unchanged and delivery wall-clock time drops by more than half. Any shard failure must fail the reusable workflow and the required `ci-fast-result` check.

## Chosen design

Use four parallel, file-preserving pytest shards. Each shard gets its own GitHub runner and PostgreSQL service, then uses the existing four xdist workers internally. A repository-owned selector collects the real pytest node IDs and applies deterministic greedy bin packing with a checked-in, per-file duration baseline. Keeping a file wholly inside one shard preserves module-scoped fixtures and the existing `--dist=loadfile` behavior. New or changed files scale their recorded per-item duration or fall back to the suite-wide seconds-per-item value.

The first three-way item-count benchmark proved why timing evidence is required: all groups contained exactly 969 items, but their accumulated testcase time was approximately 4,508s, 2,238s, and 2,318s, producing jobs of 20m44s, 11m36s, and 11m52s. JUnit run `29104632060` is therefore the versioned source for the initial baseline. Repacking that evidence into four groups yields approximately 2,266 accumulated testcase seconds per group and a projected 11-minute job including setup.

Each shard uploads JUnit timing data and prints selected/total item counts plus estimated duration. A validated baseline builder makes later refreshes reproducible. Contract and unit tests prove that assignments are deterministic, mutually exclusive, exhaustive, timing-balanced, and fail closed on invalid/empty collection or a malformed baseline. Governance checks remain mandatory: direct/nightly Full Regression runs execute them once, while CI Fast passes `run_governance: false` because its existing architecture and dependency-audit jobs already execute the same gates. No test, security audit, frontend check, or deployment prerequisite is removed.

## Alternatives rejected

- A larger hosted runner reduces code change but adds recurring cost and vendor-plan dependency.
- Hashing individual node IDs balances well but splits files across jobs and can change module-fixture behavior.
- Reusing PR results or skipping the `main` full run offers the largest saving, but is unsafe until required checks, up-to-date merges, and branch protection or merge queue are enforced.

## Safety and rollback

Capability owner is CI governance. No product route, external call, production data, runtime configuration, or fixture data is changed. The only PostgreSQL instances are ephemeral Actions service containers. Rollback is a revert to the previous single `full-python` job. If the first real run exceeds 14 minutes or shows a material shard skew, use the uploaded JUnit data to tune weights before merge rather than reducing coverage.
