# Issue #131 R12-G Final Runtime Module Size Split

## Goal

Remove the final four runtime Python modules from the shrinking 1500-line allowlist without changing business behavior.

## Implementation

1. Split Cloud legacy PostgreSQL methods and the in-memory repository while keeping the public repository classes on the original facade.
2. Split AI Audience package/version persistence into an existing-class mixin; keep the SQLAlchemy repository class on the original module.
3. Split Group Ops row mapping and SQL helper methods into a mixin; keep engine and transaction methods unchanged.
4. Split Commerce payload/header/page-context helpers while keeping every route and handler seam in `commerce.api`.
5. Extend facade identity contracts and clear the runtime module-size allowlist.

## Verification

- Runtime module-size guard reports zero oversized modules.
- Cloud, AI Audience, Group Ops, and Commerce contract suites pass.
- Repository ownership, DB boundary, runtime inventory, and full architecture gates pass.
- The GitHub selector requires full PostgreSQL CI with no unmatched changed files.
