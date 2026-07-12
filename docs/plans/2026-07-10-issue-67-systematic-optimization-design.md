# Issue 67 Systematic Optimization Design

**Epic:** `qianlan333/AI-CRM-ID-refactor#67`

**Validated baseline:** `main@5b1f0d47f10bd74d4570f1613883dd31f9c7f93e`, Alembic head `0096_admin_wecom_directory_members`

## Decision

The Epic will be delivered as dependency-ordered, independently reversible work packages R00 through R15. A single repository-wide rewrite is rejected because it violates the Epic's authorization boundary, prevents useful parity evidence, and makes schema/runtime rollback unsafe. Uncoordinated domain-specific rewrites are also rejected because identity, event, effect, delivery, and deployment correctness share the same contracts. The selected approach starts with R00's executable behavior baseline, then follows the dependency graph in Issue #67. Every package gets a child issue with exact authorized files, non-goals, tests, reconciliation evidence, and rollback before implementation.

Every PR must keep `User-visible capability delta: none`. The work may add internal policy, audit, reconciliation, test, migration, and diagnostic structures only when they replace or verify an existing unsafe or inconsistent path. Existing pages, routes, request/response fields, and operator steps stay compatible unless the package records a security or correctness breaking decision. No Customer 360, Activity, analytics, Journey, Note/Task, multi-tenant, new AI feature, menu, page, business route, or business model is introduced.

## Program Architecture

R00 freezes observable behavior and makes full regression unavoidable for high-risk changes. R01-R04 then close route authorization, secret/PII, unionid identity, sidebar, customer-detail, and questionnaire access gaps. R05-R10 converge callback, internal event, external effect, payment/refund/entitlement, questionnaire/external push, and Group Ops delivery onto durable, idempotent existing chains. R11-R13 establish installable schema ownership, one-way module dependencies, bounded modules, and reproducible frontend artifacts. R14 makes the verified commit the exact serialized deployment unit and adds real readiness/recovery. R15 finishes performance baselines and evidence-driven retirement.

The invariant across packages is one owner per route, table write, job claim, state transition, and external effect. Cross-package changes use expand/contract and parity before owner cutover. Provider acceptance without a durable local receipt becomes `unknown_after_dispatch`, never an automatic resend. Simulated, blocked, retryable, terminal, cancelled, and succeeded states remain distinct. Production external effects stay behind the existing execution gates; this Epic does not authorize new providers or new real-call surfaces.

## R00 Executable Baseline

R00 produces one deterministic runtime-contract inventory from the real composition root and checked-in governance sources. It records pages/routes and OpenAPI request/response contracts, migration head, table lifecycle/ownership, internal-event consumers, external-effect types, systemd services/timers, and environment-variable references. A generated JSON snapshot is committed, and a `--check` mode fails when runtime or manifests drift. Fixture-only state is excluded or explicitly labelled so a local fixture cannot masquerade as production behavior.

A separate high-risk contract manifest maps auth, callback, payment, refund/entitlement, questionnaire, Group Ops, and delivery to existing success, failure, and replay/concurrency pytest node IDs. The checker proves each node exists and remains selected by the relevant CI scope. `needs_full_ci=true` calls the reusable full regression workflow from `CI Fast`; the final required job depends on that result. The manually triggered/nightly full workflow remains available and uses the same jobs, eliminating divergent definitions.

R00 adds no route, business state, or external-call mode. Baseline reconciliation found one schema defect introduced before R00: `service_period_entitlements.mobile_snapshot` violated the already-enforced unionid-only final schema. R00 therefore includes one corrective `0097` migration that drops only that duplicate column and reads mobile from `crm_user_identity` by unionid. Rollback downgrades to `0096` before reverting the PR. The prior CI behavior and existing manifests remain usable after revert, while later work packages are blocked until R00 is green.

## Verification and Completion

R00 reaches L3 only when the current full Python/PostgreSQL and frontend suites have zero failures, every prior failure has a recorded classification, the generated inventory is reproducible, a deliberate drift makes CI fail, and high-risk files demonstrably trigger their scoped integration tests plus full regression. Later packages must satisfy their own success/failure/fault/concurrency evidence, schema parity, rollback, CI, deployment, and live verification before their child issue closes. The Epic closes only after the Issue #67 total acceptance checklist is re-audited against current code, CI, migrations, deployment logs, and runtime behavior.
