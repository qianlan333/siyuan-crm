# siyuan AI-CRM Next customer projection staging rehearsal - 2026-06-09

## 1. 执行环境

- Commit SHA: `103f9a4`
- Python: `Python 3.10.12`
- PostgreSQL CLI: `psql (PostgreSQL) 14.22 (Ubuntu 14.22-0ubuntu0.22.04.1)` / `pg_dump (PostgreSQL) 14.22 (Ubuntu 14.22-0ubuntu0.22.04.1)`
- Staging DB: `siyuancrm_next`
- DATABASE_URL: present; PostgreSQL CLI URL normalized successfully
- systemd/nginx: not modified
- Production cutover: not performed
- Temporary staging service: used a local staging port only; stopped after smoke test

Recent git log:

```text
103f9a4 Merge pull request #51 from qianlan333/codex/customer-read-model-projection-backfill
323798a Backfill siyuan customer read-model projections
e495a68 Merge pull request #50 from qianlan333/codex/startup-compatibility-closeout
aa26e5e Close out startup compatibility with Next-only app entry
c1018c7 Merge pull request #49 from qianlan333/docs/record-completed-rehearsal-after-blocker-fix
20f031a Record completed staging rehearsal after blocker fix
6472741 Merge pull request #48 from qianlan333/codex/fix-aicrm-next-rehearsal-blockers
1293154 Fix AI-CRM Next rehearsal blockers
6e5faf0 Merge pull request #47 from qianlan333/docs/record-server-rehearsal-read-model-blocker
c853d36 Merge pull request #46 from qianlan333/codex/fix-siyuan-validate-table-name-ambiguity
```

Git status after report generation will include this report only. Status before report regeneration:

```text
?? docs/reports/siyuan_aicrm_next_staging_rehearsal_customer_projection_20260609.md
```

## 2. 恢复结果

- Dump path: `/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump`
- Staging DB: `siyuancrm_next`
- pg_restore status: `0`
- CLEAN=true scope: explicit staging DB `siyuancrm_next` only

Restore output:

```text
PASS STAGING_DATABASE_URL is available for PostgreSQL CLI tools
PASS restored /home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump to explicit staging database
```

## 3. health / schema 初始化

- `python3 app.py health` status: `0`
- `python3 app.py init-db-legacy` status: `1`
- `python3 app.py init-db` fallback status: `0`
- `python3 app.py init-next-schema-safe` status: `0`

Health output:

```text
/home/ubuntu/venvs/openclaw/lib/python3.10/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
{'ok': True, 'status_code': 200, 'default_runtime': 'ai_crm_next', 'route_owner': 'ai_crm_next'}
```

`init-db-legacy` output:

```text
init-db-legacy: Legacy Flask runtime has been removed from startup compatibility. Use `python3 app.py run` for AI-CRM Next.
```

Note: latest main has removed legacy Flask startup compatibility, so `init-db-legacy` now exits with the removal message. For PR #51 validation this rehearsal continued with `init-db` alias and `init-next-schema-safe`; the runbook command contract still needs manual confirmation before cutover.

`init-next-schema-safe` output:

```text
{'ok': True, 'initialized_tables': ['customer_list_index_next', 'customer_detail_snapshot_next', 'customer_timeline_event_next', 'customer_recent_message_next', 'user_ops_pool_current_next', 'user_ops_do_not_disturb_next', 'user_ops_send_records_next'], 'drop_or_truncate_executed': False}
```

## 4. customer projection sync

Dry-run summary:

```json
{
  "detail_snapshot_count": 3303,
  "dry_run": true,
  "masked_samples": [
    {
      "external_userid": "wm***XQ",
      "mobile": "",
      "owner_userid_present": true
    },
    {
      "external_userid": "wm***Wg",
      "mobile": "",
      "owner_userid_present": true
    },
    {
      "external_userid": "wm***CA",
      "mobile": "",
      "owner_userid_present": true
    }
  ],
  "ok": true,
  "projected_customer_count": 3303,
  "recent_message_count": 0,
  "reconciliation": {
    "completed_at": "2026-06-09T03:05:19.553786+00:00",
    "diff_count": 0,
    "field_diffs": [],
    "missing_in_source": [],
    "missing_in_target": [],
    "run_id": "b7043e4d31074c67a9a27afd6f2c3aec",
    "source_count": 3303,
    "started_at": "2026-06-09T03:05:19.553775+00:00",
    "status": "dry_run",
    "target_count": 0
  },
  "replace": false,
  "run_id": "e7bc2a0fa8184107b3d7a3ee630b4b60",
  "skipped_count": 0,
  "skipped_reasons": {},
  "source_count": 3303,
  "source_customer_count": 3303,
  "source_name": "live",
  "target_count": 0,
  "timeline_event_count": 0,
  "written_customers": 0,
  "written_recent_messages": 0,
  "written_timeline_events": 0
}
```

Real sync summary:

```json
{
  "detail_snapshot_count": 3303,
  "dry_run": false,
  "masked_samples": [
    {
      "external_userid": "wm***XQ",
      "mobile": "",
      "owner_userid_present": true
    },
    {
      "external_userid": "wm***Wg",
      "mobile": "",
      "owner_userid_present": true
    },
    {
      "external_userid": "wm***CA",
      "mobile": "",
      "owner_userid_present": true
    }
  ],
  "ok": true,
  "projected_customer_count": 3303,
  "recent_message_count": 0,
  "reconciliation": {
    "completed_at": "2026-06-09T03:06:20.009382+00:00",
    "diff_count": 0,
    "field_diffs": [],
    "missing_in_source": [],
    "missing_in_target": [],
    "run_id": "2fd0ecc7f3914c9ab6261e13995a9e27",
    "source_count": 3303,
    "started_at": "2026-06-09T03:06:20.009370+00:00",
    "status": "completed",
    "target_count": 3303
  },
  "replace": false,
  "run_id": "d4750cd6a50144e885aba5492bf108b0",
  "skipped_count": 0,
  "skipped_reasons": {},
  "source_count": 3303,
  "source_customer_count": 3303,
  "source_name": "live",
  "target_count": 3303,
  "timeline_event_count": 0,
  "written_customers": 3303,
  "written_recent_messages": 0,
  "written_timeline_events": 0
}
```

Projection validation:

```text
CREATE TABLE
DELETE 0
DO
                metric                |  result   | count_value 
--------------------------------------+-----------+-------------
 contacts.count                       | ok        |        3303
 customer_detail_snapshot_next.count  | ok        |        3303
 customer_list_index_next.count       | ok        |        3303
 customer_recent_message_next.count   | ok        |           0
 customer_timeline_event_next.count   | ok        |           0
 external_contact_bindings.count      | ok        |           2
 people.count                         | ok        |           2
 projected_external_userid_count      | ok        |        3303
 projection_coverage_against_bindings | 2/2       |           2
 projection_coverage_against_contacts | 3303/3303 |        3303
(10 rows)
```

Key counts:

- customer_detail_snapshot_next: `3303`
- contacts: `3303`
- external_contact_bindings: `2`
- people: `2`
- projection_coverage_against_contacts: `3303/3303`
- projection_coverage_against_bindings: `2/2`
- sampled external_userid: `wm***lw`

## 5. customer/sidebar smoke

```text
PASS projection_count customer_detail_snapshot_next=3303
PASS customer_detail /api/customers/wm***lw status=200
PASS customer_timeline /api/customers/wm***lw/timeline status=200
PASS sidebar_customer_context /api/sidebar/customer-context?external_userid=wm***lw status=200
PASS sidebar_profile /api/sidebar/profile?external_userid=wm***lw status=200
```

Customer/sidebar result using masked external_userid `wm***lw`:

- `/api/customers/{external_userid}`: passed with non-400/non-404/non-503 status
- `/api/customers/{external_userid}/timeline`: passed with non-5xx status
- `/api/sidebar/customer-context`: passed with non-400/non-404/non-503 status
- `/api/sidebar/profile`: passed with non-400/non-404/non-503 status

## 6. 渠道码回归

Channel backfill output:

```text
psql:scripts/siyuan_migration/03_channel_backfill.sql:125: NOTICE:  automation_channel_scene_alias rows inserted: 3
psql:scripts/siyuan_migration/03_channel_backfill.sql:125: NOTICE:  automation_channel_qrcode_asset rows inserted: 3
DO
```

Migration validation:

```text
CREATE TABLE
TRUNCATE TABLE
DO
                  metric                  | value 
------------------------------------------+-------
 admin_user_roles                         | 19
 admin_users                              | 6
 admin_users.total                        | 6
 automation_channel                       | 4
 automation_channel_contact               | 25
 automation_channel_entry_effect_log      | 19
 automation_channel_qrcode_asset          | 3
 automation_channel_scene_alias           | 3
 automation_channel.scene_value_non_empty | 3
 contacts                                 | 3303
 contacts.total                           | 3303
 external_contact_bindings                | 2
 external_contact_bindings.total          | 2
 people                                   | 2
 qrcode_asset_coverage                    | 3/3
 scene_alias_coverage                     | 3/3
 user_ops_do_not_disturb                  | 0
 user_ops_pool_current                    | 0
 user_ops_send_records                    | 0
 wecom_external_contact_event_logs        | 386
(20 rows)
```

Next blocker validation:

```text
CREATE TABLE
DELETE 0
DO
          check_name           | status  | count_value 
-------------------------------+---------+-------------
 customer_detail_snapshot_next | present |        3303
 customer_list_index_next      | present |        3303
 customer_recent_message_next  | present |           0
 customer_timeline_event_next  | present |           0
 user_ops_do_not_disturb_next  | present |           0
 user_ops_pool_current_next    | present |           0
 user_ops_send_records_next    | present |           0
(7 rows)
```

Scene runtime diagnosis samples, all scene values masked:

```text
scene_1 masked=aq***1c status=200 ok=True
scene_2 masked=aq***cb status=200 ok=True
scene_3 masked=aq***ae status=200 ok=True
```

## 7. user-ops 回归

Basic smoke:

```text
[health] GET /health -> 200
HEADER x-aicrm-route-owner: ai_crm_next
HEADER x-aicrm-app: ai_crm_next
HEADER x-aicrm-release-sha: unknown
PASS health status=200

[admin] GET /admin -> 200
HEADER x-aicrm-route-owner: ai_crm_next
HEADER x-aicrm-app: ai_crm_next
HEADER x-aicrm-release-sha: unknown
PASS admin status=200

[admin_channels_page] GET /admin/channels -> 200
HEADER x-aicrm-route-owner: ai_crm_next
HEADER x-aicrm-app: ai_crm_next
HEADER x-aicrm-release-sha: unknown
PASS admin_channels_page status=200

[user_ops_overview] GET /api/admin/user-ops/overview -> 200
HEADER x-aicrm-route-owner: ai_crm_next
HEADER x-aicrm-app: ai_crm_next
HEADER x-aicrm-release-sha: unknown
PASS user_ops_overview status=200

[channel_runtime_diagnosis] GET /api/admin/channels/runtime-diagnosis?scene_value=[REDACTED] -> 200
HEADER x-aicrm-route-owner: ai_crm_next
HEADER x-aicrm-app: ai_crm_next
HEADER x-aicrm-release-sha: unknown
PASS channel_runtime_diagnosis status=200

WARN SAMPLE_EXTERNAL_USERID not set; skipped customer/sidebar read-model smoke checks

PASS smoke test completed without 5xx failures
```

Endpoint status snapshot:

```text
/health 200
/admin 200
/admin/channels 200
/admin/customers 200
/admin/config 200
/admin/api-docs 200
/api/admin/user-ops/overview 200
```

- `fixture_repository_blocked_in_production` observed: `no`

## 8. 后台入口 smoke

- `/admin`: see endpoint status snapshot; no 5xx observed
- `/admin/channels`: see endpoint status snapshot; no 5xx observed
- `/admin/customers`: see endpoint status snapshot; no 5xx observed
- `/admin/config`: see endpoint status snapshot; no 5xx observed
- `/admin/api-docs`: see endpoint status snapshot; no 5xx observed

## 9. 授权配置检查

Only present/missing is recorded:

```text
SECRET_KEY: present
WECOM_CORP_ID: present
WECOM_AGENT_ID: present
WECOM_SECRET: present
WECOM_CONTACT_SECRET: present
WECOM_CALLBACK_TOKEN: present
WECOM_CALLBACK_AES_KEY: present
WECHAT_MP_APP_ID: present
WECHAT_MP_APPID: missing
WECHAT_MP_APP_SECRET: present
ADMIN_LOGIN_REDIRECT_URI: present
CRM_API_TOKEN: present
MCP_BEARER_TOKEN: present
SIDEBAR_THIRD_PARTY_API_TOKEN: present
```

## 10. 风险结论

- Customer projection blocker from PR #49: `resolved_in_staging`
- `customer_detail_snapshot_next` is no longer 0: `3303`
- Customer/sidebar sampled endpoints: passed for masked external_userid `wm***lw`
- User Ops overview: 200 in smoke; no `fixture_repository_blocked_in_production`
- Channel scene diagnosis: 3 masked scene samples returned 200 / ok=true
- Production cutover window review: PR #51 customer projection blocker resolved in staging. Production cutover window review can proceed only after confirming the current runbook no longer requires the removed `init-db-legacy` command.
- Remaining manual confirmation:
  - Confirm/update runbook command sequence because `init-db-legacy` is removed on latest main.
  - Confirm WeCom / WeChat callback settings before cutover.
  - Confirm file assets and verification files are present in the final release path.

## 11. 安全声明

- Did not modify systemd/nginx.
- Did not cut production traffic.
- Did not run DROP/CLEAN/pg_restore against production DB.
- CLEAN=true was used only for explicit staging DB `siyuancrm_next`.
- Did not commit env, dump, uploads, pem/key, real secrets, raw external_userid, raw scene_value, mobile, unionid, or openid.
