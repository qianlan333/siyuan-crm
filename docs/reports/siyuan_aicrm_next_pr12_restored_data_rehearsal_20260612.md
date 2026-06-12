# siyuan AI-CRM baseline PR-12 restored-data rehearsal - 2026-06-12

## 1. Executive Summary

Conclusion: FAIL

PR-12 reran the same-server restored-data rehearsal for PR #87 head commit `94f1bbbfdce75376e407593f4a865622c77d914d` using an isolated release directory, isolated virtualenv, isolated restored database, and intended local-only port `127.0.0.1:5016`.

The rehearsal progressed past checkout, dependency install, restored DB creation, production dump, restore, pre-migration data counts, compile, health, and route inventory. It failed at `alembic upgrade head` because the restored production data contains Alembic revision `0037_channel_multi_staff_assignment`, while PR #87 head cannot locate that revision.

Follow-up fix recorded after this failed rehearsal: PR #87 branch commit `b1e601ba` restores `migrations/versions/0037_channel_multi_staff_assignment.py` and connects it into the final Alembic merge revision. This report conclusion remains `FAIL` until PR-12 is rerun successfully against a clean isolated rehearsal environment.

No PR #87 merge was performed. No push to `main` was performed. No production service restart or reload was performed. No production nginx, systemd, deploy unit, deploy workflow, production env, or production database schema/data change was performed.

## 2. Execution Context

- execution time: `2026-06-12 CST`
- server hostname: `iv-yelatkuuwwqbxyvtieq5`
- server user: `ubuntu`
- release directory: `/home/ubuntu/releases/siyuan-aicrm-baseline-94f1bbb`
- virtualenv directory: `/home/ubuntu/venvs/siyuan-aicrm-baseline-94f1bbb`
- git commit under rehearsal: `94f1bbbfdce75376e407593f4a865622c77d914d`
- rehearsal DB name: `siyuan_aicrm_pr12_restored_20260612`
- intended rehearsal port: `5016`
- PR-11 source branch: `codex/siyuan-pr11-rebase-to-aicrm-baseline`
- PR-12 branch: `codex/siyuan-pr12-restored-data-rehearsal`

## 3. Production Boundary Check

| boundary | result | notes |
|---|---|---|
| PR #87 merge | not performed | PR #87 remains independent and unmerged |
| push to `main` | not performed | PR-12 work stays on a separate branch |
| `.github/workflows/deploy.yml` | not modified | PR-12 does not alter main-push production deploy behavior |
| `deploy/` | not modified | PR-12 does not alter deploy units or scripts |
| production systemd | not touched | no restart, reload, enable, disable, or unit edit |
| production nginx | not touched | no config edit or reload |
| production DB | read-only dump only | no migration, init, schema change, truncate, delete, drop, or update on production |
| production directory | not modified | `/home/ubuntu/极简 crm` was only observed |
| secrets/raw identifiers | not recorded | no full DB URL, token, secret, private key, raw contact ID, phone, customer ID, or order ID is written in this report |

## 4. Dump / Restore Method

- production DB was dumped with `pg_dump --format=custom --no-owner --no-acl`
- restored DB was created as `siyuan_aicrm_pr12_restored_20260612`
- dump was restored with `pg_restore --no-owner --no-acl`
- dump file was deleted after successful restore
- a cleanup trap also removes the dump file if any later step fails

## 5. Environment Validation

| check | result | notes |
|---|---|---|
| production service observation | PASS | service was active; no restart or reload |
| production health observation | PASS | current production health returned `ok=true` |
| release directory creation | PASS | isolated release directory created |
| checkout fixed commit | PASS | checked out `94f1bbbfdce75376e407593f4a865622c77d914d` |
| venv creation | PASS | isolated venv created |
| dependency install | PASS | requirements installed in isolated venv |
| restored DB creation | PASS | created `siyuan_aicrm_pr12_restored_20260612` |
| dump restore | PASS | restored into isolated DB |
| dump deletion | PASS | dump no longer exists |
| `python -m compileall` | PASS | local code validation completed on server release |
| `python app.py health` | PASS | returned `default_runtime=ai_crm_next` and `route_owner=ai_crm_next` |
| `python app.py routes` | PASS | route inventory was generated |
| Alembic `upgrade head` | FAIL | missing revision `0037_channel_multi_staff_assignment` |

## 6. Restored DB Validation

| validation item | result | notes |
|---|---|---|
| production dump generated | PASS | production DB was read for dump only |
| dump restored to rehearsal DB | PASS | restored DB exists |
| migration to head on restored DB | FAIL | Alembic cannot locate revision `0037_channel_multi_staff_assignment` |
| safe Next schema init | not run | blocked by Alembic failure |
| existing business data preservation | not fully verified | before counts collected; after counts not collected because migration failed |

## 7. Data Reconciliation

Before counts were collected from the restored DB after restore and before migration. After counts were not collected because `alembic upgrade head` failed.

| data family | before count signal | after count | result | notes |
|---|---:|---:|---|---|
| customers / contacts | `contacts=3374`, Next snapshots present | not collected | BLOCKED_BY_ALEMBIC | no destructive mutation observed |
| channel codes / channel sources | missing/zero tables observed | not collected | BLOCKED_BY_ALEMBIC | schema baseline not reached |
| WeCom bindings | source tables not found by generic list | not collected | BLOCKED_BY_ALEMBIC | no raw IDs recorded |
| transactions / orders | commerce/order tables missing or zero in generic list | not collected | BLOCKED_BY_ALEMBIC | no raw order IDs recorded |
| automation / broadcast jobs | broadcast/runtime tables present with zero counts | not collected | BLOCKED_BY_ALEMBIC | no worker started |
| material library / mini program cover data | source tables not found by generic list | not collected | BLOCKED_BY_ALEMBIC | schema baseline not reached |
| service staff / assignee / assignment data | source tables not found by generic list | not collected | BLOCKED_BY_ALEMBIC | schema baseline not reached |
| authorization-related data, if present | source tables not found by generic list | not collected | BLOCKED_BY_ALEMBIC | schema baseline not reached |

## 8. Runtime V2 / Commerce / WeChat Shop Validation

| check | result | notes |
|---|---|---|
| runtime v2 schema after safe init | not run | blocked by Alembic failure |
| commerce / WeChat Shop schema after safe init | not run | blocked by Alembic failure |
| WeChat Shop order/refund core tables usable | not run | blocked by Alembic failure |
| rehearsal-only webhook smoke | not run | app was not started |

## 9. WeCom Ability Validation

| check | result | notes |
|---|---|---|
| WeCom auth readiness | not run | app was not started |
| multi-WeCom service-staff API load | not run | app was not started |
| assignee / assignment API access | not run | app was not started |
| PATCH status-only behavior | not run | app was not started |
| raw identifier handling | not exercised | no raw production identifier was used or written |

## 10. HTTP Smoke

HTTP smoke did not run because the rehearsal app was not started after the Alembic failure.

| endpoint family | result | notes |
|---|---|---|
| `GET /health` on `127.0.0.1:5016` | not run | app was not started |
| customer list/detail APIs | not run | app was not started |
| channel source APIs | not run | app was not started |
| transaction/order APIs | not run | app was not started |
| automation/broadcast config APIs | not run | app was not started |
| multi-WeCom service-staff APIs | not run | app was not started |
| runtime v2 APIs | not run | app was not started |
| commerce / WeChat Shop APIs | not run | app was not started |

## 11. Failure Detail

Alembic failed with:

```text
Can't locate revision identified by '0037_channel_multi_staff_assignment'
```

Interpretation:

- the restored production DB records an Alembic revision named `0037_channel_multi_staff_assignment`
- PR #87 head does not provide a migration with that exact revision identifier
- this prevents the restored production DB from upgrading to the PR #87 baseline

Root cause:

- PR-11 baseline rebase accidentally omitted the siyuan production migration file that current main already carried: `migrations/versions/0037_channel_multi_staff_assignment.py`
- the restored DB was valid; the PR #87 migration graph was incomplete for a production-restored database

Follow-up fix:

- PR #87 branch commit `b1e601ba` restored `0037_channel_multi_staff_assignment.py`
- the restored revision keeps `revision = "0037_channel_multi_staff_assignment"`
- the restored revision keeps `down_revision = "0036_wechat_shop_sync_runs"`
- `0038_merge_duplicate_channel_wechat_shop_heads` now includes `0037_channel_multi_staff_assignment` as a parent so the restored production revision can upgrade to the current head
- Alembic graph tests were updated to cover revision locate, the `0036_wechat_shop_sync_runs -> 0037_channel_multi_staff_assignment` chain, upgrade path resolution from the restored production revision, and idempotent SQL guards

## 12. Security Statement

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
- rehearsal app was not left running; port `5016` was free after failure

## 13. Conclusion and Next Step

Conclusion: FAIL

PR #87 must not be merged based on this PR-12 result.

Required next step:

- rerun PR-12 restored-data rehearsal after the `b1e601ba` Alembic compatibility fix
- do not run the original absent-path script unchanged because the failed rehearsal already created:
  - `/home/ubuntu/releases/siyuan-aicrm-baseline-94f1bbb`
  - `/home/ubuntu/venvs/siyuan-aicrm-baseline-94f1bbb`
  - `siyuan_aicrm_pr12_restored_20260612`
- before rerun, either safely remove only those isolated rehearsal resources or use a new suffix for release, venv, and restored DB
- rerun must still avoid production directory, production DB mutation, deploy workflow, systemd, nginx, and env changes
- only if rerun returns `PASS` or `PASS_WITH_NOTES`, proceed to temporarily disable production deploy workflow, merge PR #87, then continue to PR-13 blue-green cutover
