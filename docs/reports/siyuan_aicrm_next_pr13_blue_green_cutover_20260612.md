# siyuan AI-CRM baseline PR-13 blue-green cutover - 2026-06-12

## 1. Executive Summary

Conclusion: CUTOVER_PASS_WITH_NOTES

PR-13 manually cut production over to main commit `97c9bf68c789500eb636607e6d3529d6ab9514a9` with a blue-green release directory and independent virtualenv. GitHub `Deploy to Production` remained disabled and no main-push deploy workflow was used.

The old production directory and old virtualenv were preserved. The cutover modified only the production systemd service unit to point to the new release/venv; nginx continued proxying to `127.0.0.1:5001` and did not require a config change.

No rollback was triggered.

## 2. Cutover Context

- cutover time: `2026-06-12 20:06 CST`
- hostname: `iv-yelatkuuwwqbxyvtieq5`
- old production directory: `/home/ubuntu/极简 crm`
- old commit: `a43da560dffdf11ffcd350368123e5bcf42ddf15`
- new release: `/home/ubuntu/releases/siyuan-aicrm-main-97c9bf68`
- new venv: `/home/ubuntu/venvs/siyuan-aicrm-main-97c9bf68`
- new commit: `97c9bf68c789500eb636607e6d3529d6ab9514a9`
- pre-cutover local port: `127.0.0.1:5017`
- production service port after cutover: `127.0.0.1:5001`
- env file: `/home/ubuntu/.openclaw-wecom-pg.env`

## 3. Boundary Checks

| boundary | result | notes |
|---|---|---|
| GitHub `Deploy to Production` workflow | PASS | remained `disabled_manually` |
| main push auto deploy | PASS | not used |
| PR #88 | PASS | not merged; remains evidence-only |
| old production directory | PASS | retained at old commit |
| old venv | PASS | retained |
| old release/logs/env | PASS | retained |
| `.github/workflows/deploy.yml` | PASS | not modified |
| `deploy/` | PASS | not modified |
| production secrets/raw IDs in report | PASS | not recorded |

## 4. Preflight

| check | result | evidence |
|---|---|---|
| production service active before cutover | PASS | `openclaw-wecom-postgres.service` active |
| production head before cutover | PASS | `a43da560dffdf11ffcd350368123e5bcf42ddf15` |
| production health before cutover | PASS | `GET /health` returned 200 |
| PostgreSQL available | PASS | read-only connection check passed |
| Alembic before cutover | PASS | `0037_channel_multi_staff_assignment` |
| port `5017` free | PASS | no listener before pre-cutover smoke |
| new release absent | PASS | absent before creation |
| new venv absent | PASS | absent before creation |
| disk space | PASS | `/home/ubuntu` had sufficient free space |

## 5. New Release / Venv

The server had intermittent GitHub clone failures, so the fixed main commit was packaged locally with `git archive` and uploaded to the server. The archive source was commit `97c9bf68c789500eb636607e6d3529d6ab9514a9`; the release stores this provenance in `.source_commit`.

Validation:

| check | result |
|---|---|
| fixed commit provenance | PASS |
| independent venv created | PASS |
| dependencies installed | PASS |
| `python -m compileall app.py aicrm_next scripts tools tests` | PASS |
| `python app.py health` | PASS |
| `python app.py routes` | PASS, 631 route lines generated |

## 6. DB Backup and Migration

| item | value |
|---|---|
| backup completed | yes |
| backup path | `/home/ubuntu/pr13-db-backups/siyuan-prod-before-pr13-20260612T120516Z.dump` |
| backup size | `3173715` bytes |
| backup format | `pg_dump --format=custom --no-owner --no-acl` |
| file permissions | `600` |
| Alembic before | `0037_channel_multi_staff_assignment` |
| Alembic after | `0038_merge_duplicate_channel_wechat_shop_heads (head) (mergepoint)` |
| safe init | PASS |

No DB URL, token, secret, raw external identifier, phone, order ID, or customer ID is recorded in this report.

## 7. Pre-Cutover Smoke

The new release was started on `127.0.0.1:5017` with worker/outbound/real external-call switches disabled. Listener validation confirmed local-only binding.

| endpoint | status | result |
|---|---:|---|
| `/health` | 200 | PASS |
| `/admin` | 200 | PASS |
| `/api/customers` | 200 | PASS |
| `/api/admin/channels` | 200 | PASS |
| `/api/admin/automation-conversion/programs` | 200 | PASS |
| `/api/admin/automation-conversion/group-ops/plans` | 200 | PASS |
| `/api/sidebar/jssdk-config?url=<LOCAL_SIDEBAR_URL>` | 200 | PASS |
| `/api/admin/config/mcp-tools` | 200 | PASS |
| `/api/admin/channels/<channel_id>/assignees` | 200 | PASS |
| `/api/system/runtime-route-map` | 200 | PASS |
| `/api/admin/wechat-shop/sync-runs` | 200 | PASS |
| `/api/admin/channels/runtime-diagnosis?scene_value=<TEST_PLACEHOLDER>` | 200 | PASS |
| `/api/admin/wecom/tags/live/gate` | 200 | PASS |
| `/api/admin/commerce/transactions` | 404 | SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST |

Pre-cutover smoke passed under the adjusted PR-12/PR-13 acceptance scope.

## 8. Systemd / Nginx Switch

Before switching, rollback files were written under:

- `/home/ubuntu/pr13-blue-green-work-20260612/rollback/openclaw-wecom-postgres.service.before-pr13`
- `/home/ubuntu/pr13-blue-green-work-20260612/rollback/nginx-siyuan-crm.before-pr13`

Systemd change summary:

- service: `openclaw-wecom-postgres.service`
- old `WorkingDirectory`: `/home/ubuntu/极简 crm`
- new `WorkingDirectory`: `/home/ubuntu/releases/siyuan-aicrm-main-97c9bf68`
- old venv: `/home/ubuntu/venvs/openclaw`
- new venv: `/home/ubuntu/venvs/siyuan-aicrm-main-97c9bf68`
- production port: `5001`
- bind address: `127.0.0.1`

Nginx change summary:

- no nginx config change was required
- existing nginx proxy continued to `127.0.0.1:5001`
- `nginx -t` passed after cutover

## 9. Post-Cutover Smoke

| check | result | notes |
|---|---|---|
| systemd active | PASS | service active after restart |
| production listener | PASS | `127.0.0.1:5001` |
| production health | PASS | `legacy_runtime_enabled=false`, `runtime_owner=ai_crm_next` |
| nginx active/config | PASS | nginx active; `nginx -t` successful |
| log scan | PASS | no traceback/import/migration/DB/5xx signal in sampled service tail |

HTTP smoke:

| endpoint | status | result |
|---|---:|---|
| `/health` | 200 | PASS |
| `/admin` | 200 | PASS |
| `/api/customers` | 200 | PASS |
| `/api/admin/channels` | 200 | PASS |
| `/api/admin/automation-conversion/programs` | 200 | PASS |
| `/api/admin/automation-conversion/group-ops/plans` | 200 | PASS |
| `/api/sidebar/jssdk-config?url=<LOCAL_SIDEBAR_URL>` | 200 | PASS |
| `/api/admin/config/mcp-tools` | 200 | PASS |
| `/api/admin/channels/<channel_id>/assignees` | 200 | PASS |
| `/api/system/runtime-route-map` | 200 | PASS |
| `/api/admin/wechat-shop/sync-runs` | 200 | PASS |
| `/api/admin/channels/runtime-diagnosis?scene_value=<TEST_PLACEHOLDER>` | 200 | PASS |
| `/api/admin/wecom/tags/live/gate` | 200 | PASS |
| `/api/admin/commerce/transactions` | 404 | SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST |

## 10. Worker / Timer Status

| unit | status | notes |
|---|---|---|
| `openclaw-external-push-worker.timer` | enabled, active | existing timer remained active |
| `openclaw-external-push-worker.service` | inactive after successful run | last observed run exited `0/SUCCESS` and scanned zero items |

No new worker unit was installed or enabled by PR-13. The existing timer state was not changed by this manual cutover.

## 11. Rollback Plan

Rollback command file:

- `/home/ubuntu/pr13-blue-green-work-20260612/rollback_commands.txt`

Rollback commands:

```bash
sudo cp /home/ubuntu/pr13-blue-green-work-20260612/rollback/openclaw-wecom-postgres.service.before-pr13 /etc/systemd/system/openclaw-wecom-postgres.service
sudo systemctl daemon-reload
sudo systemctl restart openclaw-wecom-postgres.service
curl -sSf http://127.0.0.1:5001/health
```

DB restore was not triggered. The DB backup is retained for emergency recovery, but automatic DB restore is not recommended unless a severe data issue is confirmed.

## 12. Security Statement

- no DB URL recorded
- no secrets/tokens recorded
- no raw `external_userid`, `scene_value`, `openid`, `unionid`, phone, order ID, customer ID, or contact ID recorded
- DB backup retained only on the server with restricted permissions
- GitHub `Deploy to Production` remains disabled
- no GitHub main-push deploy was used

## 13. Final Result

Conclusion: CUTOVER_PASS_WITH_NOTES

Notes:

- `/api/admin/commerce/transactions` remains `SKIPPED_NON_CORE_EMPTY_TRANSACTION_LIST`, consistent with the adjusted PR-12 acceptance scope.
- Existing external push worker timer is still active; no new worker/timer was enabled by this cutover.
- Old production directory, old venv, old env, old logs, rollback unit, and DB backup are retained.

Recommended next step: enter PR-14 observation.
