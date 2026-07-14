# R09 Questionnaire, Radar, and External Push Closure

Issue: #104
Parent: #67
Base: `main@a9240955d97ddebc655f650b42e036e1ef6e0d0f`

## Architecture preflight

- Capability owners: `questionnaire`, `radar_links`, `customer_tags`, with neutral durable primitives owned by `platform_foundation`.
- Routes: `/api/h5/questionnaires/{slug}/submit`, `/api/h5/questionnaires/{slug}/result/{submission_id}`, `/s/{slug}/submitted`, `/r/{code}`, `/api/h5/radar/oauth/start`, `/api/h5/radar/oauth/callback`, and existing Radar content/event routes.
- All scoped routes are AI-CRM Next native owners. No legacy facade or compatibility fallback is permitted.
- Real external calls already exist for WeCom tags and outbound webhooks. R09 moves them behind existing External Effect workers; H5 and Radar request paths must execute no provider call.
- Test-server production-shaped data is read only unless a separately audited reconciliation repair is explicitly selected. Tests use isolated PostgreSQL `aicrm_r09_work`.
- Fixture risk: existing unit tests rely heavily on in-memory repositories and fake OAuth. Every transaction, retry, and ownership claim therefore requires a real PostgreSQL contract test.
- Checkers: extend test-scope, runtime/route/table ownership, and add count-only R09 reconciliation.
- Rollback: roll back the release and migration. Preserve durable outbox/effect rows; never restore synchronous provider calls or query/cookie identity trust.

## Step 1: transactional questionnaire continuation

- Output: PostgreSQL submission, answer snapshots, identity-resolution queue, and one `questionnaire.submitted` outbox share one caller-owned transaction.
- Test: injected answer/outbox failures roll back all rows; replay produces one submission and one outbox lineage.

## Step 2: single durable tag and webhook planners

- Output: H5 performs no provider call and no direct External Effect planning. Internal Event consumers reload authoritative submission/config and plan exactly one webhook job and one WeCom tag job.
- Test: missing identity, DB faults, planner faults, 429, timeout, duplicate consumer replay, and process restart retain retryable/terminal truth without duplicate jobs.

## Step 3: result and Radar identity boundary

- Output: result access accepts only random token plus bound signed grant; Radar ignores untrusted query/plain cookies and only trusts signed viewer sessions issued by a validated OAuth callback.
- Test: sequential IDs, cross-slug grants, tampering, expiry, forged query/cookies, and fake callback identity outside explicit fixture mode cannot reveal or attribute identity.

## Step 4: ownership, schema, and reconciliation

- Output: Radar click-event schema has an Alembic create/upgrade path and unique write owner. R09 count-only reconciliation reports missing outbox, missing/duplicate effects, successful tag effects missing local projection, and legacy retry residue without PII/provider calls.
- Test: empty production-shaped upgrade from the current test baseline, ownership/lifecycle gates, no-provider diagnostics, and idempotent continuation-only repair.

## Step 5: full delivery

- Output: local full PostgreSQL/frontend/architecture/dependency evidence, PR with forced full CI, merge, main CI, exact-SHA test deployment, worker/timer and count-only reconciliation evidence.
- Test: all required GitHub checks green and public/server release SHA equals the merge SHA.

## Non-goals

- No new product route, page, menu, metric, customer model, Journey, or analytics feature.
- No direct provider execution from H5/Radar routes.
- No restoration of retired external-push worker/service/timer.
- No bulk repair that can trigger real external calls.
