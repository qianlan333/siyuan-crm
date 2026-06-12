# siyuan AI-CRM Next restored staging rehearsal after Alembic closeout - 2026-06-12

## 1. 执行环境

- branch: `codex/siyuan-pr5-restored-staging-rehearsal`
- base commit SHA: `9bed92ec24cbe99fd93112055cb0ec36beef4d77`
- Python: `Python 3.10.12`
- PostgreSQL CLI: `psql (PostgreSQL) 14.22`
- staging DB: `siyuancrm_next_pr5`
- app port: `5015`
- systemd/nginx modified: no
- production cutover: no
- production DB destructive action: no

## 2. Env Present / Missing

Only present/missing was printed. No env values were printed or recorded.

- DATABASE_URL: present
- app signing/session key: present
- WeCom corp/agent/contact/callback credential keys: present
- WeChat MP app credential keys: present
- ADMIN_LOGIN_REDIRECT_URI: present
- AICRM_NEXT_WECOM_ADMIN_AUTH_MODE: present
- AICRM_NEXT_WECOM_ADMIN_AUTH_MODE_live: true
- AUTOMATION_INTERNAL_API_TOKEN: missing
- CRM_API_TOKEN: missing
- MCP_BEARER_TOKEN: missing
- SIDEBAR_THIRD_PARTY_API_TOKEN: missing

## 3. Backup Result

- dump path: `/home/ubuntu/backups/siyuan-aicrm-pr5-staging-rehearsal/siyuan-current-20260612-132106.dump`
- env backup path: `/home/ubuntu/backups/siyuan-aicrm-pr5-staging-rehearsal/.openclaw-wecom-pg.env.20260612-132106`
- assets archive path: `/home/ubuntu/backups/siyuan-aicrm-pr5-staging-rehearsal/siyuan-assets-20260612-132106.tar.gz`
- file sizes:
  - dump: `3086341` bytes
  - env backup: `1868` bytes
  - assets archive: `243` bytes
- env content recorded: no

## 4. Restore Result

- staging DB: `siyuancrm_next_pr5`
- initial restore status: blocked by source-role DEFAULT ACL statements in the custom dump.
- minimal fix: `scripts/siyuan_migration/02_restore_to_staging_db.sh` now passes `--no-acl` together with `--no-owner`, so staging restore skips source ACL ownership statements.
- rerun restore status: pass.
- restore output:
  - `PASS STAGING_DATABASE_URL is available for PostgreSQL CLI tools`
  - `PASS restored /home/ubuntu/backups/siyuan-aicrm-pr5-staging-rehearsal/siyuan-current-20260612-132106.dump to explicit staging database`
- CLEAN=true scope: explicit staging DB only.
- staging DB creation: production app role could not create databases, so `sudo -n -u postgres` was used only for the explicit `siyuancrm_next_pr5` database.

## 5. Alembic Result

- heads: `0036_wechat_shop_sync_runs (head)`
- current before upgrade: `0036_wechat_shop_sync_runs (head)`
- upgrade head status: pass.
- current after upgrade: `0036_wechat_shop_sync_runs (head)`
- stamp used: no
- errors: none after the restore helper ACL fix.

## 6. Safe Init Result

- initial finding: restored DB was already stamped at Alembic head, but runtime v2 and WeChat Shop audit tables were absent.
- minimal fix: `init-next-schema-safe` now covers schema-only PR-3 runtime/audit tables with `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
- init-next-schema-safe status: pass.
- initialized tables:
  - `customer_list_index_next`
  - `customer_detail_snapshot_next`
  - `customer_timeline_event_next`
  - `customer_recent_message_next`
  - `user_ops_pool_current_next`
  - `user_ops_do_not_disturb_next`
  - `user_ops_send_records_next`
  - `automation_event_v2`
  - `automation_membership_v2`
  - `automation_stage_entry_v2`
  - `automation_task_plan_v2`
  - `wechat_shop_refunds`
  - `wechat_shop_sync_runs`
- drop_or_truncate_executed: false

## 7. Customer Projection Result

- dry-run summary:
  - ok: true
  - source_count: `3370`
  - projected_customer_count: `3370`
  - target_count before write: `3303`
  - diff_count: `0`
- real sync summary:
  - ok: true
  - source_count: `3370`
  - projected_customer_count: `3370`
  - target_count after write: `3370`
  - written_customers: `3370`
  - diff_count: `0`
- source contacts: `3370`
- customer_detail_snapshot_next: `3370`
- projection_coverage_against_contacts: `3370/3370`
- projection_coverage_against_bindings: `3/3`
- masked external_userid sample: `wm***VA`

## 8. Channel Backfill Result

- backfill status: pass.
- automation_channel_scene_alias rows inserted: `2`
- automation_channel_qrcode_asset rows inserted: `2`
- scene_alias_coverage: `5/5`
- qrcode_asset_coverage: `5/5`
- masked scene diagnosis samples: `aq***ae`

## 9. Runtime v2 / Commerce Schema Result

All required tables are present after safe init rerun:

- automation_event_v2: present
- automation_membership_v2: present
- automation_stage_entry_v2: present
- automation_task_plan_v2: present
- wechat_shop_refunds: present
- wechat_shop_sync_runs: present
- user_ops_pool_current_next: present
- user_ops_do_not_disturb_next: present
- user_ops_send_records_next: present

## 10. HTTP Smoke Result

- `/health`: `200`
- `/admin`: `200`
- `/admin/channels`: `200`
- `/admin/customers`: `200`
- `/admin/config`: `200`
- `/admin/api-docs`: `200`
- `/api/admin/user-ops/overview`: `200`
- customer/sidebar smoke:
  - customer detail: `200`
  - customer timeline: `200`
  - sidebar customer context: `200`
  - sidebar profile: `200`
- channel runtime diagnosis: `200`
- external orders missing-token smoke:
  - status: `503`
  - ok: `false`
  - error_code: `internal_token_not_configured`
  - route_owner: `ai_crm_next`
  - fallback_used: `false`
- no 5xx: yes

## 11. WeCom Auth Readiness

- live mode: true
- `/auth/wecom/callback` missing code: `400`
- `/auth/wecom/callback?code=dummy&state=dummy`: `400`, `invalid_or_expired_state`
- `/auth/wecom/start?mode=qr&next=/admin`: `302`, WeCom authorization redirect observed
- external_call_blocked observed: no
- real login executed: no

## 12. Conclusion

PASS_WITH_NOTES

Restored staging migration, safe init, customer projection, channel backfill, runtime v2 / commerce schema checks, HTTP smoke, and WeCom auth readiness all passed after the two minimal safety fixes.

Notes before production cutover readiness:

- Configure `AUTOMATION_INTERNAL_API_TOKEN` before enabling external orders in production.
- The restored DB had Alembic head stamped but missed PR-3 schema-only tables; `init-next-schema-safe` now covers those tables as a safe staging/cutover guard.
- The restore helper now skips source ACL statements with `--no-acl`, avoiding role-membership failures when restoring to staging.

## 13. Security Statement

- no env committed
- no dump committed
- no uploads/instance/pem/key committed
- no secrets printed
- no raw external_userid/scene_value/mobile/unionid/openid recorded
- no production DB destructive action
- no systemd/nginx change
- no production cutover
