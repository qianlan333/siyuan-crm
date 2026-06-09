# siyuan AI-CRM Next 生产切换报告 - 2026-06-09

## 1. 基本信息

- 执行时间：2026-06-09 11:44-11:54 CST
- 执行人：Codex via authorized SSH shell
- 代码 commit：`0b6d7944` (`Merge pull request #54`)
- 旧 release 路径：`/home/ubuntu/极简 crm`
- 新 release 路径：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`
- 旧 DB 标识：`openclaw`
- 新 DB 标识：`siyuancrm_next_prod`
- 切换策略：策略 A，新生产库切换
- 切换结论：No-Go，已回滚

## 2. 切换前确认

- 新 release 目录存在。
- PR #54 已同步到服务器 release，commit 为 `0b6d7944`。
- `git status --short` 干净。
- `bash -n scripts/siyuan_migration/*.sh scripts/siyuan_migration/lib_db_url.sh` 通过。
- `scripts/siyuan_migration/test_lib_db_url.sh` 通过。
- `scripts/siyuan_migration/10_cutover_readiness_check.sh` 通过，关键命令、迁移脚本和 app 子命令均存在。
- 服务器无法直接从 GitHub 拉取，表现为 GitHub TLS/443 连接失败；本次使用本地 `origin/main` 生成 git bundle 后在服务器上 `git fetch bundle + merge --ff-only`，未使用 reset。
- 服务器已有未跟踪 staging 报告文件，已先移动到仓库外 `/tmp/siyuan-crm-untracked-backup-20260609-114639/`，避免覆盖用户产物。

## 3. 冻结写入入口

- 冻结开始时间：2026-06-09 11:48:33 CST
- 已停止主服务：`openclaw-wecom-postgres.service`
- 已停止 timer/service：
  - `openclaw-automation-conversion-due-runner.timer`
  - `openclaw-external-contact-sync.timer`
  - `openclaw-external-contact-full-sync.timer`
  - `openclaw-external-push-worker.timer`
  - 对应 service 如正在运行也已停止
- 冻结完成时间：2026-06-09 11:48:41 CST
- 风险说明：本次通过停止主服务冻结全部 Web 写入，因此只读后台查看在冻结窗口内也不可用。

## 4. 最终备份

| 项目 | 路径 | 大小 | 结果 |
| --- | --- | --- | --- |
| dump | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-current-20260609-114849.dump` | 2242680 bytes | 成功 |
| env backup | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/.openclaw-wecom-pg.env.20260609-114849` | 1386 bytes | 成功 |
| assets archive | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-assets-20260609-114849.tar.gz` | 243 bytes | 成功 |
| config backup | `/home/ubuntu/backups/siyuan-aicrm-cutover-final/config-backups-20260609-115152/` | N/A | 成功 |

安全说明：备份文件未放入 git 仓库，报告不包含 env 内容或完整数据库 URL。

## 5. 新生产库准备与恢复

- 目标 DB：`siyuancrm_next_prod`
- 应用 DB 用户直接 `createdb` 失败，原因是无 `CREATEDB` 权限。
- 使用本机 PostgreSQL 管理员创建 `siyuancrm_next_prod` 并授权给当前应用 DB 用户。
- 新 DB 写入探针：成功。
- `pg_restore`：成功。
- `CLEAN=true` 仅作用于 `siyuancrm_next_prod`，未对旧生产库执行 `DROP` / `CLEAN` / `pg_restore`。

## 6. 初始化与 Projection Sync

| 命令 | 结果 | 备注 |
| --- | --- | --- |
| `python3 app.py health` | 成功 | status_code 200, `default_runtime=ai_crm_next`, `route_owner=ai_crm_next` |
| `python3 app.py init-db` | 成功 | 转发到 `init-next-schema-safe` |
| `python3 app.py init-next-schema-safe` | 成功 | 7 张 Next 表初始化检查通过，未执行 drop/truncate |
| `python3 app.py sync-customer-read-model --dry-run` | 成功 | source/projected customer count 为 3303 |
| `python3 app.py sync-customer-read-model` | 成功 | 写入 projection 成功 |

Projection 结果：

- source_customer_count：3303
- projected_customer_count：3303
- customer_detail_snapshot_next：3303
- customer_list_index_next：3303
- customer_timeline_event_next：0
- customer_recent_message_next：0
- skipped_count：0
- skipped_reasons：`{}`
- projection_coverage_against_contacts：3303/3303
- projection_coverage_against_bindings：2/2

## 7. Channel Backfill 与 Validation

- `03_channel_backfill.sql`：成功。
- `automation_channel`：4
- `automation_channel.scene_value_non_empty`：3
- `automation_channel_scene_alias`：3
- `automation_channel_qrcode_asset`：3
- `scene_alias_coverage`：3/3
- `qrcode_asset_coverage`：3/3
- `contacts`：3303
- `external_contact_bindings`：2
- `people`：2
- `admin_users`：6
- 7 张 Next blocker 表全部存在。

## 8. 切换与 Smoke Test

已执行：

- systemd 配置备份成功。
- env 配置备份成功。
- systemd `WorkingDirectory` 切到新 release。
- env `DATABASE_URL` 切到 `siyuancrm_next_prod`。
- `sudo systemctl daemon-reload` 成功。
- `sudo nginx -t` 成功。
- `sudo systemctl restart openclaw-wecom-postgres.service` 成功。

切换后通过项：

- `/health`：200。
- `https://www.xinliushangye.com/health`：200。
- `/admin`：200。
- `/admin/channels`：200。
- `/admin/customers`：200。
- `/admin/config`：200。
- `/admin/api-docs`：200。
- `/api/admin/user-ops/overview`：200。
- `/api/customers/{external_userid}`：200，ID 已在执行输出中脱敏。
- `/api/customers/{external_userid}/timeline`：200，ID 已在执行输出中脱敏。
- `/api/sidebar/customer-context`：200，ID 已在执行输出中脱敏。
- `/api/sidebar/profile`：200，ID 已在执行输出中脱敏。
- 3 个旧 scene runtime diagnosis：均 200 / `ok=true`，scene 已脱敏。
- `/wecom/external-contact/callback`：400 `invalid callback signature`，无 5xx。
- `/api/wecom/events`：400 `invalid callback signature`，无 5xx。

## 9. No-Go Blocker

切换后发现关键 blocker：

- `/auth/wecom/callback`：503。
- `/auth/wecom/callback?code=<dummy>&state=<dummy>`：503。
- 响应错误为 `external_call_blocked`。
- 代码行为显示 `aicrm_next/auth_wecom/api.py` 当前将 WeCom admin auth external calls 显式阻断，返回 `adapter_mode=real_blocked`。

影响判断：

- 该路径是项目交接中记录的企业微信授权登录回调地址。
- 即使核心后台页面、渠道码、customer/sidebar、user-ops 均通过，企业微信后台登录 callback 503 仍属于生产切换 Go 条件失败。
- 按 runbook 执行 No-Go，并回滚。

## 10. 回滚结果

- 回滚时间：2026-06-09 11:54:06 CST
- 已从 `/home/ubuntu/backups/siyuan-aicrm-cutover-final/config-backups-20260609-115152/` 恢复：
  - `openclaw-wecom-postgres.service.before-cutover`
  - `.openclaw-wecom-pg.env.before-cutover`
- systemd `WorkingDirectory` 已恢复为 `/home/ubuntu/极简 crm`。
- 主服务已 restart 且 active。
- timers 已恢复：
  - `openclaw-automation-conversion-due-runner.timer`
  - `openclaw-external-contact-sync.timer`
  - `openclaw-external-contact-full-sync.timer`
  - `openclaw-external-push-worker.timer`

回滚后验证：

- `http://127.0.0.1:5001/health`：200。
- `https://www.xinliushangye.com/health`：200。
- `http://127.0.0.1:5001/admin`：200。
- `https://www.xinliushangye.com/admin`：200。
- `/wecom/external-contact/callback`：400 `invalid callback signature`，无 5xx。
- `/api/wecom/events`：400 `invalid callback signature`，无 5xx。
- `/auth/wecom/callback`：仍为 503 `external_call_blocked`。

说明：回滚恢复了旧 release 与旧 DB，核心健康检查和后台可用；但 `/auth/wecom/callback` 503 在回滚后仍存在，说明该问题属于当前生产代码路径中的 WeCom admin auth blocker，需要专项修复或确认该路径是否已不再作为真实登录入口。

## 11. Go / Rollback

- 是否 Go：否。
- 是否完成生产切换：否。
- 是否执行回滚：是。
- 是否需要数据恢复：否。旧生产库未被 `DROP` / `CLEAN` / `pg_restore`，采用新生产库切换，回滚只需切回旧 release/旧 DB。
- 是否需要 blocker 修复 PR：是。

## 12. 遗留问题与下一步

必须先处理：

1. 修复或配置 WeCom admin auth live callback，使 `/auth/wecom/callback` 不再返回 `external_call_blocked` 503。
2. 明确 `/auth/wecom/callback` 是否仍是生产后台登录真实入口。
3. 若该路径已废弃，需要同步更新企业微信后台回调配置、交接文档和生产切换 Go/No-Go 标准。
4. 修复后重新执行 production cutover rehearsal 或正式切换窗口。

建议 PR 标题：

`Fix siyuan AI-CRM Next WeCom admin auth callback blocker`

## 13. 安全声明

- 未提交 `.env`、dump、uploads、instance、pem/key。
- 未在报告中记录完整 `DATABASE_URL`。
- 未在报告中记录数据库密码、token、secret、AESKey、私钥。
- 未在报告中记录 raw `external_userid`、raw `scene_value`、手机号、unionid、openid。
- 未对旧生产库执行 `DROP` / `CLEAN` / `pg_restore`。
- 新生产库 `siyuancrm_next_prod` 保留为本次 No-Go 调查证据，未作为生产服务继续使用。
