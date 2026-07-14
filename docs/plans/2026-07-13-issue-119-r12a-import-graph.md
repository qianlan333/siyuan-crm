# Issue #119 — R12-A Import Graph / SCC Guard

## Objective

Turn the current cross-context import graph into a deterministic CI contract before changing module boundaries. This slice adds governance only; it does not change runtime behavior.

## Baseline

- Base: `main@b3b5f80bab7f775dd014bf45596dd67493c2b47f`
- Runtime contexts: 40
- Cross-context edges: 194
- Cyclic components: 1
- Contexts in the existing cyclic component: 26

## Implementation sequence

1. Add failing scanner tests for absolute, relative, function-local, type-only, and dynamic imports.
2. Add SCC contract tests for the existing baseline, shrink/split progress, expansion, and new cycles.
3. Implement deterministic AST scanning, evidence collection, Tarjan SCC calculation, baseline validation, and CLI output.
4. Register the current cyclic component with owner, reason, and removal date.
5. Run the guard in the fast architecture gate and ensure every runtime Python change selects at least that gate.
6. Run directed tests, the repository guard, the full architecture gate, and full CI before merge.

## Safety and rollback

- No business routes, schemas, repositories, templates, or external calls change.
- Non-literal dynamic imports fail closed rather than disappearing from the graph.
- Reverting this PR removes only the governance contract.

## Follow-up boundary

R12-B will move registry, executor, and fixture lifecycle into the app composition root. Later R12 slices will remove reverse imports and split all runtime Python files above 1500 lines using this graph as the non-regression guard.
