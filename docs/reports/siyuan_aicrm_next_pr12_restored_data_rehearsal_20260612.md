# siyuan AI-CRM baseline PR-12 restored-data rehearsal - 2026-06-12

## 1. Executive Summary

Conclusion: PASS_WITH_NOTES

PR-12 reran the same-server restored-data rehearsal against PR #87 head commit `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9`, using a fresh isolated release directory, isolated virtualenv, isolated restored database, isolated work directory, and local-only port `127.0.0.1:5016`.

The core rehearsal gates passed:

- restored DB was created from a production dump
- Alembic upgraded from the restored production revision to head
- `scripts/siyuan_migration/06_safe_next_schema_init.sql` completed safely
- expanded before/after data reconciliation passed for channel, automation, sidebar, identity/mobile, and config families
- core HTTP smoke passed
- the rehearsal app listened only on `127.0.0.1:5016` and was stopped after smoke

Note: `GET /api/admin/commerce/transactions` is recorded as `SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST`. Current siyuan transaction management has no core historical data, so the missing empty transaction-list compatibility endpoint is not a PR-12 merge gate. No compatibility shell route was added.

No PR #87 or PR #88 merge was performed. No push to `main` was performed. No production service restart or reload was performed. No production nginx, systemd, deploy unit, deploy workflow, production env, or production database schema/data change was performed.

## 2. Execution Context

- execution time: `2026-06-12 CST`
- server hostname: `iv-yelatkuuwwqbxyvtieq5`
- server user: `ubuntu`
- release directory: `/home/ubuntu/releases/siyuan-aicrm-baseline-b1e601b-pr12-rerun2`
- virtualenv directory: `/home/ubuntu/venvs/siyuan-aicrm-baseline-b1e601b-pr12-rerun2`
- work directory: `/home/ubuntu/pr12-rehearsal-work-20260612-rerun2`
- git commit under rehearsal: `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9`
- rehearsal DB name: `siyuan_aicrm_pr12_restored_20260612_rerun2`
- rehearsal port: `5016`
- PR-11 source branch: `codex/siyuan-pr11-rebase-to-aicrm-baseline`
- PR-12 branch: `codex/siyuan-pr12-restored-data-rehearsal`

## 3. Production Boundary Check

| boundary | result | notes |
|---|---|---|
| PR #87 merge | not performed | PR #87 remains independent and unmerged |
| PR #88 merge | not performed | PR #88 remains Draft/open |
| push to `main` | not performed | PR-12 work stays on a separate branch |
| `.github/workflows/deploy.yml` | not modified | PR-12 does not alter main-push production deploy behavior |
| `deploy/` | not modified | PR-12 does not alter deploy units or scripts |
| production systemd | not touched | no restart, reload, enable, disable, or unit edit |
| production nginx | not touched | no config edit or reload |
| production DB | read-only dump only | no migration, init, schema change, truncate, delete, drop, or update on production |
| production directory | not modified | `/home/ubuntu/极简 crm` was only observed |
| old isolated resources | not touched | previous `94f1bbb` and `rerun1` isolated resources were left intact |
| secrets/raw identifiers | not recorded | no full DB URL, token, secret, private key, raw contact ID, phone, customer ID, or order ID is written in this report |

## 4. Preflight

| check | result | notes |
|---|---|---|
| hostname / user observed | PASS | `iv-yelatkuuwwqbxyvtieq5` / `ubuntu` |
| production service observed only | PASS | current service was checked without restart or reload |
| production directory read-only check | PASS | `/home/ubuntu/极简 crm` was not modified |
| `127.0.0.1:5016` free | PASS | port was free before starting rehearsal |
| new release directory absent | PASS | absent before creation |
| new venv directory absent | PASS | absent before creation |
| new work directory absent | PASS | absent before creation |
| new restored DB absent | PASS | absent before creation |
| deploy workflow / deploy unchanged | PASS | no production deployment files were modified |

## 5. Dump / Restore Method

- production DB was dumped with `pg_dump --format=custom --no-owner --no-acl`
- restored DB was created as `siyuan_aicrm_pr12_restored_20260612_rerun2`
- dump was restored with `pg_restore --no-owner --no-acl`
- dump file was deleted after successful restore
- cleanup also confirmed no dump was left behind

## 6. Environment Validation

| check | result | notes |
|---|---|---|
| release directory creation | PASS | isolated release directory created |
| checkout fixed commit | PASS | checked out `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9` |
| venv creation | PASS | isolated venv created |
| dependency install | PASS | requirements installed in isolated venv |
| restored DB creation | PASS | created `siyuan_aicrm_pr12_restored_20260612_rerun2` |
| dump restore | PASS | restored into isolated DB |
| dump deletion | PASS | dump no longer exists |
| `python -m compileall` | PASS | local code validation completed on server release |
| `python app.py health` | PASS | returned healthy status |
| `python app.py routes` | PASS | route inventory was generated |
| Alembic `upgrade head` | PASS | restored DB upgraded to head |
| safe Next schema init | PASS | `scripts/siyuan_migration/06_safe_next_schema_init.sql` completed |

## 7. Migration Result

The previous Alembic blocker is fixed by PR #87 commit `b1e601ba`. During this rerun, Alembic successfully traversed from the restored production revision through the merge revisions to `0038_merge_duplicate_channel_wechat_shop_heads`.

Observed upgrade path included:

- `0035_wechat_shop_refunds -> 0036_channel_multi_staff_assignment`
- `0036_channel_multi_staff_assignment, 0036_wechat_shop_sync_runs -> 0037_merge_channel_multi_staff_and_wechat_shop_heads`
- `0036_channel_multi_staff_assignment, 0036_wechat_shop_sync_runs -> 0037_merge_channel_wechat_shop_heads`
- `0037_merge_channel_wechat_shop_heads, 0037_merge_channel_multi_staff_and_wechat_shop_heads, 0037_channel_multi_staff_assignment -> 0038_merge_duplicate_channel_wechat_shop_heads`

## 8. Data Reconciliation

Expanded before/after reconciliation passed. The script automatically enumerated existing relevant tables and compared row counts, non-null sensitive-field counts, distinct/key counts where safe, and hashed distribution signatures for status/type/command-like fields. It did not print raw `scene_value`, `external_userid`, mobile, `openid`, `unionid`, customer ID, contact ID, token, secret, or raw payload values.

| category | result | tables checked | metrics checked | missing seed/table metrics |
|---|---|---:|---:|---:|
| channel / channel source | PASS | 14 | 82 | 3 |
| automation operations | PASS | 91 | 425 | 2 |
| sidebar | PASS | 10 | 39 | 0 |
| identity | PASS | 22 | 93 | 5 |
| mobile | PASS | 19 | 90 | 2 |
| config | PASS | 16 | 79 | 0 |

Interpretation:

- channel code/source/radar/assignment related data did not lose rows or non-null identity signals
- automation/group_ops/workflow/task/member/program/broadcast/followup related data did not lose rows or status/type distribution signatures
- sidebar/MCP/assistant/operation related tables did not lose rows or command/status/type distribution signatures
- customer/contact/identity/mobile/openid/unionid/external_userid related counts and non-null signals did not regress
- config/setting/feature/integration/material/media related counts and safe key counts did not regress

## 9. Runtime V2 / Commerce / WeChat Shop Validation

| check | result | notes |
|---|---|---|
| runtime v2 schema after safe init | PASS | safe init completed without error |
| runtime route map | PASS | `GET /api/system/runtime-route-map` returned 200 |
| commerce / WeChat Shop schema after safe init | PASS | safe init completed and WeChat Shop sync-runs route returned 200 |
| WeChat Shop route smoke | PASS | `GET /api/admin/wechat-shop/sync-runs` returned 200 |
| transaction list API | SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST | `GET /api/admin/commerce/transactions` returned 404 and is not a merge gate under the adjusted PR-12 scope |

## 10. WeCom / Sidebar Validation

| check | result | notes |
|---|---|---|
| channel runtime diagnosis | PASS | `GET /api/admin/channels/runtime-diagnosis?scene_value=<TEST_PLACEHOLDER>` returned 200 |
| WeCom tags gate | PASS | `GET /api/admin/wecom/tags/live/gate` returned 200 |
| channel assignee API | PASS | `GET /api/admin/channels/<channel_id>/assignees` returned 200; raw ID was not recorded |
| sidebar JSSDK API | PASS | `GET /api/sidebar/jssdk-config?url=<LOCAL_SIDEBAR_URL>` returned 200 |
| sidebar MCP/config API | PASS | `GET /api/admin/config/mcp-tools` returned 200 |
| raw sidebar read APIs | NOTE | naked sidebar read endpoints return controlled 400/503 without a real sidebar identity context and were not used as the no-raw-ID smoke gate |

## 11. HTTP Smoke

HTTP smoke was run only against `http://127.0.0.1:5016`. `/health` required `200`. Core endpoints allowed only `200`, `204`, `301`, `302`, `401`, or `403`. `404`, `405`, `000`, and `5xx` remain hard failures for core endpoints.

| name | endpoint | status | result |
|---|---|---:|---|
| health | `/health` | 200 | PASS |
| admin root | `/admin` | 200 | PASS |
| customers list | `/api/customers` | 200 | PASS |
| channel sources | `/api/admin/channels` | 200 | PASS |
| automation programs | `/api/admin/automation-conversion/programs` | 200 | PASS |
| automation group ops | `/api/admin/automation-conversion/group-ops/plans` | 200 | PASS |
| sidebar JSSDK | `/api/sidebar/jssdk-config?url=<LOCAL_SIDEBAR_URL>` | 200 | PASS |
| sidebar MCP config | `/api/admin/config/mcp-tools` | 200 | PASS |
| channel assignees | `/api/admin/channels/<channel_id>/assignees` | 200 | PASS |
| runtime route map | `/api/system/runtime-route-map` | 200 | PASS |
| WeChat Shop sync runs | `/api/admin/wechat-shop/sync-runs` | 200 | PASS |
| WeCom runtime diagnosis | `/api/admin/channels/runtime-diagnosis?scene_value=<TEST_PLACEHOLDER>` | 200 | PASS |
| WeCom tags live gate | `/api/admin/wecom/tags/live/gate` | 200 | PASS |
| commerce transactions | `/api/admin/commerce/transactions` | 404 | SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST |

## 12. Rehearsal App Isolation

| check | result | notes |
|---|---|---|
| bind address | PASS | listener check confirmed only `127.0.0.1:5016` |
| forbidden bind addresses | PASS | no `0.0.0.0:5016` or `[::]:5016` listener was observed |
| background jobs / workers / outbound dispatch | PASS_WITH_NOTES | script set known disable switches and launched only the local web process; no external dispatch was intentionally triggered |
| app stop cleanup | PASS | rehearsal app was stopped |
| final port release | PASS | post-cleanup verification confirmed `5016` free |

## 13. Notes

`GET /api/admin/commerce/transactions` remains absent from the current route surface and returned 404 during smoke. Under the adjusted PR-12 scope, this is recorded as `SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST` because current siyuan transaction management has no core historical data and this empty-list compatibility endpoint is not a merge gate.

No compatibility shell route was added for this endpoint.

## 14. Security Statement

- no env file committed
- no dump committed
- no dump retained on the server after restore
- no uploads, instance files, pem, or key material committed
- no secrets printed into this report
- no full DB URL printed into this report
- no raw production contact ID, scene value, mobile, union ID, open ID, customer ID, contact ID, or order ID recorded
- no production DB writes were performed
- no production service restart or reload was performed
- no production nginx/systemd/env/deploy workflow change was performed
- rehearsal app was stopped; port `5016` was free after cleanup

## 15. Conclusion and Next Step

Conclusion: PASS_WITH_NOTES

PR-12 core restored-data rehearsal gates are satisfied under the adjusted acceptance criteria.

Recommended next step:

- keep PR #87 and PR #88 unmerged until the operator explicitly approves the next phase
- then proceed to temporarily disable production deploy workflow, merge PR #87, and start PR-13 blue-green cutover
