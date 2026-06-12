# siyuan AI-CRM baseline PR-14 post-cutover observation - 2026-06-12

## 1. Executive Summary

Conclusion: OBSERVATION_PASS_WITH_NOTES

PR-14 observed the production service after the PR-13 manual blue-green cutover. The service is running main commit `97c9bf68c789500eb636607e6d3529d6ab9514a9`, GitHub `Deploy to Production` remains `disabled_manually`, nginx still proxies to `127.0.0.1:5001`, and no production rollback was triggered.

Core API smoke and core read-only data observation passed. The only application note is a non-core commerce summary probe returning 500 because `wechat_shop_orders` is not present in the current siyuan production schema. This is consistent with the adjusted PR-12/PR-13 scope where transaction-management compatibility is not a merge/cutover gate for the current siyuan data set.

PR-15 old asset cleanup was not started.

## 2. Observation Context

| item | value |
|---|---|
| observation time | `2026-06-12 20:15-20:20 CST` |
| hostname | `iv-yelatkuuwwqbxyvtieq5` |
| user | `ubuntu` |
| old commit | `a43da560dffdf11ffcd350368123e5bcf42ddf15` |
| new/current production commit | `97c9bf68c789500eb636607e6d3529d6ab9514a9` |
| current release | `/home/ubuntu/releases/siyuan-aicrm-main-97c9bf68` |
| current venv | `/home/ubuntu/venvs/siyuan-aicrm-main-97c9bf68` |
| production service port | `127.0.0.1:5001` |
| DB backup retained | `/home/ubuntu/pr13-db-backups/siyuan-prod-before-pr13-20260612T120516Z.dump` |
| rollback file retained | `/home/ubuntu/pr13-blue-green-work-20260612/rollback_commands.txt` |

## 3. Boundary Checks

| boundary | result | notes |
|---|---|---|
| GitHub `Deploy to Production` workflow | PASS | still `disabled_manually` |
| PR #88 | PASS | Draft/open/unmerged; evidence only |
| PR-15 | PASS | not started |
| old production directory/release/venv/env/logs | PASS | retained |
| DB backup and rollback file | PASS | retained |
| `.github/workflows/deploy.yml` | PASS | not modified |
| `deploy/` | PASS | not modified |
| systemd/nginx/env | PASS | not modified during observation |
| Alembic/safe init | PASS | not executed during observation |
| production restart/reload | PASS | not executed during observation |
| secrets/raw identifiers in report | PASS | not recorded |

No deploy workflow run targeting commit `97c9bf68c789500eb636607e6d3529d6ab9514a9` was observed.

## 4. Basic Status

| check | result | evidence |
|---|---|---|
| production service | PASS | `openclaw-wecom-postgres.service` active |
| nginx | PASS | active |
| PostgreSQL | PASS | active |
| `/health` | PASS | 200 |
| production listener | PASS | `127.0.0.1:5001` |
| current git/source commit | PASS | `97c9bf68c789500eb636607e6d3529d6ab9514a9` |
| health runtime owner | PASS | `ai_crm_next` |
| legacy runtime | PASS | `legacy_runtime_enabled=false` |

Health response summary:

| field | value |
|---|---|
| ok/status | `true` / `ok` |
| service | `aicrm-next` |
| database mode | `postgres` |
| fixture mode | `false` |
| production data ready | `true` |
| repository policy | `production_repositories_required` |

## 5. Core API Smoke

| endpoint | status | result |
|---|---:|---|
| `/health` | 200 | PASS |
| `/admin` | 200 | PASS |
| `/api/customers` | 200 | PASS |
| `/api/customers/<external_userid>` | 200 | PASS |
| `/admin/customers/<external_userid>` | 200 | PASS |
| `/api/admin/channels` | 200 | PASS |
| `/api/admin/automation-conversion/programs` | 200 | PASS |
| `/api/admin/automation-conversion/group-ops/plans` | 200 | PASS |
| `/api/sidebar/jssdk-config?url=<LOCAL_SIDEBAR_URL>` | 200 | PASS |
| `/api/admin/config/mcp-tools` | 200 | PASS |
| `/api/admin/channels/<channel_id>/assignees` | 200 | PASS |
| `/api/system/runtime-route-map` | 200 | PASS |
| `/api/admin/wechat-shop/sync-runs` | 200 | PASS |
| `/api/admin/channels/runtime-diagnosis?scene_value=<TEST_PLACEHOLDER>` | 200 | PASS |
| `/api/admin/wecom/tags/live/gate` | 200 | PASS |
| `/api/admin/commerce/transactions` | 404 | SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST |
| `/api/admin/customers/<external_userid>/commerce-summary` | 500 | NON_CORE_COMMERCE_NOTE |

Commerce notes:

- `GET /api/admin/commerce/transactions` remains `SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST`.
- `GET /api/admin/customers/<external_userid>/commerce-summary` returned 500 during observation because relation `wechat_shop_orders` does not exist. This was recorded as a non-core commerce note, not a rollback trigger, because the core customer detail API and admin customer detail page both returned 200.

## 6. Core Data Read-Only Observation

The observation used read-only aggregate checks only. It recorded counts, non-null signal counts, and distribution metrics. It did not record raw phone numbers, external identifiers, openids, unionids, customer IDs, contact IDs, order IDs, tokens, or secrets.

| category | result | tables checked | total rows | metrics checked | sensitive non-null signals | distribution metrics | missing seed metrics | zero-row tables |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| channel / qrcode / source | PASS | 11 | 532 | 85 | 2940 | 16 | 3 | 5 |
| automation / group ops | PASS | 89 | 1379 | 460 | 4714 | 103 | 2 | 69 |
| sidebar / MCP / assistant | PASS | 10 | 115 | 41 | 226 | 10 | 0 | 7 |
| identity / customers / contacts | PASS | 17 | 17905 | 98 | 64917 | 19 | 5 | 7 |
| mobile | PASS | 17 | 17905 | 95 | 64917 | 19 | 2 | 7 |
| config / settings / material | PASS | 16 | 143 | 81 | 286 | 11 | 0 | 9 |

No obvious zeroing, clearing, or identity/mobile loss signal was observed in the sampled aggregate checks.

## 7. Worker / Timer Status

| unit | status | notes |
|---|---|---|
| `openclaw-external-push-worker.timer` | active, enabled | existing timer remained active |
| `openclaw-external-push-worker.service` | inactive after successful run | last observed run exited `0/SUCCESS` |
| `openclaw-external-contact-sync.timer` | active, enabled | existing timer, observed only |
| `openclaw-external-contact-full-sync.timer` | active, enabled | existing timer, observed only |
| `openclaw-automation-conversion-due-runner.timer` | active, enabled | existing timer, observed only |

External push worker sampled output reported:

| metric | value |
|---|---:|
| scanned count | 0 |
| success count | 0 |
| skipped count | 0 |
| failed count | 0 |
| retry count | 0 |

No new worker or timer was installed, enabled, restarted, or modified during PR-14 observation.

## 8. Log Observation

Log scan scope:

- `openclaw-wecom-postgres.service` journal since cutover
- `openclaw-external-push-worker.service` journal since cutover
- recent nginx error log

Summary:

| signal | result | notes |
|---|---|---|
| import/module error | PASS | none observed |
| migration error | PASS | none observed |
| permission error | PASS | none observed |
| core DB error | PASS | none observed |
| core 5xx | PASS | none observed |
| external push failure | PASS | sampled runs scanned zero items and exited successfully |
| nginx upstream 5xx | PASS | none observed in sampled error log |
| non-core commerce summary 500 | NOTE | relation `wechat_shop_orders` does not exist |
| nginx external SSL handshake noise | NOTE | unrelated external client handshake errors existed before/around observation |

No rollback-triggering error was found.

## 9. Rollback Status

| item | value |
|---|---|
| rollback required | no |
| rollback triggered | no |
| rollback file retained | yes |
| DB backup retained | yes |
| old production assets retained | yes |

## 10. Recommendation

Keep GitHub `Deploy to Production` disabled until the operator explicitly decides how production deploys should be re-enabled or replaced.

Do not start PR-15 old asset cleanup immediately from this report alone. Recommended next action is to continue holding old assets, DB backup, rollback file, and disabled deploy workflow through an additional observation window, then schedule PR-15 cleanup only after operator acceptance.

## 11. Final Result

Conclusion: OBSERVATION_PASS_WITH_NOTES

Notes:

- Core production health, service status, API smoke, and aggregate data observation passed.
- `/api/admin/commerce/transactions` remains `SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST`.
- `/api/admin/customers/<external_userid>/commerce-summary` returned a non-core commerce 500 because `wechat_shop_orders` is absent.
- No rollback was triggered.
- PR-15 cleanup was not started.
