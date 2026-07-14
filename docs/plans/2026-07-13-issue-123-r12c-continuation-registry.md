# Issue #123 R12-C External Effect Continuation Registry

## Goal

Remove the platform worker's runtime imports of `automation_agents` and `customer_tags` while preserving both post-provider-success behaviors.

## Delivery slices

1. Add an immutable platform continuation registry with explicit injection and no mutable process-global registration.
2. Move automation-agent webhook continuation ownership into `automation_agents`.
3. Move questionnaire tag projection ownership into `questionnaire`.
4. Compose a fresh registry per web app and per scheduler CLI process from a package-root composition module.
5. Inject the composition into behavior tests, scheduler, and admin run-due routes.
6. Tighten import-graph budgets and add permanent full-CI selector coverage.

## Verification

- Registry/composition unit tests.
- Existing automation-agent webhook continuation regression.
- Existing questionnaire real-WeCom tag projection regression.
- Scheduler script injection regression.
- Full architecture gates and exact import-graph baseline.
