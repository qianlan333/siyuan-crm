# siyuan AI-CRM Next post-cutover observation - 2026-06-12

## 1. Executive Summary

- conclusion: POST_CUTOVER_STABLE_WITH_NOTES
- production cutover PR #79: merged
- active DB: `siyuancrm_next_prod_cutover`
- observation window: post-cutover checks on 2026-06-12 after PR #79 merge
- rollback executed: no
- production service changed in this PR: no

The production service stayed healthy after the final cutover. The active DB is the new cutover DB, key pages and APIs returned 200, customer/sidebar/channel/user-ops smoke passed, and log checks did not show traceback, DB connection errors, fixture repository blocks, or external-call blocks.

## 2. Scope

- Observation only.
- No production cutover executed in this PR.
- No systemd/nginx/env change.
- No production DB writes.
- No legacy prune.

## 3. Code / Service State

- repo: `qianlan333/siyuan-crm`
- branch used for observation: `codex/siyuan-pr8-post-cutover-observation`
- HEAD on server during observation: `20dd2033eed9b639e19141ab6f717dbf00467642`
- working tree clean before observation: yes
- service: `openclaw-wecom-postgres.service`
- health: `200`, ok true
- active DB: `siyuancrm_next_prod_cutover`
- release SHA header: `unknown`

## 4. Env Present / Missing

Only present/missing and boolean readiness were printed. No values were printed or recorded.

- core env: present
- WeCom live: true
- SQL repo backends: true
- fixture repo blocked: true
- AUTOMATION_INTERNAL_API_TOKEN: missing
- CRM_API_TOKEN: missing
- MCP_BEARER_TOKEN: missing
- SIDEBAR_THIRD_PARTY_API_TOKEN: missing

## 5. DB Read-only Checks

- current_database: `siyuancrm_next_prod_cutover`
- contacts: `3372`
- customer_detail_snapshot_next: `3372`
- automation_channel: `5`
- admin_users: `6`
- required runtime/commerce/user_ops tables:
  - `automation_event_v2`
  - `automation_membership_v2`
  - `automation_stage_entry_v2`
  - `automation_task_plan_v2`
  - `wechat_shop_refunds`
  - `wechat_shop_sync_runs`
  - `user_ops_pool_current_next`
  - `user_ops_do_not_disturb_next`
  - `user_ops_send_records_next`

## 6. HTTP Smoke

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
- external orders:
  - token present: no
  - status: `503`
  - error_code: `internal_token_not_configured`
  - route_owner: `ai_crm_next`
  - fallback_used: `false`
- no 5xx: yes, except the expected external orders controlled 503 while token is missing

## 7. WeCom Auth

- missing code: `400`
- dummy state: `400`, `invalid_or_expired_state`
- start QR: `302`, WeCom authorization redirect observed
- real login: not executed in this observation run
- external_call_blocked: no

## 8. Logs

- journal traceback: `0`
- journal expected controlled 5xx: `2`, both were local `/api/external/orders` missing-token observations
- DB connection errors: `0`
- fixture_repository_blocked: `0`
- external_call_blocked: `0`
- WeCom callback errors: no unexpected callback errors; matching lines were expected auth smoke 400s and normal WeCom/OAuth 200/302 entries
- nginx errors: sampled matches were unrelated SSL handshake noise

## 9. Queue / Automation Snapshot

- broadcast_jobs status distribution: no rows returned
- runtime v2 tables: present
- commerce audit tables: present
- user ops tables: present
- no write actions executed: yes

## 10. Notes

- `AUTOMATION_INTERNAL_API_TOKEN` is still missing. External orders remain disabled with controlled `503 internal_token_not_configured` until an authorized token is configured.
- Real WeCom admin login was not executed during this observation run and remains an authorized-operator follow-up.
- Legacy prune remains deferred to PR #9.

## 11. Security Statement

- no env committed
- no dump committed
- no uploads/instance/pem/key committed
- no secrets printed
- no raw external_userid/scene_value/mobile/unionid/openid recorded
- no production DB writes
- no systemd/nginx change
- no legacy prune
