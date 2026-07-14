# R14-C Runtime Readiness

## Goal

Keep `/health` as a lightweight liveness probe and make `/api/system/health` a fail-closed readiness surface for the deployed runtime.

## Implementation

1. Probe PostgreSQL connectivity and compare the database Alembic revision with the repository head.
2. Report count-only queue age and terminal/dead-letter metrics for webhook inbox, internal events, and external effects.
3. Report typed WeCom execution mode and exact release SHA without exposing credentials or PII.
4. Return HTTP 503 for critical component failures; expose backlog threshold breaches as explicit warnings.
5. After systemd runtime-unit verification, require the deployment to pass application readiness before leaving the rollback window.

## Verification

- Fixture, healthy PostgreSQL, connection failure, migration drift, queue warning, and HTTP status tests.
- Deploy workflow contract tests.
- Runtime contract inventory and full architecture gates.
