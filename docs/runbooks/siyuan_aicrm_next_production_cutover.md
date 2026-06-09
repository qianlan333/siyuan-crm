# siyuan AI-CRM Next 生产切换 Runbook

本文档用于 `siyuan-crm` 从当前生产 release 切换到 AI-CRM Next 基线。它只描述人工切换窗口内的操作、检查、回滚和验收口径，不包含任何真实密钥、数据库 URL、dump 或生产配置内容。

## 1. 切换目标

- 将 `siyuan-crm` 生产服务切换到 AI-CRM Next 产品基线。
- 保留 siyuan 当前生产数据、授权配置、渠道码、侧边栏基础用户数据、微信/企微验证文件和文件资产。
- 不导入 AI-CRM 的生产数据。
- 尽量保持域名、端口、企业微信 callback path、公众号 OAuth redirect path 不变。

## 2. 切换前置条件

切换窗口开始前，必须确认：

- PR #53 已完成并合并，真实 staging rehearsal 已通过 customer projection blocker。
- 最新 `main` 包含 `sync-customer-read-model`、`init-next-schema-safe` 和相关 validation/smoke 脚本。
- 有普通 SSH shell，不是只读诊断通道。
- `/home/ubuntu/.openclaw-wecom-pg.env` 存在，且由授权人员管理。
- 可以执行 `pg_dump`、`pg_restore`、`psql`。
- 可以访问当前生产 PostgreSQL。
- 可以写入目标生产库或新生产库。
- 能修改 systemd/nginx 的负责人已在切换窗口待命。
- 旧 release 目录存在且可快速切回。
- 最终备份目录可写，且不在 git 仓库内。
- 企业微信/公众号后台 callback 域名和路径已确认不变，或已准备同步修改方案。
- 当前生产资产目录已确认，例如 `/home/ubuntu/极简 crm`。

## 3. 冻结写入入口

切换窗口开始前，应冻结或降低以下写入入口：

- 企业微信客户回调。
- 渠道码新增/编辑。
- 订单/支付回调。
- 问卷提交。
- 自动化运营任务。
- 批量群发/队列任务。
- 后台配置保存。
- 侧边栏写入。

只读后台查看可以保留。如果不能冻结所有写入，必须记录风险窗口、可能丢失或延迟同步的数据类型，以及回补负责人。

## 4. 最终生产备份

备份命令只应由授权人员在生产服务器执行。不要打印完整 `DATABASE_URL`，不要打印 env 内容，不要把备份放到仓库里。

```bash
cd /home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609

set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a

BACKUP_DIR=/home/ubuntu/backups/siyuan-aicrm-cutover-final \
ENV_FILE=/home/ubuntu/.openclaw-wecom-pg.env \
APP_DIR="/home/ubuntu/极简 crm" \
scripts/siyuan_migration/01_backup_current_assets.sh
```

切换记录中只写：

- dump 文件路径。
- env backup 文件路径。
- assets archive 文件路径。
- 文件大小。
- 执行时间。

不得记录 env 内容、完整数据库 URL、密码、token、secret、AESKey、私钥、raw `external_userid` 或 raw `scene_value`。

## 5. 推荐切换策略

### 策略 A：新生产库切换，推荐

1. 最终冻结写入后，`pg_dump` 当前生产库。
2. 恢复到新生产库，例如 `siyuancrm_next_prod`，或经人工确认后的 `siyuancrm_next`。
3. 让 AI-CRM Next 新 release 临时连接新生产库。
4. 对新生产库执行 health、schema safe init、customer projection sync、channel backfill 和 validation。
5. 将 systemd env 指向新生产库。
6. 切换服务。
7. 保留旧生产库和旧 release 作为回滚路径。

该策略更安全，因为旧生产库没有被 schema 初始化、projection sync 或 backfill 写入；异常时优先切回旧 `DATABASE_URL` 和旧 release。

### 策略 B：原生产库原地升级，不推荐但可选

1. 最终备份后，直接在原生产库执行 `init-next-schema-safe`、customer projection sync 和 channel backfill。
2. 切换 systemd 到新 release。
3. 异常时需要使用最终 dump 恢复原生产库。

该策略风险更高，只适合无法准备新生产库时使用。选择该策略前必须明确回滚负责人、恢复耗时和写入冻结窗口。

## 6. 新生产库恢复与初始化命令

以下命令模板用于策略 A。`DATABASE_URL` 应指向目标新生产库，不是旧生产库。应用 URL 可以是 `postgresql+psycopg://...`；PostgreSQL CLI URL 通过 helper 转换，禁止在报告中打印完整 URL。

```bash
cd /home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609

set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a

export DATABASE_URL='<APP_TARGET_DATABASE_URL_FOR_NEW_PROD_DB>'
export APP_ENV=production
export DEPLOY_ENV=production
export AICRM_NEXT_ENV=production
export AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD=false
export USER_OPS_REPO_BACKEND=sqlalchemy
export CUSTOMER_READ_MODEL_REPO_BACKEND=sqlalchemy

source scripts/siyuan_migration/lib_db_url.sh
PG_CLI_TARGET_DATABASE_URL="$(normalize_pg_cli_url "$DATABASE_URL")"
```

恢复最终 dump 到目标新生产库：

```bash
DUMP_FILE=/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-current-YYYYMMDD-HHMMSS.dump \
STAGING_DATABASE_URL="$DATABASE_URL" \
CLEAN=true \
scripts/siyuan_migration/02_restore_to_staging_db.sh
```

初始化和同步：

```bash
python3 app.py health
python3 app.py init-db
python3 app.py init-next-schema-safe
python3 app.py sync-customer-read-model --dry-run
python3 app.py sync-customer-read-model

psql "$PG_CLI_TARGET_DATABASE_URL" -f scripts/siyuan_migration/03_channel_backfill.sql
psql "$PG_CLI_TARGET_DATABASE_URL" -f scripts/siyuan_migration/04_validate_migration.sql
psql "$PG_CLI_TARGET_DATABASE_URL" -f scripts/siyuan_migration/07_validate_next_blockers.sql
psql "$PG_CLI_TARGET_DATABASE_URL" -f scripts/siyuan_migration/08_validate_customer_projection.sql
```

`init-db` 当前只是兼容别名，仍建议同时执行 `init-next-schema-safe` 作为明确记录。不要使用 `init-db-legacy`。

## 7. systemd/nginx 切换检查

本 runbook 只提供 checklist，不自动修改真实文件。

切换前人工确认：

- systemd `ExecStart` 指向新 release。
- systemd `WorkingDirectory` 指向新 release。
- env 文件路径仍为 `/home/ubuntu/.openclaw-wecom-pg.env`，或已人工确认新 env 路径。
- env 中 `DATABASE_URL` 指向目标新生产库。
- `APP_HOST` / `APP_PORT` 保持不变。
- Nginx upstream 保持不变，或已与 `APP_HOST` / `APP_PORT` 同步调整。
- 企业微信 callback path 不变。
- 公众号 OAuth redirect path 不变。
- `WW_verify_*.txt` / `MP_verify_*.txt` 可访问。
- `uploads/`、`static/uploads/`、`instance/`、`*.pem`、`*.key` 已复制或挂载到新 release 的可用路径。
- 旧 release 目录和旧 env 可快速切回。

可选执行只读 readiness check。该脚本不修改 DB、systemd 或 nginx，不主动读取 env 文件内容；如果需要检查 env key 的 present/missing，请先由授权人员手动加载 env，再设置 `CHECK_CURRENT_ENV=true`。

```bash
BASE_URL=http://127.0.0.1:5001 \
ENV_FILE=/home/ubuntu/.openclaw-wecom-pg.env \
OLD_RELEASE_DIR="/home/ubuntu/极简 crm" \
NEW_RELEASE_DIR=/home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609 \
scripts/siyuan_migration/10_cutover_readiness_check.sh
```

## 8. 切换后 smoke test

切换后立即执行：

```bash
curl -i http://127.0.0.1:5001/health

BASE_URL=http://127.0.0.1:5001 \
SAMPLE_SCENE_VALUE='真实值用于请求，报告必须脱敏' \
scripts/siyuan_migration/05_smoke_test.sh

BASE_URL=http://127.0.0.1:5001 \
SAMPLE_EXTERNAL_USERID='真实值用于请求，报告必须脱敏' \
scripts/siyuan_migration/09_smoke_customer_projection.sh
```

还必须检查：

- `/admin`
- `/admin/channels`
- `/admin/customers`
- `/admin/config`
- `/admin/api-docs`
- `/api/admin/user-ops/overview`
- `/api/customers/{external_userid}`
- `/api/customers/{external_userid}/timeline`
- `/api/sidebar/customer-context`
- `/api/sidebar/profile`
- 企业微信 callback GET 校验。
- 企业微信 callback POST 日志。
- 旧渠道码扫码路径。
- 订单/问卷/侧边栏基础链路，如果当前生产启用。

判断规则：

- 任何 5xx 必须阻断。
- 登录态页面返回 302/401/403 可以接受。
- 对已 projected 的真实 `external_userid`，customer/sidebar 抽样必须 200。
- 旧 `scene_value` runtime diagnosis 必须 200 且 `ok=true`。
- 报告中所有 `external_userid`、`scene_value`、手机号、unionid、openid 必须脱敏。

## 9. 观察窗口

切换后建议至少覆盖一次真实扫码、侧边栏打开和后台查看。观察内容：

- 5xx 日志。
- 企业微信 callback 日志。
- PostgreSQL connection count。
- `/api/admin/user-ops/overview`。
- customer/sidebar API。
- channel runtime diagnosis。
- 最近新增客户归因。
- 自动化任务是否异常。
- 队列/worker 是否异常。

观察时长由人工决定；如不能完整覆盖真实业务动作，必须在切换报告中记录未覆盖项。

## 10. 回滚方案

### 快速回滚

1. systemd 切回旧 release。
2. env 切回旧 `DATABASE_URL`。
3. restart 服务。
4. 验证 `/health`、`/admin`、企业微信 callback。
5. 冻结写入直到确认旧链路稳定。

### 数据回滚

- 如果采用新生产库切换，优先只切回旧 `DATABASE_URL`，通常不需要恢复旧库。
- 如果已经写过原生产库，使用最终 cutover dump 恢复。
- 回滚后继续冻结写入，避免新旧库双写差异扩大。
- 回滚报告必须记录切回时间、旧/新 DB 标识、恢复命令结果和未回补数据窗口。

## 11. 切换 Go / No-Go 标准

### Go

- 最终备份完成。
- 新生产库 restore 成功。
- `python3 app.py health` 成功，`/health` 返回 200。
- `python3 app.py init-db` 成功。
- `python3 app.py init-next-schema-safe` 成功。
- `python3 app.py sync-customer-read-model` 成功。
- `customer_detail_snapshot_next > 0`。
- projection coverage against contacts 为 100%，或有明确解释和业务确认。
- `scene_alias_coverage=3/3`，或不低于 PR #53 staging rehearsal。
- `qrcode_asset_coverage=3/3`，或不低于 PR #53 staging rehearsal。
- `/api/admin/user-ops/overview` 返回 200。
- 至少一个真实但报告脱敏的 customer/sidebar 抽样返回 200。
- 核心 admin 页面无 5xx。
- callback path 已确认。
- 回滚负责人和旧 release 可用。

### No-Go

- 无最终备份。
- 生产 env 不完整。
- health 失败。
- init/schema 失败。
- customer projection 为空。
- customer/sidebar 对真实 projected `external_userid` 仍返回 404/400/503。
- `/api/admin/user-ops/overview` 返回 503。
- scene diagnosis 失败。
- 企业微信 callback path 不确定。
- 无回滚负责人。
- 旧 release 不可用。

## 12. 安全边界

- 不提交真实 `.env`。
- 不提交 dump。
- 不提交 uploads、instance、pem/key。
- 不记录完整 `DATABASE_URL`。
- 不记录密码、token、secret、AESKey、私钥。
- 不记录 raw `external_userid`、raw `scene_value`、手机号、unionid、openid。
- 不自动修改 systemd/nginx。
- 不在脚本中默认对生产库执行 `DROP`、`CLEAN`、`pg_restore`。
