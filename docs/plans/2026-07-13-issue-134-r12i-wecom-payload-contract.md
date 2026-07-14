# Issue #134 R12-I WeCom Payload Contract

## Goal

Remove the Integration Gateway reverse import into Automation Engine without changing WeCom payload behavior.

## Implementation

1. Move the two pure payload normalization functions to a shared neutral contract.
2. Re-export them from the existing Group Ops modules to preserve import compatibility.
3. Point WeCom group/private adapters directly at the shared contract.
4. Add identity and behavior contracts plus permanent full-CI selector coverage.
5. Shrink the import-graph baseline by one edge and one cyclic context.

## Verification

- WeCom adapter and Group Ops message/domain suites pass.
- Import graph reports 187 edges and 17 cyclic contexts with `automation_engine` outside the SCC.
- Full architecture gates and complete PostgreSQL CI pass.
