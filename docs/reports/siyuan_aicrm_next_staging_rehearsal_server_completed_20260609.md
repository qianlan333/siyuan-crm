# siyuan-crm AI-CRM Next server staging rehearsal - 2026-06-09

## 1. 执行环境

- 仓库：`qianlan333/siyuan-crm`
- 服务器入口：项目交接文档中的普通 SSH shell 入口。
- rehearsal 目录：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`
- 代码同步方式：服务器到 GitHub 443 连接不稳定，使用本地 `origin/main` 生成 git bundle 后同步到服务器。
- commit sha：`f5e521713d8e51f01fa5bb8163f1afe8032dcec6`
- main 状态：包含 PR #44 和 PR #45，且晚于 PR #40/#41。
- Python：`3.10.12`
- PostgreSQL CLI：`psql`、`pg_dump`、`pg_restore` 均可用。
- staging DB：`siyuancrm_next`
- staging 连接：应用 DB 用户可连接、可写、可执行 `pg_restore --clean --if-exists --no-owner`。
- systemd/nginx：未修改。
- 生产切换：未执行。

基础检查结果：

- `bash -n scripts/siyuan_migration/*.sh scripts/siyuan_migration/lib_db_url.sh`：通过。
- `scripts/siyuan_migration/test_lib_db_url.sh`：通过。
- `scripts/siyuan_migration/00_preflight.sh`：通过；加载 env 前出现 `DATABASE_URL is not set` 的预期 warning。
- `DATABASE_URL`：present。
- PostgreSQL CLI URL normalize：success。

## 2. 备份结果

使用生产 env 与生产资产目录执行备份：

- 生产资产目录：`/home/ubuntu/极简 crm`
- dump：`/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump`
- dump size：`2213161 bytes`
- env backup：`/home/ubuntu/backups/siyuan-aicrm-migration/.openclaw-wecom-pg.env.20260609-090350`
- env backup size：`1386 bytes`
- assets archive：`/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-assets-20260609-090350.tar.gz`
- assets archive size：`243 bytes`

备份文件未放入 git。报告不包含 env 内容、数据库 URL、密码、token、secret、AESKey 或私钥。

## 3. 恢复结果

已将生产 dump 恢复到 staging DB：

- staging DB：`siyuancrm_next`
- dump file：`/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump`
- restore command：`scripts/siyuan_migration/02_restore_to_staging_db.sh`
- `CLEAN=true`：仅作用于显式 staging DB `siyuancrm_next`
- pg_restore：成功

安全边界确认：

- 未对生产库执行 `DROP`。
- 未对生产库执行 `CLEAN`。
- 未对生产库执行 `pg_restore`。
- 未修改 systemd/nginx。

## 4. health / schema 初始化

AI-CRM Next 连接 staging DB 后执行：

- `python3 app.py health`：成功
- status_code：`200`
- default_runtime：`ai_crm_next`
- route_owner：`ai_crm_next`
- `python3 app.py routes`：成功
- route inventory count：`594`
- `historical deprecated python3 app.py init-db-legacy`：成功

关键表存在性：

- `admin_user_roles`
- `admin_users`
- `automation_channel`
- `automation_channel_contact`
- `automation_channel_entry_effect_log`
- `automation_channel_qrcode_asset`
- `automation_channel_scene_alias`
- `contacts`
- `external_contact_bindings`
- `people`
- `user_ops_do_not_disturb`
- `user_ops_pool_current`
- `user_ops_send_records`

补充检查：

- 直接运行 `python3 app.py routes | head` 会触发 Python `BrokenPipeError`，因为 `head` 提前关闭管道。
- 改为先输出到临时文件再 `head` 后 route inventory 正常。

## 5. 渠道码 backfill

backfill 前：

| table | count |
| --- | ---: |
| automation_channel | 4 |
| automation_channel_scene_alias | 0 |
| automation_channel_qrcode_asset | 0 |

执行：

- `03_channel_backfill.sql`：成功
- 首次插入 scene alias：`3`
- 首次插入 qrcode asset：`3`

幂等复跑：

- scene alias 新增：`0`
- qrcode asset 新增：`0`

validation 结果：

| metric | value |
| --- | ---: |
| automation_channel | 4 |
| automation_channel.scene_value_non_empty | 3 |
| automation_channel_scene_alias | 3 |
| automation_channel_qrcode_asset | 3 |
| scene_alias_coverage | 3/3 |
| qrcode_asset_coverage | 3/3 |
| contacts.total | 3303 |
| external_contact_bindings.total | 2 |
| people | 2 |
| admin_users.total | 6 |
| wecom_external_contact_event_logs | 386 |

渠道码判断：

- `scene_value_non_empty > 0`，且 scene alias 覆盖率为 `3/3`。
- qrcode asset 覆盖率为 `3/3`。
- 3 个抽样旧 scene 的 runtime diagnosis 均无 5xx，状态均为 `200`，返回 `ok=true`。

### validation SQL 修复

`04_validate_migration.sql` 首次执行失败：

```text
ERROR: column reference "table_name" is ambiguous
```

原因是 PL/pgSQL 变量 `table_name` 与 `information_schema.columns.table_name` 列名歧义。

已开独立修复 PR：

- PR #46：`Fix siyuan staging rehearsal script issue: avoid validate table_name ambiguity`

服务器 rehearsal 目录临时应用 PR #46 同款 SQL 修复后，validation 成功。

## 6. 用户/侧边栏数据

基础数据 count：

| table | count |
| --- | ---: |
| contacts | 3303 |
| external_contact_bindings | 2 |
| people | 2 |

脱敏绑定抽样：

- `external_userid`：present
- `person_id`：present
- `first_owner_userid`：present
- bindings with external_userid：`2`
- bindings with person_id：`2`

read model / sidebar endpoint 检查：

| endpoint | status |
| --- | ---: |
| `/admin/customers/{external_userid}` | 200 |
| `/api/customers/{external_userid}` | 503 |
| `/api/customers/{external_userid}/timeline` | 503 |
| `/api/sidebar/customer-context` | 503 |
| `/api/sidebar/profile` | 503 |

503 原因：

```text
customer_detail_snapshot_next relation does not exist
```

影响：

- 旧用户基础数据本身已恢复到 staging：`contacts=3303`、`external_contact_bindings=2`、`people=2`。
- 后台 customer detail 页面可打开。
- Next customer read model / sidebar API 依赖的 `customer_detail_snapshot_next` 尚未创建，相关 API 返回 503。

## 7. 后台 smoke test

staging 服务端口：

- `127.0.0.1:5001` 已被占用。
- 为避免影响现有生产进程，本次 staging app 使用临时端口 `127.0.0.1:5011`。

smoke result：

| endpoint | status | result |
| --- | ---: | --- |
| `/health` | 200 | PASS |
| `/admin` | 200 | PASS |
| `/admin/channels` | 200 | PASS |
| `/api/admin/user-ops/overview` | 503 | FAIL |
| runtime diagnosis sample | 200 | PASS |

额外入口检查：

| endpoint | status |
| --- | ---: |
| `/admin/customers` | 200 |
| `/admin/config` | 200 |
| `/admin/api-docs` | 200 |

`/api/admin/user-ops/overview` 503 原因：

```text
fixture_repository_blocked_in_production
```

解释：

- `AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD=false` 已生效。
- 该 endpoint 在 production mode 下仍落到 fixture/in-memory user ops repository，被生产 guard 拦截。
- 这属于 Next user-ops repository/provider wiring blocker，不能进入生产切换窗口。

## 8. 授权配置 present/missing

只检查存在性，未打印真实值：

| key | status |
| --- | --- |
| SECRET_KEY | present |
| WECOM_CORP_ID | present |
| WECOM_AGENT_ID | present |
| WECOM_SECRET | present |
| WECOM_CONTACT_SECRET | present |
| WECOM_CALLBACK_TOKEN | present |
| WECOM_CALLBACK_AES_KEY | present |
| WECHAT_MP_APP_ID | present |
| WECHAT_MP_APPID | missing |
| WECHAT_MP_APP_SECRET | present |
| ADMIN_LOGIN_REDIRECT_URI | present |
| CRM_API_TOKEN | missing |
| MCP_BEARER_TOKEN | missing |
| SIDEBAR_THIRD_PARTY_API_TOKEN | missing |

## 9. 迁移/脚本问题

本次演练发现两个脚本层问题：

1. `01_backup_current_assets.sh` 对不存在的字面资产目录不容错。
   - 已修复：PR #44。
   - main 已包含该修复。

2. `04_validate_migration.sql` 存在 `table_name` 歧义。
   - 已开 PR：#46。
   - rehearsal 临时应用该修复后 validation 通过。

还发现一个迁移体系问题：

- `python3 -m alembic current` 和 `python3 -m alembic upgrade head` 在 staging DB 上失败。
- 原因：migrations revision graph 有重复 revision `0012`、`0016`，且 `0014` 引用缺失的 `0013`。
- 因此无法通过 Alembic 自动创建 `customer_detail_snapshot_next` 等 Next customer read-model 表。

## 10. 风险结论

当前结论：不能进入生产切换窗口。

已通过：

- 真实生产 DB 备份成功。
- dump 恢复到 `siyuancrm_next` 成功。
- AI-CRM Next 可连接 staging DB。
- `/health` 成功。
- Historical record: deprecated `init-db-legacy` succeeded during that rehearsal; current startup closeout uses `init-next-schema-safe` instead.
- channel backfill 成功且幂等。
- validate migration 在应用 PR #46 修复后输出完整。
- 3 个旧 scene runtime diagnosis 均无 5xx。
- `/admin`、`/admin/channels`、`/admin/customers`、`/admin/config`、`/admin/api-docs` 均无 5xx。
- `contacts`、`external_contact_bindings`、`people` 数据未丢。

阻塞：

- `/api/admin/user-ops/overview` 返回 503：生产模式下 user-ops repository/provider 仍落入 fixture/in-memory，被 guard 拦截。
- `/api/customers/{external_userid}`、`/api/customers/{external_userid}/timeline`、`/api/sidebar/customer-context`、`/api/sidebar/profile` 返回 503：缺少 `customer_detail_snapshot_next`。
- Alembic revision graph 损坏，无法自动创建 Next customer read-model 表。

需要 blocker 修复：

- 修复或补充 user-ops production repository/provider wiring。
- 修复 customer read-model schema 初始化路径，确保 `customer_detail_snapshot_next` 等表能在 staging/production schema upgrade 中创建。
- 修复 Alembic revision graph，或提供可重复执行的 safe schema init 脚本。

## 11. 仍需人工确认项

- 是否接受 `WECHAT_MP_APPID` missing，但 `WECHAT_MP_APP_ID` present。
- `CRM_API_TOKEN`、`MCP_BEARER_TOKEN`、`SIDEBAR_THIRD_PARTY_API_TOKEN` missing 是否符合 siyuan 当前生产配置预期。
- staging app 使用 `5011` 端口是为了避免占用 `5001` 的现有进程；生产切换前仍需确认正式端口和服务编排。

## 12. 生产切换建议

当前不建议切换生产。

待 blocker 修复并重新完整 staging rehearsal 通过后，再进入生产切换窗口：

1. 冻结写入入口或降低写入流量。
2. 做最终生产数据库/env/文件资产备份。
3. 部署新 release，但不提交真实 env、dump、uploads、pem/key。
4. 切 systemd/nginx 指向新 release。
5. 运行 `/health`、`/admin`、`/admin/channels`、`/api/admin/user-ops/overview` smoke test。
6. 验证 customer read-model/sidebar endpoints 无 5xx。
7. 观察企业微信 callback、渠道码 runtime diagnosis 和 5xx。
8. 异常时切回旧代码目录和旧 `DATABASE_URL`，必要时用最终备份恢复。
