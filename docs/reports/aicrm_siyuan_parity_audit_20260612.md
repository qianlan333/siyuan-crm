# AI-CRM / siyuan-crm Parity Audit - 2026-06-12

## 1. Executive Summary

Conclusion: **NOT_IN_PARITY**

siyuan-crm has completed the AI-CRM Next migration, production cutover, post-cutover observation, and the first legacy HTTP prune wave. However, the current `siyuan-crm@main` is still not at the same product-function baseline as `AI-CRM@main`.

The remaining differences are not limited to database contents, env values, domains, reports, deployment overlays, or customer identifiers. The diff includes runtime router ownership, legacy compatibility removal, sidebar write behavior, identity/contact binding, channel assignment and QR behavior, commerce/admin payment APIs, schema migrations, background jobs, external push services, and test contracts.

This PR is an audit only. It does not modify product code, migrations, tests, scripts, env, deployment, or production state.

## 2. Baselines

- AI-CRM repo: `qianlan333/AI-CRM`
- AI-CRM main SHA: `6feb8c9daa7170ef4b260cb1610f15ef6510e1e6`
- siyuan-crm repo: `qianlan333/siyuan-crm`
- siyuan-crm main SHA: `38a3e491be03f3b0c9180ae771010def0c4526b8`
- Audit date: `2026-06-12 15:17:58 CST`
- Compare scope:
  - `app.py`
  - `requirements.txt`
  - `aicrm_next`
  - `migrations`
  - `scripts`
  - `tests`
  - `tools`
  - `docs/architecture`
  - `docs/route_ownership`
  - `docs/development`
  - `docs/external_orders_api.md`
- Compare command summary:
  - `git diff --name-status origin/main aicrm/main -- <scope>` wrote `/tmp/pr10_name_status.txt`
  - `git diff --stat origin/main aicrm/main -- <scope>` wrote `/tmp/pr10_diff_stat.txt`

Path-level diff count by area:

| Area | Changed paths |
|---|---:|
| `aicrm_next` | 109 |
| `migrations` | 14 |
| `scripts` | 47 |
| `tests` | 302 |
| `docs` | 34 |
| `tools` | 13 |
| `app.py` / `requirements.txt` | 2 |

## 3. Expected Permanent Overlays

These differences are expected and should not be blindly overwritten by AI-CRM:

- `docs/reports/siyuan_*` production cutover, staging rehearsal, and observation reports.
- `scripts/siyuan_migration/*` restored staging and cutover helpers.
- `docs/runbooks/siyuan_*` migration and cutover runbooks.
- `app.py` migration overlay commands in siyuan, if still intentionally retained for safe operational recovery.
- `requirements.txt` entries that are required only by siyuan deployment/runtime overlay.
- Deployment paths, systemd unit names, nginx upstreams, domains, and base URLs.
- Database names and production DB strategy.
- Env, secrets, tokens, private keys, and deployment-local config.
- Real customer IDs, external user IDs, scene values, union IDs, open IDs, mobile numbers, order numbers, product catalogs, and other production data.
- AI-CRM data migrations that mutate AI-CRM production campaign/member/broadcast data must remain siyuan-safe no-op placeholders or be separately re-authored for siyuan.

## 4. Blocking Functional Gaps

| Area | Gap | Evidence | Impact | Proposed PR |
|---|---|---|---|---|
| Runtime router parity | AI-CRM `aicrm_next/main.py` no longer imports or mounts `frontend_compat_router` or `post_legacy_deferred_router`; siyuan still has those compatibility surfaces and route registry tooling. | `git diff origin/main aicrm/main -- aicrm_next/main.py`; `aicrm_next/frontend_compat/legacy_routes.py`, `aicrm_next/post_legacy_deferred/api.py`, and `aicrm_next/platform_foundation/route_registry/*` exist only in siyuan. | Route ownership and fallback behavior are not fully aligned with AI-CRM current main. | PR-11 Core Runtime Parity |
| Runtime entry overlay | AI-CRM `app.py` removed `init-next-schema-safe` and `sync-customer-read-model`; siyuan still carries those commands as migration/cutover overlay. | `git diff origin/main aicrm/main -- app.py` shows AI-CRM removed safe-init and sync CLI entrypoints. | This may be an expected siyuan operational overlay, but it must be explicitly kept or retired; it should not be overwritten blindly. | PR-11 Core Runtime Parity |
| Legacy package residual | AI-CRM removed route registry, legacy compatibility docs, and many legacy guard tests. siyuan has completed PR-9 HTTP module prune, but still carries compatibility inventory/checker surfaces. | `git diff --name-status origin/main aicrm/main -- aicrm_next/frontend_compat aicrm_next/post_legacy_deferred aicrm_next/platform_foundation/route_registry scripts/check_no_new_legacy.py tests`. | Legacy deletion degree is different; parity guard model is not the same baseline. | PR-11 Core Runtime Parity |
| Sidebar bind-mobile production parity | AI-CRM allows production `BindMobileCommand` through a Postgres-backed sidebar write path while keeping other unsafe sidebar writes blocked. siyuan still treats production sidebar write as unavailable for command execution. | `git diff origin/main aicrm/main -- aicrm_next/sidebar_write/application.py aicrm_next/sidebar_write/repo.py tests/test_sidebar_write_commands.py`; AI-CRM adds `PostgresSidebarWriteRepository.bind_mobile` and production tests. | Users can bind mobile from the sidebar in AI-CRM production, but siyuan may still return controlled unavailable for the same flow. | PR-12 Sidebar / Identity / Customer Parity |
| Sidebar bind-mobile native page | AI-CRM adds native `/sidebar/bind-mobile` page ownership tests and removes it from frontend compatibility inventory. | `tests/test_sidebar_bind_mobile_native_page.py` exists only in AI-CRM; diff shows endpoint owner assertion against `aicrm_next.identity_contact.admin_pages`. | Admin/sidebar UX parity differs. | PR-12 Sidebar / Identity / Customer Parity |
| External contact identity compatibility | AI-CRM adds admin identity resolve/link APIs, identity binding repository, mobile binding normalization, and event sync behavior that tolerates missing `openid`. | `git diff origin/main aicrm/main -- aicrm_next/identity_contact aicrm_next/channel_entry/identity_bridge_service.py tests/test_channel_identity_bridge_native_service.py tests/test_identity_application_contract.py`. | External contact identity sync and user/customer resolution contract are not fully aligned. | PR-12 Sidebar / Identity / Customer Parity |
| Customer read-model parity | AI-CRM changes customer read-model projection/backfill/repository behavior and removes `sync_cli.py`; siyuan keeps safe sync overlay and older projection code. | `git diff --stat origin/main aicrm/main -- aicrm_next/customer_read_model`. | Customer projection and sidebar context behavior may diverge from AI-CRM main. | PR-12 Sidebar / Identity / Customer Parity |
| Channel multi-staff assignment parity | AI-CRM adds assignment mode/strategy, assignee persistence, assignment events, active assignee selection, and assignee APIs. siyuan lacks these schema and runtime additions. | `aicrm_next/automation_engine/channels_api.py`, `aicrm_next/channel_entry/repo.py`, `aicrm_next/channel_entry/application.py`, `tests/test_channel_multi_staff_backend.py`, and `tests/test_channel_multi_staff_frontend_contract.py` differ; AI-CRM adds `migrations/versions/0036_channel_multi_staff_assignment.py`. | Multi-staff channel assignment and distribution rules are missing from siyuan. | PR-13 Channel Center / Multi-staff / QR Parity |
| Channel QR generation type parity | AI-CRM adjusts channel QR generation for multi-staff assignees and related WeCom payload behavior. | `aicrm_next/channel_entry/application.py` diff shows QR generation reading active assignees for `multi_staff`; `tests/test_next_channel_qrcode_generate.py` differs. | Generated QR codes may target different staff semantics between repos. | PR-13 Channel Center / Multi-staff / QR Parity |
| Channel center list action/status parity | AI-CRM adds status-only PATCH validation, assignee endpoints, archive/inactive behavior, and updated list/edit UI shell. | `aicrm_next/automation_engine/channels_api.py`, `channel_code_center_next.js`, `channel_admission_pages.js/css`, and channel form templates differ. | Admin channel center operations differ from AI-CRM main. | PR-13 Channel Center / Multi-staff / QR Parity |
| Welcome message placeholder parity | AI-CRM has a recent welcome customer-name placeholder fix and related channel welcome send content changes. | AI-CRM baseline includes `Fix next welcome customer name placeholder`; diffs include `aicrm_next/automation_engine/group_ops/message_content.py` and `tests/test_next_channel_welcome_send_content_composer.py`. | Welcome content rendered to users can differ. | PR-13 Channel Center / Multi-staff / QR Parity |
| Alembic/schema parity | AI-CRM has channel multi-staff schema and extra merge revisions. siyuan retains no-op placeholders for AI-CRM data migrations, which is correct as data overlay, but schema capability is still behind. | AI-CRM adds `0036_channel_multi_staff_assignment.py`, `0037_merge_channel_and_wechat_shop_heads.py`, `0037_merge_channel_multi_staff_and_wechat_shop_heads.py`, and `0038_merge_duplicate_channel_wechat_shop_heads.py`; siyuan keeps 0032/0033/0034 no-op data placeholders. | Migration graph and schema capabilities are not functionally identical. | PR-13 Channel Center / Multi-staff / QR Parity |
| Commerce/admin payment parity | AI-CRM adds/changes admin order APIs, refunds, exports, webhooks, WeChat Shop client/service/signature, and transaction detail behavior. siyuan PR-2 covered external orders but not the current full commerce admin baseline. | `git diff --name-status origin/main aicrm/main -- aicrm_next/commerce tests` shows `admin_exports.py`, `admin_refunds.py`, `admin_webhooks.py`, `wechat_shop_client.py`, `wechat_shop_service.py`, `wechat_shop_signature.py`, and `tests/test_admin_p0_commerce_api.py` only in AI-CRM. | Commerce back-office feature surface differs. | PR-14 External API Docs / Parity Guard |
| External orders docs/base URL overlay | AI-CRM docs contain production base URL and product/order examples; siyuan docs intentionally use deployment-owned placeholders. | `docs/external_orders_api.md` differs substantially. | This is partly expected domain/docs overlay, but product examples and doc contracts must be curated to avoid importing AI-CRM production-specific data. | PR-14 External API Docs / Parity Guard |
| External orders implementation parity | `external_orders.py` differs in error handling and user resolve behavior. | `git diff origin/main aicrm/main -- aicrm_next/commerce/external_orders.py` shows changed `production_unavailable` / not-found branches. | API behavior may diverge under missing schema or unmatched user cases. | PR-14 External API Docs / Parity Guard |
| Background jobs parity | AI-CRM has a `aicrm_next/background_jobs` package and rewired worker scripts; siyuan does not. | AI-CRM-only files include `background_jobs/automation_member_backfill.py`, `automation_ops_scheduler.py`, `broadcast_queue_worker.py`, `external_contact_sync.py`, and `db.py`. | Scheduler/worker runtime baseline is not the same. | PR-11 Core Runtime Parity |
| External push service parity | AI-CRM adds `aicrm_next/external_push` service/repo/security and related tests; siyuan does not. | AI-CRM-only files include `aicrm_next/external_push/*`, `tests/test_external_push_next_native_service.py`, and `tests/test_external_push_worker_next_native.py`. | External push delivery internals differ. | PR-14 External API Docs / Parity Guard |
| Test and guard parity | 302 test paths differ, including route ownership, production route resolution, legacy checker, channel, sidebar, commerce, background jobs, and deployment-service tests. | `/tmp/pr10_name_status.txt` has 302 changed test paths; AI-CRM deletes several legacy registry tests and adds new Next-native tests. | Contract coverage is not aligned; CI can pass while product behavior still diverges. | PR-14 External API Docs / Parity Guard |

## 5. Non-blocking / Overlay Differences

| Area | Difference | Treatment |
|---|---|---|
| siyuan migration scripts | `scripts/siyuan_migration/*` exists only in siyuan. | Keep as siyuan operational overlay. Do not import into AI-CRM or delete during parity sync unless a separate operational decision is made. |
| Production reports | siyuan cutover/readiness/observation reports are repo-specific. | Keep. They are evidence artifacts, not product gaps. |
| Safe schema init | siyuan still has `aicrm_next/schema_init.py` and app CLI wrappers; AI-CRM has removed them. | Decide in PR-11 whether this remains a permanent recovery overlay or is retired after production stabilization. |
| AI-CRM production data migrations | AI-CRM 0032/0033/0034 contain AI-CRM production campaign/member/broadcast mutations. | Do not import those data mutations into siyuan. Keep no-op placeholders or re-author only schema-safe parts if needed. |
| External API docs domain/examples | AI-CRM docs reference its production domain and examples; siyuan docs should use target deployment-owned placeholders. | Keep domain/product examples as siyuan overlay while aligning the API contract text. |
| Requirements | AI-CRM drops dependencies that may be needed by siyuan overlay. | Preserve siyuan-specific dependencies unless verified unused. |
| Deployment/runbooks | systemd/nginx/env and cutover runbooks differ by deployment. | Keep overlay; do not change production deployment in parity PRs. |

## 6. Recommended PR Plan

### PR-11 Core Runtime Parity

- Align `aicrm_next/main.py` router registrations with AI-CRM current main.
- Decide whether `frontend_compat`, `post_legacy_deferred`, route registry, and `check_no_new_legacy.py` remain as temporary siyuan overlays or should be removed.
- Port AI-CRM `background_jobs` package and worker script refactors if they are production runtime baseline.
- Keep `app.py` migration overlay only if explicitly retained; otherwise plan a separate safe retirement.
- Do not delete `scripts/siyuan_migration/*`.

### PR-12 Sidebar / Identity / Customer Parity

- Port production-safe sidebar bind-mobile behavior.
- Port native bind-mobile page ownership and tests.
- Port identity binding repository and admin identity resolve/link API.
- Align external contact identity bridge behavior, including missing `openid` compatibility.
- Reconcile customer read-model/backfill differences while preserving siyuan data overlays.

### PR-13 Channel Center / Multi-staff / QR Parity

- Port channel multi-staff assignment schema and runtime.
- Align QR generation payload semantics for single-owner vs multi-staff channels.
- Align channel center list actions, status-only PATCH, inactive/archive/delete behavior, and assignee APIs.
- Align welcome message customer-name placeholder behavior.
- Add schema migrations without importing AI-CRM production data.

### PR-14 External API Docs / Parity Guard

- Align commerce admin APIs: refunds, exports, webhook admin, WeChat Shop service/client/signature, and unified order detail behavior.
- Reconcile `external_orders.py` error semantics and external user resolve behavior.
- Keep siyuan docs free of AI-CRM production product/order/user examples.
- Align parity guards/tests to prevent drift after PR-11 through PR-13.

## 7. Safety Boundaries

- Do not overwrite siyuan `app.py` blindly.
- Do not delete `scripts/siyuan_migration/*` during parity sync.
- Do not delete siyuan migration, cutover, readiness, or observation reports.
- Do not import AI-CRM production data migrations into siyuan.
- Do not commit env, dump, uploads, instance, pem, key, token, secret, AESKey, AppSecret, or database URL values.
- Do not change production systemd/nginx/deploy config in parity sync PRs.
- Do not execute production DB writes.
- Do not copy AI-CRM production user/order/product/campaign/member identifiers into siyuan docs, tests, migrations, or code.
- Keep domain/base URL differences as deployment overlay unless the user explicitly asks for domain migration.

## 8. Validation

Executed for this audit:

- `git rev-parse origin/main`
- `git rev-parse aicrm/main`
- `git log --oneline -5 origin/main`
- `git log --oneline -10 aicrm/main`
- `git diff --name-status origin/main aicrm/main -- app.py requirements.txt aicrm_next migrations scripts tests tools docs/architecture docs/route_ownership docs/development docs/external_orders_api.md > /tmp/pr10_name_status.txt`
- `git diff --stat origin/main aicrm/main -- app.py requirements.txt aicrm_next migrations scripts tests tools docs/architecture docs/route_ownership docs/development docs/external_orders_api.md > /tmp/pr10_diff_stat.txt`
- Module-specific checks for:
  - runtime entry and router registration
  - legacy compatibility removal
  - sidebar bind-mobile
  - identity/contact bridge
  - channel assignment and QR behavior
  - commerce/external orders
  - Alembic/schema
  - tests/guards

No production commands were executed. This report contains no raw database URL, secrets, tokens, private keys, mobile numbers, external user IDs, scene values, union IDs, or open IDs.

## 9. PR-11 Follow-up Status

Status after PR-11: **core runtime parity completed with siyuan overlays**.

Done in PR-11:

- `aicrm_next/main.py` no longer imports or mounts `frontend_compat_router`.
- `aicrm_next/main.py` no longer imports or mounts `post_legacy_deferred_router`.
- `/admin/api-docs` and `/admin/runtime-config` are owned by `aicrm_next.admin_config.api`.
- Cloud audit/observability APIs are owned by `aicrm_next.cloud_orchestrator.api`.
- WeCom customer acquisition link safe-mode APIs are owned by `aicrm_next.automation_engine.channels_api`.
- AI-CRM `aicrm_next/background_jobs/*` and `aicrm_next/external_push/*` packages are present in siyuan.

Expected overlays retained:

- `app.py` migration and restored-DB operational commands.
- `scripts/siyuan_migration/*`.
- route registry and legacy guard tooling.
- historical `post_legacy_deferred` and `frontend_compat/legacy_routes.py` source files as unmounted guard/inventory sources.

Still NOT_IN_PARITY for product functionality until PR-12 / PR-13 / PR-14 close the remaining sidebar, identity, customer, channel, commerce, and final docs/guard gaps.
