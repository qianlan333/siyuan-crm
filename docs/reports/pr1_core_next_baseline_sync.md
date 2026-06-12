# PR-1 Core Next Baseline Sync

## Scope

- Migrated `aicrm_next/automation_runtime_v2` code and mounted its API router in `aicrm_next.main`.
- Migrated `aicrm_next/class_user_management` and mounted it before `post_legacy_deferred`.
- Migrated native admin pages for customer read model, user ops, and identity bind-mobile page.
- Kept siyuan migration overlay intact: `app.py`, `scripts/siyuan_migration/`, deploy files, env files, systemd, nginx, and production data were not modified.

## Route Ownership Changes

- `/admin/customers` and `/admin/customers/{external_userid}` now resolve to `aicrm_next.customer_read_model.admin_pages`.
- `/admin/user-ops` and `/admin/user-ops/ui` now resolve to `aicrm_next.ops_enrollment.admin_pages`.
- `/sidebar/bind-mobile` now resolves to `aicrm_next.identity_contact.admin_pages`.
- `/api/admin/class-user-management/export` now resolves first to `aicrm_next.class_user_management.api`; the retained `post_legacy_deferred` router remains later in app order.
- `/api/automation-runtime/v2/*` is mounted from `aicrm_next.automation_runtime_v2.api`.

## Deferred

- Commerce external orders are deferred to PR-2.
- Full Alembic graph closeout is deferred to PR-3.
- `migrations/versions/0031_automation_runtime_v2.py` was not imported in this PR to avoid forcing the current siyuan migration graph into a broader head/branch-resolution change. Runtime code must handle missing production schema with controlled degraded or unavailable states rather than bare 500s.
- HXC, cloud, commerce, api-docs, and runtime-config frontend compat closeout remains deferred to later PRs.

## Security Boundary

- No `.env`, database URL, dump, upload, instance data, pem/key, token, secret, AESKey, or AppSecret was added.
- No production database action was executed.
- No deploy, systemd, nginx, or production env file was changed.
