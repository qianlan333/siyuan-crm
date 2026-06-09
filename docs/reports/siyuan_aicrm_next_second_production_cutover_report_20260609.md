# siyuan AI-CRM Next Second Production Cutover Report - 2026-06-09

## 1. 基本信息

- 执行时间：2026-06-09。
- 执行入口：真实服务器普通 SSH shell。
- 代码 commit：`0816f059`。
- PR #56：已包含。
- 旧 release 路径：`/home/ubuntu/极简 crm`。
- 新 release 路径：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`。
- 旧 DB 标识：`openclaw`。
- 新 DB 标识：`siyuancrm_next_prod`。
- 切换策略：新生产库切换，旧库保留用于回滚。
- 是否修改 systemd/nginx：systemd service 工作目录已切到新 release；nginx 未修改。
- 当前服务状态：`openclaw-wecom-postgres.service` active。
- 当前工作目录：新 release。
- 当前 DB 标识：`siyuancrm_next_prod`。
- 当前 timers：已恢复 active。

## 2. 最终备份

最终成功切换使用的备份批次：`20260609-125121`。

| 项目 | 路径 | 大小 | 结果 |
| --- | --- | --- | --- |
| dump | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-current-20260609-125121.dump` | 2.2M | pass |
| env backup | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/.openclaw-wecom-pg.env.20260609-125121` | 4.0K | pass |
| assets archive | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-assets-20260609-125121.tar.gz` | 4.0K | pass |
| systemd backup | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/openclaw-wecom-postgres.service.cutover-20260609-125120.bak` | recorded | pass |

Additional backups:

- env pre-edit backup: `/home/ubuntu/.openclaw-wecom-pg.env.cutover-20260609-125120.bak`
- copied production assets into the new release: 3 asset entries.

No backup file content was printed or committed.

## 3. Freeze / Restore / Init

Write freeze actions:

- stopped `openclaw-wecom-postgres.service`
- stopped `openclaw-automation-conversion-due-runner.timer`
- stopped `openclaw-external-contact-sync.timer`
- stopped `openclaw-external-contact-full-sync.timer`

Restore and initialization:

| Step | Result |
| --- | --- |
| `pg_restore` final dump into `siyuancrm_next_prod` with `CLEAN=true` | pass |
| `python3 app.py health` against target DB | pass |
| `python3 app.py init-db` | pass |
| `python3 app.py init-next-schema-safe` | pass |
| `python3 app.py sync-customer-read-model --dry-run` | pass |
| `python3 app.py sync-customer-read-model` | pass |
| `scripts/siyuan_migration/03_channel_backfill.sql` | pass |
| `scripts/siyuan_migration/04_validate_migration.sql` | pass |
| `scripts/siyuan_migration/07_validate_next_blockers.sql` | pass |
| `scripts/siyuan_migration/08_validate_customer_projection.sql` | pass |

## 4. Projection / Channel Results

| Metric | Result |
| --- | --- |
| `customer_detail_snapshot_next` | 3303 |
| `customer_list_index_next` | 3303 |
| `contacts` | 3303 |
| `external_contact_bindings` | 2 |
| projection coverage against contacts | 3303/3303 |
| projection coverage against bindings | 2/2 |
| `automation_channel.scene_value_non_empty` | 3 |
| scene alias coverage | 3/3 |
| qrcode asset coverage | 3/3 |
| 7 Next blocker tables | present |

## 5. Pre-Switch Smoke

Before switching systemd/env, a temporary service was started on a non-production port against `siyuancrm_next_prod`.

| Check | Result |
| --- | --- |
| `/health` | 200 |
| `/admin` | 200 |
| `/api/admin/user-ops/overview` | 200 |
| `/auth/wecom/callback` missing code | 400, no cookie, no `external_call_blocked` |
| `/auth/wecom/callback?code=dummy&state=dummy` | 400, no cookie, no `external_call_blocked` |
| `/auth/wecom/start?mode=qr&next=/admin` | 302 WeCom QR authorize |
| `/auth/wecom/start?mode=oauth&next=/admin` | 302 WeCom OAuth authorize |
| channel runtime diagnosis | 200 |
| customer detail | 200 |
| customer timeline | 200 |
| sidebar customer context | 200 |
| sidebar profile | 200 |

All sampled `scene_value` and `external_userid` values were masked in logs and report output.

## 6. Production Switch

Changes applied after Go conditions passed:

- `DATABASE_URL` in the production env file now points to DB identifier `siyuancrm_next_prod`.
- systemd `WorkingDirectory` now points to `/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`.
- `sudo systemctl daemon-reload` executed.
- `sudo systemctl restart openclaw-wecom-postgres.service` executed.
- nginx was not modified.

## 7. Post-Switch Smoke

| Endpoint / Action | Result |
| --- | --- |
| `/health` | 200 |
| `/admin` | 200 |
| `/admin/channels` | 200 |
| `/admin/customers` | 200 |
| `/admin/config` | 200 |
| `/admin/api-docs` | 200 |
| `/api/admin/user-ops/overview` | 200 |
| `/auth/wecom/callback` missing code | 400, no cookie, no `external_call_blocked` |
| `/auth/wecom/callback?code=dummy&state=dummy` | 400, no cookie, no `external_call_blocked` |
| `/auth/wecom/start?mode=qr&next=/admin` | 302 WeCom QR authorize |
| `/auth/wecom/start?mode=oauth&next=/admin` | 302 WeCom OAuth authorize |
| channel runtime diagnosis | 200 |
| customer detail | 200 |
| customer timeline | 200 |
| sidebar customer context | 200 |
| sidebar profile | 200 |

Real WeCom login verification:

- `real_wecom_login_test`: not_run.
- Reason: SSH-only execution could not complete a human QR/OAuth login.
- Required manual follow-up: an authorized operator should verify real WeCom admin login enters `/admin` and refresh does not require repeated login.

## 8. Observation Window

- `/health` after observation: pass.
- journal scan for recent `5xx` / `ERROR` / `Traceback` / `Exception`: 0 matching lines.
- Timers restarted:
  - `openclaw-automation-conversion-due-runner.timer`: active
  - `openclaw-external-contact-sync.timer`: active
  - `openclaw-external-contact-full-sync.timer`: active

## 9. Go / Rollback

- Final Go: yes.
- Final rollback performed: no.
- Old release retained: yes.
- Old DB retained: yes.

Notes:

- A first cutover attempt in the same window rolled back before systemd/env switching because the automation script incorrectly treated the expected auth `400` response as a failure. The rollback restored the old env, old systemd service, old service, and timers. The successful final cutover is the second attempt recorded with backup batch `20260609-125121`.

## 10. Remaining Manual Items

- Complete one real WeCom admin login test through the production domain:
  - start via `/login` or `/auth/wecom/start?mode=qr&next=/admin`
  - complete WeCom authorization
  - verify redirect into `/admin`
  - refresh `/admin` and confirm session remains valid
- Continue observing callback logs and customer/channel/user-ops paths during normal traffic.

## 11. Safety Statement

- No `.env`, dump, uploads, instance, pem/key file is committed in this PR.
- No full `DATABASE_URL` is recorded.
- No database password, `WECOM_SECRET`, token, code, state, session cookie, AESKey, private key, raw userid, raw external_userid, raw scene_value, mobile, unionid, or openid is recorded.
- No production DB `DROP` / `CLEAN` / `pg_restore` was executed against the old production DB.
- `pg_restore --clean` was used only against the new DB identifier `siyuancrm_next_prod`.
- nginx was not modified.
