# siyuan AI-CRM Next 生产切换 Runbook

本文档用于 `siyuan-crm` 从当前生产 release 切换到 AI-CRM Next 基线。它只描述人工切换窗口内的操作、检查、回滚和验收口径，不包含任何真实密钥、数据库 URL、dump 或生产配置内容。

## 1. 切换目标

- 将 `siyuan-crm` 生产服务切换到 AI-CRM Next 产品基线。
- 保留 siyuan 当前生产数据、授权配置、渠道码、侧边栏基础用户数据、微信/企微验证文件和文件资产。
- 不导入 AI-CRM 的生产数据。
- 尽量保持域名、端口、企业微信 callback path、公众号 OAuth redirect path 不变。

## 2. 切换前置条件

切换窗口开始前，必须确认：

- PR #77 restored staging rehearsal 已完成并合并，结论为 `PASS_WITH_NOTES`。
- PR #77 报告中的 restored staging DB 已完成 backup/restore/Alembic/safe init/customer projection/channel backfill/runtime schema/HTTP smoke。
- 最新 `main` 使用 AI-CRM Next-only `app.py`；siyuan 初始化和 customer projection 演练使用 `scripts/siyuan_migration/*` 独立 helper，不依赖旧 app.py CLI。
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
- 生产 env 已显式设置 `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live`，用于启用 AI-CRM Next 原生企业微信后台登录。
- 企业微信 corp/agent/credential key 组与 `ADMIN_LOGIN_REDIRECT_URI` 均存在，且 `ADMIN_LOGIN_REDIRECT_URI` 与企业微信后台配置的 `/auth/wecom/callback` 回调地址一致。
- external orders 生产启用前，授权人员必须配置 internal automation API token；如果 cutover 时暂不启用 external orders，则必须明确接受 `/api/external/orders` 返回受控 `503 internal_token_not_configured`。
- customer read model 和 user ops 的生产 repo backend 必须显式设为 SQL backend，或由 operator 在 cutover 前确认默认值安全。

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
4. 对新生产库执行 health、safe schema SQL、customer projection sync、channel backfill 和 validation。
5. 将 systemd env 指向新生产库。
6. 切换服务。
7. 保留旧生产库和旧 release 作为回滚路径。

该策略更安全，因为旧生产库没有被 schema 初始化、projection sync 或 backfill 写入；异常时优先切回旧 `DATABASE_URL` 和旧 release。

### 策略 B：原生产库原地升级，不推荐但可选

1. 最终备份后，直接在原生产库执行 `scripts/siyuan_migration/06_safe_next_schema_init.sql`、customer projection sync 和 channel backfill。
2. 切换 systemd 到新 release。
3. 异常时需要使用最终 dump 恢复原生产库。

该策略风险更高，只适合无法准备新生产库时使用。选择该策略前必须明确回滚负责人、恢复耗时和写入冻结窗口。

## 6. 新生产库恢复与初始化命令

以下命令模板用于策略 A。应用的 DB URL 应指向目标新生产库，不是旧生产库。PostgreSQL CLI URL 通过 helper 转换，禁止在报告中打印完整 URL。

```bash
cd /home/ubuntu/releases/siyuan-crm-aicrm-next-rehearsal-20260609

set -a
source /home/ubuntu/.openclaw-wecom-pg.env
set +a

# 由授权 operator 在 shell 中设置应用 DB URL，目标必须是新生产库。
# 不要在终端记录或报告中打印该值。
export APP_ENV=production
export DEPLOY_ENV=production
export AICRM_NEXT_ENV=production
export AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD=false
export AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live
export USER_OPS_REPO_BACKEND=sqlalchemy
export CUSTOMER_READ_MODEL_REPO_BACKEND=sqlalchemy

source scripts/siyuan_migration/lib_db_url.sh
PG_CLI_TARGET_DB_URL="$(normalize_pg_cli_url "$APP_TARGET_DB_URL")"
```

恢复最终 dump 到目标新生产库：

```bash
export DUMP_FILE=/home/ubuntu/backups/siyuan-aicrm-cutover-final/siyuan-current-YYYYMMDD-HHMMSS.dump
export APP_TARGET_DB_URL='<set-by-authorized-operator-without-printing>'
export CLEAN=true
scripts/siyuan_migration/02_restore_to_staging_db.sh
```

The restore helper uses `pg_restore --no-owner --no-acl` so source-role ACL statements from the dump do not block restore into the target database.

初始化和同步：

```bash
python3 app.py health

psql "$PG_CLI_TARGET_DB_URL" -f scripts/siyuan_migration/06_safe_next_schema_init.sql
python3 scripts/siyuan_migration/sync_customer_read_model.py --dry-run
python3 scripts/siyuan_migration/sync_customer_read_model.py --execute
psql "$PG_CLI_TARGET_DB_URL" -f scripts/siyuan_migration/03_channel_backfill.sql
psql "$PG_CLI_TARGET_DB_URL" -f scripts/siyuan_migration/04_validate_migration.sql
psql "$PG_CLI_TARGET_DB_URL" -f scripts/siyuan_migration/07_validate_next_blockers.sql
psql "$PG_CLI_TARGET_DB_URL" -f scripts/siyuan_migration/08_validate_customer_projection.sql
```

`app.py` 保持 AI-CRM Next-only runtime 入口。不要使用 `python3 app.py init-db`、`python3 app.py init-next-schema-safe` 或 `python3 app.py sync-customer-read-model` 作为 PR-12/PR-13 的迁移入口。

`06_safe_next_schema_init.sql` includes the runtime v2 and commerce audit safety guard tables validated in PR #77:

- `automation_event_v2`
- `automation_membership_v2`
- `automation_stage_entry_v2`
- `automation_task_plan_v2`
- `wechat_shop_refunds`
- `wechat_shop_sync_runs`

企业微信后台登录预检：

```bash
curl -i "http://127.0.0.1:5001/auth/wecom/callback"
curl -i "http://127.0.0.1:5001/auth/wecom/callback?code=dummy&state=dummy"
curl -i "http://127.0.0.1:5001/auth/wecom/start?mode=qr&next=/admin"
```

预期：

- 缺少 `code` 返回 `400 missing_wecom_code`。
- dummy `code/state` 返回 `400 invalid_or_expired_state`，不能再出现 `503 external_call_blocked`。
- live 模式且配置完整时，`/auth/wecom/start` 返回 302 企业微信授权地址。
- 正式切换窗口必须至少完成一次真实企业微信授权登录，确认可进入 `/admin` 且 session cookie 生效。

## 7. systemd/nginx 切换检查

本 runbook 只提供 checklist，不自动修改真实文件。

切换前人工确认：

- systemd `ExecStart` 指向新 release。
- systemd `WorkingDirectory` 指向新 release。
- env 文件路径仍为 `/home/ubuntu/.openclaw-wecom-pg.env`，或已人工确认新 env 路径。
- env 中应用 DB URL 指向目标新生产库。
- external orders token decision 已明确：配置 token 后启用，或批准 cutover 时 external orders 暂保持受控不可用。
- `APP_HOST` / `APP_PORT` 保持不变。
- Nginx upstream 保持不变，或已与 `APP_HOST` / `APP_PORT` 同步调整。
- 企业微信 callback path 不变。
- 企业微信后台授权登录回调仍为 `/auth/wecom/callback`，并且企业微信后台配置的可信域名/回调地址与 `ADMIN_LOGIN_REDIRECT_URI` 一致。
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
- 企业微信后台登录 `/auth/wecom/start` 和 `/auth/wecom/callback`。
- external orders missing-token 或 authorized-token 行为，取决于 cutover 前 token decision。
- 旧渠道码扫码路径。
- 订单/问卷/侧边栏基础链路，如果当前生产启用。

判断规则：

- 任何 5xx 必须阻断。
- 登录态页面返回 302/401/403 可以接受。
- 对已 projected 的真实 `external_userid`，customer/sidebar 抽样必须 200。
- 旧 `scene_value` runtime diagnosis 必须 200 且 `ok=true`。
- `/auth/wecom/callback` 缺少 `code` 必须返回 400，不得返回 `external_call_blocked`。
- `/auth/wecom/callback?code=dummy&state=dummy` 必须返回 `400 invalid_or_expired_state`，不得签发 session。
- `/auth/wecom/start?mode=qr&next=/admin` 在 live 模式下必须 302 到企业微信授权地址。
- 至少一次真实企业微信后台登录必须成功进入 `/admin`。
- 报告中所有 `external_userid`、`scene_value`、手机号、unionid、openid 必须脱敏。

## 9. 观察窗口

切换后建议至少覆盖一次真实扫码、侧边栏打开和后台查看。观察内容：

- 5xx 日志。
- 企业微信 callback 日志。
- 企业微信后台登录成功率和重复登录情况。
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
2. env 切回旧应用 DB URL。
3. restart 服务。
4. 验证 `/health`、`/admin`、企业微信 callback。
5. 冻结写入直到确认旧链路稳定。

### 数据回滚

- 如果采用新生产库切换，优先只切回旧应用 DB URL，通常不需要恢复旧库。
- 如果已经写过原生产库，使用最终 cutover dump 恢复。
- 回滚后继续冻结写入，避免新旧库双写差异扩大。
- 回滚报告必须记录切回时间、旧/新 DB 标识、恢复命令结果和未回补数据窗口。

## 11. 切换 Go / No-Go 标准

### Go

- 最终备份完成。
- 新生产库 restore 成功。
- `python3 app.py health` 成功，`/health` 返回 200。
- `scripts/siyuan_migration/06_safe_next_schema_init.sql` 成功。
- `scripts/siyuan_migration/sync_customer_read_model.py` dry-run 和正式执行成功。
- `customer_detail_snapshot_next > 0`。
- projection coverage against contacts 为 100%，或有明确解释和业务确认。
- `scene_alias_coverage` 不低于 PR #77 restored staging rehearsal。
- `qrcode_asset_coverage` 不低于 PR #77 restored staging rehearsal。
- `/api/admin/user-ops/overview` 返回 200。
- 至少一个真实但报告脱敏的 customer/sidebar 抽样返回 200。
- 核心 admin 页面无 5xx。
- callback path 已确认。
- `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live`。
- 企业微信 corp/agent/credential key 组与 `ADMIN_LOGIN_REDIRECT_URI` 均存在。
- `ADMIN_LOGIN_REDIRECT_URI` 与企业微信后台回调配置一致。
- `/auth/wecom/start?mode=qr&next=/admin` live 模式返回 302 企业微信授权地址。
- `/auth/wecom/callback` 缺少 code 返回 400。
- `/auth/wecom/callback?code=dummy&state=dummy` 返回 400 invalid state，不再返回 `external_call_blocked`。
- 至少一次真实企业微信后台登录回调通过，或由切换负责人在窗口内人工确认并记录。
- external orders 如需立即启用，则 internal automation API token 已配置；否则业务已批准 external orders 暂时以受控 503 不可用。
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
- `AICRM_NEXT_WECOM_ADMIN_AUTH_MODE` 未设为 `live`。
- 企业微信后台登录配置缺失。
- `/auth/wecom/callback` 仍返回 `503 external_call_blocked`。
- `/auth/wecom/start` 无法生成企业微信授权跳转。
- 真实企业微信后台登录无法进入 `/admin`，且没有被批准的人工缓解方案。
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
