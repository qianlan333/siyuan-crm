# siyuan AI-CRM Next completed server staging rehearsal after blocker fix

## 1. 执行环境

- 执行入口：普通 SSH shell，用户 `ubuntu`。
- Rehearsal 目录：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`。
- Commit：`6472741`，包含 PR #48 `Fix siyuan AI-CRM Next production rehearsal blockers`。
- Python：`3.10.12`。
- PostgreSQL CLI：`psql` / `pg_restore` / `pg_dump` 均为 `14.22`。
- Staging DB：`siyuancrm_next`。
- 已确认未修改 systemd/nginx，未切生产，未对生产库执行 `DROP` / `CLEAN` / `pg_restore`。

## 2. Staging DB 权限确认

- `DATABASE_URL`：present，未输出真实值。
- PostgreSQL CLI URL normalize：success，未输出真实值。
- `siyuancrm_next` 写入探针：success。
- `pg_restore --clean --if-exists --no-owner` 仅作用于显式 staging DB `siyuancrm_next`。

## 3. 备份与恢复

使用既有成功备份：

| 资产 | 路径 | 大小 |
|---|---:|---:|
| dump | `/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump` | 2.2M |
| env backup | `/home/ubuntu/backups/siyuan-aicrm-migration/.openclaw-wecom-pg.env.20260609-090350` | 1.4K |
| assets archive | `/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-assets-20260609-090350.tar.gz` | 243B |

恢复结果：

- `02_restore_to_staging_db.sh`: PASS。
- 未打印数据库密码或完整连接串。

## 4. Health / Init / Safe Schema Init

- `python3 app.py health`: 200，`route_owner=ai_crm_next`。
- Historical pre-closeout record: 第一次使用 `postgresql+psycopg://` 执行 `init-db-legacy` 时，legacy psycopg 连接器不接受 SQLAlchemy scheme；未继续该失败路径。
- 改用同一 staging DB 的标准 PostgreSQL URL 后：
  - `python3 app.py health`: 200。
  - Historical pre-closeout `python3 app.py init-db-legacy`: success。
  - Historical pre-closeout `python3 app.py init-next-schema-safe`: success，`drop_or_truncate_executed=False`。

说明：AI-CRM Next SQLAlchemy 入口可接受标准 PostgreSQL URL 并转换；当前 startup closeout 后 schema 变更只走 `python3 -m alembic upgrade head`。

## 5. Customer / User Ops Next 表存在性

Safe schema init 后确认以下表均存在：

- `customer_detail_snapshot_next`
- `customer_list_index_next`
- `customer_recent_message_next`
- `customer_timeline_event_next`
- `user_ops_do_not_disturb_next`
- `user_ops_pool_current_next`
- `user_ops_send_records_next`

新增 blocker validation 结果：

| 表 | 状态 | count |
|---|---:|---:|
| `customer_detail_snapshot_next` | present | 0 |
| `customer_list_index_next` | present | 0 |
| `customer_recent_message_next` | present | 0 |
| `customer_timeline_event_next` | present | 0 |
| `user_ops_do_not_disturb_next` | present | 0 |
| `user_ops_pool_current_next` | present | 0 |
| `user_ops_send_records_next` | present | 0 |

## 6. Channel Backfill 和 Coverage

- `03_channel_backfill.sql`: success。
- `04_validate_migration.sql`: success。

关键指标：

| 指标 | 值 |
|---|---:|
| `automation_channel` | 4 |
| `automation_channel.scene_value_non_empty` | 3 |
| `automation_channel_scene_alias` | 3 |
| `automation_channel_qrcode_asset` | 3 |
| `scene_alias_coverage` | 3/3 |
| `qrcode_asset_coverage` | 3/3 |
| `automation_channel_contact` | 25 |
| `automation_channel_entry_effect_log` | 19 |
| `wecom_external_contact_event_logs` | 386 |

## 7. User / Sidebar Data Counts

| 表 | count |
|---|---:|
| `contacts` | 3303 |
| `external_contact_bindings` | 2 |
| `people` | 2 |
| `admin_users` | 6 |
| `customer_detail_snapshot_next` | 0 |
| `user_ops_pool_current_next` | 0 |

基础数据未在 restore/init/backfill 中丢失；但 Next customer read-model projection 表当前为空。

## 8. Smoke Test

临时 staging 服务：

- 端口：`127.0.0.1:5011`
- `/health`: 200
- `database_mode=postgres`
- `fixture_mode=false`
- `production_data_ready=true`

`05_smoke_test.sh` 结果：

| Endpoint | 结果 |
|---|---:|
| `/health` | 200 |
| `/admin` | 200 |
| `/admin/channels` | 200 |
| `/api/admin/user-ops/overview` | 200 |
| `/api/admin/channels/runtime-diagnosis?scene_value=[REDACTED]` | 200 |
| `/api/customers/[REDACTED]` | 404 |
| `/api/customers/[REDACTED]/timeline` | 404 |
| `/api/sidebar/customer-context?external_userid=[REDACTED]` | 404 |
| `/api/sidebar/profile?external_userid=[REDACTED]` | 400 |

结论：

- 无 5xx。
- User Ops overview 不再返回 `fixture_repository_blocked_in_production`。
- Customer/sidebar endpoint 不再因为 `customer_detail_snapshot_next` 缺失返回 schema-missing 503。
- Customer/sidebar 当前 404/400 的原因是 Next projection 表为空，需要生产切换前补齐或确认 projection backfill 策略。

额外后台入口：

| Endpoint | 结果 |
|---|---:|
| `/admin/customers` | 200 |
| `/admin/config` | 200 |
| `/admin/api-docs` | 200 |

## 9. 旧 Scene Runtime Diagnosis

抽样 3 个旧 scene，报告中全部脱敏：

| Scene | HTTP | ok |
|---|---:|---:|
| `[REDACTED-1]` | 200 | true |
| `[REDACTED-2]` | 200 | true |
| `[REDACTED-3]` | 200 | true |

## 10. 授权配置 Present/Missing

只检查存在性，未输出真实值：

| 配置 | 状态 |
|---|---|
| `SECRET_KEY` | present |
| `WECOM_CORP_ID` | present |
| `WECOM_AGENT_ID` | present |
| `WECOM_SECRET` | present |
| `WECOM_CONTACT_SECRET` | present |
| `WECOM_CALLBACK_TOKEN` | present |
| `WECOM_CALLBACK_AES_KEY` | present |
| `WECHAT_MP_APP_ID` | present |
| `WECHAT_MP_APPID` | missing |
| `WECHAT_MP_APP_SECRET` | present |
| `ADMIN_LOGIN_REDIRECT_URI` | present |
| `CRM_API_TOKEN` | missing |
| `MCP_BEARER_TOKEN` | missing |
| `SIDEBAR_THIRD_PARTY_API_TOKEN` | missing |

## 11. 修复验证结论

原 blocker 修复结果：

- User Ops production repository wiring：通过。`/api/admin/user-ops/overview` 为 200，空表返回 0 metrics，不再触发 fixture repo blocker。
- Customer read-model schema missing：通过。safe schema init 后 blocker 表存在，customer/sidebar endpoint 不再因缺 `customer_detail_snapshot_next` 返回 503。
- Channel runtime：通过。3 个旧 scene diagnosis 均 200/ok=true。
- 后台入口：通过。核心后台入口无 5xx。

仍需人工确认项：

- Next customer read-model projection 表为空；生产切换前需要执行或确认 customer projection backfill/source sync，否则 customer/sidebar 对真实 external_userid 只能返回 not_found/input_error。
- Historical pre-closeout `init-db-legacy` URL 限制仅保留为演练记录；当前生产 runbook 不再使用 legacy init。
- `scripts/siyuan_migration/07_validate_next_blockers.sql` 原版本在 psql autocommit 下会因 `ON COMMIT DROP` 失败；本报告 PR 同步修复为普通临时表并使用 `DELETE` 清空。

## 12. 是否可以进入生产切换窗口

不建议立即进入生产切换窗口。

原因不是原 blocker 仍存在，而是 Next customer/sidebar projection 仍为空。建议先补齐或确认 customer read-model projection backfill，再重新执行 smoke test 中的 customer/sidebar 抽样，确认不只是 404/400。

## 13. 生产切换建议

1. 冻结写入入口。
2. 做最终生产 DB/env/assets 备份。
3. 恢复最终 dump 到 staging/next DB。
4. 执行 `python3 -m alembic upgrade head`、channel backfill、customer projection backfill。
5. 跑 smoke test 和 3 个旧 scene diagnosis。
6. 人工确认 customer/sidebar 至少能读取抽样客户基础信息。
7. 再切 systemd/nginx 到新 release。
8. 切换后观察 `/health`、后台入口、企业微信 callback、5xx。
9. 异常时切回旧代码目录和旧 `DATABASE_URL`，必要时从备份恢复。
