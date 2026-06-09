# siyuan-crm AI-CRM Next 迁移文档

## 1. 迁移目标

本次迁移把 `siyuan-crm` 升级为 AI-CRM Next 产品形态。

迁移口径是：代码跟 AI-CRM，数据跟 siyuan，配置按 siyuan overlay 保留。仓库中只提交产品代码、迁移脚本、部署模板参考、文档和验收脚本，不导入 AI-CRM 生产数据，也不提交任何真实密钥。

## 2. 适用前提

- siyuan 当前数据较轻，适合先备份当前库，再恢复到 `siyuancrm_next` 预发库做升级验证。
- 主要保留 siyuan 当前渠道码、侧边栏用户基础数据、管理员/授权配置、微信/企微验证文件和文件资产。
- 不导入 AI-CRM 的生产数据、dump、上传文件或密钥。
- 不直接操作生产服务器；生产切换必须由人工按本文档执行。

## 3. 高层方案

1. 备份 siyuan 当前 PostgreSQL 数据库、env 文件和文件资产。
2. 新建 `siyuancrm_next` 预发库。
3. 使用 `pg_restore` 把当前 siyuan 备份恢复到预发库。
4. 使用 AI-CRM Next 新代码连接预发库。
5. 运行 `python3 app.py init-db-legacy` 做 legacy schema 初始化/升级。
6. 运行渠道码 backfill，补齐 `automation_channel_scene_alias` 和 `automation_channel_qrcode_asset`。
7. 校验 admin、channels、sidebar、user-ops、callback diagnosis 等关键入口。
8. 验证通过后，再按蓝绿方式切换生产。

## 4. 仓库比较结论

本 PR 以 `qianlan333/AI-CRM@main` 为产品代码基线，以 `qianlan333/siyuan-crm@main` 为客户数据和部署 overlay 来源。

比较结论：

- AI-CRM 的 `app.py` 已经默认使用 FastAPI / `aicrm_next.main:app`，`python3 app.py run` 会通过 uvicorn 启动 AI-CRM Next。
- AI-CRM 保留 `legacy_flask_app.py`，旧 Flask 只能通过显式 fallback 命令启动。
- siyuan-crm `main` 迁移前仍以旧 Flask / `wecom_ability_service.create_app()` 为主入口，且没有 `legacy_flask_app.py`。
- siyuan-crm 的客户侧部署资产和配置说明不能简单覆盖，包括 `.env.example`、`deploy/openclaw-*` systemd/timer 模板、`WW_verify_*.txt` / `MP_verify_*.txt` 验证文件、`xinliushangye.com` 相关回调配置说明，以及“心流商业客户管理”品牌文案。
- AI-CRM 必须整体带入的新模块包括 `aicrm_next/` FastAPI modular monolith、Next admin shell、admin auth/config/jobs、automation engine、channel entry、customer read model/sidebar v2、commerce/wechat pay/alipay、cloud orchestrator、group_ops、owner migration、radar links、media library、message archive、platform foundation，以及对应 migrations、schema、scripts 和测试契约。
- `deploy/` 本次保留 siyuan 原有部署语义；AI-CRM 的部署模板复制到 `deploy/aicrm-next/` 作为人工合并参考。
- `.env.example` 以 siyuan 原模板为底，补充 AI-CRM Next 新变量，并只保留占位说明。

## 5. 需要保留的资产清单

- PostgreSQL 数据库：保留 siyuan 当前生产数据，先备份，再恢复到 `siyuancrm_next` 预发库。
- env 文件：例如 `/home/ubuntu/.openclaw-wecom-pg.env`，必须备份，权限保持 `600`。
- 微信/企微验证文件：`WW_verify_*.txt`、`MP_verify_*.txt`。
- 文件资产：`uploads/`、`static/uploads/`、`instance/`。
- 私钥文件：`*.pem`、`*.key`，只保留在服务器安全路径，不进入 git。
- 企业微信和公众号平台后台配置：回调 URL、Token、EncodingAESKey、可信域名、OAuth 回调域名等。

如果新 release 目录没有实际验证文件，需要从旧生产目录复制回来，或确认 `wecom_ability_service/http/ops.py` 中的根路径验证文件处理逻辑仍能读取到它们。

## 6. 推荐执行命令

以下命令应在人工维护窗口内执行，且先对预发库操作。

数据库 URL 分两类使用：

- `DATABASE_URL` / `APP_DATABASE_URL`：给 Python 应用和 SQLAlchemy 使用，可以是 `postgresql+psycopg://...`。
- `PG_CLI_DATABASE_URL`：给 `psql`、`pg_dump`、`pg_restore` 使用，必须是 PostgreSQL CLI 可识别的 `postgresql://...` 或 `postgres://...`，可通过 `scripts/siyuan_migration/lib_db_url.sh` 从应用 URL 转换。

```bash
cd /path/to/siyuan-crm-next-release
source /home/ubuntu/.openclaw-wecom-pg.env
scripts/siyuan_migration/00_preflight.sh
```

备份当前生产资产：

```bash
BACKUP_DIR=/home/ubuntu/backups/siyuan-aicrm-migration \
ENV_FILE=/home/ubuntu/.openclaw-wecom-pg.env \
APP_DIR=/home/ubuntu/current-siyuan-crm \
scripts/siyuan_migration/01_backup_current_assets.sh
```

恢复到预发库：

```bash
DUMP_FILE=/home/ubuntu/backups/siyuan-aicrm-migration/siyuan-current-YYYYMMDD-HHMMSS.dump \
STAGING_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/siyuancrm_next' \
CLEAN=true \
scripts/siyuan_migration/02_restore_to_staging_db.sh
```

连接预发库并初始化/升级 schema：

```bash
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/siyuancrm_next'
source scripts/siyuan_migration/lib_db_url.sh
PG_CLI_DATABASE_URL="$(normalize_pg_cli_url "$DATABASE_URL")"

python3 app.py health
python3 app.py init-db-legacy
python3 app.py init-next-schema-safe
```

`init-next-schema-safe` 是 Alembic revision graph 治理完成前的预发/生产演练解阻路径。它只执行 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`，用于补齐 AI-CRM Next customer read model 与 User Ops SQL read model 缺失表，不会 `DROP`、`TRUNCATE` 或覆盖已有数据。也可以直接执行 SQL 文件：

```bash
psql "$PG_CLI_DATABASE_URL" -f scripts/siyuan_migration/06_safe_next_schema_init.sql
```

执行渠道码 backfill 和校验：

```bash
psql "$PG_CLI_DATABASE_URL" -f scripts/siyuan_migration/03_channel_backfill.sql
psql "$PG_CLI_DATABASE_URL" -f scripts/siyuan_migration/04_validate_migration.sql
psql "$PG_CLI_DATABASE_URL" -f scripts/siyuan_migration/07_validate_next_blockers.sql
```

启动服务后 smoke test：

```bash
BASE_URL=http://127.0.0.1:5001 \
SAMPLE_SCENE_VALUE='旧渠道码scene_value' \
SAMPLE_EXTERNAL_USERID='脱敏记录对应的旧external_userid' \
scripts/siyuan_migration/05_smoke_test.sh
```

## 7. 渠道码迁移说明

AI-CRM Next 的企业微信回调解析不只依赖旧 `automation_channel.scene_value`。为了支持历史二维码、二维码资产状态、回调诊断和后续重新生成二维码，需要补齐：

- `automation_channel_scene_alias`：记录 scene value 与 channel 的解析关系。
- `automation_channel_qrcode_asset`：记录当前二维码资产、config_id、qr_url 和生成来源。

`03_channel_backfill.sql` 会从 `automation_channel` 中 `scene_value` 非空的记录补齐这两张表：

- `provider_name` 使用 `wecom_contact_way`。
- `source` / `generation_source` 使用 `legacy_import_confirmed`。
- `status` 使用 `active`。
- `corp_id` 优先使用 `automation_channel.corp_id`，没有则为空字符串。
- `config_id` 优先使用 `automation_channel.config_id`，没有则 fallback 到 `qr_ticket`。
- `qr_url` 使用旧渠道表已有 `qr_url`。
- `created_by` 优先使用 `owner_staff_id`，没有则为空字符串。

脚本是幂等的：已有 active alias/asset 不会被覆盖，冲突时 `ON CONFLICT DO NOTHING`。

验证方式：

```bash
source scripts/siyuan_migration/lib_db_url.sh
PG_CLI_DATABASE_URL="$(normalize_pg_cli_url "$DATABASE_URL")"
psql "$PG_CLI_DATABASE_URL" -f scripts/siyuan_migration/04_validate_migration.sql
curl 'http://127.0.0.1:5001/api/admin/channels/runtime-diagnosis?scene_value=旧scene'
```

企业微信 callback 切换前，必须确认：

- 旧 scene value 在 runtime diagnosis 中可解析。
- callback path 与旧生产保持一致，优先不改企业微信后台 URL。
- `WECOM_CALLBACK_TOKEN` 和 `WECOM_CALLBACK_AES_KEY` 与平台后台一致。
- 切换前不要删除旧 release 和旧数据库。

## 8. Next schema 和生产仓库说明

AI-CRM Next 的 `CUSTOMER_READ_MODEL_REPO_BACKEND` 与 `USER_OPS_REPO_BACKEND` 在 PostgreSQL runtime 下必须使用 SQL/PostgreSQL backend。推荐显式设置：

```bash
CUSTOMER_READ_MODEL_REPO_BACKEND=sqlalchemy
USER_OPS_REPO_BACKEND=sqlalchemy
```

也可以使用 `postgres` / `postgresql` / `sql`。生产演练不应通过 `AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD=true` 放行 fixture 仓库。

如果 `/api/admin/user-ops/overview` 返回 `user_ops_schema_missing`，或 customer/sidebar 接口提示缺少 `customer_detail_snapshot_next` 等 Next 表，请先运行：

```bash
python3 app.py init-next-schema-safe
```

当前 Alembic revision graph 仍需后续专项治理：本次诊断显示 `0012`、`0016` 存在重复 revision，且 `0014_alipay_pay.py` 引用缺失的 `0013`。在 migration graph 修复前，不要让生产切换依赖 `alembic upgrade head`。

## 9. 授权配置保留说明

以下配置必须从 siyuan 生产 env 迁移或核对，不能从 AI-CRM 仓库复制真实值：

- `DATABASE_URL`
  - 应用运行可使用 `postgresql+psycopg://...`。
  - PostgreSQL CLI 工具需要使用 `normalize_pg_cli_url "$DATABASE_URL"` 得到的 `PG_CLI_DATABASE_URL`。
- `SECRET_KEY`
- `WECOM_CORP_ID`
- `WECOM_AGENT_ID`
- `WECOM_SECRET`
- `WECOM_CONTACT_SECRET`
- `WECOM_CALLBACK_TOKEN`
- `WECOM_CALLBACK_AES_KEY`
- `WECHAT_MP_APP_ID`
- `WECHAT_MP_APP_SECRET`
- `ADMIN_LOGIN_REDIRECT_URI`
- `CRM_API_TOKEN`
- `MCP_BEARER_TOKEN`
- `SIDEBAR_THIRD_PARTY_API_TOKEN`

品牌配置：

- 默认后台品牌为 `心流商业客户管理`。
- 如需覆盖，可设置 `AICRM_ADMIN_BRAND_NAME` 或 `ADMIN_BRAND_NAME`。
- 不建议在模板里硬编码多个互相冲突的品牌名。

## 10. 生产切换建议

推荐蓝绿切换：

1. 保留旧代码目录和旧库。
2. 新 release 目录连接 `siyuancrm_next` 预发库完成验证。
3. rsync 或复制验证文件、uploads、instance、pem/key 到新 release 或安全共享路径。
4. 确认域名、端口和 callback path 尽量不变。
5. 验收通过后，人工修改 systemd 指向新 release。
6. reload systemd 并重启服务。
7. 观察 `/health`、`/admin`、`/admin/channels`、企业微信 callback 日志和 5xx。

Nginx/systemd 的真实生产配置不在本 PR 中修改。当前 `deploy/` 保留 siyuan 原模板，`deploy/aicrm-next/` 只是 AI-CRM 模板参考，需要人工合并差异。

## 11. 回滚方案

如果新版本出现不可接受问题：

1. systemd 切回旧代码目录。
2. 切回旧 `DATABASE_URL`。
3. 如已改写生产库且必须恢复，用 `pg_restore` 从 `01_backup_current_assets.sh` 生成的 dump 恢复。
4. 复制回旧 env 和文件资产。
5. 回滚后检查：
   - `/health`
   - `/admin`
   - 企业微信 callback GET 校验
   - 企业微信 callback POST 日志
   - 旧渠道码二维码扫码链路

## 12. 验收清单

- `/health` 正常。
- `/admin` 正常，允许 302/401/403 登录态拦截，但不能 5xx。
- `/admin/channels` 能看到旧渠道码。
- 旧 `scene_value` 可通过 runtime diagnosis 解析。
- `automation_channel_scene_alias` 覆盖旧 scene。
- `automation_channel_qrcode_asset` 覆盖旧二维码资产。
- 侧边栏用户基础数据存在。
- `contacts` / `external_contact_bindings` / `people` 等基础表数据未丢。
- 后台管理员还能登录。
- 企微 token/aes key 配置未丢。
- 公众号 OAuth 配置未丢。
- 第三方侧边栏 API token 未丢。
- 微信/企微验证文件仍可访问。
- 无 5xx。
- 无 fixture mode 泄漏到生产。

## 12. 禁止事项

- 不提交真实 `.env` 文件。
- 不提交数据库 dump。
- 不提交真实 AccessToken、Secret、AESKey、AppSecret、私钥。
- 不导入 AI-CRM 生产数据。
- 不写脚本直接删除生产库。
- 不让脚本默认连接生产 `DATABASE_URL` 后执行破坏性操作。
- 不修改真实生产 systemd/nginx 配置。
- 不把 `uploads/`、`static/uploads/`、`instance/`、`*.pem`、`*.key` 加入 git。
