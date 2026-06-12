# Post-Legacy Product Baseline Inventory

Status: baseline_locked_after_production_compat_removal

This inventory is the first post-Legacy Product baseline after production compatibility runtime removal. It records representative product/admin/H5 page surfaces, their backing API contracts, and the remaining explicit deferred frontend URL references. It is not a runtime router source.

## Baseline Rules

- `production_compat` must not be included in runtime app startup and must not own any route.
- Representative production app responses must not include `X-AICRM-Compatibility-Facade`.
- Normal paths must not return `fallback_used=true`.
- Real payment, real send, real WeCom OAuth/token exchange, real media upload, and other external side effects remain fake, blocked, local, or explicitly gated by adapter configuration.
- A future real adapter enablement must be shipped as an explicit gated adapter PR with owner, lifecycle, smoke, rollback, and audit notes.
- Rollback policy is a Next-native fix or a feature gate disablement, never restoration of `production_compat`.

## Admin Page Matrix

| Page | Route | Owner | Expected status | API dependencies | Baseline note |
| --- | --- | --- | --- | --- | --- |
| Login | `/login` | `aicrm_next.admin_auth` | 200 | `/login` POST | Next auth shell; WeCom SSO stays blocked by default. |
| Admin dashboard | `/admin` | `aicrm_next.admin_shell` | 200 | `/api/admin/dashboard/shell-context` | Native Next admin shell, navigation, dashboard shell context, and `/admin/logout` compatibility redirect. |
| Route registry | `/admin/system/routes` | `aicrm_next.platform_foundation` | 200 | `/api/admin/system/routes` | Ownership and lifecycle source of truth page. |
| Customers | `/admin/customers` | `aicrm_next.customer_read_model` | 200 | `/api/customers` | Next customer read model only. |
| Customer detail | `/admin/customers/wx_ext_001` | `aicrm_next.customer_read_model` | 200 | `/api/customers/{external_userid}`, `/api/customers/{external_userid}/timeline`, `/api/admin/automation-conversion/member` | Detail page reads customer and automation context without compat fallback. |
| User Ops | `/admin/user-ops` | `aicrm_next.ops_enrollment` | 200 | `/api/admin/user-ops/overview`, `/api/admin/user-ops/customers`, `/api/admin/user-ops/send-records` | Enrollment workspace reads Next APIs; writes are planned/blocked. |
| Questionnaire list | `/admin/questionnaires` | `aicrm_next.questionnaire` | 200 | `/api/admin/questionnaires` | Next questionnaire read model. |
| Questionnaire new | `/admin/questionnaires/new` | `aicrm_next.questionnaire` | 200 | `/api/admin/questionnaires/preflight`, `/api/admin/questionnaires` | Editor shell only; create/update through Next admin write routes. |
| Questionnaire detail | `/admin/questionnaires/1` | `aicrm_next.questionnaire` | 200 | `/api/admin/questionnaires/{questionnaire_id}`, `/api/admin/questionnaires/{questionnaire_id}/questions`, `/api/admin/questionnaires/{questionnaire_id}/results`, `/api/admin/questionnaires/{questionnaire_id}/submissions` | Fixture id 1 proves normal route; `/admin/questionnaires/21` is controlled 404 for missing fixture data. |
| WeCom tags | `/admin/wecom-tags` | `aicrm_next.customer_tags` | 200 | `/api/admin/wecom/tags`, `/api/admin/wecom/tag-groups`, `/api/admin/wecom/tags/live/mark` | Local projection writes by default; live mutation is real-blocked. |
| Image library | `/admin/image-library` | `aicrm_next.media_library` | 200 | `/api/admin/image-library`, `/api/admin/image-library/upload`, `/api/admin/image-library/{image_id}` | Local/fake media storage by default. |
| Attachment library | `/admin/attachment-library` | `aicrm_next.media_library` | 200 | `/api/admin/attachment-library`, `/api/admin/attachment-library/upload`, `/api/admin/attachment-library/{attachment_id}` | Local/fake media storage by default. |
| Miniprogram library | `/admin/miniprogram-library` | `aicrm_next.media_library` | 200 | `/api/admin/miniprogram-library`, `/api/admin/miniprogram-library/{item_id}` | Local/fake card metadata by default. |
| Cloud campaigns | `/admin/cloud-orchestrator/campaigns` | `aicrm_next.cloud_orchestrator` | 200 | `/api/admin/cloud-orchestrator/campaigns`, `/api/admin/cloud-orchestrator/campaigns/run-due/preview`, `/api/admin/cloud-orchestrator/campaigns/run-due` | Run-due uses preview/planned side effects by default. |
| Cloud plans | `/admin/cloud-orchestrator/plans` | `aicrm_next.cloud_orchestrator` | 200 | `/api/admin/cloud-orchestrator/plans`, `/api/admin/cloud-orchestrator/plans/{plan_id}` | Review workspace over Next read model. |
| HXC dashboard | `/admin/hxc-dashboard` | `aicrm_next.hxc_dashboard` | 200 | `/api/admin/hxc-dashboard`, `/api/admin/hxc-dashboard/refresh` | Refresh creates blocked side-effect plans by default. |
| HXC send config | `/admin/hxc-send-config` | `aicrm_next.hxc_dashboard` | 200 | `/api/admin/hxc-dashboard/send-config` | Config reads local/safe model. |
| WeChat Pay products | `/admin/wechat-pay/products` | `aicrm_next.commerce` | 200 | `/api/admin/wechat-pay/products`, `/api/admin/wechat-pay/products/lead-channels`, `/api/admin/wechat-pay/products/{product_id}` | Product management is Next-owned; real payment remains disabled by default. |
| WeChat Pay product new | `/admin/wechat-pay/products/new` | `aicrm_next.commerce` | 200 | `/api/admin/wechat-pay/products`, `/api/admin/wechat-pay/products/lead-plans` | Create contract is Next API. |
| WeChat Pay transactions | `/admin/wechat-pay/transactions` | `aicrm_next.commerce` | 200 | `/api/admin/wechat-pay/orders`, `/api/admin/wechat-pay/transactions` | Transaction/order read model is Next-owned. |

## Public/H5 Page Matrix

| Page | Route | Owner | Expected status | API dependencies | Baseline note |
| --- | --- | --- | --- | --- | --- |
| Public product | `/p/test-product` | `aicrm_next.public_product` | 200 | `/api/products/test-product` | Product fixture renders without production compat. |
| Public payment landing | `/pay/test-product` | `aicrm_next.public_product` | 200 | `/api/products/test-product`, `/api/checkout/wechat` | Checkout remains fake/no real payment by default. |
| Product API | `/api/products/test-product` | `aicrm_next.public_product` | 200 | none | Next-owned product API. |
| H5 questionnaire | `/s/hxc-activation-v1` | `aicrm_next.questionnaire` | 200 | `/api/h5/questionnaires/hxc-activation-v1`, `/api/h5/questionnaires/hxc-activation-v1/submit`, `/api/h5/questionnaires/hxc-activation-v1/client-diagnostics` | H5 read/write paths are Next-owned. |
| H5 questionnaire submitted | `/s/hxc-activation-v1/submitted` | `aicrm_next.questionnaire` | 200 | `/api/h5/questionnaires/hxc-activation-v1/result/{submission_id}` | Result route is explicit Next route. |
| WeCom auth start | `/auth/wecom/start` | `aicrm_next.auth_wecom` | 503 controlled | none | Real token exchange is blocked by default. |
| WeCom auth callback | `/auth/wecom/callback` | `aicrm_next.auth_wecom` | 503 controlled | none | Real token exchange is blocked by default. |

## Additional Active Admin Route Families

These routes were auto-discovered from the FastAPI app after #1040/#1042. They are not all repeated in the focused smoke list, but they are active admin surfaces and must stay registered in the production route ownership manifest or be explicitly deprecated by a later PR.

| Family | Representative routes | Runtime owner | Baseline status |
| --- | --- | --- | --- |
| Admin jobs | `/admin/jobs`, `/admin/broadcast-jobs`, `/admin/jobs/actions` | `aicrm_next.admin_jobs` | Active; covered by existing native jobs tests and route registry. |
| Owner migration | `/admin/owner-migration` | `aicrm_next.owner_migration` | Active; Next-owned. |
| Channels | `/admin/channels`, `/admin/channels/new`, `/admin/channels/{channel_id}/edit` | `aicrm_next.automation_engine.channel_admin_pages` | Active; channel API URLs are validated by static URL alignment. |
| Automation conversion | `/admin/automation-conversion`, `/admin/automation-conversion/programs/{program_id}/setup`, `/admin/automation-conversion/programs/{program_id}/overview`, `/admin/automation-conversion/programs/{program_id}/members`, `/admin/automation-conversion/group-ops/ui` | Project pages: `aicrm_next.automation_engine.admin_pages`; group ops remains `aicrm_next.frontend_compat` pending P2-12D | Active/deferred by sub-surface; URL alignment is checked and side effects remain planned/blocked. |
| Cloud orchestrator shell | `/admin/cloud-orchestrator`, `/admin/cloud-orchestrator/observability` | `aicrm_next.frontend_compat` | Active shell; observability/audit JSON APIs are closed by `docs/architecture/post_legacy_deferred_api_cleanup_inventory.md`. |
| Admin config/runtime/API docs | `/admin/config`, `/admin/config/app-settings`, `/admin/config/login-access`, `/admin/config/checklist`, `/setup/wizard`, `/admin/runtime-config`, `/admin/api-docs` | `aicrm_next.admin_config` for config, `aicrm_next.frontend_compat` for runtime/API docs | Active support/admin surfaces; no production_compat router involvement. |
| Questionnaire external push logs | `/admin/questionnaires/external-push-logs`, `/admin/questionnaires/{questionnaire_id}/external-push-logs` | `aicrm_next.questionnaire` | Next-native log read and retry command surface; retry defaults to SideEffectPlan only and real external delivery remains gated. |
| Radar links | `/admin/radar-links`, `/admin/radar-links/new`, `/admin/radar-links/{link_id}/edit`, `/admin/radar-links/{link_id}/detail` | `aicrm_next.radar_links.admin_pages` | Active; export/events URLs resolve to Next routes. |
| Alipay admin | `/admin/alipay/transactions` | `aicrm_next.commerce` | Active payment admin surface served by the shared readonly transaction model; provider behavior remains fake/blocked by default. |
| Logout compatibility redirect | `/admin/logout` | `aicrm_next.admin_shell` | Redirects to canonical `/logout`. |

## API Contract Matrix

| Capability | Method | Route | Owner | Expected baseline | External behavior |
| --- | --- | --- | --- | --- | --- |
| Customer read | GET | `/api/customers` | `aicrm_next.customer_read_model` | 200 | none |
| Route registry read | GET | `/api/admin/system/routes` | `aicrm_next.platform_foundation` | 200 | none |
| User Ops overview | GET | `/api/admin/user-ops/overview` | `aicrm_next.ops_enrollment` | 200 | none |
| Questionnaire admin read | GET | `/api/admin/questionnaires`, `/api/admin/questionnaires/1` | `aicrm_next.questionnaire` | 200 | none |
| Questionnaire H5 read | GET | `/api/h5/questionnaires/hxc-activation-v1` | `aicrm_next.questionnaire` | 200 | none |
| Questionnaire H5 submit | POST | `/api/h5/questionnaires/hxc-activation-v1/submit` | `aicrm_next.questionnaire` | 200 | local write model; external push blocked unless gated |
| Questionnaire H5 diagnostics | POST | `/api/h5/questionnaires/hxc-activation-v1/client-diagnostics` | `aicrm_next.questionnaire` | 200 | local diagnostic write |
| Questionnaire OAuth | GET | `/api/h5/wechat/oauth/start` | `aicrm_next.questionnaire` | 200 fake or 503 controlled | real OAuth disabled unless explicit gated adapter config |
| Admin WeCom auth | GET | `/auth/wecom/start`, `/auth/wecom/callback` | `aicrm_next.auth_wecom` | 503 controlled | real token exchange blocked by default |
| WeCom tag read/write | GET/POST | `/api/admin/wecom/tags` | `aicrm_next.customer_tags` | 200 | local projection; no live sync by default |
| WeCom tag live mutation | POST | `/api/admin/wecom/tags/live/mark` | `aicrm_next.customer_tags` | 200/400 controlled | real-blocked by default |
| Media libraries | GET | `/api/admin/image-library`, `/api/admin/attachment-library`, `/api/admin/miniprogram-library` | `aicrm_next.media_library` | 200 | local/fake storage by default |
| Cloud campaigns | GET/POST | `/api/admin/cloud-orchestrator/campaigns`, `/api/admin/cloud-orchestrator/campaigns/run-due/preview`, `/api/admin/cloud-orchestrator/campaigns/run-due` | `aicrm_next.cloud_orchestrator` | 200 | preview/planned side effects only by default |
| Cloud observability | GET | `/api/admin/cloud-orchestrator/audit`, `/api/admin/cloud-orchestrator/observability` | `aicrm_next.cloud_orchestrator.api` | 200 | local read-only contract; no external observability service |
| Automation timer/member actions | POST | `/api/admin/automation-conversion/jobs/run-due/preview`, `/api/admin/automation-conversion/member/put-in-pool` | `aicrm_next.automation_engine` | 200 | planned/blocked side effects by default |
| Customer activation webhook | POST | `/api/customers/automation/activation-webhook` | `aicrm_next.automation_engine` | 200/400 controlled | real external call blocked by default |
| HXC dashboard | GET/POST | `/api/admin/hxc-dashboard`, `/api/admin/hxc-dashboard/refresh` | `aicrm_next.hxc_dashboard` | 200 | blocked side-effect plan by default |
| Class-user export | GET/POST | `/api/admin/class-user-management/export` | `aicrm_next.class_user_management.api` | 200 | local CSV export; no external storage |
| WeCom customer acquisition links | GET/POST/PATCH/DELETE | `/api/admin/wecom-customer-acquisition-links`, `/api/admin/wecom-customer-acquisition-links/{link_id}`, `/api/admin/wecom-customer-acquisition-links/{link_id}/{action}` | `aicrm_next.automation_engine.channels_api` | 200/404/410 controlled | safe-mode local fixture; real WeCom blocked |
| Checkout | POST | `/api/checkout/wechat` | `aicrm_next.commerce` | 200 | fake checkout/no real payment by default |
| Order read | GET | `/api/orders/smoke` | `aicrm_next.commerce` | 404 controlled | none |
| Provider notify | POST | `/api/wechat-pay/notify` | `aicrm_next.commerce` | 200/400/422 controlled | no legacy forward |
| Payment unknown admin/H5 | GET | `/api/admin/wechat-pay/unknown-child`, `/api/h5/wechat-pay/unknown-child` | `aicrm_next.commerce` | 410 controlled | no legacy forward |

## Deferred API Closeout References

The PR #1043 deferred frontend API references are no longer whitelisted. They are implemented as Next-owned controlled contracts and tracked in `docs/architecture/post_legacy_deferred_api_cleanup_inventory.md`.

| URL or prefix | Status | Required future action |
| --- | --- | --- |
| `/api/admin/class-user-management/export` | closed_next_export | Covered by local CSV export route; keep no external storage default. |
| `/api/admin/cloud-orchestrator/audit` | closed_next_cloud_observability | Covered by read-only empty/degraded-safe audit contract. |
| `/api/admin/cloud-orchestrator/observability` | closed_next_cloud_observability | Covered by read-only local observability contract. |
| `/api/admin/wecom-customer-acquisition-links` | closed_next_wecom_customer_acquisition | Covered by safe-mode read/create API with real WeCom blocked. |
| `/api/admin/wecom-customer-acquisition-links/{link_id}` | closed_next_wecom_customer_acquisition | Covered by safe-mode detail/update/delete API. |
| `/api/admin/wecom-customer-acquisition-links/{link_id}/{action}` | closed_next_wecom_customer_acquisition | Covered by safe-mode enable/disable/sync plan-only API; unknown action is controlled 410. |

## Final Acceptance Baseline

- Runtime `production_compat` route count: 0.
- Runtime wildcard legacy forward count: 0.
- Unknown owner count: 0.
- Undocumented route count: 0.
- Deleted-but-still-registered count: 0.
- Deferred frontend API whitelist count: 0.
- Representative smoke responses: no `X-AICRM-Compatibility-Facade`.
- Normal JSON contracts: `route_owner=ai_crm_next`, `fallback_used=false`, and `real_external_call_executed=false` when those fields are present.
