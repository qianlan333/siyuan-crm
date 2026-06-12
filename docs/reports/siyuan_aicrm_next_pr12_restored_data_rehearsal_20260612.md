# siyuan AI-CRM baseline PR-12 restored-data rehearsal - 2026-06-12

## 1. Executive Summary

Conclusion: BLOCKED

PR-12 was intended to validate PR #87 head commit `94f1bbbfdce75376e407593f4a865622c77d914d` in an isolated same-server restored-data rehearsal environment. The available production-server access is a forced-command read-only channel. It exposes status, health, file listing, and read-only SQL helpers, but it does not provide the write-capable operations required to create an independent release directory, virtualenv, restored database, local port service, or migration run.

No PR #87 merge was performed. No push to `main` was performed. No production service restart or reload was performed. No production nginx, systemd, deploy unit, deploy workflow, production env, or production database schema/data change was performed.

## 2. Execution Context

- execution time: `2026-06-12 17:49 CST`
- server hostname: `VM-0-17-ubuntu`
- access mode observed: forced-command sandbox, `mode=read-only`
- server DB user observed: `claude_ro`, read-only transactions
- target release directory: `/home/ubuntu/releases/siyuan-aicrm-baseline-94f1bbb`
- git commit under rehearsal: `94f1bbbfdce75376e407593f4a865622c77d914d`
- intended rehearsal DB name: `siyuan_aicrm_pr12_restored_20260612`
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
| production DB | read-only observation only | no migration, init, schema change, truncate, delete, drop, or restore |
| secrets/raw identifiers | not recorded | no full DB URL, token, secret, private key, raw contact ID, phone, customer ID, or order ID is written in this report |

## 4. Intended Dump / Restore Method

The rehearsal was planned to use an independent restored database:

- create a new database named `siyuan_aicrm_pr12_restored_20260612`
- generate a production dump without changing production data
- restore into the rehearsal database with owner and ACL stripping, for example `--no-owner --no-acl`
- point the rehearsal app only at the restored database
- bind the rehearsal HTTP service to `127.0.0.1:5016`
- run all smoke checks against `127.0.0.1:5016`

This was not executed because the available production channel is read-only and cannot create a database, write a dump, restore a dump, or start a rehearsal process.

## 5. Environment Validation

| check | result | notes |
|---|---|---|
| create release directory | BLOCKED | read-only sandbox cannot create `/home/ubuntu/releases/siyuan-aicrm-baseline-94f1bbb` |
| checkout fixed commit | BLOCKED | read-only sandbox cannot run a normal shell checkout into the new release directory |
| create venv | BLOCKED | read-only sandbox cannot create files under the target release |
| install dependencies | BLOCKED | requires the venv and write-capable shell |
| `python -m compileall` | BLOCKED | release checkout and venv were not created |
| `python app.py health` | BLOCKED | release checkout and venv were not created |
| `python app.py routes` | BLOCKED | release checkout and venv were not created |
| Alembic heads/current/upgrade head | BLOCKED | restored DB was not created |

Observed read-only production health returned an OK Next runtime with PostgreSQL and legacy runtime disabled. This is production status evidence only; it is not a PR-12 rehearsal result.

## 6. Local Repository Validation

These checks were executed locally against the PR-12 branch and the existing local virtualenv. They validate the code checkout, but they do not replace the blocked same-server restored-data rehearsal.

| check | result | notes |
|---|---|---|
| `.venv/bin/python -m compileall app.py aicrm_next scripts tools tests` | PASS | local compile completed |
| `.venv/bin/python app.py health` | PASS | returned `default_runtime=ai_crm_next` and `route_owner=ai_crm_next` |
| `.venv/bin/python app.py routes > /tmp/pr12_routes.txt` | PASS | route output produced `631` lines |
| `.venv/bin/python -m pytest tests/test_alembic_revision_chain.py -q` | PASS | `7 passed` |
| core pytest set requested for PR-12 | PASS | `72 passed`, `7 skipped`, one Starlette deprecation warning |
| report secret/raw identifier scan | PASS | no full DB URL, secret, token, private key, raw contact ID, mobile, union ID, open ID, customer ID, or order ID pattern found in this report |

## 7. Restored DB Validation

| validation item | result | notes |
|---|---|---|
| production dump generated | BLOCKED | no write-capable dump path is available through the sandbox |
| dump restored to rehearsal DB | BLOCKED | sandbox cannot create or restore `siyuan_aicrm_pr12_restored_20260612` |
| migration to head on restored DB | BLOCKED | restored DB does not exist |
| `init-next-schema-safe` on restored DB | BLOCKED | restored DB does not exist |
| existing business data preservation | BLOCKED | migration and safe init were not run on a restored copy |

## 8. Data Reconciliation

| data family | before count | after count | result | notes |
|---|---:|---:|---|---|
| customers / contacts | not collected | not collected | BLOCKED | restored DB not available |
| channel codes / channel sources | not collected | not collected | BLOCKED | restored DB not available |
| WeCom bindings | not collected | not collected | BLOCKED | restored DB not available |
| transactions / orders | not collected | not collected | BLOCKED | restored DB not available |
| automation / broadcast jobs | not collected | not collected | BLOCKED | restored DB not available |
| material library / mini program cover data | not collected | not collected | BLOCKED | restored DB not available |
| service staff / assignee / assignment data | not collected | not collected | BLOCKED | restored DB not available |
| authorization-related data, if present | not collected | not collected | BLOCKED | restored DB not available |

No destructive or mutating query was run against production to obtain these counts.

## 9. Runtime V2 / Commerce / WeChat Shop Validation

| check | result | notes |
|---|---|---|
| runtime v2 schema exists after safe init | BLOCKED | restored DB not available |
| commerce / WeChat Shop schema exists after safe init | BLOCKED | restored DB not available |
| WeChat Shop order/refund core tables usable | BLOCKED | restored DB not available |
| rehearsal-only webhook smoke | BLOCKED | rehearsal app was not started |

## 10. WeCom Ability Validation

| check | result | notes |
|---|---|---|
| WeCom auth readiness | BLOCKED | rehearsal app was not started |
| multi-WeCom service-staff API load | BLOCKED | rehearsal app was not started |
| assignee / assignment API access | BLOCKED | rehearsal app was not started |
| PATCH status-only behavior | BLOCKED | rehearsal app was not started |
| raw identifier handling | not exercised | no raw production identifier was used or written |

## 11. HTTP Smoke

| endpoint family | result | notes |
|---|---|---|
| `GET /health` on `127.0.0.1:5016` | BLOCKED | rehearsal app was not started |
| route inventory | BLOCKED | rehearsal app was not started |
| customer list/detail APIs | BLOCKED | rehearsal app was not started |
| channel source APIs | BLOCKED | rehearsal app was not started |
| transaction/order APIs | BLOCKED | rehearsal app was not started |
| automation/broadcast config APIs | BLOCKED | rehearsal app was not started |
| multi-WeCom service-staff APIs | BLOCKED | rehearsal app was not started |
| runtime v2 APIs | BLOCKED | rehearsal app was not started |
| commerce / WeChat Shop APIs | BLOCKED | rehearsal app was not started |

## 12. Evidence Collected

- `ssh -T crm-prod whoami`: confirmed `user=ubuntu`, `host=VM-0-17-ubuntu`, and `mode=read-only`.
- `ssh -T crm-prod health`: confirmed the current production service is healthy and running the Next runtime.
- `ssh -T crm-prod pg-status`: confirmed PostgreSQL is accepting connections.
- `ssh -T crm-prod git-status`: confirmed the current production checkout is on `main`; no checkout or mutation was attempted.
- `ssh -T crm-prod ls /home/ubuntu/releases`: confirmed release directories are listable, but no new release directory was created.

These commands were read-only evidence gathering. They do not constitute restored-data rehearsal execution.

## 13. Failure / Skipped / Risk Items

| item | status | required fix |
|---|---|---|
| independent release directory | BLOCKED | provide an operator-controlled shell or a narrowly scoped sandbox command to create `/home/ubuntu/releases/siyuan-aicrm-baseline-94f1bbb` |
| independent venv | BLOCKED | provide write-capable rehearsal setup access that cannot affect production services |
| independent restored DB | BLOCKED | provide controlled DB admin path to create and restore `siyuan_aicrm_pr12_restored_20260612` from production dump |
| migration and safe init on restored DB | BLOCKED | run only against the restored DB after it is created |
| 127.0.0.1:5016 rehearsal app | BLOCKED | provide a non-systemd foreground or supervised rehearsal launch path isolated from production |
| HTTP smoke and data reconciliation | BLOCKED | rerun after restored DB and rehearsal app exist |

## 14. Security Statement

- no env file committed
- no dump committed
- no uploads, instance files, pem, or key material committed
- no secrets printed into this report
- no full DB URL printed into this report
- no raw production contact ID, scene value, mobile, union ID, open ID, customer ID, or order ID recorded
- no production DB writes were performed
- no production service restart or reload was performed
- no production nginx/systemd/env/deploy workflow change was performed

## 15. Conclusion and Next Step

Conclusion: BLOCKED

PR #87 must not be merged based on this PR-12 result. The required restored-data same-server rehearsal did not run because the available production access is read-only and cannot create the isolated release, venv, restored database, or local rehearsal app process.

Required next step before PR #87 merge:

- provide a write-capable but isolated operator path for PR-12 rehearsal, or extend the sandbox with explicit safe commands for:
  - creating the independent release directory
  - checking out commit `94f1bbbfdce75376e407593f4a865622c77d914d`
  - creating a new venv
  - creating and restoring `siyuan_aicrm_pr12_restored_20260612`
  - running migrations and safe init only on the restored DB
  - starting the rehearsal app only on `127.0.0.1:5016`
  - executing data reconciliation and HTTP smoke against the rehearsal environment

After PR-12 is rerun and returns `PASS` or `PASS_WITH_NOTES`, the recommended sequence remains: temporarily disable production deploy workflow, merge PR #87, then proceed to PR-13 blue-green cutover.
