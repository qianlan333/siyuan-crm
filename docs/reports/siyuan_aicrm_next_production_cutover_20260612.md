# siyuan AI-CRM Next production cutover - 2026-06-12

## 1. Executive Summary

- conclusion: CUTOVER_SUCCESS_WITH_NOTES
- cutover executed: yes
- rollback executed: no
- service: `openclaw-wecom-postgres.service`
- new production DB label: `siyuancrm_next_prod_cutover`
- old production DB retained: yes

The final production cutover proceeded after PR #78 was merged into `main`. The service was switched to the new production DB, restarted successfully, and passed production smoke. Remaining notes are limited to external orders token configuration and real WeCom login coverage.

## 2. Preconditions

- PR #78 readiness: merged at `2026-06-12T06:01:24Z`
- PR #77 restored staging: `PASS_WITH_NOTES`
- final backup: completed
- write freeze: not technically enforced from shell; operator/user explicitly authorized continuing after PR #78 merge. Risk window recorded for post-cutover observation.
- operator: ordinary SSH entry as `ubuntu`
- external orders token decision: token missing; external orders remain disabled with controlled `503 internal_token_not_configured` until authorized token is configured.
- SQL repo backend env: set to `sqlalchemy` in the active production env during cutover.

## 3. Final Backup

- dump path: `/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-current-20260612-140406.dump`
- env backup path: `/home/ubuntu/backups/siyuan-aicrm-cutover-final/.openclaw-wecom-pg.env.20260612-140406`
- assets archive path: `/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-assets-20260612-140406.tar.gz`
- sizes:
  - dump: `3113233` bytes
  - env backup: `1868` bytes
  - assets archive: `243` bytes
- env content recorded: no

## 4. New Production DB Restore

- target DB label: `siyuancrm_next_prod_cutover`
- old DB untouched: yes
- restore status: passed
- restore output:
  - `PASS STAGING_DATABASE_URL is available for PostgreSQL CLI tools`
  - `PASS restored /home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-current-20260612-140406.dump to explicit staging database`
- CLEAN scope: explicit new production DB only
- target DB creation: production app role could not create DB; `sudo -n -u postgres` was used only for the explicit target DB.

## 5. New Production DB Initialization

- alembic heads: `0036_wechat_shop_sync_runs (head)`
- current before: `0036_wechat_shop_sync_runs (head)`
- upgrade head: passed
- current after: `0036_wechat_shop_sync_runs (head)`
- init-next-schema-safe: passed, `drop_or_truncate_executed: False`
- projection:
  - dry-run source/projected: `3372/3372`
  - real sync source/target: `3372/3372`
  - written_customers: `3372`
  - reconciliation diff_count: `0`
- channel backfill:
  - automation_channel_scene_alias rows inserted: `2`
  - automation_channel_qrcode_asset rows inserted: `2`
- validation SQL:
  - contacts: `3372`
  - customer_detail_snapshot_next: `3372`
  - projection_coverage_against_contacts: `3372/3372`
  - projection_coverage_against_bindings: `3/3`
  - scene_alias_coverage: `5/5`
  - qrcode_asset_coverage: `5/5`
  - user_ops next tables: present
  - runtime v2 / commerce audit tables: present

## 6. Env / Service Switch

- env backup:
  - `/home/ubuntu/.openclaw-wecom-pg.env.pre-aicrm-next-cutover-20260612-140648`
  - `/home/ubuntu/.openclaw-wecom-pg.env.pre-next-active-20260612-140648`
- env updated keys:
  - `DATABASE_URL`
  - `CUSTOMER_READ_MODEL_REPO_BACKEND`
  - `USER_OPS_REPO_BACKEND`
  - `AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD`
- post-update readiness:
  - repo_backends_sql: true
  - fixture_repo_blocked: true
  - wecom_live: true
  - automation internal API token: missing
- systemd service: `openclaw-wecom-postgres.service`
- nginx changed: no
- restart status: passed
- post-restart service state: active
- post-restart health: `200`, ok true

## 7. Production Smoke

- active DB label after switch: `siyuancrm_next_prod_cutover`
- active DB counts:
  - contacts: `3372`
  - customer_detail_snapshot_next: `3372`
  - automation_channel: `5`
- masked external_userid sample: `wm***VA`
- masked scene sample: `aq***ae`
- `/health`: `200`
- `/admin`: `200`
- `/admin/channels`: `200`
- `/admin/customers`: `200`
- `/admin/config`: `200`
- `/admin/api-docs`: `200`
- `/api/admin/user-ops/overview`: `200`
- customer/sidebar:
  - customer detail: `200`
  - customer timeline: `200`
  - sidebar customer context: `200`
  - sidebar profile: `200`
- channel runtime diagnosis: `200`
- external orders:
  - status: `503`
  - error_code: `internal_token_not_configured`
  - route_owner: `ai_crm_next`
  - fallback_used: `false`
- no 5xx: yes

## 8. WeCom Auth

- missing code: `400`
- dummy state: `400`, `invalid_or_expired_state`
- start QR: `302`, WeCom authorization redirect observed
- real login: not executed in this cutover run
- external_call_blocked observed: no

## 9. Observation

- journalctl: no recent error/traceback/fixture/external-call-blocked matches in sudo-filtered last 200 service lines
- nginx error log: only unrelated SSL handshake noise observed in sampled tail
- DB connection: healthy via app health and smoke
- callback: smoke paths behaved as expected; real callback/login still requires operator observation
- known notes:
  - Business-side write freeze was not technically enforced by this shell; continue post-cutover observation.
  - External orders remain disabled until token is configured.
  - Real WeCom admin login should be completed by an authorized operator.

## 10. Rollback

- rollback executed: no
- rollback reason: n/a
- old release retained: yes
- old DB retained: yes
- rollback command summary:
  - restore previous env backup if needed,
  - restart `openclaw-wecom-postgres.service`,
  - verify `/health` and `/admin`.

## 11. Remaining Notes

- AUTOMATION_INTERNAL_API_TOKEN: missing; configure before enabling external orders in production.
- real WeCom login if not executed: still required by authorized operator after cutover.
- post-cutover observation PR #8: recommended.
- legacy prune PR #9: deferred.

## 12. Security Statement

- no env committed
- no dump committed
- no uploads/instance/pem/key committed
- no secrets printed
- no raw external_userid/scene_value/mobile/unionid/openid recorded
- old DB retained
- rollback path retained
