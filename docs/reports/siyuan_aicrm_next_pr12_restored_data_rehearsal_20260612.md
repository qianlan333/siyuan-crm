# siyuan AI-CRM baseline PR-12 restored-data rehearsal - 2026-06-12

## 1. Executive Summary

Conclusion: FAIL

PR-12 reran the same-server restored-data rehearsal against PR #87 head commit `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9`, using a fresh isolated release directory, isolated virtualenv, isolated restored database, isolated work directory, and local-only port `127.0.0.1:5016`.

This rerun confirms that the previous Alembic blocker is fixed: the restored production DB can locate `0037_channel_multi_staff_assignment`, `alembic upgrade head` succeeds, safe Next schema init succeeds, and before/after data counts reconcile.

The rehearsal still fails because required HTTP smoke for `GET /api/admin/commerce/transactions` returns `404`. The route inventory contains `GET /api/admin/wechat-pay/transactions` and WeChat Shop routes, but not the requested commerce transactions endpoint. Under the PR-12 acceptance rule, `404` is a hard failure.

No PR #87 or PR #88 merge was performed. No push to `main` was performed. No production service restart or reload was performed. No production nginx, systemd, deploy unit, deploy workflow, production env, or production database schema/data change was performed.

## 2. Execution Context

- execution time: `2026-06-12 CST`
- server hostname: `iv-yelatkuuwwqbxyvtieq5`
- server user: `ubuntu`
- release directory: `/home/ubuntu/releases/siyuan-aicrm-baseline-b1e601b-pr12-rerun1`
- virtualenv directory: `/home/ubuntu/venvs/siyuan-aicrm-baseline-b1e601b-pr12-rerun1`
- work directory: `/home/ubuntu/pr12-rehearsal-work-20260612-rerun1`
- git commit under rehearsal: `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9`
- rehearsal DB name: `siyuan_aicrm_pr12_restored_20260612_rerun1`
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
| old isolated resources | not touched | previous `94f1bbb` release, venv, work dir, and restored DB were left intact |
| secrets/raw identifiers | not recorded | no full DB URL, token, secret, private key, raw contact ID, phone, customer ID, or order ID is written in this report |

## 4. Preflight

| check | result | notes |
|---|---|---|
| hostname / user observed | PASS | `iv-yelatkuuwwqbxyvtieq5` / `ubuntu` |
| production service observed only | PASS | current service was checked without restart or reload |
| production health observed only | PASS | `/health` returned `ok=true` |
| production directory read-only check | PASS | `/home/ubuntu/极简 crm` was not modified |
| `127.0.0.1:5016` free | PASS | port was free before starting rehearsal |
| new release directory absent | PASS | absent before creation |
| new venv directory absent | PASS | absent before creation |
| new work directory absent | PASS | absent before creation |
| new restored DB absent | PASS | absent before creation |
| deploy workflow / deploy unchanged | PASS | no production deployment files were modified |

## 5. Dump / Restore Method

- production DB was dumped with `pg_dump --format=custom --no-owner --no-acl`
- restored DB was created as `siyuan_aicrm_pr12_restored_20260612_rerun1`
- dump was restored with `pg_restore --no-owner --no-acl`
- dump file was deleted after successful restore
- a cleanup trap also removes the dump file if any later step fails

## 6. Environment Validation

| check | result | notes |
|---|---|---|
| release directory creation | PASS | isolated release directory created |
| checkout fixed commit | PASS | checked out `b1e601baab56bb8e6713a7b2a3646bfdf331d0e9` |
| venv creation | PASS | isolated venv created |
| dependency install | PASS | requirements installed in isolated venv |
| restored DB creation | PASS | created `siyuan_aicrm_pr12_restored_20260612_rerun1` |
| dump restore | PASS | restored into isolated DB |
| dump deletion | PASS | dump no longer exists |
| `python -m compileall` | PASS | local code validation completed on server release |
| `python app.py health` | PASS | returned healthy status |
| `python app.py routes` | PASS | route inventory was generated |
| Alembic `upgrade head` | PASS | restored DB upgraded to head |
| safe Next schema init | PASS | `scripts/siyuan_migration/06_safe_next_schema_init.sql` completed |

## 7. Migration Result

The previous PR-12 failure was:

```text
Can't locate revision identified by '0037_channel_multi_staff_assignment'
```

That blocker is now fixed by PR #87 commit `b1e601ba`. During this rerun, Alembic successfully traversed from the restored production revision through the merge revisions to `0038_merge_duplicate_channel_wechat_shop_heads`.

Observed upgrade path included:

- `0035_wechat_shop_refunds -> 0036_channel_multi_staff_assignment`
- `0036_channel_multi_staff_assignment, 0036_wechat_shop_sync_runs -> 0037_merge_channel_multi_staff_and_wechat_shop_heads`
- `0036_channel_multi_staff_assignment, 0036_wechat_shop_sync_runs -> 0037_merge_channel_wechat_shop_heads`
- `0037_merge_channel_wechat_shop_heads, 0037_merge_channel_multi_staff_and_wechat_shop_heads, 0037_channel_multi_staff_assignment -> 0038_merge_duplicate_channel_wechat_shop_heads`

## 8. Data Reconciliation

Before and after counts matched. Missing tables are recorded as `missing` and are not treated as failures by the rehearsal script. Any SQL count error would have failed the run.

| data family | before signal | after signal | result |
|---|---:|---:|---|
| customers / contacts | `contacts=3374`, `customer_list_index_next=3372`, `customer_detail_snapshot_next=3372` | unchanged | PASS |
| channel codes / channel sources | source tables missing, `radar_links=0` | unchanged | PASS |
| WeCom bindings | generic source tables missing | unchanged | PASS |
| transactions / orders | generic commerce/order tables missing, `wechat_shop_refunds=0` | unchanged | PASS |
| automation / broadcast jobs | `broadcast_jobs=0`, runtime v2 tables zero | unchanged | PASS |
| material library / mini program cover data | generic source tables missing | unchanged | PASS |
| service staff / assignee / assignment data | generic source tables missing, automation assignment tables zero | unchanged | PASS |
| authorization-related data, if present | generic source tables missing | unchanged | PASS |

## 9. Runtime V2 / Commerce / WeChat Shop Validation

| check | result | notes |
|---|---|---|
| runtime v2 schema after safe init | PASS | safe init completed without error |
| commerce / WeChat Shop schema after safe init | PASS_WITH_NOTES | safe init completed; HTTP smoke later exposed a missing required commerce route |
| WeChat Shop order/refund core tables usable | PARTIAL | route inventory includes WeChat Pay and WeChat Shop routes; required commerce transactions smoke failed |
| rehearsal-only webhook smoke | not reached | smoke stopped at first hard failure |

## 10. WeCom Ability Validation

| check | result | notes |
|---|---|---|
| multi-WeCom service-staff API route inventory | PARTIAL | route inventory was generated, but smoke stopped before assignment endpoints |
| assignee / assignment API access | not reached | smoke stopped at required commerce endpoint failure |
| PATCH status-only behavior | not reached | smoke stopped at required commerce endpoint failure |
| raw identifier handling | PASS | no raw production identifier was used or written |

## 11. HTTP Smoke

HTTP smoke was run only against `http://127.0.0.1:5016`. `/health` required `200`. Other endpoints allowed only `200`, `204`, `301`, `302`, `401`, or `403`. `404`, `405`, `000`, and `5xx` are failures.

| name | endpoint | status | result |
|---|---|---:|---|
| health | `/health` | 200 | PASS |
| admin root | `/admin` | 200 | PASS |
| customers list | `/api/customers` | 200 | PASS |
| channel sources | `/api/admin/channels` | 200 | PASS |
| transactions | `/api/admin/commerce/transactions` | 404 | FAIL |

Smoke stopped at the first hard failure. The remaining requested endpoints were not executed in this run:

- `/api/admin/group-ops/plans`
- `/api/admin/channels/staff-assignments`
- `/api/admin/automation/runtime-v2/programs`
- `/api/admin/commerce/wechat-shop/orders`

Route inventory evidence:

- `GET /api/admin/wechat-pay/transactions` exists
- `GET /api/admin/wechat-shop/events` exists
- `POST /api/admin/wechat-shop/orders/{order_id}/sync` exists
- `GET /api/admin/wechat-shop/sync-runs` exists
- `GET /api/admin/commerce/transactions` was not present in the generated route inventory

## 12. Rehearsal App Isolation

| check | result | notes |
|---|---|---|
| bind address | PASS | listener check confirmed only `127.0.0.1:5016` |
| forbidden bind addresses | PASS | no `0.0.0.0:5016` or `[::]:5016` listener was observed |
| background jobs / workers / outbound dispatch | PASS_WITH_NOTES | script set known disable switches and launched only the local web process; no external dispatch was intentionally triggered |
| app stop cleanup | PASS_WITH_NOTES | cleanup stopped the parent process; a child `app.py run` process remained and was then manually stopped |
| final port release | PASS | post-cleanup verification confirmed `5016` free |

## 13. Failure Detail

Failure:

```text
GET /api/admin/commerce/transactions -> 404
```

Interpretation:

- restored DB migration compatibility is now verified
- safe init is now verified
- preserved data count reconciliation is now verified
- runtime startup and local-only binding are verified
- PR-12 still cannot pass because the required transaction smoke endpoint is absent from the current PR #87 route surface

This must be resolved before PR #87 can be merged and before PR-13 can begin.

## 14. Security Statement

- no env file committed
- no dump committed
- no dump retained on the server after restore
- no uploads, instance files, pem, or key material committed
- no secrets printed into this report
- no full DB URL printed into this report
- no raw production contact ID, scene value, mobile, union ID, open ID, customer ID, or order ID recorded
- no production DB writes were performed
- no production service restart or reload was performed
- no production nginx/systemd/env/deploy workflow change was performed
- rehearsal app was stopped; port `5016` was free after cleanup

## 15. Conclusion and Next Step

Conclusion: FAIL

PR #87 must not be merged based on this PR-12 result.

Required next step:

- fix the PR #87 route/API contract mismatch for the required transaction smoke endpoint, or explicitly revise the PR-12 acceptance endpoint list before rerun
- rerun PR-12 restored-data rehearsal with another fresh suffix, or after an explicitly approved cleanup of isolated rerun resources
- continue to avoid production directory, production DB mutation, deploy workflow, systemd, nginx, and env changes
- only if rerun returns `PASS` or `PASS_WITH_NOTES`, proceed to temporarily disable production deploy workflow, merge PR #87, then continue to PR-13 blue-green cutover
