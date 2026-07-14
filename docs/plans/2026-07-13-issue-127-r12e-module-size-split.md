# Issue #127 R12-E Runtime Module Size Governance

## Goal

Create a shrinking line-count budget for runtime Python modules and split the first three oversized files without behavior changes.

## Plan

1. Add a 1500-line runtime module scanner and an allowlist that rejects new oversized files, growth, missing files, and stale entries.
2. Keep SQL implementations and command/query services on their existing import modules so monkeypatch and public import seams remain stable.
3. Move Internal Event support/in-memory persistence into focused modules.
4. Move Questionnaire support/in-memory persistence into focused modules.
5. Move Admin Config constants and validation helpers into a support module.
6. Remove all three files from the oversized baseline and lock selector coverage to full PostgreSQL CI.

## Verification

- Size guard unit and checked-tree tests.
- Stable facade import contract tests.
- Internal Event, Questionnaire, and Admin Config directed regressions.
- Full architecture gates and CI.
