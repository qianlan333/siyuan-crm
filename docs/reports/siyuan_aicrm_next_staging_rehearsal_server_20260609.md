# siyuan-crm AI-CRM Next server staging rehearsal report - 2026-06-09

## 1. 执行环境

- 目标：在真实服务器或预发服务器继续执行 siyuan-crm AI-CRM Next staging rehearsal。
- 本次可达服务器入口：`crm-prod`。
- 服务器通道模式：只读受限诊断通道。
- 服务器用户状态：`user=ubuntu cwd=/home/ubuntu host=VM-0-17-ubuntu mode=read-only`。
- 数据库只读状态：`pg-user: claude_ro (SELECT only, default_transaction_read_only=on)`。
- PostgreSQL 状态：`/var/run/postgresql:5432 - accepting connections`。
- 是否使用 staging DB：否，因当前通道无建库、恢复、写入权限，已停止。
- 是否触碰 production systemd/nginx：否。

## 2. 服务器入口能力边界

`crm-prod` 入口返回的是 `claude-debug.sh` 受限通道，只允许以下只读子命令：

- `logs`
- `status`
- `tail`
- `health`
- `pg-status`
- `git-status`
- `ps` / `disk` / `mem` / `whoami`
- `psql` / `psql-stdin`，且只读 SELECT
- `cat` / `ls`，并禁止读取 `.env`、`.pem`、`.key`、`.pgpass`、SSH 私钥等敏感文件

因此当前入口不能执行：

- `git fetch`
- `git checkout main`
- `git pull --ff-only origin main`
- `bash -n scripts/...`
- `scripts/siyuan_migration/test_lib_db_url.sh`
- `scripts/siyuan_migration/00_preflight.sh`
- `source /home/ubuntu/.openclaw-wecom-pg.env`
- `pg_dump`
- `createdb`
- `pg_restore`
- `python3 app.py health`
- `historical deprecated python3 app.py init-db-legacy`
- `python3 app.py run`
- `psql -f scripts/siyuan_migration/03_channel_backfill.sql`

## 3. 真实 env 与生产资产路径

只读 `ls /home/ubuntu` 显示：

- `/home/ubuntu/.openclaw-wecom-pg.env`：存在
- `/home/ubuntu/current-siyuan-crm`：不存在
- `/home/ubuntu/releases`：存在
- `/home/ubuntu/极简 crm`：存在，指向 `/home/ubuntu/releases/aicrm-laohuang-20260426144637`

只读 `ls /home/ubuntu/releases` 显示当前 release 目录：

- `aicrm-fb650be-manual-20260424094855`
- `aicrm-laohuang-20260426144637`

未在当前只读可见路径中发现 `/home/ubuntu/current-siyuan-crm` 或明确的 siyuan-crm 新 release 目录。

## 4. 当前 git 状态观察

受限通道的 `git-status` 输出指向现有生产 release，结果为：

- `## main...origin/main`
- 最近提交：
  - `19cdbcc5 Merge pull request #1136 from qianlan333/codex/p2-b3-user-ops-admin-pages-native`
  - `e58c0cb8 Migrate User Ops admin pages to native shell`
  - `c81b49e2 Merge pull request #1135 from qianlan333/codex/p2-b2-customer-detail-native-page`

这看起来是现有 AI-CRM 生产 release，而不是 `qianlan333/siyuan-crm` 的 PR #40/#41 演练目录。由于通道只读，无法在服务器上创建或更新 siyuan-crm 新 release。

## 5. 备份结果

未执行真实备份。

原因：

- 当前服务器入口禁止普通 shell 命令。
- 当前数据库连接用户是 `claude_ro`，只允许 SELECT。
- 无法 source `/home/ubuntu/.openclaw-wecom-pg.env`。
- 无法运行 `scripts/siyuan_migration/01_backup_current_assets.sh`。
- 无法运行 `pg_dump`。

因此未生成 dump、env backup 或 assets archive。

明确未执行事项：

- 未执行生产 `pg_dump`。
- 未创建或清理 `siyuancrm_next`。
- 未执行 `pg_restore`。
- 未执行 `python3 app.py health`。
- 未执行 `historical deprecated python3 app.py init-db-legacy`。
- 未执行 channel backfill。
- 未执行 smoke test。
- 未修改 systemd/nginx。

## 6. 恢复结果

未执行。

原因：

- 没有生产 dump 文件。
- 当前入口无法创建 `siyuancrm_next`。
- 当前入口无法执行 `pg_restore`。
- 当前入口不具备对显式 staging DB 执行 `CLEAN=true` 的权限。

没有对生产库执行 DROP、CLEAN 或 pg_restore。

## 7. health / schema 初始化结果

未执行。

原因：

- 未能拉取/进入服务器上的 siyuan-crm 新 release。
- 未能恢复 staging DB。
- 受限通道不能执行 `python3 app.py health` 或 `historical deprecated python3 app.py init-db-legacy`。

## 8. 渠道码 backfill 结果

未执行。

原因：

- 未恢复 staging DB。
- 当前只读 PostgreSQL 用户不能执行 backfill SQL。
- 未运行 `03_channel_backfill.sql` 和 `04_validate_migration.sql`。

## 9. 用户/侧边栏数据结果

未执行真实 staging 验证。

原因：

- 未恢复 production dump 到 `siyuancrm_next`。
- 当前只读通道不能启动 AI-CRM Next staging 服务。
- 未验证侧边栏 read model 或客户详情 API。

## 10. 后台 smoke test

未执行。

原因：

- 当前入口不能启动 staging 服务。
- 未配置 AI-CRM Next 连接 `siyuancrm_next`。

## 11. 授权配置 present/missing

未执行。

原因：

- 受限通道禁止读取 `.env` 文件内容。
- 按安全边界，没有打印任何真实 secret、token、AES key、数据库 URL 或私钥。

## 12. 风险结论

当前结论：不能进入生产切换窗口。

阻塞原因不是脚本或业务代码，而是当前可用服务器入口权限不足：

- 只有只读诊断通道。
- 数据库用户是 `claude_ro`，且事务只读。
- 无法执行 `pg_dump`、`createdb`、`pg_restore`、schema init、backfill 或服务启动。
- 当前服务器可见 release 目录不像 `qianlan333/siyuan-crm` 新 release。

当前不需要新开业务修复 PR；需要先提供可执行普通 shell 命令的预发服务器入口，或由有权限的运维人员在服务器上按迁移文档执行。

## 13. 继续演练所需条件

需要一个具备以下能力的服务器入口：

1. 可以进入 siyuan-crm 新 release 或演练目录。
2. 可以执行 `git fetch`、`git checkout main`、`git pull --ff-only origin main`。
3. 可以 source `/home/ubuntu/.openclaw-wecom-pg.env`，但执行记录中不得打印真实值。
4. 可以使用生产 `DATABASE_URL` 执行 `pg_dump`。
5. 可以创建或访问 staging DB `siyuancrm_next`。
6. 可以对 `siyuancrm_next` 执行 `pg_restore --clean --if-exists --no-owner`。
7. 可以运行 `python3 app.py health`、`python3 -m alembic upgrade head` 和 `python3 app.py run`；`init-db-legacy` 仅作为 historical deprecated 记录，不再是当前 startup 操作。
8. 可以只对 staging DB 执行 backfill 和 validate SQL。

## 14. 生产切换建议

本次未进入生产切换建议阶段。只有在真实 staging 演练全部通过后，才建议进入生产切换窗口：

1. 冻结写入入口或降低写入流量。
2. 做最终生产数据库/env/文件资产备份。
3. 部署新 release，但不提交真实 env、dump、uploads、pem/key。
4. 切 systemd/nginx 指向新 release。
5. 运行 `/health`、`/admin`、`/admin/channels`、`/api/admin/user-ops/overview` smoke test。
6. 观察企业微信 callback、渠道码 runtime diagnosis 和 5xx。
7. 异常时切回旧代码目录和旧 `DATABASE_URL`，必要时用最终备份恢复。
