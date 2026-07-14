# Issue #132 R12-H Admin Jobs Archive Sync Gateway

## Goal

Remove the direct `admin_jobs -> message_archive` import while preserving the disabled-by-default archive-sync control-plane behavior.

## Implementation

1. Add a package-root gateway that composes Admin Jobs with the existing Message Archive runner.
2. Point `admin_jobs.application` at the gateway without changing request parameters, result payloads, audit behavior, or the production execution gate.
3. Add a gateway contract test and permanent full-CI selector coverage.
4. Shrink the import-graph baseline by one edge and one cyclic context.

## Verification

- Admin Jobs and archive-sync contract tests pass.
- Import graph reports 188 real context edges and 18 cyclic contexts with `message_archive` outside the SCC; package-root composition modules are excluded consistently as non-contexts.
- Full architecture gates and complete PostgreSQL CI pass.
