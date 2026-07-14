# Issue #135 R12-J Send Content Media Gateway

## Goal

Remove the direct `send_content -> media_library` repository import without changing material behavior.

## Implementation

1. Add a package-root composition gateway that builds the canonical Media Library PostgreSQL repository.
2. Point Send Content's PostgreSQL adapter at the gateway; keep all list, lookup, usage, SQL, and error semantics unchanged.
3. Add gateway identity coverage and permanent full-CI selector coverage.
4. Shrink the import-graph baseline by one edge and one cyclic context.

## Verification

- Material Picker, usage, and table-boundary tests pass.
- Import graph reports 186 edges and 16 cyclic contexts with `send_content` outside the SCC.
- Full architecture gates and complete PostgreSQL CI pass.
