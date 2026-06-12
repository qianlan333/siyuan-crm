# siyuan AI-CRM Next production cutover readiness - 2026-06-12

## 1. Scope

- This is readiness only.
- No production cutover executed.
- No production systemd/nginx/env change.
- No production DB migration/write.
- Based on PR #77 restored staging rehearsal `PASS_WITH_NOTES`.

## 2. Code State

- repository: `qianlan333/siyuan-crm`
- branch used for readiness collection: `codex/siyuan-pr6-production-cutover-readiness`
- HEAD: `3de695897dc4b960edf4800928b11bff2b2a9f2a`
- latest origin/main: `3de695897dc4b960edf4800928b11bff2b2a9f2a`
- working tree clean before checks: yes
- PR #73/#74/#75/#77 included: yes
- static validation summary:
  - `python3 -m compileall app.py aicrm_next scripts tools tests`: passed
  - `python3 app.py health`: ok true
  - `python3 -m pytest tests/test_alembic_revision_chain.py -q`: `8 passed`
  - `python3 -m pytest tests/test_siyuan_rehearsal_blocker_fixes.py -q`: `7 passed`
  - PR-1/PR-2 route/external order regression tests: `13 passed`
  - `python3 -m alembic heads`: `0036_wechat_shop_sync_runs (head)`

## 3. Production Env Present / Missing

Only present/missing and boolean readiness were printed. No values were printed or recorded.

Required for cutover:

- DATABASE_URL: present
- app signing/session key: present
- WeCom corp/agent/contact/callback credential keys: present
- WeChat MP app credential keys: present
- ADMIN_LOGIN_REDIRECT_URI: present
- AICRM_NEXT_WECOM_ADMIN_AUTH_MODE: present
- AICRM_NEXT_WECOM_ADMIN_AUTH_MODE_live: true
- AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD_false: true
- CUSTOMER_READ_MODEL_REPO_BACKEND_sql: false; env key missing, cutover should set it explicitly to SQL backend or confirm production default.
- USER_OPS_REPO_BACKEND_sql: false; env key missing, cutover should set it explicitly to SQL backend or confirm production default.
- AICRM_NEXT_ADMIN_SESSION_COOKIE_SECURE: present
- AICRM_NEXT_WECOM_ADMIN_AUTH_TIMEOUT_SECONDS: present

Optional / feature-gated:

- AUTOMATION_INTERNAL_API_TOKEN: missing
- CRM_API_TOKEN: missing
- MCP_BEARER_TOKEN: missing
- SIDEBAR_THIRD_PARTY_API_TOKEN: missing

## 4. Production Read-only Probe

- current DB label/name: `siyuancrm_next_prod`
- transaction_read_only: `off`
- contacts_count: `3371`
- automation_channel_count: `5`
- admin_users_count: `6`
- no writes executed: yes

## 5. Current Production Service / Nginx Read-only Check

- service name: `openclaw-wecom-postgres.service`
- ExecStart summary: activates `/home/ubuntu/venvs/openclaw` and runs `python app.py run`
- WorkingDirectory summary: `/home/ubuntu/极简 crm`
- EnvironmentFile summary: `/home/ubuntu/.openclaw-wecom-pg.env`
- app port/upstream: nginx proxy targets `127.0.0.1:5001`
- nginx upstream/proxy summary:
  - `listen 80`
  - `listen 443 ssl`
  - `server_name www.xinliushangye.com xinliushangye.com`
  - `proxy_pass http://127.0.0.1:5001`
  - `sudo -n nginx -T`: syntax ok and test successful
- current local production health:
  - status: `200`
  - `x-aicrm-route-owner`: `ai_crm_next`
  - `x-aicrm-app`: `ai_crm_next`
  - `x-aicrm-release-sha`: `unknown`
  - body ok: true
- no service restart: yes
- no nginx reload: yes

## 6. Restored Staging Rehearsal Reference

From PR #77:

- staging DB: `siyuancrm_next_pr5`
- backup/restore: pass after restore helper used `--no-acl`
- Alembic current: `0036_wechat_shop_sync_runs (head)`
- Alembic upgrade head: pass
- safe init: pass, including runtime v2 and commerce audit guard tables
- customer projection: `3370/3370`
- channel coverage: scene alias `5/5`, qrcode asset `5/5`
- runtime v2 / commerce schema: all required tables present
- HTTP smoke: no 5xx
- WeCom auth readiness: live mode true, missing code 400, dummy state 400, start QR 302
- conclusion: `PASS_WITH_NOTES`

## 7. External Orders Token Decision

- AUTOMATION_INTERNAL_API_TOKEN: missing
- Current behavior when missing:
  - `/api/external/orders` returns controlled `503` with `internal_token_not_configured`.
  - Production external orders are not enabled until an authorized token is configured.
- Cutover decision:
  - Configure the token before cutover if external orders must be available immediately.
  - Or explicitly approve cutover with external orders disabled and the controlled `503` behavior documented.

## 8. Cutover Go / No-Go

READY_WITH_NOTES

Go criteria status:

- PR #77 restored staging passed: yes.
- production env core keys present: yes.
- WeCom admin auth live mode true: yes.
- customer/user_ops repo backend SQL-ready or defaults known safe: note; explicit env keys are missing and should be set or confirmed before cutover.
- rollback path confirmed: runbook has rollback flow; final operator/old release path must be confirmed in the cutover window.
- final backup plan confirmed: runbook has final backup flow.
- operator available for systemd/nginx: required for final cutover PR/window, not executed here.
- real WeCom login plan confirmed: must be executed in cutover window.

Readiness notes:

- External orders token is missing. This is acceptable only if external orders remain disabled at cutover.
- SQL repository backend env keys are missing. Set them explicitly in the target cutover env or confirm production defaults before the final cutover.
- Production DB is writable (`transaction_read_only=off`), but this PR executed only read-only SELECTs.

## 9. Cutover Plan Reference

Future cutover steps, not executed in this PR:

1. Freeze writes.
2. Final backup.
3. Restore final dump to new production DB.
4. Run alembic upgrade head on new production DB.
5. Run init-next-schema-safe.
6. Run sync-customer-read-model dry-run/real.
7. Run channel backfill and validation.
8. Copy/mount uploads/instance/verification files.
9. Switch systemd WorkingDirectory/env DB URL or release pointer.
10. Restart service.
11. Run smoke.
12. Real WeCom login.
13. Observe.
14. Rollback if needed.

## 10. Rollback Plan

- old release path: current service uses `/home/ubuntu/极简 crm`; final cutover operator must confirm the exact old release path before changing systemd.
- old DB URL retained: yes, retained in operator-managed env/backup path; value not printed or recorded.
- final backup path: `/home/ubuntu/backups/siyuan-aicrm-cutover-final` per runbook.
- rollback owner: production operator for the cutover window.
- rollback command summary:
  - switch systemd WorkingDirectory/release pointer back to old release,
  - restore old DB URL in the env file or release pointer,
  - restart service,
  - verify `/health`, `/admin`, and WeCom callback.
- no rollback executed in this PR: yes

## 11. Security Statement

- no env committed
- no dump committed
- no uploads/instance/pem/key committed
- no secrets printed
- no raw external_userid/scene_value/mobile/unionid/openid recorded
- no production DB write
- no systemd/nginx change
- no production cutover
