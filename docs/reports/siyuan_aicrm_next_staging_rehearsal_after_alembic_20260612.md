# siyuan AI-CRM Next Staging Rehearsal After Alembic Closeout - 2026-06-12

## Conclusion

`NO_GO`

Local static validation for PR-3 Alembic closeout passed, but the available
server entry is a read-only forced-command diagnostic sandbox. It does not
provide ordinary shell access, writable PostgreSQL access, `pg_dump` / restore
execution, Alembic upgrade execution, or a way to start a staging service.

Because the required staging DB rehearsal permissions were not available, this
PR records the blocker and does not claim a restored staging rehearsal pass.

## Execution Environment

- Repository: `qianlan333/siyuan-crm`
- Branch: `codex/siyuan-pr4-staging-rehearsal-after-alembic`
- Commit SHA: `4943971f4fdcc6f755752fd150110c25ccbe1e81`
- Python: `Python 3.13.7`
- Local PostgreSQL CLI: `psql (PostgreSQL) 16.13 (Homebrew)`
- Staging DB masked name: unavailable, staging DB was not provisioned from the
  available entry.
- Modified systemd/nginx: no
- Production cutover: no
- Production DB destructive action: no

## Initial Local Static Confirmation

```bash
git status --short
```

Result: clean.

```bash
git log --oneline -5
```

Result:

```text
4943971f PR-3: close Alembic revision graph (#75)
9ec400fc PR-2: add external orders read API (#74)
0d51e6d5 PR-1: Sync core AI-CRM Next native baseline into siyuan-crm (#73)
565fa2e8 Fix questionnaire WeChat OAuth identity resolution (#69)
d8df6498 Add contact description backfill (#72)
```

```bash
python3 -m compileall app.py aicrm_next scripts tools tests
```

Result: passed.

```bash
python3 app.py health
```

Result:

```text
{'ok': True, 'status_code': 200, 'default_runtime': 'ai_crm_next', 'route_owner': 'ai_crm_next'}
```

```bash
python3 -m pytest tests/test_alembic_revision_chain.py -q
```

Result:

```text
8 passed
```

```bash
python3 -m alembic heads
```

Result:

```text
0036_wechat_shop_sync_runs (head)
```

```bash
python3 -m alembic history --verbose > /tmp/pr4_alembic_history.txt
```

Result: passed, no missing parent / duplicate / multiple heads error.

## Server Entry Check

The configured server entry is a forced-command sandbox, not an ordinary shell.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 crm-prod 'echo PR4_SHELL_OK && pwd && whoami'
```

Result:

```text
unknown subcommand: echo
```

The repository-supported diagnostic wrapper confirms the read-only boundary:

```bash
scripts/prod.sh whoami
```

Result:

```text
user=ubuntu cwd=/home/ubuntu host=VM-0-17-ubuntu mode=read-only
pg-user: claude_ro (SELECT only, default_transaction_read_only=on)
allowed-services: openclaw-wecom-postgres nginx postgresql
allowed-log-prefixes: /var/log/ /home/ubuntu/极简 crm/logs/ /home/ubuntu/logs/
allowed-file-prefixes: /home/ubuntu/ /var/log/ /etc/nginx/
denied-file-patterns: *.env *.pem *.key *.pgpass *authorized_keys* *id_rsa* *id_ed25519*
```

## Env Present / Missing

Not available from the current entry.

Reason: the server entry is read-only forced-command access. It does not allow a
general shell, and env / key files are explicitly denied by sandbox policy.

No env values were printed or read.

## Backup Result

Not executed.

Reason: the current entry does not provide ordinary shell access or `pg_dump`
execution. The rehearsal requirement explicitly needs permission to execute
`scripts/siyuan_migration/01_backup_current_assets.sh`; that permission was not
available.

## Restore Result

Not executed.

Reason: the current entry does not provide staging DB creation/access,
`pg_restore`, writable PostgreSQL credentials, or a safe way to validate
`STAGING_DATABASE_URL`.

## Alembic Restored DB Result

Not executed on a restored staging DB.

Local graph validation passed:

- `python3 -m alembic heads` returned `0036_wechat_shop_sync_runs (head)`.
- `python3 -m alembic history --verbose` completed.
- `tests/test_alembic_revision_chain.py` passed.

Staging `alembic upgrade head` was not executed because no writable staging DB
entry was available.

Alembic stamp used: no.

## Safe Init Result

Not executed on staging.

Reason: staging DB restore was not available.

Local `python3 app.py health` passed, but that is not a substitute for restored
staging DB validation.

## Customer Projection Result

Not executed.

Required commands were blocked by missing staging DB access:

- `python3 app.py sync-customer-read-model --dry-run`
- `python3 app.py sync-customer-read-model`
- customer projection validation SQL

No raw customer identifiers were read or recorded.

## Channel Backfill Result

Not executed.

Required staging SQL scripts were blocked by missing writable staging DB access:

- `scripts/siyuan_migration/03_channel_backfill.sql`
- `scripts/siyuan_migration/04_validate_migration.sql`
- `scripts/siyuan_migration/07_validate_next_blockers.sql`
- `scripts/siyuan_migration/08_validate_customer_projection.sql`

No raw scene values were read or recorded.

## Runtime v2 / Commerce Schema Result

Not executed against restored staging DB.

Local PR-3 migration graph includes schema migrations for:

- `automation_event_v2`
- `automation_membership_v2`
- `automation_stage_entry_v2`
- `automation_task_plan_v2`
- `wechat_shop_refunds`
- `wechat_shop_sync_runs`

Their presence on a restored siyuan staging DB still requires an authorized
staging rehearsal.

## HTTP Smoke Result

Staging HTTP smoke was not executed.

Reason: the current entry does not allow starting a staging service or setting a
staging `DATABASE_URL`.

Local `python3 app.py health` passed:

```text
{'ok': True, 'status_code': 200, 'default_runtime': 'ai_crm_next', 'route_owner': 'ai_crm_next'}
```

The following restored-staging smoke checks remain pending:

- `/health`
- `/admin`
- `/admin/channels`
- `/admin/customers`
- `/admin/config`
- `/admin/api-docs`
- `/api/admin/user-ops/overview`
- `/api/customers/{masked}`
- `/api/sidebar/customer-context`
- `/api/sidebar/profile`
- `/api/external/orders`

## WeCom Auth Readiness

Not executed.

Reason: env present/missing cannot be checked from the current read-only
forced-command entry, and staging service startup was not available.

Pending checks for an authorized staging rehearsal:

- live mode present/missing
- callback missing code result
- dummy state result
- start QR redirect result
- no dummy session issued

## Required Next Step

Provide an operator-controlled staging rehearsal entry with:

1. A latest `siyuan-crm` checkout or release directory for this PR branch.
2. Ordinary shell command execution.
3. Env key present/missing inspection without printing values.
4. Permission to run `pg_dump`.
5. A clearly named staging DB such as `siyuancrm_next_pr4`.
6. Permission to run `pg_restore` against that staging DB.
7. Permission to run `python3 -m alembic upgrade head` on that staging DB.
8. Permission to run `python3 app.py init-next-schema-safe`.
9. Permission to run customer projection and channel backfill scripts against
   staging only.
10. Permission to start a local staging service on a non-production port.
11. Permission to run curl smoke against that local staging service.

Production systemd/nginx/env changes are not required for this PR and should
remain out of scope.

## Security Statement

- No env committed.
- No dump committed.
- No uploads, instance data, pem, or key committed.
- No secrets printed.
- No raw customer external IDs, channel scene tokens, phone numbers, or identity
  binding values recorded.
- No production DB destructive action executed.
- No staging DB write executed from the read-only entry.
- No systemd/nginx change.
- No production cutover.
