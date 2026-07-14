# Issue #125 R12-D User Ops Gateway

## Goal

Remove the `ai_audience_ops -> ops_enrollment` runtime edge without changing the guarded production E2E behavior.

## Plan

1. Replace concrete User Ops DTO/Command dependencies in the E2E runner with a primitive-value gateway protocol.
2. Implement the adapter inside `ops_enrollment`, preserving the exact `BatchSendRequest` mapping.
3. Build a fresh gateway-backed runner factory in a package-root composition module.
4. Attach a fresh factory to each FastAPI app and resolve it from the external route.
5. Tighten import-graph budgets and add permanent full-CI selector coverage.

## Verification

- Gateway request mapping and confirm false/true tests.
- Existing E2E hard guards and external API tests.
- Multi-app composition isolation test.
- Import graph, selector, and full architecture gates.
