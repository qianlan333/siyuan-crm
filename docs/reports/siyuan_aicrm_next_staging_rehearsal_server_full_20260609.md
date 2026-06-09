# siyuan-crm AI-CRM Next full server staging rehearsal - 2026-06-09

## 1. 执行环境

- 仓库：`qianlan333/siyuan-crm`
- 服务器入口：通过项目交接文档中的普通 SSH shell 入口登录。
- 服务器用户：`ubuntu`
- rehearsal 目录：`/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609`
- 代码来源：由于服务器访问 GitHub 443 超时，本次使用本地 `origin/main` 生成 git bundle 后上传到服务器 clone。
- 当前 commit：`20b4186bcc5f25ee10dcc2406497e541ff96b2a2`
- 最近提交包含：
  - `20b4186 Merge pull request #43 from qianlan333/docs/record-blocked-server-staging-rehearsal`
  - `9a60b98 Record blocked siyuan server staging rehearsal`
  - `d7e5582 Merge pull request #42 from qianlan333/codex/fix-channel-qrcode-generate-feedback`
  - `55ea97b Fix channel QR code generate feedback`
  - `61d525a Merge pull request #41 from qianlan333/codex/normalize-siyuan-pg-cli-url`
- PR #40/#41 状态：当前 main 晚于 `61d525ad`，包含 PostgreSQL CLI URL normalize 修复，并晚于 AI-CRM Next 产品基线迁移。
- Python：`3.10.12`
- PostgreSQL CLI：`psql`、`pg_dump`、`pg_restore` 均可用。
- 是否使用 staging DB：否，`siyuancrm_next` 创建失败，未进入 restore 阶段。
- 是否修改 systemd/nginx：否。

## 2. 脚本基础检查

已运行：

```bash
bash -n scripts/siyuan_migration/*.sh scripts/siyuan_migration/lib_db_url.sh
scripts/siyuan_migration/test_lib_db_url.sh
scripts/siyuan_migration/00_preflight.sh
```

结果：

- `bash -n`：通过。
- `test_lib_db_url.sh`：`PASS lib_db_url normalize_pg_cli_url tests`。
- `00_preflight.sh`：
  - `PASS required commands are available`
  - `PASS python version 3.10.12`
  - `WARN DATABASE_URL is not set in the current shell; source the siyuan env file before DB checks`
  - `PASS current branch is main`
  - `PASS no tracked or staged local modifications`
  - `PASS no pending sensitive files detected in git status`
  - `PASS no tracked sensitive files detected`
  - `PASS preflight completed`

## 3. 生产 env 和资产目录

- `/home/ubuntu/.openclaw-wecom-pg.env`：存在。
- `DATABASE_URL`：present。
- PostgreSQL CLI URL normalize：success。
- `/home/ubuntu/current-siyuan-crm`：不存在。
- 生产资产目录：`/home/ubuntu/极简 crm`。
- 未打印完整 `DATABASE_URL`。
- 未打印数据库密码、token、secret、AESKey 或私钥。

## 4. 备份结果

已执行生产数据库/env/文件资产备份：

```bash
BACKUP_DIR=/home/ubuntu/backups/siyuan-aicrm-migration \
ENV_FILE=/home/ubuntu/.openclaw-wecom-pg.env \
APP_DIR="/home/ubuntu/极简 crm" \
scripts/siyuan_migration/01_backup_current_assets.sh
```

最新成功备份文件：

| 类型 | 路径 | 大小 |
| --- | --- | --- |
| PostgreSQL dump | `/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump` | 2213161 bytes |
| env backup | `/home/ubuntu/backups/siyuan-aicrm-migration/.openclaw-wecom-pg.env.20260609-090350` | 1386 bytes |
| assets archive | `/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-assets-20260609-090350.tar.gz` | 243 bytes |

备份文件未放入 git。

### 备份脚本问题

首次执行 `01_backup_current_assets.sh` 时，生产 DB dump 和 env backup 已写入，但 assets 打包在 `uploads/`、`static/uploads/`、`instance/` 不存在时失败。原因是脚本把不存在的字面目录传给了 `tar`。

已开独立修复 PR：

- PR：`#44 Fix siyuan staging rehearsal script issue: tolerate missing asset paths`
- 修复内容：只把实际存在的资产路径传给 `tar`。

为继续本次演练，服务器 rehearsal 目录临时应用了 PR #44 同款脚本修复，并重新执行备份成功。该修复只影响迁移脚本资产打包容错，不修改业务代码、不修改生产配置、不修改数据库。

## 5. staging DB 创建结果

目标 staging DB：`siyuancrm_next`

检查结果：`siyuancrm_next` 不存在。

尝试使用生产 env 中的 PostgreSQL CLI URL 创建：

```bash
psql "$PG_CLI_DATABASE_URL" -v ON_ERROR_STOP=1 -c 'CREATE DATABASE siyuancrm_next;'
```

结果：

```text
ERROR:  permission denied to create database
```

随后按迁移步骤尝试：

```bash
createdb siyuancrm_next
```

结果：

```text
createdb: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: FATAL:  role "ubuntu" does not exist
```

结论：当前服务器 shell 可用，生产库可 `pg_dump`，但当前 PostgreSQL 权限不足以创建 staging DB `siyuancrm_next`。

## 6. 恢复结果

未执行 `pg_restore`。

原因：staging DB `siyuancrm_next` 未能创建。

安全边界确认：

- 未对生产库执行 `DROP`。
- 未对生产库执行 `CLEAN`。
- 未对生产库执行 `pg_restore`。
- 未对任何非显式 staging DB 执行 restore。

## 7. health / schema 初始化

未执行：

- `python3 app.py health`
- `python3 app.py routes`
- `historical deprecated python3 app.py init-db-legacy`

原因：`siyuancrm_next` 未创建，AI-CRM Next 不能连接 staging DB 验证。

## 8. 渠道码 backfill

未执行：

- backfill 前 count
- `03_channel_backfill.sql`
- `04_validate_migration.sql`
- scene alias 覆盖率
- qrcode asset 覆盖率

原因：未恢复 dump 到 staging DB。

## 9. 用户/侧边栏数据

未执行：

- `contacts` count
- `external_contact_bindings` count
- `people` count
- 抽样 read model / sidebar API

原因：未恢复 dump 到 staging DB。

## 10. 后台 smoke test

未执行：

- `/health`
- `/admin`
- `/admin/channels`
- `/api/admin/user-ops/overview`
- scene runtime diagnosis

原因：staging 服务未启动，未连接 staging DB。

## 11. 授权配置 present/missing

未执行完整 present/missing 列表。

已确认：

- `/home/ubuntu/.openclaw-wecom-pg.env` 存在。
- `DATABASE_URL` present。
- PostgreSQL CLI URL normalize success。

未打印任何真实授权配置值。

## 12. 风险结论

当前结论：不能进入生产切换窗口。

本次真实 server rehearsal 已完成到：

- 普通 shell 登录成功。
- siyuan-crm AI-CRM Next rehearsal 代码目录准备完成。
- 迁移脚本基础检查通过。
- 生产 env 存在，`DATABASE_URL` present，CLI URL normalize 成功。
- 真实生产 DB 已 `pg_dump` 成功。
- env backup 成功。
- 文件资产 archive 成功。

阻塞点：

- 当前 PostgreSQL 权限无法创建 `siyuancrm_next`。
- 因此未执行 `pg_restore`、schema init、channel backfill、validate、smoke test。

是否需要 blocker 修复 PR：

- 需要合并 PR #44，以修复缺失资产目录时 backup 脚本失败的问题。
- 还需要运维提供 staging DB 创建权限，或预先创建 `siyuancrm_next` 并授权当前应用 DB 用户写入。

## 13. 仍需人工确认项

继续完整 staging rehearsal 前，需要人工完成至少一项：

1. 由 PostgreSQL 管理员创建 staging DB：

   ```sql
   CREATE DATABASE siyuancrm_next;
   ```

2. 或授予当前演练所用 DB 用户创建数据库权限。

3. 或提供一个已经存在、可由当前应用 DB 用户 clean/restore/write 的 `siyuancrm_next`。

完成后再从 restore 阶段继续：

```bash
DUMP_FILE=/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-20260609-090350.dump \
STAGING_DATABASE_URL="$STAGING_DATABASE_URL" \
CLEAN=true \
scripts/siyuan_migration/02_restore_to_staging_db.sh
```

## 14. 生产切换建议

当前不建议切换生产。

只有完整 staging rehearsal 通过后，再进入生产切换窗口：

1. 冻结写入入口或降低写入流量。
2. 做最终生产数据库/env/文件资产备份。
3. 部署新 release，但不提交真实 env、dump、uploads、pem/key。
4. 切 systemd/nginx 指向新 release。
5. 运行 `/health`、`/admin`、`/admin/channels`、`/api/admin/user-ops/overview` smoke test。
6. 观察企业微信 callback、渠道码 runtime diagnosis 和 5xx。
7. 异常时切回旧代码目录和旧 `DATABASE_URL`，必要时用最终备份恢复。
